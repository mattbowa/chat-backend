import json
import logging
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.message import Message
from app.models.tenant import TenantSettings
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.chat import ChatRequest, MessageOut, SessionOut
from app.services.llm import STREAM_ERROR_MESSAGE, stream_chat_response
from app.services.retrieval import embed_query, retrieve_chunks

router = APIRouter(prefix="/chat", tags=["chat"])

logger = logging.getLogger(__name__)


@router.post("")
async def chat(
    body: ChatRequest,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id))
    tenant_settings = result.scalar_one()

    user_msg = Message(
        tenant_id=user.tenant_id,
        session_id=body.session_id,
        role="user",
        content=body.message,
    )
    db.add(user_msg)
    await db.commit()

    query_embedding = await embed_query(body.message)
    chunks = await retrieve_chunks(db, user.tenant_id, query_embedding, top_k=tenant_settings.top_k_chunks)

    async def event_stream():
        full_response = ""
        try:
            async for token in stream_chat_response(
                query=body.message,
                chunks=chunks,
                system_prompt=tenant_settings.system_prompt,
                model=tenant_settings.model,
                temperature=tenant_settings.temperature,
                max_tokens=tenant_settings.max_response_tokens,
            ):
                full_response += token
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception:
            # The 200 and headers are already on the wire, so this can't become
            # an HTTP error response — without an explicit error event the UI
            # would sit on a typing indicator forever.
            logger.exception("LLM stream failed for tenant %s", user.tenant_id)
            yield f"data: {json.dumps({'error': STREAM_ERROR_MESSAGE})}\n\n"
            yield f"data: {json.dumps({'done': True, 'sources': []})}\n\n"
            return

        assistant_msg = Message(
            tenant_id=user.tenant_id,
            session_id=body.session_id,
            role="assistant",
            content=full_response,
            sources=chunks,
        )
        db.add(assistant_msg)
        await db.commit()

        yield f"data: {json.dumps({'done': True, 'sources': chunks})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        select(
            Message.session_id,
            func.count(Message.id).label("message_count"),
            func.max(Message.created_at).label("last_message_at"),
        )
        .where(Message.tenant_id == user.tenant_id)
        .group_by(Message.session_id)
        .order_by(func.max(Message.created_at).desc())
    )
    return [SessionOut(session_id=r.session_id, message_count=r.message_count, last_message_at=r.last_message_at) for r in rows]


@router.get("/sessions/{session_id}", response_model=list[MessageOut])
async def get_session(
    session_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id, Message.tenant_id == user.tenant_id)
        .order_by(Message.created_at)
    )
    return result.scalars().all()
