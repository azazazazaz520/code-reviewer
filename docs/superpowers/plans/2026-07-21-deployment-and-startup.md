# Deployment & Startup Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One command, one process to start the app; backend auto-clones repos so users never type a local path.

**Architecture:** FastAPI mounts the Vite-built frontend as static files, serving API and UI from a single origin. Repo creation triggers `git clone` server-side. Dev mode uses a `start.py` launcher that spawns uvicorn and vite concurrently.

**Tech Stack:** FastAPI, Uvicorn, SQLAlchemy, React 19, Vite 8, TypeScript, Tailwind CSS v4

## Global Constraints

- Python >=3.11, frontend built with Node 22+
- Frontend SPA uses BrowserRouter — all non-/api paths must return index.html
- Git operations (clone, fetch) timeout at 120s
- SQLite stays as-is — no database migration needed; `local_path` stays NOT NULL (backend always fills it)
- `start.py` uses `subprocess` (no extra deps needed)

---

### Task 1: Frontend — Change API baseURL to relative path

**Files:**
- Modify: `frontend/src/api/client.ts`

**Interfaces:**
- Consumes: none (first task)
- Produces: Axios instance `api` with `baseURL: "/api"` — all existing API callers work unchanged

- [ ] **Step 1: Replace hardcoded baseURL with relative path**

```typescript
// frontend/src/api/client.ts
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 10000,
});

export default api;
```

- [ ] **Step 2: Verify frontend builds cleanly**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/client.ts
git commit -m "fix: change API baseURL to relative /api path"
```

---

### Task 2: Frontend — Remove local_path from UI and API types

**Files:**
- Modify: `frontend/src/pages/RepoList.tsx`
- Modify: `frontend/src/pages/RepoDetail.tsx`
- Modify: `frontend/src/types/index.ts`
- Modify: `frontend/src/api/repos.ts`

**Interfaces:**
- Consumes: none
- Produces: Repo form no longer collects/requires `local_path`; `Repo` type marks `local_path` optional; `repoApi.create` and `repoApi.update` omit `local_path`

- [ ] **Step 1: Make local_path optional in types**

```typescript
// frontend/src/types/index.ts — Repo interface
export interface Repo {
  id: string;
  name: string;
  git_url: string;
  local_path?: string;  // backend auto-fills, not shown/edited in UI
  default_branch: string;
  created_at: string;
}
```

- [ ] **Step 2: Update repoApi signatures to omit local_path**

```typescript
// frontend/src/api/repos.ts
import api from "./client";
import { Repo, HeatmapResponse, PRItem } from "../types";

export const repoApi = {
  list: () => api.get<Repo[]>("/repos").then((r) => r.data),

  create: (data: { name: string; git_url: string; default_branch: string }) =>
    api.post<Repo>("/repos", data).then((r) => r.data),

  get: (id: string) => api.get<Repo>(`/repos/${id}`).then((r) => r.data),

  update: (id: string, data: { name: string; git_url: string; default_branch: string }) =>
    api.put<Repo>(`/repos/${id}`, data).then((r) => r.data),

  delete: (id: string) => api.delete(`/repos/${id}`),

  listPRs: (id: string) => api.get<PRItem[]>(`/repos/${id}/prs`).then((r) => r.data),
};
```

- [ ] **Step 3: Remove localPath state and input from RepoList.tsx**

In `frontend/src/pages/RepoList.tsx`:

Remove line 28:
```typescript
// DELETE this line:
const [localPath, setLocalPath] = useState("");
```

Remove lines 51 and 57 references to localPath, and update handleSave:

```typescript
// In handleSave (around line 57-63), change from:
if (!name || !gitUrl || !localPath) return;
// ... await repoApi.update(editing.id, { name, git_url: gitUrl, local_path: localPath, default_branch: defaultBranch });
// ... await repoApi.create({ name, git_url: gitUrl, local_path: localPath, default_branch: defaultBranch });

// To:
if (!name || !gitUrl) return;
try {
  if (editing) {
    await repoApi.update(editing.id, { name, git_url: gitUrl, default_branch: defaultBranch });
  } else {
    await repoApi.create({ name, git_url: gitUrl, default_branch: defaultBranch });
  }
  // ...
```

Remove the "本地路径" table header (around line 100) and the corresponding table cell (around line 119-120):

```tsx
// DELETE the <TableHead> for 本地路径 and the <TableCell> showing r.local_path
```

Remove the local path input field from the form (around lines 162-163):

```tsx
// DELETE:
<label className="text-sm font-medium">本地路径</label>
<input className="flex h-9 w-full rounded-md border bg-background px-3 py-1 text-sm mt-1" value={localPath} onChange={(e) => setLocalPath(e.target.value)} placeholder="/path/to/repo" />
```

Update the save button disabled check (around line 172):

```tsx
// Change from:
<Button onClick={handleSave} disabled={saving || !name || !gitUrl || !localPath}>
// To:
<Button onClick={handleSave} disabled={saving || !name || !gitUrl}>
```

- [ ] **Step 4: Simplify local_path display in RepoDetail.tsx**

In `frontend/src/pages/RepoDetail.tsx` (around line 105), change from:

```tsx
{repo.git_url} · 本地: {repo.local_path}
```

To:

```tsx
{repo.git_url}
```

- [ ] **Step 5: Verify frontend builds cleanly**

Run: `cd frontend && npm run build`
Expected: Build succeeds with no TypeScript errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/RepoList.tsx frontend/src/pages/RepoDetail.tsx frontend/src/types/index.ts frontend/src/api/repos.ts
git commit -m "refactor: remove local_path from frontend — backend will auto-clone"
```

---

### Task 3: Backend — Make local_path optional in API schema

**Files:**
- Modify: `backend/app/models/schemas.py`

**Interfaces:**
- Consumes: none
- Produces: `RepoCreate.local_path` is now `str | None = None` (not required from client)

- [ ] **Step 1: Change RepoCreate.local_path to optional**

```python
# backend/app/models/schemas.py — RepoCreate class (line 12)
# Change from:
local_path: str = Field(..., min_length=1, max_length=500)
# To:
local_path: str | None = Field(default=None, max_length=500)
```

- [ ] **Step 2: Verify backend imports cleanly**

Run: `cd backend && python -c "from app.models.schemas import RepoCreate; print(RepoCreate(name='t', git_url='https://github.com/a/b.git'))"`
Expected: Prints the RepoCreate object with `local_path=None`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/schemas.py
git commit -m "refactor: make RepoCreate.local_path optional"
```

---

### Task 4: Backend — Auto-clone git repo on creation

**Files:**
- Modify: `backend/app/api/repos.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: `RepoCreate.local_path` (optional, from Task 3), `Settings` from config
- Produces: `create_repo` auto-clones git_url to `data/repos/{uuid}/`, stores path in `Repo.local_path`

- [ ] **Step 1: Add repos_dir to config**

```python
# backend/app/config.py — add to Settings class:
class Settings(BaseSettings):
    # ... existing fields ...

    # 仓库存储
    repos_dir: str = "./data/repos"
```

- [ ] **Step 2: Rewrite create_repo with auto-clone**

```python
# backend/app/api/repos.py — replace create_repo function
import uuid as uuid_mod
from pathlib import Path

@router.post("", response_model=RepoResponse, status_code=201)
def create_repo(body: RepoCreate, db: Session = Depends(get_db)):
    # 确定 clone 目标目录
    repo_uuid = str(uuid_mod.uuid4())
    clone_dir = Path(settings.repos_dir) / repo_uuid
    clone_dir.mkdir(parents=True, exist_ok=True)

    # 构造 clone URL（私有仓库注入 GitHub token）
    clone_url = body.git_url
    if settings.github_token and "github.com" in clone_url:
        # 将 https://github.com/... 变成 https://<token>@github.com/...
        clone_url = clone_url.replace(
            "https://github.com/", f"https://{settings.github_token}@github.com/"
        )

    # 执行 clone
    result = subprocess.run(
        ["git", "clone", "--depth", "1", "--single-branch",
         "--branch", body.default_branch, clone_url, str(clone_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
    )
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        # 清理失败的空目录
        import shutil
        if clone_dir.exists():
            shutil.rmtree(clone_dir)
        raise HTTPException(status_code=400, detail=f"Git clone 失败: {stderr}")

    repo = Repo(
        id=repo_uuid,
        name=body.name,
        git_url=body.git_url,
        local_path=str(clone_dir.resolve()),
        default_branch=body.default_branch,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo
```

- [ ] **Step 3: Add import for shutil at top of repos.py**

```python
# backend/app/api/repos.py — add to existing imports:
import shutil
```

- [ ] **Step 4: Verify backend imports and basic structure**

Run: `cd backend && python -c "from app.api.repos import router; print('OK')"`
Expected: Prints "OK".

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/repos.py backend/app/config.py
git commit -m "feat: auto git-clone repo on creation — no more manual local_path"
```

---

### Task 5: Backend — Git fetch before review

**Files:**
- Modify: `backend/app/api/reviews.py`

**Interfaces:**
- Consumes: `repo.local_path` (populated by Task 4's auto-clone)
- Produces: `_run_review_workflow` runs `git fetch` before passing repo_path to the review engine

- [ ] **Step 1: Add git fetch in _run_review_workflow**

In `backend/app/api/reviews.py`, inside `_run_review_workflow`, after the repo existence check (after `if not repo: raise ValueError(...)`), add:

```python
# 审查前拉取最新代码
import subprocess as git_subprocess
try:
    fetch_result = git_subprocess.run(
        ["git", "-C", repo.local_path, "fetch", "--depth", "1", "origin",
         repo.default_branch],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    if fetch_result.returncode != 0:
        log_hook(step="load_pr", level="warn",
                 message=f"git fetch 警告: {(fetch_result.stderr or '').strip()[:200]}")
except git_subprocess.TimeoutExpired:
    log_hook(step="load_pr", level="warn", message="git fetch 超时，继续使用本地已有数据")
except Exception as e:
    log_hook(step="load_pr", level="warn", message=f"git fetch 异常: {str(e)[:200]}")
```

- [ ] **Step 2: Verify backend imports cleanly**

Run: `cd backend && python -c "from app.api.reviews import router; print('OK')"`
Expected: Prints "OK".

- [ ] **Step 3: Commit**

```bash
git add backend/app/api/reviews.py
git commit -m "feat: git fetch before review to ensure latest code"
```

---

### Task 6: Backend — Serve frontend static files from FastAPI

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/config.py`

**Interfaces:**
- Consumes: `frontend/dist/` directory (must exist)
- Produces: FastAPI app serves:
  - `/api/*` → API routes
  - `/assets/*`, `/*.js`, `/*.css`, `/*.ico` → static files from `dist/`
  - all other `/*` → `dist/index.html` (SPA fallback)

- [ ] **Step 1: Add frontend_dist_dir to config**

```python
# backend/app/config.py — add to Settings class:
class Settings(BaseSettings):
    # ... existing fields ...

    # 前端静态文件
    frontend_dist_dir: str = "../frontend/dist"
```

- [ ] **Step 2: Add SPA fallback middleware and static file mount to main.py**

```python
# backend/app/main.py — complete replacement:

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.base import engine, Base

import app.models.repo  # noqa: F401

from app.api.repos import router as repos_router
from app.api.reviews import router as reviews_router
from app.api.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    yield
    engine.dispose()


app = FastAPI(
    title="Code Reviewer",
    description="自动化代码审查系统 API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ──
app.include_router(repos_router)
app.include_router(reviews_router)
app.include_router(stats_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


# ── Frontend static files + SPA fallback ──
frontend_dist = Path(settings.frontend_dist_dir).resolve()

if frontend_dist.exists() and frontend_dist.is_dir():
    # Mount static assets (JS, CSS, images, fonts) under /assets/
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    # SPA fallback: non-API, non-static requests → index.html
    @app.middleware("http")
    async def spa_fallback(request: Request, call_next):
        from fastapi.responses import Response
        path = request.url.path
        # Let API routes, static assets, and health pass through
        if path.startswith("/api/") or path.startswith("/assets/"):
            return await call_next(request)
        # Try serving the file from dist; if it exists, serve it; otherwise index.html
        file_path = frontend_dist / path.lstrip("/")
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        # SPA fallback
        index_path = frontend_dist / "index.html"
        if index_path.exists():
            return FileResponse(str(index_path))
        return await call_next(request)
```

- [ ] **Step 3: Ensure data/repos directory is created on startup**

Add to the `lifespan` function, after `Path(db_path).parent.mkdir(...)`:

```python
    # 确保 repos 目录存在
    repos_path = Path(settings.repos_dir)
    repos_path.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Build frontend and verify server starts**

Run:
```bash
cd frontend && npm run build
cd ../backend && python -c "from app.main import app; print('OK')"
```
Expected: Prints "OK" with no errors.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/app/config.py
git commit -m "feat: serve frontend static files from FastAPI with SPA fallback"
```

---

### Task 7: Dev launcher — start.py

**Files:**
- Create: `start.py` (project root)

**Interfaces:**
- Consumes: `backend/` and `frontend/` directories
- Produces: Single `python start.py` command starts both uvicorn (backend) and vite (frontend dev server) concurrently; Ctrl+C kills both

- [ ] **Step 1: Create start.py**

```python
"""Code Reviewer — one-command dev launcher.

Usage:
    python start.py           # dev mode: uvicorn + vite
    python start.py --prod    # production: uvicorn only (serves built frontend)

Requirements: Python 3.11+, Node 22+, npm dependencies installed.
"""

import subprocess
import sys
import time
import signal
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

_processes: list[subprocess.Popen] = []


def main():
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

    backend_proc = subprocess.Popen(
        backend_args,
        cwd=str(ROOT / "backend"),
    )
    _processes.append(backend_proc)

    if not prod:
        # Start frontend dev server
        print("[frontend] Starting Vite dev server...")
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"
        frontend_proc = subprocess.Popen(
            [npm_cmd, "run", "dev"],
            cwd=str(ROOT / "frontend"),
        )
        _processes.append(frontend_proc)

    print("\n" + "-" * 50)
    if prod:
        print("App running at: http://localhost:8000")
    else:
        print("Frontend: http://localhost:5173")
        print("Backend:  http://localhost:8000")
    print("Press Ctrl+C to stop")
    print("-" * 50 + "\n")

    # Wait for any process to exit, or handle Ctrl+C
    def shutdown(sig, frame):
        print("\nShutting down...")
        for p in _processes:
            p.terminate()
        for p in _processes:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        for p in _processes:
            p.wait()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add Vite proxy config for dev mode**

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
```

- [ ] **Step 3: Test dev mode**

Run: `python start.py`
Expected: Backend starts on :8000, frontend on :5173. Visiting http://localhost:5173 shows the app with API calls proxied correctly. Ctrl+C kills both processes.

- [ ] **Step 4: Test production mode**

Run:
```bash
cd frontend && npm run build
cd .. && python start.py --prod
```
Expected: Visiting http://localhost:8000 serves the full app with working API. Ctrl+C stops.

- [ ] **Step 5: Commit**

```bash
git add start.py frontend/vite.config.ts
git commit -m "feat: add one-command dev launcher (start.py) and Vite API proxy"
```

---

### Task 8: Integration smoke test

**Files:** none (test only)

**Interfaces:**
- Consumes: all previous tasks
- Produces: verified end-to-end flow

- [ ] **Step 1: Build frontend**

```bash
cd frontend && npm run build
```

- [ ] **Step 2: Start in production mode and verify health**

In one terminal:
```bash
python start.py --prod
```

In another terminal:
```bash
curl http://localhost:8000/api/health
```
Expected: `{"status":"ok","version":"0.1.0"}`

- [ ] **Step 3: Verify frontend is served**

```bash
curl http://localhost:8000/
```
Expected: Returns HTML containing `<div id="root">` (the React app shell).

- [ ] **Step 4: Verify SPA fallback**

```bash
curl http://localhost:8000/repos
```
Expected: Returns the same `index.html` (not a 404).

- [ ] **Step 5: Kill server**

Ctrl+C in the server terminal.

- [ ] **Step 6: No commit needed (verification only)**
