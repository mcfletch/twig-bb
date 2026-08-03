"""Turning batched geometry into a PBR scenegraph."""

from __future__ import annotations

import numpy as np
from twig_bb.lightmapatlas import build_atlas
from twig_bb.materials import MaterialLibrary
from twig_bb.scene import build_scene
from twig_bb.surfaces import SurfaceStyle
from twig_bb.worldgeometry import GeometryBuilder


def _library(tmp_path):
    return MaterialLibrary([str(tmp_path)], family='quake2')


def _world(*styles, page=-1):
    builder = GeometryBuilder()
    positions = np.array([(0, 0, 0), (64, 0, 0), (64, 64, 0), (0, 64, 0)], 'f')
    normals = np.tile(np.array([0, 0, 1], 'f'), (4, 1))
    uv = np.array([(0, 0), (1, 0), (1, 1), (0, 1)], 'f')
    indices = np.array([0, 1, 2, 0, 2, 3], np.uint32)
    for style in styles:
        builder.add_surface(style, page, positions, normals, uv, uv, indices)
    return builder.build()


def test_each_drawn_batch_becomes_one_shape(tmp_path):
    world = _world(SurfaceStyle(name='a'), SurfaceStyle(name='b'))
    group = build_scene(world, build_atlas([]), _library(tmp_path))
    assert len(group.children) == 2


def test_a_shape_carries_the_batchs_geometry(tmp_path):
    world = _world(SurfaceStyle(name='a'))
    shape = build_scene(world, build_atlas([]), _library(tmp_path)).children[0]
    mesh = shape.geometry
    assert len(mesh.positions) == 4
    assert len(mesh.indices) == 6
    assert mesh.texcoords is not None
    assert mesh.texcoords1 is not None
    assert mesh.tangents is not None


def test_an_undrawn_batch_is_not_in_the_scene(tmp_path):
    """SPEC-BSP38 §8.1: a nodraw surface exists for collision only."""
    world = _world(SurfaceStyle(name='a', draw=False))
    assert build_scene(world, build_atlas([]), _library(tmp_path)).children == []


def test_a_sky_batch_is_not_drawn_as_geometry(tmp_path):
    """SPEC-BSP38 §8.1: the surface is a hole the skybox shows through, so
    leaving it undrawn lets the background node show instead."""
    world = _world(SurfaceStyle(name='a', sky=True, draw=False))
    assert build_scene(world, build_atlas([]), _library(tmp_path)).children == []


def test_a_lit_batch_is_wired_to_its_atlas_page(tmp_path):
    page = np.full((16, 16, 3), 200, np.uint8)
    atlas = build_atlas([page], page_size=64)
    world = _world(SurfaceStyle(name='a'), page=0)
    shape = build_scene(world, atlas, _library(tmp_path)).children[0]
    assert 'lightmap' in shape.appearance.material.textures


def test_batches_on_one_page_share_a_single_lightmap_texture(tmp_path):
    """One GL texture per page, not one per batch."""
    atlas = build_atlas([np.zeros((8, 8, 3), np.uint8)], page_size=64)
    world = _world(SurfaceStyle(name='a'), SurfaceStyle(name='b'), page=0)
    shapes = build_scene(world, atlas, _library(tmp_path)).children
    first = shapes[0].appearance.material.textures['lightmap']
    second = shapes[1].appearance.material.textures['lightmap']
    assert first is second


def test_an_unlit_batch_gets_no_lightmap_texture(tmp_path):
    atlas = build_atlas([np.zeros((8, 8, 3), np.uint8)], page_size=64)
    world = _world(SurfaceStyle(name='a'), page=-1)
    shape = build_scene(world, atlas, _library(tmp_path)).children[0]
    assert 'lightmap' not in shape.appearance.material.textures


def test_a_transparent_batch_carries_a_blended_material(tmp_path):
    world = _world(SurfaceStyle(name='a', opacity=1 / 3))
    shape = build_scene(world, build_atlas([]), _library(tmp_path)).children[0]
    assert shape.appearance.material.alphaMode == 'BLEND'


def test_a_double_sided_batch_is_not_marked_solid(tmp_path):
    """`PBRMesh.solid` is the cull flag; a two-sided material must not cull."""
    world = _world(SurfaceStyle(name='a', double_sided=True))
    shape = build_scene(world, build_atlas([]), _library(tmp_path)).children[0]
    assert not shape.geometry.solid


def test_a_single_sided_batch_is_marked_solid(tmp_path):
    world = _world(SurfaceStyle(name='a'))
    shape = build_scene(world, build_atlas([]), _library(tmp_path)).children[0]
    assert shape.geometry.solid


def test_an_empty_world_yields_an_empty_group(tmp_path):
    group = build_scene(GeometryBuilder().build(), build_atlas([]), _library(tmp_path))
    assert group.children == []


def test_the_geometry_arrays_are_the_types_the_gpu_path_expects(tmp_path):
    world = _world(SurfaceStyle(name='a'))
    mesh = build_scene(world, build_atlas([]), _library(tmp_path)).children[0].geometry
    assert mesh.positions.dtype == np.float32
    assert mesh.indices.dtype == np.uint32
    assert mesh.tangents.shape[1] == 4


def test_shapes_are_named_after_their_texture_for_debugging(tmp_path):
    world = _world(SurfaceStyle(name='xenos/comptile'))
    shape = build_scene(world, build_atlas([]), _library(tmp_path)).children[0]
    assert 'comptile' in shape.DEF


def test_the_scene_can_be_restricted_to_the_shadow_casters(tmp_path):
    """SPEC-BSP38 §8.3.3: a NOSHADOW surface is drawn but never written into a
    shadow map."""
    world = _world(SurfaceStyle(name='a'), SurfaceStyle(name='b', casts_shadow=False))
    group = build_scene(world, build_atlas([]), _library(tmp_path))
    casters = [child for child in group.children if getattr(child.geometry, "castsShadow", True)]
    assert len(casters) == 1
