from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AsyncAzureOpenAI, AsyncOpenAI

from .config import ConfigError, GatewayBackendConfig, GatewayConfig
from .schemas import ChatCompletionMessage, ChatCompletionRequest, ResponsesRequest


class BackendClient:
    def __init__(self, cfg: GatewayBackendConfig):
        self.cfg = cfg
        self.model_name = cfg.options.get("model")
        if not self.model_name:
            raise ConfigError(f"Backend '{cfg.id}' is missing required 'model' option.")

        if cfg.backend_type == "openai-compatible":
            base_url = cfg.options.get("base_url")
            api_key_env = cfg.options.get("api_key_env")
            if not base_url or not api_key_env:
                raise ConfigError(
                    f"Backend '{cfg.id}' requires 'base_url' and 'api_key_env' options."
                )
            api_key = os.getenv(api_key_env)
            if not api_key:
                raise ConfigError(
                    f"Environment variable '{api_key_env}' required for backend '{cfg.id}'."
                )
            self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        elif cfg.backend_type == "azure":
            endpoint = cfg.options.get("azure_endpoint")
            api_version = cfg.options.get("api_version")
            api_key_env = cfg.options.get("api_key_env")
            if not endpoint or not api_version or not api_key_env:
                raise ConfigError(
                    f"Azure backend '{cfg.id}' requires 'azure_endpoint', 'api_version', and 'api_key_env'."
                )
            api_key = os.getenv(api_key_env)
            if not api_key:
                raise ConfigError(
                    f"Environment variable '{api_key_env}' required for backend '{cfg.id}'."
                )
            self.client = AsyncAzureOpenAI(
                azure_endpoint=endpoint,
                api_version=api_version,
                api_key=api_key,
            )
        else:
            raise ConfigError(f"Unknown backend type '{cfg.backend_type}' for backend '{cfg.id}'.")

    async def complete(self, request: ChatCompletionRequest) -> Any:
        payload: Dict[str, Any] = {
            "model": self.model_name,
            "messages": [msg.model_dump() for msg in request.messages],
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.metadata:
            payload["metadata"] = request.metadata

        if request.stream:
            return await self.client.chat.completions.create(stream=True, **payload)
        return await self.client.chat.completions.create(**payload)


class GatewayRegistry:
    def __init__(self, cfg: GatewayConfig):
        self.config = cfg
        self.backends: Dict[str, BackendClient] = {
            backend_id: BackendClient(backend_cfg)
            for backend_id, backend_cfg in cfg.backends.items()
        }

    def resolve(self, backend_id: Optional[str]) -> BackendClient:
        if backend_id and backend_id in self.backends:
            return self.backends[backend_id]

        # Fallback to default backend when alias is unknown (e.g. "internal-gateway").
        client = self.backends.get(self.config.default_backend)
        if client:
            return client

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No backend configured to handle the request.",
        )


def _build_chat_messages_from_responses(
    request: ResponsesRequest,
) -> List[ChatCompletionMessage]:
    messages: List[ChatCompletionMessage] = []
    for item in request.input:
        text_parts: List[str] = []
        for block in item.content:
            if block.text:
                text_parts.append(block.text)
        if not text_parts:
            continue
        messages.append(
            ChatCompletionMessage(
                role=item.role,
                content="\n\n".join(text_parts),
            )
        )
    return messages


def _format_sse(event: str, payload: Dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode("utf-8")


def build_gateway_router(registry: GatewayRegistry) -> APIRouter:
    router = APIRouter()

    @router.post("/v1/chat/completions")
    async def chat_completions(request: ChatCompletionRequest) -> Any:
        client = registry.resolve(request.model)
        result = await client.complete(request)

        if request.stream:
            async def stream_generator() -> AsyncIterator[bytes]:
                async for chunk in result:
                    data = chunk.model_dump()
                    yield f"data: {json.dumps(data)}\n\n".encode("utf-8")
                yield b"data: [DONE]\n\n"

            return StreamingResponse(stream_generator(), media_type="text/event-stream")

        return JSONResponse(content=result.model_dump())

    @router.post("/responses")
    async def responses_endpoint(request: ResponsesRequest) -> Any:
        print(f"Received request: {request}")
        client = registry.resolve(request.model)
        messages = _build_chat_messages_from_responses(request)
        completion_request = ChatCompletionRequest(
            model=request.model,
            messages=messages,
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
        )

        completion = await client.complete(completion_request)

        response_id = f"resp_{uuid.uuid4().hex}"
        message_id = f"msg_{uuid.uuid4().hex}"

        assistant_text = ""
        if completion.choices:
            choice = completion.choices[0]
            if hasattr(choice.message, "content"):
                assistant_text = choice.message.content or ""
            elif isinstance(choice.message, dict):
                assistant_text = choice.message.get("content") or ""

        usage = completion.usage.model_dump() if completion.usage else {}
        usage_payload = {
            "input_tokens": usage.get("prompt_tokens"),
            "input_tokens_details": usage.get("prompt_tokens_details"),
            "output_tokens": usage.get("completion_tokens"),
            "output_tokens_details": usage.get("completion_tokens_details"),
            "total_tokens": usage.get("total_tokens"),
        }

        async def stream() -> AsyncIterator[bytes]:
            created_event = {
                "type": "response.created",
                "response": {
                    "id": response_id,
                    "created_at": int(time.time()),
                },
            }
            yield _format_sse("response.created", created_event)

            message_event = {
                "type": "response.output_item.done",
                "response": {
                    "id": response_id,
                },
                "item": {
                    "id": message_id,
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": assistant_text,
                        }
                    ],
                },
            }
            yield _format_sse("response.output_item.done", message_event)

            completed_event = {
                "type": "response.completed",
                "response": {
                    "id": response_id,
                    "usage": usage_payload,
                },
            }
            yield _format_sse("response.completed", completed_event)
            yield b"data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    return router
