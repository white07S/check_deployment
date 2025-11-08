from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CODEX_VERSION = "0.56.0"
DEFAULT_ALLOWED_PYTHON_LIBS: tuple[str, ...] = (
    "fastapi",
    "uvicorn",
    "pydantic",
    "sqlalchemy",
    "aiosqlite",
    "httpx",
    "numpy",
    "pandas",
    "polars",
    "duckdb",
    "requests",
    "matplotlib",
    "nltk",
    "tqdm",
    "scikit-learn",
)


class ConfigError(RuntimeError):
    """Raised when configuration is invalid or missing."""


@dataclass(frozen=True)
class PathConfig:
    """Holds important filesystem locations for the backend runtime."""

    backend_root: Path
    codex_runtime_root: Path
    codex_bin_dir: Path
    codex_data_root: Path
    codex_global_config_dir: Path
    codex_read_dir: Path
    codex_sessions_root: Path
    codex_tmp_dir: Path
    database_dir: Path
    database_path: Path


@dataclass(frozen=True)
class GatewayBackendConfig:
    id: str
    backend_type: str
    options: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GatewayConfig:
    backends: Dict[str, GatewayBackendConfig]
    default_backend: str


def resolve_paths() -> PathConfig:
    backend_root = Path(__file__).resolve().parent.parent
    codex_runtime_root = Path(os.environ.get("CODEX_RUNTIME_ROOT", "/codex_runtime")).resolve()
    codex_data_root = Path(os.environ.get("CODEX_DATA_ROOT", "/codex_data")).resolve()
    database_dir = Path(os.environ.get("CODEX_DB_ROOT", "/db")).resolve()

    codex_bin_dir = codex_runtime_root / "bin"
    codex_global_config_dir = codex_data_root / "global_config"
    codex_sessions_root = codex_data_root / "sessions"
    codex_read_dir = codex_data_root / "read_dir"
    codex_tmp_dir = codex_data_root / "tmp"
    database_path = database_dir / "chat.sqlite"

    return PathConfig(
        backend_root=backend_root,
        codex_runtime_root=codex_runtime_root,
        codex_bin_dir=codex_bin_dir,
        codex_data_root=codex_data_root,
        codex_global_config_dir=codex_global_config_dir,
        codex_read_dir=codex_read_dir,
        codex_sessions_root=codex_sessions_root,
        codex_tmp_dir=codex_tmp_dir,
        database_dir=database_dir,
        database_path=database_path,
    )


def load_gateway_config(path_config: PathConfig) -> GatewayConfig:
    config_path = path_config.codex_global_config_dir / "llm_backends.yaml"
    if not config_path.exists():
        raise ConfigError(f"Expected gateway configuration at {config_path} (missing).")

    data = yaml.safe_load(config_path.read_text())
    if not isinstance(data, dict):
        raise ConfigError("llm_backends.yaml must be a mapping.")

    backends_raw = data.get("backends")
    if not isinstance(backends_raw, list) or not backends_raw:
        raise ConfigError("llm_backends.yaml must contain a non-empty 'backends' list.")

    backends: Dict[str, GatewayBackendConfig] = {}
    for backend in backends_raw:
        if not isinstance(backend, dict):
            raise ConfigError("Each backend entry must be a mapping.")
        backend_id = backend.get("id")
        backend_type = backend.get("type")
        if not backend_id or not backend_type:
            raise ConfigError("Each backend entry requires 'id' and 'type'.")
        options = {k: v for k, v in backend.items() if k not in {"id", "type"}}
        backends[backend_id] = GatewayBackendConfig(
            id=backend_id,
            backend_type=backend_type,
            options=options,
        )

    default_backend = data.get("default_backend")
    if not isinstance(default_backend, str) or default_backend not in backends:
        raise ConfigError(
            "llm_backends.yaml must define 'default_backend' matching one of the backends."
        )

    return GatewayConfig(backends=backends, default_backend=default_backend)


def load_codex_version_lock(path_config: PathConfig) -> Optional[str]:
    lock_path = path_config.codex_global_config_dir / "codex_version.lock"
    if lock_path.exists():
        value = lock_path.read_text().strip()
        return value or None
    return None


def write_codex_version_lock(path_config: PathConfig, version: str) -> None:
    lock_path = path_config.codex_global_config_dir / "codex_version.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(version.strip() + "\n")
