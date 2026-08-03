"""The match: who is in it, what shooting does, and who is winning.

Everything here is data and arithmetic, so all of it runs with no window.
That is deliberate rather than convenient: a bot debugged only by watching it is
a bot debugged slowly, and a damage rule that can only be checked by playing is
a damage rule nobody checks.

Three §11 seams are load-bearing and each has tests of its own below: state is
**addressed by id** so it can be enumerated and copied, the simulation **emits
events** and never draws, and nothing in here reads a wall clock.
"""

from __future__ import annotations

import numpy as np
import pytest

from twig_bb import arena, weapons


def _imported_from(node):
    """Every module name one AST node imports, or nothing for other nodes."""
    import ast
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom):
        return [node.module or '']
    return []


def table():
    return weapons.default_table()


def match(bots=1, **named):
    """An arena with a player and ``bots`` opponents, all at the origin."""
    made = arena.Arena(weapons=table(), **named)
    made.add('player', position=(0.0, 0.0, 0.0), name='You')
    for index in range(bots):
        made.add('bot%d' % index, position=(float(index + 5), 0.0, 0.0),
                 name='Bot %d' % index)
    return made


class TestWhoIsInIt:

    def test_a_combatant_joins_with_full_health(self):
        assert match().combatant('player').health == arena.STARTING_HEALTH

    def test_combatants_are_addressed_by_id(self):
        """§11: a thing that can be enumerated and copied can be snapshotted."""
        found = match(bots=2)
        assert sorted(found.ids()) == ['bot0', 'bot1', 'player']

    def test_an_unknown_id_is_no_combatant_rather_than_an_error(self):
        assert match().combatant('nobody') is None

    def test_two_combatants_cannot_share_an_id(self):
        found = match()
        with pytest.raises(ValueError):
            found.add('player', position=(0, 0, 0))

    def test_a_combatant_starts_alive(self):
        assert match().combatant('player').alive

    def test_a_combatant_spawns_with_the_starting_loadout(self):
        """One weapon and its own ammunition; the rest is on the floor.

        A map places what a player picks up (`twig_bb.items`), so spawning
        with everything leaves nothing worth walking to.
        """
        carried = match().combatant('player').player.weapons
        assert carried == ['pistol']

    def test_spawning_and_respawning_hand_out_the_same_thing(self):
        """The asymmetry that dying used to cost four weapons for good.

        `restore` has always given back the starting loadout; `add` handed out
        the whole table, so a first death quietly took the difference away and
        never returned it.
        """
        made = match()
        fought = made.combatant('player').player
        spawned = list(fought.weapons)
        fought.restore(made.weapons)
        assert list(fought.weapons) == spawned


class TestBeingShot:

    def test_damage_comes_off_health(self):
        found = match()
        found.damage('bot0', 30, by='player')
        assert found.combatant('bot0').health == arena.STARTING_HEALTH - 30

    def test_damage_beyond_what_is_left_does_not_go_negative(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert found.combatant('bot0').health == 0

    def test_running_out_of_health_is_death(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert not found.combatant('bot0').alive

    def test_the_dead_take_no_further_damage(self):
        """Otherwise a burst of fire scores several frags for one kill."""
        found = match()
        found.damage('bot0', 500, by='player')
        found.events.clear()
        found.damage('bot0', 50, by='player')
        assert not [event for event in found.events
                    if isinstance(event, arena.Death)]

    def test_armour_takes_its_share_before_health_does(self):
        found = match()
        found.combatant('bot0').armour = 100
        found.damage('bot0', 50, by='player')
        target = found.combatant('bot0')
        assert target.health > arena.STARTING_HEALTH - 50
        assert target.armour < 100

    def test_armour_runs_out_and_the_rest_reaches_health(self):
        found = match()
        found.combatant('bot0').armour = 10
        found.damage('bot0', 100, by='player')
        target = found.combatant('bot0')
        assert target.armour == 0
        assert target.health < arena.STARTING_HEALTH

    def test_damaging_nobody_is_harmless(self):
        match().damage('nobody', 50, by='player')


class TestBeingKilledOutright:
    """Some things are not hits.

    The bottom of the world is not something armour takes a share of, and a
    rule expressing it as a very large number would leave somebody with enough
    armour surviving a fall out of the level.  It is its own verb, and it goes
    through the same bookkeeping every other death does.
    """

    def test_it_ends_them(self):
        found = match()
        assert found.kill('bot0', cause='fall') is True
        assert not found.combatant('bot0').alive
        assert found.combatant('bot0').health == 0

    def test_armour_does_not_soften_it(self):
        found = match()
        found.combatant('bot0').armour = 100
        found.kill('bot0', cause='fall')
        assert not found.combatant('bot0').alive

    def test_it_says_what_did_it(self):
        found = match()
        found.kill('bot0', cause='fall')
        deaths = [event for event in found.events
                  if isinstance(event, arena.Death)]
        assert deaths and deaths[-1].cause == 'fall'

    def test_it_reports_the_hit_as_well(self):
        """The whole presentation layer listens for damage; a death with no
        hit before it arrives out of nowhere."""
        found = match()
        found.kill('bot0', cause='fall')
        hits = [event for event in found.events
                if isinstance(event, arena.Damaged)]
        assert hits and hits[-1].amount == arena.STARTING_HEALTH

    def test_dying_to_the_map_costs_a_frag(self):
        found = match()
        found.kill('bot0', cause='fall')
        assert found.score('bot0') == -1

    def test_a_killer_gets_the_frag_when_there_is_one(self):
        found = match()
        found.kill('bot0', cause='fall', by='player')
        assert found.score('player') == 1

    def test_the_dead_cannot_be_killed_again(self):
        found = match()
        found.kill('bot0', cause='fall')
        found.events.clear()
        assert found.kill('bot0', cause='fall') is False
        assert not found.events

    def test_killing_nobody_is_harmless(self):
        assert match().kill('nobody') is False


class TestTheEventsItEmits:
    """§11: the simulation emits, presentation consumes, and never the reverse."""

    def test_damage_emits_an_event(self):
        found = match()
        found.damage('bot0', 30, by='player')
        hits = [event for event in found.events if isinstance(event, arena.Damaged)]
        assert hits and hits[0].target == 'bot0' and hits[0].by == 'player'

    def test_the_event_carries_how_much_actually_landed(self):
        """Not what was asked for: 500 damage to a target with 100 left is 100."""
        found = match()
        found.damage('bot0', 500, by='player')
        hit = [e for e in found.events if isinstance(e, arena.Damaged)][0]
        assert hit.amount == arena.STARTING_HEALTH

    def test_death_emits_its_own_event(self):
        found = match()
        found.damage('bot0', 500, by='player')
        deaths = [event for event in found.events if isinstance(event, arena.Death)]
        assert deaths and deaths[0].target == 'bot0' and deaths[0].by == 'player'

    def test_events_are_drained_by_whoever_consumes_them(self):
        found = match()
        found.damage('bot0', 5, by='player')
        assert found.drain()
        assert found.drain() == []

    def test_nothing_in_the_rules_reads_a_clock(self):
        """§11: rules read the tick number; a wall clock cannot be replayed."""
        import inspect
        source = inspect.getsource(arena)
        assert 'time.time' not in source
        assert 'perf_counter' not in source

    def test_nothing_in_the_rules_can_reach_the_presentation(self):
        """§11: an import of the HUD here is a damage number computed in a draw call.

        Read from the imports rather than from the text, because the module's
        own prose says the word "HUD" while being the thing that must not
        touch one.
        """
        import ast
        import inspect
        for node in ast.walk(ast.parse(inspect.getsource(arena))):
            for name in _imported_from(node):
                assert not name.startswith('OpenGLContext')
                assert name.rpartition('.')[2] not in (
                    'hud', 'effects', 'firstperson', 'viewer')


class TestSayingAShotWasTaken:
    """A fight has two facts a presentation layer cannot work out for itself.

    Damage says somebody was hurt, which is not the same as somebody firing:
    a shot that missed still made a noise and still came from somewhere, and a
    player who cannot hear an opponent miss cannot find them.
    """

    def test_firing_emits_an_event(self):
        found = match()
        found.fired('bot0', 'rifle', origin=(1, 2, 3), direction=(1, 0, 0))
        shot = [e for e in found.events if isinstance(e, arena.Fired)][0]
        assert shot.shooter == 'bot0'
        assert shot.weapon == 'rifle'
        assert shot.origin == (1.0, 2.0, 3.0)

    def test_the_direction_is_a_unit_heading(self):
        """So a listener can place a sound along it without normalising first."""
        found = match()
        found.fired('bot0', 'rifle', origin=(0, 0, 0), direction=(0, 5, 0))
        shot = [e for e in found.events if isinstance(e, arena.Fired)][0]
        assert shot.direction == pytest.approx((0.0, 1.0, 0.0))

    def test_an_impact_carries_where_and_what_it_met(self):
        found = match()
        found.impact(point=(1, 2, 3), normal=(0, 1, 0), surface='metal',
                     target='', by='player')
        met = [e for e in found.events if isinstance(e, arena.Impact)][0]
        assert met.point == (1.0, 2.0, 3.0)
        assert met.normal == pytest.approx((0.0, 1.0, 0.0))
        assert met.surface == 'metal'
        assert not met.on_somebody

    def test_an_impact_on_a_person_says_so(self):
        """The one a player acts on: did I hit them."""
        found = match()
        found.impact(point=(1, 2, 3), normal=(0, 1, 0), target='bot0',
                     by='player')
        met = [e for e in found.events if isinstance(e, arena.Impact)][0]
        assert met.on_somebody
        assert met.target == 'bot0'

    def test_both_are_drained_with_everything_else(self):
        """One stream, so one loop turns events into effects and sounds."""
        found = match()
        found.fired('player', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        found.impact(point=(1, 0, 0), normal=(-1, 0, 0), by='player')
        kinds = {type(event) for event in found.drain()}
        assert kinds == {arena.Fired, arena.Impact}

    def test_the_events_are_plain_data(self):
        """§11: what a replay writes down and a network sends must be sendable."""
        found = match()
        found.fired('player', 'rifle', origin=(0, 0, 0), direction=(1, 0, 0))
        found.impact(point=(1, 0, 0), normal=(-1, 0, 0), surface='stone')
        for event in found.drain():
            for value in vars(event).values():
                assert isinstance(value, (str, int, float, tuple))


class TestScoring:

    def test_a_kill_scores_a_frag(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert found.score('player') == 1

    def test_everyone_starts_at_nothing(self):
        assert match().score('player') == 0

    def test_killing_yourself_costs_a_frag(self):
        """Otherwise the fastest way to win is to jump into the lava."""
        found = match()
        found.damage('player', 500, by='player')
        assert found.score('player') == -1

    def test_dying_to_the_world_costs_a_frag_too(self):
        """Lava has no id, and a death that scores nothing is a free escape."""
        found = match()
        found.damage('player', 500, by='')
        assert found.score('player') == -1

    def test_the_scoreboard_is_sorted_by_frags(self):
        found = match(bots=2)
        found.damage('bot0', 500, by='bot1')
        rows = found.scoreboard()
        assert rows[0].id == 'bot1'
        assert [row.frags for row in rows] == sorted(
            (row.frags for row in rows), reverse=True)

    def test_the_scoreboard_names_everyone_including_the_dead(self):
        found = match(bots=1)
        found.damage('bot0', 500, by='player')
        assert {row.id for row in found.scoreboard()} == {'player', 'bot0'}

    def test_deaths_are_counted_as_well_as_frags(self):
        found = match()
        found.damage('bot0', 500, by='player')
        rows = {row.id: row for row in found.scoreboard()}
        assert rows['bot0'].deaths == 1


class TestEndingTheMatch:

    def test_reaching_the_frag_limit_ends_it(self):
        found = match(fragLimit=2)
        for _ in range(2):
            found.damage('bot0', 500, by='player')
            found.respawn('bot0', position=(5, 0, 0))
        assert found.over

    def test_falling_short_of_it_does_not(self):
        found = match(fragLimit=5)
        found.damage('bot0', 500, by='player')
        assert not found.over

    def test_the_time_limit_ends_it(self):
        found = match(fragLimit=0, timeLimit=1.0)
        found.advance(61.0)
        assert found.over

    def test_the_clock_is_advanced_rather_than_read(self):
        found = match(fragLimit=0, timeLimit=1.0)
        found.advance(30.0)
        assert not found.over
        found.advance(31.0)
        assert found.over

    def test_the_winner_is_the_one_with_the_most_frags(self):
        found = match(bots=2, fragLimit=1)
        found.damage('bot0', 500, by='bot1')
        assert found.winner() == 'bot1'

    def test_a_match_nobody_has_scored_in_has_no_winner_yet(self):
        assert match().winner() is None

    def test_ending_emits_an_event(self):
        found = match(fragLimit=1)
        found.damage('bot0', 500, by='player')
        assert [event for event in found.events
                if isinstance(event, arena.MatchOver)]

    def test_a_match_ends_once(self):
        found = match(fragLimit=1)
        found.damage('bot0', 500, by='player')
        found.drain()
        found.damage('bot0', 500, by='player')
        assert not [event for event in found.events
                    if isinstance(event, arena.MatchOver)]


class TestRespawning:

    def test_a_respawned_combatant_is_alive_again(self):
        found = match()
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(9, 0, 0))
        assert found.combatant('bot0').alive

    def test_respawning_restores_health(self):
        found = match()
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(9, 0, 0))
        assert found.combatant('bot0').health == arena.STARTING_HEALTH

    def test_respawning_moves_them_to_the_spawn(self):
        found = match()
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(9, 1, 2))
        assert np.allclose(found.combatant('bot0').position, (9, 1, 2))

    def test_respawning_keeps_the_score(self):
        """A death costs a frag; it does not wipe the ones you earned."""
        found = match(bots=2)
        found.damage('bot1', 500, by='bot0')
        found.damage('bot0', 500, by='bot1')
        found.respawn('bot0', position=(0, 0, 0))
        assert found.score('bot0') == 1

    def test_the_dead_are_due_a_respawn_after_the_delay(self):
        found = match()
        found.damage('bot0', 500, by='player')
        assert 'bot0' not in found.due_to_respawn()
        found.advance(arena.RESPAWN_DELAY + 0.1)
        assert 'bot0' in found.due_to_respawn()

    def test_the_living_are_never_due_a_respawn(self):
        found = match()
        found.advance(100.0)
        assert found.due_to_respawn() == []


class TestComingBackAsTheSamePerson:
    """A respawn must not hand out a new record for the same combatant.

    The HUD, the input path and the rules all hold *one*
    :class:`~twig_bb.player.PlayerState` per person, on purpose: two records
    of the same health would eventually disagree. Replacing it on a respawn is
    exactly that disagreement, and it shows up as a HUD frozen at nought health
    from the player's first death onwards.
    """

    def test_the_state_object_survives_a_respawn(self):
        found = match()
        held = found.combatant('bot0').player
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert found.combatant('bot0').player is held

    def test_whoever_was_holding_it_sees_the_new_health(self):
        found = match()
        held = found.combatant('bot0').player
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert held.health == arena.STARTING_HEALTH
        assert held.alive

    def test_they_come_back_with_a_full_loadout(self):
        found = match()
        held = found.combatant('bot0').player
        held.ammo['bullets'] = 0
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert held.ammo['bullets'] > 0

    def test_the_weapons_they_picked_up_do_not_come_back_with_them(self):
        """Dying costs you what you collected, which is what makes the things
        a map places worth walking to — and a player who respawned holding
        every weapon would never leave the room they died in."""
        found = match()
        held = found.combatant('bot0').player
        held.give('rocket')
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert not held.has('rocket')

    def test_the_starting_weapon_does(self):
        found = match()
        held = found.combatant('bot0').player
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert held.weapons and held.selected == held.weapons[0]

    def test_the_armour_they_had_does_not_come_back_with_them(self):
        found = match()
        held = found.combatant('bot0').player
        held.give_armour(100)
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert held.armour == 0

    def test_an_unspent_shove_does_not_survive_the_body_it_was_given_to(self):
        found = match()
        found.shove('bot0', (5.0, 0.0, 0.0))
        found.damage('bot0', 500, by='player')
        found.respawn('bot0', position=(1.0, 0.0, 0.0))
        assert not found.combatant('bot0').push.any()
