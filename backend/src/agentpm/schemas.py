from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ImportProjectRequest(BaseModel):
    repo_path: str
    name: str | None = None


class CreateFeatureRequest(BaseModel):
    title: str
    goal: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    auto_execute: bool = True


class FeatureChatRequest(BaseModel):
    message: str


class UpdateTaskStatusRequest(BaseModel):
    status: str


class PlanningTask(BaseModel):
    planning_key: str
    title: str
    description: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: int = 3
    labels: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)
    auto_execute: bool = True
    status: str = "ready"


class PlanningResponse(BaseModel):
    summary: str
    status: str = "active"
    feature_doc: str = ""
    project_memory: str = ""
    changelog: str = ""
    tasks: list[PlanningTask] = Field(default_factory=list)


class ProjectDTO(BaseModel):
    id: str
    name: str
    repo_path: str
    repo_url: str | None = None
    default_branch: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FeatureMessageDTO(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class TaskDTO(BaseModel):
    id: str
    feature_id: str
    planning_key: str
    title: str
    description: str
    status: str
    priority: int
    acceptance_criteria: list[str]
    labels: list[str]
    auto_execute: bool
    archived: bool
    branch_name: str | None = None
    worktree_path: str | None = None
    latest_run_id: str | None = None
    depends_on: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class DocumentDTO(BaseModel):
    id: str
    kind: str
    path: str
    content: str
    updated_at: datetime


class FeatureDTO(BaseModel):
    id: str
    project_id: str
    title: str
    goal: str
    status: str
    summary: str
    acceptance_criteria: list[str]
    auto_execute: bool
    needs_replan: bool
    last_planned_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    messages: list[FeatureMessageDTO] = Field(default_factory=list)
    tasks: list[TaskDTO] = Field(default_factory=list)
    documents: list[DocumentDTO] = Field(default_factory=list)


class RunEventDTO(BaseModel):
    id: str
    run_id: str
    feature_id: str
    event_type: str
    level: str
    message: str
    payload: dict[str, Any]
    created_at: datetime


class RunDTO(BaseModel):
    id: str
    project_id: str
    feature_id: str
    task_id: str
    provider: str
    status: str
    branch_name: str | None = None
    worktree_path: str | None = None
    session_id: str | None = None
    pr_url: str | None = None
    result_summary: str
    result_json: dict[str, Any]
    error: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    created_at: datetime
    events: list[RunEventDTO] = Field(default_factory=list)
