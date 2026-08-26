"""The chat log - what was said, and what it cost to say it.

This is the *other* log. `core/hermes/logs.py` is what the machine did; this is
what was said. They were both called "log" and that ambiguity is the reason
this file and that one were written on the same day.

Isabella stores no message content - that is a rule in CLAUDE.md and DATA.md and
it is not being bent here. The transcript lives in Hermes' `state.db`; this reads
it back out and adds the three things a transcript alone does not tell you:

- **how long she took.** The wait is the assistant message's timestamp minus the
  user message that prompted it. She reasons before she speaks - 8s for a simple
  question, up to 90s for an identity one - and a log that does not print the
  wait makes the slowest thing in the system invisible.
- **what she was doing in the gap.** qwen3 reasons into a separate field, so a
  turn that looks like four words of output is usually thousands of characters of
  deliberation. The count is shown; the reasoning itself is not, because it is
  not what she said.
- **what it cost.** Tokens per session, out of Hermes' own counters.

One failure gets named rather than shown as a blank turn: reasoning counts
against `max_tokens`, and starved, content comes back empty with
`finish_reason: length`. CLAUDE.md calls that a real error, so this calls it one.
"""

from core.config import Settings
from core.hermes import state

WHO = {"user": "owen", "assistant": "isabella"}


def _note(message: state.Message, seconds: float | None) -> str:
    """One line about the turn itself, or empty when there is nothing to say."""
    if message.role != "assistant":
        return ""
    if message.finish_reason == "length" and not message.content:
        return (
            "Empty - the reasoning used the whole token budget and nothing was left "
            "to answer with. Not a transport failure; raise MAX_TOKENS."
        )
    parts: list[str] = []
    if message.tool_name:
        parts.append(f"called {message.tool_name}")
    if message.reasoned:
        parts.append(f"reasoned {message.reasoning_chars:,} chars")
    if seconds is not None and seconds >= 1:
        parts.append(f"{seconds:.0f}s")
    if message.finish_reason and message.finish_reason != "stop":
        parts.append(f"finish: {message.finish_reason}")
    return " · ".join(parts)


def read(cfg: Settings, limit: int = 12) -> dict:
    """Her recent conversations, newest session first, oldest turn first within.

    Never raises; an unreadable database comes back as `available: false` with
    the reason, and the view draws the absence.
    """
    sessions, detail = state.read_sessions(cfg, limit=limit)
    if not sessions:
        return {"available": False, "detail": detail or "Nothing has been said yet.", "sessions": []}

    ids = [s.id for s in sessions]
    messages, message_detail = state.read_messages(cfg, session_ids=ids, limit=600)

    grouped: dict[str, list[state.Message]] = {sid: [] for sid in ids}
    for message in messages:
        if message.role in WHO:
            grouped[message.session_id].append(message)

    out = []
    for session in sessions:
        turns = []
        asked_at: float | None = None
        for message in grouped[session.id]:
            if message.role == "user":
                asked_at = message.timestamp
                seconds = None
            else:
                seconds = message.timestamp - asked_at if asked_at else None
                asked_at = None
            turns.append({
                "id": message.id,
                "who": WHO[message.role],
                "text": message.content,
                "at": state.stamp(message.timestamp),
                "seconds": round(seconds, 1) if seconds is not None else None,
                "tokens": message.token_count,
                "reasoned": message.reasoned,
                "reasoning_chars": message.reasoning_chars,
                "finish_reason": message.finish_reason,
                "tool": message.tool_name,
                "note": _note(message, seconds),
            })
        out.append({**state.session_stamp(session), "turns": turns})

    return {
        "available": True,
        "detail": message_detail,
        "sessions": out,
    }
