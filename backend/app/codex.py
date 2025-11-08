from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
from asyncio.subprocess import PIPE
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Optional


class CodexInvocationError(RuntimeError):
    """Raised when the Codex CLI exits with a non-zero status."""


@dataclass(slots=True)
class SessionPaths:
    codex_home: Path
    workspace_dir: Path


class CodexRunner:
    """Wrapper around the Codex CLI providing async JSONL streaming."""

    def __init__(
        self,
        codex_binary: Path,
        *,
        model_alias: str,
        gateway_url: str,
        static_api_key: str,
        data_read_dir: Path,
    ) -> None:
        self.codex_binary = codex_binary
        self.model_alias = model_alias
        self.gateway_url = gateway_url.rstrip("/")
        self.static_api_key = static_api_key
        self.data_read_dir = data_read_dir

    async def stream_turn(
        self,
        *,
        prompt: str,
        session_paths: SessionPaths,
        llm_session_id: str,
        codex_thread_id: Optional[str],
        extra_env: Optional[Dict[str, str]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Spawn codex exec and yield parsed JSON events."""

        cmd = [
            str(self.codex_binary),
            "exec",
        ]

        # Prefer modern Codex flag; allow override for older versions.
        # Example overrides:
        #   CODEX_JSON_FLAG="--json"
        #   CODEX_JSON_FLAG="--experimental-json"
        json_flag_env = os.environ.get("CODEX_JSON_FLAG", "--json")
        json_flags = [flag for flag in shlex.split(json_flag_env) if flag.strip()]
        if not json_flags:
            json_flags = ["--json"]

        cmd.extend(json_flags)

        cmd.extend(
            [
                "--dangerously-bypass-approvals-and-sandbox",
                "--model",
                self.model_alias,
                "--cd",
                str(session_paths.workspace_dir),
                # optional, but often useful when running in temp dirs:
                "--skip-git-repo-check",
            ]
        )

        # Use Codex exec resume syntax when thread id present:
        # codex exec --json resume SESSION_ID "next prompt"
        if codex_thread_id:
            cmd.extend(["resume", codex_thread_id, prompt])
        else:
            cmd.append(prompt)

        env = os.environ.copy()
        env.update(
            {
                "CODEX_HOME": str(session_paths.codex_home),
                "OPENAI_BASE_URL": self.gateway_url,
                "CODEX_API_KEY": self.static_api_key,
                "LLM_SESSION_ID": llm_session_id,
                "DATA_READ_DIR": str(self.data_read_dir),
                "DATA_WRITE_DIR": str(session_paths.workspace_dir),
            }
        )

        if extra_env:
            env.update(extra_env)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=PIPE,
            stderr=PIPE,
            env=env,
        )

        stderr_chunks: list[bytes] = []

        async def _read_stderr() -> None:
            if not process.stderr:
                return
            async for chunk in process.stderr:
                stderr_chunks.append(chunk)

        stderr_task = asyncio.create_task(_read_stderr())

        try:
            if not process.stdout:
                raise CodexInvocationError("Codex process missing stdout pipe.")

            async for raw_line in process.stdout:
                line = raw_line.decode("utf-8").strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise CodexInvocationError(
                        f"Failed to decode Codex event: {line}"
                    ) from exc
                yield payload

            return_code = await process.wait()
            await stderr_task

            if return_code != 0:
                stderr_text = b"".join(stderr_chunks).decode("utf-8", errors="replace")
                raise CodexInvocationError(
                    f"Codex exited with code {return_code}: {stderr_text.strip()}"
                )

        finally:
            if not stderr_task.done():
                stderr_task.cancel()
                with contextlib.suppress(Exception):
                    await stderr_task