import { useEffect, useState } from "react";
import { Brain3D } from "../components/Brain3D";
import { EMPTY, type MindSnapshot } from "../lib/mind";
import { api, type Health } from "../api";
import { SESSION_ID, type Chat } from "../useChat";

/**
 * Home. Selene calls this screen the HUD and it is the same screen: a core in
 * the middle of an instrument frame, with the thing you type into underneath it.
 *
 * **What the core is, and why it is not a memory graph.** Selene's brain is her
 * memories. Isabella has no memory table and must not have one - recall is
 * Hermes' - so this brain is built out of what is actually on disk in
 * HERMES_HOME: the curated memory store, her sessions, and the messages in
 * them. See core/mind.py. Nothing in it is invented, which is why a memory
 * with no recorded importance says "unrated" instead of taking a default.
 *
 * The layout is two layers and they are separate on purpose:
 *
 *   · the VOLUME is WebGL. The nodes turn, so they live in a space that turns.
 *   · the FRAME is SVG on top, and it does not turn. Drawing a dashed circle in
 *     three dimensions to get a 2D dashed circle would be work in exchange for
 *     nothing. It ignores the pointer so the brain can be dragged through it.
 *
 * **Chat is on this page, and there is no box on it.** You talk to her through
 * the palette: `K`, type, Enter. Text that matches a command runs it, text that
 * matches nothing is said to her. There WAS an input here, and it was the wrong
 * shape - two boxes on one screen means a new pair of eyes has to work out the
 * difference between them before typing anything, and the honest answer is that
 * there is no difference worth learning.
 *
 * What stays here is her latest reply and what it cost. The full transcript is
 * in `chat`, and Selene's reasoning for that split holds: printing the whole
 * conversation over the top of the graph is the same thing in two places, and
 * the copy under the core is the copy nobody scrolls. A failure is not
 * transcript, so an error stays on screen.
 */

/** Ticks as structure, and structure is grey — the same rule Rings.tsx states
 *  at length for the health dial.
 *
 *  Two rules from the design system decide everything about this frame:
 *  every arc that means something is a REAL QUANTITY, and violet marks what is
 *  LIVE and nothing else. So the rings and ticks here are grey — they are the
 *  instrument, not a reading — and the only violet in the frame is the sweep
 *  and the think-rings, both of which are motion that is genuinely happening. */
function Ticks({ r1, r2, n, every, stroke }: { r1: number; r2: number; n: number; every: number; stroke: string }) {
  const lines = [];
  for (let i = 0; i < n; i++) {
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    const big = i % every === 0;
    const r = big ? r2 : (r1 + r2) / 2;
    lines.push(
      <line
        key={i}
        stroke={stroke}
        opacity={big ? 0.95 : 0.42}
        x1={250 + Math.cos(a) * r1}
        y1={250 + Math.sin(a) * r1}
        x2={250 + Math.cos(a) * r}
        y2={250 + Math.sin(a) * r}
      />,
    );
  }
  return <g>{lines}</g>;
}

function Frame({ phase }: { phase: "idle" | "thinking" }) {
  return (
    <svg
      viewBox="-100 -50 700 600"
      fill="none"
      strokeLinecap="round"
      className="core__frame"
      aria-hidden="true"
    >
      <circle cx="250" cy="250" r="228" stroke="var(--edge)" />
      <circle cx="250" cy="250" r="196" stroke="var(--field)" />
      <circle cx="250" cy="250" r="140" stroke="var(--edge)" />
      <circle cx="250" cy="250" r="108" stroke="var(--field)" />
      <Ticks r1={228} r2={240} n={72} every={6} stroke="#4A4A55" />
      <Ticks r1={140} r2={130} n={48} every={4} stroke="#3A3A44" />

      <g className="core__spin" stroke="var(--muted)" strokeWidth="1.25" opacity=".5">
        <circle cx="250" cy="250" r="214" strokeDasharray="64 26 12 26" />
      </g>
      <g className="core__spin-rev" stroke="var(--muted)" strokeWidth="1" opacity=".35">
        <circle cx="250" cy="250" r="170" strokeDasharray="34 18" />
      </g>
      <g className="core__sweep">
        <path d="M250,88 A162,162 0 0 1 383,158" stroke="var(--mark)" strokeWidth="1.75" opacity=".9" />
      </g>
      <circle cx="250" cy="250" r="162" stroke="var(--mark)" opacity=".2" />

      {/* Thinking: rings falling inward, staggered so one is always
          mid-flight. Nothing here is bound to progress - she does not know
          how long she will take, and a bar that pretends otherwise is the
          lie this whole screen is built to avoid. */}
      {phase === "thinking" && (
        <g stroke="var(--mark)" fill="none">
          {[0, 0.63, 1.26].map((d) => (
            <circle
              key={d}
              className="core__think"
              cx="250"
              cy="250"
              r="214"
              strokeWidth="1.1"
              strokeDasharray="46 20"
              style={{ animationDelay: `${d}s` }}
            />
          ))}
        </g>
      )}
    </svg>
  );
}

function Elapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const tick = setInterval(() => setSeconds((n) => n + 1), 1000);
    return () => clearInterval(tick);
  }, []);
  return (
    <span className="core__wait">
      THINKING · {seconds}S{seconds > 30 && " · IDENTITY QUESTIONS REACH 90S"}
    </span>
  );
}

export function Home({ chat, tick }: { chat: Chat; tick: number }) {
  const [snap, setSnap] = useState<MindSnapshot>(EMPTY);
  const [failed, setFailed] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  /* Refetched when a turn settles, not on a timer. The graph changes when
     something is said, and polling a database every few seconds to learn that
     nothing happened is a cost with no reader. */
  useEffect(() => {
    let live = true;
    api
      .mind(SESSION_ID)
      .then((data) => live && (setSnap(data), setFailed(null)))
      .catch((cause) => live && setFailed((cause as Error).message));
    api.health().then((h) => live && setHealth(h)).catch(() => {});
    return () => {
      live = false;
    };
  }, [tick, chat.waiting]);

  const phase = chat.waiting ? "thinking" : "idle";
  const drawn = Math.min(snap.total, snap.max_nodes);
  const undrawn = snap.total - drawn;

  return (
    <div className="core">
      <div className="core__readout core__readout--left">
        ISABELLA // <b>{chat.waiting ? "THINKING" : health?.ok === false ? "DEGRADED" : "IDLE"}</b>
        <br />
        {health?.model ?? "…"}
        <br />
        {chat.said.length} TURN{chat.said.length === 1 ? "" : "S"} THIS SESSION
      </div>

      <div className="core__readout core__readout--right">
        MIND <b>{snap.total}</b> NODES
        {/* Say what is being withheld. A graph quietly drawing a subset while
            the count beside it claims the whole corpus is a small lie. */}
        {undrawn > 0 && (
          <>
            {" · "}
            <b>{undrawn} UNDRAWN</b>
          </>
        )}
        <br />
        {snap.counts.memory} MEMORY · {snap.counts.session} SESSION · {snap.counts.message} MESSAGE
        <br />
        IN CONTEXT <b>{snap.budget}</b> · SCAN {snap.scan_ms} MS
      </div>

      <div className={`core__stage ${phase === "thinking" ? "core__stage--thinking" : ""}`}>
        {phase === "thinking" && <div className="core__glow" />}
        <Brain3D snap={snap} phase={phase} />
        <Frame phase={phase} />
      </div>

      <div className="core__legend">
        <span>
          <i className="dot dot--mark" />
          IN CONTEXT
        </span>
        <span>
          <i className="dot dot--memory" />
          MEMORY
        </span>
        <span>
          <i className="dot dot--session" />
          SESSION
        </span>
        <span>
          <i className="dot dot--message" />
          MESSAGE
        </span>
        <span>
          <i className="dot dot--hollow" />
          UNRATED
        </span>
      </div>

      <div className="core__under">
        {/* Her memory store being switched off is a fact about the machine,
            and the graph is thinner because of it. Say so here rather than
            let an absent third of the volume pass unremarked. */}
        {snap.counts.memory === 0 && !snap.memory_enabled && (
          <p className="core__note">{snap.detail}</p>
        )}
        {failed && <p className="notice notice--bad">{failed}</p>}
        {chat.error && <p className="notice notice--bad">{chat.error}</p>}

        {chat.waiting && <Elapsed />}
        {!chat.waiting && chat.last && (
          <p className="core__said">{chat.last.text}</p>
        )}

        {/* Nothing has been said yet, so say where the words go. The palette is
            the only input on this screen and an empty screen that does not name
            it is an empty screen nobody types into. */}
        {!chat.waiting && !chat.last && !chat.error && (
          <span className="core__hint">PRESS K AND SAY SOMETHING</span>
        )}

        {chat.last && (
          <div className="core__stats">
            <span>
              REPLY <b>{chat.last.seconds?.toFixed(1) ?? "—"} S</b>
            </span>
            <span>
              WROTE <b>{chat.last.tokens ?? "—"} TOK</b>
            </span>
            <span>
              FULL TRANSCRIPT <b>CHAT</b>
            </span>
            <span>
              ASK AGAIN <b>K</b>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
