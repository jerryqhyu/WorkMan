from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import yaml

DEFAULT_PROJECT_YAML = {
    "name": "Managed Project",
    "commands": {
        "test": "pytest -q",
        "lint": "ruff check .",
        "format": "ruff format .",
    },
    "policies": {
        "auto_execute": True,
        "max_parallel_runs": 2,
    },
    "claude": {
        "allowed_tools": ["Read", "Edit", "Write", "Glob", "Grep", "Bash"],
    },
}

DEFAULT_AGENTS_MD = dedent(
    """
    # AGENTS.md

    - Prefer small, reviewable changes.
    - Update tests when behavior changes.
    - Update CHANGELOG.md for user-visible changes.
    - Keep .agentpm/memory/PROJECT_MEMORY.md current when architecture or workflow conventions change.
    - Do not commit secrets.
    """
).strip() + "\n"

DEFAULT_CLAUDE_MD = dedent(
    """
    # CLAUDE.md

    Project-level instructions for Claude Code.

    ## Workflow
    - Read `.agentpm/memory/PROJECT_MEMORY.md` and the active feature doc before making changes.
    - Implement only the requested task.
    - Run the configured test and lint commands before finishing.
    - Do not create commits or push branches unless explicitly asked by the parent orchestrator.
    """
).strip() + "\n"

DEFAULT_PROJECT_MEMORY = dedent(
    """
    # Project Memory

    This living document is maintained by AgentPM and project contributors.

    ## Architecture snapshot
    - Describe the major subsystems.

    ## Conventions
    - Record build, test, release, and review norms here.

    ## Current risks
    - Track risks, migration notes, and temporary workarounds.
    """
).strip() + "\n"

DEFAULT_CHANGELOG = dedent(
    """
    # Changelog

    All notable changes to this project should be documented in this file.
    """
).strip() + "\n"


def bootstrap_repo(repo_path: str | Path, project_name: str | None = None) -> None:
    root = Path(repo_path)
    (root / ".agentpm" / "memory").mkdir(parents=True, exist_ok=True)
    (root / ".agentpm" / "features").mkdir(parents=True, exist_ok=True)

    project_yaml_path = root / ".agentpm" / "project.yaml"
    if not project_yaml_path.exists():
        content = dict(DEFAULT_PROJECT_YAML)
        if project_name:
            content["name"] = project_name
        project_yaml_path.write_text(yaml.safe_dump(content, sort_keys=False), encoding="utf-8")

    for path, content in {
        root / "AGENTS.md": DEFAULT_AGENTS_MD,
        root / "CLAUDE.md": DEFAULT_CLAUDE_MD,
        root / ".agentpm" / "memory" / "PROJECT_MEMORY.md": DEFAULT_PROJECT_MEMORY,
        root / "CHANGELOG.md": DEFAULT_CHANGELOG,
    }.items():
        if not path.exists():
            path.write_text(content, encoding="utf-8")


def load_repo_config(repo_path: str | Path) -> dict:
    path = Path(repo_path) / ".agentpm" / "project.yaml"
    if not path.exists():
        return DEFAULT_PROJECT_YAML
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    merged = dict(DEFAULT_PROJECT_YAML)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
