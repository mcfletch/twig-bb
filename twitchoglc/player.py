"""What the player has right now: health, armour, ammunition, weapons.

**A record, not attributes scattered over the scenegraph.**
[PROJECT-PLAN §11](../PROJECT-PLAN.md) asks for game state that can be
enumerated, copied and compared long before there is a network to send it over,
and that is a decision worth taking now rather than retrofitting: a thing that
can be copied can be snapshotted, asserted about in a test, and later
replicated.  So this is a plain dataclass with no drawing, no GL and no
scenegraph in it.

**It reads a weapon's numbers; it does not hold them.**  Fire rate, cost per
shot and the cone of fire are fields of :mod:`twitchoglc.weapons`, which is the
game's design document; what is here is how much of each the player has left.

Firing, damage and hit detection proper are §7.  What this carries of them is
the bookkeeping the HUD has to show: ammunition going down, health and armour
coming off, and how far the current weapon's cone has opened.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ['PlayerState']


@dataclass
class PlayerState:
    """One player's simulation state.

    Health and armour are whole numbers because that is how they are shown and
    how a player thinks about them; a fractional health bar reading 63.4 helps
    nobody.
    """

    #: The most of anything a player can carry.  A cap rather than an infinite
    #: pile so a HUD's ammunition field has a width and a pickup can be
    #: refused.
    AMMO_MAXIMUM = 999

    #: Armour absorbs this share of incoming damage while there is any left.
    #: Ours, not anybody else's: §7 owns the tuning, and this is the value the
    #: HUD is built against until it says otherwise.
    ARMOUR_SHARE = 0.6

    #: Seconds for a fully-open cone of fire to close again.
    SPREAD_RECOVERY = 0.6
    #: How much of the way to the widest cone one shot opens it.
    SPREAD_PER_SHOT = 0.35

    health: int = 100
    max_health: int = 100
    armour: int = 0
    max_armour: int = 100
    #: Ammunition by type name, matching ``Weapon.ammoType``.
    ammo: Dict[str, int] = field(default_factory=dict)
    #: Weapon keys held, in the order they were picked up.
    weapons: List[str] = field(default_factory=list)
    #: The key of the weapon in hand.
    selected: str = ''
    #: Frags and deaths, for §6's scoreboard.
    score: int = 0
    deaths: int = 0

    #: When the last shot was fired, on the caller's clock; None before any.
    last_shot: Optional[float] = None

    #: How open the cone of fire was at ``_fired_at``, and when that was.
    #: Private because the answer a caller wants is :meth:`spread_fraction`,
    #: which is a function of the clock.
    _spread: float = 0.0
    _fired_at: Optional[float] = None

    # -- starting out -----------------------------------------------------
    @classmethod
    def starting(cls, table: Any) -> 'PlayerState':
        """A player as they spawn: full health, the first weapon, some ammunition.

        The first weapon is whichever sits on slot 1, so a variant that retunes
        the table changes what a player spawns with by editing the table.
        """
        first = table.by_slot(1) or (table.weapons[0] if table.weapons else None)
        state = cls()
        if first is not None:
            state.weapons = [str(first.key)]
            state.selected = str(first.key)
            state.ammo = {str(first.ammoType): 50}
        return state

    @classmethod
    def carrying(cls, table: Any, ammunition: int = 60) -> 'PlayerState':
        """A player holding **everything** in the table, with ammunition for it.

        The stand-in loadout, and it exists because of a gap rather than a
        design: nothing in a map yet hands a player a weapon -- item entities
        are [§6](../PROJECT-PLAN.md) -- so a player who spawned with one would
        have number keys that could never do anything, which reads as a broken
        key rather than as a feature that has not arrived.  Everything held is
        the honest stand-in until items exist, at which point
        :meth:`starting` is what a match wants.
        """
        state = cls.starting(table)
        for weapon in table.weapons:
            state.give(str(weapon.key))
            state.give_ammo(str(weapon.ammoType), ammunition)
        return state

    @property
    def alive(self) -> bool:
        return self.health > 0

    # -- damage -----------------------------------------------------------
    def take_damage(self, amount: float) -> int:
        """Apply damage, armour first.  Returns how much reached the health.

        Armour absorbs a share of each hit and is spent doing it, which is what
        makes picking it up worth a detour without making it a second health
        bar.
        """
        amount = max(0.0, float(amount))
        absorbed = 0.0
        if self.armour > 0:
            absorbed = min(float(self.armour), amount * self.ARMOUR_SHARE)
            self.armour = int(round(self.armour - absorbed))
        taken = int(round(amount - absorbed))
        self.health = max(0, self.health - taken)
        return taken

    def heal(self, amount: float) -> None:
        """Restore health, never past the maximum."""
        self.health = min(self.max_health, self.health + int(round(amount)))

    def give_armour(self, amount: float) -> None:
        self.armour = min(self.max_armour, self.armour + int(round(amount)))

    # -- weapons ----------------------------------------------------------
    def has(self, key: str) -> bool:
        return key in self.weapons

    def give(self, key: str) -> bool:
        """Pick a weapon up.  False if it was already held."""
        if self.has(key):
            return False
        self.weapons.append(key)
        return True

    def select(self, key: str) -> bool:
        """Put a weapon in hand.  False if it is not held, or already in hand."""
        if not self.has(key) or key == self.selected:
            return False
        self.selected = key
        return True

    def select_slot(self, table: Any, slot: int) -> bool:
        """Select whatever sits on a number key.  False if it is not held."""
        weapon = table.by_slot(slot)
        if weapon is None:
            return False
        return self.select(str(weapon.key))

    def cycle(self, table: Any, step: int = 1) -> str:
        """Move to the next weapon held, in table order, and return its key.

        Table order rather than pickup order, so the wheel always walks the
        weapons in the order the HUD shows them -- a wheel whose order depends
        on what was picked up when is a wheel nobody can aim with.
        """
        held = [key for key in table.keys() if self.has(key)]
        if not held:
            return self.selected
        try:
            index = held.index(self.selected)
        except ValueError:
            index = 0 if step > 0 else -1
            self.selected = held[index]
            return self.selected
        self.selected = held[(index + step) % len(held)]
        return self.selected

    # -- ammunition -------------------------------------------------------
    def ammo_for(self, weapon: Any) -> int:
        """How much of what this weapon eats the player has."""
        if weapon is None:
            return 0
        return int(self.ammo.get(str(weapon.ammoType), 0))

    def give_ammo(self, kind: str, amount: int) -> int:
        """Add ammunition, capped.  Returns the new total."""
        total = min(self.AMMO_MAXIMUM, self.ammo.get(kind, 0) + int(amount))
        self.ammo[kind] = total
        return total

    def can_fire(self, weapon: Any) -> bool:
        return (weapon is not None
                and self.ammo_for(weapon) >= int(weapon.ammoPerShot))

    def spend(self, weapon: Any) -> bool:
        """Take one shot's worth of ammunition.  False if there was not enough."""
        if not self.can_fire(weapon):
            return False
        self.ammo[str(weapon.ammoType)] -= int(weapon.ammoPerShot)
        return True

    # -- firing -----------------------------------------------------------
    def ready(self, weapon: Any, now: float) -> bool:
        """Whether enough time has passed since the last shot to take another.

        The interval is the weapon's, so a fast weapon is fast because of its
        table entry and not because of anything here.
        """
        if weapon is None:
            return False
        if self.last_shot is None:
            return True
        return (now - self.last_shot) >= float(weapon.fireInterval)

    def fired(self, now: float) -> None:
        """Record a shot: the cone opens, and starts closing from here."""
        self._spread = min(1.0, self.spread_fraction(now) + self.SPREAD_PER_SHOT)
        self._fired_at = now
        self.last_shot = now

    def spread_fraction(self, now: float) -> float:
        """How far open the cone of fire is, from 0 (rest) to 1 (widest).

        A function of the clock rather than a value something has to remember
        to decay each frame: nothing has to tick, and the answer is the same
        whether it is asked once a frame or ten times.
        """
        if self._fired_at is None or self._spread <= 0:
            return 0.0
        elapsed = max(0.0, now - self._fired_at)
        if elapsed >= self.SPREAD_RECOVERY:
            return 0.0
        return max(0.0, self._spread * (1.0 - elapsed / self.SPREAD_RECOVERY))
