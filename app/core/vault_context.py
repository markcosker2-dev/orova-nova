"""Read-only vault context injector (ADR-0004 A1).

Loads a small, capped set of curated markdown notes from vault/ into the
planner's system prompt — the read half of the bidirectional Obsidian brain.
Runs locally only: on Render, VAULT_DIR won't exist, so this degrades to ""
with no error (same fail-open posture as everything else in planner.py).
"""
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

VAULT_DIR = Path(os.getenv("VAULT_DIR", "vault"))
MAX_CHARS_PER_NOTE = 2000
MAX_TOTAL_CHARS = 6000  # hard cap: this is a supplement, not the context
ALWAYS_READ = [
    "10-brain/active-context.md",
    "10-brain/strategy-snapshot.md",
]


def get_vault_context(niche: str = "", client_id: int = 0) -> str:
    """Return a capped markdown digest for system-prompt injection.

    Sync + pure I/O — call from async code via asyncio.to_thread. Never
    raises: any unreadable file is skipped, a missing vault returns "".
    """
    try:
        if not VAULT_DIR.exists():
            return ""  # Render: no local vault — fail open, silent
        chunks = []
        for rel in ALWAYS_READ:
            path = VAULT_DIR / rel
            if path.exists():
                text = path.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_PER_NOTE]
                chunks.append(f"--- {rel} ---\n{text}")
        if niche:
            # niche-scoped skill note, e.g. vault/50-skills/find_leads.md
            skill_note = VAULT_DIR / "50-skills" / f"{niche}.md"
            if skill_note.exists():
                chunks.append(skill_note.read_text(encoding="utf-8", errors="ignore")[:MAX_CHARS_PER_NOTE])
        return "\n\n".join(chunks)[:MAX_TOTAL_CHARS]
    except Exception as e:
        logger.debug(f"[VAULT_CONTEXT] read skipped: {e}")
        return ""
