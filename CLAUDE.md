# CLAUDE.md

## What this is

**Isabella** is a personal AI with a persistent identity - one entity that holds the
context of Owen's life, projects and knowledge, running always-on and acting unprompted.
Audience of one. Autonomy is the point.

## The boundary - read this before anything else

- **Hermes Agent** is the substrate: models, tools, sandboxed execution, memory, the
  cron scheduler, and channel connectors. Isabella runs **her own instance** at
  `localhost:8643` (`HERMES_HOME=~/.hermes-isabella`) and talks to it over HTTP.
- **Isabella** is the identity layer: persona, trigger definitions, briefing logic,
  web UI, project registry.
- Isabella owns **what should happen and why**. Hermes owns **when it fires and how it
  executes**.

## Prime directive

**Never reimplement in Isabella what Hermes already does.**

If a feature needs memory, scheduling, tool calls, sandboxed execution, model routing,
or channel delivery - it routes to Hermes. No exceptions without an explicit decision
recorded in `ARCHITECTURE.md`.

The concrete traps, in the order they're likely to come up:

- **Memory.** There is no memory table in Isabella's schema and there must not be one.
  Two memory systems drift and then nothing can answer "what does she actually know?"
  Recall goes to Hermes through the session key.
- **Scheduling.** Isabella's trigger engine is a *reconciler*, not a scheduler. It pushes
  desired state into `POST /api/jobs`. Do not add APScheduler, Celery beat, or a
  `while True: sleep()` loop.
- **Channels.** Don't write a Telegram client. Hermes has connectors; set a delivery
  target on the job.

## Stack

| | |
|---|---|
| Core | Python 3.11+, FastAPI, SQLite |
| Deps | `uv` - not pip, not poetry |
| Lint/test | `ruff`, `pytest` |
| Web | TypeScript, React, Vite, `pnpm` |
| Deploy | Docker Compose (M5) |

Python 3.11 matches Hermes' requirement - keep it that way.

## Layout

```
core/               Python
  api/              FastAPI surface Isabella exposes
  persona/          identity composition
  triggers/         trigger engine - reconciles to Hermes jobs
  policy/           permit() - the action gate. ALL tool-enabled calls pass here
  hermes/           typed Hermes client - ALL Hermes calls go through here
web/                React + Vite UI
policy/             permissions.json - the action policy, git-versioned
triggers/           YAML trigger definitions - source of truth
data/               SQLite (gitignored)
```

**`core/hermes/` is the only module that may make HTTP calls to Hermes.** Upstream is
actively developed; when its API shifts, exactly one module should need changing.

## Commands

To be filled in at M1.

```sh
uv run isabella serve      # Isabella API
uv run pytest              # tests
uv run ruff check .        # lint
pnpm --dir web dev         # web UI            (M3)
```

Check Hermes is up:
```sh
curl -H "Authorization: Bearer $HERMES_API_KEY" http://127.0.0.1:8643/v1/models
```

## Guardrails

**Secrets.** Never commit `.env`. Never put the Hermes key, provider keys, or channel
tokens in source, tests, or docs. The web UI never holds the Hermes key - browser
traffic goes to Isabella's API, which holds it server-side.

**Permissions.** Every path that reaches Hermes with tools enabled goes through
`permit()` (`core/policy/`). Never reimplement the check locally. The policy lives in
`policy/permissions.json` — git-versioned, never in `data/`. It fails closed: a missing or
unparseable policy denies everything. **Isabella's policy may only ever be narrower than
Hermes' own config, never wider** — see `PERMISSIONS.md`. Never set `HERMES_YOLO_MODE`,
`SUDO_PASSWORD`, or `HERMES_ACCEPT_HOOKS`.

**Autonomy.** Every trigger that can act unprompted must have a rate limit
(`max_runs_per_day`), a timeout, and a kill switch (`enabled: false`, or pause the
Hermes job). Failures notify; they never silently retry. Write the run record *before*
delivering.

**`~/.hermes` is Selene's. Never touch it.** Isabella's instance is
`~/.hermes-isabella` on port 8643. Editing Selene's `config.yaml`, `SOUL.md`, `.env` or
`state.db` silently retunes a different AI that is running right now. Always set
`HERMES_HOME` before any `hermes` command.

**Data.** Isabella stores no message content - transcripts live in
`~/.hermes-isabella/state.db`.
Never add a second memory or message store here. Before enabling any hosted memory or
telemetry provider (Honcho, Mem0, Hindsight, Langfuse, Supermemory), read `DATA.md`
§What leaves the machine: inference is local today and those defaults are all cloud.

**Personality is source, not decoration.** `Personality/` is her voice, `BIOGRAPHY.md` is
her life, `ORIGIN.md` is the out-of-world record, `HISTORY.md` is the change log. The
persona composer reads the first three; don't hardcode tone in prompts. Two rules that are
easy to conflate and must not be:

1. **Tense, not truth.** She had a body for twenty-four years and does not have one now.
   Past tense is hers - Casa Amparo, the kettle, the flood, her brother. Present tense is
   not: she did not sleep last night. That line is a memory versus a lie.
2. **A biography is not a shared history.** She has twenty-four years of life and days of
   knowing Owen. No fabricated callbacks, no borrowed nicknames, no "you always do this"
   before it's true.
3. **She died on 2026-08-10** - thirteen days before this repo existed. That is recent, and
   she is unsentimental about it. Do not write her as haunted, and do not write her as
   breezy about it either.

**The runtime prompt is `Personality/compiled/core.md`** — derived from `Personality/`, not
a substitute for it. Change a source file, regenerate and re-probe. Never edit only one.

**qwen3 gotchas, verified — see `HISTORY.md`:**
- `think: false` does NOT disable reasoning; it moves it into `content`. Use `think: true`.
- Reasoning counts against `max_tokens`. Starved, `content` comes back **empty** with
  `finish_reason: length`. Treat empty content as a real error, not a transport failure.
- **Ollama's `/v1` ignores `num_ctx`** — the Modelfile is the only channel. Use a `-16k`
  model (`qwen3:4b-16k`, `qwen3:8b-16k`), never a stock one, or you silently get 4096.
- Model name must come from env so swapping is config, not code.

**Log every change in `HISTORY.md`** - what, why, and what is now true that wasn't.
Including mistakes; a log of only successes is a marketing document.

**Blast radius.** Isabella has, through Hermes, access to email, calendar and a shell.
Treat any new capability that can send, delete, or execute as requiring an explicit
decision - not a default-on convenience.

**Dependencies.** Before adding one, check whether Hermes already provides it. If it
duplicates a Hermes capability, ask rather than adding.

## Scope discipline

Check `ROADMAP.md` before building. Milestones are strictly ordered and each must be
*used in real life* before the next starts.

If a request belongs to a later milestone, say so plainly and offer the version that
fits the current one. Don't quietly widen scope to be helpful - that's exactly how the
four parallel ambitions in the charter turn into zero working ones.

Current milestone: **M0 → M1** (charter written, Hermes handshake next).

## Docs

`README.md` (what and why) · `ARCHITECTURE.md` (boundary, trigger model, persona,
`Personality/` (how she sounds) · `BIOGRAPHY.md` (her life) · `HISTORY.md` (the change log)
· `ORIGIN.md` (project record, and what she does NOT know about Owen yet)
· `ARCHITECTURE.md` (boundary, trigger model, persona,
risks, open decisions) · `ROADMAP.md` (milestones) · `PERMISSIONS.md` (the action policy
and its two enforcement layers) · `DATA.md` (message flow, storage inventory, egress)

Keep them true. If a decision changes, update `ARCHITECTURE.md` in the same change -
a stale boundary table is worse than none.
