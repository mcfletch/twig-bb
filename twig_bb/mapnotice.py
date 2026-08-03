"""What the running map is, and under whose terms it is being played.

A level is somebody's work, fetched under a licence that asks for attribution.
:mod:`twig_bb.notices` credits every *pack* this program can download; that is
the obligation to the catalogue, and it is answered whether or not anything is
running.  This module answers the other half: a player standing in a map wants
to know **which** map, by whom, and under what terms, without first working out
which of five packs it came from.

Three sources, in the order they are trusted:

* **What the mapper embedded.** A Quake map's ``worldspawn`` carries a
  ``message``, which is where the title goes and where a mapper usually signs
  the work (``SPEC-BSP38 §3.2``, ``SPEC-BSP46 §5.2``).  It is the only
  attribution that travels *inside* the file, so it survives repacking.
* **The pack the file sits under.** The catalogue states each pack's terms, and
  a map's path says which pack it came from; a map of your own claims nothing.
* **The licence documents that travel with the content.** A release ships its
  own ``COPYING``/``CREDITS``/``LICENSE``.  Those are cited by path rather than
  quoted: they run to tens of kilobytes, and a reader wants to be told where
  the authoritative text is, not have it pasted over the screen.

Every reader here is defensive, for the same reason
:mod:`twig_bb.debug`'s are: a notice is wanted exactly when something is half
built, and no missing file, absent key or unfetched pack is a reason for a
frame to fail.
"""

from __future__ import annotations

import os
import re
import textwrap
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional, Sequence, Tuple

__all__ = ['CREDIT_WIDTH', 'LICENCE_NAMES', 'Locator', 'MapNotice', 'for_map',
           'licence_documents', 'title_and_author']

#: Characters that fit across the HUD's message queue at its authored size.
#: The queue draws a line as given and never wraps, so this is the width a
#: credit is wrapped to rather than a suggestion.
CREDIT_WIDTH = 32

#: Where a pack's content is unpacked.  The seam between a notice and the
#: downloader's idea of a cache, so a differently-laid-out build is served by
#: passing its own rather than by editing this module.
Locator = Callable[..., str]

#: File names that hold a release's own terms or credits, lower-cased and
#: without extension.  Matched by stem so ``COPYING``, ``COPYING.txt`` and
#: ``LICENSE.md`` are one rule rather than three.
LICENCE_NAMES = ('copying', 'licence', 'license', 'credits', 'copyright',
                 'notice', 'notices')

#: ``Aggressor - by Tyrann`` and ``GalMevish by Armageddon_Man``.  The dash is
#: optional and the space before ``by`` is not, which is what keeps ``Flyby``
#: a title rather than a map by ``y``.
_BY = re.compile(r'^(?P<title>.*?)\s*(?:[-–—:]\s*)?\bby\b\s*'
                 r'(?P<author>.+)$', re.IGNORECASE)


@dataclass(frozen=True)
class MapNotice:
    """One running map, as much of it as could be established.

    Every field may be empty: a map that embeds no message, sits under no
    catalogued pack and ships no licence file still has a name, and naming it
    is the point.
    """

    #: The map's file name without extension -- always known, since it is what
    #: was loaded.
    name: str
    #: The title the mapper embedded, empty when they embedded none.
    title: str = ''
    #: The author, when the embedded title named one.
    author: str = ''
    #: The title of the catalogued pack the file sits under, when it does.
    pack: str = ''
    #: That pack's stated terms.
    licence: str = ''
    #: Paths of the licence and credit documents shipped with the content.
    documents: Tuple[str, ...] = field(default_factory=tuple)
    #: ``(title, terms)`` for each other pack whose content this map is drawn
    #: with -- base textures, replacement art.  Separate from :attr:`licence`
    #: because those terms can be stricter than the map's own: the Quake 3
    #: replacement textures are CC BY-NC-ND, and somebody recording a level
    #: drawn with them needs to know that from the level they are in.
    drawn_with: Tuple[Tuple[str, str], ...] = field(default_factory=tuple)

    @property
    def summary(self) -> str:
        """One line naming the map and whoever made it.

        Deliberately ASCII: this is drawn by the HUD's bitmap font, which has
        no glyph for the dashes the rest of this project's prose uses and
        draws one as ``?``.
        """
        shown = self.title or self.name
        return '%s, by %s' % (shown, self.author) if self.author else shown

    def credit_lines(self, width: int = 0) -> List[str]:
        """The credit as short lines: the map, then its terms in full.

        The HUD's message queue draws each line as it is given and never
        wraps, so a licence long enough to run off the screen is wrapped here
        instead.  **Wrapped and not shortened**: a truncated licence states
        weaker terms than the content actually carries, which is the one thing
        an attribution notice must not do.
        """
        lines = [self.summary]
        if self.licence:
            lines.extend(textwrap.wrap(self.licence, width or CREDIT_WIDTH))
        return lines

    def text(self) -> str:
        """The block that opens the acknowledgements while this map is running."""
        lines = ['The map you are in', '', '  %s' % (self.summary,)]
        if self.title and self.title != self.name:
            lines.append('    %s' % (self.name,))
        if self.pack:
            lines.append('    from %s' % (self.pack,))
        if self.licence:
            lines.append('    %s' % (self.licence,))
        if self.documents:
            lines.append('')
            lines.append('    Its own terms, in full, are in:')
            lines.extend('      %s' % (path,) for path in self.documents)
        if self.drawn_with:
            lines.append('')
            lines.append('    Drawn with content from, and under the terms of:')
            for title, terms in self.drawn_with:
                lines.append('      %s' % (title,))
                if terms:
                    lines.append('        %s' % (terms,))
        lines.append('')
        return '\n'.join(lines)


def title_and_author(message: str) -> Tuple[str, str]:
    """Split an embedded ``message`` into its title and its author.

    Mappers write the credit into the title by convention rather than by any
    rule -- ``Aggressor - by Tyrann``, ``GalMevish by Armageddon_Man`` -- so
    this reads the convention and gives up cleanly when it does not hold,
    returning the whole thing as a title rather than guessing.  Padding is
    stripped because these fields are padded to line up in an editor.
    """
    text = (message or '').strip()
    if not text:
        return '', ''
    found = _BY.match(text)
    if found and found.group('title').strip() and found.group('author').strip():
        return found.group('title').strip(), found.group('author').strip()
    return text, ''


def licence_documents(roots: Sequence[str]) -> List[str]:
    """Every licence or credit document shipped under these content roots.

    Searched one level down as well as at the top, because a release commonly
    wraps its content in a version directory and puts its ``COPYING`` beside
    the paks rather than above them.  One level, not a walk: the terms of a
    release live at its root, and descending further finds the licences of
    things bundled *into* it, which is a different question.
    """
    found: List[str] = []
    seen = set()
    for root in roots:
        for directory in _search_roots(root):
            for name in _sorted_entries(directory):
                path = os.path.join(directory, name)
                stem = os.path.splitext(name)[0].lower()
                if stem in LICENCE_NAMES and os.path.isfile(path):
                    real = os.path.realpath(path)
                    if real not in seen:
                        seen.add(real)
                        found.append(path)
    return found


def for_map(loaded: Any, packs: Optional[Sequence[Any]] = None,
            directory_of: Optional[Locator] = None) -> MapNotice:
    """The notice for a loaded map.

    ``packs`` defaults to the catalogue and ``directory_of`` to where the
    downloader unpacks one.  Both are parameters so that a caller with its own
    content layout -- a test, or a build that ships a different catalogue --
    is not made to patch a module to be heard.
    """
    title, author = title_and_author(_embedded_message(loaded))
    roots = _pack_roots(packs, directory_of)
    pack, root = _pack_for(getattr(loaded, 'path', ''), roots)
    return MapNotice(
        name=getattr(loaded, 'name', '') or '',
        title=title,
        author=author,
        pack=pack.title if pack is not None else '',
        licence=pack.copyright if pack is not None else '',
        documents=tuple(licence_documents(
            _own_roots(getattr(loaded, 'roots', ()) or (), root, roots))),
        drawn_with=_borrowed(getattr(loaded, 'roots', ()) or (), root, roots),
    )


def _borrowed(content: Sequence[str], root: str,
              packs: Sequence[Tuple[Any, str]]) -> Tuple[Tuple[str, str], ...]:
    """``(title, terms)`` for the other packs this map's content roots reach.

    Each once, in the order the map resolves against them, which is the order
    a reader can check them in.
    """
    found: List[Tuple[str, str]] = []
    for own in content:
        for pack, other in packs:
            if other == root or not _is_within(own, other):
                continue
            entry = (pack.title, pack.copyright)
            if entry not in found:
                found.append(entry)
    return tuple(found)


def _own_roots(content: Sequence[str], root: str,
               packs: Sequence[Tuple[Any, str]]) -> List[str]:
    """The roots whose licence documents are *this map's*.

    A map resolves its textures against packs it did not come from -- base
    content, replacement textures -- and every one of those roots is on its
    list and ships a ``COPYING`` of its own.  Under a heading that says *its
    own terms* those are somebody else's, and citing them there misstates what
    the level is under.  So: the pack the map came from and the roots inside
    it, or, for a map of your own, its roots minus any that fall inside a
    catalogued pack.

    The pack root comes first because a release states its terms at its top,
    while a map's content roots start at the pak directory the textures
    resolve against -- one or two levels below the ``COPYING``.
    """
    if root:
        return [root] + [own for own in content if _is_within(own, root)]
    return [own for own in content
            if not any(_is_within(own, other) for _pack, other in packs)]


def _embedded_message(loaded: Any) -> str:
    """``worldspawn``'s ``message``, or empty when the map carries none."""
    try:
        for entity in loaded.entities:
            if entity.classname == 'worldspawn':
                return str(entity.get('message', '') or '')
    except Exception:                                   # pragma: no cover
        return ''
    return ''


def _pack_roots(packs: Optional[Sequence[Any]],
                directory_of: Optional[Locator]) -> List[Tuple[Any, str]]:
    """Every catalogued pack paired with where it unpacks.

    Resolved once: both which pack a map came from and which roots belong to
    somebody else are answered against this same list.
    """
    if packs is None or directory_of is None:
        from . import download
        packs = download.ASSET_PACKS if packs is None else packs
        directory_of = directory_of or download.pack_directory
    found: List[Tuple[Any, str]] = []
    for pack in packs:
        try:
            found.append((pack, os.path.abspath(directory_of(pack))))
        except Exception:                               # pragma: no cover
            continue
    return found


def _pack_for(path: str,
              packs: Sequence[Tuple[Any, str]]) -> Tuple[Any, str]:
    """The catalogued pack this file sits under, and where that pack unpacks.

    ``(None, '')`` for a map of somebody's own, which claims no pack's terms.
    """
    if not path:
        return None, ''
    absolute = os.path.abspath(path)
    for pack, root in packs:
        if _is_within(absolute, root):
            return pack, root
    return None, ''


def _is_within(path: str, root: str) -> bool:
    """Whether ``path`` is under ``root``, by path component.

    Compared component-wise rather than by prefix, so ``openarena-maps-old``
    is not taken for a child of ``openarena-maps``.
    """
    return os.path.commonpath([path, root]) == root if root else False


def _search_roots(root: str) -> List[str]:
    """``root`` and its immediate subdirectories, skipping what is not there."""
    if not root or not os.path.isdir(root):
        return []
    found = [root]
    for name in _sorted_entries(root):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            found.append(path)
    return found


def _sorted_entries(directory: str) -> List[str]:
    """A directory's names in a stable order, or none when it cannot be read."""
    try:
        return sorted(os.listdir(directory))
    except OSError:
        return []
