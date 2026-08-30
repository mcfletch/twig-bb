# SPEC-BSP46: Reading `IBSP` version 46 map files (Quake 3)

| | |
|---|---|
| Source consulted | **No copyleft source was consulted.** See "Provenance" below. |
| Licence of source | n/a — the sources used are a published format reference, this workspace's own BSD-licensed code, and sample file bytes |
| Version / commit | n/a |
| Files consulted | `http://www.mralligator.com/q3/` (published format reference); `twitch/twig_bb/bsp.py` at `master` (this workspace's own BSD code, whose module docstring cites that same reference); the bytes of sample `.bsp` files |
| Non-copyleft sources checked first | This document *is* the non-copyleft record: no engine tree was opened at any point. |
| Reader | n/a — not a clean-room spec; written by the Implementer from licence-clean sources |
| Date | 2026-07-25 |
| **Clean-room status** | **Not applicable.** No copyleft source was read for any fact below, so no wall was needed. This file exists to satisfy the "record which you used" requirement in [../plans/TWIG-BB-ARENA-VIEWER.md](../plans/TWIG-BB-ARENA-VIEWER.md), and to give the implementation a numbered document to cite, exactly as it cites the clean-room specs. |

## Provenance

Three licence-clean sources, in the order of preference set by
[../CLEAN-ROOM.md](../CLEAN-ROOM.md) Rule 0:

1. **A published, independent format reference** — `http://www.mralligator.com/q3/`,
   a long-circulated third-party description of the `IBSP` v46 container. It
   supplied the magic and version, the 17-entry lump directory and its index
   order, and the binary record layout of every lump (§1, §2, §4).
2. **This workspace's own prior implementation** — `twitch/twig_bb/bsp.py`,
   BSD-licensed code written by this project's author, whose module docstring
   records that same public reference as its source. It independently confirms
   every record layout in §4 and the patch-tessellation convention in §6.
3. **Sample file bytes** — read directly, used to confirm the header, the
   directory arithmetic and the record sizes.

No Quake, ioquake3, Alien Arena or other engine source was opened.

## Scope

What is needed in order to **read** an `IBSP` version 46 map well enough to
render its world geometry with textures and baked lightmaps, tessellate its
Bezier patches, and import its entity placements. Rendering technique, the
visibility algorithm, and the `.shader` material language are out of scope
(the last is covered by §7 of this document only to the extent of where the
files live).

## Facts

### 1. Container

**1.1** A file begins with the four ASCII bytes `I`, `B`, `S`, `P` at offsets
0..3.

**1.2** Bytes 4..7 hold a 32-bit signed version number. The version described
here is **46** (`0x2e`). A reader must reject any other value rather than guess.

**1.3** All multi-byte scalars are **little-endian**; floating-point values are
IEEE-754 binary32.

**1.4** Bytes 8 onward hold the lump directory: fixed 8-byte entries, each two
32-bit signed integers — byte offset of the lump's data from the start of the
file, then the lump's length in bytes.

**1.5** The directory has exactly **17** entries, so the header is
8 + 17 × 8 = **144 bytes**.

**1.6** For a lump of fixed-size records the record count is the lump length
divided by the record size. A length that is not an exact multiple of the record
size indicates a malformed file.

### 2. Lump directory indices

**2.1** Directory entry index → lump identity, with record size:

| Index | Lump | Record size (bytes) | Layout |
|---|---|---|---|
| 0 | Entities | variable (text) | §5 |
| 1 | Textures | 72 | §4.1 |
| 2 | Planes | 16 | §4.2 |
| 3 | Nodes | 36 | §4.3 |
| 4 | Leafs | 48 | §4.4 |
| 5 | Leaffaces | 4 | §4.5 |
| 6 | Leafbrushes | 4 | §4.5 |
| 7 | Models | 40 | §4.6 |
| 8 | Brushes | 12 | §4.7 |
| 9 | Brushsides | 8 | §4.8 |
| 10 | Vertexes | 44 | §4.9 |
| 11 | Meshverts | 4 | §4.10 |
| 12 | Effects | 72 | §4.11 |
| 13 | Faces | 104 | §4.12 |
| 14 | Lightmaps | 49152 | §4.13 |
| 15 | Lightvols | 8 | §4.14 |
| 16 | Visdata | variable | §4.15 |

**2.2** Note that this is **not** the version 38 lump order: v46 has 17 lumps
where v38 has 19, and the identities at a given index differ. A reader must
dispatch on the version before interpreting the directory
(cf. [SPEC-BSP38](SPEC-BSP38.md) §2.1).

### 3. Coordinate system and units

**3.1** The world is right-handed with **+Z up**, as in
[SPEC-BSP38](SPEC-BSP38.md) §3.1.

**3.2** Distances are in the same Quake units as
[SPEC-BSP38](SPEC-BSP38.md) §3.2.

**3.3** Entity angles follow the same (pitch, yaw, roll) convention as
[SPEC-BSP38](SPEC-BSP38.md) §3.3.

### 4. Fixed-size lump record layouts

Fields are listed in file order.

#### 4.1 Textures (lump 1) — 72 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 64 | 64 bytes | name, §6.1 |
| 64 | 4 | int32 | surface flags, §6.2 |
| 68 | 4 | int32 | contents flags, §6.2 |

#### 4.2 Planes (lump 2) — 16 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | normal (x, y, z) |
| 12 | 4 | float32 | distance from the origin along the normal |

**4.2.1** Unlike v38 ([SPEC-BSP38](SPEC-BSP38.md) §4.1) there is no
axis-classification field, so the record is 16 bytes rather than 20.

#### 4.3 Nodes (lump 3) — 36 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index into the planes lump |
| 4 | 8 | 2 × int32 | children: front, back |
| 12 | 12 | 3 × int32 | bounding-box minimum |
| 24 | 12 | 3 × int32 | bounding-box maximum |

**4.3.1** A non-negative child reference indexes the nodes lump; a negative one
denotes leaf `−(reference) − 1`. Bounding boxes are **int32** here, where v38
uses int16.

#### 4.4 Leafs (lump 4) — 48 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | visibility cluster index (−1 = in no cluster) |
| 4 | 4 | int32 | area index |
| 8 | 12 | 3 × int32 | bounding-box minimum |
| 20 | 12 | 3 × int32 | bounding-box maximum |
| 32 | 4 | int32 | index of the first leafface entry |
| 36 | 4 | int32 | number of leafface entries |
| 40 | 4 | int32 | index of the first leafbrush entry |
| 44 | 4 | int32 | number of leafbrush entries |

**4.4.1** There is no contents field on a v46 leaf; contents live on brushes
(§4.7) and on the texture record (§4.1).

#### 4.5 Leaffaces (lump 5) and Leafbrushes (lump 6) — 4 bytes each

**4.5.1** Arrays of int32 indices into the faces lump and the brushes lump
respectively. (In v38 both are uint16.)

#### 4.6 Models (lump 7) — 40 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | bounding-box minimum |
| 12 | 12 | 3 × float32 | bounding-box maximum |
| 24 | 4 | int32 | index of the first face |
| 28 | 4 | int32 | number of consecutive faces |
| 32 | 4 | int32 | index of the first brush |
| 36 | 4 | int32 | number of consecutive brushes |

**4.6.1** Model index 0 is the world; indices 1 and above are brush models,
referenced from entities by the `"*N"` convention of
[SPEC-BSP38](SPEC-BSP38.md) §10.5. There is no origin field, unlike v38.

#### 4.7 Brushes (lump 8) — 12 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index of the first brushside |
| 4 | 4 | int32 | number of brushsides |
| 8 | 4 | int32 | index into the textures lump |

**4.7.1** A brush's contents come from the referenced texture record's contents
field (§4.1), not from a field of its own.

#### 4.8 Brushsides (lump 9) — 8 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index into the planes lump |
| 4 | 4 | int32 | index into the textures lump |

#### 4.9 Vertexes (lump 10) — 44 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | position (x, y, z) |
| 12 | 8 | 2 × float32 | surface texture coordinates (s, t) |
| 20 | 8 | 2 × float32 | lightmap texture coordinates (s, t) |
| 28 | 12 | 3 × float32 | normal (x, y, z) |
| 40 | 4 | 4 × uint8 | colour (r, g, b, a) |

**4.9.1** This is the fundamental difference from v38: v46 stores texture
coordinates, lightmap coordinates and normals **per vertex**, so nothing has to
be derived from projection axes as in [SPEC-BSP38](SPEC-BSP38.md) §6.1 and §7.2.

**4.9.2** The surface coordinates are **normalised** (0..1 spans the texture
once) and wrap by repetition, so values outside [0, 1) are normal.

**4.9.3** The lightmap coordinates are normalised within the face's own block of
the 128 × 128 lightmap image selected by the face's lightmap index (§4.12).

#### 4.10 Meshverts (lump 11) — 4 bytes

**4.10.1** An array of int32 values. Each is an offset **relative to a face's
first vertex** (§4.12), not an absolute vertex index: the absolute index is the
face's first-vertex index plus the meshvert value.

#### 4.11 Effects (lump 12) — 72 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 64 | 64 bytes | effect shader name |
| 64 | 4 | int32 | index into the brushes lump |
| 68 | 4 | int32 | unused |

**4.11.1** A renderer that does not implement fog volumes may ignore this lump
entirely; a face's effect index of −1 means "no effect".

#### 4.12 Faces (lump 13) — 104 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index into the textures lump |
| 4 | 4 | int32 | index into the effects lump, or −1 |
| 8 | 4 | int32 | face type, §4.12.1 |
| 12 | 4 | int32 | index of the face's first vertex |
| 16 | 4 | int32 | number of vertices |
| 20 | 4 | int32 | index of the face's first meshvert |
| 24 | 4 | int32 | number of meshverts |
| 28 | 4 | int32 | lightmap index, or −1 for none |
| 32 | 8 | 2 × int32 | lightmap corner within the lightmap image |
| 40 | 8 | 2 × int32 | lightmap block size |
| 48 | 12 | 3 × float32 | lightmap origin in world space |
| 60 | 24 | 2 × 3 × float32 | lightmap s and t world-space axes |
| 84 | 12 | 3 × float32 | face normal |
| 96 | 8 | 2 × int32 | patch control-point grid size (width, height) |

**4.12.1** The face type enumeration:

| Value | Meaning |
|---|---|
| 1 | polygon |
| 2 | Bezier patch, §6 |
| 3 | mesh (an arbitrary triangle soup) |
| 4 | billboard / sprite |

Types 1 and 3 are drawn identically — as an indexed triangle list built from the
face's meshvert range. Type 2 needs tessellation (§6). Type 4 carries no
polygon geometry and a renderer may skip it.

**4.12.2** A lightmap index of −1, or one outside the lightmaps lump, means the
face has no baked lighting.

#### 4.13 Lightmaps (lump 14) — 49152 bytes

**4.13.1** Each record is a **128 × 128** RGB image, three unsigned bytes per
texel in R, G, B order, stored row-major: 128 × 128 × 3 = 49152 bytes. There is
no header and no padding.

**4.13.2** Unlike v38 ([SPEC-BSP38](SPEC-BSP38.md) §7.2) the blocks are of
fixed, uniform size and a face addresses one whole image by index, so no luxel
grid has to be derived.

#### 4.14 Lightvols (lump 15) — 8 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 3 | 3 × uint8 | ambient colour |
| 3 | 3 | 3 × uint8 | directional colour |
| 6 | 2 | 2 × uint8 | direction, as (phi, theta) angle bytes |

**4.14.1** A grid of samples used to light moving models. A renderer that lights
only world surfaces may ignore this lump.

**4.14.2** The lump records samples and nothing else — no origin, no
dimensions — so where the samples are has to be derived from the map. The
spacing is 64 × 64 × 128 units unless the `worldspawn` entity (§5) carries a
`gridsize` key, which gives three numbers replacing it. The samples sit on the
lattice of points whose coordinates are whole multiples of the spacing and
which lie inside model 0's bounding box (§4.7), so along each axis *i*:

```
first[i] = ceil(mins[i] / spacing[i])
last[i]  = floor(maxs[i] / spacing[i])
count[i] = last[i] - first[i] + 1
origin[i] = first[i] * spacing[i]
```

**4.14.3** The samples are stored with x varying fastest, then y, then z:
sample (x, y, z) is record `x + count[0] * (y + count[1] * z)`.

**4.14.4** §4.14.2 and §4.14.3 were derived from the file bytes rather than from
any description of them, and hold for all seventeen maps in this workspace's
sample content. §4.14.2 predicts each lump's record count exactly — the count is
`count[0] × count[1] × count[2]` and the lump length is eight times that, which
no other placement satisfies. §4.14.3 was settled by comparing neighbouring
samples: a grid samples a light field 64 units apart, so the reading that is
right is the one whose neighbours agree, and reading x fastest gives about half
the sample-to-sample variation that reading z fastest does, in every map.

**4.14.5** The direction bytes are angles in units of 2π/255 radians: the first
is measured from +Z and the second about +Z from +X, giving

```
towards = (sin(phi) cos(theta), sin(phi) sin(theta), cos(phi))
```

as a unit vector pointing **towards** the light. Also derived from the bytes:
of the four readings the two bytes admit, this is the one whose vectors agree
with the direction the sampled brightness increases in, and the only one that
also points upwards on average — which is where a map lit by a sky and by
ceiling lights is lit from.

#### 4.15 Visdata (lump 16) — variable

**4.15.1** Two int32 values — the number of cluster vectors and the size of each
in bytes — followed by that many bytes of bit vectors, one bit per cluster. A
renderer that draws the whole map or does its own culling does not need it.

**4.15.2** The vectors are indexed by cluster and so is each bit within one:
vector *n* is the one belonging to cluster *n*, and bit *m* of it stands for
cluster *m*. Bit *m* lies in byte `m >> 3` of the vector, at mask `1 << (m & 7)`.
A cluster of −1 (§4.4) is not in the set at all and no vector belongs to it.

The vectors are stored flat, at `sz_vecs` bytes each, with no run-length or other
encoding — the lump's length is exactly `8 + n_vecs × sz_vecs`, which is what
lets it be indexed arithmetically rather than scanned. This follows from §4.15.1
and §4.4 and is recorded here because those two state the layout without saying
how it is addressed; no other source was consulted for it, and what the bits are
*used for* remains out of scope (§E.2).

### 5. The entity lump

**5.1** Lump 0 is a plain-text block with the same syntax as v38: brace-delimited
blocks of double-quoted key/value pairs. See [SPEC-BSP38](SPEC-BSP38.md) §10,
which applies unchanged, including the `"*N"` brush-model convention of §10.5.

### 6. Texture names, flags and Bezier patches

**6.1** The texture name field is 64 bytes holding a NUL-terminated,
NUL-padded string. It is a forward-slash path relative to the content archive's
root, **without** a file extension — for example `textures/base_wall/c_met5_2`.
The same name is also the name of a material in a `.shader` script.

**6.2** The surface-flags and contents words of a texture record (§4.1) are
**not** the version 38 words: the two families share the field position and the
low bits, and diverge above them. This document deliberately records **no** bit
values for v46, and the implementation built from it interprets neither word;
Quake 3 surface behaviour is taken from the `.shader` material scripts and from
the texture name instead, both of which are content, not engine data. See
"Excluded" E.1.

**6.3** A **Bezier patch** face (type 2) has a control-point grid whose
dimensions are the face's size field (§4.12): `width × height` control points,
read consecutively from the vertexes lump starting at the face's first vertex,
in row-major order with width as the fast axis. Both dimensions are odd and at
least 3.

**6.4** The grid is a mesh of biquadratic (order-3) Bezier surface patches laid
side by side: control points `[2i .. 2i+2] × [2j .. 2j+2]` form one patch, so a
`(2m+1) × (2n+1)` grid is `m × n` patches sharing edge control points.

**6.5** A biquadratic Bezier patch is evaluated with the quadratic Bernstein
basis. For a parameter *u* in [0, 1] the three basis weights are

```
b0 = (1 − u)²      b1 = 2·u·(1 − u)      b2 = u²
```

and the surface point at (*u*, *v*) is the double sum of the nine control points
weighted by `b_i(u) · b_j(v)`. The same weighting applies to every per-vertex
attribute — position, normal, and both texture-coordinate sets — since they are
all interpolated over the same parameter domain.

**6.6** The number of subdivisions per patch is a renderer's own choice; it
affects only smoothness.

### 7. Where a map's assets live

**7.1** A Quake 3 map ships in a `.pk3` file, which is an ordinary ZIP archive.
Paths inside it are the paths a texture name (§6.1) is resolved against.

**7.2** Conventionally `maps/<name>.bsp` holds the map, `scripts/*.shader` the
material scripts, `textures/...` the images and `levelshots/<name>.jpg` a
preview image.

**7.3** A texture name carries no extension; the file is found by trying the
image extensions the renderer supports.

## Excluded

**E.1 — Surface-flag and contents-flag bit values for v46.** Deliberately not
recorded and deliberately not implemented. The public reference used here states
that the fields exist but not what their bits mean, and the alternative sources
for those values are either engine source (which was not opened) or documents
whose licence would need checking. They are not needed: material behaviour comes
from the `.shader` scripts, which are content and are documented publicly in the
Quake III Arena shader manual. If a future feature genuinely needs a v46 flag
value, it must come from a licence-clean source and be recorded here first — and
it must **not** be taken from [SPEC-BSP38](SPEC-BSP38.md) §8, which describes a
different family's bit assignments in the same field.

**E.2 — The visibility bit-vector decompression.** Not needed by a renderer that
draws the whole map (§4.15.1), and out of scope here for the same reason as
[SPEC-BSP38](SPEC-BSP38.md) E.2.

**E.3 — The `.shader` material language.** Documented publicly in the Quake III
Arena shader manual and treated as a separate concern; §7 records only where the
files live.

**E.4 — What a renderer does with a sampled lightvol.** §4.14 records the
record layout, where the samples are and how to read the two angle bytes —
everything needed to get the same values out of the file that wrote them. How
those values are then turned into shading is renderer design and is not
recorded here.
