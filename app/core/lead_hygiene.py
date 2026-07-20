"""Lead hygiene sweep (Phase 0 data integrity, 2026-07-20).

The storage gate in _lead_repo.save_lead stops new junk, but junk already
lives in the Drive snapshot and the Google Sheet — both of which are restored
into a fresh DB on every deploy. This sweep runs at every boot, re-validates
every stored lead against the same gate, and:

- quarantines unfixable rows (no/fake business name, fixture data) by setting
  status='Invalid' — Mission Control's /api/leads excludes them;
- empties unverifiable email/phone/url fields on rows that are otherwise real
  (placeholders must never be displayed);
- recomputes the ICP score for not-yet-contacted rows, so a fabricated
  payload score (the live fixture arrived pre-scored 85) cannot persist.

Idempotent and fail-open: a hygiene failure must never block boot.
"""
import logging

from app.core.database import DatabaseManager

logger = logging.getLogger(__name__)

# Statuses that mean outreach already happened — keep their score history.
_CONTACTED_STATUSES = {"email sent", "contacted", "replied", "meeting booked"}


async def quarantine_invalid_leads() -> dict:
    from app.skills.lead_validator import validate_lead_for_storage

    summary = {"checked": 0, "quarantined": 0, "cleaned": 0, "rescored": 0}
    try:
        rows = await DatabaseManager.query(
            "SELECT * FROM leads WHERE COALESCE(status,'') != 'Invalid'",
            (), fetchall=True,
        )
    except Exception as e:
        logger.warning(f"[HYGIENE] sweep query failed (non-fatal): {e}")
        return summary

    for row in rows or []:
        lead = dict(row)
        summary["checked"] += 1
        lead_id = lead.get("id")
        try:
            gate = validate_lead_for_storage(lead)
            if not gate["ok"]:
                reason = "; ".join(gate["reasons"])[:300]
                await DatabaseManager.query(
                    """UPDATE leads SET status='Invalid',
                       notes = TRIM(COALESCE(notes,'') || ' | [HYGIENE] ' || ?, ' |'),
                       updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
                    (reason, lead_id),
                )
                summary["quarantined"] += 1
                logger.warning(f"[HYGIENE] quarantined lead {lead_id}: {reason}")
                continue

            cleaned = gate["lead"]
            field_changes = {
                f: cleaned.get(f, "") for f in ("owner", "email", "phone", "url", "website")
                if (cleaned.get(f) or "") != (lead.get(f) or "")
            }
            rescore = ((lead.get("status") or "").lower() not in _CONTACTED_STATUSES
                       and cleaned.get("score") != lead.get("score"))
            if not field_changes and not rescore:
                continue

            sets, params = [], []
            for f, v in field_changes.items():
                sets.append(f"{f} = ?")
                params.append(v)
            if rescore:
                sets.append("score = ?")
                params.append(cleaned.get("score", 0))
                summary["rescored"] += 1
            if gate["reasons"]:
                sets.append("notes = TRIM(COALESCE(notes,'') || ' | [HYGIENE] ' || ?, ' |')")
                params.append("; ".join(gate["reasons"])[:300])
            sets.append("updated_at = CURRENT_TIMESTAMP")
            params.append(lead_id)
            await DatabaseManager.query(
                f"UPDATE leads SET {', '.join(sets)} WHERE id = ?", tuple(params))
            if field_changes:
                summary["cleaned"] += 1
                logger.info(f"[HYGIENE] cleaned lead {lead_id} "
                            f"({lead.get('business','?')}): {'; '.join(gate['reasons'])}")
        except Exception as e:
            logger.warning(f"[HYGIENE] lead {lead_id} sweep failed (non-fatal): {e}")

    if summary["quarantined"] or summary["cleaned"] or summary["rescored"]:
        logger.warning(f"[HYGIENE] sweep result: {summary}")
    else:
        logger.info(f"[HYGIENE] sweep clean: {summary['checked']} leads OK")
    return summary
