import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.qa import QAPair
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.qa import QAPairCreate, QAPairOut, QAPairUpdate
from app.services.qa import create_qa_pair, update_qa_pair

router = APIRouter(prefix="/qa", tags=["qa"])

# Curated answers are cheap (one row, one embedding) and don't count against
# the document limit, but the cap keeps a runaway script in check.
QA_LIMIT = 200


@router.get("", response_model=list[QAPairOut])
async def list_qa_pairs(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(QAPair)
        .where(QAPair.tenant_id == user.tenant_id)
        .order_by(QAPair.updated_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=QAPairOut, status_code=201)
async def add_qa_pair(
    body: QAPairCreate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(func.count(QAPair.id)).where(QAPair.tenant_id == user.tenant_id)
    )
    if (result.scalar() or 0) >= QA_LIMIT:
        raise HTTPException(400, f"Answer limit of {QA_LIMIT} reached. Get in touch to have it raised.")

    qa_id = await create_qa_pair(db, user.tenant_id, body.question.strip(), body.answer.strip())
    await db.commit()

    result = await db.execute(select(QAPair).where(QAPair.id == qa_id))
    return result.scalar_one()


@router.patch("/{qa_id}", response_model=QAPairOut)
async def edit_qa_pair(
    qa_id: uuid.UUID,
    body: QAPairUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QAPair).where(QAPair.id == qa_id, QAPair.tenant_id == user.tenant_id)
    )
    pair = result.scalar_one_or_none()
    if not pair:
        raise HTTPException(404, "Answer not found")

    question = body.question.strip()
    await update_qa_pair(
        db,
        qa_id,
        user.tenant_id,
        question,
        body.answer.strip(),
        reembed=question != pair.question,
    )
    await db.commit()

    result = await db.execute(select(QAPair).where(QAPair.id == qa_id))
    return result.scalar_one()


@router.delete("/{qa_id}", status_code=204)
async def remove_qa_pair(
    qa_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(QAPair).where(QAPair.id == qa_id, QAPair.tenant_id == user.tenant_id)
    )
    pair = result.scalar_one_or_none()
    if not pair:
        raise HTTPException(404, "Answer not found")

    await db.delete(pair)
    await db.commit()
