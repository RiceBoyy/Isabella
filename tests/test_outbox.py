"""Reading a delivered briefing back off disk.

The failure this guards against is quiet and bad: a briefing shown against the
wrong morning, or the prompt shown as though she wrote it. Both would look
plausible on the page, which is exactly why they are tested rather than eyeballed.
"""

from datetime import UTC, datetime

from core.config import Settings
from core.hermes import outbox

# The shape Hermes actually writes, trimmed. Kept verbatim rather than
# paraphrased - if upstream changes the headings, this file is where it shows.
REAL = """# Cron Job: isabella:daily-briefing

**Job ID:** 1c9924cddac7
**Run Time:** 2026-08-26 08:23:36
**Schedule:** 0 7 * * 1,2,3,4,5

## Prompt

Brief me from it.

## Script Output
The following data was collected by a pre-run script.

```
CALENDAR (today)
UNAVAILABLE: Not authenticated.
```

## Response

Sir. No calendar or unread emails accessible - authentication required for
google-workspace. You're forgetting the google-workspace skill needs authorising.
"""


def cfg(tmp_path, **over) -> Settings:
    return Settings(
        hermes_home=tmp_path, hermes_timezone="Europe/Copenhagen", _env_file=None, **over
    )


def write(tmp_path, job_id: str, name: str, body: str) -> None:
    folder = tmp_path / "cron" / "output" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(body, encoding="utf-8")


# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------


def test_hermes_home_reroots_the_instance_paths(tmp_path):
    settings = cfg(tmp_path)
    assert settings.cron_output_path == tmp_path / "cron" / "output"
    assert settings.soul_path == tmp_path / "SOUL.md"
    assert settings.hermes_scripts_path == tmp_path / "scripts"


def test_an_explicit_path_outranks_the_derivation(tmp_path):
    settings = cfg(tmp_path, soul_path=tmp_path / "elsewhere" / "SOUL.md")
    assert settings.soul_path == tmp_path / "elsewhere" / "SOUL.md"


# ----------------------------------------------------------------------
# Parsing
# ----------------------------------------------------------------------


def test_parse_takes_the_response_and_not_the_prompt():
    stamp, text = outbox.parse(REAL, outbox.zone(Settings(hermes_timezone="Europe/Copenhagen", _env_file=None)))

    assert text.startswith("Sir. No calendar")
    # The prompt and the script's output are above the heading and must not
    # arrive as though she said them.
    assert "Brief me from it" not in text
    assert "UNAVAILABLE" not in text
    # 08:23:36 in Copenhagen is 06:23:36 UTC. Getting this wrong by the offset
    # is how a briefing lands on the wrong day.
    assert stamp == datetime(2026, 8, 26, 6, 23, 36, tzinfo=UTC)


def test_a_file_with_no_response_section_is_not_a_crash():
    stamp, text = outbox.parse("# Cron Job\n\n**Run Time:** 2026-08-26 08:23:36\n", None)
    assert text is None
    # No zone, no guess: an unmatched delivery beats one attached to the wrong run.
    assert stamp is None


# ----------------------------------------------------------------------
# Reading and matching
# ----------------------------------------------------------------------


def test_a_job_that_never_delivered_locally_reads_as_empty(tmp_path):
    assert outbox.deliveries(cfg(tmp_path), "1c9924cddac7") == []


def test_attach_matches_a_run_to_its_own_output(tmp_path):
    write(tmp_path, "1c9924cddac7", "2026-08-26_08-23-36.md", REAL)
    runs = [{"job_id": "1c9924cddac7", "finished_at": "2026-08-26T06:23:36.627036+00:00"}]

    assert outbox.attach(cfg(tmp_path), runs)[0]["briefing"].startswith("Sir.")


def test_a_run_from_another_morning_gets_nothing(tmp_path):
    write(tmp_path, "1c9924cddac7", "2026-08-26_08-23-36.md", REAL)
    runs = [{"job_id": "1c9924cddac7", "finished_at": "2026-08-25T06:23:36+00:00"}]

    assert outbox.attach(cfg(tmp_path), runs)[0]["briefing"] is None


def test_a_run_that_never_finished_gets_nothing(tmp_path):
    write(tmp_path, "1c9924cddac7", "2026-08-26_08-23-36.md", REAL)
    runs = [{"job_id": "1c9924cddac7", "finished_at": None, "outcome": "running"}]

    assert outbox.attach(cfg(tmp_path), runs)[0]["briefing"] is None


def test_the_nearest_delivery_wins(tmp_path):
    """Two runs in one day is allowed; the wrong one must not be shown."""
    later = REAL.replace("08:23:36", "08:24:40")
    write(tmp_path, "1c9924cddac7", "2026-08-26_08-23-36.md", REAL)
    write(tmp_path, "1c9924cddac7", "2026-08-26_08-24-40.md", later.replace("Sir.", "Later."))
    runs = [{"job_id": "1c9924cddac7", "finished_at": "2026-08-26T06:24:41+00:00"}]

    assert outbox.attach(cfg(tmp_path), runs)[0]["briefing"].startswith("Later.")
