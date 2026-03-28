from __future__ import annotations

from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Document, Feature, Project
from .ops import record_operation


PROJECT_MEMORY_PATH = ".agentpm/memory/PROJECT_MEMORY.md"
CHANGELOG_PATH = "CHANGELOG.md"


def upsert_document(
    session: Session,
    *,
    project_id: str,
    feature_id: str | None,
    kind: str,
    path: str,
    content: str,
) -> Document:
    document = session.scalar(
        select(Document).where(
            Document.project_id == project_id,
            Document.feature_id == feature_id,
            Document.path == path,
        )
    )
    if document is None:
        document = Document(
            project_id=project_id,
            feature_id=feature_id,
            kind=kind,
            path=path,
            content=content,
        )
        session.add(document)
    else:
        document.kind = kind
        document.content = content
    return document



def ensure_project_docs(session: Session, project: Project) -> None:
    upsert_document(
        session,
        project_id=project.id,
        feature_id=None,
        kind="project_memory",
        path=PROJECT_MEMORY_PATH,
        content=(
            "# Project Memory\n\n"
            "This document is maintained by AgentPM.\n\n"
            "## Architecture snapshot\n- Fill in during planning and execution.\n"
        ),
    )
    upsert_document(
        session,
        project_id=project.id,
        feature_id=None,
        kind="changelog",
        path=CHANGELOG_PATH,
        content="# Changelog\n\nAll notable changes to this project should be documented in this file.\n",
    )



def update_planning_docs(
    session: Session,
    *,
    project: Project,
    feature: Feature,
    feature_doc: str,
    project_memory: str,
    changelog: str,
) -> None:
    ensure_project_docs(session, project)
    feature_path = f".agentpm/features/{feature.id}.md"
    upsert_document(
        session,
        project_id=project.id,
        feature_id=feature.id,
        kind="feature_memory",
        path=feature_path,
        content=feature_doc or f"# {feature.title}\n\n{feature.goal}\n",
    )
    if project_memory:
        upsert_document(
            session,
            project_id=project.id,
            feature_id=None,
            kind="project_memory",
            path=PROJECT_MEMORY_PATH,
            content=project_memory,
        )
    if changelog:
        upsert_document(
            session,
            project_id=project.id,
            feature_id=None,
            kind="changelog",
            path=CHANGELOG_PATH,
            content=changelog,
        )
    record_operation(
        session,
        project_id=project.id,
        entity_type="feature",
        entity_id=feature.id,
        op_type="docs.updated",
        payload={"feature_path": feature_path},
    )



def materialize_documents(session: Session, project_id: str, feature_id: str | None, target_root: str | Path) -> None:
    root = Path(target_root)
    docs = session.scalars(
        select(Document).where(
            Document.project_id == project_id,
            (Document.feature_id.is_(None)) | (Document.feature_id == feature_id),
        )
    ).all()
    for doc in docs:
        path = root / doc.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(doc.content, encoding="utf-8")



def sync_documents_from_path(session: Session, project_id: str, feature_id: str | None, source_root: str | Path) -> None:
    root = Path(source_root)
    docs = session.scalars(
        select(Document).where(
            Document.project_id == project_id,
            (Document.feature_id.is_(None)) | (Document.feature_id == feature_id),
        )
    ).all()
    for doc in docs:
        path = root / doc.path
        if path.exists():
            doc.content = path.read_text(encoding="utf-8")
