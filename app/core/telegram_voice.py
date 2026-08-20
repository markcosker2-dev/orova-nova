"""How Nova talks to Mark on Telegram.

Every proactive message used to be a form:

    📞 **Call Initiated**

    I am now calling **LEWCO CONTRACTING** (Patrick Lewis).
    Call ID: `abc123`

Bold header, emoji field labels, an internal `[Client 0]`, a call ID no human
will ever use, and "I am now calling" — a sentence no colleague has said out
loud. It reports the EVENT and leaves Mark to work out the meaning.

The rules below are what changed. They are deliberately about content, not
decoration: the old messages did not fail because they lacked warmth, they
failed because they carried nothing Mark could act on.

1. **Say what it means, then what happened.** "Patrick Lewis wants a call" is
   the news; "New Reply — HOT" is a database row.
2. **End with the ask, or say there isn't one.** A worker who reports without
   saying whether you are needed has just moved the triage onto you.
3. **No internal identifiers.** client_id, call IDs, message IDs and tracebacks
   go to the log. Mark cannot act on any of them.
4. **Write like a person.** Contractions. One idea per line. No bold field
   labels, at most one emoji, and only where it helps him scan on a phone.
5. **Silence is a feature.** A composer returning None means "not worth a
   notification". Routine success with nothing to decide should not buzz his
   phone at 3am — he is in the Philippines and the lanes run around the clock.
6. **Never manufacture cheer.** Zero leads is not "Great news!". OROVA has no
   clients and no results, and the voice must never imply otherwise.

Pure string functions: no I/O, no AI call. Nova runs on free-tier Groq/Gemini
that already throws 429s, and a notification that depends on a model is a
notification that silently stops arriving.
"""
from typing import Optional

_NOTHING_NEEDED = "Nothing needed from you."


def _clean(text: Optional[str], limit: int = 200) -> str:
    """Collapse whitespace and trim to something quotable in a chat message."""
    t = " ".join((text or "").split())
    return (t[: limit - 1] + "…") if len(t) > limit else t


def hunt_complete(count: int, query: str, top_business: str = "",
                  top_score: Optional[float] = None,
                  sole_operators: Optional[int] = None) -> Optional[str]:
    """A finished hunt. Silent when it found nothing new.

    Re-finding the same businesses is the normal case now the register is
    walked page by page (#171), and it is not news.
    """
    if count <= 0:
        return None

    lines = [f"Found {count} new lead{'s' if count != 1 else ''} hunting '{query}'."]
    if top_business:
        best = f"Best of them: {top_business}"
        if top_score is not None:
            best += f", scoring {int(top_score)}"
        lines.append(best + ".")
    if sole_operators:
        lines.append(f"{sole_operators} of them are sole operators.")
    lines.append("They're in the sheet. " + _NOTHING_NEEDED)
    return "\n".join(lines)


def hunt_failed(reason: str) -> str:
    """A hunt that broke. Plain language, no traceback."""
    return ("The lead hunt didn't finish.\n"
            f"{_clean(reason, 160)}\n"
            "It'll retry on the next run — no leads were lost.")


def new_reply(sender: str, subject: str, snippet: str, intent: str,
              queued_booking: bool) -> str:
    """Someone replied. The one message that should always interrupt."""
    who = _clean(sender, 80)
    if intent == "HOT":
        head = f"🔥 {who} replied and they're interested."
    elif intent == "WARM":
        head = f"{who} replied — worth a look."
    elif intent == "COLD":
        head = f"{who} replied, but it's a no."
    else:
        head = f"{who} replied."

    subj = _clean(subject, 100)
    subj = subj[3:].lstrip() if subj[:3].lower() == "re:" else subj
    lines = [head, "", f"Re: {subj}",
             f'"{_clean(snippet, 220)}"', ""]
    if intent == "COLD":
        lines.append("I've left it alone. Nothing needed unless you disagree.")
    elif queued_booking:
        lines.append("I've drafted a reply with a booking link — it goes out "
                     "once you approve it.")
    else:
        lines.append("Have a read and reply if it's worth pursuing.")
    return "\n".join(lines)


def call_starting(business: str, contact: str = "") -> str:
    who = f" — {_clean(contact, 60)}" if contact else ""
    return f"Calling {_clean(business, 80)}{who} now. I'll tell you how it goes."


def call_failed(business: str, reason: str) -> str:
    return (f"Couldn't get the call to {_clean(business, 80)} to connect.\n"
            f"{_clean(reason, 160)}\n"
            "They're still in the queue for another try.")


def call_outcome(name: str, phone: str, when: str, summary: str,
                 booked: bool) -> str:
    """The call ended. Only a real yes earns the 🎉."""
    who = _clean(name, 60) or "They"
    if booked:
        head = f"🎉 {who} said yes — they want a call with you."
        tail = (f"They're free {_clean(when, 80)}."
                if when and when.lower() not in ("n/a", "none", "") else
                "They didn't pin a time down.")
        ask = ("Email them to confirm — Nova can't book, so nothing's locked "
               "in yet.")
    else:
        head = f"{who} was interested but didn't commit."
        tail = ""
        ask = "Worth reading the summary before deciding whether to chase."

    lines = [head]
    if tail:
        lines.append(tail)
    if phone:
        lines.append(f"Number: {phone}")
    if summary:
        lines += ["", _clean(summary, 300)]
    lines += ["", ask]
    return "\n".join(lines)


def appointment_booked(name: str, email: str, when: str, title: str = "") -> str:
    who = _clean(name, 60) or "Someone"
    lines = [f"🎉 {who} booked a slot with you.", _clean(when, 80)]
    if email:
        lines.append(email)
    if title:
        lines.append(_clean(title, 100))
    lines += ["", "It's in your calendar."]
    return "\n".join(lines)


def booking_link_sent(name: str, business: str = "", link: str = "") -> str:
    who = _clean(name, 60)
    where = f" at {_clean(business, 60)}" if business else ""
    if link:
        return f"Sent {who}{where} the booking link. {_NOTHING_NEEDED}"
    return (f"Replied to {who}{where}, but there's still no booking link "
            "configured, so I asked them for times instead.\n"
            "Setting CAL_COM_EVENT_SLUG would let me send a link straight away.")


def booking_link_failed(sender: str, attempts: int) -> str:
    return (f"I couldn't get a reply out to {_clean(sender, 80)} after "
            f"{attempts} tries.\n"
            "Worth replying by hand — they're waiting.")


def cold_lead_call(business: str, contact: str, phone: str, days: int) -> str:
    who = f" — {_clean(contact, 60)}" if contact else ""
    return (f"Calling {_clean(business, 80)}{who} — they've gone quiet for "
            f"{days}+ days.\n{phone}")


def cold_escalation_done(called: int, days: int) -> Optional[str]:
    """Silent when nothing was escalated — a quiet lane is not news."""
    if called <= 0:
        return None
    return (f"Called {called} lead{'s' if called != 1 else ''} back after "
            f"{days}+ days of silence. I'll report anything that comes of it.")


def first_touch_call(business: str, contact: str, phone: str) -> str:
    who = _clean(contact, 60) or "no name on file"
    return f"First call to {_clean(business, 80)} ({who}) going out now.\n{phone}"
