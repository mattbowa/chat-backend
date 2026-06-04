import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from supabase import create_client

from sqlalchemy import func
from app.core.config import settings
from app.core.database import get_db

FREE_TIER_DOC_LIMIT = 10

supabase = create_client(settings.supabase_url, settings.supabase_service_key)
from app.models.document import Document
from app.models.user import User
from app.routers.deps import current_user
from app.schemas.document import DocumentOut
from app.services.ingestion import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}
MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    doc_count = await db.execute(
        select(func.count(Document.id)).where(Document.tenant_id == user.tenant_id)
    )
    if (doc_count.scalar() or 0) >= FREE_TIER_DOC_LIMIT:
        raise HTTPException(400, f"Free tier limit of {FREE_TIER_DOC_LIMIT} documents reached.")

    ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(400, "File too large (max 20 MB)")

    doc = Document(
        tenant_id=user.tenant_id,
        filename=file.filename,
        storage_path=f"{user.tenant_id}/{uuid.uuid4()}{ext}",
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    background_tasks.add_task(ingest_document, doc.id, user.tenant_id, file.filename, content)

    return doc


@router.get("", response_model=list[DocumentOut])
async def list_documents(user: User = Depends(current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Document).where(Document.tenant_id == user.tenant_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.get("/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == user.tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    signed = supabase.storage.from_(settings.supabase_storage_bucket).create_signed_url(
        path=doc.storage_path,
        expires_in=60,  # URL valid for 60 seconds
    )
    return RedirectResponse(url=signed["signedURL"])


@router.delete("/{document_id}", status_code=204)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Document).where(Document.id == document_id, Document.tenant_id == user.tenant_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")

    await db.execute(
        text("DELETE FROM document_chunks WHERE document_id = :doc_id AND tenant_id = :tenant_id"),
        {"doc_id": str(document_id), "tenant_id": str(user.tenant_id)},
    )
    await db.delete(doc)
    await db.commit()

    supabase.storage.from_(settings.supabase_storage_bucket).remove([doc.storage_path])
