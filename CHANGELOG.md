# Changelog

All notable changes to this project are documented in this file.

The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-04-13

Initial standalone release, ported from the project internal toolkit.

### Added
- `ftk` CLI with `clean`, `build`, `info`, `analyze`, `test`, `icons`,
  `unused`, `translations`, `deploy`, `backup`, `sonar`, `run`, `init`,
  `projects`, `server`, and `help` sub-commands.
- Multi-project registry at `~/.ftk/projects.yaml` with `--project` / `--root`
  global flags and `FTK_HOME` / `FTK_PROJECT` / `FTK_PROJECT_ROOT` env vars.
- FastAPI + WebSocket web UI with streaming output and prompt handling.
- YAML-driven per-project configuration (`ftk.yaml`). Missing `flavors:`
  hides all flavor UI; missing integration sections disable the matching
  command in the UI but keep the tab visible.
- Optional dependencies via pip extras: `icons`, `backup`, `deploy`, `all`,
  `dev`.
- Cross-platform launcher scripts and install/uninstall/restart service
  helpers for Windows (schtasks) and Linux (systemd --user).
