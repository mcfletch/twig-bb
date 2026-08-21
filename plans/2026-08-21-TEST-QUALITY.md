# Test quality review, 2026-08-21

A review of `tests/` for runtime, organisation, shared code and robustness,
alongside the same review of `openglcontext`, `glisteel` and `glisteel-editor`.

## What was found

**The runtime is not a problem.** 2168 tests in 26 s, and the slowest single
test is 1.2 s. Nothing here drives a simulation for tens of seconds or bakes a
world, which is what the other two game suites spend their time on. There is
nothing to speed up.

**The assertions are not vacuous.** The six guarded `if ... : assert ...` blocks
in the suite are per-item filters inside loops -- "for each item, if it names a
weapon, then" -- rather than the shape that lets a test pass without testing
anything.

**The shared machinery is already shared.** `tests/bspbuilder.py` synthesises
`IBSP` files independently of the reader (which is the point: a test that fed
the reader its own dtypes would prove the dtypes are self-consistent), and
`tests/conftest.py` holds the map fixtures and the collection guard for the two
modules that need a GL backend to import at all.

**One file was doing too much.** `tests/test_viewer.py` was 2272 lines: the
command line, spawn placement, map yaw, the collision world, jump pads, texture
packs and their prompts, looking, walking, swimming, the key bindings, the mode
overlay, the jump report, dying and coming back, the weapon wheel, the
scoreboard, the match wiring, mouse aiming and four separate classes about where
a shot goes. Helpers were defined wherever they were first wanted, and used
several hundred lines away.

## What changed

Split by what a reader would come looking for:

| file | lines | what is in it |
|---|---|---|
| `tests/test_viewer.py` | 1315 | the command line, spawn placement, map yaw, collision, packs and prompts, looking, walking, swimming, keys and the mode overlay |
| `tests/test_viewer_match.py` | 837 | the match a player meets: dying and coming back, the wheel, the scoreboard, the match wiring, and where a shot goes |
| `tests/viewersupport.py` | 162 | what both make up: a synthetic map, a platform standing in it, and a context with no window whose input path still runs |

The helpers gained real names on the way out (`synthetic_map`,
`walking_platform`, `HeadlessContext`, `BindingRecorder`, `look_once`,
`NullInput`, `LookInput`, `NavStub`, `KeyEvent`, `walk_mode`), since a module
other files import from should not be a wall of leading underscores.
`tests/conftest.py` declines to collect the new module for the same reason it
declines the old one: importing it reaches `twig_bb.viewer`, which needs a GL
backend to build its context classes.

Same tests, same result: 2156 passed, 12 skipped, before and after.

## Still open

`tests/test_game.py` is 1094 lines and has the same shape of problem one size
down. It was left alone: the split above is worth doing where a reader cannot
find things, and a thousand lines on one subject is not yet that.
