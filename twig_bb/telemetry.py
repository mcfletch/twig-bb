"""What this game tells a session recording about itself.

:mod:`OpenGLContext.telemetry` records a whole session to one file: every input
the platform delivered, every frame's time, every exception, and the developer
overlay's own description of the game sampled every few seconds.  What it cannot
know is what any of that *meant* -- that a level finished loading, that the
player took the launcher, that a bot had been watching them for four seconds
before it fired.  Those are marks, and this is where the game makes them.

A mark is the line somebody looks for first when a journal is four minutes long
and the failure is at the end of it::

    0:03.204  frame  190  level-loaded map=ztn3dm1 pickups=37 triangles=51345
    2:41.067  frame 9640  bot-target bot=bot1 target=player
    2:41.910  frame 9691  fired by=bot1 weapon=rocket at=[-704.0, -832.0, 430.0]
    2:42.004  frame 9697  damaged target=player by=bot1 amount=63
    2:42.004  frame 9697  death target=player by=bot1

**The stream is the source.**  Everything a match does already reaches
:mod:`twig_bb.feedback` as events, so marking reads that same stream rather than
being called from inside the rules: a mark and the thing the player saw are then
two readings of one account, and neither can drift from the other.
:class:`GameMarks` is the second reader of it.

**A mark is made unconditionally.**  The guard that asks whether anything is
recording lives here, once, so no call site has to carry one -- a mark behind an
``if``                  is a mark somebody eventually guards away, and those are exactly the ones
that would have explained the failure nobody could reproduce.  With nothing
recording, a call costs an attribute read.

The marks this game makes:

======================  =====================================================
``level-loading``       a map is being read, with seconds to go before it is
``level-loaded``        the map is up: what it is and what is in it
``level-failed``        it would not load, and why
``match-started``       who is in it and what ends it
``weapon-selected``     the player changed weapons, by hand or by running dry
``weapon-empty``        the trigger was pulled on an empty weapon
``weapon-refused``      a weapon was asked for that the player is not carrying
``fired``               somebody shot, wherever it went
``hit``                 a shot landed on somebody
``damaged``             what it cost them, or what the map cost them
``detonated``           a projectile went off
``death``               somebody ran out of health
``pickup``              somebody collected something
``respawn-asked``       the player asked to come back
``spawned``             somebody came back, and where
``bot-target``          a bot found somebody to fight
``bot-lost``            and lost them again
``match-over``          the match reached its limit
``walking``             the player changed how they move
``movement-mode``       and how the camera is steered
``screen``              a screen went up over the game
``download-started``    content the player consented to is being fetched
``download-finished``   and how that went
======================  =====================================================

Replaying a recorded session (``OPENGLCONTEXT_TELEMETRY_REPLAY``) makes these
same marks again and the engine compares them, mark for mark and frame for
frame, with the ones in the journal -- so the marks are also how the session
says whether it played out the same way the second time.  See
:class:`OpenGLContext.telemetry.replay.MarkComparison`.
"""

from __future__ import annotations

import logging
from typing import (Any, Callable, Dict, List, Mapping, Optional, Sequence,
                    Set, Tuple)

from . import arena as arenamod

log = logging.getLogger(__name__)

__all__ = ['GameMarks', 'PLACES']

#: Decimal places a position is marked to.  Scene units are metres, so this is
#: a millimetre: fine enough that two runs of one session are being compared on
#: where somebody was rather than on the last bit of a float, coarse enough that
#: a journal is not mostly digits.
PLACES = 3


class GameMarks:
    """The game's own account of a session, as marks on the recording.

    session -- the context this game runs in: anything with ``mark(name,
        **fields)`` and a ``telemetry`` attribute that is None when no session
        is being recorded or replayed (see
        :meth:`OpenGLContext.context.Context.mark`).

    One per context, kept for the whole run: it remembers what each bot was
    doing so that a bot fighting the same person for ten seconds is one mark
    rather than six hundred.
    """

    def __init__(self, session: Any) -> None:
        self.session = session
        #: Who each bot was last seen fighting, so only the changes are marked.
        self._fighting: Dict[str, str] = {}
        #: Who is waiting to come back and has already said so; see
        #: :meth:`asked_to_respawn`.
        self._asking: Set[str] = set()

    @property
    def listening(self) -> bool:
        """Whether anything is recording or replaying this session."""
        return getattr(self.session, 'telemetry', None) is not None

    def mark(self, name: str, /, **fields: Any) -> None:
        """Make one mark, if there is a session to make it on.

        The name is positional, so a field may be called ``name`` -- which is
        what this game calls a map, a weapon and a player.
        """
        if self.listening:
            self.session.mark(name, **fields)

    # -- the level --------------------------------------------------------
    def loading(self, target: str) -> None:
        """A map is being read.

        Before it arrives rather than after: a big level is seconds of work on
        a worker thread, and a session that died in them is one whose last line
        should say which map it was reading.
        """
        self.mark('level-loading', target=str(target))

    def loaded(self, loaded: Any, arena: Any = None, title: str = '') -> None:
        """The map is up, and a match is being played in it.

        Two marks, because they are two facts: which level this is, and who is
        in it.  A match restarted on the same map makes the second again.
        ``title`` is what the level calls itself, which a map carries in its
        own notice rather than in its geometry (:mod:`twig_bb.mapnotice`).
        """
        self._fighting.clear()
        self._asking.clear()
        if loaded is not None:
            found = _level(loaded)
            if title:
                found['title'] = str(title)
            self.mark('level-loaded', **found)
        if arena is not None:
            self.mark('match-started', bots=len(arena.bots()),
                      combatants=len(arena.ids()),
                      **{'frag limit': int(arena.fragLimit),
                         'minutes': float(arena.timeLimit)})

    def failed(self, target: str, error: Optional[BaseException]) -> None:
        """A map would not load.  The session goes on, on the start screen."""
        self.mark('level-failed', target=str(target),
                  error=str(error) if error is not None else '',
                  type=type(error).__name__ if error is not None else '')

    # -- what the player asked for ----------------------------------------
    def commands(self, events: Sequence[Any], weapon: str = '') -> None:
        """This frame's weapon commands, as :mod:`twig_bb.controls` answered them.

        ``weapon`` is what is in hand once they have been applied.  A shot is
        not marked here: it reaches the match's own stream as
        :class:`~twig_bb.arena.Fired`, for the player and for a bot alike, and
        marking the command as well would say it twice.
        """
        if not self.listening:
            return
        for event in events:
            if event.kind == 'select':
                self.mark('weapon-selected', weapon=str(weapon),
                          title=str(event.text))
            elif event.kind == 'empty':
                self.mark('weapon-empty', weapon=str(weapon),
                          said=str(event.text))
            elif event.kind == 'refused':
                self.mark('weapon-refused', said=str(event.text))

    def asked_to_respawn(self, who: str) -> None:
        """Somebody asked to come back from the dead.

        The player's trigger is what ends their death, so a death that went on
        for twenty seconds is either a player who did not pull it or a request
        that was swallowed, and those are different bugs.

        Once per death: the trigger is *held*, so the ask arrives every frame
        until the wait is over, and sixty marks a second saying the same thing
        would bury the one that says it was first made.
        """
        if who in self._asking:
            return
        self._asking.add(who)
        self.mark('respawn-asked', who=str(who))

    def walking(self, walking: bool, mode: str = '') -> None:
        """The player changed how they move: on foot, or a free-flying camera."""
        self.mark('walking', on=bool(walking), mode=str(mode))

    def movement(self, mode: str) -> None:
        """The player chose another way of steering: walk, fly, mouse-look.

        Every input after it means something different, so a session read
        without this looks like a player who suddenly stopped turning.
        """
        self.mark('movement-mode', mode=str(mode))

    def screen(self, name: str) -> None:
        """A screen went up over the game: the start menu, the settings page.

        While one is up the player is not walking and their input is not
        reaching the world, which is otherwise indistinguishable in a journal
        from a session that has stopped responding.
        """
        self.mark('screen', name=str(name))

    def downloading(self, packs: Sequence[Any]) -> None:
        """A content download the player consented to has started."""
        self.mark('download-started',
                  packs=[str(getattr(pack, 'key', pack)) for pack in packs])

    def downloaded(self, job: Any) -> None:
        """That download finished, was cancelled, or would not complete."""
        failed = getattr(job, 'failed', None)
        self.mark('download-finished', roots=len(getattr(job, 'roots', ())),
                  cancelled=bool(getattr(job, 'cancelled', False)),
                  error=str(failed) if failed is not None else '')

    # -- what the match did -----------------------------------------------
    def events(self, events: Sequence[Any]) -> None:
        """One tick of the match's own stream, as marks.

        The single loop the presentation layer reads, read a second time: see
        :mod:`twig_bb.feedback`.
        """
        if not self.listening:
            return
        for event in events:
            describe = _DESCRIBE.get(type(event))
            if describe is None:
                continue
            described = describe(event)
            if described is not None:
                self.session.mark(described[0], **described[1])

    def respawned(self, respawned: Mapping[str, Any]) -> None:
        """Whoever a tick brought back, and the feet it put them on."""
        if not self.listening:
            return
        for who, feet in respawned.items():
            self._asking.discard(who)
            self.session.mark('spawned', who=str(who), at=_place(feet))

    def minds(self, minds: Mapping[str, Any]) -> None:
        """What the opponents are doing, marking only what changed.

        A bot fighting the same person for ten seconds is one mark and not six
        hundred: what a reader is looking for is the moment it saw somebody, and
        a stream that repeats itself every frame buries it.
        """
        if not self.listening:
            return
        for id, mind in minds.items():
            target = str(getattr(mind, 'target', '') or '')
            before = self._fighting.get(id, '')
            if target == before:
                continue
            self._fighting[id] = target
            if target:
                self.session.mark('bot-target', bot=str(id), target=target)
            else:
                self.session.mark('bot-lost', bot=str(id), target=before)


# -- one event, described ----------------------------------------------------

Described = Optional[Tuple[str, Dict[str, Any]]]


def _fired(event: Any) -> Described:
    return ('fired', {'by': event.shooter, 'weapon': event.weapon,
                      'at': _place(event.origin)})


def _impact(event: Any) -> Described:
    """A shot that met somebody.

    A shot that met the level is left out: it is the commonest event in the
    game, it says only that a wall is where the map put it, and a journal it
    filled is one nothing else can be found in.
    """
    if not event.on_somebody:
        return None
    return ('hit', {'by': event.by, 'target': event.target,
                    'weapon': event.weapon})


def _damaged(event: Any) -> Described:
    found = {'target': event.target, 'by': event.by, 'amount': int(event.amount)}
    if event.cause:
        found['cause'] = event.cause
    return ('damaged', found)


def _detonated(event: Any) -> Described:
    return ('detonated', {'kind': event.kind, 'by': event.by,
                          'target': event.target, 'at': _place(event.point)})


def _death(event: Any) -> Described:
    found = {'target': event.target, 'by': event.by}
    if event.cause:
        found['cause'] = event.cause
    return ('death', found)


def _picked_up(event: Any) -> Described:
    return ('pickup', {'target': event.target, 'item': event.key,
                       'at': _place(event.point)})


def _match_over(event: Any) -> Described:
    return ('match-over', {'winner': event.winner, 'reason': event.reason})


#: Which events are worth a mark, and what each says.  A stream carries more
#: than this; what is left out is what a reader can derive from what is here.
_DESCRIBE: Dict[type, Callable[[Any], Described]] = {
    arenamod.Fired: _fired,
    arenamod.Impact: _impact,
    arenamod.Damaged: _damaged,
    arenamod.Detonated: _detonated,
    arenamod.Death: _death,
    arenamod.PickedUp: _picked_up,
    arenamod.MatchOver: _match_over,
}


def _level(loaded: Any) -> Dict[str, Any]:
    """What a map is, in the few numbers a reader wants first."""
    found: Dict[str, Any] = {'map': str(getattr(loaded, 'name', '')),
                             'family': str(getattr(loaded, 'family', ''))}
    for name, what in (('pickups', 'pickups'), ('spawns', 'spawn_points')):
        counter = getattr(loaded, what, None)
        if callable(counter):
            try:
                found[name] = len(counter())
            except Exception:               # noqa: BLE001 - diagnostic only
                log.debug('could not count a level\'s %s', name, exc_info=True)
    world = getattr(loaded, 'world', None)
    triangles = getattr(world, 'triangle_count', None)
    if isinstance(triangles, int):
        found['triangles'] = triangles
    return found


def _place(point: Any) -> List[float]:
    """A position as the few numbers a journal holds for it, or an empty list."""
    if point is None:
        return []
    try:
        return [round(float(value), PLACES) for value in point]
    except (TypeError, ValueError):
        return []
