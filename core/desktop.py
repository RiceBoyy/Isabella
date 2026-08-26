"""Opening a terminal on Owen's machine, for the small number of things worth
watching live.

**This executes, so read the shape before extending it.** Isabella's floor
removes `terminal` and `code_execution` from every Hermes platform by explicit
decision - *capability removed, not sandboxed* - and Docker is not installed, so
`TERMINAL_ENV=docker` is not an available fallback. Nothing here changes that:
this path never reaches Hermes, and Hermes never reaches this.

What makes it narrow enough to exist:

- **The commands are constants.** A caller picks a target by name from `TARGETS`
  and gets the command that was written here and reviewed here. Nothing composes
  a command from a request, a prompt, or a model's output. An unknown name is a
  404, never a passthrough. The one thing interpolated besides `HERMES_HOME` is
  the path to `core/logcolour.awk`, which is derived from this file's own
  location - still a constant, still git-versioned, still reviewed here.
- **Every target is read-only** - `tail`, `cat`. Nothing in this file writes,
  deletes, or sends. The one exception is `close_target`, which kills the
  pipeline it started; see the note on it, and PERMISSIONS §desktop.
- **The model cannot call it.** It is an endpoint on Isabella's API that Owen
  drives from the palette. Selene's `tools.ts` draws this same line and gives
  the reason: *"wiring a write to a regex with no confirmation step would be the
  Awareness-and-Sensing argument made backwards."*

When `permit()` lands (PERMISSIONS.md P1) this becomes a `Desktop(open:*)`
decision with a real subject. Until then the gate is that the command is a
constant, which is the strongest gate available before the policy engine exists.

**macOS only, and it says so rather than failing.** ROADMAP M5 wants no
macOS-only assumptions in core; this is one, in the same way the iMessage bridge
is, so it degrades to an explicit "not available on this host" instead of an
exception.
"""

import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from core.config import Settings

# The colouriser the log targets pipe through. A file rather than an inline awk
# program because the command ends up inside an AppleScript string, and an awk
# program full of quotes and backslashes through that escaping is a bug waiting
# to happen. See core/logcolour.awk for what it paints and why only that much.
COLOUR = Path(__file__).resolve().parent / "logcolour.awk"


class DesktopError(RuntimeError):
    """A failure worth showing verbatim."""


@dataclass(frozen=True, slots=True)
class Target:
    name: str
    summary: str
    # A format string over exactly one name - `home`. Written here, reviewed
    # here, and never assembled from anything a caller sends.
    template: str

    # What the target watches, so the palette can say "nothing there yet"
    # rather than opening a window onto an empty file.
    file: str = ""

    def command(self, cfg: Settings) -> str:
        # `{colour}` is substituted AFTER the braces in this template are
        # consumed, so the awk program's own braces are never seen by format().
        return self.template.format(home=cfg.hermes_home, colour=COLOUR)

    def path(self, cfg: Settings) -> Path | None:
        return cfg.hermes_home / self.file if self.file else None


TARGETS: dict[str, Target] = {
    # The three log targets pipe through the same colouriser: red is an error,
    # yellow a warning, everything else dim. Three steps and no more, because
    # the question being asked of a scrolling log is "is anything wrong", and a
    # rainbow answers it worse than three colours do. This is the ONLY place
    # logs are read - there is no log view in the web UI, by decision.
    "logs": Target(
        name="logs",
        summary="Her agent log, live and colourised - every request, model call and failure",
        template="tail -n 200 -f '{home}/logs/agent.log' | awk -f '{colour}'",
        file="logs/agent.log",
    ),
    "errors": Target(
        name="errors",
        summary="Only what went wrong, live and colourised",
        template="tail -n 100 -f '{home}/logs/errors.log' | awk -f '{colour}'",
        file="logs/errors.log",
    ),
    "gateway": Target(
        name="gateway",
        summary="Her gateway's own log - startup, shutdown, what port it took",
        template="tail -n 100 -f '{home}/logs/gateway.log' | awk -f '{colour}'",
        file="logs/gateway.log",
    ),
    "briefing": Target(
        name="briefing",
        summary="The most recent briefing as Hermes wrote it, prompt and all",
        # The whole file, not the parsed Response - this is the raw record,
        # which is the point of looking at it in a terminal rather than in her UI.
        template=(
            "cat \"$(ls -t '{home}'/cron/output/*/*.md | head -1)\"; "
            "echo; echo '-- enter to close --'; read"
        ),
        file="cron/output",
    ),
}


def available() -> tuple[bool, str]:
    if sys.platform != "darwin":
        return False, f"Opening a terminal is macOS-only; this host is {sys.platform}."
    return True, "ok"


def targets(cfg: Settings) -> list[dict]:
    """What can be opened, whether there is anything there yet, and whether it
    is already on screen.

    `open` is what lets the palette offer `close logs` only when there is a
    logs window to close - nothing is listed that is not wired.
    """
    ok, detail = available()
    on_screen = set(windows()) | {w.name for w in husks()} if ok else set()
    return [
        {
            "name": target.name,
            "summary": target.summary,
            "exists": bool(target.path(cfg) and target.path(cfg).exists()),
            "available": ok,
            "detail": detail if not ok else "",
            # A husk counts: it is a window on screen with her name on it, and
            # `close logs` is what gets rid of it.
            "open": target.name in on_screen,
        }
        for target in TARGETS.values()
    ]


def _quote(text: str) -> str:
    """Escape a string for an AppleScript literal.

    The commands are constants, so this is belt-and-braces rather than
    load-bearing - but the day someone adds a target with a quote in a path is
    the day it stops being decorative.
    """
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _first_open(target: "Target", command: str) -> str:
    """A new window, stamped with her title so it can be found again."""
    return (
        'tell application "Terminal"\n'
        f'  set t to do script "{_quote(command)}"\n'
        f'  set custom title of t to "{_quote(TITLE + target.name)}"\n'
        "  activate\n"
        "end tell"
    )


def _close(window: "Window") -> str:
    """Close a window. Only works once nothing is running in it - see the note
    at the top of the closing section."""
    return f'tell application "Terminal" to close window id {window.window_id}'


def _reopen(window: "Window", command: str) -> str:
    """The window she already has: show it, and restart the command if it died.

    A busy tab is left alone - re-running `tail -f` into a tab already tailing
    would type the command into the running process rather than start a second
    one, which is not what anyone means by `open logs`.
    """
    return (
        'tell application "Terminal"\n'
        f"  set w to window id {window.window_id}\n"
        + ("" if window.busy else f'  do script "{_quote(command)}" in tab 1 of w\n')
        + "  set frontmost of w to true\n"
        "  activate\n"
        "end tell"
    )


def open_target(cfg: Settings, name: str) -> dict:
    """Open Terminal.app on one named target. Returns what was run."""
    ok, detail = available()
    if not ok:
        raise DesktopError(detail)

    target = TARGETS.get(name)
    if target is None:
        # Named, never composed. This is the whole security argument in one line.
        raise DesktopError(f"No such target: {name}")

    command = target.command(cfg)

    # One window per target. If she already has a `logs` window up, bring that
    # one to the front and restart the command in it if it has stopped, rather
    # than opening a second window onto the same file. Same rule the browser
    # views follow.
    existing = windows().get(name)
    reused = existing is not None
    if existing:
        _osascript(_reopen(existing, command))
    else:
        # Any husk for this target is closed first. Its shell has exited, so
        # Terminal will not take a new command in it, and leaving it on screen
        # beside the real one is the confusing outcome. Not busy, so it goes.
        for husk in husks():
            if husk.name == name:
                _osascript(_close(husk))
        _osascript(_first_open(target, command))

    return {"opened": target.name, "command": command, "reused": reused}


# ----------------------------------------------------------------------
# Closing what was opened.
#
# **Terminal refuses to close a BUSY window, silently.** `close window id N`
# returns success and nothing happens while a job is running in it - there is no
# error to catch, because what Terminal wants to do is put up its "terminate
# running processes?" sheet, and it cannot do that to a script. An idle window
# closes immediately.
#
# So closing is three steps, in this order:
#
#   1. **kill what is running in it.** This is the only thing in this file that
#      is not read-only, and it is bounded three ways: the process must be on
#      the tty of a window Isabella titled herself, it must not be a shell, and
#      its command must be one of the handful this file ever runs. Anything else
#      sharing that terminal is left alone.
#   2. **wait for it to actually stop.** `busy` goes false a moment after the
#      signal lands, and asking to close before then is the failure above.
#   3. **close the window.**
#
# A window whose shell has exited - a husk, showing "[Process completed]" - is
# not busy and closes straight away.
#
# Do not diagnose step 1 by watching `id of every window`: that list keeps
# returning ids for windows that are already gone, which is exactly the trap
# that produced a day of code built around "Terminal ignores close". Enumerate
# the windows that still have tabs, which is what `_LIST` does.
# ----------------------------------------------------------------------

# Stamped on every tab Isabella opens. It is how a window of hers is told from
# one of Owen's, and nothing is ever killed or hidden without it.
TITLE = "Isabella · "

# What may be killed. Every one of these is a command this file runs itself.
# A process on her tty that is not on this list is something Owen started in a
# window of hers, and it is not hers to end.
KILLABLE = frozenset({"tail", "awk", "cat", "head", "ls"})

# `/dev/ttys003` and nothing else. This string reaches a subprocess, so it is
# checked rather than trusted - AppleScript is not a trusted input just because
# it is local.
_TTY = re.compile(r"^/dev/ttys\d+$")

_LIST = f'''
-- `tab` inside a `tell application "Terminal"` block is Terminal's TAB ELEMENT,
-- not the character. Bound out here, where it still means the character, or
-- every field separator comes back as the literal word "tab".
set sep to tab
if application "Terminal" is running then
	tell application "Terminal"
		set out to ""
		repeat with w in windows
			try
				repeat with t in tabs of w
					try
						set ct to custom title of t
						if ct starts with "{TITLE}" then
							set out to out & (id of w as text) & sep & ct & sep & (busy of t as text) & sep & (tty of t) & sep & (count of processes of t as text) & linefeed
						end if
					end try
				end repeat
			end try
		end repeat
		return out
	end tell
end if
return ""
'''


def _osascript(script: str) -> str:
    """Run one AppleScript. Never raises for a Terminal that is not running."""
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        raise DesktopError(f"Could not talk to Terminal: {exc}") from exc
    if proc.returncode != 0:
        raise DesktopError(proc.stderr.strip() or "Terminal refused.")
    return proc.stdout


@dataclass(frozen=True, slots=True)
class Window:
    name: str
    window_id: int
    busy: bool
    tty: str
    # Whether the shell in it is still alive. A tab whose shell has exited shows
    # "[Process completed]" and cannot be given a new command - Terminal will
    # not restart a dead tab - so a window like that is not reusable, however
    # much it still looks like one.
    live: bool


def windows() -> dict[str, Window]:
    """Which of her terminals are open right now, keyed by target name.

    Reads Terminal without launching it - `application "Terminal" is running`
    is the idiom that does not, and `tell application "Terminal"` on its own
    would open it, which would be an interface opening a terminal to find out
    whether it had opened a terminal.

    **Live windows only, one per target.** A husk - a window whose shell has
    exited, showing "[Process completed]" - cannot be given a new command, so it
    is not something `open logs` can reuse. It is still a window on screen with
    her name on it, so `close logs` should still reach it; those come back from
    `husks()`.
    """
    if not available()[0]:
        return {}
    try:
        out = _osascript(_LIST)
    except DesktopError:
        return {}

    seen: dict[str, Window] = {}
    for line in out.splitlines():
        window = _parse(line)
        if window is None:
            continue
        if not window.live:
            continue
        # Newer beats older. Terminal hands them back in no order worth relying
        # on, and a second live window for one target should not be a coin flip.
        best = seen.get(window.name)
        if best is None or window.window_id > best.window_id:
            seen[window.name] = window
    return seen


def husks() -> list[Window]:
    """Her windows whose shell has exited - hidden, unusable, still listed.

    Kept out of `windows()` so nothing offers to reopen one, and swept by
    `close_target` so the Window menu does not fill up with them.
    """
    if not available()[0]:
        return []
    try:
        out = _osascript(_LIST)
    except DesktopError:
        return []

    dead: list[Window] = []
    for line in out.splitlines():
        window = _parse(line)
        if window is not None and not window.live:
            dead.append(window)
    return dead


def _parse(line: str) -> Window | None:
    """One line of the listing, or None if it is not one of hers."""
    parts = line.split("\t")
    if len(parts) != 5:
        return None
    window_id, title, busy, tty, procs = parts
    name = title.removeprefix(TITLE).strip()
    # The title has to name a target she actually has. A stray
    # `Isabella · something` window is not one, and must not become one just by
    # being labelled - the name still selects from the constant table.
    if name not in TARGETS or not window_id.isdigit():
        return None
    return Window(
        name=name,
        window_id=int(window_id),
        busy=busy.strip() == "true",
        tty=tty.strip(),
        live=procs.strip().isdigit() and int(procs.strip()) > 0,
    )


def _kill(tty: str) -> int:
    """End the pipeline in one of her terminals. Returns how many it ended.

    **This is the only thing in this module that is not read-only.** Three
    bounds, all of them necessary rather than belt-and-braces:

    - the tty comes from a window carrying her title, so it is one she opened;
    - the shell is never touched, only the job running in it;
    - the command must be one this file itself runs. A process on her tty that
      is not on that list is something Owen started in a window of hers, and it
      is not hers to end.
    """
    if not _TTY.match(tty):
        return 0
    try:
        listing = subprocess.run(
            ["ps", "-t", tty.removeprefix("/dev/"), "-o", "pid=,comm="],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout
    except (subprocess.TimeoutExpired, OSError):
        return 0

    ended = 0
    for line in listing.splitlines():
        pid, _, comm = line.strip().partition(" ")
        command = comm.strip().rsplit("/", 1)[-1]
        if not pid.isdigit() or command not in KILLABLE:
            continue
        try:
            subprocess.run(["kill", pid], capture_output=True, timeout=5, check=False)
            ended += 1
        except (subprocess.TimeoutExpired, OSError):
            pass
    return ended


def close_target(cfg: Settings, name: str | None = None) -> dict:
    """Stop what is running in her terminals and take them off the screen.

    `name` closes one; omitted, closes all of hers. Owen's own windows are never
    matched, because they do not carry her title.
    """
    ok, detail = available()
    if not ok:
        raise DesktopError(detail)
    if name is not None and name not in TARGETS:
        raise DesktopError(f"No such target: {name}")

    wanted = [
        w
        for key, w in windows().items()
        if name is None or key == name
    ]
    # Husks are windows too. Not busy, so they close on the first ask.
    wanted += [w for w in husks() if name is None or w.name == name]

    if not wanted:
        return {"closed": [], "ended": 0, "stubborn": [], "detail": "Nothing of hers is open."}

    closed: list[str] = []
    stubborn: list[str] = []
    ended = 0
    for window in wanted:
        ended += _kill(window.tty)
        # Terminal will not close a busy window and will not say so - see the
        # note above. Wait for the job to actually stop before asking.
        if not _settled(window):
            stubborn.append(window.name)
            continue
        _osascript(_close(window))
        closed.append(window.name)

    return {
        "closed": closed,
        "ended": ended,
        "stubborn": stubborn,
        "detail": (
            ""
            if not stubborn
            else (
                f"Still running in {', '.join(stubborn)} - something is in that window that "
                "is not hers to kill, so it was left open. Close it yourself with shift-cmd-W."
            )
        ),
    }


def _settled(window: Window, tries: int = 12, wait: float = 0.2) -> bool:
    """Wait for a window to stop being busy, up to about two seconds.

    Returns False if something is still running - which means something is in
    there that `_kill` would not touch, because it is not one of hers. That
    window is left alone and reported, rather than having its contents fought
    over.
    """
    for _ in range(tries):
        try:
            busy = _osascript(
                f'tell application "Terminal" to return (busy of tab 1 of window id {window.window_id})'
            )
        except DesktopError:
            # No such window, or no tabs in it. Either way there is nothing left
            # to wait for.
            return True
        if busy.strip() != "true":
            return True
        time.sleep(wait)
    return False
