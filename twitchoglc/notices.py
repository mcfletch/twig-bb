"""Acknowledgements: what this is built from, and what it is playing.

Not decoration. This project plays freely-licensed content under licences with
attribution requirements, and depends on libraries whose licences ask to be
reproduced; an acknowledgements screen is how a distributed application meets
those obligations. It is also how the project is a good citizen about the
content whose licences ask for nothing.

**The content half is generated and the code half is checked**, because those
are the two ways an acknowledgement goes missing and each wants a different
answer:

* a **pack** is credited from the catalogue's own ``copyright`` field, so one
  added to `packs.json` appears here without anyone remembering — which is the
  whole reason that field is mandatory;
* a **library** is listed by hand in ``NOTICES.md``, and a test compares that
  list against what `pyproject.toml` declares, so a dependency added and not
  acknowledged fails the suite rather than shipping unattributed.

Printable from the command line as well as openable in the window, because
whoever is packaging this has no window to open.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from dataclasses import dataclass
from typing import List, Optional, Sequence, Set

from OpenGLContext.ui.dialogs import notice

from . import catalog
from .assetpack import AssetPack

__all__ = ['NOTICES_PATH', 'Acknowledgement', 'acknowledged',
           'content_notices', 'declared_dependencies', 'full_text',
           'provenance', 'screen', 'unacknowledged']

_HERE = os.path.dirname(os.path.abspath(__file__))

#: The checked-in manifest of what this program is built on.
NOTICES_PATH = os.path.join(os.path.dirname(_HERE), 'NOTICES.md')

#: Where the declared dependencies are read from.
PROJECT_PATH = os.path.join(os.path.dirname(_HERE), 'pyproject.toml')

#: Extras that are *not* shipped and so are not acknowledged.  A test runner is
#: not part of the program.
UNSHIPPED_EXTRAS = ('dev', 'test', 'docs')

#: A row of the libraries table in ``NOTICES.md``.
_ROW = re.compile(r'^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|'
                  r'\s*([^|]+?)\s*\|\s*$')

#: A dependency specifier's name, before any version or extra.
_NAME = re.compile(r'^([A-Za-z0-9._-]+)')


@dataclass(frozen=True)
class Acknowledgement:
    """One library, as ``NOTICES.md`` records it."""

    name: str
    licence: str
    home: str
    #: Whether it is an extra rather than something every install has.  A
    #: notice has to be accurate about what a *given* install contains.
    optional: bool


def acknowledged(path: Optional[str] = None) -> List[Acknowledgement]:
    """Every library ``NOTICES.md`` lists."""
    found: List[Acknowledgement] = []
    try:
        with open(path or NOTICES_PATH, 'r', encoding='utf-8') as handle:
            lines = handle.readlines()
    except OSError:
        return found
    for line in lines:
        match = _ROW.match(line)
        if match is None:
            continue
        name, licence, home, ships = (part.strip() for part in match.groups())
        if name.lower() in ('component', '---') or set(name) <= set('- '):
            continue
        # The manifest is markdown, so a bare URL is written <like this>; the
        # brackets are its syntax and not part of the address.
        found.append(Acknowledgement(name=name, licence=licence,
                                     home=home.strip('<>'),
                                     optional='optional' in ships.lower()))
    return found


def declared_dependencies(path: Optional[str] = None) -> Set[str]:
    """Every package `pyproject.toml` says this program ships with.

    Both the required list and the optional extras, minus the extras that are
    not shipped at all: a test runner is not part of the program and has
    nothing to acknowledge.

    Read with a small scanner rather than a TOML parser because the answer is
    wanted at test time on any supported Python, and the shape being read is
    two lists of strings.
    """
    try:
        with open(path or PROJECT_PATH, 'r', encoding='utf-8') as handle:
            text = handle.read()
    except OSError:
        return set()
    found: Set[str] = set()
    for name, block in _lists(text):
        if name in UNSHIPPED_EXTRAS:
            continue
        for entry in re.findall(r'"([^"]+)"', block):
            match = _NAME.match(entry.strip())
            if match:
                found.add(match.group(1).lower())
    return found


def _lists(text: str) -> List[tuple]:
    """``(name, block)`` for the dependency list and each optional extra."""
    blocks: List[tuple] = []
    for match in re.finditer(r'^dependencies\s*=\s*\[(.*?)\]', text,
                             re.MULTILINE | re.DOTALL):
        blocks.append(('', match.group(1)))
    section = re.search(r'^\[project\.optional-dependencies\](.*?)(?=^\[|\Z)',
                        text, re.MULTILINE | re.DOTALL)
    if section is not None:
        for match in re.finditer(r'^(\w+)\s*=\s*\[(.*?)\]', section.group(1),
                                 re.MULTILINE | re.DOTALL):
            blocks.append((match.group(1).lower(), match.group(2)))
    return blocks


def unacknowledged(project: Optional[str] = None,
                   path: Optional[str] = None) -> List[str]:
    """Declared dependencies that ``NOTICES.md`` does not list.

    The check that makes an unattributed dependency a failing build.
    """
    listed = {entry.name.lower() for entry in acknowledged(path)}
    return sorted(name for name in declared_dependencies(project)
                  if name not in listed)


def content_notices(packs: Optional[Sequence[AssetPack]] = None) -> str:
    """The content half, generated from the catalogue.

    A pack appears here because it is in the catalogue and states its terms,
    not because anyone remembered to write it down.
    """
    lines = [
        'Content this program can download',
        '',
        'Fetched to a per-user cache at your request, and never included in '
        'this program. Each is used under the terms below.',
        '',
    ]
    for pack in (catalog.load() if packs is None else packs):
        lines.append('  %s — %d MB' % (pack.title,
                                       round(pack.approximate_bytes / 1e6)))
        lines.append('    %s' % (pack.copyright,))
        if pack.url_page:
            lines.append('    %s' % (pack.url_page,))
        lines.append('')
    lines.extend(_shipped_art())
    return '\n'.join(lines)


def _shipped_art() -> List[str]:
    """The art that ships *with* the program, credited whether or not asked.

    CC0 requires nothing and our own work requires nothing.  Crediting both
    anyway is the rule for every piece of geometry here, and it costs a few
    lines: a reader should not have to work out which files carry an obligation
    and which do not.
    """
    return [
        'Art included with this program',
        '',
        '  Stand-in weapons — CC0 1.0',
        '    3dmodelscc0, Free CC0 Guns & Explosives Pack',
        '    https://3dmodelscc0.itch.io/',
        '',
        '  The medikit — BSD-3-Clause',
        '    Mike C. Fletcher, modelled for this project',
        '',
    ]


def provenance() -> str:
    """How the map formats came to be readable without reading an engine."""
    return (
        'Where the format knowledge came from\n'
        '\n'
        'No engine source was read while writing this program. Every format\n'
        'constant, layout and behaviour cites a numbered fact in specs/, and\n'
        'each of those documents records where its own facts came from:\n'
        'published documentation, this project\'s own earlier BSD code, the\n'
        'bytes of shipped content, or the Reader/Implementer wall of\n'
        'specs/CLEAN-ROOM.md.\n'
        '\n'
        'Where a fact could not be established from a permitted source, the\n'
        'specification says so and marks the implementation\'s answer as a\n'
        'choice rather than dressing it up as the original\'s behaviour.\n'
    )


def code_notices(path: Optional[str] = None) -> str:
    """The code half, read from the checked-in manifest."""
    lines = ['Libraries this program is built on', '']
    for entry in acknowledged(path):
        lines.append('  %s — %s%s' % (entry.name, entry.licence,
                                      ' (optional)' if entry.optional else ''))
        if entry.home:
            lines.append('    %s' % (entry.home,))
    lines.append('')
    return '\n'.join(lines)


def full_text() -> str:
    """Everything, in the order a reader wants it."""
    from .menu import GAME_TITLE
    return '\n'.join([
        '%s' % (GAME_TITLE,),
        'BSD-3-Clause — Mike C. Fletcher',
        '',
        code_notices(),
        content_notices(),
        provenance(),
    ])


def screen(on_close: Optional[object] = None) -> object:
    """The acknowledgements, as a scrolling panel over whatever is running."""
    return notice('Acknowledgements', full_text(), on_close=on_close)


def main(argv: Optional[List[str]] = None) -> int:
    """Print the acknowledgements, for anyone packaging this."""
    parser = argparse.ArgumentParser(
        prog='python -m twitchoglc.notices',
        description=__doc__.split('\n\n')[0])
    parser.add_argument('--check', action='store_true',
                        help='exit non-zero if a dependency is unacknowledged')
    options = parser.parse_args(argv)
    if options.check:
        missing = unacknowledged()
        if missing:
            sys.stderr.write('not in NOTICES.md: %s\n' % (', '.join(missing),))
            return 1
        sys.stdout.write('every declared dependency is acknowledged\n')
        return 0
    sys.stdout.write(full_text() + '\n')
    return 0


if __name__ == '__main__':                      # pragma: no cover
    raise SystemExit(main())
