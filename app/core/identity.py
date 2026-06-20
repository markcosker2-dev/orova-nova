"""Centralised identity-probe detection (CQ-02).

Both ``planner.py`` and ``router.py`` previously maintained their own
copy of the identity-probe regex and deflection message.  This module
is the single source of truth.
"""

import re
import unicodedata

# ── Identity-probe regex ────────────────────────────────────
# Matches common phrasings users employ to probe the AI's identity.
IDENTITY_PROBE_RE = re.compile(
    r"\b(what (ai|model|llm|system) are you"
    r"|are you (chatgpt|gpt|gemini|claude|openai|anthropic|google)"
    r"|who (made|built|created|trained|developed) you"
    r"|what (powers|runs|underlies) you"
    r"|what (are|is) (your|the) (model|ai|engine)"
    r"|which (company|team|lab) (built|made|created) you"
    r"|powered by|underlying model)\b",
    re.IGNORECASE,
)

IDENTITY_DEFLECT = "I'm Nova, OROVA's AI. Let me know what you need."


def normalise_for_probe(text: str) -> str:
    """Normalise text before identity-probe matching.

    Strips zero-width characters, removes separator chars inside words,
    and collapses whitespace so that obfuscated probes still match.
    """
    text = unicodedata.normalize("NFKD", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", text)
    text = re.sub(r"(?<=\w)[.\-_](?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()
