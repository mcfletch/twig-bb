# SPEC-UNVASSETS: Unvanquished asset packages, as a delta from Quake 3

| | |
|---|---|
| Source consulted | the bytes of 15 released `.dpk` asset packages (1481 files), listed in §0.2 |
| Licence of source | the *files* are content, published under CC BY-SA; the facts below are format facts read out of them |
| Version / commit | packages as published on `dl.unvanquished.net/pkg/`, fetched 2026-08-30 |
| Files consulted | the byte content of the package entries themselves, and nothing else |
| Non-copyleft sources checked first | not applicable — **no copyleft source was consulted at any point**, not the engine, not the game logic, not the build tooling, not the wiki. Every fact below was derived from file bytes per [CLEAN-ROOM.md](CLEAN-ROOM.md) Rule 0 item 2, from this project's own BSD specs, or from a published format specification cited by URL. |
| Reader | derived directly; no wall was required, because no copyleft source was read |
| Date | 2026-08-30 |

## Scope

What changes for a reader that already implements Quake 3 — [SPEC-BSP46](SPEC-BSP46.md)
for the map container, [SPEC-Q3SHADER](SPEC-Q3SHADER.md) for material scripts,
[SPEC-Q3ENTITIES](SPEC-Q3ENTITIES.md) for the entity vocabulary — and now wants to
walk around an Unvanquished level. Everything a Quake 3 reader already does is
assumed and not restated; this document records only the delta.

Two of that delta's parts are already written down and are cited rather than
repeated: [SPEC-CRN](SPEC-CRN.md) for the Crunch texture container and
[SPEC-EXTLM](SPEC-EXTLM.md) for lightmap pages stored beside the `.bsp`.

Marker legend, as used by this project's other specs: `[OBSERVED]` read out of
bytes, with the sample size stated; `[DERIVED]` reasoned from observations, with
the reasoning stated; `[DOCUMENTED]` from a published specification, cited by
URL; `[UNKNOWN]` observed to exist, meaning not established — an implementation
must not invent one.

## Facts

### 0. The corpus

**0.1** `[OBSERVED]` Everything below rests on 15 packages holding **1481 files**
in total. Three of those files are `.bsp` maps, 28 are `.shader` material
scripts, and 1076 are images.

**0.2** `[OBSERVED]` The packages, by kind:

| Kind | Packages | Files |
|---|---|---|
| Maps | `map-plat23_1.14`, `map-usstremor_1.1`, `map-yocto_1.1` | 365 |
| Textures | `tex-all_2.3`, `tex-common_2.5`, `tex-pk02_1.3.2`, `tex-space_1.3` | 546 |
| Resources | `res-ambient_0.55`, `res-buildables_0.54.1`, `res-leveleditor_0.54`, `res-players_0.56.2`, `res-voices_0.55.3` | 62 |
| Base game | `unvanquished_0.56.1`, `unvanquished_0.56.2`, `bugfix_0.52.1-…` | 508 |

**0.3** `[OBSERVED]` The three maps are the only maps in the corpus, so every
per-map count below has a sample size of three. Counts over materials, entity
keys and file formats have the larger sample sizes stated in place.

---

### 1. Packaging

**1.1** `[OBSERVED]` A `.dpk` is an ordinary ZIP archive. All 15 begin with
`PK\x03\x04`, carry no archive comment, and use only the two universally
supported compression methods — deflate (1387 entries) and store (109). A
reader that already opens `.pk3` files (`SPEC-BSP46 §7.1`) opens these with no
change beyond the extension.

**1.2** `[OBSERVED]` Paths inside are the same forward-slash paths a texture name
resolves against (`SPEC-BSP46 §6.1`), and the same top-level directories occur:
`maps/`, `scripts/`, `textures/`, `models/`, `env/`, `sound/`, `gfx/`. Two
further top-level directories carry content a viewer may want: `sounds/` (a
second spelling, used by one map's own audio) and `minimaps/`.

**1.3** `[OBSERVED]` The file name is `<name>_<version>.dpk`. All 15 follow it;
the version part is a dotted numeric string, optionally with a suffix
(`0.52.1-20210624-032404-b3fe650-slipher`).

**1.4** `[OBSERVED]` **11 of the 15 packages carry a root entry named `DEPS`** —
a plain-text file, one dependency per line, each line either a package name
alone or a package name and a minimum version separated by a space. Observed
examples: `tex-common`; `res-players 0.56`.

**1.5** `[DERIVED]` `DEPS` is what tells a reader which other packages must be
mounted for a map's texture names to resolve. `map-usstremor` names four texture
packages and `map-yocto` names one (`tex-all`, itself a package holding nothing
but a `DEPS` listing ten more). Without following it, a map's materials are
simply absent: of the corpus's three maps, 60 of 189 texture names have no
material definition in the packages present here. Three of the 60 are the
reserved name `noshader` (§2.3.4); the other 57 name texture packages the
corpus does not include (`textures/shared_pk01/…`, `textures/shared_ex/…`).

**1.6** `[OBSERVED]` 7 packages carry `scripts/shaderlist.txt`: a plain-text list
of `.shader` basenames without the extension, one per line, naming the scripts
that package contributes. This is the same file Quake 3 content carries.

**1.7** `[OBSERVED]` Three further root entries occur, each in a single package:
`VERSION` (a version string), `LICENSE`, and `DELETED` (a list of paths). A
viewer needs none of them.

---

### 2. Maps

The finding of this section, stated first because it is the most useful fact in
the document: **the three maps are byte-compatible with Quake 3 `IBSP` version
46.** Every check in §2.2 and §2.3 passes on all three. A reader built to
`SPEC-BSP46` parses them without a single change to its binary layer.

#### 2.1 Container

**2.1.1** `[OBSERVED]` All three files begin with the ASCII bytes `IBSP` and a
version field of **46**, exactly `SPEC-BSP46 §1.1` and `§1.2`.

**2.1.2** `[OBSERVED]` All three carry a **17-entry** lump directory in the
`SPEC-BSP46 §2.1` order, and in all three the highest lump end equals the file
size exactly, with no trailing bytes.

**2.1.3** `[OBSERVED]` The first lump's data begins at byte **172**, not at 144
where `SPEC-BSP46 §1.5` puts the end of the header. The 28 bytes between hold
eight bytes of numeric data followed by the NUL-padded ASCII text
`I LOVE MY Q3MAP2`. No directory entry references this region.

**2.1.4** `[DERIVED]` It is a watermark written by the map compiler, and it is
inert: a reader that addresses lumps through the directory, as `SPEC-BSP46 §1.4`
requires, never sees it. It is recorded only so that a reader validating "the
first lump starts right after the header" does not reject the file. `[UNKNOWN]`
The meaning of the eight numeric bytes; they differ per map and equal no length
or offset in the file.

#### 2.2 Lump sizes

**2.2.1** `[OBSERVED]` Every fixed-record lump's length is an exact multiple of
the `SPEC-BSP46 §2.1` record size, in all three maps, with **zero remainder in
all 42 cases** (14 fixed-record lumps × 3 maps). The resulting record counts:

| Lump | Record | plat23 | usstremor | yocto |
|---|---|---|---|---|
| 1 textures | 72 | 54 | 69 | 66 |
| 2 planes | 16 | 10496 | 29860 | 20576 |
| 3 nodes | 36 | 1730 | 4279 | 253 |
| 4 leafs | 48 | 1735 | 4314 | 280 |
| 5 leaffaces | 4 | 6598 | 34823 | 30387 |
| 6 leafbrushes | 4 | 6115 | 14895 | 12123 |
| 7 models | 40 | 4 | 34 | 26 |
| 8 brushes | 12 | 3546 | 6621 | 10852 |
| 9 brushsides | 8 | 28361 | 57553 | 81213 |
| 10 vertexes | 44 | 25504 | 121269 | 202385 |
| 11 meshverts | 4 | 15372 | 67863 | 72927 |
| 12 effects | 72 | 0 | 1 | 3 |
| 13 faces | 104 | 4309 | 14391 | 29071 |
| 14 lightmaps | 49152 | **0** | **0** | **0** |
| 15 lightvols | 8 | 95285 | 134758 | 24288 |

**2.2.2** `[OBSERVED]` The **lightmaps lump is empty in all three maps**. This is
the external-lightmap case, and [SPEC-EXTLM](SPEC-EXTLM.md) describes it in
full: pages live at `maps/<name>/lm_NNNN.webp`, a face's `lm_index` is the file
index directly, and every referenced index is even because the odd pages are
direction maps.

**2.2.3** `[OBSERVED]` `usstremor` is a third map confirming
`SPEC-EXTLM §4.2` — it references only the even `lm_index` values 0, 2, 4, 6, 8,
10, 12 and 14 and ships exactly 16 pages, `lm_0000` through `lm_0015`. Its pages
are 1024×1024 RGB, as both earlier maps' are (`SPEC-EXTLM §2.3`).

#### 2.3 Field validation

Every check below passes on all three maps unless stated otherwise. Counts are
over the record counts in §2.2.1.

**2.3.1** `[OBSERVED]` **Planes.** All 60 932 plane normals are unit length: the
smallest observed magnitude is 0.99999994 and the largest is 1.0, so none
deviates by more than one float32 ulp. No component is non-finite.

**2.3.2** `[OBSERVED]` **Face types.** Only the values 1 (polygon), 2 (Bezier
patch) and 3 (mesh) occur — 44 190 polygons, 3578 patches, 3 meshes. Type 4 does
not occur. Every value is within the `SPEC-BSP46 §4.12.1` set.

**2.3.3** `[OBSERVED]` **Patch grids.** Every type-2 face has odd width and odd
height, both at least 3, and its vertex count equals width × height, as
`SPEC-BSP46 §6.3` requires. Observed widths run 3 to 31 and heights 3 to 31.

**2.3.4** `[OBSERVED]` **Texture names.** All 189 name fields are NUL-terminated
with nothing but NULs after the terminator, and every byte of every name is
printable ASCII. All are forward-slash paths without an extension
(`textures/plat23_pk02/light03_blue_750`) except the single reserved name
`noshader`, which occurs once per map.

**2.3.5** `[OBSERVED]` **Index fields.** Every index is in range, in all three
maps: face → texture and face → effect (or −1); face → vertex and face →
meshvert ranges lie inside their lumps; each meshvert value lies within its own
face's vertex count, as `SPEC-BSP46 §4.10.1` requires; node → plane; node
children resolve to a node or, negated, to a leaf; leaf → leafface and leaf →
leafbrush ranges; model → face and model → brush ranges; brush → brushside and
brush → texture; brushside → plane and brushside → texture.

**2.3.6** `[OBSERVED]` **Vertexes.** All 349 158 positions are finite. All
vertex normals are unit length to within 1e-3. For the 47 463 faces with a
non-negative `lm_index`, every lightmap coordinate lies in [0, 1].

**2.3.7** `[OBSERVED]` **Visdata.** In all three maps the lump length is exactly
`8 + n_vecs × sz_vecs`, as `SPEC-BSP46 §4.15.2` states, and `n_vecs` is one more
than the highest leaf cluster index — so the vectors are indexed by cluster with
nothing left over.

**2.3.8** `[OBSERVED]` **Lightvols.** `SPEC-BSP46 §4.14.2` predicts the record
count exactly for all three maps, from model 0's bounding box and the grid
spacing. `usstremor` carries `"gridsize" "128 128 128"` on its `worldspawn` and
the other two carry none, taking the 64 × 64 × 128 default; the predicted counts
95285, 134758 and 24288 are the observed ones.

**2.3.9** `[OBSERVED]` **Entity lump.** All three are pure 7-bit ASCII,
LF-terminated, ending in a single NUL. Every non-brace line matches the
`SPEC-BSP38 §10` form of two double-quoted tokens; there are no comments, no
backslash escapes and no CRLF.

**2.3.10** `[OBSERVED]` Every `"model" "*N"` value in the three maps resolves to
a brush model in range, and no entity's `model` value takes any other form.

#### 2.4 Where a field is used differently

**2.4.1** `[OBSERVED]` **A face's lightmap corner and lightmap block size fields
are zero on every face of every map** — all four int32s at offsets 32..47 of the
`SPEC-BSP46 §4.12` record. A reader that sub-addresses a 128×128 lightmap image
with them gets a degenerate rectangle. Nothing needs them: with external pages
the UVs already span the whole page (`SPEC-EXTLM §3.2`).

**2.4.2** `[OBSERVED]` **A negative `lm_index` here is −3, not −1.** It occurs on
43, 147 and 118 faces of the three maps and −1 occurs on none. `SPEC-EXTLM §3.3`
records this and the rule it implies: treat any negative value as "no lightmap".

**2.4.3** `[OBSERVED]` The effect record's second int32, which `SPEC-BSP46 §4.11`
marks unused, holds 1, 3, 2 and 2 on the four effect records in the corpus
rather than zero. Its first int32 is a brush index and is in range in all four.
`[UNKNOWN]` What the second field means. A reader that ignores the effects lump,
as `SPEC-BSP46 §4.11.1` permits, is unaffected.

**2.4.4** `[OBSERVED]` **The texture record's surface and contents words carry
values outside the Quake 3 assignments.** The 22 distinct surface-flag values
across the three maps are 0x0, 0x20, 0x80, 0x82, 0xC14, 0xC20, 0x1000, 0x4000,
0x4010, 0x4020, 0x4030, 0x4080, 0x4088, 0x4180, 0x4C00, 0x5000, 0x5080,
0x11000, 0x11020, 0x18000, 0x18030, 0x20C16. The 8 distinct contents values are
0x0, 0x1, 0x4001, 0x20000000, 0x20000001, 0x20000040, 0x20010000, 0x30000000.

**2.4.5** `[OBSERVED]` Three of those contents bits are named by content in the
corpus. `res-leveleditor_0.54.dpk` ships `scripts/custinfoparms.txt`, a text
file declaring custom contents flags: `noalienbuild` = 0x1000, `nohumanbuild` =
0x2000, `nobuild` = 0x4000. The observed contents value 0x4001 is consistent
with that: it is `nobuild` combined with the low bit that appears alone on
ordinary solid brushes. The same three names appear as `surfaceparm` values in
the material scripts (§4.4).

**2.4.6** `[UNKNOWN]` **Every other bit of both words.** This document records no
further meaning, for the same reason `SPEC-BSP46 E.1` records none: the values
cannot be established from data alone, and the surface behaviour a viewer needs
comes from the material scripts and the texture name instead. A viewer must not
carry the version 38 assignments of `SPEC-BSP38 §8` across.

---

### 3. Content formats

**3.1** `[OBSERVED]` The extensions present across the corpus, with counts.
"Q3-era" means id Software's Quake III Arena 1.32 would already read it.

**3.1.1 Images** — 1076 files.

| Extension | Files | Format | Specification | Q3-era |
|---|---|---|---|---|
| `.crn` | 706 | Crunch, a block-compressed texture container | [SPEC-CRN](SPEC-CRN.md) | no |
| `.webp` | 306 | WebP | `[DOCUMENTED]` RFC 9649, `https://www.rfc-editor.org/rfc/rfc9649.html` | no |
| `.jpg` | 47 | JPEG/JFIF | `[DOCUMENTED]` ITU-T T.81, `https://www.w3.org/Graphics/JPEG/itu-t81.pdf` | yes |
| `.tga` | 17 | Truevision TGA | `[DOCUMENTED]` TGA File Format Specification 2.0, `https://www.dca.fee.unicamp.br/~martino/disciplinas/ea978/tgaffs.pdf` | yes |

**3.1.2** `[OBSERVED]` All 306 `.webp` files are RIFF/WEBP containers. Three
chunk kinds occur: `VP8 ` lossy (252), `VP8X` extended (28) and `VP8L` lossless
(26). All 47 `.jpg` are JFIF. All 17 `.tga` are uncompressed 24/32-bit images of
size 1×1 — colour swatches, not surface textures.

**3.1.3** `[OBSERVED]` The 706 `.crn` files satisfy every check in
[SPEC-CRN](SPEC-CRN.md) — the `Hx` signature, the file-size field matching the
file's own length, the mip count matching a full chain, and a face count of 1 —
across a corpus more than twice the size that spec was written from. Their pixel
format codes are 0 (377 files), 2 (226) and 7 (103), the same three
`SPEC-CRN §3.1` records.

**3.1.4** `[OBSERVED]` Where the images sit: `textures/` holds 487 `.crn`, 54
`.webp`, 47 `.jpg` and all 17 `.tga`; `env/` holds 186 `.webp` and nothing else;
`maps/` holds 28 `.webp` (the lightmap pages of §2.2.2); `ui/`, `gfx/`, `icons/`
and `emoticons/` hold 208 `.crn` and 17 `.webp` between them.

**3.1.5** `[OBSERVED]` The skyboxes in `env/` use the Quake 3 six-face naming
unchanged — `<base>_bk`, `_dn`, `_ft`, `_lf`, `_rt`, `_up` — 31 complete sets of
six, all `.webp`.

**3.1.6 Models** — 14 files.

| Extension | Files | Format | Specification | Q3-era |
|---|---|---|---|---|
| `.iqm` | 2 | Inter-Quake Model | `[DOCUMENTED]` `https://github.com/lsalzman/iqm` (`iqm.txt`, public domain) | no |
| `.ase` | 9 | ASCII scene export, text | `[UNKNOWN]` no published specification found | no |
| `.md3` | 3 | Quake 3 model | `[UNKNOWN]` no published id Software specification; community-documented | yes |

**3.1.7** `[OBSERVED]` Both `.iqm` files begin with the 16 bytes
`INTERQUAKEMODEL\0` and carry version **2**. All three `.md3` begin with `IDP3`
and carry version 15, the ordinary Quake 3 value. All nine `.ase` begin with the
text `*3DSMAX_`.

**3.1.8 Sounds** — 41 files.

| Extension | Files | Format | Specification | Q3-era |
|---|---|---|---|---|
| `.opus` | 34 | Ogg-encapsulated Opus | `[DOCUMENTED]` RFC 7845 (encapsulation), RFC 6716 (codec) | no |
| `.ogg` | 6 | Ogg Vorbis | `[DOCUMENTED]` `https://xiph.org/vorbis/doc/Vorbis_I_spec.html` | no |
| `.wav` | 1 | RIFF WAVE | `[DOCUMENTED]` Multimedia Programming Interface and Data Specifications 1.0 | yes |

**3.1.9** `[OBSERVED]` All 34 `.opus` files carry an `OpusHead` packet in the
first Ogg page. **Neither channel count nor input sample rate is uniform**: 31
are mono and 3 stereo, and the declared input rates are 48 000 Hz (23 files),
44 100 (9) and 22 050 (2). This is the same non-uniformity
`SPEC-Q3ENTITIES §2.2` records for Quake 3 content, so the handling that spec
already prescribes applies unchanged.

**3.1.10 Scripts and configuration** — 168 files.

| Extension | Files | What it is | Q3-era |
|---|---|---|---|
| `.cfg` | 113 | key/value text under `configs/` (classes, weapons, buildables, missiles) | no |
| `.shader` | 28 | material scripts — §4 | yes, with the delta in §4 |
| `.bt` | 22 | text behaviour descriptions under `bots/` | no |
| `.particle` | 2 | text particle-system definitions under `scripts/` | no |
| `.lua` | 1 | Lua source under `ui/` | no |
| `.skin` | 1 | model skin mapping, `<name>,<material>` per line | yes |
| `.voice` | 1 | text voice-command table | no |

**3.1.11 Map-adjacent metadata** — 70 files.

| Extension | Files | What it is | Q3-era |
|---|---|---|---|
| `.bsp` | 3 | the maps — §2 | yes |
| `.map` | 2 | the editor source of two of the maps | n/a |
| `.navMesh` | 11 | binary navigation meshes beside the map | no |
| `.arena` | 3 | brace-delimited map metadata, §3.3 | yes |
| `.minimap` | 3 | brace-delimited minimap placement, §3.4 | no |
| `.txt` | 21 | `shaderlist.txt`, `custinfoparms.txt`, credits | partly |
| `.md`, `DEPS`, `VERSION`, `LICENSE`, `DELETED` | 27 | package metadata — §1 | no |

**3.1.12** `[OBSERVED]` All 11 `.navMesh` files begin with the four bytes
`TESM` followed by a 32-bit value of 3. `[UNKNOWN]` The layout beyond that; a
viewer that walks a level with its own collision does not need it, so it was not
pursued.

**3.1.13 User interface** — 76 files: 55 `.rml` and 9 `.rcss`, which are the
markup and stylesheet languages of RmlUi (`[DOCUMENTED]`
`https://mikke89.github.io/RmlUiDoc/`, MIT), and 12 `.ttf` fonts
(`[DOCUMENTED]` OpenType, `https://learn.microsoft.com/en-us/typography/opentype/spec/`).
None is Q3-era.

**3.1.14 Translations** — 19 files: 14 `.po`, one `.pot` and four `.orig`, GNU
gettext message catalogues. Not needed to render a level.

**3.1.15 Compiled game logic** — 17 files: 16 `.nexe` and one `.7z` of debug
symbols. `[OBSERVED]` The `.nexe` files are ELF binaries (four 32-bit, and the
rest split between 32- and 64-bit across three architectures). **Nothing inside
them was examined, disassembled or decompiled**; they are the project's own
game logic and are outside this document by the licence constraint that governs
it. They are listed only so the extension census is complete.

**3.2** `[DERIVED]` **A Quake-3-era loader reads none of the images that matter.**
Of the 1076 image files, 1012 are `.crn` or `.webp`, formats postdating Quake 3
by a decade or more. The 47 `.jpg` and 17 `.tga` it could read are editor
preview images and 1×1 colour swatches. §4.6 turns this into a count of surfaces.

**3.3** `[OBSERVED]` A map ships `meta/<name>/<name>.arena`, a single
brace-delimited block of key/value pairs in the Quake 3 `.arena` style, with the
keys `map`, `longname`, `author` and `type`. Observed `type` values are
`tremulous` (2) and `unvanquished` (1). The `author` value may carry `^`-prefixed
colour escapes.

**3.4** `[OBSERVED]` A map ships `minimaps/<name>.minimap`, a brace-delimited
text block. All three carry a `zone` block holding `bounds` with six numbers and
`image` with a texture path and four numbers; one also carries a top-level
`backgroundColor` with four numbers. `[DERIVED]` The four numbers after the image
path are a world-space rectangle in the map's own units: in all three maps they
equal the map's x and y extents to within a few units of model 0's bounding box.
`[UNKNOWN]` The meaning of `bounds`' six numbers, which are all zero in one of
the three maps while its `image` rectangle is populated.

---

### 4. Material scripts

**4.1** `[OBSERVED]` They live where Quake 3's do and are spelled the same way:
`scripts/*.shader`, 28 files across 9 of the 15 packages, holding **1973
materials and 1969 stage blocks**. The block syntax of `SPEC-Q3SHADER §1` — a
name token, a brace-delimited body, brace-delimited stage blocks, `//` comments,
case-insensitive keywords, one directive per line — parses all 28 files with no
unbalanced brace and no line that does not fit.

**4.2** `[OBSERVED]` Material names are the same forward-slash extensionless
paths (`SPEC-Q3SHADER §1.6`), and they match the map's texture names: 129 of the
189 texture names across the three maps have a material of exactly that name in
the corpus. Of the 60 that do not, 3 are `noshader` and 57 name packages the
corpus does not include (§1.5).

**4.3** `[OBSERVED]` `scripts/shaderlist.txt` (§1.6) names which scripts a
package contributes, in the same form Quake 3 content uses.

#### 4.4 Quake 3 keywords that still appear

**4.4.1** `[OBSERVED]` Occurrence counts across the 28 files. The column split is
by package kind, because the base game's UI scripts are numerous and would
otherwise swamp the counts that matter to a map: *map* is the three map
packages, *tex* the four texture packages, *res* the five resource packages,
*base* the three base-game packages.

| Keyword | Total | map | tex | res | base |
|---|---|---|---|---|---|
| `map` | 1750 | 62 | 63 | 20 | 1605 |
| `blendFunc` | 1664 | 41 | 2 | 23 | 1598 |
| `sort` | 1540 | 2 | 0 | 0 | 1538 |
| `rgbGen` | 1143 | 23 | 26 | 11 | 1083 |
| `surfaceparm` | 566 | 165 | 384 | 17 | 0 |
| `cull` | 557 | 17 | 17 | 3 | 520 |
| `alphaGen` | 525 | 4 | 0 | 2 | 519 |
| `qer_editorImage` | 357 | 87 | 248 | 22 | 0 |
| `q3map_*` (14 spellings) | 225 | 96 | 113 | 16 | 0 |
| `nopicmip` | 55 | 3 | 0 | 0 | 52 |
| `polygonOffset` | 33 | 26 | 0 | 7 | 0 |
| `skyparms` | 33 | 3 | 30 | 0 | 0 |
| `tcMod` | 32 | 8 | 0 | 22 | 2 |
| `alphaFunc` | 21 | 13 | 8 | 0 | 0 |
| `entityMergable` | 9 | 7 | 0 | 1 | 1 |
| `nomipmaps` | 5 | 1 | 0 | 0 | 4 |
| `depthFunc` | 5 | 5 | 0 | 0 | 0 |
| `tcGen` | 4 | 4 | 0 | 0 | 0 |
| `depthWrite` | 4 | 2 | 2 | 0 | 0 |
| `animMap` | 3 | 0 | 0 | 3 | 0 |
| `fogparms` | 2 | 2 | 0 | 0 | 0 |
| `portal` | 2 | 2 | 0 | 0 | 0 |
| `deformVertexes` | 1 | 0 | 0 | 1 | 0 |
| `tessSize` | 1 | 0 | 1 | 0 | 0 |

**4.4.2** `[OBSERVED]` Two keywords `SPEC-Q3SHADER` lists **do not occur at all**:
`clampmap` (0 occurrences — §4.5.9 gives what is used instead) and `detail`.
`light` occurs only as an entity key (§5), never as a directive.

**4.4.3** `[OBSERVED]` The argument shapes are those `SPEC-Q3SHADER §2.3`
records. `blendFunc` takes two GL factors (1582 times) or one shorthand (82:
`add` 29, `filter` 27, `blend` 26). `alphaFunc` takes `GE128` in all 21
occurrences. `cull` takes `back` (512), `none` (39) or `disable` (6). `tcMod`
takes `scale`, `scroll`, `rotate`, `turb` and `transform` forms of the arities
`SPEC-Q3SHADER §2.4.2` gives. `rgbGen` takes `const ( r g b )`, `exactVertex`,
`vertex`, `identity`, `identityLighting` and one `wave` form. `sort` takes a
number or the token `nearest`.

**4.4.4** `[OBSERVED]` **`surfaceparm` values**, 566 occurrences over 30 distinct
values. Values `SPEC-Q3SHADER §2.2` already lists: `trans` 109, `nolightmap` 79,
`nonsolid` 77, `alphashadow` 38, `sky` 34, `nodraw` 33, `playerclip` 5,
`botclip` 1, `hint` 1, `skip` 1, `origin` 1. Values it does not list, with counts
and, where the name and its bearers make it plain, a derived reading:

| Value | Count | Reading |
|---|---|---|
| `nomarks` | 64 | `[UNKNOWN]` — no visual effect a viewer produces |
| `noimpact` | 63 | `[UNKNOWN]` |
| `metalsteps` | 34 | `[DERIVED]` a footstep-sound class; no visual effect |
| `slick` | 4 | `[UNKNOWN]` |
| `structural` | 4 | `[UNKNOWN]` — a compile-time classification |
| `nobuild` | 3 | `[DERIVED]` the contents flag 0x4000 of §2.4.5, by name |
| `lightfilter` | 2 | `[UNKNOWN]` |
| `fog` | 2 | `[DERIVED]` a fog volume, as `SPEC-Q3SHADER §2.2` treats `water`/`slime`/`lava` |
| `noalienbuild`, `nohumanbuild` | 1 each | `[DERIVED]` the contents flags 0x1000 and 0x2000 of §2.4.5, by name |
| `nodlight`, `areaportal`, `nodamage`, `donotenter`, `ladder`, `detail`, `lightgrid`, `nodrop`, `dust` | 1 each | `[UNKNOWN]` |

None of these changes what is drawn, so `SPEC-Q3SHADER §2.2`'s final row —
record it and otherwise ignore it — remains correct for all of them.

#### 4.5 Keywords `SPEC-Q3SHADER` does not list

**4.5.1** `[OBSERVED]` **The stage's texture is usually not named by `map`.** Six
stage keywords name an image and none is in `SPEC-Q3SHADER`:

| Keyword | Total | map | tex | res | Argument shape |
|---|---|---|---|---|---|
| `diffuseMap` | 215 | 53 | 149 | 13 | one extensionless path |
| `specularMap` | 184 | 48 | 123 | 13 | one extensionless path |
| `normalMap` | 183 | 48 | 123 | 12 | one extensionless path |
| `heightMap` | 128 | 1 | 119 | 8 | one extensionless path |
| `glowMap` | 40 | 19 | 15 | 6 | one extensionless path |
| `lightFalloffImage` | 2 | 0 | 0 | 0 | one extensionless path (body-level, not stage-level) |

**4.5.2** `[DERIVED]` They are the channels of one physically-based material, and
the file-naming convention in the content says so directly: 205 of the 215
`diffuseMap` arguments end in `_d`, 184 of 184 `specularMap` in `_s`, 183 of 183
`normalMap` in `_n`, and 128 of 128 `heightMap` in `_h`. A stage carrying them
names one surface's several maps rather than one pass over it — a stage of this
kind holds no `blendFunc` and needs none.

**4.5.3** `[OBSERVED]` How materials name their image, over all 1973:

| Shape | Materials |
|---|---|
| `map`/`clampmap`/`animMap` only | 1687 |
| `diffuseMap` only, no `map` at all | 169 |
| both `map` and `diffuseMap`, in different stages | 46 |
| no stage block at all | 71 |

**4.5.4** `[OBSERVED]` **All 169 of the `diffuseMap`-only materials carry a
`qer_editorImage`**, and in 154 of them its argument is the same path as the
`diffuseMap`. So `SPEC-Q3SHADER §2.3.1`'s fallback chain does find an image for
every one of them, and usually the right one.

**4.5.5** `[OBSERVED]` The 46 materials carrying both are the case that goes
wrong. In them the PBR stage comes first and a later stage carries `map <path>_a`
with an additive blend — a glow mask. `SPEC-Q3SHADER §2.3.1` takes the first
stage `map` and therefore takes the mask. Across the three maps' texture names
this happens to **14 surfaces**, against 50 where the chain reaches
`qer_editorImage` and gets the correct diffuse image (47 of which resolve to a
file the corpus ships).

**4.5.6** `[DERIVED]` The rule that gets this right is to prefer `diffuseMap`
over `map` when a material has both, and to fall back to
`SPEC-Q3SHADER §2.3.1`'s chain otherwise. It costs one extra keyword in the
parser and it is correct for all 1973 materials in the corpus.

**4.5.7** `[OBSERVED]` **`blend` is an alternative spelling of the `blendFunc`
shorthand**: 73 occurrences across 3 files, always exactly one argument, either
`add` (44) or `blend` (29) — two of the three shorthand names
`SPEC-Q3SHADER §2.3` gives for `blendFunc`. `[DERIVED]` A parser that does not
know it treats a translucent or additive stage as opaque. The two spellings
coexist in the corpus and even in the same package, so a reader must accept both.

**4.5.8** `[OBSERVED]` **`red`, `green` and `blue`** each occur 44 times, each
taking one number, and they occur only together and only in a stage that also
carries `map` and `blend add` — all 44 stages have exactly that shape.
`[DERIVED]` They scale the stage's three colour channels by constants, which is
what `rgbGen const ( r g b )` does in `SPEC-Q3SHADER §2.4.4`; the observed values
(`.2 .2 .3` on the additive glow of a blue-tinted light) fit nothing else.

**4.5.9** `[OBSERVED]` **Texture wrap is set by argument-less stage keywords**
rather than by `clampmap`, which does not occur (§4.4.2): `zeroClamp` (3
occurrences) and `edgeClamp` (1), both in the base game's light-attenuation
materials. `[DERIVED]` They select a clamping wrap mode, the two names
distinguishing clamp-to-border-zero from clamp-to-edge.

**4.5.10** `[OBSERVED]` **`stage <token>`** — 6 occurrences, one token, values
`attenuationMapXY` (3), `heathazeMap` (2), `attenuationMapZ` (1). It appears
inside a stage block alongside a `map`. `[DERIVED]` It labels what the stage's
image is for, in the same way `diffuseMap`/`normalMap` do by keyword, for roles
that have no keyword of their own. `[UNKNOWN]` The rendering each label selects.
The `heathazeMap` stages sit in a forcefield and an energy-distortion material,
so a viewer that skips them draws the surface without its distortion.

**4.5.11** `[OBSERVED]` **`when <state> <material>`** — 7 occurrences, always two
tokens, at body level. Observed states: `unpowered` (2), `destroyed` (3),
`idle2` (1), and the second token is always another material's name. All 7 are in
buildable models. `[DERIVED]` It names a substitute material for a game state.
A viewer that has no such state draws the material as written, which is the
default appearance.

**4.5.12** `[OBSERVED]` **`imageMinDimension <number>`** — 12 occurrences at body
level, one number, values 24, 128 and 256. `[DERIVED]` A floor on how far the
material's textures may be downscaled, from the name and from the values, which
are all powers of two smaller than the textures they guard. It has no effect on
a viewer that does not downscale.

**4.5.13** `[OBSERVED]` The remaining new keywords, all rare, all inside a stage
block:

| Keyword | Count | Arguments | Meaning |
|---|---|---|---|
| `normalFormat` | 8 | three tokens, always `X Y Z` | `[DERIVED]` the axis order and sign of the normal map's channels; `X Y Z` is the unmodified reading |
| `rawSpecularMap` | 4 | none | `[UNKNOWN]` — appears after a `specularMap` in terrain materials |
| `forceHighQuality` | 3 | none | `[UNKNOWN]` — a rendering-quality request |
| `colored` | 3 | none | `[UNKNOWN]` — appears with `attenuationMapXY` |
| `deformMagnitude` | 2 | one number (1, 6) | `[DERIVED]` the strength of the `heathazeMap` distortion it always accompanies |
| `specularExponentMin` | 2 | one number (10) | `[DERIVED]` the low end of a specular exponent range |
| `specularExponentMax` | 2 | one number (25) | `[DERIVED]` the high end of the same range |
| `rawColorMap` | 1 | none | `[UNKNOWN]` — appears after a `map` in a forcefield material |

**4.5.14** `[OBSERVED]` Three editor-only body-level keywords beyond the
`qer_editorImage` that `SPEC-Q3SHADER §2.1` lists: `qer_trans` (81, one number),
`qer_nocarve` (9, no arguments) and `qer_alphaFunc` (7, a token and a number).
`[DERIVED]` They describe the material to the map editor, as the `qer_` prefix
and their absence from any drawing decision indicate, and a viewer ignores them —
except `qer_editorImage`, which §4.5.4 makes load-bearing.

**4.5.15** `[OBSERVED]` **New reserved `$` values for `map`.** Beyond
`SPEC-Q3SHADER §2.3`'s `$lightmap` (9 occurrences) and `$whiteimage` (1543),
three more occur: `$white` (28), `$black` (5) and `$blackimage` (3, in two
spellings differing only in case). `[DERIVED]` `$white` is a second spelling of
`$whiteimage` and `$black`/`$blackimage` are its black counterpart. `[DERIVED]`
A reader must test for a leading `$` rather than for the two names it knows,
since a `$` value taken as a path yields a missing texture.

**4.5.16** `[DERIVED]` `SPEC-Q3SHADER §2.1.1`'s line-oriented skip holds for
every new keyword above: all 26 of them keep their arguments on one line, and no
directive in the corpus spans a line break. An unrecognised directive can still
be skipped to end of line without desynchronising.

#### 4.6 What the material scripts point at

**4.6.1** `[OBSERVED]` Of the 931 image references made by stage keywords across
all 1973 materials, **796 resolve to a `.crn` file and 67 to a `.webp`**. None
resolves to a `.tga` or a `.jpg`. The remaining 68 name packages the corpus does
not include.

**4.6.2** `[OBSERVED]` Of the 357 `qer_editorImage` references, 198 resolve to
`.crn`, 70 to `.webp`, 45 to `.jpg`, 32 to `.tga` and 12 to nothing.

**4.6.3** `[DERIVED]` So the extension search of `SPEC-BSP46 §7.3` and
`SPEC-Q3SHADER §1.6` is unchanged in form but must be given `.crn` and `.webp`
to search: a reader offering only the Quake 3 extensions finds an image for a
minority of editor previews and for no surface texture at all.

---

### 5. Entities

**5.1** `[OBSERVED]` **The entity lump is unchanged.** §2.3.9 records the syntax
check: brace-delimited blocks of double-quoted key/value pairs, pure ASCII, no
escapes, no comments, terminated by a NUL. `SPEC-BSP46 §5.1` and
`SPEC-BSP38 §10` apply as written, including the `"*N"` brush-model convention
(§2.3.10). Nothing about parsing changes.

**5.2** `[OBSERVED]` The three maps place **446 entities** — 55 in `plat23`, 292
in `usstremor`, 99 in `yocto` — carrying **32 distinct classnames**.

#### 5.3 The classnames

**5.3.1** `[OBSERVED]` Every classname in the corpus, with how many entities
carry it and how many of the three maps place at least one:

| Classname | Entities | Maps |
|---|---|---|
| `gfx_light_flare` | 81 | 1 |
| `target_location` | 69 | 3 |
| `target_speaker` | 67 | 2 |
| `func_door` | 42 | 2 |
| `misc_particle_system` | 42 | 1 |
| `lightJunior` | 23 | 1 |
| `info_null` | 16 | 1 |
| `team_alien_acid_tube` | 14 | 3 |
| `team_human_mgturret` | 11 | 3 |
| `trigger_multiple` | 10 | 1 |
| `team_alien_spawn` | 9 | 3 |
| `target_delay` | 8 | 1 |
| `team_human_spawn` | 8 | 3 |
| `trigger_hurt` | 5 | 2 |
| `path_corner` | 4 | 1 |
| `info_alien_intermission` | 3 | 3 |
| `info_human_intermission` | 3 | 3 |
| `info_player_intermission` | 3 | 3 |
| `light` | 3 | 1 |
| `team_alien_overmind` | 3 | 3 |
| `team_human_armoury` | 3 | 3 |
| `team_human_reactor` | 3 | 3 |
| `worldspawn` | 3 | 3 |
| `func_button` | 2 | 1 |
| `team_alien_barricade` | 2 | 2 |
| `team_human_drill` | 2 | 2 |
| `team_human_medistat` | 2 | 2 |
| `func_plat` | 1 | 1 |
| `func_timer` | 1 | 1 |
| `func_train` | 1 | 1 |
| `target_print` | 1 | 1 |
| `team_alien_leech` | 1 | 1 |

**5.3.2** `[OBSERVED]` The keys carried, over all 446 entities:

| Key | Count | Key | Count | Key | Count |
|---|---|---|---|---|---|
| `classname` | 446 | `psName` | 42 | `sound2to1` | 15 |
| `origin` | 383 | `group` | 38 | `angles` | 10 |
| `angle` | 107 | `volrange` | 36 | `dmg` | 6 |
| `radius` | 81 | `lip` | 35 | `_color` | 3 |
| `shader` | 81 | `count` | 26 | `light` | 3 |
| `message` | 73 | `target` | 26 | `reverbEffect` | 3 |
| `targetname` | 71 | `style` | 23 | `reverbIntensity` | 3 |
| `noise` | 69 | `sound1to2` | 17 | `gradingTexture` | 3 |
| `spawnflags` | 62 | `soundPos1` | 15 | `health` | 2 |
| `model` | 61 | `soundPos2` | 15 | 10 more | see §5.8.1 |
| `wait` | 54 | | | | |
| `speed` | 44 | | | | |

41 distinct keys occur in all. The ten not named above are `worldspawn`'s own
and are listed in §5.8.1.

**5.3.3** `[OBSERVED]` Only `classname` is universal. `origin` is carried by 383
of the 446; of the 63 without it, 60 are brush entities that take their position
from their `"*N"` model and the other 3 are the maps' `worldspawn` entities.

#### 5.4 Spawn points

**5.4.1** `[OBSERVED]` **The Quake 3 spawn classnames are absent.** Neither
`info_player_deathmatch` nor `info_player_start` occurs in any of the three
maps, nor does any `team_CTF_*` classname. A viewer that looks for them finds no
spawn point at all and has nowhere to put the camera.

**5.4.2** `[OBSERVED]` What the maps place instead — **17 team spawn entities**
across the three maps, `team_alien_spawn` (9) and `team_human_spawn` (8), every
map carrying at least one of each. Both carry `origin` on every occurrence and
`angle` on 15 of the 17.

**5.4.3** `[OBSERVED]` **Three intermission classnames** occur, and all three
maps carry exactly one of each: `info_player_intermission`,
`info_alien_intermission` and `info_human_intermission`. Each carries an
`origin`; orientation comes from either `angle` (a single yaw, 5 of the 9) or
`angles` (three numbers, 4 of the 9).

**5.4.4** `[DERIVED]` The intermission points are the better camera placement for
a viewer: they are the map author's chosen overview of the level, they exist in
every map, and there are exactly three of them so the choice is not arbitrary.
The team spawns are where a player body would start. A viewer should look for
both and prefer whichever suits it, rather than looking for `info_player_*` and
giving up.

**5.4.5** `[OBSERVED]` `angle` and `angles` are **not interchangeable spellings**
in this content: 107 entities carry `angle` (one number) and 10 carry `angles`
(three numbers), and no entity carries both. The `angle` values include `-1` and
`-2`, which occur only on `func_door` (14 of 42) and `func_button` (2 of 2) —
`[DERIVED]` these are the Quake 3 convention of `-1` and `-2` meaning "up" and
"down" for a moving brush rather than a compass direction, since a door is the
only place they occur and a door is the only entity that moves vertically.

#### 5.5 Lights

**5.5.1** `[OBSERVED]` **Static lights barely appear in the compiled map**: 3
`light` entities in one map and 23 `lightJunior` in another, none in the third.
`[DERIVED]` The map compiler consumes light entities into the lightmap, so what
survives into the `.bsp` is a small remainder rather than the map's lighting.
Two of the three maps carry `"_keepLights" "1"` on `worldspawn`, so the setting
that governs the remainder is visible in the data, but with three maps its
effect on the counts is not established.

**5.5.2** `[OBSERVED]` `light` carries `origin`, `light` (a single number, 20 in
all 3) and `_color` (three numbers). `lightJunior` carries `origin`,
`targetname` (a distinct `lspot_door_*` name on each) and `style` (a single
integer, the 23 consecutive values 32 through 54, one per entity).

**5.5.3** `[OBSERVED]` **`gfx_light_flare`, 81 entities in one map**, is the
numerous light-like entity. All 81 carry `origin`, `shader` (a material name,
one distinct value across all 81) and `radius` (three numbers, values
`20 0 0.1` on 78 and `8 0 8` on 3). `[DERIVED]` It places a camera-facing lens
flare drawn with the named material. `[UNKNOWN]` What the three numbers of
`radius` are; the name says the first is a size and the values differ too little
to establish the others.

**5.5.4** `[OBSERVED]` The `lightJunior` and `gfx_light_flare` entities are in
the same map and eight of the 23 `lightJunior` sit exactly 66 units along x from
a flare. The other fifteen have no flare nearer than 70 units, so the two sets
are not a paired source-and-flare authoring throughout. `[UNKNOWN]` Whether a
`lightJunior` and a flare are related at all.

**5.5.5** `[DERIVED]` A viewer lit by the baked lightmap needs none of these:
`SPEC-EXTLM` supplies the light the author baked, and §2.3.8 supplies the
lightvol grid for anything that moves.

#### 5.6 Doors, platforms and push volumes

**5.6.1** `[OBSERVED]` **No push volumes and no teleporters.** `trigger_push`,
`trigger_teleport`, `misc_teleporter_dest`, `target_position` and
`target_teleporter` occur in none of the three maps, so
[SPEC-Q3PUSH](SPEC-Q3PUSH.md) and [SPEC-TRIGGER-PUSH](SPEC-TRIGGER-PUSH.md)
describe nothing this content places. Vertical travel is by `func_door`,
`func_plat` and `func_train` instead.

**5.6.2** `[OBSERVED]` **`func_door`, 42 entities in two maps**, is the moving
brush of this content. Every one carries `model` (`"*N"`) and `angle`; 40 carry
`speed`, 32 `lip`, 31 `wait`, 5 `targetname`, 3 `spawnflags` and 2 `health`. The
keys and their shapes are Quake 3's.

**5.6.3** `[OBSERVED]` `func_door` carries **four sound keys not in
`SPEC-Q3ENTITIES`** — `sound1to2`, `sound2to1`, `soundPos1` and `soundPos2` — 14
occurrences each, plus one `func_plat` and two `func_button` carrying the same
family. `[DERIVED]` They name the sounds of the four moments of a two-position
mover: leaving position 1, leaving position 2, and arriving at each. The values
support it — `sound/yocto/lift1to2`, `sound/yocto/lift2to1`,
`sound/yocto/doorstop` for both `soundPos` keys — and 12 of the 14 in one map are
the placeholder `sound/yocto/null`.

**5.6.4** `[OBSERVED]` **`group`, 38 occurrences, all on `func_door`**, a short
token (`alienbase`, `windowhall`, `00`, `10`). `[DERIVED]` It ties several door
brushes into one door: the values repeat across 2 to 5 entities each and never
appear on anything else.

**5.6.5** `[OBSERVED]` One `func_train` and four `path_corner` occur, in one map,
with the Quake 3 keys — `target` and `targetname` chaining the corners into a
loop, `speed` on the train.

**5.6.6** `[OBSERVED]` `trigger_multiple` (10) and `trigger_hurt` (5) are brush
triggers carrying `model`. `trigger_multiple` carries `wait` and `target`;
`trigger_hurt` carries `dmg` and, on 3 of 5, `spawnflags`. `[DERIVED]` Neither
is drawn, so a viewer that walks the level skips both — but their brush models
are in the models lump, and a viewer that draws every model rather than only the
ones no entity claims will draw the trigger volumes as solid boxes.

#### 5.7 Sound

**5.7.1** `[OBSERVED]` **`target_speaker`, 67 entities in two maps.** All 67
carry `origin` and `noise`, 54 carry `spawnflags` (the value `1` in all 54), 36
carry `volrange`, 13 carry `targetname` and 6 carry `angle`. This matches
`SPEC-Q3ENTITIES §1.1.2` in shape, and `§1.4.2`'s reading of bit 1 as "loops" is
consistent: the sounds carrying it are `computer_sounds`, `machine_with_pipe`,
`window_rumble`.

**5.7.2** `[OBSERVED]` **`volrange` is new** — 36 occurrences, two numbers,
`512 512` in every one. `[UNKNOWN]` What the two numbers are. The name and the
units of the map suggest a distance range in map units, and the two being equal
in every occurrence means the data cannot distinguish an inner/outer pair from
anything else. A reader must not infer an attenuation curve from this.

**5.7.3** `[OBSERVED]` **The extension on a sound reference is advisory here
too**, exactly as `SPEC-Q3ENTITIES §1.2.3` records for Quake 3 content. Across
the 132 sound references in the three maps' entity lumps (`noise`, the four
mover keys, and `music`): 69 carry no extension at all, 53 carry `.opus`, and 10
carry `.wav`. **All 122 that resolve, resolve to a `.opus` file**, and every one
of the 10 `.wav` references names a file that does not exist under any
extension. `SPEC-Q3ENTITIES §1.2.4`'s procedure — strip the extension, try the
supported ones — is required, with `.opus` among them.

**5.7.4** `[OBSERVED]` `worldspawn` may carry `music` (1 of 3 maps), naming a
level-wide track the same way (`sounds/usstremor/levelwide_rumble.opus`).

**5.7.5** `[OBSERVED]` Sound paths use two root directories, `sound/` and
`sounds/`, one map using each. `[DERIVED]` The path is used as written; there is
no root to strip or add.

#### 5.8 `worldspawn`

**5.8.1** `[OBSERVED]` The keys the three `worldspawn` entities carry:
`_q3map2_version` (3), `_q3map2_cmdline` (3), `message` (3, the map's display
name), `reverbEffect` (3), `reverbIntensity` (3), `gradingTexture` (3),
`_keepLights` (2), `_lightmapscale` (2), `_blocksize` (2), `music` (1),
`_floodlight` (1), `gridsize` (1), `_farplanedist` (1), `author` (1).

**5.8.2** `[OBSERVED]` `gridsize` is the key `SPEC-BSP46 §4.14.2` needs, and
§2.3.8 confirms it behaves as that fact describes.

**5.8.3** `[OBSERVED]` **`gradingTexture`, on all three maps**, names an image
(`gfx/<mapname>/colorgrading`), and all three ship that file as a `.webp`.
`[DERIVED]` It is a colour-grading lookup applied to the finished frame — from
the name, from its being one image per map, and from its living under `gfx/`
rather than `textures/`. `[UNKNOWN]` How the image is indexed. A viewer that
ignores it renders the map's own colours, which is a defensible result.

**5.8.4** `[OBSERVED]` `reverbEffect` (values `spacestation_alcove`,
`spacestation_mediumroom`, `spacestation_smallroom`) and `reverbIntensity`
(0.6, 0.75, 0.8) name a level-wide reverb by name and scale it. `[UNKNOWN]` The
vocabulary of effect names and the parameters behind each.

**5.8.5** `[OBSERVED]` The `_`-prefixed keys are compiler directives with no
run-time meaning, the same family as `SPEC-Q3SHADER §2.1`'s `q3map_*`.

#### 5.9 Classnames a viewer does not need

**5.9.1** `[OBSERVED]` **`target_location`, 69 entities across all three maps**,
carries `origin`, `message` (a room name such as `Machine Room`) and, on 26,
`count`. `[DERIVED]` It labels a region of the map for display; nothing is drawn
at its origin.

**5.9.2** `[OBSERVED]` **`misc_particle_system`, 42 entities in one map**,
carries `origin`, `psName` (10 distinct values, `usstremor/stars_01` and the
like) and `angle` on 3. `[DERIVED]` `psName` names a definition in one of the
`.particle` files of §3.1.10, which are text and could be read; a viewer that
draws no particles skips them.

**5.9.3** `[OBSERVED]` **Eleven `team_*` classnames** — `team_alien_spawn`,
`team_alien_overmind`, `team_alien_acid_tube`, `team_alien_barricade`,
`team_alien_leech`, `team_human_spawn`, `team_human_reactor`,
`team_human_armoury`, `team_human_medistat`, `team_human_drill`,
`team_human_mgturret` — 58 entities in all. Every one carries `origin` and most
carry `angle`; none carries anything else. `[DERIVED]` They place a team's
starting structures, and a viewer with no models for them has nothing to draw
and loses nothing by skipping them. They are the closest thing this content has
to Quake 3's pickups, and `SPEC-Q3ENTITIES §3`'s pickup classnames — `item_*`,
`weapon_*`, `ammo_*`, `holdable_*` — occur **not once** in these maps.

**5.9.4** `[OBSERVED]` `info_null` (16, one map) carries `targetname` and
`origin` and nothing else; every `targetname` begins `decal_`. `target_delay`
(8), `target_print` (1), `func_timer` (1) and `func_button` (2) are the Quake 3
trigger vocabulary, wiring the map's one lift. `SPEC-Q3ENTITIES §1.6.2` applies:
without a trigger system these are out of scope.

---

### 6. What a Quake-3-only loader gets wrong

Ranked by how much of the level is lost, worst first. Each is tied to the fact
above that causes it.

**6.1** `[OBSERVED]` **Every surface is untextured.** All 863 resolvable image
references from material scripts land on a `.crn` or a `.webp` and none on a
`.tga` or `.jpg` (§4.6.1); a Quake 3 loader supports neither format (§3.1.1). It
draws the whole level in whatever it uses for a missing texture. Cause: §3.1.1,
§4.6.1.

**6.2** `[OBSERVED]` **The level has no baked light.** The lightmaps lump is
empty in all three maps (§2.2.2); the light is in `.webp` pages beside the
`.bsp` that a Quake 3 loader does not look for and could not decode
([SPEC-EXTLM](SPEC-EXTLM.md)). With §6.1 it draws untextured geometry under no
lighting at all. Cause: §2.2.2, §3.1.1.

**6.3** `[OBSERVED]` **There is nowhere to stand.** `info_player_deathmatch` and
`info_player_start` occur in none of the three maps (§5.4.1). A loader keyed to
them finds no spawn point and must either fail or place the camera arbitrarily.
The fix is small — read `team_alien_spawn`, `team_human_spawn` and the three
`info_*_intermission` classnames (§5.4.2, §5.4.3). Cause: §5.4.1.

**6.4** `[OBSERVED]` **169 materials — 8.6% of the corpus, and 32 of one map's 54
surfaces — have no `map` directive in any stage**, because they name their
texture with `diffuseMap` (§4.5.3). `SPEC-Q3SHADER §2.3.1`'s fallback saves this
case: all 169 carry a `qer_editorImage` (§4.5.4). A loader without that fallback
has no image path at all for them, even before §6.1. Cause: §4.5.1, §4.5.3.

**6.5** `[OBSERVED]` **14 surfaces across the three maps get the wrong image**:
the material carries both a PBR stage and a later additive glow-mask stage, and
`SPEC-Q3SHADER §2.3.1` picks the first `map` it sees, which is the mask
(§4.5.5). These render as a glow pattern on black rather than as the surface.
Unlike §6.4 the fallback does not rescue it, because a `map` was found — it was
simply the wrong one. Cause: §4.5.5.

**6.6** `[OBSERVED]` **73 stages are drawn opaque that should blend**, because
they spell the blend directive `blend add` or `blend blend` rather than
`blendFunc` (§4.5.7). Additive glows and translucent decals become solid
rectangles. Cause: §4.5.7.

**6.7** `[OBSERVED]` **Every placed sound is silent.** All 122 resolvable sound
references resolve to `.opus` (§5.7.3), which a Quake 3 loader does not decode,
and 10 of the 132 references additionally name a `.wav` that does not exist, so
even the extension a Quake 3 loader would try is wrong. Cause: §3.1.8, §5.7.3.

**6.8** `[DERIVED]` **The skybox is missing.** The `skyparms` directive and the
six-face `_bk`/`_dn`/`_ft`/`_lf`/`_rt`/`_up` naming are unchanged (§3.1.5), so a
Quake 3 loader looks in the right place under the right names and finds only
`.webp`. Where 34 `surfaceparm sky` materials are involved, the sky reads as
untextured rather than as sky. Cause: §3.1.1, §3.1.5.

**6.9** `[DERIVED]` **Faces with no lightmap are treated as having one, or
rejected.** A loader that tests `lm_index == -1` for "no lightmap" mishandles the
308 faces across the three maps that carry `-3` (§2.4.2), and one that indexes
the lightmaps lump with a value of 0 through 14 while that lump is empty
(§2.2.2) reads past its end. Cause: §2.4.2, §2.2.2.

**6.10** `[DERIVED]` **Trigger and clip volumes may be drawn as solid boxes.** 15
brush entities across the three maps are `trigger_multiple` or `trigger_hurt`
(§5.6.6), and their brush models sit in the models lump like any other. A loader
that draws models 1..N without checking which entity claims each, and without
honouring `surfaceparm nodraw` (33 occurrences, §4.4.4), puts them in the middle
of the level. Cause: §5.6.6, §4.4.4.

**6.11** `[OBSERVED]` **Nothing in the map container itself misparses.** §2.2.1
and §2.3 record 42 divisibility checks and ten classes of field check passing
on all three maps with no exception. Every failure above is a *content* failure —
an image format, a keyword spelling, a classname — and none of them is a reason
to change the binary reader. Cause: §2.

---

## Excluded

- **The compiled game logic.** The 16 `.nexe` binaries and the `.7z` symbol
  archive were listed in the extension census and never opened (§3.1.15).
- **The interior of any image or audio codec.** Crunch is covered by
  [SPEC-CRN](SPEC-CRN.md), which itself defers the entropy coding to a
  permissively licensed decoder; WebP, Opus, Vorbis, JPEG and TGA are cited to
  published specifications in §3.1 and nothing about them was reverse-engineered.
- **The `.navMesh` layout** beyond its first eight bytes (§3.1.12), the `.bt`,
  `.cfg`, `.particle` and `.voice` languages, and the RmlUi interface files. None
  is needed to walk around a level.
- **Surface-flag and contents-flag bit meanings** beyond the three named by
  shipped content in §2.4.5. This continues `SPEC-BSP46 E.1`'s exclusion for the
  same reason.
- **What the `.map` editor sources contain.** Two of the three maps ship one; the
  compiled `.bsp` is what a viewer reads and the source was not analysed.
- **Anything about the engine's own behaviour.** Every "meaning" above is derived
  from a name, its arguments and the company it keeps in the data. Where that was
  not enough, the fact is marked `[UNKNOWN]` and left alone.

## Escalations

None. No copyleft source was read, fetched, cloned or opened at any point in
producing this document — not the engine, not the game logic, not the build
tooling, not the wiki, and not the quarantined material from an earlier attempt.
Every fact is from the bytes of the 15 packages, from this project's own
BSD-licensed specs, or from a published specification cited by URL.
