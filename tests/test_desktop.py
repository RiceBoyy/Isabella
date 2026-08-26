"""The one path that executes on the host.

These tests exist to hold a line rather than to check a feature: the command
must come from the constant table and never from the caller. If a future change
makes `open_target` assemble a command out of its argument, the first two tests
here are what should fail.
"""

import subprocess

import pytest

from core import desktop
from core.config import Settings
from core.desktop import DesktopError


def cfg(tmp_path) -> Settings:
    return Settings(hermes_home=tmp_path, _env_file=None)


def fake_osascript(monkeypatch, record, returncode=0, stderr=""):
    def run(argv, **kwargs):
        record.append(argv)
        return subprocess.CompletedProcess(argv, returncode, "", stderr)

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(desktop.sys, "platform", "darwin")


def test_an_unknown_target_is_refused_and_never_run(tmp_path, monkeypatch):
    calls = []
    fake_osascript(monkeypatch, calls)

    with pytest.raises(DesktopError, match="No such target"):
        desktop.open_target(cfg(tmp_path), "rm -rf /")
    assert calls == []


def test_the_caller_cannot_reach_the_command(tmp_path, monkeypatch):
    """The name selects a constant; it is not part of what gets executed."""
    calls = []
    fake_osascript(monkeypatch, calls)

    desktop.open_target(cfg(tmp_path), "logs")

    # Every osascript this ran, not just the first - opening now asks Terminal
    # what is already on screen before it opens anything.
    script = "\n".join(call[-1] for call in calls)
    assert "tail -n 200 -f" in script
    assert str(tmp_path) in script
    # Every target reads. Nothing here writes, deletes or sends.
    assert not any(word in script for word in ("rm ", "mv ", "curl", "> "))


def test_every_shipped_target_is_read_only(tmp_path):
    """Including the colouriser. A pipeline is only as read-only as its
    last stage, and the log targets now have two."""
    for target in desktop.TARGETS.values():
        command = target.command(cfg(tmp_path))
        for stage in command.split("|"):
            assert stage.strip().split()[0] in {"tail", "cat", "awk", "head"}, command


def test_the_log_targets_are_coloured_by_a_file_in_this_repo(tmp_path):
    """The awk program is a constant like every other part of the command -
    git-versioned, next to desktop.py, never assembled from a request."""
    assert desktop.COLOUR.is_file()
    assert desktop.COLOUR.name == "logcolour.awk"

    for name in ("logs", "errors", "gateway"):
        command = desktop.TARGETS[name].command(cfg(tmp_path))
        assert f"awk -f '{desktop.COLOUR}'" in command

    # The briefing is markdown, not a log. Colouring it would be decoration.
    assert "awk" not in desktop.TARGETS["briefing"].command(cfg(tmp_path))


def test_a_non_mac_host_says_so_rather_than_failing(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "linux")

    ok, detail = desktop.available()
    assert ok is False
    assert "macOS-only" in detail
    with pytest.raises(DesktopError, match="macOS-only"):
        desktop.open_target(cfg(tmp_path), "logs")


def test_targets_report_whether_there_is_anything_to_look_at(tmp_path):
    listed = {t["name"]: t for t in desktop.targets(cfg(tmp_path))}
    assert listed["logs"]["exists"] is False

    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "agent.log").write_text("x")
    listed = {t["name"]: t for t in desktop.targets(cfg(tmp_path))}
    assert listed["logs"]["exists"] is True


def test_quotes_in_a_path_cannot_break_out_of_the_applescript(tmp_path):
    script = desktop._first_open(desktop.TARGETS["logs"], 'tail -f "/a/b"')
    assert '\\"' in script
    assert script.count('"') % 2 == 0


# ----------------------------------------------------------------------
# Closing what was opened.
#
# Terminal refuses to close a BUSY window and says nothing about it, so closing
# is kill, wait, close. The thing worth pinning here is that it can only ever
# reach a window Isabella titled herself, and can only ever kill a command she
# runs herself.
# ----------------------------------------------------------------------


def test_only_her_own_windows_are_ever_matched(tmp_path, monkeypatch):
    """Owen has his own Terminal windows open. None of them carry her title,
    and none of them are hers to end."""
    listing = (
        "111\tIsabella \u00b7 logs\ttrue\t/dev/ttys003\t4\n"
        "222\t\u25d1 m3-briefing-ui\ttrue\t/dev/ttys009\t3\n"
        "333\tTerminal\tfalse\t/dev/ttys001\t2\n"
    )
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_osascript", lambda script: listing)

    found = desktop.windows()
    assert list(found) == ["logs"]
    assert found["logs"].window_id == 111


def test_a_title_that_is_not_a_known_target_is_ignored(tmp_path, monkeypatch):
    """A stray `Isabella · something` window is not a target and must not
    become one - the name still has to select from the constant table."""
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(
        desktop, "_osascript", lambda script: "111\tIsabella \u00b7 whatever\ttrue\t/dev/ttys003\t4\n"
    )
    assert desktop.windows() == {}


def test_a_husk_is_not_a_window_to_reopen(tmp_path, monkeypatch):
    """Two windows can carry the same title: one whose shell exited, and the
    real one opened after it. `open logs` must find the live one - a dead tab
    will not take a new command."""
    listing = (
        "999\tIsabella \u00b7 logs\ttrue\t/dev/ttys007\t4\n"
        "111\tIsabella \u00b7 logs\tfalse\t/dev/ttys003\t0\n"
    )
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_osascript", lambda script: listing)

    assert desktop.windows()["logs"].window_id == 999
    assert [w.window_id for w in desktop.husks()] == [111]


def test_a_husk_still_counts_as_something_to_close(tmp_path, monkeypatch):
    """A window whose shell exited cannot take a new command, so `open logs`
    will not reuse it - but it is still a window on screen with her name on it,
    and `close logs` is what gets rid of it."""
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(
        desktop, "_osascript", lambda script: "111\tIsabella \u00b7 logs\tfalse\t/dev/ttys003\t0\n"
    )

    assert desktop.windows() == {}
    assert [w.window_id for w in desktop.husks()] == [111]
    assert {t["name"]: t["open"] for t in desktop.targets(cfg(tmp_path))}["logs"] is True


def test_an_unknown_target_cannot_be_closed_either(tmp_path, monkeypatch):
    monkeypatch.setattr(desktop.sys, "platform", "darwin")
    monkeypatch.setattr(desktop, "_osascript", lambda script: "")

    with pytest.raises(DesktopError, match="No such target"):
        desktop.close_target(cfg(tmp_path), "rm -rf /")


def test_only_her_own_commands_are_ever_killed(tmp_path, monkeypatch):
    """The one thing in this module that is not read-only. A process on her tty
    that she did not start is Owen's, and it is not hers to end."""
    monkeypatch.setattr(
        desktop.subprocess,
        "run",
        lambda argv, **kw: subprocess.CompletedProcess(
            argv, 0, "111 login\n112 -zsh\n113 tail\n114 awk\n115 vim\n", ""
        ),
    )
    killed: list[str] = []
    real = desktop.subprocess.run

    def spy(argv, **kw):
        if argv[0] == "kill":
            killed.append(argv[1])
            return subprocess.CompletedProcess(argv, 0, "", "")
        return real(argv, **kw)

    monkeypatch.setattr(desktop.subprocess, "run", spy)
    desktop._kill("/dev/ttys003")

    # tail and awk, which she runs. Not the shell, not login, and not vim.
    assert killed == ["113", "114"]


def test_a_tty_that_is_not_a_tty_is_refused(tmp_path, monkeypatch):
    """The tty comes back from AppleScript, and AppleScript is not a trusted
    input just because it is local."""
    calls = []
    monkeypatch.setattr(
        desktop.subprocess, "run", lambda argv, **kw: calls.append(argv) or subprocess.CompletedProcess(argv, 0, "", "")
    )
    assert desktop._kill("/dev/ttys003; rm -rf /") == 0
    assert desktop._kill("") == 0
    assert calls == []
