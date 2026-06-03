from collections.abc import AsyncGenerator

import anthropic

from app.core.config import settings

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _build_context_block(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[Source {i}]\n{chunk['content']}")
    return "\n\n".join(parts)


async def stream_chat_response(
    query: str,
    chunks: list[dict],
    system_prompt: str,
    model: str,
    temperature: float,
    max_tokens: int,
) -> AsyncGenerator[str, None]:
    context = _build_context_block(chunks)

    full_system = (
        f"{system_prompt}\n\n"
        "Use the reference information below to answer the user's question. "
        "Answer naturally and conversationally — never mention 'context', 'reference material', or 'documents' in your reply. "
        "If the question is not covered by the reference information, politely say you can only help with topics related to this service and suggest the user contact support.\n\n"
        f"REFERENCE INFORMATION:\n{context}"
    )

    async with client.messages.stream(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=full_system,
        messages=[{"role": "user", "content": query}],
    ) as stream:
        async for text in stream.text_stream:
            yield text
