"""Driving a map's animated surfaces from one clock.

The evaluation is `twig_bb.surfaceanim`'s and is tested there; this is about
*applying* it -- which material field each directive lands on, what a frame of
the clock does to it, and the unit conversion between what a `.shader` script
writes and what the scenegraph is in.
"""

import numpy as np
import pytest

from OpenGLContext.scenegraph.pbrmaterial import PBRMaterial
from OpenGLContext.scenegraph.pbrmesh import PBRMesh

from twig_bb import animator, surfaceanim as anim, surfaces
from twig_bb.worldgeometry import SCENE_SCALE


def style(**named):
    named.setdefault('name', 'textures/x')
    return surfaces.SurfaceStyle(**named)


def scrolling(s=1.0, t=0.0):
    return anim.SurfaceAnimation(tcmods=(anim.TCModScroll(s, t),))


def flat(count=4):
    positions = np.zeros((count, 3), dtype='f')
    positions[:, 0] = np.arange(count) * SCENE_SCALE
    normals = np.tile((0.0, 1.0, 0.0), (count, 1)).astype('f')
    texcoords = np.zeros((count, 2), dtype='f')
    return PBRMesh(positions=positions, normals=normals, texcoords=texcoords)


class TestWhatIsWorthDriving:
    def test_a_still_surface_is_not_taken_on(self):
        driver = animator.SurfaceAnimator()
        assert not driver.add(style(), PBRMaterial())
        assert len(driver) == 0

    def test_an_animated_surface_is(self):
        driver = animator.SurfaceAnimator()
        assert driver.add(style(animation=scrolling()), PBRMaterial())
        assert len(driver) == 1

    def test_a_constant_transform_is_applied_once_and_not_driven(self):
        """A `tcMod scale` tiles the surface; it is not an animation."""
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        constant = anim.SurfaceAnimation(tcmods=(anim.TCModScale(2.0, 2.0),))
        assert not driver.add(style(animation=constant), material)
        assert material.uv_transform is not None
        assert np.allclose(np.asarray(material.uv_transform)[0][0], 2.0)

    def test_updating_an_empty_animator_is_harmless(self):
        assert animator.SurfaceAnimator().update(3.0) == 0

    def test_it_reports_how_many_surfaces_it_moved(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), PBRMaterial())
        driver.add(style(animation=scrolling(0.0, 1.0)), PBRMaterial())
        assert driver.update(1.0) == 2


class TestTextureTransform:
    def test_a_scroll_reaches_the_materials_uv_transform(self):
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(0.5, 0.0)), material)
        driver.update(2.0)
        assert np.allclose(np.asarray(material.uv_transform)[0][2], 1.0)

    def test_the_transform_moves_as_the_clock_does(self):
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(1.0, 0.0)), material)
        driver.update(1.0)
        first = np.asarray(material.uv_transform).copy()
        driver.update(2.0)
        assert not np.allclose(first, np.asarray(material.uv_transform))

    def test_only_the_base_colour_channel_is_transformed(self):
        """A scrolling texture must not drag the baked lightmap with it."""
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), material)
        assert material.texCoordMask & (animator.BASE_COLOR_BIT << 8)
        assert not material.texCoordMask & (animator.LIGHTMAP_BIT << 8)

    def test_the_existing_texcoord_mask_is_kept(self):
        """A lightmapped surface samples its second UV set; that must survive."""
        material = PBRMaterial(texCoordMask=animator.LIGHTMAP_BIT)
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), material)
        assert material.texCoordMask & animator.LIGHTMAP_BIT

    def test_updating_bumps_the_material_version_so_the_pass_re_uploads(self):
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), material)
        before = material._ubo_version
        driver.update(1.0)
        assert material._ubo_version > before

    def test_the_transform_is_a_row_major_three_by_three(self):
        material = PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), material)
        driver.update(1.0)
        assert np.asarray(material.uv_transform).shape == (3, 3)


class TestColourAndOpacity:
    def test_a_colour_wave_reaches_the_base_colour(self):
        material = PBRMaterial(baseColor=(1.0, 1.0, 1.0))
        wave = anim.Wave('sin', 0.5, 0.5, 0.25, 0.0)
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(
            rgbgen=anim.ColorGen.wave(wave), tcmods=(anim.TCModScroll(1, 0),))),
            material)
        driver.update(0.0)
        assert tuple(material.baseColor) == pytest.approx((1.0, 1.0, 1.0))

    def test_a_colour_wave_darkens_the_surface_at_its_trough(self):
        material = PBRMaterial(baseColor=(1.0, 1.0, 1.0))
        wave = anim.Wave('sin', 0.5, 0.5, 0.0, 1.0)
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(
            rgbgen=anim.ColorGen.wave(wave))), material)
        driver.update(0.75)
        assert max(material.baseColor) < 0.1

    def test_the_authored_base_colour_is_multiplied_not_replaced(self):
        """A material with no texture carries its colour in baseColor."""
        material = PBRMaterial(baseColor=(0.5, 0.25, 0.0))
        gen = anim.ColorGen.wave(anim.Wave('sin', 1.0, 0.0, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(rgbgen=gen)), material)
        driver.update(0.0)
        assert tuple(material.baseColor) == pytest.approx((0.5, 0.25, 0.0))

    def test_an_alpha_wave_reaches_a_blended_material(self):
        material = PBRMaterial(alphaMode='BLEND', transparency=0.0)
        gen = anim.AlphaGen(wave_source=anim.Wave('sin', 0.5, 0.5, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(alphagen=gen)), material)
        driver.update(0.75)
        assert material.transparency > 0.9

    def test_an_alpha_wave_is_ignored_on_an_opaque_material(self):
        """Opacity that cannot be drawn should not silently vanish the surface."""
        material = PBRMaterial(alphaMode='OPAQUE', transparency=0.0)
        gen = anim.AlphaGen(wave_source=anim.Wave('sin', 0.0, 0.0, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(alphagen=gen)), material)
        driver.update(0.0)
        assert material.transparency == pytest.approx(0.0)


class TestFrameAnimation:
    def test_the_frame_texture_is_swapped_as_the_clock_advances(self):
        loaded = {}

        def resolve(name):
            loaded.setdefault(name, object())
            return loaded[name]

        material = PBRMaterial()
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   material, resolve=resolve)
        driver.update(0.0)
        first = material.textures.get('baseColor')
        driver.update(0.6)
        assert material.textures.get('baseColor') is not first

    def test_the_same_frame_is_not_re_uploaded(self):
        calls = []

        def resolve(name):
            calls.append(name)
            return object()

        cycle = anim.AnimMap(1.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   PBRMaterial(), resolve=resolve)
        driver.update(0.0)
        driver.update(0.1)
        driver.update(0.2)
        assert calls == ['a.tga']

    def test_a_frame_that_will_not_resolve_leaves_the_last_one_showing(self):
        material = PBRMaterial(textures={'baseColor': 'original'})
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   material, resolve=lambda name: None)
        driver.update(0.0)
        assert material.textures['baseColor'] == 'original'

    def test_with_no_resolver_a_cycle_does_nothing(self):
        material = PBRMaterial()
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)), material)
        driver.update(0.5)
        assert 'baseColor' not in material.textures


class TestDeformation:
    def wave(self, amplitude=4.0):
        return anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, amplitude, 0.25, 0.0)),))

    def test_a_deform_reaches_the_mesh(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), PBRMaterial(), mesh=mesh)
        driver.update(0.0)
        assert mesh.positions[:, 1].max() > 0.0

    def test_the_amplitude_is_in_map_units_not_metres(self):
        """`deformVertexes wave ... 4 ...` is four map units, not four metres."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave(4.0)), PBRMaterial(), mesh=mesh)
        driver.update(0.0)
        assert mesh.positions[0, 1] == pytest.approx(4.0 * SCENE_SCALE, rel=1e-4)

    def test_the_surface_returns_to_rest_rather_than_walking_away(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        wave = anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, 4.0, 0.0, 1.0)),))
        driver.add(style(animation=wave), PBRMaterial(), mesh=mesh)
        driver.update(0.0)
        driver.update(1.0)
        assert mesh.positions[0, 1] == pytest.approx(0.0, abs=1e-6)

    def test_turbulence_moves_the_texture_coordinates(self):
        mesh = flat()
        turb = anim.SurfaceAnimation(tcmods=(
            anim.TCModTurb(anim.Wave('sin', 0.0, 0.2, 0.0, 1.0)),))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=turb), PBRMaterial(), mesh=mesh)
        driver.update(0.3)
        assert np.abs(mesh.texcoords).max() > 0.0

    def test_a_deforming_surface_asks_for_dynamic_texcoords(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), PBRMaterial(), mesh=mesh)
        assert mesh.deforms_texcoords

    def test_a_scrolling_surface_does_not_touch_the_mesh(self):
        """A texture matrix costs a uniform; vertices cost vertices."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), PBRMaterial(), mesh=mesh)
        assert not mesh.is_deformable

    def test_a_deform_with_no_mesh_is_harmless(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), PBRMaterial())
        driver.update(1.0)


class TestClock:
    def test_every_surface_sees_the_same_time(self):
        first, second = PBRMaterial(), PBRMaterial()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(0.5, 0.0)), first)
        driver.add(style(animation=scrolling(0.5, 0.0)), second)
        driver.update(7.25)
        assert np.allclose(np.asarray(first.uv_transform),
                           np.asarray(second.uv_transform))

    def test_a_failing_surface_does_not_stop_the_others(self):
        """One bad material must not silently freeze a whole map."""
        class Exploding(PBRMaterial):
            armed = False

            def __setattr__(self, name, value):
                if name == 'uv_transform' and self.armed:
                    raise RuntimeError('no')
                super().__setattr__(name, value)

        good = PBRMaterial()
        bad = Exploding()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), bad)
        bad.armed = True
        driver.add(style(animation=scrolling()), good)
        driver.update(1.0)
        assert good.uv_transform is not None


def test_a_scene_can_be_collected_from_its_batches():
    """The whole map's animated surfaces, gathered in one pass."""
    entries = [
        (style(animation=scrolling()), PBRMaterial(), flat()),
        (style(), PBRMaterial(), flat()),
    ]
    driver = animator.SurfaceAnimator()
    for surface_style, material, mesh in entries:
        driver.add(surface_style, material, mesh=mesh)
    assert len(driver) == 1


class TestIdempotence:
    """Moving to a time it is already at should cost nothing."""

    def test_a_repeated_time_moves_nothing(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), PBRMaterial())
        assert driver.update(1.0) == 1
        assert driver.update(1.0) == 0

    def test_a_new_time_moves_it_again(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), PBRMaterial())
        driver.update(1.0)
        assert driver.update(1.5) == 1

    def test_a_repeated_time_does_not_re_deform_the_mesh(self):
        """A capture pins the clock; recomputing the same wave is pure waste."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        wave = anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, 4.0, 0.25, 0.0)),))
        driver.add(style(animation=wave), PBRMaterial(), mesh=mesh)
        driver.update(0.5)
        version = mesh._deform_version
        driver.update(0.5)
        assert mesh._deform_version == version
