"""Exposing a map's baked light to suit how brightly it was baked.

A map records absolute radiosity, and the absolute scale is not shared between
projects: content baked brighter than the exposure was chosen for renders pale,
with its shadows lifted. The numbers here are measured from real content and
are quoted in :func:`twig_bb.materials.auto_lightmap_strength`.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import materials
from twig_bb.lightmapatlas import build_atlas
from twig_bb.materials import (DEFAULT_LIGHTMAP_STRENGTH,
                               REFERENCE_MEDIAN_LUXEL,
                               auto_lightmap_strength)


def _page(value, size=16):
    """One lightmap block of a uniform grey."""
    return np.full((size, size, 3), value, dtype='u1')


# -- measuring how brightly a map was baked ----------------------------------

def test_the_median_ignores_the_black_between_blocks():
    """A page is mostly padding, and counting it calls every map dark."""
    atlas = build_atlas([_page(128)])
    assert atlas.median_luxel() == pytest.approx(128 / 255.0, abs=0.02)


def test_a_map_with_no_baked_light_has_no_median():
    assert build_atlas([]).median_luxel() is None


def test_an_entirely_black_lightmap_has_no_median():
    """Every luxel unlit is the same case as having no lightmap at all."""
    assert build_atlas([_page(0)]).median_luxel() is None


def test_the_median_is_not_swayed_by_a_few_bright_fixtures():
    """The mean would be; a handful of lamps must not expose a whole level."""
    dim = [_page(20) for _ in range(9)]
    atlas = build_atlas(dim + [_page(255)])
    assert atlas.median_luxel() == pytest.approx(20 / 255.0, abs=0.02)


# -- choosing an exposure from it --------------------------------------------

def test_content_at_the_reference_brightness_keeps_the_default():
    assert auto_lightmap_strength(REFERENCE_MEDIAN_LUXEL) == DEFAULT_LIGHTMAP_STRENGTH


def test_a_map_baked_darker_than_the_reference_is_never_brightened():
    """The author baked a dim level; that is a decision, not a fault.

    Normalising in both directions would give a dim corridor and a floodlit
    hangar the same mid-tone.
    """
    for median in (0.049, 0.0565, 0.0653, 0.095):
        assert auto_lightmap_strength(median) == DEFAULT_LIGHTMAP_STRENGTH


def test_a_map_baked_brighter_than_the_reference_is_pulled_back():
    """The defect: pale surfaces with their shadows lifted off the floor."""
    assert auto_lightmap_strength(0.2527) < DEFAULT_LIGHTMAP_STRENGTH
    assert auto_lightmap_strength(0.2527) == pytest.approx(0.78, abs=0.01)


def test_the_exposure_lands_the_middle_brightness_on_the_reference():
    """What "pulled back" means, as arithmetic rather than as a direction."""
    for median in (0.1770, 0.2527, 0.7237):
        assert median * auto_lightmap_strength(median) == pytest.approx(
            REFERENCE_MEDIAN_LUXEL * DEFAULT_LIGHTMAP_STRENGTH, rel=1e-6)


def test_a_map_with_no_baked_light_takes_the_default():
    """Nothing to over-expose."""
    assert auto_lightmap_strength(None) == DEFAULT_LIGHTMAP_STRENGTH
    assert auto_lightmap_strength(0.0) == DEFAULT_LIGHTMAP_STRENGTH


def test_the_reference_is_the_one_the_default_was_chosen_against():
    """Both constants describe the same body of content, so they move together."""
    assert 0.0 < REFERENCE_MEDIAN_LUXEL < 1.0
    assert materials.DEFAULT_LIGHTMAP_STRENGTH > 0
