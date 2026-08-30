# SPEC-EXTLM: external lightmap pages beside a `.bsp`

| | |
|---|---|
| Source consulted | the bytes of `plat23.bsp` and `yocto.bsp`, and the image files shipped beside them, in `map-plat23_1.14.dpk` and `map-yocto_1.1.dpk` |
| Licence of source | the files are content under CC BY-SA; the facts below are format facts read out of them |
| Version / commit | packages as published on `dl.unvanquished.net/pkg/`, fetched 2026-08-30 |
| Files consulted | `maps/<name>.bsp` and `maps/<name>/lm_*.webp` within those packages |
| Non-copyleft sources checked first | not applicable — no copyleft source was consulted at any point. Every fact below was derived from file bytes, per CLEAN-ROOM.md Rule 0 item 2. |
| Reader | derived directly; no wall was required, because no copyleft source was read |
| Date | 2026-08-30 |

## Scope

A map compiler can write a map's baked lighting to image files beside the `.bsp`
instead of into the container's own lightmap lump. This describes how a reader
finds those files and which one a face means, so that
[SPEC-BSP46](SPEC-BSP46.md) §4.13's indexing still resolves when §4.13's lump is
empty.

This is a **map-compiler** feature, not a property of any one game: the lump is
the one `SPEC-BSP46` already describes, and a map from any source may be built
this way. It is described here because Unvanquished's maps are, and because a
reader that does not know about it renders such a map with no baked light at
all.

Marker legend: `[OBSERVED]` read out of bytes, `[DERIVED]` reasoned from
observations, `[UNKNOWN]` not established.

## Facts

### 1. Recognising it

**1.1** `[OBSERVED]` A map built this way carries a lightmap lump
(`SPEC-BSP46 §4.13`, lump index 14) of **length zero**, while its faces still
carry non-negative `lm_index` values. Both sample maps do.

**1.2** `[DERIVED]` A zero-length lightmap lump together with at least one face
whose `lm_index` is non-negative is therefore the signal to look outside the
file. A map with no baked light at all has no such face, so the two cases are
distinguishable and the search costs nothing on maps that do not need it.

### 2. Where the files are

**2.1** `[OBSERVED]` The pages sit in a directory beside the map, named after the
map: for `maps/<name>.bsp` they are `maps/<name>/lm_NNNN.<ext>`, where `NNNN` is
a decimal index zero-padded to four digits, counting from `0000`.

**2.2** `[OBSERVED]` The observed extension is `.webp`. `[DERIVED]` The extension
is not part of the naming rule and should be resolved the same way every other
texture name in this content is (`SPEC-Q3SHADER §1.6`): strip it and try the
supported ones in turn.

**2.3** `[OBSERVED]` Both sample maps' pages are 1024×1024 RGB. This is not a
fixed size — nothing in the file states it, and it is a compiler setting — so a
reader must take the dimensions from each image rather than assuming them. In
particular it is **not** the 128×128 of `SPEC-BSP46 §4.13.1`.

### 3. Which page a face means

**3.1** `[OBSERVED]` A face's `lm_index` (`SPEC-BSP46 §4.12`) is the **file
index directly**: `lm_index` *n* means `lm_%04d` with *n*. It is not scaled or
offset.

**3.2** `[OBSERVED]` A face's lightmap UVs are normalised over the whole page, as
they are for an internal lightmap block, so no change to UV handling is needed —
only the page's size and origin differ.

**3.3** `[OBSERVED]` The negative value `-3` occurs on faces in both maps (43 of
4309 in one, 118 of 29071 in the other). `[DERIVED]` It is a sentinel meaning the
face has no page, consistent with `SPEC-BSP46 §4.12`'s treatment of a negative
`lm_index`; a reader should treat any negative value as "no lightmap" rather
than testing for `-1` alone.

### 4. Deluxemaps

**4.1** `[OBSERVED]` A compiler may write a second page for every lightmap page,
holding per-luxel light *direction* rather than light. Where it does, the two
kinds alternate in the same numbering: even indices are lightmaps and odd indices
are direction maps.

**4.2** `[OBSERVED]` The evidence is the index distribution. One sample map
references only `lm_index` 0 and ships two files. The other references only the
**even** values 0, 2, 4, 6 and 8 and ships ten files, `lm_0000` through
`lm_0009`. No face in either map references an odd index.

**4.3** `[OBSERVED]` Read as images, the two kinds are unmistakable: the even
pages carry the map's baked light and look like the lit scene, and the odd pages
carry direction vectors and have the pastel appearance of an encoded normal map.

**4.4** `[DERIVED]` **No special handling is required.** Because §3.1 makes
`lm_index` a direct file index and no face references an odd page, a reader that
simply loads the page a face names gets the lightmap and never the direction map.
The direction pages cost only the load of files nothing references, which is
avoided by loading pages on demand rather than loading the directory.

**4.5** `[UNKNOWN]` Whether anything in the map file states that direction pages
are present. Nothing was found that does, and §4.4 means a reader does not need
to know.

## Excluded

- How the direction pages encode direction. A consumer that wants to use them
  must establish this; it is not needed to draw the baked light.
- The compiler options that select external pages, page size or direction maps.
  These belong to the tool that built the map, not to the file being read.

## Escalations

None. No copyleft source was read in producing this document.
