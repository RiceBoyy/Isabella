/* PORTED from Selene (`src/components/Body3D.tsx`), Owen's own component,
   unchanged except for this note. It is his asset and it has already been
   debugged against the problems that make a primitive body read as a robot -
   the taper of the trunk, pads re-lathed from the trunk's own profile, limbs
   sized to real landmarks rather than eyeballed. Rewriting it here would have
   been re-earning all of that for nothing.

   ONE ADAPTATION, and it is the reason it rendered nothing at first: Selene
   uses Tailwind and this component styles itself with it. Isabella has no
   Tailwind, so `absolute inset-0` was an inert string, the host div collapsed
   to zero height, and `el.clientHeight || 1` sized the canvas 1x1. The class
   names below are Isabella's own, in styles.css, and mean what the Tailwind
   ones meant. The component's own comment already warned that the wrapper's
   size is set by CSS alone.

   Isabella drives it with `active` only: a map of region id -> tone, where a
   bare group ("delt") lights both sides. The optional Z-Anatomy atlas is not
   installed here, and `loadJson` returning null is the supported path - the
   primitives stand in, which is the whole reason they exist.

   What lights, and why it is honest: a region is "worked" only when an
   exercise was actually TICKED in this week's log. An untouched week lights
   nothing. See core/body.py. */

import { useEffect, useRef } from "react";
import * as THREE from "three";

/* The body, in three dimensions, built out of primitives rather than
   loaded from a file.

   A downloaded anatomy model would be a large binary of uncertain
   licence sitting in the repo, and it would still need every muscle
   group split into its own named mesh before any of this could
   highlight anything. Building it here means the region names are the
   same strings the scanner already produces — "delt.l", "quad" — so a
   log line lights the body with no mapping table in between.

   The silhouette is a base mesh per limb with pads laid on top: the
   upper arm is one capsule with a bicep pad in front and a tricep pad
   behind, both the same colour as the arm until something makes them
   otherwise. Idle, it reads as one continuous body; lit, the pad is
   unmistakably a muscle rather than a glowing cylinder. */

export type Tone = "worked" | "issue" | "idle";

/* Sides. A bare group id from the program ("delt") means both; an issue
   that names a side ("delt.l") means one. The left shoulder sitting
   lower than the right is the whole reason this distinction exists.

   Not exported: a non-component export from a file that also exports a
   component turns every edit into an HMR invalidate rather than a
   refresh, and the scene — built once in an effect — silently keeps
   rendering the old geometry. */
const SIDES = ["l", "r"] as const;

const BASE = 0x4b4b60;
const WORKED = 0xb28bff;
const ISSUE = 0xf4c95d;

/** the y the model turns about — roughly the navel, so it spins in place */
const PIVOT_Y = 0.9;

type Part = {
  id: string;
  geo: THREE.BufferGeometry;
  pos: [number, number, number];
  rot?: [number, number, number];
  scale?: [number, number, number];
};

const capsule = (r: number, len: number) => new THREE.CapsuleGeometry(r, len, 10, 20);
const sphere = (r: number) => new THREE.SphereGeometry(r, 24, 18);

/**
 * A solid of revolution from a [y, radius] profile.
 *
 * The trunk is built this way rather than from stacked capsules
 * because the taper *is* the silhouette: shoulders wider than chest,
 * chest wider than waist, waist narrower than hips, all in one
 * unbroken surface. Three capsules in a pile read as a robot no matter
 * how carefully they are sized.
 */
function lathe(
  profile: [number, number][],
  segments = 36,
  phiStart = 0,
  phiLength = Math.PI * 2,
): THREE.LatheGeometry {
  return new THREE.LatheGeometry(
    profile.map(([y, r]) => new THREE.Vector2(Math.max(r, 0.0001), y)),
    segments, phiStart, phiLength,
  );
}

/* The trunk's silhouette, shared between the trunk itself and every pad
   laid on it. */
const TRUNK: [number, number][] = [
  [0.9, 0.02], [0.912, 0.092], [0.945, 0.122], [0.985, 0.132],
  [1.035, 0.126], [1.09, 0.113], [1.135, 0.108], [1.19, 0.118],
  [1.26, 0.134], [1.325, 0.143], [1.395, 0.145], [1.45, 0.135],
  [1.492, 0.113], [1.522, 0.076], [1.538, 0.044], [1.543, 0.018],
];

const TRUNK_SCALE: [number, number, number] = [1.14, 1, 0.76];

/**
 * A muscle pad as a patch of the trunk's own surface.
 *
 * Flat ellipsoids do not work here. The trunk is deeper at the centre
 * than at the sides, so a slab of constant depth is swallowed in the
 * middle and stands proud at the edges — it renders as a highlight with
 * a bite out of it, which looked like a belt buckle rather than a
 * muscle. Re-lathing the same profile a few percent larger, over a
 * slice of angle and height, gives a patch that hugs the body
 * everywhere it touches.
 *
 * Angles are measured from the front: LatheGeometry puts phi = 0 on +z,
 * and +x is his anatomical left.
 */
function pad(y0: number, y1: number, phiStart: number, phiLength: number, inflate = 1.075) {
  const within = TRUNK.filter(([y]) => y >= y0 && y <= y1);
  /* Interpolate the cut ends so a pad is not clipped to whatever
     profile points happen to fall inside its range. */
  const at = (y: number) => {
    let lo = TRUNK[0];
    let hi = TRUNK[TRUNK.length - 1];
    for (let i = 0; i < TRUNK.length - 1; i++) {
      if (TRUNK[i][0] <= y && TRUNK[i + 1][0] >= y) { lo = TRUNK[i]; hi = TRUNK[i + 1]; break; }
    }
    const t = hi[0] === lo[0] ? 0 : (y - lo[0]) / (hi[0] - lo[0]);
    return [y, lo[1] + (hi[1] - lo[1]) * t] as [number, number];
  };
  const profile = [at(y0), ...within, at(y1)].map(([y, r]) => [y, r * inflate] as [number, number]);
  return lathe(profile, 28, phiStart, phiLength);
}

/**
 * Every mesh in the body, in metres, feet at y = 0 and facing +z.
 *
 * Proportions are eyeballed against a 1.8 m frame rather than measured
 * from anyone — this is a diagram of where the muscles are, not a
 * likeness, and pretending otherwise would be another number on screen
 * that nobody wrote down.
 */
function parts(): Part[] {
  const out: Part[] = [];
  const add = (p: Part) => out.push(p);

  /* Landmarks for a 1.8 m frame: crown 1.80, chin 1.57, shoulder line
     1.45, elbow 1.13, wrist 0.87, crotch 0.92, knee 0.50, ankle 0.09.
     Limbs are sized to span those, not eyeballed — the first pass left
     the shins ending 10 cm above the feet, which is exactly the sort of
     thing that reads as "robot" without being nameable. */

  /* ── head and neck ── */
  add({ id: "head", geo: sphere(0.096), pos: [0, 1.676, 0.004], scale: [0.9, 1.2, 1.02] });
  add({ id: "neck", geo: capsule(0.04, 0.05), pos: [0, 1.532, -0.008] });

  /* ── the trunk, one surface ──
     Narrower than it looks like it should be: the deltoids sit outside
     it and carry the shoulder width. A trunk wide enough to reach the
     shoulder line swallows the arms and turns the whole thing into an
     egg with bumps. */
  add({ id: "trunk", geo: lathe(TRUNK), pos: [0, 0, 0], scale: TRUNK_SCALE });

  for (const s of SIDES) {
    /* Anatomical left, not the viewer's. Facing the camera, his left
       arm is on the right of the screen — so "left shoulder lower than
       right" lights the side he means, not its mirror. */
    const x = s === "l" ? 1 : -1;
    const side = s === "l" ? 1 : -1;   // +phi is toward his left

    /* ── trunk pads, as patches of the trunk surface ── */
    add({
      id: `chest.${s}`,
      geo: pad(1.295, 1.44, side > 0 ? 0.16 : -1.32, 1.16),
      pos: [0, 0, 0], scale: TRUNK_SCALE,
    });
    add({
      id: `lat.${s}`,
      geo: pad(1.185, 1.36, side > 0 ? 1.42 : -2.5, 1.08),
      pos: [0, 0, 0], scale: TRUNK_SCALE,
    });
    add({ id: `glute.${s}`, geo: sphere(0.066), pos: [x * 0.06, 0.945, -0.062], scale: [1, 0.94, 0.78] });

    /* ── arms: shoulder 1.45 → elbow 1.13 → wrist 0.87 ── */
    add({ id: `delt.${s}`, geo: sphere(0.065), pos: [x * 0.168, 1.428, 0], scale: [1.04, 1.02, 1] });
    add({ id: `arm.${s}`, geo: capsule(0.042, 0.235), pos: [x * 0.187, 1.29, 0], rot: [0, 0, x * -0.06] });
    add({ id: `bi.${s}`, geo: capsule(0.028, 0.165), pos: [x * 0.182, 1.3, 0.026], rot: [0, 0, x * -0.06] });
    add({ id: `tri.${s}`, geo: capsule(0.028, 0.18), pos: [x * 0.193, 1.288, -0.026], rot: [0, 0, x * -0.06] });
    add({ id: `elbow.${s}`, geo: sphere(0.037), pos: [x * 0.196, 1.128, 0.002] });
    add({ id: `forearm.${s}`, geo: capsule(0.035, 0.19), pos: [x * 0.203, 0.998, 0.004], rot: [0, 0, x * -0.025] });
    add({ id: `hand.${s}`, geo: sphere(0.04), pos: [x * 0.208, 0.842, 0.006], scale: [0.58, 1.34, 0.4] });

    /* ── legs: crotch 0.92 → knee 0.50 → ankle 0.09 ── */
    add({ id: `thigh.${s}`, geo: capsule(0.065, 0.29), pos: [x * 0.078, 0.708, 0], rot: [0, 0, x * -0.028] });
    add({ id: `quad.${s}`, geo: capsule(0.042, 0.235), pos: [x * 0.078, 0.712, 0.036], rot: [0, 0, x * -0.028] });
    add({ id: `ham.${s}`, geo: capsule(0.042, 0.215), pos: [x * 0.078, 0.722, -0.038], rot: [0, 0, x * -0.028] });
    add({ id: `knee.${s}`, geo: sphere(0.05), pos: [x * 0.072, 0.502, 0.004] });
    add({ id: `shin.${s}`, geo: capsule(0.045, 0.32), pos: [x * 0.07, 0.295, 0] });
    add({ id: `calf.${s}`, geo: sphere(0.046), pos: [x * 0.07, 0.362, -0.026], scale: [0.8, 1.85, 0.72] });
    add({ id: `ankle.${s}`, geo: sphere(0.036), pos: [x * 0.07, 0.09, 0] });
    add({ id: `foot.${s}`, geo: sphere(0.048), pos: [x * 0.07, 0.038, 0.058], scale: [0.7, 0.44, 1.85] });
  }

  /* ── midline pads ── */
  add({ id: "back", geo: pad(1.24, 1.45, Math.PI - 0.95, 1.9), pos: [0, 0, 0], scale: TRUNK_SCALE });
  add({ id: "lumbar", geo: pad(1.06, 1.21, Math.PI - 0.62, 1.24), pos: [0, 0, 0], scale: TRUNK_SCALE });
  add({ id: "core", geo: pad(1.075, 1.245, -0.52, 1.04), pos: [0, 0, 0], scale: TRUNK_SCALE });
  add({ id: "pelvis", geo: pad(0.945, 1.055, -0.72, 1.44), pos: [0, 0, 0], scale: TRUNK_SCALE });

  return out;
}

/* Regions with no muscle to light. They still need to exist or the body
   has holes in it, but nothing ever turns them violet. */
const NEVER_LIT = new Set([
  "trunk",
  "arm.l", "arm.r", "elbow.l", "elbow.r",
  "thigh.l", "thigh.r", "shin.l", "shin.r", "ankle.l", "ankle.r",
]);

/** the pedestal: a ring of ticks, the same one the flat figure stood on */
function pedestal(): THREE.Object3D {
  const g = new THREE.Group();
  const mk = (radius: number, opacity: number) => {
    const pts: THREE.Vector3[] = [];
    for (let i = 0; i <= 96; i++) {
      const a = (i / 96) * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(a) * radius, 0, Math.sin(a) * radius));
    }
    return new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineBasicMaterial({ color: 0x8a8a95, transparent: true, opacity }),
    );
  };
  g.add(mk(0.42, 0.35), mk(0.3, 0.18));

  const ticks: THREE.Vector3[] = [];
  for (let i = 0; i < 56; i++) {
    const a = (i / 56) * Math.PI * 2;
    const inner = i % 7 ? 0.44 : 0.42;
    ticks.push(
      new THREE.Vector3(Math.cos(a) * inner, 0, Math.sin(a) * inner),
      new THREE.Vector3(Math.cos(a) * 0.48, 0, Math.sin(a) * 0.48),
    );
  }
  g.add(new THREE.LineSegments(
    new THREE.BufferGeometry().setFromPoints(ticks),
    new THREE.LineBasicMaterial({ color: 0x8a8a95, transparent: true, opacity: 0.5 }),
  ));
  return g;
}

/* ── the real body ─────────────────────────────────────────────────
   The primitives above are a fallback. When public/anatomy/body.json
   is present the whole figure is replaced by a segmented human mesh —
   MakeHuman's `hm08` base mesh, CC0 1.0 (public domain), cut into
   regions by scripts/basemesh.mjs using its own joint locators.

   It is a skin surface, not an anatomy atlas: the regions are areas of
   the body, so a lit chest is the chest of a real figure rather than a
   floating pectoral. At the size this is drawn that reads better than
   overlapping muscle bellies would, and it is one mesh with one set of
   proportions — which the anatomy atlases are not. */

interface BaseMesh {
  positions: number[];
  regions: Record<string, number[]>;
  source?: string;
  licence?: string;
}

export interface LayerInfo {
  id: string;
  label: string;
  file: string;
}

interface Manifest {
  default?: string;
  layers?: LayerInfo[];
}

async function loadJson<T>(path: string): Promise<T | null> {
  try {
    const r = await fetch(path);
    return r.ok ? ((await r.json()) as T) : null;
  } catch {
    return null;   // nothing installed; the primitives stand in
  }
}

const isMesh = (d: BaseMesh | null): d is BaseMesh =>
  !!d?.positions?.length && !!d.regions;

/**
 * Region geometries that share one set of vertices.
 *
 * Normals are computed once over the whole body and then shared, not
 * computed per region. Per-region normals are only correct in a
 * region's interior — at every seam the two sides disagree about which
 * way the surface faces and the body ends up with lit scars along
 * every boundary.
 */
export interface Bounds {
  centre: THREE.Vector3;
  radius: number;
  /* The real box, kept as well as the sphere. Unioning regions as
     cubes of ±radius lets one big region — the skeleton is a single
     mesh spanning the whole figure — inflate the union far past the
     body and drag its centre off the spin axis. */
  min: THREE.Vector3;
  max: THREE.Vector3;
}

/**
 * A region's own bounds, computed from its index.
 *
 * Not `geometry.computeBoundingSphere()`: every region shares one
 * position attribute, and that method walks the whole attribute
 * ignoring the index — so each muscle would report the bounds of the
 * entire body and framing one would frame all of them.
 */
function boundsOf(positions: number[], index: number[]): Bounds {
  let minX = Infinity, minY = Infinity, minZ = Infinity;
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity;
  for (const i of index) {
    const x = positions[i * 3];
    const y = positions[i * 3 + 1];
    const z = positions[i * 3 + 2];
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (z < minZ) minZ = z;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
    if (z > maxZ) maxZ = z;
  }
  const centre = new THREE.Vector3((minX + maxX) / 2, (minY + maxY) / 2, (minZ + maxZ) / 2);
  const radius = Math.max(maxX - minX, maxY - minY, maxZ - minZ) / 2;
  return {
    centre,
    radius: Math.max(radius, 0.02),
    min: new THREE.Vector3(minX, minY, minZ),
    max: new THREE.Vector3(maxX, maxY, maxZ),
  };
}

function cutUp(mesh: BaseMesh): { id: string; geo: THREE.BufferGeometry; bounds: Bounds }[] {
  const position = new THREE.Float32BufferAttribute(mesh.positions, 3);

  const whole = new THREE.BufferGeometry();
  whole.setAttribute("position", position);
  whole.setIndex(Object.values(mesh.regions).flat());
  whole.computeVertexNormals();
  const normal = whole.getAttribute("normal");
  whole.dispose();

  return Object.entries(mesh.regions).map(([id, index]) => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", position);
    geo.setAttribute("normal", normal);
    geo.setIndex(index);
    return { id, geo, bounds: boundsOf(mesh.positions, index) };
  });
}

/** which way the model is facing */
/** which way the model is facing, so the reader knows what they are looking at */
function facing(yaw: number): string {
  const deg = ((((yaw * 180) / Math.PI) % 360) + 360) % 360;
  if (deg < 45 || deg >= 315) return "FRONT";
  if (deg < 135) return "LEFT SIDE";
  if (deg < 225) return "BACK";
  return "RIGHT SIDE";
}

export function Body3D({
  active,
  selected,
  layer,
  onPick,
  onCredit,
  onLayers,
  className = "",
}: {
  /** region id → tone. A bare group ("delt") lights both sides. */
  active: Record<string, Tone>;
  /** the region being inspected, drawn brighter than the rest */
  selected?: string | null;
  /** which layer to show: "skin" | "muscle" | "skeleton" */
  layer?: string | null;
  /** a click on a muscle, or on empty space (null) */
  onPick?: (region: string | null) => void;
  /* The mesh carries its own attribution. Z-Anatomy is CC BY-SA, which
     requires the credit be visible rather than buried in a README —
     so the mesh reports it and the view prints it. */
  onCredit?: (credit: string | null) => void;
  /** the layers the atlas actually shipped, once the manifest lands */
  onLayers?: (layers: LayerInfo[], fallback: string) => void;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const label = useRef<HTMLElement>(null);
  const readout = useRef<HTMLElement>(null);
  /* The tone map is read inside the render loop, which must not be torn
     down and rebuilt every time a log changes — the scene, meshes and
     WebGL context are built once and this ref is how new data reaches
     them. */
  const tones = useRef(active);
  tones.current = active;
  const picked = useRef(selected ?? null);
  picked.current = selected ?? null;
  const pick = useRef(onPick);
  pick.current = onPick;
  const onCreditRef = useRef(onCredit);
  onCreditRef.current = onCredit;
  const onLayersRef = useRef(onLayers);
  onLayersRef.current = onLayers;
  const wanted = useRef(layer ?? null);
  wanted.current = layer ?? null;

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.01, 100);
    camera.position.set(0, 1.02, 4.15);
    camera.lookAt(0, 0.95, 0);

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      /* No WebGL — a software fallback is not worth shipping, and a
         blank panel with no explanation is worse than a sentence. */
      el.innerHTML =
        '<div style="display:grid;place-items:center;height:100%;font-size:9px;letter-spacing:.15em;color:#8A8A95">WEBGL UNAVAILABLE</div>';
      return;
    }
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setClearColor(0x000000, 0);
    el.appendChild(renderer.domElement);

    /* The canvas is taken out of flow deliberately. Left in it, its
       intrinsic size grows the element that is measured to size it, and
       every frame makes it a little bigger — the first version of this
       reached 14720px across before anyone noticed the body had
       vanished. Absolute positioning breaks that loop: the wrapper's
       size is set by CSS alone and the canvas only ever follows. */
    Object.assign(renderer.domElement.style, {
      position: "absolute",
      inset: "0",
      width: "100%",
      height: "100%",
      display: "block",
      touchAction: "none",
      cursor: "grab",
    });

    scene.add(new THREE.HemisphereLight(0xb4b4d0, 0x14141c, 1.9));
    const key = new THREE.DirectionalLight(0xffffff, 1.6);
    key.position.set(2.2, 3.4, 3.2);
    scene.add(key);
    /* a violet rim from behind, so the silhouette still reads when the
       model is turned away from the camera */
    const rim = new THREE.DirectionalLight(0xb28bff, 1.5);
    rim.position.set(-2.4, 1.6, -3);
    scene.add(rim);

    const materials = {
      idle: new THREE.MeshStandardMaterial({ color: BASE, roughness: 0.72, metalness: 0.08 }),
      worked: new THREE.MeshStandardMaterial({
        color: 0x6d51a6, roughness: 0.45, metalness: 0.1,
        emissive: WORKED, emissiveIntensity: 0.6,
      }),
      issue: new THREE.MeshStandardMaterial({
        color: 0x7d6026, roughness: 0.5, metalness: 0.1,
        emissive: ISSUE, emissiveIntensity: 0.55,
      }),
      /* Bone. Carried so the figure has a head, hands and feet rather
         than stopping at the neck and the wrists — context, never the
         subject, so it sits back from the muscles and is never lit. */
      bone: new THREE.MeshStandardMaterial({
        color: 0x6a6a78, roughness: 0.85, metalness: 0.03,
      }),
      /* The inspected part. Brighter than either state so it reads as
         "this is the one you are reading about" regardless of whether
         it was worked, hurts, or neither. */
      selected: new THREE.MeshStandardMaterial({
        color: 0xd8d8e8, roughness: 0.3, metalness: 0.15,
        emissive: 0xffffff, emissiveIntensity: 0.28,
      }),
    };

    const body = new THREE.Group();
    const meshes: { id: string; mesh: THREE.Mesh }[] = [];
    const geos: THREE.BufferGeometry[] = [];
    /* Kept so the fallback can be torn out wholesale when the real
       body arrives — including the pieces that were never pickable. */
    const primitives: THREE.Mesh[] = [];

    for (const p of parts()) {
      const mesh = new THREE.Mesh(p.geo, materials.idle);
      mesh.position.set(...p.pos);
      if (p.rot) mesh.rotation.set(...p.rot);
      if (p.scale) mesh.scale.set(...p.scale);
      body.add(mesh);
      geos.push(p.geo);
      primitives.push(mesh);
      if (!NEVER_LIT.has(p.id)) meshes.push({ id: p.id, mesh });
    }

    /* Turn about the middle of the body rather than about its feet,
       which would swing it through the panel like a gate. Both offsets
       are refined once a real mesh lands and its true centre is known. */
    const pivot = new THREE.Group();
    pivot.position.y = PIVOT_Y;
    body.position.y = -PIVOT_Y;
    pivot.add(body);
    scene.add(pivot);

    /* The pedestal hangs off the pivot, not off the body: the body gets
       shifted onto the spin axis and the floor must not shift with it. */
    const floor = pedestal();
    pivot.add(floor);
    const placeFloor = () => { floor.position.y = -pivot.position.y; };
    placeFloor();

    /* The real body replaces the primitives outright rather than muscle
       by muscle. A segmented human mesh and a stack of capsules do not
       share proportions, so mixing them puts a correctly-placed muscle
       through the middle of an approximated limb. */
    let live = true;

    /* One group per layer, all built up front and all but one hidden.
       Switching is then a visibility flip rather than a rebuild —
       tearing the scene down and re-parsing three megabytes of JSON
       every time someone wants to see the skeleton would make the
       control feel broken. */
    const layers = new Map<string, THREE.Group>();
    /* Attribution is per layer, not per body: the skin is CC0 and owes
       nothing, the muscle and skeleton layers are CC BY-SA and owe a
       visible credit. Reporting whichever loaded first credited
       MakeHuman while Z-Anatomy was on screen. */
    const credits = new Map<string, string>();
    /* Where each region sits in the body's own space, so the camera can
       frame it. Kept per layer: the pectoralis major on the muscle
       layer and the chest patch on the skin are the same region id but
       not the same shape. */
    const bounds = new Map<string, Bounds>();
    /* The union across every layer, not per layer. `body.position` is
       one transform shared by all three, so computing it per layer let
       whichever loaded last win — the skeleton's centre was being used
       to place the figure while the muscle layer was on screen, and the
       body sat off its own pedestal. Unioning also keeps the framing
       identical as layers are switched. */
    const unionLo = new THREE.Vector3(Infinity, Infinity, Infinity);
    const unionHi = new THREE.Vector3(-Infinity, -Infinity, -Infinity);
    /* Every region's centre, so the midline can be found from the
       left/right pairs. The bounding box will not do it: the arms hang
       asymmetrically in the atlas, which pulls the box centre off the
       spine and leaves the torso visibly beside its own pedestal. */
    const centres = new Map<string, THREE.Vector3>();

    let wholeBody: Bounds = {
      centre: new THREE.Vector3(0, 0.9, 0),
      radius: 0.92,
      min: new THREE.Vector3(-0.5, 0, -0.3),
      max: new THREE.Vector3(0.5, 1.8, 0.3),
    };
    let shown: string | null = null;

    const show = (id: string | null) => {
      const want = id && layers.has(id) ? id : layers.keys().next().value ?? null;
      if (!want || want === shown) return;
      shown = want;
      for (const [name, group] of layers) group.visible = name === want;
      onCreditRef.current?.(credits.get(want) ?? null);

      /* Picking follows what is on screen. Left pointing at a hidden
         layer, a click would select a muscle nobody can see. */
      meshes.length = 0;
      const group = layers.get(want);
      group?.traverse((o) => {
        const id2 = (o as THREE.Mesh).userData?.region as string | undefined;
        if (id2 && (o as THREE.Mesh).isMesh) meshes.push({ id: id2, mesh: o as THREE.Mesh });
      });
    };

    void (async () => {
      const manifest = await loadJson<Manifest>("/anatomy/index.json");
      if (!live || !manifest?.layers?.length) return;

      let first = true;

      for (const info of manifest.layers) {
        const mesh = await loadJson<BaseMesh>(`/anatomy/${info.file}`);
        if (!live) return;
        if (!isMesh(mesh)) continue;

        if (first) {
          /* Only tear out the primitives once a real layer has actually
             arrived, so a failed fetch leaves a body on screen rather
             than an empty pedestal. */
          for (const { mesh: m } of meshes) body.remove(m);
          for (const p of primitives) body.remove(p);
          meshes.length = 0;
          first = false;
        }

        const group = new THREE.Group();
        group.visible = false;
        for (const { id, geo, bounds: b } of cutUp(mesh)) {
          const bone = id === "skeleton" || id.startsWith("skeleton.");
          /* Bone is scenery on the muscle layer and the subject on the
             skeleton layer, so it is only dimmed where something else
             is meant to be read first. */
          const dim = bone && info.id !== "skeleton";
          const m = new THREE.Mesh(geo, dim ? materials.bone : materials.idle);
          if (!dim) {
            m.userData.region = id;
            bounds.set(`${info.id}/${id}`, b);
          }
          unionLo.min(b.min);
          unionHi.max(b.max);
          if (!centres.has(id)) centres.set(id, b.centre.clone());
          group.add(m);
          geos.push(geo);
        }
        /* Framing comes from the meshes rather than a constant, so a
           taller or shorter atlas still opens fitted to the panel. */
        if (Number.isFinite(unionLo.y)) {
          /* A pair like quad.l / quad.r straddles the midline, so the
             midpoint of each pair sits on it. Averaging the pairs is far
             steadier than any single landmark. */
          const axis = new THREE.Vector3();
          let pairs = 0;
          for (const [id, c] of centres) {
            if (!id.endsWith(".l")) continue;
            const other = centres.get(`${id.slice(0, -2)}.r`);
            if (!other) continue;
            axis.x += (c.x + other.x) / 2;
            axis.z += (c.z + other.z) / 2;
            pairs++;
          }
          const box = unionLo.clone().add(unionHi).multiplyScalar(0.5);
          const centre = pairs
            ? new THREE.Vector3(axis.x / pairs, box.y, axis.z / pairs)
            : box;

          wholeBody = {
            centre,
            radius: Math.max(unionHi.y - unionLo.y, unionHi.x - unionLo.x) / 2,
            min: unionLo.clone(),
            max: unionHi.clone(),
          };
          /* Put the spin axis through the body rather than through
             whatever origin the atlas was modelled around. Off by even
             a few centimetres the figure orbits its own pedestal
             instead of turning on the spot, which reads as the whole
             scene wobbling. */
          body.position.set(-wholeBody.centre.x, -wholeBody.centre.y, -wholeBody.centre.z);
          pivot.position.y = wholeBody.centre.y;
          placeFloor();
        }
        body.add(group);
        layers.set(info.id, group);

        if (mesh.source) {
          credits.set(info.id, mesh.licence ? `${mesh.source} · ${mesh.licence}` : mesh.source);
        }
        /* Re-assert on every arrival: the shown layer may have been
           chosen before its own credit had loaded. */
        const pick2 = wanted.current ?? manifest.default ?? manifest.layers[0].id;
        if (shown === pick2) onCreditRef.current?.(credits.get(pick2) ?? null);
        show(pick2);
      }

      onLayersRef.current?.(
        manifest.layers.filter((l) => layers.has(l.id)),
        manifest.default ?? manifest.layers[0].id,
      );
    })();

    /* ── picking ── */
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    const pickable = () => meshes.map((m) => m.mesh);

    /** the region under the pointer, or null */
    const hitAt = (e: PointerEvent): string | null => {
      const r = renderer.domElement.getBoundingClientRect();
      ndc.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      ndc.y = -((e.clientY - r.top) / r.height) * 2 + 1;
      ray.setFromCamera(ndc, camera);
      const first = ray.intersectObjects(pickable(), false)[0];
      if (!first) return null;
      return meshes.find((m) => m.mesh === first.object)?.id ?? null;
    };

    /* ── input ────────────────────────────────────────────────────
       One pointer turns the body. Two pinch to zoom and slide to pan.
       Shift or the right button pans with one pointer, which is how a
       mouse without a second finger gets at the same thing. */
    let yaw = 0;
    let pitch = 0;
    let spin = 0;           // leftover velocity after a flick
    let idleFor = 0;
    /* Pan, in world units, on top of whatever the framing chose. */
    let panX = 0;
    let panY = 0;
    /* Multiplicative so a notch of wheel feels the same whether framing
       a whole body or one deltoid. */
    let userZoom = 1;

    const pointers = new Map<number, { x: number; y: number }>();
    let mode: "turn" | "pan" | null = null;
    let travel = 0;
    let pinch = 0;          // distance between two pointers, last frame

    const centreOf = () => {
      let x = 0;
      let y = 0;
      for (const p of pointers.values()) { x += p.x; y += p.y; }
      return { x: x / pointers.size, y: y / pointers.size };
    };

    const spreadOf = () => {
      const [a, b] = [...pointers.values()];
      return Math.hypot(a.x - b.x, a.y - b.y);
    };

    let panScale = 0.002;   // refreshed from the camera distance each frame

    const down = (e: PointerEvent) => {
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      idleFor = 0;
      spin = 0;
      if (pointers.size === 1) {
        travel = 0;
        mode = e.shiftKey || e.button === 2 ? "pan" : "turn";
      } else if (pointers.size === 2) {
        mode = "pan";
        pinch = spreadOf();
      }
      renderer.domElement.setPointerCapture(e.pointerId);
      renderer.domElement.style.cursor = mode === "pan" ? "move" : "grabbing";
    };

    const move = (e: PointerEvent) => {
      const prev = pointers.get(e.pointerId);
      if (!prev) return;
      const before = centreOf();
      pointers.set(e.pointerId, { x: e.clientX, y: e.clientY });
      const after = centreOf();
      const dx = after.x - before.x;
      const dy = after.y - before.y;
      travel += Math.abs(e.clientX - prev.x) + Math.abs(e.clientY - prev.y);

      if (pointers.size >= 2) {
        /* Pinch. The ratio is inverted because spreading the fingers
           should bring the body closer, not push it away. */
        const now = spreadOf();
        if (pinch > 0 && now > 0) {
          userZoom = Math.min(2.5, Math.max(0.28, userZoom * (pinch / now)));
        }
        pinch = now;
        panX -= dx * panScale;
        panY += dy * panScale;
        return;
      }

      if (mode === "pan") {
        panX -= dx * panScale;
        panY += dy * panScale;
        return;
      }

      yaw += dx * 0.009;
      spin = dx * 0.009;
      /* Pitch is clamped well short of vertical. Past that the model is
         being looked at from directly above, which tells you nothing
         about which muscle is lit. */
      pitch = Math.max(-0.42, Math.min(0.42, pitch + dy * 0.005));
    };

    const up = (e: PointerEvent) => {
      const was = mode;
      const single = pointers.size === 1;
      pointers.delete(e.pointerId);
      try { renderer.domElement.releasePointerCapture(e.pointerId); } catch { /* already gone */ }
      if (pointers.size < 2) pinch = 0;
      if (pointers.size === 0) {
        mode = null;
        renderer.domElement.style.cursor = "grab";
        /* 4px of slop, because a click from a trackpad is never
           perfectly still. Beyond that it was a drag, not a selection —
           and a pan is never a selection. */
        if (was === "turn" && single && travel < 4) pick.current?.(hitAt(e));
      }
    };

    const menu = (e: Event) => e.preventDefault();   // right-drag pans

    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointermove", move);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("pointercancel", up);
    renderer.domElement.addEventListener("contextmenu", menu);

    /* ── framing ──────────────────────────────────────────────────
       Zooming to a muscle means keeping it centred while the body
       carries on turning, so the target is recomputed every frame from
       the region's position in the *rotated* body rather than solved
       once at the moment of the click. */
    const HALF_FOV = THREE.MathUtils.degToRad(34 / 2);

    /** how far back a sphere of this radius has to be seen from */
    const distanceFor = (radius: number, margin: number) =>
      Math.max(0.42, (radius / Math.sin(HALF_FOV)) * margin);

    const wheel = (e: WheelEvent) => {
      e.preventDefault();
      userZoom = Math.min(2.5, Math.max(0.35, userZoom * (e.deltaY > 0 ? 1.12 : 0.89)));
    };
    renderer.domElement.addEventListener("wheel", wheel, { passive: false });

    const target = new THREE.Vector3(0, 0.9, 0);
    let distance = distanceFor(wholeBody.radius, 1.35);
    const focus = new THREE.Vector3();
    /* What is currently framed. Manual zoom is reset when this changes:
       carried over, a hard zoom into one lat leaves the next selection —
       or the whole body — jammed against the camera. */
    let framing: string | null = null;

    /* ── size ── */
    const resize = () => {
      const w = el.clientWidth || 1;
      const h = el.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    /* ── the loop ── */
    let raf = 0;
    let shownFacing = "";

    const tick = () => {
      raf = requestAnimationFrame(tick);

      if (!mode) {
        /* Carry the flick, then fall back to a slow drift so the back
           of the model is discoverable without being told to drag. */
        if (Math.abs(spin) > 0.0004) {
          yaw += spin;
          spin *= 0.94;
          idleFor = 0;
        } else {
          spin = 0;
          idleFor += 1;
          if (idleFor > 90) yaw += 0.0022;
        }
      }

      pivot.rotation.y = yaw;
      pivot.rotation.x = pitch;

      if (wanted.current && wanted.current !== shown) show(wanted.current);

      /* A muscle if one is selected, otherwise the whole figure. A
         selection on a layer that does not carry that region — the
         skeleton has no biceps — falls back to the body rather than
         framing nothing. */
      const key = shown && picked.current ? `${shown}/${picked.current}` : null;
      if (key !== framing) {
        framing = key;
        userZoom = 1;
        panX = 0;
        panY = 0;
      }
      const frame = (key && bounds.get(key)) || wholeBody;
      const margin = frame === wholeBody ? 1.35 : 2.6;

      /* Into world space through the body's own transform, so the
         framing follows the spin instead of sliding off it. */
      focus.copy(frame.centre);
      body.localToWorld(focus);

      focus.x += panX;
      focus.y += panY;
      target.lerp(focus, 0.12);
      distance += (distanceFor(frame.radius, margin) * userZoom - distance) * 0.12;
      /* A pixel of drag should move the body the same visual amount
         however far away it is, so the pan scale tracks the distance. */
      panScale = (distance * 2 * Math.tan(HALF_FOV)) / Math.max(el.clientHeight, 1);

      camera.position.set(target.x, target.y + frame.radius * 0.15, target.z + distance);
      camera.lookAt(target);

      /* Materials are shared and reassigned, not rebuilt: three of them
         cover the whole body however many regions are lit. */
      const map = tones.current;
      const sel = picked.current;
      for (const { id, mesh } of meshes) {
        const bare = id.split(".")[0];
        /* A sideless mesh lights when either side is active. The skin
           layer carries one `back`, while the muscle layer has back.l
           and back.r — without this a right-side issue would light the
           muscle and leave the skin blank. */
        const eitherSide = id === bare
          ? (map[`${bare}.l`] ?? map[`${bare}.r`])
          : undefined;
        const tone = map[id] ?? map[bare] ?? eitherSide ?? "idle";
        const want = id === sel ? materials.selected : (materials[tone] ?? materials.idle);
        if (mesh.material !== want) mesh.material = want;
      }

      const f = facing(yaw);
      if (f !== shownFacing && label.current) {
        shownFacing = f;
        label.current.textContent = f;
      }

      /* Where the camera is, in words. Written straight to the DOM
         rather than through state: this changes every frame, and a
         re-render per frame would cost more than the whole scene. */
      if (readout.current) {
        const deg = Math.round((((yaw * 180) / Math.PI) % 360 + 360) % 360);
        const tilt = Math.round((pitch * 180) / Math.PI);
        const next =
          `${picked.current ?? "whole body"}  ` +
          `YAW ${String(deg).padStart(3, "0")}°  ` +
          `TILT ${tilt >= 0 ? "+" : "−"}${String(Math.abs(tilt)).padStart(2, "0")}°  ` +
          `X ${panX >= 0 ? "+" : "−"}${Math.abs(panX).toFixed(2)}  ` +
          `Y ${panY >= 0 ? "+" : "−"}${Math.abs(panY).toFixed(2)}  ` +
          `${(1 / userZoom).toFixed(2)}×`;
        if (readout.current.textContent !== next) readout.current.textContent = next;
      }

      renderer.render(scene, camera);
    };
    tick();

    return () => {
      live = false;
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointermove", move);
      renderer.domElement.removeEventListener("pointerup", up);
      renderer.domElement.removeEventListener("pointercancel", up);
      renderer.domElement.removeEventListener("contextmenu", menu);
      renderer.domElement.removeEventListener("wheel", wheel);
      for (const g of geos) g.dispose();
      for (const m of Object.values(materials)) m.dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
    };
  }, []);

  return (
    /* Always absolute, filling whatever positioned ancestor it is
       dropped into. Letting the caller pass positioning meant the
       wrapper carried both `relative` and `absolute`, the two fought,
       and the element collapsed to zero width. */
    <div className={`body3d ${className}`}>
      <div ref={host} className="body3d__host" />
      {/* Both sit right, clear of the issue list the view draws down the
          left of the same area. */}
      <div className="body3d__readout">
        <i ref={readout} className="body3d__where">whole body</i>
        <div className="body3d__hints">
          <i ref={label} className="body3d__facing">FRONT</i>
          <i className="body3d__keys">· DRAG SPIN · SHIFT-DRAG PAN · SCROLL ZOOM</i>
        </div>
      </div>
    </div>
  );
}
