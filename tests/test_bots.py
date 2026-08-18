"""Opponents that decide for themselves.

The difficulty is the **axis the bot is built along**, not a multiplier bolted
on at the end, so every test here is really about the range: what near-passive
does that nightmare does not, and — the important half — what *neither* of them
is allowed to do.

**The senses never scale.** No seeing through walls, no knowing where somebody
is without having perceived them, no hidden damage multipliers. Every
difficulty uses the same perception; only the timing, the aim and the decisions
change. A bot that cheats is not difficult, it is annoying, and once one hidden
advantage is permitted the scale stops meaning anything.
"""

from __future__ import annotations

import numpy as np
import pytest

from omi_physics import model
from omi_physics.world import PhysicsWorld

from twig_bb import arena, bots, combat, projectiles, weapons
from twig_bb.player import PlayerState


def world():
    return PhysicsWorld(gravity=model.Gravity(gravity=9.81, direction=(0, -1, 0)))


def wall(w, x):
    e = 20.0
    points = np.array([(x, -e, -e), (x, e, -e), (x, e, e), (x, -e, e)], dtype='d')
    indices = np.array([(0, 1, 2), (0, 2, 3)], dtype='i')
    shape = w.add_shape(model.Shape.trimesh(points, indices))
    return w.add_body(model.Motion(type=model.STATIC),
                      collider=model.Collider(shape=shape), position=(0, 0, 0))


def match(difficulty='medium', distance=10.0, armed=True):
    made = arena.Arena(weapons=weapons.default_table())
    made.add('player', position=(0.0, 0.0, 0.0), name='You')
    made.add('bot0', position=(distance, 0.0, 0.0), bot=True,
             difficulty=difficulty, name='Bot')
    if armed:
        # A bot that has picked everything up: which weapon it *prefers* at a
        # range is only a question once it holds more than one, so the choice
        # and leading tests arm it.  A bot chooses from what its body carries
        # now (`Bot._chosen`), so a pistol-only spawn would answer every one of
        # them "pistol".  ``armed=False`` leaves it on the spawn loadout for
        # the tests that are about running dry.
        made.combatant('bot0').player = PlayerState.carrying(made.weapons)
    return made


def like(name, **changed):
    """A copy of a preset with some numbers changed.

    A *copy*, because `bots.PRESETS` is one shared set of nodes: a test that
    retunes a preset in place retunes it for every test that runs after it,
    and the failure lands somewhere else entirely.
    """
    was = bots.preset(name)
    fields = {key: getattr(was, key) for key in
              ('name', 'reactionTime', 'aimError', 'aimSpeed',
               'decisionInterval', 'fights', 'aggression', 'leadsTargets',
               'blastSense')}
    fields.update(changed)
    return bots.Difficulty(**fields)


def think(brain, found, w=None, dt=0.1, times=1, facing=(-1.0, 0.0, 0.0)):
    """Run a bot's mind for a while, as the frame loop would.

    Pointed at the player before it starts, because a fresh mind faces a
    *random* way on purpose (see :class:`TestNotBeingPredictable`) and a test
    about reacting, aiming or choosing a weapon is not a test about which way
    it happened to arrive looking.  ``facing=None`` leaves it where it is.
    """
    w = w if w is not None else world()
    if facing is not None:
        brain.facing = np.asarray(facing, dtype='d')
    last = None
    for _ in range(times):
        last = brain.think(w, found, dt)
    return last


class TestTheDifficultyPresets:

    def test_every_declared_difficulty_has_a_preset(self):
        """A menu offers these names; one with no numbers behind it is a crash."""
        from twig_bb import match as matchmod
        for name in matchmod.DIFFICULTIES:
            assert bots.preset(name) is not None

    def test_an_unknown_difficulty_falls_back_rather_than_failing(self):
        """A saved setting from a version that declared more must still play."""
        assert bots.preset('impossible') is not None

    def test_reaction_time_falls_as_the_difficulty_rises(self):
        times = [bots.preset(name).reactionTime
                 for name in ('near-passive', 'easy', 'medium', 'hard',
                              'nightmare')]
        assert times == sorted(times, reverse=True)

    def test_aim_error_falls_as_the_difficulty_rises(self):
        errors = [bots.preset(name).aimError
                  for name in ('near-passive', 'easy', 'medium', 'hard',
                               'nightmare')]
        assert errors == sorted(errors, reverse=True)

    def test_near_passive_does_not_shoot(self):
        """A genuine setting, and the fixture everything else is checked against.

        A bot that walks its path and does not fire is how navigation is
        verified without combat in the way.
        """
        assert not bots.preset('near-passive').fights

    def test_every_other_difficulty_does(self):
        for name in ('easy', 'medium', 'hard', 'nightmare'):
            assert bots.preset(name).fights

    def test_a_preset_is_declared_data_rather_than_a_branch(self):
        """So a menu can present it and a variant can retune it."""
        assert hasattr(bots.preset('medium'), 'UI_HINTS')


class TestWhatABotCanSee:
    """The half that must be the same at every difficulty."""

    def test_it_sees_somebody_in_the_open(self):
        brain = bots.Bot('bot0')
        brain.facing = np.array([-1.0, 0.0, 0.0])   # toward the player
        assert 'player' in brain.perceive(world(), match())

    def test_a_wall_hides_them(self):
        w = world()
        wall(w, x=5.0)
        assert bots.Bot('bot0').perceive(w, match()) == []

    def test_the_hardest_bot_cannot_see_through_a_wall_either(self):
        """The rule that keeps the scale meaning something."""
        w = world()
        wall(w, x=5.0)
        assert bots.Bot('bot0').perceive(w, match('nightmare')) == []

    def test_it_does_not_see_the_dead(self):
        found = match()
        found.damage('player', 500, by='bot0')
        assert bots.Bot('bot0').perceive(world(), found) == []

    def test_it_does_not_see_itself(self):
        assert 'bot0' not in bots.Bot('bot0').perceive(world(), match())

    def test_something_behind_it_is_out_of_view(self):
        """A field of view, and one that every difficulty shares."""
        found = match()
        brain = bots.Bot('bot0')
        brain.facing = np.array([1.0, 0.0, 0.0])    # away from the player
        assert brain.perceive(world(), found) == []

    def test_turning_round_brings_them_into_view(self):
        found = match()
        brain = bots.Bot('bot0')
        brain.facing = np.array([-1.0, 0.0, 0.0])
        assert 'player' in brain.perceive(world(), found)


class TestLookingAroundCostsSomething:
    """Every bot asking every tick is what made eight of them a slideshow.

    A tick was 0.26 ms at one bot and 17.6 ms at eight -- past a whole frame,
    for a menu that lets a player choose fifteen. The casts are cheap; the
    *count* is the problem, and the answer is to look less often rather than
    to see less: perception is a sense, and a sense that scaled with
    difficulty would stop the ladder meaning anything.
    """

    def looks(self, brain, found, w, dt, times):
        """How many real looks a run of ticks costs."""
        counted = []
        real = brain.perceive
        brain.perceive = lambda *a: counted.append(1) or real(*a)
        for _ in range(times):
            brain.look(w, found, dt)
        return len(counted)

    def test_it_does_not_look_again_every_tick(self):
        found, w = match(), world()
        assert self.looks(bots.Bot('bot0'), found, w, 1.0 / 60.0, 12) < 12

    def test_it_looks_about_once_an_interval(self):
        """Within one, because the first look waits on this bot's own phase."""
        found, w = match(), world()
        seconds = bots.PERCEPTION_INTERVAL * 10.0
        counted = self.looks(bots.Bot('bot0'), found, w, 1.0 / 60.0,
                             int(seconds * 60.0))
        assert counted == pytest.approx(10, abs=1)

    def test_what_it_saw_last_time_is_what_it_answers_between_looks(self):
        found, w = match(), world()
        brain = bots.Bot('bot0')
        brain.facing = np.array([-1.0, 0.0, 0.0])   # toward the player
        assert 'player' in brain.look(w, found, 0.0)
        assert 'player' in brain.look(w, found, 0.0)

    def test_somebody_who_has_died_since_is_dropped_without_looking(self):
        """A remembered sighting must not become a bot shooting a corpse."""
        found, w = match(), world()
        brain = bots.Bot('bot0')
        brain.look(w, found, 0.0)
        found.damage('player', 500, by='bot0')
        assert brain.look(w, found, 0.0) == []

    def test_two_bots_made_alike_do_not_look_on_the_same_tick(self):
        """Otherwise the saving is a stutter every few frames instead of a cost.

        The phase is the *seed*'s, so it is reproducible, which is what a
        replay needs.
        """
        found, w = match(), world()
        one, two = bots.Bot('bot0', seed=1), bots.Bot('bot0', seed=2)
        looked = []
        for brain in (one, two):
            counted = []
            real = brain.perceive
            brain.perceive = (lambda *a, _c=counted, _r=real:
                              _c.append(1) or _r(*a))
            ticks = []
            for tick in range(12):
                before = len(counted)
                brain.look(w, found, 1.0 / 60.0)
                if len(counted) > before:
                    ticks.append(tick)
            looked.append(ticks)
        assert looked[0] != looked[1]

    def test_the_interval_is_shorter_than_the_fastest_reaction(self):
        """It has to be invisible: this is a sense, and slowing a sense down
        far enough to notice is a difficulty change by the back door."""
        assert bots.PERCEPTION_INTERVAL < min(
            float(one.reactionTime) for one in bots.PRESETS.values())

    def test_forgetting_makes_it_look_again_at_once(self):
        """A respawn arrives somewhere else and must not act on the old view."""
        found, w = match(), world()
        brain = bots.Bot('bot0')
        brain.look(w, found, 0.0)
        brain.reset()
        assert self.looks(brain, found, w, 0.0, 1) == 1


class TestReacting:

    def test_it_does_not_fire_the_instant_it_sees_somebody(self):
        """Reaction time is what makes a bot beatable, so it has to bite."""
        found = match('medium')
        brain = bots.Bot('bot0', difficulty='medium')
        assert not think(brain, found).fired

    def test_it_fires_once_its_reaction_time_has_passed(self):
        found = match('medium')
        brain = bots.Bot('bot0', difficulty='medium')
        delay = bots.preset('medium').reactionTime
        result = think(brain, found, dt=delay + 0.5, times=3)
        assert result.fired

    def test_a_harder_bot_reacts_sooner(self):
        found = match()
        quick = bots.Bot('bot0', difficulty='nightmare')
        slow = bots.Bot('bot0', difficulty='easy')
        step = bots.preset('nightmare').reactionTime + 0.01
        assert think(quick, found, dt=step, times=2).fired
        assert not think(slow, found, dt=step, times=2).fired

    def test_losing_sight_resets_the_reaction(self):
        """Stepping out of cover should not be answered by an instant shot."""
        w = world()
        found = match()
        brain = bots.Bot('bot0', difficulty='medium')
        think(brain, found, w, dt=5.0)
        blocked = world()
        wall(blocked, x=5.0)
        think(brain, found, blocked, dt=1.0)
        assert not think(brain, found, w, dt=0.01).fired

    def test_a_near_passive_bot_never_fires(self):
        found = match('near-passive')
        brain = bots.Bot('bot0', difficulty='near-passive')
        assert not think(brain, found, dt=10.0, times=5).fired


class TestABotObeysTheWeaponsFireRate:
    """A bot may not shoot faster than the thing in its hands will fire.

    Its ``decisionInterval`` is how often it *thinks*, and the hardest one
    thinks twenty times a second; the weapon's ``fireInterval`` is how often
    it can shoot, and the rifle's is a second and a half.  With nothing
    holding the two together a bot empties a one-shot-kill weapon into
    somebody in the frame they walk into view, which is not a difficult
    opponent, it is a hitscan wall.
    """

    def brain(self, difficulty='nightmare'):
        return bots.Bot('bot0', difficulty=difficulty, seed=1,
                        weapons=weapons.default_table(),
                        projectiles=projectiles.default_table())

    def shots(self, brain, found, seconds=3.0, dt=0.05):
        """How many times it pulls the trigger over ``seconds``."""
        w, taken = world(), 0
        brain.facing = np.array([-1.0, 0.0, 0.0])
        for _ in range(int(seconds / dt)):
            if brain.think(w, found, dt).fired:
                taken += 1
        return taken

    def test_it_fires_no_faster_than_the_weapon_it_chose(self):
        found = match('nightmare', distance=10.0)
        brain = self.brain()
        seconds = 3.0
        taken = self.shots(brain, found, seconds=seconds)
        chosen = weapons.default_table().by_key(
            think(self.brain(), found, dt=5.0, times=2).weapon)
        assert taken <= seconds / float(chosen.fireInterval) + 1

    def test_it_still_fires_at_all(self):
        """The gate must not become a bot that never shoots."""
        assert self.shots(self.brain(), match('nightmare', distance=10.0)) > 0

    def test_a_bot_with_no_table_is_not_stopped_by_one(self):
        """Nothing said what it is holding, so nothing says how fast it fires."""
        brain = bots.Bot('bot0', difficulty='nightmare', seed=1)
        assert self.shots(brain, match('nightmare')) > 0


class TestAiming:

    def test_it_aims_at_what_it_can_see(self):
        found = match()
        brain = bots.Bot('bot0', difficulty='medium')
        result = think(brain, found, dt=5.0, times=2)
        assert result.aim is not None
        assert float(result.aim[0]) < 0.0        # the player is at -x from it

    def test_it_aims_at_nothing_when_it_sees_nothing(self):
        w = world()
        wall(w, x=5.0)
        assert think(bots.Bot('bot0'), match(), w, dt=5.0).aim is None

    def test_a_worse_bot_aims_less_accurately(self):
        """Aim error is what makes a shot survivable, and it has to be visible."""
        found = match()
        errors = []
        for name in ('easy', 'nightmare'):
            brain = bots.Bot('bot0', difficulty=name, seed=3)
            perfect = np.array([-1.0, 0.0, 0.0])
            aims = []
            for _ in range(20):
                brain.reset()
                aim = think(brain, found, dt=5.0, times=2).aim
                aims.append(float(np.linalg.norm(aim - perfect)))
            errors.append(sum(aims) / len(aims))
        assert errors[0] > errors[1]

    def test_the_aim_is_a_unit_heading(self):
        brain = bots.Bot('bot0', difficulty='medium', seed=1)
        aim = think(brain, match(), dt=5.0, times=2).aim
        assert float(np.linalg.norm(aim)) == pytest.approx(1.0, abs=1e-6)

    def test_the_aim_is_reproducible_from_its_seed(self):
        """§11 again: the same inputs give the same result on one machine."""
        aims = []
        for _ in range(2):
            brain = bots.Bot('bot0', difficulty='medium', seed=11)
            aims.append(think(brain, match(), dt=5.0, times=2).aim.tolist())
        assert aims[0] == aims[1]


class TestNotBeingPredictable:
    """Two bots that arrive together must not do the same thing.

    Reported as bots repeating the same opening: they spawned in the same
    places (which is `game.spawn_for`'s business) and then, being built from
    the same state with the same rules, played the first few seconds out
    identically.  What varies is *where it happens to be looking* and *how
    long before it commits* — neither of which is a difficulty, and both of
    which are what a person arriving in a room does differently every time.
    """

    def brain(self, seed):
        return bots.Bot('bot%d' % seed, seed=seed)

    def test_two_fresh_minds_do_not_face_the_same_way(self):
        facings = {tuple(self.brain(seed).facing) for seed in range(8)}
        assert len(facings) > 1

    def test_two_fresh_minds_do_not_commit_on_the_same_tick(self):
        waits = {round(self.brain(seed).since_decision, 6) for seed in range(8)}
        assert len(waits) > 1

    def test_none_of_them_starts_ready_to_decide(self):
        """An opening hesitation, so arriving is not the same as shooting."""
        for seed in range(8):
            assert self.brain(seed).since_decision <= 0.0

    def test_coming_back_is_a_fresh_opening_rather_than_the_same_one(self):
        brain = self.brain(3)
        was = tuple(brain.facing)
        for _ in range(3):
            brain.reset()
            if tuple(brain.facing) != was:
                return
        raise AssertionError('every respawn faced the same way')

    def test_a_replay_still_replays(self):
        """Varied is not the same as unrepeatable: same seed, same opening."""
        assert tuple(self.brain(4).facing) == tuple(self.brain(4).facing)

    def test_it_walks_one_way_for_a_while_rather_than_jittering(self):
        """A heading rerolled every tick is a bot vibrating on the spot.

        Its own docstring said it holds a heading until something interesting
        happens, and it drew a fresh angle sixty times a second.
        """
        brain = self.brain(2)
        headings = {tuple(np.round(brain._wander(1.0 / 60.0), 6))
                    for _ in range(20)}
        assert len(headings) == 1

    def test_it_does_change_its_mind_eventually(self):
        brain = self.brain(2)
        first = tuple(np.round(brain._wander(0.0), 6))
        for _ in range(40):
            brain._wander(bots.WANDER_INTERVAL * 0.25)
        assert tuple(np.round(brain._wander(0.0), 6)) != first

    def test_two_of_them_do_not_turn_on_the_same_tick(self):
        """Otherwise a room of bots pivots in unison, which reads as a script."""
        def turns(seed):
            brain = self.brain(seed)
            was, at = tuple(np.round(brain._wander(0.0), 6)), []
            for tick in range(400):
                now = tuple(np.round(brain._wander(1.0 / 60.0), 6))
                if now != was:
                    at.append(tick)
                was = now
            return at
        assert turns(1) != turns(2)


class TestMoving:

    def test_it_moves_toward_what_it_is_chasing(self):
        found = match()
        brain = bots.Bot('bot0', difficulty='medium')
        result = think(brain, found, dt=5.0, times=2)
        assert result.move is not None
        assert float(result.move[0]) < 0.0

    def test_it_wanders_when_it_sees_nobody(self):
        """A bot standing still in an empty room reads as a broken bot."""
        w = world()
        wall(w, x=5.0)
        result = think(bots.Bot('bot0', seed=2), match(), w, dt=1.0, times=3)
        assert result.move is not None
        assert float(np.linalg.norm(result.move)) > 0.0

    def test_it_keeps_its_distance_rather_than_walking_into_you(self):
        found = match(distance=1.0)
        brain = bots.Bot('bot0', difficulty='medium')
        result = think(brain, found, dt=5.0, times=2)
        assert float(result.move[0]) >= 0.0      # backing off, or holding

    def test_a_dead_bot_does_nothing(self):
        found = match()
        found.damage('bot0', 500, by='player')
        result = think(bots.Bot('bot0'), found, dt=5.0, times=2)
        assert not result.fired and result.aim is None


class TestTheCommandItProduces:
    """§11: a bot emits the same per-tick record a key press does."""

    def test_the_decision_is_a_record_rather_than_a_write(self):
        result = think(bots.Bot('bot0', difficulty='medium'), match(),
                       dt=5.0, times=2)
        assert isinstance(result, bots.Command)

    def test_a_bot_writes_nothing_to_the_arena(self):
        """It decides; something else applies.  That is what makes it testable."""
        found = match()
        before = found.combatant('player').health
        think(bots.Bot('bot0', difficulty='nightmare'), found, dt=10.0, times=5)
        assert found.combatant('player').health == before

    def test_the_command_names_who_it_is_for(self):
        assert think(bots.Bot('bot0'), match(), dt=1.0).id == 'bot0'


class TestChoosingAWeapon:
    """A bot that only ever fires hitscan is not playing the same game.

    Which weapon, and whether it is safe to use, are **difficulty**: the
    near-passive bot may cheerfully blow itself up and the nightmare bot must
    not.
    """

    def brain(self, difficulty='medium'):
        return bots.Bot('bot0', difficulty=difficulty, seed=1,
                        weapons=weapons.default_table(),
                        projectiles=projectiles.default_table())

    def test_it_names_the_weapon_it_wants(self):
        found = match(distance=10.0)
        assert think(self.brain(), found, dt=5.0, times=2).weapon

    def test_a_bot_with_no_table_names_nothing_and_still_fights(self):
        """The caller's own weapon is what a bot without a loadout uses."""
        result = think(bots.Bot('bot0', difficulty='nightmare', seed=1),
                       match(), dt=5.0, times=2)
        assert result.weapon == ''
        assert result.aim is not None

    def test_it_reaches_for_a_splash_weapon_at_a_distance(self):
        found = match(distance=18.0)
        weapon = think(self.brain('hard'), found, dt=5.0, times=2).weapon
        assert str(weapons.default_table().by_key(weapon).projectile)

    def test_it_does_not_fire_a_rocket_into_its_own_face(self):
        """A burst radius away is a burst that kills whoever set it off."""
        found = match(distance=1.5)
        weapon = think(self.brain('nightmare'), found, dt=5.0, times=2).weapon
        assert not str(weapons.default_table().by_key(weapon).projectile)

    def test_a_careless_bot_will_do_it_anyway(self):
        """That is what the low rungs of the ladder are: worse decisions."""
        careless = bots.Bot('bot0', difficulty='easy', seed=1,
                            weapons=weapons.default_table(),
                            projectiles=projectiles.default_table())
        careless.skill = like('easy', blastSense=0.0)
        found = match(difficulty='easy', distance=1.5)
        weapon = think(careless, found, dt=5.0, times=2).weapon
        assert str(weapons.default_table().by_key(weapon).projectile)

    def test_it_does_not_choose_a_weapon_that_cannot_reach(self):
        """A shotgun across a level is a bot standing in the open for nothing."""
        table = weapons.WeaponTable(weapons=[
            weapons.default_table().by_key(key) for key in
            ('pistol', 'shotgun')])
        brain = bots.Bot('bot0', difficulty='hard', seed=1, weapons=table)
        assert think(brain, match(distance=40.0), dt=5.0, times=2).weapon \
            == 'pistol'

    def test_and_does_choose_it_where_it_is_the_better_one(self):
        table = weapons.WeaponTable(weapons=[
            weapons.default_table().by_key(key) for key in
            ('pistol', 'shotgun')])
        brain = bots.Bot('bot0', difficulty='hard', seed=1, weapons=table)
        assert think(brain, match(distance=3.0), dt=5.0, times=2).weapon \
            == 'shotgun'

    def test_the_safe_range_is_the_projectiles_own_radius(self):
        """Not a constant: a bigger burst has to be kept further away."""
        rockets = projectiles.default_table()
        near = bots.safe_range(rockets.by_key(projectiles.ROCKET), 1.0)
        rockets.by_key(projectiles.ROCKET).splashRadius *= 2.0
        far = bots.safe_range(rockets.by_key(projectiles.ROCKET), 1.0)
        assert far > near

    def test_no_sense_at_all_makes_everywhere_safe(self):
        rockets = projectiles.default_table()
        assert bots.safe_range(rockets.by_key(projectiles.ROCKET), 0.0) == 0.0

    def test_it_does_not_lob_a_grenade_at_something_it_cannot_reach(self):
        """The grenade is worth *more* than the rocket, which is the trap.

        A grenade's burst is the bigger one, so a bot weighing only what a
        weapon does picks it at every range there is — and then throws a
        thing that falls fourteen metres a second squared at somebody forty
        metres away, where it lands in the floor less than half way.
        """
        found = match(distance=40.0)
        chosen = think(self.brain('hard'), found, dt=5.0, times=2).weapon
        assert chosen != 'grenade'

    def test_it_still_reaches_for_the_rocket_out_there(self):
        """The bound is per projectile, not a blanket "no splash at range"."""
        found = match(distance=40.0)
        chosen = think(self.brain('hard'), found, dt=5.0, times=2).weapon
        assert chosen == 'rocket'


class TestFiringFromTheLoadoutItCarries:
    """A bot may only fire what it has picked up, the same as a player.

    The whole of "the bots always open on a rocket and never run dry" was that
    their shots came out of nowhere: they ignored the loadout their body
    carries.  A bot chooses from, and fires out of, exactly that loadout now,
    which is what makes a rocket something it has to *find*.
    """

    def brain(self, difficulty='hard'):
        return bots.Bot('bot0', difficulty=difficulty, seed=1,
                        weapons=weapons.default_table(),
                        projectiles=projectiles.default_table())

    def test_a_spawned_bot_opens_with_the_weapon_it_spawned_holding(self):
        """Its body carries the starting loadout -- a pistol -- so at a range
        that would beg for a rocket it fires the one thing it actually has."""
        found = match(difficulty='hard', distance=18.0, armed=False)
        chosen = think(self.brain(), found, dt=5.0, times=2).weapon
        assert chosen == 'pistol'

    def test_finding_a_launcher_is_what_lets_it_choose_one(self):
        found = match(difficulty='hard', distance=18.0, armed=False)
        # Walk it over a rocket launcher, so to speak: the pool the level fills.
        found.combatant('bot0').player.give('rocket')
        found.combatant('bot0').player.give_ammo('rockets', 5)
        chosen = think(self.brain(), found, dt=5.0, times=2).weapon
        assert chosen == 'rocket'

    def test_it_runs_dry_and_falls_back(self):
        """Down to one rocket, it fires that and then reaches for the pistol
        rather than clicking an empty launcher for the rest of the fight."""
        found = match(difficulty='hard', distance=18.0, armed=False)
        loadout = found.combatant('bot0').player
        loadout.give('rocket')
        loadout.ammo['rockets'] = 1
        assert think(self.brain(), found, dt=5.0, times=2).weapon == 'rocket'
        loadout.ammo['rockets'] = 0
        assert think(self.brain(), found, dt=5.0, times=2).weapon == 'pistol'


class TestHowFarAThrownWeaponReaches:
    """:func:`bots.reach` measured against the flight itself.

    A bot aims *straight at* what it is fighting — nothing lofts a shot — so a
    projectile that falls is below that line by the time it arrives, and past
    some range it is landing in the floor short of them.  Where that range is
    has to be settled by flying one: a rule checked against another rule can
    be wrong in both places at once, and this one exists precisely because the
    grenade's own numbers are what decide it.
    """

    def drop(self, kind, gap):
        """How far below its line a projectile is ``gap`` metres out.

        Flown in the real batch, in an empty world with nothing to meet, so
        what is measured is the integration the game actually uses rather than
        a closed form that agrees with it today.
        """
        flight = projectiles.Projectiles(table=projectiles.default_table())
        empty = arena.Arena(weapons=weapons.default_table())
        w = world()
        assert flight.launch(kind, origin=(0.0, 0.0, 0.0), direction=(1, 0, 0))
        while flight.live and float(flight.position[0][0]) < gap:
            flight.step(w, empty, 1.0 / 480.0)
        if not flight.live:                     # its fuse or lifetime ended it
            return float('inf')
        return -float(flight.position[0][1])

    def test_a_grenade_at_its_reach_has_fallen_by_about_a_body(self):
        kind = projectiles.default_table().by_key(projectiles.GRENADE)
        assert self.drop(kind, bots.reach(kind)) == pytest.approx(
            bots.AIM_DROP, abs=0.15)

    def test_a_grenade_thrown_twice_that_far_is_in_the_floor(self):
        kind = projectiles.default_table().by_key(projectiles.GRENADE)
        assert self.drop(kind, bots.reach(kind) * 2.0) > combat.BODY_HEIGHT * 3

    def test_a_rocket_does_not_fall_and_so_reaches_as_far_as_it_lives(self):
        kind = projectiles.default_table().by_key(projectiles.ROCKET)
        assert self.drop(kind, bots.reach(kind) * 0.99) == pytest.approx(0.0)
        # As far as it gets in its lifetime -- and because it is a motor, that
        # is the distance it *accelerates* through, not its launch speed times
        # its life.
        assert bots.reach(kind) == pytest.approx(
            kind.distance_in(float(kind.lifetime)))

    def test_a_fuse_shortens_the_reach_of_something_that_does_not_fall(self):
        """The other of the two limits, on its own."""
        kind = projectiles.default_table().by_key(projectiles.ROCKET)
        kind.fuse = 1.0
        assert bots.reach(kind) == pytest.approx(kind.distance_in(1.0))


class TestHowFastTheAimCloses:
    """`aimSpeed` is a declared rung of the ladder that nothing read.

    A bot whose aim arrives the instant it decides is a bot you cannot dodge:
    strafing across one is answered before the step lands, and the only thing
    that ever saves you is how badly it happens to be aiming.  How fast the
    aim *closes* is what makes a slow bot beatable by moving.
    """

    def brain(self, speed, seed=1):
        """A bot whose *only* variable is how fast its aim closes.

        Its own `Difficulty` rather than a mutated preset: the presets are one
        shared set of nodes, and a test that retunes one retunes it for every
        test that runs afterwards.
        """
        made = bots.Bot('bot0', difficulty='medium', seed=seed)
        made.skill = bots.Difficulty(name='test', aimSpeed=speed,
                                     aimError=0.0, reactionTime=0.0,
                                     decisionInterval=0.0)
        return made

    #: Well off the target and still inside the field of view, because an aim
    #: cannot close on somebody the bot cannot see.
    START = (0.0, 0.0, 1.0)

    def swung(self, speed, times=1):
        """How far round the aim gets, from across the target to onto it."""
        found = match(distance=10.0)
        brain = self.brain(speed)
        return think(brain, found, dt=1.0, times=times,
                     facing=self.START).aim

    def test_a_slow_aim_does_not_arrive_in_one_decision(self):
        assert float(self.swung(0.2)[0]) > -0.9

    def test_it_gets_there_in_the_end(self):
        assert float(self.swung(0.2, times=25)[0]) < -0.99

    def test_a_faster_aim_gets_further_in_the_same_time(self):
        assert float(self.swung(0.8)[0]) < float(self.swung(0.2)[0])

    def test_the_fastest_aim_arrives_at_once(self):
        """Which is what the top of the ladder should feel like."""
        assert float(self.swung(1.0)[0]) == pytest.approx(-1.0, abs=1e-6)

    def test_an_aim_speed_of_nothing_never_turns(self):
        """A real setting rather than a division by zero."""
        assert self.swung(0.0) == pytest.approx(self.START, abs=1e-6)

    def test_every_preset_declares_one_and_they_rise_with_the_ladder(self):
        speeds = [float(bots.preset(name).aimSpeed)
                  for name in ('near-passive', 'easy', 'medium', 'hard',
                               'nightmare')]
        assert speeds == sorted(speeds)

    def test_the_aim_it_reports_is_a_unit_heading_all_the_way_round(self):
        found = match(distance=10.0)
        brain = self.brain(0.35)
        brain.facing = np.asarray(self.START, dtype='d')
        for _ in range(12):
            aim = brain.think(world(), found, 0.5).aim
            assert float(np.linalg.norm(aim)) == pytest.approx(1.0, abs=1e-9)


class TestLeadingATarget:
    """A slow projectile fired where somebody *is* arrives where they were."""

    def brain(self, difficulty='nightmare'):
        return bots.Bot('bot0', difficulty=difficulty, seed=1,
                        weapons=weapons.default_table(),
                        projectiles=projectiles.default_table())

    def moving(self, found, brain, steps=6, dt=0.1, speed=6.0):
        """Walk the player sideways past a bot, thinking each tick.

        Pointed at them first: a fresh mind faces a random way, and where a
        bot happened to arrive looking is not what leading is about.
        """
        last = None
        w = world()
        brain.facing = np.array([-1.0, 0.0, 0.0])
        for _ in range(steps):
            found.combatant('player').position = (
                found.combatant('player').position
                + np.array([0.0, 0.0, speed * dt]))
            last = brain.think(w, found, dt)
        return last

    def test_it_aims_ahead_of_somebody_crossing(self):
        brain = self.brain()
        brain.skill = like('nightmare', aimError=0.0, aimSpeed=1.0)
        found = match(difficulty='nightmare', distance=20.0)
        result = self.moving(found, brain)
        # The player is walking towards +Z; a bot at +X aiming back at them
        # must aim to the +Z side of straight at them.
        straight = np.asarray(found.combatant('player').position) \
            - np.asarray(found.combatant('bot0').position)
        assert float(result.aim[2]) > float(
            straight[2] / np.linalg.norm(straight))

    def test_it_does_not_lead_a_hitscan_shot(self):
        """A trace arrives instantly; leading it would only make it miss."""
        brain = self.brain()
        # A *copy* of the preset, and with the aim arriving at once: what is
        # under test is where it points, not how long it takes to get there.
        brain.skill = like('nightmare', aimError=0.0, aimSpeed=1.0)
        found = match(difficulty='nightmare', distance=3.0)
        result = self.moving(found, brain)
        straight = np.asarray(found.combatant('player').position) \
            - np.asarray(found.combatant('bot0').position)
        straight = straight / np.linalg.norm(straight)
        assert float(result.aim[2]) == pytest.approx(float(straight[2]),
                                                     abs=1e-6)

    def test_a_poor_bot_leads_worse_than_a_good_one(self):
        """Leading is a skill, so it belongs on the ladder like the rest."""
        assert float(bots.preset('nightmare').leadsTargets) \
            > float(bots.preset('easy').leadsTargets)

    def test_a_still_target_is_not_led(self):
        brain = self.brain()
        brain.skill = bots.preset('nightmare')
        brain.skill.aimError = 0.0
        found = match(difficulty='nightmare', distance=20.0)
        result = self.moving(found, brain, speed=0.0)
        straight = np.asarray(found.combatant('player').position) \
            - np.asarray(found.combatant('bot0').position)
        straight = straight / np.linalg.norm(straight)
        assert np.allclose(result.aim, straight, atol=1e-6)
