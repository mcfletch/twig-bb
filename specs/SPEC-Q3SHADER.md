# SPEC-Q3SHADER: Quake 3 `.shader` material scripts, as far as a viewer needs them

| | |
|---|---|
| Source consulted | **No copyleft source was consulted.** See "Provenance" below. |
| Licence of source | n/a — a published manual, shipped map content, and this workspace's own BSD code |
| Version / commit | n/a |
| Files consulted | *Quake III Arena Shader Manual* (id Software), read at `https://www.icculus.org/gtkradiant/documentation/Q3AShader_Manual/`; the `scripts/*.shader` files inside the sample map archives under `tmp/q3/`; `twitch/twitchoglc/shaderparser.py` at `master` (this workspace's own BSD code) |
| Revised | 2026-07-27 -- §2.4 (wave functions, `tcMod`, `deformVertexes`, `rgbGen`/`alphaGen`, `animMap`) added from the same published manual, moving those facts out of "Excluded" E.1. No new source was consulted. |
| Non-copyleft sources checked first | This document *is* the non-copyleft record: no engine tree was opened. |
| Reader | n/a — not a clean-room spec; written by the Implementer from licence-clean sources |
| Date | 2026-07-25 |
| **Clean-room status** | **Not applicable.** No copyleft source was read. This file records provenance and gives the implementation numbered facts to cite, as [SPEC-BSP46](SPEC-BSP46.md) does for the container. |

## Provenance

1. **A published manual.** The *Quake III Arena Shader Manual* is id Software's
   own released documentation of the language, widely mirrored. It supplied the
   syntax rules in §1 and the keyword vocabulary. Its prose is copyrighted but
   not copyleft; nothing is quoted, and every statement below is written
   independently.
2. **Shipped map content.** The `.shader` files inside the sample `.pk3`
   archives are data this workspace holds. A census over them established which
   keywords actually occur, their argument shapes, and their idiomatic use —
   §2's table is that census, not a transcription of any implementation.
3. **This workspace's own prior BSD reader**, `twitchoglc/shaderparser.py`,
   which independently corroborates the block syntax.

No Quake, ioquake3 or other engine source was opened.

## Scope

Enough of the language to decide, for a named material: which image to draw,
whether it is translucent, alpha-masked, two-sided, unlit, sky, or not drawn at
all, and whether it blocks movement. Animation, wave functions, deformation,
fog and the compile-time `q3map_*` family are out of scope beyond being parsed
and ignored.

## Facts

### 1. Syntax

**1.1** A `.shader` file is a sequence of material definitions. Each is a name
token followed by a brace-delimited body.

**1.2** A body holds *general* directives — one per line, a keyword and its
arguments — and zero or more *stage* blocks, each itself brace-delimited.

**1.3** `//` begins a comment that runs to the end of the line. It need not be
preceded by whitespace: `}//note` occurs in shipped content and closes a block
before the comment. (This differs from the `.rscript` descendant of a different
engine, where `//` is a whitespace-delimited token that discards only itself —
`SPEC-RSCRIPT §3.4`. The two languages must not share a tokeniser.)

**1.4** Keywords are **not** case sensitive. Shipped content mixes `blendFunc`
and `blendfunc`, `tcMod` and `tcmod`.

**1.5** `{` and `}` are tokens in their own right and need no surrounding
whitespace.

**1.6** A material's name is a forward-slash path with no extension, matching
the texture name stored in the map's textures lump (`SPEC-BSP46 §6.1`). Paths
inside directives *do* carry an extension, which is advisory: the file is found
by trying the extensions the renderer supports.

### 2. Directives a viewer must understand

Provenance tags: **[P]** stated in the published manual; **[C]** established
from the shipped `.shader` content.

#### 2.1 General (body-level) directives

| Keyword | Arguments | Meaning taken |
|---|---|---|
| `surfaceparm` | 1 token | **[P][C]** A physical/visual property of the surface; see §2.2. |
| `cull` | 1 token | **[P][C]** `none`, `disable` or `twosided` turn backface culling off; `front`/`back` are the defaults and change nothing for a viewer. |
| `skyparms` | 3 tokens | **[P][C]** The material is sky. The arguments name a far box, a cloud height, and a near box; `-` means "none". |
| `qer_editorimage` | 1 token | **[P][C]** An image the map editor shows for this material. It is the best available stand-in when no stage carries a drawable texture. |
| `deformVertexes` | variable | **[P]** Run-time geometry deformation; parsed and ignored. |
| `q3map_*` | variable | **[P][C]** Compile-time directives for the map compiler, with no run-time effect; parsed and ignored. |
| `fogparms`, `tessSize`, `sort`, `nopicmip`, `nomipmaps`, `polygonOffset`, `light`, `entityMergable`, `portal` | variable | **[P][C]** Parsed and ignored by this viewer. |

**2.1.1** Any unrecognised general directive occupies the rest of its line and
is skipped. Because a directive's arguments never span a line, a line-oriented
skip cannot desynchronise the parser — unlike `.rscript`, where arity must be
known exactly (`SPEC-RSCRIPT §4.4`).

#### 2.2 `surfaceparm` values a viewer acts on

**[P][C]** Values occur one per directive and combine freely.

| Value | Meaning taken |
|---|---|
| `nodraw` | The surface is not rendered. |
| `sky` | The surface is sky; the skybox shows through it. |
| `trans` | The surface is translucent, so it is drawn blended and unlit. |
| `nolightmap` | The surface takes no baked lightmap. |
| `nonsolid` | The surface does not block movement. |
| `alphashadow` | The surface's alpha channel is a cut-out mask. |
| `water`, `slime`, `lava` | Liquid volumes; treated as translucent and unlit. |
| `trigger`, `clip`, `playerclip`, `botclip`, `origin`, `hint`, `skip` | Compile/gameplay volumes that are never drawn. |
| anything else | Recorded and otherwise ignored. |

#### 2.3 Stage directives

| Keyword | Arguments | Meaning taken |
|---|---|---|
| `map` | 1 token | **[P][C]** The stage's texture. Two reserved values are not files: `$lightmap` means "sample the baked lightmap here" and `$whiteimage` means "a plain white texture". |
| `clampmap` | 1 token | **[P][C]** As `map`, but the texture does not repeat. |
| `animMap` | 1 number then N tokens | **[P]** Frames cycled at the given rate; the first frame stands in. |
| `blendFunc` | 1 or 2 tokens | **[P][C]** Either two GL blend factors, or one of the shorthands `add`, `filter`, `blend`. A stage that blends is not opaque. |
| `alphaFunc` | 1 token | **[P][C]** `GT0`, `LT128` or `GE128` — an alpha cut-out rather than blending. |
| `rgbGen`, `alphaGen`, `tcGen`, `tcMod`, `depthFunc`, `depthWrite`, `detail` | variable | **[P][C]** Colour generation, coordinate generation and modification; parsed and ignored beyond the line. |

**2.3.1** The material's drawable image is the first stage's `map`/`clampmap`
argument that is neither `$lightmap` nor `$whiteimage`; failing that, the
`qer_editorimage`; failing that, the material's own name treated as a texture
path.

**2.3.2** A material is lightmapped if any stage names `$lightmap`, unless a
`surfaceparm` in §2.2 says otherwise. A material with no stages at all is a
description of a surface whose texture is simply its own name.

#### 2.4 Animation

All **[P]** unless marked otherwise: the published manual documents this family
in full. Everything here is a function of **scene time in seconds** and nothing
else, which is what lets every surface in a map animate in step from one clock.

**2.4.1 Wave functions.** Several directives take a *wave*, spelled as five
tokens: a function name then `base`, `amplitude`, `phase` and `frequency`. The
value at time `t` is

    base + amplitude * f(frac(phase + t * frequency))

where `frac` is the fractional part, so the argument to `f` runs 0 to 1 over
each cycle and `frequency` is cycles per second. The named functions and their
ranges are:

| Name | `f(x)` over one cycle | Range |
|---|---|---|
| `sin` | `sin(2*pi*x)` | -1 to 1 |
| `triangle` | rises 0 to 1 over the first half, falls 1 to 0 over the second | 0 to 1 |
| `square` | 1 for `x < 0.5`, otherwise -1 | -1 or 1 |
| `sawtooth` | `x` | 0 to 1 |
| `inversesawtooth` | `1 - x` | 0 to 1 |
| `noise` | a pseudo-random value, held for the cycle | 0 to 1 |

The ranges are **not** uniform: `sin` and `square` are centred on zero while the
other three are not. The manual documents them that way and content is authored
against it, so a viewer that normalises them all to one range renders the wrong
amplitude. An unrecognised function name is treated as `sin`, since that is the
overwhelmingly common case and the alternative is a surface that does not move
at all.

**2.4.2 `tcMod`** modifies a stage's texture coordinates. Several may appear in
one stage and they apply **in the order written**, each to the output of the
last. Texture coordinates are in the unit square; the rotations and scalings
below turn about `(0.5, 0.5)`, the centre of the image, not about the origin.

| Form | Arguments | Meaning |
|---|---|---|
| `tcMod scroll <s> <t>` | 2 numbers | Add `s*time` and `t*time` to the coordinates. Units are texture widths per second. |
| `tcMod scale <s> <t>` | 2 numbers | Multiply the coordinates by `s` and `t`. Constant; not a function of time. |
| `tcMod stretch <wave>` | 5 tokens | Scale both axes about the centre by the reciprocal of the wave's value. |
| `tcMod rotate <degrees>` | 1 number | Rotate about the centre at `degrees` per second. |
| `tcMod turb <base> <amp> <phase> <freq>` | 4 numbers | Add a sinusoidal offset that depends on the *vertex position* as well as the time, so the surface appears to churn rather than to slide. It is a wave in all but spelling: the four numbers are a wave's four, with the function fixed at `sin`. |
| `tcMod transform <m00> <m01> <m10> <m11> <t0> <t1>` | 6 numbers | A general affine transform of the coordinates. Constant. |

**2.4.2.1** `turb`'s dependence on position is what distinguishes it from
`scroll`: the two produce a sliding image and a churning one respectively, and
liquid surfaces use `turb`. The manual describes the effect rather than giving
a formula; the exact spatial term is therefore **a choice** (see §4 of
`CLEAN-ROOM.md` for the convention), recorded in the implementation as such.

**2.4.3 `deformVertexes`** moves geometry at run time.

| Form | Arguments | Meaning |
|---|---|---|
| `deformVertexes wave <div> <wave>` | 1 number then 5 tokens | Displace each vertex along its normal by the wave's value. `div` spreads the phase across the surface by dividing a position term, so a large surface ripples rather than moving as one piece; `div` of 0 moves the whole surface together. |
| `deformVertexes normal <amp> <freq>` | 2 numbers | Perturb the *normals* rather than the positions, which makes a flat surface light as though it were rippling. |
| `deformVertexes bulge <width> <height> <speed>` | 3 numbers | A travelling wave along the surface's texture coordinates. |
| `deformVertexes move <x> <y> <z> <wave>` | 3 numbers then 5 tokens | Displace the whole surface along `(x, y, z)` by the wave's value. |
| `deformVertexes autosprite`, `autosprite2` | none | The surface is turned to face the viewer. |
| `deformVertexes projectionShadow`, `text0`..`text7` | none | Not visual surface animation; ignored. |

**2.4.4 `rgbGen` and `alphaGen`** generate a stage's colour and opacity.

| Form | Meaning |
|---|---|
| `rgbGen wave <wave>` | Grey level from the wave, applied to all three channels. |
| `rgbGen const ( r g b )` | A fixed colour. |
| `rgbGen identity` | Full white; the default. |
| `rgbGen identityLighting`, `entity`, `oneMinusEntity`, `vertex`, `oneMinusVertex`, `exactVertex`, `lightingDiffuse` | Colour from a source outside the material -- the entity that owns the surface, the vertex colours, or the run-time lighting. |
| `alphaGen wave <wave>` | Opacity from the wave. |
| `alphaGen const <a>` | A fixed opacity. |
| `alphaGen portal <range>`, `lightingSpecular` | Opacity from the viewer's position. |

**2.4.5 `animMap <frequency> <tex1> ... <texN>`** cycles the stage's texture
through the named images at `frequency` frames per second, wrapping. The frame
shown at time `t` is `floor(t * frequency) mod N`.

### 3. Where the files live

**3.1** Scripts live under `scripts/` inside the `.pk3`, with the extension
`.shader` (`SPEC-BSP46 §7.2`). All of them are read; a later definition of the
same name replaces an earlier one.

**3.2** A material named by the map's textures lump that has no definition in
any script is not an error: the name is used directly as a texture path.

## Excluded

**E.1 — Multi-stage animation composition.** §2.4 records what each animation
directive means, and a viewer drawing one PBR material per surface can honour
the first drawable stage's `tcMod`, `rgbGen`, `alphaGen` and `animMap` and the
material's `deformVertexes`. What it cannot reproduce is *several animated
stages composited over each other*, which is a property of the blend chain E.3
already excludes rather than of any directive.

`deformVertexes autosprite`/`autosprite2` are excluded for a different reason:
they are a rendering technique (a camera-facing billboard) rather than a
property of the surface, and a viewer that does not implement them draws a
static quad, which is what the surface is.

**E.2 — The `q3map_*` compile-time family.** These direct the map compiler and
have no run-time meaning, so only their existence matters (they must be skipped
without desynchronising the parser).

**E.3 — Sort order and the multi-pass blending model.** A viewer that draws one
PBR material per surface does not reproduce a multi-stage blend chain. §2.3.1
records how a single drawable image is chosen instead.
