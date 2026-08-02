"""Being *inside* a liquid rather than merely touching one.

Three things change when the camera goes under: the view fogs to the liquid's
own colour, the sound muffles, and the body starts swimming.  The third is the
character controller's and is tested with it; the first two are here.

None of this needs a window.  What the viewer decides is a `Fog` node's fields
and a number on the audio engine, and both are data.
"""

from __future__ import annotations

import pytest

from twitchoglc import liquids, underwater


class FakeContext:
    """A context with the two things being submerged reaches.

    The fog is a real ``Fog`` node and the engine is a real ``AudioEngine`` on
    a null device, because the muffle is a number on the mixer and the point of
    the test is that it gets there.
    """

    def __init__(self):
        self.fog = underwater.liquid_fog()


@pytest.fixture
def context():
    """A context with a real audio engine attached the way one really is."""
    from OpenGLContext.audio import scene as audioscene
    from omi_audio.device import NullDevice
    from omi_audio.engine import AudioEngine

    made = FakeContext()
    audioscene._engines[made] = AudioEngine(device=NullDevice(sample_rate=8000),
                                            voices=4)
    yield made
    audioscene.close(made)


def muffle(context):
    from OpenGLContext.audio import scene as audioscene
    return audioscene.existing_engine(context).muffle


def pool(kind, lo=(0, 0, 0), hi=(10, 5, 10)):
    import numpy as np
    return liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array(lo, 'd'), maxs=np.array(hi, 'd'),
                             kind=kind)])


class TestTheFogOfEachLiquid:

    def test_a_fog_starts_switched_off(self):
        """A `visibilityRange` of 0 is no fog at all, and dry land is the
        overwhelmingly common case."""
        assert underwater.liquid_fog().visibilityRange == 0.0

    @pytest.mark.parametrize('kind', [liquids.WATER, liquids.SLIME, liquids.LAVA])
    def test_going_under_switches_it_on(self, kind):
        fog = underwater.liquid_fog()
        underwater.apply(fog, kind)
        assert fog.visibilityRange > 0.0

    def test_surfacing_switches_it_off_again(self):
        fog = underwater.liquid_fog()
        underwater.apply(fog, liquids.WATER)
        underwater.apply(fog, '')
        assert fog.visibilityRange == 0.0

    def test_the_three_liquids_are_three_different_colours(self):
        colours = set()
        for kind in (liquids.WATER, liquids.SLIME, liquids.LAVA):
            fog = underwater.liquid_fog()
            underwater.apply(fog, kind)
            colours.add(tuple(round(float(v), 4) for v in fog.color))
        assert len(colours) == 3

    def test_water_reads_blue_and_lava_reads_red(self):
        """Not decoration: the colour is the only warning a player gets."""
        water, lava = underwater.liquid_fog(), underwater.liquid_fog()
        underwater.apply(water, liquids.WATER)
        underwater.apply(lava, liquids.LAVA)
        assert water.color[2] > water.color[0]
        assert lava.color[0] > lava.color[2]

    def test_lava_is_the_least_transparent(self):
        """You cannot see through molten rock, and that has to be obvious."""
        ranges = {}
        for kind in (liquids.WATER, liquids.SLIME, liquids.LAVA):
            fog = underwater.liquid_fog()
            underwater.apply(fog, kind)
            ranges[kind] = fog.visibilityRange
        assert ranges[liquids.LAVA] < ranges[liquids.SLIME] < ranges[liquids.WATER]

    def test_an_unknown_liquid_still_fogs(self):
        """A kind this table has no entry for must not read as dry land."""
        fog = underwater.liquid_fog()
        underwater.apply(fog, 'quicksilver')
        assert fog.visibilityRange > 0.0

    def test_the_fog_closes_in_rather_than_fading_evenly(self):
        """Water is clear close up and opaque a few metres out.

        A linear fade tints the weapon in your hands as much as it tints the
        wall behind it, which reads as a coloured pane of glass over the
        screen; the exponential curve hangs back and then closes.
        """
        fog = underwater.liquid_fog()
        underwater.apply(fog, liquids.WATER)
        assert fog.fogType == 'EXPONENTIAL'


class TestTheMuffle:

    def test_dry_land_is_not_muffled(self):
        assert underwater.muffle_for('') == 0.0

    def test_going_under_muffles_the_whole_mix(self):
        assert underwater.muffle_for(liquids.WATER) > 0.5

    def test_the_muffle_is_not_total(self):
        """Silence would read as the sound having broken, not as water."""
        assert underwater.muffle_for(liquids.WATER) < 1.0


class TestTheWholeStepFromAViewer:
    """What the frame loop calls, once, with the camera's position."""

    def test_a_camera_in_water_fogs_and_muffles_together(self, context):
        underwater.update(context, pool(liquids.WATER), (5, 2, 5))
        assert context.fog.visibilityRange > 0.0
        assert muffle(context) > 0.0

    def test_a_camera_in_air_leaves_both_alone(self, context):
        underwater.update(context, pool(liquids.WATER), (99, 99, 99))
        assert context.fog.visibilityRange == 0.0
        assert muffle(context) == 0.0

    def test_leaving_the_water_clears_both(self, context):
        underwater.update(context, pool(liquids.WATER), (5, 2, 5))
        underwater.update(context, pool(liquids.WATER), (99, 99, 99))
        assert context.fog.visibilityRange == 0.0
        assert muffle(context) == 0.0

    def test_the_liquid_found_is_reported_back(self, context):
        found = underwater.update(context, pool(liquids.LAVA), (5, 2, 5))
        assert found == liquids.LAVA

    def test_a_map_with_no_liquid_is_harmless(self, context):
        underwater.update(context, liquids.LiquidVolumes([]), (0, 0, 0))
        assert context.fog.visibilityRange == 0.0

    def test_no_volumes_at_all_is_harmless(self, context):
        """A viewer between maps, or one that never started walking."""
        assert underwater.update(context, None, (0, 0, 0)) == ''

    def test_a_context_with_no_sound_still_fogs(self):
        """Sound is optional; the view is not, and neither may open a device.

        A machine with no audio has no engine on its context at all, and
        walking into a pool must not be the thing that tries to make one.
        """
        from OpenGLContext.audio import scene as audioscene

        silent = FakeContext()
        underwater.update(silent, pool(liquids.WATER), (5, 2, 5))
        assert silent.fog.visibilityRange > 0.0
        assert audioscene.existing_engine(silent) is None
