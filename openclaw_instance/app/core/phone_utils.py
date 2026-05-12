"""
app/core/phone_utils.py
E.164 phone number normaliser.
Every number hits this before Retell. No exceptions.
"""

import re
import logging
from typing import Optional

logger = logging.getLogger("orova.phone")


def to_e164(raw: str, country_code: str = "1") -> Optional[str]:
    """
    Normalise any US phone number to strict E.164 (+12137774445).
    Returns None if normalisation is impossible.
    A None return means: skip this lead, do NOT call Retell with garbage.

    Handles:
      (213) 777-4445   →  +12137774445
      213-777-4445     →  +12137774445
      2137774445       →  +12137774445
      +12137774445     →  +12137774445 (passthrough)
    """
    if not raw:
        return None

    digits_only = re.sub(r"[^\d+]", "", raw.strip())

    if digits_only.startswith("+"):
        inner = digits_only[1:]
        if len(inner) == 11 and inner.startswith("1"):
            return digits_only
        if len(inner) == 10:
            return "+1" + inner
        logger.warning(f"[PHONE] Unrecognised E.164: {raw!r}")
        return None

    if digits_only.startswith("1") and len(digits_only) == 11:
        return "+" + digits_only
    if len(digits_only) == 10:
        return "+1" + digits_only

    logger.warning(f"[PHONE] Cannot normalise: {raw!r}")
    return None


def is_valid_e164(number: str) -> bool:
    return bool(re.match(r"^\+1[2-9]\d{9}$", number or ""))
