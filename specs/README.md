# Format specifications

Every format constant, layout and behaviour in this viewer cites a numbered fact
in one of these documents. **No Quake, ioquake3, Alien Arena, Dæmon or
Unvanquished engine source was read while writing the viewer**; these files are
the only channel the format knowledge came through, and each one records where
its own facts came from.

| Spec | Covers |
|---|---|
| [SPEC-BSP46.md](SPEC-BSP46.md) | the `IBSP` v46 container — Quake 3 |
| [SPEC-TRIGGER-PUSH.md](SPEC-TRIGGER-PUSH.md) | push volumes, monster jumps, world gravity, and `func_door` |
| [SPEC-Q3SHADER.md](SPEC-Q3SHADER.md) | Quake 3 `.shader` material scripts, including the animation family (§2.4, added 2026-07-27 from the same published manual) |
| [SPEC-Q3PUSH.md](SPEC-Q3PUSH.md) | v46 jump pads, which are aimed at a destination rather than pointed |
| [SPEC-Q3ENTITIES.md](SPEC-Q3ENTITIES.md) | v46 game entities — `target_speaker` (§1) and the pickups a map places (§3); the rest as they are built |
| [SPEC-EXTLM.md](SPEC-EXTLM.md) | baked lightmap pages written beside a map instead of into its lightmap lump, and the deluxemap pages that interleave with them |
| [SPEC-CRN.md](SPEC-CRN.md) | the Crunch (`.crn`) block-compressed texture container |
| [SPEC-DPK.md](SPEC-DPK.md) | the `.dpk` package: its ZIP container, its name and version grammar, its `DEPS` dependency list, and its virtual filesystem |
| [SPEC-UNVASSETS.md](SPEC-UNVASSETS.md) | what Unvanquished packages hold, written as the delta from Quake 3: the map container, the content formats, the material-script keywords, the entity vocabulary |
| [SPEC-UNVDIST.md](SPEC-UNVDIST.md) | where those packages come from and on what terms, per package |

`SPEC-TRIGGER-PUSH` was written under the clean-room procedure in
[CLEAN-ROOM.md](CLEAN-ROOM.md): a Reader who wrote no project code read the GPL
source and produced a specification, and the implementer read only the
specification. The others needed no wall at all, because their facts came from
published documentation, this project's own earlier BSD code, and the bytes of
sample files.

The five documents covering Unvanquished content — `SPEC-DPK`, `SPEC-UNVASSETS`,
`SPEC-UNVDIST`, `SPEC-CRN` and `SPEC-EXTLM` — needed **no wall either**, and
that is the point of them. Rule 0 of `CLEAN-ROOM.md` puts copyleft source last,
and here the earlier alternatives carried the whole job: a corpus of fifteen
published packages, the population of package filenames on the download server,
the packages' own licence statements, and published format specifications. The
engine is GPLv3 and was never opened. Between them the three larger documents
record 270 numbered facts, and where the data did not settle a question they say
so and mark the implementation's answer a choice — `SPEC-DPK` §8 collects those
choices in one table.

Deriving from bytes is not the weaker route it might sound. A statement that a
lump length divides exactly by a record size, over 42 lumps and three maps, is
checkable by anyone holding the same files, and it does not go stale when the
engine is refactored.

`SPEC-Q3PUSH` goes one step further and is worth reading as an example: where a
fact could not be established from a permitted source, it says so and marks the
implementation's answer as a **choice** rather than dressing it up as the
original's behaviour. Its §3 lists what is still unknown.

`SPEC-Q3ENTITIES` follows that pattern and adds a marker legend, so `[OBSERVED]`,
`[DERIVED]`, `[CHOICE]` and `[UNKNOWN]` can be told apart at a glance. It is the
document that **grows**: a section is written when an entity is implemented.
`§3` (the pickups, added 2026-07-29) is the largest so far and is a good example
of the method — every classname and key in it was read out of the entity lump of
one of 67 shipped map files, the counts say how many of them carry each, and
what the content does not establish is marked `[UNKNOWN]` rather than guessed.
Its §3.3.2 and §3.6.2 are two such gaps that an implementation has to decide for
itself, and the code that decides them says so.

### Retired specifications

[SPEC-BSP38.md](SPEC-BSP38.md) (the `IBSP` v38 container — Quake 2) is **kept but
retired**: the v38 reader was removed — a testable v38 sample map is not cleanly
downloadable, so the format was dropped rather than maintained untested — but the
spec is left in place because dozens of shared modules still cite it for facts
true of the whole Quake lineage: the unit scale, the entity text syntax, yaw,
player height. Those citations are provenance, not a live reader.

`SPEC-LTMP` (Alien Arena's external `.lightmap` file) and `SPEC-RSCRIPT` (its
`.rscript` material scripts) were written and implemented, then removed along
with the code that read them: Alien Arena's art is licensed for use only within
its own engine, so its maps cannot be textured here and the format work led
nowhere viewable. Both remain in the git history if that ever changes.

If you extend the viewer and need a fact that is not here, **request a spec
revision** rather than looking it up in an engine. A constant in the code with no
fact behind it means either a gap in these documents or a fact that came from the
wrong side of the wall.
