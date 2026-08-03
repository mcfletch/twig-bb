"""What the player has right now: health, armour, ammunition, weapons.

**A record, not attributes scattered over the scenegraph.**
[PROJECT-PLAN §11](../PROJECT-PLAN.md) asks for game state that can be
enumerated, copied and compared long before there is a network to send it over,
and that is a decision worth taking now rather than retrofitting: a thing that
can be copied can be snapshotted, asserted about in a test, and later
replicated.  So this is a plain dataclass with no drawing, no GL and no
scenegraph in it.

**It reads a weapon's numbers; it does not hold them.**  Fire rate, cost per
shot and the cone of fire are fields of :mod:`twig_bb.weapons`, which is the
game's design document; what is here is how much of each the player has left.

What a shot *does* is :mod:`twig_bb.combat` and
:mod:`twig_bb.projectiles`; what this carries is the bookkeeping the HUD has
to show and the rules read: ammunition going down, health and armour coming
off, and how far the current weapon's cone has opened.
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
    #: Ours, not anybody else's, and chosen so that a full set of armour is
    #: worth roughly another half a life -- enough to be worth a detour without
    #: making it a second health bar.
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
        the table changes what a player spawns with by editing the table — and
        how much ammunition comes with it is that weapon's own
        ``startingAmmo``, for the same reason: a number written here instead
        would be a second place to change and the first one nobody would
        remember.
        """
        first = table.by_slot(1) or (table.weapons[0] if table.weapons else None)
        state = cls()
        if first is not None:
            state.weapons = [str(first.key)]
            state.selected = str(first.key)
            state.ammo = {str(first.ammoType):
                          min(cls.AMMO_MAXIMUM, int(first.startingAmmo))}
        return state

    @classmethod
    def carrying(cls, table: Any, ammunition: Optional[int] = None) -> 'PlayerState':
        """A player holding **everything** in the table, with ammunition for it.

        Not what a match hands out -- :meth:`starting` is, and a level's
        pickups are the rest -- but what a demonstration wants: ``twig-bb-hud``
        shows the whole weapon bar and every reticule, and a bar with one
        weapon on it demonstrates nothing.  A test wanting a player who can
        fire anything wants this too.

        How much of each comes from the weapon's own ``startingAmmo``, because
        eight rockets and ninety rifle rounds are the same *amount of game*
        and a flat number for both is a rocket launcher with no cost.  Passing
        ``ammunition`` overrides every weapon's, which is what a test wanting
        one number wants.

        Two weapons sharing an ``ammoType`` share one pile: the larger of
        their numbers wins rather than the two adding up, so putting a second
        weapon on an existing pool does not quietly double it.
        """
        state = cls.starting(table)
        state.ammo = {}
        for weapon in table.weapons:
            state.give(str(weapon.key))
            wanted = (int(weapon.startingAmmo) if ammunition is None
                      else int(ammunition))
            kind = str(weapon.ammoType)
            state.ammo[kind] = min(cls.AMMO_MAXIMUM,
                                   max(state.ammo.get(kind, 0), wanted))
        return state

    def restore(self, table: Any) -> None:
        """Put this record back to how a player spawns, **in place**.

        In place rather than by handing out a new one, because everything that
        holds a player's state holds *this object* -- the HUD reads it, the
        input path writes it, the rules damage it -- and swapping it on a
        respawn leaves every one of them looking at a corpse.  That is what a
        HUD frozen at nought health from the first death onwards looks like
        from the inside.

        **Back to the starting loadout, not to everything.**  Dying costs you
        what you had picked up, which is what makes the things a map places
        worth walking to -- and a player who respawned holding every weapon in
        the game would have no reason ever to leave the room they died in.  It
        is also what makes the level a circuit rather than a room: see
        :mod:`twig_bb.items`.
        """
        fresh = self.starting(table)
        self.health, self.max_health = fresh.health, fresh.max_health
        # Armour is not restored: it is picked up, and coming back wearing what
        # you died in would make a set of armour a permanent upgrade.
        self.armour = 0
        self.ammo = dict(fresh.ammo)
        self.weapons = list(fresh.weapons)
        self.selected = fresh.selected
        self.last_shot = None
        self._spread = 0.0
        self._fired_at = None

    @property
    def alive(self) -> bool:
        return self.health > 0

    # -- damage -----------------------------------------------------------
    def take_damage(self, amount: float) -> int:
        """Apply damage, armour first.  Returns how much health it actually cost.

        Armour absorbs a share of each hit and is spent doing it, which is what
        makes picking it up worth a detour without making it a second health
        bar.
        """
        amount = max(0.0, float(amount))
        absorbed = 0.0
        if self.armour > 0:
            absorbed = min(float(self.armour), amount * self.ARMOUR_SHARE)
            self.armour = int(round(self.armour - absorbed))
        wanted = int(round(amount - absorbed))
        # What *landed*, not what was aimed: 500 damage at a target with 40
        # health left is 40, and a hit that reported 500 would put that number
        # on a HUD and in a damage log.
        taken = min(self.health, wanted)
        self.health -= taken
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

    def prefer(self, table: Any, key: str) -> bool:
        """Put a weapon just taken in hand, if it beats what is held.

        **Better only, and the table says which is better.**  A weapon walked
        over is the pickup a player most wants to feel, and one that only
        joins the bar makes the number key a step to remember in the middle of
        a fight.  Downgrading is the opposite failure and the worse one: being
        put on a pistol because you crossed the square it was lying on loses a
        firefight, so a weapon the hand already beats is taken and stowed.

        ``slot`` is the order, the same one the number keys and the weapon bar
        use, so what counts as an upgrade is a property of the table a designer
        edits rather than a rule written here.  An empty hand takes whatever
        arrives; without a table there is no order and nothing is disturbed.
        """
        if table is None or not key or not self.has(key):
            return False
        if not self.selected or not self.has(self.selected):
            return self.select(key)
        taken, held = table.by_key(key), table.by_key(self.selected)
        if taken is None or held is None:
            return False
        return self.select(key) if int(taken.slot) > int(held.slot) else False

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
