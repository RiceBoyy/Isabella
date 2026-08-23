"""Her identity: versioned here, installed where Hermes reads it.

Hermes serves her personality from ~/.hermes-isabella/SOUL.md. The source of
truth is Personality/compiled/core.md in this repo. These two must not drift,
so installing is an explicit operation with a recorded hash.
"""

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from core.config import Settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS persona_versions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256      TEXT NOT NULL,
    body        TEXT NOT NULL,
    installed_at TEXT NOT NULL,
    active      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_persona_active ON persona_versions(active);
"""


@dataclass(slots=True)
class PersonaState:
    sha256: str
    installed: bool
    drifted: bool
    detail: str


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def connect(cfg: Settings) -> sqlite3.Connection:
    cfg.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(cfg.db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def status(cfg: Settings) -> PersonaState:
    """Compare the compiled prompt against what Hermes is actually serving."""
    if not cfg.persona_path.exists():
        return PersonaState("", False, False, f"missing {cfg.persona_path}")

    source = cfg.persona_path.read_text()
    want = _digest(source)

    if not cfg.soul_path.exists():
        return PersonaState(want, False, True, f"not installed at {cfg.soul_path}")

    got = _digest(cfg.soul_path.read_text())
    if got != want:
        return PersonaState(
            want, True, True,
            "SOUL.md differs from compiled/core.md - Hermes is serving a stale identity",
        )
    return PersonaState(want, True, False, "ok")


def install(cfg: Settings) -> PersonaState:
    """Copy the compiled prompt to SOUL.md and record the version."""
    source = cfg.persona_path.read_text()
    sha = _digest(source)

    cfg.soul_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.soul_path.write_text(source)

    conn = connect(cfg)
    try:
        conn.execute("UPDATE persona_versions SET active = 0")
        conn.execute(
            "INSERT INTO persona_versions (sha256, body, installed_at, active) VALUES (?,?,?,1)",
            (sha, source, datetime.now(UTC).isoformat()),
        )
        conn.commit()
    finally:
        conn.close()

    return PersonaState(sha, True, False, "installed")
