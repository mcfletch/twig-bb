# Weapon art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

## Shipped now — 3dmodelscc0, Free CC0 Guns & Explosives Pack

| | |
|---|---|
| **Author** | 3dmodelscc0 |
| **Page** | <https://3dmodelscc0.itch.io/> |
| **Pack** | [Free CC0 Guns & Explosives Pack](https://3dmodelscc0.itch.io/free-cc0-guns-explosives-pack) (2023-10-30) |
| **Licence** | **CC0 1.0 Universal** — <https://creativecommons.org/publicdomain/zero/1.0/> |
| **Fetched** | 2026-07-27 |

| File | Original | Used as | Triangles | Textures |
|---|---|---|---|---|
| `luger-pistol.glb` | Luger | the pistol | 4 970 | its own, resampled to 512px |
| `pump-shotgun.glb` | Shotgun | the shotgun | 1 740 | **none** — see below |
| `assault-rifle.glb` | AK-47 | the rifle | 4 801 | **none** — see below |

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
python tools/prepare_weapon.py AK47.glb    assault-rifle.glb --strip-textures
```

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
are fields of the weapon in [`twitchoglc/weapons.py`](../../weapons.py), so
placing a new model is a table edit and never a code change.

These three need **no rotation and no scaling at all**: the models are authored
in centimetres lying along their own +Y, but the glTF export already carries the
node scale and the Z-up-to-Y-up rotation that undo both, so they arrive in
metres pointing down −Z — which is exactly the way the view looks. That is worth
knowing before reaching for the angles: measure where a model actually lands
before turning it, because a source that needs no turning and one that needs
90° apart look identical in the file. Only `modelOffset` differs between them,
and that is where the weapon sits in the hand: metres right, down and forward of
the eye.

`twitch-hud-demo --weapon <key>` starts holding one weapon, which is how those
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

twitch is BSD, and [the workspace rules](../../../../CLAUDE.md) forbid copying
copyleft-licensed material into it. **CC0 is not copyleft**: it is a dedication
to the public domain with no conditions, so shipping it here carries no
obligation onto anyone who redistributes twitch. That is the difference between
these files and the OpenArena content, which is CC BY-SA 3.0 and is therefore
*fetched to a user cache at the user's request* and never vendored — see
[twitchoglc/download.py](../../download.py).

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
