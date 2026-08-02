# Pickup art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

## Shipped now — the medikit

| | |
|---|---|
| **Author** | Mike C. Fletcher, for this project |
| **Licence** | **BSD-3-Clause**, the same terms as the rest of twitch (declared in [`pyproject.toml`](../../../pyproject.toml)) |
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
modelled in; `twitchoglc.items.MEDPACK` carries the two numbers that turn that
into a pickup, `modelScale` and `modelOffset`, so nothing here has to be
re-exported to change how big it is drawn or where its middle is.

The file contains a spin animation, which the game does not play:
`twitchoglc.game.move_items` turns every pickup on the spot, medikit or box, so
that the ones without art of their own move too. It is kept because it costs
1.5 kB and it is how the model looks in a glTF viewer.

## The four health packs are this model in four colours

`item_health_small`, `item_health`, `item_health_large` and `item_health_mega`
are one mesh painted four ways at load time, from the `colour` field of each
`ItemKind` — one file rather than four, so a fifth is a row in the table and no
new geometry, and so the colour a designer edits is the colour that is drawn
rather than a number that has to be kept in step with a `.glb`.
`twitchoglc.art.recolour` moves the base and emissive colours and touches
nothing else: transparency, alpha mode, metallic, roughness and sheen are the
model's own, and are what make the bubble read as glass rather than as paint.

Why those four colours, and why they are far apart in hue rather than in
brightness, is in the docstring of `twitchoglc.items.default_table`.

Each also gets a small emissive floor of its own colour
(`twitchoglc.game.ITEM_GLOW`), for the reason recorded at length in
[`../weapons/CREDITS.md`](../weapons/CREDITS.md): a map places **no dynamic
lights at all**, so an item in an unlit corner is a black shape, and a light
riding the camera was measured and washes out the baked lighting to fix it.

## How it was prepared

[`tools/clean_model.py`](../../../tools/clean_model.py) is a Blender script; it
edits the `.blend` and exports this file in the same run:

```console
python tools/clean_model.py grass-clumps/medpack.blend \
    --fill-holes --concentric \
    --export twitchoglc/assets/items/medpack.glb
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
redistributes twitch. The test for anything added here later is the one in
[`../weapons/CREDITS.md`](../weapons/CREDITS.md): **CC0, BSD or an equivalently
unconditional licence may be committed; anything share-alike must be fetched**
to a user cache at the user's request, the way the OpenArena content is. Either
way it is credited here with a link.
