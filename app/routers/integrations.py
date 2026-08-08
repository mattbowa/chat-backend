import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.integration import Integration
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.integration import IntegrationOut, WebsiteUpsert
from app.services.crawler import sync_website

router = APIRouter(prefix="/integrations", tags=["integrations"])


def _to_out(i: Integration) -> IntegrationOut:
    config = i.config or {}
    return IntegrationOut(
        id=i.id,
        type=i.type,
        status=i.status,
        last_synced_at=i.last_synced_at,
        error_message=i.error_message,
        created_at=i.created_at,
        site_url=config.get("site_url"),
        connected=bool(config.get("site_url")),
    )


@router.get("", response_model=list[IntegrationOut])
async def list_integrations(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Integration).where(Integration.tenant_id == user.tenant_id))
    return [_to_out(i) for i in result.scalars().all()]


@router.put("/website", response_model=IntegrationOut)
async def upsert_website(
    body: WebsiteUpsert,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.tenant_id == user.tenant_id,
            Integration.type == "website",
        )
    )
    integration = result.scalar_one_or_none()

    site_url = body.site_url.strip().rstrip("/")
    if "://" not in site_url:
        site_url = f"https://{site_url}"

    if integration is None:
        integration = Integration(
            tenant_id=user.tenant_id,
            type="website",
            config={"site_url": site_url},
        )
        db.add(integration)
    else:
        integration.config = {"site_url": site_url}
        integration.status = "idle"
        integration.error_message = None

    await db.commit()
    await db.refresh(integration)
    return _to_out(integration)


@router.post("/{integration_id}/sync", response_model=IntegrationOut)
async def trigger_sync(
    integration_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == user.tenant_id,
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")
    if integration.type != "website":
        raise HTTPException(status_code=400, detail="Unsupported integration type")

    integration.status = "syncing"
    integration.error_message = None
    await db.commit()
    await db.refresh(integration)

    background_tasks.add_task(sync_website, integration.id, user.tenant_id)
    return _to_out(integration)


@router.delete("/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Integration).where(
            Integration.id == integration_id,
            Integration.tenant_id == user.tenant_id,
        )
    )
    integration = result.scalar_one_or_none()
    if integration is None:
        raise HTTPException(status_code=404, detail="Integration not found")

    await db.delete(integration)
    await db.commit()
