# flutter-toolkit

Project-agnostic companion CLI + web UI for Flutter apps. One install, any
project, multi-flavor or single-flavor.

## Features
- Build web / APK / AAB / iOS / IPA / desktop with optional flavor awareness
- Clean, analyze, test, icons, translations, unused-file detection
- Deploy web artifacts via FTP / FTPS / SFTP
- Archive backups (zip / 7z / tar.gz / tar.bz2 / tar.xz / tar.zst / tar)
- FastAPI + WebSocket web UI with live log streaming, **project switcher**,
  and **server restart** button
- Multi-project registry (`~/.ftk/projects.yaml`)

## Install

**Run the installer from your Flutter project directory** (the one with the
`ftk.yaml`). One file, end-to-end: pip install + PATH + project register +
OS service install + auto-start + opens browser.

```bat
:: Windows cmd
cd C:\path\to\my-flutter-app
C:\path\to\flutter-toolkit\scripts\install.bat
```

```powershell
# Windows PowerShell
cd C:\path\to\my-flutter-app
powershell -ExecutionPolicy Bypass -File C:\path\to\flutter-toolkit\scripts\install.ps1
```

```bash
# macOS / Linux
cd /path/to/my-flutter-app
bash /path/to/flutter-toolkit/scripts/install.sh
```

The installer registers a logon-trigger service (Windows scheduled task /
macOS LaunchAgent / Linux systemd-user) so the web UI is up at every login
without touching a terminal.

If you only want the toolkit without autostart, run the installer from any
directory that has no `ftk.yaml` — it stops cleanly after `pip install`.

## Configuration

Each project has an `ftk.yaml` at its root. Every section is optional. See
`examples/ftk.minimal.yaml` and `examples/ftk.full.yaml` — the full file
documents every section inline.

Omitting sections hides UI affordances:
- no `flavors:` → every flavor picker disappears
- no `integrations.deploy` → Deploy tab hidden
- no `integrations.sonar` → Sonar tab hidden
- no `integrations.backup` → Backup tab hidden

## Multi-project registry

```bash
ftk projects add /path/to/app1 --id app1
ftk projects add /path/to/app2 --id app2
ftk projects list
ftk projects remove myapp
ftk --project app2 build --web
```

When ≥2 projects are registered, the web UI shows a project-switcher
dropdown in the header.

## Scripts

Everything automated lives in `scripts/`. Three lifecycles, one file each:

- `install.*` — install package + (when run from a project) install OS
  service + start it + open browser.
- `reset.*` — restart the OS service in place.
- `uninstall.*` — remove OS service + kill listener + pip-uninstall +
  clean PATH + optionally wipe `~/.ftk`.

See `INSTALL.md` for the full install / config / uninstall walkthrough.

## License

MIT - see `LICENSE`.
