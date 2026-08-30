# SPEC-CRN: the Crunch (`.crn`) compressed-texture container

| | |
|---|---|
| Source consulted | the bytes of 303 `.crn` files shipped in released Unvanquished asset packages (`map-plat23_1.14.dpk`, `map-yocto_1.1.dpk`, `tex-pk02_1.3.2.dpk`) |
| Licence of source | the *files* are content under CC BY-SA; the *format* is that of Crunch, whose reference implementation is zlib-licensed — permissive, not copyleft |
| Version / commit | packages as published on `dl.unvanquished.net/pkg/`, fetched 2026-08-30 |
| Files consulted | the byte content of the `.crn` entries themselves |
| Non-copyleft sources checked first | not applicable — no copyleft source was consulted at any point. Every fact below was derived from file bytes, per CLEAN-ROOM.md Rule 0 item 2, and each is stated with the check that confirms it. |
| Reader | derived directly; no wall was required, because no copyleft source was read |
| Date | 2026-08-30 |

## Scope

What a decoder needs in order to turn a `.crn` file into pixels: how to
recognise one, where its dimensions and pixel format live, and how to tell which
block-compression scheme the decompressed payload is in.

The entropy coding itself is **not** described here and does not need to be: a
permissively licensed decoder for it exists and is used (see §5).

Marker legend, as used by this project's other specs: `[OBSERVED]` read out of
bytes, `[DERIVED]` reasoned from observations, `[UNKNOWN]` not established.

## Facts

### 1. Identification

**1.1** `[OBSERVED]` A Crunch file begins with the two bytes `0x48 0x78`, which
are the ASCII characters `Hx`. All 303 sample files carry it.

**1.2** `[OBSERVED]` All multi-byte scalars in the header are **big-endian**.
This is the opposite of the `IBSP` container the same packages carry, and is the
single easiest thing to get wrong.

### 2. Header layout

**2.1** `[OBSERVED]` The header begins at offset 0 with these fields, in this
order:

| Offset | Type | Meaning |
|---|---|---|
| 0 | `uint16` | signature, `0x4878` (§1.1) |
| 2 | `uint16` | header size in bytes |
| 4 | `uint16` | header checksum |
| 6 | `uint32` | total file size in bytes |
| 10 | `uint16` | payload checksum |
| 12 | `uint16` | image width in pixels |
| 14 | `uint16` | image height in pixels |
| 16 | `uint8` | number of mip levels |
| 17 | `uint8` | number of faces |
| 18 | `uint8` | pixel format code (§3) |
| 19 | `uint16` | flags |

**2.2** `[OBSERVED]` The field at offset 6 equals the file's own length on disk,
exactly, for all 303 samples. This is the check that fixes the offsets of every
field before it, and it is worth re-running on any new sample: if it does not
hold, the layout above is being applied to something that is not this format.

**2.3** `[OBSERVED]` The field at offset 16 equals `floor(log2(max(width,
height))) + 1` for every sample — a full mip chain down to one texel. This is
the check that fixes offsets 12 through 16. Observed values run from 10
(512×512) to 12 (3840×2160).

**2.4** `[OBSERVED]` The field at offset 17 is 1 in every sample. Cube maps, if
the format expresses them this way, do not occur in this content.

**2.5** `[UNKNOWN]` The meaning of the checksum fields at offsets 4 and 10, and
of the flags at offset 19 (observed value `0x0000` throughout). A decoder does
not need them, so no attempt was made to establish them.

### 3. Pixel format codes

**3.1** `[OBSERVED]` Three format codes occur in this content, with these
frequencies and these decompressed block sizes:

| Code | Files | Bytes per 4×4 block | Where it is used |
|---|---|---|---|
| 0 | 219 | 8 | colour, alpha, height and specular maps |
| 2 | 18 | 16 | images carrying a full alpha channel |
| 7 | 66 | 16 | normal maps (files named `*_n.crn`) |

**3.2** `[DERIVED]` Code 0 is an 8-byte-per-block scheme — the size of BC1/DXT1
— and decodes correctly as BC1 (§4.2). Codes 2 and 7 are 16-byte-per-block
schemes and decode as a BC3/DXT5-family layout.

**3.3** `[UNKNOWN]` Whether code 7 is exactly BC3 or a two-channel normal-map
variant that reuses the same block size. The distinction does not arise for a
consumer that reads only the colour channels, and it was not pursued. A consumer
that wants the normal vectors must establish this first.

**3.4** `[DERIVED]` **Do not dispatch on the format code.** The block size is
recoverable from the decompressed payload's own length (§4.1), which is a direct
measurement rather than a table lookup, and it stays correct for format codes
this content does not happen to contain.

### 4. Decompressed payload

**4.1** `[OBSERVED]` Decompressing the payload for mip level 0 yields exactly
`ceil(width / 4) × ceil(height / 4) × B` bytes, where `B` is 8 or 16. All 303
samples satisfy this for one of the two values, with no residue. Comparing the
returned length against both candidates therefore identifies `B` outright.

**4.2** `[OBSERVED]` The payload is in ordinary linear block order: blocks left
to right, then top to bottom. Feeding it to a stock BC1 or BC3 decoder at the
header's width and height produces a correct image, confirmed by eye against a
map screenshot and a minimap whose subject matter is unmistakable.

**4.3** `[OBSERVED]` Only mip level 0 is returned by the decoder used; the
remaining levels of the chain are not produced. A consumer that wants mipmaps
must generate them.

### 5. Decoding the entropy coding

**5.1** `[DOCUMENTED]` `texture2ddecoder` (PyPI, **MIT** licence) exposes the
decompression step. Its licence is permissive, and the Crunch reference
implementation it builds on is zlib-licensed, so neither places any obligation
on a BSD-licensed consumer.

**5.2** `[OBSERVED]` The library exposes two bitstream variants. The one it names
for Unity is the one this content uses; the other returns a payload of the
correct *length* but with the block order wrong, which renders as a recognisably
scrambled image rather than as an error. **A length check does not catch this** —
only looking at the result does.

**5.3** `[OBSERVED]` All 303 samples decompress with that variant without an
exception and with a payload length satisfying §4.1.

## Excluded

- The entropy coding, the clustered-codebook scheme, and everything else about
  how the payload is compressed. It was never examined: a permissively licensed
  decoder performs that step, so the facts were never needed.
- The checksum algorithms (§2.5).
- The exact identity of format code 7 (§3.3).

## Escalations

None. No copyleft source was read in producing this document, and the format's
own reference implementation is permissively licensed in any case.
