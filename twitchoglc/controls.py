"""The commands this game has that are not ways of moving, and their keys.

Movement is declared as `MovementMode` nodes with their own `KeyBinding`s, and
the F6 screen enumerates them.  Choosing a weapon and firing are commands of the
same shape and want the same treatment, so they are declared the same way here
and :class:`Controls` presents both to that screen as one table.  Nothing about
the binding page had to change: it drives anything that can list its modes.

**Selection is edge-triggered and firing is not.**  A number key selects once
however long it is held (`InputState.pressed`, which is consumed by reading);
firing repeats while the button is down (`InputState.held`).  That difference is
the reason these are sampled rather than bound to event handlers -- sampling is
also what lets a rebinding take effect immediately, with nothing to unregister.

**The wheel is not rebindable yet.**  `InputState` records keyboard transitions
only, so a wheel notch cannot be sampled the way a key can; the viewer routes it
to the same next/previous commands through a mouse-button handler.  The keyboard
bindings for those commands *are* rebindable, and the wheel follows whatever
they do.
"""

from __future__ import annotations

from gettext import gettext as _
from typing import Any, List, NamedTuple, Optional, Sequence, Tuple

from vrml import field, node

from OpenGLContext.move.modes import KeyBinding

__all__ = [
    'WeaponBindings', 'Controls', 'Event', 'apply_commands',
    'FIRE', 'NEXT_WEAPON', 'PREVIOUS_WEAPON', 'slot_command', 'slot_of',
]

#: Command names.  Selecting weapon *n* is ``weapon.n`` so the commands follow
#: the table rather than being written out here: a fourth weapon needs a table
#: entry and nothing else.
FIRE = 'fire'
NEXT_WEAPON = 'weapon.next'
PREVIOUS_WEAPON = 'weapon.previous'

#: Number keys weapons are offered on, in order.
SLOT_KEYS = ('1', '2', '3', '4', '5', '6', '7', '8', '9')


def slot_command(slot: int) -> str:
    """The command name that selects the weapon on a number key."""
    return 'weapon.%d' % (int(slot),)


def slot_of(command: str) -> Optional[int]:
    """The number key a ``weapon.n`` command names, or None if it is not one."""
    if not command.startswith('weapon.'):
        return None
    tail = command[len('weapon.'):]
    return int(tail) if tail.isdigit() else None


class WeaponBindings(node.Node):
    """The weapon commands, shaped like a movement mode so F6 can show them.

    ``name``, ``bindings`` and ``defaultBindings()`` are the whole of the
    protocol the binding page and the binding store use, which is why this can
    join that page without either of them knowing what a weapon is.
    """

    PROTO = 'WeaponBindings'
    name = field.newField('name', 'SFString', 1, 'weapons')
    bindings = field.newField('bindings', 'MFNode', 1, list)
    #: How many number keys to declare.  More than the loadout has is harmless
    #: -- a command for a weapon nobody carries simply never fires -- and it is
    #: what lets §7 add a weapon without touching the binding defaults.
    slots = field.newField('slots', 'SFInt32', 1, 4)

    def __init__(self, **named: Any) -> None:
        super(WeaponBindings, self).__init__(**named)
        if not self.bindings:
            self.bindings = list(self.defaultBindings())

    def defaultBindings(self) -> Sequence[KeyBinding]:
        """The keys these commands start on."""
        made = [
            KeyBinding(command=FIRE, label=_('Fire'),
                       keys=['<control>', '<ctrl>']),
            KeyBinding(command=NEXT_WEAPON, label=_('Next weapon'),
                       keys=[']']),
            KeyBinding(command=PREVIOUS_WEAPON, label=_('Previous weapon'),
                       keys=['[']),
        ]
        for index in range(int(self.slots)):
            made.append(KeyBinding(
                command=slot_command(index + 1),
                label=_('Weapon %d') % (index + 1,),
                keys=[SLOT_KEYS[index]]))
        return made

    # -- sampling ---------------------------------------------------------
    def binding(self, command: str) -> Optional[KeyBinding]:
        for found in self.bindings:
            if str(found.command) == command:
                return found
        return None

    def keys_for(self, command: str) -> List[str]:
        found = self.binding(command)
        return [str(key) for key in found.keys] if found is not None else []

    def firing(self, state: Any) -> bool:
        """Whether the fire command is down right now."""
        keys = self.keys_for(FIRE)
        return bool(keys) and bool(state.held(*keys))

    def triggered(self, state: Any) -> List[str]:
        """The one-shot commands pressed since this was last asked.

        In declared order, and each consumed by the reading, so a key held
        across ten frames selects a weapon once.
        """
        found = []
        for binding in self.bindings:
            command = str(binding.command)
            if command == FIRE:
                continue
            keys = [str(key) for key in binding.keys]
            if keys and state.pressed(*keys):
                found.append(command)
        return found


class Controls(object):
    """Movement modes and weapon commands, as one table for the F6 screen.

    An adapter rather than a subclass of either: the navigation manager owns
    the modes and knows nothing about weapons, and the weapon bindings are a
    node with no idea a camera exists.  What the binding page needs from both
    is `modes()`, `binding_table()` and `rebind()`, and that is all this is.
    """

    def __init__(self, navigation: Any, weapons: WeaponBindings) -> None:
        self.navigation = navigation
        self.weapons = weapons

    def modes(self) -> List[Any]:
        found = list(self.navigation.modes()) if self.navigation else []
        found.append(self.weapons)
        return found

    def binding_table(self) -> List[Tuple[str, KeyBinding]]:
        """``(group name, binding)`` for every command, movement first."""
        return [(str(mode.name), binding)
                for mode in self.modes() for binding in mode.bindings]

    def rebind(self, group: str, command: str,
               keys: Sequence[str]) -> bool:
        """Point a command at different keys; False if it is not declared."""
        for mode in self.modes():
            if str(mode.name) != group:
                continue
            for binding in mode.bindings:
                if str(binding.command) == command:
                    binding.keys = list(keys)
                    return True
        return False


class Event(NamedTuple):
    """Something the simulation did, for the presentation layer to answer.

    [PROJECT-PLAN §11](../PROJECT-PLAN.md) asks that the rules emit events and
    that the HUD, the sounds and the effects consume them rather than being
    called from inside the rules.  This is that seam at its smallest: ``kind``
    is what happened and ``text`` is what a player should be told, empty when
    there is nothing worth saying.
    """

    kind: str
    text: str = ''


def apply_commands(commands: Sequence[str], firing: bool, player: Any,
                   table: Any, now: float) -> List[Event]:
    """Run this frame's commands against the player, and say what happened.

    The rules are deliberately thin: this is the stand-in for §7, which owns
    what a shot actually *does*.  What is real here is the accounting the HUD
    shows -- which weapon is in hand, ammunition going down, the fire rate the
    weapon's table entry declares, and the cone of fire opening as it is used.

    Nothing here draws or plays anything.  It returns events and the caller
    decides what to do with them.
    """
    events: List[Event] = []
    for command in commands:
        events.extend(_select(command, player, table))
    if firing:
        events.extend(_fire(player, table, now))
    return events


def _select(command: str, player: Any, table: Any) -> List[Event]:
    """One selection command: a number key, or a step through what is held."""
    before = player.selected
    slot = slot_of(command)
    if slot is not None:
        weapon = table.by_slot(slot)
        if weapon is None:
            return []
        if not player.has(str(weapon.key)):
            # Named rather than ignored: pressing 4 and getting silence leaves
            # a player wondering whether the key is bound or the weapon is
            # missing, and those want different answers.
            return [Event('refused',
                          _('NO %s') % (str(weapon.title).upper(),))]
        player.select(str(weapon.key))
    elif command == NEXT_WEAPON:
        player.cycle(table, 1)
    elif command == PREVIOUS_WEAPON:
        player.cycle(table, -1)
    else:
        return []
    if player.selected == before:
        return []
    weapon = table.by_key(player.selected)
    return [Event('select', str(weapon.title) if weapon is not None else '')]


def _fire(player: Any, table: Any, now: float) -> List[Event]:
    """One frame of holding the fire command down."""
    weapon = table.by_key(player.selected)
    if weapon is None or not player.ready(weapon, now):
        return []
    if not player.spend(weapon):
        # Out of ammunition: reported once per attempted shot rather than once
        # per frame, because ``ready`` still gates it.
        player.last_shot = now
        return [Event('empty', _('OUT OF %s')
                      % (str(weapon.ammoType).upper(),))]
    player.fired(now)
    return [Event('fire')]
