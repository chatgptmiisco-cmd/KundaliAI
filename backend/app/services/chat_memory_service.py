"""Retrieval over a user's own older chat turns — the piece that covers
conversational context with no dedicated structured field (see
app.services.life_context_service for the facts that DO get one, e.g.
career_state). chat.py's raw history window (_HISTORY_LIMIT) only ever
sends the most recent ~20 messages to the model; anything said further
back and never captured as a structured fact was previously just gone.
This lets it stay reachable by semantic similarity instead.

Deliberately no pgvector: not installed on the dev Postgres (checked via
`SELECT * FROM pg_available_extensions WHERE name='vector'` — nothing),
and unusable on the SQLite test DB regardless. Embeddings are stored as a
plain JSON-encoded float list on ChatMessage.embedding (assistant rows
only — see that column's docstring) and ranked with an ordinary Python
cosine similarity, which is more than fast enough at one user's own
message-history scale (realistically low thousands of turns at most).

Same "enhancement, never a hard dependency" philosophy as
app.services.voice.stt: any OpenAI failure here (quota, network, whatever)
degrades to "no retrieved context this turn," never a broken reply."""
import json
import math
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models.chat import ChatMessage
from app.db.models.life_context import LifeContextItem

_logger = get_logger("chat_memory_service")

# How much of a single exchange actually gets embedded — bounds the
# embedding call's input size (and cost) regardless of how long a reply
# runs; a retrieval snippet doesn't need every word to be useful for
# similarity matching or as a short "you mentioned earlier..." callback.
_EMBED_TEXT_MAX_CHARS = 2000
_DEFAULT_TOP_K = 3
# Cosine similarity is bounded [-1, 1] for real embeddings in practice
# closer to [0, 1] for same-domain text; below this, a "match" is closer
# to noise than a genuine callback and is worse than saying nothing.
_DEFAULT_MIN_SIMILARITY = 0.75


async def retrieve_native_turns(db, user_id, categories, query_text, limit=3, exclude_ids=None):
    """Cross-persona, user-scoped lexical retrieval with no embeddings required.

    Searches user statements rather than reclassifying an assistant's astrology
    as user knowledge. At most three short relevant quotes enter the response
    context. Existing semantic retrieval remains available separately.

    Three guards, all caught live off real transcripts: a past QUESTION
    ("what does my kundli say about marriage?") is never a "situation" to
    check back on — native_response.compose's callback wording only makes
    sense for a stated fact, so a row matching native_understanding.
    is_question is skipped outright rather than quoted back nonsensically.
    A bare navigational reply ("relationship", "career" — picking a topic,
    not stating a fact) is skipped the same way (is_navigational_reply).
    `exclude_ids` (already-surfaced quote ids, tracked in ConversationState
    by chat.py) keeps the same callback from resurfacing every single turn
    the topic recurs — once shown, it's shown, not repeated forever."""
    from app.services.native_understanding import detect_intents, is_navigational_reply, is_question
    from app.services.chat_understanding import relevant_domains
    # "goals" sits in almost every category's domain tuple in
    # _CATEGORY_DOMAINS (career, money, business, career_confusion,
    # debt...) — a deliberately inclusive default for FACT retrieval
    # (user_context_engine.retrieve), where surfacing a stated goal across
    # topics is reasonable. But it makes "goals" alone a false-positive
    # relevance signal for THIS callback specifically — caught live: a bare
    # "money" question resurfaced "there is no growth in my job" (a career
    # statement) as "an earlier related conversation", purely because
    # career's and money's domain tuples both happen to include "goals".
    # Excluded here only, not from _CATEGORY_DOMAINS itself, so fact
    # retrieval elsewhere is unaffected.
    domains = set(relevant_domains(categories)) - {"goals"}
    if not domains:
        return []
    exclude_ids = exclude_ids or set()
    inactive_values = [value.casefold() for value in (await db.scalars(
        select(LifeContextItem.value).where(
            LifeContextItem.user_id == user_id, LifeContextItem.status == "inactive",
        )
    )).all() if value]
    words = set(re.findall(r"\w{3,}", query_text.lower())) - {"what", "when", "will", "should", "about", "with", "have", "that", "this", "does"}
    scored = []
    # Stream history in batches: bound response context, not the user's memory
    # lifetime. No full transcript is sent to any provider.
    result = await db.stream_scalars(select(ChatMessage).where(
        ChatMessage.user_id == user_id, ChatMessage.role == "user"
    ).order_by(ChatMessage.id.desc()).execution_options(yield_per=100))
    async for row in result:
        if any(value in row.content.casefold() for value in inactive_values):
            continue
        if row.id in exclude_ids or is_question(row.content) or is_navigational_reply(row.content):
            continue
        row_domains = set(relevant_domains(detect_intents(row.content))) - {"goals"}
        if not domains.intersection(row_domains):
            continue
        overlap = len(words & set(re.findall(r"\w{3,}", row.content.lower())))
        scored.append((overlap, row.id, row))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        del scored[limit:]
    return [{"text": row.content[:360], "when": _relative_when(row.created_at), "source": "user_quote", "id": row.id}
            for _, _, row in scored]


def _turn_text(user_message: str, assistant_reply: str) -> str:
    text = f"User: {user_message}\nAssistant: {assistant_reply}"
    return text[:_EMBED_TEXT_MAX_CHARS]


async def embed_text(text: str) -> list[float] | None:
    """Returns None (never raises) on any failure — an embedding call is a
    pure enhancement; a user's actual reply must never fail because this
    did."""
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from openai import AsyncOpenAI  # local import: only needed on this path, same convention as stt.py

        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.embeddings.create(model=settings.embedding_model, input=text)
        return list(response.data[0].embedding)
    except Exception:
        _logger.warning("chat_memory_embed_failed", exc_info=True)
        return None


async def embed_turn(user_message: str, assistant_reply: str) -> tuple[list[float], str] | None:
    """Returns (embedding, source_text) so the caller can store both
    ChatMessage.embedding and .embedding_source_text together — None
    (never raises) if embedding failed, same convention as embed_text."""
    text = _turn_text(user_message, assistant_reply)
    embedding = await embed_text(text)
    if embedding is None:
        return None
    return embedding, text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _relative_when(when: datetime) -> str:
    if when.tzinfo is None:  # SQLite round-trips naive — see life_context_service's same defensive check
        when = when.replace(tzinfo=timezone.utc)
    days_ago = max(0, (datetime.now(timezone.utc) - when).days)
    if days_ago == 0:
        return "earlier today"
    if days_ago == 1:
        return "yesterday"
    if days_ago < 30:
        return f"{days_ago} days ago"
    if days_ago < 365:
        return f"{days_ago // 30} months ago"
    return f"{days_ago // 365} years ago"


async def retrieve_relevant_turns(
    db: AsyncSession, user_id: str, rishi_id: str | None, query_text: str, exclude_ids_below: int, top_k: int = _DEFAULT_TOP_K,
) -> list[dict]:
    """Nothing to retrieve (and no embedding call made at all) when
    exclude_ids_below is 0 — the conversation hasn't even filled the raw
    history window yet, so there's nothing outside it to search for. Older
    turns are anything with id < exclude_ids_below, since chat.py's raw
    window is always a contiguous most-recent block — a plain id
    comparison is an exact, cheap "strictly older than the window"
    filter, no set-membership check needed."""
    if exclude_ids_below <= 0:
        return []
    result = await db.execute(
        select(ChatMessage).where(
            ChatMessage.user_id == user_id,
            ChatMessage.rishi_id == rishi_id,
            ChatMessage.role == "assistant",
            ChatMessage.id < exclude_ids_below,
            ChatMessage.embedding.is_not(None),
        )
    )
    candidates = result.scalars().all()
    if not candidates:
        return []

    query_embedding = await embed_text(query_text)
    if query_embedding is None:
        return []

    scored: list[tuple[float, ChatMessage]] = []
    for row in candidates:
        try:
            row_embedding = json.loads(row.embedding)
        except (TypeError, ValueError):
            continue
        similarity = cosine_similarity(query_embedding, row_embedding)
        if similarity >= _DEFAULT_MIN_SIMILARITY:
            scored.append((similarity, row))
    scored.sort(key=lambda pair: pair[0], reverse=True)

    return [
        {"text": row.embedding_source_text or row.content, "when": _relative_when(row.created_at)}
        for _, row in scored[:top_k]
    ]
