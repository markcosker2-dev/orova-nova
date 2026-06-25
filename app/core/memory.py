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
        """Store the condensed fact fragment in the SQLite Wiki and FAISS index."""
        fragment_id = str(uuid.uuid4())
        await DatabaseManager.query(
            "INSERT INTO memories (id, category, content, client_id) VALUES (?, ?, ?, ?)",
            (fragment_id, "distilled_fact", content, int(client_id))
        )
        
        # Update FAISS Index
        if self.index and self.encoder:
            try:
                import numpy as np
                embedding = self.encoder.encode([content])
                self.index.add(np.array(embedding).astype('float32'))
                # In a full production setup, we would save the FAISS index to disk here.
            except Exception as e:
                logger.error(f"[MEMORY] FAISS embedding failed: {e}")

    async def retrieve_context(self, current_goal: str, client_id: int = 0) -> str:
        """Retrieve semantically relevant facts from the Wiki."""
        if self.index and self.encoder and self.index.ntotal > 0:
            try:
                import numpy as np
                # Semantic Search
                query_vector = self.encoder.encode([current_goal])
                distances, indices = self.index.search(np.array(query_vector).astype('float32'), k=3)
                
                # Fetch from SQLite using offset/rowid (simplified FAISS ID mapping)
                # Production FAISS requires IndexIDMap, here we fallback to full fetch for simplicity
                pass
            except Exception:
                pass
                
        # Fallback to recent SQLite memories
        rows = await DatabaseManager.query(
            "SELECT content FROM memories WHERE client_id = ? ORDER BY created_at DESC LIMIT 3", 
            (int(client_id),), fetchall=True
        )
        
        if not rows:
            return ""
            
        facts = "\n".join([f"- {r['content']}" for r in rows])
        return f"\n\n[RELEVANT LONG-TERM FACTS]:\n{facts}\n"
