"""Lightmap atlas packing: correctness, addressing, and the load-time budget."""

from __future__ import annotations

import time

import numpy as np
import pytest

from twitchoglc.lightmapatlas import build_atlas


def _block(width: int, height: int, value: int) -> np.ndarray:
    return np.full((height, width, 3), value, np.uint8)


def test_a_single_block_lands_on_one_page():
    atlas = build_atlas([_block(4, 4, 200)], page_size=64)
    assert len(atlas.pages) == 1
    assert atlas.page_of(0) == 0
    assert atlas.pages[0].shape == (64, 64, 3)


def test_a_blocks_pixels_are_copied_into_its_page_unchanged():
    block = np.arange(2 * 3 * 3, dtype=np.uint8).reshape((3, 2, 3))
    atlas = build_atlas([block], page_size=32)
    place = atlas.placements[0]
    region = atlas.pages[0][place.y:place.y + 3, place.x:place.x + 2]
    assert np.array_equal(region, block)


def test_blocks_do_not_overlap():
    blocks = [_block(7, 5, i + 1) for i in range(40)]
    atlas = build_atlas(blocks, page_size=64)
    occupancy = [np.zeros(page.shape[:2], bool) for page in atlas.pages]
    for place in atlas.placements:
        assert place is not None
        window = occupancy[place.page][place.y:place.y + place.height,
                                       place.x:place.x + place.width]
        assert not window.any(), 'block overlaps one already placed'
        window[:] = True


def test_blocks_that_do_not_fit_one_page_spill_onto_another():
    blocks = [_block(30, 30, 1) for _ in range(20)]
    atlas = build_atlas(blocks, page_size=64)
    assert len(atlas.pages) > 1
    assert {place.page for place in atlas.placements} == set(range(len(atlas.pages)))


def test_a_block_larger_than_the_requested_page_grows_the_page():
    """A single oversized luxel grid must not silently lose its lighting."""
    atlas = build_atlas([_block(200, 200, 5)], page_size=64)
    assert atlas.page_size >= 200
    assert atlas.placements[0] is not None


def test_an_empty_block_gets_no_placement():
    atlas = build_atlas([_block(4, 4, 1), None, _block(2, 2, 2)], page_size=32)
    assert atlas.placements[1] is None
    assert atlas.page_of(1) == -1


def test_no_blocks_at_all_produces_no_pages():
    atlas = build_atlas([], page_size=32)
    assert atlas.pages == []
    assert atlas.placements == []


def test_luxel_coordinates_address_texel_centres_of_the_block():
    """SPEC-BSP38 §7.7: a luxel samples at its centre, hence the half-texel."""
    atlas = build_atlas([_block(4, 8, 1)], page_size=64)
    place = atlas.placements[0]
    uv = atlas.uv_from_luxels(0, np.array([[0.0, 0.0], [3.0, 7.0]]))
    assert uv[0] == pytest.approx(((place.x + 0.5) / 64.0, (place.y + 0.5) / 64.0))
    assert uv[1] == pytest.approx(((place.x + 3.5) / 64.0, (place.y + 7.5) / 64.0))


def test_normalised_coordinates_span_the_whole_block():
    """A version 46 face carries lightmap UVs already normalised over its image."""
    atlas = build_atlas([_block(16, 16, 1)], page_size=64)
    place = atlas.placements[0]
    uv = atlas.uv_from_normalised(0, np.array([[0.0, 0.0], [1.0, 1.0]]))
    assert uv[0] == pytest.approx((place.x / 64.0, place.y / 64.0))
    assert uv[1] == pytest.approx(((place.x + 16) / 64.0, (place.y + 16) / 64.0))


def test_addressing_an_unplaced_block_returns_zero_coordinates():
    atlas = build_atlas([None], page_size=32)
    assert np.array_equal(atlas.uv_from_luxels(0, np.array([[1.0, 2.0]])), [[0.0, 0.0]])
    assert np.array_equal(atlas.uv_from_normalised(0, np.array([[1.0, 2.0]])),
                          [[0.0, 0.0]])


def test_blocks_are_laid_down_tallest_first():
    """Height-sorted shelving: a shelf's height is set by its first block, so
    laying them down unsorted leaves a tall block's worth of waste above every
    short one."""
    rng = np.random.default_rng(3)
    heights = [int(h) for h in rng.integers(2, 30, size=60)]
    atlas = build_atlas([_block(6, h, 1) for h in heights], page_size=64)
    laid = sorted(atlas.placements, key=lambda p: (p.page, p.y, p.x))
    ordered = [place.height for place in laid]
    assert ordered == sorted(ordered, reverse=True)


def test_padding_keeps_a_gap_between_neighbours():
    blocks = [_block(4, 4, 1), _block(4, 4, 2)]
    atlas = build_atlas(blocks, page_size=64, padding=2)
    a, b = atlas.placements
    assert abs(a.x - b.x) >= 4 + 2 or abs(a.y - b.y) >= 4 + 2


def test_pages_start_black_so_an_unused_region_adds_no_light():
    atlas = build_atlas([_block(4, 4, 255)], page_size=32)
    assert int(atlas.pages[0][31, 31, 0]) == 0


@pytest.mark.slow
def test_packing_a_whole_maps_worth_of_blocks_is_fast():
    """The plan's budget: a local map load is about two seconds in total.

    A per-rectangle search over numpy arrays is what blew that before, so this
    guards the packer specifically -- roughly the block count and size mix of
    the sample Alien Arena map at its override resolution.
    """
    rng = np.random.default_rng(7)
    sizes = rng.integers(2, 40, size=(13562, 2))
    blocks = [np.zeros((int(h), int(w), 3), np.uint8) for w, h in sizes]
    start = time.perf_counter()
    atlas = build_atlas(blocks, page_size=2048)
    elapsed = time.perf_counter() - start
    assert all(place is not None for place in atlas.placements)
    assert elapsed < 2.0, 'packing took %.2fs' % elapsed
