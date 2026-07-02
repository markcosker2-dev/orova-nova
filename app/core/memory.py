import logging
import json
import uuid
from datetime import datetime
from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

class MemoryDistiller:
    """
    LLM Wiki Pattern: Condenses large conversation histories into Fact Fragments
    and retrieves them via semantic search to maintain an O(1) context window.
    """
    def __init__(self, ai_client):
        self.ai = ai_client
        self.dimension = 384  # BGE-Micro dimension
        self.index = None
        self.encoder = None
        self._initialize_faiss()

    def _initialize_faiss(self):
        # Disabled for Render Free Tier to save 512MB RAM
        self.index = None
        self.encoder = None
        logger.info("[MEMORY] Using lightweight SQLite Wiki (Semantic RAG disabled).")

    async def distill(self, history: list, client_id: int = 0) -> list:
        """
        Check if history exceeds the 5-turn ceiling. If so, distill the oldest turns.
        Returns the compacted history (Working Memory).
        """
        if len(history) <= 5:
            return history

        logger.info("[MEMORY] Context Bloat detected. Triggering Distiller...")
        
        # Keep the system prompt and the last 3 turns
        working_memory = [history[0]] + history[-3:]
        
        # Distill the middle turns
        turns_to_distill = history[1:-3]
        if not turns_to_distill:
            return working_memory

        distillation_prompt = (
            "Extract the concrete facts, decisions, and outcomes from this conversation log. "
            "Ignore greetings and filler. Output a single paragraph summary of key facts."
            "\n\nLOG:\n" + "\n".join([f"{m.get('role')}: {m.get('content')}" for m in turns_to_distill])
        )

        try:
            # Use the cheapest/fastest model for distillation
            response = await self.ai.quick(distillation_prompt)
            fact_fragment = response
            
            # Store the fact fragment
            await self._store_fragment(fact_fragment, client_id)
            logger.info("[MEMORY] Distillation complete. Fact fragment stored.")
            
            # Free memory
            import gc
            gc.collect()

        except Exception as e:
            logger.error(f"[MEMORY] Distillation failed: {e}")

        return working_memory

    async def _store_fragment(self, content: str, client_id: int):
        """Store the condensed fact fragment with its embedding (API-based,
        zero local RAM — see app/core/embeddings.py)."""
        fragment_id = str(uuid.uuid4())
        embedding_json = None
        try:
            from app.core.embeddings import embed
            vec = await embed(content)
            if vec:
                embedding_json = json.dumps(vec)
        except Exception as e:
            logger.debug(f"[MEMORY] Embedding skipped: {e}")

        await DatabaseManager.query(
            "INSERT INTO memories (id, category, content, client_id, embedding) VALUES (?, ?, ?, ?, ?)",
            (fragment_id, "distilled_fact", content, int(client_id), embedding_json)
        )

    async def retrieve_context(self, current_goal: str, client_id: int = 0) -> str:
        """Retrieve semantically relevant facts from the Wiki.

        Semantic path: rank stored fragments by embedding similarity to the
        goal. Falls back to most-recent when embeddings are unavailable.
        """
        rows = await DatabaseManager.query(
            "SELECT content, embedding FROM memories WHERE client_id = ? ORDER BY created_at DESC LIMIT 100",
            (int(client_id),), fetchall=True
        )
        if not rows:
            return ""

        selected = None
        try:
            from app.core.embeddings import rank_by_similarity
            candidates = []
            for r in rows:
                cand = {"content": r["content"]}
                if r["embedding"]:
                    try:
                        cand["_embedding"] = json.loads(r["embedding"])
                    except Exception:
                        pass
                # Only rank fragments that already carry a vector — embedding
                # 100 legacy rows on-the-fly would blow the request budget.
                if "_embedding" in cand:
                    candidates.append(cand)
            if candidates:
                ranked = await rank_by_similarity(current_goal, candidates, top_k=3)
                if ranked:
                    selected = [c["content"] for c in ranked]
                    logger.info(f"[MEMORY] Semantic recall: {len(selected)} relevant fact(s)")
        except Exception as e:
            logger.debug(f"[MEMORY] Semantic recall unavailable: {e}")

        if not selected:
            selected = [r["content"] for r in rows[:3]]

        facts = "\n".join(f"- {c}" for c in selected)
        return f"\n\n[RELEVANT LONG-TERM FACTS]:\n{facts}\n"
