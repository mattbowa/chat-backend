import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.retrieval import embed_query

# Cap so a pasted essay can't blow out the embedding call or the context window.
MAX_QUESTION_LEN = 500
MAX_ANSWER_LEN = 4000


async def create_qa_pair(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    question: str,
    answer: str,
) -> uuid.UUID:
    """Embed the question and insert the pair. Caller owns the commit."""
    embedding = await embed_query(question)
    qa_id = uuid.uuid4()

    await db.execute(
        text(
            "INSERT INTO qa_pairs (id, tenant_id, question, answer, embedding) "
            "VALUES (:id, :tenant_id, :question, :answer, :embedding)"
        ),
        {
            "id": str(qa_id),
            "tenant_id": str(tenant_id),
            "question": question,
            "answer": answer,
            "embedding": str(embedding),
        },
    )
    return qa_id


async def update_qa_pair(
    db: AsyncSession,
    qa_id: uuid.UUID,
    tenant_id: uuid.UUID,
    question: str,
    answer: str,
    reembed: bool,
) -> None:
    """Update a pair, re-embedding only when the question text actually changed.

    Editing just the answer is the common case and needs no embedding call.
    """
    params = {
        "id": str(qa_id),
        "tenant_id": str(tenant_id),
        "question": question,
        "answer": answer,
    }

    if reembed:
        params["embedding"] = str(await embed_query(question))
        sql = (
            "UPDATE qa_pairs SET question = :question, answer = :answer, "
            "embedding = :embedding, updated_at = NOW() "
            "WHERE id = :id AND tenant_id = :tenant_id"
        )
    else:
        sql = (
            "UPDATE qa_pairs SET question = :question, answer = :answer, updated_at = NOW() "
            "WHERE id = :id AND tenant_id = :tenant_id"
        )

    await db.execute(text(sql), params)
