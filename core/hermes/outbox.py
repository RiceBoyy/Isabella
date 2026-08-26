"""Reading back what a cron job actually said.

The one place Isabella touches Hermes' filesystem rather than its HTTP API,
and it is here rather than anywhere else for the same reason the client is:
when upstream moves, one module changes.

**Why a file at all.** `deliver: local` writes each run to
`<HERMES_HOME>/cron/output/<job_id>/<local timestamp>.md`. The jobs API carries
the execution's *status* and nothing of its *output* - `latest_execution` is
`{status, timestamps, error}` - so a briefing that has already been composed
and delivered is unreadable over HTTP. The alternative was to have Isabella
store the text when she sees it, and that is a second message store, which
DATA.md forbids. So: read at request time, hand it to the caller, keep nothing.
See ARCHITECTURE.md.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import Settings

# A run record and an output file are joined on time, because neither carries
# the other's id: the file is named for the moment the job finished, to the
# second. Hermes writes the file as it finishes, so the gap is small; the
# tolerance is wide enough to absorb it and far narrower than the shortest
# interval any trigger here is allowed to run at.
MATCH_TOLERANCE_S = 120

_RUN_TIME = re.compile(r"^\*\*Run Time:\*\*\s*(.+)$", re.MULTILINE)

# Everything after this heading is the model's reply. The sections above it are
# the prompt and the pre-run script's output, which the UI must not show as
# though she wrote them.
_RESPONSE = re.compile(r"^##\s+Response\s*$", re.MULTILINE)


@dataclass(slots=True, frozen=True)
class Delivery:
    """One local delivery: when it finished, and what she said."""

    path: Path
    finished_at: datetime | None  # UTC, so it compares against a run record
    text: str | None  # None when the file has no Response section at all


def zone(cfg: Settings) -> ZoneInfo | None:
    """Her Hermes instance's timezone - the one the filenames are written in.

    None when it is unset or unknown, and callers then decline to match rather
    than guessing an offset: a briefing attached to the wrong morning is worse
    than one that is missing.
    """
    if not cfg.hermes_timezone:
        return None
    try:
        return ZoneInfo(cfg.hermes_timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return None


def parse(markdown: str, tz: ZoneInfo | None) -> tuple[datetime | None, str | None]:
    """Pull the finish time and the reply out of one output file."""
    stamp = None
    found = _RUN_TIME.search(markdown)
    if found and tz is not None:
        try:
            # The header carries no offset - the zone is the instance's, not
            # the file's, so it is supplied rather than parsed.
            stamp = (
                datetime.strptime(found.group(1).strip(), "%Y-%m-%d %H:%M:%S")
                .replace(tzinfo=tz)
                .astimezone(UTC)
            )
        except ValueError:
            stamp = None

    split = _RESPONSE.split(markdown, maxsplit=1)
    # "[SILENT]" is passed through rather than blanked. Hermes reads it as
    # "suppress delivery"; a reader of the archive should still see that she
    # chose to say nothing, which is not the same as a run that produced
    # nothing.
    text = split[1].strip() if len(split) == 2 else None
    return stamp, (text or None)


def deliveries(cfg: Settings, job_id: str) -> list[Delivery]:
    """Every recorded local delivery for one job, newest first.

    A missing directory is a job that has never delivered locally - normal, and
    not an error.
    """
    folder = cfg.cron_output_path / job_id
    if not folder.is_dir():
        return []

    tz = zone(cfg)
    out = []
    for path in sorted(folder.glob("*.md"), reverse=True):
        try:
            markdown = path.read_text(encoding="utf-8")
        except OSError:
            continue
        stamp, text = parse(markdown, tz)
        out.append(Delivery(path=path, finished_at=stamp, text=text))
    return out


def attach(cfg: Settings, runs: list[dict]) -> list[dict]:
    """Add `briefing` to each run: her text, or None.

    None is the honest answer for a run whose file is gone, for one that
    predates local delivery, and for a failure that never got as far as
    speaking. None of those is an error, so none of them raises.
    """
    wanted = {r.get("job_id") for r in runs if r.get("job_id")}
    by_job = {job_id: deliveries(cfg, job_id) for job_id in wanted}

    for run in runs:
        run["briefing"] = _match(by_job.get(run.get("job_id")) or [], run.get("finished_at"))
    return runs


def _match(found: list[Delivery], finished_at: str | None) -> str | None:
    if not finished_at:
        return None
    try:
        target = datetime.fromisoformat(finished_at).astimezone(UTC)
    except ValueError:
        return None

    best = None
    for delivery in found:
        if delivery.finished_at is None:
            continue
        gap = abs((delivery.finished_at - target).total_seconds())
        if gap <= MATCH_TOLERANCE_S and (best is None or gap < best[0]):
            best = (gap, delivery.text)
    return best[1] if best else None
