# twig-bb project plan — from map viewer to arena game

**Status legend:** ✅ **Complete** — shipped · 🟡 **Partial** — core landed, named pieces
missing · 📋 **Planned** — designed here, not yet built · ⬜ **Todo** — wanted, not yet
designed · 🛑 **Shelved** — deliberately not done.

Today twig-bb loads a Quake 3 map and lets you walk around inside it. This
plan is the route from *a map you can walk* to *a map you can play in*: characters
that move under their own direction, things that can be shot, sound, and the screens
a game needs around the outside of the render loop.

Nothing in this document is built yet. What **is** built is listed in
[README.md](README.md) and summarised as foundations below, because every phase here
leans on one of them.

---

## 1. The rules this work is done under

These are not new; they are the workspace rules ([../CLAUDE.md](../CLAUDE.md)) restated
where they bite hardest on *this* plan, because three of the phases below are the
places where a shortcut would be most tempting.

**No engine source, ever.** twig-bb is BSD; the Quake engines and their descendants are
GPL. Every format fact cites a numbered fact in [specs/](specs/), obtained either from
a permitted source (published documentation, this project's own earlier BSD code, the
bytes of shipped content) or through the Reader/Implementer wall of
[specs/CLEAN-ROOM.md](specs/CLEAN-ROOM.md). Two phases below — characters and AI — are
exactly where a developer in a hurry reaches for `ioquake3`. §5 and §6 say what to
reach for instead.

**Content is fetched, never vendored.** OpenArena's art and sound are CC BY-SA 3.0 /
GPL. They are downloaded to a user cache at the user's request, exactly as the textures
already are, and no byte of them enters this repository. This is what keeps a BSD
codebase BSD while playing a copyleft-content game. §9's acknowledgements screen is the
other half of that bargain.

**Machinery upstream, rules here.** The dividing line, applied throughout:

| Belongs in… | Because | Examples from this plan |
|---|---|---|
| [omi_physics](../omi_physics/) | anything a rigid-body world should be able to answer | ray casts and shape sweeps (§7), line-of-sight queries (§6) |
| [OpenGLContext](../openglcontext/) | anything a *second* game would want identically | spatial audio nodes (§4), particle/effect system (§8), navmesh + path search (§6), the debug overlay (§2), HUD widget primitives (§3) |
| twig-bb | anything that is a rule of *this* game | weapon behaviour, damage, bot personality, match state, entity spawning, HUD content, the start screen |

When a phase below adds to OpenGLContext, it also adds to that project's tests and its
`docs/`, and gets a line in [../openglcontext/plans/PROJECT-PLAN.md](../openglcontext/plans/PROJECT-PLAN.md).
A game feature smuggled into the engine as a game feature is a bug in this plan.

**Red/Green TDD, and headless-first design.** Every phase names the part of itself that
can be tested without a window, and that part is designed to be the larger half: a
navmesh, a path, a damage calculation, a mixed PCM buffer and a HUD layout are all
data, and data is testable. The GL half is smoke-tested through the existing
subprocess-and-capture harness with the `gl` marker.

**Documentation ships with the change.** Each phase below lists the documentation it
must update. A phase is not done while [README.md](README.md) still describes the world
before it.

---

## 2. Foundations already in place

| Foundation | Where | What the phases below take from it |
|---|---|---|
| ✅ Map loading, both families | [twig_bb/maploader.py](twig_bb/maploader.py) | geometry, entities, spawn points, liquids |
| ✅ Entity lump parsing | [twig_bb/entities.py](twig_bb/entities.py) | the classnames every game object is spawned from |
| ✅ Collision mesh + character controller | [twig_bb/viewer.py](twig_bb/viewer.py), [../omi_physics/](../omi_physics/) | the navmesh's input, and the bots' bodies |
| ✅ Physics triggers | [twig_bb/jumppads.py](twig_bb/jumppads.py) | the pattern item pickups and damage volumes follow |
| ✅ Overlay UI: panels, dialogs, settings, key bindings | [../openglcontext/OpenGLContext/ui/](../openglcontext/OpenGLContext/ui/) | every screen in §2, §3, §9, §10 |
| ✅ `renderShaderOverlay` hook | [twig_bb/viewer.py:536](twig_bb/viewer.py#L536) | the seam the HUD and debug overlay draw through |
| ✅ Asset pack fetch/unpack/consent | [twig_bb/download.py](twig_bb/download.py) | §9's catalogue and progress UI |
| ✅ Quake 3 `.shader` parsing | [twig_bb/q3shader.py](twig_bb/q3shader.py) | §8's animated effects — already parsed, currently discarded |
| ✅ glTF skinning and animation | [../openglcontext/OpenGLContext/loaders/gltf/animation.py](../openglcontext/OpenGLContext/loaders/gltf/animation.py) | §5's characters |
| ✅ Declared but unimplemented `Sound` / `AudioClip` nodes | [../pyvrml97/vrml/vrml97/basenodes.py:450](../pyvrml97/vrml/vrml97/basenodes.py#L450) | §4's audio API — already specified, needs a renderer |

Two of these deserve emphasis because they change what the phases cost. The VRML97
`Sound` and `AudioClip` nodes are **already declared** with the fields spatial audio
needs (`location`, `direction`, `minFront`/`maxFront`/`minBack`/`maxBack`, `intensity`,
`spatialize`, `pitch`, `loop`), so §4 implements an API rather than inventing one. And
OpenGLContext's glTF path already does linear-blend skinning with an animation player,
so §5's characters are a content and control problem, not a renderer problem.

---

## 3. Phases

The order is chosen so that each phase can be finished, shipped and *seen* before the
next begins, and so that the phases most likely to change the design of the others come
first. §8 (fire and water) depends on nothing after §2 and can be pulled forward
whenever a rendering-shaped stretch of time appears.

| # | Phase | Status | Depends on |
|---|---|---|---|
| §2 | Debug overlay | ✅ | — |
| §3 | Game HUD, reticule and weapon HUD | ✅ | reticule, vitals, ammunition, weapon bar, messages, damage indicator, death notice, the name under the crosshair, the frag readout and the held-key scoreboard |
| §4 | Audio: the engine, and the map's ambience | ✅ | — |
| §5 | Characters: loading and animation | 🟡 | the capsule stand-in plays, and now *walks* in the player's own controller; the rig contract and glTF art remain |
| §6 | Navigation mesh, path-finding and bot AI | 🟡 | bots see, decide, fight, score, walk in a real capsule and collect what a map places; the navmesh remains |
| §7 | Weapons: hitscan, bullets, rockets, damage | ✅ | hitscan and projectiles, splash, knockback and rocket jumps, liquid damage, the death camera, and everything a player sees and hears of it |
| §8 | Fire and water shaders | ✅ | — |
| §9 | Content catalogue, downloads and the start screen | ✅ | catalogue, streamed downloads, the start screen and the level chooser; launching with no map opens the menu |
| §10 | Acknowledgements | ✅ | — |
| §11 | Multiplayer | ⬜ | §7 — **but it constrains §5, §6 and §7 from the start** |
| §12 | MD3: map decoration models | ⬜ | nothing depends on it; needs `SPEC-MD3` first |
| §13 | Our own sounds | ⬜ | §4's engine; §5 and §7 for what needs one, and their commission |

[§14](#14--content-census-measured-2026-07-27) is not a phase: it is a reference
appendix recording what the fetched content actually contains, and the recipes
that measured it. §4, §5, §8 and §9 all read from it.

---

### §2 — Debug overlay ✅

**Goal.** One toggleable panel that holds everything a developer wants to see and a
player never should, so that §3's HUD can be built out of game information only.

**Shipped (2026-07-27).**  `OpenGLContext.ui.debugoverlay` upstream, fed by
registered providers; `twig_bb.debug` registers this game's.  Alt+F toggles
it, `OPENGLCONTEXT_DISABLE_FPS_DISPLAY` decides whether it starts on screen, and
both fixed-function frame-counter draws are gone.  Sections: Frame (windowed
median rate, frame time, viewport), Render (features, and shapes/draws/instanced
groups from a new `passes/renderstats.py`), View, Map (name, family, triangles,
batches, lightmaps, missing textures), Player (mode, navigation, position in
*both* scene metres and map units, submerged, health, weapon) and Physics
(bodies, contacts).  Docs: [../openglcontext/docs/hud.html](../openglcontext/docs/hud.html)
and this repo's README.  **Triangle counts are deliberately absent** — the pass
does not know them, and a number that is not counted is not reported.

What follows is the design as it was written; it is what was built.

Before this the two were mixed and neither was quite right. The frame rate is drawn by
OpenGLContext's own frame counter
([../openglcontext/OpenGLContext/framecounter.py:95](../openglcontext/OpenGLContext/framecounter.py#L95))
through fixed-function `glOrtho`/`glPushAttrib` calls that have no meaning in the core
profile, and the movement mode is drawn by twig-bb itself in the top-left corner
([twig_bb/viewer.py:541](twig_bb/viewer.py#L541)). A player wants neither; a
developer wants both, plus a dozen things neither of them shows.

**Build.**

- `OpenGLContext.ui.debugoverlay`: a panel drawn through the existing
  `OverlayRenderer`, toggled by a key, laid out in labelled sections, and — this is the
  part that makes it worth building upstream — **fed by registered providers**. A
  provider is a callable returning name/value rows; the renderer, the physics world and
  the application each register one, so a new subsystem appears in the overlay by
  registering rather than by editing the overlay.
- Providers shipped with it: frame time and rate (from the existing frame counter, live
  rather than lifetime average), draw calls / batches / triangles submitted, shadow and
  IBL state, physics body and contact counts, character controller state (grounded,
  velocity, mode).
- twig-bb registers its own: map name and family, position in map coordinates *and*
  scene coordinates, current movement mode, submerged volume, spawn index, and later
  the bot and projectile counts from §6 and §7.
- **Retire the fixed-function frame-counter render** in favour of the provider. That
  removes a compatibility-profile-only drawing path from the core-profile renderer,
  which is a win independent of this plan.
- Keep `OPENGLCONTEXT_DISABLE_FPS_DISPLAY` working — the capture harness relies on it —
  by making it mean "overlay starts hidden".

**Testable without GL.** Provider registration and the row/section layout: a fake
provider set in, a laid-out row list out. The metrics-based layout in
[../openglcontext/OpenGLContext/hud.py](../openglcontext/OpenGLContext/hud.py) is
already pure geometry.

**Docs.** OpenGLContext `docs/` gets the overlay and how to register a provider;
twig-bb's README gains the key and loses the "the mode is named top-left" sentence.

---

### §3 — Game HUD, aiming reticule and weapon HUD ✅

**Goal.** The screen furniture of an arena shooter: crosshair, health, armour, ammo,
current weapon and the weapons held, pickup and frag messages, and a scoreboard.

**What has landed (2026-07-27).**  `OpenGLContext.ui.hudwidgets` upstream — the
`HUDLayer` (anchored, non-interactive, drawn under the overlay stack through the
same batch), `Crosshair`, `BarMeter`, `Readout` and a fading `MessageQueue`,
plus a one-pixel shadow behind every glyph and an outline around the reticule,
because a pale HUD over a white wall is a HUD nobody can read.  Here:
`twig_bb.hud` (the arrangement and the thresholds), `twig_bb.weapons` (the
declared table, each weapon naming its own reticule and its cone of fire),
`twig_bb.player` (health, armour, ammunition, what is held — a record, per
§11) and `twig_bb.controls` (weapon commands declared as `KeyBinding`s and
presented to the F6 page beside the movement modes, with no change to that
page).  The reticule opens by the weapon's own cone, projected through the
renderer's frustum, so it tells the truth about where a shot may land.
The weapon in hand is `twig_bb.firstperson`: two nested transforms, the
outer put where the camera is each frame — from the renderer's own
`placeViewAttachments` hook, which is the only point where the camera is
settled and nothing has been gathered, so the weapon is pinned in view space
rather than lagging a frame and swimming.  A held weapon is part of the scene
(map lighting, occlusion) rather than something drawn over it, which is also
why it carries a small emissive floor: a map places no dynamic lights, and a
fill light on the camera was measured to brighten the map more than the weapon.  The viewer and
**`twig-bb-hud`** both use it; the demo adds a lit room and
`--weapon <key>` for dialling in where a weapon sits.

**A player starts with one weapon** (`PlayerState.starting`) and picks the rest
off the level, which is what makes a map a circuit rather than a room — see
§6's items and B21. Each weapon has its own model, because switching to an
identical one reads as a key that did nothing. The carry-everything stand-in
(`PlayerState.carrying`) is still what `twig-bb-hud` uses, where showing
every slot is the point.

**Completed 2026-07-29.** The remaining three pieces landed together: the whole
scoreboard on a held tab and a permanent frags-against-the-limit readout in the
corner (T7, B29); the name of whoever is under the crosshair, from the same
trace a shot takes (B25); and the death screen — a red `ScreenWash` over the
world, the camera on the floor looking at whoever did it, and `Fire to respawn`
once the wait is over (B24). Hit feedback landed with §7.

Every weapon is now modelled for this game and the imported stand-ins it was
built against have gone; how the art is made is recorded in
[twig_bb/assets/weapons/CREDITS.md](twig_bb/assets/weapons/CREDITS.md).

**The structural point.** A HUD is *not* an overlay in the existing sense. The overlay
stack is modal — while a panel is up, nothing reaches the map, which is exactly right
for settings and questions and exactly wrong for a health bar. So the HUD is a
**non-interactive layer drawn under the overlay stack** through the same renderer, via
the `renderShaderOverlay` hook the mode label already uses. It never takes input; it
never blocks the map.

**Build.**

- `OpenGLContext.ui.hudwidgets` (upstream, because every game wants these): a crosshair
  primitive with the standard shapes and a configurable gap/thickness/colour, a bar
  meter, an icon-plus-number readout, and a transient message queue that fades. All
  drawn with the existing batched quad/glyph renderer.
- `twig_bb.hud` (here, because these are this game's numbers): the arrangement, what
  each field means, and the colour thresholds — health low, armour type, ammo critical.
- The reticule is a **weapon property**, not a global: each weapon in §7 names its
  crosshair and its spread, and a weapon whose spread grows while firing shows it.
  Hit feedback (a brief marker on a confirmed hit) belongs here and comes from §7's
  damage events.
- The weapon HUD shows what is held and what is selected, with the selection driven by
  number keys and the wheel, all through declared key bindings so the F6 screen can
  rebind them like everything else.
- Scoreboard on a held key, and a respawn prompt, once §6 gives anything to score
  against.
- **Nothing developer-facing goes here.** That is §2's job, and the two must not drift
  back together.

**Testable without GL.** Everything except the drawing: the layout of a HUD given a
viewport size and a game state, the threshold colours, the message queue's expiry, the
scoreboard's sort. The metrics object gives text widths without a context.

**Docs.** README gains a HUD section and the weapon/scoreboard keys; OpenGLContext's
`docs/` gains the HUD widget primitives.

---

### §4 — Audio: the engine, and the map's ambience ✅

**Goal.** A machine that can put a sound at a place in the world, and one thing
using it: the map's own ambient `target_speaker` entities, so a level sounds like
itself.

**The sounds *this game* makes — weapons, characters, impacts, pickups,
footsteps — are [§13](#13--our-own-sounds), not this phase.** They were in here
originally and that was a mistake: they share nothing with this work but the
`play()` call. This is an engine phase and a content-resolution phase; §13 is a
commissioning-and-design phase that happens to end in audio files, and it is
gated on §5 and §7 existing to have sounds *for*. Keeping them together meant §4
could not be finished until a game existed.

**What has landed (2026-07-27).** The whole upstream half: the `omi_audio`
package — the model, every gain curve, the clip cache, the mixer, the device
seam and the engine — plus OpenGLContext's scenegraph nodes and per-context
engine (`OpenGLContext.audio`), plus
[docs/audio.html](../openglcontext/docs/audio.html), a demo, and 336 tests. See
[../openglcontext/plans/SPATIAL-AUDIO.md](../openglcontext/plans/SPATIAL-AUDIO.md).

**The map's ambience landed 2026-07-28, and the phase is closed.**
[`SPEC-Q3ENTITIES`](specs/SPEC-Q3ENTITIES.md) was written first, measured from
the shipped content, with a marker legend so `[OBSERVED]`, `[DERIVED]`,
`[CHOICE]` and `[UNKNOWN]` are told apart; `twig_bb.sounds` resolves a
`noise` and `twig_bb.speakers` places the emitters. **352 of the 381
speakers across the 50 levels now sound**; the other 29 are the 28 triggered
ones (§1.6, deliberately left out) and one lava hum absent from the content.
The search machinery came out of `materials.py` into
`twig_bb.contentsearch`, shared by textures and sounds — and writing its
tests found a **path-escape**: the case-insensitive retry walked the tree
segment by segment and so climbed out of the content root by a route the join's
check never saw. That is fixed, and it reached textures too.

Three upstream defects and gaps were found and closed on the way: a finished
one-shot **restarted two frames later** (the code's own comment said it must
not); there was no way to express "play this every 30 seconds", which is what
`wait` means and what half of ambience is, so `AudioSource` gained
`repeatInterval`/`repeatVariance`; and `audio.scene.describe()` had been written
"for a debug overlay" that never registered it, so the overlay gained an
**Audio** section. A measured find worth keeping: **all 16 `*`-prefixed
speakers are triggered**, without exception, which is real evidence for the
reading that they belong to an entity's own model (§1.2.5.1).

**The data model is glTF's, not VRML97's — a change from what this section
first said.** VRML97's `Sound` and `AudioClip` nodes *are* implemented (they had
been declared and unplayed for twenty years, and their ellipsoid falloff is
expressible by nothing else), but they are not the primary model: almost no
authoring tool exports them and almost no content uses them. The model is
[`KHR_audio_emitter`](https://github.com/omigroup/gltf-extensions/tree/main/extensions/2.0/KHR_audio_emitter),
which is the Web Audio `PannerNode` model and which Blender and Godot already
export — the same reasoning that put OMI's physics schema at the centre of
`omi_physics` rather than a private one. Both are implemented on one set of
curves; it cost one function.

**Licensing constrains the backend, and it is worth being explicit.** OpenAL Soft is
LGPL, `libsndfile` is LGPL, PyAV is LGPL. None may become a hard dependency of a
BSD library here (see [../CLAUDE.md](../CLAUDE.md)). The design that avoids the question
entirely:

- **Mix ourselves, in numpy.** Attenuation, panning and the ellipsoid falloff the
  `Sound` node specifies are arithmetic we already have the tools for, and mixing a few
  dozen voices at 44.1 kHz is trivial next to a frame of rendering. This also makes the
  mixer *testable*: a mix is a numpy array, and an array can be asserted about.
- **Decode whatever the content actually ships — and do not assume that is one
  format.** This engine family is not wav-only. Quake 3's own sound effects are
  `.wav` PCM, its descendants ship `.mp3` streamed music, later engines in the line
  added Ogg Vorbis and Opus, and community archives follow whichever their engine
  supported, so a decoder list guessed from one game is wrong for the next archive a
  user opens. **§9's content survey decides the list**; until it has run, treat `.wav`,
  `.ogg` and `.mp3` as all in scope.

  Format choice is a **licensing** question and not a patent one. MP3's patents expired
  in 2017 and the good decoders for all three formats — `dr_wav`, `dr_mp3`, `dr_flac`,
  `stb_vorbis`, `minimp3` — are public domain. The trap is in the convenience
  *wrappers*: `libsndfile`, PyAV and `pydub`-via-ffmpeg are LGPL or worse, and are what
  a hurried implementation reaches for.

**The backend is `miniaudio` — decided, not a candidate — and it stays an optional
dependency.** It is one package for both halves of the problem and it is permissively
licensed where the LGPL wrappers are not, so it is the only audio package this project
takes. It is optional for one concrete reason rather than a general preference: **it
publishes no Linux ARM64 wheel**, so making it hard would turn every `linux/arm64`
deployment into a source build needing a compiler. Facts below were checked against the
1.71 release itself rather than recalled:

- **MIT**, and the bundled C is MIT/public-domain too — the wheel's own licence file
  covers the Python bindings (Irmen de Jong), miniaudio (David Reid) and stb_vorbis
  (Sean Barrett). Nothing in the chain is copyleft.
- **Every target format in one library**: `.wav`, `.mp3`, `.ogg` (Vorbis) and `.flac`,
  with both whole-file readers and streaming generators, so effects and music take the
  same path. Formats stop being a per-format dependency decision.
- **Decode normalises on the way in.** `decode_file(name, output_format, nchannels,
  sample_rate)` resamples and re-channels while decoding, so the mixer can assume one
  sample format, one rate and mono effects — and mono is what spatialising needs, since
  a stereo source cannot be panned meaningfully. This content is a mix of rates and
  channel counts, and normalising at load is where that difference should die.
- **Output is a pull-model generator.** `PlaybackDevice` drives a generator from its own
  audio thread, which is exactly the seam §4 wants: the mixer *is* that generator, the
  render loop only ever posts voice starts to it, and neither thread waits on the other.
  It must therefore be allocation-light and must never block — mix in pre-allocated
  numpy buffers, hand over frames at the boundary, and do no resolution, decoding or
  logging inside it.
- **It does no spatialisation, and that settles a design question.** There is no
  listener, no 3D sound, no engine object in the binding — verified, not assumed. The
  falloff, panning and priority in §4 are ours to write, which is what we wanted anyway:
  the VRML97 `Sound` node specifies a particular ellipsoid attenuation, and conforming
  to that is only possible if we own the arithmetic.
- **Opus is the gap.** It is the one format in this engine family's lineage that
  miniaudio does not cover, so §9's survey should count `.opus` explicitly. If the
  answer is zero — which is likely — the gap is theoretical and stays unfilled.
- **Wheel coverage, and the hole in it.** cp310–cp314 for macOS x86_64 and arm64,
  manylinux and musllinux **x86_64**, win32 and win_amd64, plus an sdist;
  `requires_python` is `>=3.8`, wider than this project's `>=3.10`. There is **no
  `manylinux_aarch64` wheel**, so a Raspberry Pi, an ARM server or a `linux/arm64`
  container — increasingly the default on Apple Silicon hosts — installs by building the
  sdist and wants a compiler for it. That is the fact that keeps this dependency
  optional: a deployment target that cannot `pip install` the package must still get a
  working viewer, and on ARM64 Linux that is not a hypothetical target. Re-check this
  when a wheel appears; the decision is a response to a packaging gap and should not
  outlive it.

**Two ways audio can be unavailable, and both end in silence.** The package may be
absent — deliberately, on ARM64 Linux or a minimal install — and a device may fail to
open even when it is present, in a container with no ALSA or PulseAudio, on a machine
with no sound card, or against a device something else holds exclusively. Both produce
**one warning and a silent run**, never an exception that reaches the user and never a
refusal to start. A machine with no sound is a normal machine, CI is one, and audio must
never be why the viewer will not start.

The import-time branch is therefore real code that must be kept working, which is the
cost of the optional dependency and is paid deliberately: the test suite runs the
package-absent path as well as the no-device path, rather than letting either rot into a
line nobody executes.

The consequence for the test suite is a good one regardless: the mixer is fed
synthesised arrays and asserted on numerically, so all of §4 except decoding and device
opening is tested with neither the package nor sound hardware anywhere in sight.

**Build (upstream — shipped).**

- `omi_audio`: a thin device seam with a `miniaudio` implementation and a null
  (silent) one, selected when the package is absent *or* no device opens — one fallback
  serving both cases, so there is a single silent path rather than two — then the parts
  that are ours: the mixer generator, a voice pool with priority-based stealing (the
  `Sound` node's `priority` field is exactly this), distance attenuation and panning,
  the listener pose taken from
  the view platform, and the `Sound`/`AudioClip` node renderers. The seam exists to make
  silence a first-class backend and to keep the mixer testable without hardware, not to
  abstract over a second audio library nobody is going to write.
- A decoded-clip cache keyed by resolved path, so a sound fired sixty times a second
  decodes once. Clips are small; music streams rather than loads.

**What `target_speaker` needs, measured rather than assumed.** §14 is the full
census; the short version is that **29 of the 50 fetched maps place one, 381 in
all**, up to 60 in `ctf_inyard`, and these are the keys they use:

| Key | Seen as | What it needs |
|---|---|---|
| `noise` | `sound/world/neonhum.wav`, `/sound/world/wind1.wav`, `*falling1.wav` | a **sound resolver**: three spellings (bare 35, leading slash 10, `*` prefix 1), searching `.wav`/`.ogg` |
| `origin` | `1368 -512 232` | the existing map→scene conversion; nothing new |
| `spawnflags` | `1` (326), absent (21), `8` (13), `5` (10), `4` (9), `0` (2) | **only bit 1 is understood** (looping). Bits 4 and 8 occur and their meaning is unknown; record them as unknown rather than guessing |
| `wait` | `47` | seconds between repeats for a speaker that does *not* loop |
| `targetname` | `target_speaker2` | triggered rather than ambient — out of scope until there is a trigger system |

Nothing there needs a new engine feature: this is a resolver, a node, and a spec.
**44 of the 46 distinct `noise` paths resolve** in the fetched packs, all to
`.wav`. The two that do not are the two interesting cases, and both will be hit
on the first map that loads: `*falling1.wav` (the `*` prefix, an entity-model
sound with no path to resolve) and `/sound/world/lava1.wav` (simply absent). The
"missing sound is a warning and a silence" path is therefore exercised by real
content immediately rather than being a branch nobody runs.

**Build (here — remaining).**

- **A sound resolver.** The texture resolver searches `textures/` roots and image
  extensions; a sound is a different search over the same packs. The `*` prefix is
  the one genuinely unfamiliar spelling — it marks a sound belonging to an entity's
  own model rather than to a path — and a viewer with no models to attach it to
  should skip it rather than guess.
- `twig_bb.speakers`: each entity becomes an `AudioEmitter` node under a
  `Transform` at its origin, with `loop` from `spawnflags` and a looping falloff
  chosen for ambience. That is the whole of the wiring; the engine needs nothing
  else. A `noise` that does not resolve is a silence and a warning, never a
  failure, because a map may name sounds from a base game that was not fetched.
- **The entity facts need a spec first.** `target_speaker`'s keys and the meaning
  of its `spawnflags` bits are observed classnames and observed behaviour, which are
  permitted sources: extend [SPEC-TRIGGER-PUSH](specs/SPEC-TRIGGER-PUSH.md) or add
  `SPEC-Q3ENTITIES`, cite it, and mark the unobserved `spawnflags` bits **unknown**
  rather than guessing — the [SPEC-Q3PUSH](specs/SPEC-Q3PUSH.md) pattern. §6's item
  table will need the same document.

**Testable without GL, without a sound device, and without the package.** The mixer
(assert on the output array), attenuation curves at known distances, panning either
side of the listener, voice stealing under pressure, `target_speaker` parsing from a
constructed entity lump, and resolution failures — all of it pure arithmetic over
arrays. Decoding and device
opening need `miniaudio`, and those tests carry a marker and skip when it is absent, the
`gl`/`sample` marker precedent this suite already uses. **The package-absent path gets a
test of its own** rather than being assumed: with the import forced to fail, a scene
with sounds in it still builds, still runs and stays silent.

**Docs.** [docs/audio.html](../openglcontext/docs/audio.html) upstream (units,
every falloff model, the three ways a sound recurs, the two silent paths and the
data-flow diagrams); here, [README](README.md)'s **Sound** section, the "no sound
device is fine" statement and the install line, and `pyproject.toml`'s
`audio = ["miniaudio"]` extra with the ARM64 wheel gap recorded beside it so a
later reader does not "tidy" it into `dependencies`. §10's `NOTICES.md` still
owes miniaudio, stb_vorbis and the dr_* decoders, listed as an **optional**
component so the notice is accurate about what a given install contains.

---

### §5 — Characters: loading and animation 🟡

**The capsule stand-in plays (2026-07-28)**, which is the part of this phase
§6 was gated on and the reason the plan said "the capsule stays beneath all of
this". A bot is drawn as a plainly-coloured capsule, is shot as a capsule, and
walks as one. Fighting was buildable before any art existed, which is what that
fallback was for.

**What remains is the whole of the art half**: the rig and clip-name contract,
the animation state machine, the Quaternius CC0 stand-ins fitted *through* that
contract, and the artist brief. None of it blocks anything now.

What follows is the design as it was written.

**Goal.** Animated humanoid figures in the map — the player's own body, and the bots
§6 will drive.

**Custom glTF characters ship first — decided.** Not "glTF is the easier of two
readers", but: *this project's own characters, authored by us, in glTF*. The renderer
already loads skinned, animated glTF with morph targets and an animation player, so
this phase writes **no format code at all** — it is a control layer plus an asset. That
is the smallest path to a bot with a body, and §6 can start as soon as the control layer
exists.

It also settles several questions elsewhere at a stroke: characters we author carry no
content licence to reason about, no clean-room exposure, no dependency on a content pack
being fetched, and no ambiguity about what may be redistributed with the project.

**What shipping our own art actually requires**, and it is the part that is easy to
under-plan when the code is the fun bit:

- **An authored rig and clip convention that we own and document.** The animation state
  machine names clips — idle, walk, run, jump, land, fire, pain, death — and those names,
  the skeleton's joint names, the up axis, the scale in metres and the attachment points
  for a weapon are a small **published contract**, not an accident of one `.blend` file.
  Write it down in the repo, because it is what lets a contributor make a character that
  works and what lets us swap ours without touching code.
- **A licence and provenance record for our own assets too** — author, tool, licence —
  since §10's notices should be able to state what the shipped art is as confidently as
  what the fetched art is.

**The final characters will be contracted, and that is a long way off — so stand-ins are
the primary content path, not a fallback.** This is the single most schedule-relevant
fact in §5, and it inverts how the phase should be built: the placeholder path is what
everything runs on for most of this plan's life, so it gets designed, not tolerated.

- **Stand-ins already exist here, proven against this renderer.** OpenGLContext's glTF
  regression roster already carries rigged, animated humanoid samples — `CesiumMan`,
  `RiggedFigure`, `BrainStem` — with blessed reference renders in
  [../openglcontext/tests/gltf_regression/renders/](../openglcontext/tests/gltf_regression/renders/).
  These load, skin and animate correctly *today*, on this code, which makes them the
  cheapest possible starting body: no new loader, no new pipeline, and a known-good
  result to compare against when something looks wrong. Their clip sets are thin, so
  expect to author or retarget the missing states rather than to find them.
- **Check the licence per asset, not per collection.** Sample-asset repositories mix
  terms model by model. Anything *shipped* with the game must be redistributable;
  anything merely *fetched* can ride §9's existing pack machinery, which already handles
  consent, caching and attribution — a stand-in character pack needs no new download
  code. CC0 game-asset sets are the low-friction source if the samples prove too thin.
- **The named CC0 source for characters is Quaternius**, whose *free* packs are CC0
  while the extended ones are paid — so **only the CC0 packs are in scope**, and the
  distinction is per pack, which is exactly the licence-per-asset care the point above
  asks for:
  [Ultimate Modular Characters](https://quaternius.com/packs/ultimatemodularcharacters.html),
  [Ultimate Modular Women](https://quaternius.com/packs/ultimatemodularwomen.html) and
  the [Universal Animation Library](https://quaternius.com/packs/universalanimationlibrary.html)
  for clips. Modular *and* animated is what makes them worth naming here: §5's real
  cost is the clip set, and a library that already carries idle/walk/run/jump/fire/pain/
  death is the thing that turns this phase into a control layer. Being CC0 they may be
  **committed** rather than fetched, on the same rule as the weapon art
  ([assets/weapons/CREDITS.md](twig_bb/assets/weapons/CREDITS.md)) — and, like every
  other piece of geometry here, credited with a link to the author's page whether or not
  the licence demands it.
  **Practical note:** both Quaternius and itch.io serve their downloads through a
  browser-driven flow, so fetching them is a manual step, not something a script here
  can do. The retargeting to *our* rig and clip names is the work; the download is not.
- **The stand-in period is how the contract gets proven, and that is its real value.**
  Wire the stand-ins up *through* the rig/clip contract above rather than around it — the
  same joint names, up axis, metre scale, clip names and weapon attachment point. Every
  mismatch found while adapting a free model is a mismatch found before an artist is
  paid to hit the same target.
- **Therefore the artist brief is a §5 deliverable, not a contracting-day task — and it
  covers §7's weapons and §13's sounds too**, since all three come from the same
  commission at the same time.
  The contract document plus a poly and texture budget, the PBR map set expected, the
  clip list with looping and timing notes, the weapon grip and muzzle attachment points
  with their scale against the rig, §13's event list and variation counts, and the
  licensing terms — work-for-hire or a licence
  compatible with a BSD project, stated before work starts rather than negotiated after.
  Writing it while the stand-ins are being fitted costs almost nothing and makes the
  commission both cheaper and likelier to arrive usable.
- **Swapping a character must be configuration, not code.** If replacing the stand-in
  with the commissioned model means touching Python, the contract was not doing its job.
- **The capsule stays** beneath all of this, for the case where nothing resolves at all —
  §6 must remain developable when there is no art whatsoever.

**MD3 leaves this phase entirely.** Its justification has narrowed twice — characters
are ours, and §7's weapons are ours — so what is left of it is map decoration, which is
a rendering-completeness job and not a characters job. It is now **§12**, a later task
with no phase depending on it.

**Build.**

- `twig_bb.characters`: a character is a scenegraph subtree plus a
  `CharacterController` capsule plus an animation state machine. The state machine —
  idle / walk / run / jump / land / fire / pain / death, driven by the controller's own
  velocity and ground state — is the part that is genuinely shared between the player
  and the bots, and it is the part worth getting right first.
- Third-person and first-person views of the same character, because a first-person
  weapon (§7) is a bone on the same rig and a bot seen across the room is the same asset.
- Model resolution goes through the existing content resolver, and a character that
  will not resolve falls back to a plainly-drawn capsule rather than to an exception. A
  bot with no art is still a bot, and §6 must be developable before §5's art exists.

**Testable without GL.** The animation state machine against synthetic controller
states, clip selection at boundary velocities, attachment-point transforms, and the
fallback to a capsule when a model will not resolve. No format-reader tests, because
this phase adds no format reader.

**Docs.** README gains a characters section; the rig, clip-name and attachment-point
contract is documented in the repo as the thing a contributor authors against; the
shipped art gets its author, tool and licence recorded for §10.

---

### §6 — Navigation mesh, path-finding and bot AI 🟡

**Bots fight (2026-07-28).** The **ray cast landed in
[omi_physics](../omi_physics/)** first, because §6 and §7 turn out to want the
same query for different reasons: `raycast.raycast` gives the nearest hit with
its point and a normal facing back along the ray, and `line_of_sight` is the
cheaper question a bot asks many times a frame. Sphere, box, capsule and
trimesh are solved exactly; a convex hull is **named rather than guessed at**
(`unsupported_shapes`), because a prop you cannot shoot is a thing to know
about and a wrong hit point would be blamed on the weapon. A level's triangles
are transformed once and kept, which took a cast on `oa_dm1` from 1.9 ms to
0.69 ms.

`twig_bb.bots` is the mind. **A bot emits the same per-tick command record a
key press does and writes nothing**, which is §11's first seam and is what lets
a whole fight be run in a test. The difficulty is a declared node with typed
fields, and the range is the axis the bot is built along: near-passive walks
about and does not shoot, nightmare answers a sighting in 0.15 s and is a
degree off. **The senses do not scale** — every rung uses the same
`perceive`, through the same line of sight the player's own shots go through.

**The ladder is verified headlessly**, as the plan asks: `tests/test_ladder.py`
plays whole matches and asserts the ordering holds without ever asserting *how*
it was achieved. Measured over four 45-second matches per pairing: nightmare
beat easy 64–0, hard beat medium 41–6, medium beat easy 8–0, and medium against
medium was 8–7.

**Bots walk in the player's own capsule (2026-07-29).** `twig_bb.walkers`
gives each of them a `CharacterController` with the same proportions, step
height, slopes, ground snap and impulse the player has, at a slower pace — so
anywhere a player can go a bot can follow, a bot slides along a wall it meets at
an angle instead of stopping dead, and a burst throws one upward as well as
sideways. Before that a bot was a position with one ray probe ahead of it, which
is what B18's vibrating and sinking was.

**Items landed with it (2026-07-29).** `twig_bb.items` reads what a map
places and hands it out; see B21 and `SPEC-Q3ENTITIES §3`. A bot picks things up
exactly as a player does, because a circuit that existed for only one of the
people in a level would not be a circuit.

**What remains is the navmesh.** A bot walks a heading and no longer sticks on
what it meets, but it does not *route* around one. Which is exactly what the
phase said the navmesh is for, and the bots being playable without it is what
makes the navmesh a next step rather than a prerequisite.

What follows is the design as it was written.

**Goal.** Opponents that move through the map on their own — around corners, up ramps,
onto jump pads, toward items — and fight.

**The clean-room decision, stated once and up front.** Quake 3 ships pre-computed bot
navigation data alongside its maps, and its bot behaviour lives in the engine's GPL
source. **We use neither.** Not the navigation files, not the behaviour code, not a
translation of either. This is not only a licensing answer; it is the better
engineering answer, because we already hold something the original had to bake offline:
a collision mesh, in memory, at load time. Generating navigation from our own collision
mesh gives us maps the original never baked, regeneration when geometry changes, and no
dependency on content we may not read.

**Build.**

- `OpenGLContext.nav` (upstream — a navmesh over a collision world is engine machinery,
  not a rule of this game):
  - **Generation**: walkable-surface extraction from the collision mesh by slope and
    clearance, then region growing and polygonisation, parameterised by the character
    capsule's radius, height and step height so the mesh matches the body that will walk
    it. Built at load time, cached against the map's hash so the second launch is free.
  - **Search**: A* over the polygons with a string-pulled path through the portals, plus
    local steering and dynamic avoidance so two bots in a corridor do not grind.
  - **Off-mesh links**: a jump pad is an edge in the graph whose traversal is "stand
    here and be launched", and the arc is already solved by
    [twig_bb/jumppads.py](twig_bb/jumppads.py) per
    [SPEC-Q3PUSH](specs/SPEC-Q3PUSH.md). Teleporters and jumpable gaps are the same
    idea. This is where a navmesh earns its keep on these maps; a mesh that stops at
    the edge of a jump pad describes a game nobody plays.
  - **Debug rendering** of mesh, links and the current path, registered as a §2 provider.
- **A ray cast in [omi_physics](../omi_physics/)** — there is none today, and §6 needs
  it for line-of-sight just as §7 needs it for hitscan. One implementation, in the
  physics layer, over the existing broadphase tree: ray-vs-AABB down the tree, then
  ray-vs-triangle in the leaves. It also retires the five-ray AABB approximation the
  character controller's void check currently uses.
- `twig_bb.bots` (here — this *is* the game): perception (what a bot can see, gated
  by the ray cast and a field of view), a behaviour tree or utility selector over the
  goals an arena bot has (fight, take cover, get the item, get the weapon, patrol), and
  aim with human-plausible error and reaction time. Bot personalities are **our own
  design and our own numbers** — do not read anyone else's, including the
  character-parameter files shipped as content.

**Difficulty spans near-passive to nightmare — decided, and it shapes this phase.** A
range that wide is not a multiplier bolted on at the end; it is the axis the whole bot
is built along, so it is specified here rather than tuned in later.

- **A difficulty is a declared parameter set, not a branch in the code** — a node with
  typed fields like the movement modes and §7's weapon table, with named presets from
  near-passive up to nightmare. Data, so §9's start screen and the settings screen can
  present it, so a match can mix difficulties, and so the numbers can be tested.
- **What scales**: reaction time before responding to a new sighting; aim error and how
  fast it converges onto a moving target; whether shots are *led* rather than aimed at
  where a target is now; how far and how often the bot looks around; decision cadence;
  aggression and the weighting between fighting and surviving; movement skill —
  strafing, dodging, using the pads §6 already links; and, at the top, **item control**:
  a nightmare bot times item respawns and denies them, which is what high-level play in
  this genre actually is. That last one is why §6 reads item respawn intervals from the
  entity lump — the timers are already there.
- **What must never scale**: the senses. No seeing through walls, no hearing what a
  player did not make audible, no knowing where a player is without having perceived
  them, no silent health or damage multipliers. Every difficulty uses the *same*
  perception code and the same rules; only the quality of the seeing, thinking and
  aiming changes. A bot that cheats is not difficult, it is annoying, and once one
  hidden advantage is permitted the scale stops meaning anything.
- **Near-passive earns its place twice**: as a genuine setting for someone who wants to
  explore a map with company, and as the **test fixture** for everything else — a bot
  that walks its path and does not shoot is how §6's navigation is verified without
  combat in the way.
- **The scale is testable, and cheaply.** Run bot-versus-bot matches headlessly and
  assert the ordering holds: a nightmare bot beats a hard bot beats a medium bot, over
  enough matches to be more than noise. That single harness validates the entire range
  in a way that watching a match never can, and it catches the classic regression where
  a tuning change silently inverts two rungs of the ladder.
- Items and spawns come from the entity lump: the `item_*` and `weapon_*` classnames,
  their respawn intervals and what they grant. Observed classnames and observed
  behaviour are permitted sources; the facts go in a spec (extend
  [SPEC-TRIGGER-PUSH](specs/SPEC-TRIGGER-PUSH.md) or add `SPEC-Q3ENTITIES`) and the
  code cites it.

**Testable without GL, and this is the phase where that matters most.** A navmesh is
data: generate one from a constructed collision mesh and assert its connectivity;
search it and assert the path; place a bot and assert its goal choice given a synthetic
world state. Nearly all of §6 can be red/green tested with no window at all, and it
should be — a bot debugged only by watching it is a bot debugged slowly.

**Docs.** README gains a bots section; OpenGLContext `docs/` gains the navmesh (its
parameters, its cache, its limits); omi_physics gains the ray cast API and its docs;
the entity facts gain their spec.

---

### §7 — Weapons: hitscan, bullets, rockets, damage ✅

**Goal.** Things that can be fired, that travel or hit instantly, that hurt what
they hit, and that push what they hurt — and, the half that decides whether any
of it reads, everything a player *perceives* of that happening.

**What landed (2026-07-28).** All nine steps of the plan below, in the order it
set out, which was the order a player notices things missing rather than the
order the machinery suggests.

**And what a playtest then found (2026-07-29).** Nine defects, all of them
things the suite could not have caught because they were about what a person
*sees*: B18–B29 below carry each one and what it turned out to be. Three are
worth naming here because they changed the design rather than a number. A
direct hit from a splash weapon is now lethal on its own (B20) — the victim is
deliberately left out of the burst, so that one number is the whole of what a
direct hit costs and at less than a life it was not worth aiming. Death takes
the camera and the trigger is what ends it (B24), because a countdown that
returns a player while they are reading the scoreboard puts them somewhere they
were not looking. And the frame loop grew a **testable seam**:
`twig_bb.rules.Rules` is everything that *happens* in a tick, so it can be
played out against a constructed world with no window — the two worst bugs this
game has had were both a line inside `OnDraw` that no test could reach, and
everything added since is above that line.

**A shot reports everything it did.** `combat.Hit` names a combatant *or* the
world (an empty `target`, documented rather than conventional) and carries the
`SurfaceStyle` it met. Getting that surface needed a fact the physics world was
throwing away: `omi_physics.raycast.RayHit` now reports **which triangle** of a
trimesh it struck, and `twig_bb.collision.MapCollision` pairs the map's
collision mesh with a `SurfaceIndex` built from the same batches in the same
order — a mesh and an index that could be handed around separately would one day
describe different maps.

**Two new events, and one loop that reads them.** `Fired` (who, what, from
where, along what) and `Impact` (where, the normal, the surface, whether it met
a person) join `Damaged`/`Death`/`MatchOver` on `Arena.drain()`, emitted for
bots exactly as for the player. `twig_bb.feedback.Presenter` is the single
reader, and it fans out to the HUD, the sounds and the effects — so a bot's shot
and the player's reach the screen by one road and nothing in the rules can reach
a widget. A test parses `arena` and `combat` for an import of the presentation
and fails if it finds one.

**What a player gets back.** A directional damage wash at the screen edge the
hit came from (`DamageIndicator`, upstream with the other HUD widgets, because a
directional damage indicator is the same thing in every game); health and armour
meters that *flash* when they fall, and only when they fall; a death notice
naming what killed you and counting down honestly to the respawn. Impact effects
chosen by the surface — metal sparks, everything else puffs, a person gets its
own bright brief burst — through one emitter per kind bursting in many places,
which needed `ParticleEmitter.burst_at()` upstream, and `burstOnStart` to stop
every event-driven emitter going off at the world origin when a level loads.
`--effects full|reduced|off` scales the particle counts and **cannot** change
play.

**Sound, and it is ours.** Weapon fire, an impact on the level, an impact on a
person, a death and a burst — and the three that matter are chosen to be told
apart with the eyes shut, since they answer three different questions. A burst
is placed even when it is the player's own, unlike their weapon: a burst
happens *somewhere*, and that is the whole of what anybody needs to know. Every voice is
**synthesised** through `omi_audio.synth` from numbers declared in
`twig_bb.combatsound`, so the game ships with a full complement of sound and
no audio files and nothing to check under CLEAN-ROOM; a voice may name a file
instead, which is how commissioned content replaces a stand-in. The player's own
weapon is non-positional and everybody else's is placed at the muzzle.

**Projectiles, and what they cost.** `twig_bb.projectiles` steps everything
in flight as numpy arrays, **swept** through `raycast` each tick so nothing
tunnels; a rocket and a grenade differ in three declared numbers (gravity,
bounce, fuse) and in no code. Measured at ~30&nbsp;µs per projectile per tick:
0.5&nbsp;ms for the sixteen a busy match holds, 9&nbsp;ms for three hundred.
`twig_bb.blast` answers each detonation — falloff by a declared curve, cover
through a ray cast, the candidate set bounded by distance *first* (B11) — and
leaves an unspent impulse on the combatant. The player's goes into the character
controller's own `apply_impulse`, the same one a jump pad uses, which is what
makes **rocket jumps** work; self-damage at half is what makes taking one a
decision.

**Liquids hurt.** `liquids.LiquidHarm` bites every 0.4&nbsp;s from the same
volumes the swimming uses, and the death carries the liquid's name as its cause
so the line reads truly and the frag-off rule applies without inventing a
killer.

**The bots use all of it.** Two new `Difficulty` fields — `leadsTargets` and
`blastSense` — put weapon choice and self-preservation on the ladder rather than
beside it: a bot leads a crossing target by a velocity it *observed*, and keeps a
projectile's own burst radius plus a margin before firing one, scaled by its
rung. A careless bot will still rocket a wall in its own face, which is what the
bottom of the ladder is for. `tests/test_ladder.py` gained a whole-loadout match
driven through the production wiring, so a regression that broke the wiring and
not the rules is caught.

**Fixed on the way**, all three found by *playing* a captured match rather than
by any test:

- `combat.stage` added a body and a shape to the physics world **per shot** and
  could not take them out again — a world that grew for the length of the
  match, with every ray cast walking every dead body in it. It is a reused pool
  now, and 200 shots leave one body where they used to leave 200.
- **`Arena.respawn` handed out a new `PlayerState`.** Everything that reads a
  player's state holds that object — the HUD, the input path — so from the
  player's first death the HUD showed a corpse's nought health for the rest of
  the match. It is restored in place now, which is what the "one record per
  person" rule in `Combatant` always meant.
- **The HUD was being fed two clocks.** The layer is ticked with
  `time.monotonic` and the game marked hits with `time.time`, so every fade was
  the difference between them: about fifty years, which drew a damage wash at
  an alpha of a hundred million and a hit mark that never went away. There is
  one `hud.now()` now, and a test that says so.
- **The presenter was bound once and the match was built twice.** `_buildMatch`
  runs at start-up (the menu needs a match) and again when a level is loaded,
  and each build makes a fresh arena, a fresh set of emitters and a fresh
  projectile batch; the presenter captured the *first* set. Every effect was
  then born into emitters that were not in the scene — never stepped, never
  drawn — and the death notice read a match nobody was playing. From inside the
  game that is a weapon that does nothing at all. `_bindPresenter` now runs from
  both places, and `TestTheMatchWiringStaysInStep` asserts the objects match.
- **A particle emitter was bounded by where its node is, not where its
  particles are.** `burst_at` exists so one emitter can burst anywhere, and the
  frustum filter was culling the whole system whenever the scene origin was off
  screen — which in a level is almost always.

- **Nothing was bound to the mouse.** Firing was `ctrl`, held — and in this
  genre the trigger is the left mouse button, so a player clicking on a bot saw
  no shot, no sound and no ammunition move, because no shot was taken. The
  cause ran deeper than a missing binding: the input sampler was fed keyboard
  events only, so *no* binding could name a mouse button. A button now carries
  a name in the same vocabulary keys use (`<mouse-0>`), the dispatch feeds it
  to the sampler, and `FIRE` lists it beside `ctrl` — which means the F6
  binding page can present and rebind it like anything else.

- **A wheel's click is not always 1.0.** GLFW reports scrolling as a
  continuous offset with no count of detents, and its Wayland backend divides
  the protocol's 15.0 by ten: one click reports **1.5**. Summing that against
  an assumed 1.0 made every *other* click scroll twice — 1.5 is one notch with
  half of one carried, and the next 1.5 makes 2.0 and fires two — which is a
  weapon wheel that jumps two and a menu that skips every other entry. The size
  of a click is learned from what arrives now, with
  `OPENGLCONTEXT_DEBUG_WHEEL=1` to say what a platform reports.

**And the tests that let those through have been fixed too.** The GL smoke
tests ran the *default* renderer while the viewer forces `pbr`, so they passed
while the game showed nothing; they now run the game's own renderer, and one of
them puts the camera four hundred metres out, which is where a player stands.

**What is deliberately not here**, recorded in the README as decisions: decals (a
particle burst delivers most of the readability and a decal system is real work
— do it when playing says it is wanted), first-person weapon animation (it
arrives with §5's commission), footstep and pickup sounds (neither has an event
to hang on yet), and vertical knockback on bots (a bot is a position that walks
rather than a body that falls, so an upward shove would leave one in the
ceiling; the player, who *is* a character controller, is shoved in every
direction).

---

What follows is the plan as it was written, kept because it is the argument for
the ordering and the ordering is the part that was load-bearing.

**Hitscan, damage and scoring play (2026-07-28).** `twig_bb.combat` is what a
shot *does*: a trace per pellet, scattered over the spherical cap of the
weapon's own cone — the same number the reticule is drawn from, so a shot
scatters exactly as widely as the crosshair says — seeded, so a shot is
reproducible from its inputs. Combatants are staged into the physics world as
**capsules**, the same shape the character controller walks in, so what can be
hit is what can walk and there is no second idea of where somebody is.

`twig_bb.arena` is the match: id-addressed combatants, armour before health,
deaths, respawns, frags (and a frag *off* for killing yourself or falling in
the lava, since otherwise the fastest route to the top of the scoreboard is the
lava), a scoreboard and the two limits that end it. It emits `Damaged`, `Death`
and `MatchOver` and draws nothing; a test greps the module for a wall clock,
because time arrives through `advance()` and that rule is invisible once broken.

Fixing this found a defect in `PlayerState.take_damage`: it reported *what was
aimed* rather than what landed, so a 500-damage hit on a target with 40 health
left would have put 500 on a HUD.

**What remained at that point**: everything a player can *perceive*, plus
projectiles, splash damage and knockback, and liquid damage. The next steps
below were the route, and are the argument for the *order* they were taken in —
which was the order a player notices something missing, not the order the
machinery suggests. All of them have landed; see "What landed" at the top of
this section.

---

#### The route that was taken, and why in that order

*Kept as written, because the argument for the ordering is the part worth
having: every step below has landed, and what each turned into is described in
"What landed" above.*

**Where this started from, measured (2026-07-28).** The rules were correct and
the presentation did not exist. A shot fired at a bot two metres away landed
and did its damage in every direction tested, and the arena raised `Damaged`,
`Death` and `MatchOver`. What a player got back was one mark on the crosshair.
Being shot, killing somebody, being killed, and hitting a wall were all
indistinguishable from firing into the air. That was B17, and it is why a
working fight read as a broken one.

The ordering below is deliberate and is **not** the order the machinery
suggests. It is the order a player notices things missing. Projectiles are the
most interesting engineering here and are step 6, because a rocket nobody can
hear or see land is worth less than a pistol that thumps.

Every step is red/green with no window, save the GL smoke tests called out at
the end. Each names what it can be tested against, because a step that cannot
say that is a step that will be tested by playing.

**Step 1 — a shot reports everything it did, not only who it hurt.**
`combat.fire` currently drops any trace that meets the level: it `continue`s
when the ray's body is not a combatant, so a wall impact leaves no trace in the
return value. Nothing downstream can draw a decal, play an impact sound, or
tell a miss from a hit on stone. **This is the single blocking change** —
impact effects, impact audio and (later) splash origins all wait behind it, and
it is why the two features the player asked for are one piece of work.

- `Hit` grows a way to say *what* was hit: a combatant id, or the world. An
  empty `target` is the obvious spelling and needs no new type, but it must be
  a documented part of the record rather than a convention callers rediscover.
- `Hit` already carries `point` and `normal`, which is what an effect is
  oriented from. It should also carry the **surface style** the trace met —
  `worldgeometry` knows it, and it is what lets an impact on metal differ from
  one on flesh without a second lookup. `SurfaceStyle` already reaches the
  physics mesh, so this is plumbing, not discovery.
- A trace that meets nothing at all is still not a `Hit`; a miss is an empty
  list, and the *fire* event below is what a weapon always emits.
- **Tests:** a shot at a wall returns one hit with no target; a shot at a
  combatant returns one with a target; a shot into the sky returns nothing;
  every pellet of a shotgun is reported separately, so eight pellets that hit
  make eight impacts rather than one.

**Step 2 — the events a fight emits.** Presentation must not read the rules'
state, and the HUD must not be written from the shooting code (§11). Today
`_shotLanded` reaches into the HUD directly, which is fine for one caller and
wrong as a pattern: bots fire too, and the player has to hear and see *their*
shots.

- The arena already emits `Damaged` / `Death` / `MatchOver`. Add the two a
  presentation layer cannot infer: **fired** (who, which weapon, from where,
  along what) and **impact** (where, the normal, the surface, and whether it
  met a person). Both are facts about the world, not about the player, so both
  are emitted for bots as well and the presentation decides what is worth
  showing.
- These join the same `drain()` stream, so one loop turns events into effects
  and sounds, and a replay or a network client sees exactly what the local
  player saw. `game.messages` already reads that stream; it becomes one of
  several readers rather than the only one.
- **Tests:** a bot firing produces a fired event; an impact event carries the
  surface it met; nothing in the presentation path is reachable from the rules.

**Step 3 — the feedback a player needs most: being hit.** Ordered first among
the effects because it is the one whose absence makes the game read as broken.
Taking damage with no response is why "nothing happens when I'm shot".

- A **damage indicator**: a brief directional wash at the screen edge, from the
  bearing of `Damaged.by`'s position relative to the camera — direction is the
  part that is actually useful, because it is what tells a player to turn.
  Intensity from the fraction of health lost.
- The HUD's health and armour readouts should *react* rather than merely
  update: a number that changes silently in the corner is not feedback.
- **Death:** the view stays where it was killed (already true), the gun stops
  answering (already true), and the player is told they are dead and that they
  are coming back — a respawn timer is honest and stops a player wondering
  whether the game has hung. `arena` already knows the time remaining.
- **Tests:** the bearing computed for a shooter behind, beside and in front;
  intensity scaling with damage; the indicator decaying to nothing; the death
  screen appearing and clearing on respawn. All arithmetic and state, no GL.

**Step 4 — audio.** The other half of what was asked for, and cheap once step 1
and step 2 exist: it is a listener on the event stream.

- **Three distinct sounds, because they answer three different questions**: the
  weapon firing (did my input register), an impact on the world (where did that
  go), and an impact on a person (**did I hit them**). The third is the one
  that carries information a player acts on, and it must be unmistakable
  against the other two.
- Plus death, and — from step 6 — an explosion, and a projectile in flight,
  which is what makes an incoming rocket survivable.
- The player's own weapon is **not** positional; everybody else's is. A gunshot
  from the shooter's position is how a player locates an opponent they cannot
  see, and it is one of the few sounds in this genre that is genuinely load
  bearing.
- The engine already exists: `AudioSource` nodes in the scene, updated per
  frame by `update_scene_audio`, positioned and panned. What §7 adds is
  one-shot sources that are placed, played and reclaimed — a fixed pool, since
  a firefight can ask for a dozen a second and allocation per shot is a stutter.
  The pool's voice-stealing rule matters and is already written down: a
  finished non-looping source stays finished and only a looping one may retake
  a voice.
- **Sounds are content, and content has a licence.** CC0 or our own recordings.
  Anything share-alike is fetched to the user cache and never vendored, per
  CLEAN-ROOM. The weapon table names its sounds as data, like its model.
- **Tests:** an event produces a request to play the right sound; the player's
  own fire is non-positional and another's is placed at the shooter; the pool
  reclaims and does not grow; a missing sound file is a silent shot rather than
  a crash — a game must not die because content is absent, which is the same
  rule the texture resolver follows.

**Step 5 — impacts and blood.** Now that there is somewhere to hang them.

- An **impact effect** at `Hit.point`, oriented by `Hit.normal`: a brief spark
  or dust burst from §8's particle system, which is shipped and instanced.
  Chosen by the surface the trace met, so stone puffs and metal sparks.
- A **decal** is the longer-lived half and is a separate decision: a decal
  system is real work (projection onto the geometry under the point, a budget,
  a fade) and the particle burst delivers most of the readability. **Do the
  burst first and judge whether the decal is wanted**, rather than assuming it.
- A **character hit** gets its own effect, and it must be legible across a room
  at speed — that is the job it does. Stylised and bright rather than
  realistic; §8's presets already cover this shape of burst.
- **The intensity setting filters presentation only and cannot change play.**
  Full, reduced, off. This is safe precisely because these effects ride events
  the simulation emits anyway, and it is what lets two players set it
  differently.
- **Tests:** the effect chosen for a given surface; the orientation derived from
  a normal; the intensity setting suppressing effects without altering any
  damage, event or score.

**Step 6 — projectiles: rockets and grenades.** The step that most changes how
the game plays.

- **A batch, not bodies.** A projectile is a position, a velocity, a radius and
  an owner in numpy arrays, stepped together. Hundreds must cost nothing. Drawn
  through the instanced path.
- **Swept, never tunnelling.** Each tick, cast from where it was to where it
  wants to be — `omi_physics.raycast`, which now has a spatial index and is
  ~0.26 ms for a bot's whole tick, so a batch of casts is affordable. A rocket
  as a rigid body is a rocket that passes through a wall at speed.
- **A rocket and a grenade differ in three declared numbers, not in code**:
  gravity (a rocket ignores it, a grenade does not), what happens on contact
  (detonate, or bounce with a restitution and a fuse), and the fuse itself. Two
  weapons that need two code paths is a sign the table is not carrying the
  design.
- The owner matters for the first few metres: a projectile must not detonate on
  the muzzle of the player who fired it.
- **Tests:** a projectile crossing a thin wall in one tick still hits it; a
  grenade falling under gravity and bouncing to rest; a fuse detonating in the
  air; a rocket ignoring its owner at the muzzle and not later; a batch of
  several hundred stepping within budget.

**Step 7 — splash damage, knockback and rocket jumps.**

- **Falloff with distance** from the burst centre, by a declared curve, to a
  declared radius. The numbers are ours, so the table is the design document.
- **Blocked by geometry**, through a ray cast from the burst to each candidate:
  a rocket round a corner must not kill. This is where `line_of_sight` earns
  its keep, and the O(n²) note in B11 applies — a burst tests everybody in
  radius, so bound the candidate set by distance before casting.
- **Knockback as an impulse into the character controller**, which is what makes
  rocket jumps work — and rocket jumps are why this genre exists. A shooter is
  pushed by their own rocket; that is the feature, not a bug to guard against.
  It wants a real look at how an impulse composes with the controller's
  grounded state, because a jump that only works when airborne is not the move.
- Splash hurts its owner. Self-damage is what makes a rocket jump a *decision*.
- **Tests:** damage at known distances against the declared curve; a wall
  between burst and target reducing it to nothing; an impulse of a known size
  producing a known displacement; a self-inflicted rocket jump gaining height;
  the frag-off rule already in `arena` covering a self-kill.

**Step 8 — liquid damage.** Slime and lava currently harm nobody, and the
README says so. The volumes and the "which liquid" query already exist
(`liquids.kind_at`, B3). This is a periodic damage tick while submerged, with
its own damage type so the death message reads correctly and the frag-off rule
applies. Small, and it closes a documented gap.

**Step 9 — the bots use all of it.** A bot that only ever fires hitscan is not
playing the same game. Leading a target with a slow projectile, and not firing
a rocket at a wall two feet away, are both *difficulty*: the near-passive bot
may cheerfully blow itself up and the nightmare bot must not. This is a
`SkillSet` question, which is where the difficulty axis already lives.

**GL smoke tests, and only these.** A rocket appears and moves; an explosion
draws; an impact effect appears at the right place on a real surface; the
damage indicator renders. Everything else above is testable headless and should
be tested that way — the existing §6 ladder test (nightmare beat easy 64–0) is
the model.

**Docs, shipped with the work, not after it.** README gains a weapons section
and loses the "nothing here models health" line. The weapon table's units and
defaults are documented because they are tunable and because, with a custom
loadout, **the table is the only place the game's design is written down**. The
audio settings and the effects-intensity setting are documented with their
units and defaults. Sound provenance and licences are recorded where the
content is recorded.

---

What follows is the design as it was written.

**Goal.** Things that can be fired, that travel or hit instantly, that hurt what they
hit, and that push what they hurt.

**The weapons are our own — decided.** Custom glTF models, our own behaviour, our own
damage. Not a recreation of a known loadout, so "right" means *plays well*, settled by
playing rather than by comparison, and no number in the table below is answerable by
looking anything up. This closes the provenance question for §7 completely: there is
nothing here to have a spec about, because there is no external artefact being matched.

It also means weapons follow §5's asset contract rather than needing one of their own —
a first-person weapon is a glTF model attached to the rig's weapon joint, which is
exactly what that contract already has to describe.

**The models come from the same commission as §5's characters, at the same time** — so
until then, placeholders. The good news is that a weapon placeholder is *genuinely
adequate* in a way a character placeholder is not, and that asymmetry is worth relying
on deliberately:

- What a weapon contributes to play is **its behaviour, its reticule, where its
  projectile leaves from and what its effects and sounds do** — none of which is the
  model.  The sounds themselves are §13; what §7 owns is the *event* each shot
  emits. A blocked-out shape at the right size, with the right muzzle point, plays
  correctly. A character reduced to a capsule does not read at all, which is why §5's
  stand-in problem is the harder one.
- **§7 therefore never waits on art**, and should not be scheduled as if it might.
- Because one commission covers both, the **brief written in §5 has to cover weapons
  too**: first-person and third-person detail expectations (a weapon held at the camera
  is seen far closer than one across a room), the muzzle and grip attachment points,
  scale against the character rig, and any per-weapon clips — a fire action, an idle
  sway. Those are cheap to specify while writing the character brief and awkward to add
  to a commission already underway.
- The weapon table names its model as data, so replacing a blocked-out shape with the
  commissioned asset is a table edit, not a code change.

**Build.**

- `twig_bb.weapons`: a declared table — fire rate, spread, damage, splash radius and
  falloff, projectile speed, ammo type and cost, knockback, reticule, model, sounds.
  Declared as nodes with typed fields, like the movement modes, so the settings and
  binding screens can present them and a variant can retune the game by setting fields
  rather than by editing code. Because the numbers are ours, the table is the design
  document: it must be readable, it must carry units, and a change to it must not need a
  code change. Expect to iterate on it far more than on the machinery under it.
- **Hitscan** through the §6 ray cast, with the impact point, normal and surface style
  in hand — which is what lets an impact pick its decal and its sound.
- **Projectiles** as lightweight kinematic bodies rather than full rigid bodies: a
  rocket is a position, a velocity and a radius stepped against a swept ray each
  physics tick. Hundreds of them must cost nothing, so they live in a numpy array and
  step as a batch, and they are drawn with the instanced path
  ([../openglcontext/OpenGLContext/scenegraph/instancedgl.py](../openglcontext/OpenGLContext/scenegraph/instancedgl.py)).
  A rocket that is a rigid body is a rocket that tunnels through a wall at 900 units a
  second; a swept ray does not.
- **Damage**: a health/armour model, splash damage falling off with distance and
  blocked by geometry (another ray cast), knockback as an impulse into the character
  controller — which is what makes rocket jumps work, and rocket jumps are why this
  genre exists. Damage events feed §3's HUD and §6's bot perception.
- **Gore is stylised, and that makes it an effects question rather than a rules one.**
  A hit and a death emit events; the presentation layer answers them with §8's particles
  — bright, brief, readable bursts and stylised gibs, chosen so a player can *read* a
  confirmed hit across a room at speed, which is the job this feedback actually does.
  Because it rides events the simulation emits anyway (§11's seam), an intensity setting
  — full, reduced, off — filters presentation only and **cannot change play**, which is
  what makes it safe to offer and safe for two players to set differently. §5's art
  contract carries the death clips and gib pieces this implies.
- The liquid volumes gain their damage: slime and lava currently harm nobody
  (README, "What is not implemented"). This phase closes that.

**Testable without GL.** All of the rules: ray casts against constructed geometry,
splash falloff at known distances and through known walls, ammo and fire-rate
accounting, knockback impulses, the projectile batch step. The GL half is a smoke test
that a rocket appears and an explosion draws.

**Docs.** README gains a weapons section and loses the "nothing here models health"
line; the weapon table's units and defaults are documented because they are tunable, and
because with a custom loadout the table is the only place the game's design is written
down.

---

### §8 — Fire and water shaders ✅

**Goal.** Surfaces that move. Independent of every other phase — it can be done at any
point after §2, and it is the phase that most changes how the existing maps look.

**What has landed (2026-07-27).** The particle system is shipped upstream —
`OpenGLContext.scenegraph.particles`, GPU-instanced quads, a numpy pool, emitters
as declared nodes, six presets, [docs/particles.html](../openglcontext/docs/particles.html),
a demo and 71 tests; see
[../openglcontext/plans/PARTICLE-EFFECTS.md](../openglcontext/plans/PARTICLE-EFFECTS.md).
On this side, the animation directives are **specified, parsed, carried and
drawn**: `SPEC-Q3SHADER §2.4` was added from the same published manual,
`twig_bb.surfaceanim` evaluates every form as a pure function of scene time,
`SurfaceStyle.animation` carries it, and `twig_bb.animator` applies it — the
affine `tcMod`s onto the material's `uv_transform` (one uniform), `rgbGen`
onto its base colour, `alphaGen` onto its opacity, `animMap` onto its texture,
and `deformVertexes`/`tcMod turb` onto the vertices through a new
`PBRMesh.set_surface_deformer` hook upstream. 154 tests here plus 22 upstream.
Verified against the shipped OpenArena scripts: 1387 materials parsed, 498
animated, every directive family exercised, and a map captured at two scene
times differs exactly over its lava.

**The underwater volume and buoyancy landed 2026-07-28, and the phase is
closed.** Two things upstream had declared and never driven turned out to be
exactly what it wanted. **VRML97's `Fog` node** is now rendered (the pass had
collected `nodetypes.Fog` paths for years and read none of them, and a
`context.gltf_fog` seam nothing ever set is retired), with *both* of the
specification's curves — and the choice between them is the whole point rather
than a detail: `EXPONENTIAL` leaves the weapon in the player's hands clear
while the far wall goes, which is what being inside a medium looks like, where
a linear fade or a full-screen tint colours both alike and reads as a pane of
glass over the screen. **Swimming** stopped being a use of noclip: a mode now
says which *body state* its movement assumes (`MovementMode.applyTo`), and
omi_physics' character controller grew a swim step with flying's movement,
walking's collision and a vertical that is neither. A swim built on noclip let
a player leave a pool through its wall, and one at falling speed made a pool
read as a hole in the floor.

Here: `twig_bb.underwater` (the three liquids' colours, ranges and muffles —
this game's numbers, since no specification says how far you can see through
slime), and `LiquidVolume` gained its **kind**, because a volume that knows only
that it is "a liquid" cannot tint the view its own colour and will not be able
to hurt the right amount in §7. Measured over the fetched content: **1926 pools
of water, 760 of lava and 27 of slime across 29 of the 50 maps**, with the kind
read from the leaf's contents word in one family and the brush's `surfaceparm`
in the other. Liquid **damage** landed with §7: see `liquids.LiquidHarm`.

**Most of the work was parsed and thrown away.** `.shader` scripts are read
today, and the material-animation directives were recognised and skipped
([twig_bb/q3shader.py:269](twig_bb/q3shader.py#L269),
[twig_bb/q3shader.py:314](twig_bb/q3shader.py#L314)); `SurfaceStyle` already
carries `scrolling` and `warping` flags with nothing behind them
([twig_bb/surfaces.py:71](twig_bb/surfaces.py#L71)). The facts are in
[SPEC-Q3SHADER](specs/SPEC-Q3SHADER.md), from the published shader manual — a permitted
source, so where the spec is thin the answer is a spec revision from that same manual,
not a look at an engine.

**Build.**

- Carry the parsed directives through `SurfaceStyle` into the material instead of
  dropping them, then implement in the PBR pass: texture-coordinate modification
  (scroll, turbulence, rotate, scale, stretch), vertex deformation (wave and normal —
  this is what makes water surfaces move), colour generation by wave (pulsing fire and
  glows), frame animation, and additive blending for flames and effects.
- All of it driven by one scene time uniform so surfaces animate in step, and all of it
  switchable from the F10 settings screen, like every other renderer decision.
- **Water as a volume, not just a surface.** The liquid volumes are already known
  ([twig_bb/liquids.py](twig_bb/liquids.py)): being under one should tint and fog
  the view, and — with §4 — muffle sound. This is a small change with a large effect on
  whether a map feels like a place.
- **Fire as an effect, not only a surface.** Explosions, rocket trails and sparks want a
  particle system, and there is none in OpenGLContext today. Build one upstream
  (`OpenGLContext.scenegraph.particles`): GPU-instanced quads, emitters as nodes, a
  numpy-stepped pool. §7 is its first customer, and it is the natural home for the
  smoke, impact and stylised-gore effects that phase implies. Stylised is also the
  cheaper target: bright short-lived sprites and a handful of gib pieces on the existing
  instanced path, rather than decals, fluid or persistent meshes — the look and the frame
  budget point the same way here.
- **Buoyancy**, listed as unimplemented in the README, is adjacent and cheap once the
  volumes are being read for tinting: `SwimMode.buoyancy` exists and wants partial
  gravity in the character controller.

**Testable without GL.** The directive-to-material translation, the deformation and
colour maths at known times (they are pure functions of time and position), and the
particle pool's step. Rendering is verified against captured reference images with the
existing visual-regression harness — and, because a still image cannot show animation,
by capturing one map at two pinned clock values and diffing them
([§14.4](#144-verifying-that-animation-reaches-the-pixels)). The fixtures are in
[§14.3](#143-animated-surfaces): `oa_bases3` for the visual check, `oa_ctf2` for the
uniform-only case, and **`oa_shouse` for the frame budget** — 97 surfaces, every one
of them deforming.

**Docs.** README's "Animated material effects" entry moves from "not implemented" to a
description of what is; the settings additions are documented; any spec revision is
recorded in [specs/README.md](specs/README.md).

---

### §9 — Content catalogue, downloads and the start screen ✅

**What has landed (2026-07-28).** The catalogue is a **data file**
(`twig_bb/packs.json`) read by `twig_bb.catalog`, so a pack can be added,
its size corrected or its URL moved without touching Python — and validation is
strict, because an entry with a mistyped key would otherwise be accepted and
ignored for ever. `openarena-oacmp1` is registered (measured: 59 MB, and the
Debian tarball is `.tar.xz`, which the reader detects for itself).

**Downloads no longer freeze the window.** That needed a change upstream first:
`resolver.fetch_to_cache` read the *whole* body in one call, so a 450 MB pack
was 450 MB of process memory before a byte reached the disk, reported nothing
while it happened, and could not be stopped. It now streams in chunks with
`progress` and `cancel` callbacks, and `twig_bb.fetcher` runs that on a
worker the frame loop **polls** — one bar for the whole job, weighted by the
sizes the user was shown, because a bar that fills and resets per pack reads as
three failures.

`twig_bb.match` is the match a player chooses (a declared node: level, bots,
difficulty, limits; saved and read back, and a difficulty a later version stops
declaring is dropped rather than poisoning the file). `twig_bb.menu` is the
screens — main menu, play (editing a **draft**, so Cancel is real), download
consent with the size and licence *on the screen that asks*, and a progress
screen with a Stop.

**The menu is where the game starts.** Launching with no map opens it:
`OnInit` no longer loads a level, `_loadLevel` does, and the menu calls it.
Play chooses a level from a carousel of level shots and the opponents to face,
"Get content" opens the consent screen and runs a real download behind a
progress bar that can be stopped, and Acknowledgements opens the notices. The
last choice made is offered again first. A map named on the command line still
skips straight into it, which is what a capture run and a bug report both want.

**What is left is not part of this phase's scope.** T3 is a content
*availability* question — the Quake 3 base-game material scripts have no freely
licensed replacement to catalogue, so there is nothing here to build until one
exists — and T10 is a developer tool for surveying installed content, which is
§14's tidy-up rather than a player-facing feature. Neither blocks a player from
finding, downloading and playing a level, which is what §9 was for.

What follows is the design as it was written.

**Goal.** Launching the game with no arguments should be a reasonable thing to do:
a screen that offers what can be played, fetches what is missing, and starts a match.

**What exists.** Four asset packs with sizes, licences, companions and consent rules
([twig_bb/download.py:80](twig_bb/download.py#L80)), a two-consent policy that is
already correct, and per-user unpacking. What is missing is breadth, a way to *see* the
choice, and a download that does not block the window.

**Build.**

- **A catalogue rather than a tuple.** Move the pack list to a data file that can grow
  without a code change, keep every field the current `AssetPack` carries — the
  `copyright` field is what §10 is generated from, so it stays mandatory — and register
  the packs already identified: `openarena-oacmp1` (Debian main, noted in the README as
  unregistered) and any further freely-licensed map packs, each with its licence
  recorded at the time it is added.
- **Arbitrary `.pk3` URLs**, which the viewer can already open from the command line,
  offered as a first-class path in the UI, with the same safety the unpacker already
  enforces on archive paths. A URL a user types is a consent; a URL a *map* names is
  not, and nothing downloads from map content.
- **Downloads that do not freeze the window.** Fetch on a worker thread, progress and
  cancellation drawn over the map through the overlay UI, and the licence and size
  shown *in the consent dialog* — not only in `--list-packs`. A user consenting to
  hundreds of megabytes of CC BY-SA content should see that is what they are agreeing to.
- **A start screen** when no map is named: choose the map (with its `levelshots`
  thumbnail from the archive, which is exactly the sort of thing that makes a chooser
  usable), the bot count and skill from §6, and the match rules. Built from the same UI
  primitives as the settings screens, and — following
  [../openglcontext/OpenGLContext/ui/session.py](../openglcontext/OpenGLContext/ui/session.py) —
  editing a draft, so Cancel is real.
- **Remember the last choice** and offer it again first.
- **A content survey, recorded in the README** the way the existing OpenArena survey is:
  what the packs actually contain by way of player models, weapon models and sound
  formats — counted per extension across every pack, not sampled. It is cheap: the
  archives are already fetched and indexed, so the survey is a pass over the name lists.
  §5's model reader hangs off the answer entirely. §4 no longer does, now that one
  backend covers `.wav`/`.mp3`/`.ogg`/`.flac`, so what the survey owes audio is narrower
  and sharper: **a count of `.opus`**, the one format that backend does not decode, and
  a corpus of real files of each kind to test the decode seam against.

  **Part of this is already measured — see [§14](#14--content-census-measured-2026-07-27)**,
  which records the extension counts, the `target_speaker` census, the animated-material
  census and the recipes that produced them. The audio question is answered outright:
  **255 `.wav`, 98 `.ogg`, 0 `.mp3`, 0 `.opus`**, so the Opus gap is theoretical for
  this content and stays unfilled. What §9 still owes is the **model counts by kind**
  (§5 needs player models separated from weapons and props; the bare 196 `.md3` does
  not give that), the packs nobody has fetched, and a **committed tool** rather than
  §14's recipes.

**Testable without GL.** The catalogue's schema and consent rules, the resolver, the
unpacker's path safety (already covered — extend it), the download worker's progress
and cancellation against a fake transport, and the start screen's model. No test in
this repository downloads anything from the network.

**Docs.** README's content sections are rewritten around the start screen; every new
pack appears in the table with its licence; `--list-packs` and the new options are
documented.

---

### §10 — Acknowledgements ✅

**Shipped 2026-07-28.** `twig_bb.notices`, and it is built the way the plan
asked: **the content half is generated** from the catalogue's own `copyright`
field, so a pack added to `packs.json` is credited without anyone remembering —
the whole reason that field is mandatory — and **the code half is checked**,
with a test comparing `NOTICES.md` against what `pyproject.toml` declares, so a
dependency added and not acknowledged fails the suite rather than shipping
unattributed. The provenance statement is in there too. Printable with
`python -m twig_bb.notices`, and `--check` is the gate.

**The other half, shipped 2026-08-03: crediting the world you are standing in.**
`twig_bb.mapnotice` establishes what a running map is from three sources, none of
which is required for the others to work — the **title and author** from the
map's own `worldspawn` `message`, which is where a mapper signs the work and is
inside the `.bsp` so it survives repacking; the **terms** from the catalogue
entry for the pack whose directory the file sits under, matched by path
component so `openarena-maps-old` is not taken for a child of
`openarena-maps`; and the **licence documents** a release ships, found at the
pack root and one level down (a release states its terms above the paks, while
a map's content roots start at the pak) and cited by path rather than quoted.
A map of somebody's own claims no pack's terms and is credited by name alone.

It reaches the player in three places: **on screen as the level loads**, through
the HUD's message queue; **at the top of the acknowledgements**, before the
libraries, since a player who opens that screen mid-match is asking about the
level; and in the **terminal and the overlay's `Map` section**, for a run with
no window and for checking what a recording may be published under. Two
findings paid for by drawing it rather than asserting it: the HUD's font has no
glyph for an em dash and drew one as `?`, so the on-screen form is ASCII, and
the message queue never wraps, so a long licence ran off the screen — it is now
**wrapped, never shortened**, because a truncated licence states weaker terms
than the content carries.

**What a map *is* and what it is *drawn with* are two statements, not one.** A
level resolves its textures against packs it did not come from, and every one of
those roots is on its list and ships a `COPYING` of its own — so the first cut
cited the replacement-texture licence under a heading reading *its own terms*,
which misstates what the level is under. Documents now come from the map's own
pack alone (or, for a map of your own, its roots minus any inside a catalogued
pack), and the borrowed packs are listed under **Drawn with content from**. The
distinction is not cosmetic: the Quake 3 replacement textures are CC BY-NC-ND
while the maps are CC BY-SA, and somebody publishing a recording needs the
stricter of the two stated where they are standing.

**Red/Green TDD: 40 tests**, no GL, plus one against the fetched OpenArena pack.

What follows is the design as it was written.

**Goal.** A screen, reachable from the main menu and the settings screen, that says what
this is built from and what it is playing.

This is not decoration. This project uses freely-licensed content under licences with
attribution requirements — CC BY-SA 3.0 for OpenArena's art and sound, a Creative
Commons replacement set for the Quake 3 textures — and it depends on libraries whose
licences ask to be reproduced. An acknowledgements screen is how a distributed
application meets those obligations.

We *also* need to be sure that on loading we are crediting the authors of the worlds
so that we are meeting CC BY and similar requirements. (And we want to be good
citizens, so even if a license doesn't *require* it, we want to aknowledge the 
contributions).

**Build.**

- **Generate the content half**, do not write it. Every `AssetPack` already carries a
  `title`, a `copyright` and a `url`; the screen renders that list, so a pack added in
  §9 appears here automatically and cannot be forgotten. That is the whole reason
  `copyright` is a mandatory field rather than a comment.
- **The code half from a manifest** — a `NOTICES.md` listing twig-bb, OpenGLContext,
  PyOpenGL, pyvrml97, omi_physics, numpy, Pillow, GLFW and whatever §4 adds, each with
  its licence and its home. Checked in, checked against the installed dependency set by
  a test, so a new dependency that is not acknowledged fails the suite rather than
  shipping unattributed.
- **The provenance statement**: that no engine source was read, that the format
  knowledge came through the specifications in [specs/](specs/), and that the procedure
  is [specs/CLEAN-ROOM.md](specs/CLEAN-ROOM.md). It is the truest thing about this
  project and it belongs where a user can read it.
- Rendered with the existing scrolling text panel
  ([../openglcontext/OpenGLContext/ui/scroll.py](../openglcontext/OpenGLContext/ui/scroll.py))
  and `dialogs.notice`, and printable from the command line for anyone packaging this.

**Testable without GL.** Generation from the pack catalogue, the manifest-versus-
installed-dependencies check, and that every registered pack has a non-empty licence.

**Docs.** README links the notices; `NOTICES.md` is itself the documentation.

---

### §11 — Multiplayer ⬜

**Multiplayer is a stated goal, not an open question.** It is not being built in this
plan and it is last in the order, but it is *committed*, and that changes §5, §6 and §7
today. This section exists so that those phases are built against it rather than
retrofitted to it.

**Why it has to be said now.** Nothing here is expensive while the phases are being
designed and all of it is expensive afterwards, because retrofitting networking is
rarely a networking job — it is the job of unpicking every place the rules read a key,
a clock or a camera. The constraints below are worth taking **even if multiplayer never
ships**, because each is independently better design and each makes the rules testable
without a window.

**How much of it is already standing (2026-07-29).** Every constraint below now
has a piece of code that keeps it, which is the point of having stated them
early rather than a claim that multiplayer is close. Input is a command
(`bots.Command`, produced by a bot exactly as a key press produces one). The
rules are `twig_bb.rules.Rules`, which takes its seconds as an argument and
reads no clock — a test asserts the module imports neither `time` nor
`datetime`, and another plays two identical matches out and asserts they end in
the same places. State is data addressed by id (`Arena` + `PlayerState`). And
presentation consumes a drained event stream and never writes to the rules, with
a test that parses `arena` and `combat` and fails if either imports the
presentation. What is *not* there is the fixed tick — the rules are still
advanced with the frame's own `dt` — and that is the one seam a network layer
would have to install.

**The seams §5–§7 must respect.**

- **Input is a command, not an effect.** A key press does not move a character; it
  contributes to a per-tick command record — move axes, buttons, view angles, the tick
  it belongs to — and the simulation consumes that. §6's bots emit *the same record*
  rather than writing positions, which is why a bot is testable headlessly and why a
  remote player is later just a third producer of an existing type. This one constraint
  carries most of the value.
- **Simulation runs on a fixed tick, separate from the frame rate.** The physics layer
  already works this way — fixed timestep with an accumulator and render interpolation —
  so the game rules must live on that clock too, not in `OnIdle`. Rules read the tick
  number; nothing in the rules reads a wall clock.
- **Game state is data, addressed by stable id.** Health, ammo, positions, item respawn
  timers and match score are records that can be enumerated and copied, not attributes
  scattered across scenegraph nodes. A thing that can be copied can be snapshotted,
  compared in a test, and later sent.
- **The simulation emits events; presentation consumes them.** A hit, a pickup, a death,
  a jump-pad launch. §3's HUD, §13's sounds and §8's effects subscribe to that list and
  never write to state. This is the rule that keeps a damage number from being computed
  inside a draw call — and it is what makes an effect fire identically for a remote
  player later.
- **Reproducible given inputs, not bit-exact across machines.** The realistic target for
  this genre is an authoritative server with client-side prediction, which needs the
  simulation to produce the same result from the same inputs *on one machine* — enough
  for replay tests and for prediction — and does not need cross-platform floating-point
  determinism. Lockstep determinism is a much harder promise; do not accidentally depend
  on it.

**Explicitly not now:** no protocol, no serialisation format, no interest management, no
lag compensation, no server binary. Only the seams. A phase that builds netcode before
§7 has weapons to replicate is building against a guess.

**Our own protocol, no interoperability — decided, and it removes the only risky part of
this phase.** §11 talks to our own clients and nothing else. There is no existing
server to be compatible with, therefore no wire format to establish, therefore **no
spec, no permitted-source question and no clean-room exposure anywhere in networking**.
That is the difference between a phase of ordinary engineering and one that would have
been the largest reverse-engineering effort in the project.

What that freedom is worth, concretely:

- **The protocol is a design problem with known good answers** — an authoritative server
  with snapshot/delta replication and client-side prediction is the well-understood shape
  for this genre, and we are free to take it straight, simplify it, or adopt a library
  that already does it. The only constraint on such a library is the usual one: its
  licence must suit a BSD project.
- **Tick rate, units, scale and update cadence are ours**, chosen to suit our simulation,
  rather than dictated by something else's decisions from decades ago.
- **Version matching can be strict.** Client and server ship together and must agree on a
  protocol version; there are no third-party clients to stay compatible with, so early
  versions can change the format freely rather than carrying compatibility from day one.
- **The seams above are unchanged** — they were written to be independent of this answer,
  and they are.

---

### §12 — MD3: map decoration models ⬜

**Goal.** Draw the props a map places around itself — the `misc_model` entities that
reference `.md3` files in the content packs — so a level looks the way its author built
it.

**A later task, and genuinely optional.** Three decisions emptied this phase of urgency:
characters are our own glTF (§5), weapons are our own glTF (§7), and pickups follow the
weapons. Nothing on the path to a playable game routes through MD3 any more. What is
left is decoration: real, visible, and worth doing eventually, but never blocking.

**Spec before code, without exception.** `specs/SPEC-MD3.md` is written first, from a
permitted source — the format is publicly documented, and the
[SPEC-BSP46](specs/SPEC-BSP46.md) precedent (published reference plus the bytes of
sample files, no copyleft source read) is the route to follow. Facts unobtainable that
way go through the Reader/Implementer wall of
[specs/CLEAN-ROOM.md](specs/CLEAN-ROOM.md); facts unobtainable at all are recorded as
unknown, with the implementation's answer marked a **choice** rather than dressed up as
the original's behaviour — the [SPEC-Q3PUSH](specs/SPEC-Q3PUSH.md) pattern.

**Scope note that keeps it small.** Props need the *container* — meshes, skins, surfaces
— and little else. The player-model conventions layered on top of the format (the
multi-part body, the tags joining the parts, the animation ranges in a sidecar file) are
what a character would need, and this phase has no characters to draw: ours are glTF.
Deferring MD3 deferred that whole convention layer, and §12 as scoped here does not
bring it back. MD3's vertex-morph animation is only needed for props that animate; a
static prop is a mesh.

**Testable without GL.** The reader against bytes constructed in the test — the
[tests/bspbuilder.py](tests/bspbuilder.py) pattern, which exists precisely so tests do
not depend on shipped content — plus `misc_model` placement and the resolution failure
path.

**Docs.** `specs/README.md` gains `SPEC-MD3` and its provenance line; README's
missing-content section stops describing props as undrawable; the code cites the spec,
never the original.

---

### §13 — Our own sounds ⬜

**Goal.** The noises *this game* makes: weapons firing and reloading, impacts on
each surface kind, footsteps, jumps and landings, pain and death, item pickups,
the announcer. Present on a bare install, whether or not any content pack was
ever fetched.

**Split out of §4 deliberately, and the reason is worth stating.** §4 is an
engine phase — a mixer, a device seam, gain curves, and reading a `noise` key
out of an entity lump — and it is finishable today. This is not an engine phase
at all. It is a **content and design** phase: deciding what a rocket launcher
sounds like, getting those files made, and writing down which event fires which
one. It shares exactly one line of code with §4 (`engine.play(...)`), and while
the two were one phase §4 could not be called done until a game existed to make
noises. Separating them is the same move §5 made when it pushed MD3 out to §12.

**It is gated on §5 and §7, not on §4.** There is nothing to author a weapon
sound *for* until there is a weapon, and no footstep until there is a character
with a ground state. The engine has been waiting for a customer since
2026-07-27; this phase is that customer arriving, and it arrives when they do.

**The sounds come from the same commission as the art — say so in the brief.**
§5 already makes the artist brief a §5 deliverable covering §7's weapons, because
both come from one commission at one time. Sound belongs in that same document
and for the same reason: it is far cheaper to specify a weapon's fire, impact and
reload alongside its model than to come back for them afterwards, and a sound
designer wants the same clip list, the same naming convention and the same
licensing terms the artist does. What the brief has to add:

- **A named event list**, not a file list. `weapon/rocket/fire`,
  `impact/metal`, `foot/step/stone`, `player/pain/light` — the *event* is what
  the game emits and what the table maps; which file answers it is content that
  can be replaced without touching code, exactly as §7's weapon table treats
  models.
- **Variation counts.** A footstep played identically forty times a minute reads
  as a bug. Three to five takes per event, chosen at random, is the cheap fix and
  has to be asked for up front.
- **Loudness and length conventions**, so a mix does not have to be rebalanced
  file by file: normalise to a stated peak, keep one-shots short, and state which
  events loop.
- **Mono, and why.** A stereo file has already decided where it sits in the
  stereo field and cannot then be panned to where it actually is in the world —
  the engine mixes clips down on load, so a stereo delivery is wasted work.
- **Licensing stated before work starts**: work-for-hire, or a licence
  compatible with a BSD project, recorded per asset for §10's notices exactly as
  §5 does for the art.

**Placeholders are the designed path here too, and better than §5's.**
`omi_audio.synth` makes tones, chirps, noise bursts and percussive
impacts out of arithmetic — no files, no licences — and a game with a
synthesised gunshot is a game that can be played, tuned and shipped to a tester.
Unlike a character reduced to a capsule, a synthesised impact genuinely *reads*:
it is the timing, the pitch and the falloff that tell a player they hit
something, and all three can be tuned long before a recording exists. Expect to
iterate on the event table far more than on the files.

**Build.**

- `twig_bb.sounds`: the event table — a declared node with typed fields, like
  §7's weapon table — mapping an event name to its clip list, gain, priority,
  variation policy and falloff. Because the numbers are ours, the table is the
  design document; it must be readable, carry units, and be retunable without a
  code change.
- **Events, not calls.** §11's seam already requires the simulation to emit a
  hit, a pickup, a death, a jump-pad launch and for presentation to consume them.
  Sound subscribes to that list and never writes to state, which is what makes a
  sound fire identically for a remote player later — and what keeps a `play()`
  out of a damage calculation.
- **Priority is the interesting knob.** The voice pool steals by priority, so
  the table is where "a rocket explosion outranks a footstep" is written down. A
  scene that runs out of voices should lose the footsteps.
- Bundle the shipped clips under the package with an author/tool/licence record
  beside them, so §10's notices can state what the shipped audio is as
  confidently as what the fetched audio is.

**Testable without GL, without a sound device and without the package.** The
event table's schema and defaults, the mapping from a simulation event to an
event name, variation selection over a seeded sequence, priority ordering under
a full pool, and the fallback when a clip is absent. All of it is data, and none
of it needs a speaker.

**Docs.** README gains a sound section listing the events and what a contributor
authors against; the event table's units and defaults are documented because
they are tunable; §10's notices gain the shipped audio's provenance.

---

### §14 — Content census (measured 2026-07-27)

**Why this is in the plan.** Three phases (§4, §5, §9) are gated on *what the
content actually contains*, and every earlier answer to that was a guess. These
numbers were measured, and the recipes that produced them are here so the next
session re-runs them in a minute instead of rediscovering them. They are a
**snapshot of one machine's fetched packs**, not a promise: re-run before relying
on them, and replace this with §9's proper survey tool when it exists.

Everything below was measured against the fetched OpenArena packs at
`~/.config/OpenGLContext/twig-bb-content/` (50 maps: `openarena-data` +
`openarena-maps` + `openarena-textures`), run from `twig-bb/` with the workspace
virtualenv.

#### 14.1 File formats, by extension

```text
audio :  .wav 255   .ogg 98   .mp3 0   .opus 0   .flac 0
models:  .md3 196   (no .md5mesh / .mdr / .iqm / .gltf / .glb)
other :  .shader 63   .bsp 50
```

What each phase takes from that:

- **§4 / §13:** `miniaudio` covers every byte of sound these packs ship. **The
  `.opus` count is zero**, so the one format it cannot decode is a theoretical gap
  for this content and stays unfilled. No `.mp3` either, so the streamed-music
  case does not arise here.
- **§12:** 196 `.md3` props is what map decoration is worth, and there is no
  competing model format to support.
- **§5:** nothing here is a glTF character, which is consistent with characters
  being ours to author.

```python
import collections, os
root = os.path.expanduser('~/.config/OpenGLContext/twig-bb-content')
counts = collections.Counter()
for base, _dirs, files in os.walk(root):
    for name in files:
        counts[os.path.splitext(name)[1].lower()] += 1
print({e: counts[e] for e in ('.wav', '.ogg', '.mp3', '.opus', '.flac',
                              '.md3', '.shader', '.bsp')})
```

#### 14.2 `target_speaker` entities

**29 of 50 maps, 381 speakers, 46 distinct `noise` paths, 44 of them resolving.**

| Map | Speakers | Map | Speakers |
|---|---|---|---|
| `ctf_inyard` | 60 | `ctf_gate1`, `oa_dm4` | 10 |
| `oasago2` | 52 | `delta` | 9 |
| `oa_dm3` | 41 | `sleekgrinder`, `suspended` | 7 |
| `oa_rpg3dm2` | 31 | `czest1dm`, `oa_bases7` | 6 |
| `oa_koth1` | 28 | `czest2ctf`, `fan`, `oa_dm6` | 4 |
| `oa_dm5` | 22 | `aggressor`, `ce1m7` | 3 |
| `slimefac` | 17 | `am_galmevish`, `oa_bases5`, `oa_ctf4ish`, | |
| `oa_dm2` | 14 | `oa_pvomit`, `oa_shine`, `wrackdm17` | 1 each |
| `oa_spirit3` | 13 | | |
| `kaos`, `kaos2` | 12 | | |

**Fixtures worth knowing.** `ctf_inyard` is the density case; `am_galmevish` is
the only map carrying a `*`-prefixed `noise`; `aggressor` and `ce1m7` are small
maps exercising `spawnflags 1` and `wait` respectively.

`spawnflags` values seen: `1` ×326, absent ×21, `8` ×13, `5` ×10, `4` ×9, `0` ×2.
Only bit 1 (looping) is understood; **bits 4 and 8 occur in real content and
their meaning is unknown**, so the spec must record them as unknown rather than
invent a reading.

The two `noise` paths that do not resolve — `*falling1.wav` and
`/sound/world/lava1.wav` — are the missing-content path, and real maps hit it
from the first load rather than it being a branch nobody runs.

```python
import collections, glob, os, logging
logging.disable(logging.WARNING)
from twig_bb.viewer import build_parser, load_map
counts, flags, noises = {}, collections.Counter(), collections.Counter()
for path in sorted(glob.glob(os.path.expanduser(
        '~/.config/OpenGLContext/twig-bb-content/openarena-maps/*/pak1-maps/maps/*.bsp'))):
    target = 'openarena-maps:%s' % os.path.basename(path)[:-4]
    loaded = load_map(build_parser().parse_args([target]), target)
    found = [e for e in loaded.entities if e.classname == 'target_speaker']
    if found:
        counts[os.path.basename(path)[:-4]] = len(found)
    for entity in found:
        noises[entity.get('noise', '')] += 1
        flags[entity.get('spawnflags', '(none)')] += 1
print(sum(counts.values()), 'speakers in', len(counts), 'maps')
print(dict(sorted(counts.items(), key=lambda kv: -kv[1])))
print('spawnflags:', dict(flags), 'distinct noises:', len(noises))
```

#### 14.3 Animated surfaces

Over the shipped `.shader` scripts: **1387 materials parsed, 498 animated**, by
directive —

```text
tcMod rotate        226      rgbGen wave       106      deformVertexes wave     66
tcMod scroll        173      alphaGen wave      70      tcMod turb              66
tcMod stretch       130      tcMod scale        66      animMap                 48
deformVertexes move 113                                 deformVertexes normal    1
```

Every directive family §8 implements occurs in real content, which is what
justifies the size of that implementation.

Per map: **45 of 50 maps have at least one animated surface, 286 in all.**

| Map | Animated | Deforming | Note |
|---|---|---|---|
| `oa_shouse` | 97 | 97 | the stress case — every animated surface deforms |
| `oa_spirit3` | 13 | 4 | |
| `oa_koth1` | 10 | 5 | |
| `ps37ctf` | 10 | 3 | |
| `oa_bases3` | 9 | 6 | **the visual-verification fixture**; see 14.4 |
| `oa_ctf2`, `oa_ctf2old` | 9 | 0 | uniform-only: texture matrices, no vertex cost |
| `delta` | 8 | 0 | |
| `oasago2` | — | 6 | |

`oa_shouse` at 97 deforming surfaces is the frame-budget case §8's risk row wants
watching. `oa_ctf2` is its opposite: nine animated surfaces costing nine uniforms
and no vertices.

```python
import glob, os, logging
logging.disable(logging.WARNING)
from twig_bb.viewer import build_parser, load_map
for path in sorted(glob.glob(os.path.expanduser(
        '~/.config/OpenGLContext/twig-bb-content/openarena-maps/*/pak1-maps/maps/*.bsp'))):
    target = 'openarena-maps:%s' % os.path.basename(path)[:-4]
    loaded = load_map(build_parser().parse_args([target]), target)
    moving = [b for b in loaded.world.batches if b.style.animated and b.style.draw]
    if moving:
        print('%-16s animated=%-3d deforming=%d' % (
            os.path.basename(path)[:-4], len(moving),
            sum(1 for b in moving if b.style.animation.deforming)))
```

#### 14.4 Verifying that animation reaches the pixels

A still screenshot cannot show animation. `--capture` pins the clock to
`viewer.CAPTURE_TIME`, so rendering one map at two different pinned times and
diffing the images is the check — and it is reproducible, because two runs at the
same pinned time are byte-identical.

On `oa_bases3` this gives **1817 differing pixels, max channel delta 67**,
concentrated exactly over the lava pool.

```python
# Run twice, changing PINNED, then diff. Needs a GL target; glfw works headless.
import os, sys
PINNED = 0.0                       # then 1.6
os.environ.update(OPENGLCONTEXT_BACKEND='glfw', OPENGLCONTEXT_PROFILE='core',
                  OPENGLCONTEXT_AUDIO='0')
sys.argv = ['twig-bb', 'openarena-maps:oa_bases3',
            '--capture', '/tmp/t%s.png' % PINNED, '--frames', '10']
from twig_bb import viewer
viewer.CAPTURE_TIME = PINNED
viewer.main()

# then:
# import numpy as np; from PIL import Image
# a = np.asarray(Image.open('/tmp/t0.0.png').convert('RGB'), dtype='i2')
# b = np.asarray(Image.open('/tmp/t1.6.png').convert('RGB'), dtype='i2')
# d = np.abs(a - b).max(axis=2)
# print((d > 4).sum(), 'px differ, max delta', d.max())
```

#### 14.5 What this census still owes

- **A committed tool.** §9 wants this as a repeatable command rather than a recipe
  in a plan; these numbers are a snapshot and drift as packs are added.
- **Model counts by kind.** §5 wants player models separated from weapon models
  and props, which a bare `.md3` count does not give.
- **The other packs.** Only the OpenArena set is fetched on this machine;
  `quake3-core` and anything §9 adds are uncounted.

---

## 3b. Open work, in the order it should be picked up

Everything below is *known* and *unstarted*, listed so it is a queue rather than
a memory. A phase's own section has the design; this is the checklist.

### Bugs to fix

| # | Bug | Where to start |
|---|---|---|
| B1 | **Stepping up snaps the camera forward — open, measured, three fixes tried.** Walking onto a step lurches the view forward as well as up. **Measured: 45.8 cm in the frame that mounts an 18-unit step, where 12.7 cm was due — 3.6×**, which is the "half a foot to a foot" that was reported. `CharacterController._try_step_up` mounts the whole climb in one motion and books the excess as a debt paid back over later frames, so the *average* speed is right and the *instant* is wrong. **What was tried and why each failed:** crossing at the frame's own pace leaves the capsule still inside the riser, and the step-down snap drags it back — it walks on the spot for ever; rising in place leaves it airborne over the floor it is leaving, with no walkable ground to seat on; taking the shortest advance that stands never finds one, because a capsule resting exactly at the step's height still grazes the riser and the deepest contact is a vertical face rather than the tread. **The likely answer** is to let the capsule be *briefly airborne* over the lip while advancing at its own pace, and to keep the step-down snap off it for those frames — which needs a "mounting a step" state on the controller rather than a per-frame decision. `tests/test_character_step_pace.py` measures it and is marked `xfail(strict=True)`, so the bug is visible and the next attempt has a number to aim at. **It now affects opponents as well** (B18 gave them the same controller), where it is invisible — nothing is looking through their eyes — so the lurch is still only a player's problem and the fix is still only worth making for the camera. |
| B2 | **Lava does not animate in `q3/bulk/fff.pk3` — diagnosed, and it is not the animator.** The surface is `textures/liquids/protolava`, and **no material script anywhere defines it**: the map's own `scripts/fff.shader` declares seven `textures/stecki/*` names and not that one, and the fetched OpenArena content does not define it either — it is a *Quake 3 base-game* shader. With no script the name is used as a plain texture path (`SPEC-Q3SHADER §3.2`), which is correct behaviour, and everything the script would have said goes with it: the animation, the surface parameters, the blend. **What was wrong was the silence.** A map naming shaders nobody has drew still, untextured surfaces and said nothing, so the animator got the blame for missing content. `LoadedMap.unscripted_surfaces()` now counts them, the load report names one, and the developer overlay's Map section has an **unscripted surfaces** row. `fff` reports 28. Fixing the lava itself means having the base-game shader, which is a content question — see T3 below. |

| B3 | **Water triggered at ankle depth — fixed.** Standing in shallow water fogged the whole view. The liquid volume was the *BSP leaf's* bound, and a leaf holding a pool reaches as far as the split that made it — up to the ceiling of the room — so the camera was inside the volume long before it was inside the water. Volumes now come from the **brush's own planes** (`SPEC-BSP46 §4.7`, `§4.8`), which is where a liquid states its extent; a brush that is not a box still falls back to the leaf. Across the 50 shipped maps that turned **2713 leaf-boxes into 130 brush-boxes**. |
| B4 | **Swimming dropped out of mouse-look — fixed.** `SwimMode` steered with `q`/`e` while every other mode steered with the pointer, so entering water took the player's aim away. Mouse-look moved onto `MovementMode` and is shared by both, so a player's sensitivity and inverted-look mean the same thing walking and swimming; `SwimMode` now captures the pointer as well. And **forward means where you are looking**, through a new `PhysicsViewPlatform.set_swim_move` that follows the pitch — a swim that flattened the move to the horizon is walking with the gravity turned off. Strafe stays level, and the dedicated up/down keys remain for holding depth while looking elsewhere. |
| B5 | **Underwater looked like foggy air — fixed.** The fog is blended in linear HDR *before* tone mapping, so colours that read as a pleasant mid-blue when written down arrive far brighter than a dark level — and a fog that makes distant walls *brighter* is a fog lamp, not a body of water. The water colours are now roughly a sixth of what they were and the range is 9 m rather than 18, so distance swallows a corridor instead of lighting it. Rule of thumb recorded in `twig_bb/underwater.py`: the fog colour has to sit at or below what the level itself averages. |
| B7 | **Texture animation ran far too fast in `ctf_inyard` — fixed.** The rates were parsed correctly; the wrong *stage* was animated. A Quake 3 material is a stack of stages drawn over one another, and this viewer draws **one** of them — the first with an image of its own (`SPEC-Q3SHADER §2.3.1`). `_claim_stage` gave the material's animation to the first stage that declared any, whichever that was. On the generator's light panels the base image is static and a faint glow scrolls across it on an *additive third stage*, so a layer that is never drawn handed its `tcMod scroll -0.7 0` to the panel and the whole panel raced past at 0.7 texture widths a second. Animation now comes from the stage that is actually drawn, and `ctf_inyard` goes from 6 animated batches to 4. **This is the same defect as B8** — a later stage deciding something only the first stage may decide — and both are worth remembering together when the next stage-derived property is added. The torches were never wrong: `animMap 10` over 8 frames is a 0.8 s cycle, which is what a flame looks like. |
| B8 | **Whole floors rendered as dark glass — fixed.** Reported on `oa_minia`, `ctf_inyard` and others: opaque concrete showed the room beneath it, and dark-on-dark left the screen unreadable. `_finish` marked a material transparent if **any** stage carried a non-opaque `blendFunc`, but the stages are drawn in order and it is the **first** that decides whether the surface is see-through (`SPEC-Q3SHADER §2.3`) — a lightmap filtered over solid stone is still solid stone. `oa_minia` went from 13 translucent batches to 1, `oa_dm2` from 7 to 4. |
| B9 | **Choosing bots produced no bots — fixed.** They were built, placed and given bodies, and then stood still for ever, because `TwigContext.physicsWorld` asked the *view platform* for its world. A platform owns a **character** and the character owns the world, so the answer was always `None` and every caller treated that as "physics is not up yet". Silent by construction: it also disabled the player's own shots and hid the overlay's Physics section, with nothing logged in any of the three cases. Bots' initial spawn height was wrong too — a map's spawn entity marks a player's *eyes*, and the arena addresses everything by its feet, so they hovered a metre up until `game._spawns` subtracted the eye height. |
| B10 | **A single bot cost most of the frame budget — fixed, 34x.** Reported as "30 fps max and stuttery physics" as soon as B9 let the bots start thinking. Measured at **8.95 ms per tick for one bot** on `ctf_inyard`, which is over half a 60 Hz frame for one opponent. The bots were not doing anything extravagant — a bot casts twice a tick, once for line of sight and once to probe the step ahead — but **`raycast` had no spatial index**. It narrowed by testing every triangle's bounding box in one vectorised sweep, which is O(T) and at 66,596 triangles is ~4 ms of numpy per cast however short the ray. `omi_physics.body` had had a uniform grid for exactly this reason since the character controller needed one; the ray path simply never used it, and a grid asked for a *box* would not have helped anyway — a cast across a level has a bounding box containing the level. So the grid moved into `omi_physics/trigrid.py`, shared by both callers, and grew a second way to ask: walk the cells the ray actually enters, in order, and stop at its limit. That took one bot to 0.39 ms. The cost then moved to Moller-Trumbore running in a Python loop with two `numpy.cross` calls per triangle, where numpy's fixed per-operation cost dwarfs arithmetic on three numbers; solving the whole candidate set at once took it to **0.26 ms**. |
| B11 | **Bot perception was O(n-squared) — fixed 2026-07-29, and it is now bounded by the interval rather than the count.** Every bot asked line of sight of every other combatant every tick: 0.26 ms at 1 bot, 3.07 ms at 4 and **17.6 ms at 8**, past a frame at a menu that offers 15. `Bot.look` now re-perceives at most every `PERCEPTION_INTERVAL` (0.1 s), and each bot's first look is offset by a seeded phase so a room of them never look on the same frame. **The saving is in how often, not in how much**: `perceive` is unchanged, so no difficulty sees less than any other. It is invisible because 0.1 s is shorter than the fastest `reactionTime` on the ladder (0.15 s) — a bot answers a sighting no sooner than that, so delaying the sighting itself by less changes nothing a player can feel, and slowing a *sense* far enough to matter would be a difficulty change by the back door. A sighting remembered between looks is filtered for aliveness each tick, which costs no casts and stops a bot emptying a magazine into a corpse. |
| B12 | **The developer overlay recomputed the map's texture report every frame — fixed.** `missing_textures()` resolves every name the map draws against the content tree: 0.88 ms on `ctf_inyard`, spent 60 times a second on an answer that cannot change while a map is loaded. Now a `cached_property` on `LoadedMap`. Only paid with the overlay open, which is why it was not part of B10. |
| B13 | **Every player shot raised `AttributeError` — fixed.** Reported as "no hit indication on the bots or walls". There was no indication because there was no shot: `_shoot` called `weapon.spread(...)`, and a `Weapon` declares `spread_at(fraction)`. The call sat inside the frame loop's `# pragma: no cover - GL` region, so nothing in the suite had ever executed it. **The crosshair's hit mark was never wired either** — `GameHUD.hit` has existed since the HUD was built and had no caller — so even a shot that landed said nothing. `_shoot` now feeds what it hit to `_shotLanded`, which marks the reticule when a *person* was hit. |
| B14 | **Being fragged did nothing — fixed.** The message said "Bot 1 fragged you" while the player went on standing in the same place shooting. Two causes, both in the frame loop. The gun did not check whether its owner was alive. And the respawn moved only the *record*: the tick publishes the camera's position into the match as the player's body, so a respawn the camera was never told about was overwritten on the very next frame, putting the player back exactly where they were killed. The publish is now `_publishPlayer`, which does nothing while dead — a corpse is not where the camera is, and publishing anyway also left a shootable target under a player with no body — and `_respawnDue` binds the character to the chosen spawn. Both were extracted from the GL-only loop so they could be tested at all, which is why they were broken: nothing could reach them. |
| B15 | **`test_instancing_is_faster` failed intermittently — fixed 2026-07-29.** Both measurements sat at ~15-18 ms, which is the 60 Hz frame interval: the harness asked for `glfw.swap_interval(0)` and the Wayland compositor throttled the swap regardless, so what was timed was the wait rather than the draw, and the on/off ratio was driven toward 1. The harness now stops the clock **inside `SwapBuffers`, before the swap and after a `glFinish`**, so the swap is outside the measurement. The margin assertion also moved to 200 shapes: at 800 the pass builds one model-view matrix per shape in Python every frame whether or not the draws are collapsed, and that shared cost is most of the frame, so the two modes converge on it and the ratio says more about the gather than about the draws. A second test asserts instancing is never *slower* at 800, which is the honest claim at that size. Measured after: 200 shapes on 4.2 ms / off 8.4 ms; 800 on 13.3 / off 16.4. **The ratio still needs a quiet machine** — with a dozen other processes running, `on` doubles to 8.9 ms while `off` does not move at all, because the instanced path is bound by CPU-side submission and the other is not — which is what openglcontext's `serial` marker is for: `-m "not serial"` for the bulk and `-m serial` on its own afterwards. |
| B16 | **Every respawn went to the same square — fixed.** Reported as "I respawn always to the same location where all the bots respawn so we're just on top of each other every time". The viewer asked `choose_spawn(loaded, config.spawn + 1)` on every death: a **constant index**, so a map's dozen spawn points were one spawn point and every death put the whole match back on it, standing inside one another and shot again before the screen had settled. `game.spawn_for` now picks the point furthest from everybody currently alive — maximising distance to the *nearest* living combatant rather than the total, because a point far from the crowd but touching one opponent is the worst place in the level to arrive and a sum would call it a good one. The dead do not take up room. |
| B17 | **Nothing that happens in a fight is shown.** **Closed 2026-07-28 by §7.** Every impact now reports itself (the trace that meets the level is no longer discarded), the match emits `Fired` and `Impact` beside the damage events, and one presenter turns that stream into the reticule mark, the impact and blood effects, the directional damage wash, the death notice and the sounds. |
| ~~B8~~ | ~~**Solid surfaces are drawn half-transparent.**~~ **Fixed — and it was not `surfaceparm trans` at all.** Reported three times: "dark glass on dark glass" in `ctf_inyard`, a screenshot of `oa_dm2` with the lava trench showing through the floor, and `oa_minia`'s concrete floor. **The reader was deciding transparency from *any* stage's `blendFunc`.** `SPEC-Q3SHADER §2.3`: a material draws its stages in order, each over the one before, so whether the *surface* is see-through is decided by the **first**. `textures/proto2/marble02b_floor` — a real floor from the shipped content — has an opaque first stage and then three blended ones: an environment reflection, an additive pass and the `$lightmap`. Reading those as transparency made every lit floor in the game a sheet of glass, and it also dropped the lightmap (`§2.3.2` disables lightmapping on a transparent surface), so the floors went flat as well as see-through. Now only the first stage decides. Measured: `oa_minia` **13 → 1** translucent batches (a light beam), `oa_dm2` **7 → 4** (an invisible surface, an edge, water, lava), `ctf_inyard`'s remaining six are fog clouds, a flame and decals. Five tests, including the real four-stage floor. |
| ~~B8b~~ | ~~Superseded — the `surfaceparm trans` theory below was wrong.~~ Kept as a note: `trans` is still read as transparency in `_surfaceparm`, which is *probably* also wrong (it reads as a compiler hint about light rather than a render instruction) but no longer causes a visible defect, and changing it wants a spec revision first. **Old text:** Reported twice: "dark glass on dark glass" in `ctf_inyard`, and a screenshot of `oa_dm2` where the lava trench and stairs *below the floor* show straight through it. **Measured: 7 of `oa_dm2`'s 20 drawn batches are at opacity 0.50, and one of them is `textures/proto2/marble02b_floor` — a floor.** The cause is in `q3shader._surfaceparm`: `surfaceparm trans` sets `material.transparent`, which `Material.style()` turns into a flat `TRANSLUCENT_OPACITY` of 0.5. **`surfaceparm trans` is almost certainly not a render instruction.** In this engine family it is a hint to the *compiler* — this surface lets light through, so trace lighting past it — while whether a surface is see-through at run time is decided by its stage's `blendFunc`. Reading it as "draw at half alpha" makes every floor a sheet of glass, and several stacked multiply down to the dark picture that was reported. **Do the spec first**: `SPEC-Q3SHADER §2.2` covers the surfaceparms and §E covers the stage keywords, and this needs a revision from the same published manual stating what `trans` governs before the code changes — the fix is then to take opacity from `blendFunc` and leave `trans` to the lightmap, with a test that a floor with `surfaceparm trans` and no blended stage comes out opaque. |
| B6 | **The overlay's fps and frame time jumped about — fixed.** `format_value` dropped trailing zeros, which is right for a position and wrong for a number that updates sixty times a second: 60, 59.97 and 60.1 are three different widths in three consecutive frames. `debugoverlay.Fixed` keeps its decimals whatever the value, and the two frame rows use it. |
| B18 | **Bots stuck in walls, floors and stairs, then vibrating and sinking through — fixed 2026-07-29, and there were two faults.** A bot was a *position* with one ray cast ahead of it, which is not a body: a probe is a line and a level is not, so it walked into corners the line missed, and nothing held it down. And it was published **inside the floor**: `game._spawns` dropped a spawn entity's origin by the *eye* height where the spawn convention lifts it by 0.61 m, so every bot started 0.56 m buried and nothing was trying to dig it out because nothing tested it against the geometry at all. Both are fixed at the source. `twig_bb.avatar` states the body's size and the spawn lift **once**, and the camera's spawn and the arena's now go through the same correction — they had drifted, and the *shot* capsule and the *walking* capsule had drifted apart by forty centimetres besides. `twig_bb.walkers` gives every bot the player's own `CharacterController`: same capsule, same move-and-slide, same step height, same ground snap, same impulse for knockback (so a burst now throws a bot upward as well as sideways). A bot placed inside geometry is bound from a step height above and dropped onto the floor, and one buried deeper falls, which the kill floor (B28) turns into a respawn. |
| B19 | **The pistol taking 30+ hits to kill a bot — measured 2026-07-29, and the table was right.** Pinned by `TestHowManyHitsAKillTakes`: every weapon kills a fresh unarmoured target in exactly the number of hits its own numbers say (pistol 7, rifle 13) at 3, 6, 12 and 25 metres, and an aimed trace lands at every range out to 60. So the hits were not being lost and retuning `damage` would have buried whichever thing was. Two changes made it *play* as the arithmetic says: the aim bug (fixed 2026-07-29) was sending shots away from the crosshair, and the shootable capsule was 1.42 m tall where the drawn body was 1.8 (see B18), which is a third of the target missing. What remains is the cone: at 25 m a sustained pistol burst opens to about 1.3° and the crosshair shows it, so misses at range are the weapon's declared spread doing its job. |
| B20 | **A grenade head-on not killing — fixed 2026-07-29.** The contact path was already right (`Projectiles._advance` detonates on a body rather than bouncing) and the *burst* was the part that did not arrive: `blast.burst` deliberately leaves whoever was struck head-on out of the splash, so a direct hit is one hit with one number behind it — and that number was 40 for a grenade and 90 for a rocket, neither of them a life. So a grenade square in somebody's chest left them walking, which is the one outcome nobody watching it would accept. Both direct-hit numbers are now 110: lethal against a full, unarmoured target, and armour still saves you, which is what makes armour worth the detour. Pinned at 1 m (inside the arming distance, where a projectile still ignores its thrower) and at 5 m. |
| B34 | **A rocket at somebody's feet did nothing at all — fixed 2026-08-03.** Reported as no splash damage and no shove when the burst lands near you. The burst rules were right and the *point* they were given was not: `Projectiles` reported a detonation exactly where the cast met the triangle, and a point sitting on a triangle is on both sides of it. `blast.burst` then asks whether it can **see** each person near it, and that cast meets the same triangle at a distance of zero whenever the rounding falls that way — so everybody in the room is reported to be behind cover and the rocket costs nothing and moves nobody. Half the time, which is why it read as unreliable rather than as broken. The detonation is now centred where the round's middle was, one collision `radius` back along the surface normal, which is where a warhead physically is when its nose touches and is also a better place to draw the burst. Reproduced first as two tests: the point is a radius clear of the floor and of a wall, and — at the seam where a player meets it — a rocket fired into the floor beside a bot hurts and throws them, and one at your own feet throws you up and costs you for it. Every existing burst test passed throughout: they all detonate in **open space**, which is the one place a rocket never goes off. |
| B35 | **A bot fired as fast as it thought — fixed 2026-08-03.** Nothing connected `Weapon.fireInterval` to a bot: it shot whenever its reaction and its `decisionInterval` allowed, so a nightmare bot pulled the trigger twenty times a second whatever it was holding. Measured at **58 rocket launches in three seconds** where the weapon allows three and a half. Harmless-looking while the rifle did 8 damage a shot and fatal the moment it did 120, which is how it surfaced. `Bot` now carries `since_shot` and will not fire until its chosen weapon is loaded. How often a bot *thinks* stays a difficulty; how often its weapon *fires* is the weapon's, because what should make a hard bot hard is that it aims well and commits quickly, not that it is holding a different rifle from the one the player picked up. A bot with no weapon table has nothing to be held to and is unchanged. |
| B36 | **Every hitscan weapon was the same weapon at a different rate of fire — fixed 2026-08-03, with the balance pass that asked for it.** A trace cost the same at forty metres as at two, so range decided nothing and every fight was fought at whatever distance the players happened to be standing. `Weapon` gained `fullRange`, `fadeRange` and `fadedDamage`, and `Weapon.damage_at(distance)` reads them; `combat._landed` measures the trace's own distance, which is to the near side of a capsule rather than between two positions. Linear rather than curved on purpose — this is a number a player has to be able to predict after being shot by it twice. The loadout is now written as sentences about play (a pistol kills in two close and six down a corridor; a shotgun kills outright inside five metres and does *nothing* past seventeen; a rifle kills in one anywhere it can see, once every second and a half, with ten rounds) and the table holds whatever makes them true — with the tests written the same way round, so retuning breaks a claim about the game rather than an assertion that 34 is still 34. Both bursts were widened at the same time: the falloff exponent came down to 1.15 so that a near miss costs a third of a life, which is the whole reason to aim a launcher at the floor beside somebody. |
| B37 | **The rifle had nothing to aim with, and the reticule was drawn through the wrong frustum — fixed 2026-08-03.** A weapon that kills at any range it can see has to be hard to aim or it is the only weapon anybody carries, and at three hundred metres a body is a pixel or two. `Weapon.zoomFieldOfView` declares the view a weapon can be sighted through (24 degrees, the rifle alone) and `controls.ZOOM` is held on the right mouse button, like the trigger and for the same reason: a scope left on by accident is a player who cannot see anyone walk up to them. The frustum is written every frame from what is *currently* in hand, so switching weapon, dying and running out all give the view back with nothing having to remember to cancel anything. Found on the way: the HUD read `platform.fieldOfView`, which a `ViewPlatform` does not have — it keeps `frustum` as degrees — so every reticule had been scaled through the 90-degree fallback while the view was drawn at 60. `viewer.view_fov` answers from the frustum itself, which is what makes a sighted reticule open by exactly as much as the view narrows. |
| B38 | **A launcher and a detonation sounded like a very loud rifle — fixed 2026-08-03.** Every voice in the table was `synth.impact`, which is white noise under a decay: bright at any length, so it makes a crack, a snap or a hiss and can never make a boom. `omi_audio.synth.rumble` is the other half of the range — noise with the top rolled away over a tone that falls as it goes, saturated until it growls — and `Voice` gained a `shape` naming which generator makes it, with `cutoff`, `pitch`, `pitchEnd`, `tone`, `drive` and `attack` for the rumble's numbers. The launcher spools up and sits at 102 Hz; the burst peaks at 71 Hz and falls away for a second, and every burst is that one voice whatever threw it. Measured rather than described: the spectral centroid of the two is 560 and 471 Hz against 11 kHz for every small arm in the table, and that ratio is what the tests assert. |
| B39 | **Every weapon still sounded like a hiss — fixed 2026-08-03.** B38 gave the launchers a body and left the small arms as they were, and against a rocket that now arrives in the chest a pistol reading as a *ping* is worse than it was before. All five reports are `rumble` voices now, told apart by where each sits between a roar and a ring rather than by how long it lasts: the shotgun lowest and least focussed (an explosion that barely holds together, three fifths of its power below 100 Hz), the rifle the most tonal thing in the game and ringing a long way down, the pistol a bang and the highest of the three, and the grenade launcher a hollow thump. Power-weighted spectral centres: 113, 141, 167 and 125 Hz against about 11 kHz for the noise they replaced. **And a weapon now owns both ends of its shot**: `impactSound` and `fleshSound` join `fireSound`, the `Impact` event carries the weapon that made it, and the rifle is the one weapon naming its own — a round that heavy arrives with a chunk, and the generic ping made the shot that ends a fight sound like a stone hitting a window. The invariant that a hit on a person outranks a hit on stone is now asserted over every weapon in the table rather than over the one generic pair. Measured with **power**-weighted centroids, not magnitude: a rolled-off noise still carries a very quiet tail over ten kilohertz of bandwidth, and weighting by magnitude let all that inaudible width read the shotgun as brighter than the rifle. |
| B40 | **Weapon reports built out of a falling sine read as drums — fixed 2026-08-03.** B39's rumbles put the weight of each report in a low tone, and reported back from listening: the rifle sounded like a tom and the rocket like an instrument playing a descending note. The fault is general and worth stating as a rule: **a low sine under a hard attack is a drum, and one that falls as it goes is a drum being tuned**, and that is what a listener hears whenever the tone carries the bottom end however small its share of the mix — the rifle's was twelve per cent and it still sounded like a drum kit. Weight has to come from *noise* leaning toward the bottom, which is what a blast and a motor are. `synth.rumble` gained `tilt`, in decibels per octave, and both voices now have `tone` at nought: the rifle is a crack with no pitch in it at all (3.6 kHz, a third of its power above 4 kHz, over in a fifth of a second) and the rocket is a roar. `synth.echoed` came with it — three returns, each losing its top *and* its bottom the way air and distance take them, because a return that is an exact copy is heard as somebody firing twice rather than as the first shot answering. **Aimed at two reference recordings the user supplied and copied from neither**: what crossed is measurements — how one report's energy divides between the bottom, the middle and the top, at the crack and again in the tail — and ours land within a few per cent of them at both ends. The recordings are not in the repository and carry no licence into it. |
| B41 | **The grenade launcher was a drum too, and nothing was heard for a pickup — fixed 2026-08-03.** The launcher was the last voice carrying its weight in a falling sine (`tone` at 0.58, the highest in the table) and read as one; what it wants is the **pop** of a mortar, which is a hollow band rather than a thump. `synth.rumble` gained `floor`, the bottom edge of its noise as `cutoff` is the top — the two together are a band, and a band is what anything hollow is: a tube rings around a pitch and has almost nothing underneath it. Aimed at a mortar recording the user supplied and copied from none of it: our bulk sits at 233 Hz against its 300, with 95% of the power below a kilohertz against 90%. **And picking something up now makes a sound.** `arena.PickedUp` has carried a `point` since it was written — 'so a sound comes from the thing' — and nothing had ever played one, so taking the armour was silent and therefore, as far as a player could tell, had not happened. It is a bubble going, which is what the pickups are: a rumble of pure tone pitched *upward*, because a cavity that is closing gets smaller and something smaller rings higher, and a falling one reads as a drop of water. Placed at the item rather than at the ear, so somebody else clearing the far side of the level is worth knowing about. It is the only bright thing left in the table now that every weapon is at the bottom of the range, which is what lets one piece of good news carry through a firefight without being loud — and it does **not** outrank a hit on a person for a voice, because good news can wait a frame. |
| B42 | **The rifle was a drum three times over — fixed 2026-08-03.** Reported three times running, and each fix found a different thing making the same mistake. First the weight came from a falling sine, which *is* a drum being tuned (B40). Then it came from bottom-tilted noise with a hard attack and an exponential decay — which is also a drum, and that is the less obvious half of it: the **envelope** makes a tom as surely as the spectrum does, whatever the numbers say about where the energy sits. And the 'echo slightly' it was given was three discrete returns, which over a fifty-millisecond burst are heard as *repeats* — a clap, and then another clap — so it was a drum with applause. What the reference recording actually shows, measured slice by slice, is a crack that holds its brightness for 60 ms and then a **dense tail that goes on for the better part of a second, darkening from about 4 kHz to 1.3** while the bottom drains out of it entirely. That is a room, not an echo, and no arrangement of taps is one. `synth.reverberated` builds it: three bands of decaying noise convolved in, with the **middle outlasting both the bottom and the top**, because that is what distance does — air takes the high end, and the low end of a report is a near-field thump that never comes back off anything. It is baked into the clip when it is made, so it costs the audio thread nothing and the mixer still has no reverb bus. `rumble` also gained `floor`, which takes the thud out of the first millisecond: an instantaneous attack is a *step*, and a step is a kick drum. Three assertions were rewritten to the design as it now stands, one of them **backwards** — the rifle's level must now only ever fall, because anything that gets louder again is the clap this replaced. Also found in passing: the reference holds within 4 dB for 900 ms, which is a stock effect's limiter rather than a room, and is deliberately not copied — a shot that stayed at full level for a second would smother the match. |
| B43 | **The acknowledgements credited a pack the game no longer contains — fixed 2026-08-04.** The five imported CC0 firearms were kept after every weapon got art of its own, on the grounds that a sixth weapon might want one. What that actually bought was 1.7 MB of art nothing drew and a licence to keep checking, and the acknowledgements screen went on naming a pack whose models the program does not use — which reads as a claim to contain something it does not, the failure that screen exists to prevent, pointing the other way. Removed, along with the CREDITS section describing them and the notice generated from it. Two rules are now tests rather than intentions, in both directions: every model in `assets/weapons/` is named by the weapon table or the projectile table, and nothing is credited that is not shipped. `tools/prepare_weapon.py` stays as the documented route for art from outside, which is the only thing the deleted models were still evidence of. |
| B33 | **A weapon walked over joined the bar but not the hand — fixed 2026-08-03.** Picking a weapon up is the pickup a player most wants to feel, and it changed nothing they could see: the number key became a step to remember mid-fight. `PlayerState.prefer` now puts a newly-taken weapon in hand when it beats what is held, `slot` order deciding — the same order the number keys and the bar use, so what counts as an upgrade is a property of the table a designer edits rather than a rule in the rules. **Better only:** being put on a pistol because you crossed the square it was lying on loses a firefight, so a weapon the hand already beats is taken and stowed. An empty hand takes whatever arrives; one already held is a pickup for its ammunition and does not disturb the hand. The table reaches the collection loop through `Pickups.advance(arena, dt, table)`, optional because ordering is the only thing it is for. Red/Green: 7 tests on the rule, 3 more holding the invariant the report actually named — **the model drawn is the weapon held**, over every weapon in the table, over a pickup, and never more than one at a time. Verified by walking onto a launcher in the real game. |
| B32 | **The weapon on screen was not the weapon in hand — fixed 2026-08-03.** Reported as "the 5 weapons are all drawn with exactly the same (pistol) geometry". Two faults, one on top of the other, and both invisible to every test and capture taken until then because each was only reachable by switching weapon **at runtime** — spawning holding one works, since the scene is integrated after the hand is filled, which is why every `--weapon` capture looked right.

**One: the swap was never announced.** `FlatPass` walks the scenegraph once (`SGObserver`) and thereafter keeps its renderable paths current from the add/remove signals a node's `children` list sends. `WeaponHand.select` rebound the whole list — `self.group.children = [holder]` — which puts a *new* list on the field instead of mutating the observed one, so nothing was sent and the pass went on drawing the path it last integrated. The scenegraph was correct throughout, which is what made it read as a rendering mystery. Replacing in place (`children[:] = [...]`) sends `new` and `del`.

**Two: the weapon put away was never removed.** With the signals flowing, every weapon ever held stayed in the draw set — five switches took it from 8 paths to 34, and on screen a sniper rifle and a rifle overlapped in one hand. `SGObserver.onChildRemove` invalidates the detached path, and `NodePath.invalidate` marks "this path and all children" through `iterdescendents` — which, against its own docstring, walked **children and grandchildren only**. A weapon's renderable paths are seven deep (rig → group → holder → yaw → pitch → roll → Shape), so the Shapes were never marked broken and `purge` kept them. Fixed in pyvrml97: `iterdescendents` now walks every generation, iteratively, since a path is as deep as the content under it. **That repo's own test asserted the two-level behaviour**, fixture and all, so the bug was pinned rather than merely unnoticed; it is corrected alongside, with cases for the full subtree and for leaving siblings alone.

**Scope beyond this project.** `node.children = [...]` is the natural spelling and it silently fails to notify; OpenGLContext trips over it in `physics/debugdraw.py` (new physics proxies), `scenegraph/tilesterrain.py` (streaming tiles) and `bin/gltf_demo.py`. The `invalidate` half is now fixed for every caller. The notification half is still worth fixing where the field is set, so the obvious spelling stops being the broken one.

**Red/Green: 5 tests here** — the two signals, an end-to-end one building a real `FlatPass` over the rig and asserting its path set follows the weapon, and two that hold the draw set to one weapon across a full cycle of the table — **plus 4 in pyvrml97**. Verified by switching at runtime in the real game and looking. OpenGLContext's 4703 unit tests are unmoved by the `invalidate` change. |
| B22 | **Spawning handed out the whole weapon table — fixed 2026-08-03.** B21 replaced `carrying` with `starting` in the *viewer*, but `Arena.add` builds every combatant's record and still called `carrying`, and `_buildMatch` adopts the arena's record over the one `_buildLoadout` made — so the starting loadout was constructed and then thrown away, for bots as well as for the player. Invisible as a crash and visible as a rule that made no sense: `restore` has always given back the starting loadout, so a **first death silently cost four weapons and never returned them**, and until you died the level's whole weapon circuit was scenery. `add` now hands out `PlayerState.starting`, which is what `restore` gives back — the two were the asymmetry. `carrying` stays for `twig-bb-hud`, where a weapon bar with one weapon on it demonstrates nothing. The test that pinned the old behaviour asserted it with the pre-item rationale in its docstring; it is replaced by one that spawns with the starting loadout and one that holds spawning and respawning to the same answer. Red/Green, and the other 1944 tests were unmoved. |
| B21 | **No pickups — built 2026-07-29 (with T4).** `twig_bb.items` reads the `item_*`, `weapon_*` and `ammo_*` entities a map places, and `Pickups` hands them out to anybody who walks through one. What each is worth *here* is a declared `ItemKind` table joined to the map by classname, so the amounts are tunable without touching the reader; several fields may be set at once, which is how a weapon pickup arrives with ammunition in it and why nothing branches on a *type*. An item nobody can use stays on the floor, one that is taken comes back after its own interval (`wait` overrides it), and a classname nothing declares is skipped and **counted** — reported on the load line and in the overlay, because a level whose weapon circuit is all content nobody has plays exactly like a reader that failed. `PlayerState.starting` replaces `carrying` in the viewer, `startingAmmo` is finally read, and a respawn restores the starting loadout rather than everything, which is what makes the circuit matter. Provenance: `SPEC-Q3ENTITIES §3`, measured from the entity lumps of 67 shipped maps. |
| B22 | **Lava barely hurting, and only while moving — fixed 2026-07-29.** The rate was never the problem; **where it sampled** was. `_bite` asked `volumes.kind_at(one.position)` and a combatant's position is their *feet*, and a liquid brush is not solid — falling into a pool takes you through it and on to whatever is underneath, which is commonly a hair below where the brush stops. The feet were then clear of every volume and only a step that bobbed them up a centimetre bit at all, which is exactly what was reported. `LiquidVolumes.kind_along` now tests the whole upright body, and where a body spans several volumes the **worst** wins rather than the innermost — waist-deep in lava under a sheet of water is a death, not a swim. Standing on the rim is still dry: it is the body's axis, not a cylinder around it. |
| B23 | **Bots spawning in the same places and repeating the same opening — fixed 2026-07-29.** Three separate causes. `game.spawn_for` maximised distance to the nearest living combatant, which is deterministic, so with a stationary player it chose the *same* point every time and a player could wait at the far end of the level and shoot each arrival; it now picks at random among the points within `SPAWN_SPREAD` (0.7) of the best, which keeps the safety property and loses the predictability. `start_match` places each bot by the same rule instead of by index, so two matches on one level do not open identically. And `Bot.reset` no longer leaves every fresh mind in one state: which way it faces on arrival and how long before it first commits are spread from its own seed. `_wander` was redrawing its heading **every tick** — its own docstring said it held one — which is not wandering but shaking, and is also the worst possible input to a capsule sliding along a wall; it now holds one for about `WANDER_INTERVAL`, spread, so a room of bots does not turn in unison. |
| B24 | **Dying kept the camera where it stood and respawned on a timer — fixed 2026-07-29.** The camera was the piece of a death with no owner: the view stayed exactly where it was killed, still steered by the mouse and still walked about by the keys, which reads as the death *notice* being wrong rather than as a death. `twig_bb.deathcam` takes the view: it falls to near the floor over half a second, eased, and turns to look at whoever did it — the one thing a player wants in that second and cannot otherwise get — with a red `ScreenWash` coming up on the same movement. Nothing to blame (the lava, a fall) keeps the heading it died on, which is honest. **And the trigger ends it**: `Rules.on_request` holds the player back until they ask, so the respawn timer is the *shortest* a death may be rather than the trigger for its end; the notice stops counting and says `Fire to respawn`. A request made early is remembered rather than swallowed. Bots still come back on the timer — nobody is waiting for them to press a key. |
| B25 | **Nothing said who you are looking at — half fixed 2026-07-29.** `combat.who_is_at` asks the *same trace a shot takes*, against the same staged bodies, and the HUD names the answer just below the reticule. Same trace on purpose: a name over somebody a shot would miss is worse than no name, and a wall answering nobody is also what stops it finding people through geometry. Asking damages nothing and puts nothing on the event stream, which matters because it is asked every frame. **The world-space plate is not built**, and the reason is upstream: `OpenGLContext.scenegraph.billboard.Billboard` says of itself that it is a stub and its `transform` does nothing, so a plate over each body needs billboarding implemented in the engine first. Worth deciding at the same time whether names should be visible through walls — always-on ones give positions away and change how the game plays, which is why the readout is deliberately reticule-gated. |
| B26 | **A bot firing grenades at a target it cannot possibly reach — fixed 2026-07-29.** `SkillSet._usable` asked only whether the target was *far enough away* not to blow the bot up, with no upper bound at all, and the grenade's splash is the bigger one so `_worth` preferred it at every range there is. `bots.reach` bounds it from the projectile's own numbers: it stops existing (a fuse, a lifetime) and it falls, and since nothing lofts a shot it is `g t^2 / 2` below the line by the time it arrives — past a body's height of drop it is landing in the floor short of them. The grenade comes out at about 8 m and the rocket, which does not fall, at its lifetime. `reach` is pinned against the **flight itself** rather than against a closed form, so the rule and the simulation cannot drift apart. |
| B27 | **Shoot-to-trigger doors do not react — open, and the last of the reported defects.** There is **no trigger system at all**: `func_door`, `func_button` and the `target`/`targetname` links are not read, and a shot that meets that geometry is an ordinary world impact. This is the same missing machinery that blocks T8 (a map's triggered speakers) and the `targetname` a handful of pickups carry (`SPEC-Q3ENTITIES §3.7.4`), so all three should be planned together. **Where to start:** the entity facts go in `SPEC-Q3ENTITIES` beside §3's pickups — which classnames respond to damage, how `targetname` links a trigger to what it moves, and the movement a door declares — before any code, and the same way §3 was done: by reading the entity lumps of the shipped maps rather than anybody's source. |
| B28 | **Falling off the edge fell for ever — fixed 2026-07-29.** `twig_bb.falling.KillFloor` sits a hundred metres below the map's own bounds and ends anything that passes it, with a named cause the death notice phrases (`fell out of the world`). It is a **kill** rather than a very large amount of damage — `Arena.kill` is its own verb — because armour is for being shot and the bottom of the world is not a hit, and expressing it as damage would leave somebody with enough armour surviving it. It applies to bots too, which also bounds what a bot walking through geometry can do to itself. |
| B29 | **The HUD never showed the score — fixed 2026-07-29 (with T7).** Two readings, because they answer different questions. Frags against the match's limit sit in the top-right corner **all the time**, because that is a question a player has continuously and nobody holds a key to answer one of those; it colours when one frag from the end. The whole board — everybody's frags and deaths, from `game.scoreboard_lines`, which finally has a caller — goes up on a **held** tab: it covers the middle of the screen, and a board left up by accident is a board you get shot behind. Deaths are deliberately not in the corner: on the board they are a comparison, and alone they are a number that only goes up. |
| B30 | **Eight opponents cost about 10 ms a tick — measured 2026-07-29, open.** On `ztn3dm1`: 0.6 ms at 1 bot, 4.4 at 4, 9.9 at 8. That is down from 22.8 before B11's perception interval and the shared static-proxy cache, and it is now spent in the **character controllers** rather than in perception — roughly 0.6 ms per bot per tick, most of it `_push_out` running `collide` against the level's mesh. A frame is 16.7 ms, so eight is playable and the menu's fifteen would not be. **Where to start:** a bot standing still on flat ground resolves the same geometry every tick and could keep its answer until it moves or the ground under it changes; and `_push_out` is called twice per step (once to depenetrate, once to ground-snap) where one may do. Neither is a change to make without a measurement to compare against, which the numbers above are. |
| B31 | **A frame-budget test measured the machine — fixed 2026-07-29.** `test_several_hundred_still_fit_in_one_frame` asserts that three hundred projectiles cost under a frame, and failed on and off. Measured: with nothing else running the tick costs **12.5 ms** against its 16 ms budget, and on a box running another test suite the *same code* costs **31.5** — cores, caches and memory bandwidth are all shared, so a millisecond bound stops measuring the code. Neither `time.process_time` nor a minimum over repeats helps, because the work genuinely takes longer. The test now measures **the same code at a twentieth of the scale** first, which is the only calibration that degrades the way the thing being measured does (0.71 ms quiet, 1.76 loaded), and skips with a reason when the machine is not quiet enough for the budget to mean anything. Loosening the bound instead would leave a number that no longer means "fits in a frame", which is the only thing it is for. The same disease as B15, and it is worth expecting a third: a wall-clock assertion is a claim about a machine. |
| B32 | **A pool you could fall into and not climb out of — fixed 2026-08-03.** Reported at 26,-7,-13 in `oa_spirit3`, where the deck stands 0.21 m above the water and the pool floor 1.9 m below it. Nothing was wrong with the collision geometry: **the swim ended at the eye**, and that made "eye exactly at the surface" a stable point. Swim up, the eye breaks through, `submerged` goes false, the mode hands back to walking, `set_swim(False)` zeroes the vertical speed and gravity puts the body back in — measured at the reported spot, the eye pinned to the water within a centimetre, the feet stuck 1.37 m below the deck, and the mode flipping between swim and fps **549 times in 15 seconds**. The rim of the pool was then unreachable by any means: a swimmer is never grounded, so there is nothing to jump from. `viewer.update_submerged` now **enters on the eye and leaves on the feet** — going in, the eye is right, since reading the feet would put somebody paddling in the shallows into a swim; coming out, the eye is a head's height early, and holding the swim until the body is clear of the liquid is what lets a player lift themselves to the surface and step over the rim. `PhysicsViewPlatform.feet_position()` publishes the second reading beside `camera_position()`; a platform with no body is read by its eye alone. At the reported spot the player now gets out on three of the pool's four sides (the fourth is a wall to the ceiling) with four mode changes rather than 549. The *view* still fogs from the eye, which is where that belongs. |

### Features, by phase

| # | Phase | What is left |
|---|---|---|
| ~~T0~~ | §9 | ~~**Level art in the chooser.**~~ **Done.** `OpenGLContext.ui.gallery` — a `Picture` (letterboxed, never stretched) and a `Carousel`: a band of five level shots with the chosen one in the middle, arrows rolling it round, click any picture you can see, and the chosen level's full name across the band because a tile is too narrow for one. `match.Level` gained `art`, found by walking each pack's `levelshots/` once. **59 of the 63 installed levels have a picture.** 38 tests, no GL. |
| ~~T1~~ | §9 | ~~**Start on the menu.**~~ **Done.** Launching with no map opens the main menu; `TwigContext.OnInit` no longer loads a level, `_loadLevel` does, and the menu calls it. Play chooses a level and the opponents, "Get content" downloads packs with a progress screen that can be stopped, and Acknowledgements opens the notices. The last choice is remembered. |
| T2 | §6 | **The navigation mesh — built, tested, and not yet usable on a real level.** `OpenGLContext.nav.navmesh` exists: walkable-triangle extraction by slope and facing, neighbours by shared edge, A* over the cells and a **string-pulled** path through the portals, `random_point` for a bot with nothing to do, and `from_world` to build one from a physics world. 25 tests, all green, and on synthetic geometry it does the right thing — an open floor gives a straight line, an obstacle is routed around, a ramp is climbed, an island is unreachable. **On `oa_dm1` it builds 1220 connected cells in 0.03 s and then fails at the last step: no spawn point resolves to a cell.** The coordinates line up (spawn at y=-3.05, nearest cell centre 0.35 m away horizontally at y=0.0), so the fault is in `cell_at` — either `_over`'s point-in-triangle test or the floor those spawns are actually over being dropped by the slope filter. That is where to start. **The bots are deliberately not wired to it**: half-wiring would make them worse than the heading-and-refuse they have now. Two further gaps once it resolves: the headroom test is too blunt for a real level (it removed 1092 of 1220 cells, almost none near a wall — it compares bounding boxes where it wants a distance) and is off by default; and there are no off-mesh links, so jump pads are not yet edges in the graph. |
| T3 | §9 | **A base-shader gap the catalogue cannot fill.** Maps built against Quake 3's own `.shader` scripts — `textures/liquids/protolava` and its neighbours — have no script in any pack this project can offer, so those surfaces draw untextured and still (B2). The replacement *textures* exist (`quake3-core`); the replacement *scripts* do not. Worth finding out whether a freely-licensed script set exists, and saying so in the download screen if it does not, since "28 unscripted surfaces" is now reported and a user will ask what to do about it. |
| ~~T4~~ | §6 | ~~**Item and weapon spawns.**~~ **Done 2026-07-29.** `twig_bb.items` reads a map's `item_*`, `weapon_*` and `ammo_*` entities and `Pickups` hands them out; `PlayerState.starting` has replaced the carry-everything stand-in and `startingAmmo` is finally read. The facts went in `SPEC-Q3ENTITIES §3`, measured from the entity lumps of 67 shipped maps. See B21. |
| T4 | §7 | **Projectiles, splash and knockback.** **Done 2026-07-28**: `twig_bb.projectiles` steps a swept numpy batch, `twig_bb.blast` answers each detonation with a declared falloff blocked by geometry, and the impulse goes into the character controller — so rocket jumps work. |
| T5 | §7 | **Liquid damage.** **Done 2026-07-28**: `liquids.LiquidHarm` bites every 0.4 s from the same volumes the swimming uses, and the death carries the liquid's name as its cause. |
| T6 | §5 | **Characters.** The rig and clip-name contract, the animation state machine, the Quaternius CC0 stand-ins fitted *through* that contract, and the artist brief. The capsule stays underneath. |
| ~~T7~~ | §3 | ~~**The scoreboard on a key, and a permanent score readout.**~~ **Done 2026-07-29.** Frags against the limit in the corner permanently, the whole board on a held tab, and `game.scoreboard_lines` finally has a caller. See B29. |
| T8 | §4 | **Entity audio — the `*`-prefixed sounds.** `SPEC-Q3ENTITIES §1.2.5` records that a `noise` beginning with `*` names a sound belonging to an entity's own *model* rather than to the content tree, and that all 16 in the shipped maps are triggered. They are skipped today. Resolving them needs §12's MD3 reader (to know what an entity's model *is*) and a trigger system (to know when to fire one), so this is gated on both and is recorded here so it is not mistaken for an oversight. |
| T9 | §13 | **The game's own sounds.** The engine has had no customer since it landed; weapons, footsteps, impacts and deaths now emit events for one to subscribe to. `omi_audio.synth` is the placeholder path. |
| ~~T12~~ | §7 | ~~**Art for the pickups.**~~ **The health packs are done 2026-07-31**; the rest still draw as boxes. `ItemKind` gained `model`, `modelScale` and `modelOffset`, so what a pickup looks like is a table edit like a weapon's; `twig_bb.art` is the one place that knows where shipped art lives and how to load and recolour it, and `weapons`/`firstperson` now go through it too. The medikit — a cross in a glass bubble, ours, BSD, 30 kB — is **one model painted four ways** from each kind's `colour`, so the four health packs differ only in hue and a fifth is a row in the table with no new geometry. The colours moved from four near-identical greens (hues 130–132°, one item at any real distance) to white/red/blue/gold. `tools/clean_model.py` is the Blender script that prepared it and is reusable: it drops loose parts, faces normals outward, reports open boundaries (and closes them on request), and makes a model concentric so it turns without wobbling. Armour, ammunition and the weapon pickups keep the designed box fallback, which is also what a model that fails to load falls back to. |
| T10 | §9 | **A committed content-survey tool**, replacing §14's recipes, with model counts by kind. |
| ~~T11~~ | §9 | ~~**Downloads from the menu.**~~ **Done.** `_contentScreen` opens the consent screen and starts a `fetcher.FetchJob`, which `OnIdle` polls and publishes into the progress bar; Stop cancels it. |

---

## 4. Risks, and what would tell us early

| Risk | Early signal | Response |
|---|---|---|
| **Clean-room slip** under time pressure in §5 or §6 | a constant in the code with no spec fact behind it | the retrofit procedure in [../CLEAN-ROOM.md](../CLEAN-ROOM.md); it is far cheaper before the code ships than after |
| **Frame budget** — bots, projectiles, particles and audio all want per-frame time in Python | §2's overlay, watched while the count of each rises. The measured worst case today is **`oa_shouse`: 97 deforming surfaces**, every one a per-frame vertex pass ([§14.3](#143-animated-surfaces)) | the numpy-batch design each phase already specifies; escalate to the compute-shader seam omi_physics already has |
| **Navmesh quality** on maps built for a different navigation system | bots stuck at ramps, ledges and pad edges | off-mesh links are designed in from the start (§6), not retrofitted; failing maps become test fixtures |
| **Audio dependency creep** — a format `miniaudio` does not cover pulling an LGPL decoder (`libsndfile`, PyAV, ffmpeg) in beside it | a *second* audio package appearing in `pyproject.toml` | one backend by decision; an undecodable format is a warning and a silence, and silence must stay an acceptable outcome |
| **The silent paths rotting** — audio being optional means the no-package and no-device paths are the ones developers never see | a traceback rather than a warning on a machine without sound or without `miniaudio` | both paths are tested explicitly (§4), including one test that forces the import to fail; ARM64 Linux is a real deployment target, not a hypothetical |
| **Content assumptions** about what the packs contain | §9's survey, which is why it is scheduled with the earlier phases | measure before building; the existing OpenArena survey is the model |
| **Art arrives late, and all of it at once** — characters and weapons are one commission, far off, so a slip moves both and stand-ins carry the game for most of this plan's life | a stand-in wired up around the rig contract rather than through it; a clip or attachment point the code wants that no placeholder has, quietly dropped | stand-ins are the designed path, not a fallback (§5, §7): they go through the same contract the commission will, so every gap surfaces while it is still free to fix — and no phase is scheduled as though art might arrive first |
| **Single-player assumptions hardening** despite §11 | rules code that reads a key, a wall clock or a camera directly, or a HUD that writes state | the §11 seams are cheap while §5–§7 are being written and expensive afterwards; they are also better design on their own terms, which is why they are not deferred with the phase |
| **Difficulty that cheats** — the easy way to make a nightmare bot hard is to give it senses or multipliers a player has no answer to, and it is indistinguishable from skill in the code while being obvious in play | testers describing high difficulties as unfair rather than fast; any perception path that reads state a bot has not perceived | one perception implementation for every difficulty (§6); only timing, aim quality and decision-making scale; the headless ladder test asserts the ordering without ever asserting *how* it was achieved, so cheating has to be caught by review |
| **Scope** — this plan describes a game | phases that never reach "shipped and seen" | each phase must be individually finishable and individually visible; if one cannot be, it is too big and should be split |

---

## 5. Decisions taken

Recorded here because each one closes a question this plan originally left open, and
because together they change the shape of the work: **the game's own content is ours,
and the fetched content is the levels it is played in**.

| Decision | What it settles |
|---|---|
| **Multiplayer is a goal**, built last (§11), **on our own protocol with no interoperability** | not built now, but §5–§7 are designed against its seams from the start — command-based input, fixed-tick simulation, id-addressed state, events for presentation; and with nothing to be compatible with, networking carries no spec and no clean-room exposure at all |
| **Characters are our own glTF** (§5), **contracted later, stand-ins until then** | no format work on the critical path and a rig/clip contract we author — which the stand-in period exists to prove, so the eventual artist brief is written and tested before anyone is paid |
| **Weapons are our own glTF, with our own behaviour and damage** (§7), **from the same commission as the characters** | "right" means plays well, not matches something; the weapon table becomes the design document, §7 has no provenance question at all, and blocked-out placeholder shapes play correctly until the art lands |
| **MD3 is a later task** (§12) | nothing depends on it; it is map decoration, and it still needs `SPEC-MD3` before any code whenever it happens |
| **Audio is `miniaudio`, optional** (§4) | one permissive backend for every target format; optional because of the missing Linux ARM64 wheel, with both silent paths tested |
| **The engine and the game's own sounds are separate phases** (§4, §13) | §4 is a mixer, a device seam and a `target_speaker` reader, and is finishable now; §13 is a commission and an event table, and cannot start before §5 and §7 have anything to make a noise. Bundling them meant §4 could not be called done until a game existed |
| **Difficulty spans near-passive to nightmare** (§6) | the range is the axis the bot is built along, not a late multiplier: presets are declared data, only perception quality and decision-making scale, the senses never do, and the ladder is verified by headless bot-versus-bot matches |
| **Gore is stylised** (§7, §8) | an effects decision, not a rules one — it rides the damage events the simulation already emits, so intensity is a presentation setting that cannot alter play |
| **The title is *Twitchy GLitchy Bang Bang*; game and library share one name** (2026-08-03) | settled — the package is `twig_bb`, distributed as `twig-bb`, and `twig-bb` is the command; the title still lives in one constant and still keys no stored state, so a later title change costs one line |

### The name — settled 2026-08-03

**The title is *Twitchy GLitchy Bang Bang*.** The package is `twig_bb`, distributed on
PyPI as `twig-bb`, and `twig-bb` is what a player types. Game and library carry one
name: the loader has no audience that the game does not also serve, and one name is one
thing to find, install and search for.

| | |
|---|---|
| Formal title | Twitchy GLitchy Bang Bang |
| Import name | `twig_bb` |
| Distribution | `twig-bb` — `pip install twig-bb`, `uvx twig-bb` |
| Commands | `twig-bb` (play), `twig-bb-hud`, `twig-bb-fetch`, `twig-bb-bsp` |
| Module form | `python -m twig_bb` |
| Cache directories | `~/.config/OpenGLContext/twig-bb-maps`, `.../twig-bb-content` |

**The title still lives in exactly one place** — `twig_bb.menu.GAME_TITLE`, which the
window title, §9's start screen, §10's acknowledgements and any generated documentation
read from. Two rules keep that true:

- **Never key stored state to the display title.** The settings namespace, save files
  and cache directories use a stable internal identifier that is never shown to anyone,
  so a title change never migrates a player's configuration.
- **No name in an asset filename or a translated string** where a constant would do.

**On the earlier name, factually:** "twitch" on its own collides with a very well-known
service, which matters for a public game title in a way it does not for an internal
module name. The title carries "Twitchy" as an adjective describing play, which is the
distinguishable form.

**The cache directories move with the name.** `twig-bb-maps` and `twig-bb-content`
replace the previous names outright; anyone holding fetched content from before re-fetches
it, or renames the two directories by hand. The alternative — carrying the old names
forward as an internal detail, or writing adoption code — buys a one-time convenience at
the price of a permanent inconsistency between what the program is called and what it
writes.

The through-line worth noticing: with characters, weapons and their sounds authored by
us (§5, §7, §13), our own weapon behaviour, our own difficulty design and our own
network protocol,
the only fetched content left is **maps, their textures, and their ambient sounds** —
and the only external artefact we must be *compatible* with is the map format itself.
That is a materially smaller surface than this plan started with. It makes a bare
install playable rather than grey and silent, and it leaves the clean-room wall standing
in exactly one place today — the map formats we read — plus §12 if it ever happens.
Everything else in the game is ours to design, which is why so many of the questions
this plan opened with turned out to have answers rather than trade-offs.

## 6. Open questions for the maintainer

**Only one is left, and it blocks nothing.** Everything else this plan opened with has
been answered and moved into the decisions above — which is why the phases can be
started in order without waiting on anyone.

1. **When does the title stop being provisional?** Not a blocker and deliberately not
   one — the single-constant rule above means the answer can arrive at any point,
   including late. It only becomes urgent on the day something is published under it:
   that is when the availability check, the check against existing game titles and any
   name reservation want doing, together.
