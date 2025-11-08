# Codex-as-Chat Backend

FastAPI backend that orchestrates Codex CLI runs for each user + chat session and
exposes a simple REST/WebSocket API for the React client. The service prepares a
managed runtime on startup, brokers model requests through an OpenAI-compatible
LLM gateway, and persists sessions/messages in SQLite.

## Directory layout

```
backend/
  app/
    config.py           # Filesystem layout + gateway config loader
    runtime.py          # Creates venv, installs Codex CLI, enforces dirs
    db.py               # Async SQLAlchemy engine/session helpers
    models.py           # ORM models for users/sessions/messages
    schemas.py          # Pydantic contracts for REST/gateway endpoints
    gateway.py          # OpenAI-compatible /v1/chat/completions router
    server.py           # FastAPI wiring + REST/WebSocket routes
    codex.py            # Async wrapper around `codex exec --json`
  config/llm_backends.example.yaml  # Sample gateway configuration
  main.py               # Entrypoint for `uvicorn main:app`
  pyproject.toml        # Runtime dependencies
```

At runtime the service expects the following host layout (mirroring the
requirements):

```
/codex_runtime           # virtualenv + codex npm install
/codex_data
  /global_config         # llm_backends.yaml + codex_version.lock
  /read_dir              # read-only corpus shared by all sessions
  /sessions/<user>/<chat_session>/
      CODEX_HOME/        # per-session Codex metadata
      workspace/         # writable working directory for the agent
/db/chat.sqlite          # persisted conversations
```

You can override these roots for local development via environment variables:
`CODEX_RUNTIME_ROOT`, `CODEX_DATA_ROOT`, `CODEX_DB_ROOT`.

## Boot sequence

On startup `RuntimeInitializer.prepare()` performs the required one-time setup:

1. Create the expected directory layout + permissions.
2. Create/refresh a dedicated Python virtual environment (prefers `uv`, falls
   back to `python -m venv`) and install the curated analytics stack listed in
   `DEFAULT_ALLOWED_PYTHON_LIBS`.
3. Install the pinned Codex CLI version (default `0.6.0`). The exact version is
   stored in `/codex_data/global_config/codex_version.lock` to make subsequent
   boots idempotent.

The Codex binary is symlinked to `/codex_runtime/bin/codex`. Each CLI invocation
is launched with:

```
codex exec --experimental-json --dangerously-bypass-approvals-and-sandbox \
  --model internal-gateway \
  --cd /codex_data/sessions/<user>/<chat>/workspace
```

Environment variables ensure the process is isolated:
`CODEX_HOME`, `DATA_READ_DIR`, `DATA_WRITE_DIR`, `OPENAI_BASE_URL`,
`CODEX_API_KEY`, and `LLM_SESSION_ID`. If you need to pass a different JSON
streaming flag for older/newer Codex builds, set `CODEX_JSON_FLAG` (for example
`export CODEX_JSON_FLAG="--json"`).

## LLM gateway configuration

The gateway solely depends on `llm_backends.yaml` stored under
`/codex_data/global_config`. A sample is provided in
`config/llm_backends.example.yaml`:

```yaml
backends:
  - id: deepseek-chat
    type: openai-compatible
    base_url: "https://api.deepseek.com/v1"
    api_key_env: "DEEPSEEK_API_KEY"
    model: "deepseek-chat"
  - id: gpt-4o-azure
    type: azure
    azure_endpoint: "https://your-azure-endpoint.openai.azure.com"
    api_version: "2025-01-01-preview"
    api_key_env: "AZURE_OPENAI_API_KEY"
    model: "gpt-4o"
default_backend: deepseek-chat
```

At runtime the service resolves the backend by `model` (alias), fetches the
required credentials from the declared environment variables, and forwards the
request using the official `openai` SDK (supporting both streaming and
non-streaming responses). Swapping/adding providers is a YAML edit + restart.

## Database schema

SQLite is used for durability. SQLAlchemy models map to the required schema:

- `users` — one row per logical user.
- `llm_sessions` — short-lived front-end sessions routed to a backend.
- `chat_sessions` — per conversation metadata including `codex_thread_id`,
  `codex_home`, and `workspace_dir`.
- `messages` — ordered history for each chat (user + assistant roles).

`init_models` runs automatically on startup to create tables if they are absent.

## REST & WebSocket contract

- `POST /sessions` — create a new chat session. Request body matches
  `SessionCreateRequest` and returns the generated `chat_session_id`.
- `GET /sessions?user_id=…` — list sessions for a user.
- `GET /sessions/{id}/messages?user_id=…` — retrieve prior history.
- `WS /chat?chat_session_id=…&llm_session_id=…&user_id=…` — interactive stream.
  The backend forwards Codex JSON events as simplified payloads:
  - `{type: "reasoning", content, partial?}`
  - `{type: "assistant", content}`
  - `{type: "error", content}`

Every user turn spawns a fresh `codex exec` process bound to the same
`CODEX_HOME` and workspace. Once Codex emits `thread.started`, the thread id is
persisted to allow subsequent turns to resume the same conversation context.

## Running locally

1. **Install tooling**: ensure `python3.12`, `uv` (optional but recommended),
   `npm`, and `gh` (for future artifact downloads) are available.
2. **Create configuration**:
   ```bash
   mkdir -p .runtime/codex_runtime .runtime/codex_data/global_config .runtime/db
   cp config/llm_backends.example.yaml \
     .runtime/codex_data/global_config/llm_backends.yaml
   export CODEX_RUNTIME_ROOT="$PWD/.runtime/codex_runtime"
   export CODEX_DATA_ROOT="$PWD/.runtime/codex_data"
   export CODEX_DB_ROOT="$PWD/.runtime/db"
   export CODEX_GATEWAY_URL="http://127.0.0.1:8000"
   export CODEX_INTERNAL_API_KEY="internal-static-key"
   export DEEPSEEK_API_KEY="sk-your-key"
   ```
3. **Install project deps**:
   ```bash
   pip install uv
   uv pip install -r <(echo fastapi uvicorn[standard] sqlalchemy aiosqlite pydantic pyyaml openai)
   ```
   or simply `pip install -r requirements` using the dependencies listed in
   `pyproject.toml`.
4. **Start the API**:
   ```bash
   uvicorn main:app --reload
   ```

On first boot the initializer will create the venv, install Codex, and prepare
the directory tree. Subsequent starts reuse the cached artifacts.

## Tests & validation

A lightweight `python -m compileall app` check ensures syntax correctness. To
exercise the service manually:

- Hit `POST /sessions` with the hard-coded front-end user id (`user-123`).
- Connect to the WebSocket and send `{"type":"user_message","content":"..."}`.
- Verify Codex events stream back and the SQLite database updates.

When wiring in real Codex binaries you may want to provide a fixture workspace
under `/codex_data/read_dir` so the agent has meaningful context.
