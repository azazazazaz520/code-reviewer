import uuid
from datetime import datetime, UTC

from sqlalchemy import String, Integer, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.models.base import Base, UTCDateTime


class Repo(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    git_url: Mapped[str] = mapped_column(String(500), nullable=False)
    local_path: Mapped[str] = mapped_column(String(500), nullable=False)
    default_branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    sync_status: Mapped[str] = mapped_column(String(20), default="never")
    sync_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )

    reviews: Mapped[list["ReviewTask"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )
    refs: Mapped[list["RepositoryRef"]] = relationship(
        back_populates="repo", cascade="all, delete-orphan"
    )


class RepositoryRef(Base):
    """应用最近一次同步得到的远程分支头快照。"""

    __tablename__ = "repository_refs"
    __table_args__ = (UniqueConstraint("repo_id", "name"),)

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    remote_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    head_revision: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )

    repo: Mapped["Repo"] = relationship(back_populates="refs")


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    repo_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    review_type: Mapped[str] = mapped_column(String(20), nullable=False)  # pr / local
    source_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_hash: Mapped[str | None] = mapped_column(String(40), nullable=True)
    branch: Mapped[str | None] = mapped_column(String(200), nullable=True)
    base_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    workspace_target: Mapped[str | None] = mapped_column(String(30), nullable=True)
    head_revision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    base_revision: Mapped[str | None] = mapped_column(String(40), nullable=True)
    workspace_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    workspace_stats_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )  # pending / running / done / failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    reflection_rounds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=lambda: datetime.now(UTC)
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

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
        UTCDateTime, default=lambda: datetime.now(UTC)
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
        UTCDateTime, default=lambda: datetime.now(UTC)
    )
