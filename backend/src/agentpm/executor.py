from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from textwrap import dedent

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .bootstrap import load_repo_config
from .claude import ClaudeCodeError, claude_client
from .config import get_settings
from .docsync import materialize_documents, sync_documents_from_path
from .events import broker
from .github_api import create_draft_pr, parse_github_remote
from .gitops import (
    changed_files,
    commit_all,
    create_worktree,
    git_diff_stat,
    has_changes,
    push_branch,
    remove_worktree,
    sanitize_branch_fragment,
)
from .models import Feature, Project, Run, RunEvent, RunStatus, Task, TaskEdge, TaskStatus
from .ops import record_operation


settings = get_settings()


class TaskExecutor:
    def __init__(self) -> None:
        self.allowed_tools = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]

    async def execute(self, session_factory, run_id: str) -> None:
        with session_factory.begin() as session:
            run = self._load_run(session, run_id)
            if run is None:
                return
            task = run.task
            feature = run.feature
            project = feature.project
            repo_config = load_repo_config(project.repo_path)
            branch_fragment = sanitize_branch_fragment(task.planning_key or task.title)
            branch_name = f"agentpm/{branch_fragment}-{run.id[:8]}"
            worktree = create_worktree(project.id, run.id, project.repo_path, project.default_branch, branch_name)
            run.status = RunStatus.running.value
            run.started_at = datetime.now(timezone.utc)
            run.branch_name = branch_name
            run.worktree_path = str(worktree)
            task.status = TaskStatus.implementing.value
            task.branch_name = branch_name
            task.worktree_path = str(worktree)
            session.flush()
            materialize_documents(session, project.id, feature.id, worktree)
            self._write_event(session, run, "run.started", f"Started Claude Code run in {worktree}")

        try:
            await self._implementation_phase(session_factory, run_id, repo_config)
            await self._documentation_phase(session_factory, run_id, repo_config)
            await self._finalize_phase(session_factory, run_id)
        except Exception as exc:
            with session_factory.begin() as session:
                run = self._load_run(session, run_id)
                if run is None:
                    return
                run.status = RunStatus.failed.value
                run.error = str(exc)
                run.ended_at = datetime.now(timezone.utc)
                run.task.status = TaskStatus.blocked.value
                run.feature.needs_replan = True
                self._write_event(session, run, "run.failed", str(exc), level="error")
                session.flush()
            await broker.publish({"type": "run.failed", "run_id": run_id, "message": str(exc)})
        finally:
            with session_factory.begin() as session:
                run = self._load_run(session, run_id)
                if run and run.worktree_path:
                    try:
                        remove_worktree(run.feature.project.repo_path, run.worktree_path)
                    except Exception:
                        pass

    async def _implementation_phase(self, session_factory, run_id: str, repo_config: dict) -> None:
        with session_factory.begin() as session:
            run = self._load_run(session, run_id)
            assert run is not None
            feature = run.feature
            task = run.task
            project = feature.project
            prompt = self._build_implementation_prompt(project=project, feature=feature, task=task, repo_config=repo_config)
            worktree = run.worktree_path
            assert worktree is not None

        async def on_event(event: dict) -> None:
            message = self._render_stream_message(event)
            with session_factory() as inner:
                run = self._load_run(inner, run_id)
                if run is None:
                    return
                self._write_event(inner, run, "claude.stream", message, payload=event)
                if isinstance(event, dict) and event.get("session_id") and not run.session_id:
                    run.session_id = str(event.get("session_id"))
                inner.flush()
            await broker.publish({"type": "run.event", "run_id": run_id, "message": message, "payload": event})

        await claude_client.stream_json(
            prompt=prompt,
            cwd=worktree,
            allowed_tools=repo_config.get("claude", {}).get("allowed_tools", self.allowed_tools),
            system_prompt=(
                "You are a child implementation agent running under AgentPM. "
                "Implement only the assigned task in the current git worktree. "
                "Do not commit, push, or modify git configuration."
            ),
            on_event=on_event,
        )

    async def _documentation_phase(self, session_factory, run_id: str, repo_config: dict) -> None:
        with session_factory.begin() as session:
            run = self._load_run(session, run_id)
            assert run is not None
            worktree = run.worktree_path
            assert worktree is not None
            diff_stat = git_diff_stat(worktree)
            prompt = dedent(
                f"""
                Review the current git diff and update repository living documents if needed.
                Focus on:
                - CHANGELOG.md for user-visible changes
                - .agentpm/memory/PROJECT_MEMORY.md for architecture, workflow, or repo-knowledge changes
                - .agentpm/features/{run.feature.id}.md for current feature status and implementation notes

                Current diff stat:
                {diff_stat}

                Rules:
                - Keep edits concise and useful.
                - Do not commit or push.
                - If no documentation changes are needed, say so with minimal file changes.
                """
            ).strip()

        async def on_event(event: dict) -> None:
            message = self._render_stream_message(event)
            with session_factory() as inner:
                run = self._load_run(inner, run_id)
                if run is None:
                    return
                self._write_event(inner, run, "docs.stream", message, payload=event)
                inner.flush()
            await broker.publish({"type": "run.event", "run_id": run_id, "message": message, "payload": event})

        await claude_client.stream_json(
            prompt=prompt,
            cwd=worktree,
            allowed_tools=repo_config.get("claude", {}).get("allowed_tools", self.allowed_tools),
            system_prompt=(
                "You are the documentation maintenance agent. Update the changelog and project memory when the code diff warrants it."
            ),
            on_event=on_event,
        )

    async def _finalize_phase(self, session_factory, run_id: str) -> None:
        with session_factory.begin() as session:
            run = self._load_run(session, run_id)
            assert run is not None
            task = run.task
            feature = run.feature
            project = feature.project
            worktree = Path(run.worktree_path or project.repo_path)
            sync_documents_from_path(session, project.id, feature.id, worktree)
            session.flush()
            if has_changes(worktree):
                commit_sha = commit_all(worktree, f"agentpm: {task.title}")
                self._write_event(session, run, "git.commit", f"Created commit {commit_sha[:8]}")
                try:
                    push_branch(worktree, run.branch_name or "")
                    self._write_event(session, run, "git.push", f"Pushed branch {run.branch_name}")
                except Exception as exc:
                    self._write_event(session, run, "git.push_failed", str(exc), level="warning")
                pr_url = None
                repo_ref = parse_github_remote(project.repo_url)
                if settings.github_token and repo_ref and run.branch_name:
                    owner, repo = repo_ref
                    try:
                        pr = await create_draft_pr(
                            token=settings.github_token,
                            owner=owner,
                            repo=repo,
                            title=f"AgentPM: {task.title}",
                            body=(
                                f"Auto-generated by AgentPM for feature **{feature.title}**.\n\n"
                                f"Task: `{task.planning_key}`\n"
                            ),
                            head=run.branch_name,
                            base=project.default_branch,
                        )
                        pr_url = pr.get("html_url")
                        run.pr_url = pr_url
                        self._write_event(session, run, "github.pr", f"Created draft PR {pr_url}")
                    except Exception as exc:
                        self._write_event(session, run, "github.pr_failed", str(exc), level="warning")
                run.result_summary = self._build_result_summary(worktree)
                run.result_json = {
                    "changed_files": changed_files(worktree),
                    "pr_url": pr_url,
                }
                run.status = RunStatus.succeeded.value
                run.ended_at = datetime.now(timezone.utc)
                task.status = TaskStatus.review.value if pr_url else TaskStatus.done.value
                task.latest_run_id = run.id
                feature.status = "review" if pr_url else "active"
                feature.needs_replan = True
                record_operation(
                    session,
                    project_id=project.id,
                    entity_type="run",
                    entity_id=run.id,
                    op_type="run.completed",
                    payload=run.result_json,
                )
            else:
                run.result_summary = "Claude reported completion but no file changes were detected."
                run.status = RunStatus.succeeded.value
                run.ended_at = datetime.now(timezone.utc)
                task.status = TaskStatus.done.value
                feature.needs_replan = True
                self._write_event(session, run, "run.no_changes", run.result_summary, level="warning")
            session.flush()
        await broker.publish({"type": "run.finished", "run_id": run_id})

    def _load_run(self, session: Session, run_id: str) -> Run | None:
        return session.scalar(
            select(Run)
            .where(Run.id == run_id)
            .options(
                selectinload(Run.task).selectinload(Task.incoming_edges).selectinload(TaskEdge.from_task),
                selectinload(Run.feature).selectinload(Feature.project).selectinload(Project.documents),
                selectinload(Run.feature).selectinload(Feature.documents),
                selectinload(Run.events),
            )
        )

    def _write_event(
        self,
        session: Session,
        run: Run,
        event_type: str,
        message: str,
        *,
        level: str = "info",
        payload: dict | None = None,
    ) -> None:
        session.add(
            RunEvent(
                run_id=run.id,
                feature_id=run.feature_id,
                event_type=event_type,
                level=level,
                message=message,
                payload=payload or {},
            )
        )

    def _build_implementation_prompt(self, *, project: Project, feature: Feature, task: Task, repo_config: dict) -> str:
        depends_on = [edge.from_task.planning_key for edge in task.incoming_edges if edge.from_task]
        commands = repo_config.get("commands", {})
        docs_hint = f".agentpm/features/{feature.id}.md"
        return dedent(
            f"""
            Implement the assigned task in the current git worktree.

            Project: {project.name}
            Feature: {feature.title}
            Feature goal:
            {feature.goal}

            Task key: {task.planning_key}
            Task title: {task.title}
            Task description:
            {task.description}

            Acceptance criteria:
            {task.acceptance_criteria}

            Dependency tasks already considered complete or in review:
            {depends_on}

            Repository commands:
            test: {commands.get('test', '')}
            lint: {commands.get('lint', '')}
            format: {commands.get('format', '')}

            Read these files first if present:
            - AGENTS.md
            - CLAUDE.md
            - .agentpm/memory/PROJECT_MEMORY.md
            - {docs_hint}

            Requirements:
            - Make the smallest coherent change that satisfies the task.
            - Update or add tests when behavior changes.
            - Run relevant test/lint commands.
            - Do not commit or push; the parent orchestrator will do that.
            - Keep the feature doc and project memory accurate if code changes reveal new facts.
            """
        ).strip()

    def _render_stream_message(self, event: dict) -> str:
        if not isinstance(event, dict):
            return str(event)
        if event.get("type") == "text":
            return event.get("message", "")
        if event.get("type") == "stream_event":
            payload = event.get("event", {})
            delta = payload.get("delta", {})
            if delta.get("type") == "text_delta":
                return delta.get("text", "")
            if payload.get("type"):
                return payload.get("type")
        if event.get("type") == "result":
            return event.get("result", "completed")
        if event.get("type") == "system" and event.get("subtype") == "api_retry":
            return f"API retry {event.get('attempt')}/{event.get('max_retries')}"
        return json.dumps(event)[:1000]

    def _build_result_summary(self, worktree: Path) -> str:
        diff_stat = git_diff_stat(worktree)
        files = changed_files(worktree)
        return "\n".join(
            ["Execution completed.", diff_stat or "", f"Files changed: {', '.join(files) or 'none'}"]
        ).strip()


executor = TaskExecutor()
