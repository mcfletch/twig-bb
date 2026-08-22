# Twitchy GLitchy Bang Bang (twig-bb) — a pk3-based FPS

`twig-bb` is an FPS engine that can load PK3 maps and glTF assets. It
can load most OpenArena maps, though some features such as vehicles and
doors are not yet implemented. It is implemented as a relatively thin
layer on top of OpenGLContext's rendering, UI and physics layers.

The underlying PK3 loader is coded in numpy with memory mapping directly
onto the underlying file, so load times are generally pretty fast. 
Rendering uses the built-in lightmaps in the OpenGLContext PBR render 
passes but we don't currently implement the PK3 sky rendering.

```bash
twig-bb                                 # the start screen: pick a level
twig-bb maps/oa_dm1.bsp                  # a map you already have
twig-bb some-map.pk3                    # an archive: unpacked for you
twig-bb https://example.com/map.pk3     # a URL: fetched and cached
twig-bb openarena:oa_dm1                # a map from a content pack
```

With nothing of your own to look at, `twig-bb --list-packs` shows what can
be downloaded and `openarena:<map>` fetches and opens one of the fifty
OpenArena levels — see [Content packs](#content-packs).

Maps are `IBSP` version 46 (Quake 3, and OpenArena): the header is checked and
the map is read, and everything after that — surface styles, batched geometry,
the lightmap atlas, PBR materials, the scene, the collision mesh, push volumes —
is built from it.

## Content Licensing Note

twig-bb is mostly targetted at allowing you to use existing
infrastructure (e.g. quake3 map editors) to create your own games.
However, it is also a map loader/viewer, and can be used to render existing
pk3 files.

Most sample maps that you will find on the Internet have somewhat restrictive
licenses, or are dependent on assets that have such licenses. If you are using
twig-bb as a viewer for your own use, this is fine. We can load
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

### Who made the map you are in

A level is somebody's work, and the licences these packs arrive under ask for
attribution. Every map therefore credits itself, in three places:

| Where | What it says |
|---|---|
| On screen as the map loads | the map, its author, and the terms — a few lines through the HUD's message queue, which fade like any other message |
| The **Acknowledgements** screen (escape → Acknowledgements) | the same, at the top and before the libraries, plus the paths of the licence documents shipped with the content |
| The terminal, and the developer overlay's Map section | the same again, for a run with no window to read and for checking what a recording may be published under |

Three sources feed it, and any of them may be silent without the others
failing. The **title and author** come from the map file itself: a Quake map's
`worldspawn` carries a `message`, which is where a mapper signs the work, and
being inside the `.bsp` it survives repacking. The **terms** come from the
catalogue entry for the pack the file sits under — a map of your own claims no
pack's terms and is credited by name alone. The **licence documents** a release
ships (`COPYING`, `CREDITS`, `LICENSE`) are cited by path rather than quoted:
they run to tens of kilobytes, and what a reader wants is where the
authoritative text is.

**What a map is drawn with is stated separately from what it is.** A level
resolves its textures against packs it did not come from, and those can carry
stricter terms than the map's own — the Quake 3 replacement textures are
CC BY-NC-ND, which matters to anyone recording or publishing what is on screen.
The acknowledgements list them under their own heading, so *its own terms* means
only that.

The on-screen credit is **wrapped, never shortened**: a truncated licence would
state weaker terms than the content carries. `twig_bb.mapnotice` is where all of
this lives.

## Controls

| Key | Action |
|---|---|
| `w` `a` `s` `d`, arrows | walk; `a`/`d` strafe |
| `q` / `e` | turn left / right |
| ctrl + up / down | look up / down |
| shift | run (held) |
| space | jump; rise, while flying or swimming |
| `c` | sink, while flying or swimming |
| mouse | look — **including while swimming**, where forward also means where you look |
| `f` | fly (noclip) on/off |
| `m` | cycle movement mode: mouse-look, walk, fly |
| `g` | walk (physics) / free-fly camera |
| `1`–`5` | choose a weapon |
| `[` `]`, mouse wheel | previous / next weapon held |
| left mouse button, or ctrl | fire (held) — down the middle of the reticule, wherever you are looking; **and what brings you back when you are dead** |
| right mouse button, or `z` | sight (held) — narrows the view for a weapon that has a scope, which is the rifle |
| tab | the scoreboard (held) — everybody's frags and deaths |
| alt + `f` | developer overlay — frame rate, loop timing, draw counts, where you are |
| `F2` | save a screenshot — `twig-bb-<date>-<time>.png`, in the directory you launched from |
| alt + `s` | the engine's own screenshot key — `twig-bb-screen-0001.png`, same place |
| `F6` | key bindings — rebind any command, over the map |
| `F10` | rendering settings — shadows, lighting, detail, over the map |
| escape | the menu — **Resume** first, then Quit. Escape again resumes. It never ends the match on its own: a key pressed to close something else must not throw a match away |

**Mouse-look (`fps`) is the mode you start in** — an arena map is played with
the mouse, and the pointer is grabbed so the view keeps turning past the edge of
the screen. `m` cycles to keyboard-only walking if you would rather have the
pointer back. Either way you start at one of the map's spawn points, facing the
way the mapper aimed it. Gravity and collision come from the
character controller in `OpenGLContext.move`; jump pads set the capsule's
velocity outright through the physics trigger system. Water, slime and lava are
volumes rather than floors: you fall in, and being under the surface imposes the
swim mode, fogs the view and muffles the mix until you are out again — see
[Water, slime and lava](#water-slime-and-lava).

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
reticule in the middle with the name of whoever is under it, health and armour
bottom-left, the weapon and its ammunition bottom-right, your frags against the
match's limit top-right, the weapons you are carrying along the bottom, and
transient messages along the top. Holding **tab** puts the whole scoreboard over
the middle. It is drawn *under* any screen that is open
and it never takes an event, so a click goes through it to the map — which is
what makes it a HUD rather than a panel. `--no-hud` turns it off, and a
`--capture` run has no HUD at all: a reference image is of the map, and a health
bar over one turns every visual comparison into a comparison of the health bar.

**The reticule belongs to the weapon**, not to the game. Each entry in
[`twig_bb/weapons.py`](twig_bb/weapons.py) names its own crosshair shape
and its cone of fire, and firing opens that cone — so the reticule widens by
exactly the angle a shot might now land within, projected through the renderer's
own frustum. The colours on the meters are thresholds rather than a gradient,
because what a player reads at speed is a state and not a number.

**The HUD reacts rather than merely updating.** A meter whose number slid
silently down in a corner nobody is looking at is not feedback, so losing health
or armour flashes the meter that lost it — losing only, because a pickup is
something you did on purpose and already know about. Being hit washes the screen
edge the hit came from, and dying washes the whole screen red, drops the camera
to the floor and puts up a notice naming what killed you — counting down while
you have to wait, and then saying *fire to respawn*, because a still world with
no gun and no explanation cannot be told from a hang.

**The developer overlay has a `Combat` section** for the three numbers a fight
hides: how much of the projectile budget is in the air, how many particles the
effects are holding, and what the effects setting actually is. A rocket that
never arrives and a full budget look identical from inside the game.

Its **`Map` section names the level and credits it** — title, author, pack and
terms, beside the file name — and then **reports what a level has that this game
cannot answer**, where each row exists because its absence is invisible from
inside the game and looks exactly like a bug: surfaces no material script
defines (so their animation is gone), speakers that found no sound, liquid
volumes, where the floor of the world is, how many pickups were placed, and how
many pickups are of kinds nothing here has anything to give for.

**The developer overlay** (alt + `f`) is everything a player should never see:
frame rate and frame time, the renderer's features and what the last frame cost
in shapes and draw calls, the camera's position in scene metres *and* in map units, which movement mode is in force, whether you are submerged, and the
physics world's body and contact counts. It is fed by *registered providers* —
`twig_bb/debug.py` registers this game's, OpenGLContext registers the
engine's — so a new subsystem appears in it by registering rather than by anyone
editing it. `OPENGLCONTEXT_DISABLE_FPS_DISPLAY` decides whether it starts on
screen, which is what keeps captures clean.

The movement mode used to be named in the top-left corner of the map. It is on
the developer overlay now: a player does not want to be told the name of the
camera mode, and a developer wants that plus a dozen things it never showed.

**When the frame rate looks fine and the game does not, read the `Loop`
section**, not the `Frame` one. The frame rate times the inside of a draw and
publishes a median, so it cannot see a hitch that happens anywhere else — and
in this game the *entire* update (physics, navigation, the match, the animated
surfaces) runs from `OnIdle`, which is outside the draw. `loop fps` is
wall-clock iterations per second, which is the rate your hands feel; when it
sits far below `fps`, the phase rows underneath say where the time went and
`last stall` names the worst one outright, as `match 54ms`.

This game's update is subdivided so those rows mean something: `animate`,
`weapons`, `liquids`, `navigation`, `character` and `match` nest inside the
engine's `idle`, so they *divide* it rather than adding to it. Without them
every stall reads as `idle`, which is true and useless — `OnIdle` is the whole
game.

The `Player` section says what that costs the world. The simulation's timestep
is clamped at 50 ms so a slow frame cannot move a character through a wall,
which means a stalling game does not freeze — it runs in **slow motion**, and
`behind` says so: `5% speed, 0.9s lost` is a world advancing at a twentieth of
real time with almost a second of it discarded since the map loaded. To get the
breakdown on stdout rather than watching for it:

```console
$ OPENGLCONTEXT_STALL_MS=40 twig-bb some-map.pk3 --map some-map.bsp --bots 4
WARNING OpenGLContext.looptrace:main loop stalled 67ms: match 54ms, render 12ms,
  character 1ms, animate 0ms, draw 0ms, idle 0ms, navigation 0ms, liquids 0ms,
  weapons 0ms, cascade 0ms, poll 0ms, wait 0ms, repeats 0ms
```

That is a real reading from a four-bot match, and it is what the frame rate
cannot say: the renderer is holding 11–12 ms a frame — about 85 fps — while
`_stepMatch` spends four times that, so the loop runs at 15–20 iterations a
second and the world, clamped, runs slower still.

**To find out what inside `match` is costing that, record a trace.** A phase
name is as far as the log line can go; the stack that would say more has
already unwound by the time the frame ends. `OPENGLCONTEXT_STALL_TRACE` samples
the main thread *during* the slow frames and writes a file, one record per slow
period:

```console
$ OPENGLCONTEXT_STALL_TRACE=/tmp/stalls.jsonl twig-bb some-map.pk3 --bots 4
$ python -m OpenGLContext.stalltrace /tmp/stalls.jsonl
17 slow periods, 5.1s of them

2026-08-01T00:59:10  0.8s, 18 iterations (9 slow)
  worst 158.0ms, mean 44.5ms, was running at 17.8ms
  phases: match 32.6ms, render 11.0ms, character 0.6ms, ...
  where 28 samples were, by function:
        self    cum  function
       53.6%  53.6%  collide.py _closest_point_on_triangle
       10.7%  75.0%  collide.py capsule_triangle
```

Each record also carries every section of the developer overlay as it was when
the slow period began — the map, the bot count, what was in flight — so a trace
is a whole account of the moment rather than a stack with no situation around
it. **Read it with the reader, not by eye**: the file is JSON lines, and the
per-function tally at the top is the answer while the stacks below it are the
evidence.

See [docs/hud.html](../openglcontext/docs/hud.html) for the whole section and
`twig_bb/frameclock.py` for the timestep accounting.

The widgets themselves are OpenGLContext's
([docs/hud.html](../openglcontext/docs/hud.html)), because a crosshair and a bar
meter are the same in every game; what is here is what the numbers *mean*.

### Recording a session, and playing it again

A whole session goes to one file — every input the platform delivered stamped
with the frame that acted on it, every frame's time, every exception, the
overlay's own sections sampled as it ran — and that file can be **run again**:

```console
$ OPENGLCONTEXT_TELEMETRY=/tmp/session.jsonl twig-bb some-map.pk3 --bots 4
$ python -m OpenGLContext.telemetry /tmp/session.jsonl        # read it
$ OPENGLCONTEXT_TELEMETRY_REPLAY=/tmp/session.jsonl twig-bb some-map.pk3 --bots 4
```

`OPENGLCONTEXT_TELEMETRY=1` writes a dated file under your application-data
directory instead, which is what to ask a player for. The machinery is
OpenGLContext's ([docs/telemetry.html](../openglcontext/docs/telemetry.html));
what this game adds is what the engine cannot know — **the marks**:

```
0:03.204  frame  190  level-loaded map=ztn3dm1 pickups=37 triangles=51345
2:41.067  frame 9640  bot-target bot=bot1 target=player
2:41.910  frame 9691  fired by=bot1 weapon=rocket at=[-704.0, -832.0, 430.0]
2:42.004  frame 9697  damaged target=player by=bot1 amount=63
2:42.004  frame 9697  death target=player by=bot1
```

A level loading and failing to, a match starting and ending, weapons chosen and
fired empty, every shot and hit and burst, what each pickup was and who took it,
a death and where the respawn put them, and the moment a bot found somebody to
fight or lost them again. They come from the match's own event stream — the one
the HUD, the sounds and the effects already read — so a mark and what the player
saw cannot drift apart. The whole list is in
[`twig_bb/telemetry.py`](twig_bb/telemetry.py).

**A replay says whether it reproduced the session.** Those marks are made again
while the recording plays, the engine matches them against the recorded ones —
same mark, same fields, same frame — and says how the two accounts compared, on
the overlay while it runs and in the log as it ends:

```
replay of session.jsonl: 156 marks, all as recorded
```

Which is a thing you can run without a person at the keyboard:

```console
$ tools/replay_check.py ../tmp/q3/ztn3dm1.pk3 --map ztn3dm1 --bots 3
recording a scripted match to /tmp/twig-bb-replay-check.jsonl
replaying it
156 marks, all as recorded
```

It plays a fixed fifteen seconds against three bots — walking, turning,
changing weapons, firing — records it, replays it and answers 0 when the two
agree. How many marks that is depends on how the fight goes, which is what the
session's own seed decides; what matters is that every one of them is made
again, with the same fields, on the same frame. A run that parts from its recording says where:

```
16 of 195 marks as recorded, then weapon-refused said=NO SHOTGUN
  where the recording has fired at=[-5.7, 1.2, 2.7] by=player weapon=pistol
```

**What makes that work** is that nothing in the game draws from a clock or a
random number generator of its own. Every timing is the engine's own time
source, which a recording drives; the cone of fire, the opponents' minds and the
choice between spawn points all draw from named session streams
(`OpenGLContext.entropy`), whose seed the recording keeps and a replay puts back.
`OPENGLCONTEXT_SEED=4242` fixes a whole run.

### Weapons, and what they are made of

`twig-bb-hud` puts the whole HUD on screen over a small lit room with a
first-person weapon in your hands — the fastest way to see any of the above, and
it needs no map and no downloads:

```console
twig-bb-hud          # 1-5 choose, p picks up, the mouse fires, h hurts
```

The weapon table is **declared data**: fire rate, cone of fire, ammunition type
and cost, the reticule, the sound, the model and *what it throws* are fields, so
retuning the game is editing that table rather than editing code. Every number
is ours, so the table is the only place this game's design is written down —
which is why it is documented here rather than left to be read out of the code
that consumes it.

| Field | Units | What it decides |
|---|---|---|
| `key`, `title`, `slot` | — | how the game names it, how the HUD shows it, which number key selects it |
| `ammoType` | a name | which pile it eats from; two weapons naming the same one share it |
| `ammoPerShot` | rounds | what one pull of the trigger costs |
| `startingAmmo` | rounds | how much of that pile a player begins with |
| `fireInterval` | seconds | the shortest gap between shots |
| `damage` | health | what one **hitscan** trace takes off inside `fullRange`; ignored for a projectile weapon, whose damage is the projectile's |
| `fullRange` | metres | how far `damage` carries undiminished |
| `fadeRange` | metres | how far a trace has to fly to be worth `fadedDamage`; **at or inside `fullRange` means no falloff at all**, which is the default |
| `fadedDamage` | health | what one trace costs at `fadeRange` and beyond — zero for a weapon with a hard limit, like the shotgun |
| `pellets` | count | traces or projectiles one shot sends — a shotgun's eight |
| `zoomFieldOfView` | degrees | the view it can be sighted through while the sight key is held; **zero is a weapon with no scope** |
| `projectile` | a key, or empty | **empty is hitscan.** Otherwise the entry of the projectile table it throws |
| `restSpread`, `maxSpread` | degrees of cone half-angle | how wide the shot can land, at rest and firing continuously |
| `crosshair` | a node | the reticule drawn while it is held; it opens by the spread above |
| `fireSound` | a key | which entry of the sound table its **report** is |
| `impactSound`, `fleshSound` | keys | what one of its rounds sounds like **arriving**, on the level and on a person; empty is the table's generic pair |
| `recoilKick` | metres | how far back the weapon in hand is thrown by a shot |
| `recoilRise` | degrees | how far its muzzle lifts with the same shot |
| `recoilRecovery` | seconds | how long the two above take to settle back to nothing |
| `model`, `modelScale`, `modelOffset`, `modelYaw/Pitch/Roll` | metres, degrees | the first-person model and where it sits in the hand |

What each weapon **throws** is a separate table, because those are the
projectile's numbers rather than the weapon's — a rocket falls, bounces, bursts
and pushes the same way whichever launcher threw it:

| Field | Units | What it decides |
|---|---|---|
| `speed` | m/s | how fast it leaves the muzzle |
| `acceleration` | m/s² along its heading | thrust: **zero is an unpowered round** that only ever slows; above zero is a motor that builds speed as it flies |
| `maxSpeed` | m/s | the speed a motor levels off at; zero never levels off |
| `gravity` | m/s² downward | **zero is a rocket**; anything else arcs |
| `radius` | metres | how near a surface it has to pass to touch it |
| `fuse` | seconds | when it goes off in the air; zero never does |
| `lifetime` | seconds | when an unspent one is given up on |
| `bounce` | 0–1 | how much speed a bounce keeps; **zero detonates on contact** |
| `damage` | health | a direct hit |
| `splashDamage`, `splashRadius` | health, metres | the burst at its centre, and how far it reaches |
| `splashFalloff` | exponent | the curve from centre to edge; 1 is linear, above 1 concentrates it |
| `knockback` | m/s | how hard it shoves, at the centre |
| `selfDamage` | 0–1 | the share of splash the shooter takes from their own burst |

A rocket and a grenade differ only in those numbers — the rocket's thrust and
top speed, its zero gravity, its zero bounce and zero fuse against the grenade's
arc and its timer — and in nothing else: two weapons needing two code paths
would mean the table was not carrying the design.

**A pickup turns at the rate its distance earns.** Turning is what makes a
pickup readable across a room, and writing that transform is cheap — but every
part of the model beneath it then has its place in the world worked out again,
and a map places fifty of them. Past `ITEM_SPIN_RANGE` a pickup turns in steps
at `ITEM_SPIN_FAR_RATE` instead of on every frame. It tracks the same clock
either way, so walking up to one shows no jump: what changes with distance is
the size of the step, and at thirty metres that is a fraction of a pixel.

**What a kind is drawn with is one node, not one per shot.** Each kind gets an
[`InstancedModel`](../openglcontext/docs/instancing.html#instancedmodel), and how
many are in the air is an array of matrices written onto it. The renderer
therefore sees as many objects as the model has parts however full the sky is,
firing edits no scenegraph, and a match that has never fired costs nothing for
the ones it has not. `capacity` on the batch stays a *simulation* budget — how
many may be aloft at once — and no longer decides anything about the scene.

### What the five are for

Range is what tells them apart, and it is written in the table rather than left
to a player to discover:

| Weapon | Kills in | Where |
|---|---|---|
| Pistol | 2 hits close, 3 across a room, 6 down a corridor | everywhere, weakly; it is what you always have |
| Shotgun | 1 shot inside five metres, four or five at the middle | nothing at all past seventeen metres |
| Rifle | 1 hit | any range it can see, at a shot every second and a half, with ten rounds |
| Rocket launcher | 1 direct hit, or a third of a life two metres off | anywhere its burst can reach you, including round nothing at all |
| Grenade launcher | the same burst, arriving where a straight line cannot | round corners and over cover |

The rifle's price is the interval and the ammunition: a shot that misses is a
second and a half of standing still while whoever heard it closes, and a level
puts ten rounds in front of you rather than fifty. Armour still saves a target
from it, which is what armour is for.

**You spawn with one weapon and go and find the rest.** It is whichever sits on
slot 1 — the pistol — with that weapon's own `startingAmmo`, and everything else
is placed around the level for you to walk to: see
[Picking things up](#picking-things-up). Dying returns you to exactly that, so
what you had collected is what a death costs, and the circuit is worth running
again.

`startingAmmo` is per weapon rather than one number for all of them — eight
rockets and ten rifle rounds against sixty pistol bullets — because sixty of
everything makes a rocket launcher a pistol with a bigger bang. It is read in both places
that hand ammunition out: what you spawn holding, and what a weapon pickup
arrives with. Slot 1 is read from the table too, so a variant that retunes the
table changes what a player starts with by editing the table and nothing else.

**Fire a weapon dry and the hand falls to the best one still loaded** — the
*highest* by slot you have ammunition for, not merely the next one along, so
emptying the launcher drops you onto the rifle rather than the pistol. It
happens on the shot that spends the last round, so the trigger you are already
holding meets a loaded weapon on its next pull rather than a dead click, and the
switch is announced on the HUD exactly as a chosen one is. A weapon you hold
with an empty pool is passed over like one you never picked up; with nothing
left loaded the trigger simply reports empty.

`PlayerState.carrying` still exists and holds the whole table, but nothing in a
match uses it: it is what `twig-bb-hud` wants, where the point is to show every
weapon on the bar.

**Each weapon is modelled for this game**, in metres, at life size, and every
one of them is the weapon it is meant to be: a launcher, a sawn-off shotgun, an
M79-style grenade launcher, a sniper rifle and a handgun, cartoon-shaped so
they read in the hand rather than photoreal. They are built by
[`grass-clumps/arsenal.py`](../grass-clumps/arsenal.py), which makes the
geometry, the materials and the maps from nothing every time it runs and writes
them straight into
[`twig_bb/assets/weapons/`](twig_bb/assets/weapons/) — so re-running it after an
edit is the whole update procedure.

The wear is procedural and then baked, because none of it survives a glTF
export as nodes: paint chipped off the edges, scratches down the flanks, grime
in the hollows, and a wood grain grown rather than photographed, flattened into
the three maps of a glTF metallic/roughness material.

Every piece of geometry, its author and a link to their page are in
[`twig_bb/assets/weapons/CREDITS.md`](twig_bb/assets/weapons/CREDITS.md),
which is the rule for all art here and is enforced by a test — as is the
converse, that nothing is credited the game does not ship. All of it is ours and
BSD, which is why it may be committed at all, unlike the share-alike OpenArena
content, which is fetched to a user cache and never vendored. Replacing any of
it is a table edit rather than a code change:
`model`, `modelScale`, `modelOffset` and `modelYaw` are fields of the weapon,
so better art is a row in the table and a file in
[`twig_bb/assets/weapons/`](twig_bb/assets/weapons/).

The weapon is drawn as **part of the scene**, on a transform put where the
camera is each frame, so it takes the map's own lighting and is occluded by
geometry the way anything else is. `twig-bb-hud --weapon shotgun` starts
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
| `--effects full\|reduced\|off` | how much impact and blood to draw (default `full`); presentation only, it cannot change play |
| `--headlight` | a lamp at the camera, for maps with no baked lighting |

Set `OPENGLCONTEXT_DEBUG_WHEEL=1` to have every scroll report the offset it was
given and how many notches it made of it. Platforms disagree about what one
click of a wheel comes to — X11 says 1.0 and GLFW's Wayland backend says 1.5 —
and this is how to see which yours is.

Set `TWIG_BB_DEBUG_JUMP=1` to have every jump press say what the capsule thought
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
twig-bb-bsp map.bsp     # report a map's contents without opening a window
twig-bb-fetch URL          # fetch and unpack an archive; prints the map path
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
twig-bb openarena:oa_dm3            # fetched for you
twig-bb oa/maps/oa_dm3.bsp --content oa-textures --content oa-pak0
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
naming a map inside a pack (`twig-bb openarena:oa_dm1`) or naming the pack
(`twig-bb --fetch openarena-textures`) is itself the answer, since a pack
must be on disk before there is a window to ask in; anything else is asked in
the window, over the map it is about, with two buttons. A pack unpacks once per
user under `<cache>/twig-bb-content/<pack>` and every later run finds it there.

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
`<cache>/twig-bb-content/<pack>` — rather than into one more hash-named
per-archive tree, which makes it something you can find, point another tool at,
or delete on purpose. It is unpacked rather than read straight from the archive
because texture lookup lists directories to match names whose case differs from
the map's. A release that wraps its content in a version directory and a pak
directory is resolved to the level texture names are actually relative to.
`twig-bb-fetch --purge` removes it along with the unpacked maps.

One other gap is deliberate. Skyboxes are not drawn: a sky surface is a hole the
sky shows through (`SPEC-Q3SHADER §2.2`), and the hole shows the viewer's own
backdrop.

## How it is put together

| Module | What it does |
|---|---|
| `bspfile` | the `IBSP` container: header, directory, lumps |
| `q3bsp` | the format layer: lumps as arrays, entities as objects |
| `entities` | the entity lump's text syntax |
| `surfaces` | `SurfaceStyle` — translucency, masking, sky, scrolling, lightmapping, stated once |
| `worldgeometry` | batched triangles in scene space, and the map-to-scene axis convention |
| `q3geometry` | faces into those batches |
| `lightmapatlas` | thousands of small baked-light blocks into a few GPU pages |
| `q3shader` | Quake 3 `.shader` material scripts |
| `materials` | texture names to images, surface styles to PBR materials |
| `scene` | one shape per batch, with its lightmap page wired in |
| `jumppads` | push volumes, driven by the physics trigger system |
| `liquids` | water, slime and lava as volumes to swim in |
| `maploader` | check the version, read the map, and hand back a loaded map |
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
| `SPEC-TRIGGER-PUSH` | `trigger_push`, `trigger_monsterjump`, world gravity | clean-room |
| `SPEC-BSP46` | the `IBSP` v46 container | no copyleft source: a published format reference, this project's own earlier BSD reader, and sample bytes |
| `SPEC-Q3SHADER` | Quake 3 `.shader` material scripts | no copyleft source: the published shader manual and shipped map content |
| `SPEC-Q3PUSH` | version 46 aimed jump pads | no copyleft source: entity data observed in the 50 shipped OpenArena maps, plus projectile physics |
| `SPEC-Q3ENTITIES` | version 46 game entities: placed sounds (§1) and the pickups a map places (§3) | no copyleft source: every classname and key read out of the entity lumps of 67 shipped maps, with the counts recorded |

Three further specifications are retired. `SPEC-BSP38` (the `IBSP` v38 container —
Quake 2) is kept for provenance: the v38 reader has been removed, but many shared
modules still cite it for facts true of the whole Quake lineage — the unit scale,
the entity text syntax, yaw. `SPEC-LTMP` and `SPEC-RSCRIPT` were written and
implemented for Alien Arena and then retired with the code that read them. See
[`specs/README.md`](specs/README.md).

The procedure those specs were written under is
[`specs/CLEAN-ROOM.md`](specs/CLEAN-ROOM.md). If you extend this viewer and need a fact
that is not in a spec, request a spec revision — do not go and look it up in an
engine.

## Installing

To play without installing anything permanently:

```bash
uvx twig-bb
```

To install it:

```bash
pip install twig-bb            # from PyPI
pip install twig-bb[audio]     # with the sound-card backend, see Sound
pip install -e .               # from a checkout, for working on it
```

The import name is `twig_bb` and the distribution is `twig-bb`. Four commands
come with it, and the game also runs as a module, which needs no directory on
`PATH`:

| | |
|---|---|
| `twig-bb` | play — the start screen, or a map named on the command line |
| `python -m twig_bb` | the same thing, from any interpreter that can import it |
| `twig-bb-hud` | the HUD over a small lit room, with a weapon in hand |
| `twig-bb-fetch` | fetch and unpack an archive; prints the map path |
| `twig-bb-bsp` | report a map's contents without opening a window |

It needs `OpenGLContext` with a GLFW backend, `omi_physics`, `numpy` and
`pillow`. It does **not** need `requests` (downloads go through the
OpenGLContext resolver) or `simpleparse` (both script languages are hand-written
token scanners).

### As a binary, with no Python to install

The releases page carries two builds of each tagged version:

* **`twig-bb-<version>-windows-x64.zip`** — unzip it anywhere and run
  `twig-bb.exe`. `twig-bb-fetch.exe` and `twig-bb-bsp.exe` are beside it.
* **`twig-bb_<version>_amd64.deb`** — installs the game and the Python that runs
  it under `/opt/twig-bb`, with the three commands in `/usr/games`, and puts the
  game in the desktop menu. `apt install ./twig-bb_*.deb` rather than `dpkg -i`,
  so that the OpenGL and X11 libraries it asks the machine for are resolved.
  Sound is a *recommendation* rather than a requirement: without ALSA the game
  runs silently, which is what a missing backend has always meant here.

No map travels with either, for the same reason none travels with the wheel:
the content is other people's, under licences of its own (see
[Content Licensing Note](#content-licensing-note) and `NOTICES.md`). Both builds
fetch it the way an installed copy does — `twig-bb --list-packs`, then
`twig-bb openarena:oa_dm1`.

### Building them yourself

Both builds are cut by a tag — `dist/v3.0.0` builds the distributions for
`3.0.0` and attaches them to a release — and the version in the tag has to be
the one in `twig_bb/__init__.py`. This is deliberately separate from the version
bump on `main` that publishes to PyPI (`release.yml`), so a source release and a
binary release stay separate decisions. `.github/workflows/dist.yml` runs both,
and `workflow_dispatch` builds them from whatever is checked out without
spending a version number.

`packaging/` holds what either build needs:

| File | Holds |
|---|---|
| `requirements-stack.txt` | where the engine stack comes from, which is the one place either build says so |
| `entry.py` | the commands a bundle offers, and what each one runs |
| `twig-bb.spec` | the PyInstaller bundle |

To build them by hand, in an environment with the game installed **not**
editable — PyInstaller follows import statements and cannot see through an
editable install's import hook:

```bash
pip install -r packaging/requirements-stack.txt ".[audio]" pyinstaller
pyinstaller packaging/twig-bb.spec --noconfirm       # dist/twig-bb/

uv python install --install-dir runtime 3.12
oglc-deb --project . --extras audio --runtime runtime \
    --requirement packaging/requirements-stack.txt \
    --command twig-bb --command twig-bb-fetch --command twig-bb-bsp \
    --recommends 'libasound2t64 | libasound2' --output dist
```

Almost nothing about the engine is in the spec file: PyOpenGL and OpenGLContext
carry their own PyInstaller hooks, which PyInstaller finds by itself. `oglc-deb`
is part of the engine too. Both are documented in [Packaging an
application](https://github.com/mcfletch/openglcontext/blob/main/docs/packaging.html).

## Testing

```bash
pytest                      # the whole suite
pytest -m "not gl"          # skip the tests that open a window
pytest -m "not slow"        # skip whole-map loads and timing checks
```

The viewer's own tests are in three files rather than one:
`tests/test_viewer.py` for the command line, spawn placement, packs, looking and
walking; `tests/test_viewer_match.py` for the match a player meets -- dying and
coming back, the weapon wheel, the scoreboard, and where a shot goes when the
mouse aimed it; and `tests/viewersupport.py` for what all of them make up -- a
synthetic map on disk, a platform standing in it, and a context with no window
whose input path still runs.

Tests that need a sample map skip themselves when it is absent. The GL tests
either run the viewer in a subprocess and check that a frame was rendered, or —
for the combat effects — put the nodes in a scene, render, and check that pixels
changed where pixels should have. They are deliberately shallow: a reference
image of a particle system is a reference image of a random number generator.

`tools/replay_check.py` is not part of the suite and takes a few minutes: it
records a scripted match against a real map and replays it, which is the one
check that a session recording is worth what it claims — see [Recording a
session, and playing it again](#recording-a-session-and-playing-it-again).

The timing budgets (the projectile batch) skip themselves when something is
tracing, because a wall-clock budget measured under `--cov` is a measurement of
the coverage tracer — and again when **the machine is busy**, which they detect
by first measuring the same code at a twentieth of the scale. Three hundred
projectiles cost 12.5 ms of work on a quiet box and 31.5 ms for the identical
code with another suite running: cores, caches and memory bandwidth are shared,
so a fixed millisecond bound would fail for a reason nothing here can fix.
Loosening it instead would leave a number that no longer means "fits in a
frame", which is the only thing it is for. **Run one suite at a time** if you
want those numbers to mean anything.

### On CI

[`.github/workflows/test.yml`](.github/workflows/test.yml) runs on every pull
request: the suite on CPython 3.10 through 3.13 with a coverage floor of 95%,
`ruff check` and `mypy twig_bb`. A 3.14 row runs alongside and is advisory, so a
regression against a CPython prerelease is reported without holding up a merge.

A hosted runner has no display and none of the fetched maps, so CI deselects the
`gl` and `sample` cases with `-m "not gl and not sample"`. Those run on a machine
with a GPU, from the commands above.

OpenGLContext is installed from source in CI. The releases on PyPI predate the
scenegraph, movement and HUD modules this package imports, so `>=3.0.0a1` in
`pyproject.toml` names the version that actually satisfies the imports, and CI
takes it from its repository until a 3.0 release is published there.

### Cutting a release

[`.github/workflows/release.yml`](.github/workflows/release.yml) runs those same
checks on every push to `main`, then compares `__version__` in
[`twig_bb/__init__.py`](twig_bb/__init__.py) against PyPI. If the version is
already published the run stops there; if it is new and the checks are green, the
sdist and wheel are built and uploaded.

**Bumping the version is what cuts a release.** A push that leaves it alone is an
ordinary CI run. Nothing is published from a red build — PyPI versions are
immutable, and a release number burned on a broken build cannot be reused.

Uploading uses PyPI trusted publishing, so no API token is stored. It needs a
publisher registered on the PyPI project for this repository with workflow
`release.yml` and **the environment field left blank**: the OIDC claim carries no
environment, and a publisher that names one will not match.

## Where this is going

[PROJECT-PLAN.md](PROJECT-PLAN.md) is the route from a map you can walk to a map
you can play in: characters and bots, weapons, sound, the HUD and debug overlay,
animated fire and water surfaces, a start screen, the acknowledgements a project
built on freely-licensed content owes, and eventually multiplayer. It records
the design, the order, and which sources may and may not be read, and it marks
each phase with what is done and what is not.

The game that plan describes is **Twitchy GLitchy Bang Bang**. `twig_bb` is both
halves: the map-loading and rendering library, usable on its own as a component,
and the game built on it.

The game's own content — characters, weapons and their sounds — is **ours**,
authored in glTF and shipped with the code; the figures' bodies are CC0 base
characters, credited in
[twig_bb/assets/characters/CREDITS.md](twig_bb/assets/characters/CREDITS.md),
with everything else about them ours. What gets fetched is the levels: maps,
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
together rather than drifting apart.

The evaluation is `twig_bb.surfaceanim` (waves, coordinate transforms,
deformation, colour) and the application is `twig_bb.animator` (which
material field each answer lands on). Both are tested without a window: 154
tests over the numbers at known times. Against the shipped OpenArena scripts the
parser reads **1387 materials, of which 498 animate** — 226 rotations, 173
scrolls, 130 stretches, 113 moves, 106 colour waves, 70 alpha waves, 66 wave
deforms, 66 turbulences and 48 frame cycles.

**Which stage decides whether a surface is see-through matters more than it
sounds.** A material draws its stages in order, each over the one before, so
the *first* is what a player looks through — everything after it is detail
painted on top: an environment reflection, an additive glow, the lightmap.
Deciding from any stage made every lit floor in the game a sheet of glass with
the room below showing through, and dropped its lightmap along with it.

Two things are deliberately left out, both because a viewer drawing **one** PBR
material per surface cannot express them: several animated stages composited
over each other (`SPEC-Q3SHADER E.1`, `E.3`), and `deformVertexes autosprite`,
which is a camera-facing billboard rather than a property of the surface.

A `--capture` run pins the animation clock so a reference image is the same
every time; without that a visual-regression gate is useless for exactly the
maps this feature is for.

## Water, slime and lava

They are **volumes**, not floors. Liquid surfaces are left out of the collision
mesh, so you fall in; the volumes come from the BSP leaves, and being inside one
is what decides you are swimming. Across the fifty OpenArena levels that is
**1926 pools of water, 760 of lava and 27 of slime** in 29 maps.

**A swim starts at your eye and ends at your feet.** The liquid closing over
your head is what takes walking away from you, so that is where it begins —
paddling in the shallows is walking, not swimming. It holds until your whole
body is clear of the liquid, which is what lets you haul yourself out: your eye
reaches the surface a head's height before your feet do, and a swim that ended
there would drop you back in every time you broke the surface, leaving any pool
with a rim above its water impossible to climb out of. Hold forward and the
rise key (space) to get out of one.

Being under one changes three things.

**You swim, and swimming is not flying.** A swimmer collides with the world —
a pool has a bottom, a wall and a ceiling — and is pulled by whatever fraction
of gravity `SwimMode.buoyancy` does not cancel. Drag bleeds that away, so you
sink at a steady speed instead of accelerating; a swim that was simply noclip
let you leave a pool through its side, and one at falling speed made a pool
read as a hole in the floor. A stroke builds and coasts rather than switching
on and off.

**The controls do not change when you go under.** The mouse still steers — a
scheme that fell back to the turn keys the moment your feet left the floor
would take your aim away exactly where you need it — and *forward* means where
you are looking, up and down included, which is what swimming is. Strafing
stays level, because sidling should not sink you, and space and `c` still rise
and dive for holding depth while looking elsewhere.

**The volume is the water, not the room it is in.** Standing ankle-deep used to
fog the whole view, because the volume was the BSP *leaf* holding the pool and a
leaf reaches up to the ceiling. It comes from the liquid brush's own planes now
— across the fifty levels that turned 2713 leaf-boxes into 130 brush-boxes.

**The view fogs to the liquid's own colour**, through OpenGLContext's `Fog`
node. Water is a dim blue-green you can see a room's width through; slime is
thicker; lava is close and opaque, because you cannot see through molten rock
and a player who has fallen into it should be in no doubt which of the three it
is. The colour is a warning, not decoration.

It is a fog and deliberately not a tint over the screen: the weapon in your
hands stays clear while the far wall does not, which is what being inside a
medium looks like. A flat tint would colour both alike and read as a pane of
glass.

**The sound muffles**, through the whole-mix low-pass in the audio engine — 75%
under water, more under slime and lava, and never total, because silence reads
as the sound having broken.

**Two of them hurt.** Standing in slime or lava costs health, in a bite every
0.4 s rather than as a trickle — a number sliding down by one is not a warning
and being taken a chunk at a time is. Lava takes 32 health a second and slime
12; water takes none, which is a decision recorded in the same table
(`twig_bb.liquids.HARM`) rather than a hole in it. The numbers are ours, and
what they are chosen around is that lava should be a mistake you may just
survive crossing.

A death in one carries the liquid's name as its cause, so the line you read is
"You burned up in the lava" rather than a bare "You died", and the arena's own
rule — dying to the map costs a frag — applies without anything having to
invent a killer to put on the scoreboard.

The colours, ranges and muffles are this game's own numbers
([`twig_bb/underwater.py`](twig_bb/underwater.py)); no specification says
how far you can see through slime.

## Sound

A map's own ambience plays: wind over a courtyard, a furnace, water, the hum of
a light. **29 of the 50 OpenArena levels place at least one speaker and 381 in
all**, so this is a large part of what makes a level sound like itself, and it
arrives without anything being switched on.

Each `target_speaker` entity becomes an `AudioEmitter` at its origin, and the
render pass does the rest: it finds audible nodes while it is gathering the
frame, and **the camera is the listener**. The engine is OpenGLContext's
([docs/audio.html](../openglcontext/docs/audio.html)), on glTF's
`KHR_audio_emitter` model.

The entity's keys are specified in
[`SPEC-Q3ENTITIES §1`](specs/SPEC-Q3ENTITIES.md), measured from the shipped
content rather than looked up:

| Key | Becomes |
|---|---|
| `noise` | the sound, resolved against the content packs — the extension it carries is advisory, and a leading `/` is the same path |
| `origin` | where it is, through the same map→scene transform a spawn point uses |
| `spawnflags` bit 1 | whether it loops (336 of the 381 do) |
| `wait`, `random` | seconds between repeats of a one-shot, and the spread on that |

**Three things are deliberately not acted on**, and each is a case where doing
something would be worse than nothing. A speaker with a `targetname` is fired by
an event, and there is nothing here to fire it, so playing it as ambience would
turn a sound that should answer something into a constant — 28 are left out on
that ground. `spawnflags` bits 4 and 8 occur in real maps and mean nothing this
project has established, so the *bits* are ignored while the entity still plays.
And `angle` is not read as a cone however plausible that is; the spec records it
as unknown, so the code does not invent a reading.

A `noise` that resolves to nothing is a **silence and one warning, never a
failed load** — most installs have a map's geometry and not the base game's
sound. Across the 50 levels that costs exactly one speaker (a lava hum in `fan`
that is simply absent from the content). The developer overlay's Map section
counts the speakers that found a sound, which is the number that answers "why is
it silent"; its Audio section says what the engine is doing about them.

**No sound device is a normal machine, and so is no `miniaudio`.** Either one
gives one warning and a silent run, never an error and never a refusal to start.
Install the optional backend with:

```bash
pip install 'twig-bb[audio]'
```

## Fighting

`--bots N` puts opponents in the map and the scoreboard starts moving.

```bash
twig-bb openarena:oa_dm1 --bots 3 --difficulty hard
twig-bb openarena:oa_dm1 --bots 1 --difficulty near-passive   # a companion
```

**The left mouse button fires** — held, so it keeps firing at the weapon's own
rate — and `ctrl` does the same for anyone who would rather use the keyboard.
Both are declared bindings on the F6 page, because a mouse button is an input
with a name like any other. Three of the weapons are **hitscan**: the shot leaves the camera
down the middle of the reticule, meets the first thing in its way, and takes
that weapon's damage off whatever it met. A wall stops it, which is what makes
cover mean something. A shotgun sends eight traces scattered over the cone the
crosshair is drawing, so the reticule tells the truth about where a shot may
land.

**How far a trace flew is what decides what it costs.** Each weapon declares
the range its damage carries undiminished, the range by which it has faded, and
what is left at the far end — so a pistol is worth three times as much in
somebody's face as it is down a corridor, and a shotgun past seventeen metres
arrives, is heard, and does nothing. It is measured to what the trace actually
met rather than between the two of you, because the trace stops at the near
side of a body. **The rifle declares no fade at all**, which is its whole
argument: one hit anywhere it can see, a second and a half between shots, and
ten rounds. It is also the one weapon with a scope — hold the right mouse
button and the view narrows to 24°. The reticule is drawn through whatever
field of view the frame was, so what it says about where a shot may land stays
true while you are sighted rather than becoming a picture of the wide view.

**The right mouse button is held, not toggled**: a scope left on by accident is
a player who cannot see anyone walk up to them. Switching weapon, dying and
running out all give the wide view back on their own, because what the frustum
follows is whatever is in your hand this frame.

The other two **throw something**. A rocket is a *motor*, not a bullet: it
leaves slowly — walking pace, so up close it is a splash weapon aimed at the
floor rather than a flat one aimed at a chest — and thrusts hard to a top speed
a sidestep at any real distance cannot beat, bursting on contact. A grenade
arcs, bounces, and goes off on a fuse. Both are stepped as one batch of numbers
rather than as physics bodies, and both are **swept** — each tick casts from
where the projectile was to where it wants to be, so a rocket cannot be on one
side of a wall and then the other having touched nothing.

### Bursts, knockback and rocket jumps

A burst hurts everybody it can *see*: the damage falls off from the centre by
the projectile's declared curve, and a ray cast from the burst to each person
means a rocket round a corner does not kill. Only those inside the radius are
tested against geometry at all — a cast for everybody in the match would cost
more the busier the fight got.

**A near miss is meant to hurt**, and the curve is what decides that rather
than the damage: two metres off costs a third of a life for either launcher.
Without that a launcher is only a slow rifle, because what these weapons ask of
you is to aim at the floor beside somebody rather than at them.

The burst is centred where the round's *middle* was — one collision radius back
along the surface it met — rather than on the surface itself. Fifteen
centimetres of geometry, and it is the difference between a rocket at somebody's
feet and nothing happening at all: a point sitting exactly on a triangle is on
both sides of it, so the cast asking "can this burst see you" meets that same
triangle at no distance and reports the whole room to be behind cover.

It also **shoves** what it hurts, and it shoves the person who fired it. That is
the feature and not an oversight: a rocket at your own feet throws you, which is
a rocket jump, and the self-damage (`selfDamage`, a little under half a
rocket's splash) is
what makes taking one a decision rather than free movement. `selfDamage` scales
the damage and *not* the shove — you are thrown exactly as hard as anybody else
standing there, or your own rocket would lift you less than a plain jump does. The shove goes into
the same character-controller impulse a jump pad uses, so a rocket jump is
exactly as reliable as a jump pad.

### What you get back

Four things answer a shot, and each answers a different question:

- **The reticule's hit mark** — *did I hit them*. Only for a hit on a person and
  only for your own shot; a mark for a wall would make it a lie.
- **An impact effect** where the shot landed, chosen by what it met: metal
  sparks, everything else puffs. A hit on a person is its own bright, brief
  burst, sized to be read across a room at speed, because that is the job it is
  doing.
- **A sound** — the weapon firing, an impact on the level, and an impact on a
  person, which are three different questions and so three different sounds; a
  death and a burst have their own, and the burst is the loudest thing the game
  makes. **Your own weapon is not positional and everybody else's is**: a
  gunshot placed where it was fired from is how you find somebody you cannot
  see. A burst is placed even when it is your own, because a burst happens
  *somewhere* and that is the whole of what anybody needs to know about it.
- **A directional damage wash** when you are hit, at the screen edge you would
  turn towards. How much you lost is already on the meter; where it came from is
  the part you cannot see and have to act on.
- **The gun kicking**, which is the one piece of feedback that comes from what
  is in your hands rather than from the world, so it arrives even for a shot
  into the sky that meets nothing at all. It is thrown back and its muzzle
  lifts, and both settle over `recoilRecovery` seconds; the three numbers are
  the weapon's own, so a rocket launcher shoves harder and for longer than a
  pistol. Raising a weapon clears any kick left on it — something just brought
  up is not still recoiling.

- **The name of whoever is under the crosshair**, drawn just below it. It comes
  from the *same trace a shot takes*, so it names somebody only when a shot
  would actually reach them: a wall between you answers nobody, which is also
  what stops it being a way to find people through geometry.

### Who you are fighting

Everybody the rules move is drawn as a figure, and the figures ship with the
game: a male and a female build of the same crew, 5200 triangles each, on a
humanoid skeleton with nineteen animation clips. `twig_bb.characters` decides
which of those clips a body is playing from what the rules already know about
it -- how fast it is going, whether it is on the ground, what it is carrying and
whether it is dead -- and the engine plays them:

| What it is doing | What it plays |
|---|---|
| standing, or turning on the spot | `idle`, `turn_left`, `turn_right` |
| moving | `walk` under 4 m/s, `run` above it |
| off the ground | `jump` going up, `fall` coming down, `land` on arrival |
| dead | `die`, held on its last frame |

The weapon clips play *over* the movement, on a layer masked to the spine and
everything above it, so a figure runs and fires at the same time. What it is
carrying is mounted on an attachment point in its right hand, so the weapon a
combatant holds is the same `.glb` the pickup and the first-person view use —
and it is *the model* that says where a hand takes hold of it, so a rifle sits
in a fist rather than hanging off it by whatever point it was modelled about.

What is in the hand follows what the rules say, checked each frame, so picking
a different weapon up changes what everyone sees somebody carrying with nothing
having to send an event about it — and a body that is dead is a body playing no
weapon clip, which is a body holding nothing. One model is loaded per weapon
and shared by everybody carrying that one, so a room of bots with rifles is a
single instanced draw rather than one per bot.

A figure that will not load leaves the body drawn as a plain capsule and the
match carries on: the rules decide a match, not the art.

**Which way it is going decides what it plays**, in its own frame rather than
the world's: a bot backing away from you while it shoots plays a backward walk,
and one crossing in front of you sidesteps. Cycles play at the rate the body is
really travelling, so feet stay on the ground instead of skating. And a body
turns to face **where it is looking** before where it is going, which is what
makes somebody shooting at you look like they are shooting at you.

**Watching it out of the game.** `twig-bb-bots` puts one bot in front of a
camera, scripts what the rules would be saying about it -- walking, backing
off, sidestepping, turning onto a target, being shot -- and lays the frames out
as contact sheets with an index page. It drives the same `move_bodies` the
match calls, so what lands on the sheet is what a player sees, and it is how
every one of these was judged:

```bash
twig-bb-bots --out sheets/
twig-bb-bots --out sheets/ --weapon pistol --takes firing,turn-and-shoot
```

**Authoring your own.** [CHARACTER-RIG.md](CHARACTER-RIG.md) is the contract --
the skeleton's bone names, the clip names, the attachment points, the materials
and the budget. Anything that satisfies it is a character here, and swapping one
in is a name in `twig_bb.characters.BUILDS` rather than a code change. The two
that ship are generated by
[`grass-clumps/character.py`](../grass-clumps/character.py), and
`oglc-character-sheet` renders every clip of a model from four sides so a new
one can be checked against the contract by looking at it.

### Dying

Death takes the camera away. It falls to near the floor, where a body would be,
and turns to look at whoever did it — the one thing you want to know in that
second and the one thing you cannot otherwise get. The world goes on being drawn
behind a red wash, because watching the fight continue without you is most of
what a death is; the wash is well short of a curtain for the same reason.

**The trigger is what brings you back.** The countdown is a floor rather than a
trigger — it is the shortest a death can be — and once it has run out the notice
stops counting and says *fire to respawn*. A death that ended on the timer alone
would put you back in a corridor you were not looking at, usually while you were
reading the scoreboard. Pressing fire early is remembered rather than swallowed,
so a trigger pulled the instant you die brings you back the moment the wait is
over.

Coming back gives you the **starting loadout** and nothing else: whatever you
had picked up is lost, which is what makes the things a map places worth walking
to. Armour does not come back either.

Deaths and the end of the match are announced over the middle of the screen;
individual hits are not, because a line per bullet is a wall of text.

### Where you spawn

A respawn goes to one of the points **far from everybody currently alive**,
picked at random among them. Two opposite failures are being avoided. Always
choosing the same point puts the whole match on one square, standing inside one
another and shot again before the screen has settled. But always choosing the
*furthest* point is just as predictable: a player who stands still can wait at
the far end of the level and shoot each arrival as it appears. What is measured
is the distance to the **nearest** living combatant — a point far from the crowd
but touching one opponent is the worst place in the level to arrive — and
anything within `SPAWN_SPREAD` of the best is as good as the best.

The opening of a match is chosen the same way, so two matches on one level do
not begin identically.

### Picking things up

A level is a **circuit**, and the things placed around it are what give it a
shape: health where the fighting is thickest, armour behind a jump you have to
commit to, a rocket launcher somewhere everybody walks past. Every one of the 67
sample maps places at least one — 3561 in all, an average of 53 a map — so a
viewer that ignores them ignores most of what the author placed, and a match is
a fixed loadout spent once.

Walk into one and you take it. On `ztn3dm1` that is 44 things — eleven armour
shards, seven small medikits, three rifles, a rocket launcher, a body armour and
a mega health among them — with the nearest 4 m from a spawn point. What each is
worth *here* is a declared table (`twig_bb.items`), and the join to the map is
the classname the level was authored with, so the amounts are tunable without
touching the reader:

| What a map placed | What it gives here |
|---|---|
| `item_health_small`, `item_health`, `item_health_large`, `item_health_mega` | 5, 25, 50 or 100 health |
| `item_armor_shard`, `item_armor_combat`, `item_armor_body` | 5, 50 or 100 armour |
| `ammo_bullets`, `ammo_shells`, `ammo_cells`, `ammo_rockets`, `ammo_grenades` | that pool, refilled |
| `weapon_shotgun`, `weapon_rocketlauncher`, `weapon_grenadelauncher` | the weapon, **with ammunition in it** |
| `weapon_railgun`, `weapon_lightning`, `weapon_plasmagun`, `weapon_chaingun` | the rifle: no counterpart exists here, and the nearest one keeps the level's circuit intact |

**A weapon you walk over goes into your hands**, not just onto the bar — but
only when it beats what you are already holding. Which beats which is the
table's `slot` order, the same order the number keys use, so walking over a
rocket launcher while holding the pistol arms you with it and walking over a
pistol while holding the rocket launcher does not disarm you. One you already
have is a pickup for the ammunition inside it and leaves your hands alone.
Whatever you are holding is what is drawn in front of you: `1`–`5`, the wheel,
a pickup and a respawn all move the same one thing.

**It pops when you take it**, and it pops *where it was* rather than in your
ears: somebody else clearing the armour off the far side of the level is worth
knowing about and worth being able to point at. The sound is a bubble going,
which is what the pickups are — a rising tone, because a cavity that is closing
gets smaller and something smaller rings higher, and a falling one would read
as a drop of water. It is the only bright thing the game makes, so it carries
through a firefight without being loud; it does not outrank a hit on a person
when there are more sounds than voices, because good news can wait a frame and
*did I hit them* cannot.

An item nobody can use **stays on the floor** — walking over a medikit at full
health does not destroy it for everybody else — and one that is taken comes back
after its own interval, which the map may override with a `wait` key. Timed
powerups (quad, haste, invisibility) are content this game does not have; they
are skipped and *counted*, and the count is on the load report and in the
developer overlay, because a level whose whole weapon circuit is content nobody
has plays exactly like a reader that failed.

Where all of this comes from is [`SPEC-Q3ENTITIES §3`](specs/SPEC-Q3ENTITIES.md),
which is explicit about which parts are observed in map files and which parts
are ours.

#### What they look like

The four health pickups are drawn as a **medikit**: a cross floating inside a
glass bubble, half a metre across, turning on the spot so it does not read as
part of the wall. It is ours, it is BSD, and it is credited in
[`twig_bb/assets/items/CREDITS.md`](twig_bb/assets/items/CREDITS.md) —
which is the rule for all art here, and is enforced by a test.

**All four are the same model in four different colours**, and the colour is
the whole signal: you decide whether to cross a room for a pickup from the
other side of it, and at that range the shape is a smudge while the hue is not.
So they are four hues far apart rather than four brightnesses of one — white
for the 5, **red** for the 25, blue for the 50 and gold for the mega. Red is
the middling one rather than the best one on purpose: a red cross means
"health" to everybody, and that meaning is worth most spent on the pickup a map
places most often.

The colour is the `colour` field of the `ItemKind`, applied to the model when
it loads, so a fifth variant is a row in the table and no new geometry.
Everything else about the material — the bubble's transparency, its metallic
and roughness, its sheen — is the model's own, which is what keeps the glass
looking like glass in all four. A kind that names no model, which is every
armour, ammunition and weapon pickup for now, is still drawn as a coloured box:
a level's circuit has to be playable before everything in it has been modelled,
the same reason the bots are capsules.

Placement is data too — `model`, `modelScale` and `modelOffset` are fields of
the `ItemKind` — so putting different art on a pickup is a table edit and never
a code change. `tools/clean_model.py` is the Blender script that tidies the
source `.blend` and exports the `.glb`; what it fixed in this one is recorded
beside the model.

### Knowing whether you are winning

Your frags sit in the top-right corner against the match's limit, all the time,
because that is a question you have continuously and nobody holds a key to
answer one of those. Holding **tab** puts the whole board up — everybody's frags
and deaths — which is a comparison and is read between fights. It is a held key
rather than a toggle: it covers the middle of the screen, and a board left up by
accident is a board you get shot behind.

### Falling out of the level

Nothing in a map stops a fall. Step off the edge of one built as an island and
there is nothing below to land on and nothing above to come back to — the camera
never stops and no message is ever printed, which reads as the game having hung.
A floor a hundred metres below the map's own bounds ends it as a named death,
for opponents as much as for you.

`--effects full|reduced|off` decides how much of the impact and blood is drawn.
It **filters presentation and cannot change play** — the events it reads are
emitted whether anything is drawing them or not — which is what makes it safe
for two players to set differently.

**The sounds are ours, and they are arithmetic rather than files.** Every one is
synthesised through `omi_audio.synth` from numbers declared in
`twig_bb.combatsound`, so the game ships with a full complement of sound, no
audio files, and nothing to check under
[CLEAN-ROOM](../CLEAN-ROOM.md). A voice may name a file instead, which is how
commissioned or CC0 content would replace a synthesised stand-in: a table edit.
A sound that will not resolve is a silent shot and never a crash.

Each voice declares which of two **shapes** it is made from. An `impact` is
noise under a decay: bright however long it rings, which is what a crack, a
snap and a ping are, and it is what a round *arriving* sounds like. A `rumble`
is noise with the top rolled off over a tone that falls as it goes, saturated
until it growls — the bottom of the range, where a motor and a detonation
belong. Its numbers — `cutoff`, `pitch`, `pitchEnd`, `tone`, `drive` and
`attack` — are fields of the voice like everything else.

`cutoff` and `floor` are where a rumble's noise rolls away above and below, and
the two together are a **band** — which is what anything hollow is. A tube
rings around a pitch and has almost nothing underneath it, and that is the
whole difference between the pop of a mortar and a thump.

A voice may also declare an **echo** — how loud the first return is, how far
behind it arrives, and where a return loses its top and its bottom (`echo`,
`echoDelay`, `echoDamping`, `echoThinning`) — or a **room**, which is `reverb`
and `reverbSeconds`. They are not two strengths of one thing. Discrete returns
are heard as *repeats*, a clap and then another clap; a room is heard as one
sound going on, dense and darkening as the air takes the top out of it. Over a
short bright report the first reads as applause and only the second reads as a
place.

**Every weapon firing is a rumble**, because a report is a small explosion and
how much of one is the first thing anybody hears. What separates them is how
much of each is the *charge* and how much is the *round leaving*:

| | Sounds like | Where it sits |
|---|---|---|
| Shotgun | an explosion that barely holds together | lowest of the lot; three fifths below 100 Hz, and less than half of it at any pitch at all |
| Pistol | a bang rather than a ping | almost all charge — two thirds below 400 Hz, one per cent above 4 kHz |
| Rifle | a hard, sharp crack with a valley behind it | the only bright thing in the loadout: the crack is over in fifty milliseconds and the room it leaves goes on for two seconds, darkening from 5 kHz to 1.8 as it dies |
| Grenade launcher | the pop of a mortar | a hollow band around 230 Hz, with the bottom taken off as well as the top: a tube coughs rather than thumps |
| Rocket launcher | a motor lighting | a roar with no pitch in it, taking a moment to catch; meant to be heard behind you |
| A burst | the deepest thing there is | a second of tail to take cover during |
| Picking something up | a bubble going | the **only** bright thing in the table: a rising pop, so the one piece of good news cuts through a firefight without being loud |

**Weight comes from `tilt`, not from `tone`,** and this is the trap worth
naming because both of the sounds here that got it wrong got it wrong the same
way. A low sine under a hard attack is a *drum*, and one that falls as it goes
is a drum being tuned — which is what a listener hears whenever the tone is
carrying the bottom end, however small its share. A rifle built that way is a
tom; a rocket built that way is an instrument playing a descending note. `tilt`
leans the *noise* toward the bottom instead, which is what a blast and a motor
actually are, and both of those voices now have no tone in them at all.

The rifle is the one weapon whose sound is mostly the *round* rather than the
charge: it leaves faster than sound, so what a listener gets is the whip of
that and then the report coming back off whatever is around. It has almost no
weight low down and does not want any — **a short bottom-weighted noise burst
with a hard attack is a drum**, which is the less obvious half of the same
trap, and it took three passes to stop building one. What says *high-powered*
about it is not the bottom of the spectrum but the two seconds of room behind
it.

It also names **its own impacts**, and it is the only weapon that does: a round
that heavy arriving is a *chunk*, and the generic ping made a shot that ends a
fight sound like a stone hitting a window. Everything else keeps the generic
pair, which is where the pistol's ping now lives — the small calibre is heard
when it lands rather than when it fires.

**Two recordings were measured to get the pistol and the rifle there**, and
nothing was copied from either: what came across is a handful of numbers —
how the energy of one report is shared between the bottom, the middle and the
top, at the crack and again in the tail — and our arithmetic was aimed at them.
The recordings are not in this repository and carry no licence into it. Ours
land at 491 Hz against a measured 475 for the pistol's crack, and 3.6 kHz
against 3.6 for the rifle's, with 17% of its power below 400 Hz against 18%.

### The difficulties

| | Reacts in | Aim error | Aim closes | Leads a target | Avoids its own blast | Fights |
|---|---|---|---|---|---|---|
| `near-passive` | 1.5 s | 25° | 0.15 | 0.0 | 0.0 | **no** |
| `easy` | 1.0 s | 14° | 0.25 | 0.15 | 0.2 | yes |
| `medium` | 0.55 s | 7° | 0.45 | 0.5 | 0.6 | yes |
| `hard` | 0.3 s | 3° | 0.7 | 0.8 | 0.85 | yes |
| `nightmare` | 0.15 s | 1° | 0.95 | 1.0 | 1.0 | yes |

Every one of these is a skill rather than an exemption. **How fast the aim
closes** is the share of the way to the target a bot's aim travels per decision:
one whose aim arrived the instant it decided would be a bot nobody could dodge,
because strafing across it is answered before the step has landed. **Leading** is
aiming ahead of somebody crossing you: a slow projectile fired where a target
*is* arrives where they *were*, and a bot works out how fast they are moving by
watching them do it rather than by reading the rules. **Avoiding its own blast**
is how far a bot keeps before it will fire a splash weapon — the projectile's
own radius plus a margin, scaled by this number, so a bigger burst is kept
further away. A careless bot will happily rocket a wall two feet from its own
face, which is exactly what the bottom of the ladder should do.

A bot also will not throw something it cannot reach you with. A grenade falls at
fourteen metres a second squared and a bot aims straight down the line to its
target, so past about eight metres a flat throw is in the floor before it
arrives; the limit comes from the projectile's own speed, gravity, fuse and
lifetime, so retuning the table moves it. It will not choose a weapon that
cannot hurt you where you are standing, either — a shotgun across a level is a
bot in the open firing at somebody it cannot reach.

**And no bot fires faster than the weapon in its hands.** How often it thinks
and how often its weapon shoots are two clocks, and only the first of them is a
difficulty: the hardest bot decides twenty times a second, and held to nothing
but that it would empty a rocket launcher into you in the frame you walked into
view. What makes a hard bot hard is that it aims well and commits quickly, not
that it is holding a different rifle from the one you picked up.

**A bot fires from the loadout it carries, exactly as you do.** It spawns
holding the pistol and goes and finds the rest — its shots come out of the same
`PlayerState` a player's do, each one spends a round, and a weapon it never
picked up or has emptied is simply not on the menu when it chooses. So a bot and
a player spawning in view of each other are on the same footing, the launcher is
something a bot has to *reach* on the map rather than something it was born
holding, and the same fights stop being the same: a bot with a rocket in its
pack plays one way and the same bot down to its pistol plays another. A respawn
restores that starting pistol, and the level's ammunition and weapon pickups are
where a bot rearms — the circuit it runs is the one you run.

`near-passive` is both a real setting — company while you look around a level —
and the fixture navigation is checked against, because a bot that walks and does
not shoot is how movement is verified without combat in the way.

**The senses never scale, and that is the rule the whole range rests on.** No
seeing through walls, no knowing where you are without having perceived you, no
hidden damage. Every difficulty uses the same line-of-sight ray cast your own
shots use; only the reaction, the aim and the decisions change. A bot that
cheats is not difficult, it is annoying, and once one hidden advantage is
allowed there is no reason to believe the next rung is skill rather than another
exemption.

The ladder is verified by playing whole matches **headlessly** and asserting the
ordering holds — over four 45-second matches per pairing, nightmare beat easy
64–0, hard beat medium 41–6, and medium against medium finished 8–7. The
harness never asserts *how* a bot won, so a bot made hard by a hidden multiplier
would pass it; that has to be caught by reading the code, which is why the
perception is one function every difficulty calls.

**Opponents walk in the same capsule you do** — the same move-and-slide, the
same step height, the same slopes, the same ground snap — so anywhere you can go
one can follow, and one that is placed inside geometry is dug back out of it.
The only difference is the pace, which is slower than yours: a bot that could
run exactly as fast as you can would be impossible to escape and dull to chase.
Being blown about goes through the controller's own impulse, so a rocket at a
bot's feet throws it exactly as a rocket at yours throws you.

Every bot looks around at most ten times a second rather than every frame, and
the ten are spread so a room full of them do not all look on the same one.
Looking is the expensive half of an opponent — each asks line of sight of
everybody else, which is quadratic in the count — and at eight opponents that
was past a whole frame on its own. It is invisible because the interval is
shorter than the fastest reaction on the ladder: a bot answers a sighting no
sooner than its `reactionTime`, so delaying the sighting itself by less than
that changes nothing anybody can feel. Slowing a *sense* down far enough to
matter would be a difficulty change by the back door, which is the one thing
this ladder is built to prevent.

A fresh opponent does not start in the same state as every other one: which way
it happens to be looking when it arrives, how long before it first commits, and
which way it wanders when it has nothing to fight are all spread. Neither of the
first two is a difficulty — a hard bot is not one that arrives facing you — and
both are what a person entering a room does differently every time.

Opponents are drawn as capsules. That is the designed stand-in and not an
oversight: fighting had to be buildable before there was any art, and
[§5](PROJECT-PLAN.md) is where the art goes.

## What is not implemented

Recorded as decisions rather than oversights:

- **Brush-model movers.** `func_door`, `func_plat` and friends are drawn where
  they stand and do not move (`SPEC-TRIGGER-PUSH §10` describes what a mover
  would need). In some maps the thing in front of the spawn that looks like a
  jump pad is one of these: a rising plate, not a push volume.
- **`func_conveyor` and the current content bits** (`SPEC-TRIGGER-PUSH §9.5`) —
  a movement-solver feature rather than a pad.
- **Footstep and pickup sounds.** Weapons, impacts, bursts and deaths all make
  a noise (see [Fighting](#fighting)); walking and picking something up do not.
  Footsteps want a step event the character controller does not yet emit; a
  pickup now says so on the HUD and is silent, which is the half that is left.
- **Decals.** An impact leaves a burst of particles and no lasting mark.
  Deliberate: the burst delivers most of the readability, and a decal system is
  real work — projection onto the geometry, a budget, a fade — so it waits until
  playing says it is wanted rather than being assumed.
- **First-person animation.** The weapon in your hands recoils — thrown back
  and its muzzle lifted, settling over the weapon's own recovery — but does not
  sway or reload; it is a model on a transform. The clips arrive with
  [§5](PROJECT-PLAN.md)'s commission.
- **A name over an opponent's head.** Who you are pointing at is named under
  the crosshair (see [What you get back](#what-you-get-back)), which answers
  the question a fight asks. A world-space plate over each body is not built:
  `OpenGLContext.scenegraph.billboard.Billboard` says of itself that it is a
  stub, and its `transform` does nothing, so a plate would need the billboarding
  implemented in the engine first — and it is worth deciding at the same time
  whether names should be visible through walls, because always-on ones give
  positions away and change how the game plays.
- **Shoot-to-trigger doors.** `func_door`, `func_button` and the
  `target`/`targetname` links are not read, so map geometry that looks like a
  door does nothing when shot. It is the same missing machinery a map's
  triggered speakers want, and the entity facts belong in `SPEC-Q3ENTITIES`
  beside the pickups before any code is written.
- **Timed powerups.** `item_quad`, `item_haste`, `item_invis` and the rest are
  read, recognised as pickups and deliberately not answered — there is no
  counterpart here to give. They are counted rather than dropped in silence.
- **Path-finding.** There *is* a navmesh
  ([`OpenGLContext.nav`](../openglcontext/OpenGLContext/nav/navmesh.py)) — it
  builds 1220 connected cells on `oa_dm1` in 0.03 s and does A* with a
  string-pulled path — but no spawn point resolves to a cell on a real level
  yet, so the bots are deliberately still walking headings rather than routes.
  They no longer *stick* on geometry, because they walk in the player's own
  capsule and slide along a wall met at an angle; what they still cannot do is
  route around one. [§3b T2](PROJECT-PLAN.md) says where it stops.
- **Stepping up lurches the view forward.** Measured at 45.8 cm in the frame
  that mounts an 18-unit step, where 12.7 cm was due. Known, measured and
  recorded as [§3b B1](PROJECT-PLAN.md); the measurement is
  `omi_physics/tests/test_character_step_pace.py`, marked `xfail`.
- **Visibility culling.** Neither family's visibility lump is decompressed; the
  whole map is drawn and the frustum does the culling.
- **Multi-style lightmaps.** Only the always-on style-0 block is read, which
  `SPEC-BSP38 §7.6` permits and `SPEC-LTMP §7.8` recommends given that the
  original's own multi-style path is disabled.
