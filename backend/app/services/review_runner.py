"""ReviewTask 的持久化 worker。

任务先写入数据库，再由应用生命周期内的 worker 领取。这样 API 进程重启后，
pending 任务仍可继续执行；running 任务会在下一次启动时回到 pending。
当前实现是单进程 worker，后续可在同一 claim 接缝替换为外部队列。
"""

from __future__ import annotations

import asyncio

from app.config import settings
from app.models.base import SessionLocal
from app.models.repo import ReviewTask


class ReviewTaskRunner:
    """消费 ReviewTask 的单进程 worker。"""

    def __init__(self, poll_seconds: float | None = None):
        self.poll_seconds = poll_seconds or settings.review_worker_poll_seconds
        self._stop = asyncio.Event()
        self._worker: asyncio.Task | None = None

    async def start(self) -> None:
        """恢复上次进程遗留的 running 任务并启动 worker。"""
        await asyncio.to_thread(_recover_running_tasks)
        self._stop.clear()
        self._worker = asyncio.create_task(self._run(), name="review-task-worker")

    async def stop(self) -> None:
        """停止领取新任务，并等待当前任务自然结束。"""
        self._stop.set()
        if self._worker:
            await self._worker
            self._worker = None

    async def _run(self) -> None:
        while not self._stop.is_set():
            task_id = await asyncio.to_thread(_claim_next_task)
            if task_id:
                await asyncio.to_thread(_run_review_workflow, task_id)
                continue

            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.poll_seconds)
            except asyncio.TimeoutError:
                pass


def _recover_running_tasks() -> None:
    db = SessionLocal()
    try:
        db.query(ReviewTask).filter(ReviewTask.status == "running").update(
            {
                ReviewTask.status: "pending",
                ReviewTask.error_message: None,
            },
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _claim_next_task() -> str | None:
    """原子地把最早 pending 任务改为 running。"""
    db = SessionLocal()
    try:
        task = (
            db.query(ReviewTask)
            .filter(ReviewTask.status == "pending")
            .order_by(ReviewTask.created_at.asc())
            .first()
        )
        if not task:
            return None

        updated = (
            db.query(ReviewTask)
            .filter(
                ReviewTask.id == task.id,
                ReviewTask.status == "pending",
            )
            .update(
                {
                    ReviewTask.status: "running",
                    ReviewTask.error_message: None,
                },
                synchronize_session=False,
            )
        )
        if updated != 1:
            db.rollback()
            return None
        db.commit()
        return task.id
    finally:
        db.close()


def _run_review_workflow(task_id: str) -> None:
    """在 worker 线程中执行一个已被领取的 ReviewTask。"""
    from app.api.reviews import _run_review_workflow as run_task

    run_task(task_id)
