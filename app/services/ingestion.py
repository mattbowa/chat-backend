import io
import uuid

from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import AsyncOpenAI
from pypdf import PdfReader
from sqlalchemy import select, text
from supabase import create_client
import docx

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.document import Document

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
supabase = create_client(settings.supabase_url, settings.supabase_service_key)
splitter = RecursiveCharacterTextSplitter(chunk_size=512, chunk_overlap=50)
EMBEDDING_MODEL = "text-embedding-3-small"


def _extract_text(filename: str, content: bytes) -> str:
    if filename.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    if filename.endswith(".docx"):
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    return content.decode("utf-8", errors="ignore")


async def _embed_texts(texts: list[str]) -> list[list[float]]:
    response = await openai_client.embeddings.create(model=EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


async def ingest_document(
    document_id: uuid.UUID,
    tenant_id: uuid.UUID,
    filename: str,
    file_content: bytes,
) -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Document).where(Document.id == document_id))
        doc = result.scalar_one()
        doc.status = "processing"
        await db.commit()

        try:
            # Upload original file to Supabase Storage for later download
            try:
                supabase.storage.from_(settings.supabase_storage_bucket).upload(
                    path=doc.storage_path,
                    file=file_content,
                    file_options={"content-type": "application/octet-stream", "upsert": "true"},
                )
            except Exception:
                pass  # storage upload failure doesn't block ingestion

            text_content = _extract_text(filename, file_content)
            chunks = splitter.split_text(text_content)

            all_embeddings = []
            for i in range(0, len(chunks), 100):
                batch = chunks[i : i + 100]
                embeddings = await _embed_texts(batch)
                all_embeddings.extend(embeddings)

            for idx, (chunk_text, embedding) in enumerate(zip(chunks, all_embeddings)):
                await db.execute(
                    text(
                        "INSERT INTO document_chunks (id, tenant_id, document_id, chunk_index, content, embedding) "
                        "VALUES (:id, :tenant_id, :doc_id, :idx, :content, :embedding)"
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "tenant_id": str(tenant_id),
                        "doc_id": str(document_id),
                        "idx": idx,
                        "content": chunk_text,
                        "embedding": str(embedding),
                    },
                )

            doc.chunk_count = len(chunks)
            doc.status = "ready"

        except Exception as e:
            doc.status = "error"
            doc.error_message = str(e)[:900]

        await db.commit()
