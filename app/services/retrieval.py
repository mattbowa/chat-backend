import uuid

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings

openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
EMBEDDING_MODEL = "text-embedding-3-small"


async def embed_query(query: str) -> list[float]:
    response = await openai_client.embeddings.create(model=EMBEDDING_MODEL, input=[query])
    return response.data[0].embedding


async def retrieve_chunks(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    result = await db.execute(
        text(
            "SELECT content, document_id, chunk_index, "
            "1 - (embedding <=> :embedding) AS similarity "
            "FROM document_chunks "
            "WHERE tenant_id = :tenant_id "
            "ORDER BY embedding <=> :embedding "
            "LIMIT :top_k"
        ),
        {
            "embedding": str(query_embedding),
            "tenant_id": str(tenant_id),
            "top_k": top_k,
        },
    )
    return [
        {
            "content": row.content,
            "document_id": str(row.document_id),
            "chunk_index": row.chunk_index,
            "similarity": float(row.similarity),
        }
        for row in result
    ]
