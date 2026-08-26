# Roadmap

## The sequencing rule

**Each milestone must be usable on its own before the next one starts.**

Not "compiles." Not "tested." *Used* - as in I actually got value from it in real life
before the next milestone begins. Four ambitions were named at charter time (life ops,
second brain, dev copilot, proactive daemon). Building all four in parallel produces
none of them.

If a request belongs to a later milestone, it waits. Say so out loud rather than
quietly widening the current one.

---

## M0 - Charter ✅

**Goal:** Write down what Isabella is, before any code exists to argue with.

**Done when**
- `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `CLAUDE.md` exist and agree with each other
- The Isabella/Hermes ownership boundary is unambiguous
- Her character exists: `Personality/` (19 files), `BIOGRAPHY.md`, `ORIGIN.md`
- A compiled runtime prompt exists and has been **probed against a real model**
- Repo has its first commit

**Out of scope:** all code, dependency installs, directory scaffolding.

---

## M1 - Hermes handshake ✅

**Goal:** Isabella talks to Hermes and answers *as Isabella*, not as a generic model.

The smallest possible thing that proves the whole premise: a persona layer on Isabella's
side, an HTTP call to Hermes, a reply that sounds like her.

**Build**
- `core/hermes/` - typed client. Bearer auth, base URL from env, one place all Hermes
  calls funnel through. `POST /v1/chat/completions` and `GET /health` only.
- `core/persona/` - load `Personality/compiled/core.md`. **Do not concatenate the corpus**;
  it is ~27,000 tokens against a 16,384 window (see `HISTORY.md`).
- Model name, base URL and key from env. `qwen3:4b-16k` to start - a `-16k` Modelfile build,
  never a stock model, because Ollama's `/v1` ignores `num_ctx` and silently gives you 4096.
- **Handle empty `content`.** qwen3 reasons before answering; exhausting `max_tokens`
  mid-thought returns empty content with `finish_reason: length`. A real error path, not a
  crash.
- `core/api/` - FastAPI with `POST /chat` and `GET /health`.
- SQLite bootstrap: `persona_versions` table.
- `.env.example`, `uv` project, `ruff`, `pytest`.

**Done when**
- **Voice test, not a plumbing test:** she sounds like `Personality/`, draws on
  `BIOGRAPHY.md`, and claims no history she doesn't have
- `curl -X POST localhost:8000/chat -d '{"message":"who are you?"}'` returns a reply in
  Isabella's voice
- Isabella's `/health` reports whether Hermes is reachable
- Killing Hermes produces a clean, useful error - not a stack trace

**Out of scope:** web UI, triggers, sessions, memory, any scheduling.

**Landed 2026-08-23.** Both done-when criteria met; see `HISTORY.md`. Carried into M2:
the API is unauthenticated on loopback, and replies take 8-90s because qwen3 reasons
before answering.

---

## M2 - Daily briefing daemon ⭐

**The first slice that earns its keep.** Everything before this is plumbing.

**Goal:** She wakes up on her own, reads my calendar and email, and sends me a briefing
before I ask. Autonomy, end to end, once.

**Prerequisite: the L1 permission floor.** Before anything fires unattended, set Hermes'
env floor and `platform_toolsets` by hand - `TERMINAL_ENV=docker`, `HERMES_MAX_ITERATIONS`,
`HERMES_WRITE_SAFE_ROOT`, and no `HERMES_YOLO_MODE`. This is P0 in `PERMISSIONS.md`, and
the briefing must not be the thing that discovers the floor is missing.

**Build**
- `triggers/daily-briefing.yaml` - the trigger schema from `ARCHITECTURE.md`, made real
  for exactly one trigger.
- `core/triggers/` - parse the YAML, reconcile it into a Hermes job via `POST /api/jobs`.
  Idempotent: running reconcile twice changes nothing.
- Briefing composition: the prompt, the skills (`calendar`, `email`), what belongs in a
  briefing and what doesn't.
- Delivery through Telegram via Hermes' connector - chosen because it needs no inbound
  network, so the remote-access decision stays deferred.
- Guardrails: `max_runs_per_day`, timeout, `on_failure: notify`.
- `runs` table - every execution recorded before delivery.

**Done when**
- I wake up on a real morning to a briefing I did not ask for
- It's good enough that I'd miss it if it stopped
- `POST /api/jobs/{id}/pause` kills it instantly, and I've verified that

**Out of scope:** web UI, more than one trigger, generalized trigger engine, voice.

**The honest checkpoint:** if the briefing isn't useful, the fix is the *prompt and the
composition logic*, not more architecture. Iterate here before building anything else.

**Status 2026-08-26 - the pipeline runs end to end; only the credentials are missing.**
Fired by hand, the whole chain works: cron -> `briefing_fetch.py` -> stdout injected as
prompt context -> a model with **zero** toolsets writes the briefing -> the run lands in
`runs` with `outcome: ok`. Her output was *"Sir. No calendar or unread emails accessible -
authentication required for google-workspace... You're forgetting the google-workspace skill
needs authorising."* That is the correct briefing for a morning with no credentials: she
reported the blind spot rather than inventing a day.

Resolved since: **timezone** is `Europe/Copenhagen` on both sides, **execution** is
settled by pre-fetching rather than granting toolsets (`platform_toolsets.cron: []`), and
**Google authorisation** now has a flow - a Connect panel in the web UI, read-only scopes,
token written server-side (`ARCHITECTURE.md` §Open decision, resolved). The one thing still
outstanding is **delivery**, held at `local` by decision.
The done-when criteria are unchanged and none is met yet - nobody has woken up to a
briefing. Until the token exists she runs every weekday and reports the blind spot, which
is the correct behaviour rather than a broken one.

**Earlier status, 2026-08-23 - engine built, briefing blocked.** `core/triggers/` reconciles
`triggers/daily-briefing.yaml` into Hermes job `isabella:daily-briefing`; idempotency,
pause and resume are verified against the live gateway. The `runs` table records manual
fires. Three things still stand between this and a briefing, none of them code:

| | |
|---|---|
| Google OAuth | **Resolved 2026-08-26** - a Connect Google panel in `web/` drives the skill's `setup.py`; scopes decided as read-only Gmail + Calendar. The mechanism exists; the grant is not given until Owen clicks through Google's consent screen. Superseded text follows: **Deferred 2026-08-26.** Not a missing file - a flow: pick account and scopes, consent in a browser, redirect, exchange, store the refresh token. `setup.py` does this from a terminal and is likely enough for an audience of one; a "Connect Google" button is M3 work. Decide the *scopes* first - they become her real ceiling for Google. See `ARCHITECTURE.md` §Open decision |
| ~~Execution for the cron path~~ | **Resolved 2026-08-26** by pre-fetching: a script gathers the data, the model gets no tools at all |
| ~~Timezone~~ | **Resolved 2026-08-26**: `Europe/Copenhagen`, set explicitly on both sides |

Telegram is unconfigured, so delivery is `local` - the fourth thing, and the one that
decides whether a briefing reaches him at all. **Correction 2026-08-26:** an earlier version
of this line said the job was paused. It is not, and has not been - it is active and fires
07:00 on weekdays. `hermes cron list` hides paused jobs rather than showing them, which is
how the wrong belief survived; `--all` is the flag that tells the truth.

---

## M3 - Web UI ⭐

**Goal:** A place to talk to her and see what she's been doing.

**Started 2026-08-26, out of order, deliberately.** M2's done-when is *not* met - nobody has
woken up to a briefing, and delivery is still `local`. Owen chose to build the reading
surface first, with the tradeoff stated: a page you have to visit is not a briefing that
arrives. What that bought is that the briefing is no longer written into a file nobody
opens.

Landed in the first slice: `web/` (React + Vite + pnpm), Briefings with the real text read
back from Hermes' cron output, Triggers with pause/resume/run-now verified against the live
gateway, and Chat. Second slice: the Selene design system, a Connect Google panel, a Body
view of her own runtime, `open logs` into Terminal.app - and **no buttons**. Every action is
a palette command (`K`), views are `1`-`5`.

**That last one is aimed at M6.** Voice control was asked for; voice itself is M6 and she has
no STT or TTS. The step available now is the layer underneath - a command router - so speech
later feeds the same list instead of needing a second control surface. Buttons would have
been the thing to throw away.

**The HUD is the destination, not the next step**, on the authority of the design note that
proposes it: *a HUD with no voice is a wall of telemetry with nothing to talk to.* Its panels
also want data she does not have. The register landed; the instrument panel waits for M6.

Still open from the build list below: **SSE streaming** - which matters at 8-90s per reply -
and the run-now path being visible while it runs.

**Build**
- `web/` - React + Vite, `pnpm`. Talks only to Isabella's API; never holds the Hermes key.
- Chat over `POST /chat`, streaming via Hermes' Runs API (`/v1/runs/{id}/events`, SSE).
- Trigger list: view, enable/disable, run-now.
- Briefing history from the `runs` table.
- Stable `X-Hermes-Session-Key` per surface so memory scopes correctly.

**Done when** I use the web UI in preference to the terminal, and can pause a trigger
from it.

**Out of scope:** auth (loopback only), mobile layout, remote access.

---

## M4 - Trigger engine generalized

**Goal:** Adding a new automation means writing YAML, not writing code.

**Build**
- Full trigger schema: `schedule`, `webhook`, `event`, `manual`; conditions; all three
  action types.
- Hot reload - file change reconciles without a restart.
- `POST /triggers/{id}/fire` webhook endpoint, so external systems (n8n, Zapier,
  GitHub Actions, Home Assistant) can call her.
- Full reconciliation: create, update, delete, orphan cleanup.
- 2–3 real triggers beyond the briefing, driven by actual need.

**Done when** I add a useful automation end-to-end without touching Python.

---

## M5 - Portability

**Goal:** She runs wherever I put her.

**Build**
- `docker-compose.yml` - Isabella API, web UI, Hermes on one network.
- ARM64 build (Pi, Apple silicon). All config via environment.
- Documented per-host setup and what degrades where.
- **Decide remote access.** Tailscale is the standing recommendation; see
  `ARCHITECTURE.md`. This milestone is where the decision gets made, not deferred again.

**Done when** she's running on a second device with the same state and the same triggers.

---

## M6 - Voice and more channels

**Goal:** Talk to her out loud; reach her wherever I already am.

Voice and additional connectors (Slack, iMessage on macOS, email) come from Hermes.
This milestone is configuration and persona adaptation per surface - she should be terse
out loud and fuller in writing - not new infrastructure.

**The UI is already built for this.** M3 removed every button in favour of a command
palette, so voice arrives as a new *front end* on an existing command list rather than as a
parallel control surface. When it lands, the HUD layout from
`vault/Projects/selene/Design` becomes buildable for the first time - it is voice-first by
design, and its own note says so.

**Done when** I've had a useful spoken conversation with her.

---

## Deferred - deliberately not now

Each of these is real and wanted. None is next.

| | Why it waits |
|---|---|
| **Second-brain ingest** | Needs M4's event triggers and a clear answer on where knowledge lives given that memory is Hermes'. Genuinely unsolved - don't start it early. |
| **Dev copilot / repo watching** | Wants M4 webhooks. GitHub Actions → `POST /triggers/{id}/fire` is nearly free once that exists. |
| **Self-hosted n8n** | The native trigger system was chosen over it. Revisit only if a specific integration is painful to build and n8n already has it - and then only behind the webhook endpoint. |
| **Multi-user / sharing** | Audience of one. Not a goal. |
| **Full `permit()` gate** | `PERMISSIONS.md` P1-P6 runs alongside these milestones on its own phasing. Only P0 - the Hermes-side floor - blocks M2. |
| **Sub-agents** | Hermes has them. Use them when a real task needs delegation, not before. |
