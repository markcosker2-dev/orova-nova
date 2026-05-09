import os
import asyncio
import logging
from mem0 import Memory

logger = logging.getLogger(__name__)

class MegaMemory:
    """
    Hermes Evolution: Integrated Mem0 for personalized, entity-based long-term memory.
    Replaces the basic fact-distiller with a multi-layered knowledge graph.
    """
    def __init__(self):
        # [P1] FIXED: Use openai_compatible provider to target OpenRouter correctly
        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": os.path.join(
                        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 
                        "app", "data", "mem0_db"
                    ),
                }
            },
            "llm": {
                "provider": "openai_compatible",
                "config": {
                    "api_key": os.getenv("OPENROUTER_API_KEY"),
                    "model": "google/gemini-2.0-flash-lite-preview-02-05",
                    "openai_base_url": "https://openrouter.ai/api/v1",
                }
            },
            "embedder": {
                "provider": "openai_compatible",
                "config": {
                    "api_key": os.getenv("OPENROUTER_API_KEY"),
                    "model": "openai/text-embedding-3-small",
                    "openai_base_url": "https://openrouter.ai/api/v1",
                }
            }
        }
        try:
            self.memory = Memory.from_config(config)
            logger.info("🧠 Mem0 Mega-Memory Online (Hermes Evolution Active)")
        except Exception as e:
            logger.error(f"💥 Mem0 Initialization failed: {e}")
            self.memory = None

    async def add(self, data: str, user_id: str = "nova", metadata: dict = None):
        """Add information to the long-term memory."""
        if not self.memory: return
        # [P1] FIXED: Offload blocking sync call to thread pool
        loop = asyncio.get_event_loop()
        try:
            await loop.run_in_executor(
                None, lambda: self.memory.add(data, user_id=user_id, metadata=metadata)
            )
        except Exception as e:
            logger.error(f"💥 Mem0 Add failed: {e}")

    async def retrieve(self, query: str, user_id: str = "nova") -> str:
        """Retrieve relevant context for a query."""
        if not self.memory: return ""
        # [P1] FIXED: Offload blocking sync call to thread pool
        loop = asyncio.get_event_loop()
        try:
            # Use similarity threshold to prevent context pollution
            results = await loop.run_in_executor(
                None, lambda: self.memory.search(query, user_id=user_id, limit=3)
            )
            if not results: return ""
            
            context = "\n[RECALLED MEMORIES]:\n"
            for res in results:
                # Only surface memories with high similarity
                score = res.get("score", 1.0)
                if score > 0.7: 
                    context += f"- {res['memory']}\n"
            return context if context != "\n[RECALLED MEMORIES]:\n" else ""
        except Exception as e:
            logger.error(f"💥 Mem0 Search failed: {e}")
            return ""

    async def prune(self, user_id: str = "nova", keep_last: int = 200):
        """Prune stale memories to prevent context bloat."""
        if not self.memory: return
        loop = asyncio.get_event_loop()
        try:
            all_mem = await loop.run_in_executor(
                None, lambda: self.memory.get_all(user_id=user_id)
            )
            if len(all_mem) > keep_last:
                to_delete = all_mem[:-keep_last]
                for m in to_delete:
                    await loop.run_in_executor(
                        None, lambda mid=m["id"]: self.memory.delete(mid)
                    )
                logger.info(f"🗑️ Pruned {len(to_delete)} stale memories for {user_id}")
        except Exception as e:
            logger.error(f"💥 Mem0 Prune failed: {e}")

# Singleton instance
mega_memory = MegaMemory()
