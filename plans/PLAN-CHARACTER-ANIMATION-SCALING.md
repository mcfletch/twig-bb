# Plan — scale animated characters to the hundreds

**Status:** 🟡 Partial — the load path is fixed and landed in the engine; the
per-frame animation path and off-thread loading are designed here, not yet built.

**Goal (engine-level).** A game built on OpenGLContext can put **hundreds of
skinned, animated characters** on screen and animate them in parallel without the
frame rate or the load time falling over. twig-bb is the demo that exercises this;
the bar is *"fast enough for any reasonable game a developer might build on the
engine,"* not *"fast enough for this demo."* Every capability below therefore
lands in **OpenGLContext** (or PyOpenGL) as a proper, owned API, and twig-bb
merely calls it — see [../CLAUDE.md](../CLAUDE.md), "The product is the engine."

**Who this is for.** A machine with a permanent network connection, which can do
what this dev container cannot: fetch the glTF sample models and **bless the
conformance baselines** (`oglc-gltf-regression --bless`), pull character LOD
assets, install profilers, and run long GPU benchmarks on real hardware. Pick up
at [§4 Task board](#4-task-board).

---

## 1. The symptom, measured

twig-bb grew combatants drawn as skinned figures (commits `f36b321`,
`a0fa32…`). Two regressions appeared, both rooted in the **engine**, not the demo:

| Symptom | Measured cause |
|---|---|
| "Play" → map load feels **frozen** (seconds) | Each `CharacterModel.load` of a ~1.5 MB rig cost **~2.9 s**, ~97 % of it in `pygltflib`'s `dataclasses_json` JSON→object decode. The rig has 2462 accessors / 2465 bufferViews / 3933 animation channels; `dataclasses_json` runs `get_type_hints`+`issubclass` **per object**. `json.loads` of the same bytes: **0.014 s**. |
| Frame rate **~12 fps** (was 20–30) on integrated graphics | `CharacterModel.update(dt)` costs **~6.7 ms per figure per frame** — mixer `_apply_layer`, glTF `animation.apply`/`walk`, per-bone TRS matrix rebuild, and `PBRMesh._apply_deform` (CPU linear-blend skinning via `np.einsum`), followed by a dynamic-VBO re-upload. It runs for every figure every frame regardless of distance or visibility. Four visible bots ≈ 27 ms/frame in animation alone. |

Per-frame profile of one figure's `update` (60 frames), hottest first:
`animation.apply` (0.062 s) · `einsum` skinning (0.059 s) · TRS `rotMatrix`/
`transMatrix`/`scaleMatrix` rebuild (0.07 s combined) · `PBRMesh._apply_deform`
(0.026 s). No GPU skinning exists anywhere in the engine today: skinning is CPU
`np.einsum` in `PBRMesh._apply_deform`, uploaded per frame through
`_MeshGPU.update_dynamic` (`glBufferSubData`) keyed on `_deform_version`.

---

## 2. What has already landed (engine)

Both in `openglcontext/`, on branch `develop`, fully tested (`ruff`/`mypy`
clean on the touched files; the one remaining `mypy` note is the pre-existing
`_require_pygltflib` return, untouched here).

### 2.1 Fast glTF decode — the load freeze

`OpenGLContext/loaders/gltf/fastdecode.py` (new) builds the pygltflib object
graph directly from `json.loads`, resolving each of the 28 reachable dataclasses'
field types **once** and caching the plan — the cache `dataclasses_json` lacks.
`Attributes` (the one non-dataclass, arbitrary vertex-attribute names) is rebuilt
from its dict; a list of `Attributes` (morph targets) stays raw dicts to match
pygltflib exactly. `loader.py` routes every decode (`.glb`, `.gltf`, path, URL)
through it, with a **logged fallback** to pygltflib for any unforeseen document
shape.

- **Result:** a full `CharacterModel.load` went **2.87 s → 0.149 s** (~19×); the
  decode itself ~2.9 s → ~0.05 s. Benefits *every* glb the engine loads (weapons,
  items, tiles, characters) with **no caller change** — twig-bb already gets it.
- **Tests:** `tests/unit/test_gltf_fastdecode.py` — equivalence to
  `pygltflib.GLTF2.from_json` over a document exercising every shape, custom
  attributes, morph targets, GLB blob, malformed inputs.

### 2.2 Shared document — one asset, many instances

`loader.parse_gltf(source) -> SharedDocument` parses once; `load_gltf(document=…)`
builds a fresh, independent scenegraph from it. Decoded **immutable** arrays
(vertex positions/normals/tangents/weights and animation keyframes) are memoised
on the shared document (`accessors.py`, keyed by `(kind, index)`) and marked
**read-only**, so every instance references the same base data while owning its
own materials and its own deformable-mesh state. Exposed from
`OpenGLContext.loaders.gltf` (`parse_gltf`, `SharedDocument`).

- **Result:** four male figures from one parse = **0.28 s total (~0.07 s each
  after the parse)** vs 0.58 s as independent loads — and the rig's vertex/keyframe
  arrays exist **once in memory** instead of once per figure. Combined with 2.1:
  four figures of a build went from ~11.5 s (original) to ~0.28 s.
- **Tests:** `tests/unit/test_gltf_shared_document.py` — equivalence to a plain
  load, shared-array identity, read-only enforcement, instance independence.

**Not yet wired into twig-bb:** the `Cast` still calls `CharacterModel.load(path)`
once per figure. Task **A** below wires it to `parse_gltf`.

---

## 3. Design for hundreds of characters

The load path is now cheap and shares memory. Scaling the **per-frame** cost is
the substance of the goal. Four levers, cheapest-first; C4 is the one that makes
"hundreds" routine.

### C1 — Don't animate what no one sees (LOD + update budget)
The engine should not spend a full skin+re-upload on a figure that is off-screen,
tiny, or far away. Build into OpenGLContext a **character LOD/update policy**:
- Skip or decimate `update()` for figures outside the frustum or beyond a
  distance, holding their last pose (a distant figure updated at 10 Hz reads
  fine).
- Use the `*_lod1.glb` variants that already ship beside each character but which
  `characters.load` never selects; pick LOD by screen-space size.
- A per-frame **animation budget**: N figures, cap the CPU-skin work per frame and
  round-robin the remainder. This is an engine scheduler, not a demo hack.

### C2 — Evaluate a clip once, not once per figure
Many figures play the same clip (`idle`, `run`) at the same phase. Sampling a
clip to a pose is independent of which body wears it. Cache/dedupe **pose
evaluation** by `(clip, time-quantised)` so a crowd of idlers samples one pose,
then each body applies its own world transform. Lands in
`OpenGLContext.character.mixer` / `loaders/gltf/animation`.

### C3 — Parallelise / batch the CPU skin (interim, if C4 slips)
`_apply_deform`'s `np.einsum` releases the GIL. Either **batch** all same-build
figures into one vectorised einsum (shared bind mesh from §2.2, stacked joint
palettes), or run per-figure deforms across a thread pool. Interim headroom while
C4 is built; keep behind the same engine API so callers don't change.

### C4 — GPU skinning (the real answer)
Move linear-blend skinning into the **vertex shader**. §2.2 already gives every
instance a **shared, read-only bind mesh** (positions/normals/`JOINTS_0`/
`WEIGHTS_0` all decoded once) — the exact input GPU skinning wants. Per frame,
upload only the **per-instance joint-matrix palette** (a UBO or a matrix texture),
not deformed vertices. This deletes both the per-frame `einsum` **and** the
per-frame `glBufferSubData` re-upload — the two dominant costs in §1.
- New shader path alongside the PBR pass; attributes `JOINTS_0`/`WEIGHTS_0` at
  fixed locations; skin matrices from the palette. Floor: GL 3.3 for the base
  path (palette as a UBO or `RGBA32F` texture).
- `PBRMesh` keeps the CPU `_apply_deform` as the fallback for drivers/paths that
  can't skin on the GPU (headless byte-stable reference renders may want it).

### C5 — Instanced skinned draw
With C4, identical-build figures share one bind mesh and one material; draw them
as **one instanced call** with a per-instance palette (extend the existing
instancing batcher, which today handles only static meshes —
`passes/instancing.py`). This is what turns hundreds of draws into a handful.

### Off-thread loading (kills any residual freeze)
Even at 0.07 s/figure, a hundred figures is seconds — and it must not run in the
render loop. The engine already has the pattern (`OpenGLContext/bin/view.py`
async load; `loaders/tiles3d/loadmanager.py`). Generalise it into a **reusable
background-load facility**: the worker thread runs `parse_gltf` + `load_gltf`
(both **GL-free** — verified; GL uploads happen lazily at first draw), the render
thread mounts the result when ready. In twig-bb, figures start as the existing
capsule fallback and **swap to the rig when its load posts** — no frozen frame,
ever.

---

## 4. Task board

Ordered. Each task is TDD, `ruff`/`mypy`-clean on touched paths, and ships its
docs (engine docs live in `openglcontext/docs/`, this plan and
`openglcontext/plans/PROJECT-PLAN.md` get status updates).

| # | Task | Lands in | Notes |
|---|---|---|---|
| **A** | Wire `Cast` to `parse_gltf`: parse each distinct build once, pass `document=` to every figure of it | twig-bb `characters.py` | Small; uses the shipped §2.2 API. Test: two ids of one build share `_base_positions`. |
| **B** | Reusable background-load facility; twig-bb figures load off-thread, capsule→rig swap | OpenGLContext + twig-bb | Generalise `bin/view.py` async pattern. GL only on the render thread. |
| **C1** | Character LOD + per-frame update budget; use `*_lod1.glb`; skip off-screen/distant | OpenGLContext.character | Biggest cheap win for crowds. |
| **C2** | Dedupe pose evaluation by `(clip, quantised time)` | OpenGLContext.character.mixer | |
| **C4** | GPU skinning vertex-shader path (+ CPU fallback) | OpenGLContext passes + pbrmesh | The scalability keystone. |
| **C5** | Instanced skinned draw for same-build figures | OpenGLContext.passes.instancing | Depends on C4. |
| **C3** | Batched/threaded CPU skin | OpenGLContext.pbrmesh | Only if C4 is delayed; interim headroom. |

### Acceptance
A **benchmark scene** (new, in `openglcontext/tests/` or `twig-bb/tools/`) of
100 / 250 / 500 skinned characters, each animating, on both integrated (Intel
UHD-class) and discrete GPUs. Target: interactive frame rate (≥ the auto-preset's
60 fps goal — keep shadows; see the forest-demo preset work) at 250, and no load
stall regardless of count. Record before/after per-frame `update` cost and draw
count. The network machine runs the **full gltf conformance suite with blessed
baselines** to prove none of C1–C5 shifted rendered output (the two known-flaky
timing/IBL tests excepted — see `openglcontext/CLAUDE.md`).

### Constraints & non-negotiables
- **Engine-first:** no capability a real game would want may live in twig-bb. If
  the demo needs it, build it in OpenGLContext and have the demo call it.
- **Correctness before speed:** the CPU deform stays as the reference/fallback;
  GPU skinning must match it within the conformance tolerance.
- **GL floor:** base path GL 3.3; advanced paths GL 4.1 + `ARB_texture_storage`
  (see `openglcontext/CLAUDE.md`). Skin-palette upload must respect the 3.3 floor.
- **Licensing:** glTF is an open spec and the character assets are ours — no
  clean-room concern here, unlike the Quake-format work (§ CLEAN-ROOM).
- **No destroying work to experiment** — benchmark in a worktree/scratch copy,
  never over the live tree ([../CLAUDE.md](../CLAUDE.md)).

---

## 5. Landmarks in the code

- Decode: `openglcontext/OpenGLContext/loaders/gltf/fastdecode.py`,
  `loader.py` (`parse_gltf`, `SharedDocument`, `_decode_document`),
  `accessors.py` (`_shared`/`_keep` memo).
- Skinning today: `OpenGLContext/scenegraph/pbrmesh.py` (`_apply_deform`,
  `_deform_version`, `_MeshGPU.update_dynamic`); mixer in
  `OpenGLContext/character/mixer.py`; clip sampling in
  `loaders/gltf/animation.py`.
- Character API: `OpenGLContext/character/model.py` (`CharacterModel`).
- Instancing (static today): `OpenGLContext/passes/instancing.py`.
- Async precedent: `OpenGLContext/bin/view.py`,
  `loaders/tiles3d/loadmanager.py`.
- Demo side: `twig_bb/characters.py` (`Cast`, `Character`, `Armoury`),
  `twig_bb/game.py` (`move_bodies` → `cast.update`), `twig_bb/viewer.py`
  (`_buildMatch` builds the `Cast`).
