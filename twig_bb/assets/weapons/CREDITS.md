# Weapon art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

Every file here is this project's own, and the rule runs the other way as well:
nothing is credited that is not shipped, since an acknowledgement for art the
program does not contain is a claim about nothing. `tests/test_weapons.py`
checks both directions against what is on disk.

## Made for this project — the javelin launcher and its rocket

| | |
|---|---|
| **Author** | this project |
| **Licence** | the same BSD terms as the rest of twig-bb |
| **Source** | [`grass-clumps/arsenal.py`](../../../../grass-clumps/arsenal.py) in this workspace |

| File | Used as | Textures |
|---|---|---|
| `javelin-launcher.glb` | the rocket launcher | its own, baked at 512px |
| `javelin-rocket.glb` | what it throws — the projectile in flight | its own, baked at 256px |
| `sawn-off-shotgun.glb` | the shotgun | its own, baked at 512px |
| `grenade-launcher.glb` | the grenade launcher | its own, baked at 512px |
| `grenade-round.glb` | what it throws — the projectile in flight | its own, baked at 256px |
| `sniper-rifle.glb` | the rifle | its own, baked at 512px |
| `handgun.glb` | the pistol | its own, baked at 512px |

One script builds all of them: the geometry, the materials and the maps, from
nothing every time it runs, written straight into this directory. Re-running it after
an edit is the whole update procedure, and `javelin-launcher.blend` beside it
opens with the material node graphs still live rather than with the flattened
textures.

The rocket is modelled to fit the launcher's barrel — 0.20 m long and 0.066 m
across, inside the 0.084 m bore — so the two are to each other's scale rather
than to a guess. [`twig_bb.game`](../../game.py) draws it for everything in
flight, at :data:`~twig_bb.game.PROJECTILE_DRAW_SCALE`, and every slot in the
batch is handed *the same* subtree so the pass collapses them into one
instanced draw per part however many are in the air.

It is modelled at life size in metres — a 0.60 m tube with a 0.10 m barrel —
and its wear is procedural: paint chipped off the edges, scratches down the
flanks, grime in the hollows. None of that survives a glTF export as nodes, so
the export bakes it into the three maps of the glTF metallic/roughness
material: base colour, a second image carrying occlusion, roughness and
metallic in its red, green and blue, and a tangent-space normal map. The
accent strips are not textured at all; their emission travels as a factor.

Its **emissive floor follows its own base colour** rather than being flat grey
— the same 0.07 as everything else here, and for the same reason (see below),
but applied through the base-colour map, so the paint keeps its hue instead of
being lifted towards grey.

### The wood is grown, not photographed

The shotgun's stock and the grenade launcher's furniture are procedural: a wave
of growth rings bent by noise, between the pale early wood and the dark late
wood of a year's growth, with the roughness following the colour because the
late wood is the harder of the two. It is baked into each weapon's own atlas
like everything else here.

**A CC0 photo texture was the brief and this is a deliberate departure.**
ambientCG's library is the obvious source and is CC0, but its API carries no
licence field to check against — and the rule at the top of this file is that
a shipped texture is one whose terms someone can *name from here*. Wood that
belongs to the project outright is freer than CC0 and needs no such claim, so
that is what it is. Swapping in a fetched texture later is a change to
`wood()` in the build script and a row in this table.

## Bringing in art from somewhere else

[`tools/prepare_weapon.py`](../../../tools/prepare_weapon.py) is the route for a
model this project did not build. Source art carries 2048×2048 maps and arrives
at eight or nine megabytes a gun, which is not a thing to commit; the tool
resamples the maps or strips them for a plain metallic material, leaves the
geometry alone, and prints what it did so the numbers can be recorded in a table
here beside the file.

## Where each weapon sits in the hand

`model`, `modelScale`, `modelOffset`, `modelYaw`, `modelPitch` and `modelRoll`
are fields of the weapon in [`twig_bb/weapons.py`](../../weapons.py), so
placing a new model is a table edit and never a code change.

Nothing here needs a rotation or a scale. Each is modelled in metres for this
game and its export turns it so it leaves already pointing down −Z, which is
exactly the way the view looks. That is worth knowing before reaching for the
angles: measure where a model actually lands before turning it, because a source
that needs no turning and one that needs 90° apart look identical in the file.
Only `modelOffset` differs between them, and that is where the weapon sits in
the hand: metres right, down and forward of the eye.

`twig-bb-hud --weapon <key>` starts holding one weapon, which is how those
numbers are dialled in.

**In a combatant's hand it is the model that says where it is held.** Each
weapon here carries a `socket_grip` node at the grip — the wrist of the stock,
the pistol grip, the rear grip of the launcher — and a figure's own
`socket_grip` is lined up with it (see
[CHARACTER-RIG.md §4](../../../CHARACTER-RIG.md)). That is what lets these be
modelled about their balance point, which is what the first-person placement
above wants, without a rifle hanging off a fist fifteen centimetres from the
hand. It is an ordinary glTF node: the format has no attachment-point extension
and needs none.

**Every model also gets a small emissive floor** (`EMISSIVE_FILL` in the build
script, 0.07), and that is not decoration. A map places no dynamic lights at all — both
families bake their lighting into lightmaps, which is what makes them look like
themselves — so a weapon held in front of the camera is lit by almost nothing
and renders as a black silhouette. The obvious fix, a fill light riding the
camera, was tried and measured on a real map: it brightened the *map* by +61
grey levels and the weapon by only +26, which is a flashlight washing out the
baked lighting in order to show one gun. The emissive floor is per material,
so on the same capture it lifted the weapon by +16 and moved the map by **0**.

## Why these may be committed at all

They are ours and they are BSD, so they carry no obligation onto anyone who
redistributes twig-bb — which is what [the workspace
rules](../../../../CLAUDE.md) require of anything vendored into a BSD codebase.

The test applies to any art added here later: **BSD, CC0 or an equivalently
unconditional licence may be committed; anything share-alike must be fetched**
to a user cache at the user's request, the way the OpenArena content is — it is
CC BY-SA 3.0 and is therefore never vendored, see
[twig_bb/download.py](../../download.py). Either way it is credited here with a
link.
