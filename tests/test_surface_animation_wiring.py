"""The animation directives, from a `.shader` script to a surface style.

`SPEC-Q3SHADER §2.4`'s directives were parsed and thrown away; these tests hold
them to being carried all the way through to the style the renderer reads.
"""

import numpy as np
import pytest

from twig_bb import q2bsp, q3shader, surfaceanim as anim, surfaces


def material(text):
    return q3shader.parse(text)['test']


class TestParsingIntoAMaterial:
    def test_a_scrolling_stage_becomes_a_scroll(self):
        found = material('''
            test {
                { map textures/x.tga
                  tcMod scroll 0.1 -0.2 }
            }''')
        assert found.animation.tcmods == (anim.TCModScroll(0.1, -0.2),)

    def test_several_modifiers_are_kept_in_the_order_written(self):
        found = material('''
            test {
                { map textures/x.tga
                  tcMod scale 2 2
                  tcMod scroll 1 0 }
            }''')
        assert [type(m) for m in found.animation.tcmods] == [
            anim.TCModScale, anim.TCModScroll]

    def test_a_turbulent_stage_becomes_turbulence(self):
        found = material('''
            test {
                { map textures/water.tga
                  tcMod turb 0 0.1 0 0.5 }
            }''')
        assert isinstance(found.animation.tcmods[0], anim.TCModTurb)

    def test_a_deform_is_read_from_the_body_not_a_stage(self):
        found = material('''
            test {
                deformVertexes wave 100 sin 0 4 0 0.4
                { map textures/x.tga }
            }''')
        assert isinstance(found.animation.deforms[0], anim.DeformWave)

    def test_several_deforms_are_all_kept(self):
        found = material('''
            test {
                deformVertexes wave 100 sin 0 4 0 0.4
                deformVertexes normal 0.5 2
                { map textures/x.tga }
            }''')
        assert len(found.animation.deforms) == 2

    def test_a_colour_wave_is_read(self):
        found = material('''
            test {
                { map textures/x.tga
                  rgbGen wave sin 0.5 0.5 0 1.6 }
            }''')
        assert found.animation.rgbgen.animated

    def test_an_alpha_wave_is_read(self):
        found = material('''
            test {
                { map textures/x.tga
                  alphaGen wave sin 0.5 0.5 0 1 }
            }''')
        assert found.animation.alphagen.animated

    def test_a_frame_cycle_is_read_with_all_its_frames(self):
        found = material('''
            test {
                { animMap 8 textures/a.tga textures/b.tga textures/c.tga }
            }''')
        assert found.animation.animmap.frames == (
            'textures/a.tga', 'textures/b.tga', 'textures/c.tga')

    def test_the_first_frame_is_still_the_material_image(self):
        """A cycling stage draws its first frame when nothing animates it."""
        found = material('test { { animMap 8 textures/a.tga textures/b.tga } }')
        assert found.image == 'textures/a.tga'

    def test_a_material_with_no_directives_is_not_animated(self):
        assert not material('test { { map textures/x.tga } }').animation.animated

    def test_a_directive_that_does_not_parse_is_skipped(self):
        found = material('''
            test {
                { map textures/x.tga
                  tcMod scroll fast slow }
            }''')
        assert found.animation.tcmods == ()

    def test_an_unknown_modifier_is_skipped(self):
        found = material('test { { map x.tga\n tcMod warp 3 } }')
        assert found.animation.tcmods == ()

    def test_keywords_are_not_case_sensitive(self):
        found = material('test { { map x.tga\n TCMOD SCROLL 1 0 } }')
        assert found.animation.tcmods == (anim.TCModScroll(1.0, 0.0),)

    def test_only_the_first_stages_modifiers_are_taken(self):
        """One PBR material draws one stage; a second stage's tcMod is not it."""
        found = material('''
            test {
                { map textures/a.tga
                  tcMod scroll 1 0 }
                { map textures/b.tga
                  tcMod scroll 0 9 }
            }''')
        assert found.animation.tcmods == (anim.TCModScroll(1.0, 0.0),)


class TestReachingTheStyle:
    def test_the_style_carries_the_animation(self):
        found = material('test { { map x.tga\n tcMod scroll 1 0 } }')
        assert found.style().animation.animated

    def test_a_scrolling_material_sets_the_scrolling_flag(self):
        """The flag has meant nothing until now; it means this."""
        assert material('test { { map x.tga\n tcMod scroll 1 0 } }').style().scrolling

    def test_a_turbulent_material_sets_the_warping_flag(self):
        assert material('test { { map x.tga\n tcMod turb 0 .1 0 .5 } }').style().warping

    def test_a_deforming_material_sets_the_warping_flag(self):
        found = material('test {\n deformVertexes wave 100 sin 0 4 0 0.4\n'
                         ' { map x.tga } }')
        assert found.style().warping

    def test_a_still_material_sets_neither(self):
        style = material('test { { map x.tga } }').style()
        assert not style.scrolling
        assert not style.warping

    def test_the_animation_is_part_of_the_batch_key(self):
        """Two surfaces that animate differently cannot share a draw call."""
        still = surfaces.SurfaceStyle(name='x')
        moving = surfaces.SurfaceStyle(name='x', animation=anim.flowing_animation())
        assert still.batch_key() != moving.batch_key()

    def test_two_identical_animations_batch_together(self):
        first = surfaces.SurfaceStyle(name='x', animation=anim.flowing_animation())
        second = surfaces.SurfaceStyle(name='x', animation=anim.flowing_animation())
        assert first.batch_key() == second.batch_key()

    def test_a_style_with_no_animation_is_still_hashable(self):
        assert hash(surfaces.SurfaceStyle(name='x').batch_key())

    def test_a_style_reports_whether_it_animates(self):
        assert not surfaces.SurfaceStyle(name='x').animated
        assert surfaces.SurfaceStyle(name='x',
                                     animation=anim.flowing_animation()).animated


class TestQuake2Flowing:
    """Version 38 has no script: the flag is the whole of the directive."""

    def test_a_flowing_surface_gets_a_scroll(self):
        style = surfaces.style_from_quake2_flags('x', q2bsp.SURF_FLOWING)
        assert style.animation.animated
        assert style.scrolling

    def test_a_still_surface_gets_none(self):
        assert not surfaces.style_from_quake2_flags('x', 0).animation.animated

    def test_a_warped_surface_is_marked_warping(self):
        style = surfaces.style_from_quake2_flags('x', q2bsp.SURF_WARP)
        assert style.warping


def test_the_transform_moves_as_time_passes():
    """End to end: a script's scroll produces a moving texture matrix."""
    style = material('test { { map x.tga\n tcMod scroll 0.5 0 } }').style()
    at_zero = anim.apply_transform(style.animation.transform_at(0.0), (0.0, 0.0))
    at_two = anim.apply_transform(style.animation.transform_at(2.0), (0.0, 0.0))
    assert at_two[0] - at_zero[0] == pytest.approx(1.0)


def test_a_deforming_style_reports_that_it_costs_vertices():
    found = material('test {\n deformVertexes wave 100 sin 0 4 0 0.4\n { map x.tga } }')
    assert found.style().animation.deforming


def test_a_scrolling_style_does_not():
    assert not material('test { { map x.tga\n tcMod scroll 1 0 } }').style().animation.deforming


def test_a_liquid_material_reads_both_its_deform_and_its_turbulence():
    """What a water surface in real content actually carries."""
    found = material('''
        test {
            qer_editorimage textures/water.tga
            surfaceparm water
            deformVertexes wave 64 sin 0 4 0 0.4
            {
                map textures/water.tga
                tcMod turb 0 0.15 0 0.3
                tcMod scroll 0.05 0.05
            }
        }''')
    style = found.style()
    assert style.liquid
    assert style.warping
    assert style.scrolling
    assert len(style.animation.tcmods) == 2
    assert np.isfinite(style.animation.transform_at(1.0)).all()
