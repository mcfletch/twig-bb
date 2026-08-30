# SPEC-UNVDIST: licensing and distribution of the Unvanquished asset packages

| | |
|---|---|
| Source consulted | the released Unvanquished **asset packages** — their `README.md`, `DEPS`, `about/`, `LICENSE` and `COPYING.txt` members — plus the directory listings, checksum manifests and HTTP headers of `https://dl.unvanquished.net/`, and third-party distributor metadata (Flathub, Repology, Debian) |
| Licence of source | the packages carry CC0 1.0, CC BY 3.0, CC BY 4.0, CC BY-SA 2.5, CC BY-SA 3.0, CC BY-SA 4.0, MIT and OFL 1.1 content; per-package detail is §1 |
| Version / commit | release 0.56.2, published 2026-05-11; package files as listed on `dl.unvanquished.net/pkg/` on 2026-08-30 |
| Files consulted | metadata members of 15 locally held `.dpk` files, metadata members read by HTTP range request from 12 further `.dpk` files, `/current.txt`, `/versions.json`, `/release/unvanquished_0.56.2.zip` (its central directory, `README.txt` and `pkg/md5sums`), the Flathub manifest and AppStream metadata |
| Non-copyleft source checked first | **no copyleft source was consulted at any point.** The Unvanquished game logic and the Dæmon engine are GPLv3 and were not read, cloned, fetched or opened; neither was the project's build tooling nor its wiki. Every fact below comes from a package's own metadata files, from the download server, from a licence text, or from a distributor's published metadata — CLEAN-ROOM.md Rule 0 items 1, 2 and 4. |
| Reader | Claude (Opus 5), acting as Reader |
| Date | 2026-08-30 |

## Scope

Whether a third-party BSD-licensed viewer may fetch and read Unvanquished
content, what it must say when it does, which files it must fetch to render one
level, what those files weigh, and where an already-installed copy lives.

This describes **content**, not the engine. The engine and the game logic are a
separate work under separate terms, and nothing here depends on them.

Marker legend, as used by this project's other specs: `[OBSERVED]` read out of a
package or measured over HTTP, `[DOCUMENTED]` stated on a project or distributor
page (URL given), `[DERIVED]` reasoned from observations, `[UNKNOWN]` not
established.

## Facts

### 1. Per-package licensing

Every package is a ZIP archive (§4.1). Each states its own terms; the terms
differ from package to package, and §1.1 is the table a consumer needs.

**1.1** `[OBSERVED]` Terms as the packages state them. "Stated in" names the
member the statement was read from.

| Package | Stated licence | Stated author(s) | Attribution the licence requires | Stated in |
|---|---|---|---|---|
| `map-plat23_1.14` | Creative Commons Attribution-ShareAlike 3.0 | Jack “EmperorJack” Purvis | credit the author, link the licence, mark changes | `README.md`, `about/map-plat23.txt` |
| `map-yocto_1.1` | Creative Commons Attribution-ShareAlike 3.0 | Paweł “Pevel” Micek | credit the author, link the licence, mark changes | `README.md`, `about/map-yocto.txt` |
| `map-usstremor_1.1` | Creative Commons Attribution 4.0 International for the author's own files; per-file exceptions listed in §1.2 | Matthias “Masmblr” Peters, plus five further rights holders | credit each listed author for their listed files, link the licence, mark changes (the package marks modified files itself) | `README.md`, `LICENSE` |
| `tex-common_2.5` | CC0 1.0 Universal | Stijn “Ingar” Buys; Maximilian “Viech” Stahlberg; Thomas “illwieckz” Debesse | none required by the licence | `README.md`, `about/tex-common.txt` |
| `tex-pk01_1.3.1` | Creative Commons Attribution 3.0 Unported | Philip “Blazeeer” Klevestav | credit the author, link the licence, mark changes | `about/tex-pk01.txt` |
| `tex-pk02_1.3.2` | Creative Commons Attribution 3.0 Unported | Philip “Blazeeer” Klevestav, modified by Unvanquished Development | credit the author, link the licence, mark changes | `README.md`, `about/tex-pk02.txt` |
| `tex-space_1.3` | Creative Commons Attribution-ShareAlike 3.0 **or** GPL version 2, at the redistributor's choice | Stijn “Ingar” Buys | under the CC option: credit the author, link the licence, mark changes | `README.md`, `about/tex-space.txt` |
| `tex-vega_1.5` | Creative Commons Attribution-ShareAlike 3.0 **or** GPL version 2, at the redistributor's choice | Stijn “Ingar” Buys | as above | `about/tex-vega.txt` |
| `tex-ej01_1.3.1` | Creative Commons Attribution-ShareAlike 3.0 | Jack “EmperorJack” Purvis | credit the author, link the licence, mark changes | `about/tex-ej01-clean.txt` |
| `tex-ex_1.3.1` | Creative Commons Attribution-ShareAlike 4.0 International | Yves “evillair” Allaire | credit the author, link the licence, mark changes | `about/tex-ex.txt` |
| `tex-exm_1.3.3` | Creative Commons Attribution-ShareAlike 4.0 International | Yves “evillair” Allaire, modified by Unvanquished Development | credit the author, link the licence, mark changes | `about/tex-exm.txt` |
| `tex-tech_1.3.1` | Creative Commons Attribution-ShareAlike 3.0 | Scott “Cr4zy” Coxhead | credit the author, link the licence, mark changes | `about/tex-tech.txt` |
| `tex-trak5_1.3.2` | MIT (“X11”) | Georges “TRaK” Grondin | keep the copyright and permission notice | `about/tex-trak5.txt` |
| `tex-all_2.3` | **unstated** — see §1.5 | The Unvanquished team | — | `README.md` (no Legal section) |
| `res-leveleditor_0.54` | CC0 1.0 Universal | The Unvanquished team | none required by the licence | `README.md` |
| `res-ambient_0.55` | **unstated** — see §1.5 | The Unvanquished team | — | `README.md` (no Legal section) |
| `res-legacy_0.55` | **unstated** — see §1.5, §1.6 | The Tremulous team; the Unvanquished team | — | `README.md` (no Legal section) |
| `res-players_0.56` / `_0.56.2` | **unstated** — see §1.5 | The Unvanquished team | — | `README.md` (no Legal section); the patch package carries no `README.md` at all |
| `res-buildables_0.56` / `_0.54.1` | **unstated** — see §1.5 | The Unvanquished team | — | as above |
| `res-weapons_0.56` / `_0.56.2` | **unstated** — see §1.5 | The Unvanquished team | — | as above |
| `res-voices_0.56` / `_0.55.3` | **unstated** — see §1.5 | The Unvanquished team | — | no `README.md` |
| `res-soundtrack_0.54` | **unstated** — see §1.5 | The Unvanquished team | — | `README.md` (no Legal section) |
| `unvanquished_0.56.2` (base) | Creative Commons Attribution-ShareAlike 2.5 for media, with the exceptions in §1.3 | The Unvanquished team | credit the author, link the licence, mark changes | `COPYING.txt` |
| `unvanquished_0.56.1`, `bugfix_0.52.1-…` | not content: compiled game-logic binaries, see §1.7 | — | — | file listing |

**1.2** `[OBSERVED]` `map-usstremor_1.1` states its terms per file, in six
groups: Matthias “Masmblr” Peters under CC BY 4.0 (the level itself, its
navigation meshes, models, sounds and most textures); Philip Klevestav under CC
BY 3.0 Unported (seven texture files); Stijn “Ingar” Buys under an Attribution
licence, version not given (twenty-one model and texture files); the freesound
contributor `newlocknew` under Attribution 4.0 (twenty-three sound files);
Unvanquished Development under "GNU GPLv3, CC BY-SA 2.5" (one colour-grading
image, `gfx/usstremor/colorgrading.webp`); and the Librestile font by
`ocelothe2k1` under SIL Open Font License 1.1, used inside several textures. The
package marks its modified and derivative files with an asterisk.

**1.3** `[OBSERVED]` The base package `unvanquished_0.56.2` is the one tree that
mixes terms materially. `COPYING.txt` states CC BY-SA 2.5 for the media and
lists one code exception, a BSD-licensed Lua file. Three further statements
inside the same package are **not** covered by that summary:

- `ui/assets/icons/LICENSE.md` states that `ban.svg` and `ban.webp` are under
  the **GPL**, attributed to `nagoshiashumari` via SVGrepo.
- `gfx/feedback/bottactic/license.md` and `gfx/feedback/vsay/license.md` state
  **MIT** for icons from Feather Icons (Cole Bemis) and from Grise, and point at
  SVGrepo's licensing page for three further source icons.
- `about/dejavu.copyright.txt` and `about/unifont.copyright.txt` cover the
  bundled fonts: the Bitstream Vera permissive font licence for DejaVu, and
  Unifont's own terms.

The package also carries `GPL.txt`, the text of GPL version 3.

**1.4** `[OBSERVED]` `unvanquished_0.56.2` additionally contains six `.nexe`
files — compiled game-logic modules — alongside its media. Their terms are those
of the game logic, which is GPLv3 (§1.7). A viewer has no use for them, but
their presence is what makes this package a mixed-licence tree.

**1.5** `[OBSERVED]` Nine packages state no licence anywhere in the archive:
`tex-all`, `res-ambient`, `res-legacy`, `res-players`, `res-buildables`,
`res-weapons`, `res-voices`, `res-soundtrack`, and each of the small patch
packages. Their `README.md`, where they carry one, has an *About* and a
*Credits* section but no *Legal* section, and no `about/` directory. These are
the packages holding the player models, buildable models, weapon models,
soundtrack and voice lines. `[DERIVED]` The project-wide statement in
`COPYING.txt` (§1.3) is the only terms that reach them, which would make them CC
BY-SA 2.5. That inference is **not** a fact and is escalated at §E.1.

**1.6** `[OBSERVED]` `res-legacy` states that most of its assets are inherited
from the Tremulous project, and credits the Tremulous team. It states no licence
of its own, and the terms under which those inherited assets arrived are
`[UNKNOWN]` from the sources allowed here. Escalated at §E.2.

**1.7** `[OBSERVED]` Two of the fifteen locally held files are not content
packages at all. `unvanquished_0.56.1.dpk` contains six `.nexe` files and a
`DEPS`; `bugfix_0.52.1-20210624-032404-b3fe650-slipher.dpk` contains four
`.nexe` files and a symbol archive. `[DOCUMENTED]` The project's licence is
declared as `MIT AND GPL-3.0-or-later AND Zlib AND BSD-3-Clause`
(https://flathub.org/api/v2/appstream/net.unvanquished.Unvanquished). These
binaries are the GPLv3 part. A viewer must neither ship them nor disassemble
them; it has no reason to fetch them.

**1.8** `[DOCUMENTED]` Nixpkgs, which packages release 0.56.2, records the
licence set as MIT, GPL-3.0-or-later, Zlib, BSD-3-Clause, CC-BY-SA-2.5,
CC-BY-SA-3.0, CC-BY-3.0, CC-BY-SA-4.0 and CC0-1.0
(https://repology.org/project/unvanquished/versions). That list corroborates
§1.1 and adds nothing the packages do not say for themselves, except that it
places CC-BY-SA-2.5 over content that states nothing (§1.5).

**1.9** `[OBSERVED]` `res-leveleditor_0.54`'s `README.md` refers the reader to
`about/tex-common.txt` for its contributor list. That member is not in the
package. The reference resolves in `tex-common_2.5`, which the package declares
as a dependency.

### 2. The two questions

These have different answers and are set out separately.

#### 2.1 May a BSD-licensed viewer download these packages and read them?

**2.1.1** `[DERIVED]` Yes, for every package in §1.1 that states terms. None of
the licences found — CC0 1.0, CC BY 3.0, CC BY 4.0, CC BY-SA 2.5/3.0/4.0, MIT,
OFL 1.1 — restricts *use* by engine, by application or by field of endeavour.
Reading a file and drawing it on screen is use, and CC licences grant it
unconditionally; the CC obligations attach to *sharing* and to *adapting*, not
to viewing. Nothing in any package's stated terms resembles the Alien Arena
restriction (art licensed for use only within its own engine) that this project
already refuses.

**2.1.2** `[OBSERVED]` No package carries a non-commercial, no-derivatives, or
engine-restricted clause. The strictest term found anywhere is ShareAlike.

**2.1.3** `[DERIVED]` ShareAlike does not reach the viewer. A renderer that
loads a texture and draws it produces no adapted work of the texture that it
then distributes; the ShareAlike condition would attach only if the viewer
distributed a modified copy of the content. A BSD-licensed program that reads
CC BY-SA data is not a derivative of that data, in the same way that an image
viewer is not a derivative of the photographs it opens.

**2.1.4** `[DERIVED]` The precedent already in `twig_bb/packs.json` matches:
the OpenArena packs are offered with the copyright field `OpenArena project, CC
BY-SA 3.0 / GPL; Debian main`, downloaded on request and read. The
Unvanquished content sits in the same category, and is if anything more
permissive, since several of its packages are CC0 or MIT.

**2.1.5** `[DERIVED]` The attribution obligation is discharged the way the
project already discharges it: a `copyright` field per pack (§3), shown on the
loading screen and in the acknowledgements. A pack whose terms cannot be stated
must not be offered — which rules out the packages in §1.5 unless §E.1 is
resolved.

#### 2.2 May it redistribute or bundle them?

**2.2.1** `[DERIVED]` For the map and texture packages of §1.1 that state terms:
yes, with attribution, and with the licence named and linked. CC BY, CC BY-SA,
CC0 and MIT all permit verbatim redistribution. Redistribution is a heavier
obligation than reading: the licence text or its URI must travel with the
content, authorship must be preserved, and any modification must be marked.

**2.2.2** `[DERIVED]` Bundling a CC BY-SA package inside a BSD-licensed
*distribution* does not relicense the BSD code. Mere aggregation of separately
licensed works in one archive leaves each under its own terms. What it does do
is oblige the aggregate's shipper to carry the attribution and licence notices
for each bundled package, and to keep the ShareAlike content identifiable so a
recipient can tell which files it covers.

**2.2.3** `[DERIVED]` Redistributing `tex-space` or `tex-vega` requires choosing
between the two offered licences (§1.1) and stating which was chosen, because a
recipient cannot otherwise tell which terms apply. Choosing the CC BY-SA 3.0
option is the one that keeps the aggregate free of a GPL obligation.

**2.2.4** `[DERIVED]` The base package `unvanquished_0.56.2` should **not** be
bundled. It is a mixed tree (§1.3, §1.4): CC BY-SA 2.5 media, a GPL-licensed
icon, MIT icons, a BSD Lua file, several font licences, and six compiled GPLv3
game-logic binaries in one archive. Redistributing it means discharging all of
those at once, including GPLv3 source-offer obligations for the binaries. A
viewer does not need it: no map package depends on it, and it holds menu art,
fonts and game logic rather than level content.

**2.2.5** `[DERIVED]` The packages of §1.5 must not be redistributed until their
terms are established. Downloading one at a user's request is a different act
from shipping it, and only the latter is blocked by the gap.

**2.2.6** `[DERIVED]` The recommendation for this project is therefore: offer
the map and texture packages as downloads (§2.1), and bundle nothing. That keeps
the viewer's own distribution BSD-only and leaves every attribution obligation
discharged by the acknowledgements screen.

**2.2.7** Every statement in §2.1 and §2.2 is a reading of licence names, not a
legal opinion. §2.1.3, §2.2.2 and §2.2.4 in particular are judgements. They are
escalated at §E.3.

### 3. Ready-to-use `copyright` fields

**3.1** `[DERIVED]` In the format `twig_bb/assetpack.py` documents: who holds it
and under what terms, then a semicolon, then where the content was packaged. The
first clause is what a map shows on one line while loading.

| Pack | `copyright` |
|---|---|
| `map-plat23` | `Jack "EmperorJack" Purvis, CC BY-SA 3.0; Unvanquished project packages` |
| `map-yocto` | `Pawel "Pevel" Micek, CC BY-SA 3.0; Unvanquished project packages` |
| `map-usstremor` | `Matthias "Masmblr" Peters and others, CC BY 4.0; Unvanquished project packages` |
| `tex-common` | `Stijn "Ingar" Buys and the Unvanquished team, CC0 1.0; Unvanquished project packages` |
| `tex-pk01` | `Philip Klevestav, CC BY 3.0; Unvanquished project packages` |
| `tex-pk02` | `Philip Klevestav, CC BY 3.0; Unvanquished project packages` |
| `tex-space` | `Stijn "Ingar" Buys, CC BY-SA 3.0; Unvanquished project packages` |
| `tex-vega` | `Stijn "Ingar" Buys, CC BY-SA 3.0; Unvanquished project packages` |
| `tex-ej01` | `Jack "EmperorJack" Purvis, CC BY-SA 3.0; Unvanquished project packages` |
| `tex-ex` | `Yves "evillair" Allaire, CC BY-SA 4.0; Unvanquished project packages` |
| `tex-exm` | `Yves "evillair" Allaire, CC BY-SA 4.0; Unvanquished project packages` |
| `tex-tech` | `Scott "Cr4zy" Coxhead, CC BY-SA 3.0; Unvanquished project packages` |
| `tex-trak5` | `Georges "TRaK" Grondin, MIT; Unvanquished project packages` |

**3.2** `[DERIVED]` `map-usstremor` credits six rights holders (§1.2). One line
cannot hold them, so the first clause names the level's author and the
`notes` field carries the rest — the acknowledgements screen prints the whole
entry. A suggested `notes`: *Textures by Philip Klevestav (CC BY 3.0) and Stijn
Buys; sounds by newlocknew (CC BY 4.0); Librestile font by ocelothe2k1 (OFL
1.1). Per-file detail in the package's own LICENSE and README.*

**3.3** `[DERIVED]` `tex-space` and `tex-vega` are offered under CC BY-SA 3.0
above rather than GPLv2, because the choice is the redistributor's (§1.1) and
this one keeps the pack free of a copyleft-code obligation. The `notes` field
should record that the author offers both.

**3.4** No `copyright` field is offered for the packages of §1.5, for
`tex-all`, or for the base package. A pack that cannot state its terms is
refused by `twig_bb.catalog`, and that is the correct outcome here.

### 4. Distribution

**4.1** `[OBSERVED]` Archive family: **zip**. Every `.dpk` opens as a ZIP
archive; the release bundle `unvanquished_0.56.2.zip` is a ZIP holding further
ZIPs. The older `.pk3` files on the same server are also ZIPs. In
`twig_bb/packs.json` terms, `"archive": "zip"` throughout.

**4.2** `[OBSERVED]` Canonical locations, all under `https://dl.unvanquished.net/`:

| Path | What it holds |
|---|---|
| `/pkg/` | every content package ever published, all versions, one flat directory |
| `/pkg/dev/` | development and hotfix packages, including the `bugfix_*` game-logic packages |
| `/release/` | one bundle zip per release, plus a `.sha512sum` beside each |
| `/current.txt` | the current release number as plain text |
| `/versions.json` | the same, as JSON, alongside the updater's version |

**4.3** `[OBSERVED]` Measured 2026-08-30 by HTTP HEAD against
`https://dl.unvanquished.net/pkg/<file>`. `Content-Length` in bytes.

| File | `Content-Length` |
|---|---|
| `map-plat23_1.14.dpk` | 3808627 |
| `map-usstremor_1.1.dpk` | 10573034 |
| `map-yocto_1.1.dpk` | 19103961 |
| `tex-all_2.3.dpk` | 519 |
| `tex-common_2.5.dpk` | 75195 |
| `tex-ej01_1.3.1.dpk` | 5481526 |
| `tex-ex_1.3.1.dpk` | 10928333 |
| `tex-exm_1.3.3.dpk` | 1964231 |
| `tex-pk01_1.3.1.dpk` | 4785909 |
| `tex-pk02_1.3.2.dpk` | 23618489 |
| `tex-space_1.3.dpk` | 16388337 |
| `tex-tech_1.3.1.dpk` | 18895689 |
| `tex-trak5_1.3.2.dpk` | 10311721 |
| `tex-vega_1.5.dpk` | 17669738 |
| `res-ambient_0.55.dpk` | 1205184 |
| `res-buildables_0.56.dpk` | 83013111 |
| `res-legacy_0.55.dpk` | 2410327 |
| `res-leveleditor_0.54.dpk` | 868 |
| `res-players_0.56.dpk` | 74442763 |
| `res-players_0.56.2.dpk` | 4131683 |
| `res-soundtrack_0.54.dpk` | 10104205 |
| `res-voices_0.56.dpk` | 1959972 |
| `res-weapons_0.56.dpk` | 57118818 |
| `res-weapons_0.56.2.dpk` | 131457 |
| `unvanquished_0.56.2.dpk` | 18503967 |

**4.4** `[OBSERVED]` `https://dl.unvanquished.net/release/unvanquished_0.56.2.zip`
answers HEAD with `Content-Length: 626828717`. It holds the whole release: the
33 content packages, seven per-platform engine archives, a symbol archive and a
`README.txt`. The content packages inside it total **526524010** bytes, so
roughly 100 MB of the download is engine binaries a viewer cannot use.

**4.5** `[OBSERVED]` **Smallest complete set that renders one playable map.**
Platform 23 with its declared dependency closure — four files, **43890648**
bytes (43.9 MB):

| URL | `Content-Length` |
|---|---|
| `https://dl.unvanquished.net/pkg/map-plat23_1.14.dpk` | 3808627 |
| `https://dl.unvanquished.net/pkg/tex-common_2.5.dpk` | 75195 |
| `https://dl.unvanquished.net/pkg/tex-pk02_1.3.2.dpk` | 23618489 |
| `https://dl.unvanquished.net/pkg/tex-space_1.3.dpk` | 16388337 |

**4.6** `[OBSERVED]` **Full asset set.** The 33 content packages of release
0.56.2, fetched individually from `/pkg/`, total **526524010** bytes (526.5 MB).
The file names are those in §4.3 plus the ten remaining release maps listed in
§7.3. Fetching them individually avoids the ~100 MB of engine binaries in the
release bundle (§4.4) and avoids `unvanquished_0.56.2.dpk`, which §2.2.4
recommends against; dropping that base package brings the set to **508020043**
bytes.

**4.7** `[OBSERVED]` Intermediate sets, for a viewer offering more than one map:

| Set | Packages | Bytes |
|---|---|---|
| all eleven release maps, no textures | 11 | 163380180 |
| every texture package (the `tex-all` closure) | 11 | 110119687 |
| all eleven maps + every texture package | 22 | 273499867 |
| the `res-*` model, sound and voice packages | 10 | 234518388 |

**4.8** `[OBSERVED]` The server supports HTTP range requests and reports
`Content-Type: application/octet-stream` and a `Last-Modified` for each package.
A package file at a given version-stamped name is immutable in practice: the
`Last-Modified` of `map-plat23_1.14.dpk` matches the release date of 0.56.0,
2026-03-23, and a new version gets a new file name rather than replacing the old
one.

### 5. Dependencies between packages

**5.1** `[OBSERVED]` A package declares its dependencies in a top-level `DEPS`
member: plain text, one dependency per line, each line a package name optionally
followed by whitespace and a version. Trailing blank lines occur.

**5.2** `[DERIVED]` A line naming a version identifies a *patch* package: the
small archive supplements a specific base version rather than replacing it. The
evidence is that `res-players_0.56.2.dpk` is 4.1 MB and holds two model files
with `DEPS` naming `res-players 0.56`, while the release ships both
`res-players_0.56.dpk` (74.4 MB) and `res-players_0.56.2.dpk`. A line with no
version names a package without constraining its version.

**5.3** `[OBSERVED]` Declared dependencies, as read from each package's `DEPS`:

| Package | `DEPS` |
|---|---|
| `map-plat23` | `tex-common`, `tex-pk02`, `tex-space` |
| `map-usstremor` | `tex-common`, `tex-pk01`, `tex-pk02`, `tex-space` |
| `map-yocto` | `tex-all` |
| `tex-all` | `tex-common`, `tex-ej01`, `tex-ex`, `tex-exm`, `tex-pk01`, `tex-pk02`, `tex-space`, `tex-tech`, `tex-trak5`, `tex-vega` |
| `tex-exm` | `tex-ex` |
| `tex-common`, `tex-ej01`, `tex-ex`, `tex-pk01`, `tex-pk02`, `tex-space`, `tex-tech`, `tex-trak5`, `tex-vega` | none — leaves |
| `res-ambient` | `res-legacy` |
| `res-legacy` | none |
| `res-players_0.56` | `res-legacy` |
| `res-players_0.56.2` | `res-players 0.56`, `res-legacy` |
| `res-buildables_0.56` | `res-legacy` |
| `res-buildables_0.54.1` | `res-buildables 0.54`, `res-legacy`, `res-players`, `res-weapons` |
| `res-weapons_0.56` | `res-buildables`, `res-legacy`, `res-players` |
| `res-voices_0.55.3` | `res-voices 0.54`, `res-legacy` |
| `res-leveleditor` | `tex-common`, `res-buildables`, `res-players`, `res-weapons` |
| `unvanquished_0.56.2` | `tex-common`, `res-players`, `res-weapons`, `res-buildables`, `res-voices`, `res-soundtrack`, `res-legacy` |
| `unvanquished_0.56.1` | `unvanquished 0.56.0` |

**5.4** `[OBSERVED]` **A map package alone does not render.** It carries its
level geometry, its lightmaps, its own custom textures and its shader scripts,
and it names shared texture sets it does not contain. `map-plat23_1.14.dpk` is
3.8 MB and needs 40 MB of shared textures to draw; `map-yocto_1.1.dpk` names the
`tex-all` meta package and so pulls in every texture set the project publishes,
110 MB more.

**5.5** `[OBSERVED]` Closure sizes, per map:

| Map | Closure | Packages | Bytes |
|---|---|---|---|
| Platform 23 | map + `tex-common`, `tex-pk02`, `tex-space` | 4 | 43890648 |
| USS Tremor | map + `tex-common`, `tex-pk01`, `tex-pk02`, `tex-space` | 5 | 55440964 |
| Yocto | map + `tex-all` and its ten members | 12 | 129223648 |

**5.6** `[DERIVED]` The `res-*` packages hold player models, buildable models,
weapons, voice lines and the soundtrack. No map package declares them. A viewer
that walks a level's geometry does not need them; a viewer that wants the
entities a running game would place does. They are also the packages whose terms
are unstated (§1.5), so they are the ones to leave out.

**5.7** `[DERIVED]` For `twig_bb/packs.json`, the natural shape is a map pack
with `companions` naming its texture packs — the mechanism the OpenArena entries
already use for exactly this relationship.

### 6. Installed copies

**6.1** `[DOCUMENTED]` **Flathub** publishes `net.unvanquished.Unvanquished`,
version 0.56.2, download size stated as 546 MiB
(https://flathub.org/apps/net.unvanquished.Unvanquished). Its build manifest
takes the packages from the same release zip named in §4.4 and installs the
package directory unchanged at `/app/pkg` inside the sandbox
(https://github.com/flathub/net.unvanquished.Unvanquished).

**6.2** `[DERIVED]` A Flatpak-installed copy therefore has the `.dpk` files, by
the same names as §4.3, at:

- system install: `/var/lib/flatpak/app/net.unvanquished.Unvanquished/current/active/files/pkg/`
- user install: `~/.local/share/flatpak/app/net.unvanquished.Unvanquished/current/active/files/pkg/`

The `files/` component is the standard Flatpak mapping of the sandbox's `/app`;
the `pkg/` component is `[DOCUMENTED]` from the manifest.

**6.3** `[OBSERVED]` A manual install from the release zip puts the packages at
`<wherever the user unpacked>/unvanquished_0.56.2/pkg/`. The bundle's own
`README.txt` instructs the user to unpack an engine archive alongside that
directory, so the engine executable sits beside `pkg/` rather than above it.

**6.4** `[DOCUMENTED]` **Debian ships nothing.** Repology lists Unvanquished in
AltLinux Sisyphus, AUR, Nixpkgs, openSUSE games and LibreGameWiki, and lists no
Debian or Ubuntu entry (https://repology.org/project/unvanquished/versions). A
search of the Debian package archive for the name returns nothing.

**6.5** `[DOCUMENTED]` **itch.io has no copy.** The page at
`https://unvanquished.itch.io/unvanquished` does not exist, and the itch.io
project named "Unvanquished" (https://hankportney.itch.io/unvanquished) is an
unrelated 2023 game-jam entry. Nothing on itch.io should be treated as this
project's assets.

**6.6** `[DOCUMENTED]` **Nixpkgs** carries 0.56.2 and records the licence set of
§1.8. Its store path is `[UNKNOWN]` and is not stable enough to probe for.

**6.7** `[UNKNOWN]` Where the game's own in-game updater places downloaded
packages on each platform. Establishing it would mean reading the engine or the
project wiki, and neither is available under this procedure. A viewer looking
for an installed copy should probe §6.2 and §6.3 and otherwise download.

### 7. Versioning

**7.1** `[OBSERVED]` A package file name is `<name>_<version>.dpk`. The version
is dotted decimal; map packages count independently of the game
(`map-plat23_1.14`), resource and texture packages likewise
(`tex-pk02_1.3.2`, `res-players_0.56.2`).

**7.2** `[OBSERVED]` The current release number is published as plain text at
`https://dl.unvanquished.net/current.txt`, which read `0.56.2` on 2026-08-30,
and as JSON at `https://dl.unvanquished.net/versions.json`, which read
`{"unvanquished": "0.56.2", "updater": "v0.2.1"}`. Either is a one-request way
for a viewer to learn the current release without parsing a directory listing.

**7.3** `[OBSERVED]` A release pins one exact version of every package. Release
0.56.2 pins: `map-antares_1.1`, `map-chasm_1.3`, `map-forlorn_0.16`,
`map-parpax_2.8`, `map-perseus_1.1`, `map-plat23_1.14`, `map-spacetracks_1.2`,
`map-station15_1.2`, `map-thunder_1.4`, `map-vega_1.5`, `map-yocto_1.1`,
`res-ambient_0.55`, `res-buildables_0.56`, `res-legacy_0.55`,
`res-leveleditor_0.54`, `res-players_0.56` **and** `res-players_0.56.2`,
`res-soundtrack_0.54`, `res-voices_0.56`, `res-weapons_0.56` **and**
`res-weapons_0.56.2`, `tex-all_2.3`, `tex-common_2.5`, `tex-ej01_1.3.1`,
`tex-ex_1.3.1`, `tex-exm_1.3.3`, `tex-pk01_1.3.1`, `tex-pk02_1.3.2`,
`tex-space_1.3`, `tex-tech_1.3.1`, `tex-trak5_1.3.2`, `tex-vega_1.5` and
`unvanquished_0.56.2`.

**7.4** `[OBSERVED]` The release bundle carries `pkg/md5sums`, an MD5 line per
package in the `md5sum` binary-mode format. That file is the authoritative
statement of which package versions constitute a release, and it lets a viewer
verify a downloaded package against the release it belongs to.

**7.5** `[OBSERVED]` `map-usstremor_1.1` is **not** in any release. It is on the
package server (dated 2024-04-10) but absent from the 0.56.2 bundle. A viewer
offering it is offering a community map, and should say so.

**7.6** `[DERIVED]` **Packages from different releases mix, with two provisos.**
Every version of a package remains on `/pkg/` and the flat namespace has no
per-release directories, so a `map-plat23_1.13.5` next to a `tex-pk02_1.3.2` is
an ordinary arrangement. The provisos: a patch package (§5.2) names the exact
base version it supplements and is meaningless without it; and a map compiled
against a texture set can lose surfaces if paired with a set that has since
renamed or dropped shaders. Pinning the versions of one release (§7.3, §7.4) is
what avoids the second, and is what a viewer should record in its catalogue.

**7.7** `[OBSERVED]` Version numbers are not comparable across package
families. `unvanquished_0.56.1` and `unvanquished_0.56.2` share a name and a
version series but hold entirely different content: the first is six compiled
game-logic binaries patching 0.56.0, the second a 496-member media package.
Reading a version number as a guide to what a file contains does not work.

## Escalations

Each of these needs a human decision. CLEAN-ROOM.md requires escalation when a
licence is unclear or a tree mixes licences, and all three cases arise.

**E.1** Nine packages state no licence at all (§1.5) — including every package
holding player, buildable and weapon models, the soundtrack, and the voice
lines. The project-wide CC BY-SA 2.5 statement in the base package's
`COPYING.txt` is the only terms that plausibly reach them, and Nixpkgs's licence
list (§1.8) is consistent with that reading, but neither is a statement by the
package. **Recommendation:** do not offer these packages until upstream states
their terms, and do not infer terms on their behalf. The maps and textures a
viewer actually needs are unaffected.

**E.2** `res-legacy` carries assets inherited from Tremulous (§1.6) and states
no licence for them. Tremulous's own terms are not established from any source
allowed here. This compounds E.1: `res-legacy` is a dependency of most other
`res-*` packages, so the gap propagates.

**E.3** The reasoning in §2 is a reading of licence names, not legal advice.
Three points are judgement rather than fact and should be confirmed by a human
before the project relies on them: that a renderer reading CC BY-SA content
creates no ShareAlike obligation (§2.1.3); that aggregating CC BY-SA content
into a BSD distribution does not relicense the BSD code (§2.2.2); and that the
base package's mixture (§1.3, §1.4) makes it unsuitable to bundle (§2.2.4). The
first two are the settled reading of these licences and match what the project
already does with the OpenArena packs; they are flagged because the consequence
of being wrong is a licence breach rather than a bug.

**E.4** `map-usstremor` states "GNU GPLv3, CC BY-SA 2.5" for one image and an
unversioned "Attribution License" for twenty-one files (§1.2). Neither is a
licence identifier a consumer can act on without guessing. The map is otherwise
clean and offerable; if it is offered, the `notes` field should name the
uncertainty rather than paper over it.

## Excluded

- **The engine and the game logic.** GPLv3, not read, not fetched, not
  described. Nothing in this spec depends on them.
- **The `.nexe` binaries** in `unvanquished_0.56.1.dpk`,
  `bugfix_0.52.1-...dpk` and `unvanquished_0.56.2.dpk`. Recorded as present and
  as game logic; not opened, not disassembled, not characterised beyond their
  size and name.
- **The project's build tooling and wiki.** Not consulted. The consequence is
  §6.7: where the in-game updater stores packages is left `[UNKNOWN]` rather
  than answered from a forbidden source.
- **Licence texts.** Named, never quoted beyond the name and the canonical URI.
  A consumer needing the terms should read them at creativecommons.org or from
  the `LICENSE` member of the package concerned.
- **Package contents beyond metadata.** File names, sizes and counts were read
  from ZIP directories; the only members whose content was read are `README.md`,
  `DEPS`, `about/*.txt`, `LICENSE`, `COPYING.txt`, the `license.md` files and
  `pkg/md5sums`.
