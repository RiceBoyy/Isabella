"""Reading Owen's body log.

The rule under every test here is the one Selene's scanner states: **nothing
fills a gap.** A missing weight must arrive as `None`, never as zero and never
as last week's, because the view draws what it is given and this particular
dashboard would be telling a story about a real person's health.
"""

import json
from datetime import date

import pytest

from core.body import GROUPS, read, week_key, worked_by
from core.config import REPO_ROOT, Settings


def vault(tmp_path, files: dict[str, str]) -> Settings:
    for name, text in files.items():
        path = tmp_path / "Personal" / "Body" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Settings(vault_path=tmp_path, hermes_timezone="Europe/Copenhagen", _env_file=None)


def test_no_body_log_at_all_is_a_state_not_a_crash(tmp_path):
    got = read(Settings(vault_path=tmp_path, _env_file=None), date(2026, 8, 26))
    assert got["available"] is False
    assert "No body log" in got["detail"]


def test_an_unlogged_measure_stays_absent(tmp_path):
    """A day he trained and did not weigh himself."""
    cfg = vault(tmp_path, {"Body/2026-08-19.md": "---\nwater: 1.1/2.5\n---\n"})

    got = read(cfg, date(2026, 8, 26))
    assert got["weight"]["value"] is None
    assert got["water"]["used"] == 1.1
    # Zero would be a lie about a real body.
    assert got["weight"]["value"] != 0


def test_every_measure_carries_the_day_it_was_written(tmp_path):
    """A number a week old has to look a week old."""
    cfg = vault(tmp_path, {"Body/2026-08-19.md": "---\nweight: 67.5\n---\n"})

    got = read(cfg, date(2026, 8, 26))
    assert got["weight"] == {"value": 67.5, "on": "2026-08-19"}


def test_the_newest_day_wins(tmp_path):
    cfg = vault(
        tmp_path,
        {
            "Body/2026-08-11.md": "---\nweight: 70\n---\n",
            "Body/2026-08-19.md": "---\nweight: 67.5\n---\n",
        },
    )
    assert read(cfg, date(2026, 8, 26))["weight"]["value"] == 67.5


WEEK = """---
week: 2026-W35
---

## Day 1 — Push · Mon 2026-08-24

- [x] Chest Press — 3 × 12 @ 35
- [x] Cable Tricep Pushdown — 3 × 15 @ 20
- [ ] Pec Deck

## Day 2 — Pull · Tue 2026-08-25

- [ ] Lat Pulldown
"""


def test_only_what_was_ticked_counts_as_worked(tmp_path):
    cfg = vault(tmp_path, {"Workout/2026-W35.md": WEEK})

    week = read(cfg, date(2026, 8, 26))["week"]
    assert week["logged"] is True
    assert week["days"][0] == {"n": 1, "name": "Push", "on": "Mon 2026-08-24", "done": 2, "total": 3}
    # Pec Deck is unticked, so nothing it works is lit.
    assert week["worked"] == ["chest", "tri"]


def test_an_untouched_template_week_lights_nothing(tmp_path):
    cfg = vault(tmp_path, {"Workout/2026-W35.md": WEEK.replace("[x]", "[ ]")})

    week = read(cfg, date(2026, 8, 26))["week"]
    assert week["logged"] is False
    assert week["worked"] == []
    # The rotation is still shown - a planned day is not a missed one.
    assert week["days"][0]["total"] == 3


def test_the_week_follows_his_day_not_the_machine(tmp_path):
    assert week_key(date(2026, 8, 26)) == "2026-W35"
    assert week_key(date(2026, 8, 10)) == "2026-W33"


MEASURES = """---
height: 168-170
---

## Log

### 2026-06-30

| Area | Left | Right | Note |
| --- | --- | --- | --- |
| Neck | 38 | | |
| Thigh | 53 | 50 | left +3 |

### earlier — date unknown

| Area | Left | Right | Note |
| --- | --- | --- | --- |
| Thigh | 51 | 49 | |
"""


def test_measurements_take_the_newest_dated_session(tmp_path):
    cfg = vault(tmp_path, {"measurements.md": MEASURES})

    got = read(cfg, date(2026, 8, 26))["measurements"]
    assert got["on"] == "2026-06-30"
    thigh = next(a for a in got["areas"] if a["area"] == "Thigh")
    # The asymmetry is the reason both columns get written down.
    assert thigh["gap"] == 3.0
    neck = next(a for a in got["areas"] if a["area"] == "Neck")
    assert neck["right"] is None and neck["gap"] is None


# ----------------------------------------------------------------------
# Exercise names. The model turns, so back muscles are drawable too.
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("exercise", "expect"),
    [
        ("Chest Press", ("chest", "tri")),
        ("Incline Dumbbell Press", ("chest", "delt")),
        ("Lateral Raise", ("delt",)),
        ("Lat Pulldown", ("lat", "bi")),
        ("Seated Row", ("lat", "back")),
        ("Deadlift", ("back", "ham", "glute")),
        ("Calf Raise", ("calf",)),
        # Nothing in the map. A session that lights nothing is still a session.
        ("Sauna", ()),
    ],
)
def test_the_log_s_own_names_map_to_the_model_s_regions(exercise, expect):
    assert worked_by(exercise) == expect


@pytest.mark.parametrize(
    ("exercise", "expect", "wrong"),
    [
        # "curl" is inside "Leg Curl", and a hamstring exercise must not light
        # a bicep.
        ("Leg Curl", "ham", "bi"),
        # "push" is inside "Pushdown", and a pushdown is not a press.
        ("Cable Tricep Pushdown", "tri", "chest"),
    ],
)
def test_the_longest_keyword_wins_and_wins_alone(exercise, expect, wrong):
    """The substring trap, both times it has actually bitten."""
    got = worked_by(exercise)
    assert expect in got
    assert wrong not in got


# ----------------------------------------------------------------------
# The contract with the 3D atlas
# ----------------------------------------------------------------------

ATLAS = REPO_ROOT / "web" / "public" / "anatomy" / "muscle.json"


@pytest.mark.skipif(not ATLAS.exists(), reason="atlas not installed; primitives stand in")
def test_every_group_the_reader_produces_lights_a_real_region():
    """The join between a Markdown log and a 3D mesh, asserted.

    `worked_by` returns ids like "chest"; the model resolves a bare id to both
    sides. If the atlas is regenerated with different names, muscles quietly
    stop lighting and nothing else fails - so this is the test that notices.
    """
    regions = set(json.loads(ATLAS.read_text())["regions"])

    missing = [g for g in GROUPS if not {f"{g}.l", f"{g}.r"} <= regions]
    assert missing == [], f"no region in the atlas for: {missing}"


@pytest.mark.skipif(not ATLAS.exists(), reason="atlas not installed")
def test_the_atlas_carries_the_attribution_it_requires():
    """Z-Anatomy is CC BY-SA: the credit has to reach the screen, and it can
    only do that if the mesh still carries it."""
    mesh = json.loads(ATLAS.read_text())
    assert mesh["source"]
    assert mesh["licence"] == "CC BY-SA 4.0"
