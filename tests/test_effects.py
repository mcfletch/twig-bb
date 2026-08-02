"""What a fight looks like: which burst, where, and how much of it to show.

The choice of effect is arithmetic over an event, so it is tested here with no
window.  That a particle reaches a pixel is a GL smoke test and is not this
file's job.
"""

from __future__ import annotations

import numpy as np
import pytest

from twitchoglc import arena, effects, game, weapons


@pytest.fixture
def match():
    made = arena.Arena(weapons=weapons.default_table(), fragLimit=15,
                       timeLimit=10.0)
    made.add(game.PLAYER_ID, position=(0.0, 0.0, 0.0), name='You')
    made.add('bot1', position=(10.0, 0.0, 0.0), bot=True, name='Bot 1')
    return made


@pytest.fixture
def shown(match):
    return effects.Effects(match)


def live(shown, kind):
    return shown.emitters[kind].pool.live


class TestChoosingASurface:
    """Stone puffs and metal sparks; anything unnamed falls back to dust."""

    def test_a_metal_surface_sparks(self):
        assert effects.surface_kind('textures/base_wall/metalfloor') \
            == effects.SPARKS

    def test_a_stone_surface_puffs(self):
        assert effects.surface_kind('textures/gothic_block/blocks18') \
            == effects.DUST

    def test_a_surface_nobody_has_classified_still_gets_an_effect(self):
        """A plain puff is honest; no effect at all reads as a shot that missed."""
        assert effects.surface_kind('textures/quiddity/nonsuch') == effects.DUST

    def test_no_surface_at_all_still_gets_one(self):
        assert effects.surface_kind('') == effects.DUST

    def test_it_finds_the_word_wherever_the_content_spelled_it(self):
        """Real content writes metalfloor, e7bmetal, basemetal and metal01."""
        for path in ('textures/e7/e7bmetal', 'textures/base/metal01',
                     'textures/x/basemetal', 'textures/y/metalfloor'):
            assert effects.surface_kind(path) == effects.SPARKS

    def test_it_does_not_care_about_case(self):
        assert effects.surface_kind('TEXTURES/BASE/METAL01') == effects.SPARKS


class TestWhatAnImpactDraws:

    def test_a_hit_on_the_world_bursts_where_it_landed(self, shown, match):
        match.impact(point=(3, 1, 2), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        assert live(shown, effects.DUST) > 0
        assert np.allclose(shown.emitters[effects.DUST].pool.position[0],
                           (3, 1, 2))

    def test_a_hit_on_metal_sparks_instead(self, shown, match):
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='metaldoor')
        shown.show(match.drain())
        assert live(shown, effects.SPARKS) > 0
        assert live(shown, effects.DUST) == 0

    def test_a_hit_on_a_person_is_its_own_effect(self, shown, match):
        """Legible across a room at speed is the job it does."""
        match.impact(point=(1, 0, 0), normal=(0, 1, 0), target='bot1')
        shown.show(match.drain())
        assert live(shown, effects.BLOOD) > 0
        assert live(shown, effects.DUST) == 0

    def test_a_burst_is_thrown_along_the_surface_normal(self, shown, match):
        """Out of the wall rather than into it."""
        match.impact(point=(0, 0, 0), normal=(1, 0, 0), surface='stone')
        shown.show(match.drain())
        assert shown.emitters[effects.DUST].pool.velocity[0][0] > 0.0

    def test_eight_pellets_burst_in_eight_places(self, shown, match):
        for index in range(8):
            match.impact(point=(index, 0, 0), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        places = shown.emitters[effects.DUST].pool.position[:live(shown, effects.DUST)]
        assert len(np.unique(places[:, 0])) == 8

    def test_a_death_is_marked_where_it_happened(self, shown, match):
        match.combatant('bot1').position = np.array([6.0, 0.0, 0.0])
        match.damage('bot1', 500, by=game.PLAYER_ID)
        shown.show(match.drain())
        assert live(shown, effects.GIBS) > 0

    def test_firing_draws_nothing(self, shown, match):
        """A muzzle flash belongs to the weapon model, not to the world."""
        match.fired(game.PLAYER_ID, 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        shown.show(match.drain())
        assert not any(shown.emitters[kind].pool.live for kind in shown.emitters)


class TestTheIntensitySetting:
    """Presentation only: it may never change what happened."""

    def test_full_shows_everything(self, match):
        shown = effects.Effects(match, intensity=effects.FULL)
        match.impact(point=(0, 0, 0), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        assert live(shown, effects.DUST) > 0

    def test_reduced_shows_fewer_particles(self, match):
        full, fewer = (effects.Effects(match, intensity=level)
                       for level in (effects.FULL, effects.REDUCED))
        for each in (full, fewer):
            each.show([arena.Impact(point=(0, 0, 0), normal=(0, 1, 0),
                                    surface='stone')])
        assert 0 < live(fewer, effects.DUST) < live(full, effects.DUST)

    def test_off_shows_nothing(self, match):
        shown = effects.Effects(match, intensity=effects.OFF)
        match.impact(point=(0, 0, 0), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        assert not any(shown.emitters[kind].pool.live for kind in shown.emitters)

    def test_off_still_lets_the_damage_happen(self, match):
        """The setting filters presentation and cannot reach the rules."""
        shown = effects.Effects(match, intensity=effects.OFF)
        before = match.combatant('bot1').health
        match.damage('bot1', 25, by=game.PLAYER_ID)
        shown.show(match.drain())
        assert match.combatant('bot1').health == before - 25

    def test_an_unknown_setting_is_read_as_full(self, match):
        """A typo in a config leaves the game playable and visible."""
        shown = effects.Effects(match, intensity='lavish')
        match.impact(point=(0, 0, 0), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        assert live(shown, effects.DUST) > 0

    def test_the_setting_can_be_changed_while_playing(self, match):
        shown = effects.Effects(match, intensity=effects.OFF)
        shown.intensity = effects.FULL
        match.impact(point=(0, 0, 0), normal=(0, 1, 0), surface='stone')
        shown.show(match.drain())
        assert live(shown, effects.DUST) > 0


class TestPuttingItInTheScene:

    def test_every_kind_is_one_node_in_the_scene(self, shown):
        """A node per impact would be a scenegraph edit a dozen times a second."""
        assert len(shown.group.children) == len(shown.emitters)

    def test_the_particles_stay_where_they_were_thrown(self, shown):
        """World space: a burst does not follow the emitter to the next impact."""
        assert all(emitter.worldSpace for emitter in shown.emitters.values())

    def test_nothing_emits_continuously(self, shown):
        """Every effect here is an event; a rate would be a permanent haze."""
        assert all(float(emitter.rate) == 0.0
                   for emitter in shown.emitters.values())


class TestADetonation:

    def test_it_draws_the_biggest_thing_the_game_has(self, shown, match):
        match.detonated(point=(2, 1, 0), kind='rocket', by=game.PLAYER_ID)
        shown.show(match.drain())
        assert live(shown, effects.BURST) > live(shown, effects.DUST)

    def test_it_bursts_where_it_went_off(self, shown, match):
        match.detonated(point=(2, 1, 0), kind='rocket', by=game.PLAYER_ID)
        shown.show(match.drain())
        assert np.allclose(shown.emitters[effects.BURST].pool.position[0],
                           (2, 1, 0))


class TestATrail:
    """What makes an incoming rocket readable before it arrives."""

    def test_a_projectile_in_flight_leaves_smoke(self, shown):
        shown.trail([(0.0, 1.0, 0.0)], dt=0.1)
        assert live(shown, effects.TRAIL) > 0

    def test_it_is_left_where_the_projectile_is(self, shown):
        shown.trail([(4.0, 1.0, 2.0)], dt=0.1)
        assert np.allclose(shown.emitters[effects.TRAIL].pool.position[0],
                           (4.0, 1.0, 2.0))

    def test_two_projectiles_leave_two_trails(self, shown):
        shown.trail([(0.0, 1.0, 0.0), (9.0, 1.0, 0.0)], dt=0.1)
        places = shown.emitters[effects.TRAIL].pool.position[
            :live(shown, effects.TRAIL)]
        assert len(np.unique(places[:, 0])) == 2

    def test_nothing_in_flight_leaves_nothing(self, shown):
        shown.trail([], dt=0.1)
        assert live(shown, effects.TRAIL) == 0

    def test_a_faster_machine_does_not_get_a_denser_trail(self, match):
        """The rate is per second and the remainder is carried between frames."""
        slow, fast = effects.Effects(match), effects.Effects(match)
        slow.trail([(0.0, 0.0, 0.0)], dt=0.1)
        for _ in range(10):
            fast.trail([(0.0, 0.0, 0.0)], dt=0.01)
        assert abs(live(slow, effects.TRAIL)
                   - live(fast, effects.TRAIL)) <= 1

    def test_the_intensity_setting_reaches_the_trail_too(self, match):
        shown = effects.Effects(match, intensity=effects.OFF)
        shown.trail([(0.0, 0.0, 0.0)], dt=0.5)
        assert live(shown, effects.TRAIL) == 0
