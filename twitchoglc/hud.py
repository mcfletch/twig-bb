"""This game's screen furniture: what the numbers mean and where they go.

The widgets are OpenGLContext's (:mod:`OpenGLContext.ui.hudwidgets`), because a
crosshair and a bar meter are the same thing in every game.  What is *here* is
everything that is a rule of **this** game: which corner health goes in, that
armour is hidden until there is some, that two rounds left is worth colouring
red, and that the reticule comes from the weapon in hand rather than from the
HUD.

**Nothing developer-facing goes here.**  Frame rates, draw counts, positions in
map coordinates and the movement mode are the debug overlay's
(:mod:`twitchoglc.debug`), and the two must not drift back together: the whole
point of splitting them is that a player sees a game and a developer sees a
game plus instruments.

**It reads a state; it does not own one.**  :meth:`GameHUD.update` takes a
:class:`~twitchoglc.player.PlayerState` and writes what it finds onto the
widgets.  Nothing here changes the game, which is what lets the HUD be driven
from a test with a constructed state and no window.

**Every time it is given is :func:`now`'s**, which is the clock the layer is
ticked against.  Two clocks in a HUD is not a small mistake: every fade becomes
the difference between them.
"""

from __future__ import annotations

import math
import time
from typing import Any, List, Optional, Sequence, Tuple

from vrml import field

from OpenGLContext.ui.geometry import Rect
from OpenGLContext.ui.hudwidgets import (
    BarMeter, Crosshair, DamageIndicator, HUDGroup, HUDLayer, HUDWidget,
    MessageQueue, Readout, ScreenWash, hud_text,
)
from OpenGLContext.ui.metrics import FontMetrics

from . import weapons as weapontable

__all__ = ['GameHUD', 'WeaponBar', 'WeaponSlot', 'AMMO_CRITICAL', 'now']


def now() -> float:
    """The clock every reading on this HUD is taken against.

    **One clock, and this is it.**  Everything on a HUD that fades, expires or
    flashes is driven by :meth:`~OpenGLContext.ui.hudwidgets.HUDLayer.tick`,
    which the context calls once a frame with :func:`time.monotonic`.  A game
    that marked a hit with :func:`time.time` and let the layer expire it
    against the monotonic clock would compute every fade from the difference
    between two of them -- which is about fifty years, and looks on screen like
    a damage wash and a hit mark that never go away.

    Named here rather than left as a call to :mod:`time` at each site so there
    is one place to be right, and so a test can say what the rule is.
    """
    return time.monotonic()

#: Rounds left at or below which the ammunition readout turns red.  Enough for
#: a shot or two, so it means "reload or run" rather than "you have already
#: lost".
AMMO_CRITICAL = 5

#: How far above the bottom row the weapon bar sits, in pixels at the reference
#: font size: a line of text and the space around it.
WEAPON_BAR_LIFT = 26

#: How far below the middle of the screen the name of whoever is under the
#: crosshair sits, in pixels at the reference font size.  Clear of the
#: reticule, because a name drawn through it makes both unreadable.
TARGET_DROP = 34

#: What the world looks like through being dead.  The strength is the death
#: camera's -- see :data:`twitchoglc.deathcam.WASH` -- because it comes up with
#: the fall, and this is only the colour.
DEATH_WASH_COLOUR = (0.65, 0.04, 0.04)

#: The vertical field of view the reticule's spread is projected through when
#: nobody has said otherwise.  The view platform's own frustum is what should
#: be passed in; this is what a test or a first frame gets.
DEFAULT_FIELD_OF_VIEW = math.pi / 2.0


class WeaponSlot(object):
    """One entry in the weapon bar: a number key and the weapon on it."""

    __slots__ = ('label', 'title', 'key', 'held', 'selected')

    def __init__(self, label: str, title: str, key: str,
                 held: bool = False, selected: bool = False) -> None:
        self.label = label
        self.title = title
        self.key = key
        self.held = held
        self.selected = selected


class WeaponBar(HUDWidget):
    """The weapons, which are held, and which is in hand.

    Every weapon in the table is shown whether or not it is held, because what
    a player wants from this at a glance is *which number key do I press* --
    and a bar that reflows as weapons are picked up makes that a question they
    have to re-read every time.
    """

    PROTO = 'WeaponBar'
    anchor = field.newField('anchor', 'SFString', 1, 'bottom')
    #: Pixels between one slot and the next, at the reference font size.
    spacing = field.newField('spacing', 'SFFloat', 1, 10.0)

    def __init__(self, **named: Any) -> None:
        super(WeaponBar, self).__init__(**named)
        #: What is on the bar right now.  Not a field: it is this frame's
        #: reading of the player's state.
        self.slots: List[WeaponSlot] = []
        #: Whether there is room for the weapons' names as well as their keys.
        #: Decided by :meth:`arrange` against the window it is being laid out
        #: in; True until something has measured it, so a bar nobody has
        #: arranged reads as it would on a screen with room.
        self.titled = True

    def slotColour(self, slot: WeaponSlot, skin: Any) -> Any:
        """The colour one slot's text is drawn in.

        Three states and three colours: in hand, held, and not held.  The
        selected weapon uses the good/accent colour rather than a brighter
        white, because "which one am I holding" is the question this bar is
        most often being scanned for.
        """
        if slot.selected:
            return skin.hudGood
        if slot.held:
            return skin.hudText
        return skin.disabledText

    def slotText(self, slot: WeaponSlot) -> str:
        """One slot as it is drawn: its key and title, or the key alone.

        **The number key is what survives.**  It is the one thing on this bar
        a player cannot work out for themselves, so when a loadout no longer
        fits across the window the titles go and the keys stay -- rather than
        the bar running off both ends and answering "which key" for the middle
        weapons only.
        """
        if self.titled:
            return '%s %s' % (slot.label, slot.title)
        return slot.label

    def content_size(self, metrics: FontMetrics,
                     available: Optional[int] = None) -> Tuple[int, int]:
        """How much room the bar wants, dropping the titles if it must.

        Decided while it is being measured, because it is a question about the
        *window*: the same loadout wants its titles on a desktop and its number
        keys alone in a small one, and neither is a property of the weapons.
        """
        if not self.slots:
            return (0, 0)
        wide = self._width(metrics, True)
        self.titled = available is None or wide <= int(available)
        return ((wide if self.titled else self._width(metrics, False)),
                metrics.char_height)

    def _width(self, metrics: FontMetrics, titled: bool) -> int:
        """How wide the bar is, drawn one way or the other."""
        spacing = metrics.pixels(self.spacing)
        width = sum(metrics.text_width(
            '%s %s' % (slot.label, slot.title) if titled else slot.label)
            for slot in self.slots)
        return width + spacing * (len(self.slots) - 1)

    def slotRects(self, metrics: FontMetrics) -> List[Tuple[WeaponSlot, Rect]]:
        """Each slot and where it is drawn, left to right."""
        spacing = metrics.pixels(self.spacing)
        cursor = self.rect.x
        placed = []
        for slot in self.slots:
            width = metrics.text_width(self.slotText(slot))
            placed.append((slot, Rect(cursor, self.rect.y, width,
                                      self.rect.height)))
            cursor += width + spacing
        return placed

    def paint(self, renderer: Any) -> None:
        skin = renderer.skin
        for slot, rect in self.slotRects(renderer.metrics):
            hud_text(renderer, rect, self.slotText(slot),
                     self.slotColour(slot, skin))


class GameHUD(HUDLayer):
    """The arrangement: reticule in the middle, vitals left, ammunition right.

    Built once from a weapon table and then written to every frame.  The
    widgets are held as attributes rather than looked up by name because this
    class *is* the arrangement -- there is no file to author it in and no
    reason to pretend otherwise.
    """

    PROTO = 'GameHUD'

    def __init__(self, table: Any = None, **named: Any) -> None:
        super(GameHUD, self).__init__(**named)
        self.table = table if table is not None else weapontable.default_table()

        self.crosshair = Crosshair()
        self.health = BarMeter(label='HEALTH', value=100, maximum=100,
                               barWidth=160)
        # Armour keeps its own colour rather than the health thresholds: it is
        # a resource that runs out, not a state that gets dangerous, and
        # colouring it red at 20 would say the wrong thing.
        self.armour = BarMeter(label='ARMOUR', value=0, maximum=100,
                               barWidth=160, color=(0.55, 0.72, 1.0, 1.0),
                               visible=False)
        self.vitals = HUDGroup(anchor='bottom-left', spacing=4,
                               children=[self.health, self.armour])
        self.ammo = Readout(anchor='bottom-right', align='right')
        # Lifted a line clear of the bottom row: at a small window the meters
        # and the ammunition reach far enough across that a bar on the same
        # line runs through both of them.
        self.weaponbar = WeaponBar(anchor='bottom', offset=(0, WEAPON_BAR_LIFT))
        self.messages = MessageQueue(anchor='top', duration=4.0, fade=1.0)
        self.damage = DamageIndicator()
        # Two lines rather than one, because they answer two questions and a
        # player reads the first of them at a glance and the second on purpose.
        self.deathcause = Readout(value='', align='center')
        self.respawn = Readout(value='', align='center')
        self.dead = HUDGroup(anchor='center', spacing=6, visible=False,
                             children=[self.deathcause, self.respawn])
        # **How you are doing, permanently.**  A player who cannot tell
        # whether they are winning is playing a different game from the one
        # the frag limit describes, and the full board on a held key is not a
        # substitute: nobody holds a key to find out something they want to
        # know continuously.  Small, in the corner furthest from the reticule
        # and from the meters, because it is read at a glance between fights
        # rather than during one.
        self.frags = Readout(anchor='top-right', label='FRAGS', align='right')
        # **Who is under the crosshair.**  Nothing in the world said who
        # anybody was, so a fight was against interchangeable red shapes and
        # there was no way to tell an opponent you were hunting from one who
        # had just arrived.  Under the reticule rather than over their head:
        # a name that hung over everybody would show through walls and change
        # how the game is played, and this only ever names somebody a shot
        # would actually reach.
        self.target = Readout(anchor='center', align='center',
                              offset=(0, -TARGET_DROP), visible=False)
        # The whole board, on a held key.  Rebuilt from the match each time it
        # goes up rather than kept current: it is up for a second at a time
        # and a scoreboard nobody is looking at should cost nothing.
        self.standings = HUDGroup(anchor='center', spacing=2, visible=False,
                                  children=[])
        # What the world looks like through being dead.  Under everything,
        # like the damage wash and for the same reason -- and *over* nothing,
        # because the point of leaving the world drawn is watching the fight
        # go on without you.
        self.death = ScreenWash(colour=DEATH_WASH_COLOUR, strength=0.0)
        # The washes go underneath everything else: they are the world being
        # tinted, not widgets, and a health bar one covered would be a health
        # bar nobody could read at the moment they most need to.
        self.children = [
            self.death, self.damage, self.crosshair, self.target, self.vitals,
            self.ammo, self.weaponbar, self.messages, self.frags,
            self.standings, self.dead,
        ]

    # -- reading the game -------------------------------------------------
    def update(self, player: Any, now: float,
               viewport: Optional[Sequence[int]] = None,
               field_of_view: float = DEFAULT_FIELD_OF_VIEW) -> None:
        """Write a player's state onto the widgets.

        ``viewport`` and ``field_of_view`` are needed only by the reticule,
        which converts the weapon's cone of fire into pixels through the
        renderer's own projection; without them it keeps the gap it has.
        """
        weapon = self.table.by_key(player.selected)
        self._updateVitals(player, now)
        self._updateAmmo(player, weapon)
        self._updateWeapons(player)
        self._updateReticule(player, weapon, now, viewport, field_of_view)

    def _updateVitals(self, player: Any, now: float) -> None:
        """Write health and armour, and flash whichever of them just fell.

        **Falling only.**  Losing health is the thing a player has to notice
        while looking somewhere else; picking a medkit up is something they
        did on purpose and already know about, and flashing for it would spend
        the signal on the half of the news that is good.
        """
        self._settle(self.health, float(player.health), now)
        self.health.maximum = float(player.max_health)
        self._settle(self.armour, float(player.armour), now)
        self.armour.maximum = float(player.max_armour)
        # Hidden rather than drawn empty: a player with no armour has one
        # meter to read, and an empty second bar is a thing to check for.
        self.armour.visible = player.armour > 0

    @staticmethod
    def _settle(meter: Any, value: float, now: float) -> None:
        """Put a value on a meter, flashing it if that is a drop."""
        if value < float(meter.value):
            meter.flash(now)
        meter.value = value

    def _updateAmmo(self, player: Any, weapon: Any) -> None:
        if weapon is None:
            self.ammo.label = ''
            self.ammo.value = ''
            self.ammo.critical = False
            return
        rounds = player.ammo_for(weapon)
        self.ammo.label = str(weapon.title)
        self.ammo.value = str(rounds)
        self.ammo.critical = rounds <= AMMO_CRITICAL

    def _updateWeapons(self, player: Any) -> None:
        self.weaponbar.slots = [
            WeaponSlot(str(int(weapon.slot)), str(weapon.title),
                       str(weapon.key),
                       held=player.has(str(weapon.key)),
                       selected=str(weapon.key) == player.selected)
            for weapon in self.table.weapons
        ]

    def _updateReticule(self, player: Any, weapon: Any, now: float,
                        viewport: Optional[Sequence[int]],
                        field_of_view: float) -> None:
        """Take the reticule from the weapon, and open it by its spread.

        The weapon's own ``Crosshair`` node is copied onto the one the HUD
        draws rather than swapped in, so the layer's children do not change as
        weapons are switched and the hit mark's clock survives a switch.
        """
        if weapon is not None and weapon.crosshair:
            source = weapon.crosshair
            for name in ('shape', 'gap', 'length', 'thickness', 'dotSize'):
                setattr(self.crosshair, name, getattr(source, name))
        if weapon is None or viewport is None:
            return
        # ``spread`` is authored in reference pixels like every other size in
        # the UI, and the projection answers in real ones, so the interface
        # scale has to come back out of it -- otherwise the reticule of a
        # weapon would open twice as far on a 4K display as the shot does.
        pixels = weapontable.reticule_spread(
            weapon, player.spread_fraction(now), int(viewport[1]),
            field_of_view)
        self.crosshair.spread = pixels / max(1e-6, self.metrics.scale)

    def looking_at(self, name: str) -> None:
        """Name whoever is under the crosshair, or clear it with ''.

        Hidden rather than blanked when there is nobody, so an empty line does
        not hold a gap under the reticule for the whole of a match.
        """
        self.target.value = str(name)
        self.target.visible = bool(name)

    # -- how the match is going --------------------------------------------
    def score(self, frags: int, limit: int = 0) -> None:
        """Write the player's standing into the corner.

        ``limit`` is the frags that end the match, and is shown because "7"
        means nothing on its own: what a player is deciding is whether to
        press or to go and find armour, and that decision is about the
        distance left.  A match with no frag limit shows the count alone
        rather than an ``/ 0`` nobody can read.

        Deaths are deliberately *not* in the corner.  They belong on the board
        with everybody else's, where a death count is a comparison; on its own
        it is a number that only ever goes up, and it would make the corner
        say two things at once.
        """
        self.frags.value = ('%d / %d' % (int(frags), int(limit))
                            if int(limit) > 0 else str(int(frags)))
        # One frag from the end, which is the moment a player most needs to
        # know where they are.
        self.frags.critical = (int(limit) > 0
                               and int(frags) >= int(limit) - 1)

    def scoreboard(self, lines: Sequence[str]) -> None:
        """Put the whole board up, one row per line.

        The rows are rebuilt rather than updated, because the board is shown
        for a second at a time and a set of widgets kept current for a panel
        nobody is looking at is work done for nothing.  Left-aligned and taken
        as given: :func:`twitchoglc.game.scoreboard_lines` has already made
        the columns line up, and a HUD that re-tabulated them would be a
        second opinion about the same table.
        """
        self.standings.children = [Readout(value=str(line), align='left')
                                   for line in lines]
        self.standings.visible = bool(lines)

    def hide_scoreboard(self) -> None:
        """Take the board down.  Idempotent: a key released twice is one key."""
        self.standings.visible = False

    # -- events -----------------------------------------------------------
    def post(self, text: str, now: Optional[float] = None,
             color: Optional[Sequence[float]] = None) -> None:
        """Announce a pickup, a frag or a warning."""
        self.messages.post(text, now=now, color=color)

    def hit(self, now: Optional[float] = None) -> None:
        """Acknowledge a confirmed hit, so the player sees the shot land."""
        self.crosshair.hit(now)

    def dying(self, strength: float) -> None:
        """How red the world is right now, 0 to 1.

        Driven every frame rather than switched on at the death, because it
        comes up *with* the camera's fall: the two are one movement, and a
        wash that arrived first would read as a screen effect rather than as
        dying.  See :class:`twitchoglc.deathcam.DeathCamera`.
        """
        self.death.strength = max(0.0, min(1.0, float(strength)))

    def died(self, cause: str, respawn_in: float) -> None:
        """Say the player is dead, and what will bring them back.

        The countdown is honest and is the point of the second line: a player
        looking at a still world with no gun and no explanation cannot tell a
        death from a hang, and telling them costs one number.

        Once the wait is over the line becomes an **instruction** rather than
        a count, because at that moment the wait is no longer what is stopping
        them -- pulling the trigger is what ends a death, and a screen still
        saying "respawning..." while nothing happens is the same hang the
        countdown exists to rule out.
        """
        self.deathcause.value = cause or 'You died'
        self.respawn.value = ('Respawning in %.1f' % (respawn_in,)
                              if respawn_in > 0 else 'Fire to respawn')
        self.dead.visible = True

    def revived(self) -> None:
        """Take the death notice down; the player has a new body.

        The damage marks go with it: a fresh body is not still bleeding from
        the wounds of the last one.
        """
        self.dead.visible = False
        self.damage.clear()
        self.death.strength = 0.0
