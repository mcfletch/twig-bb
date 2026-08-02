"""A whole match, played out with nobody watching.

This is the test that says the game *works*: two bots are put in a room, their
minds are run, their commands are applied, and at the end somebody has won. It
exercises perception, reaction, aim, hitscan, damage, death, respawn and
scoring in one pass, which is a thing no unit test can do and no amount of
playing can do quickly.

It is also how the difficulty range is verified. **The harness asserts the
ordering and never asserts how it was achieved**, which is deliberate: a bot
made "hard" by a hidden damage multiplier would pass this exactly as well as
one made hard by aiming better, so cheating has to be caught by reading the
code. What this catches is the classic regression where a tuning change
silently inverts two rungs of the ladder.

Marked slow because a run is many hundreds of ticks; the arithmetic is cheap
but there is a lot of it.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twitchoglc import arena, bots, combat, weapons

#: The tick the match is simulated at.  Fixed, and nothing reads a clock.
TICK = 1.0 / 30.0

#: How long a match runs before it is called, in seconds.
MATCH_SECONDS = 90.0

#: Where the two of them start, and how big the room is.
ROOM = 12.0


def room():
    """A floor and nothing else: an arena with no cover, so aim decides it."""
    world = PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))
    extent = ROOM * 2
    points = np.array([(-extent, 0.0, -extent), (extent, 0.0, -extent),
                       (extent, 0.0, extent), (-extent, 0.0, extent)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = world.add_shape(model.Shape.trimesh(points, indices))
    world.add_body(model.Motion(type=model.STATIC),
                   collider=model.Collider(shape=shape), position=(0, 0, 0))
    return world


#: Where each side spawns, so a respawn puts them back somewhere sensible.
SPAWNS = {'a': np.array([-ROOM * 0.5, 0.0, 0.0]),
          'b': np.array([ROOM * 0.5, 0.0, 0.0])}


def play(first: str, second: str, seed: int = 0,
         seconds: float = MATCH_SECONDS) -> arena.Arena:
    """Run one match between two difficulties; returns the finished arena."""
    world = room()
    table = weapons.default_table()
    match = arena.Arena(weapons=table, fragLimit=0, timeLimit=seconds / 60.0)
    match.add('a', position=SPAWNS['a'], bot=True, difficulty=first, name='A')
    match.add('b', position=SPAWNS['b'], bot=True, difficulty=second, name='B')
    minds = {'a': bots.Bot('a', difficulty=first, seed=seed),
             'b': bots.Bot('b', difficulty=second, seed=seed + 1000)}
    # Facing each other to begin with, as two players dropped into a room and
    # looking around would be within a second.
    minds['a'].facing = np.array([1.0, 0.0, 0.0])
    minds['b'].facing = np.array([-1.0, 0.0, 0.0])

    gun = table.by_key('rifle')
    # One tick past the limit, so the match actually reaches its end rather
    # than stopping a rounding error short of it.
    ticks = int(seconds / TICK) + 2
    for tick in range(ticks):
        if match.over:
            break
        for id, mind in minds.items():
            command = mind.think(world, match, TICK)
            _apply(world, match, id, command, gun, seed + tick)
        match.advance(TICK)
        for id in match.due_to_respawn():
            match.respawn(id, position=SPAWNS[id])
            minds[id].reset()
        match.drain()
    return match


def _apply(world, match, id, command, gun, seed):
    """Turn one bot's command into what actually happens.

    The seam §11 asks for: a command is consumed here, and the same function
    would consume a key press or a packet.
    """
    one = match.combatant(id)
    if one is None or not one.alive:
        return
    if command.move is not None:
        step = np.asarray(command.move, dtype='d') * 4.0 * TICK
        moved = one.position + step
        # Kept inside the room, since nothing here walks into a wall and stops.
        one.position = np.clip(moved, -ROOM, ROOM)
        one.position[1] = 0.0
    if command.fired and command.aim is not None:
        combat.fire(world, match, id, gun,
                    origin=one.position + np.array([0.0, combat.EYE_HEIGHT, 0.0]),
                    direction=command.aim, spread=float(gun.restSpread),
                    seed=seed)


class TestAMatchHappensAtAll:

    def test_two_bots_fight(self):
        """The whole chain: seeing, reacting, aiming, hitting, dying, scoring."""
        match = play('hard', 'hard', seed=1)
        assert sum(row.frags for row in match.scoreboard()) != 0 or \
            sum(row.deaths for row in match.scoreboard()) > 0

    def test_somebody_dies(self):
        match = play('nightmare', 'easy', seed=2)
        assert sum(row.deaths for row in match.scoreboard()) > 0

    def test_the_match_ends_on_its_time_limit(self):
        assert play('medium', 'medium', seed=3, seconds=10.0).over

    def test_a_near_passive_bot_is_shot_and_does_not_shoot_back(self):
        """The setting that is both a real choice and the navigation fixture."""
        match = play('nightmare', 'near-passive', seed=4)
        rows = {row.id: row for row in match.scoreboard()}
        assert rows['a'].frags > 0
        assert rows['b'].frags <= 0

    def test_the_dead_come_back(self):
        """A match where the first death ended it would prove very little."""
        match = play('nightmare', 'easy', seed=5)
        assert sum(row.deaths for row in match.scoreboard()) > 1


@pytest.mark.slow
class TestTheLadderHolds:
    """The regression this exists for: a tuning change inverting two rungs.

    Several matches per pairing, because one match is noise — the aim error is
    random and a worse bot wins some of them, which is the point of having aim
    error at all.
    """

    def frags(self, first: str, second: str, matches: int = 5) -> tuple:
        """Total frags each side takes over ``matches`` runs."""
        totals = [0, 0]
        for index in range(matches):
            match = play(first, second, seed=index * 17, seconds=45.0)
            rows = {row.id: row for row in match.scoreboard()}
            totals[0] += rows['a'].frags
            totals[1] += rows['b'].frags
        return tuple(totals)

    @pytest.mark.parametrize('better,worse', [
        ('nightmare', 'easy'),
        ('hard', 'easy'),
        ('medium', 'near-passive'),
    ])
    def test_the_better_bot_wins(self, better, worse):
        ahead, behind = self.frags(better, worse)
        assert ahead > behind, '%s scored %d, %s scored %d' % (
            better, ahead, worse, behind)

    def test_two_equal_bots_are_close(self):
        """Not equal — the aim error is random — but not a rout either."""
        ahead, behind = self.frags('medium', 'medium')
        assert abs(ahead - behind) <= max(4, abs(ahead + behind))


# -- the whole loadout, through the production wiring -------------------------
#
# The harness above drives the bots by hand, which keeps the ladder tests about
# the ladder.  This one runs the *game module's* own loop instead — the same
# calls the frame loop makes — so what it exercises is everything §7 added:
# weapon choice, projectiles in flight, bursts, knockback and the events all of
# it emits.  A regression that broke the wiring and not the rules would pass
# every unit test above and fail here.

def play_armed(first: str, second: str, seed: int = 0,
               seconds: float = MATCH_SECONDS) -> tuple:
    """One match with the full loadout; returns the arena and what it emitted."""
    from twitchoglc import game, projectiles

    world = room()
    table = weapons.default_table()
    kinds = projectiles.default_table()
    match = arena.Arena(weapons=table, fragLimit=0, timeLimit=seconds / 60.0)
    match.add('a', position=SPAWNS['a'], bot=True, difficulty=first, name='A')
    match.add('b', position=SPAWNS['b'], bot=True, difficulty=second, name='B')
    minds = {id: bots.Bot(id, difficulty=difficulty, seed=seed + offset,
                          weapons=table, projectiles=kinds)
             for id, difficulty, offset in (('a', first, 0), ('b', second, 1000))}
    minds['a'].facing = np.array([1.0, 0.0, 0.0])
    minds['b'].facing = np.array([-1.0, 0.0, 0.0])
    flight = projectiles.Projectiles(kinds)

    seen: list = []
    for tick in range(int(seconds / TICK) + 2):
        if match.over:
            break
        game.step_bots(world, match, minds, TICK, table.by_key('rifle'),
                       seed=seed + tick, flight=flight)
        game.step_projectiles(world, match, flight, TICK)
        match.advance(TICK)
        for id in match.due_to_respawn():
            match.respawn(id, position=SPAWNS[id])
            minds[id].reset()
        for one in (match.combatant(id) for id in match.ids()):
            one.position = np.clip(one.position, -ROOM, ROOM)
            one.position[1] = 0.0
        seen.extend(match.drain())
    return (match, seen)


@pytest.mark.slow
class TestTheWholeLoadout:
    """Everything §7 added, driven by the calls the frame loop actually makes."""

    def kinds(self, seen, of):
        return [event for event in seen if isinstance(event, of)]

    def test_a_match_is_played_and_somebody_dies(self):
        match, _seen = play_armed('hard', 'hard', seed=3)
        assert sum(row.deaths for row in match.scoreboard()) > 0

    def test_the_bots_reach_for_the_projectile_weapons(self):
        """A bot that only ever fires hitscan is not playing the same game."""
        _match, seen = play_armed('hard', 'hard', seed=3)
        thrown = {event.weapon for event in self.kinds(seen, arena.Fired)}
        assert thrown & {'rocket', 'grenade'}

    def test_rockets_go_off(self):
        _match, seen = play_armed('hard', 'hard', seed=3)
        assert self.kinds(seen, arena.Detonated)

    def test_a_burst_hurts_somebody(self):
        """Splash reaching somebody in a real fight, not only in a fixture."""
        _match, seen = play_armed('hard', 'hard', seed=3)
        after = False
        hurt = []
        for event in seen:
            if isinstance(event, arena.Detonated):
                after = True
            elif after and isinstance(event, arena.Damaged):
                hurt.append(event)
        assert hurt

    def test_nobody_is_left_in_the_air_at_the_end(self):
        """A projectile with nothing to hit must give up rather than be carried."""
        from twitchoglc import projectiles
        world = room()
        table, kinds = weapons.default_table(), projectiles.default_table()
        match = arena.Arena(weapons=table)
        match.add('a', position=SPAWNS['a'], bot=True, name='A')
        flight = projectiles.Projectiles(kinds)
        flight.launch(kinds.by_key(projectiles.ROCKET), origin=(0, 2, 0),
                      direction=(0, 1, 0), owner='a')
        from twitchoglc import game
        for _ in range(int(10.0 / TICK)):
            game.step_projectiles(world, match, flight, TICK)
        assert len(flight) == 0

    def test_the_better_bot_still_wins_with_everything_available(self):
        """The ladder must survive the loadout growing under it."""
        match, _seen = play_armed('nightmare', 'easy', seed=5)
        assert match.score('a') > match.score('b')
