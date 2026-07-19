from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models.base import engine, Base

# 导入所有模型（确保 Base.metadata 感知所有表）
import app.models.repo  # noqa: F401

from app.api.repos import router as repos_router
from app.api.reviews import router as reviews_router
from app.api.stats import router as stats_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 确保数据目录存在
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
    allow_origins=["http://localhost:5173"],
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
