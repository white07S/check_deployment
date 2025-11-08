from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import (
    DEFAULT_ALLOWED_PYTHON_LIBS,
    DEFAULT_CODEX_VERSION,
    PathConfig,
    load_codex_version_lock,
    write_codex_version_lock,
)


class RuntimePreparationError(RuntimeError):
    """Raised when the runtime environment cannot be prepared."""


@dataclass(slots=True)
class RuntimeState:
    codex_binary: Path
    venv_python: Path
    codex_version: str


class RuntimeInitializer:
    """Ensures filesystem layout, Python environment, and Codex installation."""

    def __init__(
        self,
        paths: PathConfig,
        *,
        codex_version: str | None = None,
        python_libs: Sequence[str] = DEFAULT_ALLOWED_PYTHON_LIBS,
    ) -> None:
        self.paths = paths
        self.codex_version = codex_version or os.environ.get("CODEX_VERSION", DEFAULT_CODEX_VERSION)
        # Preserve order while removing duplicates
        seen: dict[str, None] = {}
        for lib in python_libs:
            seen.setdefault(lib, None)
        self.python_libs = tuple(seen.keys())
        self.venv_dir = self.paths.codex_runtime_root / "venv"
        self._state: RuntimeState | None = None

    @property
    def state(self) -> RuntimeState:
        if self._state is None:
            raise RuntimePreparationError("RuntimeInitializer.prepare() must run before usage.")
        return self._state

    def prepare(self) -> RuntimeState:
        self._ensure_directories()
        self._sync_global_instructions()
        self._ensure_python_env()
        self._ensure_codex_install()

        codex_binary = self._resolve_codex_binary()
        venv_python = self._resolve_python_binary()

        self._state = RuntimeState(
            codex_binary=codex_binary,
            venv_python=venv_python,
            codex_version=self.codex_version,
        )
        return self._state

    # ------------------------------------------------------------------
    # Directory helpers
    # ------------------------------------------------------------------

    def _ensure_directories(self) -> None:
        dirs_with_modes: list[tuple[Path, int]] = [
            (self.paths.codex_runtime_root, 0o755),
            (self.paths.codex_bin_dir, 0o755),
            (self.paths.codex_data_root, 0o755),
            (self.paths.codex_global_config_dir, 0o755),
            (self.paths.codex_read_dir, 0o755),
            (self.paths.codex_sessions_root, 0o700),
            (self.paths.codex_tmp_dir, 0o755),
            (self.paths.database_dir, 0o755),
        ]

        for directory, mode in dirs_with_modes:
            directory.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(directory, mode)
            except PermissionError:
                # In development environments chmod may fail; continue best-effort.
                pass

    def _sync_global_instructions(self) -> None:
        """Expose repository-provided AGENTS.md guidance to every session."""

        src = self.paths.backend_root / "config" / "codex_configs_md"
        if not src.exists():
            return

        dest = self.paths.codex_read_dir / "codex_configs_md"
        if dest.exists():
            if dest.is_symlink() or dest.is_file():
                dest.unlink()
            else:
                shutil.rmtree(dest)

        shutil.copytree(src, dest)

    # ------------------------------------------------------------------
    # Python environment helpers
    # ------------------------------------------------------------------

    def _ensure_python_env(self) -> None:
        if not self.venv_dir.exists():
            self._create_python_env()
        self._install_python_libs_if_needed()

    def _create_python_env(self) -> None:
        uv = shutil.which("uv")
        if uv:
            self._run(
                [uv, "venv", str(self.venv_dir)],
                cwd=self.paths.codex_runtime_root,
                desc="create python venv via uv",
            )
        else:
            python = shutil.which("python3") or shutil.which("python")
            if not python:
                raise RuntimePreparationError("No python interpreter found to create virtualenv.")
            self._run(
                [python, "-m", "venv", str(self.venv_dir)],
                cwd=self.paths.codex_runtime_root,
                desc="create python venv",
            )

    def _install_python_libs_if_needed(self) -> None:
        marker = self.paths.codex_runtime_root / ".venv-libs.json"
        desired = {"libs": list(self.python_libs)}
        if marker.exists():
            try:
                existing = json.loads(marker.read_text())
                if existing == desired:
                    return
            except json.JSONDecodeError:
                pass

        python = self._resolve_python_binary()
        uv = shutil.which("uv")
        if uv:
            self._run(
                [uv, "pip", "install", "--python", str(python), *self.python_libs],
                cwd=self.paths.codex_runtime_root,
                desc="install python libs via uv",
            )
        else:
            self._run(
                [str(python), "-m", "pip", "install", "--upgrade", "pip"],
                cwd=self.paths.codex_runtime_root,
                desc="upgrade pip in venv",
            )
            self._run(
                [str(python), "-m", "pip", "install", *self.python_libs],
                cwd=self.paths.codex_runtime_root,
                desc="install python libs via pip",
            )

        marker.write_text(json.dumps(desired, indent=2))

    # ------------------------------------------------------------------
    # Codex installation helpers
    # ------------------------------------------------------------------

    def _ensure_codex_install(self) -> None:
        node_modules_bin = self.paths.codex_runtime_root / "node_modules" / ".bin"
        codex_binary = node_modules_bin / "codex"
        current_lock = load_codex_version_lock(self.paths)

        if codex_binary.exists() and current_lock == self.codex_version:
            self._ensure_symlink(codex_binary)
            return

        npm = shutil.which("npm")
        if not npm:
            raise RuntimePreparationError("npm is required to install Codex CLI but was not found.")

        self._run(
            [npm, "install", f"@openai/codex@{self.codex_version}", "--no-save"],
            cwd=self.paths.codex_runtime_root,
            desc="install Codex CLI",
        )

        if not codex_binary.exists():
            raise RuntimePreparationError(
                f"Codex binary expected at {codex_binary} after installation."
            )

        self._ensure_symlink(codex_binary)
        write_codex_version_lock(self.paths, self.codex_version)

    def _ensure_symlink(self, codex_binary: Path) -> None:
        self.paths.codex_bin_dir.mkdir(parents=True, exist_ok=True)
        target = self.paths.codex_bin_dir / "codex"
        if target.exists() or target.is_symlink():
            try:
                target.unlink()
            except OSError:
                pass
        try:
            target.symlink_to(codex_binary)
        except FileExistsError:
            pass

    # ------------------------------------------------------------------
    # Utility helpers
    # ------------------------------------------------------------------

    def _resolve_python_binary(self) -> Path:
        if os.name == "nt":
            candidate = self.venv_dir / "Scripts" / "python.exe"
        else:
            candidate = self.venv_dir / "bin" / "python"
        if not candidate.exists():
            raise RuntimePreparationError(
                f"Expected python executable at {candidate}; virtualenv may be corrupted."
            )
        return candidate

    def _resolve_codex_binary(self) -> Path:
        binary = self.paths.codex_bin_dir / "codex"
        if os.name == "nt":
            binary = binary.with_suffix(".cmd")
        if not binary.exists():
            raise RuntimePreparationError(
                f"Expected Codex binary at {binary}. Did runtime preparation run?"
            )
        if os.name != "nt":
            binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        return binary

    def _run(self, cmd: Sequence[str], *, cwd: Path, desc: str) -> None:
        try:
            completed = subprocess.run(
                cmd,
                cwd=str(cwd),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True,
            )
        except FileNotFoundError as exc:
            raise RuntimePreparationError(f"Failed to {desc}: command {cmd[0]!r} not found.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimePreparationError(
                f"Command {' '.join(cmd)} failed while attempting to {desc}:\n{exc.stderr}"
            ) from exc

        if completed.stderr:
            print(f"[runtime] {desc}: {completed.stderr.strip()}")
