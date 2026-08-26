"""Owen's body, read out of the vault.

**The vault is the only truth here.** A Mac has no Health database to read -
HealthKit links but `isHealthDataAvailable()` is false - so there is no device
to sync and nothing here pretends otherwise. Owen writes Markdown and this reads
the same Markdown he reads. The formats are Selene's, unchanged, because the
files are the interface and two readers disagreeing about them would be worse
than either.

    Personal/Body/Body/<date>.md          weight, water
    Personal/Body/Sleep/<date>.md         the night
    Personal/Body/Workout/<YYYY-Www>.md   the week's rotation, ticked as it goes
    Personal/Body/measurements.md         girths, dated, left and right

**Nothing here fills a gap.** An unlogged measure comes back `null` and the view
draws the absence. A zero, or last week's weight carried forward, is a dashboard
telling a story - and the story would be about a real person's health, which is
the worst possible subject to be confidently wrong about.

Every measure carries the date it was written, so a number a week old *looks* a
week old rather than looking like today.

Read-only, and one subtree of one directory. Nothing in this module writes.
"""

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.config import Settings

BODY = Path("Personal") / "Body"

# The model's own region ids. A bare group lights both sides; the model turns,
# so back muscles are drawable too - which a front-view drawing could not show.
GROUPS = (
    "chest", "delt", "tri", "bi", "forearm", "core",
    "lat", "back", "quad", "ham", "glute", "calf",
)

# Exercise name -> what it worked. Keywords rather than exact names, because the
# log is written by hand and "Cable Tricep Pushdown" and "Tricep Pushdown" are
# the same movement on different days.
#
# **Longest match wins, and only one match counts** (see `worked_by`). That rule
# is load-bearing: "Leg Curl" contains "curl", and unioning every keyword that
# appears would light his biceps for a hamstring exercise. The same trap took
# "Cable Tricep Pushdown" and lit the chest.
WORKS: dict[str, tuple[str, ...]] = {
    "chest press": ("chest", "tri"),
    "bench": ("chest", "tri"),
    "pec deck": ("chest",),
    "fly": ("chest",),
    "incline": ("chest", "delt"),
    # Not "push". "Cable Tricep Pushdown" contains it and is not a press -
    # a substring map lights the wrong muscles the moment a key is a word
    # that turns up inside other words.
    "pushup": ("chest", "tri", "delt"),
    "push up": ("chest", "tri", "delt"),
    "dip": ("chest", "tri"),
    "lateral raise": ("delt",),
    "shoulder press": ("delt", "tri"),
    "overhead press": ("delt", "tri"),
    "front raise": ("delt",),
    "tricep": ("tri",),
    "skull": ("tri",),
    "squat": ("quad",),
    "leg press": ("quad",),
    "leg extension": ("quad",),
    "lunge": ("quad",),
    "calf": ("calf",),
    "lat pulldown": ("lat", "bi"),
    "pulldown": ("lat", "bi"),
    "pull up": ("lat", "bi"),
    "pullup": ("lat", "bi"),
    "chin": ("lat", "bi"),
    "row": ("lat", "back"),
    "shrug": ("back",),
    "face pull": ("back", "delt"),
    "deadlift": ("back", "ham", "glute"),
    "hip thrust": ("glute",),
    "leg curl": ("ham",),
    "hamstring": ("ham",),
    "rdl": ("ham", "glute"),
    "curl": ("bi",),
    "hammer": ("bi", "forearm"),
    "wrist": ("forearm",),
    "plank": ("core",),
    "crunch": ("core",),
    "ab ": ("core",),
    "core": ("core",),
    "hanging": ("core",),
}


@dataclass(slots=True)
class Measure:
    value: float | None
    on: str | None


def _frontmatter(text: str) -> dict[str, str]:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _latest(folder: Path) -> tuple[dict[str, str], str | None]:
    """The most recent dated file in a folder, by name. Names are ISO dates, so
    sorting them is sorting by date without parsing any of them."""
    if not folder.is_dir():
        return {}, None
    files = sorted((f for f in folder.glob("*.md") if f.stem[:4].isdigit()), reverse=True)
    if not files:
        return {}, None
    try:
        return _frontmatter(files[0].read_text(encoding="utf-8")), files[0].stem
    except OSError:
        return {}, None


def _number(raw: str | None) -> float | None:
    if not raw:
        return None
    found = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(found.group()) if found else None


def _today(cfg: Settings) -> date:
    zone = None
    if cfg.hermes_timezone:
        try:
            zone = ZoneInfo(cfg.hermes_timezone)
        except (ZoneInfoNotFoundError, ValueError):
            zone = None
    return datetime.now(tz=zone).astimezone().date()


def week_key(today: date) -> str:
    year, week, _ = today.isocalendar()
    return f"{year}-W{week:02d}"


def _workout(root: Path, today: date) -> dict:
    """This week's rotation: which days have been ticked, and what they worked."""
    path = root / BODY / "Workout" / f"{week_key(today)}.md"
    blank = {"key": week_key(today), "logged": False, "days": [], "worked": []}
    if not path.is_file():
        return blank
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return blank

    days, worked = [], set()
    current = None
    for line in text.splitlines():
        header = re.match(r"##\s+Day\s+(\d+)\s*[—-]\s*(.+)", line)
        if header:
            title = header.group(2)
            name, _, when = title.partition("·")
            current = {
                "n": int(header.group(1)),
                "name": name.strip(),
                "on": when.strip(),
                "done": 0,
                "total": 0,
            }
            days.append(current)
            continue

        tick = re.match(r"\s*-\s*\[( |x|X)\]\s*(.+)", line)
        if tick and current is not None:
            current["total"] += 1
            if tick.group(1).lower() == "x":
                current["done"] += 1
                worked.update(worked_by(tick.group(2)))

    return {
        "key": week_key(today),
        "logged": any(d["done"] for d in days),
        # Only days with something in them; seven empty headings is a template,
        # not a week, and listing them would read as seven missed sessions.
        "days": [d for d in days if d["total"]],
        "worked": sorted(worked),
    }


def worked_by(exercise: str) -> tuple[str, ...]:
    """What one exercise worked. Longest keyword wins, and it wins alone.

    Unioning every keyword that appears in the name is the bug this exists to
    prevent: "Leg Curl" contains "curl" and would light a bicep, and "Cable
    Tricep Pushdown" contains "push" and lit a whole chest. The most specific
    phrase that matches is the one that describes the movement.
    """
    name = exercise.lower()
    for keyword in sorted(WORKS, key=len, reverse=True):
        if keyword in name:
            return WORKS[keyword]
    return ()


def _measurements(root: Path) -> dict:
    """The newest dated session in measurements.md, as a table of areas."""
    path = root / BODY / "measurements.md"
    if not path.is_file():
        return {"on": None, "areas": []}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return {"on": None, "areas": []}

    sessions = re.split(r"^###\s+", text, flags=re.MULTILINE)[1:]
    for session in sessions:
        head, _, body = session.partition("\n")
        on = head.strip()
        if not re.match(r"\d{4}-\d{2}-\d{2}", on):
            continue
        areas = []
        for line in body.splitlines():
            cells = [c.strip() for c in line.split("|")[1:-1]]
            if len(cells) < 3 or cells[0].lower() in {"area", "---"} or set(cells[0]) <= {"-"}:
                continue
            left, right = _number(cells[1]), _number(cells[2])
            if left is None and right is None:
                continue
            areas.append({
                "area": cells[0],
                "left": left,
                "right": right,
                # The asymmetry is the point of writing both columns down.
                "gap": round(left - right, 1) if left is not None and right is not None else None,
                "note": cells[3] if len(cells) > 3 else "",
            })
        if areas:
            return {"on": on, "areas": areas}
    return {"on": None, "areas": []}


def read(cfg: Settings, today: date | None = None) -> dict:
    """Everything the body view draws. Absent measures stay absent."""
    # His day, not the machine's. The week key depends on which day it is, and
    # a server drifting a zone away would show last week's rotation.
    today = today or _today(cfg)
    root = cfg.vault_path

    if not (root / BODY).is_dir():
        return {
            "available": False,
            "detail": f"No body log at {root / BODY}.",
            "as_of": today.isoformat(),
        }

    day, day_on = _latest(root / BODY / "Body")
    night, night_on = _latest(root / BODY / "Sleep")

    water_used, water_goal = None, None
    if "water" in day:
        # "1.1/2.5" - used over goal, which is a real quantity against a real
        # budget and therefore allowed to be drawn as a meter.
        parts = day["water"].split("/")
        water_used = _number(parts[0])
        water_goal = _number(parts[1]) if len(parts) > 1 else None

    return {
        "available": True,
        "detail": "",
        "as_of": today.isoformat(),
        "weight": {"value": _number(day.get("weight")), "on": day_on},
        "water": {"used": water_used, "goal": water_goal, "on": day_on},
        "sleep": {"hours": _number(night.get("sleep")), "on": night_on},
        "week": _workout(root, today),
        "measurements": _measurements(root),
    }
