#!/usr/bin/env python3
"""Collect the facts the morning briefing is made of.

Runs BEFORE the model, as a Hermes cron pre-run script. Its stdout is injected
into the prompt under "## Script Output"; the model then has no reason to call
a tool, and is configured to have none (`platform_toolsets.cron: []`).

That is the whole point. Decided 2026-08-23: calendar and email arrive as
pre-fetched context rather than as tool calls, so the unattended 07:00 path -
which does not pass through Isabella's `permit()` - never needs shell or
arbitrary Python in the model's hands. This script is code that was written and
reviewed once and sits in a containment-checked directory. That is a different
thing from execution the model composes at runtime, and the difference is the
entire security argument.

**It fails loudly on purpose.** A model with no tools and an empty context will
happily invent a plausible Tuesday. Every failure here prints an explicit
UNAVAILABLE line so the briefing says "I couldn't reach your calendar" instead
of quietly making one up. Silence is the one output this script must never
produce.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes-isabella")).expanduser()
GOOGLE = HOME / "skills" / "productivity" / "google-workspace" / "scripts" / "google_api.py"

# Long enough for a slow API, short enough that the job's 180s timeout is not
# spent entirely here.
TIMEOUT_S = 45
MAX_EVENTS = 20
MAX_MAIL = 25
UNREAD_WINDOW_HOURS = 12


def call(*args: str) -> tuple[bool, object]:
    """Run google_api.py and parse its JSON. Returns (ok, payload_or_reason)."""
    if not GOOGLE.exists():
        return False, f"the google-workspace skill is not installed at {GOOGLE}"
    try:
        proc = subprocess.run(
            [sys.executable, str(GOOGLE), *args],
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )
    except subprocess.TimeoutExpired:
        return False, f"Google did not answer within {TIMEOUT_S}s"

    if proc.returncode != 0 or not proc.stdout.strip():
        return False, explain(proc)
    try:
        return True, json.loads(proc.stdout)
    except json.JSONDecodeError:
        return False, "Google returned something that was not JSON"


# Lines worth surfacing over whatever happened to be printed last. The skill
# ends its auth error with a bare command path, which reads as nonsense on its
# own; the sentence above it is the one that says what is wrong.
SIGNALS = ("not authenticated", "credential", "token", "quota", "permission", "denied")


def explain(proc: subprocess.CompletedProcess) -> str:
    """One useful sentence, never a stack trace and never the environment."""
    lines = [ln.strip() for ln in (proc.stderr or "").splitlines() if ln.strip()]
    for line in lines:
        if any(word in line.lower() for word in SIGNALS):
            return line.rstrip(":") + " - the google-workspace skill needs authorising"
    for line in reversed(lines):
        # Skip the bare command lines that follow a "run this first" message.
        if not line.startswith(("python", "/", "File \"", "  ")):
            return line
    return lines[-1] if lines else f"exit {proc.returncode} with no output"


def rows(payload: object) -> list:
    """The skill returns either a bare list or {items|events|messages: [...]}."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("items", "events", "messages", "results"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def section(title: str, ok: bool, body: list[str], reason: object = "") -> str:
    if not ok:
        return f"{title}\nUNAVAILABLE: {reason}\n"
    if not body:
        return f"{title}\n(nothing)\n"
    return title + "\n" + "\n".join(body) + "\n"


def calendar_today(now: datetime) -> str:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    ok, payload = call(
        "calendar", "list", "--start", start.isoformat(),
        "--end", end.isoformat(), "--max", str(MAX_EVENTS),
    )
    if not ok:
        return section("CALENDAR (today)", False, [], payload)

    lines = []
    for ev in rows(payload)[:MAX_EVENTS]:
        if not isinstance(ev, dict):
            continue
        when = ev.get("start") or ev.get("start_time") or ""
        if isinstance(when, dict):
            when = when.get("dateTime") or when.get("date") or ""
        # Keep the clock time; the date is already "today" by construction.
        when = when[11:16] if len(str(when)) >= 16 else (when or "all-day")
        title = ev.get("summary") or ev.get("title") or "(untitled)"
        where = ev.get("location") or ""
        lines.append(f"- {when} {title}" + (f" @ {where}" if where else ""))
    return section("CALENDAR (today)", True, lines)


def unread_mail() -> str:
    ok, payload = call(
        "gmail", "search", f"is:unread newer_than:{UNREAD_WINDOW_HOURS}h",
        "--max", str(MAX_MAIL),
    )
    if not ok:
        return section(f"EMAIL (unread, last {UNREAD_WINDOW_HOURS}h)", False, [], payload)

    lines = []
    for msg in rows(payload)[:MAX_MAIL]:
        if not isinstance(msg, dict):
            continue
        sender = msg.get("from") or msg.get("sender") or "(unknown)"
        subject = msg.get("subject") or "(no subject)"
        # Bodies are deliberately not included: the briefing is about what needs
        # attention, and full bodies would blow the 16k window.
        lines.append(f"- {sender}: {subject}")
    return section(f"EMAIL (unread, last {UNREAD_WINDOW_HOURS}h)", True, lines)


def main() -> int:
    now = datetime.now().astimezone()
    out = [
        f"AS OF: {now.strftime('%A %d %B %Y, %H:%M %Z')}",
        "",
        calendar_today(now),
        unread_mail(),
        ("Anything marked UNAVAILABLE could not be read. Say so plainly in the "
         "briefing; do not guess what it might have contained."),
    ]
    print("\n".join(out))
    # Always 0: a non-zero exit makes Hermes treat the whole job as failed, and
    # an honest "UNAVAILABLE" briefing is more useful than no briefing at all.
    return 0


if __name__ == "__main__":
    sys.exit(main())
