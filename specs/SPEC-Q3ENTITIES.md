# SPEC-Q3ENTITIES — game entities in the version 46 family

**Status:** current. Grows a section at a time, as an entity is implemented.
**Provenance:** no copyleft source was read. Every fact below is observed in
shipped, freely-licensed map content — OpenArena 0.8.5, 50 maps
(`openarena-maps_0.8.5split` and `openarena-data_0.8.5split`, CC BY-SA / GPL,
Debian main) — measured on 2026-07-28, or is marked `[CHOICE]` where this
project decided something the content cannot establish. See
[CLEAN-ROOM.md](CLEAN-ROOM.md).

**Scope.** Entities of an `IBSP` version 46 map that *play* rather than
*describe geometry*. The container itself is [SPEC-BSP46](SPEC-BSP46.md), the
entity-lump syntax is [SPEC-BSP38 §10](SPEC-BSP38.md) (adopted unchanged by
`SPEC-BSP46 §5.1`), push volumes are [SPEC-Q3PUSH](SPEC-Q3PUSH.md), and
material scripts are [SPEC-Q3SHADER](SPEC-Q3SHADER.md).

**How to read the markers.** `[OBSERVED]` — counted in the content named above.
`[DERIVED]` — follows from an observed fact plus ordinary reasoning stated in
place. `[CHOICE]` — the content does not establish it, an implementation must
decide, and this document records *our* decision as a decision. `[UNKNOWN]` —
observed to exist, meaning not established; an implementation must not invent
one.

---

## 1. `target_speaker` — a sound placed in the map

### 1.1 How common it is

**1.1.1** [OBSERVED] **29 of the 50 maps place at least one, 381 in all.** The
densest is `ctf_inyard` with 60; `oasago2` has 52 and `oa_dm3` 41. Twenty-one
maps place none.

**1.1.2** [OBSERVED] The keys carried, with the number of the 381 entities
carrying each:

| Key | Count | Section |
|---|---|---|
| `classname` | 381 | — |
| `noise` | 381 | §1.2 |
| `origin` | 381 | §1.3 |
| `spawnflags` | 360 | §1.4 |
| `targetname` | 28 | §1.6 |
| `wait` | 24 | §1.5 |
| `random` | 19 | §1.5 |
| `angle` | 7 | §1.7 |
| `light` | 3 | §1.7 |

Every one of the 381 carries `noise` and `origin`; nothing else is universal.

### 1.2 `noise` — which sound

**1.2.1** [OBSERVED] `noise` is a path. Across the 381 entities there are **46
distinct values**, and all 46 are lower-case.

**1.2.2** [OBSERVED] Three spellings occur, and they are spellings of the same
thing rather than three kinds of value:

| Spelling | Entities | Example |
|---|---|---|
| bare relative path | 344 | `sound/world/wind1.wav` |
| leading `/` | 21 | `/sound/world/wind1.wav` |
| leading `*` | 16 | `*falling1.wav` |

Six of the 46 distinct values carry a leading `/`, and the *same* path occurs
elsewhere in the content without one — `sound/world/demonwind01.wav`,
`drone6.wav`, `lava1.wav`(§1.2.5), `lava_amb_01_quiet.wav`, `suck1.wav`,
`wind1.wav` and `wind2.wav` each appear both ways. That is what establishes the
leading slash as an alternate spelling of a path rooted at the content tree and
not a distinct namespace.

**1.2.3** [OBSERVED] **The extension is advisory.** 43 of the 46 distinct values
end in `.wav`; **three carry no extension at all** — `sound/world/drops`,
`sound/world/suck1` and `sound/world/wind1` — and each of those three names a
file that exists in the content as `.wav`. This is the same rule
`SPEC-Q3SHADER §1.6` states for texture names, arrived at independently from
sound data.

**1.2.4** [DERIVED] A reader must therefore strip whatever extension a `noise`
carries and search the supported audio extensions in turn, against each content
root in precedence order — the identical procedure `SPEC-BSP46 §7.3` describes
for textures. `.wav` and `.ogg` are the extensions this content uses (§1.2.6).

**1.2.5** [UNKNOWN] **The leading `*` is not a path.** All 16 occurrences are
`*falling1.wav`, spread across eleven maps (`oa_koth1` ×4, `delta` ×3, and one
each in `am_galmevish`, `ctf_inyard`, `czest1dm`, `czest2ctf`, `oa_ctf4ish`,
`oa_pvomit`, `oa_shine`, `suspended` and `wrackdm17`), and no file of that name
exists anywhere in the content. In this engine family the `*` prefix marks a
sound belonging to an entity's own model rather than to the content tree; what
model, and how the name is resolved against it, is **not established here**. An
implementation with no such models to consult must skip the value rather than
guess at a path.

**1.2.5.1** [OBSERVED] **All sixteen also carry a `targetname`** (§1.6) — they
are the only `noise` value for which that is true of every occurrence, against
28 triggered speakers in total. So an entity-model sound is, in this content,
without exception a sound something *fires* rather than one a map leaves
running. That is consistent with the reading above and with the name: a falling
sound belongs to a moment. It does not establish what the `*` resolves against,
and this document still does not say.

**1.2.6** [OBSERVED] The content ships **255 `.wav` and 98 `.ogg`** sound files
and no other audio format (no `.mp3`, `.opus` or `.flac`). **44 of the 46
distinct `noise` values resolve** against it. The two that do not are
`*falling1.wav` (§1.2.5) and `/sound/world/lava1.wav`, which is simply absent —
maps routinely name sounds from a base game a given install did not fetch.

**1.2.7** [DERIVED] A `noise` that resolves to nothing is therefore a normal
condition of loading real content, not an error. It must produce a silence and
at most a warning, never a failed load.

### 1.3 `origin` — where the sound is

**1.3.1** [OBSERVED] All 381 carry an `origin`: a point in map coordinates, in
the form three whitespace-separated numbers take everywhere else in the lump
(`SPEC-BSP38 §10.4`). Example, from `oa_dm3`: `1368 -512 232`.

**1.3.2** [DERIVED] It converts to scene space by the map→scene transform of
`SPEC-BSP38 §3.2`, exactly as a spawn point or a push destination does. Nothing
about sound needs a new conversion.

### 1.4 `spawnflags` — how it repeats

**1.4.1** [OBSERVED] The values seen across the 381, and their counts:

| Value | Count | Bits set |
|---|---|---|
| `1` | 326 | 1 |
| *absent* | 21 | — |
| `8` | 13 | 8 |
| `5` | 10 | 1, 4 |
| `4` | 9 | 4 |
| `0` | 2 | — |

**1.4.2** [DERIVED] **Bit 1 means the sound loops.** It is set on 336 of the 381
and its bearers are unambiguously ambience: `sound/world/wind1.wav`,
`firesoft.wav`, `neonhum.wav`, `machinerydrone01.wav`. It is also the one bit
that appears alone on the overwhelming majority of speakers, in maps where the
sound is plainly continuous.

**1.4.3** [UNKNOWN] **Bits 4 and 8 occur in real content and their meanings are
not established.** Bit 4 appears 19 times (as `4` and as `5`), bit 8 thirteen
times. Nothing observable in the map data distinguishes their bearers from
their neighbours. An implementation must ignore them rather than assign a
meaning, and must not treat an unrecognised bit as a reason to reject the
entity.

**1.4.4** [DERIVED] An absent `spawnflags` is zero, as an absent numeric key is
everywhere else in the lump. It is therefore a non-looping speaker, which is
consistent with §1.5: of the 21 entities with no `spawnflags`, all but one also
carry a `wait`.

### 1.5 `wait` and `random` — repeating without looping

**1.5.1** [OBSERVED] `wait` appears on 24 entities and takes the values `10`
(×6), `15`, `30` (×6), `34` (×2), `35` (×5), `47` (×2) and `347` (×2). `random`
appears on 19, always alongside a `wait`.

**1.5.2** [DERIVED] `wait` is a period in **seconds** between repeats of a
speaker that does not loop, and `random` is a spread applied to it so a repeated
one-shot does not become metronomic. The units follow from the values: 10 to 47
seconds is the cadence of a distant, occasional noise, which is what the sounds
carrying them are (`1shot_greg_03.wav`, `growl1.wav`, `x_ominous.wav`) — and the
name `1shot_` is the map author's own statement that these are one-shots.

**1.5.3** [UNKNOWN] Whether `random` is a symmetric spread (±*n* seconds) or an
addition (0 to *n*) is not established by the data. An implementation must
state which it chose.

### 1.6 `targetname` — triggered rather than ambient

**1.6.1** [OBSERVED] 28 of the 381 carry a `targetname`, for example
`target_speaker2`. Their `noise` values are `*falling1.wav` (×16, and see
§1.2.5.1), `sound/world/portal02.wav` (×6), `growl3.wav` (×4), `growl2.wav` and
`sound/items/n_health.wav` — a portal, a monster and a health pickup, all of
them sounds that answer something happening rather than sounds a room makes.

**1.6.2** [DERIVED] A `targetname` is what another entity's `target` names
(`SPEC-Q3PUSH §1.3`), so these speakers are fired by something else rather than
being ambient. What fires them, and when, is a trigger system this project does
not have; such a speaker is **out of scope** until one exists, and until then it
should be treated as any other speaker or skipped, but not silently mis-timed.

### 1.7 The rest

**1.7.1** [UNKNOWN] `angle` (7 entities) and `light` (3) are keys the level
editor writes on every entity type it offers. Neither has an established meaning
for a speaker: a directional cone would be plausible for `angle`, and this
document does not assert it. Ignore both.

---

## 2. Sound files in the content

**2.1** [OBSERVED] 353 sound files across the fetched packs: 255 `.wav` and 98
`.ogg`. They live under a `sound/` directory at the root of a content tree, at
the same level as the `textures/` root of `SPEC-BSP38 §6.4`, and are found by
the same search over the same roots.

**2.2** [OBSERVED] All 255 `.wav` files are uncompressed PCM and every `.ogg`
is Vorbis. **Neither the sample rate nor the channel count is uniform**: the
`.wav` files carry six distinct rates — 44 100 Hz (×167), 22 050 (×68), 11 025
(×17), and one each at 32 075, 32 000 and 16 000 — and 41 of the 255 are stereo.
A reader that assumes one rate, or mono, is wrong about this content.

**2.3** [CHOICE] Rate and channel differences are normalised at decode rather
than carried into the mixer, and every clip is mixed to mono, because a stereo
source has already decided where it sits in the stereo field and cannot then be
panned to where it actually is in the world. This is our decision, not an
observation about the content.

---

## 3. Pickups — the items a map places for players to collect

**Provenance note.** The counts in this section are over **67 version 46 maps**
in this workspace's sample content — the 50 OpenArena 0.8.5 maps of the header
plus 17 further freely-licensed maps — read on 2026-07-29 by enumerating the
entity lump of each file. No copyleft source was consulted; every classname and
key below was *seen in a map file*. Where a meaning could not be established
from the content it is marked `[UNKNOWN]` and this project does not invent one.

### 3.1 How common they are

**3.1.1** [OBSERVED] **Every one of the 67 maps places at least one**, 3561 in
all — an average of 53 a map. The densest is `czest3ctf` with 174, then
`czest1dm` with 127 and `oa_bases7` with 116. Pickups are not an optional
decoration of this content: they are the most numerous playable entity in it by
an order of magnitude, and a viewer that ignores them is ignoring most of what
the level author placed.

**3.1.2** [OBSERVED] The keys carried, with the number of the 3561 entities
carrying each:

| Key | Count | Section |
|---|---|---|
| `classname` | 3561 | §3.2 |
| `origin` | 3561 | §3.3 |
| `angle` | 528 | §3.7 |
| `spawnflags` | 190 | §3.6 |
| `wait` | 133 | §3.5 |
| `weight` | 93 | §3.7 |
| `count` | 50 | §3.4 |
| `random` | 44 | §3.5 |
| `gametype` | 23 | §3.7 |
| `rotation` | 22 | §3.7 |
| `notfree` | 8 | §3.7 |
| `targetname` | 7 | §3.7 |
| `notta` | 3 | §3.7 |
| `notq3a` | 2 | §3.7 |
| `notbot` | 2 | §3.7 |
| `notsingle` | 2 | §3.7 |
| `target` | 1 | §3.7 |

Only `classname` and `origin` are universal. **Everything else is optional and
most of it is rare**, so a reader that requires any other key will refuse most
of this content.

### 3.2 `classname` — what it is

**3.2.1** [OBSERVED] Four prefixes account for all 3561: `item_` (1876),
`ammo_` (1079), `weapon_` (591) and `holdable_` (15).

**3.2.2** [DERIVED] The prefix is not sufficient on its own — `item_` covers
health, armour and timed powerups alike — so the **whole classname** is what
identifies a pickup, and the prefix is only a way to recognise that an unknown
name is *probably* a pickup.

**3.2.3** [OBSERVED] The distinct classnames, with how many entities carry each
and how many of the 67 maps place at least one:

| Classname | Entities | Maps |
|---|---|---|
| `ammo_belt` | 6 | 3 |
| `ammo_bfg` | 2 | 1 |
| `ammo_bullets` | 133 | 41 |
| `ammo_cells` | 184 | 46 |
| `ammo_chaingun` | 2 | 1 |
| `ammo_grenades` | 92 | 39 |
| `ammo_lightning` | 109 | 45 |
| `ammo_mines` | 2 | 1 |
| `ammo_nailgun` | 4 | 1 |
| `ammo_nails` | 8 | 4 |
| `ammo_proxmine` | 2 | 1 |
| `ammo_rockets` | 238 | 62 |
| `ammo_shells` | 201 | 58 |
| `ammo_slugs` | 96 | 40 |
| `holdable_invulnerability` | 1 | 1 |
| `holdable_kamikaze` | 2 | 2 |
| `holdable_medkit` | 4 | 3 |
| `holdable_teleporter` | 8 | 6 |
| `item_ammoregen` | 14 | 7 |
| `item_armor_body` | 50 | 39 |
| `item_armor_combat` | 94 | 50 |
| `item_armor_shard` | 567 | 42 |
| `item_botroam` | 129 | 16 |
| `item_doubler` | 15 | 8 |
| `item_enviro` | 6 | 5 |
| `item_guard` | 17 | 9 |
| `item_haste` | 9 | 8 |
| `item_health` | 430 | 59 |
| `item_health_large` | 80 | 34 |
| `item_health_mega` | 55 | 43 |
| `item_health_small` | 334 | 40 |
| `item_invis` | 9 | 8 |
| `item_kamikaze` | 2 | 1 |
| `item_quad` | 32 | 32 |
| `item_regen` | 5 | 5 |
| `item_scout` | 14 | 7 |
| `weapon_bfg` | 3 | 2 |
| `weapon_chaingun` | 7 | 4 |
| `weapon_grenadelauncher` | 73 | 47 |
| `weapon_lightning` | 65 | 49 |
| `weapon_nailgun` | 9 | 6 |
| `weapon_plasmagun` | 92 | 47 |
| `weapon_railgun` | 77 | 52 |
| `weapon_rocketlauncher` | 131 | 64 |
| `weapon_shotgun` | 130 | 63 |

**3.2.4** [OBSERVED] The names are **not a closed set**. Eleven of the 46 appear
in a single map each, and several are plainly a mod's own (`ammo_proxmine`,
`weapon_prox_launcher`, `weapon_smartgun`, `weapon_disruptor`,
`weapon_flamethrower`, `item_adrenaline`). A reader must treat an unrecognised
pickup classname as content it does not have, not as a malformed map.

**3.2.5** [OBSERVED] One map writes the classname
`item_health_small (0 1 0` — 14 entities of it. The entity-lump grammar of
`SPEC-BSP38 §10` permits any string inside the quotes, so this is a
well-formed entity with a classname nothing recognises, and it is covered by
§3.2.4 rather than being an error.

**3.2.6** [OBSERVED] `item_botroam` (129 entities across 16 maps) carries
`weight` and never appears with anything a player could collect. It is a
navigation hint placed for opponents rather than a pickup, and is named here so
that a reader recognising `item_` by prefix does not put an invisible,
uncollectable object in the level.

### 3.3 `origin` — where it is

**3.3.1** [OBSERVED] Present on all 3561, three numbers, in map units, in the
map's own axes — `SPEC-BSP38 §3.2` — exactly as a spawn point or a speaker is.

**3.3.2** [UNKNOWN] What the origin marks *relative to the item* — its middle,
its base, or the point a player's body must reach — is not established by the
content. A reader must decide, and record the decision as one.

### 3.4 `count` — how much it gives

**3.4.1** [OBSERVED] 50 entities carry `count`, always a positive integer. The
values, with how many carry each: 5 (×19), 8 (×16), 10 (×8), 75 (×4), 20 (×1),
100 (×1), 150 (×1).

**3.4.2** [DERIVED] The two clusters follow the classname rather than being two
meanings: the small values sit on `ammo_*` entities and the large ones on
`item_health*`, which is the same quantity — *how much this one gives* —
measured in each family's own units.

**3.4.3** [DERIVED] It is an override and not a requirement: 3511 of the 3561
carry no `count` at all, so every classname must have an amount of its own that
`count` replaces when it is present.

### 3.5 `wait` and `random` — coming back

**3.5.1** [OBSERVED] 133 entities carry `wait`, always a positive number of
seconds: 10 (×89), 20 (×10), 7 (×8), 15 (×7), 5 (×6), 40 (×3), 90 (×3), 45
(×2), 75 (×2), and one each of 30, 60 and 80.

**3.5.2** [OBSERVED] 44 carry `random`: 5 (×21), 7 (×9), 3 (×5), 15 (×3), 10
(×3), 25 (×2), 6 (×1).

**3.5.3** [DERIVED] These are the same two keys, spelled the same way and
carrying the same kinds of value, that `§1.5` establishes for a repeating
speaker: a period and a jitter either side of it. A pickup is a thing that
comes back after being taken, which is the same shape of fact, and the
clustering of `wait` at 10 seconds is consistent with a respawn interval.

**3.5.4** [DERIVED] As with `count`, absence is the common case — 3428 carry no
`wait` — so each classname must have a respawn interval of its own that `wait`
overrides.

### 3.6 `spawnflags`

**3.6.1** [OBSERVED] 190 entities carry `spawnflags`: 1 (×122), 2 (×29), 4
(×25), 0 (×14). Every value is a power of two or zero, so it is a bit field, as
`§1.4` establishes for a speaker.

**3.6.2** [UNKNOWN] What each bit means for a *pickup* is not established by the
content. A pickup floating where it was placed rather than dropping to the floor
is a plausible reading of bit 1 and this document does not assert it.

### 3.7 The rest

**3.7.1** [UNKNOWN] `angle` (528) and `rotation` (22) place the item's
orientation, which matters only to something drawing the author's own model for
it. Neither affects what a pickup gives or when it returns.

**3.7.2** [OBSERVED] `gametype` (23), `notfree` (8), `notta` (3), `notq3a` (2),
`notbot` (2) and `notsingle` (2) are filters naming the modes an entity does or
does not appear in — `gametype` holds a comma-separated list such as
`ffa, ctf, ctfelim, dd`. They are rare enough to matter to no map's playability
and their vocabularies are not established here.

**3.7.3** [UNKNOWN] `weight` (93) appears on `item_botroam` (§3.2.6) and nothing
else. It is a hint to opponent navigation, and what the numbers mean is not
established.

**3.7.4** [OBSERVED] `targetname` (7) and `target` (1) are the same triggering
keys `§1.6` covers, and place a pickup in the same target/targetname graph a
speaker can be in.
