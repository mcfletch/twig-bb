"""Quake 3 `.shader` material scripts, against SPEC-Q3SHADER."""

from __future__ import annotations

import pytest

from twitchoglc import q3shader
from twitchoglc.surfaces import SurfaceStyle


def parse(text: str):
    return q3shader.parse(text)


def test_a_material_is_a_name_then_a_braced_body():
    """SPEC-Q3SHADER §1.1, §1.2."""
    materials = parse('textures/base/wall\n{\n\t{\n\t\tmap textures/base/wall.tga\n\t}\n}\n')
    assert list(materials) == ['textures/base/wall']
    assert materials['textures/base/wall'].image == 'textures/base/wall.tga'


def test_a_double_slash_comment_runs_to_the_end_of_the_line():
    """SPEC-Q3SHADER §1.3."""
    materials = parse('// a whole line\ntextures/a/b { // trailing\n cull disable\n}\n')
    assert materials['textures/a/b'].double_sided


def test_a_comment_may_follow_a_brace_with_no_space():
    """SPEC-Q3SHADER §1.3: `}//note` occurs in shipped content."""
    materials = parse('textures/a/b\n{\n cull none\n}//======\ntextures/c/d\n{\n}\n')
    assert set(materials) == {'textures/a/b', 'textures/c/d'}


def test_keywords_are_not_case_sensitive():
    """SPEC-Q3SHADER §1.4: content mixes `blendFunc` and `blendfunc`."""
    materials = parse('textures/a/b { SurfaceParm NoDraw }')
    assert not materials['textures/a/b'].draw


def test_braces_need_no_surrounding_whitespace():
    """SPEC-Q3SHADER §1.5."""
    materials = parse('textures/a/b{{map x.tga}}')
    assert materials['textures/a/b'].image == 'x.tga'


def test_the_first_drawable_stage_map_is_the_materials_image():
    """SPEC-Q3SHADER §2.3.1."""
    materials = parse('n { { map $lightmap } { map real.tga } { map second.tga } }')
    assert materials['n'].image == 'real.tga'


def test_the_white_image_placeholder_is_not_a_file():
    """SPEC-Q3SHADER §2.3: `$whiteimage` is a plain white texture, not a path."""
    materials = parse('n { { map $whiteimage } { map real.tga } }')
    assert materials['n'].image == 'real.tga'


def test_the_editor_image_stands_in_when_no_stage_carries_one():
    """SPEC-Q3SHADER §2.3.1."""
    materials = parse('n { qer_editorimage textures/liquids/lava.tga\n { map $lightmap } }')
    assert materials['n'].image == 'textures/liquids/lava.tga'


def test_a_material_with_no_usable_image_falls_back_to_its_own_name():
    """SPEC-Q3SHADER §2.3.1, §3.2."""
    materials = parse('textures/base/floor { surfaceparm nolightmap }')
    assert materials['textures/base/floor'].image == 'textures/base/floor'


def test_a_clamped_map_is_a_texture_like_any_other():
    """SPEC-Q3SHADER §2.3: `clampmap` differs only in its wrap mode."""
    assert parse('n { { clampmap sky.tga } }')['n'].image == 'sky.tga'


def test_an_animated_maps_first_frame_stands_in():
    """SPEC-Q3SHADER §2.3: `animMap <rate> <frames...>`."""
    materials = parse('n { { animMap 5 one.tga two.tga three.tga } }')
    assert materials['n'].image == 'one.tga'


def test_a_stage_that_samples_the_lightmap_marks_the_material_lightmapped():
    """SPEC-Q3SHADER §2.3.2."""
    assert parse('n { { map $lightmap } { map x.tga } }')['n'].lightmapped
    assert not parse('n { { map x.tga } }')['n'].lightmapped


def test_surfaceparm_nolightmap_wins_over_a_lightmap_stage():
    """SPEC-Q3SHADER §2.2, §2.3.2."""
    materials = parse('n { surfaceparm nolightmap\n { map $lightmap } }')
    assert not materials['n'].lightmapped


@pytest.mark.parametrize('value,attribute,expected', [
    ('nodraw', 'draw', False),
    ('sky', 'sky', True),
    ('nonsolid', 'solid', False),
    ('trigger', 'draw', False),
    ('clip', 'draw', False),
    ('playerclip', 'draw', False),
    ('origin', 'draw', False),
    ('hint', 'draw', False),
    ('skip', 'draw', False),
])
def test_surfaceparm_values_take_effect(value, attribute, expected):
    """SPEC-Q3SHADER §2.2."""
    materials = parse('n { surfaceparm %s }' % value)
    assert getattr(materials['n'], attribute) is expected


def test_a_translucent_surface_is_blended_and_unlit():
    """SPEC-Q3SHADER §2.2: `trans` implies blended and no baked lightmap."""
    material = parse('n { surfaceparm trans\n { map $lightmap } { map x.tga } }')['n']
    assert material.transparent
    assert not material.lightmapped


@pytest.mark.parametrize('liquid', ['water', 'slime', 'lava'])
def test_liquids_are_translucent_and_unlit(liquid):
    """SPEC-Q3SHADER §2.2."""
    material = parse('n { surfaceparm %s }' % liquid)['n']
    assert material.transparent
    assert not material.lightmapped


def test_alphashadow_marks_a_cut_out_mask():
    """SPEC-Q3SHADER §2.2."""
    assert parse('n { surfaceparm alphashadow }')['n'].masked


@pytest.mark.parametrize('mode,expected', [
    ('none', True), ('disable', True), ('twosided', True),
    ('front', False), ('back', False),
])
def test_cull_decides_double_sidedness(mode, expected):
    """SPEC-Q3SHADER §2.1."""
    assert parse('n { cull %s }' % mode)['n'].double_sided is expected


def test_skyparms_marks_the_material_as_sky():
    """SPEC-Q3SHADER §2.1."""
    assert parse('n { skyparms - 512 - }')['n'].sky


def test_a_blending_first_stage_makes_the_material_transparent():
    """SPEC-Q3SHADER §2.3: a stage that blends is not opaque."""
    assert parse('n { { map x.tga blendFunc GL_ONE GL_ONE } }')['n'].transparent
    assert parse('n { { map x.tga blendFunc add } }')['n'].transparent
    assert not parse('n { { map x.tga } }')['n'].transparent


def test_an_opaque_blend_function_is_not_transparency():
    """`GL_ONE GL_ZERO` is the default, opaque, blend."""
    assert not parse('n { { map x.tga blendFunc GL_ONE GL_ZERO } }')['n'].transparent


def test_alphafunc_marks_a_cut_out_rather_than_blending():
    """SPEC-Q3SHADER §2.3."""
    material = parse('n { { map x.tga alphaFunc GE128 } }')['n']
    assert material.masked
    assert not material.transparent


def test_compile_time_and_unknown_directives_are_skipped_by_line():
    """SPEC-Q3SHADER §2.1.1: a directive never spans a line."""
    materials = parse(
        'n {\n q3map_surfacelight 1500\n q3map_sun 1 .78 .48 100 230 54\n'
        ' tessSize 128\n mysteryKeyword a b c\n { map x.tga }\n}\n'
        'm {\n { map y.tga }\n}\n')
    assert materials['n'].image == 'x.tga'
    assert materials['m'].image == 'y.tga'


def test_stage_level_modifiers_do_not_break_the_parse():
    """SPEC-Q3SHADER §2.3: tcMod/rgbGen/depthWrite are parsed and ignored."""
    materials = parse('n { { map x.tga\n tcMod scroll 0.15 0.15\n tcMod turb 0 .2 0 .1\n'
                      ' rgbGen identity\n depthWrite\n } }\nm { { map y.tga } }')
    assert materials['n'].image == 'x.tga'
    assert materials['m'].image == 'y.tga'


def test_a_later_definition_replaces_an_earlier_one():
    """SPEC-Q3SHADER §3.1."""
    materials = parse('n { { map one.tga } } n { { map two.tga } }')
    assert materials['n'].image == 'two.tga'


def test_a_material_becomes_a_surface_style():
    """The shared vocabulary: nothing downstream branches on map family."""
    materials = parse('textures/a/glass { surfaceparm trans cull none\n'
                      ' { map glass.tga blendFunc GL_SRC_ALPHA GL_ONE_MINUS_SRC_ALPHA } }')
    style = materials['textures/a/glass'].style()
    assert isinstance(style, SurfaceStyle)
    assert style.name == 'glass'
    assert style.double_sided
    assert style.transparent
    assert not style.lightmapped


def test_a_missing_material_yields_a_plain_style_named_after_the_texture():
    """SPEC-Q3SHADER §3.2: an undefined name is used directly as a texture path."""
    style = q3shader.style_for({}, 'textures/base/wall')
    assert style.name == 'textures/base/wall'
    assert style.draw and style.lightmapped


def test_a_defined_material_supplies_the_style():
    materials = parse('textures/base/wall { surfaceparm nodraw }')
    assert not q3shader.style_for(materials, 'textures/base/wall').draw


def test_a_material_name_matches_case_insensitively():
    """SPEC-Q3SHADER §1.4, §1.6."""
    materials = parse('Textures/Base/Wall { surfaceparm nodraw }')
    assert not q3shader.style_for(materials, 'textures/base/wall').draw


def test_scripts_are_loaded_from_the_scripts_directory(tmp_path):
    """SPEC-Q3SHADER §3.1."""
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'a.shader').write_text('n { { map one.tga } }')
    (tmp_path / 'scripts' / 'b.shader').write_text('m { { map two.tga } }')
    materials = q3shader.load_scripts([str(tmp_path)])
    assert set(materials) == {'n', 'm'}


def test_a_tree_with_no_scripts_loads_nothing(tmp_path):
    assert q3shader.load_scripts([str(tmp_path)]) == {}


# -- against real shipped scripts --------------------------------------------

def test_a_real_maps_scripts_parse(quake3_map):
    """The `.shader` files shipped inside the sample map's archive."""
    import os
    root = os.path.dirname(os.path.dirname(quake3_map))
    materials = q3shader.load_scripts([root])
    assert materials
    sky = [m for m in materials.values() if m.sky]
    assert sky, 'the sample map defines a sky material'
    for material in materials.values():
        assert material.image, 'every material resolves to some image'


# -- the editor/compiler texture set ------------------------------------------

@pytest.mark.parametrize('name', [
    'textures/common/caulk', 'textures/common/clip', 'textures/common/nodraw',
    'textures/common/trigger', 'textures/common/hint', 'textures/common/origin',
    'textures/common/areaportal', 'textures/common/weapclip',
])
def test_the_common_set_is_not_drawn_even_with_no_shader_for_it(name):
    """`textures/common/*` are the editor and compiler volumes: clip brushes,
    caulk seals, hints, triggers.  Their `surfaceparm nodraw` lives in the base
    game's own `scripts/common.shader`, so a map loaded without that script has
    no definition for them — and treating them as ordinary textures paints solid
    grey walls where the original draws nothing at all."""
    assert not q3shader.style_for({}, name).draw


def test_the_common_set_still_blocks_movement():
    """A clip brush is invisible *and* solid; dropping the collision with the
    drawing would open holes in every map that uses one."""
    style = q3shader.style_for({}, 'textures/common/clip')
    assert style.solid
    assert not style.lightmapped


def test_a_shader_that_does_define_a_common_texture_still_wins():
    """The rule is a fallback for an absent definition, not an override."""
    materials = parse('textures/common/mirror1 { { map textures/x/m.tga } }')
    assert q3shader.style_for(materials, 'textures/common/mirror1').draw


def test_a_texture_merely_named_common_elsewhere_is_unaffected():
    assert q3shader.style_for({}, 'textures/base_wall/common_trim').draw
    assert q3shader.style_for({}, 'models/mapobjects/common/lamp').draw


# -- liquids ------------------------------------------------------------------

@pytest.mark.parametrize('parm', ['water', 'slime', 'lava'])
def test_a_liquid_surfaceparm_marks_the_material_as_a_liquid(parm):
    """`SPEC-Q3SHADER §2.2` names the three; a viewer needs them to know which
    volumes are swum through rather than walked on."""
    text = 'textures/liquids/%s\n{\n surfaceparm %s\n}\n' % (parm, parm)
    style = q3shader.parse(text)['textures/liquids/%s' % parm].style()
    assert style.liquid
    assert not style.solid


def test_an_ordinary_material_is_not_a_liquid():
    text = 'textures/base/wall\n{\n{\nmap textures/base/wall.tga\n}\n}\n'
    assert not q3shader.parse(text)['textures/base/wall'].style().liquid
