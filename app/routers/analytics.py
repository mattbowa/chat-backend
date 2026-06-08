from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.message import Message
from app.models.document import Document
from app.models.user import User
from app.routers.deps import current_user

router = APIRouter(prefix="/analytics", tags=["analytics"])

FREE_TIER_LIMIT = 100  # messages per month


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

    return {
        "plan": "free",
        "messages_this_month": messages_this_month,
        "free_tier_limit": FREE_TIER_LIMIT,
        "messages_remaining": max(0, FREE_TIER_LIMIT - messages_this_month),
        "total_messages": total_messages,
        "doc_count": doc_count,
        "daily_messages": daily,
        "recent_questions": recent_questions,
        # --------------------------------------------------------
        # STRIPE (future) — uncomment when billing is added
        # --------------------------------------------------------
        # "stripe_status": tenant.subscription_status,
        # "next_billing_date": ...,
    }