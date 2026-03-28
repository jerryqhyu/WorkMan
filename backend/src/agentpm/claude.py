from __future__ import annotations

import asyncio
import json
import os
import shutil
from collections.abc import Awaitable, Callable
from typing import Any

from .config import get_settings


class ClaudeCodeError(RuntimeError):
    pass


settings = get_settings()


class ClaudeCodeClient:
    def __init__(self, binary: str = "claude") -> None:
        self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    async def run_json(
        self,
        *,
        prompt: str,
        cwd: str,
        allowed_tools: list[str] | None = None,
        system_prompt: str | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not self.available():
            if settings.allow_fake_claude:
                return {"structured_output": {}}
            raise ClaudeCodeError("Claude Code CLI not found on PATH.")
        cmd = [self.binary, "--bare", "-p", prompt, "--output-format", "json"]
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        if system_prompt:
            cmd.extend(["--append-system-prompt", system_prompt])
        if json_schema:
            cmd.extend(["--json-schema", json.dumps(json_schema)])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise ClaudeCodeError(stderr.decode("utf-8", errors="ignore") or stdout.decode("utf-8", errors="ignore"))
        text = stdout.decode("utf-8", errors="ignore")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise ClaudeCodeError(f"Failed to parse Claude output as JSON: {text}") from exc

    async def stream_json(
        self,
        *,
        prompt: str,
        cwd: str,
        allowed_tools: list[str] | None = None,
        system_prompt: str | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None]] | None = None,
    ) -> dict[str, Any]:
        if not self.available():
            if settings.allow_fake_claude:
                fake = {"type": "result", "result": "fake Claude execution completed"}
                if on_event:
                    await on_event(fake)
                return fake
            raise ClaudeCodeError("Claude Code CLI not found on PATH.")
        cmd = [
            self.binary,
            "--bare",
            "-p",
            prompt,
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
        ]
        if allowed_tools:
            cmd.extend(["--allowedTools", ",".join(allowed_tools)])
        if system_prompt:
            cmd.extend(["--append-system-prompt", system_prompt])
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        final_event: dict[str, Any] = {}
        assert proc.stdout is not None
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="ignore").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "text", "message": line}
            final_event = event
            if on_event:
                await on_event(event)
        stderr = await proc.stderr.read() if proc.stderr else b""
        return_code = await proc.wait()
        if return_code != 0:
            raise ClaudeCodeError(stderr.decode("utf-8", errors="ignore") or json.dumps(final_event))
        return final_event


claude_client = ClaudeCodeClient()
