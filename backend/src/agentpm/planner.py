from __future__ import annotations

import re
from datetime import datetime, timezone
from textwrap import dedent

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .claude import ClaudeCodeError, claude_client
from .docsync import update_planning_docs
from .gitops import list_repo_files
from .models import Feature, FeatureMessage, Project, Task, TaskEdge, TaskStatus
from .ops import record_operation
from .schemas import PlanningResponse


TERMINAL_TASK_STATUSES = {TaskStatus.done.value, TaskStatus.review.value, TaskStatus.merged.value}


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")[:80] or "task"


class FeaturePlanner:
    async def plan_feature(self, session: Session, feature_id: str) -> Feature:
        feature = session.scalar(
            select(Feature)
            .where(Feature.id == feature_id)
            .options(
                selectinload(Feature.project).selectinload(Project.documents),
                selectinload(Feature.messages),
                selectinload(Feature.tasks).selectinload(Task.incoming_edges).selectinload(TaskEdge.from_task),
                selectinload(Feature.documents),
            )
        )
        if feature is None:
            raise ValueError(f"Feature {feature_id} not found")

        project = feature.project
        prompt = self._build_prompt(project=project, feature=feature)
        allowed_tools = ["Read", "Glob", "Grep", "Bash"]
        plan: PlanningResponse
        try:
            response = await claude_client.run_json(
                prompt=prompt,
                cwd=project.repo_path,
                allowed_tools=allowed_tools,
                system_prompt=(
                    "You are the master planning agent. Maintain a task graph for the feature, "
                    "emit stable planning_key values, and respond with JSON only."
                ),
                json_schema=PlanningResponse.model_json_schema(),
            )
            structured = response.get("structured_output") or response
            plan = PlanningResponse.model_validate(structured)
        except (ClaudeCodeError, Exception):
            plan = self._fallback_plan(feature)

        self._apply_plan(session=session, project=project, feature=feature, plan=plan)
        feature.summary = plan.summary
        feature.status = plan.status
        feature.needs_replan = False
        feature.last_planned_at = datetime.now(timezone.utc)
        feature.updated_at = datetime.now(timezone.utc)
        update_planning_docs(
            session,
            project=project,
            feature=feature,
            feature_doc=plan.feature_doc,
            project_memory=plan.project_memory,
            changelog=plan.changelog,
        )
        session.add(
            FeatureMessage(
                feature_id=feature.id,
                role="assistant",
                content=(
                    f"Plan updated. {plan.summary}\n\n"
                    f"Tasks in graph: {', '.join(task.planning_key for task in plan.tasks) or 'none'}"
                ),
                metadata_json={"kind": "plan_update"},
            )
        )
        record_operation(
            session,
            project_id=project.id,
            entity_type="feature",
            entity_id=feature.id,
            op_type="feature.planned",
            payload=plan.model_dump(),
        )
        session.flush()
        return feature

    def _build_prompt(self, *, project: Project, feature: Feature) -> str:
        repo_files = list_repo_files(project.repo_path, limit=250)
        recent_messages = feature.messages[-12:]
        existing_tasks = []
        for task in sorted(feature.tasks, key=lambda item: (item.archived, item.priority, item.title)):
            depends_on = [edge.from_task.planning_key for edge in task.incoming_edges if edge.from_task]
            existing_tasks.append(
                {
                    "id": task.id,
                    "planning_key": task.planning_key,
                    "title": task.title,
                    "status": task.status,
                    "priority": task.priority,
                    "depends_on": depends_on,
                    "archived": task.archived,
                    "latest_run_id": task.latest_run_id,
                }
            )
        messages_block = "\n".join(f"- {msg.role}: {msg.content}" for msg in recent_messages)
        docs = {doc.path: doc.content for doc in feature.documents}
        project_memory = next((doc.content for doc in feature.project.documents if doc.kind == "project_memory"), "")
        feature_doc = docs.get(f".agentpm/features/{feature.id}.md", "")
        return dedent(
            f"""
            Project name: {project.name}
            Repository root: {project.repo_path}
            Default branch: {project.default_branch}

            Feature ID: {feature.id}
            Feature title: {feature.title}
            Feature goal:
            {feature.goal}

            Acceptance criteria:
            {feature.acceptance_criteria}

            Current feature summary:
            {feature.summary}

            Recent feature chat:
            {messages_block or '- no messages yet'}

            Existing tasks:
            {existing_tasks}

            Project memory:
            {project_memory}

            Existing feature doc:
            {feature_doc}

            Repository file map (truncated):
            {repo_files}

            Produce a full desired task graph for this feature.
            Requirements:
            - Use stable kebab-case planning_key values.
            - Break work into independently reviewable tasks.
            - Add or remove tasks as needed based on the latest state.
            - Only mark a task ready when its prerequisites are captured in depends_on.
            - Prefer 3-8 tasks total unless the feature clearly requires more.
            - Keep feature_doc as markdown suitable for `.agentpm/features/<id>.md`.
            - Keep project_memory as the authoritative living project memory markdown if it should change, otherwise return the existing memory.
            - Keep changelog as the full desired CHANGELOG.md content when user-visible changes are expected.
            - Status should be one of draft, planning, ready, active, review, done, blocked.
            - Return JSON only.
            """
        ).strip()

    def _fallback_plan(self, feature: Feature) -> PlanningResponse:
        key = slugify(feature.title)
        return PlanningResponse(
            summary="Generated a fallback one-task plan because planner JSON was unavailable.",
            status="active",
            feature_doc=f"# {feature.title}\n\n## Goal\n{feature.goal}\n",
            project_memory=(
                "# Project Memory\n\n"
                "AgentPM fallback planning mode was used. Replace with richer project memory after the first successful planning pass.\n"
            ),
            changelog="# Changelog\n\n- Planned feature work in AgentPM.\n",
            tasks=[
                {
                    "planning_key": key,
                    "title": feature.title,
                    "description": feature.goal,
                    "acceptance_criteria": feature.acceptance_criteria,
                    "priority": 1,
                    "labels": ["feature"],
                    "depends_on": [],
                    "auto_execute": True,
                    "status": "ready",
                }
            ],
        )

    def _apply_plan(self, *, session: Session, project: Project, feature: Feature, plan: PlanningResponse) -> None:
        existing_by_key = {task.planning_key: task for task in feature.tasks}
        desired_keys = {task.planning_key for task in plan.tasks}

        for planning_task in plan.tasks:
            task = existing_by_key.get(planning_task.planning_key)
            if task is None:
                task = Task(
                    feature_id=feature.id,
                    planning_key=planning_task.planning_key,
                    title=planning_task.title,
                    description=planning_task.description,
                    status=planning_task.status,
                    priority=planning_task.priority,
                    acceptance_criteria=planning_task.acceptance_criteria,
                    labels=planning_task.labels,
                    auto_execute=planning_task.auto_execute,
                    archived=False,
                )
                session.add(task)
                session.flush()
                existing_by_key[planning_task.planning_key] = task
            else:
                if task.status not in TERMINAL_TASK_STATUSES:
                    task.title = planning_task.title
                    task.description = planning_task.description
                    task.priority = planning_task.priority
                    task.acceptance_criteria = planning_task.acceptance_criteria
                    task.labels = planning_task.labels
                    task.auto_execute = planning_task.auto_execute
                    task.archived = False
                    if task.status not in {TaskStatus.implementing.value, TaskStatus.review.value}:
                        task.status = planning_task.status

        for key, task in existing_by_key.items():
            if key not in desired_keys and task.status not in TERMINAL_TASK_STATUSES:
                task.archived = True
                task.status = TaskStatus.archived.value

        session.flush()
        feature_tasks = {task.planning_key: task for task in feature.tasks}
        for task in feature.tasks:
            for edge in list(task.outgoing_edges):
                session.delete(edge)
        session.flush()
        for planning_task in plan.tasks:
            target = feature_tasks[planning_task.planning_key]
            for dep_key in planning_task.depends_on:
                source = feature_tasks.get(dep_key)
                if source is None or source.id == target.id:
                    continue
                session.add(TaskEdge(from_task_id=source.id, to_task_id=target.id))


planner = FeaturePlanner()
