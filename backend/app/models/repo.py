import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Text, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base


class Repo(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    git_url: Mapped[str] = mapped_column(String(500), nullable=False)
    local_path: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(100), default="main")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    reviews: Mapped[list["ReviewTask"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pr / local
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending / running / done / failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_rounds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    repo: Mapped["Repo"] = relationship(back_populates="reviews")
    report: Mapped["ReviewReport | None"] = relationship(
        back_populates="task", uselist=False, cascade="all, delete-orphan"
    )


class ReviewReport(Base):
    __tablename__ = "review_reports"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("review_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    risk_level: Mapped[str] = mapped_column(
        String(10), nullable=False
    )  # low / medium / high / critical
    findings_json: Mapped[str] = mapped_column(Text, nullable=False)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )

    task: Mapped["ReviewTask"] = relationship(back_populates="report")


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("review_tasks.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[str] = mapped_column(String(30), nullable=False)
    level: Mapped[str] = mapped_column(String(10), default="info")
    message: Mapped[str] = mapped_column(Text, nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(30), nullable=True)
    tool_args: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now()
    )
