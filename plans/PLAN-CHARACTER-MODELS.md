# Plan: Rigged Character Models for twig-bb

**Status:** Built (2026-08-18) — the generator, the figures and the control
layer all land, on CC0 base bodies rather than on procedural ones; see *What
landed* below for where each piece went and what the plan's own answers turned
out to be wrong about.
**Target:** Blender script to generate rigged humanoid models with animations

## Overview

Create a Blender Python script that procedurally generates rigged humanoid character
models suitable for use in twig-bb. The models export to GLB format (binary glTF),
matching the existing weapon assets in `twig_bb/assets/`.

## Requirements

### Polygon Budget
- **Primary model:** 1500 triangles maximum
- **Low-resolution stand-in:** ~300-500 triangles (LOD1)

### Character Variants
- **Male:** Muscular but lean build, long flowing hair
- **Female:** Muscular but lean build, short spikey hair
- **Proportions:** Follow Vitruvian Man ratios (8 heads tall)
- **Style:** Serious warriors, not exaggerated; de-emphasized but obvious sexual characteristics

### Outfit
- Space jumpsuit with:
  - Accent colour stripes
  - Belt details
  - 8 colour variants (accent colours only, base suit remains consistent)

### Skeleton/Rig
Standard humanoid armature with:
- Root bone
- Spine chain (hips, spine, chest, neck, head)
- Arms (shoulder, upper_arm, forearm, hand, fingers)
- Legs (thigh, shin, foot, toe)
- Hair bones for secondary animation (male: chain of 4-6 bones, female: cluster for spikes)

### Animations Required

#### Base Movement (all weapons)
| Animation | Frames | Loop | Notes |
|-----------|--------|------|-------|
| idle      | 60     | yes  | Breathing motion, subtle weight shift |
| walk      | 30     | yes  | 1 step cycle |
| run       | 20     | yes  | Fast run cycle |
| jump      | 15     | no   | Launch phase |
| fall      | 10     | yes  | Airborne loop |
| land      | 12     | no   | Impact recovery |
| die       | 45     | no   | Collapse to ground |
| turn_left | 15     | no   | 90-degree pivot |
| turn_right| 15     | no   | 90-degree pivot |

#### Weapon-Specific Animations
Each weapon type needs a fire animation (different stance/recoil):

| Weapon         | Key in twig-bb | Fire Animation | Notes |
|----------------|----------------|----------------|-------|
| Pistol         | `pistol`       | fire_pistol    | One-handed grip, light recoil |
| Shotgun        | `shotgun`      | fire_shotgun   | Two-handed, strong recoil |
| Sniper rifle   | `rifle`        | fire_rifle     | Two-handed, shoulder brace, steady |
| Rocket launcher| `rocket`       | fire_rocket    | Two-handed, shoulder-mounted |

Additional weapon poses for each:
- `hold_<weapon>`: Idle stance while holding weapon
- `aim_<weapon>`: Aiming down sights pose (rifle, pistol)

### Colour Variants
Accent colours (stripes, belt, trim):
1. Red
2. Blue
3. Green
4. Yellow
5. Orange
6. Purple
7. Cyan
8. White

Base jumpsuit remains dark grey/charcoal across all variants.

### Output Files
```
grass-clumps/
├── character.py              # Generation script (new)
├── character.blend           # Generated .blend with live materials
└── character-preview.png     # Optional rendered preview

twig_bb/assets/characters/    # Exported GLB files
├── male_character.glb        # Primary male model with all animations
├── male_character_lod1.glb   # Low-res male stand-in
├── female_character.glb      # Primary female model with all animations
├── female_character_lod1.glb # Low-res female stand-in
└── CREDITS.md                # Attribution and generation info
```

Run command:
```bash
python grass-clumps/character.py --output-dir grass-clumps
# or via Blender:
blender --background --python grass-clumps/character.py -- --output-dir grass-clumps
```

## Technical Approach

### Mesh Generation
1. **Base body:** Construct from primitives using bmesh operations
   - Torso: Tapered cylinder with edge loops
   - Limbs: Tapered cylinders with joint detail
   - Hands/feet: Simplified blocky geometry (low poly budget)
   - Head: Sphere-based with facial plane

2. **Hair:**
   - Male: Ribbon/strip geometry, vertex groups for bone weighting
   - Female: Spike clusters from head

3. **Outfit details:**
   - Modeled directly onto body mesh (not separate geometry)
   - Stripe/belt as separate vertex groups for material assignment

### Materials
- Use PBR workflow (glTF-compatible):
  - Base colour
  - Metallic
  - Roughness
- Separate materials for:
  - `skin`
  - `suit_base`
  - `suit_accent` (colour variants)
  - `hair`
  - `belt_hardware`

### Rigging
- Use Blender's Rigify or manual armature
- Ensure bone naming follows glTF conventions
- Weight paint all vertices
- Set up bone constraints for natural movement

### Animation
- Use Blender's action system
- Each animation as a separate NLA track
- Export all actions via glTF

### Export
- GLB format (binary glTF)
- Include animations
- Embedded textures (if any)
- Apply modifiers before export

## Scale and Integration

- **Player height:** 1.8 metres (authoring scale)
- Model authored at real-world scale (1 Blender unit = 1 metre)
- Export scale handled by glTF exporter settings
- `twig_bb/avatar.py` defines collision/spawn geometry in map units; the visual
  model height of 1.8m is the design target

## Execution Environment

**The script must run within the dev-container** at `/workspaces/OpenGL-dev/` using
the Blender installation available there.

**Verified:** Blender 5.0.1 is installed at `/usr/bin/blender`

Run the script with:
```bash
cd /home/mcfletch/OpenGL-dev
python grass-clumps/character.py --output-dir grass-clumps
# or via Blender directly:
blender --background --python grass-clumps/character.py -- --output-dir grass-clumps
```

The script follows the same dual-invocation pattern as `arsenal.py`: it works
both as a standalone Python script (using `bpy` module) and as a Blender script
(using `blender --python`).

## Implementation Steps

1. [x] Verify Blender availability in dev-container (Blender 5.0.1)
2. [x] Create base body mesh generator
3. [x] Add Vitruvian proportions system
4. [x] Implement male/female variant geometry
5. [x] Create hair systems (long flowing / short spikey)
6. [x] Build outfit geometry (jumpsuit, neckline, belt)
7. [x] Set up materials with colour variants
8. [x] Generate armature with proper bone hierarchy
9. [x] Weight the mesh to the bones
10. [x] Create base movement animations
11. [x] Create weapon-specific animations
12. [x] Implement LOD generation (decimation)
13. [x] Export to GLB format
14. [x] Test import in twig-bb renderer
15. [x] Create CREDITS.md

## What landed

**The bodies are not this project's.** Composing a human out of primitives got
a figure with the right measurements and the wrong anatomy, and no amount of
adjustment to a generator was going to fix that: modelling a body is a
modelling problem. The figures are built on **Quaternius' CC0 Universal Base
Characters** (2026-08-18), credited in
[`twig_bb/assets/characters/CREDITS.md`](../twig_bb/assets/characters/CREDITS.md),
and what this project writes is everything around them -- the bone names, the
suit, the poses, the clips, the sockets and the budget. The polygon budget went
up from 1500 to 5200 to buy that anatomy, which is the trade the plan's own
"increase it if the aesthetics need it" allowed for.

The clothing is what made this a small change rather than a rewrite: the suit
is painted by asking **where a texel lands on the body**, so the same
description of a garment clothes a mesh this project neither modelled nor
unwrapped. A contributor's own base body goes through the same script.

**Where each piece went.** The generator is
[`grass-clumps/character.py`](../../grass-clumps/character.py); the figures are
in [`twig_bb/assets/characters/`](../twig_bb/assets/characters/); the contract
they satisfy is [CHARACTER-RIG.md](../CHARACTER-RIG.md); the game's control
layer is [`twig_bb/characters.py`](../twig_bb/characters.py); and the machinery
any second game would want identically is
[`OpenGLContext.character`](../../openglcontext/OpenGLContext/character/) with
`oglc-character-sheet` for reviewing a figure.

**The standards that were looked for, and what they gave.** The plan left the
rig, the clip names and the attachment points as this project's own invention.
They are not:

* **VRM 1.0** (`VRMC_vrm`) publishes a humanoid bone vocabulary -- 55 names,
  a required subset and a fixed parent chain -- so the skeleton uses those
  names and the figures state their own bone map in the extension as well. An
  avatar toolchain can retarget onto them without being taught our naming.
* **`VRMC_vrm_animation`** is the same map in a clip-only document, which is
  what a retargetable clip file would arrive as; the engine reads it.
* **Attachment points need no extension.** A node parented to a joint already
  inherits that joint's animated transform, so a named empty node under the
  joint is a socket in glTF's own terms. Both the Khronos registry and OMI's
  set were checked, twice and a fortnight apart; neither has an
  attachment-point extension in any state, and none is needed.
* **The thing being held declares its own grip**, as a node of the same name
  inside its own file, which `attachment.mounted` lines up with the figure's.
  This is the half the plan did not anticipate and the one that decides whether
  a stance can be written at all: with the weapon mounted by its origin, a
  shouldered rifle needs the hand 0.44 m from the shoulder because the origin
  is 0.39 m up the weapon from the butt, and the arm comes out straight. With
  the weapon mounted by its grip the hand goes where a hand goes -- 0.29 m out,
  the rifle's length of pull -- and the elbow bends.
* **Blending is nobody's standard.** No glTF extension describes it and none is
  proposed; it is runtime behaviour, and it went into the engine's mixer.

**Where the plan's own answers were wrong.**

* *"Position at palm centre, oriented so +Z is forward (barrel direction)."*
  A Blender bone exports as a node whose **+Y** is the bone's direction, and
  what mounts on a point faces its **-Z**. The socket bones are laid up the
  mounted thing and rolled, which is what makes a weapon go on with no
  transform of its own.
* *"8 colour variants"* as separate files. The accent is a colour the
  generator is given -- `--accent R,G,B` -- rather than eight shipped figures.
  Once the whole body is one painted sheet the accent is paint on it, so a
  variant is a texture rather than a material; a load-time switch between them
  is what `KHR_materials_variants` describes, and the loader does not read that
  extension today.
* *"Embedded textures (if any)"*. The whole figure is textured: one 512-pixel
  sheet carries the suit, its trim, the belt, the boots and the gloves, over
  the base body's own face and hands, with its normal map resampled beside it.
  Stripes drawn as rings of geometry would cost two hundred triangles to say
  what the sheet says for nothing. The eyes are the base body's own inset
  geometry, which is the one place a flat colour would ruin the figure.
* *"Stripe/belt as separate vertex groups for material assignment"* -- both are
  paint on the sheet, so neither is geometry and neither is a material.
* *"Hair bones for secondary animation"*. The hairstyles come rigged to the
  head bone, and a shell that moves with the head is what a figure fielded by
  the hundred can afford.
* The **poses are solved, not authored**: a weapon stance says where the grip
  is and which way the weapon points, and two-bone inverse kinematics works out
  the shoulder and the elbow. A degree of error at the shoulder is two
  centimetres at the hand, which is the difference between holding a rifle and
  holding air.
* A **sighted stance is solved against the weapon's own anatomy**, not guessed.
  Where the butt, the comb and the eyepiece sit inside the rifle is what fixes
  where the hand has to be and how far the head has to come over: the mount
  point is 0.39 m up the weapon from the butt, so a butt in the shoulder pocket
  puts the hand that far forward and no nearer. The numbers in `SHOULDERED`
  were searched for rather than typed, against two measurements taken off the
  posed figure -- how far the butt is from the shoulder pocket and how far the
  eye is from behind the sight -- with the butt weighted the heavier of the two
  because a stock resting on a collarbone is what a player would notice.

**Still open.** The suit is drawn by rule rather than by hand, so it reads at
the distance a match is fought at rather than close to; the hair is a shell
rather than strands; and the reduced models are decimations rather than
authored low-detail meshes. A per-team accent is a second build rather than a
load-time switch (see above).

## Weapon Attachment Approach

**Recommended: Grip bone with runtime parenting**

The character rig includes a `weapon_grip` bone in the right hand. Weapons are
separate GLB files (already exist in `twig_bb/assets/weapons/`). At runtime,
the weapon model is parented to this bone.

### Implementation

1. **Character side:**
   - Add `weapon_grip` bone as child of `hand.R` bone
   - Position at palm centre, oriented so +Z is "forward" (barrel direction)
   - Bone has zero length (marker bone) or minimal length
   - Export bone with rest pose transformation

2. **Weapon side:**
   - Weapons already exist as standalone GLB files
   - Each weapon needs a grip point defined (can be origin, or a named node)
   - Weapons are authored with grip at origin, barrel along +Z

3. **Runtime attachment:**
   - Load weapon GLB as child of character's `weapon_grip` bone
   - glTF node hierarchy supports this natively
   - Weapon inherits bone's animated transform

4. **Animation coordination:**
   - Character's `hold_<weapon>` and `fire_<weapon>` animations pose the arm/hand
   - Weapon follows via bone parenting
   - No weapon-specific skeletal animation needed

### Alternative considered: Baked weapon geometry

Baking weapons into character mesh was rejected because:
- Increases polygon budget per weapon variant
- 4 weapons × 2 genders × 8 colours = 64 model variants
- Weapons already exist as separate assets
- Runtime attachment is more flexible

## Visual Style

**Cartoony rendering** - stylized rather than realistic:

### Face Detail
- Simplified geometric features within polygon budget
- Defined brow ridge, nose bridge, cheekbones
- Eyes as inset geometry (not texture-painted)
- Minimal lip definition
- Strong silhouette reads at distance

### Body Proportions
- Vitruvian base (8 heads tall) with slight stylization
- Slightly larger hands for weapon readability
- Defined muscle groups as edge flow, not high-poly sculpt
- Clean topology over anatomical accuracy

### Polygon Budget Allocation (1500 tri target)
| Region      | Triangles | Notes |
|-------------|-----------|-------|
| Torso       | 300       | Chest, abdomen, back |
| Head + face | 250       | Stylized features |
| Arms × 2    | 200       | Upper, lower, hands |
| Legs × 2    | 300       | Thigh, calf, feet |
| Hair        | 200       | Male: ribbons, Female: spikes |
| Details     | 250       | Belt, stripes, collar |
| **Total**   | **1500**  | |

## Animation System

**glTF 2.0 animation model:**

- Animations stored as glTF animation clips
- Each clip is a named action (e.g., `idle`, `walk`, `fire_pistol`)
- Blending handled by runtime (OpenGLContext or game code)
- glTF supports:
  - Linear interpolation (default)
  - Step interpolation (for snappy poses)
  - Cubic spline interpolation (smooth curves)
- Export all actions via Blender's glTF exporter with "Group by NLA Track" or
  "Export all actions"

### Blending Considerations
- Transitions between animations are runtime responsibility
- Author animations with consistent root motion
- First/last frames of loops should match for seamless blend
- Fire animations return to hold pose for clean blend-out

## Resolved Questions

1. ~~Weapon attachment~~ → Grip bone with runtime parenting (see above)
2. ~~Face detail~~ → Cartoony style with geometric features (see above)
3. ~~Animation blending~~ → glTF model, runtime handles blending
4. **Inverse kinematics:** FK only for export; IK is authoring convenience only

## Existing Tools and Patterns

### Arsenal Generation Script (Primary Reference)

**`grass-clumps/arsenal.py`** is the established pattern for procedural model
generation. The character script will follow the same architecture:

#### Mesh Construction Primitives
```python
def revolve(name, profile, segments, **kwargs)  # Lathe operation
def cylinder(name, radius, y_from, y_to, ...)   # Capped cylinder
def box(name, size, location, tilt, ...)        # Cuboid with rotation
def prism(name, polygon, thickness, ...)        # Extruded 2D shape
def arc(name, centre, radius, width, ...)       # Curved bar
def tube(name, outer, bore, y_from, y_to, ...)  # Hollow cylinder
```

#### Material System
- `worn_metal()` - Procedural wear with chipping, scratches, grime
- `glowing()` - Emissive accent materials
- Materials tagged with `material['bake'] = True/False`

#### UV and Baking
- `atlas(parts)` - Smart UV project all parts into shared 0..1 space
- `bake_asset(parts, name, size)` - Bakes procedural materials to:
  - Base colour map
  - ORM (Occlusion/Roughness/Metallic) packed texture
  - Normal map
- Creates `baked_material()` with glTF-compatible node setup

#### Export
- `export_glb(root, path)` - Handles coordinate conversion (Blender Y-up to glTF)
- `add_iridescence()` - Post-process GLB to add extensions

### Existing Prototype

**`grass-clumps/crude-character.blend`** contains a basic mesh:
- 382 vertices, 380 faces (~760 triangles)
- No armature or animations yet
- Starting point for proportions

### twig-bb Processing Tools

- **`tools/clean_model.py`** - Post-process .blend files, export to GLB
- **`tools/prepare_weapon.py`** - Texture resampling for existing assets

## Character Script Architecture

The new `grass-clumps/character.py` script will:

1. **Import arsenal.py utilities** or replicate the pattern
2. **Add humanoid-specific primitives:**
   - `limb()` - Tapered cylinder with joint bulges
   - `torso()` - Chest/abdomen with muscle definition
   - `head()` - Stylized head with facial planes
   - `hand()` - Low-poly hand with finger groups
   - `hair_ribbons()` / `hair_spikes()` - Hair geometry

3. **Add rigging system:**
   - `build_armature(name)` - Create bone hierarchy
   - `weight_paint(mesh, armature)` - Auto-weight with corrections
   - `add_bone_constraints()` - IK for posing (FK export only)

4. **Add animation system:**
   - `create_action(name, bone_keyframes)` - Build animation clips
   - `pose_idle()`, `pose_walk()`, etc. - Keyframe generation
   - Actions exported via glTF NLA tracks

5. **Variant generation:**
   - `build_male()` / `build_female()` - Body shape variants
   - `apply_colour_variant(materials, accent)` - 8 colour schemes

## References

- twig-bb weapon models: `twig_bb/assets/weapons/`
- Avatar dimensions: `twig_bb/avatar.py`
- glTF 2.0 specification for animation export
- Vitruvian Man proportions (Leonardo da Vinci)
- Blender Python API (bpy) for mesh generation and rigging
