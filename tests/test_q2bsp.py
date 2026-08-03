"""`IBSP` version 38 container reading, against SPEC-BSP38 §1–§4, §8, §9, §12."""

from __future__ import annotations

import struct

import numpy as np
import pytest

import bspbuilder
from twig_bb import q2bsp
from twig_bb.bspfile import MalformedBSP


def test_the_header_identifies_a_version_38_map(write_map):
    """SPEC-BSP38 §1.1, §1.2."""
    path = write_map(38, bspbuilder.v38_quad())
    bsp = q2bsp.load(path)
    assert bsp.version == 38


def test_a_wrong_version_is_refused_rather_than_guessed(write_map):
    """SPEC-BSP38 §1.2: a reader must reject any other value."""
    data = bytearray(bspbuilder.build(38, bspbuilder.v38_quad()))
    data[4:8] = struct.pack('<i', 29)
    path = write_map(38, {})
    open(path, 'wb').write(bytes(data))
    with pytest.raises(MalformedBSP):
        q2bsp.load(path)


def test_a_file_that_is_not_a_bsp_is_refused(tmp_path):
    """SPEC-BSP38 §1.1: the identifier is the first four bytes."""
    path = tmp_path / 'not.bsp'
    path.write_bytes(b'PK\x03\x04' + b'\x00' * 200)
    with pytest.raises(MalformedBSP):
        q2bsp.load(str(path))


def test_the_directory_has_nineteen_entries(write_map):
    """SPEC-BSP38 §1.5: 19 entries, so the header is 160 bytes."""
    path = write_map(38, bspbuilder.v38_quad())
    bsp = q2bsp.load(path)
    assert bsp.directory.shape == (19, 2)
    # Lump data begins at or after the 160-byte header; an absent lump is
    # zero-length and carries no meaningful offset (SPEC-BSP38 §1.6).
    populated = bsp.directory[bsp.directory[:, 1] > 0]
    assert int(populated[:, 0].min()) >= 160


def test_a_zero_length_lump_reads_as_no_records(write_map):
    """SPEC-BSP38 §1.6: a zero-length lump is legal."""
    path = write_map(38, bspbuilder.v38_quad())
    bsp = q2bsp.load(path)
    assert len(bsp.brushes) == 0
    assert len(bsp.areaportals) == 0


def test_every_fixed_record_lump_has_the_size_the_spec_gives(write_map):
    """SPEC-BSP38 §2.1: the record sizes are part of the format."""
    path = write_map(38, bspbuilder.v38_quad())
    bsp = q2bsp.load(path)
    sizes = {
        'planes': 20, 'vertexes': 12, 'nodes': 28, 'texinfo': 76, 'faces': 20,
        'leafs': 28, 'leaffaces': 2, 'leafbrushes': 2, 'edges': 4,
        'surfedges': 4, 'models': 48, 'brushes': 12, 'brushsides': 4,
        'areas': 8, 'areaportals': 8,
    }
    for name, size in sizes.items():
        assert getattr(bsp, name).dtype.itemsize == size, name


def test_a_lump_that_runs_past_the_end_of_the_file_is_refused(write_map):
    """SPEC-BSP38 §12.1: validate offsets and lengths before dereferencing."""
    data = bytearray(bspbuilder.build(38, bspbuilder.v38_quad()))
    entry = 8 + bspbuilder.V38_INDEX['faces'] * 8
    data[entry + 4:entry + 8] = struct.pack('<i', 1 << 20)
    path = write_map(38, {})
    open(path, 'wb').write(bytes(data))
    with pytest.raises(MalformedBSP):
        q2bsp.load(path)


def test_a_negative_lump_offset_is_refused(write_map):
    """SPEC-BSP38 §12.1."""
    data = bytearray(bspbuilder.build(38, bspbuilder.v38_quad()))
    entry = 8 + bspbuilder.V38_INDEX['faces'] * 8
    data[entry:entry + 4] = struct.pack('<i', -16)
    path = write_map(38, {})
    open(path, 'wb').write(bytes(data))
    with pytest.raises(MalformedBSP):
        q2bsp.load(path)


def test_a_partial_trailing_record_is_dropped_rather_than_read(write_map):
    """SPEC-BSP38 §1.6: a length that is not a multiple of the record size."""
    lumps = bspbuilder.v38_quad()
    lumps['planes'] = lumps['planes'] + b'\x01\x02\x03'
    path = write_map(38, lumps)
    bsp = q2bsp.load(path)
    assert len(bsp.planes) == 1


def test_plane_fields_read_back_as_written(write_map):
    """SPEC-BSP38 §4.1: normal, distance, then the classification code."""
    lumps = bspbuilder.v38_quad()
    lumps['planes'] = bspbuilder.v38_plane((0.0, 0.6, 0.8), 17.5, 5)
    bsp = q2bsp.load(write_map(38, lumps))
    plane = bsp.planes[0]
    assert tuple(plane['normal']) == pytest.approx((0.0, 0.6, 0.8))
    assert float(plane['distance']) == pytest.approx(17.5)
    assert int(plane['type']) == 5


def test_face_fields_read_back_as_written(write_map):
    """SPEC-BSP38 §4.6: plane, side, first surfedge, count, texinfo, styles, offset."""
    lumps = bspbuilder.v38_quad()
    lumps['faces'] = bspbuilder.v38_face(0, 1, 7, 4, 0, (0, 3, 255, 255), 96)
    bsp = q2bsp.load(write_map(38, lumps))
    face = bsp.faces[0]
    assert int(face['plane']) == 0
    assert int(face['side']) == 1
    assert int(face['first_edge']) == 7
    assert int(face['num_edges']) == 4
    assert int(face['texinfo']) == 0
    assert list(face['styles']) == [0, 3, 255, 255]
    assert int(face['lightofs']) == 96


def test_texinfo_carries_its_projection_axes_and_texture_name(write_map):
    """SPEC-BSP38 §4.5, §6.4: 32-byte NUL-padded name with no extension."""
    lumps = bspbuilder.v38_quad()
    lumps['texinfo'] = bspbuilder.v38_texinfo(
        (0.5, 0, 0), 8.0, (0, 0, -0.25), -3.0, flags=4, value=200,
        name='xenos/comptile')
    bsp = q2bsp.load(write_map(38, lumps))
    info = bsp.texinfo[0]
    assert tuple(info['s_axis']) == pytest.approx((0.5, 0.0, 0.0))
    assert float(info['s_offset']) == pytest.approx(8.0)
    assert tuple(info['t_axis']) == pytest.approx((0.0, 0.0, -0.25))
    assert float(info['t_offset']) == pytest.approx(-3.0)
    assert int(info['flags']) == 4
    assert int(info['value']) == 200
    assert bsp.texture_name(0) == 'xenos/comptile'


def test_a_texture_name_that_fills_all_thirty_two_bytes_is_read_whole(write_map):
    """SPEC-BSP38 §6.4: if all 32 bytes are non-NUL the string is 32 characters."""
    name = 'a' * 32
    lumps = bspbuilder.v38_quad()
    lumps['texinfo'] = bspbuilder.v38_texinfo((1, 0, 0), 0, (0, 1, 0), 0, name=name)
    bsp = q2bsp.load(write_map(38, lumps))
    assert bsp.texture_name(0) == name


def test_the_entity_lump_is_parsed_into_entities(write_map):
    """SPEC-BSP38 §10.1, §10.7."""
    lumps = bspbuilder.v38_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn', 'gravity': '600'},
        {'classname': 'info_player_deathmatch', 'origin': '-1072 154 -40'},
    ])
    bsp = q2bsp.load(write_map(38, lumps))
    assert [e.classname for e in bsp.entities] == [
        'worldspawn', 'info_player_deathmatch']
    assert bsp.worldspawn.number('gravity') == 600.0


def test_worldspawn_is_empty_when_the_map_has_no_entities(write_map):
    lumps = bspbuilder.v38_quad()
    lumps['entities'] = b''
    bsp = q2bsp.load(write_map(38, lumps))
    assert bsp.worldspawn.classname == ''


def test_models_carry_their_face_range_and_origin(write_map):
    """SPEC-BSP38 §4.12: model 0 is the world; 1+ are brush models."""
    lumps = bspbuilder.v38_quad()
    lumps['models'] = (bspbuilder.v38_model((0, 0, 0), (64, 64, 0), (0, 0, 0), 0, 0, 1)
                       + bspbuilder.v38_model((1, 2, 3), (5, 6, 7), (8, 9, 10), 0, 0, 1))
    bsp = q2bsp.load(write_map(38, lumps))
    assert len(bsp.models) == 2
    assert tuple(bsp.models[1]['origin']) == pytest.approx((8.0, 9.0, 10.0))
    assert int(bsp.models[0]['num_faces']) == 1


def test_the_lighting_lump_is_a_flat_byte_array(write_map):
    """SPEC-BSP38 §7.1: an undifferentiated byte array of RGB samples."""
    lumps = bspbuilder.v38_quad()
    lumps['lighting'] = bytes(range(24))
    bsp = q2bsp.load(write_map(38, lumps))
    assert bsp.lighting.dtype == np.uint8
    assert len(bsp.lighting) == 24


def test_the_surface_flag_values_are_the_ones_the_spec_gives():
    """SPEC-BSP38 §8.1 -- the stock Quake 2 bits, the only ones read."""
    assert q2bsp.SURF_LIGHT == 0x00000001
    assert q2bsp.SURF_SLICK == 0x00000002
    assert q2bsp.SURF_SKY == 0x00000004
    assert q2bsp.SURF_WARP == 0x00000008
    assert q2bsp.SURF_TRANS33 == 0x00000010
    assert q2bsp.SURF_TRANS66 == 0x00000020
    assert q2bsp.SURF_FLOWING == 0x00000040
    assert q2bsp.SURF_NODRAW == 0x00000080


def test_no_flag_bits_beyond_the_stock_set_are_defined():
    """SPEC-BSP38 §8.2 records five further bits belonging to an engine this
    viewer no longer targets.  §8.4 says a reader ignores what it does not
    recognise, which is the right behaviour for them -- and defining them would
    invite code that acts on them."""
    assert not [n for n in dir(q2bsp)
                if n.startswith('SURF_') and getattr(q2bsp, n) > 0x00000200]


def test_the_contents_flag_values_are_the_ones_the_spec_gives():
    """SPEC-BSP38 §9.1, §9.2."""
    assert q2bsp.CONTENTS_SOLID == 0x00000001
    assert q2bsp.CONTENTS_WINDOW == 0x00000002
    assert q2bsp.CONTENTS_LAVA == 0x00000008
    assert q2bsp.CONTENTS_SLIME == 0x00000010
    assert q2bsp.CONTENTS_WATER == 0x00000020
    assert q2bsp.CONTENTS_MIST == 0x00000040
    assert q2bsp.CONTENTS_PLAYERCLIP == 0x00010000
    assert q2bsp.CONTENTS_DETAIL == 0x08000000
    assert q2bsp.CONTENTS_LADDER == 0x20000000


def test_the_derived_masks_are_the_unions_the_spec_states():
    """SPEC-BSP38 §9.4."""
    assert q2bsp.MASK_PLAYERSOLID == (q2bsp.CONTENTS_SOLID | q2bsp.CONTENTS_PLAYERCLIP
                                      | q2bsp.CONTENTS_WINDOW)
    assert q2bsp.MASK_LIQUID == (q2bsp.CONTENTS_WATER | q2bsp.CONTENTS_LAVA
                                 | q2bsp.CONTENTS_SLIME)


def test_units_and_axes_match_the_spec():
    """SPEC-BSP38 §3.1, §3.2: +Z up, roughly an inch per unit."""
    assert q2bsp.UNITS_TO_METRES == pytest.approx(0.0254)


# -- against the real sample map ---------------------------------------------

def test_the_sample_map_reads_with_the_counts_its_bytes_imply(arena_map):
    """The lump lengths in the file divided by the spec's record sizes."""
    bsp = q2bsp.load(arena_map)
    assert bsp.version == 38
    assert len(bsp.faces) == 271240 // 20
    assert len(bsp.texinfo) == 180120 // 76
    assert len(bsp.models) == 144 // 48
    assert len(bsp.lighting) == 2362968


def test_the_sample_maps_entity_census_is_what_the_file_holds(arena_map):
    """A whole-file cross-check of the entity parser on real content."""
    bsp = q2bsp.load(arena_map)
    counts: dict = {}
    for entity in bsp.entities:
        counts[entity.classname] = counts.get(entity.classname, 0) + 1
    assert counts['light'] == 115
    assert counts['misc_mapmodel'] == 16
    assert counts['target_speaker'] == 8
    assert counts['func_door'] == 2
    assert counts['worldspawn'] == 1
    assert 'trigger_push' not in counts
    assert 'trigger_monsterjump' not in counts


def test_the_sample_maps_brush_models_are_referenced_by_entities(arena_map):
    """SPEC-BSP38 §10.5 against real content: `*1` and `*2` exist as models."""
    bsp = q2bsp.load(arena_map)
    referenced = sorted({e.brush_model() for e in bsp.entities if e.brush_model()})
    assert referenced == [1, 2]
    assert len(bsp.models) == 3
