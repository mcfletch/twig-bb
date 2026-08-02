"""What a burst does to everybody near it: damage, cover, and the shove.

The other half of :mod:`twitchoglc.projectiles`.  A projectile's flight is one
question and what its detonation *means* is another, and they are apart because
the second is what makes rockets interesting: the damage falls off, geometry
stops it, and the push it gives is what a rocket jump is made of.

**Falloff is a declared curve to a declared radius.**  The numbers are ours —
there is nothing to look up and nothing to match — so
:class:`~twitchoglc.projectiles.Projectile`'s fields *are* the design and this
module only reads them.

**Blocked by geometry.**  A rocket round a corner must not kill, so every
candidate is tested with a ray cast from the burst to their chest.  The
candidate set is bounded by distance **first**: casting at everybody in the
match and then discarding the far ones is O(n²) in a firefight (B11), and the
cheap test is a subtraction.

**A shooter is pushed by their own rocket, and hurt by it.**  That is the
feature and not a case to guard against: the push is what makes the jump, and
the self-damage is what makes it a decision.  ``selfDamage`` scales the *damage*
and never the shove — a shooter is thrown exactly as hard as anybody else
standing there, or their own rocket would lift them less than a plain jump
does.  Both numbers are declared, so how brutal a rocket jump is can be tuned
without touching any of this.

The shove is left on the combatant as an unspent impulse rather than being
applied here.  The rules say how hard somebody was pushed; whatever *moves*
them decides what that means — the character controller for the player, a step
for a bot — which is what keeps the camera out of the rules.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Sequence

import numpy as np

from omi_physics import raycast

from . import combat

log = logging.getLogger(__name__)

__all__ = ['Splash', 'burst', 'falloff']

#: How far up a combatant's body a burst is aimed at when testing whether it
#: can see them, and where the push is measured to.  The chest rather than the
#: feet: a burst on the far side of a low wall should be stopped by it, and a
#: burst on the near side should not be stopped by the floor.
CHEST_HEIGHT = combat.BODY_HEIGHT * 0.5

#: What a burst exactly on top of somebody pushes them along.  Straight up,
#: because there is no other direction that a burst with no offset implies —
#: and up is the one that makes a rocket at your own feet a jump.
STRAIGHT_UP = np.array([0.0, 1.0, 0.0])


@dataclass(frozen=True)
class Splash:
    """What one burst did to one combatant."""

    target: str
    #: Health it actually cost, and the impulse it added, in metres per second.
    damage: int
    push: np.ndarray
    #: Metres from the centre of the burst to their chest.
    distance: float


def falloff(distance: float, radius: float, exponent: float = 1.0) -> float:
    """How much of a burst reaches ``distance``, from 1 at the centre to 0 at ``radius``.

    ``exponent`` above 1 concentrates the damage near the middle, which is what
    makes a near miss much weaker than a hit at the feet; below 1 spreads it
    out.  It is a field of the projectile, because the shape of this curve is
    a design decision and not an implementation detail.
    """
    if radius <= 0.0:
        return 0.0
    share = 1.0 - max(0.0, float(distance)) / float(radius)
    if share <= 0.0:
        return 0.0
    return float(share ** max(1e-6, float(exponent)))


def burst(world: Any, arena: Any, point: Sequence[float], kind: Any,
          by: str = '', direct: str = '') -> List[Splash]:
    """Detonate at ``point``; hurt and shove everybody who can see it.

    ``direct`` is whoever the projectile hit head-on, and is **left out of the
    splash**: the direct damage already says that it hit them squarely, and
    adding the burst on top would make a direct hit two hits with one number
    to tune between them.

    Returns what happened to each, which is what a test reads and what a
    replay would write down; the damage and the shove have already been
    applied to the match.
    """
    radius = float(kind.splashRadius)
    if radius <= 0.0:
        return []
    centre = np.asarray(point, dtype='d')
    done: List[Splash] = []
    for id, chest, distance in _candidates(arena, centre, radius, direct):
        if not raycast.line_of_sight(world, centre, chest):
            continue
        done.append(_caught(arena, kind, id, centre, chest, distance, by))
    return done


def _candidates(arena: Any, centre: np.ndarray, radius: float,
                direct: str) -> List[Any]:
    """Everybody alive, in range, and not the direct hit -- with their chest.

    Distance first and geometry afterwards, because a subtraction is free and
    a ray cast is not: a burst in an eight-player match would otherwise cast
    at all eight however far away they were standing.
    """
    found = []
    for id in arena.ids():
        if id == direct:
            continue
        one = arena.combatant(id)
        if one is None or not one.alive:
            continue
        chest = (np.asarray(one.position, dtype='d')
                 + np.array([0.0, CHEST_HEIGHT, 0.0]))
        distance = float(np.linalg.norm(chest - centre))
        if distance <= radius:
            found.append((id, chest, distance))
    return found


def _caught(arena: Any, kind: Any, id: str, centre: np.ndarray,
            chest: np.ndarray, distance: float, by: str) -> Splash:
    """One combatant's share of a burst, applied.

    **``selfDamage`` scales the damage and never the shove.**  The push *is*
    the rocket jump; the reduced damage is what makes taking one a decision
    rather than free movement.  Scaling both would leave a shooter's own rocket
    lifting them less than a plain jump does, which is not a rocket jump at
    all.
    """
    share = falloff(distance, float(kind.splashRadius),
                    float(kind.splashFalloff))
    hurt = share * (float(kind.selfDamage) if id == by else 1.0)
    taken = arena.damage(id, float(kind.splashDamage) * hurt, by=by,
                         point=centre)
    push = _away(centre, chest) * float(kind.knockback) * share
    arena.shove(id, push)
    return Splash(target=id, damage=taken, push=push, distance=distance)


def _away(centre: np.ndarray, chest: np.ndarray) -> np.ndarray:
    """A unit direction from a burst to somebody, or straight up.

    Straight up is the answer when the two are in the same place, which is
    exactly the rocket-at-your-own-feet case: any horizontal direction there
    would be arbitrary, and up is the one that is the move.
    """
    away = chest - centre
    length = float(np.linalg.norm(away))
    if length < 1e-9:
        return STRAIGHT_UP.copy()
    return away / length


def answer(world: Any, arena: Any, table: Any,
           detonations: Sequence[Any]) -> List[Splash]:
    """Burst for each of ``detonations``; returns everything they did.

    The seam between a projectile's flight and its consequences.  They are
    apart because they are two questions — *where did it go* and *what did
    that cost* — and because keeping them apart is what lets a burst be tested
    at a known distance through a known wall without anything having to fly.

    A detonation naming a kind this table does not have is skipped rather than
    raising: a variant that retunes the loadout mid-match should cost a bang,
    not a frame.
    """
    done: List[Splash] = []
    for gone in detonations:
        kind = table.by_key(gone.kind)
        if kind is None:
            log.warning('nothing in the table is a %r; its burst is skipped',
                        gone.kind)
            continue
        done.extend(burst(world, arena, gone.point, kind, by=gone.by,
                          direct=gone.target))
    return done


def spend(arena: Any, id: str) -> Optional[np.ndarray]:
    """Take somebody's unspent shove, or None if there is not one.

    None rather than a zero vector so a caller can tell "nothing happened"
    from "pushed by nothing", and so applying an impulse of zero to a
    character controller — which would cancel a jump already in progress —
    never happens by accident.
    """
    push = arena.spend_push(id)
    if float(np.linalg.norm(push)) < 1e-9:
        return None
    return push
