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
    """Nearest-neighbour search over document chunks AND curated Q&A pairs.

    Both live in the same vector space (same embedding model), so one UNION'd
    scan ranks them together and a curated answer competes on merit. Each row
    carries a `kind` so the prompt builder can mark curated answers as
    authoritative — see app/services/llm.py.

    Note: the UNION means neither table's IVFFlat index (both commented out in
    migrations, to be built by hand) can serve this as a single ANN lookup.
    That's fine at current scale; revisit if a tenant's corpus gets large.
    """
    result = await db.execute(
        text(
            "SELECT content, kind, ref_id, chunk_index, "
            "1 - (embedding <=> :embedding) AS similarity "
            "FROM ("
            "  SELECT content, 'document' AS kind, document_id AS ref_id, chunk_index, embedding "
            "  FROM document_chunks WHERE tenant_id = :tenant_id "
            "  UNION ALL "
            "  SELECT 'Q: ' || question || E'\\nA: ' || answer AS content, "
            "         'qa' AS kind, id AS ref_id, 0 AS chunk_index, embedding "
            "  FROM qa_pairs WHERE tenant_id = :tenant_id"
            ") AS candidates "
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
            "kind": row.kind,
            # Kept named document_id for backwards compatibility: this field is
            # persisted into messages.sources and read by the chat UI. For a
            # curated pair it holds the qa_pairs id.
            "document_id": str(row.ref_id),
            "chunk_index": row.chunk_index,
            "similarity": float(row.similarity),
        }
        for row in result
    ]
