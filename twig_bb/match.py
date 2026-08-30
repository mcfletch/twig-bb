"""What a match is: the level, the opponents, and the rules that end it.

A declared node with typed fields rather than a bag of arguments, for the same
reason the movement modes and the weapon table are one: a settings screen can
present it knowing nothing about this game, a variant can retune it by setting
fields, and it saves and reads back without a serialiser of its own.

It is also the one record the pieces that do not exist yet all read — §6's bots
take their count and difficulty from here, §7's scoring takes the limits that
end the match — which is why it is worth declaring properly before either of
them is built.

**The difficulty is a name, not a number**, and the range runs from a bot that
walks about and does not shoot to one that times item respawns and denies them.
That range is the axis a bot is built along rather than a multiplier bolted on
at the end, so the presets are declared here where a menu can offer them and a
test can enumerate them.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from vrml import field, node

log = logging.getLogger(__name__)

__all__ = ['DIFFICULTIES', 'Level', 'MatchSetup', 'SETUP_FILE',
           'levels_available', 'recall', 'save', 'setup_path', 'validate']

#: The bot difficulties, easiest first.  Named rather than numbered because a
#: player chooses between *characters* — one that wanders, one that will beat
#: you — and because a number invites the code to branch on it, which is
#: exactly what a difficulty must not be.
DIFFICULTIES = ('near-passive', 'easy', 'medium', 'hard', 'nightmare')

#: Where the last choice is remembered.
SETUP_FILE = 'match.json'


class MatchSetup(node.Node):
    """One match, as chosen from the start screen."""

    PROTO = 'MatchSetup'

    #: The level: ``pack:mapname``, a path, or empty for "ask".
    level = field.newField('level', 'SFString', 1, '')
    #: How many bots to play against.
    bots = field.newField('bots', 'SFInt32', 1, 1)
    #: Which of :data:`DIFFICULTIES` they play at.
    difficulty = field.newField('difficulty', 'SFString', 1, 'medium')
    #: Frags that end the match; 0 for no frag limit.
    fragLimit = field.newField('fragLimit', 'SFInt32', 1, 15)
    #: Minutes that end the match; 0 for no time limit.
    timeLimit = field.newField('timeLimit', 'SFFloat', 1, 10.0)

    UI_HINTS = {
        'level': {'skip': True},        # chosen from a list, not typed
        'bots': {'label': 'Opponents', 'minimum': 0, 'maximum': 15, 'step': 1},
        'difficulty': {'label': 'Difficulty', 'options': DIFFICULTIES,
                       'optionLabels': ('Near-passive', 'Easy', 'Medium',
                                        'Hard', 'Nightmare')},
        'fragLimit': {'label': 'Frag limit', 'minimum': 0, 'maximum': 100,
                      'step': 5},
        'timeLimit': {'label': 'Time limit (min)', 'minimum': 0.0,
                      'maximum': 60.0, 'step': 1.0},
    }


#: The fields that are saved and read back.  Named rather than discovered, so a
#: field added later is a deliberate addition to the file format.
SAVED = ('level', 'bots', 'difficulty', 'fragLimit', 'timeLimit')


def validate(setup: MatchSetup) -> MatchSetup:
    """Check a setup is playable; returns it, or says what is wrong.

    Called where a choice enters the game rather than where it is edited: a
    half-finished setting on a screen is normal, and a match that cannot start
    is not.
    """
    if setup.difficulty not in DIFFICULTIES:
        raise ValueError('%r is not a difficulty; the choices are %s'
                         % (setup.difficulty, ', '.join(DIFFICULTIES)))
    if setup.bots < 0:
        raise ValueError('a match cannot have %d opponents' % (setup.bots,))
    if setup.fragLimit <= 0 and setup.timeLimit <= 0:
        raise ValueError('a match with no frag limit and no time limit never '
                         'ends; set one of them')
    return setup


# -- remembering the last choice ---------------------------------------------

def setup_path(directory: Optional[str] = None) -> str:
    """Where the last choice is kept: a named directory, or the user's own."""
    if directory is None:
        from OpenGLContext.contextconfig import ContextConfigMixin
        directory = ContextConfigMixin.getUserAppDataDirectory()
    return os.path.join(directory, SETUP_FILE)


def save(setup: MatchSetup, path: Optional[str] = None) -> str:
    """Remember this setup; returns where it went.

    **Written whole or not at all.**  ``open(path, 'w')`` truncates before it
    writes, so a save interrupted part-way leaves a file that will not parse —
    and the next launch would silently start with somebody else's defaults.
    """
    if not isinstance(setup, MatchSetup):
        raise TypeError('%r is not a match setup' % (setup,))
    path = path or setup_path()
    stored = {name: getattr(setup, name) for name in SAVED}
    directory = os.path.dirname(path) or '.'
    os.makedirs(directory, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, prefix='.match-',
                                         suffix='.json')
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as target:
            json.dump(stored, target, indent=2, sort_keys=True)
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise
    return path


def recall(path: Optional[str] = None) -> MatchSetup:
    """The last setup saved, or the defaults.

    **Never raises.**  A settings file that will not parse, or that names a
    difficulty a later version stopped declaring, must not be a game that will
    not start: what can be read is used and the rest falls back.
    """
    path = path or setup_path()
    try:
        with open(path, 'r', encoding='utf-8') as source:
            stored = json.load(source)
    except (OSError, ValueError):
        return MatchSetup()
    if not isinstance(stored, dict):
        log.warning('%s does not hold a saved match; using the defaults', path)
        return MatchSetup()
    setup = MatchSetup()
    for name in SAVED:
        if name in stored:
            _restore(setup, name, stored[name], path)
    return setup


def _restore(setup: MatchSetup, name: str, value: Any, path: str) -> None:
    """Put one saved value back, or leave the default in place."""
    if name == 'difficulty' and value not in DIFFICULTIES:
        log.warning('%s remembers the difficulty %r, which is no longer offered',
                    path, value)
        return
    try:
        setattr(setup, name, value)
    except (TypeError, ValueError):
        log.warning('%s: %s is not a usable %s', path, value, name)


# -- what can be played right now --------------------------------------------

#: Where a map's own picture lives inside a content tree, and what it may be
#: called.  A level shot is what tells one arena from another at a glance, and
#: 93 of them ship with the content this project can fetch.
LEVELSHOT_DIR = 'levelshots'

#: The other place a picture lives.  Unvanquished keeps a map's metadata in a
#: directory named after the map, and its picture beside the `.arena` file
#: there rather than in a shared `levelshots/` (``SPEC-UNVASSETS §3.3``); a
#: reader that knows only the shared directory lists those levels blank.  The
#: file is named for the map, which is also the name of the directory holding
#: it, and that is what tells it apart from anything else under `meta/`.
METADATA_DIR = 'meta'

#: `.webp` and `.crn` are here because that is what the pictures actually are:
#: of the three Unvanquished maps this build offers, two ship Crunch and one
#: ships WebP.  Crunch needs :mod:`twig_bb.crnfile`, which
#: :func:`register_picture_decoders` wires into the toolkit's picture cache.
LEVELSHOT_EXTENSIONS = ('.jpg', '.tga', '.png', '.jpeg', '.webp', '.crn')


def register_picture_decoders() -> None:
    """Let the UI's picture cache read the formats this content ships.

    The toolkit decodes through the imaging library, which reads WebP and has
    never heard of Crunch, so a `.crn` level shot would be a blank plate.
    ``OpenGLContext.ui.pictures`` takes a decoder per suffix for exactly this,
    which keeps a game-texture container and its optional dependency here, with
    the content, rather than in the general toolkit.

    Idempotent, and safe to call before a window exists.
    """
    from OpenGLContext.ui import pictures
    from . import crnfile
    pictures.registerDecoder(crnfile.EXTENSION, crnfile.load)


@dataclass(frozen=True)
class Level:
    """One map that can be started without downloading anything."""

    #: The bare map name, as a player reads it.
    name: str
    #: What the loader is handed: ``pack:mapname``.
    target: str
    #: Which pack it came from.
    pack: str
    #: Its own picture, or empty for a map that ships none.  Empty is common
    #: and is not a failure: a chooser shows a plate instead.
    art: str = ''


def levels_available(cache_dir: Optional[str] = None,
                     packs: Optional[Any] = None) -> List[Level]:
    """Every level already on disk, in pack order and then by name.

    Only what is fetched: a chooser that listed levels a player cannot start
    would be a chooser most of whose entries are an error message.  What is
    *not* fetched is offered as a download instead, which is a different
    question and belongs on a different screen.
    """
    from . import download
    found: List[Level] = []
    for pack in (download.ASSET_PACKS if packs is None else packs):
        root = download.pack_root(pack, cache_dir)
        if root is None:
            continue
        art = _levelshots(root)
        for name in download.list_maps(root):
            found.append(Level(name=name, target='%s:%s' % (pack.key, name),
                               pack=pack.key, art=art.get(name, '')))
    return found


def _levelshots(root: str) -> Dict[str, str]:
    """``{map name: picture}`` for one unpacked pack.

    The tree is walked once per pack rather than searched once per map: a
    release splits its content across several pak directories, so the picture
    for a map is rarely beside the map, and fifty separate searches over the
    same tree is fifty times the work for the same answer.
    """
    found: Dict[str, str] = {}
    for base, _dirs, files in os.walk(root):
        directory = os.path.basename(base).lower()
        shared = directory == LEVELSHOT_DIR
        # A metadata directory is named after its map, so the picture in it is
        # the one whose stem matches the directory's own name; anything else
        # under `meta/` belongs to something other than the level's portrait.
        metadata = os.path.basename(os.path.dirname(base)).lower() == METADATA_DIR
        if not shared and not metadata:
            continue
        for name in files:
            stem, extension = os.path.splitext(name)
            if extension.lower() not in LEVELSHOT_EXTENSIONS:
                continue
            if metadata and stem.lower() != directory:
                continue
            # First wins, matching the pack precedence the texture
            # resolver uses: an earlier pak overrides a later one.
            found.setdefault(stem.lower(), os.path.join(base, name))
    return found


def describe(setup: MatchSetup) -> Dict[str, Any]:
    """This match as rows for the developer overlay."""
    return {
        'level': setup.level or '-',
        'bots': setup.bots,
        'difficulty': setup.difficulty,
        'frag limit': setup.fragLimit or '-',
        'time limit': setup.timeLimit or '-',
    }
