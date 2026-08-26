"""What has to hold before anything runs unattended.

Idempotency, the guardrails being mandatory, and - most of all - that a
reconcile never touches a job Isabella did not create. Other Hermes jobs live
on the same instance.
"""

import httpx
import pytest
import yaml
from pydantic import ValidationError

from core.config import Settings
from core.hermes.client import HermesClient
from core.triggers import store
from core.triggers.compile import compile_cron, compile_job, job_drifted
from core.triggers.engine import Engine, TimezoneMismatch
from core.triggers.schema import TriggerDef, load_dir, load_file

GOOD = {
    "id": "daily-briefing",
    "enabled": True,
    "trigger": {"type": "schedule", "cron": "0 7 * * *", "timezone": "Asia/Manila"},
    "condition": {"weekdays": ["mon", "tue", "wed", "thu", "fri"]},
    "action": {"type": "prompt", "prompt": "Brief me.", "skills": ["google-workspace"]},
    "deliver": {"channel": "local"},
    "guardrails": {"max_runs_per_day": 1, "timeout_seconds": 180, "on_failure": "notify"},
}


def defn(**over) -> TriggerDef:
    raw = {**GOOD, **over}
    return TriggerDef.model_validate(raw)


# ----------------------------------------------------------------------
# Schema
# ----------------------------------------------------------------------


def test_the_shipped_trigger_is_valid():
    """The real file, not a fixture. It is what actually fires."""
    d = load_file(Settings().triggers_path / "daily-briefing.yaml")
    assert d.id == "daily-briefing"
    assert d.guardrails.max_runs_per_day == 1


def test_guardrails_are_mandatory():
    raw = {k: v for k, v in GOOD.items() if k != "guardrails"}
    with pytest.raises(ValidationError):
        TriggerDef.model_validate(raw)


def test_a_typo_in_a_guardrail_is_an_error_not_a_default():
    """`max_runs` instead of `max_runs_per_day` must not quietly mean 'no limit'."""
    raw = {**GOOD, "guardrails": {"max_runs": 1, "timeout_seconds": 180, "on_failure": "notify"}}
    with pytest.raises(ValidationError):
        TriggerDef.model_validate(raw)


def test_unknown_top_level_key_is_rejected():
    with pytest.raises(ValidationError):
        TriggerDef.model_validate({**GOOD, "delivery": {"channel": "telegram"}})


def test_bad_cron_field_count_rejected():
    with pytest.raises(ValidationError):
        defn(trigger={"type": "schedule", "cron": "0 7 * *", "timezone": "UTC"})


# ----------------------------------------------------------------------
# Compilation
# ----------------------------------------------------------------------


def test_weekdays_compile_to_digits_not_names():
    """Hermes' parse_schedule gates on ^[\\d\\*\\-,/]+$ - `mon-fri` never
    reaches croniter and is misread as a timestamp."""
    assert compile_cron(defn()) == "0 7 * * 1,2,3,4,5"


def test_weekdays_and_an_explicit_dow_field_conflict_loudly():
    d = defn(
        trigger={"type": "schedule", "cron": "0 7 * * 0", "timezone": "Asia/Manila"},
        condition={"weekdays": ["mon"]},
    )
    with pytest.raises(ValueError, match="day-of-week"):
        compile_cron(d)


def test_no_weekdays_leaves_the_cron_alone():
    assert compile_cron(defn(condition={})) == "0 7 * * *"


def test_job_payload_carries_only_fields_hermes_accepts():
    payload = compile_job(defn())
    assert set(payload) == {"name", "schedule", "prompt", "deliver", "skills"}
    assert payload["name"] == "isabella:daily-briefing"


def test_matching_job_shows_no_drift():
    assert job_drifted(defn(), as_hermes_returns_it(compile_job(defn()), "j1")) == {}


def test_the_parsed_schedule_hermes_returns_is_not_drift():
    """Hermes echoes the cron as {kind, expr, display}; PATCH wants the string.
    Comparing them naively made every reconcile PATCH forever."""
    job = as_hermes_returns_it(compile_job(defn()), "j1")
    assert isinstance(job["schedule"], dict)
    assert job_drifted(defn(), job) == {}


def test_null_skills_is_not_drift():
    """Hermes returns null for an empty list; that must not loop forever."""
    d = defn(action={"type": "prompt", "prompt": "Brief me.", "skills": []})
    job = {**as_hermes_returns_it(compile_job(d), "j1"), "skills": None}
    assert job_drifted(d, job) == {}


def test_changed_schedule_is_drift():
    job = as_hermes_returns_it({**compile_job(defn()), "schedule": "0 9 * * *"}, "j1")
    assert job_drifted(defn(), job) == {"schedule": "0 7 * * 1,2,3,4,5"}


# ----------------------------------------------------------------------
# Reconciliation
# ----------------------------------------------------------------------


def as_hermes_returns_it(payload: dict, job_id: str) -> dict:
    """Shape a job the way the live gateway does, not the way we sent it.

    Verified against Hermes 0.20.4: the cron string comes back parsed into
    {kind, expr, display}, and `skills` is mirrored into a legacy singular
    `skill`. A fake that echoes the request hides the drift bug this caused.
    """
    return {
        **payload,
        "id": job_id,
        "enabled": True,
        "schedule": {"kind": "cron", "expr": payload["schedule"], "display": payload["schedule"]},
        "skill": (payload.get("skills") or [None])[0],
    }


class FakeHermes:
    """Stands in for the jobs API, and records every write."""

    def __init__(self, jobs=None):
        self.jobs = {j["id"]: j for j in (jobs or [])}
        self.writes: list[tuple[str, str]] = []
        self._n = 0

    async def list_jobs(self):
        return list(self.jobs.values())

    async def create_job(self, payload):
        self._n += 1
        job = as_hermes_returns_it(payload, f"job-{self._n}")
        self.jobs[job["id"]] = job
        self.writes.append(("create", job["id"]))
        return job

    async def update_job(self, job_id, payload):
        patched = {**self.jobs[job_id], **payload}
        if "schedule" in payload:
            patched["schedule"] = {"kind": "cron", "expr": payload["schedule"],
                                   "display": payload["schedule"]}
        self.jobs[job_id] = patched
        self.writes.append(("update", job_id))
        return self.jobs[job_id]

    async def delete_job(self, job_id):
        self.jobs.pop(job_id, None)
        self.writes.append(("delete", job_id))

    async def run_job(self, job_id):
        self.writes.append(("run", job_id))
        return self.jobs[job_id]

    async def pause_job(self, job_id):
        self.jobs[job_id]["enabled"] = False
        self.writes.append(("pause", job_id))
        return self.jobs[job_id]

    async def resume_job(self, job_id):
        self.jobs[job_id]["enabled"] = True
        self.writes.append(("resume", job_id))
        return self.jobs[job_id]


@pytest.fixture
def env(tmp_path):
    tdir = tmp_path / "triggers"
    tdir.mkdir()
    (tdir / "daily-briefing.yaml").write_text(yaml.safe_dump(GOOD))
    cfg = Settings(
        db_path=tmp_path / "isabella.db",
        triggers_path=tdir,
        hermes_timezone="Asia/Manila",
    )
    hermes = FakeHermes()
    return cfg, hermes, Engine(cfg, hermes, tdir)


@pytest.mark.asyncio
async def test_reconcile_creates_then_does_nothing(env):
    """The property everything else rests on."""
    _cfg, hermes, engine = env

    first = await engine.reconcile()
    assert first.created == ["daily-briefing"]

    second = await engine.reconcile()
    assert second.unchanged == ["daily-briefing"]
    assert not second.changed
    assert [w[0] for w in hermes.writes] == ["create"]


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(env):
    _cfg, hermes, engine = env
    plan = await engine.reconcile(dry_run=True)
    assert plan.created == ["daily-briefing"]
    assert hermes.writes == []


@pytest.mark.asyncio
async def test_edited_yaml_patches_the_job(env):
    cfg, hermes, engine = env
    await engine.reconcile()

    edited = {**GOOD, "trigger": {"type": "schedule", "cron": "0 6 * * *", "timezone": "Asia/Manila"}}
    (cfg.triggers_path / "daily-briefing.yaml").write_text(yaml.safe_dump(edited))

    plan = await engine.reconcile()
    assert plan.updated == ["daily-briefing"]
    assert hermes.jobs["job-1"]["schedule"]["expr"] == "0 6 * * 1,2,3,4,5"


@pytest.mark.asyncio
async def test_disabling_in_yaml_removes_the_job(env):
    """`enabled: false` is a kill switch, not a paused job left to forget."""
    cfg, hermes, engine = env
    await engine.reconcile()

    (cfg.triggers_path / "daily-briefing.yaml").write_text(yaml.safe_dump({**GOOD, "enabled": False}))
    plan = await engine.reconcile()

    assert plan.deleted == ["daily-briefing"]
    assert hermes.jobs == {}


@pytest.mark.asyncio
async def test_deleted_yaml_removes_the_orphan(env):
    cfg, hermes, engine = env
    await engine.reconcile()
    (cfg.triggers_path / "daily-briefing.yaml").unlink()

    plan = await engine.reconcile()
    assert plan.deleted == ["daily-briefing"]
    assert hermes.jobs == {}


@pytest.mark.asyncio
async def test_reconcile_never_touches_a_job_it_does_not_own(env):
    """Selene's jobs, and anything made by `hermes cron`, share the instance.
    Deleting one is not a recoverable mistake."""
    cfg, _hermes0, engine = env
    foreign = as_hermes_returns_it(
        {"name": "backup-photos", "schedule": "0 3 * * *", "prompt": "back up"}, "x1"
    )
    hermes = FakeHermes([foreign])
    engine = Engine(cfg, hermes, cfg.triggers_path)

    await engine.reconcile()
    await engine.reconcile()

    assert hermes.jobs["x1"] == foreign
    assert all(w[1] != "x1" for w in hermes.writes)


@pytest.mark.asyncio
async def test_timezone_mismatch_refuses_rather_than_firing_wrong(env):
    """Hermes has no per-job timezone. Reconciling anyway means the briefing
    arrives hours off, every day, with nothing in the logs to say why."""
    cfg, hermes, _ = env
    cfg = cfg.model_copy(update={"hermes_timezone": "Europe/Copenhagen"})
    engine = Engine(cfg, hermes, cfg.triggers_path)

    with pytest.raises(TimezoneMismatch, match="Asia/Manila"):
        await engine.reconcile()
    assert hermes.writes == []


# ----------------------------------------------------------------------
# Guardrails at runtime
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_fire_is_recorded_before_it_is_triggered(env):
    cfg, _hermes, engine = env
    await engine.reconcile()

    result = await engine.fire("daily-briefing")
    assert result["ok"]

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    conn.close()
    assert len(runs) == 1
    assert runs[0]["source"] == "manual"
    # Not "delivered": Hermes runs it asynchronously and she cannot see the end.
    assert runs[0]["outcome"] == "triggered"


@pytest.mark.asyncio
async def test_max_runs_per_day_applies_to_manual_fires_too(env):
    _cfg, hermes, engine = env
    await engine.reconcile()

    assert (await engine.fire("daily-briefing"))["ok"]
    second = await engine.fire("daily-briefing")

    assert second["ok"] is False
    assert second["reason"] == "rate_limited"
    assert [w for w in hermes.writes if w[0] == "run"] == [("run", "job-1")]


@pytest.mark.asyncio
async def test_a_failed_run_is_recorded_as_an_error_not_lost(env):
    cfg, hermes, engine = env
    await engine.reconcile()

    async def boom(job_id):
        raise RuntimeError("gateway died mid-run")

    hermes.run_job = boom
    with pytest.raises(RuntimeError):
        await engine.fire("daily-briefing")

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    conn.close()
    assert runs[0]["outcome"] == "error"
    assert "gateway died" in runs[0]["detail"]


@pytest.mark.asyncio
async def test_pause_stops_it_at_hermes(env):
    _cfg, hermes, engine = env
    await engine.reconcile()

    await engine.pause("daily-briefing")
    assert hermes.jobs["job-1"]["enabled"] is False

    await engine.resume("daily-briefing")
    assert hermes.jobs["job-1"]["enabled"] is True


@pytest.mark.asyncio
async def test_unknown_trigger_is_not_found_not_a_crash(env):
    _, _, engine = env
    assert await engine.pause("no-such-trigger") is None
    assert await engine.fire("no-such-trigger") is None


# ----------------------------------------------------------------------
# The client's contract with Hermes
# ----------------------------------------------------------------------


def _client(handler) -> HermesClient:
    cfg = Settings(hermes_api_key="test-key")
    c = HermesClient(cfg)
    c._http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url=cfg.hermes_base_url
    )
    return c


@pytest.mark.asyncio
async def test_client_drops_fields_the_jobs_api_would_silently_ignore():
    """create_job takes `model` and `enabled_toolsets`; the HTTP surface does
    not pass them on. Sending them anyway looks like they applied."""
    seen = {}

    def handler(request):
        seen.update(__import__("json").loads(request.content))
        return httpx.Response(200, json={"job": {"id": "j1"}})

    c = _client(handler)
    await c.create_job({"name": "isabella:x", "schedule": "0 7 * * *", "prompt": "hi",
                        "model": "qwen3:8b-16k", "enabled_toolsets": ["terminal"]})
    assert "model" not in seen
    assert "enabled_toolsets" not in seen


@pytest.mark.asyncio
async def test_saved_but_not_scheduled_is_an_error_not_a_success():
    """424: the job exists and will never fire. A 2xx-only check misses it."""
    from core.hermes.errors import JobRejected

    c = _client(lambda r: httpx.Response(424, json={"error": "scheduler registration failed"}))
    with pytest.raises(JobRejected) as exc:
        await c.create_job({"name": "isabella:x", "schedule": "0 7 * * *", "prompt": "hi"})
    assert exc.value.status == 424


def test_duplicate_ids_across_files_are_rejected(tmp_path):
    for name in ("a.yaml", "b.yaml"):
        (tmp_path / name).write_text(yaml.safe_dump(GOOD))
    with pytest.raises(ValueError, match="duplicate"):
        load_dir(tmp_path)


# ----------------------------------------------------------------------
# The kill switch has to survive a reconcile
# ----------------------------------------------------------------------


def test_a_paused_job_is_not_re_enabled_by_drift():
    """`enabled: true` in the YAML must not undo a pause. A kill switch that
    lasts until the next reconcile is not a kill switch."""
    job = as_hermes_returns_it(compile_job(defn()), "j1")
    job |= {"enabled": False, "state": "paused", "paused_at": "2026-08-23T08:34:36+02:00"}
    assert "enabled" not in job_drifted(defn(), job)


def test_edits_still_reach_a_paused_job():
    """Pause freezes whether it runs, not what it would do."""
    job = as_hermes_returns_it({**compile_job(defn()), "schedule": "0 9 * * *"}, "j1")
    job |= {"enabled": False, "state": "paused", "paused_at": "2026-08-23T08:34:36+02:00"}
    assert job_drifted(defn(), job) == {"schedule": "0 7 * * 1,2,3,4,5"}


@pytest.mark.asyncio
async def test_pause_survives_reconcile_end_to_end(env):
    _cfg, hermes, engine = env
    await engine.reconcile()
    await engine.pause("daily-briefing")
    hermes.jobs["job-1"] |= {"state": "paused", "paused_at": "2026-08-23T08:34:36+02:00"}

    plan = await engine.reconcile()

    assert not plan.changed
    assert hermes.jobs["job-1"]["enabled"] is False


def test_duplicate_jobs_are_deduped_oldest_wins():
    """Hermes does not enforce unique job names. Keying by name would let one
    shadow the other while both kept firing."""
    from core.triggers.engine import _owned

    old = {"name": "isabella:daily-briefing", "id": "a", "created_at": "2026-08-23T08:00:00+02:00"}
    new = {"name": "isabella:daily-briefing", "id": "b", "created_at": "2026-08-23T09:00:00+02:00"}
    group = _owned([new, old])["isabella:daily-briefing"]
    assert [j["id"] for j in group] == ["a", "b"]


@pytest.mark.asyncio
async def test_reconcile_deletes_a_duplicate_rather_than_firing_twice(env):
    _cfg, hermes, engine = env
    await engine.reconcile()
    dupe = as_hermes_returns_it(compile_job(defn()), "job-dupe")
    dupe["created_at"] = "2099-01-01T00:00:00+00:00"
    hermes.jobs["job-dupe"] = dupe

    await engine.reconcile()

    assert "job-dupe" not in hermes.jobs
    assert "job-1" in hermes.jobs


# ----------------------------------------------------------------------
# Scheduled runs: Isabella is not in the path, so she has to pull them
# ----------------------------------------------------------------------


def execution(exec_id="e1", status="completed", error=None, source="builtin"):
    """Timestamps relative to now, not hardcoded.

    A manual fire opens its row at `now()` and the execution is claimed just
    after; the sync links them by that ordering. Fixed dates made this pass or
    fail depending on what day it was run - which it duly did.
    """
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    return {
        "id": exec_id,
        "source": source,
        "status": status,
        "claimed_at": (now + timedelta(seconds=1)).isoformat(),
        "started_at": (now + timedelta(seconds=2)).isoformat(),
        "finished_at": (now + timedelta(seconds=42)).isoformat(),
        "error": error,
    }


@pytest.mark.asyncio
async def test_a_scheduled_run_becomes_visible(env):
    """The whole point: cron fires without her, and she still knows."""
    cfg, hermes, engine = env
    await engine.reconcile()
    hermes.jobs["job-1"]["latest_execution"] = execution()

    assert await engine.sync_runs() == {"inserted": 1, "linked": 0, "unchanged": 0}

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    conn.close()
    assert runs[0]["outcome"] == "ok"
    assert runs[0]["execution_id"] == "e1"


@pytest.mark.asyncio
async def test_syncing_twice_does_not_duplicate(env):
    _cfg, hermes, engine = env
    await engine.reconcile()
    hermes.jobs["job-1"]["latest_execution"] = execution()

    await engine.sync_runs()
    assert await engine.sync_runs() == {"inserted": 0, "linked": 0, "unchanged": 1}


@pytest.mark.asyncio
async def test_a_failed_run_carries_the_reason(env):
    """`blocked_config` is the real failure today; the reason is the useful part."""
    cfg, hermes, engine = env
    await engine.reconcile()
    hermes.jobs["job-1"]["latest_execution"] = execution(
        status="failed", error="[blocked_config] attached skill 'google-workspace' is not ready"
    )
    await engine.sync_runs()

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    conn.close()
    assert runs[0]["outcome"] == "error"
    assert "blocked_config" in runs[0]["detail"]


@pytest.mark.asyncio
async def test_a_manual_fire_is_not_counted_twice(env):
    """The manual row is opened before Hermes has an execution id. Inserting a
    second row on sync would show one press as two runs - and burn two of the
    day's allowance."""
    cfg, hermes, engine = env
    await engine.reconcile()
    await engine.fire("daily-briefing")
    hermes.jobs["job-1"]["latest_execution"] = execution(source="manual")

    assert await engine.sync_runs() == {"inserted": 0, "linked": 1, "unchanged": 0}

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    assert len(runs) == 1
    # The optimistic "triggered" is corrected by what actually happened.
    assert runs[0]["outcome"] == "ok"
    assert runs[0]["source"] == "manual"
    assert store.runs_today(conn, "daily-briefing") == 1
    conn.close()


@pytest.mark.asyncio
async def test_a_run_still_in_flight_is_updated_when_it_finishes(env):
    cfg, hermes, engine = env
    await engine.reconcile()
    hermes.jobs["job-1"]["latest_execution"] = execution(status="running")
    await engine.sync_runs()

    hermes.jobs["job-1"]["latest_execution"] = execution(status="failed", error="timed out")
    assert await engine.sync_runs() == {"inserted": 0, "linked": 1, "unchanged": 0}

    conn = store.connect(cfg)
    runs = store.recent_runs(conn, "daily-briefing")
    conn.close()
    assert len(runs) == 1
    assert runs[0]["outcome"] == "error"


@pytest.mark.asyncio
async def test_a_scheduled_run_counts_against_the_daily_limit(env):
    """Otherwise the rate limit only governs what she was asked to do."""
    _cfg, hermes, engine = env
    await engine.reconcile()
    hermes.jobs["job-1"]["latest_execution"] = execution()
    await engine.sync_runs()

    assert (await engine.fire("daily-briefing"))["reason"] == "rate_limited"


def test_run_timestamps_are_stored_in_utc(tmp_path):
    """Hermes reports local time. `runs_today` compares strings, so a run at
    01:00 +02:00 - yesterday in UTC - would otherwise eat today's allowance."""
    cfg = Settings(db_path=tmp_path / "i.db", triggers_path=tmp_path)
    conn = store.connect(cfg)
    store.record_execution(
        conn, trigger_id="daily-briefing", job_id="j1",
        execution={**execution(), "started_at": "2026-08-24T07:00:01+02:00"},
    )
    row = store.recent_runs(conn, "daily-briefing")[0]
    conn.close()
    assert row["started_at"] == "2026-08-24T05:00:01+00:00"


# ----------------------------------------------------------------------
# Pre-fetched context: data in the prompt instead of tools in the model
# ----------------------------------------------------------------------


SCRIPTED = {**GOOD, "action": {**GOOD["action"], "script": "briefing_fetch.py", "skills": []}}


def test_a_script_must_be_a_bare_filename():
    """Hermes resolves it inside HERMES_HOME/scripts/ and refuses escapes, so a
    path here is a mistake rather than a feature."""
    for bad in ("../../etc/passwd", "/abs/path.py", "sub/dir.py"):
        with pytest.raises(ValidationError):
            TriggerDef.model_validate({**GOOD, "action": {**GOOD["action"], "script": bad}})


@pytest.mark.asyncio
async def test_a_script_job_is_not_created_over_http(env):
    """POST /api/jobs drops `script` silently. Creating anyway would look
    reconciled and brief from nothing."""
    from core.triggers.engine import ScriptJobNotCreatable

    cfg, hermes, engine = env
    (cfg.triggers_path / "daily-briefing.yaml").write_text(yaml.safe_dump(SCRIPTED))

    with pytest.raises(ScriptJobNotCreatable, match="briefing_fetch.py"):
        await engine.reconcile()
    assert hermes.writes == []


def test_the_refusal_hands_back_a_command_that_works():
    from core.triggers.compile import create_command

    cmd = create_command(TriggerDef.model_validate(SCRIPTED))
    assert "hermes cron create" in cmd
    assert "--script briefing_fetch.py" in cmd
    assert "--name isabella:daily-briefing" in cmd
    assert '"0 7 * * 1,2,3,4,5"' in cmd


def test_script_drift_is_reported_not_silently_tolerated():
    """`script` is not in PATCH's whitelist, so this can only be reported."""
    from core.triggers.compile import script_mismatch

    d = TriggerDef.model_validate(SCRIPTED)
    job = as_hermes_returns_it(compile_job(d), "j1")
    assert script_mismatch(d, {**job, "script": "briefing_fetch.py"}) is None
    assert "something_else.py" in script_mismatch(d, {**job, "script": "something_else.py"})


@pytest.mark.asyncio
async def test_an_existing_script_job_reconciles_normally(env):
    """Once created by hand, everything else is managed from the YAML."""
    cfg, hermes, engine = env
    (cfg.triggers_path / "daily-briefing.yaml").write_text(yaml.safe_dump(SCRIPTED))
    d = TriggerDef.model_validate(SCRIPTED)
    hermes.jobs["job-1"] = {
        **as_hermes_returns_it(compile_job(d), "job-1"), "script": "briefing_fetch.py",
    }

    assert not (await engine.reconcile()).changed

    edited = {**SCRIPTED, "deliver": {"channel": "telegram"}}
    (cfg.triggers_path / "daily-briefing.yaml").write_text(yaml.safe_dump(edited))
    assert (await engine.reconcile()).updated == ["daily-briefing"]
    assert hermes.jobs["job-1"]["deliver"] == "telegram"
    assert hermes.jobs["job-1"]["script"] == "briefing_fetch.py"


def test_a_stale_installed_script_is_caught(tmp_path):
    """Same trap as SOUL.md, one directory over: the repo is the source, but
    Hermes only ever runs the installed copy."""
    repo, installed = tmp_path / "scripts", tmp_path / "hermes-scripts"
    repo.mkdir(); installed.mkdir()
    cfg = Settings(db_path=tmp_path / "i.db", scripts_path=repo, hermes_scripts_path=installed)

    (repo / "briefing_fetch.py").write_text("print('v2')")
    assert store.script_status(cfg, "briefing_fetch.py")["drifted"] is True  # not installed

    (installed / "briefing_fetch.py").write_text("print('v1')")
    status = store.script_status(cfg, "briefing_fetch.py")
    assert status["drifted"] is True
    assert "not version-controlled" in status["detail"]

    (installed / "briefing_fetch.py").write_text("print('v2')")
    assert store.script_status(cfg, "briefing_fetch.py")["drifted"] is False


def test_the_shipped_script_is_installed_and_current():
    """The real pair, not a fixture. If this fails, Hermes is running code the
    repo does not contain."""
    d = load_file(Settings().triggers_path / "daily-briefing.yaml")
    status = store.script_status(Settings(), d.action.script)
    assert status["installed"], status["detail"]
    assert not status["drifted"], status["detail"]
