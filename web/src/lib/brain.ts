/* The volume the memory graph lives in — a brain, in normalised units.

   Pure. No React, no three. The layout seeds against it, the simulation
   is contained by it, and the tests check it, so it cannot depend on
   any of them.

   Space: origin at the centre of the cerebrum, +x his anatomical left,
   +y up, +z forward (the frontal lobe). Half-width is 1, and every
   other extent is expressed against that. The renderer scales; nothing
   here knows about pixels.

   The read is carried by three things, in this order:

     · the FISSURE. Two hemispheres with a gap down the midline is the
       single feature that separates a brain from an egg at a glance,
       and it has to survive being seen from the front, where it is a
       notch, as well as from above, where it is a canyon
     · the FOLDS. A smooth ellipsoid reads as a smooth ellipsoid. The
       shell radius is modulated by a low-frequency sinusoid of both
       surface angles, which at node density reads as gyri
     · the CEREBELLUM. The lobe at the lower rear is what stops the
       silhouette being a ball — it gives the shape a back and a
       bottom, and therefore an orientation you can see it turn about

   A downloaded brain mesh was not considered for the same reason
   Body3D builds its anatomy from primitives: it would be a binary of
   uncertain licence, and the nodes would still need somewhere to sit
   inside it. */

export type Region = "cortex" | "deep" | "cerebellum" | "stem";

export interface P3 { x: number; y: number; z: number }

/* The cerebrum, as ellipsoid radii.

   Proportions matter more than any other number in this file. A human
   brain is about 17cm long, 14cm wide and 9.5cm tall — that is, clearly
   LONGER than it is wide and much FLATTER than either. The first pass
   used radii close to equal and the result read as a ball with texture
   on it, no matter how good the folds were.

   These are no longer eyeballed. They are fitted to the real cerebrum
   in public/anatomy/brain.json, measured by scripts/zbrain.py: the
   drawn shell reaches half-width 0.852, half-height 0.729 and
   half-length 1.100 in these units, which is where that mesh's surface
   actually is. An earlier hand-guessed RX made the analytic cortex a
   little over half the real width, and every node placed on it floated
   deep inside the mesh instead of sitting on the surface.

   RX is the full width before the hemispheres halve it, so the drawn
   half-width is RX/2. */
const RX = 1.6, RY = 0.68, RZ = 1.1;

/* How much wider the rear is than the front. A real cerebrum is
   occipitally broad and frontally tapered; without this the shape is
   symmetric front-to-back and turning it tells you nothing. */
/* Small on purpose. This scales the whole radius, so a large value
   pulls the frontal pole BACKWARDS as well as narrowing it — at 0.2 the
   analytic front stopped at z=0.92 while the real one reaches 1.10, and
   nodes on the frontal cortex sank inside the mesh. Narrowing x alone
   would be the anatomically truer fix, but that is what broke the
   shell/contains inverse before; a gentle radial taper costs less. */
const TAPER = 0.05;

/** The gap between the hemispheres. Total width, so each is pushed out by half. */
export const FISSURE = 0.13;

/* How deep the fissure cuts. Not all the way down — the hemispheres
   are joined below by the corpus callosum, and two fully separated
   halves read as two objects rather than one brain. */
const FISSURE_DEPTH = 0.55;

/* The folds. AMP is a fraction of the shell radius; the frequencies are
   how many ridges wrap the surface in each direction. Kept low — at
   MAX_NODES the surface is sampled sparsely, and a high frequency
   aliases into noise rather than reading as folds. */
const FOLD_AMP = 0.075;
const FOLD_THETA = 6;
const FOLD_PHI = 4;

/* The cortex band: nodes sit between these fractions of the shell
   radius, never filling the middle. A solid volume hides its own
   silhouette and turns the edges into a haystack. */
const BAND_LO = 0.84, BAND_HI = 1.0;

/* ── the lateral fissure and the temporal lobe ──

   After the overall proportions, this is what a brain seen from the
   side is actually recognised BY: a deep groove running back and
   upward from the front, with a separate lobe bulging below it. An
   ellipsoid with gyri on it and no Sylvian fissure reads as a walnut.

   The fissure is expressed as a valley in the radius function rather
   than as a cut in the mesh, which is what keeps `shell` and `contains`
   exact inverses of each other — see the note on `radius`. */
const SYL_FROM = 0.24, SYL_TO = 0.82;  // theta, as a fraction of PI
/** Where the fissure sits at a given theta — it climbs as it runs back. */
const sylvianAt = (t: number) => -0.66 + (t - SYL_FROM) * 0.6;
/** How deep the groove cuts, and how far the lobe below it bulges. */
const SYL_DEPTH = 0.1, TEMPORAL = 0.075;
/** How far past each end the feature fades out, in the same units as t. */
const SYL_FADE = 0.14;

/* The lobe at the lower rear. Sits BELOW the cerebrum's underside
   rather than inside it — the transverse gap between the two is most of
   what makes the side profile read as a brain rather than a bean. */
/* Both fitted to the same mesh as the cerebrum above — the lobe and the
   stalk sit where Z-Anatomy's actually are. */
export const CEREBELLUM = {
  c: { x: 0, y: -0.66, z: -0.41 },
  r: { x: 0.75, y: 0.34, z: 0.56 },
};

/* The brainstem, as a capsule from the underside of the cerebrum down
   and slightly back. */
export const STEM = {
  a: { x: 0, y: -0.3, z: 0.1 },
  b: { x: 0, y: -1.25, z: -0.15 },
  r: 0.25,
};

const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

/**
 * The cerebrum's radius in a direction, in the normalised space where
 * the bare ellipsoid is the unit sphere.
 *
 * `theta` is the angle about the vertical axis in [0, PI] — 0 is the
 * front, PI the back, and one hemisphere is the whole sweep because the
 * halves are mirrored. `phi` is the elevation from the equator in
 * [-PI/2, PI/2].
 *
 * Both the folds and the frontal taper live here rather than in the
 * axis radii, and that is deliberate: `shell` and `contains` are exact
 * inverses of each other only while the shape is one function of
 * direction. An earlier pass applied the taper to x inside `shell`,
 * which meant the angle `contains` recovered from a point was not the
 * angle that placed it, and nodes laid on the surface tested as
 * outside it.
 */
export function radius(theta: number, phi: number): number {
  const folds = 1 + FOLD_AMP * (
    Math.sin(theta * FOLD_THETA) * Math.cos(phi * FOLD_PHI) * 0.6 +
    Math.sin(phi * FOLD_PHI + theta * 2) * 0.4);
  /* narrower toward the front — a cerebrum is occipitally broad and
     frontally tapered, and without this it turns without telling you
     which way it is facing */
  const taper = 1 - TAPER * Math.max(0, Math.cos(theta) * Math.cos(phi));
  let r = folds * taper;

  /* The Sylvian fissure, and the temporal lobe under it. Both fade out
     at each end of their span so the feature does not stop dead at the
     frontal and occipital poles. */
  const t = theta / Math.PI;
  if (t > SYL_FROM - SYL_FADE && t < SYL_TO + SYL_FADE) {
    const span = Math.min(1,
      Math.min(t - (SYL_FROM - SYL_FADE), (SYL_TO + SYL_FADE) - t) / SYL_FADE);
    const line = sylvianAt(t);
    const groove = (phi - line) / 0.11;
    r -= SYL_DEPTH * span * Math.exp(-groove * groove);
    const lobe = (phi - (line - 0.34)) / 0.3;
    r += TEMPORAL * span * Math.exp(-lobe * lobe);
  }
  return r;
}

/** How far out of the midline the hemispheres are pushed at a height. */
function inset(y: number): number {
  /* Only above the corpus callosum: two fully separated halves read as
     two objects rather than one brain. */
  const above = clamp((y / RY + 1 - FISSURE_DEPTH) / FISSURE_DEPTH, 0, 1);
  return (FISSURE / 2) * above;
}

/**
 * A point on the cortical shell of one hemisphere.
 *
 * `side` is -1 or +1; the point is pushed out from the midline by half
 * the fissure so the gap exists at every height the fissure reaches.
 * `depth` is a fraction of the radius — 1 is the surface.
 */
export function shell(theta: number, phi: number, side: -1 | 1, depth = 1): P3 {
  const f = radius(theta, phi) * depth;
  const cp = Math.cos(phi);
  const x = Math.sin(theta) * cp * RX * f;
  const y = Math.sin(phi) * RY * f;
  const z = Math.cos(theta) * cp * RZ * f;
  /* Split: the hemisphere owns half the width, moved out by the fissure. */
  return { x: side * (Math.abs(x) * 0.5 + inset(y)), y, z };
}

const ell = (p: P3, c: P3, r: P3) => {
  const dx = (p.x - c.x) / r.x, dy = (p.y - c.y) / r.y, dz = (p.z - c.z) / r.z;
  return dx * dx + dy * dy + dz * dz;
};

/** Distance from a point to the stem's axis, and how far along it fell. */
function toStem(p: P3) {
  const ax = STEM.b.x - STEM.a.x, ay = STEM.b.y - STEM.a.y, az = STEM.b.z - STEM.a.z;
  const len2 = ax * ax + ay * ay + az * az;
  const t = clamp(((p.x - STEM.a.x) * ax + (p.y - STEM.a.y) * ay + (p.z - STEM.a.z) * az) / len2, 0, 1);
  const cx = STEM.a.x + ax * t, cy = STEM.a.y + ay * t, cz = STEM.a.z + az * t;
  return { d: Math.hypot(p.x - cx, p.y - cy, p.z - cz), c: { x: cx, y: cy, z: cz } };
}

/** Is this point inside the brain — any of its parts? */
export function contains(p: P3): boolean {
  if (ell(p, CEREBELLUM.c, CEREBELLUM.r) <= 1) return true;
  if (toStem(p).d <= STEM.r) return true;

  /* The cerebrum, minus the fissure it is split by. Undo the split
     first — the halved, offset x is put back the way `shell` made it —
     then the test is the plain one against `radius`. */
  const ax = Math.abs(p.x);
  const cut = inset(p.y);
  if (ax < cut) return false;
  const nx = ((ax - cut) * 2) / RX, ny = p.y / RY, nz = p.z / RZ;
  const d = Math.sqrt(nx * nx + ny * ny + nz * nz);
  if (d === 0) return true;
  const theta = Math.atan2(nx, nz);
  const phi = Math.asin(clamp(ny / d, -1, 1));
  return d <= radius(theta, phi);
}

/**
 * The nearest legal point, for anything the simulation has pushed out
 * of the volume. This is the containment that replaced the ring clamp
 * the old 2D layout used to keep its middle clear.
 *
 * Cheap and iterative rather than exact: the surface is folded, so
 * there is no closed form for the nearest point on it. Walking back
 * along the ray toward the centre of whichever part the point is
 * closest to converges in a handful of steps and is called at most once
 * per node per frame.
 */
export function project(p: P3): P3 {
  if (contains(p)) return p;

  /* Which part is it nearest? Pull toward a point known to be inside
     THAT part, so a node that drifted off the cerebellum is not yanked
     up into the cerebrum — a memory teleporting across the space is the
     one thing the layout promises will not happen.

     The cerebrum's anchor is deliberately off the midline. The origin
     is not inside the brain — the fissure runs through it — and an
     earlier version bisected toward it, found nothing contained
     anywhere along the ray, and returned points still outside. */
  const stem = toStem(p);
  const cerebrum = { x: (p.x < 0 ? -1 : 1) * (RX * 0.3), y: 0, z: 0 };
  const cands: [P3, number][] = [
    [cerebrum, Math.hypot(p.x - cerebrum.x, p.y, p.z)],
    [CEREBELLUM.c, Math.hypot(p.x - CEREBELLUM.c.x, p.y - CEREBELLUM.c.y, p.z - CEREBELLUM.c.z)],
    [stem.c, stem.d],
  ];
  cands.sort((a, b) => a[1] - b[1]);
  const c = cands.find(([q]) => contains(q))?.[0] ?? cerebrum;

  let lo = 0, hi = 1;
  for (let i = 0; i < 18; i++) {
    const t = (lo + hi) / 2;
    const q = { x: c.x + (p.x - c.x) * t, y: c.y + (p.y - c.y) * t, z: c.z + (p.z - c.z) * t };
    if (contains(q)) lo = t; else hi = t;
  }
  /* a hair inside, so the next frame does not immediately find it out
     again on a rounding error */
  const t = lo * 0.995;
  return { x: c.x + (p.x - c.x) * t, y: c.y + (p.y - c.y) * t, z: c.z + (p.z - c.z) * t };
}

/**
 * A deterministic point in a named region.
 *
 * Every input is a number in [0,1) derived from the node's identity, so
 * the same memory lands in the same place between turns — the property
 * the whole layout is built to preserve.
 *
 * `u` walks around, `v` walks up, `w` walks inward.
 */
export function place(region: Region, u: number, v: number, w: number, side: -1 | 1 = 1): P3 {
  switch (region) {
    case "cortex": {
      /* Half a turn, not a whole one. The hemisphere is a mirrored
         half, so theta and 2PI-theta land on the same point — sweeping
         the full circle stacks every node on a twin. */
      const theta = u * Math.PI;
      /* Elevation is biased toward the equator by the arcsine: sampling
         phi uniformly crowds both poles, and the crown of the brain
         ends up a cap of nodes with bare temples under it. */
      const phi = Math.asin(clamp(v * 2 - 1, -1, 1)) * 0.86;
      return shell(theta, phi, side, BAND_LO + (BAND_HI - BAND_LO) * w);
    }
    case "deep": {
      /* Just off the midline, inside the cerebrum — the structures the
         cortex hangs off. */
      const theta = u * Math.PI;
      const phi = (v - 0.5) * 0.9;
      return shell(theta, phi, side, 0.34 + w * 0.16);
    }
    case "cerebellum": {
      const theta = u * Math.PI * 2;
      const phi = Math.asin(clamp(v * 2 - 1, -1, 1)) * 0.9;
      const f = 0.72 + w * 0.24;
      return {
        x: CEREBELLUM.c.x + Math.sin(theta) * Math.cos(phi) * CEREBELLUM.r.x * f,
        y: CEREBELLUM.c.y + Math.sin(phi) * CEREBELLUM.r.y * f,
        z: CEREBELLUM.c.z + Math.cos(theta) * Math.cos(phi) * CEREBELLUM.r.z * f,
      };
    }
    case "stem": {
      const t = v;
      const a = u * Math.PI * 2;
      const r = STEM.r * 0.62 * w;
      return {
        x: STEM.a.x + (STEM.b.x - STEM.a.x) * t + Math.cos(a) * r,
        y: STEM.a.y + (STEM.b.y - STEM.a.y) * t,
        z: STEM.a.z + (STEM.b.z - STEM.a.z) * t + Math.sin(a) * r,
      };
    }
  }
}

/** The radius of the smallest sphere about the origin holding all of it. */
export const EXTENT = 1.62;
