from __future__ import annotations

import asyncio
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncIterator

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from .codex import CodexInvocationError, CodexRunner, SessionPaths
from .config import resolve_paths
from .db import build_engine, build_session_factory, init_models
from .gateway import GatewayRegistry, build_gateway_router
from .models import Base, ChatSession, LLMSession, Message, User
from .prompts import build_prompts_router
from .runtime import RuntimeInitializer, RuntimePreparationError
from .schemas import (
    ChatSessionSummary,
    MessageRead,
    MessagesListResponse,
    SessionCreateRequest,
    SessionCreateResponse,
    SessionsListResponse,
)


def create_app() -> FastAPI:
    app = FastAPI(title="Codex as Chat Backend")

    allowed_origins = os.environ.get("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
    origins = [origin.strip() for origin in allowed_origins.split(",") if origin.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    paths = resolve_paths()
    runtime = RuntimeInitializer(paths)
    engine = build_engine(paths)
    session_factory = build_session_factory(engine)

    model_alias = os.environ.get("CODEX_MODEL_ALIAS", "internal-gateway")
    gateway_url = os.environ.get("CODEX_GATEWAY_URL", "http://127.0.0.1:8000")
    internal_api_key = os.environ.get("CODEX_INTERNAL_API_KEY", "internal-static-key")

    async def get_session() -> AsyncIterator[AsyncSession]:
        session = session_factory()
        try:
            yield session
        finally:
            await session.close()

    gateway_registry = GatewayRegistry()
    app.include_router(build_gateway_router(gateway_registry))
    app.include_router(build_prompts_router(get_session))

    @app.on_event("startup")
    async def on_startup() -> None:
        try:
            runtime_state = await asyncio.to_thread(runtime.prepare)
        except RuntimePreparationError as exc:
            raise RuntimeError(f"Runtime preparation failed: {exc}") from exc

        await init_models(engine, Base)

        codex_runner = CodexRunner(
            runtime_state.codex_binary,
            model_alias=model_alias,
            gateway_url=gateway_url,
            static_api_key=internal_api_key,
            data_read_dir=paths.codex_read_dir,
        )

        app.state.paths = paths
        app.state.runtime_state = runtime_state
        app.state.codex_runner = codex_runner
        app.state.session_factory = session_factory
        app.state.gateway_registry = gateway_registry

    sessions_router = APIRouter(prefix="/sessions", tags=["sessions"])

    @sessions_router.post("", response_model=SessionCreateResponse)
    async def create_session_endpoint(
        payload: SessionCreateRequest,
        db: AsyncSession = Depends(get_session),
    ) -> SessionCreateResponse:
        backend_client = gateway_registry.resolve(payload.mode, payload.llm_session_id)
        backend_id = backend_client.backend_id

        user = await db.get(User, payload.user_id)
        if not user:
            user = User(id=payload.user_id)
            db.add(user)

        llm_session = await db.get(LLMSession, payload.llm_session_id)
        if not llm_session:
            llm_session = LLMSession(
                id=payload.llm_session_id,
                user_id=payload.user_id,
                backend_id=backend_id,
            )
            db.add(llm_session)

        chat_session_id = str(uuid.uuid4())
        base_dir = paths.codex_sessions_root / payload.user_id / chat_session_id
        codex_home = base_dir / "CODEX_HOME"
        workspace_dir = base_dir / "workspace"
        for directory in (base_dir, codex_home, workspace_dir):
            directory.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(directory, 0o700)
            except PermissionError:
                pass

        configs_src = paths.codex_read_dir / "codex_configs_md"
        if configs_src.exists():
            workspace_configs = workspace_dir / "codex_configs_md"
            if not workspace_configs.exists():
                try:
                    os.symlink(configs_src, workspace_configs, target_is_directory=True)
                except (AttributeError, NotImplementedError, OSError):
                    shutil.copytree(configs_src, workspace_configs, dirs_exist_ok=True)

        config_path = codex_home / "config.toml"
        config_text = "\n".join(
            [
                'model_reasoning_summary = "detailed"',
                'model_reasoning_effort = "medium"',
                "hide_agent_reasoning = false",
                "show_raw_agent_reasoning = true",
            ]
        )
        try:
            config_path.write_text(config_text + "\n", encoding="utf-8")
            os.chmod(config_path, 0o600)
        except OSError:
            pass

        chat_session = ChatSession(
            id=chat_session_id,
            user_id=payload.user_id,
            llm_session_id=payload.llm_session_id,
            backend_id=backend_id,
            codex_home=str(codex_home),
            workspace_dir=str(workspace_dir),
            title=payload.title,
        )
        db.add(chat_session)
        await db.commit()

        return SessionCreateResponse(
            chat_session_id=chat_session.id,
            model=backend_id,
            codex_thread_id=chat_session.codex_thread_id,
            created_at=chat_session.created_at,
            title=chat_session.title,
        )

    @sessions_router.get("", response_model=SessionsListResponse)
    async def list_sessions(
        user_id: str = Query(..., min_length=1),
        db: AsyncSession = Depends(get_session),
    ) -> SessionsListResponse:
        stmt = (
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
        )
        scalar_result = await db.scalars(stmt)
        chat_records = list(scalar_result)
        session_ids = [chat.id for chat in chat_records]

        if session_ids:
            counts_stmt = (
                select(Message.chat_session_id, func.count(Message.id))
                .where(Message.chat_session_id.in_(session_ids))
                .group_by(Message.chat_session_id)
            )
            counts_result = await db.execute(counts_stmt)
            counts_map = {chat_id: count for chat_id, count in counts_result}

            row_number = func.row_number().over(partition_by=Message.chat_session_id, order_by=Message.created_at)
            first_stmt = (
                select(Message.chat_session_id, Message.content, row_number.label("rn"))
                .where(
                    Message.chat_session_id.in_(session_ids),
                    Message.role == "user",
                )
            )
            first_result = await db.execute(first_stmt)
            first_map: dict[str, str] = {}
            for chat_id, content, rn in first_result:
                if rn == 1 and chat_id not in first_map:
                    first_map[chat_id] = content
        else:
            counts_map = {}
            first_map = {}

        sessions = [
            ChatSessionSummary(
                id=chat.id,
                title=chat.title,
                backend_id=chat.backend_id,
                created_at=chat.created_at,
                updated_at=chat.updated_at,
                first_message_preview=first_map.get(chat.id),
                message_count=counts_map.get(chat.id, 0),
            )
            for chat in chat_records
        ]

        return SessionsListResponse(sessions=sessions)

    @sessions_router.get("/{chat_session_id}/messages", response_model=MessagesListResponse)
    async def get_messages(
        chat_session_id: str,
        user_id: str = Query(..., min_length=1),
        db: AsyncSession = Depends(get_session),
    ) -> MessagesListResponse:
        chat_session = await db.get(ChatSession, chat_session_id)
        if not chat_session or chat_session.user_id != user_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        stmt = (
            select(Message)
            .where(Message.chat_session_id == chat_session_id)
            .order_by(Message.created_at.asc())
        )
        result = await db.scalars(stmt)
        messages = [
            MessageRead(
                id=msg.id,
                role=msg.role,  # type: ignore[arg-type]
                content=msg.content,
                created_at=msg.created_at,
            )
            for msg in result
        ]
        return MessagesListResponse(messages=messages)

    app.include_router(sessions_router)

    @app.websocket("/chat")
    async def chat_endpoint(websocket: WebSocket) -> None:
        await websocket.accept()
        query = websocket.query_params
        user_id = query.get("user_id")
        chat_session_id = query.get("chat_session_id")
        llm_session_id = query.get("llm_session_id")

        if not user_id or not chat_session_id or not llm_session_id:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        async with session_factory() as db_session:
            chat_session = await db_session.get(ChatSession, chat_session_id)
            if not chat_session or chat_session.user_id != user_id:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return

        runner: CodexRunner = app.state.codex_runner
        session_paths = SessionPaths(
            codex_home=Path(chat_session.codex_home),
            workspace_dir=Path(chat_session.workspace_dir),
        )
        codex_thread_id = chat_session.codex_thread_id
        assistant_buffer = ""
        reasoning_buffer = ""
        assistant_final_sent = False

        def _append_text_blocks(blocks: list[dict[str, object]] | None) -> str:
            if not blocks:
                return ""
            parts: list[str] = []
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            return "".join(parts)

        async def emit_reasoning_delta(delta: str) -> None:
            nonlocal reasoning_buffer
            if not delta:
                return
            reasoning_buffer += delta
            await websocket.send_json({"type": "reasoning", "content": reasoning_buffer, "partial": True})

        async def emit_reasoning_final(text: str) -> None:
            nonlocal reasoning_buffer
            final_text = text or reasoning_buffer
            if not final_text:
                return
            reasoning_buffer = ""
            await websocket.send_json({"type": "reasoning", "content": final_text})

        async def emit_assistant_delta(delta: str) -> None:
            nonlocal assistant_buffer
            if not delta:
                return
            assistant_buffer += delta
            await websocket.send_json({"type": "assistant_partial", "content": assistant_buffer})

        async def emit_assistant_final(text: str) -> None:
            nonlocal assistant_buffer, assistant_final_sent
            final_text = text or assistant_buffer
            if not final_text:
                return
            assistant_buffer = ""
            await websocket.send_json({"type": "assistant", "content": final_text})
            if not assistant_final_sent:
                await store_message("assistant", final_text)
                assistant_final_sent = True

        async def store_message(role: str, content: str) -> None:
            async with session_factory() as db:
                chat = await db.get(ChatSession, chat_session_id)
                if not chat:
                    return
                db.add(
                    Message(
                        chat_session_id=chat_session_id,
                        role=role,
                        content=content,
                    )
                )
                chat.updated_at = datetime.now(timezone.utc)
                await db.commit()

        async def update_thread_id(thread_id: str) -> None:
            async with session_factory() as db:
                chat = await db.get(ChatSession, chat_session_id)
                if chat and not chat.codex_thread_id:
                    chat.codex_thread_id = thread_id
                    chat.updated_at = datetime.now(timezone.utc)
                    await db.commit()

        try:
            while True:
                try:
                    payload = await websocket.receive_json()
                except WebSocketDisconnect:
                    break

                if payload.get("type") != "user_message":
                    await websocket.send_json({"type": "error", "content": "Unsupported message type."})
                    continue

                content = payload.get("content")
                if not isinstance(content, str):
                    await websocket.send_json({"type": "error", "content": "Message content must be string."})
                    continue

                await store_message("user", content)

                try:
                    assistant_buffer = ""
                    reasoning_buffer = ""
                    assistant_final_sent = False

                    async for event in runner.stream_turn(
                        prompt=content,
                        session_paths=session_paths,
                        llm_session_id=llm_session_id,
                        codex_thread_id=codex_thread_id,
                    ):
                        event_type = event.get("type")
                        payload = event.get("payload") or {}
                        payload_type = payload.get("type")

                        if event_type == "thread.started":
                            thread_id = event.get("thread_id")
                            if thread_id and not codex_thread_id:
                                codex_thread_id = thread_id
                                await update_thread_id(thread_id)
                        elif event_type == "event_msg":
                            if payload_type in {"agent_reasoning_delta", "agent_reasoning_raw_content_delta"}:
                                delta = payload.get("delta") or payload.get("message") or payload.get("text")
                                if isinstance(delta, str):
                                    await emit_reasoning_delta(delta)
                            elif payload_type in {"agent_reasoning", "agent_reasoning_raw_content"}:
                                text = payload.get("message") or payload.get("text")
                                if isinstance(text, str):
                                    await emit_reasoning_final(text)
                            elif payload_type == "agent_reasoning_section_break":
                                reasoning_buffer = ""
                            elif payload_type == "agent_message_delta":
                                delta = payload.get("delta")
                                if isinstance(delta, str):
                                    await emit_assistant_delta(delta)
                            elif payload_type == "agent_message":
                                text = payload.get("message")
                                if isinstance(text, str):
                                    await emit_assistant_final(text)
                            elif payload_type == "token_count":
                                continue
                        elif event_type == "response_item":
                            if payload_type in {"reasoning", "raw_reasoning"}:
                                text = _append_text_blocks(payload.get("content"))
                                if text:
                                    await emit_reasoning_final(text)
                            elif payload_type in {"reasoning_delta", "raw_reasoning_delta"}:
                                text = _append_text_blocks(payload.get("content")) or payload.get("delta", "")
                                if isinstance(text, str) and text:
                                    await emit_reasoning_delta(text)
                            elif payload_type in {"message_delta", "output_text_delta"}:
                                delta_text = payload.get("delta")
                                if isinstance(delta_text, str) and delta_text:
                                    await emit_assistant_delta(delta_text)
                                else:
                                    combined = _append_text_blocks(payload.get("content"))
                                    if combined:
                                        await emit_assistant_delta(combined)
                            elif payload_type == "message":
                                role = payload.get("role")
                                if role == "assistant":
                                    response_text = _append_text_blocks(payload.get("content"))
                                    if response_text and not assistant_final_sent:
                                        await emit_assistant_final(response_text)
                        elif event_type == "agent_reasoning_delta":
                            delta = event.get("delta")
                            if isinstance(delta, str):
                                await emit_reasoning_delta(delta)
                        elif event_type == "agent_message_delta":
                            delta = event.get("delta")
                            if isinstance(delta, str):
                                await emit_assistant_delta(delta)
                        elif event_type == "item.completed":
                            item = event.get("item") or {}
                            item_type = item.get("type")
                            if item_type == "reasoning":
                                text = item.get("text", "")
                                if isinstance(text, str) and text:
                                    await emit_reasoning_final(text)
                            elif item_type == "agent_message":
                                text = item.get("text", "")
                                if isinstance(text, str) and text:
                                    await emit_assistant_final(text)
                        elif event_type == "item.updated":
                            item = event.get("item") or {}
                            if item.get("type") == "reasoning":
                                text = item.get("text", "")
                                if isinstance(text, str):
                                    await emit_reasoning_delta(text)
                        elif event_type == "turn.failed":
                            error = event.get("error", {}).get("message", "Codex turn failed.")
                            await websocket.send_json({"type": "error", "content": error})
                            break
                        elif event_type == "error":
                            await websocket.send_json({"type": "error", "content": event.get("message", "")})
                            break
                        elif event_type == "agent_reasoning":
                            text = event.get("text")
                            if isinstance(text, str):
                                await emit_reasoning_final(text)
                        elif event_type == "agent_message":
                            text = event.get("text")
                            if isinstance(text, str):
                                await emit_assistant_final(text)
                except CodexInvocationError as exc:
                    await websocket.send_json({"type": "error", "content": str(exc)})

        finally:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close()

    return app
