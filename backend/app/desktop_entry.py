"""Electron sidecar entry point."""

from __future__ import annotations

import argparse
import os
from pathlib import Path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Code Reviewer local API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--frontend-dist", type=Path)
    return parser


def _configure_environment(data_dir: Path | None, frontend_dist: Path | None) -> None:
    if data_dir is not None:
        data_dir = data_dir.expanduser().resolve()
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / "repos").mkdir(parents=True, exist_ok=True)
        os.environ["DATABASE_URL"] = (
            f"sqlite:///{(data_dir / 'code_reviewer.db').as_posix()}"
        )
        os.environ["REPOS_DIR"] = str(data_dir / "repos")
        os.environ["CODE_REVIEWER_DATA_DIR"] = str(data_dir)

    if frontend_dist is not None:
        os.environ["FRONTEND_DIST_DIR"] = str(frontend_dist.expanduser().resolve())


def main() -> None:
    args = _build_parser().parse_args()
    if args.host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("desktop sidecar 只允许绑定本机回环地址")

    _configure_environment(args.data_dir, args.frontend_dist)

    import uvicorn

    from app.main import app

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
