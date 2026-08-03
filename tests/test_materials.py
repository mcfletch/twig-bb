"""Resolving texture names to images and PBR materials.

Facts under test are SPEC-BSP38 §6.4, SPEC-BSP46 §6.1/§7.3 and
SPEC-Q3SHADER §1.6.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb.materials import MaterialLibrary
from twig_bb.surfaces import SurfaceStyle


def write_image(path, size=(8, 4), colour=(255, 0, 0)):
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new('RGB', size, colour).save(str(path))
    return path


@pytest.fixture
def content(tmp_path):
    """A content root with one texture in it."""
    write_image(tmp_path / 'textures' / 'xenos' / 'comptile.tga', size=(16, 8))
    return tmp_path


def test_a_world_texture_is_looked_up_under_the_textures_prefix(content):
    """SPEC-BSP38 §6.4: a bare name under the `textures/` root."""
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.texture_size('xenos/comptile') == (16, 8)


def test_the_extension_search_order_prefers_tga_over_jpg(content):
    """SPEC-Q3SHADER §1.6: the extension is advisory; ours are tried in turn."""
    write_image(content / 'textures' / 'xenos' / 'comptile.jpg', size=(32, 32))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.texture_size('xenos/comptile') == (16, 8)    # the .tga wins


def test_a_jpg_is_found_when_no_tga_exists(content):
    write_image(content / 'textures' / 'bg' / 'tile.jpg', size=(4, 4))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.texture_size('bg/tile') == (4, 4)


def test_a_missing_texture_reports_the_documented_fallback_size(content):
    """SPEC-BSP38 §6.2 divides by the real size, so a missing image is guessed."""
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.texture_size('nowhere/absent') == (64, 64)


def test_the_base_colour_map_is_sampled_as_srgb(content):
    """A diffuse map is authored in sRGB; a lightmap holds light and is not."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='xenos/comptile'))
    assert material.textures['baseColor'].srgb


def test_an_opaque_style_produces_an_opaque_material(content):
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='xenos/comptile'))
    assert material.alphaMode == 'OPAQUE'
    assert material.transparency == 0.0


def test_a_translucent_style_produces_a_blended_material(content):
    """SPEC-BSP38 §8.1: TRANS33 draws at roughly one-third opacity."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='xenos/comptile', opacity=1 / 3))
    assert material.alphaMode == 'BLEND'
    assert material.transparency == pytest.approx(2 / 3)


def test_a_masked_style_produces_a_cut_out_material(content):
    """SPEC-Q3SHADER §2.3: `alphaFunc GE128` keeps alpha of at least 128/255."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='xenos/comptile', masked=True))
    assert material.alphaMode == 'MASK'
    assert material.alphaCutoff == pytest.approx(128.0 / 255.0)


def test_a_double_sided_style_disables_backface_culling(content):
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x', double_sided=True))
    assert material.doubleSided


def test_a_lightmap_page_is_wired_to_the_lightmap_channel(content):
    library = MaterialLibrary([str(content)], family='quake2')
    page = np.full((8, 8, 3), 128, np.uint8)
    material = library.material_for(SurfaceStyle(name='x'), lightmap=page)
    assert 'lightmap' in material.textures


def test_the_lightmap_is_read_linearly_and_never_as_srgb(content):
    """A lightmap holds light, not colour, so it must not be gamma-decoded."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x'),
                                    lightmap=np.zeros((4, 4, 3), np.uint8))
    assert not material.textures['lightmap'].srgb


def test_the_lightmap_samples_the_second_uv_set(content):
    """The atlas needs its own coordinates, so the lightmap bit selects UV set 1."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x'),
                                    lightmap=np.zeros((4, 4, 3), np.uint8))
    assert material.texCoordMask & 32


def test_a_material_without_a_lightmap_selects_no_second_uv_set(content):
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x'))
    assert not material.texCoordMask & 32


def test_the_default_lightmap_strength_is_the_engines_two(content):
    """A map bakes absolute radiosity; the viewer picks the exposure."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x'),
                                    lightmap=np.zeros((4, 4, 3), np.uint8))
    assert material.lightmapStrength == pytest.approx(2.0)


def test_the_lightmap_strength_is_configurable(content):
    """Exposure is a rendering choice, so `--lightmap` must reach it."""
    library = MaterialLibrary([str(content)], family='quake2', lightmap_strength=3.5)
    material = library.material_for(SurfaceStyle(name='x'),
                                    lightmap=np.zeros((4, 4, 3), np.uint8))
    assert material.lightmapStrength == pytest.approx(3.5)


def test_an_unlit_style_gets_no_lightmap_even_with_a_page(content):
    """SPEC-BSP38 §7.8: a sky or warped surface carries no lightmap."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='x', lightmapped=False),
                                    lightmap=np.zeros((4, 4, 3), np.uint8))
    assert 'lightmap' not in material.textures


def test_an_image_is_loaded_once_and_shared(content):
    """A map names one texture on many surfaces; decoding it repeatedly is waste."""
    library = MaterialLibrary([str(content)], family='quake2')
    first = library.material_for(SurfaceStyle(name='xenos/comptile'))
    second = library.material_for(SurfaceStyle(name='xenos/comptile'))
    assert first.textures['baseColor'] is second.textures['baseColor']


def test_a_material_is_built_once_per_style(content):
    library = MaterialLibrary([str(content)], family='quake2')
    style = SurfaceStyle(name='xenos/comptile')
    assert library.material_for(style) is library.material_for(style)


def test_a_missing_image_still_yields_a_usable_material(content):
    """A map whose textures are absent must still render as untextured geometry."""
    library = MaterialLibrary([str(content)], family='quake2')
    material = library.material_for(SurfaceStyle(name='nowhere/absent'))
    assert 'baseColor' not in material.textures
    assert tuple(material.baseColor) == pytest.approx((0.25, 0.25, 0.25))


def test_a_quake3_name_is_already_a_full_path(content):
    """SPEC-BSP46 §6.1, §7.3: a v46 texture name is rooted at the archive."""
    write_image(content / 'textures' / 'base_wall' / 'c_met5_2.tga', size=(2, 2))
    library = MaterialLibrary([str(content)], family='quake3')
    assert library.texture_size('textures/base_wall/c_met5_2') == (2, 2)


def test_a_quake3_name_with_an_extension_still_resolves(content):
    """SPEC-Q3SHADER §1.6: an extension inside a script is advisory."""
    write_image(content / 'textures' / 'base_wall' / 'c_met5_2.jpg', size=(2, 2))
    library = MaterialLibrary([str(content)], family='quake3')
    assert library.texture_size('textures/base_wall/c_met5_2.tga') == (2, 2)


def test_several_content_roots_are_searched_in_order(tmp_path):
    """Candidates resolve against the content roots in precedence order."""
    first, second = tmp_path / 'a', tmp_path / 'b'
    write_image(second / 'textures' / 'x' / 'y.tga', size=(4, 4))
    write_image(first / 'textures' / 'x' / 'y.tga', size=(8, 8))
    library = MaterialLibrary([str(first), str(second)], family='quake2')
    assert library.texture_size('x/y') == (8, 8)


def test_a_texture_name_may_not_escape_its_content_root(content):
    """Map content is untrusted: a name with `..` must not read outside the root."""
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.resolve('../../etc/passwd') is None
    assert library.resolve('/etc/passwd') is None


def test_a_wal_texture_is_reported_rather_than_silently_missing(content, caplog):
    """SPEC-BSP38 §6.4 names `.wal` as the stock v38 asset; decoding it needs a
    palette this viewer does not carry, so the gap is logged rather than left
    as a silent blank."""
    (content / 'textures' / 'e1u1').mkdir(parents=True, exist_ok=True)
    (content / 'textures' / 'e1u1' / 'wall.wal').write_bytes(b'\x00' * 100)
    library = MaterialLibrary([str(content)], family='quake2')
    with caplog.at_level('WARNING'):
        assert library.resolve('e1u1/wall') is None
    assert any('.wal' in record.message for record in caplog.records)


def test_a_texture_is_found_when_only_its_case_differs(content):
    """Quake content is authored case-insensitively -- the shader manual asks
    for lowercase filenames and maps do not always comply -- so on a
    case-sensitive filesystem an exact-case lookup loses real textures."""
    write_image(content / 'textures' / 'natestah' / 'Nateweb.tga', size=(2, 2))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.resolve('natestah/nateweb') is not None
    assert library.texture_size('natestah/nateweb') == (2, 2)


def test_an_exactly_matching_name_still_wins_over_a_differently_cased_one(content):
    write_image(content / 'textures' / 'dup' / 'Wall.tga', size=(2, 2))
    write_image(content / 'textures' / 'dup' / 'wall.tga', size=(4, 4))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.texture_size('dup/wall') == (4, 4)


def test_a_name_whose_directory_case_differs_is_still_found(content):
    write_image(content / 'textures' / 'MixedCase' / 'floor.tga', size=(2, 2))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.resolve('mixedcase/floor') is not None


def test_a_name_that_matches_nothing_at_all_is_still_missing(content):
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.resolve('nowhere/at/all') is None


# -- light-variant shader names -----------------------------------------------

def test_a_light_variant_name_falls_back_to_the_texture_it_is_built_on(content):
    """A map names `textures/base_light/light1_5000` — a shader in the base
    game's scripts that draws `light1` and emits 5000 units of light.  Without
    those scripts the name resolves to no file at all, and the surface renders
    untextured even though the image it is built on is right there."""
    write_image(content / 'textures' / 'base_light' / 'light1.tga', size=(4, 4))
    library = MaterialLibrary([str(content)], family='quake3')
    for name in ('textures/base_light/light1_5000',
                 'textures/base_light/light1_2k',
                 'textures/base_light/light1_20K',
                 'textures/base_light/light1_300'):
        assert library.resolve(name) is not None, name


def test_the_exact_name_is_always_preferred_over_the_stripped_one(content):
    write_image(content / 'textures' / 'base_light' / 'light1.tga', size=(4, 4))
    write_image(content / 'textures' / 'base_light' / 'light1_2k.tga', size=(8, 8))
    library = MaterialLibrary([str(content)], family='quake3')
    assert library.texture_size('textures/base_light/light1_2k') == (8, 8)


def test_a_name_whose_stripped_form_is_also_absent_stays_missing(content):
    """The fallback recovers a texture that exists; it never invents one."""
    library = MaterialLibrary([str(content)], family='quake3')
    assert library.resolve('textures/base_light/nothing_2k') is None


def test_a_name_with_no_numeric_suffix_is_not_stripped(content):
    """Only a trailing light value is dropped, not any trailing word."""
    write_image(content / 'textures' / 'base_wall' / 'comp3b.tga', size=(4, 4))
    library = MaterialLibrary([str(content)], family='quake3')
    assert library.resolve('textures/base_wall/comp3b_dark') is None


def test_the_fallback_applies_to_quake2_names_too(content):
    write_image(content / 'textures' / 'e1u1' / 'lamp.tga', size=(4, 4))
    library = MaterialLibrary([str(content)], family='quake2')
    assert library.resolve('e1u1/lamp_1000') is not None


class TestTextureForName:
    """Resolving a bare texture name, which is what a frame cycle asks for."""

    def test_a_name_with_no_image_resolves_to_nothing(self, tmp_path):
        library = MaterialLibrary([str(tmp_path)])
        assert library.texture_for('textures/absent') is None

    def test_a_name_with_an_image_resolves_to_a_texture(self, tmp_path):
        from PIL import Image
        directory = tmp_path / 'textures'
        directory.mkdir()
        Image.new('RGB', (4, 4), (255, 0, 0)).save(directory / 'frame.png')
        library = MaterialLibrary([str(tmp_path)])
        assert library.texture_for('textures/frame') is not None

    def test_the_same_name_gives_the_same_texture(self, tmp_path):
        """One decode however many surfaces or frames name it."""
        from PIL import Image
        directory = tmp_path / 'textures'
        directory.mkdir()
        Image.new('RGB', (4, 4), (0, 255, 0)).save(directory / 'frame.png')
        library = MaterialLibrary([str(tmp_path)])
        assert library.texture_for('textures/frame') is library.texture_for('textures/frame')
