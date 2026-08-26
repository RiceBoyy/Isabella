/* PORTED from Selene (`src/lib/graph.ts`), and ADAPTED — read the adaptation
   before changing anything, because the geometry below still assumes Selene's
   three-tier corpus and only the NAMES were free to change.

   The mapping, and why each one lands where it does:

     Selene            Isabella      because
     ──────            ────────      ───────
     core     ──────▶  memory        the frame everything hangs off, so it
                                     takes the stem and the deep structures
     entity   ──────▶  session       one place each, spread over the cortex,
                                     so the same conversation is found in
                                     roughly the same spot between visits
     atomic   ──────▶  message       sits beside the thing it belongs to,
                                     which here is its session

   TWO REAL CHANGES, both load-bearing:

   1. **Edges resolve by id, not by title.** Selene keyed on title because a
      memory's title IS its key. Sessions here are titled from their first
      message and two of them really are both called "hello", so a title-keyed
      edge would join two unrelated conversations.
   2. **`importance` may be null**, and null is not zero — see lib/mind.ts. The
      radius comes from `size` instead, which the server guarantees is a real
      count for every kind.

   Everything below this line is Selene's, including the reasoning. --------

   Layout for the memory graph — Knowledge Graph.md.

   Positions derive from each node's identity, so the SEED is stable
   between turns. The simulation in sim.ts moves nodes off that seed but
   is anchored back to it, which is the compromise: the space stays
   learnable — the same memory is always found in roughly the same place
   — while the graph is visibly alive rather than a diagram.

   A pure simulation was rejected for the original reason, which still
   holds: reseeding a free layout every turn shuffles the whole space and
   nothing can ever be learned by position.

   The space is the brain volume in brain.ts, in its normalised units —
   not pixels. Nothing here knows how large the thing is drawn; the
   renderer decides that. Anatomy carries meaning rather than decoration:
   core memories are the stem and the deep structures the rest hangs
   off, entities are spread over the cortex, and an atomic memory sits
   on the cortex beside the entity it names. */
import type { MindSnapshot, MindKind } from "./mind";
import { place, type P3 } from "./brain";

export interface Placed {
  id: string; title: string; kind: MindKind;
  /** 0-10 where it is recorded, null where it is not. Never defaulted to 0. */
  importance: number | null;
  confidence: number;
  /** 0-1, always a real count. This, not importance, is what sizes a node. */
  size: number;
  /** the real quantity, printed in the readout */
  measure: string;
  /** the opening of the body, for the hover readout */
  excerpt?: string;
  x: number; y: number; z: number; hop?: 0 | 1 | 2;
}

/* How many nodes are drawn at once.

   Every turn can write an atomic memory, so the corpus only grows — it
   went 21 → 24 in a single sitting of testing. Past roughly this many the
   surface is a smear of dots nobody can read, and the frame cost of the
   simulation is quadratic in the node count. What survives the cut is
   chosen by what matters, never by what happens to be first. */
export const MAX_NODES = 72;

const hash = (s: string) => {
  let h = 0;
  for (const ch of s) h = (h * 31 + ch.charCodeAt(0)) & 2047;
  return h / 2047;
};

/* Which hemisphere a node belongs to. Off its identity, so it does not
   move between them when the corpus grows. */
const sideOf = (id: string): -1 | 1 => (hash(id + "side") < 0.5 ? -1 : 1);

/** Fold a cortex `u` back into [0,1) — the sweep is a loop front to back. */
const wrap = (u: number) => ((u % 1) + 1) % 1;

/** Roughly where on the cortex a point sits, for placing things beside it. */
function surfaceOf(p: P3): { u: number; v: number } {
  const d = Math.hypot(p.x, p.y, p.z) || 1;
  return {
    u: wrap(Math.atan2(Math.abs(p.x), p.z) / Math.PI),
    v: (Math.max(-1, Math.min(1, p.y / d)) + 1) / 2,
  };
}

/* Which nodes get drawn when there are more than we can show.

   Anything recalled is kept unconditionally — dropping a node she is
   actually holding, to make room for one she is not, would make the
   graph disagree with the Surfaced panel beside it. Core is kept because
   it is the frame everything else hangs off. The remainder is ranked by
   importance, and ties break on id so the set does not flicker between
   frames. */
export function visible(snap: MindSnapshot, max = MAX_NODES) {
  if (snap.nodes.length <= max) return { nodes: snap.nodes, hidden: 0 };

  const recalled = new Set(snap.recalled.map((r) => r.id));
  const rank = (n: MindSnapshot["nodes"][number]) =>
    recalled.has(n.id) ? 3 : n.kind === "memory" ? 2 : n.kind === "session" ? 1 : 0;

  /* `size` rather than `importance`, because two of the three kinds do not
     have an importance and never will. Ranking on a field that is null for
     most of the corpus would sort by kind and then by nothing. */
  const nodes = [...snap.nodes]
    .sort((a, b) =>
      rank(b) - rank(a) ||
      b.size - a.size ||
      b.confidence - a.confidence ||
      a.id.localeCompare(b.id))
    .slice(0, max);

  return { nodes, hidden: snap.nodes.length - nodes.length };
}

export function layout(snap: MindSnapshot, max = MAX_NODES) {
  const hopOf = new Map(snap.recalled.map((r) => [r.id, r.hop]));
  const { nodes: shown, hidden } = visible(snap, max);
  /* relations resolve against the DRAWN set: an edge to a node that was cut
     has nothing to attach to, and a line into empty space reads as a
     relation that does not exist */
  const byKey = new Map(shown.map((n) => [n.id, n]));

  const core = shown.filter((n) => n.kind === "memory");
  const entities = shown.filter((n) => n.kind === "session");
  const atomic = shown.filter((n) => n.kind === "message");

  const P = new Map<string, P3>();

  /* Core runs down the stem and the deep structures under the cortex.
     It is the frame everything else hangs off, and putting it where the
     brain puts what everything else hangs off means the anatomy is
     saying the same thing the graph is.

     The first few take the stem, which is short; the rest go deep, so a
     corpus with many core memories does not stack them into a column. */
  core.forEach((n, i) => {
    const t = core.length === 1 ? 0.5 : i / Math.max(1, core.length - 1);
    P.set(n.id, i < 4
      ? place("stem", hash(n.id), 0.12 + t * 0.76, 0.3 + hash(n.id + "r") * 0.6)
      : place("deep", hash(n.id), hash(n.id + "v"), hash(n.id + "w"), sideOf(n.id)));
  });

  /* Entities are spread evenly over the cortex of both hemispheres.
     Alternating the side by index rather than by hash guarantees both
     halves are populated — left to chance, a small corpus can land
     entirely on one side and the brain reads as half a brain. */
  entities.forEach((n, i) => {
    const side: -1 | 1 = i % 2 === 0 ? 1 : -1;
    const rank = Math.floor(i / 2);
    const of = Math.max(1, Math.ceil(entities.length / 2));
    /* walk around the surface by index, up and down it by hash — an
       even sweep front to back with the height jittered off identity */
    const u = (rank + 0.5) / of;
    const v = 0.24 + hash(n.id + "v") * 0.52;
    P.set(n.id, place("cortex", u, v, 0.35 + hash(n.id + "w") * 0.3, side));
  });

  /* A message sits on the cortex beside the session it belongs to, found
     by the same id lookup the edges use. Parentless ones go to the
     frontal pole rather than the middle — the middle is the fissure,
     and nothing lives there. */
  atomic.forEach((n) => {
    const parent = n.relations.map((r) => byKey.get(r)).find((t) => t && P.has(t.id));
    const anchor = parent ? P.get(parent.id)! : place("cortex", 0.08, 0.5, 0.7, sideOf(n.id));
    const side: -1 | 1 = anchor.x < 0 ? -1 : 1;
    /* Offset in the surface's own coordinates rather than in space, so
       the memory stays ON the cortex instead of floating off it. */
    const { u, v } = surfaceOf(anchor);
    const a = hash(n.id) * Math.PI * 2;
    const spread = 0.06 + hash(n.id + "s") * 0.06;
    P.set(n.id, place(
      "cortex",
      wrap(u + Math.cos(a) * spread),
      Math.min(0.97, Math.max(0.03, v + Math.sin(a) * spread * 1.6)),
      0.55 + hash(n.id + "w") * 0.45,
      side,
    ));
  });

  const placed: Placed[] = shown.map((n) => {
    const p = P.get(n.id) ?? { x: 0, y: 0, z: 0 };
    return { ...n, x: p.x, y: p.y, z: p.z, hop: hopOf.get(n.id) };
  });

  const edges: [Placed, Placed][] = [];
  const byId = new Map(placed.map((p) => [p.id, p]));
  for (const n of shown) {
    const a = byId.get(n.id)!;
    for (const r of n.relations) {
      const t = byKey.get(r);
      if (t && t.id !== n.id) {
        const b = byId.get(t.id);
        if (b) edges.push([a, b]);
      }
    }
  }
  return { placed, edges, hidden };
}

/** How big a node is drawn, in brain units.

    Small. The volume is about two units across and holds a few thousand
    tissue points; a memory has to read as one of the things IN the
    brain, not as a ball resting on it.

    `size` is the server's normalised real quantity — importance for a
    memory, message count for a session, tokens for a message — so every
    radius on screen is a number somebody could go and check. An unrated
    memory has size 0 and comes out at the floor, which is correct: it is
    there, and nothing says how much it weighs. */
export const radiusOf = (n: Placed) =>
  n.kind === "memory" ? 0.026 + n.size * 0.022
  : n.kind === "session" ? 0.019 + n.size * 0.016
  : 0.009 + n.size * 0.011;
