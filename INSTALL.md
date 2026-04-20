# Installing flutter-toolkit

`flutter-toolkit` ships as a Python package (`ftk`) with a CLI and a web UI.
One command installs everything — package, all optional extras, and `ftk` on
your `PATH`.

---

## 1. Prerequisites

- **Python 3.10+** — [python.org](https://www.python.org/downloads/) on Windows
  (tick **Add python.exe to PATH**), `brew install python` on macOS,
  `sudo apt install python3 python3-pip python3-venv` on Debian/Ubuntu.
- **Flutter SDK** — only needed by `build`, `clean`, `test`, `info`.

---

## 2. Install — one command, end-to-end

**Run the installer from your Flutter project directory**, not from the
toolkit repo. That's the difference: it picks up the `ftk.yaml` at your
cwd, registers the project, installs the OS service that auto-starts the
web UI at every login, and opens the browser. One file does the lot.

| OS                       | Command                                                                                                |
|--------------------------|--------------------------------------------------------------------------------------------------------|
| **Windows (cmd)**        | `cd C:\path\to\my-flutter-app` then `C:\path\to\flutter-toolkit\scripts\install.bat`                  |
| **Windows (PowerShell)** | `cd C:\path\to\my-flutter-app` then `powershell -ExecutionPolicy Bypass -File C:\path\to\flutter-toolkit\scripts\install.ps1` |
| **macOS**                | `cd /path/to/my-flutter-app` then `bash /path/to/flutter-toolkit/scripts/install.sh`                  |
| **Linux**                | `cd /path/to/my-flutter-app` then `bash /path/to/flutter-toolkit/scripts/install.sh`                  |

The installer does the following in one shot:

1. Finds a suitable Python.
2. Runs `python -m pip install -e ".[all]"` from the toolkit repo.
3. Adds the Python `Scripts`/`bin` directory to your user `PATH` (persistent).
4. Verifies `ftk --version`.
5. **If `ftk.yaml` exists in the cwd**: registers the project and installs
   an OS-level service that runs `ftk server` automatically at every login.
   - Windows → scheduled task `FlutterToolkitServer` (logon trigger).
   - macOS   → `~/Library/LaunchAgents/com.flutter-toolkit.server.plist`.
   - Linux   → `~/.config/systemd/user/flutter-toolkit.service`.
6. Starts the service and opens `http://127.0.0.1:8742` in your browser.

If you only need the toolkit installed without autostart (e.g. you'll run
`ftk server` manually), run the installer from any directory that has no
`ftk.yaml` — it stops cleanly after step 4.

After install, open a NEW terminal (so the updated `PATH` is active):

```bash
ftk --version
ftk --help
```

If `ftk` still isn't found, everything works via the module form too:
`python -m ftk` (Windows) or `python3 -m ftk` (macOS/Linux).

---

## 3. Point it at a Flutter project

Each Flutter project gets its own `ftk.yaml` in its root.

```bash
cd /path/to/my-flutter-app
ftk init                     # create a minimal ftk.yaml
ftk init --with-flavors      # include a multi-flavor sample
```

### Authoring `ftk.yaml`

Every section is optional. The smallest valid file is a single-line identity:

```yaml
project:
  id: my-flutter-app
  name: My Flutter App
```

Build up from there using `examples/ftk.full.yaml` as a reference. Sections
you can add:

| Section                 | What it does                                                  |
|-------------------------|---------------------------------------------------------------|
| `project`               | Id and display name (required for the registry)               |
| `languages`             | Locale list for `ftk translations` (e.g. `[en, hu, ro]`)       |
| `paths`                 | Where `lib/`, translations, entry points, web files live      |
| `build`                 | Default mode, obfuscation toggle, desktop targets             |
| `commands`              | Show/hide individual commands in the UI + CLI                 |
| `flavors`               | Per-flavor iOS plist, web prefix, icon color. **Omit entirely for a single-flavor app — all flavor UI disappears.** |
| `default_flavor`        | The flavor chosen when you run `ftk build` with no `-f`       |
| `integrations.server`   | Host/port/log dir for the web UI                              |
| `integrations.sonar`    | Scanner command + extra args. Omit → Sonar tab hidden         |
| `integrations.backup`   | Default archive format + password. Omit → Backup tab hidden   |
| `integrations.deploy`   | FTP/FTPS/SFTP target per flavor. Omit → Deploy tab hidden     |

See `examples/ftk.minimal.yaml` and `examples/ftk.full.yaml`.

---

## 4. Register the project (optional but useful)

The registry at `~/.ftk/projects.yaml` lets you select projects by id from
anywhere, **and is the source of the project-switcher dropdown in the UI
header.**

```bash
ftk projects add /path/to/my-flutter-app --id myapp
ftk projects add /path/to/other-app     --id other
ftk projects list
ftk --project other build --apk
```

Override the registry location with `FTK_HOME=/custom/path`.

---

## 5. The web UI

If you ran the installer from a project (§2 step 5), the server is already
running in the background and `http://127.0.0.1:8742` opened automatically.
It will keep running and re-launch at every login — no terminal required.

To start it manually instead (or override host/port):

```bash
cd /path/to/my-flutter-app
ftk server                  # http://127.0.0.1:8742
ftk server --port 9000
ftk server --host 0.0.0.0   # expose to LAN
ftk --project myapp server  # explicit project
```

In the browser you get:

- **Project switcher** (top-right) when ≥2 projects are registered — the page
  reloads after switching so every tab reflects the new project.
- **Server restart** button (circular-arrow icon) — restarts the running
  `ftk server` process in-place.
- **Build / Clean / Test / Analyze / Deploy / Backup / Sonar** tabs with live
  streaming output.

Stop with **Ctrl-C** (manual mode) or run `scripts/reset.*` to restart the
service in place.

---

## 6. Maintenance scripts

All live in `scripts/`:

| File                                          | What it does                                                                                            |
|-----------------------------------------------|---------------------------------------------------------------------------------------------------------|
| `install.bat` / `.ps1` / `.sh` / `.command`   | Install package + (when run from a project) install OS service + start it (see §2)                      |
| `reset.bat` / `.sh`                           | Restart the OS service (Windows scheduled task / macOS LaunchAgent / Linux systemd-user); HTTP fallback |
| `uninstall.bat` / `.sh`                       | Remove the OS service, kill the listening process, pip-uninstall, clean PATH, optionally wipe `~/.ftk`  |

If you skipped step 5 and just want to launch the UI manually, `ftk server`
from any registered project works.

---

## 7. First commands to try

```bash
ftk info --env            # Flutter/Dart versions, SDK paths
ftk info --doctor         # flutter doctor
ftk info --sizes          # size of build/, .dart_tool/, etc.
ftk clean                 # nuke caches and locks
ftk analyze               # flutter analyze + dart fix
ftk test --coverage       # flutter test with coverage
ftk build --apk           # APK for default flavor
ftk build --web --flavor flavorA
ftk help build            # argparse help for a sub-command
ftk run                   # interactive menu
```

Short aliases: `b`=build, `c`=clean, `i`=info, `a`=analyze, `t`=translations,
`te`=test, `ic`=icons, `u`=unused, `d`=deploy, `bk`=backup, `s`=sonar,
`srv`=server, `proj`/`ls`=projects, `h`=help.

---

## 8. Troubleshooting

| Symptom                                                | Fix                                                                  |
|--------------------------------------------------------|----------------------------------------------------------------------|
| `ftk: command not found` after install                 | Open a **new terminal** – `PATH` changes only apply to new shells    |
| `ftk: command not found` after opening a new terminal  | Run `python -m ftk` / `python3 -m ftk` (works identically)           |
| `externally-managed-environment` on macOS/Linux        | `scripts/install.sh` handles it with `--user --break-system-packages` |
| `Command 'deploy' is disabled in ftk.yaml`             | Add an `integrations.deploy:` block, or toggle `commands.deploy`      |
| Server port already in use                             | `ftk server --port 8743`, or run `scripts/reset.*`                    |
| `Unknown project id: 'foo'`                            | `ftk projects add /path --id foo`                                     |
| Double-clicking `install.command` opens in text editor | Finder → right-click → Open With → Terminal (or run `bash install.sh`) |

---

## 9. Uninstall

```bat
scripts\uninstall.bat     rem Windows
```

```bash
bash scripts/uninstall.sh   # macOS/Linux
```

The script removes the pip package, cleans the PATH entry it added, and
offers to wipe `~/.ftk` (the project registry).
