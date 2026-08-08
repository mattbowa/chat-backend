import json
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.message import Message
from app.models.tenant import Tenant, TenantSettings
from app.services.llm import stream_chat_response
from app.services.retrieval import embed_query, retrieve_chunks

router = APIRouter(prefix="/public", tags=["public"])

SIMILARITY_THRESHOLD = 0.35

# Per-IP rate limit for the public chat endpoint. In-memory sliding window —
# resets on restart and is per-process, which is fine for a single instance.
RATE_LIMIT_REQUESTS = 20
RATE_LIMIT_WINDOW_SECONDS = 60
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_rate_limit(request: Request) -> None:
    now = time.monotonic()
    bucket = _rate_buckets[_client_ip(request)]
    while bucket and now - bucket[0] > RATE_LIMIT_WINDOW_SECONDS:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    bucket.append(now)
    # Bound memory: drop stale buckets once the map grows large
    if len(_rate_buckets) > 10_000:
        for ip in [ip for ip, b in _rate_buckets.items() if not b or now - b[-1] > RATE_LIMIT_WINDOW_SECONDS]:
            del _rate_buckets[ip]


# The dashboard/widget-preview runs on our own frontend — always allowed.
_TRUSTED_HOSTS = {
    urlparse(o if "://" in o else f"https://{o}").netloc.split(":")[0].lower()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
}


def _check_origin(request: Request, parent_host: str | None, allowed_domains: list[str] | None) -> None:
    """If the tenant configured a domain allowlist, the widget may only be
    embedded on those domains (or their subdomains). Empty list = allow all.

    The widget iframe is served from OUR frontend, so the Origin header of
    chat requests is always our own domain — the embedding site's host is
    passed by widget.js as `parent_host`. This deters embed-code copying;
    scripted abuse is handled by the rate limit and monthly cap.
    """
    if not allowed_domains:
        return

    candidates = set()
    if parent_host:
        candidates.add(parent_host.strip().lower())
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if value:
            candidates.add(urlparse(value).netloc.split(":")[0].lower())
    candidates.discard("")

    if candidates & _TRUSTED_HOSTS:
        return
    for domain in allowed_domains:
        d = domain.strip().lower().lstrip("*.").rstrip("/")
        if "://" in d:
            d = urlparse(d).netloc.split(":")[0]
        if d and any(host == d or host.endswith("." + d) for host in candidates):
            return
    raise HTTPException(status_code=403, detail="This chatbot is not enabled for this website.")


async def _check_message_limit(tenant_id: uuid.UUID, db: AsyncSession) -> None:
    """Cap assistant messages per calendar month to bound LLM spend.

    There is no paid tier — over-limit tenants are pointed at the contact
    form so the limit can be raised manually.
    """
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == tenant_id,
            Message.role == "assistant",
            Message.created_at >= month_start,
        )
    )
    count = result.scalar() or 0
    if count >= settings.monthly_message_limit:
        raise HTTPException(
            status_code=429,
            detail=(
                f"This chatbot has reached its limit of {settings.monthly_message_limit} "
                "messages this month. Please get in touch to have it raised."
            ),
        )


class PublicChatRequest(BaseModel):
    session_id: str
    message: str
    visitor_email: str | None = None
    parent_host: str | None = None


@router.post("/chat/{slug}")
async def public_chat(
    slug: str,
    body: PublicChatRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    _check_rate_limit(request)

    result = await db.execute(select(Tenant).where(Tenant.slug == slug))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(404, "Chatbot not found")

    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == tenant.id))
    tenant_settings = result.scalar_one()

    _check_origin(request, body.parent_host, tenant_settings.allowed_domains)
    await _check_message_limit(tenant.id, db)

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
    chunks = await retrieve_chunks(db, tenant.id, query_embedding, top_k=tenant_settings.top_k_chunks)
    max_sim = max((c["similarity"] for c in chunks), default=0.0)
    suggested_questions = tenant_settings.suggested_questions or []

    async def event_stream():
        if max_sim < SIMILARITY_THRESHOLD:
            fallback = tenant_settings.fallback_message
            yield f"data: {json.dumps({'token': fallback})}\n\n"

            user_msg.is_fallback = True
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
            system_prompt=tenant_settings.system_prompt,
            model=tenant_settings.model,
            temperature=tenant_settings.temperature,
            max_tokens=tenant_settings.max_response_tokens,
            fallback_message=tenant_settings.fallback_message,
        ):
            full_response += token
            yield f"data: {json.dumps({'token': token})}\n\n"

        # The LLM is instructed to echo the fallback message verbatim when the
        # retrieved context doesn't cover the question — count that too.
        if full_response.strip() == tenant_settings.fallback_message.strip():
            user_msg.is_fallback = True

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
