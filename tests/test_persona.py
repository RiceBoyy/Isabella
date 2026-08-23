"""Drift between compiled/core.md and SOUL.md means Hermes serves a stale identity."""

from core.config import Settings
from core.persona import store


def _cfg(tmp_path, body="You are Isabella."):
    persona = tmp_path / "core.md"
    persona.write_text(body)
    return Settings(
        persona_path=persona,
        soul_path=tmp_path / "SOUL.md",
        db_path=tmp_path / "isabella.db",
    )


def test_not_installed_is_drift(tmp_path):
    s = store.status(_cfg(tmp_path))
    assert not s.installed and s.drifted


def test_install_then_clean(tmp_path):
    cfg = _cfg(tmp_path)
    store.install(cfg)
    s = store.status(cfg)
    assert s.installed and not s.drifted
    assert cfg.soul_path.read_text() == "You are Isabella."


def test_edited_soul_is_detected(tmp_path):
    cfg = _cfg(tmp_path)
    store.install(cfg)
    cfg.soul_path.write_text("You are Hermes Agent.")
    s = store.status(cfg)
    assert s.drifted and "stale" in s.detail


def test_install_records_a_version(tmp_path):
    cfg = _cfg(tmp_path)
    store.install(cfg)
    conn = store.connect(cfg)
    rows = conn.execute("SELECT sha256, active FROM persona_versions").fetchall()
    conn.close()
    assert len(rows) == 1 and rows[0][1] == 1
