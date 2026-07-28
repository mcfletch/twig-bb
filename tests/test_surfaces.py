"""The shared surface-style value object, and the version 38 flag reading."""

from __future__ import annotations

import pytest

from twitchoglc import q2bsp
from twitchoglc import surfaces
from twitchoglc.surfaces import SurfaceStyle, style_from_quake2_flags


def test_a_plain_surface_is_drawn_opaque_lit_and_solid():
    style = SurfaceStyle(name='xenos/comptile')
    assert style.draw
    assert style.opacity == 1.0
    assert style.lightmapped
    assert style.solid
    assert not style.transparent


def test_nodraw_is_not_drawn():
    """SPEC-BSP38 §8.1: `SURF_NODRAW` is not rendered at all."""
    style = style_from_quake2_flags('common/nodraw', q2bsp.SURF_NODRAW)
    assert not style.draw


def test_sky_is_marked_and_carries_no_lightmap():
    """SPEC-BSP38 §8.1 and §7.8: sky is substituted, and has no lightmap."""
    style = style_from_quake2_flags('sky/space1', q2bsp.SURF_SKY)
    assert style.sky
    assert not style.lightmapped


def test_a_warped_surface_carries_no_lightmap():
    """SPEC-BSP38 §7.8: a warped surface has no usable lightmap."""
    style = style_from_quake2_flags('water/water1', q2bsp.SURF_WARP)
    assert style.warping
    assert not style.lightmapped


def test_the_two_translucency_bits_give_a_third_and_two_thirds_opacity():
    """SPEC-BSP38 §8.1: TRANS33 is ~1/3 opacity, TRANS66 is ~2/3."""
    third = style_from_quake2_flags('glass', q2bsp.SURF_TRANS33)
    two_thirds = style_from_quake2_flags('glass', q2bsp.SURF_TRANS66)
    assert third.opacity == pytest.approx(1.0 / 3.0)
    assert two_thirds.opacity == pytest.approx(2.0 / 3.0)
    assert third.transparent and two_thirds.transparent


def test_a_translucent_surface_is_drawn_without_a_lightmap():
    """SPEC-RSCRIPT §12.2: translucent surfaces are also drawn without one."""
    style = style_from_quake2_flags('glass', q2bsp.SURF_TRANS33)
    assert not style.lightmapped


def test_both_translucency_bits_together_take_the_lower_opacity():
    """SPEC-BSP38 §8.1 lets bits combine freely; the stronger one wins."""
    style = style_from_quake2_flags('glass', q2bsp.SURF_TRANS33 | q2bsp.SURF_TRANS66)
    assert style.opacity == pytest.approx(1.0 / 3.0)


def test_flowing_marks_the_surface_as_scrolling_and_not_as_a_push():
    """SPEC-TRIGGER-PUSH §9.3: `SURF_FLOWING` scrolls the texture only."""
    style = style_from_quake2_flags('water/river', q2bsp.SURF_FLOWING)
    assert style.scrolling
    assert style.solid          # no movement effect of any kind


def test_sky_is_excluded_from_shadow_maps():
    """Sky is drawn by the backdrop, not as geometry, so it casts nothing."""
    assert not style_from_quake2_flags('sky/s', q2bsp.SURF_SKY).casts_shadow


def test_an_unrecognised_bit_is_ignored_rather_than_rejected():
    """SPEC-BSP38 §8.4: unrecognised bits are reserved, not errors."""
    style = style_from_quake2_flags('wall', 0x40000000 | q2bsp.SURF_LIGHT)
    assert style.draw
    assert style.emissive


def test_the_light_bit_marks_an_emissive_surface():
    """SPEC-BSP38 §8.1: a real-time renderer may use it as an emissive term."""
    assert style_from_quake2_flags('lights/lamp', q2bsp.SURF_LIGHT).emissive


def test_the_style_names_the_texture_it_came_from():
    assert style_from_quake2_flags('xenos/comptile', 0).name == 'xenos/comptile'


def test_styles_are_hashable_so_batches_can_be_keyed_by_them():
    a = style_from_quake2_flags('wall', q2bsp.SURF_SKY)
    b = style_from_quake2_flags('wall', q2bsp.SURF_SKY)
    c = style_from_quake2_flags('wall', 0)
    assert a == b and hash(a) == hash(b)
    assert a != c
    assert len({a, b, c}) == 2


def test_a_masked_style_carries_the_cut_out_threshold():
    """SPEC-Q3SHADER §2.3: `alphaFunc GE128` keeps alpha of at least 128/255."""
    style = SurfaceStyle(name='grate', masked=True)
    assert style.alpha_cutoff == pytest.approx(128.0 / 255.0)


def test_a_style_can_be_derived_with_changes():
    """A `.shader` refines the style the map's own flags produced."""
    base = style_from_quake2_flags('wall', 0)
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


def test_a_warped_version_38_surface_is_a_liquid():
    """`SPEC-BSP38 §8.1` gives version 38 no contents bit on a face; the warp
    flag is what the compiler puts on the surfaces of a liquid volume."""
    style = surfaces.style_from_quake2_flags('e1u1/water', q2bsp.SURF_WARP)
    assert style.liquid


def test_an_ordinary_version_38_surface_is_not_a_liquid():
    assert not surfaces.style_from_quake2_flags('e1u1/wall', 0).liquid


def test_a_liquid_is_not_solid_so_a_player_falls_into_it():
    """`SPEC-BSP38 §9.4`: what stops a player is solid, playerclip and window —
    a liquid is not among them."""
    assert not surfaces.style_from_quake2_flags('e1u1/water', q2bsp.SURF_WARP).solid


def test_the_liquid_flag_is_part_of_what_separates_batches():
    a = SurfaceStyle(name='x', liquid=True)
    b = SurfaceStyle(name='x', liquid=False)
    assert a.batch_key() != b.batch_key()
