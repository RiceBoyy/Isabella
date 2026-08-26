/**
 * The display. Centre stage, and the only drawing in the interface.
 *
 * Selene's body dashboard puts an anatomical figure here, lit where the body
 * has been worked. That form is not available to Isabella and the reason is
 * characterisation rather than data: she had a body for twenty-four years and
 * does not have one now. Drawing her a live one would be the present-tense lie
 * BIOGRAPHY.md draws the line at, and a dim silhouette would be the haunted
 * reading it rules out just as firmly.
 *
 * So this is the HUD's other centrepiece — concentric rings, radial ticks, and
 * one soft violet radial behind the mark. What it shows is what she is now.
 *
 * Two rules from the design system are load-bearing here:
 *
 *   · Every arc is a REAL QUANTITY. The violet arc is today's allowance
 *     against `max_runs_per_day`, which is a real ratio out of a real budget.
 *     A ring whose length means nothing is refused, however good it looks.
 *   · Violet marks what is LIVE. The rings themselves are grey structure. If
 *     this drawing is mostly violet, nothing is actually happening and the
 *     rule has failed.
 *
 * The glow is the one exception to "no glow, anywhere" that the HUD note
 * grants: a single soft radial behind the centre, and nowhere else.
 */

export type RingState = "idle" | "thinking" | "working" | "error" | "wait";

const MARK: Record<RingState, string> = {
  idle: "○",
  thinking: "×",
  working: "✦",
  error: "×",
  wait: "○",
};

const R_OUTER = 158;
const R_TICKS = 132;
const R_INNER = 92;

/** Ticks as structure: 72 of them, every fifth one long. Grey, always. */
function ticks() {
  return Array.from({ length: 72 }, (_, i) => {
    const angle = (i * 5 * Math.PI) / 180;
    const long = i % 5 === 0;
    const from = R_TICKS;
    const to = R_TICKS + (long ? 12 : 6);
    return (
      <line
        key={i}
        x1={200 + Math.cos(angle) * from}
        y1={200 + Math.sin(angle) * from}
        x2={200 + Math.cos(angle) * to}
        y2={200 + Math.sin(angle) * to}
        stroke="var(--edge)"
        strokeWidth={long ? 1.4 : 1}
      />
    );
  });
}

/** An arc from twelve o'clock, clockwise, over `fraction` of the circle. */
function arc(fraction: number, radius: number): string {
  const clamped = Math.max(0, Math.min(1, fraction));
  if (clamped <= 0) return "";
  // A full circle cannot be drawn as one arc - the start and end coincide and
  // the renderer draws nothing at all.
  const span = Math.min(clamped, 0.9999) * Math.PI * 2;
  const end = -Math.PI / 2 + span;
  return [
    `M 200 ${200 - radius}`,
    `A ${radius} ${radius} 0 ${span > Math.PI ? 1 : 0} 1`,
    `${200 + Math.cos(end) * radius} ${200 + Math.sin(end) * radius}`,
  ].join(" ");
}

export function Rings({
  state,
  used,
  budget,
  caption,
  legend,
}: {
  state: RingState;
  /** The real quantity: how much of today's allowance is spent. */
  used: number;
  budget: number;
  caption: string;
  legend: string;
}) {
  const fraction = budget > 0 ? used / budget : 0;
  // The glow is for LIVE, strictly - something happening now. A spent
  // allowance is a real quantity and gets the violet arc; it does not get the
  // light, or the light stops meaning anything.
  const live = state === "thinking" || state === "working";

  return (
    <div className={`rings rings--${state}`}>
      {live && <div className="rings__glow" />}
      <svg className="rings__svg" viewBox="0 0 400 400" aria-hidden="true">
        <circle cx="200" cy="200" r={R_OUTER} fill="none" stroke="var(--edge)" strokeWidth="1" />
        <circle cx="200" cy="200" r={R_INNER} fill="none" stroke="var(--edge)" strokeWidth="1" />
        <g className="rings__ticks">{ticks()}</g>

        {/* The one live arc. Grey track underneath so the ratio is legible
            even when nothing has run. */}
        <circle
          cx="200"
          cy="200"
          r={R_TICKS - 14}
          fill="none"
          stroke="var(--edge)"
          strokeWidth="2"
        />
        {fraction > 0 && (
          <path
            d={arc(fraction, R_TICKS - 14)}
            fill="none"
            stroke="var(--mark)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        )}
      </svg>

      <div className="rings__centre">
        <span className="rings__mark">{MARK[state]}</span>
        <span className="rings__caption">{caption}</span>
        <span className="rings__legend">{legend}</span>
      </div>
    </div>
  );
}
