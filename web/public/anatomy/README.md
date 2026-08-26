# The body, in three layers

The 3D body renders one of three layers — **skin → muscle → skeleton** —
switchable in the view. They are generated, not hand-made, and they all
stand in one shared coordinate frame so switching between them does not
make the figure jump.

    index.json      which layers exist, and which one opens by default
    skin.json       683 KB   26,756 tris   MakeHuman        CC0
    muscle.json     3.1 MB  100,597 tris   Z-Anatomy        CC BY-SA 4.0
    skeleton.json   1.4 MB   46,972 tris   Z-Anatomy        CC BY-SA 4.0

With no `index.json` the view falls back to built-in primitives and
still works.

## Controls

    drag                 turn
    shift-drag           pan
    right-drag           pan
    two fingers          pan and pinch to zoom
    scroll               zoom
    click a muscle       select it and frame it
    click empty space    deselect and pull back

A readout in the corner prints what is framed, the yaw and tilt, the pan
offset and the zoom factor, so it is always possible to tell where the
camera is rather than having to guess from the picture.

## Zooming

Click a muscle and the camera frames it; click empty space to pull back
to the whole figure. Scroll adjusts on top of whatever the framing
chose, and resets when the selection changes — carried over, a hard
zoom into one lat leaves the next selection jammed against the camera.

The framing target is recomputed every frame from the region's position
in the *rotated* body, not solved once at the moment of the click, so a
zoomed-in muscle stays centred while the body carries on turning.

Region bounds are computed from each region's index. Three's
`computeBoundingSphere()` is no use here: every region shares one
position attribute and that method walks the whole attribute ignoring
the index, so each muscle would report the bounds of the entire body.

## Standing on the axis

The figure is centred on the spin axis using the **midline of its
left/right region pairs** — `quad.l` and `quad.r` straddle the midline,
so the midpoint of each pair sits on it, and averaging the pairs is
steadier than any single landmark. The bounding box will not do: the
arms hang asymmetrically, which drags the box centre off the spine.

Three things had to be true at once for the body to stop orbiting its
own pedestal:

- The offset is computed from the **union of all layers**, because
  `body.position` is one transform shared by all three. Computed per
  layer, whichever loaded last won — the skeleton's centre was placing
  the figure while the muscle layer was on screen.
- The pedestal hangs off the **pivot**, not the body, so it does not
  ride the centring offset.
- The canvas fills the centre column exactly. Sized by content it came
  out 837px wide inside a 720px column and hung past it, which put the
  projection centre off the panel centre.

## The shared frame

`scripts/zanatomy.py` measures the frame across the muscles *and* the
skeleton — the skeleton is what reaches the crown of the skull and the
soles of the feet, while the muscle mass stops short at both ends and
would otherwise put the floor through the ankles. It prints the height
it measured (currently **1.73836 m**), and the skin is fitted to
exactly that.

**Regenerate all three together.** Rebuilding one on its own with a
different height is how the layers drift apart.

## Licences differ per layer, and the credit follows what is on screen

The skin is **CC0** and owes nothing. The muscle and skeleton layers are
**CC BY-SA 4.0**, which requires a visible credit and imposes
share-alike on anything distributed onward.

So attribution is per layer, not per project: each file carries its own
`source` and `licence`, and the status strip prints whichever layer is
currently visible. Reporting whichever loaded first credited MakeHuman
while Z-Anatomy was on screen, which is exactly the failure the licence
is about.

## Regenerating

**Muscle and skeleton** need **Blender 3.6** — Z-Anatomy is reported
incompatible with 4.5 and Homebrew ships 5.x, so the version matters:

    https://download.blender.org/release/Blender3.6/blender-3.6.23-macos-arm64.dmg

plus `Z-Anatomy.zip` (83 MB) from
<https://github.com/Z-Anatomy/Models-of-human-anatomy>, which unzips to
a 293 MB `Startup.blend`. Then, headless:

    blender -b Startup.blend --python scripts/zanatomy.py -- public/anatomy 95000

It selects the ~677 named muscle bodies down to the fifteen groups the
dashboard names, decimates each to a share of the budget, and writes
both layers. Note the height it prints.

**Skin** comes from MakeHuman (`base.obj` + `caucasian-male-young.target`,
both CC0), segmented by its own joint locators:

    node scripts/basemesh.mjs base.obj public/anatomy/skin.json male.target 1.73836

## Why the skin is MakeHuman and not Z-Anatomy

Z-Anatomy has no skin. Its 123 "surface of…" objects are surfaces of
organs and bones, and "9: Regions of human body" is label geometry.

## Why the skeleton is also carried on the muscle layer

Muscles alone stop at the neck and the wrists, which reads as a body
with its head cut off. On the muscle layer the bones are dimmed
scenery — never lit, never clickable, because they are not regions the
program has an opinion on. On the skeleton layer they are the subject
and get the whole budget.

The joints are the exception: knee and elbow are regions an issue can
be logged against but which no muscle can ever light, so they come from
bone and stay clickable.
