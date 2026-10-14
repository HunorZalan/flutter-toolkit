"""Keep the host machine awake while long jobs are running.

The web UI server holds an OS-level "do not sleep" request while this is switched on.
Unlike the browser's Screen Wake Lock API it does not depend on the browser tab being
visible, and it protects the build processes and the WebSocket connection themselves
(a sleeping machine is what produces "Connection lost" / "Connection failed" halfway
through a build).

Backends
  * Windows : SetThreadExecutionState (system + display), held by a dedicated thread
              because the execution state belongs to the thread that set it.
  * macOS   : ``caffeinate -di -w <server pid>`` (exits together with the server).
  * Linux   : ``systemd-inhibit ... tail --pid=<server pid> -f /dev/null``.

None of them can stop a sleep the user triggers on purpose (closing the lid, power button).
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from typing import Callable, Optional

log = logging.getLogger("ftk.server")

__all__ = ["KeepAwake"]


class _Backend:
    name = "none"

    def available(self) -> bool:
        return False

    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        """Release the request. Must be safe to call repeatedly."""

    def alive(self) -> bool:
        return False


class _WindowsBackend(_Backend):
    name = "windows"
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001
    ES_DISPLAY_REQUIRED = 0x00000002

    def __init__(self, kernel32=None) -> None:
        self._k32 = kernel32  # injectable for tests
        self._thread: Optional[threading.Thread] = None
        self._release = threading.Event()
        self._ready = threading.Event()
        self._error = ""

    def available(self) -> bool:
        return self._k32 is not None or sys.platform == "win32"

    @staticmethod
    def _load_kernel32():
        import ctypes

        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        k32.SetThreadExecutionState.argtypes = [ctypes.c_uint]
        k32.SetThreadExecutionState.restype = ctypes.c_uint
        return k32

    def start(self) -> None:
        k32 = self._k32 or self._load_kernel32()
        self._release.clear()
        self._ready.clear()
        self._error = ""
        self._thread = threading.Thread(
            target=self._hold, args=(k32,), name="ftk-keep-awake", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(5):
            raise RuntimeError("keep-awake thread did not start")
        if self._error:
            raise RuntimeError(self._error)

    def _hold(self, k32) -> None:
        flags = self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED | self.ES_DISPLAY_REQUIRED
        held = False
        try:
            k32.SetThreadExecutionState(flags)
            # The call returns the *previous* state, so a second call proves the first one worked.
            held = bool(k32.SetThreadExecutionState(flags))
            if not held:
                self._error = "SetThreadExecutionState failed"
        except Exception as exc:  # noqa: BLE001
            self._error = f"SetThreadExecutionState: {exc}"
        finally:
            self._ready.set()
        if not held:
            return
        self._release.wait()
        try:
            k32.SetThreadExecutionState(self.ES_CONTINUOUS)
        except Exception:  # noqa: BLE001
            pass

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            self._release.set()
            thread.join(2)

    def alive(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._release.is_set()


class _ProcessBackend(_Backend):
    """A helper process that holds the inhibitor for as long as it lives."""

    def __init__(self, name: str, argv: Callable[[], list], probe: Callable[[], bool]) -> None:
        self.name = name
        self._argv = argv
        self._probe = probe
        self._proc: Optional[subprocess.Popen] = None

    def available(self) -> bool:
        try:
            return bool(self._probe())
        except Exception:  # noqa: BLE001
            return False

    def start(self) -> None:
        argv = self._argv()
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            code = self._proc.wait(timeout=0.4)  # a healthy inhibitor keeps running
        except subprocess.TimeoutExpired:
            return
        self._proc = None
        raise RuntimeError(f"{argv[0]} exited immediately (code {code})")

    def stop(self) -> None:
        proc, self._proc = self._proc, None
        if proc is None:
            return
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)  # session leader: pgid == pid
            except (OSError, AttributeError):
                proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        else:
            proc.wait()  # reap

    def alive(self) -> bool:
        proc = self._proc
        return proc is not None and proc.poll() is None


def _default_backend() -> _Backend:
    if sys.platform == "win32":
        return _WindowsBackend()
    if sys.platform == "darwin":
        return _ProcessBackend(
            "caffeinate",
            lambda: ["caffeinate", "-di", "-w", str(os.getpid())],
            lambda: shutil.which("caffeinate") is not None,
        )
    return _ProcessBackend(
        "systemd-inhibit",
        lambda: [
            "systemd-inhibit", "--what=idle:sleep", "--who=Flutter Toolkit",
            "--why=Long-running command", "--mode=block",
            "tail", f"--pid={os.getpid()}", "-f", "/dev/null",
        ],
        lambda: shutil.which("systemd-inhibit") is not None and shutil.which("tail") is not None,
    )


class KeepAwake:
    """Thread-safe on/off switch around one backend.

    ``auto_off`` means "until the running (or next) command finishes": the server calls
    :meth:`release_if_auto` whenever a command ends.
    """

    def __init__(self, backend: Optional[_Backend] = None) -> None:
        self._backend = backend if backend is not None else _default_backend()
        self._lock = threading.RLock()
        self._active = False
        self.auto_off = False
        self.error = ""
        atexit.register(self.disable)

    def enable(self, auto_off: bool = False) -> bool:
        with self._lock:
            self.auto_off = bool(auto_off)
            if self._active and self._backend.alive():
                return True
            self._active = False
            if not self._backend.available():
                self.error = f"Keep-awake is not available on this host ({self._backend.name})."
                self.auto_off = False
                return False
            try:
                self._backend.start()
            except Exception as exc:  # noqa: BLE001
                self.error = str(exc)
                self.auto_off = False
                log.warning("Keep-awake could not start: %s", exc)
                return False
            self._active = True
            self.error = ""
            log.info("Keep-awake ON via %s%s", self._backend.name,
                     " (until the run finishes)" if self.auto_off else "")
            return True

    def disable(self) -> None:
        with self._lock:
            was = self._active
            self._active = False
            self.auto_off = False
            try:
                self._backend.stop()
            except Exception as exc:  # noqa: BLE001
                log.warning("Keep-awake release failed: %s", exc)
            if was:
                log.info("Keep-awake OFF")

    def release_if_auto(self) -> bool:
        """Release when it was requested "until the run finishes". Returns True if released."""
        with self._lock:
            if self._active and self.auto_off:
                self.disable()
                return True
            return False

    def status(self) -> dict:
        with self._lock:
            if self._active and not self._backend.alive():
                self._active = False
                self.auto_off = False
                self.error = self.error or "The keep-awake helper stopped unexpectedly."
            return {
                "supported": self._backend.available(),
                "active": self._active,
                "auto_off": self.auto_off if self._active else False,
                "backend": self._backend.name,
                "error": self.error,
            }
