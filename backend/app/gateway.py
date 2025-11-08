from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AsyncAzureOpenAI, AsyncOpenAI

from .schemas import ChatCompletionMessage, ChatCompletionRequest, ResponsesRequest


def get_llm_client(mode: str, llm_session_id: str):
    """
    mode: "open-ai-comptiable" or "azure-ai"
    llm_session_id: used to decide which backend to route to
    """
    # OpenAI-compatible (e.g. self-hosted / gateway)
    if mode == "open-ai-comptiable" and llm_session_id.startswith("abc"):
        return AsyncOpenAI(
            base_url=os.getenv("OPENAI_COMPAT_BASE_URL"),
            api_key=os.getenv("OPENAI_COMPAT_API_KEY"),
        )

    # Azure OpenAI
    if mode == "azure-ai" and llm_session_id.startswith("adc"):
        return AsyncAzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"),
        )

    raise ValueError("No matching client for given mode and llm_session_id.")


class BackendClient:
    def __init__(self, mode: str, llm_session_id: str):
        self.mode = mode
        self.llm_session_id = llm_session_id
        self.backend_id = mode
        self.client = get_llm_client(mode, llm_session_id)

    async def complete(self, request: ChatCompletionRequest) -> Any:
        if request.mode != self.mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request mode does not match resolved backend.",
            )
        if request.llm_session_id != self.llm_session_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Request llm_session_id does not match resolved backend.",
            )
        if not request.model:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Model must be provided in the request.",
            )

        payload: Dict[str, Any] = {
            "model": request.model,
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
    def __init__(self) -> None:
        self._cache: Dict[tuple[str, str], BackendClient] = {}

    def resolve(self, mode: Optional[str], llm_session_id: str) -> BackendClient:
        if not mode:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Mode is required to resolve backend.",
            )
        cache_key = (mode, llm_session_id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        try:
            client = BackendClient(mode, llm_session_id)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

        self._cache[cache_key] = client
        return client


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
        client = registry.resolve(request.mode, request.llm_session_id)
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
        backend_client = registry.resolve(request.mode, request.llm_session_id)
        messages = _build_chat_messages_from_responses(request)
        completion_request = ChatCompletionRequest(
            mode=request.mode,
            llm_session_id=request.llm_session_id,
            model=request.model,
            messages=messages,
            max_tokens=request.max_output_tokens,
            temperature=request.temperature,
        )

        completion = await backend_client.complete(completion_request)

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
