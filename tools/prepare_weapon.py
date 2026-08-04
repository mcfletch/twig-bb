#! /usr/bin/env python
"""Turn a source weapon model into one small enough to commit.

The route for a model this project did not build.  Art arrives as a `.glb` with
2048x2048 PBR maps embedded -- eight or nine megabytes for one gun, which is not
a thing to put in a source repository.  This trims one to something
proportionate:

    python tools/prepare_weapon.py in.glb out.glb --textures 512
    python tools/prepare_weapon.py in.glb out.glb --strip-textures

Two jobs, and which one is wanted depends on the source:

* ``--textures N`` **resamples** every embedded image to at most N pixels on a
  side.  A weapon held at the edge of the screen or seen across a room does not
  resolve 2048 pixels of rust, and 512 is already generous.
* ``--strip-textures`` removes them altogether and leaves a plain metallic
  material.  For a model whose maps are *wrong* -- a batch conversion binding
  one model's textures onto another is a common way for a pack to arrive -- a
  clean grey gun is honest and reads better than a rifle wearing a landmine.

Neither touches the geometry: the mesh, its normals and its UVs come through
untouched, so re-running with better maps later is a re-run rather than a
re-model.

Requires ``pygltflib`` and ``Pillow``, both already dependencies of the test
environment.  Prints what it did, because the numbers belong in
``twig_bb/assets/weapons/CREDITS.md`` beside the model.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

#: What an imported model's maps are resampled to unless told otherwise.  Big
#: enough that a weapon held at the camera still reads, small enough to commit.
DEFAULT_TEXTURE_SIZE = 512

#: The material a stripped model is given: dark, half metallic, fairly rough --
#: blued steel rather than chrome.  A high metallic with a low roughness under
#: an environment probe reads as a mirror, and a mirror-finish rifle looks like
#: a mistake rather than like blocked-out art.
STRIPPED_BASE_COLOR = (0.30, 0.30, 0.32, 1.0)
STRIPPED_METALLIC = 0.5
STRIPPED_ROUGHNESS = 0.55

#: A little light of the model's own, added to every material.  A map places no
#: dynamic lights -- it is lit by the lightmaps its author baked -- so a weapon
#: held in front of the camera is lit by almost nothing and renders as a
#: silhouette.  The obvious fix, a light riding the camera, lights the *map*
#: as well, and washing out the baked lighting to show one gun is the wrong
#: trade.  A small emissive floor is per-material: it touches this model and
#: nothing else in the world.  Small enough not to glow in a lit room.
DEFAULT_FILL = 0.07


def _image_bytes(gltf: Any, index: int) -> Tuple[bytes, Any]:
    """The raw bytes of one embedded image, and the buffer view it came from."""
    image = gltf.images[index]
    view = gltf.bufferViews[image.bufferView]
    blob = gltf.binary_blob()
    start = view.byteOffset or 0
    return (bytes(blob[start:start + view.byteLength]), view)


def resample(data: bytes, limit: int) -> Optional[bytes]:
    """One image resampled to at most ``limit`` on a side; None if it already is.

    Re-encoded as PNG regardless of what it arrived as, because the sources are
    PNG and a second format in the file buys nothing.
    """
    from PIL import Image
    image = Image.open(io.BytesIO(data))
    if max(image.size) <= limit:
        return None
    scale = limit / float(max(image.size))
    size = (max(1, int(round(image.width * scale))),
            max(1, int(round(image.height * scale))))
    resized = image.resize(size, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    resized.save(out, format='PNG', optimize=True)
    return out.getvalue()


def add_fill(gltf: Any, fill: float) -> int:
    """Give every material a little emission, so it is never fully black.

    Returns how many materials were touched.  See :data:`DEFAULT_FILL` for why
    this is preferred over a light attached to the camera.
    """
    touched = 0
    for material in gltf.materials or []:
        material.emissiveFactor = [fill, fill, fill]
        touched += 1
    return touched


def strip_textures(gltf: Any) -> int:
    """Drop every image and texture, leaving a plain metallic material.

    Returns how many images went.  The materials keep their identity -- a model
    with three of them still has three -- so a later pass that binds the right
    maps has something to bind them to.
    """
    dropped = len(gltf.images or [])
    for material in gltf.materials or []:
        pbr = material.pbrMetallicRoughness
        if pbr is None:
            continue
        pbr.baseColorTexture = None
        pbr.metallicRoughnessTexture = None
        pbr.baseColorFactor = list(STRIPPED_BASE_COLOR)
        pbr.metallicFactor = STRIPPED_METALLIC
        pbr.roughnessFactor = STRIPPED_ROUGHNESS
        material.normalTexture = None
        material.occlusionTexture = None
        material.emissiveTexture = None
        material.emissiveFactor = [0.0, 0.0, 0.0]
    gltf.textures = []
    gltf.images = []
    gltf.samplers = []
    return dropped


def rebuild(gltf: Any, replacements: dict) -> None:
    """Write a new binary blob holding only the views something still points at.

    The buffer is rebuilt rather than patched for two reasons: every view after
    a resampled image moves, and a stripped model's image data is still *in*
    the file until the views that held it are dropped -- which is why stripping
    the textures off a nine-megabyte model has to shrink the buffer, not just
    the JSON.

    Views are renumbered as they are dropped, so every accessor and image that
    referred to one by index is repointed.  A stale index is a model that loads
    to nothing.
    """
    blob = gltf.binary_blob()
    referenced = set()
    for accessor in gltf.accessors or []:
        if accessor.bufferView is not None:
            referenced.add(accessor.bufferView)
        # Sparse accessors point at two more views apiece; this art uses none,
        # and dropping one silently would be a corrupt file, so refuse instead.
        if getattr(accessor, 'sparse', None):
            raise NotImplementedError(
                'sparse accessors are not handled; this model needs a '
                'different tool')
    for image in gltf.images or []:
        if image.bufferView is not None:
            referenced.add(image.bufferView)

    order = [index for index in sorted(
        range(len(gltf.bufferViews)),
        key=lambda i: gltf.bufferViews[i].byteOffset or 0)
        if index in referenced]
    image_view = {image.bufferView: index
                  for index, image in enumerate(gltf.images or [])}

    pieces: List[bytes] = []
    offset = 0
    kept: List[Any] = []
    renumbered: Dict[int, int] = {}
    for view_index in order:
        view = gltf.bufferViews[view_index]
        start = view.byteOffset or 0
        data = bytes(blob[start:start + view.byteLength])
        replacement = replacements.get(image_view.get(view_index))
        if replacement is not None:
            data = replacement
        # Every view starts on a four-byte boundary; a mis-aligned accessor is
        # undefined behaviour in the spec and a crash in some loaders.
        pad = (4 - (offset % 4)) % 4
        if pad:
            pieces.append(b'\0' * pad)
            offset += pad
        view.byteOffset = offset
        view.byteLength = len(data)
        renumbered[view_index] = len(kept)
        kept.append(view)
        pieces.append(data)
        offset += len(data)

    for accessor in gltf.accessors or []:
        if accessor.bufferView is not None:
            accessor.bufferView = renumbered[accessor.bufferView]
    for image in gltf.images or []:
        if image.bufferView is not None:
            image.bufferView = renumbered[image.bufferView]
    gltf.bufferViews = kept
    gltf.set_binary_blob(b''.join(pieces))
    gltf.buffers[0].byteLength = offset


def prepare(source: str, target: str, limit: int = DEFAULT_TEXTURE_SIZE,
            strip: bool = False, fill: float = DEFAULT_FILL) -> str:
    """Write a trimmed copy of ``source`` to ``target``; returns what it did."""
    from pygltflib import GLTF2

    gltf = GLTF2().load(source)
    before = os.path.getsize(source)
    if strip:
        dropped = strip_textures(gltf)
        rebuild(gltf, {})
        note = 'stripped %d texture%s' % (dropped, '' if dropped == 1 else 's')
    else:
        replacements = {}
        for index in range(len(gltf.images or [])):
            data, _view = _image_bytes(gltf, index)
            smaller = resample(data, limit)
            if smaller is not None:
                replacements[index] = smaller
        rebuild(gltf, replacements)
        note = 'resampled %d texture%s to %dpx' % (
            len(replacements), '' if len(replacements) == 1 else 's', limit)
    # After stripping, never before: stripping clears every material's
    # emission along with its maps, so a fill applied first is thrown away.
    add_fill(gltf, fill)
    gltf.save(target)
    after = os.path.getsize(target)
    return '%s: %s, %.1f MB -> %.2f MB' % (os.path.basename(target), note,
                                           before / 1e6, after / 1e6)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('source', help='the .glb to read')
    parser.add_argument('target', help='the .glb to write')
    parser.add_argument('--textures', type=int, default=DEFAULT_TEXTURE_SIZE,
                        metavar='PIXELS',
                        help='longest side to resample maps to (default %d)'
                             % (DEFAULT_TEXTURE_SIZE,))
    parser.add_argument('--strip-textures', action='store_true',
                        help='drop the maps entirely, leaving plain gunmetal; '
                             'for a model whose maps are wrong')
    parser.add_argument('--fill', type=float, default=DEFAULT_FILL,
                        metavar='FRACTION',
                        help='emission added to every material so the model is '
                             'never black in an unlit map (default %g)'
                             % (DEFAULT_FILL,))
    options = parser.parse_args(argv)
    sys.stdout.write(prepare(options.source, options.target,
                             limit=options.textures,
                             strip=options.strip_textures,
                             fill=options.fill) + '\n')
    return 0


if __name__ == '__main__':                      # pragma: no cover
    sys.exit(main())
