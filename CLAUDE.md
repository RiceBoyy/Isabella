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
  body.py           reads Owen's body log from the vault. Read-only, one subtree
  mind.py           the graph home draws - memories, sessions, messages
  transcript.py     the transcript behind `chat`: what was said, and what it cost
  desktop.py        opens Terminal.app on a NAMED target. The only executing path
  logcolour.awk     colours her logs in that terminal. Read by desktop.py
  policy/           permit() - the action gate. ALL tool-enabled calls pass here
  hermes/           typed Hermes client - ALL Hermes calls go through here
    state.py        reads Hermes' state.db + memories/, READ-ONLY. Schema coupling
web/                React + Vite UI
policy/             permissions.json - the action policy, git-versioned
triggers/           YAML trigger definitions - source of truth
scripts/            pre-run scripts - source of truth, installed to HERMES_HOME/scripts/
data/               SQLite (gitignored)
```

**`core/hermes/` is the only module that may make HTTP calls to Hermes.** Upstream is
actively developed; when its API shifts, exactly one module should need changing.

## Commands

```sh
# 1. Her Hermes gateway must be running first.
export HERMES_HOME=~/.hermes-isabella
hermes gateway &                      # port 8643

# 2. Her API.
uv run uvicorn core.api.app:app --host 127.0.0.1 --port 8000

# 3. Talk to her.
curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
  -d '{"message":"who are you?"}'

curl -s localhost:8000/health         # 503 if Hermes is down OR persona drifted

uv run pytest -q
uv run ruff check .

# 3b. Her web UI. Talks only to the API above - it never holds the Hermes key.
#     No buttons: K opens the command palette, the number keys switch views,
#     Q closes a view window and hands the screen back to home.
#     Every view has an address, so a screen can be linked and reloaded:
#       /  ·  /chat  ·  /briefings  ·  /triggers  ·  /body  ·  /health
#       /settings  ·  /settings/google
cd web && pnpm install && pnpm dev     # http://127.0.0.1:5173

curl -s 'localhost:8000/mind?live=<session_id>'   # the graph home draws
curl -s localhost:8000/chat/log                   # the transcript behind `chat`

# 3c. What she can open on the host. Named targets only, read-only commands.
curl -s localhost:8000/desktop
curl -s -X POST localhost:8000/desktop/open/logs    # tails her agent log in Terminal.app
curl -s localhost:8000/runtime                      # model, gateway, persona, storage

# 4. Triggers. The engine reconciles triggers/*.yaml into Hermes jobs - it never
#    schedules anything itself.
curl -s -X POST 'localhost:8000/triggers/reconcile?dry_run=true'   # show the plan
curl -s -X POST localhost:8000/triggers/reconcile                  # apply it
curl -s localhost:8000/triggers                                    # incl. next_run_at
curl -s -X POST localhost:8000/triggers/daily-briefing/pause       # the kill switch
curl -s localhost:8000/runs   # incl. `briefing` - what she actually said, read from
                              # ~/.hermes-isabella/cron/output at request time, never stored
```

A pause **outranks the YAML** - reconcile will not turn a paused job back on. To restart
it, `POST .../resume`. `enabled: false` in the file deletes the job outright.

**Answers take 8-90 seconds.** qwen3 reasons before speaking; simple questions are ~8s and
identity questions can reach 90s. Not a hang - set client timeouts accordingly.

Stop her gateway by PID, never by name:
```sh
kill "$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.hermes-isabella/gateway.pid")))["pid"])')"
```

## Guardrails

**Secrets.** Never commit `.env`. Never put the Hermes key, provider keys, or channel
tokens in source, tests, or docs. The web UI never holds the Hermes key - browser
traffic goes to Isabella's API, which holds it server-side.

**Permissions.** Every path that reaches Hermes with tools enabled goes through
`permit()` (`core/policy/`). Never reimplement the check locally. The policy lives in
`policy/permissions.json` - git-versioned, never in `data/`. It fails closed: a missing or
unparseable policy denies everything. **Isabella's policy may only ever be narrower than
Hermes' own config, never wider** - see `PERMISSIONS.md`. Never set `HERMES_YOLO_MODE`,
`SUDO_PASSWORD`, or `HERMES_ACCEPT_HOOKS`.

**Autonomy.** Every trigger that can act unprompted must have a rate limit
(`max_runs_per_day`), a timeout, and a kill switch (`enabled: false`, or pause the
Hermes job). Failures notify; they never silently retry. Write the run record *before*
delivering.

**Her Hermes instance is `~/.hermes-isabella`, on port 8643.** Export
`HERMES_HOME=~/.hermes-isabella` before any `hermes` command, always. Everything of hers -
config, state, memory, transcripts - lives there.

```sh
export HERMES_HOME=~/.hermes-isabella
hermes gateway            # her gateway
hermes config get model.default
```

`HERMES_HOME` redirects **state only**. The program itself is a single shared install at
`~/.hermes/hermes-agent/`, which the `hermes` wrapper hardcodes - so upgrading Hermes
upgrades it for every instance on this machine.

**Scope process commands by PID, never by name.** Other Hermes gateways run on this machine
and `pkill -f "hermes gateway"` kills all of them. To stop hers:

```sh
kill "$(python3 -c 'import json,os;print(json.load(open(os.path.expanduser("~/.hermes-isabella/gateway.pid")))["pid"])')"
```

**Her persona lives in `~/.hermes-isabella/SOUL.md`**, not in a system message. It is a copy
of `Personality/compiled/core.md`. Regenerate the compiled prompt and you must copy it across
- otherwise Hermes serves a stale identity. Requests to `/v1` send **no system message**;
sending one stacks a second identity on top of SOUL.md and the model burns reasoning
reconciling them.

**Data.** Isabella stores no message content - transcripts live in
`~/.hermes-isabella/state.db`.
Never add a second memory or message store here. Before enabling any hosted memory or
telemetry provider (Honcho, Mem0, Hindsight, Langfuse, Supermemory), read `DATA.md`
§What leaves the machine: inference is local today and those defaults are all cloud.

**Logs are terminals, and there is no log view.** Her agent log, error log and
gateway log are read through `core/desktop.py` - `open logs`, `open errors`,
`open gateway` - and nowhere else. A browser log view was built on 2026-08-26 and
removed the same day: a scrolling log wants a terminal, and two places to read the
same file is one place too many. **Do not add `GET /log` back.**

`close logs` / `close errors` / `close gateway` - and `close terminals` for all of them -
stop what is running and close the window. Offered only when a window is actually open, and
they never touch a window Isabella did not open: every tab she opens is stamped
`Isabella · <target>` as its custom title, and that title is the only thing the close path
matches on.

**Terminal refuses to close a BUSY window, and says nothing about it.** `close window id N`
returns success and the window stays, because what Terminal wants to do is put up its
"terminate running processes?" sheet and it cannot do that to a script. So closing is three
steps in order: kill what is running, **wait for `busy` to go false**, then close. Skip the
wait and it silently does nothing.

**Do not diagnose this by watching `id of every window`.** That list keeps returning ids for
windows that are already gone, which is what produced a day of code built around the wrong
belief that Terminal ignores `close` entirely. Enumerate windows that still have tabs -
`_LIST` does.

If something is still running after the kill it is something Owen started in a window of
hers. That window is reported as `stubborn` and left alone rather than fought over.

`_kill()` is the one thing in `core/desktop.py` that is not read-only. Three bounds, all
necessary: the tty must belong to a window carrying her title, the shell is never touched,
and the command must be one of `KILLABLE` - the handful this file itself runs. A process on
her tty that is not on that list is something Owen started in a window of hers.

`core/logcolour.awk` colours those three for a glance: red is an error, yellow a
warning, everything else dim, and a traceback inherits the colour of the line above
so a stack trace reads as part of its error. Three steps and no more - the question
being asked of a scrolling log is *is anything wrong*, and a rainbow answers it
worse. It is a file rather than an inline awk program because the command is
embedded in an AppleScript string; the path is still a constant derived from the
repo's own location, which is the property `desktop.py` exists to keep.

**`chat` is not a log** - it is the transcript, read back out of Hermes' `state.db`
at request time (`core/transcript.py`). It is a view because it is prose she wrote,
not machine output. It was briefly called `chat log`, which put it in the same
sentence as the agent log; that is the confusion the rename ended.

**`home` draws a brain, and it is made of what is actually on disk.** Selene's brain is
her memory graph; Isabella has no memory table, must not have one, and Hermes' gateway
exposes no memory endpoint. So the graph is memories (`HERMES_HOME/memories/*.md`),
sessions and messages (`state.db`) - see `core/mind.py` and ARCHITECTURE.md §what the
brain on `home` is made of. Three rules, none of them negotiable:

  1. **Importance is 0-10 where an entry records one and `null` where it does not.**
     Hermes' memory format has no importance field, so `[importance: N]` is a tag
     Isabella READS and never writes. Null travels to the renderer, which draws it
     hollow and says `unrated`. A default of 5 is a judgement about Owen's life that
     nobody made - the same rule `core/body.py` keeps for an unlogged weight.
  2. **Every radius is a real count** (`size`, normalised server-side).
  3. **The three kinds are told apart by VALUE, not hue.** Violet is LIVE - the session
     being spoken in - and nothing else. A second colour would say "this is happening"
     about a conversation from Tuesday.

**`core/hermes/state.py` reads Hermes' state.db and memory store READ-ONLY**, opened
`mode=ro` so a stray write is a SQLite error rather than a corrupted agent. It is the
second module coupled to Hermes' internals and the tighter of the two - `client.py`
couples to an HTTP API, this couples to a schema. Name every column explicitly; never
`SELECT *`. `tests/test_mind.py` carries a cut-down copy of that schema so an upstream
change breaks a test, not a view. **Nothing here writes, and nothing here caches** -
Isabella still stores no message content.

**The web UI has no buttons, and that is deliberate.** Every action is a command in the
palette (`K`); views are `1`-`5`, unadvertised on purpose - nothing in the chrome announces
that other views exist, and a command's label is the bare word (`body`, not `show body`)
because that is the string voice will carry at M6. This is the surface voice plugs into at M6 - a command
router does not care whether the string was typed or spoken - so **do not add a button**,
add a command. Two rules for the palette, both from Selene's: *nothing is listed that is
not wired* (build commands from live state, never a hardcoded menu), and the kill switch
stays reachable - `pause daily-briefing` must always be one of them.

**There is exactly ONE input for talking to her, and it is the palette.** A string that
matches a command runs it; a string that matches nothing is said to her. Home carried a
second box for a day and it was the wrong shape - two boxes on one screen means working
out the difference between them before typing anything, and there is no difference worth
learning. **Do not add a text box to a view.** The fallback row is sans in a list that is
otherwise mono, because the two faces split by who is speaking and that row is the one
thing on screen a person is about to say.

Commands win the tie: typing `body` shows the body rather than asking her about bodies.
The ask row appears only when nothing matches.

The one standing exception is `/settings/google`, which takes a paste of the redirect URL
Google hands back. That is a credential arriving from outside the app, not a second way to
talk to her, and it is submitted with Enter and never kept in component state longer than
the call. A new input needs a reason of that kind or it does not go in.

**Every view has an address** and `ROUTES` in `web/src/App.tsx` is the only table of them -
the palette builds its view commands from it, the number keys index into it, and the
renderer switches on it. Adding a view is one line there. `web/src/router.ts` is
hand-written; `react-router` for eight static paths with no params would be a dependency
bought for nothing, and would not have done the tab rule below. An address that is not a
route says so and names the ones that are - **never redirect an unknown path to home**,
that hides the typo that got you there.

**Home is never replaced, and that is what the router is actually for.** Home is the screen
Owen leaves up; losing the brain to go and read the trigger list was the wrong trade. So:

  - from **home**, picking a view opens it in a **window** of its own - not a tab. A tab
    behind a tab strip is still hidden, and hidden was the complaint. The window is NAMED
    (`isabella/chat`), so picking `chat` twice reuses it rather than opening a second.
  - from a **spawned** window, everything navigates in place - it is already not home.
  - from a spawned window, `home` - or **`Q`** - **closes** it. `window.close()` works
    because it was script-opened; a second copy of home in a window called "chat" would be
    worse than none. It falls back to navigating home if the browser refuses. `Q` on home
    does nothing but say why: home is the one that stays.
  - a deep link typed by hand has no opener and behaves like an ordinary page.

**A window is a window because features are passed.** `window.open(url, name, "popup=yes,
width=…")` opens a window; the same call with no third argument opens a tab. `chrome()` in
`router.ts` must never return an empty string, and the size/offset are not decoration - a new
window landing exactly on top of home looks like home was replaced, which is the one thing
this rule exists to prevent.

**The feature string is a request, not an instruction.** When home is maximised or
full-screen the browser hands the new window the same shape, which covers home completely.
So the size is applied TWICE: `fit()` from the opener, and `useOwnWindow()` in the new
window itself on first load. Keep both - the opener's call runs before the window has laid
anything out and is the one browsers most readily ignore; the child's runs in its own
context, after it exists. The child corrects itself **only if it came out covering the
screen, and only once** (a `sessionStorage` flag), so a window someone maximised on purpose
is never shrunk back. macOS native full-screen is the case this cannot fix: the new window
opens in its own Space and no script can pull it out.

Two things follow and are easy to break. **`open()` must stay synchronous from the
keypress** - `window.open` after an `await` is an unsolicited popup and gets blocked. And
**anything carrying this window's state must use `navigate()`, not `open()`**: the live chat
turn lives in App memory, so asking her something from `/triggers` moves in place to `/chat`
rather than spending a window the answer would not be in.

**On the body view, `←`/`→` step through the anatomy layers** (skin, muscle, skeleton) and
the palette still names them, because that is what voice will say at M6. Keys are bound only
where they do something.

**The body's meshes live in `web/public/anatomy/`** - skin (MakeHuman, CC0), muscle and
skeleton (**Z-Anatomy, CC BY-SA 4.0**). The licence requires the credit be *visible where the
work is seen*: the mesh carries it, `Body3D` reports it through `onCredit`, and the view
prints it. Don't drop that. Without the atlas the component falls back to built-in primitives
and still works, so a 404 here is silent - if the body looks crude, check the manifest loaded.

**The body is drawn by `web/src/components/Body3D.tsx`** - ported from Selene, Owen's own
component, and the reason to keep it in sync rather than edit it here is that its geometry
was debugged against problems that are invisible in the output. Isabella drives it with
`active` alone: region id to tone, where a bare group (`chest`) lights both sides. Muscles
light only from an exercise **actually ticked** this week.

**`body` is Owen's body; `health` is hers.** `core/body.py` reads `Personal/Body` in the
vault - the same Markdown he writes, read-only, and the only source there is, because a Mac
has no Health database. **Nothing fills a gap:** an unlogged measure stays `null` all the way
to the panel, which draws the absence. A zero or a carried-forward number would be a
dashboard telling a story about a real person's health. Every measure carries the day it was
written so staleness is visible.

**`core/desktop.py` executes on the host.** It opens Terminal.app on one of four named,
read-only targets. The commands are **constants**; nothing composes one from a request or
a model's output, and Hermes cannot reach it. Adding a target that writes, or one whose
command is built from a parameter, is a different decision - see `ARCHITECTURE.md`
§Opening a terminal before touching it.

**The web UI follows a design system, and it is not in this repo.**
`~/Projects/vault/Projects/selene/Design` - `Color Theme.md` (the palette, with its contrast
measurements) and `Visual Style.md` (type, space, density, motion, the emphasis ladder). The
tokens at the top of `web/src/styles.css` are copied from it; change them there, not
piecemeal in components. Two rules break most easily: **the violet marks what is LIVE** and
nothing else, and **the two faces split by who is speaking** - sans for Isabella, mono for
the machine. **The moth is Selene's** and is not Isabella's to wear; she uses the geometric
presence mark.

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

**The runtime prompt is `Personality/compiled/core.md`** - derived from `Personality/`, not
a substitute for it. Change a source file, regenerate and re-probe. Never edit only one.

**qwen3 gotchas, verified - see `HISTORY.md`:**
- `think: false` does NOT disable reasoning; it moves it into `content`. Use `think: true`.
- Reasoning counts against `max_tokens`. Starved, `content` comes back **empty** with
  `finish_reason: length`. Treat empty content as a real error, not a transport failure.
- **Ollama's `/v1` ignores `num_ctx`** - the Modelfile is the only channel. Use a `-16k`
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

Current milestone: **M2**, with the first slice of **M3** built out of order by decision on
2026-08-26 - a web UI at `web/`, because the briefing was being delivered into a file nobody
opened. See `ROADMAP.md` M3 for what that cost.

The trigger engine is built and the briefing runs end to end - cron fires a pre-run script,
its output is injected as prompt context, and a model with **no toolsets** composes the
briefing. Google authorisation now has a flow - the **Connect Google** panel in `web/`, which
drives the skill's `setup.py` and writes a read-only refresh token into `HERMES_HOME`. Until
someone clicks through Google's consent screen she correctly reports the blind spot instead
of inventing a day. See `HISTORY.md`.

**The Google grant is server-side, and has to be.** A browser session token is unreachable at
07:00, when the briefing fires with nobody logged in. Never move it into a cookie, and never
reimplement the OAuth exchange here - `core/hermes/google_auth.py` drives Hermes' script and
that is the whole of Isabella's share in it.

**Calendar and email are pre-fetched, never tool calls.** `action.script` names a script;
Hermes injects its stdout into the prompt. `platform_toolsets.cron` is `[]` and must stay
that way - the 07:00 path does not pass through `permit()`. If a trigger needs new data,
extend the script; do not grant a toolset.

**Pre-run scripts live in `scripts/` and are installed to `~/.hermes-isabella/scripts/`.**
The repo is the source of truth; Hermes only ever runs the installed copy. Same trap as
`SOUL.md` - edit one, forget the other, and the briefing is built by unreviewed code. Copy
across after every change:
```sh
cp scripts/briefing_fetch.py ~/.hermes-isabella/scripts/
```
`GET /triggers` reports `script_install.drifted` when the two differ, and a test fails.
The script must never exit non-zero or print nothing: a model with no tools and an empty
context invents a plausible day. Every failure prints an explicit `UNAVAILABLE` line.

**A script trigger has to be created once by hand** - `POST /api/jobs` accepts neither
`script` nor `no_agent`. Reconcile refuses and prints the `hermes cron create` to run. After
that, everything else is reconciled from the YAML.

**Run `hermes` via its venv**, or it cannot import `yaml`:
```sh
~/.hermes/hermes-agent/venv/bin/python ~/.hermes/hermes-agent/hermes cron list --all
```
**`--all`, always.** Plain `cron list` hides paused jobs - it prints *"No scheduled jobs"*
rather than showing the job as paused, so verifying the kill switch without it looks exactly
like the job having been deleted.

## Docs

`README.md` (what and why) · `ARCHITECTURE.md` (boundary, trigger model, persona,
`Personality/` (how she sounds) · `BIOGRAPHY.md` (her life) · `HISTORY.md` (the change log)
· `ORIGIN.md` (project record, and what she does NOT know about Owen yet)
· `ARCHITECTURE.md` (boundary, trigger model, persona,
risks, open decisions) · `ROADMAP.md` (milestones) · `PERMISSIONS.md` (the action policy
and its two enforcement layers) · `DATA.md` (message flow, storage inventory, egress)

Keep them true. If a decision changes, update `ARCHITECTURE.md` in the same change -
a stale boundary table is worse than none.
