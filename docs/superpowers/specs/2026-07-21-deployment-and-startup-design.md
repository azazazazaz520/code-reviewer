# Deployment & Startup Simplification Design

## Goal

Make the Code Reviewer tool start with **one command, one process**, and support **cloud deployment** by automating git repo cloning.

## Current Problems

1. **Two processes**: must start uvicorn (backend) and vite/nginx (frontend) separately
2. **Manual local_path**: adding a repo requires typing the local filesystem path by hand
3. **Hardcoded API URL**: frontend hardcodes `http://127.0.0.1:8000/api`, causing CORS issues in deployment
4. **Cloud-unfriendly**: backend can't access user's local filesystem when deployed remotely

## Design

### 1. Single-process startup — FastAPI serves frontend

FastAPI mounts the Vite build output (`frontend/dist/`) as static files. In production, visiting `localhost:8000` serves the SPA; API routes under `/api/*` are handled by FastAPI routers.

- **Production**: `uvicorn app.main:app` → one process, frontend + API on same origin
- **Development**: `python start.py` → starts uvicorn + vite dev server concurrently; vite proxies `/api` to uvicorn

Frontend `baseURL` changes from hardcoded absolute URL to relative `/api`, eliminating CORS entirely in production.

### 2. Auto-clone on repo creation

When a user adds a repo via `POST /api/repos`, the backend:

1. Parses `git_url`
2. Clones the repo to `data/repos/{uuid}/` on the server (with optional GitHub token auth for private repos)
3. Stores the resulting `local_path` automatically

The `local_path` field stays on the model (unchanged) — it's just no longer required from the user. The frontend form removes the local_path input.

### 3. Pre-review git fetch

Before each review, run `git fetch` in the cloned repo to ensure the latest commits/PR refs are available.

### 4. SPA fallback

All non-API, non-static-file requests return `index.html` for client-side routing.

## Files to Change

| File | Change |
|------|--------|
| `backend/app/main.py` | Add `StaticFiles` mount for `frontend/dist/`, SPA fallback |
| `backend/app/config.py` | Add `frontend_dist_dir` config, remove CORS requirement in prod |
| `backend/app/api/repos.py` | `create_repo`: auto `git clone`, auto-fill `local_path` |
| `backend/app/api/reviews.py` | `_run_review_workflow`: `git fetch` before review |
| `frontend/src/api/client.ts` | `baseURL` → `/api` |
| `frontend/vite.config.ts` | Add proxy for `/api` in dev mode |
| `start.py` (new) | Dev launcher: concurrent uvicorn + vite |
