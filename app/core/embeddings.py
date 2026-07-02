"""
Embedding Service — API-based semantic similarity for Render free tier
======================================================================
Uses Gemini text-embedding-004 (free tier) so there is ZERO local model RAM
cost. Vectors are cached in SQLite keyed by content hash, so repeated goals,
tool names, and memory fragments never re-hit the API.

Falls back gracefully: every public function returns None when embeddings are
unavailable (no GOOGLE_API_KEY, quota, network), and callers keep their
keyword-based heuristics as the fallback path.
"""

import asyncio
import hashlib
import json
import logging
import math
import os
import time
from typing import List, Optional

logger = logging.getLogger(__name__)

_EMBED_MODEL = "models/text-embedding-004"
_CACHE_TABLE_READY = False
_CACHE_LOCK = asyncio.Lock()
# Circuit breaker: after repeated API failures, stop trying for a cooldown
_FAIL_COUNT = 0
_FAIL_LIMIT = 3
_COOLDOWN_UNTIL = 0.0
_COOLDOWN_SECONDS = 600

# Small in-process LRU on top of the SQLite cache (hot goals/tools repeat a lot)
_hot_cache: dict = {}
_HOT_CACHE_MAX = 256


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


async def _ensure_cache_table():
    global _CACHE_TABLE_READY
    if _CACHE_TABLE_READY:
        return
    async with _CACHE_LOCK:
        if _CACHE_TABLE_READY:
            return
        from app.core.database import DatabaseManager
        await DatabaseManager.query(
            """CREATE TABLE IF NOT EXISTS embedding_cache (
                hash TEXT PRIMARY KEY,
                vector TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        _CACHE_TABLE_READY = True


def _available() -> bool:
    if not os.getenv("GOOGLE_API_KEY"):
        return False
    return time.time() >= _COOLDOWN_UNTIL


def _record_api_failure(err: Exception):
    global _FAIL_COUNT, _COOLDOWN_UNTIL
    _FAIL_COUNT += 1
    if _FAIL_COUNT >= _FAIL_LIMIT:
        _COOLDOWN_UNTIL = time.time() + _COOLDOWN_SECONDS
        _FAIL_COUNT = 0
        logger.warning(f"[EMBED] API failing ({err}); cooling down for {_COOLDOWN_SECONDS}s")


def _embed_sync(text: str) -> Optional[List[float]]:
    """Blocking Gemini embedding call; run via executor."""
    import google.generativeai as genai
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    result = genai.embed_content(model=_EMBED_MODEL, content=text[:8000])
    return result.get("embedding") if isinstance(result, dict) else getattr(result, "embedding", None)


async def embed(text: str) -> Optional[List[float]]:
    """Return the embedding vector for text, or None if unavailable."""
    global _FAIL_COUNT
    if not text or not text.strip() or not _available():
        return None

    key = _hash(text.strip().lower())
    if key in _hot_cache:
        return _hot_cache[key]

    try:
        await _ensure_cache_table()
        from app.core.database import DatabaseManager
        row = await DatabaseManager.query(
            "SELECT vector FROM embedding_cache WHERE hash = ?", (key,), fetchone=True
        )
        if row and row["vector"]:
            vec = json.loads(row["vector"])
            _remember_hot(key, vec)
            return vec
    except Exception as e:
        logger.debug(f"[EMBED] Cache read failed (non-fatal): {e}")

    try:
        loop = asyncio.get_running_loop()
        vec = await asyncio.wait_for(
            loop.run_in_executor(None, _embed_sync, text), timeout=10.0
        )
        if not vec:
            return None
        _FAIL_COUNT = 0
        _remember_hot(key, vec)
        try:
            from app.core.database import DatabaseManager
            await DatabaseManager.query(
                "INSERT OR REPLACE INTO embedding_cache (hash, vector) VALUES (?, ?)",
                (key, json.dumps(vec)),
            )
        except Exception as e:
            logger.debug(f"[EMBED] Cache write failed (non-fatal): {e}")
        return vec
    except Exception as e:
        _record_api_failure(e)
        logger.debug(f"[EMBED] Embedding failed: {e}")
        return None


def _remember_hot(key: str, vec: List[float]):
    if len(_hot_cache) >= _HOT_CACHE_MAX:
        _hot_cache.pop(next(iter(_hot_cache)))
    _hot_cache[key] = vec


def cosine(a: List[float], b: List[float]) -> float:
    """Cosine similarity in pure Python — no numpy (saves ~30MB RAM)."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


async def semantic_similarity(text_a: str, text_b: str) -> Optional[float]:
    """Cosine similarity of two texts, or None when embeddings unavailable."""
    va, vb = await asyncio.gather(embed(text_a), embed(text_b))
    if va is None or vb is None:
        return None
    return cosine(va, vb)


async def rank_by_similarity(query: str, candidates: List[dict], text_key: str = "content", top_k: int = 3) -> Optional[List[dict]]:
    """Rank candidate dicts by similarity of candidate[text_key] to query.

    Candidates may carry a pre-computed vector under '_embedding' (list) to
    avoid re-embedding. Returns top_k candidates, or None when unavailable.
    """
    qv = await embed(query)
    if qv is None:
        return None
    scored = []
    for cand in candidates:
        vec = cand.get("_embedding")
        if vec is None:
            vec = await embed(cand.get(text_key, "") or "")
        if vec is None:
            continue
        scored.append((cosine(qv, vec), cand))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [c for (s, c) in scored[:top_k] if s > 0.3]
