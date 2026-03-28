from __future__ import annotations

import asyncio
from contextlib import suppress

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import load_repo_config
from .config import get_settings
from .events import broker
from .executor import executor
from .models import Feature, Run, RunStatus, Task, TaskEdge, TaskStatus
from .planner import planner


settings = get_settings()


class Orchestrator:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self._loop_task: asyncio.Task | None = None
        self._active_runs: dict[str, asyncio.Task] = {}
        self._stopped = asyncio.Event()

    async def start(self) -> None:
        self._stopped.clear()
        self._loop_task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopped.set()
        if self._loop_task:
            self._loop_task.cancel()
            with suppress(asyncio.CancelledError):
                await self._loop_task
        for task in list(self._active_runs.values()):
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    async def request_replan(self, feature_id: str) -> None:
        with self.session_factory.begin() as session:
            feature = session.get(Feature, feature_id)
            if feature:
                feature.needs_replan = True
                feature.status = "planning"
                session.flush()
        await broker.publish({"type": "feature.replan_requested", "feature_id": feature_id})

    async def spawn_task_run(self, task_id: str) -> str | None:
        with self.session_factory.begin() as session:
            task = session.scalar(
                select(Task)
                .where(Task.id == task_id)
                .options(selectinload(Task.feature).selectinload(Feature.project))
            )
            if task is None:
                return None
            existing = session.scalar(
                select(Run).where(Run.task_id == task.id, Run.status.in_([RunStatus.queued.value, RunStatus.running.value]))
            )
            if existing:
                return existing.id
            run = Run(project_id=task.feature.project_id, feature_id=task.feature_id, task_id=task.id, status=RunStatus.queued.value)
            session.add(run)
            session.flush()
            task.status = TaskStatus.leased.value
            task.latest_run_id = run.id
            run_id = run.id
        self._start_run_task(run_id)
        return run_id

    def _start_run_task(self, run_id: str) -> None:
        if run_id in self._active_runs:
            return
        task = asyncio.create_task(self._run_and_cleanup(run_id))
        self._active_runs[run_id] = task

    async def _run_and_cleanup(self, run_id: str) -> None:
        try:
            await executor.execute(self.session_factory, run_id)
        finally:
            self._active_runs.pop(run_id, None)

    async def _loop(self) -> None:
        while not self._stopped.is_set():
            await self._tick()
            await asyncio.sleep(settings.planner_heartbeat_seconds)

    async def _tick(self) -> None:
        await self._plan_pending_features()
        await self._queue_ready_tasks()
        await self._update_feature_statuses()

    async def _plan_pending_features(self) -> None:
        with self.session_factory.begin() as session:
            feature_ids = [row[0] for row in session.execute(select(Feature.id).where(Feature.needs_replan.is_(True))).all()]
        for feature_id in feature_ids:
            try:
                with self.session_factory.begin() as session:
                    await planner.plan_feature(session, feature_id)
                    session.flush()
                await broker.publish({"type": "feature.planned", "feature_id": feature_id})
            except Exception as exc:
                with self.session_factory.begin() as session:
                    feature = session.get(Feature, feature_id)
                    if feature:
                        feature.status = "blocked"
                        feature.summary = f"Planner failed: {exc}"
                        feature.needs_replan = False
                        session.flush()
                await broker.publish({"type": "feature.plan_failed", "feature_id": feature_id, "message": str(exc)})

    async def _queue_ready_tasks(self) -> None:
        new_run_ids: list[str] = []
        with self.session_factory.begin() as session:
            tasks = session.scalars(
                select(Task)
                .where(Task.status.in_([TaskStatus.ready.value, TaskStatus.backlog.value]))
                .options(selectinload(Task.feature).selectinload(Feature.project), selectinload(Task.incoming_edges).selectinload(TaskEdge.from_task))
            ).all()

            queued = 0
            for task in tasks:
                if task.archived or not task.auto_execute or not task.feature.auto_execute:
                    continue
                repo_config = load_repo_config(task.feature.project.repo_path)
                max_parallel = int(repo_config.get("policies", {}).get("max_parallel_runs", settings.default_parallel_runs))
                if len(self._active_runs) + queued >= max_parallel:
                    continue
                if not self._dependencies_satisfied(session, task):
                    task.status = TaskStatus.blocked.value
                    continue
                if task.status == TaskStatus.backlog.value:
                    task.status = TaskStatus.ready.value
                existing = session.scalar(
                    select(Run).where(Run.task_id == task.id, Run.status.in_([RunStatus.queued.value, RunStatus.running.value]))
                )
                if existing:
                    continue
                run = Run(project_id=task.feature.project_id, feature_id=task.feature_id, task_id=task.id, status=RunStatus.queued.value)
                session.add(run)
                session.flush()
                task.status = TaskStatus.leased.value
                task.latest_run_id = run.id
                new_run_ids.append(run.id)
                queued += 1
        for run_id in new_run_ids:
            if run_id not in self._active_runs:
                self._start_run_task(run_id)

    def _dependencies_satisfied(self, session: Session, task: Task) -> bool:
        if not task.incoming_edges:
            return True
        allowed = {TaskStatus.review.value, TaskStatus.merged.value, TaskStatus.done.value}
        for edge in task.incoming_edges:
            if edge.from_task is None:
                continue
            predecessor = session.get(Task, edge.from_task_id)
            if predecessor is None or predecessor.status not in allowed:
                return False
        return True

    async def _update_feature_statuses(self) -> None:
        with self.session_factory.begin() as session:
            features = session.scalars(select(Feature).options(selectinload(Feature.tasks))).all()
            for feature in features:
                tasks = [task for task in feature.tasks if not task.archived]
                if not tasks:
                    continue
                statuses = {task.status for task in tasks}
                if statuses <= {TaskStatus.done.value, TaskStatus.merged.value, TaskStatus.review.value}:
                    feature.status = "review" if TaskStatus.review.value in statuses else "done"
                elif TaskStatus.implementing.value in statuses or TaskStatus.leased.value in statuses:
                    feature.status = "active"
                elif TaskStatus.blocked.value in statuses and len(statuses) == 1:
                    feature.status = "blocked"
            session.flush()
