"""What a map leaves lying about for players to pick up.

A level is not a room with people shooting in it: it is a *circuit*, and the
things placed around that circuit are what give it a shape. Health where the
fighting is thickest, armour behind a jump you have to commit to, a rocket
launcher somewhere everybody has to walk past — that is the level design, and
it is by far the most numerous thing a map author places. Every one of the 67
sample maps places at least one, 3561 in all, an average of 53 a map
(``SPEC-Q3ENTITIES §3.1``). Without them a match is a fixed loadout spent once,
and then a player with nothing to shoot with.

**Two tables, and the join between them is data.** A map names things by
classname — ``item_health``, ``weapon_rocketlauncher``, ``ammo_shells`` — and
those names belong to a game this is not. :class:`ItemKind` says what one of
them is *worth here*, in this game's own units, and :class:`ItemTable` holds
the mapping. A classname nobody has declared is content this does not have
(``SPEC-Q3ENTITIES §3.2.4``: the names are not a closed set and eleven of the
46 appear in one map each), and is skipped rather than being an error.

**Nothing here draws or reads a clock.** :meth:`Pickups.advance` takes the
seconds that have passed, exactly as the liquids and the match do, so a whole
circuit of a level can be played out in a test.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np
from vrml import field as vfield, node

from . import avatar
from .worldgeometry import to_scene_points

log = logging.getLogger(__name__)

__all__ = ['ItemKind', 'ItemTable', 'Pickup', 'Pickups', 'Taken', 'MEDPACK',
           'LAUNCHER_PICKUP', 'ROCKET_PICKUP', 'default_table', 'from_entities']

#: The classname prefixes that mean "this is probably something to pick up"
#: (``SPEC-Q3ENTITIES §3.2.1``).  Used only to tell an *unrecognised pickup*
#: from an entity of some other kind entirely, so that the first is worth
#: reporting and the second is not.
PREFIXES = ('item_', 'weapon_', 'ammo_', 'holdable_')

#: How near a body's axis has to pass for it to be collected, in metres.
#: **Ours**: ``SPEC-Q3ENTITIES §3.3.2`` records that the content does not
#: establish what an item's origin marks, so this game decides — the origin is
#: the middle of the thing, and walking your body through it takes it.  Wider
#: than the body's own radius, because a pickup you have to stand exactly on
#: is a pickup you run past.
REACH = avatar.RADIUS + 0.5

#: How far above and below the *body* an item may be and still be reached, in
#: metres.  The same tolerance as across, so the shape asked about is a body
#: with a little room around it: an item on a knee-high plinth is walked into,
#: and one on a balcony is not collected from the floor beneath it.
REACH_HEIGHT = REACH

#: The medikit, and how it is placed: a red cross inside a glass bubble, shared
#: by all four health pickups because they differ only in what they are worth
#: and what colour they are.  ``modelScale`` makes the bubble half a metre
#: across -- a third of a player's height, so it reads across a room without
#: standing in front of the level.  ``modelOffset`` is the model's own middle,
#: in its own units: the art sits on the floor of the scene it was modelled in,
#: and a pickup turns about its middle rather than about the modeller's floor.
MEDPACK = dict(model='items/medpack.glb', modelScale=0.5,
               modelOffset=(0.0, -1.0, 0.0))

#: The rocket launcher and its ammunition, each modelled as the thing itself
#: floating in a soap bubble the same size as the medikit's.  ``tinted`` is off
#: because these say which pickup they are by their *shape*: painting a
#: launcher flat red would throw away the only reason to model one.  Their
#: middles are already their origins, so unlike the medikit they need no
#: offset.  The bubbles are the same mesh in both files, which is what lets
#: every one on screen collapse into a single instanced draw.
LAUNCHER_PICKUP = dict(model='items/javelin-launcher-pickup.glb',
                       modelScale=0.5, tinted=False)
ROCKET_PICKUP = dict(model='items/javelin-rocket-pickup.glb',
                     modelScale=0.5, tinted=False)

#: The rest of the arsenal, on the same terms.  Each weapon's two pickups share
#: a bubble colour, so a player learns one colour per weapon rather than one
#: per pickup: green is the shotgun, cyan the grenade launcher, lime the
#: sniper, orange the handgun, red the rocket launcher.
def _pickup(name):
    return dict(model='items/%s.glb' % (name,), modelScale=0.5, tinted=False)


SHOTGUN_PICKUP = _pickup('sawn-off-shotgun-pickup')
SHELL_PICKUP = _pickup('shotgun-shell-pickup')
GRENADE_LAUNCHER_PICKUP = _pickup('grenade-launcher-pickup')
GRENADE_ROUND_PICKUP = _pickup('grenade-round-pickup')
SNIPER_PICKUP = _pickup('sniper-rifle-pickup')
SNIPER_ROUND_PICKUP = _pickup('sniper-round-pickup')
HANDGUN_PICKUP = _pickup('handgun-pickup')
CARTRIDGE_PICKUP = _pickup('handgun-cartridge-pickup')

#: Armour, in gold: a shard is one plate of the stuff and a suit is two on a
#: pair of straps, so the pair are told apart by *how much of it there is*,
#: which is what they are worth.
ARMOUR_SHARD_PICKUP = _pickup('armour-shard-pickup')
ARMOUR_PICKUP = _pickup('armour-pickup')
#: The same carrier with a pauldron over each shoulder: a hundred armour is
#: fifty's shape with more of it on, so the two are read against each other
#: rather than learnt separately.
BODY_ARMOUR_PICKUP = _pickup('body-armour-pickup')

#: Seconds before a taken item comes back, when the entity does not say.
#: ``SPEC-Q3ENTITIES §3.5.1`` observes ``wait`` clustering hard at 10 seconds
#: across the 133 entities that carry one, and §3.5.4 that the other 3428 must
#: therefore have an interval of their own; this is it.
RESPAWN = 10.0


class ItemKind(node.Node):
    """One kind of pickup, as data: what it gives and how long until it returns.

    Several of the fields may be set at once, and that is how a weapon pickup
    arrives with ammunition in it — which is what the content expects and what
    makes picking one up worth the walk.  Nothing here branches on a *type*
    field: an item gives whatever its numbers say, and a zero gives nothing.

    Amounts are in this game's own units.  The classnames are somebody else's
    and are the join to the map.
    """

    PROTO = 'ItemKind'

    #: How this game names it, and what the HUD says when one is taken.
    key = vfield.newField('key', 'SFString', 1, '')
    title = vfield.newField('title', 'SFString', 1, '')
    #: The map classnames that mean this (``SPEC-Q3ENTITIES §3.2``).  Several,
    #: because different content spells the same idea differently and because
    #: a weapon this game does not have is still best answered by the nearest
    #: one it does.
    classnames = vfield.newField('classnames', 'MFString', 1, list)

    #: Health restored, never past the maximum.
    health = vfield.newField('health', 'SFInt32', 1, 0)
    #: Armour given, never past the maximum.
    armour = vfield.newField('armour', 'SFInt32', 1, 0)
    #: Ammunition given, and which pool it goes into -- the same names
    #: :class:`~twig_bb.weapons.Weapon`'s ``ammoType`` uses.
    ammo = vfield.newField('ammo', 'SFInt32', 1, 0)
    ammoType = vfield.newField('ammoType', 'SFString', 1, '')
    #: A weapon added to what the player holds, by key.
    weapon = vfield.newField('weapon', 'SFString', 1, '')

    #: Seconds before one that has been taken comes back
    #: (``SPEC-Q3ENTITIES §3.5``).  Overridden per entity by ``wait``.
    respawn = vfield.newField('respawn', 'SFFloat', 1, RESPAWN)

    #: What colour it is, and therefore *which* pickup it is at fifty metres.
    #: The kinds that share a model are told apart by this and nothing else, so
    #: it is the design and not a decoration -- see :func:`default_table`.  A
    #: kind with no model is drawn as a box in it.
    colour = vfield.newField('colour', 'SFColor', 1, (1.0, 1.0, 1.0))

    #: Whether the model is painted in :attr:`colour`, or arrived with colours
    #: of its own worth keeping.  The four medikits are one model painted four
    #: ways and *must* be tinted -- the colour is the whole of what tells them
    #: apart.  A pickup modelled as the thing it gives says which it is by its
    #: shape instead, and painting that one flat colour would throw away the
    #: shape it was modelled for.  Either way it is lit from within, because a
    #: map places no dynamic lights.
    tinted = vfield.newField('tinted', 'SFBool', 1, True)

    #: The model, relative to :data:`twig_bb.art.ASSETS`, and how to place
    #: it.  Empty for a kind whose art has not been made yet, which is drawn as
    #: a coloured box instead.
    model = vfield.newField('model', 'SFString', 1, '')
    #: What one of the model's own units is worth in metres.
    modelScale = vfield.newField('modelScale', 'SFFloat', 1, 1.0)
    #: Where the middle of the thing is *in the model*, in the model's own
    #: units, so that a pickup turns about its middle and sits where the map
    #: put it.  In the model's units rather than in metres because then
    #: retuning ``modelScale`` does not invalidate it: art is authored with its
    #: origin wherever the modeller was standing, and the two facts -- how big
    #: it is and where its middle is -- are independent.
    modelOffset = vfield.newField('modelOffset', 'SFVec3f', 1, (0.0, 0.0, 0.0))

    UI_HINTS = {
        'key': {'skip': True},
        'classnames': {'skip': True},
        'model': {'skip': True},
        'modelScale': {'skip': True},
        'modelOffset': {'skip': True},
        'title': {'label': 'Shown as'},
        'health': {'label': 'Health', 'minimum': 0, 'maximum': 200},
        'armour': {'label': 'Armour', 'minimum': 0, 'maximum': 200},
        'ammo': {'label': 'Ammunition', 'minimum': 0, 'maximum': 500},
        'respawn': {'label': 'Comes back after (s)', 'minimum': 0.0,
                    'maximum': 120.0, 'step': 1.0},
    }

    def give_to(self, player: Any) -> bool:
        """Hand this to somebody; False if they could not use any of it.

        False matters: an item nobody can use must stay on the floor, or a
        player at full health walking over a medikit destroys it for everyone
        and gets nothing.  Health and armour are refused when full, a weapon
        is still worth taking for the ammunition inside it, and a pool that is
        already at the carrying limit refuses like the rest.
        """
        took = False
        if int(self.health) > 0 and player.health < player.max_health:
            player.heal(int(self.health))
            took = True
        if int(self.armour) > 0 and player.armour < player.max_armour:
            player.give_armour(int(self.armour))
            took = True
        if str(self.weapon) and player.give(str(self.weapon)):
            took = True
        if int(self.ammo) > 0 and str(self.ammoType):
            kind = str(self.ammoType)
            if player.ammo.get(kind, 0) < player.AMMO_MAXIMUM:
                player.give_ammo(kind, int(self.ammo))
                took = True
        return took


class ItemTable(node.Node):
    """Every kind of pickup this game knows about, and the names it answers to."""

    PROTO = 'ItemTable'
    kinds = vfield.newField('kinds', 'MFNode', 1, list)

    def for_classname(self, classname: str) -> Optional[ItemKind]:
        """The kind a map's classname means, or None for content we lack."""
        wanted = str(classname).strip().lower()
        for kind in self.kinds:
            if wanted in [str(name).lower() for name in kind.classnames]:
                return kind
        return None

    def by_key(self, key: str) -> Optional[ItemKind]:
        for kind in self.kinds:
            if str(kind.key) == key:
                return kind
        return None


def default_table() -> ItemTable:
    """What each of the content's pickups is worth in this game.

    The amounts are **ours** and are the design: a shard is a scrap you take
    in passing, a body armour is worth crossing the level for, and a weapon
    arrives with enough ammunition to be worth having immediately.

    The classname lists are where a game this is not meets this one.  Several
    of that game's weapons have no counterpart here, and each is answered by
    the nearest thing that does — a railgun and a lightning gun are both
    hitscan and become the rifle — because a level whose weapon pickups did
    nothing would have most of its circuit missing.  Where there is no honest
    counterpart at all (the timed powerups: quad, haste, invisibility) nothing
    is declared, and ``SPEC-Q3ENTITIES §3.2.4``'s rule applies: it is content
    this game does not have.

    **The four health pickups are one model in four colours, and the colours
    are load-bearing.**  A player has to know which one is across the room
    *before* deciding to cross to it, and at that range a shape is a smudge
    while a hue is unmistakable -- so they are four hues far apart rather than
    four brightnesses of one, which is what the placeholder boxes were and
    which read as a single item at any real distance.  Red is the middling one
    rather than the best one, because a red cross means "health" to anybody who
    has ever seen one, and that meaning is worth more spent on the pickup a map
    places most: white is the scrap, blue the serious one, gold the
    hundred-point prize.  A fifth would be a colour and a row.

    A function rather than a constant, because every field is writable and one
    match's tuning must not become every match's.
    """
    return ItemTable(kinds=[
        ItemKind(key='health-small', title='HEALTH', health=5,
                 classnames=['item_health_small'], respawn=15.0,
                 colour=(0.92, 0.94, 0.96), **MEDPACK),
        ItemKind(key='health', title='HEALTH', health=25,
                 classnames=['item_health'], respawn=15.0,
                 colour=(0.85, 0.18, 0.14), **MEDPACK),
        ItemKind(key='health-large', title='HEALTH', health=50,
                 classnames=['item_health_large'], respawn=25.0,
                 colour=(0.20, 0.55, 0.95), **MEDPACK),
        ItemKind(key='health-mega', title='MEGA HEALTH', health=100,
                 classnames=['item_health_mega'], respawn=35.0,
                 colour=(1.00, 0.78, 0.18), **MEDPACK),
        ItemKind(key='armour-shard', title='ARMOUR', armour=5,
                 **ARMOUR_SHARD_PICKUP,
                 classnames=['item_armor_shard'], respawn=15.0,
                 colour=(0.9, 0.85, 0.3)),
        ItemKind(key='armour', title='ARMOUR', armour=50,
                 **ARMOUR_PICKUP,
                 classnames=['item_armor_combat'], respawn=25.0,
                 colour=(0.95, 0.8, 0.2)),
        ItemKind(key='armour-body', title='BODY ARMOUR', armour=100,
                 **BODY_ARMOUR_PICKUP,
                 classnames=['item_armor_body'], respawn=35.0,
                 colour=(1.0, 0.7, 0.1)),

        ItemKind(key='bullets', title='BULLETS', ammo=30, ammoType='bullets',
                 classnames=['ammo_bullets', 'ammo_belt', 'ammo_chaingun'],
                 colour=(0.75, 0.7, 0.6), **CARTRIDGE_PICKUP),
        ItemKind(key='shells', title='SHELLS', ammo=10, ammoType='shells',
                 classnames=['ammo_shells'], colour=(0.8, 0.5, 0.3),
                 **SHELL_PICKUP),
        # Ten, where the other ammunition kinds hand out thirty and fifty:
        # every one of these is a kill outright, so a box of fifty would be
        # fifty kills lying on the floor.  What holds the rifle in check is
        # how many rounds a level puts in front of you.
        ItemKind(key='cells', title='CELLS', ammo=10, ammoType='cells',
                 classnames=['ammo_cells', 'ammo_lightning', 'ammo_slugs',
                             'ammo_nails', 'ammo_nailgun'],
                 colour=(0.4, 0.7, 1.0), **SNIPER_ROUND_PICKUP),
        ItemKind(key='rockets', title='ROCKETS', ammo=5, ammoType='rockets',
                 classnames=['ammo_rockets', 'ammo_bfg'],
                 colour=(1.0, 0.45, 0.2), **ROCKET_PICKUP),
        ItemKind(key='grenades', title='GRENADES', ammo=5,
                 ammoType='grenades',
                 classnames=['ammo_grenades', 'ammo_mines', 'ammo_proxmine'],
                 colour=(0.6, 0.8, 0.35), **GRENADE_ROUND_PICKUP),

        # Each arrives with ammunition in it, because a weapon you cannot fire
        # is not a pickup, it is a disappointment.
        ItemKind(key='weapon-shotgun', title='SHOTGUN', weapon='shotgun',
                 ammo=10, ammoType='shells', respawn=20.0,
                 classnames=['weapon_shotgun'], colour=(0.8, 0.5, 0.3),
                 **SHOTGUN_PICKUP),
        ItemKind(key='weapon-rifle', title='RIFLE', weapon='rifle',
                 ammo=5, ammoType='cells', respawn=20.0,
                 classnames=['weapon_railgun', 'weapon_lightning',
                             'weapon_plasmagun', 'weapon_chaingun',
                             'weapon_nailgun'],
                 colour=(0.4, 0.7, 1.0), **SNIPER_PICKUP),
        ItemKind(key='weapon-rocket', title='ROCKET LAUNCHER',
                 weapon='rocket', ammo=5, ammoType='rockets', respawn=25.0,
                 classnames=['weapon_rocketlauncher', 'weapon_bfg'],
                 colour=(1.0, 0.45, 0.2), **LAUNCHER_PICKUP),
        ItemKind(key='weapon-grenade', title='GRENADES', weapon='grenade',
                 ammo=5, ammoType='grenades', respawn=20.0,
                 classnames=['weapon_grenadelauncher',
                             'weapon_prox_launcher', 'weapon_proxmine'],
                 colour=(0.6, 0.8, 0.35), **GRENADE_LAUNCHER_PICKUP),
        # The handgun a player starts with is still worth placing: a map that
        # offers one is offering ammunition and a second chance, and the
        # classname is the one Quake III uses for its own starting weapon.
        ItemKind(key='weapon-pistol', title='PISTOL', weapon='pistol',
                 ammo=30, ammoType='bullets', respawn=20.0,
                 classnames=['weapon_machinegun'], colour=(0.75, 0.7, 0.6),
                 **HANDGUN_PICKUP),
    ])


@dataclass
class Pickup:
    """One thing a map placed, and whether it is there to be taken.

    ``waiting`` is the seconds left before it comes back, and ``None`` means
    it is on the floor now — the state a match starts in and the one it is in
    most of the time, so it is the one that reads as "nothing has happened".
    """

    kind: ItemKind
    #: Where it is, in scene metres.  The **middle** of the thing; see
    #: :data:`REACH`.
    position: np.ndarray
    #: Seconds before it returns once taken, from the entity or its kind.
    respawn: float = RESPAWN
    waiting: Optional[float] = None

    @property
    def available(self) -> bool:
        return self.waiting is None


@dataclass
class Taken:
    """One pickup collected: who took what, and where it was."""

    by: str
    key: str
    title: str
    point: np.ndarray = field(default_factory=lambda: np.zeros(3))


def from_entities(entities: Iterable[Any],
                  table: Optional[ItemTable] = None) -> List[Pickup]:
    """Every pickup a map places that this game has something to give for.

    An entity whose classname nothing declares is skipped and *counted* rather
    than being an error (``SPEC-Q3ENTITIES §3.2.4``); see
    :func:`unknown_classnames` for reporting them, which matters because a
    silent skip and a broken reader look identical from inside the game.

    ``wait`` overrides the kind's own respawn interval where the entity
    carries one (``SPEC-Q3ENTITIES §3.5``).
    """
    known = table if table is not None else default_table()
    found: List[Pickup] = []
    for entity in entities:
        kind = known.for_classname(entity.classname)
        if kind is None:
            continue
        where = to_scene_points(np.array([entity.vector('origin')],
                                         dtype='f'))[0]
        found.append(Pickup(kind=kind, position=np.asarray(where, dtype='d'),
                            respawn=entity.number('wait', 0.0)
                            or float(kind.respawn)))
    return found


def unknown_classnames(entities: Iterable[Any],
                       table: Optional[ItemTable] = None) -> Dict[str, int]:
    """Pickup classnames this game has nothing for, and how many of each.

    Reported because the alternative is silence: a map whose weapons are all
    ones this game does not answer to plays as a map with no weapons in it,
    and nothing distinguishes that from a reader that failed.
    """
    known = table if table is not None else default_table()
    missing: Dict[str, int] = {}
    for entity in entities:
        name = entity.classname
        if name.startswith(PREFIXES) and known.for_classname(name) is None:
            missing[name] = missing.get(name, 0) + 1
    return missing


class Pickups:
    """Every item in a level, and who is walking through them.

    Ticked with the match, like the liquids are.  It reads positions and
    writes to players, holds no scenegraph and reads no clock.
    """

    def __init__(self, items: Sequence[Pickup]) -> None:
        self.items: List[Pickup] = list(items)

    def __len__(self) -> int:
        return len(self.items)

    def available(self) -> List[Pickup]:
        """The ones on the floor right now."""
        return [item for item in self.items if item.available]

    def advance(self, arena: Any, dt: float,
                table: Any = None) -> List[Taken]:
        """Bring items back, hand out the ones walked into; returns what was taken.

        The order matters: an item whose wait ends this tick is available to
        somebody standing on it this tick, which is what makes camping an item
        respawn a *decision* rather than a lottery about frame boundaries.

        ``table`` is the weapon table, and it is what decides whether a weapon
        walked over goes into the hand as well as onto the bar -- see
        :meth:`~twig_bb.player.PlayerState.prefer`.  Optional because the
        ordering is the only thing it is wanted for: without one a weapon is
        still collected, it simply does not take the hand.
        """
        step = max(0.0, float(dt))
        for item in self.items:
            if item.waiting is not None:
                item.waiting -= step
                if item.waiting <= 0.0:
                    item.waiting = None
        return self._collect(arena, table)

    def _collect(self, arena: Any, table: Any = None) -> List[Taken]:
        """Hand each available item to the first living body standing in it."""
        took: List[Taken] = []
        standing = [(id, np.asarray(one.position, dtype='d'))
                    for id, one in ((id, arena.combatant(id))
                                    for id in arena.ids())
                    if one is not None and one.alive]
        if not standing:
            return took
        for item in self.items:
            if not item.available:
                continue
            for id, feet in standing:
                if not _reaches(feet, item.position):
                    continue
                one = arena.combatant(id)
                if one is None:
                    continue
                # Asked before it is handed over: a weapon already held is a
                # pickup for its ammunition and must not disturb the hand.
                wanted = str(item.kind.weapon)
                fresh = bool(wanted) and not one.player.has(wanted)
                if not item.kind.give_to(one.player):
                    # Nothing they could use: it stays on the floor, or a
                    # player at full health destroys a medikit for everybody.
                    continue
                if fresh:
                    one.player.prefer(table, wanted)
                item.waiting = max(0.0, float(item.respawn))
                took.append(Taken(by=id, key=str(item.kind.key),
                                  title=str(item.kind.title),
                                  point=item.position.copy()))
                arena.picked_up(id, key=str(item.kind.key),
                                title=str(item.kind.title),
                                point=item.position)
                break
        return took

    def describe(self) -> Dict[str, Any]:
        """What this is holding, as rows for the developer overlay."""
        return {'items': len(self.items),
                'items waiting': sum(1 for one in self.items
                                     if not one.available)}


def _reaches(feet: np.ndarray, item: np.ndarray) -> bool:
    """Whether a body standing at ``feet`` is touching an item at ``item``.

    The body's own upright span against a cylinder about the item, which is the
    same shape of test the liquids use: a radius across, and from a little
    below the feet to a little above the head.  A body rather than a point at
    either end -- an item is taken by walking into it at any height a person
    occupies, and an item on a balcony is not collected from the floor beneath
    it.
    """
    across = feet[[0, 2]] - item[[0, 2]]
    if float(np.dot(across, across)) > REACH * REACH:
        return False
    above = float(item[1]) - float(feet[1])
    return -REACH_HEIGHT <= above <= avatar.HEIGHT + REACH_HEIGHT
