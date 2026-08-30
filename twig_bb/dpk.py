"""`.dpk` packages: their names, their versions, and what each one depends on.

A `.dpk` is a ZIP archive laying its content out the way a `.pk3` does
(``SPEC-DPK §1``, ``§5``), so once one is unpacked the rest of this viewer
resolves textures and scripts out of it without knowing the difference.  What is
new is that a package **names the other packages it needs**, in a `DEPS` file at
its root (``SPEC-DPK §4``), and a map drawn without them is a map without its
art.  Resolving that list into an ordered set of content roots is this module's
job.

``SPEC-DPK`` is unusually careful about the line between what its corpus showed
and what it could not, and this module keeps that line visible: every decision
the data did not settle is marked below as a **choice**, with the section that
says so, rather than being presented as the original's behaviour.
"""

from __future__ import annotations

import logging
import os
import zipfile
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

log = logging.getLogger(__name__)

#: The package extension (``SPEC-DPK §1``).
EXTENSION = '.dpk'

#: ``SPEC-DPK §4.1`` -- the dependency list, at the archive root, capitalised
#: and without an extension.
DEPS_NAME = 'DEPS'

#: ``SPEC-DPK §2.2`` -- the one character separating a package's name from its
#: version.
VERSION_SEPARATOR = '_'


class Requirement(NamedTuple):
    """One line of a `DEPS` file (``SPEC-DPK §4.5``)."""

    name: str
    #: The version the line asked for, or None where it named only a package.
    #: ``SPEC-DPK §4.10`` could not establish what a version means here and
    #: chose "at least this"; only a package naming *itself* was ever observed
    #: with one (``§4.7``).
    version: Optional[str] = None


def split_name(filename: str) -> Tuple[str, str]:
    """A package file's ``(name, version)`` (``SPEC-DPK §2.1``).

    ``SPEC-DPK §2.3``: no observed name or version contains the separator, so
    splitting on the first and on the last give the same answer for every real
    package; splitting on the **last** is the spec's choice and is kept here.

    A filename with no separator has no version, which is the answer for the
    two non-package files the published listing carries (``§2.2``).
    """
    base = os.path.basename(filename)
    if base.lower().endswith(EXTENSION):
        base = base[:-len(EXTENSION)]
    name, separator, version = base.rpartition(VERSION_SEPARATOR)
    if not separator:
        return (base, '')
    return (name, version)


def version_key(version: str) -> Optional[Tuple[int, ...]]:
    """A version as a tuple of integers, or None if it is not purely numeric.

    ``SPEC-DPK §3.4``: compare component-wise on `.`, a shorter prefix being
    the lesser.  Every published version the spec's corpus covered orders this
    way.  ``SPEC-DPK §3.6`` records that comparing the version *strings*
    happens to agree on every version published so far, and ``§3.7`` why that
    is not something to rely on: a `1.9` released before a `1.10` orders the
    wrong way round as strings, and the grammar permits both.

    None for a version that is not a plain ``N(.N)*``.  ``SPEC-DPK §3.5``:
    how such a version orders was not established, so it is treated as
    incomparable rather than coerced to something that looks adjacent to it.
    """
    if not version:
        return None
    parts = version.split('.')
    if not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def newest(paths: Sequence[str]) -> Optional[str]:
    """The highest-versioned package among ``paths``, or None if empty.

    ``SPEC-DPK §3.5``: a version that will not parse is not ordered against
    one that will, and a parseable build is preferred when a choice has to be
    made.  Ties and unparseable-only sets fall back to the name, so the answer
    does not depend on the order the caller happened to list them in.
    """
    best: Optional[str] = None
    best_key: Optional[Tuple[int, ...]] = None
    unparseable: List[str] = []
    for path in paths:
        key = version_key(split_name(path)[1])
        if key is None:
            unparseable.append(path)
        elif best_key is None or key > best_key:
            best, best_key = path, key
    if best is not None:
        return best
    return sorted(unparseable)[0] if unparseable else None


def parse_deps(text: str) -> List[Requirement]:
    """The requirements a `DEPS` file states, in the file's own order.

    ``SPEC-DPK §4.5``: each line is a package name, optionally followed by a
    single space and a version.  ``§4.12`` could not establish whether the
    order means anything, and chose to preserve it in case it does.

    ``SPEC-DPK §4.14``: blank lines are skipped and surrounding whitespace is
    stripped, which cannot mis-handle any observed file.  No comment syntax is
    invented -- the observed grammar makes a line beginning with `#` a package
    name, and it is read as one.
    """
    requirements: List[Requirement] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        fields = stripped.split()
        requirements.append(Requirement(fields[0],
                                        fields[1] if len(fields) > 1 else None))
    return requirements


def read_deps(package: str) -> List[Requirement]:
    """The requirements of a package, archived or already unpacked.

    ``SPEC-DPK §4.2``: a package with no `DEPS` depends on nothing, which is
    ordinary and not an error.
    """
    try:
        if os.path.isdir(package):
            path = os.path.join(package, DEPS_NAME)
            if not os.path.isfile(path):
                return []
            with open(path, 'r', errors='replace') as handle:
                return parse_deps(handle.read())
        with zipfile.ZipFile(package) as archive:
            try:
                raw = archive.read(DEPS_NAME)
            except KeyError:
                return []
        return parse_deps(raw.decode('ascii', errors='replace'))
    except (OSError, zipfile.BadZipFile) as error:
        log.warning('cannot read %s from %s: %s', DEPS_NAME, package, error)
        return []


def available(directory: str) -> Dict[str, List[str]]:
    """Every package in ``directory``, as ``{name: [paths]}``.

    Both archives and unpacked directories count, since a package may have
    been extracted already; ``SPEC-DPK §3.10`` notes that an extracted package
    keeps its version only in the name of the directory it went into, which is
    why unpacking under the package's own file name matters.
    """
    found: Dict[str, List[str]] = {}
    try:
        entries = sorted(os.scandir(directory), key=lambda entry: entry.name)
    except OSError:
        return found
    for entry in entries:
        if entry.is_file() and entry.name.lower().endswith(EXTENSION):
            found.setdefault(split_name(entry.name)[0], []).append(entry.path)
        elif entry.is_dir() and VERSION_SEPARATOR in entry.name:
            found.setdefault(split_name(entry.name)[0], []).append(entry.path)
    return found


def resolve(package: str, search: Dict[str, List[str]]) -> Tuple[List[str], List[str]]:
    """``package`` and everything it needs, in load order, plus what is absent.

    ``SPEC-DPK §4.15``, ``§4.16``: the dependency graph is neither a tree nor
    guaranteed acyclic, so this is a transitive closure that never revisits a
    name.  Requirements are followed in the order the file gives them
    (``§4.12``).

    **The order is this viewer's choice, not a fact** (``SPEC-DPK §7.4``): a
    package is placed before the packages it names, so a map's own content
    shadows the art packs it draws from, which is the rule
    :class:`~twig_bb.contentsearch.ContentSearch` already applies to content
    roots and the one ``§7.5`` requires for an incremental package to have any
    effect.

    Returns ``(paths, missing)`` -- the second being requirement names nothing
    in ``search`` satisfies, which a caller reports rather than fails on, since
    a map with some of its art draws better than no map at all.
    """
    order: List[str] = []
    missing: List[str] = []
    seen = {split_name(package)[0]}
    queue = [(package, read_deps(package))]
    order.append(package)
    while queue:
        _owner, requirements = queue.pop(0)
        for requirement in requirements:
            if requirement.name in seen:
                continue
            seen.add(requirement.name)
            candidates = search.get(requirement.name, [])
            chosen = newest(candidates)
            if chosen is None:
                missing.append(requirement.name)
                continue
            order.append(chosen)
            queue.append((chosen, read_deps(chosen)))
    return (order, missing)
