from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.tenant import TenantSettings
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.settings import SettingsOut, SettingsUpdate

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=SettingsOut)
async def get_settings(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id))
    return result.scalar_one()


@router.patch("", response_model=SettingsOut)
async def update_settings(
    body: SettingsUpdate,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TenantSettings).where(TenantSettings.tenant_id == user.tenant_id))
    s = result.scalar_one()

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(s, field, value)

    await db.commit()
    await db.refresh(s)
    return s
