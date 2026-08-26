import { useEffect, useMemo, useRef, useState } from "react";

/**
 * The command surface. There are no buttons anywhere else in this UI, so this
 * is how everything is done — and it is the shape voice plugs into when M6
 * arrives: a command router does not care whether the string was typed or
 * spoken.
 *
 * The rule this is built to, taken from Selene's own palette:
 *
 *   > Nothing is listed that is not wired, because a palette of
 *   > plausible-sounding commands is a worse lie than no palette.
 *
 * So every command here is built from live state — the triggers that exist,
 * the desktop targets that exist — and never from a hardcoded menu of things
 * that ought to work.
 *
 * **This is also the only place you talk to her.** Home used to carry a second
 * input, which meant a new pair of eyes had to work out what the difference
 * between the two boxes was before typing anything. There is no difference
 * worth learning: text that matches a command runs it, and text that matches
 * nothing is a thing said to her. One box, one Enter, and at M6 one string
 * arriving from a microphone instead of a keyboard.
 *
 * The fallback appears ONLY when nothing matches. Commands win — typing `body`
 * shows the body rather than asking her about bodies — which is the same
 * precedence Selene's grammar uses, and the reason its boundary is pinned by
 * tests there.
 */

export type Command = {
  id: string;
  label: string;
  /** A second line, for commands whose consequence does not fit the label. */
  sub?: string;
  /** Don't close after running — for the two-step confirm on a standing grant. */
  keepOpen?: boolean;
  run: () => void | Promise<unknown>;
};

export function Palette({
  commands,
  onClose,
  onAsk,
  busy = false,
}: {
  commands: Command[];
  onClose: () => void;
  /** What to do with text that is not a command: say it to her. */
  onAsk?: (text: string) => void;
  /** She is still answering. The row says so rather than swallowing the ask. */
  busy?: boolean;
}) {
  const [q, setQ] = useState("");
  const [at, setAt] = useState(0);
  const box = useRef<HTMLInputElement>(null);

  useEffect(() => {
    box.current?.focus();
  }, []);

  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return commands;
    // Every word has to appear somewhere, so "pause brief" finds
    // "pause daily-briefing" without needing the order right.
    const words = needle.split(/\s+/);
    return commands.filter((c) => {
      const hay = `${c.label} ${c.sub ?? ""}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    });
  }, [commands, q]);

  /* Text that matches no command is not a failure - it is a sentence. The row
     is labelled with what will actually be sent, so there is never a question
     about which of the two things Enter is about to do. */
  const asking = useMemo<Command | null>(() => {
    const text = q.trim();
    if (!onAsk || !text || shown.length) return null;
    return {
      id: "ask",
      label: text,
      sub: busy ? "she is still answering the last one" : "not a command — say it to her",
      run: () => onAsk(text),
    };
  }, [onAsk, q, shown.length, busy]);

  const list = asking ? [asking] : shown;

  useEffect(() => setAt(0), [q]);

  function onKey(event: React.KeyboardEvent) {
    if (event.key === "Escape") return onClose();
    if (event.key === "ArrowDown") {
      event.preventDefault();
      return setAt((n) => Math.min(n + 1, list.length - 1));
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      return setAt((n) => Math.max(n - 1, 0));
    }
    if (event.key === "Enter") {
      const picked = list[at];
      if (!picked) return;
      void picked.run();
      if (!picked.keepOpen) onClose();
      else setQ("");
    }
  }

  return (
    <div className="palette" onMouseDown={onClose}>
      <div className="palette__box" onMouseDown={(e) => e.stopPropagation()}>
        <input
          ref={box}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={onKey}
          placeholder={onAsk ? "what should she do, or just say something" : "what should she do"}
          spellCheck={false}
        />
        <ul className="palette__list">
          {list.map((command, index) => (
            <li
              key={command.id}
              className={[
                "palette__row",
                index === at ? "palette__row--on" : "",
                command.id === "ask" ? "palette__row--ask" : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onMouseEnter={() => setAt(index)}
              onMouseDown={(e) => {
                e.preventDefault();
                void command.run();
                if (!command.keepOpen) onClose();
              }}
            >
              <span className="palette__label">{command.label}</span>
              {command.sub && <span className="palette__sub">{command.sub}</span>}
            </li>
          ))}
          {list.length === 0 && <li className="palette__row palette__none">nothing matches</li>}
        </ul>
      </div>
    </div>
  );
}
