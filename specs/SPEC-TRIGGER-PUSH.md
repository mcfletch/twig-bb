# SPEC-TRIGGER-PUSH: jump-pad / push-volume entity behaviour in Quake-lineage maps

> **Status (2026-08).** twig-bb reads only `IBSP` version 46 (Quake 3 /
> OpenArena) maps; the version 38 (Quake 2) reader has been removed. This spec
> is **retained and live**: the push-volume, world-gravity and `func_door`
> vocabulary and arithmetic it records are shared across the Quake lineage, and
> the current Quake 3 push implementation (`twig_bb.jumppads`) cites it
> throughout. Its provenance is genuinely Alien Arena (the source read under the
> clean-room wall below), and that is left unaltered; the **Alien-Arena-specific
> divergences** it flags (deathmatch door doubling, monsterjump-affects-players,
> the low-gravity mode) are historical notes about that source rather than
> behaviour of the current viewer.

| | |
|---|---|
| Source consulted | Alien Arena — https://github.com/alienarena/alienarena.git |
| Licence of source | GPLv2 (`unix_dist/GPLv2`) |
| Version / commit | `a1aaf7fed8f5e2825c94406cbf2071e7ed3b6542`, Mon 15 Jun 2026 |
| Files consulted | `source/game/g_trigger.c`, `source/game/g_utils.c`, `source/game/g_func.c`, `source/game/g_spawn.c`, `source/game/g_save.c`, `source/game/g_main.c`, `source/game/q_shared.c`, `source/game/q_shared.h`, `source/game/g_local.h`, `source/qcommon/pmove.c`, `source/server/sv_world.c`, `Tools/defaults/entities.def` |
| Non-copyleft sources checked first | See "Rule 0 record" below. |
| Reader | Claude Opus 5 sub-agent (Reader role, clean-room procedure per `CLEAN-ROOM.md`) |
| Date | 2026-07-25 |
| **Clean-room status** | **Clean.** This spec is the sanctioned channel: the Reader wrote no project code, and the implementation built from it is written by someone who has not read the copyleft source. Facts below are the only thing that crossed the wall. |

### Rule 0 record

Non-copyleft sources were consulted **first**, and they carry a substantial fraction of what follows:

| Checked | Outcome |
|---|---|
| Published Quake 2 entity/mapping reference (gamers.org `q2_entities.html`, `Q2DP_Map`) | Confirms `trigger_push` exists, reads `speed`, and that `speed` defaults to 1000. Confirms most `func_door` keys and defaults (`speed` 100, `wait` 3, `lip` 8, `dmg` 2) and the START_OPEN / TOGGLE / NOMONSTER flags. Silent on the velocity scaling, on spawnflag *bit values*, on the direction-derivation special cases, and on the link-time bounding-box adjustment. |
| Community mapping wikis / tutorials (quakewiki.org `trigger_push`, quake2.com jump-pad tutorial, OpenArena mapping manual) | Confirms `angle = -1` means up and `angle = -2` means down; confirms `angles` (pitch/yaw/roll) may be used instead; confirms the mapper convention of writing `angle 360` rather than `0`. Confirms `sv_gravity` default 800. Confirms the "× 10" velocity scaling exists in the Quake lineage. These are CC-BY-SA-ish texts, so the *facts* are restated here in this Reader's own words and none of the text is reused. |
| Valve Developer Community `Quake II.fgd` (an editor entity-definition file) | HTTP 403 — could not be retrieved. |
| Editor entity-definition file shipped with the source (`Tools/defaults/entities.def`) | Present, but it lives inside the GPLv2 tree, and for `trigger_push` it documents only the existence of `speed`. Insufficient, and not licence-clean anyway. |
| Observed behaviour (running the engine, measuring) | Not attempted: no build of the engine and no sample map were available in this environment, and the timing-sensitive facts (per-frame reapplication) would need instrumentation. |

**Conclusion:** the licence-clean sources cover the key vocabulary and most defaults, but do **not** cover the exact velocity scaling factor, the spawnflag bit assignments, the behaviour when the orientation keys are absent, the link-time bounding-box growth, the reapplication cadence, or any Alien-Arena-specific divergence. Those facts were taken from the GPLv2 source under the wall, and every fact below is written in this Reader's own words.

## Scope

A third party writing an independent engine or an importer wants to reproduce the behaviour a level designer encoded when they placed a jump pad, wind tunnel, or push volume in a Quake 2 or Alien Arena `.bsp`. This document states the entity keys involved, their defaults, the arithmetic that turns those keys into an imparted velocity, the geometry of the affected volume, the cadence at which the effect is applied, and the world constants against which pad strengths are conventionally quoted. It also enumerates every other mechanism in this engine family that can move a player without player input, so an importer knows whether it has covered the space.

A short, importer-oriented treatment of `func_door` is appended (§10) for a possible future feature; it is deliberately limited to what a map importer must know.

Everything here is written for the Alien Arena fork at the commit above. Where that fork diverges from stock Quake 2 behaviour as documented by the public mapping references, the divergence is flagged explicitly.

## Facts

### 1. The `trigger_push` entity

**1.1** The classname is `trigger_push`. It is a brush entity: the map compiler emits it with a `model` key whose value is a reference to an inline BSP submodel, conventionally written as an asterisk followed by the submodel index (for example `*7`).

**1.2** The entity keys `trigger_push` reads are, in full:

| Key | Type | Default if absent or zero | Meaning |
|---|---|---|---|
| `model` | inline submodel reference | (required; supplied by the compiler) | defines the volume — see §5 |
| `speed` | number | **1000** | push strength — see §2 |
| `angle` | number | none (see §3.5) | push direction, yaw-only shorthand — see §3.2 |
| `angles` | three numbers | none (see §3.5) | push direction, full orientation — see §3.3 |
| `spawnflags` | integer bitfield | 0 | see §4 |
| `origin` | three numbers | 0 0 0 | offsets the submodel bounds — see §5.3 |

**1.3** `trigger_push` reads no other keys. In particular it has no `target`, no `targetname`, no `wait`, no `delay`, no `height`, and no per-axis velocity keys. It cannot be switched on or off, and it cannot be aimed at a destination entity. (This distinguishes it from the Quake 3 family, where jump pads are commonly aimed at a target entity and the engine solves a ballistic arc. **No such mechanism exists here** — the direction is always an orientation, never a destination.)

**1.4** A `speed` value of exactly zero, or an absent `speed` key, both yield 1000. There is therefore no way to author a zero-strength push via `speed`; the substitution is unconditional on the value being zero, not merely on the key being missing.

### 2. Velocity imparted

**2.1** When the push fires on an eligible entity, that entity's velocity is **set to**

> **velocity** = **d** × *speed* × 10

where **d** is the unit push direction from §3 and *speed* is the key from §1.2. All quantities are in world units and world units per second.

**2.2** The factor of 10 is unconditional and is not derived from any other key or from the server tick rate. It is a fixed part of the relationship between the authored `speed` number and the resulting velocity.

**2.3** With the default `speed` of 1000, the imparted speed is therefore **10 000 world units per second**.

**2.4** The assignment **replaces** the entity's velocity outright. Any velocity the entity had on entering the volume — run-up speed, residual fall speed, a previous pad's impulse — is discarded, not added to. There is no accumulation and no clamping.

**2.5** Consequences of §2.4 that an importer must reproduce: (a) a player entering a pad at high horizontal speed leaves it with exactly the pad's velocity and no more; (b) a player falling into an upward pad is not slowed proportionally — the downward component is simply erased; (c) two overlapping push volumes do not sum, and the one whose effect is applied last in a given frame wins.

**2.6** Eligibility. The push is applied to a touching entity if **either** of the following holds:
- the entity's classname is exactly `grenade`; **or**
- the entity's health is strictly greater than zero.

Entities failing both tests — corpses, gibs, dropped items, most projectiles other than grenades — are unaffected. Note that health > 0 is not restricted to players: any living entity, including bots and monsters, is pushed identically.

**2.7** Additional effects when the pushed entity is a player client, both of which are cosmetic/quality-of-life rather than physical:
- the client's fall-damage reference velocity is resynchronised to the newly assigned velocity, so the pad's own impulse does not itself register as a fall and produce landing damage on the way down;
- a wind sound is played on the pushed entity, rate-limited so that it plays at most once per **1.5 seconds** per entity.

**2.8** No damage, no gravity change, no friction change, and no change to the player's ground state is applied by the push itself. (Whether the player is subsequently treated as airborne follows from the ordinary movement code once the new velocity carries them off the floor.)

### 3. Deriving the push direction

**3.1** The push direction is a unit vector derived once, at map load, from the entity's orientation triple. The triple is ordered **(pitch, yaw, roll)** — index 0 is pitch, index 1 is yaw, index 2 is roll. See §6 for the geometric convention and the forward-vector formula.

**3.2** The `angle` key is a **yaw-only shorthand**. A map that supplies `angle` with numeric value *a* is equivalent to one supplying the orientation triple (0, *a*, 0). Pitch and roll are forced to zero; any prior value is overwritten. `angle` is therefore incapable of expressing a tilted push except through the special cases in §3.4.

**3.3** The `angles` key supplies all three components directly, in the order pitch, yaw, roll.

**3.4** **Special-case values.** Two orientation triples are *not* interpreted as orientations at all, and instead select a fixed vertical direction:

| Orientation triple | Push direction |
|---|---|
| exactly (0, −1, 0) | (0, 0, +1) — straight up |
| exactly (0, −2, 0) | (0, 0, −1) — straight down |

Because `angle` expands to (0, *a*, 0) per §3.2, the familiar mapper idiom `angle -1` (up) and `angle -2` (down) falls out of this. Two consequences an importer must get right:
- The comparison is against the **whole triple**, not against the yaw component alone. `angles "0 -1 0"` is therefore also "straight up", while `angles "10 -1 0"` is **not** a special case and is treated as an ordinary orientation with a yaw of −1 degrees.
- The match is exact equality on all three components. A value of −1.0001 is not a special case.

**3.5** **Absent or zero orientation.** The direction is computed **only** if the orientation triple differs from (0, 0, 0) in at least one component. If the map supplies no `angle` and no `angles`, or supplies values that leave all three components at zero, no direction is computed and the push direction remains the **zero vector**.

**3.6** The observable consequence of §3.5, which an importer must reproduce rather than "fix": such a `trigger_push` sets a touching entity's velocity to **(0, 0, 0)** every frame it is inside — because §2.1 multiplies a zero direction by the speed and §2.4 assigns rather than adds. A `trigger_push` with no angle is a *freeze volume*, not a no-op and not a default-direction push. Maps in the wild may rely on this.

**3.7** This is why the mapping convention is to write **`angle 360`** rather than `angle 0` when a push along +X is wanted: 360 is a non-zero key value that passes the §3.5 test, and yields the same forward vector as 0 (see §6.4).

**3.8** After the direction has been derived, the entity's stored orientation triple is reset to (0, 0, 0). The orientation is consumed by the direction derivation and does not additionally rotate or re-orient the brush volume. An importer that keeps the authored angles on its trigger object must ensure they have no further geometric effect.

**3.9** The derived direction is a **unit** vector in the ordinary orientation case (§6.5) and in both special cases (§3.4). §2.1's magnitude therefore depends only on `speed`.

### 4. Spawnflags honoured by `trigger_push`

**4.1** `trigger_push` examines exactly **one** bit of `spawnflags`:

| Bit value | Name used in editor entity definitions | Effect |
|---|---|---|
| **1** (bit 0) | `PUSH_ONCE` | After the push has been applied, the trigger entity is removed from the world. It can therefore affect at most one touch event in the entire match. |

**4.2** All other `spawnflags` bits are ignored by `trigger_push`. There is no "start off", no "toggle", no "players only", no "no monsters", and no "add to velocity" flag.

**4.3** Note the removal in §4.1 is unconditional on whether an eligible entity was actually pushed — it happens on any touch that reaches the push handler, including by an entity that failed the §2.6 eligibility test. An importer should destroy the volume on first contact by any entity that the trigger dispatch delivers to it, not on first *successful* push.

**4.4** With `PUSH_ONCE` clear (the default), the volume is permanent and reapplies per §7.

### 5. The trigger volume

**5.1** The volume is the brush geometry of the inline BSP submodel named by the `model` key (§1.1). The engine takes the submodel's axis-aligned bounding box as the entity's local bounds. No entity key can override or resize these bounds.

**5.2** The trigger is non-solid to movement — entities pass through it freely — and it is not rendered. It is not affected by physics and never moves.

**5.3** The entity's world-space box is its local bounds translated by the `origin` key. For brush entities the compiler normally leaves `origin` at (0, 0, 0), with the submodel bounds already in world coordinates; a map that uses an origin-brush construct will have a non-zero `origin` and correspondingly re-based submodel bounds.

**5.4** **Link-time bounding-box adjustment.** When any entity is linked into the world's spatial structures, the engine grows its world-space box outward by **1 world unit on each of the six faces**: each minimum coordinate is decreased by 1 and each maximum coordinate is increased by 1. This is applied to every linked entity, not only to triggers.

**5.5** The overlap test that decides whether an entity is inside a trigger is performed between two boxes that have **both** received the §5.4 growth — the moving entity's box and the trigger's box. The effective slack is therefore **2 world units on every axis** relative to a naive test between the raw player hull and the raw brush bounds. An importer that implements a strict box-vs-box test will find players failing to catch pads that work in the original engine, particularly at the edges of thin pad brushes.

**5.6** The overlap test is a pure axis-aligned box intersection against the trigger's bounding box. The brush's actual planes are **not** consulted. A non-box-shaped push brush therefore behaves as its bounding box — a wedge-shaped pad pushes throughout the full box that encloses the wedge.

**5.7** A separate, additional consequence of §5.4: because the box grew, an axis-aligned pad brush that is flush with the floor is reachable by a player standing on that floor.

### 6. Angle convention and the forward vector

**6.1** Coordinate system: right-handed, with **+X** and **+Y** horizontal and **+Z** vertically **up**. All lengths are in world units. All angles below are in **degrees** and are converted to radians before use.

**6.2** The orientation triple is ordered **(pitch, yaw, roll)**.

- **Yaw** is rotation about the vertical (+Z) axis. Yaw 0 faces along **+X**; increasing yaw rotates towards **+Y** (counter-clockwise seen from above).
- **Pitch** is elevation. Positive pitch aims **downward**; negative pitch aims upward. This sign convention is the one an importer is most likely to get backwards.
- **Roll** is rotation about the facing axis.

**6.3** The forward direction vector is

> **f** = ( cos(pitch)·cos(yaw), cos(pitch)·sin(yaw), −sin(pitch) )

**6.4** Roll does **not** appear in §6.3 and has no effect whatsoever on the push direction. A `trigger_push` authored with a non-zero roll and zero pitch and yaw is not the zero vector — it passes the §3.5 non-zero test and yields **f** = (1, 0, 0), i.e. a push along +X. The same value is produced by yaw 0 and by yaw 360.

**6.5** **f** as defined in §6.3 has unit length for all finite pitch and yaw, since cos²(pitch)·cos²(yaw) + cos²(pitch)·sin²(yaw) + sin²(pitch) = 1.

**6.6** Worked reference values for a pad using the default `speed` of 1000, so that the velocity magnitude is 10 000 units/s (§2.3):

| Authored | Direction **d** | Resulting velocity |
|---|---|---|
| `angle -1` | (0, 0, 1) | (0, 0, 10000) |
| `angle -2` | (0, 0, −1) | (0, 0, −10000) |
| `angle 360` | (1, 0, 0) | (10000, 0, 0) |
| `angle 90` | (0, 1, 0) | (0, 10000, 0) |
| `angles "-45 0 0"` | (0.7071, 0, 0.7071) | (7071, 0, 7071) |
| `angles "45 0 0"` | (0.7071, 0, −0.7071) | (7071, 0, −7071) |
| no angle key at all | (0, 0, 0) | (0, 0, 0) — see §3.6 |

### 7. Application cadence

**7.1** The push is **not** a one-shot on entry. Trigger contacts are evaluated **every server frame**, and the push is applied afresh in every frame during which the overlap of §5.5 holds. A player who remains inside the volume has their velocity re-set to the pad velocity on every one of those frames.

**7.2** Combined with §2.4, this means a player inside a push volume is *velocity-clamped* to the pad's exact velocity for as long as they remain inside — they cannot accelerate, decelerate, steer, or be knocked off course while in contact. The launch trajectory begins at the moment of the last frame of contact.

**7.3** The exception is `PUSH_ONCE` (§4.1), which removes the volume after the first contact and therefore produces a genuine single application.

**7.4** Server frame rate in this fork is configurable. The default is **100 frames per second**; the value is clamped to the range **10 to 125** frames per second inclusive, with out-of-range values snapped to the nearer bound. Frame duration is the reciprocal of that rate.

**7.5** Because the push assigns rather than integrates (§2.4), the resulting launch speed is **independent** of the frame rate. Frame rate affects only the granularity of the exit moment and hence how precisely a player can leave the volume.

**7.6** Trigger contacts are evaluated for a player after that player's movement for the frame has been resolved and their new position has been linked into the world. An importer should therefore apply push effects post-integration, not pre-integration, or the pad will lag by one frame.

**7.7** Dead players and dead monsters — that is, entities that are either a client or flagged as a monster **and** whose health is at or below zero — generate no trigger contacts at all. This exclusion sits above `trigger_push` and applies to every trigger type. Other entities with non-positive health (loose items, debris) still generate contacts; they are filtered instead by the eligibility rule in §2.6.

**7.8** Entities in a noclip-style movement mode do not generate trigger contacts.

### 8. World gravity

**8.1** The engine's default world gravity is **800 world units per second squared**, directed along −Z. Pad `speed` values are conventionally quoted and tuned relative to this figure.

**8.2** Gravity is exposed as a server variable whose default value is 800. A map may override it for the whole level via a numeric `gravity` key on the `worldspawn` entity; when `worldspawn` supplies no such key, 800 is used.

**8.3** This fork additionally provides a server-side low-gravity mode which, when enabled and when `worldspawn` does not specify gravity, substitutes **300** units per second squared. This is an Alien Arena divergence and is a gameplay option, not a map property.

**8.4** Per-entity gravity is a dimensionless multiplier applied on top of §8.1, defaulting to 1.0. The `trigger_gravity` entity sets this multiplier on touching entities (see §9.6); it does not impart velocity.

**8.5** Sanity check for an importer, using §2.3 and §8.1: a default-`speed` pad aimed straight up imparts 10 000 units/s, which under 800 units/s² gives a rise time of 12.5 s and an apex 62 500 units above the pad. This is far beyond any plausible map scale, which is why authored `trigger_push` pads in real maps use `speed` values well below the default — a jump of height *h* units requires a vertical velocity of √(2·800·*h*), so `speed` ≈ √(1600·*h*) / 10 = 4·√*h*. For example a 256-unit hop needs `speed` ≈ 64, and a 1024-unit launch needs `speed` ≈ 128.

### 9. Other mechanisms that can move a player

**9.1 Definitive answer: YES**, there are other mechanisms, but only three, and only one of them is a texture/surface-driven effect. They are listed exhaustively below.

**9.2** The complete set of **push-capable classnames** in this engine's entity spawn table is:

| Classname | Mechanism |
|---|---|
| `trigger_push` | this document, §1–§8 |
| `trigger_monsterjump` | §9.4 |
| `func_conveyor` | §9.5 |

No other classname in the spawn table imparts velocity to a player. In particular, none of the `target_*` entities, none of the `misc_*` entities, and no other `trigger_*` or `func_*` entity does so.

**9.3** **Surface flags: NO.** There is no surface flag and no texture-name convention that makes a surface push a player. The flag with bit value **0x40**, named `SURF_FLOWING` in the surface-flag vocabulary, causes the texture to scroll visually in the direction of the surface's angle and has **no** effect on movement. An importer must not couple texture scrolling to physics.

**9.4** **`trigger_monsterjump`.** A brush trigger, same volume rules as §5, direction derived by exactly the same rules as §3 including the −1/−2 special cases.
- Keys: `speed` (default **200**) is the horizontal throw speed; `height` (default **200**) is the vertical throw speed; both are read at spawn.
- If the authored yaw is exactly 0, it is replaced with 360 before the direction is derived, so this entity — unlike `trigger_push` — cannot accidentally fall into the zero-direction case of §3.5 through a plain `angle 0`.
- On contact the touched entity's X and Y velocity components are **set to** the X and Y components of the direction vector scaled by `speed`, and the Z velocity component is **set to** the `height` value directly (not scaled by the direction's Z component). The entity is detached from its ground.
- Retrigger is rate-limited to at most once every **0.1 seconds**.
- Entities that fly or swim, dead monsters, and gibs are skipped.
- **Alien Arena divergence, important for an importer:** despite the name, this entity in this fork does **not** restrict itself to monsters. Any touching entity that is not excluded by the preceding rule is thrown, **including player clients**. A map using `trigger_monsterjump` will move players.

**9.5** **`func_conveyor` and brush "current" content flags.** This is a content-flag mechanism, not a surface-flag one.
- The brush content-flag bits that mean "current", and the world direction each selects:

| Bit value | Direction contributed |
|---|---|
| 0x00040000 | +X |
| 0x00080000 | +Y |
| 0x00100000 | −X |
| 0x00200000 | −Y |
| 0x00400000 | +Z |
| 0x00800000 | −Z |

  Multiple bits on one brush contribute additively, producing a vector sum which is **not** renormalised.
- **Standing on** a brush carrying current contents adds a contribution to the player's desired-velocity of **100 units/s** along that summed vector. This magnitude is a hard-coded constant in this fork; the `func_conveyor` entity's `speed` key is **not** used to scale it, notwithstanding that the entity accepts `speed` with a default of **100**.
- **Submerged in** a volume carrying current contents adds a contribution of **400 units/s** along the summed vector, **halved to 200** when the player is only shallowly in the liquid *and* is standing on ground.
- The conveyor contributions are added to the player's *desired* velocity within the movement solver, so they are subject to the usual acceleration and friction handling and do **not** simply overwrite velocity as §2.4 does.
- `func_conveyor` spawnflag bits: **1** = start on, **2** = toggle (remain switchable after first use). The entity's `use` handler toggles the effect on and off. The brush must additionally carry the content bits above for anything to happen.

**9.6** Mechanisms that are frequently mistaken for pushes and are **not**:
- `trigger_gravity` sets the per-entity gravity multiplier (§8.4) on touching entities and imparts no velocity. It requires a non-zero `gravity` key and removes itself at load if that key is absent.
- `misc_teleporter` **zeroes** a teleported player's velocity rather than imparting any.
- Weapon and explosion knockback moves players, but it is a combat effect driven by damage events, not something a mapper places.
- Moving brush entities (`func_door`, `func_plat`, `func_train`, `func_rotating`) carry or crush players by pushing them geometrically; they impart no scripted velocity.

## 10. `func_door` — importer's summary

Included for a possible future feature; deliberately brief and limited to what an importer needs.

**10.1** Classname `func_door`. Brush entity, referenced through `model` exactly as in §1.1, solid, and moved by the engine's pusher physics.

**10.2** Keys and defaults:

| Key | Default if absent or zero | Meaning |
|---|---|---|
| `angle` / `angles` | none | opening direction; derived by exactly the rules of §3 and §6, including the −1 (up) and −2 (down) special cases |
| `speed` | **100** | movement speed in world units per second |
| `wait` | **3** | seconds to remain open before returning; a negative value means never return |
| `lip` | **8** | world units of the door left protruding at the end of the move |
| `dmg` | **2** | damage inflicted per blocking event |
| `health` | see §10.8 | if non-zero the door must be shot to open |
| `targetname` | none | if set, the door is opened only by a targeting entity |
| `target` | none | fired when the door opens; also used to pair the door with area portals |
| `message` | none | text shown on touch, for targeted doors |
| `sounds` | none | selects the door sound set; value 1 means silent |
| `team` | none | groups doors that must move together |

**10.3** **Travel distance.** With **d** the unit opening direction from §10.2 and (*sx*, *sy*, *sz*) the extents of the door's brush bounding box along each axis, the distance travelled is

> *distance* = |*d<sub>x</sub>*|·*sx* + |*d<sub>y</sub>*|·*sy* + |*d<sub>z</sub>*|·*sz* − *lip*

i.e. the door slides its own size along the chosen axis, less the `lip`. For an axis-aligned direction this reduces to "the door's own thickness along that axis, minus `lip`". Note the formula uses absolute values, so a door opening along −X travels the same distance as one opening along +X.

**10.4** **Positions.** The closed position is the door's spawn origin. The open position is the closed position displaced by **d** × *distance*.

**10.5** **Movement profile.** The door moves in a straight line between the two positions at a constant **`speed`** units per second. The entity also carries independent acceleration and deceleration rates which each default to the value of `speed`; while all three are equal the motion is unaccelerated. Only when a map explicitly sets a differing acceleration or deceleration does the door ramp its speed, and in that case the total travel distance and the two endpoints are unchanged.

**10.6** **Alien Arena divergence:** in deathmatch mode — which is this fork's normal mode — the effective `speed` is **doubled** at spawn, after the default of 100 has been substituted. An importer reproducing this fork's feel should double; one reproducing stock Quake 2 should not.

**10.7** **Return behaviour.** On reaching the open position, a door with the TOGGLE flag set stays open and waits for another activation. Otherwise, if `wait` is zero or positive, the door begins closing `wait` seconds later; if `wait` is negative it stays open permanently.

**10.8** **Activation.**
- If `targetname` is set, the door is opened only by another entity firing it (a button, a trigger, etc.), and no automatic touch volume is created. If such a door also has a `message`, it additionally responds to being touched by showing that message.
- If `targetname` is **not** set, the engine automatically creates an invisible touch volume at load. Its box is the union of the bounding boxes of every door in the door's `team`, grown by **60 world units** in **±X and ±Y only** — not in Z. Touching that volume opens the door. (The §5.4 one-unit link growth applies to this volume as well.)
- **Alien Arena divergence:** an untargeted door is additionally given `health` = 1 unless the map authored a `health` value in the range 1 to 8 inclusive, which makes untargeted doors shootable as well as touchable. Once shot open, the door's damageability is cleared and its health restored.

**10.9** **Blocking.** An entity caught by a closing or opening door takes `dmg` damage per blocking event if it is a player or a monster, and is destroyed outright otherwise. With the CRUSHER flag set the door continues through the obstruction; without it, and provided `wait` is non-negative, the door reverses direction.

**10.10** **Spawnflag bits for `func_door`:**

| Bit value | Name | Effect |
|---|---|---|
| 1 | START_OPEN | the two positions are exchanged at spawn, so the door begins open and its sense of operation is inverted |
| 2 | — | unused by `func_door` (this bit is REVERSE on `func_door_rotating`) |
| 4 | CRUSHER | do not reverse when blocked |
| 8 | NOMONSTER | monsters do not activate it |
| 16 | ANIMATED | brush texture animates |
| 32 | TOGGLE | wait for a further activation in both the open and closed states |
| 64 | ANIMATED_FAST | brush texture animates at the faster rate |

**10.11** As with §3.8, the door's authored orientation is consumed by the direction derivation and reset to zero, so a `func_door` is not rendered rotated by its `angle` key.

## Excluded

The following were deliberately **not** stated, and why.

1. **The dispatch and sequencing logic of trigger contact evaluation.** The order in which candidate entities are gathered, the guards against entities being destroyed mid-iteration, and the shape of the per-frame loop are implementation structure under the guardrails. §7 states the externally observable cadence and the post-integration ordering, which is what an importer needs; the mechanism producing it is the implementer's own choice.

2. **The spatial partitioning structure used to find candidate trigger overlaps.** This is a performance structure with many valid alternatives and is not part of the observable contract. §5.5 states the test that must hold; how candidates are narrowed is unconstrained.

3. **The engine's per-entity numeric field layout and save/restore field table.** These are internal names and offsets, not interface vocabulary. The externally meaningful part — which *map keys* exist and what they mean — is in §1.2 and §10.2.

4. **The complete entity spawn table.** Reproducing the full classname-to-handler table would be reproducing the source's data organisation. §9.2 gives the answer actually requested — the exhaustive list of *push-capable* classnames — and §9.6 the near-misses.

5. **The accelerated-movement profile used when a `func_door`'s acceleration differs from its speed.** The endpoint positions and total distance are stated (§10.3–§10.5), but the specific speed-ramping curve is a tuned behaviour whose statement could not be separated from its expression. It affects only doors whose maps explicitly set differing acceleration values, and any monotonic ramp between the same endpoints at the same nominal speed is a faithful import. **Flagged for a human** if a future door feature needs frame-exact door positions.

6. **Sound asset paths and the sound-set selection table** for doors and for the push wind effect. These are content references, not behaviour. §2.7 and §10.2 state that a sound exists and its rate limit, which is the behavioural part.

7. **Any statement about the contents of an implementation.** This Reader read no project code; nothing here is derived from or checked against any, so the facts stand on the source and the public references alone.

### Escalations

**E1 — no observed-behaviour cross-check was possible.** Rule 0 preference 3 (run it and measure) could not be exercised: no engine build and no sample map were available. Every numeric fact below the level covered by the public mapping references rests on a single reading of the copyleft source. The values most worth confirming against a running build or against a licence-clean reimplementation, before code depends on them, are: the ×10 factor (§2.1), the 1-unit link-time box growth and hence the 2-unit effective slack (§5.4–§5.5), and the per-frame reapplication (§7.1).

**E2 — `trigger_monsterjump` affects players in this fork (§9.4).** This is a divergence from the behaviour its name and the public Quake 2 documentation imply. A human should confirm the intent before an importer relies on it, since it changes how existing maps play.

**E3 — the deathmatch door-speed doubling (§10.6) and the automatic health on untargeted doors (§10.8)** are Alien-Arena-specific gameplay decisions rather than map-format facts. If the downstream goal is a general Quake 2 map importer rather than an Alien Arena one, a human should decide which of the two behaviours to target; the spec records both.
