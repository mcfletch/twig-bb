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
