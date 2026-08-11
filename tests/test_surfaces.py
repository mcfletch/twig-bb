"""The shared surface-style value object."""

from __future__ import annotations

import pytest

from twig_bb.surfaces import SurfaceStyle


def test_a_plain_surface_is_drawn_opaque_lit_and_solid():
    style = SurfaceStyle(name='xenos/comptile')
    assert style.draw
    assert style.opacity == 1.0
    assert style.lightmapped
    assert style.solid
    assert not style.transparent


def test_styles_are_hashable_so_batches_can_be_keyed_by_them():
    a = SurfaceStyle(name='wall', sky=True)
    b = SurfaceStyle(name='wall', sky=True)
    c = SurfaceStyle(name='wall')
    assert a == b and hash(a) == hash(b)
    assert a != c
    assert len({a, b, c}) == 2


def test_a_masked_style_carries_the_cut_out_threshold():
    """SPEC-Q3SHADER §2.3: `alphaFunc GE128` keeps alpha of at least 128/255."""
    style = SurfaceStyle(name='grate', masked=True)
    assert style.alpha_cutoff == pytest.approx(128.0 / 255.0)


def test_a_style_can_be_derived_with_changes():
    """A `.shader` refines the style a plainer reading produced."""
    base = SurfaceStyle(name='wall')
    derived = base.replace(masked=True, double_sided=True)
    assert derived.masked and derived.double_sided
    assert derived.name == base.name
    assert not base.masked           # the original is untouched


def test_a_texture_name_with_backslashes_is_the_same_surface():
    """Some maps write Windows separators.  Left as they are, one texture
    becomes two styles, two batches and two copies of the same image."""
    forward = SurfaceStyle(name='models/mapobjects/treebark')
    backward = SurfaceStyle(name='models\\mapobjects\\treebark')
    assert backward.name == forward.name
    assert backward == forward


def test_a_texture_name_carrying_an_extension_is_the_same_surface():
    """SPEC-BSP46 §6.1 names carry no extension, but SPEC-Q3SHADER §1.6 paths
    inside a script do, and both reach a style."""
    assert SurfaceStyle(name='textures/a/water.tga') == SurfaceStyle(name='textures/a/water')
    assert SurfaceStyle(name='textures/a/water.JPG').name == 'textures/a/water'


def test_a_name_that_is_not_an_image_path_keeps_its_suffix():
    """Only known image extensions are stripped; a dot in a name is not one."""
    assert SurfaceStyle(name='textures/a/v1.2_wall').name == 'textures/a/v1.2_wall'


# -- liquids ------------------------------------------------------------------

def test_a_style_is_not_a_liquid_unless_it_says_so():
    assert not SurfaceStyle(name='wall').liquid


def test_the_liquid_flag_is_part_of_what_separates_batches():
    a = SurfaceStyle(name='x', liquid=True)
    b = SurfaceStyle(name='x', liquid=False)
    assert a.batch_key() != b.batch_key()
