"""Driving the google-workspace setup script.

The property that matters most is the boring one: the token must land in
Isabella's HERMES_HOME. The default is Selene's, and a grant written there
would be both useless to Isabella and sitting in another agent's directory.
"""

import subprocess

import pytest

from core.config import Settings
from core.hermes import google_auth
from core.hermes.google_auth import GoogleAuthError


def cfg(tmp_path) -> Settings:
    home = tmp_path / "hermes-isabella"
    script = home / "skills" / "productivity" / "google-workspace" / "scripts"
    script.mkdir(parents=True)
    (script / "setup.py").write_text("# stand-in for the skill's script\n")
    (home / "google_client_secret.json").write_text("{}")
    return Settings(hermes_home=home, _env_file=None)


def fake_run(monkeypatch, *, returncode=0, stdout="", stderr="", record=None):
    def run(argv, **kwargs):
        if record is not None:
            record.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, returncode, stdout, stderr)

    monkeypatch.setattr(subprocess, "run", run)


# ----------------------------------------------------------------------
# The instance boundary
# ----------------------------------------------------------------------


def test_the_script_runs_against_her_home_and_not_the_default(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setenv("HERMES_HOME", "/somewhere/else")
    fake_run(monkeypatch, stdout="AUTHENTICATED: Token valid", record=calls)

    google_auth.status(cfg(tmp_path))

    _, kwargs = calls[0]
    assert kwargs["env"]["HERMES_HOME"] == str(tmp_path / "hermes-isabella")
    # Not inherited: an ambient HERMES_HOME must not decide where a standing
    # grant gets written.
    assert "/somewhere/else" not in kwargs["env"]["HERMES_HOME"]


def test_nothing_is_passed_through_a_shell(tmp_path, monkeypatch):
    calls = []
    fake_run(monkeypatch, stdout="OK: Authenticated.", record=calls)

    google_auth.complete(cfg(tmp_path), "http://localhost:1/?code=4/0A&state=x")

    argv, kwargs = calls[0]
    assert kwargs.get("shell") is not True
    # The pasted value arrives as one argument, uninterpreted.
    assert argv[-1] == "http://localhost:1/?code=4/0A&state=x"


# ----------------------------------------------------------------------
# Status
# ----------------------------------------------------------------------


def test_a_missing_client_secret_says_so_rather_than_failing(tmp_path):
    settings = cfg(tmp_path)
    (settings.hermes_home / "google_client_secret.json").unlink()

    state = google_auth.status(settings)
    assert state.connected is False
    assert state.state == "no_client_secret"


def test_a_partial_grant_is_not_reported_as_a_whole_one(tmp_path, monkeypatch):
    """A deselected scope at the consent screen must stay visible."""
    fake_run(monkeypatch, stdout="AUTHENTICATED (partial): Token valid but missing 1 scopes:")
    settings = cfg(tmp_path)
    (settings.hermes_home / "google_token.json").write_text(
        '{"scopes": ["https://www.googleapis.com/auth/calendar.readonly"]}'
    )

    state = google_auth.status(settings)
    assert state.connected is True
    assert state.state == "partial"
    assert state.scopes == ["https://www.googleapis.com/auth/calendar.readonly"]


def test_not_connected_is_a_state_and_not_an_error(tmp_path, monkeypatch):
    fake_run(monkeypatch, returncode=1, stdout="NOT_AUTHENTICATED: No token at /x")

    state = google_auth.status(tmp_path and cfg(tmp_path))
    assert state.state == "absent"
    assert "NOT_AUTHENTICATED" in state.detail


def test_a_script_that_will_not_run_keeps_the_panel_alive(tmp_path, monkeypatch):
    def boom(argv, **kwargs):
        raise OSError("no such interpreter")

    monkeypatch.setattr(subprocess, "run", boom)

    state = google_auth.status(cfg(tmp_path))
    assert state.state == "unavailable"


# ----------------------------------------------------------------------
# Consent
# ----------------------------------------------------------------------


def test_consent_url_is_returned_alone(tmp_path, monkeypatch):
    fake_run(monkeypatch, stdout="https://accounts.google.com/o/oauth2/auth?x=1\n")
    assert google_auth.consent_url(cfg(tmp_path)).startswith("https://accounts.google.com/")


def test_a_refused_consent_raises_with_the_script_s_own_words(tmp_path, monkeypatch):
    fake_run(monkeypatch, returncode=1, stdout="ERROR: No client secret stored.")

    with pytest.raises(GoogleAuthError, match="No client secret"):
        google_auth.consent_url(cfg(tmp_path))


def test_a_stale_code_reports_what_google_said(tmp_path, monkeypatch):
    fake_run(monkeypatch, returncode=1, stdout="ERROR: OAuth state mismatch.")

    with pytest.raises(GoogleAuthError, match="state mismatch"):
        google_auth.complete(cfg(tmp_path), "http://localhost:1/?code=old")


def test_an_empty_paste_never_reaches_the_script(tmp_path, monkeypatch):
    calls = []
    fake_run(monkeypatch, record=calls)

    with pytest.raises(GoogleAuthError):
        google_auth.complete(cfg(tmp_path), "   ")
    assert calls == []
