"""Turn a trigger definition into the job payload Hermes will accept.

Everything Hermes cannot express has to be folded in here, because the
alternative is a guardrail that silently doesn't apply. Two of those, both
verified against the installed Hermes (0.20.4):

1. **Cron fields must be numeric.** `cron/jobs.py::parse_schedule` gates on
   `^[\\d\\*\\-,/]+$` before handing the expression to croniter, so `mon-fri`
   is not a valid day-of-week - it falls through the cron branch entirely and
   is then misread as a timestamp. `condition.weekdays` compiles to digits.

2. **There is no per-job timezone.** `hermes_time.py` resolves one timezone
   for the whole instance (HERMES_TIMEZONE, else the `timezone` key in
   config.yaml, else system local). A trigger's `timezone:` is therefore an
   *assertion about her Hermes instance*, checked at reconcile time, not
   something that travels with the job.
"""

import hashlib
import json

from core.triggers.schema import TriggerDef

# croniter's day-of-week numbering: 0 = Sunday.
DOW = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}


def compile_cron(defn: TriggerDef) -> str:
    """Fold `condition.weekdays` into the cron expression's 5th field.

    Done here rather than as a runtime predicate so a skipped day costs
    nothing: Hermes simply never fires. A condition evaluated after waking the
    model would burn a run and an inference to decide to do nothing.
    """
    fields = defn.trigger.cron.split()
    days = defn.condition.weekdays
    if not days:
        return " ".join(fields)

    if fields[4] != "*":
        raise ValueError(
            f"{defn.id}: cron already constrains day-of-week ({fields[4]!r}) and "
            "condition.weekdays would silently overwrite it. Use one or the other."
        )
    fields[4] = ",".join(str(n) for n in sorted(DOW[d] for d in days))
    return " ".join(fields)


def compile_job(defn: TriggerDef) -> dict:
    """The POST /api/jobs body.

    `repeat` is deliberately absent: omitted means run forever on the schedule,
    which is what a daily briefing is. `max_runs_per_day` is Isabella's own
    limit and is enforced against the `runs` table, not by Hermes.
    """
    return {
        "name": defn.job_name(),
        "schedule": compile_cron(defn),
        "prompt": defn.action.prompt,
        "deliver": defn.deliver.channel,
        "skills": defn.action.skills,
    }


def create_command(defn: TriggerDef) -> str:
    """The `hermes cron create` that makes a script job Isabella cannot.

    `POST /api/jobs` accepts neither `script` nor `no_agent`, and PATCH's
    whitelist does not either, so a pre-fetch trigger has to be created once by
    hand. Handing back the exact command beats an error that only says no.
    """
    parts = [
        "hermes cron create", f'"{compile_cron(defn)}"', '"<prompt from the YAML>"',
        f"--name {defn.job_name()}", f"--script {defn.action.script}",
        f"--deliver {defn.deliver.channel}",
    ]
    parts += [f"--skill {s}" for s in defn.action.skills]
    return "HERMES_HOME=~/.hermes-isabella " + " ".join(parts)


def script_mismatch(defn: TriggerDef, job: dict) -> str | None:
    """Whether the live job's pre-run script is the one the YAML asked for.

    Reported, never repaired: `script` is not in PATCH's whitelist, so the only
    fix is to delete the job and recreate it. Silently tolerating a mismatch
    would mean the briefing is built from data nobody chose.
    """
    want = defn.action.script
    got = job.get("script")
    if (want or None) == (got or None):
        return None
    return f"job runs script {got!r}, the trigger asks for {want!r}"


def spec_digest(defn: TriggerDef) -> str:
    """Fingerprint of the whole definition.

    Covers guardrails and timezone too, not just the job payload, so a change
    to something Hermes never sees still counts as drift worth recording.
    """
    body = json.dumps(defn.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(body.encode()).hexdigest()


def job_drifted(defn: TriggerDef, job: dict) -> dict:
    """Fields where the live Hermes job disagrees with the definition.

    Returns only what differs, which is exactly the PATCH body. Empty means
    reconciliation has nothing to do - that is what makes it idempotent.
    """
    want = compile_job(defn)
    changed = {}
    for key, value in want.items():
        current = job.get(key)
        if key == "schedule":
            # Asymmetric on purpose: PATCH takes the cron *string*, but the job
            # comes back with it parsed into {kind, expr, display}. Comparing
            # what we sent against what we got makes every reconcile look like
            # drift and PATCH forever. Caught by reconciling twice for real.
            current = current.get("expr") if isinstance(current, dict) else current
        if key == "skills":
            # Hermes may return null for an empty list, or a legacy single
            # `skill` string. Compare as sets so neither reads as drift.
            current = current or []
            if isinstance(current, str):
                current = [current]
            if sorted(current) != sorted(value):
                changed[key] = value
            continue
        if current != value:
            changed[key] = value

    # A pause is a deliberate human act and outranks the file until someone
    # resumes it. Reconciling `enabled: true` back over a paused job would make
    # the kill switch last only until the next reconcile - which is to say, not
    # a kill switch. Hermes marks this as state=paused with a paused_at stamp;
    # `enabled: false` alone (never set by us) is not enough to infer intent.
    if is_paused(job):
        changed.pop("enabled", None)
        return changed

    if bool(job.get("enabled", True)) != defn.enabled:
        changed["enabled"] = defn.enabled
    return changed


def is_paused(job: dict) -> bool:
    return job.get("state") == "paused" or bool(job.get("paused_at"))
