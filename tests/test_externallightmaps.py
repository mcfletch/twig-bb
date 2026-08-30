"""Lightmap pages that live beside a map rather than in it — ``SPEC-EXTLM``."""

from __future__ import annotations



import bspbuilder
from twig_bb import externallightmaps, maploader, q3bsp
from twig_bb.materials import TEXTURE_EXTENSIONS

PAGE_SIZE = 32


def _write_map(tmp_path, lm_index: int, lightmaps: bytes = None) -> str:
    """A one-face map under ``maps/``, with the given face lightmap index."""
    maps = tmp_path / 'maps'
    maps.mkdir(exist_ok=True)
    lumps = bspbuilder.v46_quad(lm_index=lm_index, lightmaps=lightmaps)
    path = maps / 'test.bsp'
    path.write_bytes(bspbuilder.build(46, lumps))
    return str(path)


def _write_pages(tmp_path, indices, colour=(200, 100, 50)) -> None:
    """Write ``lm_NNNN.png`` pages beside the map (``SPEC-EXTLM §2.1``)."""
    from PIL import Image
    directory = tmp_path / 'maps' / 'test'
    directory.mkdir(parents=True, exist_ok=True)
    for index in indices:
        image = Image.new('RGB', (PAGE_SIZE, PAGE_SIZE), colour)
        image.save(str(directory / (externallightmaps.PAGE_NAME % index + '.png')))


def test_a_map_with_its_own_lightmaps_is_left_alone(tmp_path):
    """SPEC-EXTLM §1.1: a non-empty lump means the light is already inside."""
    internal = bytes(bytearray([80]) * q3bsp.LIGHTMAP_BYTES)
    path = _write_map(tmp_path, lm_index=0, lightmaps=internal)
    bsp = q3bsp.load(path)
    assert len(bsp.lightmaps) == 1
    assert not externallightmaps.wanted(bsp)
    assert externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS) is None


def test_an_empty_lump_with_a_named_page_wants_external_pages(tmp_path):
    """SPEC-EXTLM §1.2: empty lump plus a face that still names a page."""
    path = _write_map(tmp_path, lm_index=0)
    bsp = q3bsp.load(path)
    assert len(bsp.lightmaps) == 0
    assert externallightmaps.wanted(bsp)


def test_a_map_with_no_baked_light_at_all_wants_nothing(tmp_path):
    """SPEC-EXTLM §1.2: no face names a page, so there is nothing to look for.

    The two cases have to stay distinguishable, or every unlit map would pay
    for a search of a directory that is not there.
    """
    path = _write_map(tmp_path, lm_index=-1)
    bsp = q3bsp.load(path)
    assert not externallightmaps.wanted(bsp)
    assert externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS) is None


def test_only_non_negative_indices_are_pages(tmp_path):
    """SPEC-EXTLM §3.3: any negative value means the face has no page.

    `-3` occurs in real content, so testing only for `-1` would send the
    reader looking for a page numbered minus three.
    """
    path = _write_map(tmp_path, lm_index=-3)
    bsp = q3bsp.load(path)
    assert externallightmaps.indices(bsp) == []
    assert not externallightmaps.wanted(bsp)


def test_the_page_a_face_names_is_loaded_by_that_number(tmp_path):
    """SPEC-EXTLM §2.1, §3.1: `lm_index` n is the file `lm_000n`."""
    path = _write_map(tmp_path, lm_index=2)
    _write_pages(tmp_path, [0, 1, 2, 3])
    bsp = q3bsp.load(path)
    pages = externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS)
    assert pages is not None
    assert externallightmaps.indices(bsp) == [2]
    page = pages.page(2)
    assert page is not None
    assert page.shape == (PAGE_SIZE, PAGE_SIZE, 3)
    assert tuple(page[0, 0]) == (200, 100, 50)


def test_a_deluxemapped_map_never_reads_its_direction_pages(tmp_path):
    """SPEC-EXTLM §4.4: faces name only even pages, so odd ones stay unread.

    That is the whole of deluxemap handling, and it is worth pinning: the odd
    pages are direction vectors and would light the map in pastel nonsense if
    anything sampled them.
    """
    path = _write_map(tmp_path, lm_index=0)
    _write_pages(tmp_path, [0, 1])
    bsp = q3bsp.load(path)
    pages = externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS)
    assert pages is not None
    pages.page(0)
    assert 1 not in pages._pages, 'the direction page was read and should not be'


def test_pages_stand_in_for_the_lump_when_the_map_is_loaded(tmp_path):
    """The loader swaps them in, so nothing downstream knows the difference."""
    path = _write_map(tmp_path, lm_index=0)
    _write_pages(tmp_path, [0, 1])
    loaded = maploader.load(path)
    assert len(loaded.bsp.lightmaps) == 1
    assert len(loaded.atlas.pages) == 1
    assert loaded.atlas.pages[0].max() > 0, 'the atlas page is black'


def test_a_missing_directory_leaves_the_map_unlit_rather_than_failing(tmp_path):
    """A map naming pages nobody shipped still loads; it just draws unlit."""
    path = _write_map(tmp_path, lm_index=0)
    bsp = q3bsp.load(path)
    assert externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS) is None
    assert maploader.load(path) is not None


def test_a_named_page_the_directory_does_not_hold_is_reported(tmp_path):
    """The directory exists but the page is absent: no pages, and a warning."""
    path = _write_map(tmp_path, lm_index=5)
    _write_pages(tmp_path, [0])
    bsp = q3bsp.load(path)
    assert externallightmaps.for_map(path, bsp, TEXTURE_EXTENSIONS) is None
