"""Weapon commands: how they are declared, sampled, and what they do.

The binding page is OpenGLContext's and is tested there; what matters here is
that these commands are declared in the shape that page understands, that a
number key selects once however long it is held, and that firing goes through
the weapon's own numbers.
"""

from __future__ import annotations

import pytest

from OpenGLContext.events.inputstate import InputState

from twig_bb import controls, weapons
from twig_bb.player import PlayerState


class FakeMode:
    def __init__(self, name, bindings):
        self.name = name
        self.bindings = bindings


class FakeNavigation:
    def __init__(self, modes):
        self._modes = modes

    def modes(self):
        return self._modes


def key(state, name, down=1):
    """Feed one key transition, as the event system spells it."""
    class Event:
        pass
    event = Event()
    event.name = name
    event.state = down
    state.process(event)


def button(state, index, down=1):
    """Feed one mouse-button transition, as the event system spells it."""
    from OpenGLContext.events.mouseevents import MouseButtonEvent
    event = MouseButtonEvent()
    event.button = index
    event.state = down
    state.process(event)


@pytest.fixture
def bindings():
    return controls.WeaponBindings()


@pytest.fixture
def table():
    return weapons.default_table()


@pytest.fixture
def player(table):
    return PlayerState.starting(table)


class TestDeclaration:
    def test_a_command_is_declared_for_every_number_key_offered(self, bindings):
        names = [str(binding.command) for binding in bindings.bindings]
        assert controls.slot_command(1) in names
        assert controls.slot_command(int(bindings.slots)) in names

    def test_firing_and_the_two_directions_are_declared(self, bindings):
        names = [str(binding.command) for binding in bindings.bindings]
        for command in (controls.FIRE, controls.NEXT_WEAPON,
                        controls.PREVIOUS_WEAPON):
            assert command in names

    def test_every_weapon_in_the_loadout_has_a_number_key(self, table,
                                                          bindings):
        """A weapon with no key is a weapon most players never find."""
        names = [str(binding.command) for binding in bindings.bindings]
        for weapon in table.weapons:
            assert controls.slot_command(int(weapon.slot)) in names, weapon.key

    def test_every_command_carries_a_label_for_the_binding_page(self, bindings):
        for binding in bindings.bindings:
            assert str(binding.label)

    def test_the_defaults_can_be_asked_for_again(self, bindings):
        """The binding page's Reset needs this; it is the mode protocol."""
        assert bindings.defaultBindings()

    def test_a_command_name_says_which_slot_it_selects(self):
        assert controls.slot_of('weapon.3') == 3
        assert controls.slot_of(controls.FIRE) is None


class TestSampling:
    def test_a_number_key_fires_its_command_once_per_press(self, bindings):
        state = InputState()
        key(state, '2')
        assert controls.slot_command(2) in bindings.triggered(state)
        assert bindings.triggered(state) == []

    def test_holding_the_fire_key_keeps_firing(self, bindings):
        state = InputState()
        key(state, '<control>')
        assert bindings.firing(state) is True
        assert bindings.firing(state) is True
        key(state, '<control>', down=0)
        assert bindings.firing(state) is False

    def test_firing_is_not_reported_as_a_one_shot_command(self, bindings):
        state = InputState()
        key(state, '<control>')
        assert controls.FIRE not in bindings.triggered(state)

    def test_a_rebound_key_takes_effect_at_once(self, bindings):
        state = InputState()
        bindings.binding(controls.NEXT_WEAPON).keys = ['q']
        key(state, 'q')
        assert controls.NEXT_WEAPON in bindings.triggered(state)

    def test_an_unbound_command_never_fires(self, bindings):
        state = InputState()
        bindings.binding(controls.NEXT_WEAPON).keys = []
        key(state, ']')
        assert controls.NEXT_WEAPON not in bindings.triggered(state)


class TestZooming:
    """Held like the trigger, because it is a thing you look *through*.

    A toggle would be the wrong shape: a player zooms for the second it takes
    to line a shot up and wants the wide view back the instant the finger
    lifts, and a scope left on by accident is a player who cannot see anyone
    walk up to them.
    """

    def test_it_is_declared(self, bindings):
        assert controls.ZOOM in [str(one.command) for one in bindings.bindings]

    def test_it_is_on_the_right_mouse_button(self, bindings):
        """Where every game in this genre puts it."""
        assert '<mouse-1>' in bindings.keys_for(controls.ZOOM)

    def test_holding_it_keeps_it_zoomed(self, bindings):
        state = InputState()
        button(state, 1)
        assert bindings.zooming(state) is True
        assert bindings.zooming(state) is True

    def test_letting_go_gives_the_view_back(self, bindings):
        state = InputState()
        button(state, 1)
        button(state, 1, down=0)
        assert bindings.zooming(state) is False

    def test_it_is_not_reported_as_a_one_shot_command(self, bindings):
        """Or holding it would count as a selection, once a frame."""
        state = InputState()
        button(state, 1)
        assert controls.ZOOM not in bindings.triggered(state)

    def test_it_can_be_rebound_like_anything_else(self, bindings):
        state = InputState()
        bindings.binding(controls.ZOOM).keys = ['v']
        key(state, 'v')
        assert bindings.zooming(state) is True


class TestBindingPage:
    def test_the_table_holds_movement_and_weapons_together(self, bindings):
        from OpenGLContext.move.modes import KeyBinding
        walk = FakeMode('walk', [KeyBinding(command='forward', keys=['w'])])
        table = controls.Controls(FakeNavigation([walk]),
                                  bindings).binding_table()
        groups = [group for group, _binding in table]
        assert 'walk' in groups
        assert 'weapons' in groups

    def test_movement_comes_first(self, bindings):
        from OpenGLContext.move.modes import KeyBinding
        walk = FakeMode('walk', [KeyBinding(command='forward', keys=['w'])])
        table = controls.Controls(FakeNavigation([walk]),
                                  bindings).binding_table()
        assert table[0][0] == 'walk'

    def test_a_context_with_no_navigation_still_offers_the_weapons(self,
                                                                   bindings):
        table = controls.Controls(None, bindings).binding_table()
        assert [group for group, _binding in table] == ['weapons'] * len(
            bindings.bindings)

    def test_rebinding_reaches_the_declared_binding(self, bindings):
        made = controls.Controls(None, bindings)
        assert made.rebind('weapons', controls.NEXT_WEAPON, ['n']) is True
        assert bindings.keys_for(controls.NEXT_WEAPON) == ['n']

    def test_rebinding_something_undeclared_says_so(self, bindings):
        made = controls.Controls(None, bindings)
        assert made.rebind('weapons', 'weapon.teleport', ['t']) is False


class TestWhatTheCommandsDo:
    def test_a_number_key_puts_a_held_weapon_in_hand(self, player, table):
        player.give('shotgun')
        events = controls.apply_commands([controls.slot_command(2)], False,
                                         player, table, now=0.0)
        assert player.selected == 'shotgun'
        assert [event.kind for event in events] == ['select']

    def test_selecting_a_weapon_says_which(self, player, table):
        player.give('shotgun')
        events = controls.apply_commands([controls.slot_command(2)], False,
                                         player, table, now=0.0)
        assert events[0].text == 'SHOTGUN'

    def test_a_weapon_you_do_not_have_says_so(self, player, table):
        events = controls.apply_commands([controls.slot_command(2)], False,
                                         player, table, now=0.0)
        assert [event.kind for event in events] == ['refused']
        assert 'SHOTGUN' in events[0].text

    def test_selecting_what_is_already_in_hand_says_nothing(self, player,
                                                            table):
        assert controls.apply_commands([controls.slot_command(1)], False,
                                       player, table, now=0.0) == []

    def test_a_slot_with_no_weapon_on_it_does_nothing(self, player, table):
        assert controls.apply_commands(['weapon.9'], False, player, table,
                                       now=0.0) == []

    def test_firing_spends_ammunition(self, player, table):
        before = player.ammo['bullets']
        controls.apply_commands([], True, player, table, now=1.0)
        assert player.ammo['bullets'] == before - 1

    def test_the_fire_rate_is_the_weapon_s_own(self, player, table):
        controls.apply_commands([], True, player, table, now=1.0)
        spent = player.ammo['bullets']
        controls.apply_commands([], True, player, table, now=1.01)
        assert player.ammo['bullets'] == spent, 'fired faster than the table'
        interval = float(table.by_key('pistol').fireInterval)
        controls.apply_commands([], True, player, table, now=1.0 + interval)
        assert player.ammo['bullets'] == spent - 1

    def test_firing_opens_the_cone(self, player, table):
        controls.apply_commands([], True, player, table, now=1.0)
        assert player.spread_fraction(1.0) > 0

    def test_an_empty_weapon_says_so_rather_than_firing(self, player, table):
        player.ammo['bullets'] = 0
        events = controls.apply_commands([], True, player, table, now=1.0)
        assert [event.kind for event in events] == ['empty']

    def test_an_empty_weapon_does_not_say_so_every_frame(self, player, table):
        player.ammo['bullets'] = 0
        controls.apply_commands([], True, player, table, now=1.0)
        assert controls.apply_commands([], True, player, table,
                                       now=1.01) == []

    def _arm(self, player, *keys):
        for key in keys:
            weapon = weapons.default_table().by_key(key)
            player.give(key)
            player.give_ammo(str(weapon.ammoType), int(weapon.startingAmmo))

    def test_firing_the_last_round_falls_to_the_best_loaded_weapon(self, player,
                                                                    table):
        """The trigger the player is still holding meets a loaded gun next pull,
        rather than the spent one it just emptied."""
        self._arm(player, 'rocket')
        player.ammo['bullets'] = 1
        events = controls.apply_commands([], True, player, table, now=1.0)
        assert [event.kind for event in events] == ['fire', 'select']
        assert events[1].text == 'ROCKET'
        assert player.selected == 'rocket'

    def test_an_empty_trigger_switches_to_the_best_loaded_weapon(self, player,
                                                                  table):
        self._arm(player, 'rocket')
        player.ammo['bullets'] = 0
        events = controls.apply_commands([], True, player, table, now=1.0)
        assert [event.kind for event in events] == ['empty', 'select']
        assert player.selected == 'rocket'

    def test_it_falls_to_the_highest_not_the_next_one_along(self, player, table):
        """Pistol empty, both a shotgun and a launcher loaded: the launcher."""
        self._arm(player, 'shotgun', 'rocket')
        player.ammo['bullets'] = 0
        controls.apply_commands([], True, player, table, now=1.0)
        assert player.selected == 'rocket'

    def test_with_nothing_else_loaded_it_only_says_it_is_empty(self, player,
                                                               table):
        player.ammo['bullets'] = 0
        events = controls.apply_commands([], True, player, table, now=1.0)
        assert [event.kind for event in events] == ['empty']
        assert player.selected == 'pistol'

    def test_the_wheel_walks_the_weapons_held(self, player, table):
        player.give('shotgun')
        controls.apply_commands([controls.NEXT_WEAPON], False, player, table,
                                now=0.0)
        assert player.selected == 'shotgun'
        controls.apply_commands([controls.PREVIOUS_WEAPON], False, player,
                                table, now=0.0)
        assert player.selected == 'pistol'


class TestTheTriggerIsTheMouseButton:
    """In a first-person game the left mouse button fires.

    Not a preference: it is the one binding every player of the genre already
    has in their hand, and a game that answered only `ctrl` reads as a game
    where firing does nothing at all — no shot, no sound, no ammunition going
    down, nothing to diagnose from inside it.
    """

    def bindings(self):
        return controls.WeaponBindings()

    def test_the_left_mouse_button_fires(self):
        state = InputState()
        button(state, controls.LEFT_BUTTON)
        assert self.bindings().firing(state)

    def test_letting_go_stops_firing(self):
        state = InputState()
        button(state, controls.LEFT_BUTTON)
        button(state, controls.LEFT_BUTTON, down=0)
        assert not self.bindings().firing(state)

    def test_control_still_fires_as_well(self):
        """The old binding is kept: some players hold a modifier by habit."""
        state = InputState()
        key(state, '<control>')
        assert self.bindings().firing(state)

    def test_the_right_button_does_not_fire(self):
        state = InputState()
        button(state, controls.LEFT_BUTTON + 1)
        assert not self.bindings().firing(state)

    def test_the_binding_page_can_show_it(self):
        """It is a declared binding like any other, not a special case."""
        from OpenGLContext.events import mouseevents
        keys = self.bindings().keys_for(controls.FIRE)
        assert mouseevents.button_name(controls.LEFT_BUTTON) in keys
