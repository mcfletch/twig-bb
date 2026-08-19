# The character contract

What a figure has to carry to be a combatant in this game: a skeleton whose
joints are named the way the engine reads them, a set of clips named the way
the state machine asks for them, and the points things are held on.

It is a contract rather than a description of one `.blend` file. Anything that
satisfies it is a character here — the two figures that ship, a contributor's
own, a commissioned model, or one adapted from somewhere else — and none of
that is a code change: `twig_bb.characters.load` takes a name and
`twig_bb.characters.BUILDS` lists the ones a match hands out.

The figures that ship are built by
[grass-clumps/character.py](../grass-clumps/character.py), which is the
reference implementation of everything below. Their bodies come from
Quaternius' CC0 base characters, which that script expects unpacked beside
itself; the figures' own
[CREDITS.md](twig_bb/assets/characters/CREDITS.md) says where to get them.

## 1. Space, scale and facing

| | |
|---|---|
| Format | glTF 2.0 binary (`.glb`), one file per figure |
| Units | metres; **1 glTF unit is 1 metre** |
| Up | +Y (glTF's own) |
| Facing | **+Z**, following the avatar conventions |
| Origin | between the feet, on the ground the figure stands on |
| Height | 1.80 m to the crown; hair may stand above it |

Facing +Z is the opposite of the weapons and projectiles, which are authored
facing -Z. Both are right for what they are, and neither has to know about the
other: `twig_bb.characters.FORWARD` and `twig_bb.game.MODEL_FORWARD` say which
is which, and an attachment point resolves the difference on its own (§4).

## 2. The skeleton

Joints carry **VRM 1.0's humanoid bone names** — `hips`, `spine`, `chest`,
`upperChest`, `neck`, `head`, `leftShoulder`, `leftUpperArm`, `leftLowerArm`,
`leftHand`, `leftUpperLeg`, `leftLowerLeg`, `leftFoot`, `leftToes` and their
right-hand twins. The rest pose is a T-pose.

A file may also state the map outright in a `VRMC_vrm` extension, and the ones
that ship do. Either is enough:
`OpenGLContext.character.humanoid.Humanoid` reads the extension first and falls
back to the names, and it recognises the other conventions in circulation
(Mixamo's, Unreal's, Blender's Rigify) as well, so a model from elsewhere
usually resolves without being renamed.

**Required**: `hips`, `spine`, `head`, and both complete arms and legs — the
fifteen bones VRM requires. Everything else is optional, and a figure that has
no `leftToes` simply has none.

Beyond the humanoid bones a figure may carry whatever it likes. The shipped
ones carry both complete hands — VRM's `*Metacarpal`, `*Proximal`,
`*Intermediate` and `*Distal` for all five digits — which is what closes a hand
round a grip, and a `root` under the hips that the whole figure hangs from.
Their hair is weighted to `head` and needs no bones of its own.

## 3. The clips

Each is a separate glTF animation, named exactly:

| Clip | Loops | What it is |
|---|---|---|
| `idle` | yes | standing, breathing, weight shifting |
| `walk` | yes | one stride cycle |
| `run` | yes | one stride cycle, at pace |
| `walk_back` | yes | one stride cycle, going backwards |
| `strafe_left`, `strafe_right` | yes | one sidestep: out and closed |
| `jump` | no | the launch |
| `fall` | yes | airborne |
| `land` | no | the impact and the recovery out of it |
| `die` | no | struck, buckling, and flat on the ground at the end |
| `turn_left`, `turn_right` | no | the shuffle a figure makes while it is turned |

and, for each of `pistol`, `shotgun`, `rifle`, `rocket`:

| Clip | Loops | What it is |
|---|---|---|
| `hold_<weapon>` | yes | carrying it |
| `aim_<weapon>` | yes | sighted; only `pistol` and `rifle` have one |
| `fire_<weapon>` | no | the shot, from the sights where the weapon has them, lowering to the carry |

**A weapon that can be sighted is fired sighted.** A rifle goes off from the
shoulder rather than from the hip, so `fire_rifle` opens where `aim_rifle`
holds and comes down to where `hold_rifle` begins — which is the pose the game
blends back to. A weapon with no `aim_` clip fires from the carry.

**Which way a body is going decides which of these plays**, and it is decided
in the body's own frame rather than the world's: a combatant facing you while
it backs off is playing `walk_back`, and one crossing in front of you is
sidestepping. A figure that has only `walk` still walks, forwards, because a
missing clip is not an error — but it is the thing a player notices first.

A cycle is played at **the rate the body is actually travelling**, so its feet
stay on the ground rather than skating over it; `walk_back` and the sidesteps
serve every speed that way rather than having a run of their own.

**A looping clip's last frame is its first**, so the cycle closes. **A one-shot
ends in the pose the game will hold** — `die` ends on the floor, because that
is the frame a body stays in.

`twig_bb.characters` is what chooses between them, and it plays the movement
clip over the whole body with the weapon clip layered over the spine and above,
so a figure runs and fires at the same time. **The clip decides the hand**: a
figure playing a weapon clip is holding that weapon's model on `socket_grip`,
and a figure playing none — anybody empty-handed, and anybody dead — is holding
nothing.

A figure that is missing a clip is not an error: what it does not have, it does
not play.

## 4. Attachment points

Things are held on ordinary glTF nodes named `socket_<name>`, parented to the
joint they ride with. glTF needs no extension for this — a node under a joint
already inherits that joint's animated transform — and
`OpenGLContext.character.attachment` is what finds them.

| Point | On | Carries |
|---|---|---|
| `socket_grip` | right hand | the weapon |
| `socket_offhand` | left hand | the supporting hand's position |
| `socket_back` | upper chest | a stowed weapon, facing backwards |
| `socket_view` | head | the first-person eye |

**A mounted model faces the point's own -Z, with its +Y up**, which is what
every model this project builds is authored to and what a glTF camera looks
down. So a weapon goes on with no transform of its own, and a camera put on
`socket_view` looks where the figure looks.

**The thing being held says where it is held.** A weapon carries a
`socket_grip` node of its own, at the grip its modeller put there, and
`OpenGLContext.character.attachment.mounted` lines that node up with the
figure's point of the same name. A weapon is modelled about whatever origin
suits it — these are built about their balance point — and the grip node is what
makes that irrelevant: nothing outside the model needs to know where its origin
sits, and re-modelling a weapon does not move the hand that holds it. A model
that declares no such node is mounted by its own origin.

Both sides are ordinary glTF nodes. There is no glTF extension for attachment
points, in the Khronos registry or OMI's, and none is wanted: a node in the
hierarchy is what the format already offers.

## 5. Materials and the texture

**One texture carries the figure.** A 512-pixel base-colour sheet holds the
face, the hands, the suit, its trim, the belt, the boots and the gloves — the
whole body, on the body's own unwrap.

The suit on that sheet is painted by **where a texel lands on the body**, not
by where it lands on the sheet: the neckline is a V cut into the chest, the
gloves start past a distance from the middle, the boots are below a height.
Nothing in that description knows the unwrap, which is what lets it clothe a
body somebody else modelled — including one a contributor brings.

Four materials, because four things behave differently:

| Name | What it is |
|---|---|
| `body` | the figure: the sheet above, plus the surface detail its normal map carries |
| `hair` | one colour, no map; a hairstyle is one colour at the size a game draws it |
| `eyebrows` | the same colour as the hair, on the base body's own brow mesh |
| `eyes` | the one thing on a figure a flat colour would ruin, so it keeps its own texture |

Roughness and metallic are per-material constants. The figure carries no
roughness map: one jumpsuit is one roughness.

**The accent colour is paint, not a material.** It is on the sheet along with
everything else, so a variant is a different sheet:
`grass-clumps/character.py --accent R,G,B` builds one. Switching accent at
runtime, without a second file, is what `KHR_materials_variants` is for; the
loader does not read that extension today.

## 6. Budget

| | |
|---|---|
| Triangles | 5200 for the full model |
| Reduced model | `<name>_lod1.glb`, about 1560 triangles, same skeleton and clips |
| Bones | 57 on the shipped figures, 52 of them named as humanoid bones |
| Textures | one 512px base-colour sheet, one 512px normal map, one eye map, all packed into the `.glb` |
| Materials | four, so four glTF primitives |
| File | about 1.5 MB per figure, animation included |

The reduced model is the same character seen from further away — same
skeleton, same clip names — so switching between them is a change of mesh and
never of behaviour.

## 7. Checking a figure against this

`oglc-character-sheet` renders every clip of a model from four sides as a
contact sheet, with an `index.html` to read them down one page:

```bash
oglc-character-sheet twig_bb/assets/characters/male_character.glb \
    --out sheets/ --hold grip=twig_bb/assets/weapons/sniper-rifle.glb
```

A figure that satisfies this document holds its weapon the right way up, ends
its loops where it began them, and leaves its dead on the floor.
