from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.sql.sqltypes import DateTime


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class Base(AsyncAttrs, DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    llm_sessions: Mapped[List["LLMSession"]] = relationship(back_populates="user")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="user")


class LLMSession(Base):
    __tablename__ = "llm_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    backend_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="llm_sessions")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="llm_session")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    llm_session_id: Mapped[str] = mapped_column(ForeignKey("llm_sessions.id", ondelete="SET NULL"))
    backend_id: Mapped[str] = mapped_column(String, nullable=False)
    codex_thread_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    codex_home: Mapped[str] = mapped_column(String, nullable=False)
    workspace_dir: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="chat_sessions")
    llm_session: Mapped[Optional[LLMSession]] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["Message"]] = relationship(
        back_populates="chat_session", order_by="Message.created_at"
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    chat_session_id: Mapped[str] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    chat_session: Mapped[ChatSession] = relationship(back_populates="messages")


def _generate_prompt_id() -> str:
    return str(uuid.uuid4())


class Prompt(Base):
    __tablename__ = "prompts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_generate_prompt_id)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    persona: Mapped[str] = mapped_column(String, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    requires_data: Mapped[bool] = mapped_column(Boolean, default=False)
    data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    response: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    copied_from_prompt_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    copied_from_user_id: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    copied_from_user_name: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    def keywords(self) -> List[str]:
        try:
            value = json.loads(self.keywords_json or "[]")
            if isinstance(value, list):
                return [str(item) for item in value if isinstance(item, str)]
        except json.JSONDecodeError:
            pass
        return []

    def to_dict(self, *, requesting_user_id: Optional[str] = None) -> dict[str, Any]:
        keywords = self.keywords()
        is_owner = requesting_user_id is not None and self.user_id == requesting_user_id
        return {
            "id": self.id,
            "user_id": self.user_id,
            "persona": self.persona,
            "task": self.task,
            "if_task_need_data": bool(self.requires_data),
            "data": self.data,
            "response": self.response,
            "keywords_used_for_search": keywords,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "copied_from_prompt_id": self.copied_from_prompt_id,
            "copied_from_user_id": self.copied_from_user_id,
            "copied_from_user_name": self.copied_from_user_name,
            "is_copy": bool(self.copied_from_prompt_id),
            "copied_from_user": self.copied_from_user_name,
            "is_owner": is_owner,
        }
