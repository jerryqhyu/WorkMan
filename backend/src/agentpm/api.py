from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import bootstrap_repo
from .database import SessionLocal, get_db, init_db
from .docsync import ensure_project_docs
from .events import broker
from .gitops import GitError, detect_default_branch, detect_repo_url, ensure_git_repo
from .models import Feature, FeatureMessage, Project, Run, Task, TaskEdge
from .ops import record_operation
from .orchestrator import Orchestrator
from .schemas import CreateFeatureRequest, FeatureChatRequest, ImportProjectRequest, UpdateTaskStatusRequest
from .serializers import feature_to_dto, run_to_dto, task_to_dto


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    orchestrator = Orchestrator(SessionLocal)
    app.state.orchestrator = orchestrator
    await orchestrator.start()
    yield
    await orchestrator.stop()


app = FastAPI(title="AgentPM", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/projects")
def list_projects(db: Session = Depends(get_db)) -> list[dict]:
    projects = db.scalars(select(Project).order_by(Project.created_at.desc())).all()
    return [
        {
            "id": project.id,
            "name": project.name,
            "repo_path": project.repo_path,
            "repo_url": project.repo_url,
            "default_branch": project.default_branch,
            "metadata_json": project.metadata_json,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
        }
        for project in projects
    ]


@app.post("/projects/import")
def import_project(
    payload: ImportProjectRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    repo_path = Path(payload.repo_path).expanduser().resolve()
    if not repo_path.exists():
        raise HTTPException(status_code=400, detail="Repository path does not exist")
    try:
        ensure_git_repo(repo_path)
    except GitError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    existing = db.scalar(select(Project).where(Project.repo_path == str(repo_path)))
    if existing:
        return {"project_id": existing.id}
    bootstrap_repo(repo_path, payload.name)
    project = Project(
        name=payload.name or repo_path.name,
        repo_path=str(repo_path),
        repo_url=detect_repo_url(repo_path),
        default_branch=detect_default_branch(repo_path),
        metadata_json={"source": "local"},
    )
    db.add(project)
    db.flush()
    ensure_project_docs(db, project)
    record_operation(
        db,
        project_id=project.id,
        entity_type="project",
        entity_id=project.id,
        op_type="project.imported",
        payload={"repo_path": str(repo_path)},
    )
    return {"project_id": project.id}


@app.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db)) -> dict:
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(selectinload(Project.features), selectinload(Project.documents))
    )
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    features = [feature_to_dto(feature).model_dump(mode="json") for feature in project.features]
    return {
        "id": project.id,
        "name": project.name,
        "repo_path": project.repo_path,
        "repo_url": project.repo_url,
        "default_branch": project.default_branch,
        "metadata_json": project.metadata_json,
        "features": features,
        "documents": [
            {"id": doc.id, "kind": doc.kind, "path": doc.path, "content": doc.content, "updated_at": doc.updated_at}
            for doc in project.documents
        ],
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


@app.post("/projects/{project_id}/features")
async def create_feature(
    project_id: str,
    payload: CreateFeatureRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    feature = Feature(
        project_id=project.id,
        title=payload.title,
        goal=payload.goal,
        acceptance_criteria=payload.acceptance_criteria,
        auto_execute=payload.auto_execute,
        status="planning",
        needs_replan=True,
    )
    db.add(feature)
    db.flush()
    db.add(
        FeatureMessage(
            feature_id=feature.id,
            role="user",
            content=f"Create a new feature plan for: {payload.goal}",
            metadata_json={"kind": "feature_create"},
        )
    )
    record_operation(
        db,
        project_id=project.id,
        entity_type="feature",
        entity_id=feature.id,
        op_type="feature.created",
        payload=payload.model_dump(),
    )
    await request.app.state.orchestrator.request_replan(feature.id)
    return {"feature_id": feature.id}


@app.get("/projects/{project_id}/features")
def list_features(project_id: str, db: Session = Depends(get_db)) -> list[dict]:
    features = db.scalars(
        select(Feature)
        .where(Feature.project_id == project_id)
        .options(
            selectinload(Feature.messages),
            selectinload(Feature.tasks).selectinload(Task.incoming_edges),
            selectinload(Feature.documents),
        )
        .order_by(Feature.created_at.desc())
    ).all()
    return [feature_to_dto(feature).model_dump(mode="json") for feature in features]


@app.get("/features/{feature_id}")
def get_feature(feature_id: str, db: Session = Depends(get_db)) -> dict:
    feature = db.scalar(
        select(Feature)
        .where(Feature.id == feature_id)
        .options(
            selectinload(Feature.messages),
            selectinload(Feature.tasks).selectinload(Task.incoming_edges).selectinload(TaskEdge.from_task),
            selectinload(Feature.documents),
        )
    )
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature_to_dto(feature).model_dump(mode="json")


@app.post("/features/{feature_id}/chat")
async def feature_chat(
    feature_id: str,
    payload: FeatureChatRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    feature = db.get(Feature, feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    db.add(FeatureMessage(feature_id=feature.id, role="user", content=payload.message, metadata_json={"kind": "chat"}))
    feature.needs_replan = True
    feature.status = "planning"
    db.flush()
    await request.app.state.orchestrator.request_replan(feature_id)
    return {"ok": True}


@app.get("/features/{feature_id}/runs")
def list_runs(feature_id: str, db: Session = Depends(get_db)) -> list[dict]:
    runs = db.scalars(select(Run).where(Run.feature_id == feature_id).options(selectinload(Run.events)).order_by(Run.created_at.desc())).all()
    return [run_to_dto(run).model_dump(mode="json") for run in runs]


@app.get("/runs/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.scalar(select(Run).where(Run.id == run_id).options(selectinload(Run.events)))
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run_to_dto(run).model_dump(mode="json")


@app.post("/tasks/{task_id}/spawn")
async def spawn_task(task_id: str, request: Request, db: Session = Depends(get_db)) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    run_id = await request.app.state.orchestrator.spawn_task_run(task_id)
    return {"run_id": run_id}


@app.patch("/tasks/{task_id}")
def update_task(task_id: str, payload: UpdateTaskStatusRequest, db: Session = Depends(get_db)) -> dict:
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = payload.status
    db.flush()
    return task_to_dto(task).model_dump(mode="json")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await broker.connect_websocket(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        broker.disconnect_websocket(websocket)



def create_app() -> FastAPI:
    return app
