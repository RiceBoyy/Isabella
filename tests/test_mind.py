"""The graph the brain draws, and the transcript behind it.

The rule under every test here is the one `core/body.py` already lives by:
**nothing fills a gap.** A memory nobody rated arrives with `importance: None`
and stays that way; a default of 5 would be Isabella inventing a judgement
about Owen's life that nobody made. The other rule is that every radius on
screen is a real count, which is what `size` is tested for.
"""

import sqlite3

import pytest

from core import mind, transcript
from core.config import Settings
from core.hermes import state

# A cut-down copy of the two tables Hermes actually has. Only the columns this
# code names - if upstream drops one of them the test fails here, loudly, which
# is the point of naming them rather than SELECT *.
SCHEMA = """
CREATE TABLE sessions (
  id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT, model TEXT,
  started_at REAL NOT NULL, last_activity_at REAL,
  message_count INTEGER DEFAULT 0, tool_call_count INTEGER DEFAULT 0,
  api_call_count INTEGER DEFAULT 0, input_tokens INTEGER DEFAULT 0,
  output_tokens INTEGER DEFAULT 0, reasoning_tokens INTEGER DEFAULT 0,
  hidden INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, role TEXT NOT NULL,
  content TEXT, timestamp REAL NOT NULL, token_count INTEGER, finish_reason TEXT,
  tool_name TEXT, reasoning TEXT, reasoning_content TEXT,
  active INTEGER NOT NULL DEFAULT 1
);
"""


def home(tmp_path, *, memory: str | None = None, enabled: bool = False, rows: bool = True) -> Settings:
    db = tmp_path / "state.db"
    if rows:
        con = sqlite3.connect(db)
        con.executescript(SCHEMA)
        con.execute(
            "INSERT INTO sessions (id, source, title, model, started_at, last_activity_at,"
            " message_count, api_call_count, input_tokens, output_tokens)"
            " VALUES ('web-1','api_server','who are you?','qwen3:4b-16k',1000,1100,2,1,1800,900)"
        )
        con.execute(
            "INSERT INTO sessions (id, source, title, started_at, message_count)"
            " VALUES ('cron-1','cron','daily-briefing',900,0)"
        )
        con.executescript(
            "INSERT INTO messages (session_id, role, content, timestamp)"
            " VALUES ('web-1','user','who are you?',1000);"
            "INSERT INTO messages (session_id, role, content, timestamp, finish_reason, reasoning)"
            " VALUES ('web-1','assistant','Isabella.',1042,'stop','thinking out loud');"
        )
        con.commit()
        con.close()

    (tmp_path / "config.yaml").write_text(
        f"memory:\n  memory_enabled: {'true' if enabled else 'false'}\n", encoding="utf-8"
    )
    if memory is not None:
        (tmp_path / "memories").mkdir(exist_ok=True)
        (tmp_path / "memories" / "MEMORY.md").write_text(memory, encoding="utf-8")

    return Settings(hermes_home=tmp_path, _env_file=None)


# ----------------------------------------------------------------------
# Reading Hermes' state
# ----------------------------------------------------------------------


def test_no_state_db_is_a_state_not_a_crash(tmp_path):
    cfg = Settings(hermes_home=tmp_path, _env_file=None)
    sessions, detail = state.read_sessions(cfg)
    assert sessions == []
    assert "No Hermes state" in detail


def test_the_database_is_opened_read_only(tmp_path):
    """Writing to Hermes' database behind Hermes' back is how two systems end
    up disagreeing about what was said. The connection refuses, it does not
    merely decline to try."""
    cfg = home(tmp_path)
    with (
        state._connect(cfg.hermes_home / "state.db") as db,
        pytest.raises(sqlite3.OperationalError),
    ):
        db.execute("INSERT INTO sessions (id, source, started_at) VALUES ('x','y',1)")


def test_compacted_messages_are_not_shown(tmp_path):
    """`active = 0` means compression has folded it away - it is no longer in
    her context, and printing it would claim a conversation she has compacted."""
    cfg = home(tmp_path)
    con = sqlite3.connect(cfg.hermes_home / "state.db")
    con.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, active)"
        " VALUES ('web-1','user','forgotten',1010,0)"
    )
    con.commit()
    con.close()

    messages, _ = state.read_messages(cfg)
    assert [m.content for m in messages] == ["who are you?", "Isabella."]


# ----------------------------------------------------------------------
# Memory, and the importance that is allowed to be missing
# ----------------------------------------------------------------------


def test_an_unrated_memory_has_no_importance(tmp_path):
    cfg = home(tmp_path, memory="I need to bring work shoes tomorrow.", enabled=True)
    memories, enabled, _ = state.read_memories(cfg)

    assert enabled is True
    assert len(memories) == 1
    # Not 0, and not 5. Nobody rated it.
    assert memories[0].importance is None


def test_a_rated_memory_keeps_its_rating_and_loses_the_tag(tmp_path):
    cfg = home(tmp_path, memory="[importance: 9] His brother.", enabled=True)
    memories, _, _ = state.read_memories(cfg)

    assert memories[0].importance == 9
    assert "importance" not in memories[0].body
    assert memories[0].body == "His brother."


def test_memory_switched_off_says_so_rather_than_looking_empty(tmp_path):
    """An empty store with memory disabled is a configuration fact, not an
    empty mind, and the view has to be able to tell the two apart."""
    cfg = home(tmp_path)
    memories, enabled, detail = state.read_memories(cfg)

    assert memories == []
    assert enabled is False
    assert "memory_enabled" in detail


def test_wikilinks_between_memories_resolve_to_ids(tmp_path):
    cfg = home(
        tmp_path,
        memory="Casa Amparo\n\n§\n\n[importance: 7] The flood at [[Casa Amparo]].",
        enabled=True,
    )
    got = mind.snapshot(cfg)
    linked = next(n for n in got["nodes"] if n["title"].startswith("The flood"))
    target = next(n for n in got["nodes"] if n["title"] == "Casa Amparo")

    assert linked["relations"] == [target["id"]]


# ----------------------------------------------------------------------
# The graph
# ----------------------------------------------------------------------


def test_the_graph_is_three_kinds_and_counts_them(tmp_path):
    got = mind.snapshot(home(tmp_path, memory="[importance: 3] A thing.", enabled=True))

    assert got["counts"] == {"memory": 1, "session": 2, "message": 2}
    assert got["total"] == 5


def test_every_node_carries_a_real_size(tmp_path):
    """A circle whose size means nothing is refused, however good it looks."""
    got = mind.snapshot(home(tmp_path, memory="[importance: 10] Everything.", enabled=True))

    for node in got["nodes"]:
        assert 0.0 <= node["size"] <= 1.0
    memory = next(n for n in got["nodes"] if n["kind"] == "memory")
    assert memory["size"] == 1.0
    assert memory["measure"] == "10/10"


def test_an_unrated_memory_is_drawn_uncertain_not_worthless(tmp_path):
    got = mind.snapshot(home(tmp_path, memory="Work shoes.", enabled=True))
    memory = next(n for n in got["nodes"] if n["kind"] == "memory")

    assert memory["importance"] is None
    assert memory["measure"] == "unrated"
    # Low confidence is how the renderer draws it hollow: present, weight
    # unknown. That is a different statement from importance zero.
    assert memory["confidence"] < 0.6


def test_a_message_hangs_off_its_own_session_by_id(tmp_path):
    """Sessions are titled from their first message and two really can be
    called the same thing, which is why the edge is keyed on id."""
    got = mind.snapshot(home(tmp_path))
    message = next(n for n in got["nodes"] if n["kind"] == "message")

    assert message["relations"] == ["session:web-1"]


def test_only_the_live_session_is_lit(tmp_path):
    cfg = home(tmp_path)

    assert mind.snapshot(cfg)["recalled"] == []

    lit = mind.snapshot(cfg, "web-1")["recalled"]
    assert {"id": "session:web-1", "hop": 0} in lit
    # Its messages, one hop out. Nothing from the other session.
    assert all(r["id"].startswith(("session:web-1", "message:")) for r in lit)
    assert mind.snapshot(cfg, "web-1")["budget"] == len(lit)


def test_a_session_id_that_is_not_there_lights_nothing(tmp_path):
    assert mind.snapshot(home(tmp_path), "web-nonexistent")["recalled"] == []


# ----------------------------------------------------------------------
# The chat log
# ----------------------------------------------------------------------


def test_the_chat_log_carries_the_real_wait(tmp_path):
    got = transcript.read(home(tmp_path))
    web = next(s for s in got["sessions"] if s["id"] == "web-1")
    reply = web["turns"][1]

    assert reply["who"] == "isabella"
    # 1042 - 1000. The slowest thing in the system, printed.
    assert reply["seconds"] == 42.0
    assert "42s" in reply["note"]
    assert reply["reasoned"] is True


def test_an_empty_completion_is_named_as_the_error_it_is(tmp_path):
    """Reasoning counts against max_tokens; starved, content comes back empty
    with finish_reason=length. CLAUDE.md calls that a real error."""
    cfg = home(tmp_path)
    con = sqlite3.connect(cfg.hermes_home / "state.db")
    con.execute(
        "INSERT INTO messages (session_id, role, content, timestamp, finish_reason)"
        " VALUES ('web-1','assistant','',1200,'length')"
    )
    con.commit()
    con.close()

    got = transcript.read(cfg)
    starved = next(s for s in got["sessions"] if s["id"] == "web-1")["turns"][-1]
    assert "token budget" in starved["note"]


def test_the_chat_log_reports_tokens_from_hermes_own_counters(tmp_path):
    got = transcript.read(home(tmp_path))
    web = next(s for s in got["sessions"] if s["id"] == "web-1")

    assert web["tokens"] == {"input": 1800, "output": 900, "reasoning": 0}
    assert web["api_call_count"] == 1
