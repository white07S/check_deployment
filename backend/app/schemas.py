from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional, Sequence

from pydantic import BaseModel, Field


class SessionCreateRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    llm_session_id: str = Field(..., min_length=1)
    title: Optional[str] = Field(default=None, max_length=120)
    model: Optional[str] = Field(default=None, description="Requested backend/model identifier")


class SessionCreateResponse(BaseModel):
    chat_session_id: str
    model: str
    codex_thread_id: Optional[str]
    created_at: datetime
    title: Optional[str]


class ChatSessionSummary(BaseModel):
    id: str
    title: Optional[str]
    backend_id: str
    created_at: datetime
    updated_at: datetime


class MessageRead(BaseModel):
    id: int
    role: Literal["user", "assistant"]
    content: str
    created_at: datetime


class SessionsListResponse(BaseModel):
    sessions: List[ChatSessionSummary]


class MessagesListResponse(BaseModel):
    messages: List[MessageRead]


class ChatCompletionMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool", "function"]
    content: Any
    name: Optional[str] = None


class ChatCompletionRequest(BaseModel):
    model: Optional[str] = None
    messages: Sequence[ChatCompletionMessage]
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None
    stream: bool = False


class ChatCompletionChoiceMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatCompletionChoiceMessage
    finish_reason: Optional[str] = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"]
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: Optional[ChatCompletionUsage] = None


class ResponseContentBlock(BaseModel):
    type: str
    text: Optional[str] = None


class ResponseInputItem(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: List[ResponseContentBlock]


class ResponsesRequest(BaseModel):
    model: Optional[str] = None
    input: List[ResponseInputItem] = Field(default_factory=list)
    max_output_tokens: Optional[int] = None
    temperature: Optional[float] = None
    metadata: Optional[dict[str, Any]] = None
