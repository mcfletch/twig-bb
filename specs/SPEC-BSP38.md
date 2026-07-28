# SPEC-BSP38: Reading `IBSP` version 38 map files (Quake 2 / Alien Arena)

| | |
|---|---|
| Source consulted | Alien Arena — https://github.com/alienarena/alienarena.git |
| Licence of source | GPLv2 (`unix_dist/GPLv2`; `docs/license.txt` confirms GPLv2-or-later for source, with a separately-licensed BSD SHA-2 component that is unrelated to this area) |
| Version / commit | `a1aaf7fed8f5e2825c94406cbf2071e7ed3b6542`, Mon Jun 15 2026 |
| Files consulted | `source/qcommon/qfiles.h`, `source/game/q_shared.h`, `source/qcommon/cmodel.c`, `source/ref_gl/r_model.c`, `source/ref_gl/r_light.c`, `source/ref_gl/r_surf.c`, `source/ref_gl/r_shadowmaps.c`, `source/ref_gl/r_warp.c`, `docs/` (checked, contains no format material) |
| Non-copyleft sources checked first | **Yes — see §0.** Independent public format documentation was consulted first and supplied the great majority of the layout facts below. The GPL tree was consulted only for the residue listed in §0.3. |
| Reader | Claude (Opus 5) sub-agent, acting solely as Reader; wrote no project code |
| Date | 2026-07-25 |
| **Clean-room status** | **Clean.** This spec is the sanctioned channel: the Reader wrote no project code, and the implementation built from it is written by someone who has not read the copyleft source. Facts below are the only thing that crossed the wall. |

## Scope

What a third party needs in order to **read** an `IBSP` version 38 map file well
enough to (a) render its world and brush-model geometry with textures and baked
lightmaps, and (b) import its collision volumes and entity placements.

Covered: container header and lump directory; the binary record layout of every
lump a renderer or physics importer touches; surface flags (including Alien
Arena's additions beyond stock Quake 2) and contents flags; entity-lump text
syntax and the brush-model reference convention; lightmap addressing and luxel
grid derivation; texture-coordinate derivation; units and axis orientation.

Not covered: writing/compiling BSP files, the visibility decompression
algorithm, the area-portal gameplay mechanism, and Alien Arena's separate
high-detail lightmap sidecar file (see "Excluded").

## 0. Provenance of the facts (Rule 0 record)

**0.1** Each fact below is tagged with where it came from:

- **[PUB]** — confirmed against widely published, independent format
  documentation for the Quake 2 BSP format. This format has been publicly
  documented for decades in format references that are not derived from, and do
  not carry the licence of, the Alien Arena tree.
- **[SRC]** — genuinely required reading the GPLv2 tree, because the fact is
  specific to Alien Arena and is not present in public Quake 2 documentation.
- **[BOTH]** — present in public documentation and additionally checked against
  the tree for agreement.

**0.2** Non-copyleft sources checked, in the order of preference set by
CLEAN-ROOM.md Rule 0:

1. Published format references for Quake 2 BSP v38 — the long-circulated
   "unofficial" Quake 2 BSP format reference and its many independent
   restatements, plus permissively-licensed reimplementation documentation.
   These supplied: the magic and version, the 19-entry lump directory and its
   index order, the record layout of every fixed-size lump, the visibility
   lump's shape, the plane-type enumeration, the coordinate convention, the
   texture-coordinate projection, the stock Quake 2 `SURF_*` and `CONTENTS_*`
   values, the entity-lump text syntax, the `"*N"` brush-model convention, and
   the 16-unit luxel grid.
2. The Alien Arena tree's own `docs/` directory was checked on the chance that
   it was documentation rather than code. It contains a developer reference and
   licence text only; it says nothing about the BSP format, so it was of no use.
3. Sample map bytes were not needed, because 1 was sufficient for layout.

**0.3** Facts that genuinely required the GPLv2 source — everything tagged
**[SRC]** — reduce to exactly these:

- Alien Arena's five surface-flag additions beyond stock Quake 2 and their
  numeric values (§8.2), and what a renderer does with each (§8.3).
- Confirmation that Alien Arena introduces **no** change to the container,
  lump directory, or any record layout relative to stock Quake 2 v38 (§1.7) —
  a negative fact that could only be established by looking.
- The declared upper design bounds (§11).
- Alien Arena's texture-asset naming convention for reading a face's material
  (§6.5).

## Facts

### 1. Container

**1.1** [PUB] A file begins with a 4-byte identifier whose bytes are the ASCII
characters `I`, `B`, `S`, `P` in that order at file offsets 0..3. Read as a
little-endian 32-bit integer this is `0x50534249`.

**1.2** [PUB] Bytes 4..7 hold a 32-bit signed integer version number. The
version described by this spec is **38**. A reader must reject any other value
rather than guess.

**1.3** [BOTH] All multi-byte scalars everywhere in the file are **little-endian**.
Floating-point values are IEEE-754 binary32.

**1.4** [PUB] Bytes 8 onward hold the lump directory: an array of fixed 8-byte
entries, each being two 32-bit signed integers in this order:

| Offset in entry | Size | Type | Meaning |
|---|---|---|---|
| 0 | 4 | int32 | byte offset of the lump's data from the **start of the file** |
| 4 | 4 | int32 | length of the lump's data in bytes |

**1.5** [PUB] The directory has exactly **19** entries. The header is therefore
8 + 19 × 8 = **160 bytes**, and lump data begins at or after offset 160.

**1.6** [PUB] A lump of length 0 is legal and means the map contains no records
of that kind. For a lump made of fixed-size records, the record count is the
lump length divided by the record size; a length that is not an exact multiple
of the record size indicates a malformed file.

**1.7** [SRC] Alien Arena reads and writes this container unchanged from stock
Quake 2: same identifier, same version number 38, same 19-lump directory, same
record layouts. Its only format extensions in this area are additional bits in
the surface-flags word (§8.2) and a separate sidecar file that is not part of
the BSP (see "Excluded"). A reader written to stock Quake 2 v38 will read Alien
Arena maps correctly apart from the extra flag bits.

**1.8** [PUB] Lumps are addressed only through the directory. A reader must not
assume lumps appear in the file in directory order, nor that they are
contiguous, nor that they are free of padding between them.

### 2. Lump directory indices

**2.1** [BOTH] Directory entry index → lump identity. These indices are part of
the format; they are how a lump is named.

| Index | Lump | Record size (bytes) | Layout |
|---|---|---|---|
| 0 | Entities | variable (text) | §10 |
| 1 | Planes | 20 | §4.1 |
| 2 | Vertexes | 12 | §4.2 |
| 3 | Visibility | variable | §4.3 |
| 4 | Nodes | 28 | §4.4 |
| 5 | Texinfo | 76 | §4.5 |
| 6 | Faces | 20 | §4.6 |
| 7 | Lighting | variable (bytes) | §7 |
| 8 | Leafs | 28 | §4.7 |
| 9 | Leaffaces | 2 | §4.8 |
| 10 | Leafbrushes | 2 | §4.9 |
| 11 | Edges | 4 | §4.10 |
| 12 | Surfedges | 4 | §4.11 |
| 13 | Models | 48 | §4.12 |
| 14 | Brushes | 12 | §4.13 |
| 15 | Brushsides | 4 | §4.14 |
| 16 | Pop | variable | §4.15 |
| 17 | Areas | 8 | §4.16 |
| 18 | Areaportals | 8 | §4.17 |

**2.2** [PUB] The names in the table above are the conventional names for these
lumps and are the vocabulary a third party must use to interoperate; they are
not required to appear anywhere in the file.

### 3. Coordinate system and units

**3.1** [PUB] The world is right-handed with **+Z up**. +X and +Y span the
horizontal plane. This is the Quake family convention, not the Y-up convention
used by most modelling and glTF pipelines; an importer targeting a Y-up engine
must rotate accordingly.

**3.2** [PUB] Distances are in **Quake units**. One unit is approximately one
inch (the standing player character is 56 units tall and occupies a 32×32-unit
footprint), so a scale factor of roughly 0.0254 converts a map to metres.

**3.3** [PUB] Angles in entity values are in degrees. The three-component
angle convention used by entity keys is (pitch, yaw, roll), with yaw measured
counter-clockwise about +Z; note that this ordering places pitch first, unlike
the (x, y, z) rotation ordering common elsewhere.

### 4. Fixed-size lump record layouts

Each table below lists fields in file order. "Offset" is the byte offset within
one record. Field names are descriptive names chosen for this spec.

#### 4.1 Planes (lump 1) — 20 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | normal vector (x, y, z) |
| 12 | 4 | float32 | distance along the normal from the origin |
| 16 | 4 | int32 | axis-classification code, §4.1.2 |

**4.1.1** [PUB] The plane is the set of points **p** satisfying
`dot(normal, p) = distance`. The normal is unit length. A point is in front of
the plane when `dot(normal, p) − distance` is positive.

**4.1.2** [PUB] The classification code takes these values: 0 = normal is
aligned with the +X axis; 1 = +Y; 2 = +Z; 3 = non-axial, closest to X;
4 = non-axial, closest to Y; 5 = non-axial, closest to Z. It is redundant —
a reader may recompute it from the normal and may ignore it entirely.

**4.1.3** [PUB] Planes are stored so that a plane and its opposite occupy
adjacent slots: for any even index *i*, plane *i* and plane *i*+1 are the same
surface with opposed normals. A reader need not rely on this.

#### 4.2 Vertexes (lump 2) — 12 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | position (x, y, z) in world units |

#### 4.3 Visibility (lump 3) — variable

**4.3.1** [PUB] The lump begins with a 32-bit signed integer cluster count,
followed by that many pairs of 32-bit signed integers. Each pair holds two byte
offsets, both measured **from the start of the visibility lump**: the first is
the potentially-visible set for that cluster, the second is the
potentially-hearable set. Pair element index 0 is PVS and index 1 is PHS.

**4.3.2** [PUB] Each set is a run-length-compressed bit vector with one bit per
cluster. Decompression is not specified here — see "Excluded" §E.2. A renderer
that draws the whole map, or that does its own culling, does not need this lump
at all.

#### 4.4 Nodes (lump 4) — 28 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index into the planes lump — the splitting plane |
| 4 | 4 | int32 | front child reference, §4.4.1 |
| 8 | 4 | int32 | back child reference, §4.4.1 |
| 12 | 6 | 3 × int16 | bounding-box minimum (x, y, z) |
| 18 | 6 | 3 × int16 | bounding-box maximum (x, y, z) |
| 24 | 2 | uint16 | index of the first face in the faces lump |
| 26 | 2 | uint16 | number of consecutive faces |

**4.4.1** [PUB] A child reference that is zero or positive is an index into the
nodes lump. A negative reference denotes a leaf: the leaf index is
`−(reference) − 1`. Child index 0 is the front (positive) side of the plane and
child index 1 is the back side.

**4.4.2** [PUB] The bounding box is in integer world units and is a
conservative bound used for culling.

**4.4.3** [PUB] The face range on a node covers faces on both sides of the
splitting plane.

#### 4.5 Texinfo (lump 5) — 76 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | S projection axis (x, y, z) |
| 12 | 4 | float32 | S offset |
| 16 | 12 | 3 × float32 | T projection axis (x, y, z) |
| 28 | 4 | float32 | T offset |
| 32 | 4 | int32 | surface flags — see §8 |
| 36 | 4 | int32 | auxiliary value, §4.5.2 |
| 40 | 32 | 32 bytes | texture name, §6.4 |
| 72 | 4 | int32 | next texinfo in the animation cycle, §4.5.3 |

**4.5.1** [PUB] The two axis/offset groups are stored as four consecutive
float32 each — three axis components then the offset — with the S group first.

**4.5.2** [PUB] The auxiliary value carries the emitted light strength when the
surface flags include `SURF_LIGHT` (§8.1). For surfaces without that flag it
carries no meaning defined by this spec and a reader may ignore it.

**4.5.3** [PUB] A value of −1 terminates the animation cycle. Otherwise the
value is the index of the next texinfo record in a cyclic chain of animation
frames, all of which share geometry mapping but name different textures.

#### 4.6 Faces (lump 6) — 20 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 2 | uint16 | index into the planes lump |
| 2 | 2 | int16 | plane side, §4.6.1 |
| 4 | 4 | int32 | index of the first entry in the surfedges lump |
| 8 | 2 | int16 | number of consecutive surfedge entries |
| 10 | 2 | int16 | index into the texinfo lump |
| 12 | 4 | 4 × uint8 | lightmap style bytes, §7.5 |
| 16 | 4 | int32 | byte offset into the lighting lump, §7.4 |

**4.6.1** [PUB] A plane side of 0 means the face's outward normal equals the
referenced plane's normal; any non-zero value means the face's outward normal is
the negation of the plane's normal.

**4.6.2** [PUB] The first-surfedge field is 32 bits specifically so that a map
may contain more than 65535 surfedge entries.

#### 4.7 Leafs (lump 8) — 28 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | contents flags — the bitwise OR of the contents of every brush in this leaf; see §9 |
| 4 | 2 | int16 | visibility cluster index, §4.7.1 |
| 6 | 2 | int16 | area index |
| 8 | 6 | 3 × int16 | bounding-box minimum (x, y, z) |
| 14 | 6 | 3 × int16 | bounding-box maximum (x, y, z) |
| 20 | 2 | uint16 | index of the first entry in the leaffaces lump |
| 22 | 2 | uint16 | number of consecutive leafface entries |
| 24 | 2 | uint16 | index of the first entry in the leafbrushes lump |
| 26 | 2 | uint16 | number of consecutive leafbrush entries |

**4.7.1** [PUB] A cluster index of −1 means the leaf belongs to no visibility
cluster and is never considered visible through the PVS; solid leaves are the
usual case. Otherwise the value indexes the visibility lump's cluster table.

**4.7.2** [PUB] Faces reached through a leaf's leafface range are the faces to
draw when that leaf is visible. Brushes reached through the leafbrush range are
the collision volumes occupying the leaf.

#### 4.8 Leaffaces (lump 9) — 2 bytes

**4.8.1** [PUB] An array of uint16 indices into the faces lump.

#### 4.9 Leafbrushes (lump 10) — 2 bytes

**4.9.1** [PUB] An array of uint16 indices into the brushes lump.

#### 4.10 Edges (lump 11) — 4 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 2 | uint16 | index into the vertexes lump — first endpoint |
| 2 | 2 | uint16 | index into the vertexes lump — second endpoint |

**4.10.1** [PUB] Edge record 0 is never referenced by a face, because the sign
of a surfedge entry carries direction and zero has no sign (§4.11.1).

#### 4.11 Surfedges (lump 12) — 4 bytes

**4.11.1** [PUB] An array of **signed** 32-bit integers. The magnitude is an
index into the edges lump. A positive entry means the edge is traversed from its
first endpoint to its second; a negative entry means the edge is traversed from
its second endpoint to its first. This is what allows a face's edges to be
walked as a consistently-wound ring.

#### 4.12 Models (lump 13) — 48 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 12 | 3 × float32 | bounding-box minimum (x, y, z) |
| 12 | 12 | 3 × float32 | bounding-box maximum (x, y, z) |
| 24 | 12 | 3 × float32 | origin (x, y, z) |
| 36 | 4 | int32 | index of this model's root node in the nodes lump |
| 40 | 4 | int32 | index of the first face in the faces lump |
| 44 | 4 | int32 | number of consecutive faces |

**4.12.1** [PUB] Model index 0 is the world. Model indices 1 and above are
**brush models** (also called inline or sub-models): movable or scriptable
pieces of world geometry such as doors, lifts and rotating machinery, referenced
from entities by the convention in §10.5.

**4.12.2** [PUB] A brush model's faces may be drawn directly as the contiguous
face range given here, without walking the BSP tree. The root-node reference
exists for collision queries against the model.

**4.12.3** [PUB] The origin is a reference point used for sound emission and
for rotation of rotating brush models; brush-model geometry is stored in world
coordinates, so the origin is generally not a translation that has already been
applied to the vertices.

#### 4.13 Brushes (lump 14) — 12 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | index of the first entry in the brushsides lump |
| 4 | 4 | int32 | number of consecutive brushside entries |
| 8 | 4 | int32 | contents flags — see §9 |

**4.13.1** [PUB] A brush is a convex volume defined as the intersection of the
negative half-spaces of its sides' planes. This is the representation a physics
importer wants; the face/edge/vertex data is a rendering representation of the
same solids and is not a closed volume description.

#### 4.14 Brushsides (lump 15) — 4 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 2 | uint16 | index into the planes lump; the plane faces **out of** the brush |
| 2 | 2 | int16 | index into the texinfo lump, or −1 for no texinfo |

#### 4.15 Pop (lump 16)

**4.15.1** [PUB] Reserved; unused in practice and normally zero length. A
reader should skip it.

#### 4.16 Areas (lump 17) — 8 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | number of area portals belonging to this area |
| 4 | 4 | int32 | index of the first entry in the areaportals lump |

#### 4.17 Areaportals (lump 18) — 8 bytes

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | int32 | portal number, matching an entity's portal identifier |
| 4 | 4 | int32 | index of the area on the other side |

**4.17.1** [PUB] Areas and area portals implement run-time occlusion that can
close off whole regions (a closed door sealing two areas). A pure importer or a
renderer that does no server-side visibility work can ignore both lumps.

### 5. Reconstructing a face's polygon

**5.1** [PUB] For a face, walk its surfedge entries from its first-surfedge
index for its edge count. Each entry yields an ordered vertex pair per §4.11.1;
taking the **first** vertex of each successive directed edge produces the face's
vertex ring in order, with one vertex per surfedge entry.

**5.2** [PUB] The ring is a simple convex polygon lying in the face's plane. It
can be triangulated as a fan from any of its vertices.

**5.3** [PUB] The face's outward normal is the plane normal from §4.1, negated
when the plane-side field is non-zero (§4.6.1). Vertex winding as produced by
§5.1 is consistent across the file, so a renderer need only determine the
handedness convention once and, if it is the wrong way round for its API,
reverse it uniformly.

**5.4** [PUB] The file stores no per-vertex normals and no per-vertex tangent
frames. A renderer needing smooth normals or tangents must compute them.

### 6. Texture coordinates

**6.1** [PUB] For a world-space point **p** on a face, with the face's texinfo
record (§4.5), the texture coordinates in **texel units** are:

```
S = p·(S axis) + (S offset)
T = p·(T axis) + (T offset)
```

where `·` is the ordinary 3-component dot product. Both are affine projections
of world position; no perspective term and no per-vertex data are involved.

**6.2** [PUB] These are absolute texel coordinates, not normalised. To obtain
normalised coordinates for a texture of dimensions *w* × *h*, divide S by *w*
and T by *h*. Texture wrapping is repeat, so values outside [0,1) are normal.

**6.3** [PUB] The lengths of the S and T axes encode the texture scale: a longer
axis vector means the texture repeats more often per world unit. The axes are
not required to be orthogonal or unit length, so a texture may be sheared.

**6.4** [PUB] The texture name field is 32 bytes holding a NUL-terminated
string, NUL-padded if shorter; if all 32 bytes are non-NUL the string is exactly
32 characters. It is a path with forward slashes, relative to a texture root,
**without** a file extension. Under stock Quake 2 the asset is found by
appending `.wal` to `textures/` + this name.

**6.5** [SRC] Alien Arena resolves the same name to a richer material. The base
colour map is looked up under `textures/` + name with an
implementation-dependent search over supported image extensions, `.wal` being
the stock one. Two companion maps are looked up by suffixing the same path:
`_nm.tga` supplies a tangent-space normal map and `_hm.tga` supplies a height
map. Both are optional; when a companion is absent the base colour map stands in
and the corresponding effect is off. A third-party reader wanting Alien Arena's
material appearance should follow the same naming; one wanting only stock
behaviour may ignore §6.5 entirely.

### 7. Lightmaps

**7.1** [PUB] The lighting lump (lump 7) is an undifferentiated byte array of
baked light samples. Samples are **24-bit RGB, three bytes per luxel, in R, G, B
order**, with no per-block header, no padding and no alignment guarantee. It is
addressed only through byte offsets stored in face records.

**7.2** [BOTH] **Units per luxel: 16 world units in each of S and T.** The luxel
grid for a face is derived from the face's texture-space extent as follows.
Project every vertex of the face by §6.1 to get S and T values. Let *Smin*,
*Smax*, *Tmin*, *Tmax* be the minimum and maximum over those vertices. Then, for
each of the two axes independently:

```
grid_min   = floor(min / 16)            (integer, in luxel steps)
grid_max   = ceil (max / 16)            (integer, in luxel steps)
texture_min = grid_min × 16             (world/texel units)
extent      = (grid_max − grid_min) × 16
```

and the luxel grid dimensions are

```
width  = extent_S / 16 + 1 = grid_max_S − grid_min_S + 1
height = extent_T / 16 + 1 = grid_max_T − grid_min_T + 1
```

Note the `+1`: the grid samples the **corners** of the 16-unit cells, so a face
one cell wide has two luxels across.

**7.3** [PUB] One lightmap block for a face is therefore `width × height × 3`
bytes, stored row-major: consecutive luxels along S, then successive rows along
T.

**7.4** [BOTH] The face's lighting offset (§4.6) is a **byte** offset from the
start of the lighting lump to the face's first block. A negative offset, or one
that falls outside the lighting lump, means the face has no baked lighting; a
reader must treat both cases as "no lightmap" rather than trusting the value.

**7.5** [BOTH] The four style bytes in a face record select light styles. Slots
are filled from index 0 upward, and the value **255** marks an unused slot and
terminates the list — a reader stops at the first 255. The number of blocks
stored for the face equals the number of style slots before that terminator, and
those blocks are stored **consecutively** starting at the face's lighting
offset, each `width × height × 3` bytes. Total bytes for the face are therefore
`styles_used × width × height × 3`.

**7.6** [PUB] Style value **0** denotes the always-on, constant light
contribution. Non-zero style values below 255 identify animated light styles
whose intensity varies over time and is supplied by the engine at run time, not
by the file. A reader that wants only static lighting can use the style-0 block
alone; a reader that wants the fully-lit look should sum all stored blocks with
each block scaled by its style's current intensity.

**7.7** [PUB] To sample a face's lightmap at a world point **p**, compute S and
T by §6.1, then the position within the face's own luxel grid is

```
luxel_S = (S − texture_min_S) / 16
luxel_T = (T − texture_min_T) / 16
```

which lies in [0, width−1] × [0, height−1]. Sampling at luxel centres for
bilinear filtering means adding 0.5 to each and dividing by *width* and *height*
respectively, i.e. normalised coordinates
`((S − texture_min_S)/16 + 0.5) / width` and likewise for T. Renderers
conventionally pack many face lightmaps into a shared atlas texture, in which
case the atlas offset of the face's block is added before normalising by the
atlas dimensions instead.

**7.8** [BOTH] Faces whose texinfo carries `SURF_WARP` have no meaningful
texture-space extent, because their surface is deformed at run time; the extent
derivation of §7.2 does not apply to them and they carry no usable lightmap.
Faces flagged `SURF_SKY` or `SURF_NODRAW` likewise carry no lightmap.

### 8. Surface flags

**8.1** [PUB] Stock Quake 2 values, carried unchanged by Alien Arena. The field
is the surface-flags word of a texinfo record (§4.5); bits combine freely.

| Name | Value | Meaning to a reader/renderer |
|---|---|---|
| `SURF_LIGHT` | 0x00000001 | The surface emits light during the compile bake. Its strength is the texinfo auxiliary value (§4.5.2). At run time the surface is drawn normally; a real-time renderer may use it to place an emissive term. |
| `SURF_SLICK` | 0x00000002 | Low-friction surface. Affects physics only; no rendering effect. |
| `SURF_SKY` | 0x00000004 | Not drawn as ordinary geometry. The surface is a hole through which the sky is shown; a renderer substitutes its skybox. Contributes no lightmap. |
| `SURF_WARP` | 0x00000008 | Surface is animated with a turbulent, water-like distortion of its texture coordinates. Such faces are conventionally subdivided into a finer mesh so the distortion is smooth. See §7.8. |
| `SURF_TRANS33` | 0x00000010 | Drawn translucent at roughly one-third opacity. |
| `SURF_TRANS66` | 0x00000020 | Drawn translucent at roughly two-thirds opacity. |
| `SURF_FLOWING` | 0x00000040 | Texture coordinates scroll continuously over time, giving the appearance of flow along the surface. |
| `SURF_NODRAW` | 0x00000080 | Not rendered at all; the surface exists for compilation and collision purposes only. Its texture need not be loaded. |

**8.1.1** [PUB] Bits 0x00000100 and 0x00000200 are used by map-compilation
tools as hint and skip markers and do not survive into a compiled map's faces in
any renderer-relevant way; a reader may ignore them.

**8.2** [SRC] **Alien Arena additions beyond stock Quake 2.** These five bits
are Alien Arena's own extension of the same word. A stock Quake 2 reader ignores
them harmlessly.

| Name | Value | |
|---|---|---|
| `SURF_BLOOD` | 0x00000400 | see §8.3.1 |
| `SURF_WATER` | 0x00000800 | see §8.3.1 |
| `SURF_SHINY` | 0x00001000 | see §8.3.1 |
| `SURF_UNDERWATER` | 0x00002000 | see §8.3.2 |
| `SURF_NOSHADOW` | 0x00004000 | see §8.3.3 |

**8.3** [SRC] What the Alien Arena additions mean to a renderer:

**8.3.1** `SURF_BLOOD`, `SURF_WATER` and `SURF_SHINY` are three mutually
alternative "wet surface" material modes, selected in that order of precedence.
Each substitutes a different overlay/reflection treatment on top of the
surface's normal shading: a dripping-blood layer, a dripping-water layer, and a
plain wet-sheen respectively. A renderer that does not implement them should
draw the surface normally; they change appearance only and have no effect on
geometry, lighting data layout or collision.

**8.3.2** `SURF_UNDERWATER` marks a surface that is submerged and should be
drawn with an animated rippling distortion, as seen through water. A map author
may set it explicitly, and Alien Arena additionally sets it automatically at
load time on surfaces it determines to be underwater; a third-party reader is
therefore not obliged to honour the stored bit to look correct, and equally may
find the bit clear on surfaces that nonetheless appear rippled in the original
engine.

**8.3.3** `SURF_NOSHADOW` excludes the surface from shadow-map rendering: it
neither casts nor is written into shadow maps, though it is still drawn.
`SURF_SKY` surfaces are excluded from shadow maps for the same reason. A
renderer without shadow maps ignores this bit.

**8.4** [PUB] A reader must treat unrecognised bits as reserved and preserve or
ignore them rather than rejecting the file.

### 9. Contents flags

**9.1** [PUB] The contents word appears on brushes (§4.13) and, as the OR of all
contained brushes, on leaves (§4.7). Bits combine freely. The low bits denote
*visible* contents — media a viewpoint can be inside — and stronger (lower)
bits take precedence when brushes overlap.

| Name | Value | Meaning |
|---|---|---|
| `CONTENTS_SOLID` | 0x00000001 | Opaque solid matter; blocks all movement and sight. A viewpoint is never legitimately inside it. |
| `CONTENTS_WINDOW` | 0x00000002 | Translucent but non-liquid solid — glass and the like. Blocks movement, does not block sight. |
| `CONTENTS_AUX` | 0x00000004 | Auxiliary visible content; no fixed meaning to a renderer. |
| `CONTENTS_LAVA` | 0x00000008 | Lava volume; a liquid. |
| `CONTENTS_SLIME` | 0x00000010 | Slime volume; a liquid. |
| `CONTENTS_WATER` | 0x00000020 | Water volume; a liquid. |
| `CONTENTS_MIST` | 0x00000040 | Non-solid visible fog/mist volume. This is the **highest visible contents bit**; every bit above it is non-visible and does not displace other brushes. |

**9.2** [PUB] Non-visible contents:

| Name | Value | Meaning |
|---|---|---|
| `CONTENTS_AREAPORTAL` | 0x00008000 | The brush is an area portal — the seal between two areas (§4.17). |
| `CONTENTS_PLAYERCLIP` | 0x00010000 | Invisible volume that blocks players only. |
| `CONTENTS_MONSTERCLIP` | 0x00020000 | Invisible volume that blocks non-player characters only. |
| `CONTENTS_CURRENT_0` | 0x00040000 | Pushes along +X (yaw 0°). |
| `CONTENTS_CURRENT_90` | 0x00080000 | Pushes along +Y (yaw 90°). |
| `CONTENTS_CURRENT_180` | 0x00100000 | Pushes along −X (yaw 180°). |
| `CONTENTS_CURRENT_270` | 0x00200000 | Pushes along −Y (yaw 270°). |
| `CONTENTS_CURRENT_UP` | 0x00400000 | Pushes along +Z. |
| `CONTENTS_CURRENT_DOWN` | 0x00800000 | Pushes along −Z. |
| `CONTENTS_ORIGIN` | 0x01000000 | Marks a brush used only to define an entity's rotation origin at compile time. Such brushes are removed by the compiler and should not appear in a finished map. |
| `CONTENTS_MONSTER` | 0x02000000 | Run-time only: an occupied non-player character volume. Should not appear on a brush in the file. |
| `CONTENTS_DEADMONSTER` | 0x04000000 | Run-time only: a corpse volume. |
| `CONTENTS_DETAIL` | 0x08000000 | Detail brush — geometry excluded from visibility computation. Rendered and collided with normally. |
| `CONTENTS_TRANSLUCENT` | 0x10000000 | Set automatically by the compiler when any of the brush's surfaces is translucent. |
| `CONTENTS_LADDER` | 0x20000000 | Climbable volume. |

**9.3** [PUB] The six current bits may be combined with each other and with any
other contents. Their yaw mapping in §9.2 follows §3.3 (yaw counter-clockwise
about +Z with 0° along +X).

**9.4** [PUB] Useful derived masks a physics importer will want, stated as
unions rather than as named constants: everything that stops a player is
`CONTENTS_SOLID | CONTENTS_PLAYERCLIP | CONTENTS_WINDOW`; every liquid is
`CONTENTS_WATER | CONTENTS_LAVA | CONTENTS_SLIME`; everything sight-blocking is
`CONTENTS_SOLID | CONTENTS_SLIME | CONTENTS_LAVA`.

**9.5** [PUB] A reader must treat unrecognised contents bits as reserved.

### 10. The entity lump

**10.1** [PUB] Lump 0 is a plain-text block, conventionally ASCII and
NUL-terminated, whose length in the directory includes any terminator. It is not
a record array; it is parsed as text.

**10.2** [PUB] The text is a sequence of entity blocks. A block opens with `{`
and closes with `}`. Between them is a sequence of key/value pairs, each written
as two double-quoted strings separated by whitespace, conventionally one pair
per line:

```
{
"classname" "light"
"origin" "128 -64 192"
"light" "300"
}
```

**10.3** [PUB] Both key and value are always double-quoted, and neither may
contain a double-quote character. Whitespace and line breaks between tokens are
insignificant. A key is limited to 32 bytes including its terminator and a value
to 1024 bytes including its terminator. Keys within one entity are conventionally
unique; the parsing convention when a key repeats is to keep the last
occurrence.

**10.4** [PUB] The `classname` key identifies what the entity is and is present
on essentially every entity. Vector-valued keys such as `origin` and `angles`
hold whitespace-separated decimal numbers inside a single quoted value, in x y z
order for positions and per §3.3 for angles. All values are text; a reader
converts them itself, and must tolerate keys it does not recognise.

**10.5** [BOTH] **Brush-model reference convention.** An entity whose geometry
is a brush model carries a `model` key whose value is an asterisk immediately
followed by a decimal integer — for example `"model" "*3"`. That integer is an
index into the models lump (§4.12). The index is always **1 or greater**: index
0 is the world and is never referenced this way. The entity's other keys
(position, movement, targeting) then animate or control that model. This is the
mechanism by which doors, platforms, rotating brushes and triggers are attached
to their geometry.

**10.6** [PUB] A `model` value that does not begin with an asterisk names an
external model asset file rather than a brush model, and is outside the scope of
this spec.

**10.7** [BOTH] The first entity block in the lump is by convention the
`worldspawn` entity, which carries map-wide settings and corresponds to model 0.

**10.8** [PUB] Comments may appear in the entity text using the `//`
line-comment and `/* */` block-comment forms, and a parser should skip them.
They are rare in compiled output.

### 11. Declared upper design bounds

**11.1** [SRC] The following limits are those declared by the Alien Arena
implementation. They are not enforced by the file format itself, but a reader
may use them as sanity checks and a writer must respect them for the map to
load. Several data types are intrinsically limited to 65536 entries by their
16-bit index fields, and are marked (*).

| Quantity | Limit |
|---|---|
| Models | 1024 |
| Brushes | 8192 |
| Entities | 2048 |
| Entity lump text size | 0x40000 bytes (262144) |
| Texinfo records | 8192 |
| Areas | 256 |
| Area portals | 1024 |
| Planes (*) | 65536 |
| Nodes | 65536 |
| Brushsides (*) | 65536 |
| Leafs | 65536 |
| Vertexes (*) | 65536 |
| Faces | 65536 |
| Leaffaces (*) | 65536 |
| Leafbrushes (*) | 65536 |
| Portals | 65536 |
| Edges | 128000 |
| Surfedges | 256000 |
| Lighting lump size | 0x200000 bytes (2097152) |
| Visibility lump size | 0x100000 bytes (1048576) |

**11.2** [SRC] Note that the edge and surfedge limits exceed 65536, which is why
a face's first-surfedge field is 32-bit (§4.6.2) while its edge endpoints are
16-bit vertex indices.

### 12. Reader robustness

**12.1** [PUB] A reader should validate, before dereferencing: that each lump's
offset and length lie inside the file; that fixed-record lump lengths are exact
multiples of the record size; and that every index read from a record lies
within the target lump's record count. Nothing in the format guarantees these,
and malformed or hostile files exist.

**12.2** [PUB] Nothing in the format requires lumps to be laid out in the file
in directory order; a reader must not infer a lump's length from the next lump's
offset (§1.8).

## Excluded

**E.1 — All source code, pseudocode and control-flow description.** Nothing in
this spec describes how the Alien Arena implementation is organised: no function
decomposition, no order of operations, no helper routines, no error-handling
shape, no internal identifiers. Where a fact could only have been phrased as a
walkthrough of code, it was either restated as a standalone mathematical or
structural relationship (as in §7.2) or dropped.

**E.2 — The visibility-lump decompression algorithm.** §4.3 states the lump's
container layout, which is public and factual. The run-length scheme by which a
cluster's bit vector is expanded is deliberately not stated. It is described in
public documentation, but restating it usefully tends toward reproducing an
algorithm with essentially one natural expression, which CLEAN-ROOM.md
"Escalation" flags. **A renderer or importer does not need it** — visibility is
a run-time culling optimisation, not a requirement for reading geometry,
materials, lighting or collision. If an implementer later needs it, request a
spec revision and derive it from public documentation, not from the GPL tree.

**E.3 — Alien Arena's high-detail lightmap sidecar file.** The tree defines a
separate, Alien Arena-specific file format (a companion file alongside the
`.bsp`) that can override per-face lightmap data at higher resolution and with a
per-face luxel scale other than 16 units. It is **not part of the BSP file**, it
is optional, and a reader that ignores it renders the map correctly using the
BSP's own lighting lump per §7. Its layout is therefore out of the scope stated
above and has been left out entirely. If it is ever wanted, it needs its own
spec and its own Reader pass.

**E.4 — The physical ordering of lumps within the file.** The implementation
carries an expected physical layout order that it uses to validate files. This
is a validation heuristic and an implementation choice, not a format
requirement — §1.8 and §12.2 state the correct portable rule instead.

**E.5 — Content masks as named constants.** The implementation defines a set of
named unions of contents bits for gameplay queries (what stops a player, what
counts as liquid, and so on). The bit unions that a physics importer actually
needs are stated as unions in §9.4; the wider set is gameplay design rather than
format, so the names and the remaining combinations are omitted.

**E.6 — Rendering technique.** How the implementation batches surfaces, packs
lightmap atlases, subdivides warped surfaces, orders translucent passes, or
implements its wet-surface and shadow-map effects is engine design, not format.
Only the file-level meaning of each flag is recorded (§8), stated as
externally-observable appearance.

**E.7 — Texture-asset file formats.** How a `.wal`, `.tga`, `.jpg` or other
image file is decoded is outside this spec. §6.4 and §6.5 record only the naming
convention that maps a texinfo name onto asset paths.

**E.8 — Any tuned or hand-authored data.** No constant table in this spec is a
creative or tuned artefact: every value recorded is either a format constant, a
bit assignment, a structural size, or a declared limit.

## Escalations

**X.1** None blocking. The one judgement call is E.2 (visibility decompression),
resolved by exclusion on the grounds that the target scope does not need it. A
human should confirm that exclusion is acceptable before any consumer of this
spec attempts PVS-based culling.

**X.2** Procedural: an implementation written before this spec existed has
been discarded rather than audited, and the viewer is being rebuilt from these
facts alone. Every constant and layout in the new code must cite a numbered fact
above; anything that cannot is a signal that a fact is missing here and should
come back as a spec revision, not as a private lookup.
