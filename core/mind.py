"""The graph the brain draws - what she holds, as nodes and the lines between.

**Read the honesty rule before the code.** Selene's HUD puts a memory graph at
its centre and Isabella does not have one: there is no memory table in her
schema and there must not be one (CLAUDE.md, prime directive), and Hermes'
gateway exposes no memory endpoint. So this graph is built out of the three
things that are *actually on disk* in `HERMES_HOME`, and it is named for what
they are rather than dressed up as recall:

| kind      | what it is                                   | where it comes from |
|-----------|----------------------------------------------|---------------------|
| `memory`  | a curated entry she has kept                 | `memories/*.md`     |
| `session` | one conversation                             | `state.db` sessions |
| `message` | one thing said in it                         | `state.db` messages |

Three rules this file exists to keep:

1. **Nothing is invented.** A memory's importance is 0-10 *where the entry
   records one* and `None` where it does not; `None` travels all the way to the
   renderer, which draws it hollow. A default of 5 would be Isabella asserting
   a judgement about Owen's life that nobody made - the same rule `core/body.py`
   follows for an unlogged weight.
2. **Size is a real quantity.** A node's radius comes from something countable:
   a memory's importance, a session's message count, a message's tokens. A
   circle whose size means nothing is refused, however good it looks.
3. **Violet is what is LIVE.** `recalled` is the session being spoken in right
   now and the messages in it - that is genuinely the context of her next turn.
   Nothing else is lit, ever.

The payload is shaped for the renderer ported from Selene (`web/src/lib/graph.ts`)
and keeps its vocabulary where the meaning survived: `nodes`, `recalled`, `hop`,
`confidence`. One deliberate divergence - **`relations` are ids, not titles.**
Selene resolved edges by title because a memory's title is its key; sessions
here are titled from their first message and two of them really are both called
"hello", so a title-keyed edge would join two unrelated conversations.
"""

import time

from core.config import Settings
from core.hermes import state

# How many nodes are worth drawing. Mirrors MAX_NODES in web/src/lib/graph.ts;
# past roughly this many the volume is a smear. The client cuts too - this cut
# is here so the response stays small.
MAX_NODES = 72

# How much of a message is carried for the hover readout. The whole thing lives
# in Hermes' database; this is an opening, not a copy.
EXCERPT = 160


def _excerpt(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= EXCERPT else flat[: EXCERPT - 1].rstrip() + "…"


def snapshot(cfg: Settings, live_session: str | None = None) -> dict:
    """Everything she holds, as a graph. Never raises - see core/hermes/state.py."""
    started = time.perf_counter()

    sessions, session_detail = state.read_sessions(cfg, limit=40)
    memories, memory_enabled, memory_detail = state.read_memories(cfg)
    messages, message_detail = state.read_messages(cfg, limit=240)

    nodes: list[dict] = []

    # ── memories ────────────────────────────────────────────────────────
    # The frame. In the layout these take the stem and the deep structures,
    # which is where a brain puts what everything else hangs off.
    by_title = {m.title.lower(): m.id for m in memories}
    for memory in memories:
        rated = memory.importance is not None
        nodes.append({
            "id": memory.id,
            "kind": "memory",
            "title": memory.title,
            "excerpt": _excerpt(memory.body),
            "at": None,
            "importance": memory.importance,
            # An unrated memory is one she is holding without a judgement
            # attached. The renderer draws low confidence hollow, which is the
            # right reading: present, weight unknown.
            "confidence": 1.0 if rated else 0.4,
            "size": (memory.importance or 0) / 10,
            "measure": f"{memory.importance}/10" if rated else "unrated",
            "source": memory.store,
            "relations": [by_title[link.lower()] for link in memory.links if link.lower() in by_title],
        })

    # ── sessions ────────────────────────────────────────────────────────
    # Spread over the cortex, one place each, so the same conversation is
    # found in roughly the same spot between visits.
    busiest = max((s.message_count for s in sessions), default=1) or 1
    for session in sessions:
        nodes.append({
            "id": f"session:{session.id}",
            "kind": "session",
            "title": session.title,
            "excerpt": f"{session.source} · {session.message_count} messages · "
                       f"{session.input_tokens + session.output_tokens} tokens",
            "at": state.session_stamp(session)["last_activity_at"],
            "importance": None,
            "confidence": 1.0,
            "size": min(1.0, session.message_count / busiest),
            "measure": f"{session.message_count} msg",
            "source": session.source,
            "relations": [],
        })

    # ── messages ────────────────────────────────────────────────────────
    # Each sits on the cortex beside the session it belongs to, and the edge
    # says so. Tool results are not drawn: they are Hermes talking to itself.
    drawn_sessions = {f"session:{s.id}" for s in sessions}
    heaviest = max((m.token_count or 0 for m in messages), default=0)
    for message in messages:
        if message.role not in ("user", "assistant"):
            continue
        parent = f"session:{message.session_id}"
        weight = (message.token_count or 0) / heaviest if heaviest else 0.3
        nodes.append({
            "id": f"message:{message.id}",
            "kind": "message",
            "title": _excerpt(message.content)[:48] or f"({message.role}, empty)",
            "excerpt": _excerpt(message.content),
            "at": None,
            "importance": None,
            "confidence": 1.0,
            "size": min(1.0, weight),
            "measure": message.role,
            "source": message.role,
            "relations": [parent] if parent in drawn_sessions else [],
        })

    # ── what is live ────────────────────────────────────────────────────
    # The conversation being spoken in, and what is in it. Hop 0 is the
    # session, hop 1 its messages - the same grading Selene's graph uses, and
    # here it means the same thing: this is the context of her next turn.
    recalled: list[dict] = []
    if live_session:
        node_id = f"session:{live_session}"
        if node_id in drawn_sessions:
            recalled.append({"id": node_id, "hop": 0})
            recalled.extend(
                {"id": f"message:{m.id}", "hop": 1}
                for m in messages
                if m.session_id == live_session and m.role in ("user", "assistant")
            )

    counts = {
        "memory": sum(1 for n in nodes if n["kind"] == "memory"),
        "session": sum(1 for n in nodes if n["kind"] == "session"),
        "message": sum(1 for n in nodes if n["kind"] == "message"),
    }

    # Say what is missing rather than showing a thin graph as if it were the
    # whole of her. An empty memory store with memory switched off is a
    # configuration fact and the view has to be able to print it.
    detail = " ".join(d for d in (session_detail, message_detail, memory_detail) if d)

    return {
        "available": bool(nodes),
        "detail": detail,
        "memory_enabled": memory_enabled,
        "counts": counts,
        "total": len(nodes),
        "max_nodes": MAX_NODES,
        # What is in context, against what she would hold at most. Both real:
        # the budget is the session's own message count, not a target.
        "budget": len(recalled),
        "nodes": nodes,
        "recalled": recalled,
        "scan_ms": state.scan_ms(started),
    }
