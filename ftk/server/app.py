"""FastAPI app factory for flutter-toolkit."""
from __future__ import annotations
import asyncio
import logging
import os
import signal
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Annotated

try:
    from fastapi import Body, FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from pydantic import BaseModel
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "FastAPI is required. Install flutter-toolkit with: pip install 'flutter-toolkit[all]'"
    ) from exc

from ftk.config import ProjectConfig, load_config, BackupConfig
from ftk.projects import list_projects, find_project, set_last_project_id
from ftk.server.commands_config import build as build_commands_config, COMMAND_ORDER


UI_DIR = Path(__file__).resolve().parent / "ui"
IS_WINDOWS = sys.platform == "win32"
_PLATFORM_LABEL: dict[str, str] = {"win32": "Windows", "darwin": "macOS"}
_PROMPT_TIMEOUT = 0.15
_background_tasks: set[asyncio.Task] = set()
MAX_RUNTIME = int(os.environ.get("FTK_TIMEOUT", os.environ.get("TOOLKIT_TIMEOUT", "3600")))


class _ProjectSelect(BaseModel):
    id: str


class _NoteBody(BaseModel):
    content: str


def _setup_logger(log_dir: Path) -> logging.Logger:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "server.log"
    logger = logging.getLogger("ftk.server")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fh = RotatingFileHandler(log_file, maxBytes=1_048_576, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    sh = logging.StreamHandler()
    sh.setLevel(logging.INFO)
    sh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def _is_prompt(text: str) -> bool:
    t = text.strip().lower()
    return any(t.endswith(s) for s in (
        "[y/n]", "[y/n]:", "(y/n)", "(y/n):", "[yes/no]", "[yes/no]:",
    ))


def _clean_prompt(text: str) -> str:
    text = text.strip()
    for suffix in ("[y/n]:", "[y/n]", "(y/n):", "(y/n)",
                   "[Y/n]:", "[Y/n]", "(Y/n):", "(Y/n)",
                   "[y/N]:", "[y/N]", "(y/N):", "(y/N)",
                   "[Y/N]:", "[Y/N]", "(Y/N):", "(Y/N)",
                   "[yes/no]:", "[yes/no]", "(yes/no):", "(yes/no)"):
        if text.lower().endswith(suffix.lower()):
            text = text[:-len(suffix)]
            break
    return text.rstrip()


def _terminate_process_group(pgid: int) -> None:
    """Send SIGTERM to *pgid*.

    Callers MUST verify that *pgid* differs from the server's own PID
    before invoking this helper.  The subprocess is started with
    ``start_new_session=True`` so it always owns a dedicated group.
    """
    os.killpg(pgid, signal.SIGTERM)  # NOSONAR — pgid is verified != server PID by caller


def _kill_proc(proc) -> None:
    """Kill a subprocess and its children."""
    try:
        if IS_WINDOWS:
            proc.kill()
        else:
            pgid = os.getpgid(proc.pid)
            if pgid == os.getpid():
                proc.kill()
            else:
                _terminate_process_group(pgid)
    except OSError:
        pass


def _stop_proc(proc_holder: list) -> None:
    if proc_holder[0]:
        _kill_proc(proc_holder[0])
        proc_holder[0] = None


_WIN_TASK_NAME = "FlutterToolkitServer"
_MAC_LAUNCHD_LABEL = "com.flutter-toolkit.server"
_LINUX_SYSTEMD_UNIT = "flutter-toolkit.service"


def _bounce_windows_supervisor(logger: logging.Logger) -> bool:
    r = subprocess.run(
        ["schtasks", "/Query", "/TN", _WIN_TASK_NAME],
        capture_output=True, shell=False, timeout=5,
    )
    if r.returncode != 0:
        return False
    cmd = (
        f'timeout /t 1 /nobreak >nul & '
        f'schtasks /End /TN "{_WIN_TASK_NAME}" >nul 2>&1 & '
        f'timeout /t 1 /nobreak >nul & '
        f'schtasks /Run /TN "{_WIN_TASK_NAME}" >nul 2>&1'
    )
    subprocess.Popen(
        f'cmd /c "{cmd}"',
        creationflags=(subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP),
        close_fds=True, shell=True,
    )
    logger.info("Bouncing scheduled task %s for restart", _WIN_TASK_NAME)
    os._exit(0)


def _bounce_macos_supervisor(logger: logging.Logger) -> bool:
    label = f"gui/{os.getuid()}/{_MAC_LAUNCHD_LABEL}"
    r = subprocess.run(["launchctl", "print", label], capture_output=True, timeout=5)
    if r.returncode != 0:
        return False
    subprocess.Popen(
        ["launchctl", "kickstart", "-k", label],
        start_new_session=True, close_fds=True,
    )
    logger.info("Kickstarting launchd agent %s for restart", label)
    os._exit(0)


def _bounce_linux_supervisor(logger: logging.Logger) -> bool:
    r = subprocess.run(
        ["systemctl", "--user", "is-active", _LINUX_SYSTEMD_UNIT],
        capture_output=True, timeout=5,
    )
    if r.stdout.strip() != b"active":
        return False
    subprocess.Popen(
        ["systemctl", "--user", "restart", _LINUX_SYSTEMD_UNIT],
        start_new_session=True, close_fds=True,
    )
    logger.info("Restarting systemd unit %s", _LINUX_SYSTEMD_UNIT)
    os._exit(0)


def _try_bounce_supervisor(logger: logging.Logger) -> bool:
    """Attempt to bounce the OS-level supervisor. Returns True if bounced."""
    try:
        if IS_WINDOWS:
            return _bounce_windows_supervisor(logger)
        if sys.platform == "darwin":
            return _bounce_macos_supervisor(logger)
        return _bounce_linux_supervisor(logger)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.warning("Supervisor bounce failed (%s); falling back to in-process re-exec", exc)
        return False


def _restart_server(logger: logging.Logger) -> None:
    """Restart the running server in place."""
    if not _try_bounce_supervisor(logger):
        new_args = [sys.executable, "-m", "ftk"] + sys.argv[1:]
        logger.info("Re-executing in place: %s", " ".join(new_args))
        os.execv(sys.executable, new_args)


class _State:
    """Per-app mutable state (active command + current project config)."""
    def __init__(self, cfg: ProjectConfig):
        self.cfg = cfg
        self.active_client: int | None = None
        self.active_command: str | None = None


def _build_allowlist(command_cfg: dict) -> set[str]:
    allowed: set[str] = set()
    for grp in command_cfg.get("groups", []):
        for opt in grp.get("options", []) or []:
            if opt.get("disabled"):
                continue
            for token in str(opt.get("flag", "")).split():
                allowed.add(token)
    for token in command_cfg.get("inject_flags", []) or []:
        allowed.add(token)
    return allowed


_BACKUP_FORMATS = {"zip", "7z", "tar.gz", "tar.bz2", "tar.xz", "tar.zst", "tar"}
_BACKUP_BOOL = {"--yes", "-y", "--dry-run", "--no-default-excludes"}


def _validate_format_arg(args: list[str], i: int) -> int:
    if i >= len(args) or args[i] not in _BACKUP_FORMATS:
        return -1
    return i + 1


def _validate_exclude_arg(args: list[str], i: int) -> int:
    consumed = 0
    while i < len(args) and not args[i].startswith("-"):
        v = args[i]
        if "/" in v or "\\" in v or ".." in v:
            return -1
        i += 1
        consumed += 1
    if consumed == 0:
        return -1
    return i


def _validate_keep_arg(args: list[str], i: int) -> int:
    if i >= len(args) or not args[i].isdigit():
        return -1
    n = int(args[i])
    if n < 1 or n > 1000:
        return -1
    return i + 1


def _validate_backup_args(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]; i += 1
        if a == "--format":
            i = _validate_format_arg(args, i)
        elif a == "--exclude":
            i = _validate_exclude_arg(args, i)
        elif a == "--keep":
            i = _validate_keep_arg(args, i)
        elif a not in _BACKUP_BOOL:
            return False
        if i < 0:
            return False
    return True


def _prepare_command(cfg: ProjectConfig, commands_config: dict, command: str, args: list[str]) -> tuple | None:
    if command not in commands_config:
        return None
    block = commands_config[command]
    if block.get("disabled"):
        return None
    script = block.get("script") or ""
    if not script:
        return None
    if command == "backup":
        if not _validate_backup_args(args):
            return None
        merged = args
    else:
        allowed = _build_allowlist(block)
        for a in args:
            if a not in allowed:
                return None
        inject = block.get("inject_flags", []) or []
        merged = [f for f in inject if f not in args] + args
    py = sys.executable
    cmd = [py, "-m", "ftk", "--root", cfg.root, script, *merged]
    return cmd, merged, script


async def _read_line_or_prompt(stream) -> tuple[bytes, bool]:
    """Read one line from *stream*, or as much as arrived within *timeout*."""
    buf = b""
    try:
        while True:
            ch = await asyncio.wait_for(stream.read(1), timeout=_PROMPT_TIMEOUT)
            if not ch:
                return buf, True
            if ch in (b"\n", b"\r"):
                return buf, False
            buf += ch
    except asyncio.TimeoutError:
        return buf, False


async def _heartbeat(ws: WebSocket) -> None:
    while True:
        await asyncio.sleep(30)
        try:
            await ws.send_json({"type": "info", "data": "Working..."})
        except Exception:
            break


async def _drain_output(proc, ws: WebSocket, skip_prompts: bool, prompt_queue: asyncio.Queue) -> None:
    while True:
        raw, eof = await _read_line_or_prompt(proc.stdout)
        if eof and not raw:
            return
        text = raw.decode("utf-8", errors="replace").rstrip("\r")
        if not text:
            continue
        if skip_prompts or not _is_prompt(text):
            await ws.send_json({"type": "output", "data": text})
            continue
        await ws.send_json({"type": "prompt", "data": _clean_prompt(text)})
        answer = await prompt_queue.get()
        proc.stdin.write((answer + "\n").encode())
        await proc.stdin.drain()


async def _run_and_drain(proc, ws: WebSocket, command: str, merged: list, start: float, prompt_queue: asyncio.Queue) -> None:
    skip_prompts = "--yes" in merged or "-y" in merged
    try:
        await asyncio.wait_for(
            _drain_output(proc, ws, skip_prompts, prompt_queue),
            timeout=MAX_RUNTIME,
        )
    except asyncio.TimeoutError:
        _kill_proc(proc)
        await ws.send_json({"type": "error", "data": f"Timed out after {MAX_RUNTIME}s (set FTK_TIMEOUT to override)"})
        await ws.send_json({"type": "exit", "code": -1, "duration": MAX_RUNTIME})
        return
    code = await proc.wait()
    duration = round(time.monotonic() - start, 1)
    await ws.send_json({"type": "exit", "code": code, "duration": duration})
    await ws.send_json({
        "type": "notify",
        "title": f"{'Done' if code == 0 else 'Failed'}: {command}",
        "body": f"Exit code {code} ({duration}s)",
    })


def _serve_ui_file(name: str, mime: str) -> Response:
    path = UI_DIR / name
    if not path.exists():
        return Response(status_code=404)
    return Response(content=path.read_bytes(), media_type=mime)


def _get_default_excludes(cfg: ProjectConfig) -> set[str]:
    backup_cfg = cfg.integrations.backup
    if backup_cfg and backup_cfg.default_excludes:
        return set(backup_cfg.default_excludes)
    return set(BackupConfig().default_excludes)

# WebSocket session
class _WebSocketSession:
    """Manages the full lifecycle of a single WebSocket connection."""

    def __init__(self, ws: WebSocket, state: _State) -> None:
        self._ws = ws
        self._state = state
        self._proc_holder: list = [None]
        self._prompt_queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def handle(self) -> None:
        await self._ws.accept()
        try:
            while True:
                data = await self._ws.receive_json()
                await self._dispatch(data)
        except WebSocketDisconnect:
            self._cancel_task_and_proc()

    async def _dispatch(self, data: dict) -> None:
        action = data.get("action", "")
        if action == "run":
            await self._handle_run(data)
        elif action == "stop":
            await self._handle_stop()
        elif action == "answer":
            await self._prompt_queue.put(data.get("value", "n"))

    async def _handle_run(self, data: dict) -> None:
        if self._task and not self._task.done():
            await self._ws.send_json({"type": "info", "data": "A process is already running."})
            return
        self._task = asyncio.create_task(
            self._stream(data.get("command", ""), data.get("args", []) or [])
        )

    async def _handle_stop(self) -> None:
        self._cancel_task_and_proc()
        self._task = None
        await self._ws.send_json({"type": "stopped", "data": "Process stopped."})

    def _cancel_task_and_proc(self) -> None:
        _stop_proc(self._proc_holder)
        if self._task and not self._task.done():
            self._task.cancel()

    async def _stream(self, command: str, args: list) -> None:
        commands_config = build_commands_config(self._state.cfg)
        prepared = _prepare_command(self._state.cfg, commands_config, command, args)
        if prepared is None:
            await self._ws.send_json({"type": "error", "data": f"Invalid command: {command}"})
            return
        if self._state.active_client not in (None, id(self._ws)):
            await self._ws.send_json({"type": "error", "data": f"Busy: {self._state.active_command}"})
            return
        self._state.active_client = id(self._ws)
        self._state.active_command = command
        cmd, merged, _ = prepared
        await self._execute(cmd, merged, command)

    async def _execute(self, cmd: list, merged: list, command: str) -> None:
        start = time.monotonic()
        display = " ".join(["ftk", command, *merged])
        await self._ws.send_json({"type": "start", "data": f"$ {display}"})
        hb = asyncio.create_task(_heartbeat(self._ws))
        try:
            await self._run_process(cmd, merged, command, start)
        except asyncio.CancelledError:
            await self._handle_cancelled()
            raise
        finally:
            hb.cancel()
            self._proc_holder[0] = None
            self._state.active_client = None
            self._state.active_command = None

    async def _run_process(self, cmd: list, merged: list, command: str, start: float) -> None:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=self._state.cfg.root,
            env={**os.environ, "NO_COLOR": "1", "PYTHONUNBUFFERED": "1"},
            **({"start_new_session": True} if not IS_WINDOWS else {}),
        )
        self._proc_holder[0] = proc
        await _run_and_drain(proc, self._ws, command, merged, start, self._prompt_queue)

    async def _handle_cancelled(self) -> None:
        _stop_proc(self._proc_holder)
        try:
            await self._ws.send_json({"type": "exit", "code": -1, "duration": 0})
        except Exception:
            pass

# HTTP route handlers
class _AppHandlers:
    """Groups all HTTP route handlers; holds shared state references."""

    def __init__(self, state: _State, logger: logging.Logger) -> None:
        self._state = state
        self._logger = logger

    # -- Static routes -------------------------------------------------------

    async def index(self) -> HTMLResponse:
        p = UI_DIR / "ui.html"

        if not p.exists():
            return HTMLResponse("<h1>ui.html missing</h1>", status_code=500)

        content = await asyncio.to_thread(p.read_text, encoding="utf-8")
        return HTMLResponse(content)

    def css(self) -> Response:
        return _serve_ui_file("ui.css", "text/css; charset=utf-8")

    def js(self) -> Response:
        return _serve_ui_file("ui.js", "application/javascript; charset=utf-8")

    def favicon(self) -> Response:
        p = UI_DIR / "favicon.ico"
        if p.exists():
            return Response(content=p.read_bytes(), media_type="image/x-icon")

        svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            '<rect rx="6" width="32" height="32" fill="#2563eb"/>'
            '<text x="50%" y="73%" text-anchor="middle" fill="white" font-size="18" '
            'font-weight="bold" font-family="system-ui">FT</text></svg>'
        )
        return Response(content=svg.encode(), media_type="image/svg+xml")

    # -- API routes ----------------------------------------------------------

    def api_status(self) -> dict:
        return {
            "busy": self._state.active_client is not None,
            "command": self._state.active_command,
        }

    def api_health(self) -> dict:
        return {
            "status": "ok",
            "uptime": time.monotonic(),
            "project": self._state.cfg.root,
        }

    def api_config(self) -> dict:
        platform = _PLATFORM_LABEL.get(sys.platform, "Linux")
        commands = build_commands_config(self._state.cfg)
        cfg = self._state.cfg

        return {
            "commands": commands,
            "project": {
                "id": cfg.id,
                "name": cfg.name,
                "root": cfg.root,
                "has_flavors": cfg.has_flavors,
                "flavors": [f.name for f in cfg.flavors],
                "default_flavor": cfg.default_flavor,
                "languages": cfg.languages,
            },
            "project_root": cfg.root,
            "platform": platform,
            "python": "python" if IS_WINDOWS else "python3",
        }

    def api_projects(self) -> dict:
        items = [
            {"id": p.id, "name": p.name, "root": p.root, "active": p.active}
            for p in list_projects()
        ]
        return {"projects": items, "active": self._state.cfg.id}

    async def api_select_project(
        self,
        body: Annotated[_ProjectSelect, Body(...)]
    ):
        entry = find_project(body.id)

        if not entry:
            return JSONResponse(
                {"ok": False, "reason": "unknown project id"},
                status_code=404,
            )

        if self._state.active_client is not None:
            return {"ok": False, "reason": "A command is currently running."}

        self._state.cfg = load_config(
            entry.root,
            project_id=entry.id,
            name=entry.name,
        )
        set_last_project_id(entry.id)

        self._logger.info("Switched project to %s (%s)", entry.id, entry.root)

        return {
            "ok": True,
            "project": {
                "id": self._state.cfg.id,
                "root": self._state.cfg.root,
            },
        }

    def api_folders(self) -> dict:
        root = Path(self._state.cfg.root)
        default_excludes = _get_default_excludes(self._state.cfg)

        entries = []
        try:
            for p in sorted(
                root.iterdir(),
                key=lambda x: (not x.is_dir(), x.name.lower()),
            ):
                entries.append({
                    "name": p.name,
                    "is_dir": p.is_dir(),
                    "default_excluded": p.name in default_excludes,
                })
        except OSError:
            pass

        return {"folders": entries}

    def _notes_path(self) -> Path:
        return Path(self._state.cfg.root) / self._state.cfg.integrations.server.notes_file

    async def api_get_notes(self) -> dict:
        p = self._notes_path()

        if not p.exists():
            return {"content": ""}

        content = await asyncio.to_thread(p.read_text, encoding="utf-8")
        return {"content": content}

    async def api_save_notes(
        self,
        body: Annotated[_NoteBody, Body(...)]
    ) -> dict:
        p = self._notes_path()

        await asyncio.to_thread(p.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(p.write_text, body.content, encoding="utf-8")

        return {"ok": True}

    async def api_restart(self) -> dict:
        if self._state.active_client is not None:
            return {"ok": False, "reason": "A command is currently running."}

        logger = self._logger

        async def _do() -> None:
            await asyncio.sleep(0.3)
            _restart_server(logger)

        task = asyncio.create_task(_do())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

        return {"ok": True}
    
# Route registration
def _register_routes(app: FastAPI, h: _AppHandlers, state: _State) -> None:
    """Wire all handlers and the WebSocket endpoint onto *app*."""
    app.add_api_route("/", h.index, response_class=HTMLResponse)
    app.add_api_route("/ui.css", h.css)
    app.add_api_route("/ui.js", h.js)
    app.add_api_route("/favicon.ico", h.favicon)

    app.add_api_route("/api/status", h.api_status)
    app.add_api_route("/api/health", h.api_health)
    app.add_api_route("/api/config", h.api_config)
    app.add_api_route("/api/projects", h.api_projects)
    app.add_api_route("/api/projects/select", h.api_select_project, methods=["POST"])
    app.add_api_route("/api/folders", h.api_folders)
    app.add_api_route("/api/notes", h.api_get_notes)
    app.add_api_route("/api/notes", h.api_save_notes, methods=["POST"])
    app.add_api_route("/api/restart", h.api_restart, methods=["POST"])

    async def ws_endpoint(ws: WebSocket) -> None:
        await _WebSocketSession(ws, state).handle()

    app.add_api_websocket_route("/ws", ws_endpoint)


# Public factory
def create_app(cfg: ProjectConfig) -> FastAPI:
    state = _State(cfg)
    log_dir = Path(cfg.root) / cfg.integrations.server.log_dir
    logger = _setup_logger(log_dir)
    logger.info("Starting server for project %s (%s)", cfg.name, cfg.root)
    app = FastAPI(title=f"flutter-toolkit ({cfg.name or cfg.id})")
    _register_routes(app, _AppHandlers(state, logger), state)
    return app
