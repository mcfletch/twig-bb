# Character art, and where it came from

**Every piece of geometry in this directory is credited here, with a link to
its author's page, whether or not its licence requires it.** That is the rule
for all art in this project, not a courtesy extended to some of it. A model
whose author cannot be named from this file does not belong here.

The rule runs the other way as well: nothing is credited that is not shipped,
since an acknowledgement for art the program does not contain is a claim about
nothing.

## The bodies: Quaternius' Universal Base Characters

The figures here are built on the base characters and hairstyles of the
**Universal Base Characters** kit, and the face, the hands and the shape of a
body are that kit's work rather than this project's.

| | |
|---|---|
| **Author** | Quaternius |
| **Page** | <https://quaternius.com/packs/universalbasecharacters.html> |
| **Home** | <https://quaternius.com> |
| **Licence** | [CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/) — public domain dedication |
| **Version used** | the free (Standard) pack, glTF, Godot/Unreal variant |

| Taken from the kit | Used as |
|---|---|
| `Superhero_Male_FullBody` | the male figure's body, skeleton, eyes and brows |
| `Superhero_Female_FullBody` | the female figure's, the same |
| `T_Superhero_Male_Dark`, `T_Superhero_Female_Dark_BaseColor` | the skin the face and hands are painted from |
| `T_Superhero_*_Normal` | the surface detail, resampled to 512 pixels |
| `T_Eye_Brown` | the eyes, left exactly as they came |
| `Hair_Long`, `Hair_Buns` | the two hairstyles |

CC0 asks for nothing. Quaternius takes support at
<https://www.patreon.com/quaternius>.

## Made for this project — the crew

What this project adds to those bodies: the skeleton's names, the suit, the
animation, the attachment points and the reduced models.

| | |
|---|---|
| **Author** | this project |
| **Licence** | the same BSD terms as the rest of twig-bb |
| **Source** | [`grass-clumps/character.py`](../../../../grass-clumps/character.py) in this workspace |
| **Tool** | Blender 5.0, through its `bpy` module |

| File | Used as | Triangles |
|---|---|---|
| `male_character.glb` | one of the two builds a match hands out | 5199 |
| `male_character_lod1.glb` | the same figure at distance | 1557 |
| `female_character.glb` | the other | 5200 |
| `female_character_lod1.glb` | the same figure at distance | 1558 |

Each carries a skeleton of 57 bones, nineteen animation clips and four
attachment points, and states its own humanoid bone map — 52 bones of it,
including both full hands — in a `VRMC_vrm` extension, so an avatar toolchain
can retarget onto it without being taught the naming. What all of that has to
satisfy is written down in [CHARACTER-RIG.md](../../../CHARACTER-RIG.md); the
figures are the reference implementation of it rather than the definition.

The suit is one 512-pixel base-colour texture, painted by the same script and
packed into the `.glb`. It is painted by *where a texel lands on the body*
rather than by where it lands on the sheet, which is what lets one description
of a garment clothe a body somebody else modelled and unwrapped.

## Conventions taken from elsewhere

The skeleton uses the bone names of **VRM 1.0**, whose specification is
published by the VRM Consortium under the MIT licence at
<https://github.com/vrm-c/vrm-specification>. Names and a schema are facts
about a format; no VRM code or asset is in this project.

The bones arrive from the kit under **Unreal Engine's mannequin names**
(`pelvis`, `spine_01`, `clavicle_l`) and are renamed to VRM's. A naming
convention is a fact about a format in the same way.
