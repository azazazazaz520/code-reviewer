"""Code Reviewer — one-command dev launcher.

Usage:
    python start.py           # dev mode: uvicorn + vite
    python start.py --prod    # production: uvicorn only (serves built frontend)

Requirements: Python 3.11+, Node 22+, npm dependencies installed.
"""

import subprocess
import sys
import signal
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_processes: list[subprocess.Popen] = []


def _shutdown(sig, frame):
    """Terminate all managed processes gracefully."""
    print("\nShutting down...")
    for p in _processes:
        p.terminate()
    for p in _processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
    sys.exit(0)


def main():
    _start_processes()
    _wait()


def _start_processes():
    prod = "--prod" in sys.argv

    print("=" * 50)
    print("Code Reviewer" + (" (production)" if prod else " (development)"))
    print("=" * 50)

    # Start backend
    print("\n[backend] Starting uvicorn...")
    backend_args = [
        sys.executable, "-m", "uvicorn", "app.main:app",
        "--host", "127.0.0.1", "--port", "8000",
    ]
    if not prod:
        backend_args.append("--reload")

    backend_proc = subprocess.Popen(backend_args, cwd=str(ROOT / "backend"))
    _processes.append(backend_proc)

    if not prod:
        print("[frontend] Starting Vite dev server...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"], cwd=str(ROOT / "frontend")
        )
        _processes.append(frontend_proc)

    _print_running_info(prod)


def _print_running_info(prod: bool):
    print("\n" + "-" * 50)
    if prod:
        print("App running at: http://localhost:8000")
    else:
        print("Frontend: http://localhost:5173")
        print("Backend:  http://localhost:8000")
    print("Press Ctrl+C to stop")
    print("-" * 50 + "\n")


def _wait():
    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)
    try:
        for p in _processes:
            p.wait()
    except KeyboardInterrupt:
        _shutdown(None, None)


if __name__ == "__main__":
    main()
