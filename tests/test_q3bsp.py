"""`IBSP` version 46 container reading, against SPEC-BSP46 §1–§6."""

from __future__ import annotations

import struct

import numpy as np
import pytest

import bspbuilder
from twig_bb import q3bsp
from twig_bb.bspfile import MalformedBSP


def test_the_header_identifies_a_version_46_map(write_map):
    """SPEC-BSP46 §1.1, §1.2."""
    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    assert bsp.version == 46


def test_a_foreign_version_is_refused_by_the_v46_reader(tmp_path):
    """SPEC-BSP46 §1.2, §2.2: the reader accepts one version, and a directory
    for another family is not interchangeable with its own."""
    # A version 38 header (magic + version + a 19-entry directory) is enough:
    # the reader must reject the version before it trusts any lump.
    header = bspbuilder.MAGIC + struct.pack('<i', 38) + b'\x00' * (19 * 8)
    path = tmp_path / 'foreign.bsp'
    path.write_bytes(header)
    with pytest.raises(MalformedBSP):
        q3bsp.load(str(path))


def test_the_directory_has_seventeen_entries(write_map):
    """SPEC-BSP46 §1.5: 17 entries, so the header is 144 bytes."""
    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    assert bsp.directory.shape == (17, 2)
    populated = bsp.directory[bsp.directory[:, 1] > 0]
    assert int(populated[:, 0].min()) >= 144


def test_every_fixed_record_lump_has_the_size_the_spec_gives(write_map):
    """SPEC-BSP46 §2.1."""
    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    sizes = {
        'textures': 72, 'planes': 16, 'nodes': 36, 'leafs': 48, 'leaffaces': 4,
        'leafbrushes': 4, 'models': 40, 'brushes': 12, 'brushsides': 8,
        'vertexes': 44, 'meshverts': 4, 'effects': 72, 'faces': 104,
        'lightvols': 8,
    }
    for name, size in sizes.items():
        assert getattr(bsp, name).dtype.itemsize == size, name


def test_vertex_fields_read_back_as_written(write_map):
    """SPEC-BSP46 §4.9: position, surface uv, lightmap uv, normal, colour."""
    lumps = bspbuilder.v46_quad()
    lumps['vertexes'] = bspbuilder.v46_vertex(
        (1.0, 2.0, 3.0), (0.25, 0.5), (0.75, 0.125), (0.0, 1.0, 0.0),
        (10, 20, 30, 40))
    bsp = q3bsp.load(write_map(46, lumps))
    vertex = bsp.vertexes[0]
    assert tuple(vertex['position']) == pytest.approx((1.0, 2.0, 3.0))
    assert tuple(vertex['surface']) == pytest.approx((0.25, 0.5))
    assert tuple(vertex['lightmap']) == pytest.approx((0.75, 0.125))
    assert tuple(vertex['normal']) == pytest.approx((0.0, 1.0, 0.0))
    assert list(vertex['colour']) == [10, 20, 30, 40]


def test_face_fields_read_back_as_written(write_map):
    """SPEC-BSP46 §4.12."""
    lumps = bspbuilder.v46_quad()
    lumps['faces'] = bspbuilder.v46_face(3, 2, 12, 9, 40, 0, lm_index=5, size=(3, 3))
    bsp = q3bsp.load(write_map(46, lumps))
    face = bsp.faces[0]
    assert int(face['texture']) == 3
    assert int(face['type']) == 2
    assert int(face['vertex']) == 12
    assert int(face['num_vertexes']) == 9
    assert int(face['meshvert']) == 40
    assert int(face['num_meshverts']) == 0
    assert int(face['lm_index']) == 5
    assert list(face['size']) == [3, 3]


def test_the_face_type_values_are_the_ones_the_spec_gives():
    """SPEC-BSP46 §4.12.1."""
    assert q3bsp.FACE_POLYGON == 1
    assert q3bsp.FACE_PATCH == 2
    assert q3bsp.FACE_MESH == 3
    assert q3bsp.FACE_BILLBOARD == 4


def test_texture_names_are_paths_without_an_extension(write_map):
    """SPEC-BSP46 §6.1: 64-byte NUL-padded path relative to the archive root."""
    lumps = bspbuilder.v46_quad()
    lumps['textures'] = (bspbuilder.v46_texture('textures/base_wall/c_met5_2')
                         + bspbuilder.v46_texture('t' * 64))
    bsp = q3bsp.load(write_map(46, lumps))
    assert bsp.texture_name(0) == 'textures/base_wall/c_met5_2'
    assert bsp.texture_name(1) == 't' * 64


def test_a_lightmap_record_is_a_128_by_128_rgb_image(write_map):
    """SPEC-BSP46 §4.13.1."""
    lumps = bspbuilder.v46_quad(lm_index=0, lightmaps=bspbuilder.v46_lightmap(77))
    bsp = q3bsp.load(write_map(46, lumps))
    assert bsp.lightmaps.shape == (1, 128, 128, 3)
    assert int(bsp.lightmaps[0, 5, 6, 1]) == 77


def test_meshverts_are_offsets_from_a_faces_first_vertex(write_map):
    """SPEC-BSP46 §4.10.1."""
    bsp = q3bsp.load(write_map(46, bspbuilder.v46_quad()))
    assert list(bsp.meshverts) == [0, 1, 2, 0, 2, 3]


def test_the_entity_lump_is_parsed_into_entities(write_map):
    """SPEC-BSP46 §5.1: the Quake-lineage entity syntax, unchanged."""
    lumps = bspbuilder.v46_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn', 'message': 'A Map'},
        {'classname': 'trigger_push', 'model': '*1', 'target': 't1'},
    ])
    bsp = q3bsp.load(write_map(46, lumps))
    assert bsp.worldspawn.get('message') == 'A Map'
    assert bsp.entities[1].brush_model() == 1


def test_the_reader_interprets_no_surface_or_contents_flag_bits():
    """SPEC-BSP46 §6.2 and E.1: v46 flag bit values are deliberately unrecorded.

    Sharing SPEC-BSP38 §8's table with this family would be wrong, so the module
    must not define one at all.
    """
    exported = [name for name in dir(q3bsp)
                if name.startswith(('SURF_', 'CONTENTS_', 'MASK_'))]
    assert exported == []


def test_units_and_axes_match_the_quake_convention():
    """SPEC-BSP46 §3.1, §3.2."""
    assert q3bsp.UNITS_TO_METRES == pytest.approx(0.0254)


def test_a_truncated_directory_is_refused(tmp_path):
    """SPEC-BSP46 §1.5 with §12-style validation."""
    path = tmp_path / 'short.bsp'
    path.write_bytes(b'IBSP' + struct.pack('<i', 46) + b'\x00' * 8)
    with pytest.raises(MalformedBSP):
        q3bsp.load(str(path))


# -- against a real sample map ------------------------------------------------

def test_the_sample_map_reads_with_the_counts_its_bytes_imply(quake3_map):
    """Record sizes from SPEC-BSP46 §2.1 divided into the real lump lengths.

    Read off the map's own directory rather than written out for one map: what
    is claimed is that a lump holds a whole number of its records and that we
    read every one of them, which is true of any v46 map and is what a second
    map would otherwise quietly stop checking.
    """
    bsp = q3bsp.load(quake3_map)
    assert bsp.version == 46
    for name, index, dtype in q3bsp._RECORD_LUMPS:
        length = int(bsp.directory[index][1])
        assert length % dtype.itemsize == 0, (
            '%s: %d bytes is not a whole number of %d-byte records'
            % (name, length, dtype.itemsize))
        assert len(getattr(bsp, name)) == length // dtype.itemsize, name
    lightmaps = int(bsp.directory[q3bsp.LUMP_LIGHTMAPS][1])
    assert len(bsp.lightmaps) == lightmaps // q3bsp.LIGHTMAP_BYTES


def test_the_sample_map_has_patches_and_polygons(quake3_map):
    """SPEC-BSP46 §4.12.1: real maps mix face types."""
    bsp = q3bsp.load(quake3_map)
    kinds = set(int(k) for k in np.unique(bsp.faces['type']))
    assert q3bsp.FACE_POLYGON in kinds
    assert q3bsp.FACE_PATCH in kinds


def test_the_sample_maps_patch_grids_are_odd_and_at_least_three(quake3_map):
    """SPEC-BSP46 §6.3: both control-grid dimensions are odd and >= 3."""
    bsp = q3bsp.load(quake3_map)
    patches = bsp.faces[bsp.faces['type'] == q3bsp.FACE_PATCH]
    sizes = patches['size']
    assert len(sizes) > 0
    assert (sizes >= 3).all()
    assert (sizes % 2 == 1).all()


def test_the_sample_maps_texture_names_carry_no_extension(quake3_map):
    """SPEC-BSP46 §6.1."""
    bsp = q3bsp.load(quake3_map)
    names = [bsp.texture_name(i) for i in range(len(bsp.textures))]
    assert any(name.startswith('textures/') for name in names)
    assert not any(name.endswith(('.tga', '.jpg')) for name in names)
