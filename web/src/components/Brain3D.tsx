import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { layout, radiusOf, type Placed } from "../lib/graph";
import { newSim, step, sync, type Body } from "../lib/sim";
import { EXTENT } from "../lib/brain";
import type { MindSnapshot } from "../lib/mind";

/* PORTED from Selene (`src/components/Brain3D.tsx`), Owen's own component.
   Kept in sync rather than rewritten for the same reason Body3D is: its
   geometry was debugged against problems that are invisible in the output.

   THREE ADAPTATIONS, and each one is here because of a rule this project
   already had:

   1. **Tailwind.** Selene styles this component with it and Isabella has no
      Tailwind, so `absolute inset-0` was an inert string, the host div
      collapsed to zero height and the canvas was sized 1x1. The class name at
      the bottom is Isabella's own, in styles.css. Body3D hit this exact wall.
   2. **Three kinds, not three tiers.** Selene draws core/entity/atomic
      memories; this draws memory/session/message (see lib/mind.ts). They are
      told apart by VALUE, not by hue — silver, grey, faint — because violet
      marks what is LIVE and nothing else, which is the one colour rule the
      design system does not bend. A second hue here would say "this is
      happening" about a conversation from Tuesday.
   3. **`importance` may be null.** It is a property of a memory, not of a
      conversation, and the readout says "unrated" rather than "null/10" or,
      worse, "0/10".

   Everything below this line is Selene's, including the reasoning. --------

   The memory graph as a brain, in three dimensions.

   Every memory is a node placed in the volume in brain.ts — core down
   the stem, entities over the cortex, atomic memories beside the entity
   they name — and every wikilink is a line between two of them. Turning
   it is how you read it: a graph seen from one angle is a diagram, and
   the thing that makes this look like a mind rather than a chart is
   watching the far hemisphere come round.

   What it MEANS is unchanged from the flat version it replaced, because
   the rules were never about the geometry:

     · violet is what is in the prompt, graded by hop — named reads
       loudest, traversed reads quietest. Flat violet across everything
       recalled makes the whole graph look live, which is the failure
       this is built to avoid
     · a hollow outline is a memory she is not confident about
     · a node throws ONE ring at the moment it enters context. Recall is
       an event; a permanent halo would say "this is recalled" where
       this says "this just got recalled"
     · a name appears because she is reading that memory, and the brain
       is quiet the rest of the time

   Built on three directly, the same way Body3D is — there is no
   react-three-fiber in this project and this is not the change that
   should add one. Several of the patterns here are lifted from that
   file because each of them fixed a real bug; they are noted where they
   appear. */

const VIOLET = new THREE.Color("#B28BFF");
/* The grey ladder, from the design system's own steps. What separates the
   three kinds is VALUE, not hue — a memory she has kept reads brightest, a
   conversation sits below it, a single message is the faintest thing in the
   volume. That ordering is also the ordering of how long each one lasts. */
const MEMORY = new THREE.Color("#D1D1D1");
const SESSION = new THREE.Color("#8A8A95");
const FAINT = new THREE.Color("#6E6E79");
/* Lighter than the #3A3A44 the flat version used. There, an edge was a
   line on an empty ground; here it is seen through a translucent shell,
   and at that value it simply disappeared into it. */
const EDGE = new THREE.Color("#57576A");

/** The camera sits far enough back that the whole volume is in frame. */
const DISTANCE = EXTENT * 3.05;

/** How long a recall ring takes to travel out and fade. Matches the
    1100ms the flat version used — it was tuned to be visible without
    lingering into the next turn. */
const RIPPLE_MS = 1100;

/** No more rings in flight at once than this. */
const RIPPLES = 12;

const colourOf = (n: Placed) =>
  n.hop !== undefined ? VIOLET
  : n.kind === "memory" ? MEMORY
  : n.kind === "session" ? SESSION
  : FAINT;

const opacityOf = (n: Placed) =>
  n.hop !== undefined
    ? (n.hop === 0 ? 1 : n.hop === 1 ? 0.68 : 0.42)
    : n.kind === "message" ? 0.5
    : n.kind === "session" ? 0.72
    : 0.88;

export function Brain3D({
  snap,
  phase,
  onCredit,
  className = "",
}: {
  snap: MindSnapshot;
  /** what the core is doing, which is how far the camera leans in */
  phase: "idle" | "hearing" | "thinking";
  /* The mesh carries its own attribution. Z-Anatomy is CC BY-SA, which
     requires the credit be visible rather than buried in a README — so
     the mesh reports it and the view prints it. */
  onCredit?: (credit: string | null) => void;
  className?: string;
}) {
  const host = useRef<HTMLDivElement>(null);
  const creditRef = useRef(onCredit);
  creditRef.current = onCredit;

  /* The seed layout. Recomputed only when the snapshot changes; the
     simulation moves nodes off it every frame but is anchored back to
     it, so this is the thing the space is learnable by. */
  const seed = useMemo(() => layout(snap), [snap]);

  /* Live data reaches the scene through refs. The scene, its meshes and
     the WebGL context are built once — rebuilding them whenever a turn
     lands would drop the context and restart the motion. */
  const seedRef = useRef(seed);
  seedRef.current = seed;
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  useEffect(() => {
    const el = host.current;
    if (!el) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(38, 1, 0.05, 40);

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

    /* Absolute, for the reason spelled out in Body3D: left in flow, the
       canvas's intrinsic size grows the element that is measured to
       size it, and it walks itself off the screen over a few seconds. */
    Object.assign(renderer.domElement.style, {
      position: "absolute",
      inset: "0",
      width: "100%",
      height: "100%",
      display: "block",
      touchAction: "none",
      cursor: "grab",
    });

    scene.add(new THREE.HemisphereLight(0xb4b4d0, 0x14141c, 2.1));
    const key = new THREE.DirectionalLight(0xffffff, 1.1);
    key.position.set(1.6, 2.4, 3);
    scene.add(key);
    /* a violet rim from behind, so the far hemisphere still reads when
       it is turned away from the camera */
    const rim = new THREE.DirectionalLight(0xb28bff, 1.2);
    rim.position.set(-2, 1, -2.6);
    scene.add(rim);

    /* Everything turns together. */
    const pivot = new THREE.Group();
    scene.add(pivot);

    /* ── the brain ──

       The real thing: Z-Anatomy's cerebrum, cerebellum and brainstem,
       decimated by scripts/zbrain.py into the same normalised units
       brain.ts places nodes in, so a node laid on the analytic cortex
       lands on the surface of this mesh rather than floating inside it.

       This replaced a point cloud that approximated the surface with a
       few thousand dots. That was there because two dozen memories
       cannot describe a shape on their own, and it worked — but an
       approximation of a brain is no longer worth carrying when the
       brain itself is 1.6MB.

       Drawn as a translucent shell so the memories inside it read
       through: `depthWrite: false` and a high `renderOrder` keep it
       from occluding the nodes, which are opaque and drawn first.
       Without both, the shell writes depth over the far hemisphere's
       nodes and they vanish as the volume turns. */
    const geos: THREE.BufferGeometry[] = [];

    /* FrontSide, and faint.

       The atlas ships the lobes as separate solids that overlap each
       other, so every ray through the head crosses many surfaces and
       the transparency accumulates. At DoubleSide and 0.16 that stacked
       into an opaque milky blob with the memories lost inside it —
       culling back faces halves the crossings, and the low opacity is
       what lets the far hemisphere's nodes read through the near one. */
    const shellMat = new THREE.MeshStandardMaterial({
      color: 0x9c9cb8, roughness: 0.6, metalness: 0.04,
      transparent: true, opacity: 0.095, depthWrite: false,
      side: THREE.FrontSide,
      emissive: 0x3a3a55, emissiveIntensity: 0.25,
    });

    let brainMesh: THREE.Mesh | null = null;
    let live = true;

    (async () => {
      try {
        const r = await fetch("/anatomy/brain.json");
        if (!r.ok) throw new Error(String(r.status));
        const data: {
          positions: number[];
          regions: Record<string, number[]>;
          source?: string;
          licence?: string;
        } = await r.json();
        /* Unmounted while the fetch was in flight — StrictMode does
           exactly this on every mount. Building the mesh now would add
           it to a scene that has already been disposed. */
        if (!live) return;

        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.Float32BufferAttribute(data.positions, 3));
        geo.setIndex(Object.values(data.regions).flat());
        geo.computeVertexNormals();
        geos.push(geo);

        brainMesh = new THREE.Mesh(geo, shellMat);
        brainMesh.renderOrder = 10;
        brainMesh.frustumCulled = false;
        pivot.add(brainMesh);

        /* Z-Anatomy is CC BY-SA: the credit has to be visible, not
           buried in a README, so the mesh reports it and the view
           prints it. */
        creditRef.current?.(
          data.licence ? `${data.source} · ${data.licence}` : data.source ?? null,
        );
      } catch {
        /* No mesh is survivable — the nodes and their edges are the
           subject, and brain.ts still places them in the same volume.
           A silhouette missing is worse-looking, not broken. */
      }
    })();


    const ball = new THREE.SphereGeometry(1, 14, 10);
    const cage = new THREE.SphereGeometry(1, 8, 6);
    geos.push(ball, cage);

    /* Opaque, both of them. The flat version graded a node by SVG
       opacity; here the grade is baked into the instance colour
       instead — on a ground this dark, dimmer and more transparent are
       the same read, and it avoids sixty transparent spheres that have
       to be depth-sorted against each other every frame. */
    const solidMat = new THREE.MeshStandardMaterial({
      roughness: 0.38, metalness: 0.05,
      /* The nodes are the subject and they are seen THROUGH the shell,
         so they carry more of their own light than they would on an
         empty ground. */
      emissive: 0xffffff, emissiveIntensity: 0.42,
    });
    const cageMat = new THREE.MeshBasicMaterial({ wireframe: true });

    const MAX = 256; // comfortably over MAX_NODES; instances are cheap
    const solid = new THREE.InstancedMesh(ball, solidMat, MAX);
    const hollow = new THREE.InstancedMesh(cage, cageMat, MAX);
    for (const m of [solid, hollow]) {
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.frustumCulled = false;
      pivot.add(m);
    }
    solid.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(MAX * 3), 3);
    hollow.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(MAX * 3), 3);

    /* ── edges ──

       One LineSegments over a buffer rewritten each frame. A line per
       edge would be a draw call per relation. */
    const EMAX = 2048;
    const edgeGeo = new THREE.BufferGeometry();
    const edgePos = new Float32Array(EMAX * 6);
    const edgeCol = new Float32Array(EMAX * 6);
    edgeGeo.setAttribute("position", new THREE.BufferAttribute(edgePos, 3));
    edgeGeo.setAttribute("color", new THREE.BufferAttribute(edgeCol, 3));
    geos.push(edgeGeo);
    const edgeMat = new THREE.LineBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.85, depthWrite: false,
    });
    const lines = new THREE.LineSegments(edgeGeo, edgeMat);
    lines.frustumCulled = false;
    pivot.add(lines);

    /* ── the recall ring ──

       Billboarded rings, one per node that has just entered context.
       Kept as a small fixed pool: at most a budget's worth can fire at
       once, and allocating geometry inside the loop is how you get a
       stutter exactly when she answers. */
    const ringGeo = new THREE.RingGeometry(0.92, 1, 40);
    geos.push(ringGeo);
    const ringMat = new THREE.MeshBasicMaterial({
      color: VIOLET, transparent: true, opacity: 0, side: THREE.DoubleSide, depthWrite: false,
    });
    const rings = Array.from({ length: RIPPLES }, () => {
      const m = new THREE.Mesh(ringGeo, ringMat.clone());
      m.visible = false;
      m.frustumCulled = false;
      pivot.add(m);
      return m;
    });

    /* ── labels ──

       A DOM layer this component owns, positioned by projecting each
       node and writing transforms straight onto the elements. Lifting
       projected positions into React state would be a re-render of the
       whole HUD every frame — the exact cost the simulation was moved
       in here to avoid. */
    const labelLayer = document.createElement("div");
    Object.assign(labelLayer.style, {
      position: "absolute", inset: "0", pointerEvents: "none", overflow: "hidden",
    });
    el.appendChild(labelLayer);
    const labels = new Map<string, HTMLElement>();

    /* ── the hover readout ──

       Point at a memory and it says what it is. The body view does this
       on CLICK, because there a click also frames the muscle and the
       readout is the second half of a deliberate act. Here there is
       nothing to select — the graph is a thing you sweep your eye over —
       so hover is the whole interaction and a click would be a gate in
       front of a glance.

       Same DOM-layer trick as the labels: written to directly, never
       through React, so moving the pointer does not re-render the HUD. */
    const tip = document.createElement("div");
    Object.assign(tip.style, {
      position: "absolute", top: "0", left: "0", maxWidth: "260px",
      padding: "7px 9px", pointerEvents: "none", display: "none",
      background: "#16161C", border: "1px solid #31313A",
      fontFamily: "var(--mono)", lineHeight: "1.5",
      /* above the SVG frame, which is drawn over this canvas */
      zIndex: "40",
    });
    el.appendChild(tip);

    /* Where the pointer is, in normalised device coords. Stored on move
       and consumed once per frame — raycasting inside the event handler
       would run several times per frame on a fast mouse for a result
       that can only be drawn once. */
    const ray = new THREE.Raycaster();
    const ndc = new THREE.Vector2();
    let pointerIn = false;
    let hoverId: string | null = null;
    /* instance slot → index into `placed`. The draw loop packs confident
       and uncertain nodes into two separate meshes, so a raycast hit
       gives an instanceId that means nothing without this. */
    const solidAt: number[] = [];
    const hollowAt: number[] = [];
    /* reused every frame — this is per-frame work, not per-frame garbage */
    const placements: {
      id: string; x: number; y: number; hop: 0 | 1 | 2; behind: boolean; text: string;
    }[] = [];

    const labelFor = (id: string) => {
      let node = labels.get(id);
      if (!node) {
        node = document.createElement("i");
        Object.assign(node.style, {
          position: "absolute", top: "0", left: "0", whiteSpace: "nowrap",
          fontFamily: "var(--mono)", fontStyle: "normal", letterSpacing: ".03em",
          paintOrder: "stroke", pointerEvents: "none",
          textShadow: "0 0 3px #16161C, 0 0 3px #16161C, 0 0 3px #16161C",
        });
        labelLayer.appendChild(node);
        labels.set(id, node);
      }
      return node;
    };

    /* ── the simulation ── */
    const sim = newSim();
    /* Scratch objects, hoisted. Allocating a Vector3 per node per frame
       is how a scene that runs fine for a minute starts hitching. */
    const dummy = new THREE.Object3D();
    const world = new THREE.Vector3();
    const colour = new THREE.Color();
    const facing = new THREE.Quaternion();

    /* ── turning it ──

       Drag to spin, and a slow drift when nobody has. Straight from
       Body3D: the flick carries, decays, and then the idle rotation
       takes over so the back of the volume is discoverable without
       anyone being told to drag. */
    /* Opens on a three-quarter view from the front left, tipped slightly
       down. A brain is least recognisable head-on — that view is a
       rounded blob — and most recognisable in profile, where the length,
       the flat crown and the cerebellum tucked under the back are all
       visible at once. This is a compromise between the two, so the
       fissure down the midline is in shot as well. */
    let yaw = -1.02, pitch = -0.2;
    let spin = 0, idleFor = 0;
    let dragging = false;
    let lastX = 0, lastY = 0;
    let tipX = 0, tipY = 0;

    const down = (e: PointerEvent) => {
      dragging = true; lastX = e.clientX; lastY = e.clientY; spin = 0;
      renderer.domElement.setPointerCapture(e.pointerId);
      renderer.domElement.style.cursor = "grabbing";
    };
    const move = (e: PointerEvent) => {
      /* Track the pointer whether or not a drag is in progress — the
         hover readout needs it, and the early return below is for the
         turning, not for the pointer. */
      const box = renderer.domElement.getBoundingClientRect();
      ndc.x = ((e.clientX - box.left) / box.width) * 2 - 1;
      ndc.y = -((e.clientY - box.top) / box.height) * 2 + 1;
      tipX = e.clientX - box.left;
      tipY = e.clientY - box.top;
      pointerIn = true;

      if (!dragging) return;
      const dx = e.clientX - lastX, dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      yaw += dx * 0.006;
      pitch = Math.max(-0.85, Math.min(0.85, pitch + dy * 0.005));
      spin = dx * 0.006;
      idleFor = 0;
    };
    const up = (e: PointerEvent) => {
      dragging = false;
      renderer.domElement.style.cursor = "grab";
      if (renderer.domElement.hasPointerCapture(e.pointerId))
        renderer.domElement.releasePointerCapture(e.pointerId);
    };
    renderer.domElement.addEventListener("pointerdown", down);
    renderer.domElement.addEventListener("pointermove", move);
    renderer.domElement.addEventListener("pointerup", up);
    renderer.domElement.addEventListener("pointercancel", up);
    const leave = () => { pointerIn = false; };
    renderer.domElement.addEventListener("pointerleave", leave);

    /* Motion is a preference, and a thing that never stops moving is a
       problem for some people. Read live rather than at mount so
       changing the system setting takes effect without a reload. */
    const stillQ = window.matchMedia("(prefers-reduced-motion: reduce)");

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
    let drift = 0;
    /* The last layout this scene reconciled against, by identity. `seed`
       is memoised on the snapshot, so a new object means new memories —
       and a phase change, which re-renders this component to move the
       camera, does not.

       It has to live INSIDE the effect. Held in a ref it outlived the
       scene, and under StrictMode — which mounts, tears down and mounts
       again — the second scene found the marker already set by the
       first, never synced, and drew an empty volume. */
    let applied: typeof seedRef.current | null = null;

    const tick = () => {
      raf = requestAnimationFrame(tick);
      const still = stillQ.matches;
      const now = Date.now();

      /* Reconcile only when the layout actually changed. */
      if (applied !== seedRef.current) {
        applied = seedRef.current;
        sync(sim, seedRef.current.placed, seedRef.current.edges, now);
      }

      if (!still) {
        drift += 0.011;
        step(sim.live, sim.links, drift);
      }

      /* the camera pulls in a little while she is working — the same
         "leaning in" the HUD wrapper does, but from the inside, so the
         volume grows rather than the whole instrument panel */
      const near = phaseRef.current === "thinking" ? 0.94 : phaseRef.current === "hearing" ? 0.97 : 1;
      camera.position.set(0, 0.08, DISTANCE * near);
      camera.lookAt(0, -0.04, 0);

      if (!dragging && !still) {
        if (Math.abs(spin) > 0.0004) {
          yaw += spin; spin *= 0.94; idleFor = 0;
        } else {
          spin = 0; idleFor += 1;
          if (idleFor > 60) yaw += 0.0016;
        }
      }
      pivot.rotation.set(pitch, yaw, 0);
      pivot.updateMatrixWorld();

      /* ── draw the nodes ── */
      const live = sim.live;
      const placed = seedRef.current.placed;
      const n = Math.min(live.length, MAX);
      let nSolid = 0, nHollow = 0;

      for (let i = 0; i < n; i++) {
        const b = live[i];
        const p = placed[i];
        const r = radiusOf(p);
        dummy.position.set(b.x, b.y, b.z);
        dummy.scale.setScalar(r);
        dummy.updateMatrix();

        const low = p.confidence < 0.6;
        const target = low ? hollow : solid;
        const slot = low ? nHollow++ : nSolid++;
        (low ? hollowAt : solidAt)[slot] = i;
        target.setMatrixAt(slot, dummy.matrix);

        colour.copy(colourOf(p)).multiplyScalar(opacityOf(p));
        target.instanceColor!.setXYZ(slot, colour.r, colour.g, colour.b);
      }
      solid.count = nSolid;
      hollow.count = nHollow;
      solid.instanceMatrix.needsUpdate = true;
      hollow.instanceMatrix.needsUpdate = true;
      solid.instanceColor!.needsUpdate = true;
      hollow.instanceColor!.needsUpdate = true;

      /* ── the hover readout ──

         Raycast against the node meshes only. The brain shell is not in
         this list, so pointing at the surface reaches the memory behind
         it rather than being swallowed by 51k triangles of cortex — and
         a drag is a turn, not a query, so the readout hides while one
         is in progress. */
      if (pointerIn && !dragging) {
        ray.setFromCamera(ndc, camera);
        const hit = ray.intersectObjects([solid, hollow], false)[0];
        const idx = hit && hit.instanceId !== undefined
          ? (hit.object === solid ? solidAt : hollowAt)[hit.instanceId]
          : undefined;
        const node = idx === undefined ? undefined : placed[idx];

        if (node) {
          renderer.domElement.style.cursor = dragging ? "grabbing" : "pointer";
          /* Rebuild the contents only when the node under the pointer
             changes; the position still follows every frame. */
          if (node.id !== hoverId) {
            hoverId = node.id;
            const live = node.hop !== undefined;
            const state = live
              ? `IN CONTEXT · ${node.hop} HOP${node.hop === 1 ? "" : "S"}`
              : "KNOWN";
            const conf = node.confidence < 0.6 ? " · UNCERTAIN" : "";
            tip.innerHTML = "";

            const name = document.createElement("div");
            name.textContent = node.title;
            Object.assign(name.style, {
              fontSize: "10.5px", color: live ? "#B28BFF" : "#D1D1D1",
              marginBottom: "3px", letterSpacing: ".02em",
            });
            tip.appendChild(name);

            const meta = document.createElement("div");
            /* `measure` is whatever real quantity this kind actually has —
               "8/10" for a rated memory, "unrated" for one without, "12 msg"
               for a session, "assistant" for a message. Printing
               `${node.importance}/10` here would read "null/10" for two of
               the three kinds. */
            meta.textContent =
              `${node.kind.toUpperCase()} · ${node.measure} · ${state}${conf}`;
            Object.assign(meta.style, {
              fontSize: "8px", letterSpacing: ".12em", color: "#6E6E79",
              marginBottom: node.excerpt ? "5px" : "0",
            });
            tip.appendChild(meta);

            if (node.excerpt) {
              const body = document.createElement("p");
              body.textContent = node.excerpt;
              Object.assign(body.style, {
                margin: "0", fontFamily: "var(--sans)",
                fontSize: "11px", lineHeight: "1.45", color: "#9A9AA5",
              });
              tip.appendChild(body);
            }
          }
          /* Flip to the other side of the pointer near the right or
             bottom edge, so the readout never runs off the panel. */
          const w = el.clientWidth, h = el.clientHeight;
          const tw = tip.offsetWidth || 240, th = tip.offsetHeight || 60;
          const left = tipX + 14 + tw > w ? tipX - 14 - tw : tipX + 14;
          const top = tipY + 12 + th > h ? tipY - 12 - th : tipY + 12;
          tip.style.transform = `translate(${left.toFixed(0)}px, ${top.toFixed(0)}px)`;
          tip.style.display = "block";
        } else {
          hoverId = null;
          tip.style.display = "none";
          renderer.domElement.style.cursor = dragging ? "grabbing" : "grab";
        }
      } else if (tip.style.display !== "none") {
        hoverId = null;
        tip.style.display = "none";
      }

      /* ── draw the edges ──

         Violet only where BOTH ends are in the prompt. One end lit is a
         relation she did not traverse, and colouring it says she did. */
      const byId = new Map<string, Body>();
      for (const b of live) byId.set(b.id, b);
      const edges = seedRef.current.edges;
      let e = 0;
      for (const [a, c] of edges) {
        if (e >= EMAX) break;
        const ba = byId.get(a.id), bc = byId.get(c.id);
        if (!ba || !bc) continue;
        const hot = (a.hop ?? 9) <= 1 && (c.hop ?? 9) <= 1;
        const col = hot ? VIOLET : EDGE;
        const k = e * 6;
        edgePos[k] = ba.x; edgePos[k + 1] = ba.y; edgePos[k + 2] = ba.z;
        edgePos[k + 3] = bc.x; edgePos[k + 4] = bc.y; edgePos[k + 5] = bc.z;
        const s = hot ? 1 : 0.75;
        for (const o of [0, 3]) {
          edgeCol[k + o] = col.r * s;
          edgeCol[k + o + 1] = col.g * s;
          edgeCol[k + o + 2] = col.b * s;
        }
        e++;
      }
      edgeGeo.setDrawRange(0, e * 2);
      edgeGeo.attributes.position.needsUpdate = true;
      edgeGeo.attributes.color.needsUpdate = true;

      /* ── the rings ── */
      let ring = 0;
      for (let i = 0; i < n && ring < RIPPLES; i++) {
        const b = live[i];
        if (b.firedAt === undefined) continue;
        const t = (now - b.firedAt) / RIPPLE_MS;
        if (t < 0 || t > 1) continue;
        const m = rings[ring++];
        m.visible = true;
        m.position.set(b.x, b.y, b.z);
        m.scale.setScalar(radiusOf(placed[i]) + 0.02 + t * 0.2);
        /* face the camera through the pivot's own rotation, so a ring
           does not turn edge-on and vanish as the brain comes round */
        m.quaternion.copy(camera.quaternion).premultiply(facing.copy(pivot.quaternion).invert());
        (m.material as THREE.MeshBasicMaterial).opacity = 0.7 * (1 - t);
      }
      for (let i = ring; i < RIPPLES; i++) rings[i].visible = false;

      /* ── the labels ──

          Only for what is actually in use.

          Core memories used to be labelled unconditionally, on the
          reasoning that they are the frame you navigate by. In practice
          that meant a permanent ring of names sitting over an idle
          graph, which is the same failure as a screen that is mostly
          violet: if a name is always there, its being there stops
          meaning anything. A name appears because she is reading that
          memory, and the brain is quiet the rest of the time. */
      const w = el.clientWidth, h = el.clientHeight;
      const seen = new Set<string>();
      placements.length = 0;

      for (let i = 0; i < n; i++) {
        const p = placed[i];
        if ((p.hop ?? 9) > 1) continue;
        const b = live[i];
        seen.add(p.id);
        world.set(b.x, b.y, b.z).applyMatrix4(pivot.matrixWorld);
        /* how far behind the volume's own centre it sits, for the fade */
        const depth = world.distanceTo(camera.position);
        world.project(camera);
        placements.push({
          id: p.id,
          x: (world.x * 0.5 + 0.5) * w,
          y: (-world.y * 0.5 + 0.5) * h,
          hop: p.hop!,
          behind: depth > DISTANCE,
          text: p.title.length > 34 ? p.title.slice(0, 32) + "…" : p.title,
        });
      }

      /* Nudge names apart.

         Memories cluster — that is the point of the layout — and where
         four of them sit on the same fold their names land on the same
         few pixels and none of the four can be read. The flat version
         never had to solve this because its nodes were spread around a
         ring by construction.

         Nudging rather than hiding: a name is on screen because she is
         reading that memory, and dropping it would be the screen
         quietly under-reporting what is in the prompt. Nearest first,
         so the ones in front keep their true position and the ones
         behind give way. */
      placements.sort((a, b) => a.y - b.y);
      for (let i = 0; i < placements.length; i++) {
        const it = placements[i];
        for (let j = 0; j < i; j++) {
          const other = placements[j];
          if (Math.abs(other.x - it.x) < 74 && it.y - other.y < 9) it.y = other.y + 9;
        }
      }

      for (const it of placements) {
        const node = labelFor(it.id);
        /* left of the node on the left of the frame, right on the right
           — so a name grows away from the volume rather than across it */
        const left = it.x < w / 2;
        node.textContent = it.text;
        node.style.textAlign = left ? "right" : "left";
        node.style.transform =
          `translate(${(left ? it.x - 8 : it.x + 8).toFixed(1)}px, ${(it.y - 4).toFixed(1)}px)` +
          (left ? " translateX(-100%)" : "");
        node.style.fontSize = it.hop === 0 ? "7.6px" : "7px";
        node.style.color = it.hop === 0 ? "#D1D1D1" : "#8A8A95";
        /* a name on the far side of the volume reads as belonging to
           whatever node happens to be in front of it */
        node.style.opacity = it.behind ? "0.3" : "1";
      }

      for (const [id, node] of labels) {
        if (!seen.has(id)) { node.remove(); labels.delete(id); }
      }

      renderer.render(scene, camera);
    };
    tick();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      renderer.domElement.removeEventListener("pointerdown", down);
      renderer.domElement.removeEventListener("pointermove", move);
      renderer.domElement.removeEventListener("pointerup", up);
      renderer.domElement.removeEventListener("pointercancel", up);
      renderer.domElement.removeEventListener("pointerleave", leave);
      for (const g of geos) g.dispose();
      live = false;
      shellMat.dispose();
      solidMat.dispose();
      cageMat.dispose();
      edgeMat.dispose();
      ringMat.dispose();
      for (const m of rings) (m.material as THREE.Material).dispose();
      renderer.dispose();
      el.removeChild(renderer.domElement);
      labelLayer.remove();
      tip.remove();
    };
  }, []);

  // `.brain3d__host` is `position:absolute; inset:0` in styles.css. It is not
  // decoration: the canvas is sized from this div's clientHeight, so a host
  // with no height renders a 1x1 canvas and nothing appears.
  return <div ref={host} className={`brain3d__host ${className}`} />;
}
