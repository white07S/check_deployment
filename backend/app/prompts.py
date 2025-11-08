from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import AsyncIterator, Callable, Iterable, List, Optional, Sequence

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Prompt
from .schemas import PromptCopy, PromptCreate, PromptUpdate

GetSession = Callable[[], AsyncIterator[AsyncSession]]


def build_prompts_router(get_session: GetSession) -> APIRouter:
    router = APIRouter(prefix="/prompts", tags=["prompts"])

    @router.post("/create")
    async def create_prompt(
        payload: PromptCreate,
        user_id: str = Query(..., description="User identifier creating the prompt"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        persona = payload.persona.strip()
        task = payload.task.strip()
        response = payload.response.strip()

        if not persona or not task or not response:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Persona, task, and response must be provided.",
            )

        if payload.if_task_need_data and not (payload.data or "").strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Data is required when if_task_need_data is true.",
            )

        keywords = _normalise_keywords(payload.keywords_used_for_search)
        prompt = Prompt(
            user_id=user_id,
            persona=persona,
            task=task,
            requires_data=payload.if_task_need_data,
            data=payload.data.strip() if payload.data else None,
            response=response,
            keywords_json=json.dumps(keywords),
        )
        db.add(prompt)
        await db.commit()
        await db.refresh(prompt)
        return {"message": "Prompt created successfully", "prompt_id": prompt.id}

    @router.get("/list")
    async def list_prompts(
        user_created: Optional[bool] = Query(None, description="Filter prompts by ownership"),
        keywords: Optional[str] = Query(
            None, description="Comma-separated keywords used for filtering results."
        ),
        user_id: str = Query(..., description="Requesting user identifier"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        stmt = select(Prompt).order_by(desc(Prompt.created_at), desc(Prompt.id))
        if user_created is True:
            stmt = stmt.where(Prompt.user_id == user_id)
        elif user_created is False:
            stmt = stmt.where(Prompt.user_id != user_id)

        result = await db.scalars(stmt)
        keyword_filters = _normalise_keywords(keywords)

        prompts: List[dict] = []
        for prompt in result:
            prompt_dict = prompt.to_dict(requesting_user_id=user_id)
            if keyword_filters and not _matches_keywords(prompt_dict, keyword_filters):
                continue
            prompts.append(prompt_dict)

        return {"prompts": prompts}

    @router.get("/{prompt_id}")
    async def get_prompt(
        prompt_id: str,
        user_id: str = Query(..., description="Requesting user identifier"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        prompt = await db.get(Prompt, prompt_id)
        if not prompt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

        return {"prompt": prompt.to_dict(requesting_user_id=user_id)}

    @router.put("/{prompt_id}")
    async def update_prompt(
        prompt_id: str,
        payload: PromptUpdate,
        user_id: str = Query(..., description="User identifier attempting the update"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        prompt = await db.get(Prompt, prompt_id)
        if not prompt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
        if prompt.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only edit your own prompts.",
            )

        updated = False

        if payload.persona is not None:
            new_persona = payload.persona.strip()
            if not new_persona:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Persona cannot be empty.",
                )
            prompt.persona = new_persona
            updated = True

        if payload.task is not None:
            new_task = payload.task.strip()
            if not new_task:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Task cannot be empty.",
                )
            prompt.task = new_task
            updated = True

        if payload.response is not None:
            new_response = payload.response.strip()
            if not new_response:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Response cannot be empty.",
                )
            prompt.response = new_response
            updated = True

        if payload.if_task_need_data is not None:
            prompt.requires_data = payload.if_task_need_data
            updated = True

        if payload.data is not None:
            data_value = payload.data.strip()
            if prompt.requires_data and not data_value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Data is required when if_task_need_data is true.",
                )
            prompt.data = data_value or None
            updated = True

        if payload.keywords_used_for_search is not None:
            keywords = _normalise_keywords(payload.keywords_used_for_search)
            prompt.keywords_json = json.dumps(keywords)
            updated = True

        if updated:
            prompt.updated_at = datetime.now(timezone.utc)
            await db.commit()
        else:
            await db.rollback()

        return {"message": "Prompt updated successfully"}

    @router.delete("/{prompt_id}")
    async def delete_prompt(
        prompt_id: str,
        user_id: str = Query(..., description="User identifier attempting deletion"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        prompt = await db.get(Prompt, prompt_id)
        if not prompt:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
        if prompt.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only delete your own prompts.",
            )

        await db.delete(prompt)
        await db.commit()
        return {"message": "Prompt deleted successfully"}

    @router.post("/copy")
    async def copy_prompt(
        payload: PromptCopy,
        user_id: str = Query(..., description="User identifier receiving the copied prompt"),
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        source = await db.get(Prompt, payload.prompt_id)
        if not source:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")

        copied = Prompt(
            user_id=user_id,
            persona=source.persona,
            task=source.task,
            requires_data=source.requires_data,
            data=source.data,
            response=source.response,
            keywords_json=source.keywords_json,
            copied_from_prompt_id=source.id,
            copied_from_user_id=source.user_id,
            copied_from_user_name=source.user_id,
        )
        db.add(copied)
        await db.commit()
        await db.refresh(copied)

        payload_dict = copied.to_dict(requesting_user_id=user_id)
        return {
            "message": "Prompt copied successfully",
            "prompt_id": copied.id,
            "copied_from_user": copied.copied_from_user_name,
            "prompt": payload_dict,
        }

    @router.get("/suggestions/{limit}")
    async def get_prompt_suggestions(
        limit: int = 5,
        db: AsyncSession = Depends(get_session),
    ) -> dict:
        if limit <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Limit must be positive."
            )

        stmt = (
            select(Prompt)
            .order_by(desc(Prompt.created_at), desc(Prompt.id))
            .limit(min(limit, 50))
        )
        result = await db.scalars(stmt)
        suggestions = [
            prompt.to_dict(requesting_user_id=None)
            for prompt in result
        ]
        return {"suggestions": suggestions}

    return router


def _normalise_keywords(
    keywords: Optional[Iterable[str] | str],
) -> List[str]:
    if keywords is None:
        return []
    if isinstance(keywords, str):
        raw_items = keywords.split(",")
    else:
        raw_items = keywords
    cleaned: List[str] = []
    seen = set()
    for item in raw_items:
        label = item.strip()
        if not label:
            continue
        lower = label.lower()
        if lower in seen:
            continue
        seen.add(lower)
        cleaned.append(label)
    return cleaned


def _matches_keywords(prompt: dict, keywords: Sequence[str]) -> bool:
    haystack = [
        prompt.get("persona", ""),
        prompt.get("task", ""),
    ]
    haystack.extend(prompt.get("keywords_used_for_search", []))

    haystack_joined = " ".join([str(item).lower() for item in haystack if item])
    for keyword in keywords:
        if keyword.lower() in haystack_joined:
            return True
    return False
