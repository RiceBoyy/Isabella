# Isabella

A personal AI with a persistent identity - one entity that knows the whole context of
my life, my projects, and what I've learned, running somewhere always-on, reachable
from whatever device I happen to be holding.

## Why she exists

I don't want another chat window. I want something that *already knows* - that has been
running while I was asleep, has read the calendar and the inbox, noticed that the deploy
failed, and has an opinion about what my day looks like before I ask.

The specific gap: context is scattered across my calendar, email, notes, repos, and
messages, and every assistant I've used starts from zero every time. Isabella is the
attempt to have one place that holds all of it and *acts on it unprompted*.

**Autonomy is the point.** If she only ever responds when spoken to, this project failed.

## What she is not

- **Not a chatbot.** Chat is one surface, not the product.
- **Not a Hermes fork.** Hermes Agent is a dependency she talks to over HTTP. Her code
  and Hermes' code stay separate.
- **Not a product.** Audience of one. No auth system, no onboarding, no multi-tenancy.

## Architecture in five lines

- **Hermes Agent** is the substrate: models, tools, sandboxed execution, memory,
  the cron scheduler, and the channel connectors (Telegram, Discord, Slack, WhatsApp,
  Signal, Email, CLI).
- **Isabella** is the identity and orchestration layer on top of it - see
  [Personality/](Personality/) and [BIOGRAPHY.md](BIOGRAPHY.md) for who that identity is.
- She owns *who she is* (persona), *what should happen and why* (triggers), and
  *how I see it* (web UI).
- Hermes owns *when things fire* and *how they execute*.
- They meet at Hermes' HTTP API on `localhost:8643` - Isabella's own Hermes
  instance, separate from Selene's on 8642.

Full detail, including the ownership boundary table: **[ARCHITECTURE.md](ARCHITECTURE.md)**

## Status

**M0 - Charter.** These documents exist; no application code yet. See
[ROADMAP.md](ROADMAP.md) for what lands next.

## Quick start

> Aspirational - none of this runs until **M1** lands. Documented now so the target
> is unambiguous.

**Prerequisites**

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and running
  (Python 3.11):
  ```sh
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
  ```
- **A Hermes instance of her own.** `~/.hermes` belongs to Selene; Isabella must not
  share it. `HERMES_HOME` scopes the config directory, the gateway PID file and the
  service name, so a second instance is a supported pattern:
  ```sh
  export HERMES_HOME=~/.hermes-isabella
  hermes gateway            # her own state.db, SOUL.md, config.yaml, toolsets
  ```
- Her API server enabled, in `~/.hermes-isabella/.env`:
  ```sh
  API_SERVER_ENABLED=true
  API_SERVER_KEY=<a long random string>   # required even on loopback
  API_SERVER_PORT=8643                    # 8642 is Selene's
  API_SERVER_HOST=127.0.0.1
  ```
- Python 3.11+ and [`uv`](https://github.com/astral-sh/uv)
- Node 20+ and `pnpm` (for the web UI, M3)

**Run**

```sh
cp .env.example .env        # set HERMES_BASE_URL and HERMES_API_KEY
uv run isabella serve       # Isabella API
pnpm --dir web dev          # web UI  (M3)
```

**Verify Hermes is reachable**

```sh
curl -H "Authorization: Bearer $HERMES_API_KEY" http://127.0.0.1:8643/v1/models
```

## Layout

Documented target. Only the docs exist today.

```
Isabella/
├── README.md  ARCHITECTURE.md  ROADMAP.md  DATA.md  PERMISSIONS.md
├── BIOGRAPHY.md  HISTORY.md  ORIGIN.md  CLAUDE.md
├── Personality/         # who she is — core personality + her own theme
├── core/               # Python - FastAPI app, persona, trigger engine, Hermes client
│   ├── api/            #   HTTP surface Isabella exposes
│   ├── persona/        #   identity composition
│   ├── triggers/       #   trigger engine - compiles to Hermes jobs
│   └── hermes/         #   typed client for the Hermes API
├── web/                # TypeScript - React + Vite UI            (M3)
├── policy/             # permissions.json — the action policy (git-versioned)
├── triggers/           # YAML trigger definitions
│   └── daily-briefing.yaml
├── scripts/            # pre-run scripts - fetch data before the model runs
│   └── briefing_fetch.py   #   installed to ~/.hermes-isabella/scripts/
├── data/               # SQLite - Isabella's own state (gitignored)
└── docker-compose.yml  # portable deployment                      (M5)
```

## Docs

| | |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The Isabella/Hermes boundary, trigger model, persona system, open decisions |
| [ROADMAP.md](ROADMAP.md) | Milestones in order, each independently useful |
| [BIOGRAPHY.md](BIOGRAPHY.md) | Her life — Molo, Iloilo, 2001–2026, and how that person became this |
| [HISTORY.md](HISTORY.md) | The log — what was added, changed or fixed, and why |
| [ORIGIN.md](ORIGIN.md) | How this project came to be, and what she doesn't know about me yet |
| [Personality/](Personality/) | Fourteen files: traits, humor, theme, how she addresses me |
| [DATA.md](DATA.md) | How messages flow, what's stored where, and what leaves the machine |
| [PERMISSIONS.md](PERMISSIONS.md) | What she may do, who may ask, and how it's enforced |
| [CLAUDE.md](CLAUDE.md) | Working agreement for Claude Code in this repo |

**Upstream:** [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) ·
[docs](https://hermes-agent.nousresearch.com/docs) ·
[API server reference](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)
