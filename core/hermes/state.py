"""Reading Hermes' own state, read-only.

**This is the second module that couples to Hermes' internals, and it is here
for the same reason `client.py` is.** `client.py` owns the HTTP surface; this
owns the two things Hermes keeps on disk that Isabella needs to *show* and
cannot ask for over HTTP:

- `HERMES_HOME/state.db` - sessions and messages. Isabella stores no message
  content (CLAUDE.md, DATA.md); the transcript lives here, in Hermes' database,
  and the only way to put a chat log on screen is to read it back out.
- `HERMES_HOME/memories/*.md` - the built-in curated memory store, `§`-delimited
  entries in `MEMORY.md` and `USER.md`.

Two rules, both load-bearing:

1. **Read-only, and enforced, not merely intended.** The connection is opened
   `mode=ro` through a URI, so a stray write is an error from SQLite rather than
   a corrupted agent. Nothing in this module has an INSERT in it, and nothing
   should acquire one - writing to Hermes' database behind Hermes' back is how
   two systems end up disagreeing about what was said.
2. **It degrades, it does not raise.** The gateway holds the database in WAL
   mode and may be mid-write, the file may not exist yet on a fresh instance,
   and the schema is upstream's to change. Every reader here answers with
   `available: False` and a sentence saying which, so the view draws the absence
   instead of a stack trace.

The schema is Hermes', which means it can move under us. Everything read here is
named explicitly rather than `SELECT *`, so a column that disappears fails on one
query with a legible message instead of silently shifting a tuple index.
"""

import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from core.config import Settings


@dataclass(frozen=True, slots=True)
class Session:
    id: str
    source: str
    title: str
    model: str | None
    started_at: float
    last_activity_at: float | None
    message_count: int
    tool_call_count: int
    api_call_count: int
    input_tokens: int
    output_tokens: int
    reasoning_tokens: int


@dataclass(frozen=True, slots=True)
class Message:
    id: int
    session_id: str
    role: str
    content: str
    timestamp: float
    token_count: int | None
    finish_reason: str | None
    tool_name: str | None
    # True when the model reasoned before answering. The text of the reasoning
    # is deliberately NOT carried: it is long, it is not what she said, and a
    # chat log that prints it is a chat log nobody reads.
    reasoned: bool
    reasoning_chars: int


@dataclass(frozen=True, slots=True)
class Memory:
    """One `§`-delimited entry out of Hermes' curated memory store."""

    id: str
    title: str
    body: str
    store: str  # "memory" (her notes) | "user" (what she knows about Owen)
    # 0-10, and only where the entry actually records one. There is no
    # importance column in Hermes' format, so this is parsed from an
    # `[importance: N]` tag written into the entry itself. Absent is `None`
    # and stays `None` - a default of 5 would be Isabella inventing a
    # judgement about Owen's life that nobody made.
    importance: int | None
    links: list[str] = field(default_factory=list)


def stamp(epoch: float | None) -> str | None:
    if not epoch:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).astimezone().isoformat(timespec="seconds")


def _connect(path: Path) -> sqlite3.Connection:
    """Open Hermes' database read-only.

    `mode=ro` is the point. The gateway is usually running and writing; this
    process must never be the one that touches it.
    """
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
    connection.row_factory = sqlite3.Row
    return connection


# ----------------------------------------------------------------------
# Sessions and messages
# ----------------------------------------------------------------------

_SESSION_COLUMNS = """
    id, source, title, model, started_at, last_activity_at,
    message_count, tool_call_count, api_call_count,
    input_tokens, output_tokens, reasoning_tokens
"""

_MESSAGE_COLUMNS = """
    id, session_id, role, content, timestamp, token_count,
    finish_reason, tool_name, reasoning, reasoning_content
"""


def _session(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        source=row["source"] or "unknown",
        # Hermes derives a title from the first message. A session that has not
        # been titled yet gets its id rather than a blank - an untitled row in
        # a list of titles reads as a bug.
        title=(row["title"] or "").strip() or row["id"],
        model=row["model"],
        started_at=row["started_at"] or 0.0,
        last_activity_at=row["last_activity_at"],
        message_count=row["message_count"] or 0,
        tool_call_count=row["tool_call_count"] or 0,
        api_call_count=row["api_call_count"] or 0,
        input_tokens=row["input_tokens"] or 0,
        output_tokens=row["output_tokens"] or 0,
        reasoning_tokens=row["reasoning_tokens"] or 0,
    )


def _message(row: sqlite3.Row) -> Message:
    reasoning = (row["reasoning"] or row["reasoning_content"] or "") or ""
    return Message(
        id=row["id"],
        session_id=row["session_id"],
        role=row["role"] or "unknown",
        content=(row["content"] or "").strip(),
        timestamp=row["timestamp"] or 0.0,
        token_count=row["token_count"],
        finish_reason=row["finish_reason"],
        tool_name=row["tool_name"],
        reasoned=bool(reasoning.strip()),
        reasoning_chars=len(reasoning),
    )


def read_sessions(cfg: Settings, limit: int = 40) -> tuple[list[Session], str]:
    """Her conversations, newest first. Never raises."""
    path = cfg.hermes_home / "state.db"
    if not path.exists():
        return [], f"No Hermes state at {path} - she has not been talked to on this instance yet."
    try:
        with _connect(path) as db:
            rows = db.execute(
                f"SELECT {_SESSION_COLUMNS} FROM sessions "
                "WHERE hidden = 0 "
                "ORDER BY COALESCE(last_activity_at, started_at) DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [_session(r) for r in rows], ""
    except sqlite3.Error as exc:
        return [], f"Could not read her state.db: {exc}"


def read_messages(
    cfg: Settings, *, session_ids: list[str] | None = None, limit: int = 200
) -> tuple[list[Message], str]:
    """Messages, oldest first within the window. Never raises.

    `active = 1` excludes what compression has folded away: those messages are
    no longer in her context, and printing them beside the live ones would say
    she is holding a conversation she has actually compacted.
    """
    path = cfg.hermes_home / "state.db"
    if not path.exists():
        return [], f"No Hermes state at {path}."
    try:
        with _connect(path) as db:
            if session_ids is None:
                rows = db.execute(
                    f"SELECT {_MESSAGE_COLUMNS} FROM messages "
                    "WHERE active = 1 ORDER BY timestamp DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            elif not session_ids:
                return [], ""
            else:
                marks = ",".join("?" * len(session_ids))
                rows = db.execute(
                    f"SELECT {_MESSAGE_COLUMNS} FROM messages "
                    f"WHERE active = 1 AND session_id IN ({marks}) "
                    "ORDER BY timestamp DESC LIMIT ?",
                    (*session_ids, limit),
                ).fetchall()
        return sorted((_message(r) for r in rows), key=lambda m: m.timestamp), ""
    except sqlite3.Error as exc:
        return [], f"Could not read her state.db: {exc}"


def session_stamp(session: Session) -> dict:
    """The parts of a session a view prints, with epochs turned into stamps."""
    return {
        "id": session.id,
        "source": session.source,
        "title": session.title,
        "model": session.model,
        "started_at": stamp(session.started_at),
        "last_activity_at": stamp(session.last_activity_at),
        "message_count": session.message_count,
        "tool_call_count": session.tool_call_count,
        "api_call_count": session.api_call_count,
        "tokens": {
            "input": session.input_tokens,
            "output": session.output_tokens,
            "reasoning": session.reasoning_tokens,
        },
    }


# ----------------------------------------------------------------------
# The curated memory store
# ----------------------------------------------------------------------

ENTRY_DELIMITER = "\n§\n"

# `[importance: 8]` anywhere in an entry. Hermes' format has no such field -
# this is a convention Isabella READS and never writes, so an entry without it
# is not wrong, it is simply unrated.
_IMPORTANCE = re.compile(r"\[\s*importance\s*[:=]\s*(10|[0-9])\s*\]", re.IGNORECASE)
_LINK = re.compile(r"\[\[([^\]]+)\]\]")

_STORES = {"MEMORY.md": "memory", "USER.md": "user"}


def _slug(text: str, n: int) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "entry"
    return f"{base}-{n}"


def read_memories(cfg: Settings) -> tuple[list[Memory], bool, str]:
    """Her curated memories, out of Hermes' own store.

    Returns `(memories, enabled, detail)`. `enabled` is whether Hermes is
    configured to write them at all - an empty store with memory switched off
    is a *configuration* fact, not an empty mind, and the view has to be able
    to say which of the two it is looking at.
    """
    home = cfg.hermes_home
    enabled = _memory_enabled(home)
    directory = home / "memories"

    found: list[Memory] = []
    for filename, store in _STORES.items():
        path = directory / filename
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return found, enabled, f"Could not read {path.name}: {exc}"
        for n, chunk in enumerate(text.split(ENTRY_DELIMITER)):
            entry = chunk.strip()
            if not entry or entry.startswith("#"):
                continue
            rated = _IMPORTANCE.search(entry)
            clean = _IMPORTANCE.sub("", entry).strip()
            first = clean.splitlines()[0].strip() if clean.splitlines() else clean
            found.append(
                Memory(
                    id=f"memory:{store}:{_slug(first, n)}",
                    title=first[:80],
                    body=clean,
                    store=store,
                    importance=int(rated.group(1)) if rated else None,
                    links=[m.strip() for m in _LINK.findall(clean)],
                )
            )

    if not found:
        # An empty store and a missing one are the same fact once you know why:
        # nothing writes to it. Say the reason rather than the path - the path
        # is not what anyone needs to know.
        detail = (
            "Her memory store is empty. Hermes' `memory.memory_enabled` is false on "
            "this instance, so nothing writes to it."
            if not enabled
            else "Her memory store is enabled and empty - nothing has been written yet."
        )
        return [], enabled, detail
    return found, enabled, ""


def _memory_enabled(home: Path) -> bool:
    """Whether Hermes will write memories at all.

    Read out of her `config.yaml` rather than assumed. Parsed with a regex and
    not with `yaml`, because this module is on Isabella's import path and adding
    a dependency to read one boolean is the kind of thing CLAUDE.md's
    dependency rule exists to stop.
    """
    try:
        text = (home / "config.yaml").read_text(encoding="utf-8")
    except OSError:
        return False
    match = re.search(r"^\s*memory_enabled\s*:\s*(true|false)\s*$", text, re.IGNORECASE | re.MULTILINE)
    return bool(match) and match.group(1).lower() == "true"


def scan_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
