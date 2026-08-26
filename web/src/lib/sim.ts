/* The memory graph, alive — a small force simulation over the layout.

   Obsidian's graph view is the reference: nodes push each other apart,
   links pull them together, and the whole thing settles rather than
   snapping into place. The difference here is the ANCHOR. Every node is
   sprung back to the deterministic seed from graph.ts, so the simulation
   can only ever perturb the learned space, never replace it. Without
   that, a corpus that gains a memory every turn would rearrange itself
   completely each time and position would stop meaning anything.

   Three dimensions now, and in brain units rather than pixels — a node
   drifts across the cortex, not across a ring. The tuning constants are
   all scaled to a volume about 2 units across.

   Deliberately O(n²): the repulsion pass is every pair. At the MAX_NODES
   cap that is ~2,600 pairs a frame, which is nothing, and an octree
   would be a lot of machinery to avoid a cost we have already bounded. */
import type { Placed } from "./graph";
import { project } from "./brain";

export interface Body {
  id: string;
  x: number; y: number; z: number;    // live position
  vx: number; vy: number; vz: number;
  ax: number; ay: number; az: number; // the seed — what it is sprung back toward
  m: number;                          // mass, from the node's drawn size
  /** when this node was last pulled into context, for the trigger ripple */
  firedAt?: number;
}

/* Tuned by eye. The anchor is deliberately the strongest term: this
   should breathe around the seed, not wander off and find its own
   arrangement. */
const REPEL = 0.0000135;  // pairwise push
const REPEL_MAX = 0.28;   // ...only within this distance; beyond it, nothing
const SPRING = 0.05;      // along an edge, per unit of extension
const REST = 0.15;        // an edge's happy length
const ANCHOR = 0.05;      // back toward the seed
const DAMP = 0.86;
const MAX_V = 0.011;
/* Hard ceiling on how far a node may sit from its seed. The soft forces
   are tuned to stay well inside this; it exists so no combination of a
   dense cluster and a long edge can ever walk a memory across the
   cortex and quietly break the one property the layout guarantees. */
const LEASH = 0.1;

/** One integration step. Exported pure so the tuning is testable. */
export function step(bodies: Body[], links: [number, number][], drift: number) {
  const fx = new Float64Array(bodies.length);
  const fy = new Float64Array(bodies.length);
  const fz = new Float64Array(bodies.length);

  // repulsion — every pair, short range
  for (let i = 0; i < bodies.length; i++) {
    for (let j = i + 1; j < bodies.length; j++) {
      const a = bodies[i], b = bodies[j];
      let dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
      let d2 = dx * dx + dy * dy + dz * dz;
      if (d2 > REPEL_MAX * REPEL_MAX) continue;
      /* Two nodes at the identical position have no direction to
         separate along. Pick one off the indices — deterministic, so the
         frame stays reproducible, and taken from ANGLES so it can
         never itself be the zero vector. An earlier version used
         (i % 7) - 3 per axis, which is zero whenever an index lands on
         3; two such nodes divided by zero and turned the graph to NaN. */
      if (d2 < 1e-8) {
        const th = i * 2.3999 + j * 0.7;
        const ph = j * 1.9997 + i * 0.3;
        dx = Math.cos(th) * Math.cos(ph);
        dy = Math.sin(ph);
        dz = Math.sin(th) * Math.cos(ph);
        d2 = 1;
      }
      const d = Math.sqrt(d2);
      const f = (REPEL * a.m * b.m) / d2;
      const ux = dx / d, uy = dy / d, uz = dz / d;
      fx[i] -= ux * f; fy[i] -= uy * f; fz[i] -= uz * f;
      fx[j] += ux * f; fy[j] += uy * f; fz[j] += uz * f;
    }
  }

  /* links pull — Hooke, once, and divided by degree.

     Two bugs live here if you write it the obvious way. Scaling by
     distance as well as extension (f * d) makes a long edge pull
     quadratically. And summing every edge un-normalised drags a hub in
     proportion to how popular it is: "Owen" relates to most of the
     corpus, so it collected a dozen pulls, left its anchor entirely, and
     took the cluster with it. Dividing each node's share by its own
     degree means a well-connected memory is held, not hauled. */
  const deg = new Float64Array(bodies.length);
  for (const [i, j] of links) { deg[i]++; deg[j]++; }

  for (const [i, j] of links) {
    const a = bodies[i], b = bodies[j];
    const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    const d = Math.hypot(dx, dy, dz) || 1;
    const f = (d - REST) * SPRING;
    const ux = dx / d, uy = dy / d, uz = dz / d;
    const wi = 1 / Math.max(1, deg[i]), wj = 1 / Math.max(1, deg[j]);
    fx[i] += ux * f * wi; fy[i] += uy * f * wi; fz[i] += uz * f * wi;
    fx[j] -= ux * f * wj; fy[j] -= uy * f * wj; fz[j] -= uz * f * wj;
  }

  for (let i = 0; i < bodies.length; i++) {
    const b = bodies[i];

    // the anchor — the whole reason this stays a recognisable space
    fx[i] += (b.ax - b.x) * ANCHOR * 60;
    fy[i] += (b.ay - b.y) * ANCHOR * 60;
    fz[i] += (b.az - b.z) * ANCHOR * 60;

    /* A settled simulation is a still image. A slow per-node circulation,
       phased off the index, keeps it breathing without anything visibly
       travelling.

       Amplitude is set against the anchor: the spring pulls back at
       ANCHOR*60 per unit, so this force divided by that is roughly how
       far a node wanders. ~0.01 units is the window — below it the
       cortex looks frozen, above it memories start swapping neighbours
       and position stops being something you can learn. */
    const ph = i * 1.7;
    fx[i] += Math.cos(drift + ph) * 0.012;
    fy[i] += Math.sin(drift * 0.9 + ph) * 0.012;
    fz[i] += Math.cos(drift * 1.1 + ph * 0.6) * 0.012;

    b.vx = (b.vx + fx[i] / (b.m * 60)) * DAMP;
    b.vy = (b.vy + fy[i] / (b.m * 60)) * DAMP;
    b.vz = (b.vz + fz[i] / (b.m * 60)) * DAMP;

    const v = Math.hypot(b.vx, b.vy, b.vz);
    if (v > MAX_V) {
      b.vx = (b.vx / v) * MAX_V; b.vy = (b.vy / v) * MAX_V; b.vz = (b.vz / v) * MAX_V;
    }

    b.x += b.vx;
    b.y += b.vy;
    b.z += b.vz;

    // the leash — never further than this from where the seed put it
    const ox = b.x - b.ax, oy = b.y - b.ay, oz = b.z - b.az;
    const od = Math.hypot(ox, oy, oz);
    if (od > LEASH) {
      b.x = b.ax + (ox / od) * LEASH;
      b.y = b.ay + (oy / od) * LEASH;
      b.z = b.az + (oz / od) * LEASH;
      b.vx *= 0.4; b.vy *= 0.4; b.vz *= 0.4;
    }

    /* Stay in the brain. This replaced a ring clamp that kept the middle
       of the old flat layout empty for a dragon that used to sit there —
       the volume is the subject now, so containment is the volume. */
    const p = project(b);
    if (p.x !== b.x || p.y !== b.y || p.z !== b.z) {
      b.x = p.x; b.y = p.y; b.z = p.z;
      b.vx *= 0.5; b.vy *= 0.5; b.vz *= 0.5;
    }
  }
}

/* PORTED from Selene, with its three tiers renamed to Isabella's three kinds —
   see lib/graph.ts for the mapping and why. The weights are unchanged: what
   the anchor holds heaviest is what the space is learnable by. */
const massOf = (n: Placed) =>
  n.kind === "memory" ? 3.2 : n.kind === "session" ? 1.6 : 0.8;

/** Everything the simulation remembers between snapshots. */
export interface Sim {
  bodies: Map<string, Body>;
  /** bodies in the order the current snapshot laid them out */
  live: Body[];
  /** edges as index pairs into `live` */
  links: [number, number][];
}

export const newSim = (): Sim => ({ bodies: new Map(), live: [], links: [] });

/**
 * Reconcile the simulation against a freshly laid-out graph.
 *
 * Bodies persist across snapshots by id, so a node that was already on
 * screen keeps its momentum when a turn adds new memories around it —
 * the graph absorbs the change instead of jumping. Called once per
 * snapshot, never per frame.
 *
 * This is deliberately not a React hook. The renderer owns one
 * animation loop that both steps the physics and draws the result;
 * having the simulation drive React state as well meant the entire HUD
 * re-rendered sixty times a second to move some dots.
 */
export function sync(sim: Sim, placed: Placed[], edges: [Placed, Placed][], now = Date.now()) {
  const live: Body[] = [];
  const index = new Map<string, number>();

  for (const p of placed) {
    let b = sim.bodies.get(p.id);
    if (!b) {
      b = {
        id: p.id,
        x: p.x, y: p.y, z: p.z,
        vx: 0, vy: 0, vz: 0,
        ax: p.x, ay: p.y, az: p.z,
        m: massOf(p),
      };
      sim.bodies.set(p.id, b);
    } else {
      b.ax = p.x; b.ay = p.y; b.az = p.z; b.m = massOf(p);
    }

    /* Note the moment a node enters context, so the view can ripple it.
       Tracked here rather than in the view because it is a transition,
       and a loop that runs sixty times a second cannot tell one from a
       steady state. */
    const on = p.hop !== undefined;
    if (on && b.firedAt === undefined) b.firedAt = now;
    if (!on) b.firedAt = undefined;

    index.set(p.id, live.length);
    live.push(b);
  }

  for (const id of [...sim.bodies.keys()]) if (!index.has(id)) sim.bodies.delete(id);

  const links: [number, number][] = [];
  for (const [a, b] of edges) {
    const i = index.get(a.id), j = index.get(b.id);
    if (i !== undefined && j !== undefined) links.push([i, j]);
  }

  sim.live = live;
  sim.links = links;
  return sim;
}

/* Motion is a preference, and a thing that never stops moving is a
   problem for some people. That used to be a hook here; it now lives in
   the renderer, which reads the media query live inside its own loop —
   the simulation simply is not stepped, and the static seed layout is a
   complete fallback because it was designed to stand on its own. */
