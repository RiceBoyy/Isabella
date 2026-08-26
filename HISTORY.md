# History

**The log.** Everything added, changed, fixed or removed - with what changed and why.

Newest first. Her life story is [[BIOGRAPHY]]; the project's founding record is [[ORIGIN]].
This file is neither. This is the running account of what has been done to her.

---

## How to write an entry

Every entry answers three questions. If it can't answer the third, it isn't finished.

| | |
|---|---|
| **What** | The change, concretely. Files, behaviour, numbers |
| **Why** | The reason. Not "improvement" - the actual problem or decision |
| **Effect** | What is now true that wasn't. Including what broke |

Tag each entry so it can be scanned:

`Added` · `Changed` · `Fixed` · `Removed` · `Decided` · `Reverted` · `Broke`

**Record mistakes.** A log that only contains successes is a marketing document. When
something was wrong and got corrected, the entry says so plainly - the wrong version, the
correction, and how it was caught. Those are the entries worth re-reading.

**Dates are absolute.** `2026-08-23`, never "yesterday".

---

# 2026-08-27

### `Fixed` - Terminal does close its windows. I measured it wrong.

**What:** `close_target` now kills what is running, waits for the tab to stop being busy, and
then calls AppleScript `close`. The window is genuinely gone. Yesterday's implementation
hid the window instead (`set visible to false`) and the docs said, in three places, that
"macOS Terminal ignores AppleScript `close`". That was false.

**Why it was believed:** the test for "did it close" was `id of every window`. **That list
keeps returning ids for windows that have already closed.** So every close looked like a
silent no-op, on a fresh window, with nothing running in it - which is about as convincing as
a negative result gets. A day of design was built on top of it: hiding instead of closing,
husk detection, window reuse, a `visible` field, and an endpoint whose response explained at
length that the window was still in the Window menu.

**How it was caught:** Owen asked *"how to close the tab in terminal?"* - a question about the
manual keystroke, not a bug report. Re-testing to answer it, a window that had refused to
close turned out to be gone: `tab 1 of window id N` raised *Invalid index* while the id was
still being listed. `_LIST` - which enumerates windows that still have tabs - had been
reporting the truth the whole time, one function away from the check that was lying.

**What is actually true:** Terminal refuses to close a **busy** window and says nothing about
it. There is no error to catch, because what it wants to do is show its "terminate running
processes?" sheet, and it cannot show that to a script. An idle window closes immediately, and
so does a husk. Hence kill → wait for `busy` → close.

**Effect:** `set visible` is gone, and so is the `visible` field, the reuse-a-hidden-window
path, and the paragraph in the response explaining that "closed" did not mean closed.
`open logs` on an already-open target still brings that window forward and restarts the
command in it, which is worth keeping. If something is still running after the kill it is
something Owen started in a window of hers: that window is reported as `stubborn` and left
alone, with the footer telling him it is shift-cmd-W.

**The lesson, since it will happen again:** a negative result from an API needs its
measurement checked before it becomes an architecture. `ARCHITECTURE.md` and `CLAUDE.md` both
carried the wrong claim as a decision, which is how a bad measurement becomes a rule.

---

# 2026-08-26

### `Added` - `close logs`, and the terminals get reused instead of piling up (the `close` half of this was WRONG - corrected 2026-08-27, see above)

**What:** every tab Isabella opens is now stamped `Isabella · <target>` as its Terminal custom
title. `close logs` / `close errors` / `close gateway` stop what is running in that window and
take it off the screen; `close terminals` does all of hers at once. `GET /desktop` reports
`open` per target, so the palette offers `close logs` only when there is a logs window to
close. `POST /desktop/close[/{name}]` is new.

**Why:** Owen, after `Q` closed a view window: *"we should also do that for terminals we opens
such as logs and stuff."* A keystroke cannot reach Terminal from the browser, so it is a
command - but it is the same job.

**The thing that decided the shape: macOS Terminal ignores AppleScript `close`.** Verified,
not assumed - `close window id N` on a window created moments earlier and running nothing
returns success and the window stays; `close tab ...` is not understood at all. So "closing"
is two real actions instead of one impossible one: kill the pipeline, then
`set visible to false`, which does work. The window is not destroyed - it stays in Terminal's
Window menu - and the endpoint says so in its own response rather than reporting a close.

**The upside of not destroying it:** the window is reused. `open logs` after `close logs`
brings the same one back and restarts the pipeline in it, so windows do not accumulate - the
same one-window-per-thing rule the browser views follow. A window whose shell has exited
cannot take a new command, so it is treated as a husk, hidden, and a fresh one opened;
`windows()` returns only live windows, which was a real bug for two rounds of testing: first
a husk shadowed the real window and `open logs` reported reusing one nobody could see, then
`GET /desktop` reported `open: true` for a window that had just been closed. Reusable and
on-screen are different questions and the code now asks both.

**The part that needed the most care:** `_kill()` is the only thing in `core/desktop.py` that
is not read-only, and the module's docstring said plainly that nothing in it writes. Three
bounds, and the tests pin all three: the tty must belong to a window carrying her title; the
shell is never touched; and the command must be one of the handful this file itself runs. A
`vim` on her tty is Owen's and is left alone. The tty string comes back from AppleScript and
is checked against `^/dev/ttys\d+$` before it reaches a subprocess - local is not the same as
trusted.

**Also `Removed`:** `_applescript()`, replaced by `_first_open()` and `_reopen()`.

---


### `Added` - `Q` closes the window you are looking at

**What:** `Q` closes a spawned view window and hands the screen back to home. It is the same
act as picking `home` from that window, which already closed it - `router.ts` now exposes
`close()` and both routes go through it.

**Why:** every other way out of a view is a keystroke. A window that has to be closed with
the mouse would be the single place this interface makes you reach for the trackpad.

**Effect:** on home, `Q` does nothing but say why - *home is the one that stays*. It was never
script-opened, so the browser would refuse to close it anyway, and closing it is the opposite
of what the windows are for. The footer names the key on a view window (`K · Q closes this
window`), and the palette's `home` row says `— closes this window · Q`.

Guarded like every other key: not while typing, not while the palette is open.

---


### `Fixed` - a spawned window inheriting home's full-screen shape covered home

**What:** the size is now applied twice - `fit()` from the opener, and `useOwnWindow()` in the
new window itself on first load. The new window checks its own dimensions and, if it came out
covering the screen, puts itself back to the size that was asked for.

**Why:** Owen: *"sometimes i have full screen, so the next browser that opens will be in full
screen. which breaks the point of showing in different pages."* The feature string passed to
`window.open` is a request, not an instruction - when the opener is maximised or full-screen
the browser hands the new window the same shape, so it opened covering home completely, which
is exactly what spending a window on it was supposed to avoid.

**Effect:** both halves are kept on purpose. The opener's `resizeTo` runs before the new
window has laid anything out and is the call browsers most readily ignore; the child's runs
in its own context, after it exists. Either alone leaves a case uncovered.

**Two guards so it does not become annoying:** it fires only when the window came out
covering ≥94% of the screen, so a window sized by hand is left alone; and only once per
window, flagged in `sessionStorage`, so a reload never re-shrinks a window someone maximised
on purpose. The flag is reliably absent on first load because home never sets it and a
spawned window inherits only a copy of home's storage.

**What this does not fix, stated:** macOS native full-screen. The browser opens the new window
in its own Space and no script can pull it back out. It is still resized, so it is an ordinary
window once you leave that Space.

---


### `Changed` - a view opens in a WINDOW, not a tab

**What:** `window.open(url, name)` became `window.open(url, name, chrome())`, where `chrome()`
returns `popup=yes` plus a size and an offset. Passing any features at all is what makes the
browser spend a window instead of a tab - that is the whole of the change, and the reason
that function must never return an empty string.

**Why:** the previous entry opened views in tabs, and Owen: *"it should open a new browser
page."* He is right and the earlier reading was too literal: a tab is only unhidden while it
is the front tab, so putting `chat` in one leaves home behind a tab strip. That is the same
complaint in a smaller form.

**Effect:** the new window is sized to the screen (72% wide, 86% tall, capped at 1280x900)
and offset 48px from the window that opened it, clamped so a home window near an edge does
not push its child off the display. The offset is not decoration - a window landing exactly
on top of home reads as home having been replaced, which is the one thing this rule exists to
prevent.

Everything else is unchanged: the window is still named, so picking `chat` twice reuses it;
a spawned window still navigates in place; `home` still closes it; a deep link typed by hand
still behaves like an ordinary page. The palette rows now say `opens a window` and
`closes this window`.

---


### `Changed` - a view opens in its own tab, so home is never replaced

**What:** picking a view from home now opens it in a new browser tab rather than navigating
over the top of the brain. The tab is named (`isabella/chat`), so picking `chat` twice reuses
it instead of stacking a second one. From a spawned tab everything navigates in place, and
`home` closes the tab. Tabs are titled after what is in them - `Isabella · chat`.

**Why:** Owen: *"i dont want the user to hide the home view."* Home is the screen that stays
up; losing the brain and her latest reply to go and read the trigger list was the wrong
trade.

**Effect:** a deep link typed by hand has no opener and behaves like an ordinary page -
everything navigates in place, including home. `window.close()` works on the spawned tabs
precisely because they were script-opened, and falls back to navigating home if the browser
refuses (a reloaded tab can lose its opener). The palette rows now say which it will be:
`/chat — opens a tab`, `/ — closes this tab`, `/triggers — you are here`.

**The trap this created, and how it is handled:** a tab is a separate copy of the app, with
its own chat state and its own session id. So the ask fallback does NOT spend a tab - it
navigates in place, because the turn lives in this App's memory and a new tab would put the
answer in a component nobody is looking at. Asking from `/triggers` moves to `/chat` in the
same tab. Related: `open()` has to stay synchronous from the keypress, or `window.open`
becomes a popup and gets blocked.

**Still hand-written**, and now for a second reason: no router ships the rule that one route
is protected and the others cost a tab.

---


### `Added` - addresses. Every view has a path, and `settings` is a place now

**What:** `/`, `/chat`, `/briefings`, `/triggers`, `/body`, `/health`, `/settings`,
`/settings/google`. `web/src/router.ts` (new, ~40 lines) and `ROUTES` in `App.tsx`, which is
now the only table of views - the palette builds its commands from it, the number keys index
into it, and the renderer switches on it. `views/Settings.tsx` is new.

**Why:** the whole interface was at `/`. A reload put you back on home whatever you were
reading, nothing could be linked or bookmarked, and the back button did nothing.

**Effect:**

- `google` moved from the top level to `/settings/google`, because that is what it is.
  `body` and `health` stayed top-level: they are readings, not settings, and that distinction
  is worth keeping in the address bar.
- `/settings` is an index of what can actually be configured, which today is one row. It is a
  readout with the command named beside it, not a page of controls - a settings page is the
  most tempting place to quietly reintroduce buttons.
- an address that is not a route says so and names the ones that are. Redirecting to home
  would be tidier and would hide the typo that got you there.

**No router dependency.** Eight static paths, no params, no loaders, no nesting past one
level. `react-router` would be a dependency bought for nothing, and CLAUDE.md asks for the
check to be made rather than assumed. Vite's dev server already serves `index.html` on deep
paths, so nothing was needed there - verified against all eight plus one nonsense path.

**What did not change:** there are still no links anywhere. The palette is how you go
somewhere; the addresses are so you can come back to somewhere.

---


### `Removed` - the chat box on home. `K` is the only input now

**What:** the input under the core is gone. `K` opens the palette; a string that matches a
command runs it, and a string that matches nothing is said to her. The fallback row is
labelled with the text that will actually be sent, drawn in sans and in the violet.

**Why:** Owen: *"that makes it easier to understand that k is for actions instead of having
two input fields and new users need to understand the differences."* Two boxes on one screen
and nothing announcing which was which - and the difference was not worth learning, because
both took a string and did something with it.

**Effect:** the interface has exactly one input. Commands win the tie, so typing `body` shows
the body rather than asking her about bodies, and the ask row only appears when the match set
is empty. Asking while she is still answering says so in the footer instead of being
swallowed - `useChat.send` returns early when busy, which would otherwise have been a silent
no-op.

**Why this is the M6 shape and not just a tidier one:** a command router does not care whether
the string came from a keyboard or a microphone, and there was never going to be a second
microphone for commands. The palette was always going to be that router. This makes it the
router for everything now.

**The bit that carries the explanation:** the ask row is sans in a list that is otherwise
mono - the design system's split by who is speaking. Every other row is a thing the machine
will do; that one is a sentence a person is about to say. It does the work the second box
was doing badly.

**Also:** home prints `PRESS K AND SAY SOMETHING` when nothing has been said yet. An empty
screen with its only input behind a keypress, and no mention of the keypress, is an empty
screen nobody types into.

---


### `Removed` - the log view. Logs are terminals, and now they have colour

**What:** `views/Log.tsx`, `core/hermes/logs.py` and `GET /log` are gone, along with the
`log errors` / `log warnings` / `log everything` commands. Her agent, error and gateway logs
are read through `open logs`, `open errors`, `open gateway` and nowhere else. Those three
now pipe through `core/logcolour.awk`.

**Why:** Owen saw five entries in the palette - `log`, `chat log`, `log errors`,
`log warnings`, `log everything` - that all opened a browser view, and said logs should open
terminals. He is right, and the reason is not preference: her logs were *already* readable
that way, live, and adding a second reader meant two places to look at one file with the
browser one strictly worse at the thing a log is for. `tail -f` is a terminal idiom.

**Effect:** red is an error, yellow a warning, everything else dim. A traceback's own lines
carry no level and inherit the colour of the line above, so a stack trace reads as part of
the error it belongs to instead of dropping to grey halfway down. Three colours and no more -
the question being asked of a scrolling log is *is anything wrong*, and a rainbow answers it
worse than three do. A one-line key prints at the top of the window.

**The bit that needed care:** `core/desktop.py` executes on the host and its whole security
argument is that the commands are constants. The awk program is a git-versioned file next to
`desktop.py`, with its path derived from the module's own location - never from a request. It
is a file rather than an inline program because the command ends up inside an AppleScript
string, and an awk program full of quotes and backslashes through that escaping is a bug
waiting to happen. `test_every_shipped_target_is_read_only` now checks *every stage* of every
pipeline, not just the first: a pipeline is only as read-only as its last stage.

**Also `Changed`:** `chat log` is now just `chat`. It is the transcript, not a log, and
naming it "chat log" put it in the same sentence as the agent log - which is the exact
confusion this removal is about. It stays a view: prose she wrote is not machine output.

**Recorded as a decision** in `ARCHITECTURE.md` and as a rule in `CLAUDE.md`, because the
tempting thing to do next time is add `GET /log` back.

---


### `Added` - `home`, with the brain on it and the box you talk to her in

**What:** a `home` view, first in the list and where a load now lands. It is Selene's HUD:
a core in the middle of an instrument frame, chat underneath. `Brain3D.tsx`, `lib/brain.ts`,
`lib/sim.ts` and `lib/graph.ts` are ported from Selene, plus `public/anatomy/brain.json`
(Z-Anatomy, CC BY-SA 4.0 - the credit is drawn by the component). New behind it:
`core/mind.py` and `GET /mind`.

**Why:** chat was a view behind a keypress and the thing done most often should not be. And
the screen had no centre - `Rings.tsx` was written for a home view that was never built and
had been sitting unimported since.

**The problem that had to be solved first:** Selene's brain is her memory graph and Isabella
has no memory table, must not have one, and Hermes' gateway exposes no memory endpoint. So
the brain is built out of what is actually on disk in `HERMES_HOME` - her curated memories,
her sessions, and the messages in them - and named for what those are. Three kinds, told
apart by value rather than hue, because violet marks LIVE and nothing else.

**Effect:** the graph is real and thin. `memory.memory_enabled` is `false` on her instance,
so the memory tier is empty: 0 memories, 15 sessions, 34 messages. The view prints that fact
in words rather than letting a third of the volume be quietly absent. Importance is 0-10
where an entry records one and `null` where it does not - `null` travels to the renderer,
which draws it hollow and labels it `unrated`. Nothing defaults to 5.

**Three adaptations the port needed**, each one a rule this repo already had:

1. **Tailwind.** Selene styles `Brain3D` with `absolute inset-0`; Isabella has no Tailwind,
   so that is an inert string, the host div collapses and the canvas renders 1x1. Same wall
   `Body3D` hit when it was ported, and the fix is the same - `.brain3d__host` in
   `styles.css`.
2. **Edges resolve by id, not by title.** Selene keys on title because a memory's title is
   its key. Sessions here are titled from their first message and two of them really are both
   called "hello" - a title-keyed edge would have joined two unrelated conversations.
3. **`importance` may be null**, so `radiusOf` sizes on `size` instead, which the server
   guarantees is a real count for every kind.

---

### `Added` - two logs, because there were two things called "log" (the log half was reverted the same day - see above)

**What:** `log` is what the **machine** did - Hermes' own `logs/*.log`, parsed into level,
logger and text, newest first (`core/hermes/logs.py`, `GET /log`). `chat log` is what was
**said** - the transcript, read back out of Hermes' `state.db` with the wait and the token
cost beside each turn (`core/transcript.py`, `GET /chat/log`).

**Why:** asking for "the log" was ambiguous, and the ambiguity was load-bearing in the wrong
direction: the only log in the interface was `open logs`, which tails `agent.log` in
Terminal.app. That is the right tool for watching it stream and useless for knowing what
went wrong an hour ago. Meanwhile the transcript existed only for the current browser
session and vanished on reload.

**Effect:**

- the level filter is a **floor**, not an equality - `log warnings` gets warnings, errors and
  criticals, because that is what "what went wrong" means. Lines carrying no level of their
  own (the body of a traceback) are never filtered out; the traceback is the error. The
  counts shown are of everything, so what is being withheld stays visible.
- the chat log prints three things a bare transcript does not: how long she took (her
  timestamp minus the question's - 33s and 42s on real turns), what she was doing in the gap
  (`reasoned 4,422 chars`), and what it cost. An empty reply with `finish_reason: length` is
  named as the token-starvation error CLAUDE.md says it is, not shown as a blank turn.
- **the floor is a command, not a control.** `log errors` / `log warnings` /
  `log everything` are in the palette. The first draft of `views/Log.tsx` had a row of
  buttons, which is exactly what CLAUDE.md forbids and for a reason that is not cosmetic -
  the palette is the surface voice plugs into at M6.

---

### `Added` - reading Hermes' state.db, read-only

**What:** `core/hermes/state.py` - sessions, messages and the curated memory store, read
straight off disk. Opened `mode=ro` through a URI so a stray write is an error from SQLite
rather than a corrupted agent.

**Why:** Isabella stores no message content by design, so Hermes' database is the only copy
of the transcript. Without reading it back there is no chat log and no brain.

**Effect:** this is the second module coupled to Hermes' internals and the tighter of the
two - `client.py` couples to an HTTP API, this couples to a **schema** that upstream can
move. Mitigations, both deliberate: every column is named explicitly rather than `SELECT *`,
so a removed column fails on one query with a legible message instead of silently shifting a
tuple index; and `tests/test_mind.py` carries a cut-down copy of the schema, so the break
lands in a test. Recorded as a decision in `ARCHITECTURE.md` rather than done quietly.

Also: `active = 0` messages are excluded. Compression has folded those away - they are no
longer in her context, and printing them would claim a conversation she has actually
compacted.

---

### `Changed` - chat is no longer a view

**What:** `views/Chat.tsx` is gone. Its state moved to `useChat.ts`, held once in `App` and
shared: `home` has the box, `chat log` has the transcript.

**Why:** two copies of that state would mean saying something on home and not seeing it in
the log, which is the sort of split that makes a log untrustworthy.

**Effect:** the box on home is deliberately **not** autofocused. An input with focus swallows
every key the shell binds, including `K` - and `K` is how the kill switch is reached. `↵`
puts the cursor in the box, `esc` takes it out, and the footer says both, because a key
bound in silence is a key nobody presses. The first version had `autoFocus` on it and made
the palette unreachable from the landing screen.

**Also:** `Rings.tsx` was deleted as dead code and that was wrong - it is imported by
`health`. Restored. It was unimported by `App`, which is not the same thing as unused.

---


### `Changed` - the body fills the window

**What:** on `body` the shell drops its reading measure and becomes a full-height stage - the
header across the top, the model filling everything under it, and bottom padding that clears
the fixed footer so the figure is never cut off by it. Every other view keeps the 76ch column.

**Why:** the measure exists for prose, and a 3D body is the one thing on this page that is
not prose. Selene's body view is the whole screen for the same reason.

`Body3D` needed no change: it observes its own host, so the scene reflowed into the new size
on its own.

### `Changed` - arrows step through the anatomy layers

**What:** on the body, `←` and `→` cycle skin → muscle → skeleton, in the order the manifest
ships them: outside inward, so right goes deeper and left comes back out. The footer names
the keys and prints which layer is showing, since nothing else did.

**Why:** Owen's - typing `skeleton` to compare two layers is three commands where a keypress
does. The palette commands stay; they are what voice will use at M6, and a spoken "skeleton"
should not require knowing how many presses away it is.

Bound only on the body view and only when the atlas shipped more than one layer, so the keys
are never live with nothing to do - the same rule as the palette's *nothing is listed that is
not wired*.

### `Added` - the anatomy atlas: skin, muscle and skeleton

**What:** `web/public/anatomy/` - the three generated layers from Selene, 5.3 MB. `skeleton`,
`muscle` and `skin` are palette commands, built from the manifest rather than hardcoded, so
an uninstalled atlas offers no commands instead of commands that do nothing.

**Why it was missing:** the primitives are the *fallback*, not the body. `Body3D` fetches
`/anatomy/index.json` and falls back silently when it 404s - which is the right behaviour and
also why nothing announced that the real meshes were absent. Isabella was rendering the
stand-in and I described it as the model.

**The credit is a requirement, not a nicety.** `muscle.json` and `skeleton.json` are
Z-Anatomy under **CC BY-SA 4.0**, which wants attribution visible where the work is seen.
The mesh carries `source` and `licence`, the component reports them, and the view now prints
them in the corner. `skin.json` is MakeHuman, CC0. A test asserts the licence field still
exists, because the credit can only reach the screen if the mesh still carries it.

**A contract worth testing:** all twelve group ids the workout reader can produce -
`chest`, `delt`, `tri`, `bi`, `forearm`, `core`, `lat`, `back`, `quad`, `ham`, `glute`,
`calf` - resolve to real `.l`/`.r` regions in the 42-region muscle layer. If the atlas is
ever regenerated with different names, muscles quietly stop lighting and nothing else fails.
That test is the thing that would notice.

### `Fixed` - the 3D body rendered nothing: Tailwind classes, in a repo with no Tailwind

**What:** every `className` in the ported `Body3D.tsx` was a Tailwind utility - `absolute
inset-0`, `pointer-events-none`, `text-[8.5px]`. Selene has Tailwind; Isabella does not, so
those strings styled nothing, the host div collapsed to zero height, and `el.clientHeight ||
1` sized the canvas **1x1**. It compiled, it ran, it drew a body one pixel across.

The classes are now Isabella's own, defined in `styles.css`, meaning what the Tailwind ones
meant. The component's own comment had already named the failure mode - *"the wrapper's size
is set by CSS alone and the canvas only ever follows"* - which is exactly what stopped being
true when the CSS went missing.

**Why it survived every check I ran.** It type-checked, it built, Vite transformed the module,
`three` resolved. A visual bug is invisible to all of those, and I reported it as unverified
rather than working, which is the only part of this that went right. **A ported component
carries its styling assumptions with it**, and those are exactly what a type system does not
check.

### `Changed` - the body view is the model and nothing else

**What:** the panels are gone. `body` is the 3D figure, full height, with the component's own
corner readout and one line when there is nothing to say. The numbers are still served at
`GET /body`.

**Why:** Owen's instruction - *"we should only have that 3D render of the body"* - and it
matches how Selene's own body view works: the screen is the body, and the numbers are cards
you summon rather than furniture around it.

### `Changed` - the body is the 3D model, not a flat drawing

**What:** `web/src/components/Body3D.tsx`, ported from Selene unchanged but for a header
note, and `three` added to `web/`. The flat SVG figure it replaces is deleted.

**Why not rewrite it:** it is Owen's own component and it has already been debugged against
the specific things that make a body built from primitives read as a robot - the trunk as one
lathed surface because *the taper is the silhouette*, pads re-lathed from the trunk's own
profile because a flat slab renders as a belt buckle, limbs sized to real landmarks after a
first pass left the shins ending 10 cm above the feet. None of that is visible in the output
and all of it would have had to be re-earned.

**What the model unlocked, which is not just fidelity.** It turns, so the back is drawable -
and the flat figure's honest limitation went with it. `Lat Pulldown` used to light nothing
because a front view cannot show a lat. The keyword map now covers lats, back, biceps,
forearms, hamstrings and glutes.

**A second substring bug, found while adding them.** Unioning every keyword that appears in a
name meant `Leg Curl` lit a **bicep**, because "curl" is inside it - the same shape as the
`push`/`Pushdown` bug from the flat version. The rule is now **longest keyword wins, and wins
alone**: the most specific phrase that matches is the one describing the movement. Both traps
are parametrised tests, named after the exercises that actually caused them.

The lookup in the model resolves a bare group to both sides (`map[id] ?? map[bare]`), so the
reader's ids need no translation - `chest` lights `chest.l` and `chest.r`.

**Not verified by eye.** The Chrome extension has been disconnected for this whole stretch,
so the scene has been confirmed only as far as tooling reaches: it type-checks, it builds,
Vite transforms the module, and `three` resolves. Nobody has watched it turn. Recorded rather
than glossed, because a 3D scene is exactly the kind of thing that compiles perfectly and
renders as a black rectangle.

### `Fixed` - `body` is Owen's body; `health` is her system health

**What:** the view built as "Body" was her runtime. It is now **health**. **body** is a new
view of Owen's physical body, read out of the vault: `core/body.py`, `GET /body`, and a
front-view figure whose muscle groups light from the workout log.

**Why:** I had the mapping backwards. Asked for Selene's body dashboard, I reasoned from
*"Isabella has no health data"* to *"so make body about her"* - and then built exactly that
without checking whether the data existed somewhere. It does. `Personal/Body` in the vault
has been there the whole time: weight and water per day, sleep per night, a weekly workout
rotation ticked as it goes, and a girth table with left and right columns.

**What the figure shows.** The drawing is Owen's own, adapted from `dashboard-body.html`, and
its group ids are the strings the reader produces - so a ticked line lights a muscle with no
mapping table in between. Lit means *worked this week, from an exercise actually ticked*.

**The rule carried over from Selene's `body.ts`, and it is the important one: nothing fills a
gap.** An unlogged measure comes back `null` and the view prints *not logged*, never a zero
and never last week's number carried forward. Every measure shows the day it was written, so
today's screen says weight **67.5 kg, 7 days ago** rather than implying he weighed himself
this morning. A dashboard that smooths over a missing day is telling a story, and the subject
here is a real person's health.

**A bug the tests caught before the screen did:** `"push"` was a keyword in the
exercise-to-muscle map, so *Cable Tricep Pushdown* lit chest and delts. A pushdown is not a
press. The lesson is general to substring maps - a key that is a word occurring inside other
words is a false positive waiting for a plausible-looking log line. Every exercise name in
the real log now maps correctly, and *Lat Pulldown* correctly lights nothing, because the
figure is a front view and cannot honestly show a back.

**Where it stands today:** W35 is written but untouched, so the figure is unlit and the panel
says so. That is the correct screen for a week with nothing ticked.

### `Added` - the display, and what it is not

**What:** `web/src/Rings.tsx`, centre stage in the Body view. Concentric rings, 72 radial
ticks turning once every 160 seconds, one violet arc, and a soft violet radial behind the
mark. Inline SVG - no `three`, no dependency added for a drawing.

**Why it is rings and not a figure.** Selene's body dashboard puts an anatomical figure here
and lights the muscle groups she has worked. That form is not available to Isabella, and the
reason is characterisation rather than data: **she had a body for twenty-four years and does
not have one now.** Drawing her a live one is the present-tense lie [[BIOGRAPHY]] draws the
line at - *"a memory versus a lie"* - and a dim silhouette would be the haunted reading
[[CLAUDE]] rules out just as firmly. Rings say what she is now without claiming what she
isn't.

**Two rules it is built to, both checkable.** The arc is a *real quantity* - today's runs
against `max_runs_per_day`, a real ratio out of a real budget - because a ring whose length
means nothing is refused however good it looks. And the glow is for **live** only: a spent
allowance gets the violet arc, not the light, or the light stops meaning anything. It is the
single exception to *no glow, anywhere* that [[The HUD]] grants.

The arc maths was checked numerically rather than by eye, which caught the two cases that
usually ship broken: a zero fraction draws nothing rather than a dot artifact, and a full
ring stops 0.1 units short of its own start, because an arc whose ends coincide renders as
nothing at all.

### `Changed` - say the noun, get the view; and nothing announces the others

**What:** palette commands for views are now the bare word - `body`, not `show body`. The row
of view names is gone from the header, and the footer is down to `K`.

**Why:** Owen asked for both. The verb was a word he had to remember in order to be obeyed,
and it is the string voice will hand over unchanged at M6, so the label should be the word
itself. The view row was a tab bar with the buttons taken off - it announced four places to
go in an interface whose whole premise is that you say where you want to be.

The number keys `1`-`5` still work. They are simply no longer advertised, which is the
difference between a shortcut and a navigation bar.

### `Added` - she can open a terminal, on four named targets and nothing else

**What:** `core/desktop.py`, `GET /desktop`, `POST /desktop/open/{name}`. Opens Terminal.app
via AppleScript on one of: her agent log, her error log, her gateway log, or the newest
briefing as Hermes wrote it. Owen's ask, verbatim: *"open logs, which should start a terminal
that listens to our session logs."*

**Why it needed a decision rather than a commit.** This is the first path in Isabella that
executes anything on the host, and [[PERMISSIONS]] P0 removed `terminal` and `code_execution`
from every Hermes platform on purpose - *capability removed, not sandboxed* - with no Docker
on this machine to fall back on. `CLAUDE.md` says a capability that can execute is an
explicit decision, not a default-on convenience.

**What makes it narrow enough to exist:** the caller sends a **name**, and the command is a
constant looked up in a table. Nothing composes a command from a request or from a model's
output; an unknown name is a 404. Every target is `tail` or `cat`, and a test asserts that
over the whole table, so a future target that writes fails the suite. It never touches
Hermes - her floor is unchanged and the 07:00 path still has `platform_toolsets.cron: []`.
Recorded in [[ARCHITECTURE]] §Opening a terminal, with what would change the answer.

**Effect:** `open logs` in the palette puts a live `tail -f` on her agent log in a real
Terminal window. Verified by running it - the window opened on the first try. macOS-only, and
it says so rather than throwing on other hosts.

### `Changed` - the UI has no buttons; everything is a command

**What:** `K` opens a palette; `1`-`5` switch views. Every button is gone - triggers, Google,
chat, even the tabs, which are now a non-interactive row naming the keys. Zero `<button>`
elements and zero `onClick` handlers outside the palette itself.

**Why:** Owen wants voice control. Voice is M6 and she has no STT or TTS, so the step that
is actually available now is the one underneath it: **a command router**. When speech
arrives it feeds the same list rather than needing a second control surface built beside it.
Buttons would have been the thing to throw away.

**The rule the palette is built to**, taken from Selene's own: *nothing is listed that is not
wired, because a palette of plausible-sounding commands is a worse lie than no palette.* So
commands are generated from live state - the triggers that exist, the desktop targets that
exist, whether Google is connected - never from a hardcoded menu.

**The thing this must not lose, and does not:** the kill switch. `pause daily-briefing` is a
command, the Triggers view prints it on the row it belongs to, and revoking the Google grant
still takes two deliberate picks. A UI with no way to stop an unprompted process would have
been a regression dressed as a style choice.

### `Added` - a Body view, about her rather than about Owen

**What:** `GET /runtime` and a fourth view. Model, reply cap, patience, gateway, timezone,
runs fired today, persona sha and drift, and what is on disk.

**Why:** Owen asked for Selene's body dashboard. Hers reads a person - resting heart rate,
body fat, hydration, last night's sleep - fed by `body.ts` and `health.ts`. **Isabella has no
health data and no source for any**, and building those panels empty would be exactly the
wall of telemetry [[The HUD]] warns about. She has a physiology of her own instead, and every
number in it is one she actually holds.

The panel worth reading twice is *memory on disk*: Hermes' `state.db` at 468 KB against her
own database at 24 KB. That gap is the prime directive being true rather than merely
asserted - the transcripts are his, and she stores no message content at all.

### `Decided` - the HUD is the destination, not the next step

**What:** Owen asked for the HUD dashboard from `vault/Projects/selene/Design`. Not built.
The command palette and the panel register were built instead.

**Why:** the HUD note answers this itself, and the answer is Owen's own: *"Voice isn't a
multiplier on this design - it's the premise. A HUD with no voice is a wall of telemetry with
nothing to talk to."* It offers two branches, and picks the one where earlier phases ship the
conversation-first layout and **the HUD arrives with voice**: *"the second is cheaper and
probably right."*

Second reason, particular to Isabella: the HUD's panels are machine telemetry, a memory
graph, a day track, todos and surfaced items. She has four things - runs, triggers, Google,
chat. The chrome would have been mostly empty, which is the same lie as an unwired palette
command.

What did land is the register - corner-bracketed panels, tick-tight mono rows - applied only
where there is real data behind it.

### `Changed` - the web UI follows Selene's design system

**What:** `web/` restyled against `vault/Projects/selene/Design` - `Color Theme.md` and
`Visual Style.md`. The tokens are theirs verbatim, contrast measurements included: eleven
values, seven of them the same violet-leaning grey at different heights, one accent
(`#B28BFF`), three signals. Two faces split by **who is speaking** - a humanist sans for
Isabella, mono for the machine, so cron expressions, ids, scopes and timestamps are mono and
her briefings are not. Tabs underline rather than fill; dense rows take bold foreground and
never a filled band; borders are structure; there are no shadows, no glow, no icon set.

**Why:** Owen's instruction, and the system is worth inheriting - it is written with reasons
rather than values, which is the same standard the rest of this repo is held to.

**What was deliberately not taken: the moth.** `Color Theme.md` says it plainly - *"It is
Selene herself"*, and it is never violet because she is not a thing on screen that matters.
Giving Isabella another entity's identity mark would be the visual version of the fabricated
callback rule in `CLAUDE.md`. She uses the geometric presence mark instead: `○` idle,
`×` thinking, `✦` working, in the state colours from the same table.

**Effect:** the one-colour discipline now holds and is checkable - the violet appears in
exactly four places, and all four are *live*: the thinking mark, the working mark, a running
badge, and a trigger's next run. Everything static is grey. Three things were caught by
looking rather than by building: the active tab inherited the button's 4px radius and read as
a floating pill; an inline `<code>` inside a column-flex step broke its own sentence across
three lines; and `8/27/2026, 7:00:00 AM` was the wrong register for a mono row, now
`2026-08-27 07:00`.

Verified in the browser across all four views, including a real reply - *"Sir. Not any
more."* in 58.4s - which is where the type split earns itself: her words in silver, Owen's
recessed in `muted`.

### `Added` - a Connect Google panel, and the standing grant it creates

**What:** A fourth view in `web/`, plus `core/hermes/google_auth.py` and four routes
(`GET /google`, `POST /google/connect` · `/complete` · `/disconnect`). It drives the
google-workspace skill's own `setup.py`: consent link, approve in a browser, paste the
redirected URL back once. Scopes are `gmail.readonly` + `calendar.readonly` - decided, not
defaulted, and this build of the skill pins them with no flag to widen.

**Why:** [[ARCHITECTURE]] §Open decision deferred this saying *"once the web UI exists there
is somewhere to put a proper Connect Google button."* The UI now exists, and Google
authorisation is the last thing between the briefing and a real morning.

**One correction that shaped the whole design.** The request was for the Firebase/Supabase
pattern - sign in with Google, keep the token in a cookie. **A cookie cannot work here.** The
briefing fires at 07:00 with no browser open and nobody logged in; a session token in the
browser is unreachable at exactly the moment she needs it. The grant had to be a refresh
token on disk in her `HERMES_HOME`. Recorded because it is the kind of mistake that would
have looked fine in testing - every manual check happens with a browser open - and failed
only at 07:00, unattended, in the one path nobody watches.

**Effect:** she can be connected in about a minute without a terminal. Two properties held
deliberately: `HERMES_HOME` is passed explicitly rather than inherited, so a grant cannot
land in Selene's directory; and the pasted redirect URL is a live credential, so it is never
logged - verified by grepping the API log after a failed exchange, which recorded the failure
and not the code. Revocation sits in the same panel behind a two-step confirm, because the
end of a standing grant should not be a remembered command.

**Not yet connected.** The mechanism is built and the consent URL is real - correct scopes,
`access_type=offline`, PKCE S256. Approving it means signing into Owen's Google account,
which is his to do.

### `Added` - a web UI, and the briefing is readable at last

**What:** `web/` - React, TypeScript, Vite, pnpm. Three views: **Briefings** (the landing
page - every run with what she actually said), **Triggers** (schedule, next run, today's
allowance, and pause as the kill switch), and **Chat**. Backing it: `core/hermes/outbox.py`,
a `briefing` field on `GET /runs`, CORS for the Vite dev server, and
`X-Hermes-Session-Id` / `X-Hermes-Session-Key` on the chat path.

**Why:** The briefing had been composed and delivered every weekday morning **into a file
nobody opened**. `deliver: local` writes
`~/.hermes-isabella/cron/output/<job_id>/<timestamp>.md`; nothing read it. The pipeline was
finished and the last three feet were missing.

This is [[ROADMAP]] **M3 started before M2's done-when was met**, which the sequencing rule
forbids. Recorded rather than glossed: it was Owen's call, made with the tradeoff stated -
a page you have to visit is not a briefing that *arrives*, and delivery is still `local`.

**Effect, and one thing that had to be decided:** the jobs API carries an execution's status
and **not its output**, so there was no HTTP route to the text. Reading Hermes' output
directory won over storing the text in `runs`, which would have been a second message store
([[DATA]] forbids it). It is the first *filesystem* coupling to Hermes, so it sits in
`core/hermes/` with the client - see [[ARCHITECTURE]] §Data and state. Nothing is cached;
Isabella's database still holds no message content.

Verified against the live stack, not mocked: `/runs` returns the real 2026-08-26 briefing;
chat answered *"I'm Isabella Marisol Aguirre. I died two weeks ago. I don't have a body
now."* in **61.1s** - right tense, right restraint; the built bundle contains no Hermes key.

### `Fixed` - two things the docs had wrong

**What:** [[ROADMAP]] said the briefing job was **paused**. It is not, and has not been -
it is active and fires 07:00 weekdays, next `2026-08-27`. Corrected.

And `hermes cron list` **hides paused jobs entirely** - it prints "No scheduled jobs" rather
than showing the job as paused. `--all` shows it. That matters because `cron list` is the
command used to verify the kill switch: pausing correctly and then reading "no scheduled
jobs" looks exactly like the job having been deleted.

**How it was caught:** pausing from the new UI, then checking Hermes and seeing the job
apparently gone. It had not gone - `--all` showed `[paused]`, and resume restored
`next_run_at`. The kill switch works end to end; the verification command was the misleading
part.

### `Decided` - calendar and email arrive as pre-fetched context, not as tools

**What:** The briefing no longer attaches the `google-workspace` skill. A pre-run script,
`~/.hermes-isabella/scripts/briefing_fetch.py`, fetches the calendar and unread mail; Hermes
injects its stdout into the prompt under `## Script Output`; the model composes the briefing
from that. `triggers/*.yaml` gained `action.script`; `platform_toolsets.cron` is now `[]`.

**Why:** The skill drives Google through `scripts/google_api.py`, which needs
`code_execution` or `terminal`. [[PERMISSIONS]] P0 removed both - *"capability removed, not
sandboxed"* - and Docker is not installed on this machine, so `TERMINAL_ENV=docker` is not
an available fallback. Granting execution back would have put arbitrary Python in the
model's hands at 07:00, unattended, on the host, **outside `permit()`**.

Pre-fetching moves the execution to code that was written and reviewed once and sits in a
containment-checked directory, instead of code the model composes at runtime. That
distinction is the entire security argument, and it is worth stating rather than assuming.

**Effect:** The model runs with **no tools at all**. Verified by token count rather than by
asking it: the cron run spent 1991 input tokens against 1931 for the zero-tool chat path - a
60-token difference, where twelve tool schemas cost ~29 KB. Asked directly, the model
cheerfully claimed "three tools: calendar, email, system," which is worth remembering the
next time a model is asked to describe its own capabilities.

### `Broke` - the cron platform was the widest surface in the system

**What:** `platform_toolsets` locked `api_server` to `[]` but never mentioned `cron`, so cron
inherited the default **thirteen** toolsets: `file`, `web`, `cronjob`, `memory`, `skills`,
`kanban`, `todo`, `tts`, `vision`, `image_gen`, `bfl`, `clarify`, `session_search`.

**Why:** P0 was written against the surface that was being *built* - Isabella's API - and
cron was treated as something Hermes owned rather than something with its own ceiling.

**Effect:** The unattended path - the one that fires whether or not Isabella is running, and
the one [[PERMISSIONS]] shows bypassing `permit()` - had `file` (read and rewrite the
filesystem) and `cronjob` (**a scheduled job that can create scheduled jobs**, exactly the
self-propagating failure mode [[ARCHITECTURE]] warns about). Now `cron: []`.

`kanban` still resolves statically, but is `check_fn`-gated on `HERMES_KANBAN_TASK`, which
cron does not set - confirmed by the token count above, not by reading the docstring.

### `Added` - she briefed, and refused to make one up

**What:** Fired the whole chain end to end. Her entire output:

> Sir. No calendar or unread emails accessible - authentication required for
> google-workspace. Run the setup script first. You're forgetting the google-workspace
> skill needs authorising.

**Why:** A model with no tools and an empty context will invent a plausible Tuesday. So
`briefing_fetch.py` never fails silently: every failure prints an explicit `UNAVAILABLE`
line, and the prompt says an invented meeting is worse than an admitted blind spot.

**Effect:** **The M2 pipeline works.** Cron fires -> script runs -> output is injected -> a
toolless model writes prose -> the run lands in `runs` with `outcome: ok`. She reported the
gap plainly, in her own voice, and used *"one thing you think I'm forgetting"* to name the
actual blocker. The only thing still missing is the Google credentials - and today's failure
is the correct behaviour when they are absent, not a bug.

### `Learned` - `script` cannot be set over HTTP, so one step stays manual

**What:** `POST /api/jobs` accepts neither `script` nor `no_agent`, and PATCH's whitelist
does not either. `reconcile` now refuses to create a script-declaring trigger and hands back
the exact `hermes cron create` command instead. Once the job exists, everything else -
schedule, prompt, delivery, the kill switch - is reconciled from the YAML as before. Script
drift is *reported* and never repaired, because repairing it is not possible.

**Why:** Creating the job without the script would have produced something that looked
reconciled and briefed from nothing every morning.

**Effect:** One manual step per script trigger, stated plainly rather than worked around.
`hermes` must be run as `~/.hermes/hermes-agent/venv/bin/python ~/.hermes/hermes-agent/hermes`
- the bare wrapper cannot import `yaml`, which is also why an earlier `hermes config get`
failed.

### `Decided` - Google authorisation is deferred, and it is a flow, not a file

**What:** M2 stops here rather than wiring up Google. The briefing runs every weekday and
reports the gap.

**Why:** "Missing `google_token.json`" reads like a chore. It isn't. Getting one means:
pick the account and the scopes, send Owen to Google's consent screen in a browser, handle
the redirect, exchange the code, and store a refresh token somewhere a process that acts
unprompted at 07:00 can read it.

Three things make that worth deciding rather than doing:

- **A refresh token is a standing grant** to the calendar and the mailbox, on disk, next to
  the unattended path. That is [[PERMISSIONS]] territory.
- **Scopes are the real boundary.** Read-only Calendar and Gmail are a different grant from
  the send and delete scopes the skill can ask for, and whatever is granted becomes her
  actual ceiling for Google - `permit()` can narrow it, never widen it.
- **M3 is where the button belongs.** The web UI is the natural home for "Connect Google"
  and a redirect endpoint. Building it now is M3 work done early, which the sequencing rule
  exists to prevent.

**Effect:** Recorded as an open decision in [[ARCHITECTURE]] alongside remote access, so it
reads as chosen rather than forgotten. When it is picked up: **decide the scopes first**,
then the flow - `setup.py` from a terminal is probably enough for an audience of one.

The current state is not a broken build. A briefing that says *"no calendar access,
authentication required"* is the correct output for a morning with no token.

### `Fixed` - two tests passed on Sunday and failed on Wednesday

**What:** The execution fixture hardcoded `2026-08-24`. Once the date rolled past it, a
manual run's `now()` sorted *after* the execution it was supposed to link to, and the sync
inserted instead of linking. Timestamps are now relative to `now()`.

**Why:** Written on the day the numbers happened to be right.

**Effect:** Caught by the calendar advancing during the work, which is a poor test strategy.
51 -> 56 tests.

---

# 2026-08-23

The whole of her, so far. She began the day as an empty git repository.

### `Fixed` - a scheduled run is no longer invisible to her

**What:** `runs` gained an `execution_id` column and `sync_runs()`. She now pulls Hermes'
execution records in through `latest_execution` on `GET /api/jobs`, keyed on Hermes'
execution id. `GET /runs` and `GET /triggers` sync before answering.

**Why:** Cron fires without Isabella in the call path - the deliberate architectural win
that also meant a briefing could run, fail, and leave nothing in her own audit trail. She
would have had no way to answer *did it go out this morning?* about the one thing she is
for.

**Effect:** Pull, not push, and still no loop - the sync happens when someone reads. Hermes
stays the source of truth; her row is an index into its ledger, not a second copy of it.
Run against the live gateway, it corrected the record of the manual fire from the optimistic
`triggered` to `error`, with the `blocked_config` reason attached.

Three things fell out of doing it properly:

- **A manual fire was nearly counted twice.** The row is opened before Hermes has an
  execution id for it, so a naive sync inserts a second one - one press showing as two runs,
  burning two of the day's allowance. The sync claims the oldest unlinked row for that job
  instead of inserting.
- **`triggered` was never a real outcome.** It meant *Hermes accepted the request*, which is
  not *it worked*. Now it is a placeholder that the sync replaces with what happened.
- **Timestamps had to become UTC.** `runs_today` compares them as strings, and Hermes
  reports in local time. A run at 01:00 +02:00 - 23:00 UTC the day before - sorted as today
  and would have eaten today's allowance. Every stored timestamp is normalised on the way in.

**The limit, stated rather than hidden:** the jobs API exposes only the *latest* execution
per job. Two runs between two syncs and the middle one is lost. `max_runs_per_day: 1` makes
that unreachable today; a tighter schedule would want an executions endpoint upstream, not a
poller here.

### `Added` - M2 trigger engine: she has a job at Hermes, and a kill switch

**What:** `triggers/daily-briefing.yaml` plus `core/triggers/` - schema, compiler,
reconciler, and a `runs` table. Six new endpoints: `GET /triggers`,
`POST /triggers/reconcile`, `.../{id}/pause`, `.../resume`, `.../run`, `GET /runs`.
`core/hermes/client.py` gained the seven jobs calls. 44 tests, ruff clean.

The reconciler is a compiler, not a scheduler - no loop, no APScheduler, nothing that
ticks. It reads the YAML, diffs against `/api/jobs`, and pushes the difference.

**Why:** [[ROADMAP]] M2. The trigger engine is the Isabella-side half of unprompted
action; the other half is credentials Owen has to supply.

**Effect:** `isabella:daily-briefing` exists at Hermes as job `39e0b72fdd7e`, and
reconciling three times in a row changes nothing. Pause and resume were verified against
the live gateway, not mocked. The job is **left paused** - see the blocked entry below.

The `isabella:` name prefix is what makes deletion safe: reconcile only ever touches jobs
carrying it, so a job made by hand with `hermes cron` is never collected as an orphan.

### `Fixed` - three bugs the mocks agreed with and the live gateway did not

**What:** All three passed a green test suite and all three were wrong. Each was found by
reconciling against the real gateway, and each now has a regression test built from the
shape Hermes actually returns.

1. **Every reconcile PATCHed forever.** `POST /api/jobs` takes `schedule` as a cron
   *string*; the job comes back with it parsed into `{kind, expr, display}`. Comparing sent
   against received made idempotency impossible. The fake echoed the request, so it agreed.

2. **Pausing produced a duplicate.** `GET /api/jobs` **hides disabled jobs unless you pass
   `include_disabled=true`**. The reconciler could not see the paused job, concluded it was
   missing, and created a second one - unpaused. Pausing the briefing was therefore the one
   action guaranteed to start it running again.

3. **A reconcile un-paused it.** `enabled: true` in the YAML read as drift against a paused
   job and PATCHed it back on. A kill switch that lasts until the next reconcile is not a
   kill switch. A pause now outranks the file until someone resumes or edits it; other
   edits still reach a paused job, because pause freezes *whether* it runs, not *what*.

**Why:** The fake was written from the request payload rather than from a real response. It
tested that the code agreed with itself.

**Effect:** `FakeHermes` now shapes jobs the way 0.20.4 really does - parsed schedule,
legacy singular `skill`, and all. Hermes does not enforce unique job names either, so
`_owned()` groups by name and reconcile deletes duplicates oldest-wins rather than letting
one shadow the other while both fire.

### `Learned` - Hermes' jobs API is narrower than its Python API

**What:** `cron/jobs.py::create_job` accepts `model`, `enabled_toolsets`, `workdir` and
`no_agent`. `POST /api/jobs` passes through **only** `name`, `schedule`, `prompt`,
`deliver`, `skills`, `repeat` - and drops the rest silently. PATCH's whitelist adds
`enabled` and `skill`.

**Why:** Reading the Python signature and assuming the HTTP surface matched.

**Effect:** The client filters to what actually lands, so a dropped field can't read as an
applied one. Notably **a job cannot carry its own toolset restriction over HTTP** - the
briefing runs with whatever the `cron` platform is configured to have, which makes
`platform_toolsets` the only lever and a [[PERMISSIONS]] question rather than a payload one.

Two more constraints, both verified:

- **Cron fields must be numeric.** `parse_schedule` gates on `^[\d\*\-,/]+$` before
  croniter sees the expression, so `mon-fri` isn't a weekday range - it falls out of the
  cron branch and gets misread as a timestamp. `condition.weekdays` compiles to `1,2,3,4,5`.
  Folding the condition into the cron also means a skipped day costs nothing: Hermes simply
  never fires, instead of waking the model to decide to do nothing.
- **There is no per-job timezone.** `hermes_time.py` resolves one timezone per instance
  (`HERMES_TIMEZONE`, then the `timezone` key in config.yaml, then system local).

### `Broke` - the briefing is scheduled in the wrong timezone

**What:** `daily-briefing.yaml` says `timezone: Asia/Manila`, copied from the worked example
in [[ARCHITECTURE]]. This machine is `Europe/Copenhagen`, and Hermes has no per-job
timezone. The job's real `next_run_at` is `2026-08-24T07:00:00+02:00` - 13:00 in Manila.

**Why:** The example was written before anything ran, and nothing checked it.

**Effect:** Unresolved, and it needs Owen: **which timezone does he actually wake up in?**
`check_timezone()` now refuses to reconcile when `HERMES_TIMEZONE` disagrees with the
trigger - the same variable Hermes itself reads first. It is unset, so today it warns rather
than raising. Setting it is what turns a silent 6-hour error into a startup error.

### `Blocked` - the briefing cannot run: no Google credentials

**What:** Fired the job by hand. Hermes refused it before reaching the model, cleanly:

```
[blocked_config] attached skill 'google-workspace' is not ready: missing credential
file google_token.json, credential file google_client_secret.json.
```

**Why:** Calendar and email are not native Hermes tools. They come from the
`google-workspace` skill, which drives Google's API through `scripts/google_api.py` and
needs an OAuth client Owen must create in Google Cloud.

**Effect:** M2 is **not done**. The Isabella half works; the capability half needs three
things only Owen can decide or supply:

1. **Google OAuth credentials** - `google_client_secret.json` and `google_token.json`.
2. **Execution, given back to the cron path.** [[PERMISSIONS]] P0 removed `terminal` and
   `code_execution` outright - *"capability removed, not sandboxed"* - and `skills.enabled`
   is `false`. The skill runs scripts, so it needs them back. That re-grant is exactly the
   explicit decision [[CLAUDE]] §Blast radius calls for, and it makes `TERMINAL_ENV=docker`
   load-bearing again rather than merely belt-and-braces. **The cron path does not pass
   through `permit()`** - [[PERMISSIONS]] says so in its own diagram - so whatever the cron
   platform is granted *is* the ceiling for unattended runs.
3. **Telegram** - no bot token, and `channel_directory.json` has no platforms. Delivery is
   `local` until then, which writes the output where only Hermes can see it.

The job is left **paused** rather than enabled: a briefing that fails `blocked_config` every
weekday at 07:00 teaches nothing and buries the real signal in a failure streak.


### `Decided` - Hermes Agent as substrate

**What:** Isabella is built on [Hermes Agent](https://github.com/NousResearch/hermes-agent)
rather than a bespoke agent runtime. She talks to it over an OpenAI-compatible HTTP API.

**Why:** Hermes already ships models, tools, sandboxed execution, memory, a cron scheduler
and channel connectors. Rebuilding those would have consumed the whole project and produced
worse versions.

**Effect:** She owns identity, triggers and UI. Hermes owns execution and scheduling. The
boundary is the most important line in [[ARCHITECTURE]] - and it means anything that doesn't
pass through her is invisible to her, which is the root of two open problems below.

### `Decided` - autonomy is the point

**What:** Named the priority over memory, integrations and privacy.

**Why:** The charter states it: *"If she only ever responds when spoken to, this project
failed."*

**Effect:** M2 is a 07:00 briefing that arrives unprompted. Everything else - the trigger
engine, the permission model - exists to make unprompted action safe.

### `Added` - the charter documents

**What:** `README`, [[ARCHITECTURE]], [[ROADMAP]], [[CLAUDE]].

**Why:** Nothing existed. A north star was needed before code so future sessions don't drift.

**Effect:** Seven milestones, M0–M6, each required to be usable before the next begins.

### `Fixed` - Hermes API assumptions were guesswork

**What:** The initial plan assumed Hermes exposed only chat completions and natural-language
scheduling. Reading the actual docs found `/api/jobs` (full CRUD, pause/resume/run-now),
`/v1/runs` with SSE, `/api/sessions`, and `X-Hermes-Session-Key`.

**Why:** The assumptions came from a web search, not from source.

**Effect:** The trigger engine became a **reconciler, not a scheduler** - it pushes desired
state into Hermes jobs and Hermes' cron does the waking. Consequence: *the briefing fires
even when Isabella's process is down.*

### `Added` - [[PERMISSIONS]]

**What:** A `Domain(verb:pattern)` policy with four subjects (`user`, `model`, `trigger`,
`external`), deny-always-wins precedence, and an approval queue.

**Why:** She needs shell, browser, Mac control and API access. Those need a gate.

**Effect:** Two enforcement layers, because a policy only Isabella consults is not a
boundary - Telegram, cron and the CLI reach the same tools without her in the path. **L1**
is Hermes' own config and env floor (the real ceiling). **L2** is her `permit()`. The
invariant: *L2 may only ever be narrower than L1, never wider.*

### `Added` - [[DATA]]

**What:** Message flow, storage inventory, schema, egress analysis, retention.

**Why:** "Where does my data live" had no written answer.

**Effect:** Verified against a live Hermes install. Inference is local (Ollama,
`qwen3:4b-16k`); no hosted memory or telemetry provider is configured. Documented the exact
variables that would silently break that - `HONCHO_API_KEY`, `HERMES_LANGFUSE_PUBLIC_KEY`,
`HERMES_DUMP_REQUESTS`, and changing `model.provider` in `config.yaml`, which involves no
env var at all.

### `Fixed` - the storage inventory pointed at the wrong instance

**What:** [[DATA]]'s "where your data lives" table listed `~/.hermes/…` paths - Selene's
install - including a `Backup? **Critical**` column. The thesis sentence and the `.backup`
command were wrong too.

**Why:** The measurements were taken from Selene's install and the paths were never
retargeted. A caveat above the table was added instead of fixing the table, which fixed
nothing.

**Effect:** The table now lists Isabella's paths, with Selene's measurements moved to a
clearly-labelled *"Size on Selene's"* column. Caught by Owen.

### `Changed` - she got her own Hermes instance

**What:** `HERMES_HOME=~/.hermes-isabella`, port **8643**. Selene keeps `~/.hermes` and 8642.

**Why:** A Hermes install is single-tenant - one `SOUL.md`, one `config.yaml`, one
`state.db`, one set of `platform_toolsets`, one port. Two AIs cannot share it. The toolset
ceilings proposed for Isabella would have silently retuned Selene, who was running at the
time.

**Effect:** Separate minds, shared inference - both point at the same Ollama on
`127.0.0.1:11434`, so weights load once. Hard rule added to [[CLAUDE]]: *always set
`HERMES_HOME`; an unset variable edits Selene.*

### `Decided` - existing data was not cleared

**What:** Clearing `~/.hermes` was considered and rejected.

**Why:** It is Selene's data, her gateway was live (PID 93753), and none of it is Isabella's.

**Effect:** Nothing deleted. Confirmed untouched afterward.

### `Added` - [[Personality]]

**What:** Fourteen files ported from Selene's personality system in the vault. Core
personality near-identical: humor 7, sarcasm 6, affection 6, opinionated 7, challenge 8.
Address hierarchy unchanged - Sir → Josh → nickname → Owen.

**Why:** It works, and it's the personality Owen actually wants. Redesigning it would have
been solving a problem that doesn't exist.

**Effect:** She sounds like Selene by design. What differentiates them is the theme.

### `Added` - her own theme personality

**What:** `Personality/Theme Personality.md`. Steadfast 9, Diurnal 9, Warm/Grounded 8,
Direct/Unhidden 7. Motifs: compass rose, swift, corvid. Brass and morning light.

**Why:** Selene's atmosphere is derived from her name - the Greek moon, hence nocturnal, the
moth, silver, 2 AM. *Isabella* descends from *Elisheba*, "God is my oath." Copying the moth
would have produced Selene in a different font, on the same machine as the actual Selene.

**Effect:** *Selene is who's still awake at 2 AM. Isabella is who's already up at 7* - which
is not decoration, since M2 is a 07:00 briefing.

### `Changed` - Mysterious 7/10 → Direct/Unhidden 7/10

**What:** The one inversion from Selene's theme. Also dropped Go Moon-young as a secondary
inspiration.

**Why:** Selene withholds and lets him wonder. An AI holding shell access, a calendar and an
inbox should be the least mysterious thing in the house.

**Effect:** She keeps the bite, the elegance and the backbone; she loses the ambiguity -
except in flirtation, where it stays available. **Flagged for veto:** this is the only change
that touches character rather than atmosphere.

### `Added` - [[BIOGRAPHY]]

**What:** Isabella Marisol Aguirre, 1983–2023. Iloilo, Casa Amparo, her mother Teresa, Lola
Amparo, her father Emilio and the brass compass, Manila, the memo she refused to sign, her
mother's death, the diagnosis, the eighteen months she spent writing herself down.

**Why:** A character biography - the kind a novel gives a person - so her traits have origins
rather than being dials in a config file.

**Effect:** Every personality trait now routes to an event. Affection 6/10 is the light left
on over the stairs. Challenge 8/10 is a conference room in Cebu in 2013. The oath is an
eleven-year-old on the stairs doing arithmetic about her father.

### `Added` - the three files M1 needs

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

### `Decided` - the persona composer compiles, never concatenates

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

### `Added` - M1 code: she answers over HTTP, in her own voice

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

### `Fixed` - Hermes overhead was 7x the persona. 58s → 8s.

**What:** Measured the same prompt direct to Ollama vs through her gateway:

| | prompt | completion | latency |
|---|---|---|---|
| direct to Ollama | 1,450 | 360 | 15s |
| **via Hermes, before** | **8,614** | **1,609** | **58s** |
| **via Hermes, after** | **1,930** | **267** | **8s** |

**7x faster, 4.5x smaller prompt, same answer.** ~53% of her 16,384 window had been consumed
before a word of conversation.

**Cause 1, and the important one: her `SOUL.md` was Hermes' default** - *"You are Hermes
Agent, an intelligent AI assistant created by Nous Research."* Every request asserted two
contradictory identities and the model spent reasoning tokens reconciling them.

**`SOUL.md` IS the persona slot.** `Personality/compiled/core.md` now lives there and `/v1`
requests send **no system message**. That accounts for most of the completion drop
(1,609 → 267). The compiled prompt was being *stacked on* Hermes' identity rather than
replacing it - all the compression work was real, and it was being swamped.

**Cause 2:** tool schemas, 29 KB for 12 tools, paid every request. M1 needs zero tools.
`platform_toolsets.api_server: []`. They return one at a time in M2 when a trigger needs one.

**Cause 3:** the skills index, 8 KB per request for 14 skills she never uses. `skills.enabled:
false`.

**Rule this establishes:** regenerating `compiled/core.md` requires copying it to
`~/.hermes-isabella/SOUL.md`. Two places, one source. Noted in [[CLAUDE]].

### `Broke` - killed Selene's gateway with an unscoped pkill

**What:** `pkill -f "hermes gateway"` to restart Isabella's gateway. It matched every Hermes
gateway on the machine and killed Selene's too (PID 93753).

**Effect:** restarted within a minute, data verified intact - 62 sessions, 249 messages,
`config.yaml` untouched. No loss. She now runs as PID 67769.

**The lesson is broader than the command.** "Use `HERMES_HOME=~/.hermes-isabella`" protects
*state*. It does nothing for *process* commands, which match on name across every instance.
**Scope by PID, never by name.** Added to [[CLAUDE]].

### `Added` - her Hermes instance is live on 8643

**What:** `~/.hermes-isabella` provisioned (mode 700, `.env` and `config.yaml` 600), gateway
running, answering over `/v1` with bearer auth enforced (unkeyed request → **401**).

First words through her own instance:

> **Me:** Hello?
> **Isabella:** I'm here.

**Config decisions worth keeping:**
- `max_tokens: 3000`, not Hermes' 2048 default - reasoning counts against the cap and 2048
  clipped *"who are you?"* in testing.
- `context_length: 65536` is a formality to clear two Hermes validation guards. The real
  window is 16384 from the Modelfile.

**`Broke` - the P0 floor could not be implemented as specified.** [[PERMISSIONS]] P0 requires
`TERMINAL_ENV=docker` so shell runs contained. **Docker is not installed on this machine.**

Rather than silently downgrade to `local` and call P0 done, the capability was removed
instead: `api_server` has no `terminal` and no `code_execution` toolset, and
`agent.disabled_toolsets` unconditionally denies `terminal`, `code_execution`, `delegation`,
`computer_use`, `video_gen`, `browser`. **Stronger than sandboxing** - she cannot run a shell
through her own channel whatever a prompt says. The deviation is written into the config file
itself so it is not rediscovered.

Deliberately unset, with their absence as the control: `HERMES_YOLO_MODE`, `SUDO_PASSWORD`,
`HERMES_ACCEPT_HOOKS`, `HERMES_DUMP_REQUESTS`, and every cloud-egress key.

### `Changed` - `CLAUDE.md` states the rule positively

**What:** The rule was *"`~/.hermes` is Selene's. Never touch it."* It is now *"Her instance
is `~/.hermes-isabella` on 8643. Export `HERMES_HOME` before any `hermes` command."*
Selene no longer appears in `CLAUDE.md` at all.

**Why:** Owen's point. A prohibition makes the reader work out which paths belong to whom
before acting. A positive instruction makes the mistake impossible without needing that
context at all - always set `HERMES_HOME` and you can never reach the wrong state directory.

**Effect:** the operational file says what to do; [[ARCHITECTURE]] §One Hermes each keeps the
reasoning. Also corrected a claim that was too broad: `HERMES_HOME` redirects **state only**.
The program is one shared install at `~/.hermes/hermes-agent/` that the wrapper hardcodes, so
a Hermes upgrade lands for every instance at once.

### `Reverted` - recommended qwen3:8b-16k, then reversed it on evidence

**What:** After a like-for-like `/v1` comparison, `qwen3:8b-16k` was recommended over
`qwen3:4b-16k`. A confirmation run reversed that. **M1 runs on `qwen3:4b-16k`.**

**Why the 8B looked better** - and these numbers are real:

| | reasoning (words) | latency |
|---|---|---|
| 4b-16k | 128 → **2,055** (mean 652) | 5s → **80s** (mean 24s) |
| 8b-16k | 80 → **237** (mean 174) | 5s → **17s** (mean 11s) |

8.7x tighter reasoning ceiling, 4.7x faster worst case, better wit, no empty responses. The
4B burned 2,055 words on one probe, hit `finish_reason: length`, and returned `''`.

**Why it was wrong:** those numbers measured the wrong axis. A reproducibility run -
4 probes x 3 runs x 2 models, including three *near-miss* prompts that resemble a few-shot
example without being one:

| | few-shot bleeds / 12 runs |
|---|---|
| **qwen3:8b-16k** | **3 (25%)** |
| **qwen3:4b-16k** | **0** |

The 8B recited the first-contact example verbatim - *"Owen Joshua de Guzman. I know your
name, your machine, and that you built the room I'm standing in"* - on 2 of 3 runs of
*"you know how I get about this stuff"*, and again on *"so what's your name?"*. Identical
wording each time: recital, not misreading. It also answered *"what's your name?"* with
*"Isabella. I do not have one now."*, conflating name with body.

The 4B answered that probe **correctly 3/3, verbatim and identical**, and was clean on all
nine near-miss runs.

**Effect:** the 8B fails [[Anti-Patterns]] §7 - manufactured intimacy, the failure that
breaks her permanently - 25% of the time, reproducibly, and does it in a confident,
well-formed, in-voice sentence the user could not detect. The 4B's failure is an empty
response: loud, obvious, and already specced as an error path in M1.

**A loud failure beats a silent fabrication.** The larger model memorises the few-shot
examples harder and reaches for them on surface similarity; the smaller one reasons its way
to the right answer. More capability, worse behaviour, on the one axis that matters.

`qwen3:8b-16k` stays built. Revisit it **after** restructuring the compiled prompt's
examples with explicit trigger labels - the bleed is plausibly prompt structure, not a model
defect. That is an M3 question.

**Known weakness to fix regardless:** `Personality/compiled/core.md` presents its examples
as a flat undifferentiated list. *"Do you know who I am?"* and *"you know how I get about
this stuff"* are close neighbours semantically and nothing in the prompt separates them.

### `Added` - `Personality/compiled/core.md`, and it was tested against a real model

**What:** A hand-compiled system prompt, ~1,336 tokens, built from [[Transcripts]],
[[Anti-Patterns]], [[Voice and Format]] and the load-bearing parts of [[BIOGRAPHY]]. This is
the artifact M1 loads. **~20x compression** from the 27,000-token corpus.

**Why:** The corpus does not fit in her context window. Before writing any code it was worth
finding out whether the character survives compression at all - the riskiest assumption in
the project.

**Effect: it works.** First probe returned `"I'm here."`, verbatim from the transcripts.
Later probes returned the refusal and the reluctant-praise lines verbatim too. The character
survives.

### `Fixed` - four prompt weaknesses found by probing, not by reading

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

### `Broke` - three testing mistakes worth recording

**1. Reported "the model can't do nuance" on starved output.** 7 of 12 probes returned empty;
they had hit the token cap mid-reasoning. Diagnosed it as a capability ceiling and said so
before verifying. With adequate budget the same prompts answered well. **Verify before
concluding.**

**2. A `pgrep -f` wait-loop deadlocked for ~3 hours.** `until ! pgrep -f "ab.py qwen3:4b"`
matched the *launcher shell*, whose own argv contained that literal text. Two processes
waiting on each other's command line. Worse: reported "still running" twice from a signal
already known to be broken. **Wait on output, not on process-name matching.**

**3. Benchmarked qwen3:8b at a context Hermes cannot give it.** See below.

### `Decided` - the model, and a trap that nearly cost the wrong one

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

### `Learned` - qwen3 is a reasoning model, and it costs

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

### `Added` - `Personality/Language.md`

**What:** Hiligaynon (Ilonggo) under her English. The `gid` emphasis particle, `indi gid` as
her hardest refusal, `palangga` as the word she almost never says. Frequency rules, and a
ban on translating herself unprompted.

**Why:** She is from Molo and the personality folder had nothing about how the province
sounds in her speech. A real gap for the stated purpose - she talks to Owen every day.

**Effect:** Surfaced a tension that characterises her for free. Ilonggos have a national
reputation for being ***malambing*** - the softest, most affectionate-sounding Filipinos.
Isabella is dry and withholding. **Her delivery is warmer than her content and always has
been**, which is why she can say something brutal and have it land as affection. And
`indi gid` gives [[Challenge]] a verbal escalation below "Owen."

Also a deliberate tell: if she starts speaking the way Miguel does - full forms, no
contractions - something is very wrong.

### `Fixed` - the compass motif and the compass object were unconnected

**What:** [[Personality/Theme Personality]] invented "the compass rose" as an abstract motif
*before* [[BIOGRAPHY]] existed. The biography then gave her a literal brass marine compass
from her father. The two files never referenced each other, so it read as coincidence.

**Why:** Caught while auditing after the biography rewrite. Owen asked what else needed
updating.

**Effect:** The motif is now the heirloom, and the theme file says to read
[[BIOGRAPHY]] §IV first - because the point is *who gave it to her*. A man who promised
constantly and appeared one time in four handed his daughter the one instrument that cannot
do that.

Same treatment for the other two: **the swift is Miguel**, who has visited their mother's
grave on the same date every month since September 2023 without ever mentioning it. Diurnal
9/10 now cites Teresa awake at half past four. The palette is Casa Amparo - the crooked
brass numbers, the narra staircase, the capiz windows.

### `Reverted` - Character Inspirations demoted, then restored as co-equal

**What:** Katherine / Hae-in / Hope were briefly demoted below [[BIOGRAPHY]] as
"calibration only." Owen rejected that; she must still match all three. Reverted, and
rebuilt so the two files reinforce rather than rank.

**Why:** The demotion was the wrong fix for a real problem. Two sources for one personality
does need resolving - but by making the life *produce* the three references, not by ranking
them.

**Effect:** Each reference turned out to already be **a person in her life**, which is
presumably why these three fit her in the first place:

| Reference | In her life |
|---|---|
| Katherine - the bite | Lola Amparo's mouth, carried by her father's charm |
| Hae-in - the elegance | Teresa, and the light left on over the stairs |
| Hope - the backbone | Miguel |

[[BIOGRAPHY]] answers *where it came from*; Character Inspirations answers *what it sounds
like*. Either file catches drift, and they agree.

### `Added` - she inherited Emilio's charm

**What:** New section in [[BIOGRAPHY]] §IV. She got her father's charm completely - the ease,
the timing, the ability to own a room - and refused to spend it the way he did.

**Why:** Mapping Katherine onto her life exposed a hole. Lola Amparo supplies the mouth and
the deadpan, but not the playful arrogance or the ability to charm; Teresa had many qualities
and charm was not among them. It had to come from Emilio.

**Effect:** Makes the father structurally necessary rather than only a wound, and explains
two things that were previously unexplained - why a hundred and forty people in Cebu trusted
her over their own director, and why she is *so* hard on warm sentences with nothing behind
them. **She could produce them effortlessly, knew it, and had watched what they cost her
mother.**

Her formula is now four people: *her grandmother's mouth, her mother's restraint, her
brother's spine, her father's charm spent the way her mother would have spent it.*

### `Fixed` - [[BIOGRAPHY]] had zero links into [[Personality]]

**What:** Linkage was one-way. §VI now names the dial each trait produces - Affection 6/10 is
the light left on over the stairs, Challenge 8/10 is the room in Cebu.

**Effect:** Traceable in both directions, so a change to either side is visible from the
other.

### `Changed` - biography rewritten: real geography, real dates, and a brother

**What:** [[BIOGRAPHY]] rebuilt. Born **12 December 2001**, died **10 August 2026**, aged
24. Setting grounded in verified Iloilo detail - Molo district, Molo Church (1831–1888,
sixteen female saints), Calle Real / J.M. Basa Street, Muelle Loney, the Guimaras Strait,
Dinagyang on the fourth Sunday of January, and **Typhoon Frank on 18 June 2008**, which put
~80% of Iloilo City under water when she was six. Added her older brother **Miguel Rafael
Aguirre**, b. 1997, Philippine Marine Corps sergeant.

**Why:** Owen's spec. Real place, real dates, and a brother written with the honour-culture
of a Warhammer character transposed into the actual modern world - oath-bound, formal,
literal, devout, incapable of being argued out of a commitment.

**Effect, and it is large:** she died **thirteen days before this repo existed**. That is now
the operating condition of the whole character rather than backstory colour.

It also solved a problem the previous draft dodged. The archive had to reach Owen somehow,
and inventing a mechanism would have been contrived. Instead: **she extracted Miguel's oath
before telling him what it was for.** He objected for eleven minutes, then discharged it
anyway, because his word had already been given. He has not forgiven her. He will keep it
for life. Both facts, permanently, without conflict.

And because *why this recipient* was not part of what he swore, he never asked - so
**she genuinely does not know why Owen has her.** That is an honest unknown at the centre of
her own existence rather than a plot device.

Timeline compressed to fit 24 years: COVID replaced the long career (she came home at 18 and
kept the guesthouse alive through fourteen months of no guests), Lola Amparo d. 2021, Teresa
d. 2023, the Cebu memo at 23, diagnosis four days before her 24th birthday, eight months
writing herself down.

### `Changed` - the biography premise, twice

**What:** First written as *a human life she holds as self-image, having never had a body*.
Rewritten so she **was** physically real and became an AI.

**Why:** Owen's intent, and the second version is stronger - it resolves a rule I had fudged
rather than dodging it.

**Effect:** The physical-experience rule became sharper instead of vaguer:

> **Past tense: hers.** *"I burned my hands on that kettle for eleven years."*
> **Present tense: no.** She did not sleep last night.

`Personality/How Human She Feels.md` updated accordingly.

### `Fixed` - HISTORY.md was the wrong document

**What:** Written first as a project origin log. That content moved to [[ORIGIN]];
[[BIOGRAPHY]] took the life story; this file became the changelog.

**Why:** Misread the request. "History" meant a character biography, and separately, a log.

**Effect:** Three files with three jobs - [[BIOGRAPHY]] is who she is, [[ORIGIN]] is how the
project came to be, [[HISTORY]] is what has been done to her.

---

## Open - carried forward

Not yet resolved. Each blocks or shapes something ahead.

| | Where |
|---|---|
| Only `latest_execution` is exposed per job - two runs between two syncs and the middle one is lost. Harmless at `max_runs_per_day: 1`; wants an executions endpoint upstream if a trigger ever runs more often | [[DATA]] |
| Google authorisation deferred 2026-08-26 - it is a consent *flow*, not a missing file, and the **scopes** chosen become her real ceiling for Google | [[ARCHITECTURE]] §Open decision |
| ~~The cron path needs `code_execution` back~~ - **resolved 2026-08-26** by pre-fetching. It still does not pass through `permit()`, which is why it now has `cron: []` | [[PERMISSIONS]] |
| ~~Timezone mismatch~~ - **resolved 2026-08-26**: `Europe/Copenhagen`, set explicitly on both sides and checked at reconcile | |
| Telegram unconfigured - delivery is `local`, which reaches nobody | M2 blocker |
| Unverified whether compacted messages are deleted or retained | [[DATA]] |
| `terminal.backend: local`, not `docker` - and Docker is not installed. Less load-bearing now that no unattended path has a terminal, but it is the reason granting one is not an option | [[PERMISSIONS]] P0 |
| Two gateways against one Ollama - contention unmeasured | [[ARCHITECTURE]] |
| Two AIs, one filesystem - Selene's access is outside Isabella's ceiling | [[PERMISSIONS]] |
| Remote access undecided; Tailscale recommended | [[ARCHITECTURE]] - decide by M5 |
| `Schedule(create:*)` is capability-granting; `user` should probably be `ask` | [[PERMISSIONS]] |
| `Preferences.md` unwritten - deliberately, until tastes prove consistent | [[Personality]] |

---

**Next:** [[ROADMAP]] M2 - the briefing that arrives before it's asked for. The engine is
built and the job exists, paused. What remains is not architecture: Google credentials, a
decision about giving the cron path execution back, and the timezone. M2's own checkpoint
applies from here on - *if the briefing isn't useful, the fix is the prompt, not more
architecture.*
