from __future__ import annotations

from .models import Document, Feature, FeatureMessage, Run, RunEvent, Task
from .schemas import (
    DocumentDTO,
    FeatureDTO,
    FeatureMessageDTO,
    RunDTO,
    RunEventDTO,
    TaskDTO,
)


def feature_message_to_dto(message: FeatureMessage) -> FeatureMessageDTO:
    return FeatureMessageDTO(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
    )


def task_to_dto(task: Task) -> TaskDTO:
    return TaskDTO(
        id=task.id,
        feature_id=task.feature_id,
        planning_key=task.planning_key,
        title=task.title,
        description=task.description,
        status=task.status,
        priority=task.priority,
        acceptance_criteria=list(task.acceptance_criteria or []),
        labels=list(task.labels or []),
        auto_execute=task.auto_execute,
        archived=task.archived,
        branch_name=task.branch_name,
        worktree_path=task.worktree_path,
        latest_run_id=task.latest_run_id,
        depends_on=[edge.from_task.planning_key for edge in task.incoming_edges if edge.from_task],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def document_to_dto(document: Document) -> DocumentDTO:
    return DocumentDTO(
        id=document.id,
        kind=document.kind,
        path=document.path,
        content=document.content,
        updated_at=document.updated_at,
    )


def feature_to_dto(feature: Feature) -> FeatureDTO:
    return FeatureDTO(
        id=feature.id,
        project_id=feature.project_id,
        title=feature.title,
        goal=feature.goal,
        status=feature.status,
        summary=feature.summary,
        acceptance_criteria=list(feature.acceptance_criteria or []),
        auto_execute=feature.auto_execute,
        needs_replan=feature.needs_replan,
        last_planned_at=feature.last_planned_at,
        created_at=feature.created_at,
        updated_at=feature.updated_at,
        messages=[feature_message_to_dto(message) for message in feature.messages],
        tasks=[task_to_dto(task) for task in feature.tasks if not task.archived],
        documents=[document_to_dto(document) for document in feature.documents],
    )


def run_event_to_dto(event: RunEvent) -> RunEventDTO:
    return RunEventDTO(
        id=event.id,
        run_id=event.run_id,
        feature_id=event.feature_id,
        event_type=event.event_type,
        level=event.level,
        message=event.message,
        payload=event.payload or {},
        created_at=event.created_at,
    )



def run_to_dto(run: Run) -> RunDTO:
    return RunDTO(
        id=run.id,
        project_id=run.project_id,
        feature_id=run.feature_id,
        task_id=run.task_id,
        provider=run.provider,
        status=run.status,
        branch_name=run.branch_name,
        worktree_path=run.worktree_path,
        session_id=run.session_id,
        pr_url=run.pr_url,
        result_summary=run.result_summary,
        result_json=run.result_json or {},
        error=run.error,
        started_at=run.started_at,
        ended_at=run.ended_at,
        created_at=run.created_at,
        events=[run_event_to_dto(event) for event in run.events],
    )
