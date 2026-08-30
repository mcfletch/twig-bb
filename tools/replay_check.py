#! /usr/bin/env python
"""Play a scripted match, record it, run the recording again, and compare.

A session recording is worth what it can be *run again*
(:mod:`OpenGLContext.telemetry`), and the only honest way to know whether this
game replays is to record one and replay it.  That is what this does, without a
person at the keyboard: it plays a fixed few seconds -- walking, turning,
changing weapons, firing -- with a real window and a real map, records the
session, then hands the journal back to an ordinary ``python -m twig_bb`` and
asks the engine how the two accounts compared.

The comparison is the game's own marks (:mod:`twig_bb.telemetry`): what it said
happened while it was recorded, against what it says happened while it is
replayed, mark for mark and frame for frame.  A replay that agrees on every one
of them has fired the same shots at the same people on the same frames.

    tools/replay_check.py ../tmp/q3/ztn3dm1.pk3 --map ztn3dm1 --bots 3

It answers 0 when the replay reproduced the recording and 1 when it did not,
so it can be run from a script.  ``--keep`` leaves the journal where a
``python -m OpenGLContext.telemetry <journal>`` can read it.

The two runs it makes are subprocesses of this one, because a session is a
whole process: one window, one main loop, one recording.  ``--stage record``
and ``--stage replay`` are those children, and are of no use on their own.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence

#: A hidden window that renders and reads back exactly as a mapped one does.
#: A window nothing is showing is never handed a frame callback by a Wayland
#: compositor, and its buffer swap then never returns.
OFFSCREEN = {'OPENGLCONTEXT_HIDDEN': '1', 'OPENGLCONTEXT_NO_VSYNC': '1'}

#: Frames of play to record, once the level is up and the player is walking.
#: Long enough for bots to find the player and for a fight to happen; short
#: enough to be run while waiting.
PLAY_FRAMES = 900

#: What the player does, as ``(frame, kind, argument)`` from the first frame of
#: play.  Keys are held: a key put down here stays down until it is lifted.
SCRIPT: Sequence[Any] = (
    (10, 'key', ('w', 1)),                  # walk
    (40, 'pointer', (60, 0)),               # look right, a little at a time
    (60, 'pointer', (60, 0)),
    (80, 'key', ('w', 0)),
    (90, 'key', ('<control>', 1)),          # fire, held
    (140, 'key', ('<control>', 0)),
    (150, 'key', ('2', 1)),                 # a different weapon
    (152, 'key', ('2', 0)),
    (160, 'key', ('<control>', 1)),
    (220, 'key', ('<control>', 0)),
    (230, 'key', ('d', 1)),                 # strafe, still turning
    (260, 'pointer', (-90, 0)),
    (300, 'key', ('d', 0)),
    (310, 'key', ('<space>', 1)),           # jump
    (315, 'key', ('<space>', 0)),
    (330, 'key', ('w', 1)),
    (360, 'key', ('3', 1)),
    (362, 'key', ('3', 0)),
    (380, 'key', ('<control>', 1)),
    (520, 'key', ('<control>', 0)),
    (560, 'pointer', (120, 0)),
    (600, 'key', ('w', 0)),
    (620, 'key', ('<control>', 1)),         # keep shooting to the end
    (860, 'key', ('<control>', 0)),
)


# -- the child that plays ----------------------------------------------------

def play(argv: List[str], scripted: bool = True) -> None:
    """Run the game, with the script above driving it when it is the recording.

    The **replayed** run takes no script at all: its input is the journal, and
    a game given both would be given every key twice.
    """
    from OpenGLContext.events import synthetic

    from twig_bb import viewer

    class Scripted(viewer.TwigContext):
        """The game, with the script delivered as the platform would deliver it.

        Through ``ProcessEvent`` and ``recordPointerMotion``, which is where a
        backend puts input and where a recording taps it -- so the journal this
        writes is one an ordinary session could have written, and the replay
        that reads it is driving an ordinary game.
        """

        #: Frames of play so far.  Counted from the frame the level was
        #: mounted on, so the script is about the match rather than about how
        #: long the map took to read.
        _played = 0
        _pointer = (0, 0)

        def OnIdle(self, *arguments: Any) -> int:
            self._playScript()
            return super(Scripted, self).OnIdle(*arguments)

        def _playScript(self) -> None:
            if not scripted or self.loaded is None or not self._walking:
                return
            frame = self._played
            self._played += 1
            for at, kind, argument in SCRIPT:
                if at != frame:
                    continue
                if kind == 'key':
                    name, state = argument
                    synthetic.dispatch(self, {'type': 'keyboard', 'key': name,
                                              'state': state})
                else:
                    x, y = self._pointer
                    self._pointer = (x + argument[0], y + argument[1])
                    synthetic.dispatch(self, {'type': 'pointer',
                                              'x': self._pointer[0],
                                              'y': self._pointer[1]})
            if self._played > PLAY_FRAMES:
                self.OnQuit()

        def OnDraw(self, *arguments: Any, **named: Any) -> Any:
            drawn = super(Scripted, self).OnDraw(*arguments, **named)
            # A replay is given no script and so has nothing to end it: the
            # session it is replaying ended because the script said so, and
            # that is not an input the journal can hold.  So it ends where the
            # recording ended.
            if not scripted and self.telemetry is not None:
                replay = getattr(self.telemetry, 'replay', None)
                if replay is not None and replay.finished:
                    self.OnQuit()
            return drawn

    options = viewer.build_parser().parse_args(argv)
    viewer.apply_render_env(options)
    Scripted.config = options
    Scripted._target = options.target
    Scripted.ContextMainLoop(definition=viewer.context_definition(
        fullscreen=viewer.wants_fullscreen(options)))


# -- the two runs ------------------------------------------------------------

def run(stage: str, game: List[str], environment: Dict[str, str],
        verbose: bool = False) -> str:
    """Run one stage as a child process and answer everything it said.

    Read a line at a time rather than waited for, so ``--verbose`` shows a run
    that takes a couple of minutes doing something rather than nothing.
    """
    settings = dict(os.environ)
    settings.update(OFFSCREEN)
    settings.update(environment)
    child = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__), '--stage', stage] + game,
        env=settings, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True)
    said: List[str] = []
    assert child.stdout is not None
    for line in child.stdout:
        said.append(line)
        if verbose:
            sys.stdout.write(line)
            sys.stdout.flush()
    if child.wait() not in (0, None):
        if not verbose:
            sys.stdout.write(''.join(said))
        raise SystemExit('the %s run failed (%d)' % (stage, child.returncode))
    return ''.join(said)


#: What the engine logs as a replay ends; see
#: :class:`OpenGLContext.telemetry.replay.MarkComparison`.
VERDICT = re.compile(r'replay of [^:]+: (.+)$', re.MULTILINE)


def verdict_of(output: str) -> Optional[str]:
    """The line the engine logged about how the replay compared, if it did."""
    found = VERDICT.search(output)
    return found.group(1).strip() if found is not None else None


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog='replay_check.py',
        description=__doc__.split('    tools/')[0].strip(),
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--stage', choices=('record', 'replay'), default=None,
                        help=argparse.SUPPRESS)
    parser.add_argument('--journal', default=None,
                        help='where to write the recording')
    parser.add_argument('--keep', action='store_true',
                        help='leave the journal behind to be read')
    parser.add_argument('--seed', default=None,
                        help='fix the session seed of the recorded run')
    parser.add_argument('--verbose', action='store_true',
                        help='pass both runs\' output through as it arrives')
    known, game = parser.parse_known_args(argv)

    if known.stage is not None:
        play(game, scripted=known.stage == 'record')
        return 0

    journal = known.journal or os.path.join(tempfile.gettempdir(),
                                            'twig-bb-replay-check.jsonl')
    recording = {'OPENGLCONTEXT_TELEMETRY': journal}
    if known.seed:
        recording['OPENGLCONTEXT_SEED'] = known.seed
    sys.stdout.write('recording a scripted match to %s\n' % (journal,))
    sys.stdout.flush()
    run('record', game, recording, known.verbose)
    sys.stdout.write('replaying it\n')
    sys.stdout.flush()
    # No seed here: the journal holds the one the recording ran from and the
    # replay puts it back, while one in the environment would outrank it.
    played = run('replay', game, {'OPENGLCONTEXT_TELEMETRY_REPLAY': journal},
                 known.verbose)
    verdict = verdict_of(played)
    if not known.keep:
        try:
            os.unlink(journal)
        except OSError:
            pass
    if verdict is None:
        sys.stdout.write('the replay said nothing about how it compared\n')
        return 1
    sys.stdout.write('%s\n' % (verdict,))
    return 0 if 'all as recorded' in verdict or verdict.endswith(
        'as recorded') else 1


if __name__ == '__main__':
    raise SystemExit(main())
