#! /usr/bin/env python
"""Tidy a modelled ``.blend`` and export the ``.glb`` the game ships.

Modelling leaves things behind.  A face extruded and undone, a mirror that
welded nothing, a curve converted to a mesh: the result is geometry that is not
part of the object any more but is still in the file, and normals that point
whichever way the operation that made them happened to leave them.  Neither is
visible in the viewport at the angle it was modelled from, and both are very
visible in a game -- a stray quad orbits a spinning pickup, and a face wound
the wrong way is lit from behind.

Three fixes to the geometry, each with a *rule* behind it rather than a
judgement, so running this twice changes nothing the second time:

* **Loose parts go.**  Every mesh keeps its largest connected component and
  drops the rest.  That is what "junk" means here and it is decidable from the
  geometry: the sphere a bubble is made of is one shell, and four vertices
  sharing no edge with it are not part of it.  A model that is *meant* to be
  several pieces should be several objects, which this leaves alone.
* **Normals face outward.**  Blender's own recalculation, applied to every
  mesh, so a face's front is its outside.  Backface culling, sheen and any
  lighting model that trusts the normal all read the same answer afterwards.
* **Holes are counted, and closed only when asked** (``--fill-holes``).  An
  open surface shows the *inside* of its far wall through the gap, which looks
  exactly like a face wound the wrong way and sends you hunting for a normal
  that is not there -- so an unclosed mesh always says so, loudly.  It is not
  closed by default because a leaf card, a banner and a curtain are open on
  purpose, and filling those would be the tool inventing geometry.

And one that is about where the pieces are rather than what they are:

* **Every piece turns about the same point** (``--concentric``).  A decoration
  modelled a few millimetres off the centre of the shell it sits inside spins
  about its own origin instead of the shell's, and *wobbles* -- which is
  invisible while modelling, because nothing is turning, and obvious the moment
  a pickup rotates on the spot.  This centres each mesh on its own origin and
  puts every origin on the centre of the largest one.

Nothing is decimated, re-topologised or welded; the vertices that survive are
the ones that were modelled.  ``--concentric`` is the only option that moves
one, and it moves it by a translation the object's origin follows.

Usage, either through a Blender install or through the ``bpy`` module -- the
same code runs both ways::

    blender medpack.blend --background --python tools/clean_model.py \\
        -- --export ../twitchoglc/assets/items/medpack.glb
    python tools/clean_model.py medpack.blend \\
        --export twitchoglc/assets/items/medpack.glb

The ``.blend`` is rewritten in place unless ``--save`` names somewhere else,
and left alone entirely under ``--no-save`` -- which, with ``--export``, is how
a shipped asset is regenerated without touching the art it came from.

**Needs Blender**, which the rest of this project does not: either an install
on the ``PATH`` or the ``bpy`` module, which is published for CPython 3.11 only
and is a large download.  Neither is a dependency of twitch and neither is
needed to *play* it -- the ``.glb`` this writes is committed, and this is how it
is regenerated when the art changes::

    uv venv --python 3.11 bpyenv && uv pip install --python bpyenv/bin/python bpy

Prints what it removed, filled, flipped and moved, because those numbers belong
beside the model in its ``CREDITS.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class Counts:
    """What one mesh had done to it, and what is still wrong with it.

    ``boundary`` is the count that is *reported rather than fixed*: an edge with
    one face beside it is a hole, and a hole is either a defect or the whole
    point of the model.  Nothing here can tell those apart, so it says so.
    """

    faces: int
    removed: int
    filled: int
    flipped: int
    boundary: int

    def line(self, name: str) -> str:
        note = ('%s: %d faces, removed %d loose, filled %d holes, flipped %d'
                % (name, self.faces, self.removed, self.filled, self.flipped))
        if self.boundary:
            note += (' -- STILL OPEN: %d boundary edge%s'
                     % (self.boundary, '' if self.boundary == 1 else 's'))
        return note


def _mesh_objects() -> List[Any]:
    """Every mesh in the open file, in a stable order."""
    import bpy
    return sorted((one for one in bpy.data.objects if one.type == 'MESH'),
                  key=lambda one: one.name)


def _components(bm: Any) -> List[List[Any]]:
    """The faces of one mesh, grouped by what is connected to what.

    Largest first, so the caller's "keep the first" is "keep the body of the
    thing".  Connectivity is through shared *vertices* rather than shared
    edges: two shells that meet at a single point are one object to anybody
    looking at them, and splitting them there would be a surprise.
    """
    seen: set = set()
    found: List[List[Any]] = []
    for start in bm.faces:
        if start.index in seen:
            continue
        group: List[Any] = []
        pending = [start]
        seen.add(start.index)
        while pending:
            face = pending.pop()
            group.append(face)
            for vertex in face.verts:
                for neighbour in vertex.link_faces:
                    if neighbour.index not in seen:
                        seen.add(neighbour.index)
                        pending.append(neighbour)
        found.append(group)
    found.sort(key=len, reverse=True)
    return found


def leave_edit_mode() -> None:
    """Put every object back into object mode.

    A ``.blend`` remembers the mode it was saved in, and art is usually saved
    from inside the edit session that made it.  A mesh left in edit mode has
    its geometry in the editor's own copy, and writing to it raises rather than
    quietly losing the edits -- so this is a precondition, not a tidy-up.
    """
    import bpy
    for obj in _mesh_objects():
        if obj.mode == 'OBJECT':
            continue
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.mode_set(mode='OBJECT')


def clean_mesh(obj: Any, fill_holes: bool = False) -> Counts:
    """Drop one mesh's loose parts and face its normals outward.

    ``fill_holes`` closes every open boundary loop first; see :func:`clean` for
    why that is asked for rather than assumed.  Filling happens *before* the
    recalculation, because "outward" is only a well-posed question about a
    closed surface -- on an open one Blender is left guessing from a raycast.

    Every count is zero for a mesh that was already tidy, which is what makes
    this safe to leave in a build.
    """
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()

    removed = 0
    groups = _components(bm)
    if len(groups) > 1:
        junk = [face for group in groups[1:] for face in group]
        removed = len(junk)
        bmesh.ops.delete(bm, geom=junk, context='FACES')
        bm.faces.ensure_lookup_table()

    filled = 0
    if fill_holes:
        open_edges = [edge for edge in bm.edges if len(edge.link_faces) == 1]
        if open_edges:
            made = bmesh.ops.holes_fill(bm, edges=open_edges, sides=0)
            filled = len(made.get('faces', ()))
            bm.faces.ensure_lookup_table()

    before = [tuple(face.normal) for face in bm.faces]
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    flipped = sum(1 for was, face in zip(before, bm.faces, strict=True)
                  if sum(a * b for a, b in zip(was, face.normal,
                                               strict=True)) < 0)

    boundary = sum(1 for edge in bm.edges if len(edge.link_faces) == 1)

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return Counts(faces=len(obj.data.polygons), removed=removed,
                  filled=filled, flipped=flipped, boundary=boundary)


def _local_centre(obj: Any) -> Any:
    """The middle of one mesh's own bounding box, in its own coordinates."""
    from mathutils import Vector
    coords = [vertex.co for vertex in obj.data.vertices]
    low = Vector((min(co[axis] for co in coords) for axis in range(3)))
    high = Vector((max(co[axis] for co in coords) for axis in range(3)))
    return (low + high) / 2.0


def _shift_location_keys(obj: Any, delta: Any) -> None:
    """Move an object's animated location by the same amount its origin moved.

    An origin that moves without its keyframes moving takes the object with it
    the moment the animation is played, which would undo the centring on frame
    one.  The offset is constant, so a path an object was animated along is
    still that path, in the new place.
    """
    action = getattr(getattr(obj, 'animation_data', None), 'action', None)
    for curve in getattr(action, 'fcurves', None) or ():
        if curve.data_path != 'location':
            continue
        step = delta[curve.array_index]
        for key in curve.keyframe_points:
            key.co.y += step
            key.handle_left.y += step
            key.handle_right.y += step
        curve.update()


def make_concentric(report: List[str]) -> None:
    """Centre every mesh on its origin, and every origin on the largest mesh.

    "Largest" is by the volume its bounding box encloses rather than by vertex
    count: the piece that gives a model its extent is the one the others sit
    inside, and a finely modelled decoration should not outvote the shell around
    it just for having more vertices.
    """
    objects = _mesh_objects()
    if not objects:
        return

    def extent(obj: Any) -> float:
        coords = [vertex.co for vertex in obj.data.vertices]
        if not coords:
            return 0.0
        size = [max(co[axis] for co in coords) - min(co[axis] for co in coords)
                for axis in range(3)]
        return size[0] * size[1] * size[2]

    biggest = max(objects, key=extent)
    middle = biggest.matrix_world @ _local_centre(biggest)

    for obj in objects:
        was = obj.location.copy()
        centre = _local_centre(obj)
        moved = (obj.matrix_world @ centre) - middle
        for vertex in obj.data.vertices:
            vertex.co -= centre
        placed = obj.matrix_world.copy()
        placed.translation = middle
        obj.matrix_world = placed
        _shift_location_keys(obj, obj.location - was)
        obj.data.update()
        report.append('%s: centred on %s, moved %.1f mm'
                      % (obj.name,
                         tuple(round(value, 4) for value in middle),
                         moved.length * 1000.0))


def clean(blend: Optional[str] = None, save: Optional[str] = None,
          export: Optional[str] = None, fill_holes: bool = False,
          concentric: bool = False) -> List[str]:
    """Open, tidy, and write; returns a line per mesh plus a line per file.

    ``fill_holes`` is asked for rather than assumed, because a hole is not
    always a mistake: a leaf card, a banner and a curtain are open surfaces on
    purpose, and closing them would be the tool inventing geometry.  A hole is
    always *counted*, though -- an unclosed surface shows the inside of its far
    wall through the gap, which reads exactly like a face wound the wrong way
    and sends you hunting for a normal that is not there.

    ``concentric`` comes last on purpose: it puts every origin on the centre of
    the largest mesh, and the largest mesh is only the right size once its loose
    parts have gone.  A stray face two metres away would otherwise decide where
    the whole model turns.
    """
    import bpy
    if blend:
        bpy.ops.wm.open_mainfile(filepath=os.path.abspath(blend))

    leave_edit_mode()
    report: List[str] = []
    for obj in _mesh_objects():
        report.append(clean_mesh(obj, fill_holes=fill_holes).line(obj.name))
    if concentric:
        make_concentric(report)

    if save:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(save))
        report.append('wrote %s' % (save,))
    if export:
        target = os.path.abspath(export)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        bpy.ops.export_scene.gltf(filepath=target, export_format='GLB')
        report.append('wrote %s (%.1f kB)'
                      % (export, os.path.getsize(target) / 1e3))
    return report


def _script_arguments(argv: List[str]) -> List[str]:
    """What the user meant, whether Blender or Python was the one launched.

    ``blender file.blend --python this.py -- --export x`` hands the whole
    command line through, and everything before ``--`` belongs to Blender.
    """
    return argv[argv.index('--') + 1:] if '--' in argv else argv[1:]


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('blend', nargs='?',
                        help='the .blend to open; omit when Blender already '
                             'opened it')
    parser.add_argument('--save', metavar='PATH',
                        help='where to write the tidied .blend '
                             '(default: over the one that was opened)')
    parser.add_argument('--no-save', dest='write', action='store_false',
                        help='leave the .blend alone; only export')
    parser.add_argument('--export', metavar='PATH',
                        help='also write a .glb here')
    parser.add_argument('--fill-holes', action='store_true',
                        help='close every open boundary loop; leave this off '
                             'for a model that is meant to be an open surface')
    parser.add_argument('--concentric', action='store_true',
                        help='centre every mesh on its own origin and every '
                             'origin on the largest mesh, so the model turns '
                             'as one piece instead of wobbling')
    options = parser.parse_args(_script_arguments(argv or sys.argv))

    save = None
    if options.write:
        save = options.save or options.blend
        if not save:
            parser.error('--save is required when Blender opened the file '
                         'and --no-save was not given')
    for line in clean(options.blend, save=save, export=options.export,
                      fill_holes=options.fill_holes,
                      concentric=options.concentric):
        sys.stdout.write(line + '\n')
    return 0


if __name__ == '__main__':                      # pragma: no cover
    sys.exit(main())
