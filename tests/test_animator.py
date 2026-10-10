"""Driving a map's animated surfaces from one clock.

The evaluation is `twig_bb.surfaceanim`'s and is tested there; this is about
*applying* it -- which appearance or material field each directive lands on,
what a frame of the clock does to it, and the unit conversion between what a `.shader` script
writes and what the scenegraph is in.
"""

import logging

import numpy as np
import pytest

from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.imagedata import ImageDataTexture
from OpenGLContext.scenegraph.pbrmesh import PBRMesh
from OpenGLContext.scenegraph.physicalmaterial import PhysicalMaterial
from OpenGLContext.scenegraph.texturemapping import (
    CHANNELS, PER_WORD, texture_mapping, transform_for, transform_matrix)
from PIL import Image

from twig_bb import animator, surfaceanim as anim, surfaces
from twig_bb.worldgeometry import SCENE_SCALE


def style(**named):
    named.setdefault('name', 'textures/x')
    return surfaces.SurfaceStyle(**named)


def scrolling(s=1.0, t=0.0):
    return anim.SurfaceAnimation(tcmods=(anim.TCModScroll(s, t),))


def surface(alphaMode='OPAQUE', **fields):
    """An appearance as `twig_bb.materials` builds one, with its material's fields."""
    return Appearance(material=PhysicalMaterial(**fields), alphaMode=alphaMode)


def texture(colour=(255, 0, 0)):
    return ImageDataTexture(image=Image.new('RGB', (2, 2), colour))


def base_matrix(appearance):
    """The 2x3 matrix the base colour map's coordinates are drawn through."""
    label = appearance.material.textureMapping('baseColor')
    return transform_matrix(transform_for(appearance, label))


def transform_slot(appearance, mesh, channel):
    """The transform slot `channel` reads through in a draw; 0 is none."""
    index = CHANNELS.index(channel)
    word = texture_mapping(appearance, mesh).codes[index // PER_WORD]
    return (word >> (5 * (index % PER_WORD))) >> 2 & 7


def flat(count=4):
    positions = np.zeros((count, 3), dtype='f')
    positions[:, 0] = np.arange(count) * SCENE_SCALE
    normals = np.tile((0.0, 1.0, 0.0), (count, 1)).astype('f')
    texcoords = np.zeros((count, 2), dtype='f')
    return PBRMesh(positions=positions, normals=normals, texcoords=texcoords)


class TestWhatIsWorthDriving:
    def test_a_still_surface_is_not_taken_on(self):
        driver = animator.SurfaceAnimator()
        assert not driver.add(style(), surface())
        assert len(driver) == 0

    def test_an_animated_surface_is(self):
        driver = animator.SurfaceAnimator()
        assert driver.add(style(animation=scrolling()), surface())
        assert len(driver) == 1

    def test_a_constant_transform_is_applied_once_and_not_driven(self):
        """A `tcMod scale` tiles the surface; it is not an animation."""
        appearance = surface()
        driver = animator.SurfaceAnimator()
        constant = anim.SurfaceAnimation(tcmods=(anim.TCModScale(2.0, 2.0),))
        assert not driver.add(style(animation=constant), appearance)
        assert np.allclose(base_matrix(appearance), [[2.0, 0.0, 0.0], [0.0, 2.0, 0.0]])

    def test_updating_an_empty_animator_is_harmless(self):
        assert animator.SurfaceAnimator().update(3.0) == 0

    def test_it_reports_how_many_surfaces_it_moved(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), surface())
        driver.add(style(animation=scrolling(0.0, 1.0)), surface())
        assert driver.update(1.0) == 2


class TestTextureTransform:
    def lightmapped(self):
        return surface(baseTexture=texture(), lightmapTexture=texture(),
                       lightmapTextureMapping='TEXCOORD_1')

    def test_a_scroll_reaches_the_appearances_texture_transform(self):
        appearance = surface()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(0.5, 0.0)), appearance)
        driver.update(2.0)
        assert base_matrix(appearance)[0][2] == pytest.approx(1.0)

    def test_the_transform_moves_as_the_clock_does(self):
        appearance = surface()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(1.0, 0.0)), appearance)
        driver.update(1.0)
        first = base_matrix(appearance)
        driver.update(2.0)
        assert not np.allclose(first, base_matrix(appearance))

    def test_only_the_base_colour_channel_is_transformed(self):
        """A scrolling texture must not drag the baked lightmap with it."""
        appearance, mesh = self.lightmapped(), flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), appearance, mesh=mesh)
        driver.update(0.25)
        assert transform_slot(appearance, mesh, 'baseColor') != 0
        assert transform_slot(appearance, mesh, 'lightmap') == 0

    def test_the_lightmaps_coordinate_set_is_kept(self):
        """A lightmapped surface samples its second UV set; that must survive."""
        appearance = self.lightmapped()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), appearance)
        assert appearance.material.lightmapTextureMapping == 'TEXCOORD_1'

    def test_updating_changes_what_the_pass_draws_the_surface_through(self):
        appearance, mesh = self.lightmapped(), flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), appearance, mesh=mesh)
        before = texture_mapping(appearance, mesh).key
        driver.update(0.25)
        assert texture_mapping(appearance, mesh).key != before

    def test_surfaces_sharing_an_appearance_share_its_transform(self):
        appearance = surface()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), appearance)
        transform = appearance.textureTransform
        driver.add(style(animation=scrolling()), appearance)
        assert appearance.textureTransform is transform


class TestColourAndOpacity:
    def test_a_colour_wave_reaches_the_base_colour(self):
        appearance = surface(baseColor=(1.0, 1.0, 1.0))
        material = appearance.material
        wave = anim.Wave('sin', 0.5, 0.5, 0.25, 0.0)
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(
            rgbgen=anim.ColorGen.wave(wave), tcmods=(anim.TCModScroll(1, 0),))),
            appearance)
        driver.update(0.0)
        assert tuple(material.baseColor) == pytest.approx((1.0, 1.0, 1.0))

    def test_a_colour_wave_darkens_the_surface_at_its_trough(self):
        appearance = surface(baseColor=(1.0, 1.0, 1.0))
        wave = anim.Wave('sin', 0.5, 0.5, 0.0, 1.0)
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(
            rgbgen=anim.ColorGen.wave(wave))), appearance)
        driver.update(0.75)
        assert max(appearance.material.baseColor) < 0.1

    def test_the_authored_base_colour_is_multiplied_not_replaced(self):
        """A material with no texture carries its colour in baseColor."""
        appearance = surface(baseColor=(0.5, 0.25, 0.0))
        gen = anim.ColorGen.wave(anim.Wave('sin', 1.0, 0.0, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(rgbgen=gen)), appearance)
        driver.update(0.0)
        assert tuple(appearance.material.baseColor) == pytest.approx((0.5, 0.25, 0.0))

    def test_an_alpha_wave_reaches_a_blended_surface(self):
        appearance = surface(alphaMode='BLEND', transparency=0.0)
        gen = anim.AlphaGen(wave_source=anim.Wave('sin', 0.5, 0.5, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(alphagen=gen)), appearance)
        driver.update(0.75)
        assert appearance.material.transparency > 0.9

    def test_an_alpha_wave_is_ignored_on_an_opaque_surface(self):
        """Opacity that cannot be drawn should not silently vanish the surface."""
        appearance = surface(alphaMode='OPAQUE', transparency=0.0)
        gen = anim.AlphaGen(wave_source=anim.Wave('sin', 0.0, 0.0, 0.0, 1.0))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(alphagen=gen)), appearance)
        driver.update(0.0)
        assert appearance.material.transparency == pytest.approx(0.0)


class TestFrameAnimation:
    def test_the_frame_texture_is_swapped_as_the_clock_advances(self):
        loaded = {}

        def resolve(name):
            loaded.setdefault(name, texture())
            return loaded[name]

        appearance = surface()
        material = appearance.material
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   appearance, resolve=resolve)
        driver.update(0.0)
        assert material.baseTexture is loaded['a.tga']
        driver.update(0.6)
        assert material.textures['baseColor'] is loaded['b.tga']

    def test_the_same_frame_is_not_re_uploaded(self):
        calls = []

        def resolve(name):
            calls.append(name)
            return texture()

        cycle = anim.AnimMap(1.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   surface(), resolve=resolve)
        driver.update(0.0)
        driver.update(0.1)
        driver.update(0.2)
        assert calls == ['a.tga']

    def test_a_frame_that_will_not_resolve_leaves_the_last_one_showing(self):
        original = texture()
        appearance = surface(baseTexture=original)
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)),
                   appearance, resolve=lambda name: None)
        driver.update(0.0)
        assert appearance.material.textures['baseColor'] is original

    def test_with_no_resolver_a_cycle_does_nothing(self):
        appearance = surface()
        cycle = anim.AnimMap(2.0, ('a.tga', 'b.tga'))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=anim.SurfaceAnimation(animmap=cycle)), appearance)
        driver.update(0.5)
        assert 'baseColor' not in appearance.material.textures


class TestDeformation:
    def wave(self, amplitude=4.0):
        return anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, amplitude, 0.25, 0.0)),))

    def test_a_deform_reaches_the_mesh(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), surface(), mesh=mesh)
        driver.update(0.0)
        assert mesh.positions[:, 1].max() > 0.0

    def test_the_amplitude_is_in_map_units_not_metres(self):
        """`deformVertexes wave ... 4 ...` is four map units, not four metres."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave(4.0)), surface(), mesh=mesh)
        driver.update(0.0)
        assert mesh.positions[0, 1] == pytest.approx(4.0 * SCENE_SCALE, rel=1e-4)

    def test_the_surface_returns_to_rest_rather_than_walking_away(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        wave = anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, 4.0, 0.0, 1.0)),))
        driver.add(style(animation=wave), surface(), mesh=mesh)
        driver.update(0.0)
        driver.update(1.0)
        assert mesh.positions[0, 1] == pytest.approx(0.0, abs=1e-6)

    def test_turbulence_moves_the_texture_coordinates(self):
        mesh = flat()
        turb = anim.SurfaceAnimation(tcmods=(
            anim.TCModTurb(anim.Wave('sin', 0.0, 0.2, 0.0, 1.0)),))
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=turb), surface(), mesh=mesh)
        driver.update(0.3)
        assert np.abs(mesh.texcoords).max() > 0.0

    def test_a_deforming_surface_asks_for_dynamic_texcoords(self):
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), surface(), mesh=mesh)
        assert mesh.deforms_texcoords

    def test_a_scrolling_surface_does_not_touch_the_mesh(self):
        """A texture matrix costs a uniform; vertices cost vertices."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), surface(), mesh=mesh)
        assert not mesh.is_deformable

    def test_a_deform_with_no_mesh_is_harmless(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=self.wave()), surface())
        driver.update(1.0)


class Exploding(PhysicalMaterial):
    """A material whose colour cannot be set once it is built."""

    def __setattr__(self, name, value):
        if name == 'baseColor':
            raise RuntimeError('no')
        super().__setattr__(name, value)


def pulsing():
    """An animation that sets its material's colour every frame."""
    return anim.SurfaceAnimation(
        rgbgen=anim.ColorGen.wave(anim.Wave('sin', 0.5, 0.5, 0.0, 1.0)))


class TestClock:
    def test_every_surface_sees_the_same_time(self):
        first, second = surface(), surface()
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling(0.5, 0.0)), first)
        driver.add(style(animation=scrolling(0.5, 0.0)), second)
        driver.update(7.25)
        assert base_matrix(first)[0][2] == pytest.approx(3.625)
        assert np.allclose(base_matrix(first), base_matrix(second))

    def test_a_failing_surface_does_not_stop_the_others(self):
        """One bad surface must not silently freeze a whole map."""
        good = surface()
        bad = Appearance(material=Exploding())
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=pulsing()), bad)
        driver.add(style(animation=scrolling()), good)
        driver.update(1.0)
        assert base_matrix(good)[0][2] == pytest.approx(1.0)

    def test_a_failing_surface_is_reported_once_and_retired(self, caplog):
        """The traceback is logged the first time, not sixty times a second."""
        bad = Appearance(material=Exploding())
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=pulsing()), bad)
        driver.add(style(animation=scrolling()), surface())
        with caplog.at_level(logging.WARNING, logger=animator.__name__):
            assert driver.update(1.0) == 1
            assert driver.update(2.0) == 1
        failures = [record for record in caplog.records
                    if record.name == animator.__name__]
        assert len(failures) == 1
        assert failures[0].exc_info is not None
        assert len(driver) == 1


def test_a_scene_can_be_collected_from_its_batches():
    """The whole map's animated surfaces, gathered in one pass."""
    entries = [
        (style(animation=scrolling()), surface(), flat()),
        (style(), surface(), flat()),
    ]
    driver = animator.SurfaceAnimator()
    for surface_style, material, mesh in entries:
        driver.add(surface_style, material, mesh=mesh)
    assert len(driver) == 1


class TestIdempotence:
    """Moving to a time it is already at should cost nothing."""

    def test_a_repeated_time_moves_nothing(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), surface())
        assert driver.update(1.0) == 1
        assert driver.update(1.0) == 0

    def test_a_new_time_moves_it_again(self):
        driver = animator.SurfaceAnimator()
        driver.add(style(animation=scrolling()), surface())
        driver.update(1.0)
        assert driver.update(1.5) == 1

    def test_a_repeated_time_does_not_re_deform_the_mesh(self):
        """A capture pins the clock; recomputing the same wave is pure waste."""
        mesh = flat()
        driver = animator.SurfaceAnimator()
        wave = anim.SurfaceAnimation(deforms=(
            anim.DeformWave(0.0, anim.Wave('sin', 0.0, 4.0, 0.25, 0.0)),))
        driver.add(style(animation=wave), surface(), mesh=mesh)
        driver.update(0.5)
        version = mesh.deform_version
        driver.update(0.5)
        assert mesh.deform_version == version
