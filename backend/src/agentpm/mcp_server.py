from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from mcp.server.fastmcp import FastMCP

from .database import SessionLocal, init_db
from .models import Document, Feature, Project, Run, Task

mcp = FastMCP("AgentPM", json_response=True)


def _init() -> None:
    init_db()


@mcp.tool()
def list_projects() -> list[dict]:
    _init()
    with SessionLocal() as session:
        projects = session.scalars(select(Project).order_by(Project.created_at.desc())).all()
        return [
            {
                "id": project.id,
                "name": project.name,
                "repo_path": project.repo_path,
                "default_branch": project.default_branch,
            }
            for project in projects
        ]


@mcp.tool()
def list_features(project_id: str) -> list[dict]:
    _init()
    with SessionLocal() as session:
        features = session.scalars(select(Feature).where(Feature.project_id == project_id).order_by(Feature.created_at.desc())).all()
        return [
            {
                "id": feature.id,
                "title": feature.title,
                "status": feature.status,
                "summary": feature.summary,
            }
            for feature in features
        ]


@mcp.tool()
def list_tasks(feature_id: str) -> list[dict]:
    _init()
    with SessionLocal() as session:
        tasks = session.scalars(select(Task).where(Task.feature_id == feature_id).order_by(Task.priority, Task.created_at)).all()
        return [
            {
                "id": task.id,
                "planning_key": task.planning_key,
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
            }
            for task in tasks
            if not task.archived
        ]


@mcp.tool()
def get_run(run_id: str) -> dict:
    _init()
    with SessionLocal() as session:
        run = session.scalar(select(Run).where(Run.id == run_id).options(selectinload(Run.events)))
        if run is None:
            return {"error": "Run not found"}
        return {
            "id": run.id,
            "status": run.status,
            "task_id": run.task_id,
            "branch_name": run.branch_name,
            "pr_url": run.pr_url,
            "summary": run.result_summary,
            "events": [
                {"type": event.event_type, "level": event.level, "message": event.message}
                for event in run.events[-50:]
            ],
        }


@mcp.resource("feature://{feature_id}")
def feature_resource(feature_id: str) -> str:
    _init()
    with SessionLocal() as session:
        feature = session.scalar(
            select(Feature)
            .where(Feature.id == feature_id)
            .options(selectinload(Feature.messages), selectinload(Feature.tasks), selectinload(Feature.documents))
        )
        if feature is None:
            return "Feature not found"
        tasks = "\n".join(f"- [{task.status}] {task.title} ({task.planning_key})" for task in feature.tasks if not task.archived)
        messages = "\n".join(f"- {msg.role}: {msg.content}" for msg in feature.messages[-10:])
        return (
            f"# {feature.title}\n\n"
            f"Status: {feature.status}\n\n"
            f"Goal:\n{feature.goal}\n\n"
            f"Summary:\n{feature.summary}\n\n"
            f"## Tasks\n{tasks or '- none'}\n\n"
            f"## Recent messages\n{messages or '- none'}\n"
        )


@mcp.resource("project-memory://{project_id}")
def project_memory_resource(project_id: str) -> str:
    _init()
    with SessionLocal() as session:
        document = session.scalar(
            select(Document).where(Document.project_id == project_id, Document.kind == "project_memory")
        )
        return document.content if document else "No project memory found"


@mcp.prompt()
def review_feature(feature_id: str) -> str:
    return f"Review the current status of feature {feature_id}, summarize the task graph, and call AgentPM tools if more context is needed."



def run_mcp(port: int = 8766, transport: str = "streamable-http") -> None:
    _init()
    try:
        mcp.settings.port = port
    except Exception:
        pass
    mcp.run(transport=transport)
