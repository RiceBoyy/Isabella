"""What Isabella records about her own autonomy.

Two tables, and neither holds message content - transcripts are Hermes'
(DATA.md). `triggers` maps a YAML definition to the Hermes job it reconciled
to; `runs` is the audit trail: what fired, when, and whether it worked.

ARCHITECTURE.md: the run record is written *before* delivery. A briefing that
was sent but never recorded is worse than one recorded but never sent - the
first is invisible, the second is a known failure.
"""

import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from core.config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS triggers (
    id            TEXT PRIMARY KEY,
    job_id        TEXT,
    enabled       INTEGER NOT NULL,
    spec_sha256   TEXT NOT NULL,
    spec          TEXT NOT NULL,
    reconciled_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    trigger_id   TEXT NOT NULL,
    job_id       TEXT,
    source       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    outcome      TEXT NOT NULL,
    detail       TEXT,
    -- Hermes' own execution id. UNIQUE is what makes syncing idempotent:
    -- folding the same execution in twice is a no-op, not a duplicate row.
    execution_id TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_runs_trigger ON runs(trigger_id, started_at);
"""

# Added after the table shipped. SQLite has no IF NOT EXISTS for columns, so
# this is checked rather than guessed.
MIGRATIONS = (("runs", "execution_id", "ALTER TABLE runs ADD COLUMN execution_id TEXT"),)

# Hermes' execution states, mapped to what Isabella records. "claimed" and
# "running" are not terminal; "unknown" means the process died without
# reporting, which is a failure she should see rather than a gap.
OUTCOMES = {
    "completed": "ok",
    "failed": "error",
    "unknown": "unknown",
    "claimed": "running",
    "running": "running",
}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _utc(stamp: str | None) -> str | None:
    """Normalise a timestamp to UTC before it is stored.

    `runs_today` compares timestamps as strings, which is only sound if they
    all share an offset. Hermes reports in its own local zone (+02:00 here), so
    a run at 01:00 local - 23:00 UTC the previous day - would sort as today and
    consume today's allowance. Every stored timestamp is UTC.
    """
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).astimezone(UTC).isoformat()
    except ValueError:
        # Unparseable is better recorded verbatim than dropped; it will sort
        # oddly, but losing the record entirely would be worse.
        return stamp


def connect(cfg: Settings) -> sqlite3.Connection:
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for table, column, ddl in MIGRATIONS:
        existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
        if column not in existing:
            conn.execute(ddl)
    conn.commit()
    return conn


@dataclass(slots=True)
class TriggerRow:
    id: str
    job_id: str | None
    enabled: bool
    spec_sha256: str


def get(conn: sqlite3.Connection, trigger_id: str) -> TriggerRow | None:
    row = conn.execute(
        "SELECT id, job_id, enabled, spec_sha256 FROM triggers WHERE id = ?", (trigger_id,)
    ).fetchone()
    if row is None:
        return None
    return TriggerRow(row["id"], row["job_id"], bool(row["enabled"]), row["spec_sha256"])


def all_rows(conn: sqlite3.Connection) -> list[TriggerRow]:
    rows = conn.execute("SELECT id, job_id, enabled, spec_sha256 FROM triggers").fetchall()
    return [TriggerRow(r["id"], r["job_id"], bool(r["enabled"]), r["spec_sha256"]) for r in rows]


def upsert(
    conn: sqlite3.Connection,
    *,
    trigger_id: str,
    job_id: str | None,
    enabled: bool,
    spec_sha256: str,
    spec: dict,
) -> None:
    conn.execute(
        """
        INSERT INTO triggers (id, job_id, enabled, spec_sha256, spec, reconciled_at)
        VALUES (?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            job_id = excluded.job_id,
            enabled = excluded.enabled,
            spec_sha256 = excluded.spec_sha256,
            spec = excluded.spec,
            reconciled_at = excluded.reconciled_at
        """,
        (trigger_id, job_id, int(enabled), spec_sha256, json.dumps(spec, sort_keys=True), _now()),
    )
    conn.commit()


def forget(conn: sqlite3.Connection, trigger_id: str) -> None:
    """Drop the trigger row. Runs are kept - the history of a deleted trigger
    is still history, and losing it would make the audit trail lie."""
    conn.execute("DELETE FROM triggers WHERE id = ?", (trigger_id,))
    conn.commit()


def start_run(
    conn: sqlite3.Connection, *, trigger_id: str, job_id: str | None, source: str
) -> int:
    """Open a run record. Called before anything is delivered."""
    cur = conn.execute(
        "INSERT INTO runs (trigger_id, job_id, source, started_at, outcome) VALUES (?,?,?,?,?)",
        (trigger_id, job_id, source, _now(), "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, *, outcome: str, detail: str = "") -> None:
    conn.execute(
        "UPDATE runs SET finished_at = ?, outcome = ?, detail = ? WHERE id = ?",
        (_now(), outcome, detail, run_id),
    )
    conn.commit()


def runs_today(conn: sqlite3.Connection, trigger_id: str) -> int:
    """How many times this trigger has run since UTC midnight.

    Backs `max_runs_per_day`. UTC because the run timestamps are UTC; a
    local-midnight window would need her Hermes timezone and is not worth the
    ambiguity for a rate limit whose job is to stop a runaway loop.
    """
    midnight = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM runs WHERE trigger_id = ? AND started_at >= ?",
        (trigger_id, midnight),
    ).fetchone()
    return int(row["n"])


def recent_runs(conn: sqlite3.Connection, trigger_id: str | None = None, limit: int = 20) -> list[dict]:
    if trigger_id:
        rows = conn.execute(
            "SELECT * FROM runs WHERE trigger_id = ? ORDER BY id DESC LIMIT ?",
            (trigger_id, limit),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def record_execution(
    conn: sqlite3.Connection, *, trigger_id: str, job_id: str, execution: dict
) -> str:
    """Fold one Hermes execution into her ledger. Idempotent.

    Isabella is not in the call path when Hermes' cron fires - that was the
    deliberate architectural win, and it is also why a scheduled briefing left
    no trace here. This is how she finds out what happened without a second
    scheduler and without a second store: Hermes remains the source of truth,
    `runs` becomes her index into it.

    Returns "inserted", "linked" or "unchanged".
    """
    exec_id = execution.get("id")
    if not exec_id:
        return "unchanged"

    outcome = OUTCOMES.get(execution.get("status", ""), execution.get("status") or "unknown")
    detail = (execution.get("error") or "").strip()
    started = _utc(execution.get("started_at") or execution.get("claimed_at")) or _now()
    finished = _utc(execution.get("finished_at"))

    existing = conn.execute(
        "SELECT id, outcome, detail FROM runs WHERE execution_id = ?", (exec_id,)
    ).fetchone()
    if existing:
        if existing["outcome"] == outcome and (existing["detail"] or "") == detail:
            return "unchanged"
        # A run seen mid-flight and now finished. Terminal states are Hermes'
        # to declare, so hers follow rather than lead.
        conn.execute(
            "UPDATE runs SET outcome = ?, detail = ?, finished_at = ? WHERE id = ?",
            (outcome, detail, finished, existing["id"]),
        )
        conn.commit()
        return "linked"

    # A manual fire opens a row before Hermes has an execution id for it. Claim
    # the oldest unlinked one for this job rather than inserting a second row -
    # otherwise one press of "run now" shows up twice and burns two of the
    # day's allowance.
    orphan = conn.execute(
        """
        SELECT id FROM runs
        WHERE job_id = ? AND execution_id IS NULL AND started_at <= ?
        ORDER BY id ASC LIMIT 1
        """,
        (job_id, started),
    ).fetchone()

    if orphan:
        conn.execute(
            "UPDATE runs SET execution_id = ?, outcome = ?, detail = ?, finished_at = ? "
            "WHERE id = ?",
            (exec_id, outcome, detail, finished, orphan["id"]),
        )
        conn.commit()
        return "linked"

    conn.execute(
        """
        INSERT INTO runs (trigger_id, job_id, source, started_at, finished_at,
                          outcome, detail, execution_id)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        (trigger_id, job_id, execution.get("source") or "schedule", started, finished,
         outcome, detail, exec_id),
    )
    conn.commit()
    return "inserted"


def script_status(cfg: Settings, script: str | None) -> dict:
    """Is the installed pre-run script the one in the repo?

    Same trap as SOUL.md, one directory over: `scripts/` here is the source of
    truth, but Hermes only ever runs the copy in HERMES_HOME/scripts/. Editing
    one and forgetting the other means the briefing is built by code nobody
    reviewed. Cheap to check, so it is checked.
    """
    if not script:
        return {"script": None}
    source = cfg.scripts_path / script
    installed = cfg.hermes_scripts_path / script
    out = {
        "script": script,
        "source": str(source),
        "installed": installed.exists(),
        "drifted": False,
        "detail": "ok",
    }
    if not source.exists():
        out |= {"drifted": True, "detail": f"not in the repo at {source}"}
    elif not installed.exists():
        out |= {"drifted": True, "detail": f"not installed at {installed}"}
    elif source.read_bytes() != installed.read_bytes():
        out |= {
            "drifted": True,
            "detail": "the installed script differs from the repo - Hermes is running "
                      "code that is not version-controlled",
        }
    return out
