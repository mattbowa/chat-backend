import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.message import Message
from app.models.tenant import Tenant, TenantSettings
from app.services.llm import stream_chat_response
from app.services.retrieval import embed_query, retrieve_chunks

router = APIRouter(prefix="/public", tags=["public"])

SIMILARITY_THRESHOLD = 0.35

FREE_TIER_LIMIT = 100  # assistant messages per month

# ----------------------------------------------------------------
# STRIPE (future) — replace this with a subscription-aware check
# that reads tenant.plan and sets the limit accordingly:
#   if tenant.plan == "pro": limit = 2000
#   elif tenant.plan == "enterprise": limit = unlimited
# ----------------------------------------------------------------
async def _check_rate_limit(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.created_at >= month_start,
        )
    )
    count = result.scalar() or 0
    if count >= FREE_TIER_LIMIT:
        raise HTTPException(
            status_code=429,
            detail=f"Free tier limit of {FREE_TIER_LIMIT} messages/month reached. Upgrade to continue.",
        )


class PublicChatRequest(BaseModel):
    session_id: str
    message: str
    visitor_email: str | None = None


@router.post("/chat/{slug}")
async def public_chat(
    slug: str,
    body: PublicChatRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Chatbot not found")

    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
    settings = result.scalar_one()

    await _check_rate_limit(tenant.id, db)

    session_id = uuid.UUID(body.session_id) if _is_valid_uuid(body.session_id) else uuid.uuid4()

    user_msg = Message(
        tenant_id=tenant.id,
        session_id=session_id,
        role="user",
        content=body.message,
        visitor_email=body.visitor_email,
    )
    db.add(user_msg)
    await db.commit()

    query_embedding = await embed_query(body.message)
    chunks = await retrieve_chunks(db, tenant.id, query_embedding, top_k=settings.top_k_chunks)
    max_sim = max((c["similarity"] for c in chunks), default=0.0)
    suggested_questions = settings.suggested_questions or []

    async def event_stream():
        if max_sim < SIMILARITY_THRESHOLD:
            fallback = settings.fallback_message
            yield f"data: {json.dumps({'token': fallback})}\n\n"

            assistant_msg = Message(
                tenant_id=tenant.id,
                session_id=session_id,
                role="assistant",
                content=fallback,
                sources=[],
            )
            db.add(assistant_msg)
            await db.commit()

            yield f"data: {json.dumps({'done': True, 'sources': [], 'suggested_questions': suggested_questions})}\n\n"
            return

        full_response = ""
        async for token in stream_chat_response(
            query=body.message,
            chunks=chunks,
            system_prompt=settings.system_prompt,
            model=settings.model,
            temperature=settings.temperature,
            max_tokens=settings.max_response_tokens,
            fallback_message=settings.fallback_message,
        ):
            full_response += token
            yield f"data: {json.dumps({'token': token})}\n\n"

        assistant_msg = Message(
            tenant_id=tenant.id,
            session_id=session_id,
            role="assistant",
            content=full_response,
            sources=chunks,
        )
        db.add(assistant_msg)
        await db.commit()

        yield f"data: {json.dumps({'done': True, 'sources': chunks, 'suggested_questions': []})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/settings/{slug}")
async def public_settings(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Chatbot not found")

    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
    s = result.scalar_one()
    return {
        "bot_name": s.bot_name,
        "primary_color": s.primary_color,
        "logo_url": s.logo_url,
        "tenant_name": tenant.name,
        "suggested_questions": s.suggested_questions or [],
    }


def _is_valid_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
