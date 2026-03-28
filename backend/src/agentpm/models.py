from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class FeatureStatus(str, enum.Enum):
    draft = "draft"
    planning = "planning"
    ready = "ready"
    active = "active"
    review = "review"
    done = "done"
    blocked = "blocked"


class TaskStatus(str, enum.Enum):
    backlog = "backlog"
    ready = "ready"
    leased = "leased"
    implementing = "implementing"
    review = "review"
    merged = "merged"
    done = "done"
    blocked = "blocked"
    archived = "archived"


class RunStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    waiting = "waiting"
    failed = "failed"
    succeeded = "succeeded"
    canceled = "canceled"


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    repo_path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    repo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    default_branch: Mapped[str] = mapped_column(String(120), default="main")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    features: Mapped[list[Feature]] = relationship(back_populates="project", cascade="all, delete-orphan")
    documents: Mapped[list[Document]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=FeatureStatus.draft.value)
    summary: Mapped[str] = mapped_column(Text, default="")
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=True)
    needs_replan: Mapped[bool] = mapped_column(Boolean, default=True)
    last_planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project: Mapped[Project] = relationship(back_populates="features")
    messages: Mapped[list[FeatureMessage]] = relationship(back_populates="feature", cascade="all, delete-orphan")
    tasks: Mapped[list[Task]] = relationship(back_populates="feature", cascade="all, delete-orphan")
    runs: Mapped[list[Run]] = relationship(back_populates="feature", cascade="all, delete-orphan")
    documents: Mapped[list[Document]] = relationship(back_populates="feature", cascade="all, delete-orphan")


class FeatureMessage(Base):
    __tablename__ = "feature_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    feature: Mapped[Feature] = relationship(back_populates="messages")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("feature_id", "planning_key", name="uq_task_feature_planning_key"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    planning_key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default=TaskStatus.backlog.value)
    priority: Mapped[int] = mapped_column(Integer, default=3)
    acceptance_criteria: Mapped[list] = mapped_column(JSON, default=list)
    labels: Mapped[list] = mapped_column(JSON, default=list)
    auto_execute: Mapped[bool] = mapped_column(Boolean, default=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    branch_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    latest_run_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    feature: Mapped[Feature] = relationship(back_populates="tasks")
    outgoing_edges: Mapped[list[TaskEdge]] = relationship(
        back_populates="from_task",
        cascade="all, delete-orphan",
        foreign_keys="TaskEdge.from_task_id",
    )
    incoming_edges: Mapped[list[TaskEdge]] = relationship(
        back_populates="to_task",
        cascade="all, delete-orphan",
        foreign_keys="TaskEdge.to_task_id",
    )
    runs: Mapped[list[Run]] = relationship(back_populates="task", cascade="all, delete-orphan")


class TaskEdge(Base):
    __tablename__ = "task_edges"
    __table_args__ = (UniqueConstraint("from_task_id", "to_task_id", name="uq_task_edge"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    from_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    to_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)

    from_task: Mapped[Task] = relationship(back_populates="outgoing_edges", foreign_keys=[from_task_id])
    to_task: Mapped[Task] = relationship(back_populates="incoming_edges", foreign_keys=[to_task_id])


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(60), default="claude-code")
    status: Mapped[str] = mapped_column(String(32), default=RunStatus.queued.value)
    branch_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    worktree_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[str] = mapped_column(Text, default="")
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    feature: Mapped[Feature] = relationship(back_populates="runs")
    task: Mapped[Task] = relationship(back_populates="runs")
    events: Mapped[list[RunEvent]] = relationship(back_populates="run", cascade="all, delete-orphan")


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[str] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    level: Mapped[str] = mapped_column(String(32), default="info")
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)

    run: Mapped[Run] = relationship(back_populates="events")


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("project_id", "feature_id", "path", name="uq_document_scope_path"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    feature_id: Mapped[str | None] = mapped_column(ForeignKey("features.id", ondelete="CASCADE"), index=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc, onupdate=now_utc)

    project: Mapped[Project] = relationship(back_populates="documents")
    feature: Mapped[Feature | None] = relationship(back_populates="documents")


class Operation(Base):
    __tablename__ = "operations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(120), nullable=False)
    op_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
