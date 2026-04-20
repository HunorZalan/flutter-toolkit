"""Launch the flutter-toolkit web UI / FastAPI server."""
from __future__ import annotations
import argparse

from ftk.common import header, ok, warn, err, info, missing_dep, init_colours
from ftk.config import ProjectConfig


def run(cfg: ProjectConfig, argv: list[str]) -> int:
    init_colours()
    parser = argparse.ArgumentParser(prog="ftk server", description="Start the web UI server.")
    parser.add_argument("--host", default=cfg.integrations.server.host)
    parser.add_argument("--port", type=int, default=cfg.integrations.server.port)
    parser.add_argument("--reload", action="store_true", default=cfg.integrations.server.auto_reload)
    args = parser.parse_args(argv)

    try:
        import uvicorn  # noqa: F401
    except ImportError:
        missing_dep("uvicorn", "all")
        return 1

    try:
        from ftk.server.app import create_app
    except ImportError as exc:
        err(f"Could not load server module: {exc}")
        return 1

    header("flutter-toolkit server")
    info(f"Project : {cfg.name or cfg.id} ({cfg.root})")
    info(f"Listen  : http://{args.host}:{args.port}")
    info("Press Ctrl+C to stop.")
    app = create_app(cfg)
    import uvicorn
    uvicorn.run(app, host=args.host, port=args.port, reload=args.reload, log_level="info")
    return 0
