"""The reconciler.

Not a scheduler. It reads `triggers/*.yaml`, compares them against Hermes'
jobs, and pushes the difference. Hermes decides when anything fires. There is
no loop here and there must never be one - CLAUDE.md, prime directive.

Reconciliation is idempotent: run it twice and the second run does nothing.
That is the property everything else depends on, so it is what the tests check.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from core.config import Settings
from core.hermes.client import HermesClient
from core.triggers import store
from core.triggers.compile import (
    compile_job,
    create_command,
    is_paused,
    job_drifted,
    script_mismatch,
    spec_digest,
)
from core.triggers.schema import TriggerDef, load_dir

log = logging.getLogger("isabella.triggers")

# Only jobs whose name carries this prefix are hers. Jobs created by hand
# through `hermes cron` share the same instance and must never be deleted by a
# reconcile - deleting someone else's scheduled work is not a recoverable
# mistake.
OWNED_PREFIX = "isabella:"


@dataclass(slots=True)
class Plan:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created or self.updated or self.deleted)

    def as_dict(self) -> dict:
        return {
            "created": self.created,
            "updated": self.updated,
            "deleted": self.deleted,
            "unchanged": self.unchanged,
            "changed": self.changed,
        }


class TimezoneMismatch(RuntimeError):
    """Her Hermes instance is in a different timezone than the trigger assumes.

    Hermes has no per-job timezone (see compile.py), so this cannot be fixed by
    the payload - it would just fire at the wrong hour, every day, silently.
    Loud failure is the only honest option.
    """


def _owned(jobs: list[dict]) -> dict[str, list[dict]]:
    """Her jobs, grouped by name.

    A list rather than a single job because Hermes does not enforce unique
    names: two jobs can share one, and keying by name would let the newer
    silently shadow the older while both keep firing. Reconcile keeps the
    oldest and deletes the rest.
    """
    owned: dict[str, list[dict]] = {}
    for j in jobs:
        name = j.get("name")
        if isinstance(name, str) and name.startswith(OWNED_PREFIX):
            owned.setdefault(name, []).append(j)
    for group in owned.values():
        group.sort(key=lambda j: (j.get("created_at") or "", j.get("id") or ""))
    return owned


def check_timezone(defn: TriggerDef, hermes_timezone: str | None) -> None:
    """Refuse to reconcile a schedule into an instance that reads it differently."""
    if hermes_timezone is None:
        log.warning(
            "%s: cannot read her Hermes timezone; %s is assumed but unverified",
            defn.id, defn.trigger.timezone,
        )
        return
    if hermes_timezone != defn.trigger.timezone:
        raise TimezoneMismatch(
            f"{defn.id} schedules {defn.trigger.cron} in {defn.trigger.timezone}, but her "
            f"Hermes instance runs in {hermes_timezone}. Hermes has no per-job timezone, "
            f"so this job would fire at the wrong hour. Set `timezone: {defn.trigger.timezone}` "
            f"in ~/.hermes-isabella/config.yaml, or change the trigger."
        )


class ScriptJobNotCreatable(RuntimeError):
    """A pre-fetch trigger has to be created once by hand.

    `POST /api/jobs` accepts neither `script` nor `no_agent`. Creating the job
    without the script would produce something that looks reconciled and
    silently briefs from nothing - so this refuses, and hands back the command
    that works. Once the job exists, reconcile manages everything else on it.
    """


class Engine:
    def __init__(self, cfg: Settings, hermes: HermesClient, directory: Path | None = None) -> None:
        self._cfg = cfg
        self._hermes = hermes
        self._dir = directory or cfg.triggers_path

    def definitions(self) -> list[TriggerDef]:
        return load_dir(self._dir)

    async def reconcile(self, *, dry_run: bool = False) -> Plan:
        """Push desired state into Hermes. Returns what changed."""
        defs = self.definitions()
        live = _owned(await self._hermes.list_jobs())
        plan = Plan()
        conn = store.connect(self._cfg)

        try:
            wanted_names: set[str] = set()

            for defn in defs:
                check_timezone(defn, self._cfg.hermes_timezone)
                name = defn.job_name()

                # `enabled: false` is a kill switch at the source: the job is
                # removed from Hermes entirely, not left paused and forgettable.
                if not defn.enabled:
                    if name in live:
                        plan.deleted.append(defn.id)
                        if not dry_run:
                            for job in live[name]:
                                await self._hermes.delete_job(job["id"])
                            store.forget(conn, defn.id)
                    continue

                wanted_names.add(name)
                group = live.get(name) or []
                job = group[0] if group else None

                # Duplicates in her own namespace: keep the oldest, delete the
                # rest. Both would fire otherwise, and the briefing would arrive
                # twice - see HISTORY.md, the paused-job duplication bug.
                for extra in group[1:]:
                    log.warning("%s: deleting duplicate job %s", defn.id, extra["id"])
                    if not dry_run:
                        await self._hermes.delete_job(extra["id"])

                if job is None:
                    if defn.action.script:
                        raise ScriptJobNotCreatable(
                            f"{defn.id} declares script {defn.action.script!r}, which the "
                            "jobs API cannot set. Create it once with:\n\n    "
                            f"{create_command(defn)}\n\n"
                            "then reconcile again - schedule, prompt, delivery and the "
                            "kill switch are managed from the YAML after that."
                        )
                    plan.created.append(defn.id)
                    if not dry_run:
                        created = await self._hermes.create_job(compile_job(defn))
                        self._record(conn, defn, created.get("id"))
                    continue

                # Reported, not repaired - `script` is not in PATCH's whitelist.
                mismatch = script_mismatch(defn, job)
                if mismatch:
                    log.warning("%s: %s (recreate the job to change it)", defn.id, mismatch)

                drift = job_drifted(defn, job)
                if drift:
                    plan.updated.append(defn.id)
                    if not dry_run:
                        await self._hermes.update_job(job["id"], drift)
                        self._record(conn, defn, job["id"])
                else:
                    plan.unchanged.append(defn.id)
                    if not dry_run:
                        self._record(conn, defn, job["id"])

            # Orphans: hers by name, but no YAML claims them any more.
            for name, group in live.items():
                if name in wanted_names:
                    continue
                orphan = name.removeprefix(OWNED_PREFIX)
                if orphan in plan.deleted:
                    continue
                plan.deleted.append(orphan)
                if not dry_run:
                    for job in group:
                        await self._hermes.delete_job(job["id"])
                    store.forget(conn, orphan)

            return plan
        finally:
            conn.close()

    def _record(self, conn, defn: TriggerDef, job_id: str | None) -> None:
        store.upsert(
            conn,
            trigger_id=defn.id,
            job_id=job_id,
            enabled=defn.enabled,
            spec_sha256=spec_digest(defn),
            spec=defn.model_dump(mode="json"),
        )

    # ------------------------------------------------------------------
    # Kill switches and manual firing
    # ------------------------------------------------------------------

    async def _job_id(self, trigger_id: str) -> str | None:
        conn = store.connect(self._cfg)
        try:
            row = store.get(conn, trigger_id)
        finally:
            conn.close()
        if row and row.job_id:
            return row.job_id
        # Fall back to Hermes: the DB can be behind, but the job is the truth.
        live = _owned(await self._hermes.list_jobs())
        group = live.get(f"{OWNED_PREFIX}{trigger_id}")
        return group[0]["id"] if group else None

    async def pause(self, trigger_id: str) -> dict | None:
        job_id = await self._job_id(trigger_id)
        return await self._hermes.pause_job(job_id) if job_id else None

    async def resume(self, trigger_id: str) -> dict | None:
        job_id = await self._job_id(trigger_id)
        return await self._hermes.resume_job(job_id) if job_id else None

    async def fire(self, trigger_id: str) -> dict | None:
        """Run now, by hand.

        The run record is opened before Hermes is asked to run, per
        ARCHITECTURE.md, and the rate limit applies here too - a manual fire
        that ignored `max_runs_per_day` would make the limit a suggestion.
        """
        defs = {d.id: d for d in self.definitions()}
        defn = defs.get(trigger_id)
        if defn is None:
            return None

        job_id = await self._job_id(trigger_id)
        if job_id is None:
            return None

        conn = store.connect(self._cfg)
        try:
            used = store.runs_today(conn, trigger_id)
            if used >= defn.guardrails.max_runs_per_day:
                return {
                    "ok": False,
                    "reason": "rate_limited",
                    "detail": f"{used}/{defn.guardrails.max_runs_per_day} runs used today",
                }

            run_id = store.start_run(conn, trigger_id=trigger_id, job_id=job_id, source="manual")
            try:
                job = await self._hermes.run_job(job_id)
            except Exception as exc:
                store.finish_run(conn, run_id, outcome="error", detail=str(exc))
                raise
            # "triggered", not "delivered": Hermes runs it asynchronously and
            # Isabella is not in the delivery path. Claiming success here would
            # be a lie about something she cannot see.
            store.finish_run(conn, run_id, outcome="triggered", detail=job.get("id", ""))
            return {"ok": True, "run_id": run_id, "job": job}
        finally:
            conn.close()

    async def sync_runs(self) -> dict:
        """Fold Hermes' execution records into her `runs` table.

        Cron fires without Isabella in the path, so this is the only way a
        scheduled briefing becomes visible to her own audit trail. Pull, not
        push - and no loop: it runs when someone reads /runs or /triggers.

        **Limit, stated rather than hidden:** the jobs API exposes only
        `latest_execution` per job. Two runs between two syncs and the middle
        one is lost. At `max_runs_per_day: 1` that cannot bite; at a tighter
        schedule it can, and the fix would be an executions endpoint upstream,
        not a poller here.
        """
        live = _owned(await self._hermes.list_jobs())
        conn = store.connect(self._cfg)
        counts = {"inserted": 0, "linked": 0, "unchanged": 0}
        try:
            for defn in self.definitions():
                for job in live.get(defn.job_name()) or []:
                    execution = job.get("latest_execution")
                    if not execution:
                        continue
                    result = store.record_execution(
                        conn, trigger_id=defn.id, job_id=job["id"], execution=execution
                    )
                    counts[result] += 1
            return counts
        finally:
            conn.close()

    async def status(self) -> list[dict]:
        # Sync first so `runs_today` reflects what Hermes actually ran, not
        # only what Isabella asked for by hand.
        await self.sync_runs()
        live = _owned(await self._hermes.list_jobs())
        conn = store.connect(self._cfg)
        try:
            out = []
            for defn in self.definitions():
                group = live.get(defn.job_name()) or []
                job = group[0] if group else None
                out.append({
                    "id": defn.id,
                    "enabled": defn.enabled,
                    "schedule": defn.trigger.cron,
                    "timezone": defn.trigger.timezone,
                    "deliver": defn.deliver.channel,
                    "skills": defn.action.skills,
                    "script": defn.action.script,
                    "script_mismatch": script_mismatch(defn, job) if job else None,
                    "script_install": store.script_status(self._cfg, defn.action.script),
                    "job_id": job.get("id") if job else None,
                    "job_enabled": bool(job.get("enabled", True)) if job else None,
                    # Surfaced separately from `enabled`: a paused job is one a
                    # human stopped, and reconcile deliberately leaves it that way.
                    "paused": is_paused(job) if job else None,
                    "next_run_at": job.get("next_run_at") if job else None,
                    "last_status": job.get("last_status") if job else None,
                    "failure_streak": job.get("failure_streak", 0) if job else None,
                    "reconciled": bool(job) and not job_drifted(defn, job),
                    "duplicates": max(0, len(group) - 1),
                    "runs_today": store.runs_today(conn, defn.id),
                    "max_runs_per_day": defn.guardrails.max_runs_per_day,
                })
            return out
        finally:
            conn.close()
