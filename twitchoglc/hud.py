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
"""

from __future__ import annotations

import math
from typing import Any, List, Optional, Sequence, Tuple

from vrml import field

from OpenGLContext.ui.geometry import Rect
from OpenGLContext.ui.hudwidgets import (
    BarMeter, Crosshair, HUDGroup, HUDLayer, HUDWidget, MessageQueue, Readout,
    hud_text,
)
from OpenGLContext.ui.metrics import FontMetrics

from . import weapons as weapontable

__all__ = ['GameHUD', 'WeaponBar', 'WeaponSlot', 'AMMO_CRITICAL']

#: Rounds left at or below which the ammunition readout turns red.  Enough for
#: a shot or two, so it means "reload or run" rather than "you have already
#: lost".
AMMO_CRITICAL = 5

#: How far above the bottom row the weapon bar sits, in pixels at the reference
#: font size: a line of text and the space around it.
WEAPON_BAR_LIFT = 26

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
        return '%s %s' % (slot.label, slot.title)

    def content_size(self, metrics: FontMetrics,
                     available: Optional[int] = None) -> Tuple[int, int]:
        if not self.slots:
            return (0, 0)
        spacing = metrics.pixels(self.spacing)
        width = sum(metrics.text_width(self.slotText(slot))
                    for slot in self.slots)
        return (width + spacing * (len(self.slots) - 1), metrics.char_height)

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
        self.children = [
            self.crosshair, self.vitals, self.ammo, self.weaponbar,
            self.messages,
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
        self._updateVitals(player)
        self._updateAmmo(player, weapon)
        self._updateWeapons(player)
        self._updateReticule(player, weapon, now, viewport, field_of_view)

    def _updateVitals(self, player: Any) -> None:
        self.health.value = float(player.health)
        self.health.maximum = float(player.max_health)
        self.armour.value = float(player.armour)
        self.armour.maximum = float(player.max_armour)
        # Hidden rather than drawn empty: a player with no armour has one
        # meter to read, and an empty second bar is a thing to check for.
        self.armour.visible = player.armour > 0

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

    # -- events -----------------------------------------------------------
    def post(self, text: str, now: Optional[float] = None,
             color: Optional[Sequence[float]] = None) -> None:
        """Announce a pickup, a frag or a warning."""
        self.messages.post(text, now=now, color=color)

    def hit(self, now: Optional[float] = None) -> None:
        """Acknowledge a confirmed hit, so the player sees the shot land."""
        self.crosshair.hit(now)
