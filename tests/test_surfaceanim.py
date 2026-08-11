"""Surface animation: waves, coordinate modification, deformation, colour.

Everything ``SPEC-Q3SHADER §2.4`` describes is a pure function of scene time, so
every assertion here is a number at a known time.  No window, no map, no
content.
"""

import math

import numpy as np
import pytest

from twig_bb import surfaceanim as anim


class TestWaveFunctions:
    """``SPEC-Q3SHADER §2.4.1``: five shapes, and their ranges are not alike."""

    def test_sine_starts_at_zero_and_peaks_a_quarter_of_the_way_through(self):
        assert anim.wave_shape('sin', 0.0) == pytest.approx(0.0)
        assert anim.wave_shape('sin', 0.25) == pytest.approx(1.0)
        assert anim.wave_shape('sin', 0.75) == pytest.approx(-1.0)

    def test_triangle_rises_then_falls_between_zero_and_one(self):
        assert anim.wave_shape('triangle', 0.0) == pytest.approx(0.0)
        assert anim.wave_shape('triangle', 0.25) == pytest.approx(0.5)
        assert anim.wave_shape('triangle', 0.5) == pytest.approx(1.0)
        assert anim.wave_shape('triangle', 0.75) == pytest.approx(0.5)

    def test_square_is_only_ever_plus_or_minus_one(self):
        assert anim.wave_shape('square', 0.25) == pytest.approx(1.0)
        assert anim.wave_shape('square', 0.75) == pytest.approx(-1.0)

    def test_sawtooth_ramps_up_and_snaps_back(self):
        assert anim.wave_shape('sawtooth', 0.0) == pytest.approx(0.0)
        assert anim.wave_shape('sawtooth', 0.9) == pytest.approx(0.9)

    def test_inverse_sawtooth_ramps_down(self):
        assert anim.wave_shape('inversesawtooth', 0.0) == pytest.approx(1.0)
        assert anim.wave_shape('inversesawtooth', 0.9) == pytest.approx(0.1, abs=1e-6)

    def test_noise_is_bounded_and_held_for_the_cycle(self):
        first = anim.wave_shape('noise', 0.1)
        assert 0.0 <= first <= 1.0
        assert anim.wave_shape('noise', 0.2) == first
        assert anim.wave_shape('noise', 1.1) != first

    def test_an_unknown_function_falls_back_to_sine(self):
        """Content misspells these; a still surface is worse than a sine."""
        assert anim.wave_shape('wobble', 0.25) == pytest.approx(1.0)

    def test_the_shapes_do_not_share_a_range(self):
        """The manual documents them that way; normalising renders wrong."""
        shapes = {name: [anim.wave_shape(name, x / 32.0) for x in range(32)]
                  for name in ('sin', 'triangle', 'sawtooth')}
        assert min(shapes['sin']) < 0.0
        assert min(shapes['triangle']) >= 0.0
        assert min(shapes['sawtooth']) >= 0.0


class TestWave:
    """A wave is a function name plus base, amplitude, phase and frequency."""

    def test_the_value_is_base_plus_amplitude_times_the_shape(self):
        wave = anim.Wave('sin', base=2.0, amplitude=3.0, phase=0.25, frequency=0.0)
        assert wave.at(0.0) == pytest.approx(2.0 + 3.0 * 1.0)

    def test_frequency_is_cycles_per_second(self):
        wave = anim.Wave('sin', 0.0, 1.0, 0.0, 2.0)
        assert wave.at(0.125) == pytest.approx(1.0)     # a quarter of a cycle
        assert wave.at(0.5) == pytest.approx(0.0, abs=1e-9)

    def test_phase_offsets_the_cycle(self):
        moved = anim.Wave('sawtooth', 0.0, 1.0, 0.25, 1.0)
        assert moved.at(0.0) == pytest.approx(0.25)

    def test_a_still_wave_is_constant(self):
        wave = anim.Wave('sin', base=0.7, amplitude=0.0, phase=0.0, frequency=1.0)
        assert wave.at(0.0) == pytest.approx(0.7)
        assert wave.at(3.7) == pytest.approx(0.7)

    def test_it_is_read_from_five_tokens(self):
        wave = anim.Wave.parse(['sin', '0.5', '0.25', '0', '1.6'])
        assert (wave.function, wave.base, wave.amplitude) == ('sin', 0.5, 0.25)
        assert wave.frequency == pytest.approx(1.6)

    def test_too_few_tokens_read_as_nothing(self):
        assert anim.Wave.parse(['sin', '0.5']) is None

    def test_tokens_that_are_not_numbers_read_as_nothing(self):
        assert anim.Wave.parse(['sin', 'x', '1', '0', '1']) is None

    def test_a_wave_is_evaluated_over_an_array_of_times_at_once(self):
        wave = anim.Wave('sin', 0.0, 1.0, 0.0, 1.0)
        values = wave.at(np.array([0.0, 0.25, 0.5]))
        assert np.allclose(values, [0.0, 1.0, 0.0], atol=1e-9)


class TestTextureCoordinateModifiers:
    """``SPEC-Q3SHADER §2.4.2``: what each ``tcMod`` does to the unit square."""

    def transform(self, modifiers, time):
        return anim.coordinate_transform(modifiers, time)

    def test_no_modifiers_is_the_identity(self):
        assert np.allclose(self.transform([], 3.0), np.identity(3))

    def test_scroll_translates_at_a_rate_per_second(self):
        scroll = anim.TCModScroll(0.5, -0.25)
        matrix = self.transform([scroll], 2.0)
        assert np.allclose(anim.apply_transform(matrix, (0.0, 0.0)), (1.0, -0.5))

    def test_scale_multiplies_the_coordinates(self):
        matrix = self.transform([anim.TCModScale(2.0, 4.0)], 0.0)
        assert np.allclose(anim.apply_transform(matrix, (0.5, 0.5)), (1.0, 2.0))

    def test_rotate_turns_about_the_centre_of_the_image(self):
        """A quarter turn a second, so one second is 90 degrees."""
        matrix = self.transform([anim.TCModRotate(90.0)], 1.0)
        assert np.allclose(anim.apply_transform(matrix, (1.0, 0.5)), (0.5, 1.0),
                           atol=1e-9)

    def test_rotate_leaves_the_centre_alone(self):
        matrix = self.transform([anim.TCModRotate(37.0)], 1.3)
        assert np.allclose(anim.apply_transform(matrix, (0.5, 0.5)), (0.5, 0.5))

    def test_stretch_scales_about_the_centre_by_the_reciprocal(self):
        stretch = anim.TCModStretch(anim.Wave('sin', 1.0, 0.0, 0.0, 1.0))
        matrix = self.transform([stretch], 0.0)
        assert np.allclose(anim.apply_transform(matrix, (1.0, 1.0)), (1.0, 1.0))

    def test_stretch_with_a_wave_below_one_magnifies(self):
        stretch = anim.TCModStretch(anim.Wave('sin', 0.5, 0.0, 0.0, 1.0))
        matrix = self.transform([stretch], 0.0)
        assert anim.apply_transform(matrix, (1.0, 0.5))[0] == pytest.approx(1.5)

    def test_a_stretch_wave_of_zero_does_not_divide_by_zero(self):
        stretch = anim.TCModStretch(anim.Wave('sin', 0.0, 0.0, 0.0, 1.0))
        matrix = self.transform([stretch], 0.0)
        assert np.isfinite(matrix).all()

    def test_transform_applies_the_six_numbers_given(self):
        matrix = self.transform([anim.TCModTransform(2, 0, 0, 3, 0.25, 0.5)], 0.0)
        assert np.allclose(anim.apply_transform(matrix, (1.0, 1.0)), (2.25, 3.5))

    def test_modifiers_apply_in_the_order_written(self):
        """Scroll then scale is not scale then scroll."""
        scroll, scale = anim.TCModScroll(1.0, 0.0), anim.TCModScale(2.0, 1.0)
        first = anim.apply_transform(self.transform([scroll, scale], 1.0), (0.0, 0.0))
        second = anim.apply_transform(self.transform([scale, scroll], 1.0), (0.0, 0.0))
        assert not np.allclose(first, second)

    def test_turbulence_is_not_an_affine_transform_and_is_kept_apart(self):
        """It depends on the vertex position, so it cannot be a matrix."""
        turb = anim.TCModTurb(anim.Wave('sin', 0.0, 0.1, 0.0, 1.0))
        assert np.allclose(self.transform([turb], 0.5), np.identity(3))

    def test_turbulence_offsets_depend_on_position_and_time(self):
        turb = anim.TCModTurb(anim.Wave('sin', 0.0, 0.1, 0.0, 1.0))
        points = np.array([[0.0, 0.0, 0.0], [4.0, 0.0, 0.0]])
        early = turb.offsets(points, 0.1)
        assert early.shape == (2, 2)
        assert not np.allclose(early[0], early[1])
        assert not np.allclose(early, turb.offsets(points, 0.6))


class TestParsingModifiers:
    def test_scroll(self):
        assert anim.parse_tcmod(['scroll', '0.1', '-0.2']) == anim.TCModScroll(0.1, -0.2)

    def test_scale(self):
        assert anim.parse_tcmod(['scale', '2', '3']) == anim.TCModScale(2.0, 3.0)

    def test_rotate(self):
        assert anim.parse_tcmod(['rotate', '45']) == anim.TCModRotate(45.0)

    def test_stretch(self):
        modifier = anim.parse_tcmod(['stretch', 'sin', '1', '0.2', '0', '0.5'])
        assert isinstance(modifier, anim.TCModStretch)
        assert modifier.wave.amplitude == pytest.approx(0.2)

    def test_turb(self):
        modifier = anim.parse_tcmod(['turb', '0', '0.1', '0', '0.5'])
        assert isinstance(modifier, anim.TCModTurb)
        assert modifier.wave.function == 'sin'

    def test_transform(self):
        assert anim.parse_tcmod(['transform', '1', '0', '0', '1', '0', '0']) == \
            anim.TCModTransform(1.0, 0.0, 0.0, 1.0, 0.0, 0.0)

    def test_case_does_not_matter(self):
        assert anim.parse_tcmod(['SCROLL', '1', '1']) == anim.TCModScroll(1.0, 1.0)

    def test_an_unknown_modifier_reads_as_nothing(self):
        assert anim.parse_tcmod(['warpspeed', '9']) is None

    def test_missing_arguments_read_as_nothing(self):
        assert anim.parse_tcmod(['scroll', '1']) is None

    def test_an_empty_directive_reads_as_nothing(self):
        assert anim.parse_tcmod([]) is None


class TestDeformation:
    """``SPEC-Q3SHADER §2.4.3``: geometry that moves."""

    def test_a_wave_deform_displaces_along_the_normal(self):
        deform = anim.DeformWave(0.0, anim.Wave('sin', 0.0, 2.0, 0.25, 0.0))
        points = np.zeros((3, 3))
        normals = np.tile((0.0, 0.0, 1.0), (3, 1))
        moved = deform.displace(points, normals, 0.0)
        assert np.allclose(moved[:, 2], 2.0)

    def test_a_division_spreads_the_phase_across_the_surface(self):
        """Positions a quarter of a cycle apart get different displacements.

        The spread is a *phase* offset, not a time offset, which is why it still
        shapes a surface whose wave has no frequency -- a standing ripple.
        """
        deform = anim.DeformWave(100.0, anim.Wave('sin', 0.0, 1.0, 0.0, 0.0))
        points = np.array([[0.0, 0, 0], [25.0, 0, 0], [50.0, 0, 0]])
        normals = np.tile((0.0, 0.0, 1.0), (3, 1))
        moved = deform.displace(points, normals, 0.0)
        assert moved[0, 2] == pytest.approx(0.0, abs=1e-9)
        assert moved[1, 2] == pytest.approx(1.0)
        assert len(set(np.round(moved[:, 2], 6))) > 1

    def test_a_division_of_zero_moves_the_whole_surface_together(self):
        deform = anim.DeformWave(0.0, anim.Wave('sin', 0.0, 1.0, 0.25, 0.0))
        points = np.array([[0.0, 0, 0], [500.0, 0, 0]])
        normals = np.tile((0.0, 0.0, 1.0), (2, 1))
        moved = deform.displace(points, normals, 0.0)
        assert moved[0, 2] == pytest.approx(moved[1, 2])

    def test_a_move_deform_displaces_along_a_fixed_axis(self):
        deform = anim.DeformMove((1.0, 0.0, 0.0),
                                 anim.Wave('sin', 0.0, 3.0, 0.25, 0.0))
        points = np.zeros((2, 3))
        moved = deform.displace(points, np.zeros((2, 3)), 0.0)
        assert np.allclose(moved[:, 0], 3.0)

    def test_a_normal_deform_leaves_positions_alone(self):
        deform = anim.DeformNormal(0.5, 1.0)
        points = np.array([[1.0, 2.0, 3.0]])
        assert np.allclose(deform.displace(points, np.zeros((1, 3)), 1.0), points)

    def test_a_normal_deform_perturbs_the_normals(self):
        deform = anim.DeformNormal(0.5, 1.0)
        normals = np.tile((0.0, 0.0, 1.0), (4, 1))
        points = np.arange(12, dtype='d').reshape(4, 3)
        perturbed = deform.perturb(points, normals, 0.3)
        assert not np.allclose(perturbed, normals)
        assert np.allclose(np.linalg.norm(perturbed, axis=1), 1.0)

    def test_parsing_a_wave_deform(self):
        deform = anim.parse_deform(['wave', '100', 'sin', '0', '4', '0', '0.5'])
        assert isinstance(deform, anim.DeformWave)
        assert deform.division == pytest.approx(100.0)

    def test_parsing_a_move_deform(self):
        deform = anim.parse_deform(
            ['move', '0', '0', '1', 'sin', '0', '8', '0', '0.2'])
        assert isinstance(deform, anim.DeformMove)
        assert np.allclose(deform.axis, (0, 0, 1))

    def test_parsing_a_normal_deform(self):
        assert anim.parse_deform(['normal', '0.5', '2']) == anim.DeformNormal(0.5, 2.0)

    def test_autosprite_is_recognised_but_not_a_deformation(self):
        """It is a rendering technique, not a property of the surface."""
        assert anim.parse_deform(['autosprite']) is None

    def test_an_unknown_deform_reads_as_nothing(self):
        assert anim.parse_deform(['squish', '3']) is None


class TestColourGeneration:
    """``SPEC-Q3SHADER §2.4.4``: colour and opacity over time."""

    def test_a_wave_gives_a_grey_level_on_all_three_channels(self):
        gen = anim.ColorGen.wave(anim.Wave('sin', 0.5, 0.5, 0.25, 0.0))
        assert gen.at(0.0) == pytest.approx((1.0, 1.0, 1.0))

    def test_a_wave_is_clamped_into_range(self):
        gen = anim.ColorGen.wave(anim.Wave('sin', 0.5, 5.0, 0.25, 1.0))
        assert gen.at(0.0) == pytest.approx((1.0, 1.0, 1.0))
        assert gen.at(0.5) == pytest.approx((0.0, 0.0, 0.0))

    def test_a_constant_colour_never_changes(self):
        gen = anim.ColorGen.constant((0.2, 0.4, 0.6))
        assert gen.at(0.0) == gen.at(9.0) == pytest.approx((0.2, 0.4, 0.6))

    def test_identity_is_full_white(self):
        assert anim.ColorGen.identity().at(3.0) == pytest.approx((1.0, 1.0, 1.0))

    def test_an_identity_generator_is_not_animated(self):
        assert not anim.ColorGen.identity().animated
        assert anim.ColorGen.wave(anim.Wave('sin', 0, 1, 0, 1)).animated

    def test_parsing_a_wave(self):
        gen = anim.parse_rgbgen(['wave', 'sin', '0.5', '0.5', '0', '1'])
        assert gen.animated

    def test_parsing_a_constant(self):
        gen = anim.parse_rgbgen(['const', '(', '0.1', '0.2', '0.3', ')'])
        assert gen.at(0.0) == pytest.approx((0.1, 0.2, 0.3))

    def test_parsing_a_source_outside_the_material(self):
        """`vertex` and friends are recognised but generate nothing here."""
        assert anim.parse_rgbgen(['vertex']) is None

    def test_parsing_an_alpha_wave(self):
        gen = anim.parse_alphagen(['wave', 'sin', '0.5', '0.5', '0', '1'])
        assert 0.0 <= gen.at(0.3) <= 1.0

    def test_parsing_a_constant_alpha(self):
        assert anim.parse_alphagen(['const', '0.25']).at(0.0) == pytest.approx(0.25)


class TestFrameAnimation:
    """``SPEC-Q3SHADER §2.4.5``: a stage whose texture cycles."""

    FRAMES = ('a.tga', 'b.tga', 'c.tga', 'd.tga')

    def test_the_first_frame_shows_at_time_zero(self):
        assert anim.AnimMap(2.0, self.FRAMES).frame(0.0) == 'a.tga'

    def test_frames_advance_at_the_given_rate(self):
        cycle = anim.AnimMap(2.0, self.FRAMES)
        assert cycle.frame(0.6) == 'b.tga'
        assert cycle.frame(1.1) == 'c.tga'

    def test_the_cycle_wraps(self):
        assert anim.AnimMap(2.0, self.FRAMES).frame(2.1) == 'a.tga'

    def test_a_rate_of_zero_holds_the_first_frame(self):
        assert anim.AnimMap(0.0, self.FRAMES).frame(99.0) == 'a.tga'

    def test_no_frames_at_all_shows_nothing(self):
        assert anim.AnimMap(2.0, ()).frame(1.0) is None

    def test_parsing(self):
        cycle = anim.parse_animmap(['8', 'x.tga', 'y.tga'])
        assert cycle.frequency == pytest.approx(8.0)
        assert cycle.frames == ('x.tga', 'y.tga')

    def test_parsing_something_that_is_not_a_rate_reads_as_nothing(self):
        assert anim.parse_animmap(['fast', 'x.tga']) is None

    def test_parsing_a_rate_with_no_frames_reads_as_nothing(self):
        assert anim.parse_animmap(['8']) is None


class TestSurfaceAnimation:
    """Everything one material animates, gathered into one value object."""

    def test_a_material_with_no_directives_is_not_animated(self):
        assert not anim.SurfaceAnimation().animated

    def test_a_scroll_makes_it_animated(self):
        assert anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),)).animated

    def test_a_constant_scale_alone_does_not(self):
        """A still transform is a property of the surface, not an animation."""
        assert not anim.SurfaceAnimation(tcmods=(anim.TCModScale(2, 2),)).animated

    def test_a_deformation_makes_it_animated(self):
        deform = anim.DeformWave(0.0, anim.Wave('sin', 0, 1, 0, 1))
        assert anim.SurfaceAnimation(deforms=(deform,)).animated

    def test_a_colour_wave_makes_it_animated(self):
        gen = anim.ColorGen.wave(anim.Wave('sin', 0, 1, 0, 1))
        assert anim.SurfaceAnimation(rgbgen=gen).animated

    def test_a_frame_cycle_makes_it_animated(self):
        assert anim.SurfaceAnimation(animmap=anim.AnimMap(4.0, ('a', 'b'))).animated

    def test_it_reports_whether_it_needs_geometry_each_frame(self):
        """Deformation costs vertices; a texture matrix costs a uniform."""
        assert not anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),)).deforming
        deform = anim.DeformWave(0.0, anim.Wave('sin', 0, 1, 0, 1))
        assert anim.SurfaceAnimation(deforms=(deform,)).deforming

    def test_it_is_hashable_so_it_can_key_a_batch(self):
        first = anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),))
        second = anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),))
        assert first == second
        assert len({first, second}) == 1

    def test_the_transform_at_a_time_composes_its_modifiers(self):
        animation = anim.SurfaceAnimation(
            tcmods=(anim.TCModScroll(1.0, 0.0), anim.TCModScale(2.0, 1.0)))
        matrix = animation.transform_at(1.0)
        assert np.allclose(anim.apply_transform(matrix, (0.0, 0.0)), (2.0, 0.0))

    def test_the_colour_at_a_time_is_white_when_nothing_generates_one(self):
        assert anim.SurfaceAnimation().color_at(3.0) == pytest.approx((1.0, 1.0, 1.0))

    def test_the_opacity_at_a_time_is_one_when_nothing_generates_one(self):
        assert anim.SurfaceAnimation().alpha_at(3.0) == pytest.approx(1.0)


class TestSteadyScrolling:
    """A steady scroll with no script behind it, built by ``flowing_animation``."""

    def test_a_flowing_surface_becomes_a_scroll(self):
        animation = anim.flowing_animation()
        assert animation.animated
        assert isinstance(animation.tcmods[0], anim.TCModScroll)

    def test_it_scrolls_along_one_axis_only(self):
        scroll = anim.flowing_animation().tcmods[0]
        assert (scroll.s != 0.0) != (scroll.t != 0.0)

    def test_it_moves_further_as_time_passes(self):
        animation = anim.flowing_animation()
        near = anim.apply_transform(animation.transform_at(0.0), (0.0, 0.0))
        far = anim.apply_transform(animation.transform_at(1.0), (0.0, 0.0))
        assert not np.allclose(near, far)


def test_the_scene_clock_is_shared_so_surfaces_animate_in_step():
    """One time in, one answer out: two surfaces asked at t agree at t."""
    first = anim.SurfaceAnimation(tcmods=(anim.TCModScroll(0.5, 0.0),))
    second = anim.SurfaceAnimation(tcmods=(anim.TCModScroll(0.5, 0.0),))
    assert np.allclose(first.transform_at(7.25), second.transform_at(7.25))


def test_turbulence_offsets_are_gathered_across_all_the_modifiers():
    animation = anim.SurfaceAnimation(tcmods=(
        anim.TCModTurb(anim.Wave('sin', 0.0, 0.1, 0.0, 1.0)),
        anim.TCModTurb(anim.Wave('sin', 0.0, 0.2, 0.0, 2.0)),
    ))
    points = np.zeros((3, 3))
    offsets = animation.turbulence_at(points, 0.3)
    assert offsets.shape == (3, 2)


def test_a_material_with_no_turbulence_reports_none():
    assert anim.SurfaceAnimation().turbulence_at(np.zeros((2, 3)), 1.0) is None


def test_degrees_per_second_is_the_unit_of_rotation():
    """Stated because a wrong unit here is a surface that spins 57 times too fast."""
    quarter = anim.coordinate_transform([anim.TCModRotate(90.0)], 1.0)
    half = anim.coordinate_transform([anim.TCModRotate(90.0)], 2.0)
    assert np.allclose(anim.apply_transform(quarter, (1.0, 0.5)), (0.5, 1.0), atol=1e-9)
    assert np.allclose(anim.apply_transform(half, (1.0, 0.5)), (0.0, 0.5), atol=1e-9)


def test_a_full_turn_comes_back_to_where_it_started():
    matrix = anim.coordinate_transform([anim.TCModRotate(360.0)], 1.0)
    assert np.allclose(anim.apply_transform(matrix, (0.9, 0.1)), (0.9, 0.1), atol=1e-9)


def test_wave_shape_is_periodic():
    for name in ('sin', 'triangle', 'square', 'sawtooth', 'inversesawtooth'):
        assert anim.wave_shape(name, 0.3) == pytest.approx(
            anim.wave_shape(name, 3.3), abs=1e-9), name


def test_a_negative_time_does_not_break_the_cycle():
    """Scene time is never negative, but a phase can push the argument below zero."""
    assert 0.0 <= anim.wave_shape('sawtooth', -0.25) <= 1.0
    assert math.isfinite(anim.wave_shape('sin', -3.7))


class TestTurbulentProperty:
    """Whether a material churns, asked cheaply rather than by evaluating it."""

    def test_a_plain_animation_is_not_turbulent(self):
        assert not anim.SurfaceAnimation().turbulent

    def test_a_scroll_is_not_turbulent(self):
        assert not anim.SurfaceAnimation(
            tcmods=(anim.TCModScroll(1, 0),)).turbulent

    def test_a_turb_modifier_is(self):
        assert anim.SurfaceAnimation(
            tcmods=(anim.TCModTurb(anim.Wave('sin', 0, 0.1, 0, 1)),)).turbulent

    def test_it_agrees_with_what_turbulence_at_returns(self):
        for animation in (
            anim.SurfaceAnimation(),
            anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),)),
            anim.SurfaceAnimation(tcmods=(anim.TCModTurb(anim.Wave()),)),
        ):
            offsets = animation.turbulence_at(np.zeros((1, 3)), 0.0)
            assert animation.turbulent == (offsets is not None)


class TestCostReporting:
    """A material says what it will cost before anything asks it to move."""

    def test_a_uniform_only_animation_costs_no_vertices(self):
        animation = anim.SurfaceAnimation(tcmods=(anim.TCModScroll(1, 0),))
        assert not animation.deforming
        assert not animation.turbulent

    def test_a_liquid_costs_vertices(self):
        animation = anim.SurfaceAnimation(
            deforms=(anim.DeformWave(0.0, anim.Wave()),),
            tcmods=(anim.TCModTurb(anim.Wave()),))
        assert animation.deforming
        assert animation.turbulent
