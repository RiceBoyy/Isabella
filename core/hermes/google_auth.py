"""Connecting her to Google, by driving Hermes' own setup script.

**Why a subprocess and not an OAuth implementation.** The google-workspace
skill already owns this flow end to end: PKCE, the pending-session state, the
exchange, scope reconciliation, refresh, and revocation. Reimplementing it here
would duplicate Hermes' credential handling - the single worst place in this
repo to have two versions of something. So Isabella drives the script and owns
only what it is bad at: telling Owen what state he is in and what to do next.

**What is actually granted.** This build of the skill pins SCOPES to
`gmail.readonly` and `calendar.readonly`, and has no flag to widen them. She can
read the day and the unread mail; she cannot send, delete, or modify. That grant
is a *standing* one - it survives reboots and sits on disk next to a process
that acts unprompted at 07:00 - which is why it is decided here rather than
defaulted, and why `disconnect()` exists as a first-class control rather than a
terminal command nobody remembers. See PERMISSIONS.md §blast radius.

**Why it cannot live in a cookie.** The briefing fires with no browser open and
nobody logged in. A session token in the browser is unreachable at 07:00; only
a refresh token on disk, in *her* HERMES_HOME, is any use to her.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Settings

# Network round-trips to Google. Generous, because a consent exchange that
# times out looks identical to a rejected one and is much more annoying.
TIMEOUT_S = 60

SCRIPT = Path("skills") / "productivity" / "google-workspace" / "scripts" / "setup.py"


class GoogleAuthError(RuntimeError):
    """A failure worth showing a human verbatim.

    Every way this module can fail arrives as one of these, so callers never
    have to catch a subprocess exception to keep a status panel alive.
    """


@dataclass(slots=True)
class GoogleAuth:
    """Her Google connection, as far as anything can tell from here."""

    connected: bool
    state: str
    detail: str
    # Read straight off the token: what was *granted*, which can be narrower
    # than what was asked for - the consent screen lets you deselect.
    scopes: list[str] = field(default_factory=list)
    token_path: str = ""


def _script(cfg: Settings) -> Path:
    return cfg.hermes_home / SCRIPT


def _run(cfg: Settings, *args: str) -> subprocess.CompletedProcess[str]:
    """Run the skill's setup script against HER instance.

    `HERMES_HOME` is set explicitly and not inherited. The default is Selene's
    home, and a token written there would be both useless to Isabella and a
    grant sitting in another agent's directory.
    """
    # Fixed argv and no shell: the pasted redirect URL reaches the script as
    # one argument and is never interpreted.
    try:
        return subprocess.run(
            [str(cfg.hermes_python), str(_script(cfg)), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
            env={
                "HERMES_HOME": str(cfg.hermes_home),
                "PATH": "/usr/bin:/bin",
                "HOME": str(Path.home()),
            },
        )
    except subprocess.TimeoutExpired as exc:
        raise GoogleAuthError(f"Google did not answer within {TIMEOUT_S}s.") from exc
    except OSError as exc:
        raise GoogleAuthError(f"Could not run the setup script: {exc}") from exc


def _first_line(text: str) -> str:
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()
    return ""


def status(cfg: Settings) -> GoogleAuth:
    """Where the connection stands. Never raises - this backs a status panel,
    and a panel that 500s tells you less than one that says what is wrong."""
    if not _script(cfg).exists():
        return GoogleAuth(False, "unavailable", "The google-workspace skill is not installed.")
    if not (cfg.hermes_home / "google_client_secret.json").exists():
        return GoogleAuth(
            False,
            "no_client_secret",
            "No OAuth client stored yet. A desktop-app client JSON from Google Cloud Console "
            "has to be installed once before consent can start.",
        )

    try:
        proc = _run(cfg, "--check")
    except GoogleAuthError as exc:
        return GoogleAuth(False, "unavailable", str(exc))

    out = _first_line(proc.stdout) or _first_line(proc.stderr)
    token = cfg.hermes_home / "google_token.json"

    if proc.returncode == 0:
        # "AUTHENTICATED (partial)" is still usable, and saying only
        # "connected" would hide that a scope was deselected at consent.
        partial = "(partial)" in proc.stdout
        return GoogleAuth(
            connected=True,
            state="partial" if partial else "connected",
            detail=out,
            scopes=_granted(token),
            token_path=str(token),
        )

    if "TOKEN_CORRUPT" in proc.stdout:
        return GoogleAuth(False, "corrupt", out)
    if "OAUTH_CLIENT_DISABLED" in proc.stdout:
        return GoogleAuth(False, "client_disabled", out)
    return GoogleAuth(False, "absent", out or "Not connected.")


def _granted(token: Path) -> list[str]:
    import json

    try:
        payload = json.loads(token.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    raw = payload.get("scopes") or payload.get("scope") or []
    return raw.split() if isinstance(raw, str) else list(raw)


def consent_url(cfg: Settings) -> str:
    """Start a consent session and return the URL to approve it at.

    The script prints the URL alone on stdout and stores the PKCE verifier
    beside it, so this must be the same instance that later completes the
    exchange - which it is, because both run against her HERMES_HOME.
    """
    proc = _run(cfg, "--auth-url")
    url = _first_line(proc.stdout)
    if proc.returncode != 0 or not url.startswith("http"):
        raise GoogleAuthError(url or _first_line(proc.stderr) or "Could not build a consent URL.")
    return url


def complete(cfg: Settings, redirect: str) -> GoogleAuth:
    """Exchange what came back from Google for a stored refresh token.

    Takes the whole redirected URL or a bare code - the script accepts either,
    and asking a human to extract a query parameter by hand is how this step
    goes wrong. The value is a live credential: it is never logged, and never
    echoed back in a response.
    """
    redirect = redirect.strip()
    if not redirect:
        raise GoogleAuthError("Nothing pasted.")

    proc = _run(cfg, "--auth-code", redirect)
    if proc.returncode != 0:
        raise GoogleAuthError(
            _first_line(proc.stdout) or _first_line(proc.stderr) or "The exchange failed."
        )
    return status(cfg)


def disconnect(cfg: Settings) -> GoogleAuth:
    """Revoke the grant with Google and delete the token.

    The end of a standing grant should be one button, not a remembered command.
    Reversible only by consenting again, which is the correct weight for it.
    """
    proc = _run(cfg, "--revoke")
    if proc.returncode != 0:
        raise GoogleAuthError(_first_line(proc.stderr) or "Revocation failed.")
    return status(cfg)
