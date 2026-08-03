# Pickup art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

## Shipped now — the rocket launcher and its ammunition

| | |
|---|---|
| **Author** | this project |
| **Licence** | **BSD-3-Clause**, the same terms as the rest of twig-bb (declared in [`pyproject.toml`](../../../pyproject.toml)) |
| **Source** | [`grass-clumps/arsenal.py`](../../../../grass-clumps/arsenal.py) in this workspace |

| File | Used as | Textures |
|---|---|---|
| `javelin-launcher-pickup.glb` | the rocket launcher pickup | its own, baked at 256px |
| `javelin-rocket-pickup.glb` | the rocket ammunition pickup | its own, baked at 256px |
| `sawn-off-shotgun-pickup.glb` | the shotgun pickup | its own, baked at 256px |
| `shotgun-shell-pickup.glb` | the shell pickup | its own, baked at 256px |
| `grenade-launcher-pickup.glb` | the grenade launcher pickup | its own, baked at 256px |
| `grenade-round-pickup.glb` | the grenade pickup | its own, baked at 256px |
| `sniper-rifle-pickup.glb` | the rifle pickup | its own, baked at 256px |
| `sniper-round-pickup.glb` | the rifle ammunition pickup | its own, baked at 256px |
| `handgun-pickup.glb` | the pistol pickup | its own, baked at 256px |
| `handgun-cartridge-pickup.glb` | the bullet pickup | its own, baked at 256px |
| `armour-shard-pickup.glb` | the armour shard pickup | its own, baked at 256px |
| `armour-pickup.glb` | the armour pickup | its own, baked at 256px |
| `body-armour-pickup.glb` | the body armour pickup | its own, baked at 256px |

**A colour per weapon, not per pickup.** Red is the rocket launcher, green the
shotgun, cyan the grenade launcher, lime the sniper and orange the handgun —
and a weapon and its ammunition share one, so what a player learns is five
colours rather than ten. Which of the pair it is comes from the shape floating
inside: the weapon itself, or three of its rounds.

**Armour is gold**, which is the colour the item table has always given it.
The three tiers are one idea at three strengths and are read against each
other: a shard is one plate of carbon fibre, fifty armour is two on a pair of
straps, and a hundred is that carrier again with a pauldron over each shoulder.
How much of the stuff there is, is what it is worth.
The weave is procedural like the wood: a checker deciding which way the tow
runs in each square, which is what a twill *is*, rather than a noise that comes
out dark and shiny.

The same script that builds the weapons builds these: each weapon, and three
of its rounds bundled, shrunk inside a bubble the same one unit across as the
medikit's. Re-running it after an edit is the whole update procedure.

**These say which pickup they are by their shape**, so unlike the medikits they
are not repainted at load time — `twig_bb.items.LAUNCHER_PICKUP` sets
`tinted` false and `twig_bb.art.brighten` gives them the light an unlit map
owes them without the paint. A launcher flattened to one colour would be a
launcher nobody could recognise, which is the only reason to model one.

### The bubbles are one mesh, in ten files

Every one of them is the medikit's lattice to the vertex — 32 by 16, one unit across — and
therefore byte-identical vertex data. The PBR pass batches instances by the
*content* of the geometry rather than by which file it came from, so every
launcher and every box of rockets a map places collapses into a single
instanced draw, and the materials differing by nothing but their colour factor
is exactly what the per-instance material array is for. Changing one bubble
without changing the rest is what would break it, which is why one function
with nothing to vary makes all of them.

### The bubbles are read before they are believed

They are **blended glazes at about a quarter opacity, the way the medikit's
is** — not refracting films — and that is a decision rather than an
approximation. The first version of these was physically modelled: full
`KHR_materials_transmission`, the index of refraction of water, a real Fresnel
rim. It is correct, and it is unusable. A level bakes its lighting and places
no lamps at all, so a bubble that shows what is behind it and reflects the rest
has nothing to show and nothing to reflect, and the pickup reads as a **black
ball** from the far side of a room. The medikit has been a flat tinted shell
since it was made and reads at any distance; the colour has to be *in* the
glaze, not borrowed from the surroundings.

So the index of refraction is 1.12 rather than water's 1.33: just enough for a
faint rim highlight, far too little to reflect a dark room. What rim there is
gets its colour from `KHR_materials_iridescence`, at a single film thickness of
400 nm.

**That extension is written into the `.glb` after Blender has finished with
it.** Blender models the film on its Principled shader but its glTF exporter
has no route from that to the extension — it is commented out of the exporter's
own list — so `add_iridescence` in the build script adds it to the finished
binary. Nothing else in either file is touched by hand.

A real film's belts of colour would need the thickness to vary across the
surface, which needs a thickness map, which needs UVs — and Blender exports no
UV layer for a material that uses no texture. The interference here is
therefore one hue that shifts with the viewing angle. Anyone adding the map
will need to give the bubble a UV set the exporter will keep.

## Shipped now — the medikit

| | |
|---|---|
| **Author** | Mike C. Fletcher, for this project |
| **Licence** | **BSD-3-Clause**, the same terms as the rest of twig-bb (declared in [`pyproject.toml`](../../../pyproject.toml)) |
| **Source** | `grass-clumps/medpack.blend` in this workspace, exported by [`tools/clean_model.py`](../../../tools/clean_model.py) |
| **Modelled** | 2026-07-31 |

| File | Used as | Textures |
|---|---|---|
| `medpack.glb` | all four health pickups | **none** — two untextured materials |

Ours, so there is nothing to check and nothing to fetch. It is credited here
anyway, because the rule above has no exception for art we made: the next
person to read this directory should not have to guess which files carry an
obligation and which do not.

## What it is

A glass bubble with a cross floating inside it, 30 kB, 1008 triangles and no
textures at all — the colour is in the two materials and the shape is in the
mesh. It is authored one unit across and sits on the floor of the scene it was
modelled in; `twig_bb.items.MEDPACK` carries the two numbers that turn that
into a pickup, `modelScale` and `modelOffset`, so nothing here has to be
re-exported to change how big it is drawn or where its middle is.

The file contains a spin animation, which the game does not play:
`twig_bb.game.move_items` turns every pickup on the spot, medikit or box, so
that the ones without art of their own move too. It is kept because it costs
1.5 kB and it is how the model looks in a glTF viewer.

## The four health packs are this model in four colours

`item_health_small`, `item_health`, `item_health_large` and `item_health_mega`
are one mesh painted four ways at load time, from the `colour` field of each
`ItemKind` — one file rather than four, so a fifth is a row in the table and no
new geometry, and so the colour a designer edits is the colour that is drawn
rather than a number that has to be kept in step with a `.glb`.
`twig_bb.art.recolour` moves the base and emissive colours and touches
nothing else: transparency, alpha mode, metallic, roughness and sheen are the
model's own, and are what make the bubble read as glass rather than as paint.

Why those four colours, and why they are far apart in hue rather than in
brightness, is in the docstring of `twig_bb.items.default_table`.

Each also gets a small emissive floor of its own colour
(`twig_bb.game.ITEM_GLOW`), for the reason recorded at length in
[`../weapons/CREDITS.md`](../weapons/CREDITS.md): a map places **no dynamic
lights at all**, so an item in an unlit corner is a black shape, and a light
riding the camera was measured and washes out the baked lighting to fix it.

## How it was prepared

[`tools/clean_model.py`](../../../tools/clean_model.py) is a Blender script; it
edits the `.blend` and exports this file in the same run:

```console
python tools/clean_model.py grass-clumps/medpack.blend \
    --fill-holes --concentric \
    --export twig_bb/assets/items/medpack.glb
```

It found three defects in the source, all of them invisible while modelling and
all of them visible in a game:

| | |
|---|---|
| **A loose quad** | four vertices sharing no edge with the sphere, 2.18 units out at ankle height. Nearly invisible — it is the bubble's transmissive glass — but it orbited the pickup as it spun and it more than doubled the model's bounding box. |
| **Inconsistent winding** | 12 shared edges on the bubble and 14 on the cross were traversed the same way by both their faces, so those faces were lit from behind. |
| **A hole** | five boundary edges at the end of one arm of the cross. This is the one that looks like a *fourth* defect and is not: an unclosed surface shows the inside of its far wall through the gap, which Blender's face-orientation overlay paints as the inside colour and which reads exactly like one last reversed face. |

`--concentric` is the fix for a wobble rather than for a defect: the cross was
modelled 18 mm off the centre of the bubble, so it turned about its own origin
instead of the sphere's. Both meshes now have their origin on the sphere's
centre, and the animation's location keys were retargeted with them.

Afterwards both meshes are closed manifolds, with no non-manifold edges, no
face pointing inward, and positive signed volume — which is what "the normals
face outward" means when it is measured rather than looked at.

## Why this may be committed at all

It is ours and it is BSD, so it carries no obligation onto anyone who
redistributes twig-bb. The test for anything added here later is the one in
[`../weapons/CREDITS.md`](../weapons/CREDITS.md): **CC0, BSD or an equivalently
unconditional licence may be committed; anything share-alike must be fetched**
to a user cache at the user's request, the way the OpenArena content is. Either
way it is credited here with a link.
