from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.models.contact import ContactSubmission
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.contact import ContactCreate, ContactOut
from app.services.email import send_contact_notification

router = APIRouter(tags=["contact"])


@router.post("/public/contact", status_code=201)
async def submit_contact(
    body: ContactCreate,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    """Unauthenticated contact form. Persists first, emails as a side effect."""
    submission = ContactSubmission(
        name=body.name,
        email=body.email,
        message=body.message,
        source=body.source,
    )
    db.add(submission)
    await db.commit()

    background_tasks.add_task(
        send_contact_notification, body.name, body.email, body.message, body.source
    )
    return {"ok": True}


@router.get("/contact/submissions", response_model=list[ContactOut])
async def list_submissions(
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner-facing inbox. Returns every submission, newest first.

    Submissions are addressed to the app owner, not to a tenant, so this
    deliberately does NOT filter by tenant_id — which means it must be
    restricted to the owner account rather than any authenticated user.
    """
    if user.email.lower() != settings.contact_to_email.lower():
        raise HTTPException(403, "Not authorised.")

    result = await db.execute(
        select(ContactSubmission).order_by(ContactSubmission.created_at.desc()).limit(200)
    )
    return list(result.scalars())
