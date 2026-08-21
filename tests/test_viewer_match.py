"""The match as a player meets it: dying, the wheel, the scoreboard and the shot.

All of it is the viewer's end of a fight -- what the context does when the
player dies and comes back, which key reaches which screen, and where a shot
goes when the mouse is what aimed it. It runs without a GL window: a context
here is its input path and a view platform, and a shot is a ray.
"""

from __future__ import annotations

import types

import numpy as np
import pytest
from OpenGLContext.move import viewplatform

from twig_bb import (
    arena, deathcam, firstperson, game, hud, player, projectiles, rules,
    viewer, weapons,
)
from viewersupport import (
    BindingRecorder, HeadlessContext, look_once, walking_platform,
)


class TestDyingAndComingBack:
    """Being killed has to be something the player *experiences*.

    The scoreboard said "Bot 1 fragged you" while the player went on standing
    in the same place shooting, which reads as the message being wrong rather
    than as a death: nothing about the world changed.  Three things follow from
    the rules deciding somebody died -- the gun stops answering, the camera
    stops being published as a body to shoot at, and coming back puts the
    player somewhere new.
    """

    def context(self, tmp_path, monkeypatch):
        """A viewer's match wiring with a real character and no window."""
        from OpenGLContext.move.viewplatform import ViewPlatform
        nav = walking_platform(tmp_path)
        context = HeadlessContext(nav)
        # The physics platform drives a plain view platform, which is what the
        # window renders from and what a shot is aimed along.
        context.platform = ViewPlatform(position=nav.camera_position())
        context.config = viewer.build_parser().parse_args(['map.bsp'])
        context.weapons = weapons.default_table()
        context.player = player.PlayerState()
        context.player.selected = context.weapons.weapons[0].key
        context.arena = arena.Arena(weapons=context.weapons, fragLimit=15,
                                    timeLimit=10.0)
        context.arena.add(game.PLAYER_ID, position=np.zeros(3), name='You')
        context.loaded = None
        context.minds = {}
        context.botBodies = {}
        context.hud = None
        # What plays the tick.  The viewer holds one of these and the rules
        # inside it are tested against a constructed world in test_rules; what
        # is checked here is that this context is wired to one.
        context.rules = rules.Rules(context.arena, minds={},
                                    flight=projectiles.Projectiles(),
                                    spawns=[np.array([4.0, 2.0, 4.0])])
        context.deathCamera = deathcam.DeathCamera()
        # A hand with nothing in it: what a context has before a model loads,
        # and enough to take the recoil a shot writes to it.
        context.hand = firstperson.WeaponHand(context.weapons)
        for name in ('_shoot', '_aim', '_cameBack', '_watchDeath'):
            setattr(context, name,
                    getattr(viewer.TwigContext, name).__get__(context))
        fired = []
        monkeypatch.setattr(viewer.game, 'shoot',
                            lambda *a, **k: fired.append(a) or None)
        return context, fired

    def kill(self, context):
        context.arena.damage(game.PLAYER_ID, 1000.0, by='bot1')
        assert not context.arena.combatant(game.PLAYER_ID).alive

    def test_a_dead_player_cannot_shoot(self, tmp_path, monkeypatch):
        context, fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._shoot()
        assert fired == []

    def test_pulling_the_trigger_while_dead_asks_to_come_back(self, tmp_path,
                                                              monkeypatch):
        """The trigger is what ends a death; the timer is only its floor."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        assert context.rules.waiting_to_come_back(game.PLAYER_ID)
        context._shoot()
        assert not context.rules.waiting_to_come_back(game.PLAYER_ID)

    def test_an_empty_rifle_still_comes_back(self, tmp_path, monkeypatch):
        """Dying with an empty gun must not trap you at the scoreboard.

        The whole trigger path runs here, not just ``_shoot``: a dead player
        holding fire with no ammunition went through the weapon accounting,
        which answered "OUT OF CARTRIDGES" and never reached the respawn.  The
        trigger is a respawn request while dead, whatever the gun holds.
        """
        context, _fired = self.context(tmp_path, monkeypatch)
        context._runCommands = viewer.TwigContext._runCommands.__get__(context)
        posted = []
        context.hud = type('_Hud', (),
                           {'post': lambda _self, text: posted.append(text)})()
        weapon = context.weapons.by_key(context.player.selected)
        context.player.ammo[str(weapon.ammoType)] = 0
        self.kill(context)
        assert context.rules.waiting_to_come_back(game.PLAYER_ID)
        context._runCommands([], firing=True)
        assert not context.rules.waiting_to_come_back(game.PLAYER_ID)
        # And the empty gun said nothing: a corpse has no round to be out of.
        assert posted == []

    def test_a_corpse_does_not_burn_ammunition(self, tmp_path, monkeypatch):
        """Holding fire while dead must not drain the ammunition you respawn
        with: a corpse has no gun, so the accounting does not run."""
        context, _fired = self.context(tmp_path, monkeypatch)
        context._runCommands = viewer.TwigContext._runCommands.__get__(context)
        context.hud = type('_Hud', (), {'post': lambda _self, text: None})()
        weapon = context.weapons.by_key(context.player.selected)
        context.player.ammo[str(weapon.ammoType)] = 5
        self.kill(context)
        context._runCommands([], firing=True)
        assert context.player.ammo[str(weapon.ammoType)] == 5

    def test_dying_takes_the_view_away_from_the_navigator(self, tmp_path,
                                                          monkeypatch):
        """The camera was the piece of a death with no owner: it stayed where
        it was killed, still steered by the mouse, which reads as the notice
        being wrong rather than as a death."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        assert context.deathCamera.watching

    def test_the_view_falls_towards_the_floor(self, tmp_path, monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        was = float(context._nav.camera_position()[1])
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        context.deathCamera.advance(deathcam.DROP_SECONDS * 2)
        assert float(context.deathCamera.position()[1]) < was

    def test_coming_back_gives_the_view_to_the_navigator_again(self, tmp_path,
                                                               monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        context._watchDeath(context.arena.drain(), dt=0.0)
        context.arena.advance(10.0)
        context.rules.ask_to_respawn(game.PLAYER_ID)
        context._cameBack(context.rules.respawn_due())
        assert not context.deathCamera.watching

    def test_a_death_with_nobody_to_blame_still_takes_the_view(self, tmp_path,
                                                               monkeypatch):
        """The lava, a long fall: there is nothing to look at, and dying is
        still dying."""
        context, _fired = self.context(tmp_path, monkeypatch)
        context.arena.kill(game.PLAYER_ID, cause='lava')
        context._watchDeath(context.arena.drain(), dt=0.0)
        assert context.deathCamera.watching

    def test_a_living_player_can(self, tmp_path, monkeypatch):
        context, fired = self.context(tmp_path, monkeypatch)
        context._shoot()
        assert fired

    def test_a_dead_player_is_not_published_into_the_match(self, tmp_path,
                                                           monkeypatch):
        """While dead there is no body to shoot at, and the camera is not it."""
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        before = np.array(context.arena.combatant(game.PLAYER_ID).position)
        context.rules.publish(game.PLAYER_ID, (9.0, 9.0, 9.0))
        assert np.allclose(
            context.arena.combatant(game.PLAYER_ID).position, before)

    def test_a_living_player_is(self, tmp_path, monkeypatch):
        context, _fired = self.context(tmp_path, monkeypatch)
        before = np.array(context.arena.combatant(game.PLAYER_ID).position)
        context.rules.publish(game.PLAYER_ID, (9.0, 9.0, 9.0))
        assert not np.allclose(
            context.arena.combatant(game.PLAYER_ID).position, before)

    def test_respawning_moves_the_camera_rather_than_only_the_record(
            self, tmp_path, monkeypatch):
        """The camera is where the player *is*.

        The arena's respawn is overwritten a frame later by the tick that
        publishes the camera into the match, so a respawn nothing told the
        camera about puts the player straight back where they were shot.  The
        rules decide *where*; what is checked here is that this context does
        something with the answer.
        """
        context, _fired = self.context(tmp_path, monkeypatch)
        self.kill(context)
        was = np.array(context._nav.camera_position()[:3])
        context.arena.advance(10.0)
        # The player comes back when they *ask*; see `Rules.ask_to_respawn`.
        context.rules.ask_to_respawn(game.PLAYER_ID)
        context._cameBack(context.rules.respawn_due())
        assert context.arena.combatant(game.PLAYER_ID).alive
        assert not np.allclose(context._nav.camera_position()[:3], was)


class _MessageSink:
    """Just enough HUD for the weapon commands: somewhere to post a line."""

    def __init__(self):
        self.lines = []

    def post(self, text, *args, **named):
        self.lines.append(text)


class _WheelRecorder(BindingRecorder):
    """A recorder that also keeps the *functions* a wheel notch would reach."""

    def __init__(self):
        super().__init__()
        self.wheel = {}
        self._wheelHandlers = []

    def addEventHandler(self, kind, **named):
        super().addEventHandler(kind, **named)
        if kind == 'mousebutton':
            self.wheel.setdefault(
                (named.get('button'), named.get('state')), []
            ).append(named.get('function'))

    def notch(self, button):
        """Deliver one wheel notch the way GLFW's scroll callback does.

        A notch is a press *and* a release (see
        :meth:`OpenGLContext.events.glfwevents.GLFWEventHandler._emitWheel`),
        so both states are offered and only the ones bound to them run.
        """
        for state in (1, 0):
            for function in self.wheel.get((button, state), ()):
                function(None)


class TestWhatTheSessionRecordingIsTold:
    """The viewer's half of :mod:`twig_bb.telemetry`.

    What each mark *says* is checked in `tests/test_telemetry.py`, against the
    marker on its own. What is checked here is the thing that file cannot see:
    that the game is wired to it, and that the marks are made where the events
    they describe actually happen.
    """

    def context(self):
        from twig_bb import telemetry as gamemarks
        recorder = _WheelRecorder()
        recorder.weapons = weapons.default_table()
        recorder.player = player.PlayerState.carrying(recorder.weapons)
        recorder.weaponBindings = viewer.controls.WeaponBindings()
        recorder.hud = _MessageSink()
        recorder.arena = arena.Arena(weapons=recorder.weapons)
        recorder.arena.add(game.PLAYER_ID, position=np.zeros(3), name='You')
        recorder.telemetry = _Session()
        recorder.marks = gamemarks.GameMarks(recorder)
        recorder.mark = recorder.telemetry.mark
        for name in ('_wheelWeapon', '_runCommands'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        return recorder

    def test_changing_weapons_is_marked(self):
        held = self.context()
        held._runCommands([viewer.controls.NEXT_WEAPON], firing=False)
        assert [name for name, _fields in held.telemetry.marks] == [
            'weapon-selected']

    def test_the_mark_says_what_ended_up_in_the_player_s_hands(self):
        """After the commands have been applied, not before: a mark naming the
        weapon that was put down would be the one thing a reader trusts."""
        held = self.context()
        held._runCommands([viewer.controls.NEXT_WEAPON], firing=False)
        assert held.telemetry.marks[0][1]['weapon'] == str(held.player.selected)

    def test_a_frame_with_nothing_in_it_says_nothing(self):
        held = self.context()
        held._runCommands([], firing=False)
        assert held.telemetry.marks == []

    def test_asking_to_come_back_is_marked(self):
        """A death that went on is either a player who never pulled the
        trigger or a request that was swallowed, and those are different bugs."""
        held = self.context()
        held.rules = _AskedRules()
        held.arena.damage(game.PLAYER_ID, 1000.0, by='bot1')
        held._runCommands([], firing=True)
        assert [name for name, _fields in held.telemetry.marks] == [
            'respawn-asked']


class _Session:
    """A recording that keeps what it was told, as the engine's does."""

    def __init__(self):
        self.marks = []

    def mark(self, name, /, **fields):
        self.marks.append((name, fields))


class _AskedRules:
    """The rules, as much of them as a trigger pulled while dead touches."""

    def __init__(self):
        self.asked = []

    def ask_to_respawn(self, who):
        self.asked.append(who)


class TestTheWeaponWheel:
    """One notch of the wheel is one weapon.

    A wheel notch arrives as a press *and* a release, so anything bound to
    both — or bound twice — steps twice for one movement of the finger, which
    reads as a wheel that skips a weapon.
    """

    def context(self):
        recorder = _WheelRecorder()
        recorder.weapons = weapons.default_table()
        recorder.player = player.PlayerState.carrying(recorder.weapons)
        recorder.weaponBindings = viewer.controls.WeaponBindings()
        recorder.hud = _MessageSink()
        for name in ('_bindWeaponKeys', '_wheelWeapon', '_runCommands'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        recorder._bindWeaponKeys()
        return recorder

    def held(self, recorder):
        return str(recorder.player.selected)

    def test_one_notch_up_moves_one_weapon(self):
        recorder = self.context()
        keys = recorder.weapons.keys()
        before = self.held(recorder)
        recorder.notch(viewer.WHEEL_UP)
        assert self.held(recorder) == keys[(keys.index(before) + 1) % len(keys)]

    def test_one_notch_down_moves_one_weapon(self):
        recorder = self.context()
        keys = recorder.weapons.keys()
        before = self.held(recorder)
        recorder.notch(viewer.WHEEL_DOWN)
        assert self.held(recorder) == keys[(keys.index(before) - 1) % len(keys)]

    def test_a_notch_is_bound_once_and_only_on_the_press(self):
        """Bound to the release as well, every notch would count twice."""
        recorder = self.context()
        for button in (viewer.WHEEL_UP, viewer.WHEEL_DOWN):
            assert len(recorder.wheel.get((button, 1), [])) == 1
            assert not recorder.wheel.get((button, 0))

    def test_a_full_turn_of_the_wheel_comes_back_to_where_it_started(self):
        recorder = self.context()
        before = self.held(recorder)
        for _notch in range(len(recorder.weapons.keys())):
            recorder.notch(viewer.WHEEL_UP)
        assert self.held(recorder) == before


class TestTheScoreboardKey:
    """The board is held down, not toggled.

    It covers the middle of the screen, so a board somebody left up by
    accident is a board they get shot behind.
    """

    def context(self):
        recorder = _WheelRecorder()
        recorder.weapons = weapons.default_table()
        recorder.player = player.PlayerState.starting(recorder.weapons)
        recorder.weaponBindings = viewer.controls.WeaponBindings()
        recorder.arena = arena.Arena(weapons=recorder.weapons, fragLimit=15,
                                     timeLimit=10.0)
        recorder.arena.add(game.PLAYER_ID, name='You')
        recorder.arena.add('bot1', bot=True, name='Bot 1')
        recorder.hud = hud.GameHUD(recorder.weapons)
        for name in ('_bindWeaponKeys', '_wheelWeapon', '_runCommands',
                     '_showScores', '_hideScores'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        recorder._bindWeaponKeys()
        return recorder

    def bound(self, recorder, state):
        return [name for kind, name, at in recorder.bindings
                if kind == 'keyboard' and at == state]

    def test_it_is_bound_to_both_the_press_and_the_release(self):
        recorder = self.context()
        assert viewer.SCOREBOARD_KEY in self.bound(recorder, 1)
        assert viewer.SCOREBOARD_KEY in self.bound(recorder, 0)

    def test_holding_it_puts_the_board_up(self):
        recorder = self.context()
        recorder._showScores()
        assert recorder.hud.standings.visible
        assert len(recorder.hud.standings.children) == 3   # heading and two

    def test_letting_go_takes_it_down(self):
        recorder = self.context()
        recorder._showScores()
        recorder._hideScores()
        assert not recorder.hud.standings.visible

    def test_a_run_with_no_hud_is_harmless(self):
        """A capture run has none and must still be able to press keys."""
        recorder = self.context()
        recorder.hud = None
        recorder._showScores()
        recorder._hideScores()


class TestTheMatchWiringStaysInStep:
    """What draws a fight must be what a fight is emitted into.

    The match is built once at start-up (so the menu has something) and again
    when a level is loaded, and each build makes a fresh arena, a fresh set of
    effect emitters and a fresh projectile batch. Anything that captured the
    *first* set and was not rebuilt with the second is then looking at objects
    nothing writes to any more: the effects go on being born into emitters that
    are not in the scene, so they are never stepped and never drawn, and from
    inside the game the weapons appear to do nothing at all.
    """

    def context(self):
        """The match wiring built twice, as a launch does.

        The weapon table and the audio engine are supplied rather than built:
        what is under test is which objects the presenter ends up holding, and
        loading a first-person model to find that out would be a test that
        failed for two reasons.
        """
        made = HeadlessContext(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.loaded = None
        made.weapons = weapons.default_table()
        made._audioEngine = lambda: None
        for name in ('_buildMatch', '_installMatch', '_bindPresenter'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._buildMatch()          # what OnInit does before a level exists
        made.hud = _MessageSink()
        made._bindPresenter()       # what _startGame does once there is a HUD
        made._buildMatch()          # what loading a level does
        return made

    def test_the_presenter_reads_the_match_that_is_being_played(self):
        made = self.context()
        assert made._presenter.match is made.arena

    def test_the_effects_it_draws_into_are_the_ones_in_the_scene(self):
        made = self.context()
        assert made._presenter.effects is made.effects

    def test_the_sounds_it_plays_are_for_the_match_being_played(self):
        made = self.context()
        assert made._presenter.sounds.match is made.arena

    def test_the_bots_think_about_the_match_being_played(self):
        made = self.context()
        assert set(made.minds) == {one.id for one in made.arena.bots()}

    def test_a_burst_reaches_an_emitter_that_is_in_the_scene(self):
        """The end of the chain, and the thing a player actually notices."""
        made = self.context()
        made.arena.impact(point=(1, 0, 0), normal=(0, 1, 0), surface='stone')
        made._presenter.show(made.arena.drain(), camera=(0, 0, 0),
                             forward=(0, 0, -1))
        drawn = {id(child) for child in made.effects.group.children}
        alive = [emitter for emitter in made.effects.emitters.values()
                 if emitter.pool.live]
        assert alive
        assert all(id(emitter) in drawn for emitter in alive)


class TestTheMouseFiresInTheGame:
    """A click on the left button has to reach a shot, through the real path.

    The unit tests say the binding names the button and the sampler records
    it; this says the two meet — that a press delivered as the backend
    delivers it, sampled the way the frame loop samples it, spends a round and
    takes a shot.
    """

    def context(self, monkeypatch):
        from OpenGLContext.events.inputstate import InputState
        made = HeadlessContext(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.weapons = weapons.default_table()
        made.player = player.PlayerState.carrying(made.weapons)
        made.player.selected = made.weapons.weapons[0].key
        # A shot can only come from a living body in a match, and the trigger
        # path now asks whether that body is alive before spending a round.
        made.arena = arena.Arena(weapons=made.weapons, fragLimit=15,
                                 timeLimit=10.0)
        made.arena.add(game.PLAYER_ID, position=np.zeros(3), name='You')
        made.weaponBindings = viewer.controls.WeaponBindings()
        made.hud = _MessageSink()
        made._inputState = InputState()
        made.getInputState = lambda: made._inputState
        made._fov = None
        fired = []
        for name in ('_sampleWeapons', '_runCommands', '_sight'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._shoot = lambda: fired.append(1)
        return made, fired

    def press(self, made, down=1, button=viewer.controls.LEFT_BUTTON):
        from OpenGLContext.events.mouseevents import MouseButtonEvent
        event = MouseButtonEvent()
        event.button = button
        event.state = down
        made._inputState.process(event)

    def test_a_held_button_takes_a_shot(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        self.press(made)
        made._sampleWeapons()
        assert fired

    def test_it_spends_a_round(self, monkeypatch):
        made, _fired = self.context(monkeypatch)
        weapon = made.weapons.by_key(made.player.selected)
        before = made.player.ammo_for(weapon)
        self.press(made)
        made._sampleWeapons()
        assert made.player.ammo_for(weapon) < before

    def test_nothing_is_fired_before_the_button_goes_down(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        made._sampleWeapons()
        assert not fired

    def test_letting_go_stops_it(self, monkeypatch):
        made, fired = self.context(monkeypatch)
        self.press(made)
        made._sampleWeapons()
        self.press(made, down=0)
        del fired[:]
        made._sampleWeapons()
        assert not fired


class TestTheMouseSightsTheRifle:
    """The other button, through the same sampler: it narrows the frustum.

    The whole of the zoom on the window's side is that the field of view the
    view is drawn with follows what is in the player's hand -- so what is
    checked is the platform's own frustum, which is what the projection is
    built from and what the reticule is scaled through.
    """

    def context(self, key='rifle'):
        from OpenGLContext.events.inputstate import InputState
        made = HeadlessContext(None)
        made.config = viewer.build_parser().parse_args(['map.bsp'])
        made.weapons = weapons.default_table()
        made.player = player.PlayerState.carrying(made.weapons)
        made.player.selected = key
        made.weaponBindings = viewer.controls.WeaponBindings()
        made.hud = _MessageSink()
        made._fov = None
        made._inputState = InputState()
        made.getInputState = lambda: made._inputState
        for name in ('_sampleWeapons', '_runCommands', '_sight'):
            setattr(made, name,
                    getattr(viewer.TwigContext, name).__get__(made))
        made._shoot = lambda: None
        return made

    def press(self, made, down=1):
        from OpenGLContext.events.mouseevents import MouseButtonEvent
        event = MouseButtonEvent()
        event.button = viewer.controls.RIGHT_BUTTON
        event.state = down
        made._inputState.process(event)

    def test_holding_it_narrows_the_view(self):
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) < wide

    def test_letting_go_gives_the_view_back(self):
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        self.press(made, down=0)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_switching_weapon_while_sighted_gives_it_back_too(self):
        """Nothing has to remember to cancel it: it is read from the hand."""
        made = self.context()
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        made.player.selected = 'pistol'
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_a_weapon_with_no_sight_does_nothing(self):
        made = self.context(key='shotgun')
        wide = viewer.view_fov(made.platform)
        self.press(made)
        made._sampleWeapons()
        assert viewer.view_fov(made.platform) == pytest.approx(wide)

    def test_the_near_and_far_planes_are_left_alone(self):
        """A frustum is four numbers and only one of them is the zoom."""
        made = self.context()
        made.platform.setFrustum(near=0.05, far=9000.0)
        self.press(made)
        made._sampleWeapons()
        assert made.platform.frustum[2:] == (0.05, 9000.0)


class TestAShotGoesWhereTheCameraLooks:
    """The reticule is in the middle of the screen, so a shot leaves along it.

    There are two ways to ask a view platform which way it is looking and they
    are not interchangeable: **the platform's angles rotate the world, not the
    camera**, so a heading built from the inverse of its orientation agrees
    with the gaze only while nothing is turned, and mirrors it as soon as
    something is. That is a shot that goes left when the player turns right,
    and up when they look down — and it looks correct in the one case anybody
    checks first, straight ahead.

    `viewer.gaze` is the verified one: `test_the_gaze_rule_agrees_with_the_walk_direction`
    checks it against `_world_dir`, which is checked against the map-angle
    spec. So a shot must agree with `gaze`.
    """

    def platform(self, tmp_path, yaw=0.0, pitch=0.0):
        """The navigator the viewer actually aims from."""
        made = walking_platform(tmp_path)
        made.yaw, made.pitch = yaw, pitch
        return made

    def fired(self, nav):
        """The direction the *context* would fire, given this navigator.

        Through the context's own aim rather than a helper, because the bug
        was which object the context asked: the view platform the renderer
        draws from does not carry the look at all, so a shot taken from it
        went the same way whichever way the player turned.
        """
        context = HeadlessContext(nav)
        context._nav = nav
        return np.asarray(viewer.TwigContext._aim(context)[1], dtype='d')

    def origin(self, nav):
        context = HeadlessContext(nav)
        context._nav = nav
        return np.asarray(viewer.TwigContext._aim(context)[0], dtype='d')

    def test_straight_ahead_it_agrees(self, tmp_path):
        made = self.platform(tmp_path)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_turned_left_it_still_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=0.7)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_turned_right_it_still_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=-0.7)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_a_pitched_shot_goes_the_way_the_camera_looks(self, tmp_path):
        """The grenade that went up when the player looked down.

        Which sign of ``pitch`` looks down is not asserted -- the platform's
        angles turn the world, so the sign says nothing on its own. What is
        asserted is that the shot goes the same way the gaze does, for both.
        """
        for pitch in (-0.6, 0.6):
            made = self.platform(tmp_path, pitch=pitch)
            looking = float(viewer.gaze(made)[1])
            assert abs(looking) > 0.1, 'the fixture is not pitched'
            assert float(self.fired(made)[1]) * looking > 0.0

    def test_looking_down_with_the_keys_shoots_downward(self, tmp_path):
        """Through the look binding, which is how a player pitches the view."""
        made = self.platform(tmp_path)
        for _frame in range(5):
            look_once(made, '<down>')
        looking = float(viewer.gaze(made)[1])
        assert looking < 0.0, 'the look-down key did not lower the gaze'
        assert float(self.fired(made)[1]) < 0.0

    def test_turned_and_pitched_together_it_agrees(self, tmp_path):
        made = self.platform(tmp_path, yaw=1.1, pitch=-0.4)
        assert self.fired(made) == pytest.approx(viewer.gaze(made), abs=1e-6)

    def test_it_is_a_unit_heading(self, tmp_path):
        made = self.platform(tmp_path, yaw=1.1, pitch=-0.4)
        assert float(np.linalg.norm(self.fired(made))) == pytest.approx(1.0)

    def test_the_shot_leaves_from_where_the_camera_is(self, tmp_path):
        """From the navigator too: the same object that knows where it looks."""
        made = self.platform(tmp_path, yaw=1.1)
        assert self.origin(made) == pytest.approx(
            np.asarray(made.camera_position()[:3], dtype='d'), abs=1e-6)

    def test_with_no_navigator_it_aims_straight_ahead(self, tmp_path):
        """A viewer that has not started walking still answers something sane."""
        class _NotWalkingYet:
            _nav = None

        origin, direction = viewer.TwigContext._aim(_NotWalkingYet())
        assert np.asarray(direction) == pytest.approx((0.0, 0.0, -1.0))
        assert np.asarray(origin) == pytest.approx((0.0, 0.0, 0.0))


class TestTheShotIsUnderTheCrosshair:
    """The one test above this that could not be argued with.

    Everything else here checks the aim against `viewer.gaze`, and `gaze`
    against `_world_dir`: three rules that agree with each other and could all
    be wrong the same way, which is what a shot that pans the wrong way *is*.

    So this checks the aim against something that is not a rule at all — the
    two matrices the renderer builds the frame from. A point along the aim is
    put through them exactly as a vertex is, and the answer has to be the
    middle of the screen, because that is where the crosshair is drawn. There
    is no convention left to get backwards: if this passes, what the player
    sees under the crosshair is what the shot hits.

    The matrices are pure arithmetic (`ViewPlatform.modelMatrix` and
    `.viewMatrix`), so this needs no window; the same measurement taken from
    inside the running game agrees with it.
    """

    #: Metres down the aim to put the mark.  Far enough that any error in the
    #: heading is a large screen offset rather than a rounding difference.
    RANGE = 30.0

    def screen_position(self, nav):
        """Where the shot's mark lands on screen, in normalised device space.

        (0, 0) is the middle -- the crosshair -- and (±1, ±1) the edges.
        """
        platform = viewplatform.ViewPlatform()
        # Driven the way the game drives it, so the frame measured here is the
        # frame the player is shown.
        platform.setPosition(nav.camera_position())
        platform.setOrientation(nav.camera_orientation())
        context = HeadlessContext(nav)
        context._nav = nav
        origin, direction = viewer.TwigContext._aim(context)
        mark = np.append(np.asarray(origin, dtype='d')
                         + np.asarray(direction, dtype='d') * self.RANGE, 1.0)
        clip = np.dot(mark, np.dot(np.asarray(platform.modelMatrix()),
                                   np.asarray(platform.viewMatrix())))
        assert clip[3] > 0.0, 'the shot went behind the camera'
        return clip[:2] / clip[3]

    @pytest.mark.parametrize('yaw', [0.0, 0.7, -0.7, 2.4, -2.4])
    @pytest.mark.parametrize('pitch', [0.0, 0.5, -0.5])
    def test_it_lands_in_the_middle_of_the_screen(self, tmp_path, yaw, pitch):
        made = walking_platform(tmp_path)
        made.yaw, made.pitch = yaw, pitch
        assert self.screen_position(made) == pytest.approx((0.0, 0.0),
                                                           abs=1e-6)


class TestEscapeMidMatch:
    """Escape must never end a match without asking.

    It was bound straight to the context's forcible quit, so a key pressed to
    close a screen, dismiss a notice or back out of anything at all ended the
    session -- with no confirmation and nothing to undo it.
    """

    def context(self, loaded=True):
        recorder = _WheelRecorder()
        recorder.quits = 0
        recorder.pushed = []
        recorder._menuPanel = None
        recorder.loaded = (types.SimpleNamespace(name='q3dm1')
                           if loaded else None)
        recorder.config = types.SimpleNamespace(cache_dir=None)
        recorder.pushOverlay = lambda panel: (recorder.pushed.append(panel)
                                              or panel)
        recorder.OnQuit = lambda event=None: setattr(
            recorder, 'quits', recorder.quits + 1)
        for name in ('OnEscape', 'showMenu', '_closeMenu', '_menuSubtitle',
                     '_playScreen', '_contentScreen', '_creditsScreen',
                     '_settings'):
            setattr(recorder, name,
                    getattr(viewer.TwigContext, name).__get__(recorder))
        return recorder

    def test_it_puts_the_menu_up_instead_of_quitting(self):
        recorder = self.context()
        recorder.OnEscape()
        assert recorder.pushed, 'no menu appeared'
        assert recorder.quits == 0

    def test_that_menu_offers_resume(self):
        recorder = self.context()
        recorder.OnEscape()
        assert recorder.pushed[-1].find('resume') is not None

    def test_resuming_puts_the_menu_away_and_keeps_the_match(self):
        recorder = self.context()
        recorder.OnEscape()
        panel = recorder.pushed[-1]
        panel.find('resume').activate()
        assert panel.closed
        assert recorder.quits == 0

    def test_quitting_is_still_offered(self):
        recorder = self.context()
        recorder.OnEscape()
        recorder.pushed[-1].find('quit').activate()
        assert recorder.quits == 1

    def test_with_no_match_running_there_is_nothing_to_resume(self):
        """At the start screen, Escape has nothing to go back to."""
        recorder = self.context(loaded=False)
        recorder.OnEscape()
        assert recorder.pushed[-1].find('resume') is None
