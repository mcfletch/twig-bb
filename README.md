# twitch — a Quake 3 (and Quake 2) map viewer

Load a `.bsp` map and walk around inside it, rendered through
[OpenGLContext](https://github.com/mcfletch/openglcontext)'s physically-based
render pass on the OpenGL core profile, with the map's own baked lighting.

```bash
twitch-viewer arena/maps/ctf-curvy.bsp        # a map you already have
twitch-viewer some-map.pk3                    # an archive: unpacked for you
twitch-viewer https://example.com/map.pk3     # a URL: fetched and cached
twitch-viewer openarena:oa_dm1                # a map from a content pack
```

With nothing of your own to look at, `twitch-viewer --list-packs` shows what can
be downloaded and `openarena:<map>` fetches and opens one of the fifty
OpenArena levels — see [Content packs](#content-packs).

Both map families go through the same entry point. `IBSP` version 38 (Quake 2)
and version 46 (Quake 3, and OpenArena) are told apart by their header and
dispatched to their own reader; everything after that — surface styles, batched
geometry, the lightmap atlas, PBR materials, the scene, the collision mesh, push
volumes — is the same objects either way.

> Note: Realistically, you likely do not want to use the Quake 2 renderer,
> as there are no CC compatible Quake2 base texture packs, so essentially all
> Quake 2 maps will be broken. However, if you for some reason need to be
> able to read the format a model should load.

## Content Licensing Note

openglcontext-twitch is mostly targetted at allowing you to use existing
infrastructure (e.g. quake3 map editors) to create your own games.
However, it is also a map loader/viewer, and can be used to render existing
pk3 files.

Most sample maps that you will find on the Internet have somewhat restrictive
licenses, or are dependent on assets that have such licenses. If you are using
openglcontext-twitch as a viewer for your own use, this is fine. We can load
OpenArena or secondary pk3 files. However, most maps will reuse base textures.
When you download or install these packs, you are accepting their licenses,
and that includes any restrictions on use.

By default if the user loads a map that uses base textures they will be 
offered the chance to download textures to replace them.

If the user decides to download them, we will download and install 
Kpax's CC BY-NC-ND 3.0 licensed [xcsv_hires](https://ioquake3.org/extras/replacement_content/) 
base texture replacements to allow most Quake 3/OpenArena maps to load.

> Note that Kpax's textures are **NOT** licensed for commercial use, so if
> you are building a game with this library and intending to sell it you will
> need to *not* offer this texture pack to the user.

## Controls

| Key | Action |
|---|---|
| `w` `a` `s` `d`, arrows | walk; `a`/`d` strafe |
| `q` / `e` | turn left / right |
| ctrl + up / down | look up / down |
| shift | run (held) |
| space | jump; rise, while flying |
| `c` | sink, while flying |
| `f` | fly (noclip) on/off |
| `m` | cycle movement mode: mouse-look, walk, fly |
| `g` | walk (physics) / free-fly camera |
| `1` `2` `3` | choose a weapon |
| `[` `]`, mouse wheel | previous / next weapon held |
| ctrl | fire (held) |
| alt + `f` | developer overlay — frame rate, draw counts, where you are |
| `F2` | save a screenshot — `twitch-<date>-<time>.png`, in the directory you launched from |
| alt + `s` | the engine's own screenshot key — `twitch-viewer-screen-0001.png`, same place |
| `F6` | key bindings — rebind any command, over the map |
| `F10` | rendering settings — shadows, lighting, detail, over the map |

**Mouse-look (`fps`) is the mode you start in** — an arena map is played with
the mouse, and the pointer is grabbed so the view keeps turning past the edge of
the screen. `m` cycles to keyboard-only walking if you would rather have the
pointer back. Either way you start at one of the map's spawn points, facing the
way the mapper aimed it. Gravity and collision come from the
character controller in `OpenGLContext.move`; jump pads set the capsule's
velocity outright through the physics trigger system. Water, slime and lava are
volumes rather than floors: you fall in, and being under the surface imposes the
swim mode until you are out again.

Quake 3 jump pads are **aimed**: a `trigger_push` there names a destination
entity rather than a direction, and every one of the 236 pads in the OpenArena
maps does. The launch is solved as an arc that passes through that point under
the map's gravity — see [`SPEC-Q3PUSH`](specs/SPEC-Q3PUSH.md), which is explicit
about which part of that is observed and which part is a choice.

The keys above are **not** hard-coded here: each way of moving is a declared
`MovementMode` node from `OpenGLContext.move.modes` carrying its own speeds and
its own key bindings, which is what lets one settings screen present the
navigation of every viewer and lets a game retune it by setting fields. `F6`
opens that screen: it lists every command of every mode, rebinds one from the
next key you press, asks before taking a key another command in the same mode
already has, and saves what you choose for next time. `F10` opens the rendering
settings — shadows, environment lighting, the light limit, batching, distance
detail — all of them read per frame by the render pass, so a map that runs badly
can be made to run without a restart. Both are OpenGLContext's
[overlay UI](../openglcontext/docs/overlayui.html); while either is up, nothing
reaches the map. The
viewer declares mouse-look (`fps`, the default), walk, fly and swim; swim is
world-imposed and appears in no cycle. Held keys are *sampled* once per frame
rather than reacted to, which is why running and jumping work in the same frame,
and a tap that begins and ends between two frames is still counted.

In mouse-look the pointer is grabbed — hidden, and free to travel past the edge
of the screen, which is what a view that keeps turning needs. Leaving the mode
gives it back, and so does opening either screen: while one is up the pointer
clicks it and its motion stops steering the map.

Jumping forgives the frames where footing is uncertain. Running over a step, a
ramp lip or a seam between two brushes leaves the capsule airborne for a frame
or two at a time, so a jump is still allowed for a moment after walking off
something, and one asked for just before landing fires on landing rather than
being dropped (`coyoteTime` and `jumpBuffer` in
[omi_physics](../omi_physics/)). A jump also survives the frame rate: a capsule
that has just launched is left alone by the ground probe rather than re-seated
for having risen only a few centimetres, because on a fast machine that is all
the first frame of a jump covers. Running up a ramp is full speed too: the pace
is spent along the ground rather than along the horizon.

## The HUD, and the developer overlay

Two layers of screen furniture, and they are deliberately different things.

**The game HUD** (`--hud`, on by default) is what a player sees: an aiming
reticule in the middle, health and armour bottom-left, the weapon and its
ammunition bottom-right, the weapons you are carrying along the bottom, and
transient messages along the top. It is drawn *under* any screen that is open
and it never takes an event, so a click goes through it to the map — which is
what makes it a HUD rather than a panel. `--no-hud` turns it off, and a
`--capture` run has no HUD at all: a reference image is of the map, and a health
bar over one turns every visual comparison into a comparison of the health bar.

**The reticule belongs to the weapon**, not to the game. Each entry in
[`twitchoglc/weapons.py`](twitchoglc/weapons.py) names its own crosshair shape
and its cone of fire, and firing opens that cone — so the reticule widens by
exactly the angle a shot might now land within, projected through the renderer's
own frustum. The colours on the meters are thresholds rather than a gradient,
because what a player reads at speed is a state and not a number.

**The developer overlay** (alt + `f`) is everything a player should never see:
frame rate and frame time, the renderer's features and what the last frame cost
in shapes and draw calls, the camera's position in scene metres *and* in map units, which movement mode is in force, whether you are submerged, and the
physics world's body and contact counts. It is fed by *registered providers* —
`twitchoglc/debug.py` registers this game's, OpenGLContext registers the
engine's — so a new subsystem appears in it by registering rather than by anyone
editing it. `OPENGLCONTEXT_DISABLE_FPS_DISPLAY` decides whether it starts on
screen, which is what keeps captures clean.

The movement mode used to be named in the top-left corner of the map. It is on
the developer overlay now: a player does not want to be told the name of the
camera mode, and a developer wants that plus a dozen things it never showed.

The widgets themselves are OpenGLContext's
([docs/hud.html](../openglcontext/docs/hud.html)), because a crosshair and a bar
meter are the same in every game; what is here is what the numbers *mean*.

### Weapons, and what is a stand-in

`twitch-hud-demo` puts the whole HUD on screen over a small lit room with a
first-person weapon in your hands — the fastest way to see any of the above, and
it needs no map and no downloads:

```console
twitch-hud-demo          # 1/2/3 choose, p picks up, ctrl fires, h hurts
```

The weapon table is **declared data**: fire rate, cone of fire, ammunition type
and cost, the reticule and the model are fields, so retuning the game is editing
that table rather than editing code. What is deliberately *not* finished here is
[§7](PROJECT-PLAN.md): a shot spends ammunition, opens the cone and obeys the
weapon's fire rate, but nothing is hit and nothing is damaged yet.

**You carry every weapon in the table from the start.** Not a design decision:
nothing in a map hands a player a weapon yet — item entities are
[§6](PROJECT-PLAN.md) — and a player who spawned with one would have number keys
that could never do anything, which reads as a broken key rather than as a
feature that has not arrived. `PlayerState.starting` still spawns with one
weapon, which is what a match will want once items exist.

The models are **stand-ins**, and that is a considered position rather than a
gap: what a weapon contributes to play is its behaviour, its reticule and where
its shot leaves from, none of which is the model. Each weapon has its **own**
model, though — a weapon you switch to that looks identical to the last one
reads as a key that did nothing. They are CC0 firearms from 3dmodelscc0's
[Guns & Explosives pack](https://3dmodelscc0.itch.io/free-cc0-guns-explosives-pack)
— a Luger, a pump shotgun and an AK-47 — trimmed for the repository by
[`tools/prepare_weapon.py`](tools/prepare_weapon.py), which resamples or strips
the 2048px maps that make each source model 8–10 MB. Every piece of geometry,
its author and a link to their page are in
[`twitchoglc/assets/weapons/CREDITS.md`](twitchoglc/assets/weapons/CREDITS.md),
which is the rule for all art here and is enforced by a test. CC0 is why they
may be committed at all: a public-domain dedication with no conditions, unlike
the share-alike OpenArena content, which is fetched to a user cache and never
vendored. Replacing them is a table edit — `model`, `modelScale`,
`modelOffset` and `modelYaw` are fields of the weapon.

The weapon is drawn as **part of the scene**, on a transform put where the
camera is each frame, so it takes the map's own lighting and is occluded by
geometry the way anything else is. `twitch-hud-demo --weapon shotgun` starts
holding one, which is how the offsets above are dialled in.

## Options

| Option | What it does |
|---|---|
| `--map NAME` | which map to load when an archive holds several |
| `--spawn INDEX` | which spawn point to start at (default 0) |
| `--lightmap SCALE` | baked-lighting exposure (default 2) |
| `--content DIR` | an extra content directory to resolve textures against |
| `--list-packs` | list the downloadable content packs and exit |
| `--fetch PACK` | download a content pack by key and exit |
| `--core-textures ask\|always\|never` | offer the replacement texture pack when a map is missing core textures (default: ask) |
| `--no-physics` | free-fly only, no gravity or collision |
| `--hud` / `--no-hud` | draw the game HUD (off during a `--capture`) |
| `--headlight` | a lamp at the camera, for maps with no baked lighting |

Set `TWITCH_DEBUG_JUMP=1` to have every jump press say what the capsule thought
at the time — whether it fired, and if not whether it was airborne, crouching or
flying. A press that does nothing can fail in four places (the event queue, the
mode that owns the binding, the character, its footing) and they look identical
from the outside; this says which.
| `--shadows` | real-time shadows; off by default, as the maps bake their own |
| `--subdivisions N` | samples per Bezier patch edge on Quake 3 maps |
| `--capture PATH` | render, save a PNG, and exit |
| `--cache-dir DIR` | where downloads and unpacked archives are cached |

Two more commands come with it:

```bash
twitch-parse-bsp map.bsp     # report a map's contents without opening a window
twitch-download URL          # fetch and unpack an archive; prints the map path
```

## Content: your maps, measured against OpenArena

**The maps this is meant to render are the ones you make.** Build a level in a
Quake 3 editor — GtkRadiant, NetRadiant, TrenchBroom — compile it to `IBSP`
v46, and open the result here with your own art and your own licence terms. The
format is the interchange; existing games are how we know we read it correctly.

That is what OpenArena and the other public content are for: fifty complete,
freely-licensed v46 maps make the widest sample of the format available to test
against, so a feature a mapper reaches for is one that has already been
exercised across fifty maps rather than one. Inspecting that content — without
opening its engine source — is also what establishes that it needs **no format
support beyond what is here**:

- **No `.rscript`.** Zero, across the whole distribution. It is a Quake 3
  descendant, so materials are `.shader` files, which
  [`SPEC-Q3SHADER`](specs/SPEC-Q3SHADER.md) already covers.
- **No large lightmaps.** Every map uses the standard 128 × 128 images of
  `SPEC-BSP46 §4.13.1`, between 0 and 82 of them; the largest is 4 MB, which
  the atlas packs into a single page. There is no sidecar and no external
  lightmap file, so no sidecar support is needed.
- **All 50 base maps are `IBSP` version 46.** Face types are 95,778 polygons,
  3,346 Bezier patches, 935 meshes and 3,958 billboards — all already handled.

Measured over those 50 maps: **99% of texture references resolve, and 43 of the
50 have every drawable texture present**; loads average 0.15 s. Twenty-seven of
them have working jump pads and twenty-nine have water to swim in, which is what
makes them a coverage corpus rather than a demo. Community map packs serve the
same purpose, and are welcome for the features they exercise. The viewer will
fetch the OpenArena content for you — see [Content packs](#content-packs) — or
you can point it at an installed copy:

```bash
twitch-viewer openarena:oa_dm3            # fetched for you
twitch-viewer oa/maps/oa_dm3.bsp --content oa-textures --content oa-pak0
```

## Content packs

A pack is content the viewer can fetch for you rather than content you supply.
`--list-packs` prints them with their size, their licence and the URL they come
from, because those are what the answer turns on:

| Key | What it is | Size |
|---|---|---|
| `openarena-maps` | fifty OpenArena levels | 42 MB |
| `openarena-textures` | the art those levels draw with | 449 MB |
| `openarena-data` | base game data, and the `.shader` scripts | 91 MB |
| `quake3-core` | freely-licensed replacements for Quake 3's base textures | 187 MB |

With all three OpenArena packs, **43 of the 50 maps have every drawable texture
present** and nine texture names go unresolved across the whole set. The
`.shader` scripts in `openarena-data` are why the base data is one of them: a
great many surface names in these maps are shader names rather than file names
(`SPEC-Q3SHADER §1.2`), and without the scripts that define them they resolve
to no file however much art is on disk — maps-and-art alone leaves only 6 of
the 50 complete.

**Nothing is fetched without being asked for.** There are exactly two consents:
naming a map inside a pack (`twitch-viewer openarena:oa_dm1`) or naming the pack
(`twitch-viewer --fetch openarena-textures`) is itself the answer, since a pack
must be on disk before there is a window to ask in; anything else is asked in
the window, over the map it is about, with two buttons. A pack unpacks once per
user under `<cache>/twitch-content/<pack>` and every later run finds it there.

The OpenArena release is split, so what one map needs spans several packs:
fetching only the maps gets you geometry and baked lighting rendered in grey.
The viewer says so, names the packs that would fix it, and asks about all of
them at once — a question that has to be answered again next launch to get the
rest is a worse question. The Debian *source* tarballs are used rather than the
`.deb` packages: the upstream archive as published, with no packaging layer to
unwrap.

`openarena-oacmp1`, a community map pack, is also in Debian main and is not
registered here yet.

## Missing textures

Almost every map ships only the textures its author added and names the rest out
of the game's base content, which is not in the map's archive. A map whose
textures are missing still loads and still lights itself — it renders in grey.

Whether that can be fixed comes down to one question: **does a freely-licensed
replacement for that base content exist?** For Quake 3 it does, and the viewer
will fetch it; for OpenArena the question does not arise, since its own content
is freely licensed and complete.

The community's high-resolution pack is a deliberate *replacement* for Quake 3's
base textures — independently produced art, made to be dropped in under the same
names, and licensed to be redistributed. So a Quake 3 map can be made to look
right without touching id Software's own content at all.

The viewer names what it could not find and offers to fetch the pack that would
supply it — in the window, over the map, with Download and Not now as real
clickable buttons (OpenGLContext's [overlay
UI](../openglcontext/docs/overlayui.html); `y`/`n` still work as accelerators,
and Escape declines). The question is modal, so nothing reaches the map until it
is answered. It asks only when something is actually missing, and unpacks once
per user rather than once per run. `--core-textures always` skips the prompt, `never` suppresses the
offer, and `--content DIR` points at content you already have.

**Which pack it offers depends on where the map came from.** A map opened from
the OpenArena pack is offered OpenArena's art; anything else is offered the
Quake 3 replacement set. Offering the wrong one would download hundreds of
megabytes that cannot name a single one of the map's textures.

A pack is unpacked into a named directory of its own —
`<cache>/twitch-content/<pack>` — rather than into one more hash-named
per-archive tree, which makes it something you can find, point another tool at,
or delete on purpose. It is unpacked rather than read straight from the archive
because texture lookup lists directories to match names whose case differs from
the map's. A release that wraps its content in a version directory and a pak
directory is resolved to the level texture names are actually relative to.
`twitch-download --purge` removes it along with the unpacked maps.

Two other gaps are deliberate. A `.wal` texture is palette-indexed and the
palette is separate content this viewer does not carry, so a stock Quake 2 map
whose textures are all `.wal` renders untextured; the warning names the file.
Skyboxes are not drawn: a sky surface is a hole the sky shows through
(`SPEC-BSP38 §8.1`), and the hole shows the viewer's own backdrop.

## How it is put together

| Module | What it does |
|---|---|
| `bspfile` | the `IBSP` container both families share: header, directory, lumps |
| `q2bsp`, `q3bsp` | the two format layers: lumps as arrays, entities as objects |
| `entities` | the entity lump's text syntax, shared by both families |
| `surfaces` | `SurfaceStyle` — translucency, masking, sky, scrolling, lightmapping, stated once |
| `worldgeometry` | batched triangles in scene space, and the map-to-scene axis convention |
| `q2geometry`, `q3geometry` | each family's faces into those batches |
| `lightmapatlas` | thousands of small baked-light blocks into a few GPU pages |
| `q3shader` | Quake 3 `.shader` material scripts |
| `materials` | texture names to images, surface styles to PBR materials |
| `scene` | one shape per batch, with its lightmap page wired in |
| `jumppads` | push volumes, driven by the physics trigger system |
| `liquids` | water, slime and lava as volumes to swim in |
| `maploader` | sniff the version, dispatch, and hand back a loaded map |
| `download` | fetch and unpack archives through the OpenGLContext resolver |
| `viewer` | the window: walk, fly, capture |

A map load is around a second: lumps are `numpy` views over the memory-mapped
file rather than parsed records, geometry is built over whole arrays rather than
face by face, and the lightmap atlas is one height-sorted shelf pack of the whole
set rather than a search per rectangle.

## Where the format knowledge comes from

This viewer is BSD licensed and the Quake engines are GPL, so **no engine source
was read while writing it**. Every format constant, layout and behaviour cites a
numbered fact in one of the specifications under [`specs/`](specs/):

| Spec | Covers | Provenance |
|---|---|---|
| `SPEC-BSP38` | the `IBSP` v38 container, lumps, flags, entities, lightmaps | clean-room: written by a Reader who wrote no code |
| `SPEC-TRIGGER-PUSH` | `trigger_push`, `trigger_monsterjump`, world gravity | clean-room |
| `SPEC-BSP46` | the `IBSP` v46 container | no copyleft source: a published format reference, this project's own earlier BSD reader, and sample bytes |
| `SPEC-Q3SHADER` | Quake 3 `.shader` material scripts | no copyleft source: the published shader manual and shipped map content |
| `SPEC-Q3PUSH` | version 46 aimed jump pads | no copyleft source: entity data observed in the 50 shipped OpenArena maps, plus projectile physics |

Two further specifications, `SPEC-LTMP` and `SPEC-RSCRIPT`, were written and
implemented for Alien Arena and then retired with the code that read them; see
[`specs/README.md`](specs/README.md).

The procedure those specs were written under is
[`specs/CLEAN-ROOM.md`](specs/CLEAN-ROOM.md). If you extend this viewer and need a fact
that is not in a spec, request a spec revision — do not go and look it up in an
engine.

## Installing

```bash
pip install -e .
```

It needs `OpenGLContext` with a GLFW backend, `omi_physics`, `numpy` and
`pillow`. It does **not** need `requests` (downloads go through the
OpenGLContext resolver) or `simpleparse` (both script languages are hand-written
token scanners).

## Testing

```bash
pytest                      # the whole suite
pytest -m "not gl"          # skip the tests that open a window
pytest -m "not slow"        # skip whole-map loads and timing checks
```

Tests that need a sample map skip themselves when it is absent. The GL tests run
the viewer in a subprocess and check that a frame was rendered.

## Where this is going

[PROJECT-PLAN.md](PROJECT-PLAN.md) is the route from a map you can walk to a map
you can play in: characters and bots, weapons, sound, the HUD and debug overlay,
animated fire and water surfaces, a start screen, the acknowledgements a project
built on freely-licensed content owes, and eventually multiplayer. Nothing in it
is built yet; it records the design, the order, and which sources may and may not
be read.

The game that plan describes has a working title of its own — **Twitchy Binners**.
`twitchoglc` stays what it is: the map-loading and rendering library the game is
built on, and a component you can use without the game.

The game's own content — characters, weapons and their sounds — is **ours**,
authored in glTF and shipped with the code. What gets fetched is the levels: maps,
their textures and their ambient sound. A bare install is therefore playable
rather than grey and silent, and the clean-room wall stands only where map formats
are read.

## Surfaces that move

A `.shader` script can say that a surface animates, and every form of it a
viewer can draw is drawn. `SPEC-Q3SHADER §2.4` records the family — added
from the same published manual the rest of that spec came from, so no engine was
opened for it — and it divides by what it costs:

| Directive | What it does | Cost per frame |
|---|---|---|
| `tcMod scroll` / `rotate` / `stretch` / `scale` / `transform` | slides, turns or squeezes the image | **one uniform** |
| `rgbGen wave` / `const` | pulses the surface's colour | **one uniform** |
| `alphaGen wave` / `const` | pulses its opacity (on a blended surface) | **one uniform** |
| `animMap` | cycles the texture through frames | one texture bind |
| `deformVertexes wave` / `move` / `normal` | heaves the geometry, or bends its normals | the vertices |
| `tcMod turb` | churns the coordinates per vertex | the vertices |

The first four are why nearly every animated surface in a map is free: a
scrolling conveyor, a rotating fan, a pulsing light and a flickering screen all
cost one uniform each, however large the surface is. Only the last two touch
geometry, and those are the liquids — which is why the split is worth making
rather than deforming everything.

Every wave is a pure function of **one scene clock**, so a map's surfaces move
together rather than drifting apart. Version 38 has no scripts, so its
`SURF_FLOWING` flag produces the same value object a `tcMod scroll` does and
nothing downstream branches on which family a map came from.

The evaluation is `twitchoglc.surfaceanim` (waves, coordinate transforms,
deformation, colour) and the application is `twitchoglc.animator` (which
material field each answer lands on). Both are tested without a window: 154
tests over the numbers at known times. Against the shipped OpenArena scripts the
parser reads **1387 materials, of which 498 animate** — 226 rotations, 173
scrolls, 130 stretches, 113 moves, 106 colour waves, 70 alpha waves, 66 wave
deforms, 66 turbulences and 48 frame cycles.

Two things are deliberately left out, both because a viewer drawing **one** PBR
material per surface cannot express them: several animated stages composited
over each other (`SPEC-Q3SHADER E.1`, `E.3`), and `deformVertexes autosprite`,
which is a camera-facing billboard rather than a property of the surface.

A `--capture` run pins the animation clock so a reference image is the same
every time; without that a visual-regression gate is useless for exactly the
maps this feature is for.

## What is not implemented

Recorded as decisions rather than oversights:

- **Brush-model movers.** `func_door`, `func_plat` and friends are drawn where
  they stand and do not move (`SPEC-TRIGGER-PUSH §10` describes what a mover
  would need). On `ctf-curvy` the thing in front of the spawn that looks like a
  jump pad is one of these: a rising plate, not a push volume.
- **`func_conveyor` and the current content bits** (`SPEC-TRIGGER-PUSH §9.5`) —
  a movement-solver feature rather than a pad.
- **Buoyancy.** Swimming works — liquid surfaces are left out of the collision
  mesh so you fall in, the volumes are read from the BSP leaves, and entering
  one imposes `SwimMode` — but a swimmer is simply free of gravity rather than
  floating. `SwimMode.buoyancy` describes the fraction of gravity that should
  push back up; carrying it needs the character controller to grow a notion of
  partial gravity, which it has not.
- **Underwater tint, fog and muffled sound.** The liquid volumes are read and
  the test for being inside one is already made every frame, and the audio
  engine has the whole-mix low-pass the muffle needs
  (`OpenGLContext.audio.engine.muffle`, 0 clear to 1 underwater). Connecting the
  two — and tinting the view — is not done.
- **Sound.** OpenGLContext has a spatial audio engine
  ([docs/audio.html](../openglcontext/docs/audio.html)) on glTF's
  `KHR_audio_emitter` model, and the viewer opens no device because nothing in a
  map yet emits. `target_speaker` entities, weapon and impact sounds and the
  content resolution for them are §4's remaining half.
- **Damage.** Slime and lava are swum through exactly as water is. There *is* a
  health and armour model now (`twitchoglc/player.py`, drawn by the HUD), but
  nothing in the world reduces it: liquids do not hurt, and a shot hits nothing.
  Both are [§7](PROJECT-PLAN.md).
- **Weapons that do anything.** Firing spends ammunition, obeys the weapon's
  fire rate and opens its cone of fire, all of which the HUD shows; no ray is
  cast, no projectile travels and nothing takes damage. The models are CC0
  stand-ins named by the table as data (see *The HUD* above).
- **Visibility culling.** Neither family's visibility lump is decompressed; the
  whole map is drawn and the frustum does the culling.
- **Multi-style lightmaps.** Only the always-on style-0 block is read, which
  `SPEC-BSP38 §7.6` permits and `SPEC-LTMP §7.8` recommends given that the
  original's own multi-style path is disabled.
