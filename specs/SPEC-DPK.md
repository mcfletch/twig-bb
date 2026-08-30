# SPEC-DPK — the `.dpk` package container, its naming, and its virtual filesystem

| | |
|---|---|
| Source consulted | **None.** No copyleft source, documentation, wiki or build tooling was read, fetched, cloned or opened at any point in the production of this document. |
| Licence of source | not applicable |
| Version / commit | not applicable |
| Files consulted | 15 `.dpk` package files (data), 4 saved/fetched HTTP directory listings from `dl.unvanquished.net` (data), and the published PKZIP APPNOTE (§9) |
| Non-copyleft sources checked first | Rule 0 alternatives 1 and 2 of [CLEAN-ROOM.md](CLEAN-ROOM.md) were sufficient and nothing further was needed. Container facts come from the published ZIP specification plus the bytes of the corpus; naming, versioning, dependency and layout facts come entirely from the bytes and from the population of published filenames. |
| Reader | Claude Opus 5, working from data only |
| Date | 2026-08-30 |

**Status:** current.

**Provenance in one line:** every fact below was measured — from 1496 archive
entries across 15 packages, from 360 published package filenames, or from a
published, permissively usable format specification. Where the data does not
settle a question, the document says so and marks the implementer's answer a
**choice**, in the manner of [SPEC-Q3PUSH](SPEC-Q3PUSH.md) §2.3.

## Corpus

**C.1** Fifteen `.dpk` files, total 1496 archive entries:

| file | entries |
|---|---|
| `bugfix_0.52.1-20210624-032404-b3fe650-slipher.dpk` | 5 |
| `map-plat23_1.14.dpk` | 24 |
| `map-usstremor_1.1.dpk` | 161 |
| `map-yocto_1.1.dpk` | 195 |
| `res-ambient_0.55.dpk` | 47 |
| `res-buildables_0.54.1.dpk` | 7 |
| `res-leveleditor_0.54.dpk` | 3 |
| `res-players_0.56.2.dpk` | 3 |
| `res-voices_0.55.3.dpk` | 2 |
| `tex-all_2.3.dpk` | 2 |
| `tex-common_2.5.dpk` | 61 |
| `tex-pk02_1.3.2.dpk` | 299 |
| `tex-space_1.3.dpk` | 184 |
| `unvanquished_0.56.1.dpk` | 7 |
| `unvanquished_0.56.2.dpk` | 496 |

**C.2** Four HTTP directory listings of the package download server, giving 360
distinct filenames with publication dates and byte sizes: `/pkg/` (313 files),
`/pkg/dev/` (32), `/pkg/rocket/` (3), `/pkg/training/` (12). Of these, 182 are
`.dpk` names, 174 are `.pk3` names, and 4 are neither.

## Scope

What a third-party engine must know to open a `.dpk`, parse its filename into a
package name and a version, order two versions of the same package, read its
dependency list, and resolve an asset path against the set of loaded packages.

It does not cover the formats of the files *inside* a package: `IBSP` map
geometry is [SPEC-BSP46](SPEC-BSP46.md), material scripts are
[SPEC-Q3SHADER](SPEC-Q3SHADER.md), entities are
[SPEC-Q3ENTITIES](SPEC-Q3ENTITIES.md), and the `.crn` texture container is
[SPEC-CRN](SPEC-CRN.md).

---

## 1. The container

**1.1** [OBSERVED] A `.dpk` is a ZIP archive. All 15 files begin at offset 0 with
the four bytes `50 4B 03 04` — the local file header signature `PK\x03\x04`.

**1.2** [DOCUMENTED] That signature, and the local-header / central-directory /
end-of-central-directory structure the corpus uses, are specified by the PKZIP
Application Note, sections 4.3.7 (local file header, signature `0x04034b50`),
4.3.12 (central directory file header, `0x02014b50`) and 4.3.16 (end of central
directory record, `0x06054b50`).
<https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT>

**1.3** [OBSERVED] Nothing precedes the first local header and nothing follows
the end-of-central-directory record. In all 15 files the first `PK\x03\x04`
occurs at byte 0, and the end-of-central-directory record's offset plus its own
length equals the file size exactly. Self-extracting prefixes and appended
trailers do not occur.

**1.4** [OBSERVED] The central directory is contiguous and correctly located: in
all 15 files, the recorded central-directory offset plus the recorded
central-directory size equals the offset of the end-of-central-directory record.

**1.5** [OBSERVED] No ZIP64 structures occur. No entry in the corpus has a local
header offset, compressed size or uncompressed size above 4 GiB, and the largest
package is 23,618,489 bytes.

**1.6** [OBSERVED] Two compression methods occur across all 1496 entries: method
8 (deflate) on 1387 entries, and method 0 (store) on 109. No other method value
occurs. An implementation that supports store and deflate reads the whole
corpus.

**1.7** [DERIVED] Method choice is per entry and carries no meaning. Already-
compressed payloads (`.crn`, `.webp`, `.opus`) appear under both methods across
the corpus, and the choice tracks whichever tool produced the archive.

**1.8** [OBSERVED] No entry is encrypted. The general-purpose bit flag takes only
the values 0 and 2 across all 1496 entries; bit 0 (encryption) and bit 3
(sizes deferred to a data descriptor) are clear on every entry. Bit 1 — the
deflate compression-level hint — accounts for the value 2.

**1.9** [OBSERVED] Neither the archive comment nor any per-entry comment is used:
all 15 archive comments are empty and none of the 1496 entries carries a comment.

**1.10** [OBSERVED] "Version made by" is 63 (ZIP 6.3) on all 1496 entries. "Version
needed to extract" is 20 on deflated entries and 10 on stored entries, which is
the ordinary convention.

**1.11** [OBSERVED] The host-system byte of "version made by" is 3 (Unix) in 14
packages and 0 (FAT) in one (`map-usstremor_1.1.dpk`). The only extra field
present anywhere in the corpus is header id `0x000a` (NTFS timestamps), 161
occurrences, all in that same package. Nothing in the corpus requires an extra
field to be understood.

**1.12** [OBSERVED] Explicit directory entries — names ending in `/` with zero
content — occur in 1 of 15 packages (`map-usstremor_1.1.dpk`, 15 of them). The
other 14 packages carry file entries only and imply their directories. A reader
must therefore build the directory tree from the file paths and must tolerate,
but need not require, explicit directory entries.

**1.13** [OBSERVED] Entry paths are `/`-separated, relative, and free of
traversal. Across 1496 entries: no backslash, no leading `/`, no drive letter,
and no `..` path component.

**1.14** [OBSERVED] No package contains two entries with the same path.

**1.15** [OBSERVED] The central directory is not required to be sorted: its order
matches lexicographic order of the entry names in 5 of 15 packages and does not
in the other 10.

**1.16** [OBSERVED] Nothing in the container bytes distinguishes a `.dpk` from an
ordinary ZIP file. There is no signature beyond `PK\x03\x04`, no archive
comment, no reserved first entry and no sentinel. The only in-band marker is the
presence of a root entry named `DEPS` (§4), and that is present in 11 of 15
packages, so it cannot serve as an identity test.

**1.17** [DERIVED] Identity therefore rests on the filename extension and on
context. A package is what it is because it is named `*.dpk` and sits where
packages are looked for.

**1.18** [OBSERVED] The extension is not load-bearing on the server. One package
published at `/pkg/training/mod-training_0.31.0` carries no extension at all and
is nevertheless a ZIP archive with a root `DEPS` entry.

**1.19** [DERIVED] A conformant ZIP reader that supports store and deflate opens
every package in the corpus with no `.dpk`-specific code. Python's `zipfile`
opened all 15 and read every entry.

---

## 2. Package name and version grammar

Evidence for this section is the population of 360 published filenames (C.2);
the 15 corpus filenames are a subset of it.

**2.1** [OBSERVED] A package filename has the form

```
<name> "_" <version> ".dpk"
```

All 182 distinct `.dpk` filenames match it.

**2.2** [OBSERVED] `_` is the separator between name and version and occurs
exactly once. No filename in the population of 360 contains more than one `_`,
and only three contain none — `PAKSERVER`, `md5sums0.47` and a loose `DEPS`,
none of which is a package. Splitting on the first `_` and splitting on the last
`_` therefore give identical results on all observed data.

**2.3** [UNKNOWN] Which of the two splits the original intends is not decidable
from the corpus, because no observed name and no observed version contains a
`_`.
[CHOICE] Split on the **last** `_`. That keeps parsing total for a hypothetical
future name containing `_`, and the observed version alphabet (§2.7) makes an
underscore in the version the less likely of the two.

**2.4** [OBSERVED] `<name>` is drawn from lowercase ASCII letters, decimal digits
and `-`. Across the name part of all 182 `.dpk` filenames the characters that
actually occur are `a`–`y`, the digits `0 1 2 3 5`, and `-`. No uppercase letter
appears in any `.dpk` name.

**2.5** [OBSERVED] `<name>` conventionally carries a role prefix ending in `-`.
Counts over the 182 distinct `.dpk` filenames: `map-` 72, `tex-` 48, `res-` 42,
`mod-` 2, and 18 with no `-` at all. The undashed names are `unvanquished` (17
versions) and `bugfix` (1).

**2.6** [DERIVED] The prefix is a convention, not a syntactic requirement: names
without one exist, and the `-` is an ordinary name character (`map-spacetracks`,
`tex-ej01`, `map-methane-beta1` each carry one or two).

**2.7** [OBSERVED] `<version>` is drawn from decimal digits, `.` and `-`, plus
lowercase letters in the two irregular cases of §2.9. Across the version part of
all 182 `.dpk` filenames the characters that actually occur are the digits
`0`–`8`, `.`, `-`, and the letters `b d e f h i l p r s t y`.

**2.8** [OBSERVED] Shape of the 182 distinct versions:

| shape | count |
|---|---|
| `N.N.N` | 94 |
| `N.N` | 83 |
| `N` | 3 |
| anything else | 2 |

The three bare-`N` versions are `map-antares_1`, `map-perseus_1` and
`map-yocto_1`. No purely numeric version has four or more components.

**2.9** [OBSERVED] The two irregular versions, and what each shows:

- `res-weapons_0.54-dirty.dpk` — a numeric version followed by `-` and a
  lowercase word. It shows that a version need not be purely numeric and that
  `-` occurs inside a version, so a parser must not treat `-` as a name/version
  separator.
- `bugfix_0.52.1-20210624-032404-b3fe650-slipher.dpk` — a numeric version
  followed by four `-`-separated fields: a date `20210624`, a time
  `032404`, a seven-character lowercase hexadecimal token, and a lowercase
  author name. It shows that the tail after the first `-` is free-form, may
  contain several `-` separators, and may contain letters. This is the longest
  version in the population at 38 characters.

**2.10** [OBSERVED] Neither `+` nor `~` occurs in any of the 182 `.dpk` names.
Both occur in the older `.pk3` population on the same server — `+` in 34 of 174
`.pk3` names, `~` in 4 — as in `map-station15_1.0+1.pk3` and
`map-station15_1.0~1.pk3`. `.pk3` names also carry versions with no numeric part
at all (`map-nano_trem`, `map-forlorn_a13`, `mod-devserver_2015-01-04-0123-viech`)
and one uppercase name (`map-UTCS_trem`).

**2.11** [DERIVED] The `.pk3` names are a different, older population and their
conventions do not carry over. An implementation that parses only `.dpk` names
should not accept `+` or `~` on the strength of them.

**2.12** [DERIVED] Grammar, stated so it can be both parsed and generated:

```
filename  ::= name "_" version ".dpk"
name      ::= namechar+                 -- but see 2.13
namechar  ::= [a-z0-9-]
version   ::= vchar+
vchar     ::= [a-z0-9.-]
```

with the additional constraint from §2.2 that neither `name` nor `version`
contains `_`. To parse: strip the `.dpk` extension, split on the last `_`, take
the left as the name and the right as the version. To generate: reject a name or
version containing `_`, join with a single `_`, append `.dpk`.

**2.13** [DERIVED] A parser should accept a name or version whose characters fall
outside the observed sets rather than reject it — the sets in §2.4 and §2.7 are
what this population happens to contain, not a demonstrated restriction. The one
constraint the data does establish is the `_` count.

**2.14** [UNKNOWN] Whether the original imposes any further restriction on name
or version characters — a maximum length, a required leading letter, a
case-folding rule — is not established. Nothing in the corpus violates any such
rule, which is weak evidence either way.

**2.15** [OBSERVED] Filenames appear percent-encoded in the server's HTML
listings (`map-UTCS_trem%2B1.pk3` for `map-UTCS_trem+1.pk3`). That is ordinary
URL encoding applied by the web server and is not part of the filename.

---

## 3. Version ordering

**3.1** [OBSERVED] Thirty of the 32 distinct `.dpk` package names in the main
listing have more than one published version, giving 145 consecutive pairs when
each name's versions are placed in publication-date order.

**3.2** [OBSERVED] For all 145 pairs, publication order agrees with comparing the
versions as tuples of integers obtained by splitting on `.`, comparing
component-wise, and treating a proper prefix as the lesser. There is no
disagreement anywhere in the data. Representative sequences, with publication
dates:

- `map-antares`: `1` (2018-12-03), `1.0.1` (2021-05-09), `1.0.2` (2022-07-31),
  `1.0.3` (2023-01-30), `1.0.4` (2024-10-20), `1.1` (2026-03-23)
- `map-chasm`: `1.2` (2018-12-03), `1.2.1`, `1.2.2`, `1.2.3`, `1.2.4`,
  `1.3` (2026-03-23)
- `map-parpax`: `2.5.1`, `2.6.1`, `2.7`, `2.7.1`, `2.7.2`, `2.7.3`, `2.7.4`,
  `2.7.5`, `2.8`
- `unvanquished`: `0.51.1`, `0.52.0`, `0.52.1`, `0.53.0`, `0.53.1`, `0.53.2`,
  `0.54.0`, `0.54.1`, `0.55.0` … `0.56.0`, `0.56.1`, `0.56.2`

**3.3** [DERIVED] The two cases the shapes of §2.8 make interesting are both
settled in the same direction by §3.2:

- `1` before `1.0.1` — three package families (`map-antares`, `map-perseus`,
  `map-yocto`) each published a bare `1` first and a `1.0.1` afterwards.
- `1.2` before `1.2.1`, and `1.2.4` before `1.3` — nine families exhibit this,
  in the same 2018 → 2021 → … → 2026 release waves.

So the *intent* is unambiguous: a shorter version that is a prefix of a longer
one is the earlier of the two, and components compare numerically rather than
lexically (`1.13.5` precedes `1.14`, published 2024 and 2026 respectively).

**3.4** [UNKNOWN] The comparison the original engine performs is not established.
Publication order is the publisher's intent, not a measurement of engine
behaviour, and no engine behaviour was observed for this document. In particular,
whether the engine compares component-wise numerically, compares as strings, or
compares only for equality is not something data can settle.
[CHOICE] Compare component-wise as integers on `.`, shorter-prefix-lesser, per
§3.2. That is the rule the entire published population is consistent with, it is
total over the 180 purely numeric versions, and an implementation should document
it as its own choice rather than as the original's algorithm.

**3.5** [UNKNOWN] How a non-numeric version (§2.9) orders against anything is not
established. `res-weapons_0.54-dirty` was published between `0.53.0` and
`0.54.1`, and `bugfix_0.52.1-20210624-032404-b3fe650-slipher` is the only
version of its package, so neither yields a comparison rule.
[CHOICE] Treat a version that does not parse as a pure `N(.N)*` tuple as
incomparable: order it only for equality, and when a choice between builds must
be made, prefer the parseable one. Silently coercing `0.54-dirty` to `0.54` would
make it compare equal to a genuinely different release.

**3.6** [OBSERVED] Version strings are not zero-padded and components are not
bounded: `0.15` … `0.16` and `1.13.5` … `1.14` both occur. Comparing the
version strings lexicographically nonetheless agrees with §3.2 on **every**
pair in the published population — over the 180 purely numeric versions there
is no counter-example, `1.13.5` and `1.14` among them.

**3.7** [DERIVED] That agreement is a property of the versions published so
far, not of the grammar, and it breaks as soon as a component reaches two
digits while a sibling is at one: a `1.9` released before a `1.10` would order
the wrong way round as strings, and §2.8 permits both. Compare component-wise
as integers, per §3.4. The reason is that string comparison **would** fail, not
that it does.

**3.8** [OBSERVED] Version sequences have gaps. `tex-vega` publishes `1.4`,
`1.4.1`, `1.4.3`, `1.4.4`, `1.5` with no `1.4.2`. An implementation must not
assume it can enumerate the versions between two it knows about.

**3.9** [OBSERVED] Nothing inside a package records its own version. No entry
named for the version, and no metadata field, carries it in any of the 15
packages. One package contains a root file named `VERSION`
(`map-usstremor_1.1.dpk`, content `beta-1.1-002`), which does not match the
package version `1.1` and is the map author's own marking.

**3.10** [DERIVED] A package's version is therefore known only from its filename,
or from the name a dependency line gives it (§4.6). A package extracted from its
filename — into a directory, say — has lost its version.

---

## 4. The `DEPS` file

**4.1** [OBSERVED] Path inside the package: `DEPS`, at the archive root, spelled
in capitals, with no extension. Present in 11 of the 15 corpus packages, absent
in 4.

**4.2** [OBSERVED] The four packages with no `DEPS` are `tex-common_2.5`,
`tex-pk02_1.3.2`, `tex-space_1.3` and
`bugfix_0.52.1-20210624-032404-b3fe650-slipher`. A missing `DEPS` is normal and
means the package depends on nothing.

**4.3** [OBSERVED] `DEPS` is not required to be the first entry. Its index within
the archive is 0 in five packages, 1 in three, 2 in one, 3 in one, and 124 (of
496) in one.

**4.4** [OBSERVED] The content is ASCII text with LF line endings. Across the 11
files: no CR byte anywhere, no non-ASCII byte, and every file ends with a
newline. The largest is 91 bytes.

**4.5** [OBSERVED] Thirty-nine lines across the 11 files. Every line is one of two
shapes:

```
<package-name>
<package-name> <version>
```

Thirty-five lines carry a bare name; four carry a name and a version separated
by a single space (0x20). No line has three or more tokens, no tab occurs, and no
other separator occurs.

**4.6** [OBSERVED] The four versioned lines, each with the package that contains
them:

| container | line |
|---|---|
| `res-buildables_0.54.1.dpk` | `res-buildables 0.54` |
| `res-players_0.56.2.dpk` | `res-players 0.56` |
| `res-voices_0.55.3.dpk` | `res-voices 0.54` |
| `unvanquished_0.56.1.dpk` | `unvanquished 0.56.0` |

**4.7** [OBSERVED] All four name the containing package's *own* name at an
earlier version, and in all four cases that version is the immediately preceding
one published for that name. No line in the corpus names a *different* package
with a version attached.

**4.8** [OBSERVED] Each of those four packages is small relative to a full release
of the same name, and carries only a fragment of the content: 6 non-`DEPS`
entries in `res-buildables_0.54.1`, 2 in `res-players_0.56.2`, 1 in
`res-voices_0.55.3` and 6 in `unvanquished_0.56.1`. For comparison,
`unvanquished_0.56.2` carries 495.

**4.9** [DERIVED] A versioned self-reference marks an incremental package: it
carries only the files that differ from the named base version, and the base must
also be loaded for the result to be complete. `unvanquished_0.56.1` is six
executable modules and a `DEPS`; the 489 asset files of a full release are not in
it.

**4.10** [UNKNOWN] What a version on a line means when the named package is *not*
the containing package is not established, because the corpus contains no such
line. Whether it is a minimum, an exact requirement or a preference cannot be
determined from data.
[CHOICE] Read it as "at least this version", and if only an older version is
available, load it and report the shortfall rather than refusing. A hard equality
requirement would make `unvanquished_0.56.1` unusable the moment `0.56.0` were
superseded.

**4.11** [OBSERVED] Lines are not sorted. `unvanquished_0.56.2` lists
`tex-common`, `res-players`, `res-weapons`, `res-buildables`, `res-voices`,
`res-soundtrack`, `res-legacy` in that order; `res-leveleditor_0.54` lists
`tex-common`, `res-buildables`, `res-players`, `res-weapons`.

**4.12** [UNKNOWN] Whether line order carries meaning — a load order, a
precedence — is not established. Nothing in the corpus distinguishes an ordering
effect from an arbitrary one.
[CHOICE] Preserve the file's order when loading, so that if it does matter the
behaviour matches, and do not rely on it.

**4.13** [OBSERVED] No blank line occurs in any of the 11 files (no `\n\n`
sequence, and no trailing blank line beyond the single terminating newline). No
comment occurs — no line begins with `#`, `//` or `;`.

**4.14** [DERIVED] Blank-line and comment handling is therefore **not exhibited by
the corpus**, and this specification does not claim the original supports either.
[CHOICE] A reader should skip empty lines and strip surrounding whitespace,
because doing so cannot mis-handle any observed file and makes the parser
tolerant of hand editing. It should not invent a comment syntax: a line starting
with `#` should be treated as a package name, which is what the observed grammar
says it is.

**4.15** [OBSERVED] The dependency graph is not a tree and is not required to be
acyclic by anything visible in the data. `res-buildables_0.54.1` depends on
`res-players`, and `res-leveleditor_0.54` depends on both `res-buildables` and
`res-players`. `tex-all_2.3` depends on nine texture packages, and
`map-yocto_1.1` depends on `tex-all` alone, so resolution is transitive.

**4.16** [DERIVED] Resolution must therefore be a transitive closure with cycle
protection: collect each named package, read its own `DEPS`, and stop revisiting
a name already collected.

**4.17** [OBSERVED] A `DEPS` file also occurs loose on the download server, at
`/pkg/training/DEPS`, containing `unvanquished\n` — the same 13 bytes as the
`DEPS` entry inside the package published beside it. Its role is not established
here.

**4.18** [OBSERVED] The complete corpus of `DEPS` contents, so the grammar can be
checked against every sample:

| package | `DEPS` |
|---|---|
| `map-plat23_1.14` | `tex-common` / `tex-pk02` / `tex-space` |
| `map-usstremor_1.1` | `tex-common` / `tex-pk01` / `tex-pk02` / `tex-space` |
| `map-yocto_1.1` | `tex-all` |
| `res-ambient_0.55` | `res-legacy` |
| `res-buildables_0.54.1` | `res-buildables 0.54` / `res-legacy` / `res-players` / `res-weapons` |
| `res-leveleditor_0.54` | `tex-common` / `res-buildables` / `res-players` / `res-weapons` |
| `res-players_0.56.2` | `res-players 0.56` / `res-legacy` |
| `res-voices_0.55.3` | `res-voices 0.54` / `res-legacy` |
| `tex-all_2.3` | `tex-common` / `tex-ej01` / `tex-ex` / `tex-exm` / `tex-pk01` / `tex-pk02` / `tex-space` / `tex-tech` / `tex-trak5` / `tex-vega` |
| `unvanquished_0.56.1` | `unvanquished 0.56.0` |
| `unvanquished_0.56.2` | `tex-common` / `res-players` / `res-weapons` / `res-buildables` / `res-voices` / `res-soundtrack` / `res-legacy` |

(`/` stands for the line break; each file is one name per line.)

**4.19** [OBSERVED] Ten package names appear as dependencies but are not in the
corpus: `res-legacy`, `res-weapons`, `res-soundtrack`, `tex-pk01`, `tex-ej01`,
`tex-ex`, `tex-exm`, `tex-tech`, `tex-trak5`, `tex-vega`. All are published on the
server (§C.2), so a dependency name is an ordinary published package name and
nothing more.

---

## 5. The virtual filesystem

**5.1** [DERIVED] Every package contributes its entry paths, unchanged, to one
shared namespace. Nothing in a package prefixes or relocates its contents: an
entry at `textures/shared_pk02_src/trim01_d.crn` is addressed by exactly that
path regardless of which package holds it.

**5.2** [OBSERVED] Root directories across the 15 packages, with the number of
packages containing each and the total number of files beneath it:

| directory | packages | files | content observed |
|---|---|---|---|
| `scripts/` | 10 | 38 | `.shader` 28, `.txt` 8, `.particle` 2 |
| `about/` | 7 | 8 | `.txt` 8 — per-package credit and licence text |
| `textures/` | 6 | 606 | `.crn` 487, `.webp` 54, `.jpg` 47, `.tga` 17, `.txt` 1 |
| `gfx/` | 5 | 101 | `.crn` 81, `.webp` 17, `.md` 2, `.skin` 1 |
| `models/` | 4 | 36 | `.webp` 19, `.ase` 9, `.crn` 3, `.md3` 3, `.iqm` 2 |
| `maps/` | 3 | 44 | `.webp` 28 (lightmaps), `.navMesh` 11, `.bsp` 3, `.map` 2 |
| `sound/` | 3 | 18 | `.opus` 11, `.ogg` 6, `.wav` 1 |
| `meta/` | 3 | 6 | `.arena` 3, `.crn` 2, `.webp` 1 |
| `minimaps/` | 3 | 6 | `.minimap` 3, `.crn` 2, `.webp` 1 |
| `env/` | 2 | 186 | `.webp` 186 — skybox faces |
| `configs/` | 2 | 97 | `.cfg` 97 |
| `ui/` | 1 | 137 | `.crn` 66, `.rml` 55, `.rcss` 9, `.cfg` 3, `.txt` 2, `.md` 1, `.lua` 1 |
| `icons/` | 1 | 44 | `.crn` 44 |
| `sounds/` | 1 | 23 | `.opus` 23 |
| `bots/` | 1 | 22 | `.bt` 22 |
| `translation/` | 1 | 19 | `.po` 14, `.orig` 4, `.pot` 1 |
| `emoticons/` | 1 | 17 | `.crn` 17 |
| `fonts/` | 1 | 12 | `.ttf` 12 |
| `presets/` | 1 | 11 | `.cfg` 11 |
| `lights/` | 1 | 4 | `.crn` 4 |
| `voice/` | 1 | 1 | `.voice` 1 |
| `default/` | 1 | 1 | `.cfg` 1 |

**5.3** [OBSERVED] `sound/` and `sounds/` both occur. Three of the four packages
carrying audio use `sound/`; `map-usstremor_1.1` alone uses `sounds/`. Nothing
else in that package refers to the directory, so this is a naming variation in
one package rather than two recognised roots.

**5.4** [OBSERVED] Root-level files (not inside any directory), with the number of
packages carrying each:

| file | packages |
|---|---|
| `DEPS` | 11 |
| `README.md` | 10 |
| `cgame-{amd64,armhf,i686}.nexe`, `sgame-{amd64,armhf,i686}.nexe` | 2 each |
| `cgame-{x86,x86_64}.nexe`, `sgame-{x86,x86_64}.nexe`, `symbols.7z` | 1 each |
| `LICENSE`, `VERSION`, `COPYING.txt`, `GPL.txt`, `default.cfg`, `DELETED` | 1 each |

**5.5** [DERIVED] `DEPS` is the only root-level file with a defined meaning here
(§4). `README.md`, `LICENSE`, `COPYING.txt`, `GPL.txt` and `VERSION` are
human-readable text and carry no format role.

**5.6** [OBSERVED] One package (`unvanquished_0.56.2`) carries a root file named
`DELETED`, 53 bytes, holding a single line of two space-separated fields: a
package name and a path.
[UNKNOWN] Its role is not established. One sample, and the path it names is a
build-tree path rather than a virtual-filesystem path, so a reader cannot tell
from the data whether the engine consults it. An implementation should ignore it
and record the fact that it ignores it.

**5.7** [OBSERVED] Asset references *inside* content are virtual-filesystem paths
with the extension removed. Measured in the three maps of the corpus:

- The `IBSP` texture lump of `map-plat23`, `map-yocto` and `map-usstremor` holds
  54, 66 and 69 shader names respectively. Every name is either the literal
  `noshader` (once per map) or a rooted path with no extension: 182 begin
  `textures/`, 4 begin `models/`.
- `minimaps/yocto.minimap` refers to its image as `"minimaps/yocto"`.

**5.8** [OBSERVED] The extension a reference resolves to varies between packages
for the same role. The minimap image is `minimaps/yocto.crn` and
`minimaps/plat23.crn` in two maps and `minimaps/usstremor.webp` in a third; the
level shot is `meta/<map>/<map>.crn` in two and `meta/<map>/<map>.webp` in the
third.

**5.9** [DERIVED] An image reference is therefore resolved by trying a set of
candidate extensions against the stem. Under `textures/` alone the corpus holds 487 `.crn`,
54 `.webp`, 47 `.jpg` and 17 `.tga`, and `.crn` and `.webp` both occur under
`gfx/`, `meta/` and `minimaps/`, so all four must be candidates.

**5.10** [UNKNOWN] The order in which candidate extensions are tried, and what
happens when two exist for the same stem, is not established. No package in the
corpus contains two image files sharing a stem — the nine within-package stem
collisions are all between files of different kinds (`maps/plat23.bsp` and
`maps/plat23.map`; `minimaps/yocto.crn` and `minimaps/yocto.minimap`;
`ui/shared/window.rml` and `ui/shared/window.rcss`), never two images.
[CHOICE] Pick an order, prefer the compressed-texture container where the
renderer can use it, and document the order chosen.

**5.11** [OBSERVED] The paths a map's own content resolves against are `textures/`
and `models/` (§5.7), plus `scripts/` for the material definitions those names
are declared in (§6.4), `maps/` for the map itself and its lightmaps, `env/` for
skyboxes, `sound/` for audio, and `gfx/`, `meta/` and `minimaps/` for the map's
presentation images.

**5.12** [OBSERVED] Path case is significant to any exact-match lookup: 69 of 1496
entries contain an uppercase letter: 26 are root-level metadata files (`DEPS`,
`README.md`, `LICENSE`, `VERSION`, `COPYING.txt`, `GPL.txt`, `DELETED`), 11 are
`maps/usstremor-*.navMesh`, 10 are `fonts/*.ttf` with mixed-case family names,
and 22 are texture and sound files with camel-case stems
(`textures/.../metalBase01_d.crn`, `sound/.../30-60HzHum.opus`).

**5.13** [UNKNOWN] Whether lookups are case-sensitive, case-insensitive, or
case-folded is not established from data.
[CHOICE] Match case-sensitively first and fall back to a case-insensitive match,
so that content authored on a case-insensitive filesystem still loads. Record the
fallback when it fires; a reference that only matches case-insensitively is
usually an authoring error.

---

## 6. Package roles

Role is a matter of content and of the name prefix (§2.5); nothing in the
container marks it.

**6.1** [OBSERVED] **Map package** (`map-`, 3 in the corpus, 72 in the listing).
Contains `maps/<shortname>.bsp`, `meta/<shortname>/<shortname>.arena`, and
`minimaps/<shortname>.minimap`. All three corpus maps carry all three. Each also
carries `maps/<shortname>/lm_NNNN.webp` external lightmap pages (2, 10 and 16 across the
three — see [SPEC-EXTLM](SPEC-EXTLM.md)), `about/<something>.txt`, and a
`DEPS` naming the texture packages its materials come from. Two of three also
ship the editable `maps/<shortname>.map` source alongside the compiled `.bsp`.

**6.2** [OBSERVED] The `.arena` file is a brace-delimited key/value block naming
the map: keys `map`, `longname`, `author`, `type` in the sample read. The
`.minimap` file is a brace-delimited block with a `zone` sub-block containing
`bounds` (six floats) and `image` (a quoted extensionless VFS path followed by
four floats).

**6.3** [OBSERVED] **Texture package** (`tex-`, 3 in the corpus, 48 in the
listing). Contains `textures/` and/or `env/` payloads plus `scripts/*.shader`,
and no `maps/`, no `meta/`, no `minimaps/` and no executable module.
`tex-common_2.5` is 56 texture files and 3 scripts; `tex-pk02_1.3.2` is 295 and
2; `tex-space_1.3` is 180 skybox faces and 2 scripts.

**6.4** [OBSERVED] A texture package's material names and its image files live at
different paths. `tex-pk02_1.3.2` declares materials named
`textures/shared_pk02/*` in `scripts/shared_pk02.shader`, while every image file
in the package is under `textures/shared_pk02_src/`. The 53 `textures/…` shader
names referenced by `map-plat23`'s BSP match no file path in any corpus package;
they are material names to be looked up in the shader scripts.

**6.5** [DERIVED] A path in a BSP texture lump is therefore a *material* name
first and a file path only as a fallback. Resolution must consult the loaded
`scripts/*.shader` declarations before treating the name as a file stem.

**6.6** [OBSERVED] Three of the texture packages carry no `DEPS` at all (§4.2) —
a leaf in the dependency graph.

**6.7** [OBSERVED] **Resource package** (`res-`, 5 in the corpus, 42 in the
listing). Contains shared game content and no map: `models/`, `configs/`,
`scripts/`, `sound/`, `textures/`, `voice/`. Sizes range from
`res-players_0.56.2` (2 `.iqm` models) to `res-ambient_0.55` (47 entries of
textures, shaders and audio). All five carry a `DEPS`.

**6.8** [OBSERVED] **Meta-package.** `tex-all_2.3` contains exactly two entries:
`DEPS` (naming ten texture packages) and `README.md`. It ships no asset at all.
Its whole content is the dependency list.

**6.9** [DERIVED] A meta-package is recognised by having a `DEPS` and no asset
directories. It needs no special handling — resolving its dependencies yields
its content — but an implementation should not treat an empty asset set as an
error.

**6.10** [OBSERVED] **Base game package.** `unvanquished_0.56.2` carries 15 of
the 22 root directories seen anywhere in the corpus, six executable modules at
the root, `default.cfg`, and a `DEPS` naming seven resource and texture packages. It
is the package everything else is layered onto: the loose `DEPS` at
`/pkg/training/` and the `DEPS` inside `mod-training_0.31.0` both name
`unvanquished` and nothing else.

**6.11** [OBSERVED] **Incremental package.** `unvanquished_0.56.1`,
`res-players_0.56.2`, `res-buildables_0.54.1` and `res-voices_0.55.3` each carry
a versioned self-reference (§4.6) and a fragment of their own content (§4.8).
`unvanquished_0.56.1` and `unvanquished_0.56.2` share six root-level entry paths — the
`.nexe` modules — and all six differ in content, five of them at an identical
uncompressed size. The same path genuinely does occur in two packages bearing
the same package name.

**6.12** [OBSERVED] **Patch package for another package.** `bugfix_0.52.1-…`
carries four `.nexe` modules and a `symbols.7z` at the root, no `DEPS`, and no
asset directory. Its name has no role prefix and its version encodes a build
timestamp and a source revision (§2.9).

**6.13** [OBSERVED] `mod-` (2 `.dpk` in the listing) is a further prefix in use.
Neither is in the corpus; the one extensionless `mod-` package inspected
(`mod-training_0.31.0`) contains a `DEPS` naming `unvanquished`.

---

## 7. Search path and precedence

This section is mostly what data cannot show. Nothing here was measured against a
running engine.

**7.1** [OBSERVED] The same path occurs in more than one package. Across the 15
corpus packages, 9 paths are duplicated: `DEPS` (11 packages), `README.md` (10),
`scripts/shaderlist.txt` (7), and the six `.nexe` modules shared between the two
`unvanquished` versions.

**7.2** [OBSERVED] The colliding `scripts/shaderlist.txt` files have different
contents in every package: `map-yocto` holds three names, `tex-pk02` one,
`tex-common` two, `res-ambient` two. Whatever consumes that file must either
merge the seven or select one.

**7.3** [UNKNOWN] Whether the engine merges same-path files, takes the first, or
takes the last is not established. `scripts/shaderlist.txt` is a build-time file
for the map compiler and level editor, and the corpus gives no evidence the
engine reads it at all.

**7.4** [UNKNOWN] The precedence order between packages — whether a later-loaded
package shadows an earlier one, whether a dependency is searched before or after
the package that named it, and where a map package sits relative to the base
game package — is engine behaviour and cannot be derived from package bytes.
[CHOICE] An implementation must pick a rule and document it as a choice. The one
constraint the data does impose is §7.5.

**7.5** [DERIVED] An incremental package (§6.11) must take precedence over the
base version it names, or it has no effect: `unvanquished_0.56.1` exists to
replace the six modules that `unvanquished_0.56.0` also contains at the same
paths. Any precedence rule must satisfy "a package that names another version of
its own name in `DEPS` wins over that version".

**7.6** [UNKNOWN] Whether more than one version of the same package may be loaded
simultaneously, and what happens if two are present, is not established. §7.5
requires that at least the base and its increment coexist for the increment to
be meaningful, but that is one direction only.
[CHOICE] Load at most one version of each package name for versions reached as
ordinary dependencies, resolving to the highest per §3.4; treat a versioned
self-reference as the one case where a second version of the name is loaded
beneath the first.

**7.7** [UNKNOWN] Where packages are looked for on disk — the directory names, the
order of a user directory against a system directory, whether an unpacked
directory tree is searched alongside archives — is not established. Nothing about
it is visible in package bytes or in a server listing.

**7.8** [UNKNOWN] Whether a package's `DEPS` is honoured transitively at load time
or only used by a downloader is not established. §4.15 shows the graph is
transitive as *published* (a map names `tex-all`, which names ten texture sets,
which hold the images the map's materials use), which is enough to require
transitive resolution somewhere, but not enough to say where.

**7.9** [OBSERVED] The download server advertises unrestricted download: the file
`/pkg/PAKSERVER` contains the single token `ALLOW_UNRESTRICTED_DOWNLOAD`.
[UNKNOWN] How that token is consumed is not established.

---

## 8. Summary of what an implementation must choose

Each of these is a decision the data leaves open. Cite the fact number and record
the decision as the implementation's own.

| § | Question | Safe choice |
|---|---|---|
| 2.3 | first or last `_` when splitting a filename | last |
| 3.4 | version comparison algorithm | component-wise integer, shorter prefix lesser |
| 3.5 | ordering a non-numeric version | incomparable; prefer the parseable build |
| 4.10 | meaning of a version on a foreign dependency line | minimum, with a reported shortfall |
| 4.12 | whether `DEPS` line order matters | preserve it, do not rely on it |
| 4.14 | blank lines and comments in `DEPS` | skip blanks; invent no comment syntax |
| 5.6 | the `DELETED` root file | ignore, and say so |
| 5.10 | extension search order for an image reference | fixed documented order |
| 5.13 | path case sensitivity | exact first, case-insensitive fallback, logged |
| 7.4 | package precedence | documented rule satisfying §7.5 |
| 7.6 | two versions of one package loaded at once | one, except a versioned self-reference |
| 7.7 | on-disk search path | implementation's own |

---

## 9. References

- PKZIP Application Note (`APPNOTE.TXT`), PKWARE — the ZIP container structures
  cited in §1.2.
  <https://pkware.cachefly.net/webdocs/casestudies/APPNOTE.TXT>
- ISO/IEC 21320-1:2015, *Document Container File — Part 1: Core*, which profiles
  the same structures and restricts conforming containers to methods 0 and 8 —
  the two methods §1.6 measures.
- [SPEC-BSP46](SPEC-BSP46.md) — the `IBSP` version 46 map format whose texture
  lump §5.7 measures.
- [SPEC-EXTLM](SPEC-EXTLM.md) — the external lightmap pages under
  `maps/<shortname>/`.
- [SPEC-Q3SHADER](SPEC-Q3SHADER.md) — the material scripts under `scripts/`.
- [SPEC-CRN](SPEC-CRN.md) — the `.crn` texture container, the most common payload
  in the corpus at 706 of 1496 entries.

## 10. Excluded

**10.1** No fact about engine internals is recorded. Sixteen questions are marked
`[UNKNOWN]` — §2.3, §2.14, §3.4, §3.5, §4.10, §4.12, §5.6, §5.10, §5.13 and the
whole of §7 — and the twelve of them that an implementation cannot avoid
answering carry a stated choice, collected in §8.

**10.2** The contents of the executable modules (`*.nexe`) were not examined
beyond their entry names and sizes. They are compiled program code, and their
format is out of scope.

**10.3** The `symbols.7z` payload in `bugfix_0.52.1-…` was not opened.

**10.4** The `.pk3` population is described only where it contrasts with `.dpk`
naming (§2.10, §2.11). Its own conventions are not specified here.

**10.5** No file under any quarantine directory in this workspace was read, and
no repository, wiki, documentation page or build tool belonging to the engine or
game project was fetched, cloned or opened. Every HTTP request made went to
`dl.unvanquished.net`: the directory listings `/pkg/dev/`, `/pkg/rocket/` and
`/pkg/training/`, and the data files `/pkg/PAKSERVER`, `/pkg/training/DEPS` and
`/pkg/training/mod-training_0.31.0`.
