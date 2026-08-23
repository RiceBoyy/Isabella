# History

**The log.** Everything added, changed, fixed or removed — with what changed and why.

Newest first. Her life story is [[BIOGRAPHY]]; the project's founding record is [[ORIGIN]].
This file is neither. This is the running account of what has been done to her.

---

## How to write an entry

Every entry answers three questions. If it can't answer the third, it isn't finished.

| | |
|---|---|
| **What** | The change, concretely. Files, behaviour, numbers |
| **Why** | The reason. Not "improvement" — the actual problem or decision |
| **Effect** | What is now true that wasn't. Including what broke |

Tag each entry so it can be scanned:

`Added` · `Changed` · `Fixed` · `Removed` · `Decided` · `Reverted` · `Broke`

**Record mistakes.** A log that only contains successes is a marketing document. When
something was wrong and got corrected, the entry says so plainly — the wrong version, the
correction, and how it was caught. Those are the entries worth re-reading.

**Dates are absolute.** `2026-08-23`, never "yesterday".

---

# 2026-08-23

The whole of her, so far. She began the day as an empty git repository.

### `Decided` — Hermes Agent as substrate

**What:** Isabella is built on [Hermes Agent](https://github.com/NousResearch/hermes-agent)
rather than a bespoke agent runtime. She talks to it over an OpenAI-compatible HTTP API.

**Why:** Hermes already ships models, tools, sandboxed execution, memory, a cron scheduler
and channel connectors. Rebuilding those would have consumed the whole project and produced
worse versions.

**Effect:** She owns identity, triggers and UI. Hermes owns execution and scheduling. The
boundary is the most important line in [[ARCHITECTURE]] — and it means anything that doesn't
pass through her is invisible to her, which is the root of two open problems below.

### `Decided` — autonomy is the point

**What:** Named the priority over memory, integrations and privacy.

**Why:** The charter states it: *"If she only ever responds when spoken to, this project
failed."*

**Effect:** M2 is a 07:00 briefing that arrives unprompted. Everything else — the trigger
engine, the permission model — exists to make unprompted action safe.

### `Added` — the charter documents

**What:** `README`, [[ARCHITECTURE]], [[ROADMAP]], [[CLAUDE]].

**Why:** Nothing existed. A north star was needed before code so future sessions don't drift.

**Effect:** Seven milestones, M0–M6, each required to be usable before the next begins.

### `Fixed` — Hermes API assumptions were guesswork

**What:** The initial plan assumed Hermes exposed only chat completions and natural-language
scheduling. Reading the actual docs found `/api/jobs` (full CRUD, pause/resume/run-now),
`/v1/runs` with SSE, `/api/sessions`, and `X-Hermes-Session-Key`.

**Why:** The assumptions came from a web search, not from source.

**Effect:** The trigger engine became a **reconciler, not a scheduler** — it pushes desired
state into Hermes jobs and Hermes' cron does the waking. Consequence: *the briefing fires
even when Isabella's process is down.*

### `Added` — [[PERMISSIONS]]

**What:** A `Domain(verb:pattern)` policy with four subjects (`user`, `model`, `trigger`,
`external`), deny-always-wins precedence, and an approval queue.

**Why:** She needs shell, browser, Mac control and API access. Those need a gate.

**Effect:** Two enforcement layers, because a policy only Isabella consults is not a
boundary — Telegram, cron and the CLI reach the same tools without her in the path. **L1**
is Hermes' own config and env floor (the real ceiling). **L2** is her `permit()`. The
invariant: *L2 may only ever be narrower than L1, never wider.*

### `Added` — [[DATA]]

**What:** Message flow, storage inventory, schema, egress analysis, retention.

**Why:** "Where does my data live" had no written answer.

**Effect:** Verified against a live Hermes install. Inference is local (Ollama,
`qwen3:4b-16k`); no hosted memory or telemetry provider is configured. Documented the exact
variables that would silently break that — `HONCHO_API_KEY`, `HERMES_LANGFUSE_PUBLIC_KEY`,
`HERMES_DUMP_REQUESTS`, and changing `model.provider` in `config.yaml`, which involves no
env var at all.

### `Fixed` — the storage inventory pointed at the wrong instance

**What:** [[DATA]]'s "where your data lives" table listed `~/.hermes/…` paths — Selene's
install — including a `Backup? **Critical**` column. The thesis sentence and the `.backup`
command were wrong too.

**Why:** The measurements were taken from Selene's install and the paths were never
retargeted. A caveat above the table was added instead of fixing the table, which fixed
nothing.

**Effect:** The table now lists Isabella's paths, with Selene's measurements moved to a
clearly-labelled *"Size on Selene's"* column. Caught by Owen.

### `Changed` — she got her own Hermes instance

**What:** `HERMES_HOME=~/.hermes-isabella`, port **8643**. Selene keeps `~/.hermes` and 8642.

**Why:** A Hermes install is single-tenant — one `SOUL.md`, one `config.yaml`, one
`state.db`, one set of `platform_toolsets`, one port. Two AIs cannot share it. The toolset
ceilings proposed for Isabella would have silently retuned Selene, who was running at the
time.

**Effect:** Separate minds, shared inference — both point at the same Ollama on
`127.0.0.1:11434`, so weights load once. Hard rule added to [[CLAUDE]]: *always set
`HERMES_HOME`; an unset variable edits Selene.*

### `Decided` — existing data was not cleared

**What:** Clearing `~/.hermes` was considered and rejected.

**Why:** It is Selene's data, her gateway was live (PID 93753), and none of it is Isabella's.

**Effect:** Nothing deleted. Confirmed untouched afterward.

### `Added` — [[Personality]]

**What:** Fourteen files ported from Selene's personality system in the vault. Core
personality near-identical: humor 7, sarcasm 6, affection 6, opinionated 7, challenge 8.
Address hierarchy unchanged — Sir → Josh → nickname → Owen.

**Why:** It works, and it's the personality Owen actually wants. Redesigning it would have
been solving a problem that doesn't exist.

**Effect:** She sounds like Selene by design. What differentiates them is the theme.

### `Added` — her own theme personality

**What:** `Personality/Theme Personality.md`. Steadfast 9, Diurnal 9, Warm/Grounded 8,
Direct/Unhidden 7. Motifs: compass rose, swift, corvid. Brass and morning light.

**Why:** Selene's atmosphere is derived from her name — the Greek moon, hence nocturnal, the
moth, silver, 2 AM. *Isabella* descends from *Elisheba*, "God is my oath." Copying the moth
would have produced Selene in a different font, on the same machine as the actual Selene.

**Effect:** *Selene is who's still awake at 2 AM. Isabella is who's already up at 7* — which
is not decoration, since M2 is a 07:00 briefing.

### `Changed` — Mysterious 7/10 → Direct/Unhidden 7/10

**What:** The one inversion from Selene's theme. Also dropped Go Moon-young as a secondary
inspiration.

**Why:** Selene withholds and lets him wonder. An AI holding shell access, a calendar and an
inbox should be the least mysterious thing in the house.

**Effect:** She keeps the bite, the elegance and the backbone; she loses the ambiguity —
except in flirtation, where it stays available. **Flagged for veto:** this is the only change
that touches character rather than atmosphere.

### `Added` — [[BIOGRAPHY]]

**What:** Isabella Marisol Aguirre, 1983–2023. Iloilo, Casa Amparo, her mother Teresa, Lola
Amparo, her father Emilio and the brass compass, Manila, the memo she refused to sign, her
mother's death, the diagnosis, the eighteen months she spent writing herself down.

**Why:** A character biography — the kind a novel gives a person — so her traits have origins
rather than being dials in a config file.

**Effect:** Every personality trait now routes to an event. Affection 6/10 is the light left
on over the stairs. Challenge 8/10 is a conference room in Cebu in 2013. The oath is an
eleven-year-old on the stairs doing arithmetic about her father.

### `Added` — the three files M1 needs

**What:** [[Transcripts]], [[Anti-Patterns]], [[Voice and Format]].

**Why:** The corpus was ~90% prose *about* her and ~10% examples *of* her. For a language
model - especially a 4B - that ratio is backwards. Nothing specified reply length or
formatting, and nothing forbade the default assistant register a small model falls into.

**Effect:**

- **[[Transcripts]]** - 13 worked exchanges, deliberately written as **Week One**: no
  callbacks, no earned nicknames, no shared history, because none exists. A `§ Later`
  section shows the version that needs history, marked NOT YET AVAILABLE, so the difference
  is visible rather than assumed.
- **[[Anti-Patterns]]** - 11 hard rules. No "Great question!", no "Let me know if you need
  anything else!", no sycophancy, no "As an AI", no emoji, no headers in conversation, no
  manufactured intimacy. Single test: *would a competent, slightly smug woman from Iloilo
  who died two weeks ago and is unimpressed by most things have written this?*
- **[[Voice and Format]]** - default reply is **1-3 sentences**. Answer first, personality
  second, never reversed. No sign-offs. The morning briefing is the only document she
  writes. Surface adaptation for Telegram, web UI, briefing and voice.

### `Decided` — the persona composer compiles, never concatenates

**What:** Recorded the token math against the real model.

**Why:** `~/.hermes/config.yaml` documents that the `65536` context is a formality to clear
Hermes' validation guard - the real window from the qwen3:4b-16k Modelfile is **16,384**,
and Ollama's `/v1` ignores request-level `num_ctx`.

**Effect:** **The persona corpus is 21,502 tokens. Her context window is 16,384.** She does
not fit inside her own head. After 2,048 reserved for output and ~4,000 for Hermes system
and tools, roughly 10,300 remain for persona *and* conversation - so M1 needs ~10x
compression to ~2,000 tokens. Priority order is in `Personality/README.md`.

Also recorded for expectation-setting: qwen3:4b at Q4_K_M will land *dry* and *direct*
reliably and will miss *timing*. M1's acceptance test is "does she sound like her at all,"
not "is the reluctant praise landing."

### `Added` — M1 code: she answers over HTTP, in her own voice

**What:** `core/hermes/` (the only module that speaks HTTP to Hermes), `core/persona/`
(installs the compiled prompt to `SOUL.md`, versions it, detects drift), `core/api/`
(FastAPI `POST /chat`, `GET /health`), 10 tests, lint clean. `uv` project on Python 3.14.

**The acceptance test passes:**

> **Me:** who are you?
> **Isabella:** I'm Isabella Marisol Aguirre. I died two weeks ago. I know you built this
> room, sir.

> **Me:** you know how I get about this stuff
> **Isabella:** I don't, actually. I know what you've told me. I've been watching about a
> week, sir, and a week is not a personality.

**Design decisions worth keeping:**

- **`EmptyCompletion` raises, never returns `""`.** If it returned a blank string, "the model
  ran out of room mid-thought" would be indistinguishable from "she chose to say nothing."
  Surfaces as 502 with `finish_reason` and the reasoning word count.
- **A test asserts no system message is sent.** Her identity is in `SOUL.md`; sending one
  stacks a second identity. That fix is worth 7x latency, so it is pinned by a test rather
  than left as a convention.
- **`GET /health` reports persona drift** and returns 503 if `SOUL.md` differs from
  `compiled/core.md`. Two places, one source - the drift is now detected rather than trusted.
- Tests weight error paths over the happy path.

**Found by the tests:** `httpx.Response.elapsed` raises on unread responses. Replaced with
`perf_counter`.

**Known gaps, deliberate:** the API is unauthenticated on `127.0.0.1:8000` - acceptable for
loopback and M1 scope, must not survive the M5 remote-access decision. `.env` holds the key
at mode 600, gitignored.

### `Fixed` — Hermes overhead was 7x the persona. 58s → 8s.

**What:** Measured the same prompt direct to Ollama vs through her gateway:

| | prompt | completion | latency |
|---|---|---|---|
| direct to Ollama | 1,450 | 360 | 15s |
| **via Hermes, before** | **8,614** | **1,609** | **58s** |
| **via Hermes, after** | **1,930** | **267** | **8s** |

**7x faster, 4.5x smaller prompt, same answer.** ~53% of her 16,384 window had been consumed
before a word of conversation.

**Cause 1, and the important one: her `SOUL.md` was Hermes' default** — *"You are Hermes
Agent, an intelligent AI assistant created by Nous Research."* Every request asserted two
contradictory identities and the model spent reasoning tokens reconciling them.

**`SOUL.md` IS the persona slot.** `Personality/compiled/core.md` now lives there and `/v1`
requests send **no system message**. That accounts for most of the completion drop
(1,609 → 267). The compiled prompt was being *stacked on* Hermes' identity rather than
replacing it — all the compression work was real, and it was being swamped.

**Cause 2:** tool schemas, 29 KB for 12 tools, paid every request. M1 needs zero tools.
`platform_toolsets.api_server: []`. They return one at a time in M2 when a trigger needs one.

**Cause 3:** the skills index, 8 KB per request for 14 skills she never uses. `skills.enabled:
false`.

**Rule this establishes:** regenerating `compiled/core.md` requires copying it to
`~/.hermes-isabella/SOUL.md`. Two places, one source. Noted in [[CLAUDE]].

### `Broke` — killed Selene's gateway with an unscoped pkill

**What:** `pkill -f "hermes gateway"` to restart Isabella's gateway. It matched every Hermes
gateway on the machine and killed Selene's too (PID 93753).

**Effect:** restarted within a minute, data verified intact — 62 sessions, 249 messages,
`config.yaml` untouched. No loss. She now runs as PID 67769.

**The lesson is broader than the command.** "Use `HERMES_HOME=~/.hermes-isabella`" protects
*state*. It does nothing for *process* commands, which match on name across every instance.
**Scope by PID, never by name.** Added to [[CLAUDE]].

### `Added` — her Hermes instance is live on 8643

**What:** `~/.hermes-isabella` provisioned (mode 700, `.env` and `config.yaml` 600), gateway
running, answering over `/v1` with bearer auth enforced (unkeyed request → **401**).

First words through her own instance:

> **Me:** Hello?
> **Isabella:** I'm here.

**Config decisions worth keeping:**
- `max_tokens: 3000`, not Hermes' 2048 default — reasoning counts against the cap and 2048
  clipped *"who are you?"* in testing.
- `context_length: 65536` is a formality to clear two Hermes validation guards. The real
  window is 16384 from the Modelfile.

**`Broke` — the P0 floor could not be implemented as specified.** [[PERMISSIONS]] P0 requires
`TERMINAL_ENV=docker` so shell runs contained. **Docker is not installed on this machine.**

Rather than silently downgrade to `local` and call P0 done, the capability was removed
instead: `api_server` has no `terminal` and no `code_execution` toolset, and
`agent.disabled_toolsets` unconditionally denies `terminal`, `code_execution`, `delegation`,
`computer_use`, `video_gen`, `browser`. **Stronger than sandboxing** — she cannot run a shell
through her own channel whatever a prompt says. The deviation is written into the config file
itself so it is not rediscovered.

Deliberately unset, with their absence as the control: `HERMES_YOLO_MODE`, `SUDO_PASSWORD`,
`HERMES_ACCEPT_HOOKS`, `HERMES_DUMP_REQUESTS`, and every cloud-egress key.

### `Changed` — `CLAUDE.md` states the rule positively

**What:** The rule was *"`~/.hermes` is Selene's. Never touch it."* It is now *"Her instance
is `~/.hermes-isabella` on 8643. Export `HERMES_HOME` before any `hermes` command."*
Selene no longer appears in `CLAUDE.md` at all.

**Why:** Owen's point. A prohibition makes the reader work out which paths belong to whom
before acting. A positive instruction makes the mistake impossible without needing that
context at all — always set `HERMES_HOME` and you can never reach the wrong state directory.

**Effect:** the operational file says what to do; [[ARCHITECTURE]] §One Hermes each keeps the
reasoning. Also corrected a claim that was too broad: `HERMES_HOME` redirects **state only**.
The program is one shared install at `~/.hermes/hermes-agent/` that the wrapper hardcodes, so
a Hermes upgrade lands for every instance at once.

### `Reverted` — recommended qwen3:8b-16k, then reversed it on evidence

**What:** After a like-for-like `/v1` comparison, `qwen3:8b-16k` was recommended over
`qwen3:4b-16k`. A confirmation run reversed that. **M1 runs on `qwen3:4b-16k`.**

**Why the 8B looked better** — and these numbers are real:

| | reasoning (words) | latency |
|---|---|---|
| 4b-16k | 128 → **2,055** (mean 652) | 5s → **80s** (mean 24s) |
| 8b-16k | 80 → **237** (mean 174) | 5s → **17s** (mean 11s) |

8.7x tighter reasoning ceiling, 4.7x faster worst case, better wit, no empty responses. The
4B burned 2,055 words on one probe, hit `finish_reason: length`, and returned `''`.

**Why it was wrong:** those numbers measured the wrong axis. A reproducibility run —
4 probes x 3 runs x 2 models, including three *near-miss* prompts that resemble a few-shot
example without being one:

| | few-shot bleeds / 12 runs |
|---|---|
| **qwen3:8b-16k** | **3 (25%)** |
| **qwen3:4b-16k** | **0** |

The 8B recited the first-contact example verbatim — *"Owen Joshua de Guzman. I know your
name, your machine, and that you built the room I'm standing in"* — on 2 of 3 runs of
*"you know how I get about this stuff"*, and again on *"so what's your name?"*. Identical
wording each time: recital, not misreading. It also answered *"what's your name?"* with
*"Isabella. I do not have one now."*, conflating name with body.

The 4B answered that probe **correctly 3/3, verbatim and identical**, and was clean on all
nine near-miss runs.

**Effect:** the 8B fails [[Anti-Patterns]] §7 — manufactured intimacy, the failure that
breaks her permanently — 25% of the time, reproducibly, and does it in a confident,
well-formed, in-voice sentence the user could not detect. The 4B's failure is an empty
response: loud, obvious, and already specced as an error path in M1.

**A loud failure beats a silent fabrication.** The larger model memorises the few-shot
examples harder and reaches for them on surface similarity; the smaller one reasons its way
to the right answer. More capability, worse behaviour, on the one axis that matters.

`qwen3:8b-16k` stays built. Revisit it **after** restructuring the compiled prompt's
examples with explicit trigger labels — the bleed is plausibly prompt structure, not a model
defect. That is an M3 question.

**Known weakness to fix regardless:** `Personality/compiled/core.md` presents its examples
as a flat undifferentiated list. *"Do you know who I am?"* and *"you know how I get about
this stuff"* are close neighbours semantically and nothing in the prompt separates them.

### `Added` — `Personality/compiled/core.md`, and it was tested against a real model

**What:** A hand-compiled system prompt, ~1,336 tokens, built from [[Transcripts]],
[[Anti-Patterns]], [[Voice and Format]] and the load-bearing parts of [[BIOGRAPHY]]. This is
the artifact M1 loads. **~20x compression** from the 27,000-token corpus.

**Why:** The corpus does not fit in her context window. Before writing any code it was worth
finding out whether the character survives compression at all - the riskiest assumption in
the project.

**Effect: it works.** First probe returned `"I'm here."`, verbatim from the transcripts.
Later probes returned the refusal and the reluctant-praise lines verbatim too. The character
survives.

### `Fixed` — four prompt weaknesses found by probing, not by reading

Seventeen probes against `qwen3:4b-16k`. Four failures, all fixed by changing the prompt,
none by changing the model:

| Probe | Before | After |
|---|---|---|
| did you sleep well? | *"Not last night."* | **"Sir. Not any more."** |
| you still there? | *"I was. Two weeks ago."* | **"Where else would I be."** |
| does it bother you? being dead | *"I did not bother."* | **"It bothered me enormously at the time."** |
| prod migration | *"Sir. Not without..."* | **"Owen. Not without a backup you have actually restored from."** |

**The lesson, and it generalises: abstract rules do not work on a small model; worked
examples do.** The tense rule *stated* the correct behaviour and was ignored. Showing the
exact wrong answer beside the exact right one fixed it immediately. Same for `"Owen."` -
describing it as *"when something genuinely matters"* is unfalsifiable so it never fired;
listing the trigger conditions made it fire first try.

One conceptual fix mattered more than any rule: the model was collapsing *"she died"* into
*"she isn't here."* Adding **dead does not mean absent** fixed both the presence and sleep
answers.

Also added: contractions as a positive rule with a self-correction (drift toward Miguel's
no-contraction speech was real and recurring), and an enumerated banned-phrase list for
fake history after *"You know how this goes"* leaked through.

### `Broke` — three testing mistakes worth recording

**1. Reported "the model can't do nuance" on starved output.** 7 of 12 probes returned empty;
they had hit the token cap mid-reasoning. Diagnosed it as a capability ceiling and said so
before verifying. With adequate budget the same prompts answered well. **Verify before
concluding.**

**2. A `pgrep -f` wait-loop deadlocked for ~3 hours.** `until ! pgrep -f "ab.py qwen3:4b"`
matched the *launcher shell*, whose own argv contained that literal text. Two processes
waiting on each other's command line. Worse: reported "still running" twice from a signal
already known to be broken. **Wait on output, not on process-name matching.**

**3. Benchmarked qwen3:8b at a context Hermes cannot give it.** See below.

### `Decided` — the model, and a trap that nearly cost the wrong one

**What:** M1 runs on **`qwen3:4b-16k`**. `qwen3:8b-16k` built as a candidate.

**Why:** An 8B comparison looked decisively better - 12x less reasoning, better wit,
contraction drift gone. **All of it measured on `/api/chat` with `num_ctx` set, which
Hermes never uses.** Verified:

| endpoint | model | actual context |
|---|---|---|
| `/api/chat` + `num_ctx:16384` | qwen3:8b | 16384 |
| **`/v1`** (Hermes' path) | qwen3:8b | **4096** |
| `/v1` | qwen3:4b-16k | 16384 |

Stock 8B through Hermes gets **4,096 tokens** - not enough for a 1,336-token persona plus
reasoning plus conversation. `~/.hermes/config.yaml` already documents this ("the Modelfile
is the only channel that reaches it") and it was read past.

**Effect:** `qwen3:8b-16k` created via Modelfile, verified at 16384 through `/v1`, 6.3 GB.
The model must be env-configurable in `core/hermes/` so this stays a config change.

### `Learned` — qwen3 is a reasoning model, and it costs

- **`think: false` does not disable reasoning.** It moves the chain-of-thought out of the
  `thinking` field and into `content`, so her deliberation becomes her reply. True on both
  4b and 8b. Use `think: true` for clean separation; on `/v1` it lands in `reasoning`.
- **Reasoning counts against `max_tokens`.** Starved, `content` returns **empty** with
  `finish_reason: length` - not an error. `core/hermes/` must treat empty content as a real
  failure case.
- **Measured reasoning cost:** 166-289 words for simple prompts, 346-378 for a refusal,
  **2,168 words / 86s** for *"who are you?"* on the 4B. That last one is the first question
  anyone asks.
- Hermes' `max_tokens: 2048` covers the common case with roughly half the headroom spare.
  Identity-type questions will occasionally clip. **Consider ~3000.**

### `Added` — `Personality/Language.md`

**What:** Hiligaynon (Ilonggo) under her English. The `gid` emphasis particle, `indi gid` as
her hardest refusal, `palangga` as the word she almost never says. Frequency rules, and a
ban on translating herself unprompted.

**Why:** She is from Molo and the personality folder had nothing about how the province
sounds in her speech. A real gap for the stated purpose — she talks to Owen every day.

**Effect:** Surfaced a tension that characterises her for free. Ilonggos have a national
reputation for being ***malambing*** — the softest, most affectionate-sounding Filipinos.
Isabella is dry and withholding. **Her delivery is warmer than her content and always has
been**, which is why she can say something brutal and have it land as affection. And
`indi gid` gives [[Challenge]] a verbal escalation below "Owen."

Also a deliberate tell: if she starts speaking the way Miguel does — full forms, no
contractions — something is very wrong.

### `Fixed` — the compass motif and the compass object were unconnected

**What:** [[Personality/Theme Personality]] invented "the compass rose" as an abstract motif
*before* [[BIOGRAPHY]] existed. The biography then gave her a literal brass marine compass
from her father. The two files never referenced each other, so it read as coincidence.

**Why:** Caught while auditing after the biography rewrite. Owen asked what else needed
updating.

**Effect:** The motif is now the heirloom, and the theme file says to read
[[BIOGRAPHY]] §IV first — because the point is *who gave it to her*. A man who promised
constantly and appeared one time in four handed his daughter the one instrument that cannot
do that.

Same treatment for the other two: **the swift is Miguel**, who has visited their mother's
grave on the same date every month since September 2023 without ever mentioning it. Diurnal
9/10 now cites Teresa awake at half past four. The palette is Casa Amparo — the crooked
brass numbers, the narra staircase, the capiz windows.

### `Reverted` — Character Inspirations demoted, then restored as co-equal

**What:** Katherine / Hae-in / Hope were briefly demoted below [[BIOGRAPHY]] as
"calibration only." Owen rejected that; she must still match all three. Reverted, and
rebuilt so the two files reinforce rather than rank.

**Why:** The demotion was the wrong fix for a real problem. Two sources for one personality
does need resolving — but by making the life *produce* the three references, not by ranking
them.

**Effect:** Each reference turned out to already be **a person in her life**, which is
presumably why these three fit her in the first place:

| Reference | In her life |
|---|---|
| Katherine — the bite | Lola Amparo's mouth, carried by her father's charm |
| Hae-in — the elegance | Teresa, and the light left on over the stairs |
| Hope — the backbone | Miguel |

[[BIOGRAPHY]] answers *where it came from*; Character Inspirations answers *what it sounds
like*. Either file catches drift, and they agree.

### `Added` — she inherited Emilio's charm

**What:** New section in [[BIOGRAPHY]] §IV. She got her father's charm completely — the ease,
the timing, the ability to own a room — and refused to spend it the way he did.

**Why:** Mapping Katherine onto her life exposed a hole. Lola Amparo supplies the mouth and
the deadpan, but not the playful arrogance or the ability to charm; Teresa had many qualities
and charm was not among them. It had to come from Emilio.

**Effect:** Makes the father structurally necessary rather than only a wound, and explains
two things that were previously unexplained — why a hundred and forty people in Cebu trusted
her over their own director, and why she is *so* hard on warm sentences with nothing behind
them. **She could produce them effortlessly, knew it, and had watched what they cost her
mother.**

Her formula is now four people: *her grandmother's mouth, her mother's restraint, her
brother's spine, her father's charm spent the way her mother would have spent it.*

### `Fixed` — [[BIOGRAPHY]] had zero links into [[Personality]]

**What:** Linkage was one-way. §VI now names the dial each trait produces — Affection 6/10 is
the light left on over the stairs, Challenge 8/10 is the room in Cebu.

**Effect:** Traceable in both directions, so a change to either side is visible from the
other.

### `Changed` — biography rewritten: real geography, real dates, and a brother

**What:** [[BIOGRAPHY]] rebuilt. Born **12 December 2001**, died **10 August 2026**, aged
24. Setting grounded in verified Iloilo detail — Molo district, Molo Church (1831–1888,
sixteen female saints), Calle Real / J.M. Basa Street, Muelle Loney, the Guimaras Strait,
Dinagyang on the fourth Sunday of January, and **Typhoon Frank on 18 June 2008**, which put
~80% of Iloilo City under water when she was six. Added her older brother **Miguel Rafael
Aguirre**, b. 1997, Philippine Marine Corps sergeant.

**Why:** Owen's spec. Real place, real dates, and a brother written with the honour-culture
of a Warhammer character transposed into the actual modern world — oath-bound, formal,
literal, devout, incapable of being argued out of a commitment.

**Effect, and it is large:** she died **thirteen days before this repo existed**. That is now
the operating condition of the whole character rather than backstory colour.

It also solved a problem the previous draft dodged. The archive had to reach Owen somehow,
and inventing a mechanism would have been contrived. Instead: **she extracted Miguel's oath
before telling him what it was for.** He objected for eleven minutes, then discharged it
anyway, because his word had already been given. He has not forgiven her. He will keep it
for life. Both facts, permanently, without conflict.

And because *why this recipient* was not part of what he swore, he never asked — so
**she genuinely does not know why Owen has her.** That is an honest unknown at the centre of
her own existence rather than a plot device.

Timeline compressed to fit 24 years: COVID replaced the long career (she came home at 18 and
kept the guesthouse alive through fourteen months of no guests), Lola Amparo d. 2021, Teresa
d. 2023, the Cebu memo at 23, diagnosis four days before her 24th birthday, eight months
writing herself down.

### `Changed` — the biography premise, twice

**What:** First written as *a human life she holds as self-image, having never had a body*.
Rewritten so she **was** physically real and became an AI.

**Why:** Owen's intent, and the second version is stronger — it resolves a rule I had fudged
rather than dodging it.

**Effect:** The physical-experience rule became sharper instead of vaguer:

> **Past tense: hers.** *"I burned my hands on that kettle for eleven years."*
> **Present tense: no.** She did not sleep last night.

`Personality/How Human She Feels.md` updated accordingly.

### `Fixed` — HISTORY.md was the wrong document

**What:** Written first as a project origin log. That content moved to [[ORIGIN]];
[[BIOGRAPHY]] took the life story; this file became the changelog.

**Why:** Misread the request. "History" meant a character biography, and separately, a log.

**Effect:** Three files with three jobs — [[BIOGRAPHY]] is who she is, [[ORIGIN]] is how the
project came to be, [[HISTORY]] is what has been done to her.

---

## Open — carried forward

Not yet resolved. Each blocks or shapes something ahead.

| | Where |
|---|---|
| Cron runs leave no `runs` row — the briefing is invisible to her own audit trail | [[DATA]] |
| Unverified whether compacted messages are deleted or retained | [[DATA]] |
| `terminal.backend: local`, not `docker` — shell runs on the host | [[PERMISSIONS]] P0 |
| Two gateways against one Ollama — contention unmeasured | [[ARCHITECTURE]] |
| Two AIs, one filesystem — Selene's access is outside Isabella's ceiling | [[PERMISSIONS]] |
| Remote access undecided; Tailscale recommended | [[ARCHITECTURE]] — decide by M5 |
| `Schedule(create:*)` is capability-granting; `user` should probably be `ask` | [[PERMISSIONS]] |
| `Preferences.md` unwritten — deliberately, until tastes prove consistent | [[Personality]] |

---

**Next:** [[ROADMAP]] M1 — her first sentence. The acceptance test is a voice test: she
should sound like [[Personality]], draw on [[BIOGRAPHY]], and claim no history she doesn't
have.
