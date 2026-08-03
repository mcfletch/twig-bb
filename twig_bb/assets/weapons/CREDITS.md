# Weapon art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

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

## Also shipped — 3dmodelscc0, Free CC0 Guns & Explosives Pack

| | |
|---|---|
| **Author** | 3dmodelscc0 |
| **Page** | <https://3dmodelscc0.itch.io/> |
| **Pack** | [Free CC0 Guns & Explosives Pack](https://3dmodelscc0.itch.io/free-cc0-guns-explosives-pack) (2023-10-30) |
| **Licence** | **CC0 1.0 Universal** — <https://creativecommons.org/publicdomain/zero/1.0/> |
| **Fetched** | 2026-07-27 |

| File | Original | Used as | Textures |
|---|---|---|---|
| `luger-pistol.glb` | Luger | nothing now — see below | its own, resampled to 512px |
| `pump-shotgun.glb` | Shotgun | nothing now — see below | **none** — see below |
| `assault-rifle.glb` | AK-47 | nothing now — see below | **none** — see below |
| `rocket-launcher.glb` | Sniper | nothing now — see below | **none** — see below |
| `pipe-bomb.glb` | Pipe_Bomb | nothing now — see below | its own, resampled to 512px |

The pack is CC0 and asks for nothing, but its author asked to be linked, and
that is the entry above. Everything in it is worth knowing about: 19 models,
firearms and explosives both, and the rest of them are a table edit away.

### What was done to them, and why

The source models are `.fbx` with 2048×2048 PBR maps; converted straight to
`.glb` each one is **8–10 MB**, which is not a thing to put in a source
repository for a *stand-in*. [`tools/prepare_weapon.py`](../../../tools/prepare_weapon.py)
trims one, and prints what it did so the numbers can be recorded here:

```console
python tools/prepare_weapon.py Luger.glb   luger-pistol.glb  --textures 512
python tools/prepare_weapon.py Shotgun.glb pump-shotgun.glb  --strip-textures
python tools/prepare_weapon.py AK47.glb      assault-rifle.glb   --strip-textures
python tools/prepare_weapon.py Sniper.glb    rocket-launcher.glb --strip-textures
python tools/prepare_weapon.py Pipe_Bomb.glb pipe-bomb.glb       --textures 512
```

**None of these is drawn any more.** Every weapon in the table now has art
modelled for it, and the five stand-ins have been stood down. They are kept
rather than deleted: they cost half a megabyte between them, they are the
nearest thing to hand if a sixth weapon turns up before it has art, and each
is one table edit from being used again.

Geometry is never touched — mesh, normals and UVs come through unchanged — so
re-running this with better maps later is a re-run and not a re-model.

**Two of the three ship with no textures at all, and that is deliberate.** The
Blender batch conversion that turns this pack into `.glb` binds *one model's*
maps onto many of the others: of the 19 converted models, 8 carry their own
maps and **11 wear something else's** — the shotgun, the AK-47, the Makarov,
the sniper rifle and the flare gun are all skinned with the anti-tank mine's
textures (byte-identical), and the M4A1 wears the Molotov's bottle. A rifle
wearing a landmine reads worse than a rifle wearing nothing, so those two were
stripped to plain gunmetal, which takes the scene's lighting and looks like
what it is: a blocked-out stand-in. The Luger's own maps *are* correct, so it
keeps them.

If the conversion is re-run with the material assignment fixed, dropping the
properly-skinned models in is `--textures 512` and a table edit.

### The models that are correctly skinned

`AT_MINE`, `C4`, `Claymore`, `Flashbang`, `Luger`, `Nuclear_Bomb`, `Pipe_Bomb`
and `Smoke_Grenade` — useful to know when §7 wants grenades, since those come
through with their own maps already.

## Where each weapon sits in the hand

`model`, `modelScale`, `modelOffset`, `modelYaw`, `modelPitch` and `modelRoll`
are fields of the weapon in [`twig_bb/weapons.py`](../../weapons.py), so
placing a new model is a table edit and never a code change.

Nothing here needs a rotation or a scale, for two different reasons worth
keeping apart. The imported models are authored in centimetres lying along
their own +Y, and the glTF export already carries the node scale and the
Z-up-to-Y-up rotation that undo both. `javelin-launcher.glb` is modelled in
metres for this game and its export turns it so it leaves already pointing down
−Z. Either way they arrive in metres pointing down −Z — which is exactly the
way the view looks. That is worth
knowing before reaching for the angles: measure where a model actually lands
before turning it, because a source that needs no turning and one that needs
90° apart look identical in the file. Only `modelOffset` differs between them,
and that is where the weapon sits in the hand: metres right, down and forward of
the eye.

`twig-bb-hud --weapon <key>` starts holding one weapon, which is how those
numbers are dialled in.

The two stripped models are given a gunmetal material — base colour 0.30,
metallic 0.5, roughness 0.55. Not chrome: a high metallic with a low roughness
under an environment probe reads as a mirror, and a mirror-finish rifle looks
like a bug rather than like a stand-in.

**Every model also gets a small emissive floor** (`--fill`, 0.07 by default),
and that is not decoration. A map places no dynamic lights at all — both
families bake their lighting into lightmaps, which is what makes them look like
themselves — so a weapon held in front of the camera is lit by almost nothing
and renders as a black silhouette. The obvious fix, a fill light riding the
camera, was tried and measured on a real map: it brightened the *map* by +61
grey levels and the weapon by only +26, which is a flashlight washing out the
baked lighting in order to show a stand-in. The emissive floor is per material,
so on the same capture it lifted the weapon by +16 and moved the map by **0**.

## Why these may be committed at all

twig-bb is BSD, and [the workspace rules](../../../../CLAUDE.md) forbid copying
copyleft-licensed material into it. **CC0 is not copyleft**: it is a dedication
to the public domain with no conditions, so shipping it here carries no
obligation onto anyone who redistributes twig-bb. That is the difference between
these files and the OpenArena content, which is CC BY-SA 3.0 and is therefore
*fetched to a user cache at the user's request* and never vendored — see
[twig_bb/download.py](../../download.py).

The test applies to any art added here later: **CC0 or an equivalently
unconditional licence may be committed; anything share-alike must be fetched.**
Either way it is credited here with a link.

## What they stand in for

Blocked-out first-person weapons, so the HUD, the reticule and the weapon model
can be built and seen before [§7](../../../PROJECT-PLAN.md)'s commissioned
weapons exist. §7 records why a weapon placeholder is adequate where a
character placeholder is not: what a weapon contributes to play is its
behaviour, its reticule and where its projectile leaves from, none of which is
the model.
