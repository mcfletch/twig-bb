# Format specifications

Every format constant, layout and behaviour in this viewer cites a numbered fact
in one of these documents. **No Quake, ioquake3 or Alien Arena engine source was
read while writing the viewer**; these files are the only channel the format
knowledge came through, and each one records where its own facts came from.

| Spec | Covers |
|---|---|
| [SPEC-BSP38.md](SPEC-BSP38.md) | the `IBSP` v38 container — Quake 2 |
| [SPEC-BSP46.md](SPEC-BSP46.md) | the `IBSP` v46 container — Quake 3 |
| [SPEC-TRIGGER-PUSH.md](SPEC-TRIGGER-PUSH.md) | push volumes, monster jumps, world gravity, and `func_door` |
| [SPEC-Q3SHADER.md](SPEC-Q3SHADER.md) | Quake 3 `.shader` material scripts, including the animation family (§2.4, added 2026-07-27 from the same published manual) |
| [SPEC-Q3PUSH.md](SPEC-Q3PUSH.md) | v46 jump pads, which are aimed at a destination rather than pointed |
| [SPEC-Q3ENTITIES.md](SPEC-Q3ENTITIES.md) | v46 game entities — `target_speaker` (§1) and the pickups a map places (§3); the rest as they are built |

Two of them — `SPEC-BSP38` and `SPEC-TRIGGER-PUSH` — were written under the
clean-room procedure in [CLEAN-ROOM.md](CLEAN-ROOM.md): a Reader who wrote no
project code read the GPL source and produced a specification, and the
implementer read only the specification. The others needed no wall at all,
because their facts came from published documentation, this project's own
earlier BSD code, and the bytes of sample files.

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

`SPEC-LTMP` (Alien Arena's external `.lightmap` file) and `SPEC-RSCRIPT` (its
`.rscript` material scripts) were written and implemented, then removed along
with the code that read them: Alien Arena's art is licensed for use only within
its own engine, so its maps cannot be textured here and the format work led
nowhere viewable. Both remain in the git history if that ever changes.

If you extend the viewer and need a fact that is not here, **request a spec
revision** rather than looking it up in an engine. A constant in the code with no
fact behind it means either a gap in these documents or a fact that came from the
wrong side of the wall.
