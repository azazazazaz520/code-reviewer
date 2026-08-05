from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.models.base import engine, Base, ensure_schema

# 导入所有模型（确保 Base.metadata 感知所有表）
import app.models.repo  # noqa: F401

from app.api.repos import router as repos_router
from app.api.reviews import router as reviews_router
from app.api.stats import router as stats_router
from app.services.review_runner import ReviewTaskRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 确保数据目录存在
    db_path = settings.database_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # 确保 repos 目录存在
    Path(settings.repos_dir).mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    runner = ReviewTaskRunner()
    app.state.review_runner = runner
    await runner.start()
    try:
        yield
    finally:
        await runner.stop()
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

app.include_router(repos_router)
app.include_router(reviews_router)
app.include_router(stats_router)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@app.get("/api/ready")
def ready():
    """报告应用已完成 lifespan 初始化，可以接收业务请求。"""
    return {"status": "ready", "version": "0.1.0"}


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
        path = request.url.path
        # Let API routes and static assets pass through
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
