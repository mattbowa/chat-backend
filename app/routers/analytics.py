from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.message import Message
from app.models.document import Document
from app.models.user import User
from app.routers.deps import current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/usage")
async def get_usage(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Messages this month
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == user.tenant_id,
            Message.role == "assistant",
            Message.created_at >= month_start,
        )
    )
    messages_this_month = result.scalar() or 0

    # Total messages ever
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == user.tenant_id,
            Message.role == "assistant",
        )
    )
    total_messages = result.scalar() or 0

    # Document count
    result = await db.execute(
        select(func.count(Document.id)).where(
            Document.tenant_id == user.tenant_id,
            Document.status == "ready",
        )
    )
    doc_count = result.scalar() or 0

    # Messages per day — last 30 days
    thirty_days_ago = now - timedelta(days=30)
    result = await db.execute(
        select(
            func.date_trunc("day", Message.created_at).label("day"),
            func.count(Message.id).label("count"),
        )
        .where(
            Message.tenant_id == user.tenant_id,
            Message.role == "assistant",
            Message.created_at >= thirty_days_ago,
        )
        .group_by(text("day"))
        .order_by(text("day"))
    )
    daily = [{"date": str(r.day.date()), "count": r.count} for r in result]

    # Recent questions (last 10 user messages)
    result = await db.execute(
        select(Message.content, Message.created_at)
        .where(Message.tenant_id == user.tenant_id, Message.role == "user")
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    recent_questions = [{"question": r.content, "at": str(r.created_at.date())} for r in result]

    # Unanswered questions — user messages that got the fallback answer,
    # grouped so repeat questions surface as one row with a count.
    result = await db.execute(
        select(
            func.min(Message.content).label("question"),
            func.count(Message.id).label("count"),
            func.max(Message.created_at).label("last_at"),
        )
        .where(
            Message.tenant_id == user.tenant_id,
            Message.role == "user",
            Message.is_fallback,
            Message.created_at >= thirty_days_ago,
        )
        .group_by(func.lower(func.trim(Message.content)))
        .order_by(text("count DESC"), text("last_at DESC"))
        .limit(20)
    )
    unanswered_questions = [
        {"question": r.question, "count": r.count, "at": str(r.last_at.date())} for r in result
    ]

    # Answer rate over the same 30-day window
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == user.tenant_id,
            Message.role == "user",
            Message.created_at >= thirty_days_ago,
        )
    )
    questions_30d = result.scalar() or 0
    result = await db.execute(
        select(func.count(Message.id)).where(
            Message.tenant_id == user.tenant_id,
            Message.role == "user",
            Message.is_fallback,
            Message.created_at >= thirty_days_ago,
        )
    )
    fallback_30d = result.scalar() or 0

    return {
        "messages_this_month": messages_this_month,
        "message_limit": settings.monthly_message_limit,
        "messages_remaining": max(0, settings.monthly_message_limit - messages_this_month),
        "total_messages": total_messages,
        "doc_count": doc_count,
        "daily_messages": daily,
        "recent_questions": recent_questions,
        "unanswered_questions": unanswered_questions,
        "questions_30d": questions_30d,
        "fallback_30d": fallback_30d,
        "answer_rate": round(100 * (1 - fallback_30d / questions_30d)) if questions_30d else None,
    }
