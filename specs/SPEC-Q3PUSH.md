# SPEC-Q3PUSH — aimed jump pads in the version 46 family

**Status:** current.
**Provenance:** no copyleft source was read. Every fact below is either
observed in shipped, freely-licensed map content (OpenArena 0.8.5, 50 maps —
`openarena-maps_0.8.5split`, CC BY-SA / GPL, Debian main), or is ordinary
projectile physics stated here so an implementation has something to cite.
See [CLEAN-ROOM.md](CLEAN-ROOM.md).

**Scope.** `trigger_push` in an `IBSP` version 46 map. The version 38 entity of
the same name is a *different* entity and is specified by
[SPEC-TRIGGER-PUSH](SPEC-TRIGGER-PUSH.md), whose §1.3 states explicitly that
the version 38 entity has no `target` and cannot be aimed. The two share a
classname and nothing else.

## 1. The entity

**1.1** [OBSERVED] A version 46 `trigger_push` is a brush entity: it carries a
`model` key of the form `"*N"` naming a brush model, and its volume is that
model's bounding box. All 236 push entities across the 50 maps carry one.

**1.2** [OBSERVED] It carries a `target` key. All 236 do. There is no observed
version 46 `trigger_push` that is aimed by an `angle`/`speed` pair the way the
version 38 entity is: `angle` appears on 3 of 236 and `speed` on 3 of 236,
always alongside `target`.

**1.3** [OBSERVED] The value of `target` matches the `targetname` of another
entity in the same map. The classnames observed carrying a matching
`targetname` are `target_position` (191 of 236), `target_push` (45) and
`target_location` (1).

**1.4** [OBSERVED] The destination entity carries an `origin` key: a point in
map coordinates. 288 of 288 observed destination entities have one.

**1.5** [OBSERVED] `height` appears on 4 of 236 push entities. Its meaning is
not established by observation and this specification does not assign one; a
reader should ignore it.

## 2. What the pad does

**2.1** [DERIVED] The pad launches whoever is inside it towards the
destination point of §1.4 — the entity is aimed at a place, not pointed in a
direction. This is what distinguishes it from the version 38 entity, and it is
what the map geometry demands: destination entities sit on ledges and platforms
that are unreachable by walking.

**2.2** [PHYSICS] The velocity is that of a projectile under the map's gravity
(`SPEC-TRIGGER-PUSH §8` gives the gravity key and its default of 800 units per
second squared) which passes through the destination point. That is a
one-parameter family of trajectories, not a single one: fixing any one of the
flight time, the launch speed, or the apex height selects a member.

**2.3** [CHOICE] The exact member the original engine selects is **not
established here** — it is not observable from map data. An implementation must
therefore choose, and must say that it has chosen. This specification's choice,
for reproducibility rather than fidelity:

- the apex of the arc is `ARC_CLEARANCE` units above the higher of the launch
  point and the destination;
- the flight time is that of a projectile rising to that apex and falling to
  the destination height;
- the horizontal velocity is the horizontal separation divided by the flight
  time.

with `ARC_CLEARANCE` = 128 units, which is roughly two player heights
(`SPEC-BSP38 §3.2` gives 56 units standing) and clears the lip of a platform
the pad is aimed at.

**2.4** [DERIVED] Where the destination cannot be resolved — no entity carries
the named `targetname`, or it has no `origin` — the pad has no aim. A reader
should fall back to the version 38 reading of `angle` and `speed`
(`SPEC-TRIGGER-PUSH §2`, `§3`), which is the only other information present,
and which §1.2 shows a handful of maps do author.

**2.5** [DERIVED] Everything else about the volume — that it replaces velocity
rather than adding to it, the two units of link slack on the box, that contacts
are evaluated after the frame's movement, that a noclip player generates none —
is behaviour of a push volume in general and is unchanged from
`SPEC-TRIGGER-PUSH §2.1`, `§5.4`–`§5.6`, `§7.6` and `§7.8`.

## 3. Open questions

**3.1** The engine's own choice of trajectory (§2.3). Establishing it needs a
source that is not the engine: a published description, or measurement of a
running engine, neither of which was available when this was written.

**3.2** The meaning of `height` (§1.5), for the four maps that author it.
