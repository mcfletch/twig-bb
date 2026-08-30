"""Fetch and unpack map archives.

Downloads go through ``OpenGLContext.loaders.resolver.fetch_to_cache``, which
is the framework's one audited path for pulling an untrusted external asset: it
locks the fetch to the requested origin across redirects, caps the response
size, coalesces concurrent fetches of the same URL, and caches under the
per-user app-data directory rather than world-writable system temp.  Using it
is also why this module needs no HTTP library of its own.

Unpacking is equally untrusted.  A `.pk3` is an ordinary ZIP archive
(``SPEC-BSP46 §7.1``) whose entry names come from whoever built it, so every
name is checked to lie inside the destination before anything is written.
"""

from __future__ import annotations

import fnmatch
import hashlib
import logging
import os
import shutil
import tarfile
import zipfile
from typing import List, Optional, Sequence, Tuple

from OpenGLContext.loaders import resolver

from . import catalog
from .assetpack import AssetPack

log = logging.getLogger(__name__)

#: Archive extensions that hold a map and its content (``SPEC-BSP46 §7.1``).
#: `.dpk` is the same ZIP container under a different name and laid out the
#: same way (``SPEC-DPK §1.1``, ``§1.19``), so it unpacks through this module
#: unchanged; what it adds is the dependency list :mod:`twig_bb.dpk` reads.
ARCHIVE_EXTENSIONS = ('.pk3', '.zip', '.dpk')
MAP_EXTENSION = '.bsp'

#: Where an unpacked archive lands when the caller names no directory.  A map
#: archive gets a directory named after a hash of where it came from, since two
#: downloads may share a base name.
CACHE_SUBDIR = 'twig-bb-maps'

#: Where shared content -- content wanted by many maps rather than by one --
#: is unpacked.  Named after the pack rather than hashed: every Quake 3 map
#: wants the same core textures, so this is a directory a user can find, point
#: another tool at, or delete on purpose.
CONTENT_SUBDIR = 'twig-bb-content'

#: Every pack this build offers, read from :mod:`twig_bb.catalog` at import.
#: A list rather than a literal here so a pack can be added or corrected in
#: `packs.json` without touching Python.
ASSET_PACKS = tuple(catalog.load())


def pack_for_key(key: str) -> Optional[AssetPack]:
    """The registered pack with this key, or None."""
    for pack in ASSET_PACKS:
        if pack.key == key:
            return pack
    return None


def packs_for(family: str) -> List[AssetPack]:
    """Every pack that could help a map of ``family``."""
    return [pack for pack in ASSET_PACKS
            if pack.family in (family, None)]


def human_size(count: int) -> str:
    """A byte count as the user should read it."""
    return '%d MB' % (round(count / 1e6),)


#: Short names a user may type in place of a pack key.
PACK_ALIASES = {'openarena': 'openarena-maps', 'oa': 'openarena-maps'}


def parse_pack_target(target: str) -> Optional[Tuple[AssetPack, str]]:
    """Read ``pack:mapname`` and return the pack and the map name.

    None for anything else, including URLs and Windows drive letters, both of
    which have the same shape and are not this.
    """
    prefix, _, name = target.partition(':')
    if not name or '/' in prefix or '\\' in prefix:
        return None
    if name.startswith(('/', '\\')):
        return None
    pack = pack_for_key(PACK_ALIASES.get(prefix.lower(), prefix.lower()))
    if pack is None:
        # Content published one package per map has no single pack to name, so
        # `<family>:<map>` also reaches a pack keyed `<family>-<map>`.  Without
        # this the only way to ask for such a level is to know which package
        # holds it, which is the thing the shorthand exists to save.
        stem = os.path.splitext(name)[0].lower()
        pack = pack_for_key('%s-%s' % (prefix.lower(), stem))
    if pack is None:
        return None
    return (pack, name)


def find_map(root: str, name: str) -> Optional[str]:
    """The path of map ``name`` inside an unpacked pack, or None.

    A maps release ships either loose `.bsp` files or `.pk3` archives holding
    them; both are searched, and an archive that holds the map is unpacked
    beside itself so its textures are found with it.
    """
    wanted = os.path.splitext(name)[0].lower()
    archives = []
    for directory, _, files in os.walk(root):
        for filename in files:
            path = os.path.join(directory, filename)
            stem, extension = os.path.splitext(filename.lower())
            if extension == MAP_EXTENSION and stem == wanted:
                return path
            if extension in ARCHIVE_EXTENSIONS:
                archives.append(path)
    for archive in sorted(archives):
        held = _maps_in_archive(archive)
        for entry in held:
            if os.path.splitext(os.path.basename(entry))[0].lower() == wanted:
                directory = os.path.splitext(archive)[0]
                return unpack(archive, directory,
                              map_name=os.path.basename(entry))
    return None


#: Directory names that mark a Quake content root -- the level a `.pk3` would
#: have at its top, and the level texture names resolve against
#: (``SPEC-BSP46 §6.1``).
CONTENT_MARKERS = ('textures', 'maps', 'scripts', 'models', 'env', 'gfx')

#: How far below a pack's top a content root may sit.  A split release wraps
#: its content in a version directory and a pak directory, so two is enough;
#: the limit is what stops the search walking `textures/` itself, which holds
#: thousands of directories and would cost a full tree scan per launch.
CONTENT_DEPTH = 2


def content_roots(root: str) -> List[str]:
    """The directories inside an unpacked pack that content resolves against.

    A release wraps its content in a version directory and one directory per
    pak, so the level a map's texture names are relative to is rarely the top
    of the pack.  Every such level is returned, since a split release puts art
    and maps in different paks and a map may draw from any of them.

    The pack's own top is returned when nothing is recognised, so an unusual
    layout resolves nothing rather than breaking the caller.
    """
    found: List[str] = []

    def _scan(directory: str, depth: int) -> None:
        children = []
        try:
            entries = sorted(os.scandir(directory), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if not entry.is_dir():
                continue
            if entry.name.lower() in CONTENT_MARKERS:
                found.append(directory)
                return
            children.append(entry.path)
        if depth < CONTENT_DEPTH:
            for child in children:
                _scan(child, depth + 1)

    _scan(root, 0)
    return found or [root]


def list_maps(root: str) -> List[str]:
    """The names of every map an unpacked pack offers, loose or archived."""
    names = set()
    for directory, _, files in os.walk(root):
        for filename in files:
            stem, extension = os.path.splitext(filename)
            if extension.lower() == MAP_EXTENSION:
                names.add(stem.lower())
            elif extension.lower() in ARCHIVE_EXTENSIONS:
                for entry in _maps_in_archive(os.path.join(directory, filename)):
                    names.add(os.path.splitext(os.path.basename(entry))[0].lower())
    return sorted(names)


def _maps_in_archive(archive: str) -> List[str]:
    """The `.bsp` entries an archive holds; empty if it cannot be read."""
    try:
        with zipfile.ZipFile(archive) as zip_file:
            return [name for name in zip_file.namelist()
                    if name.lower().endswith(MAP_EXTENSION)]
    except (zipfile.BadZipFile, OSError):
        log.warning('%s is not a readable archive', archive)
        return []


class NoMapFound(IOError):
    """An archive that holds no `.bsp` at all."""


class AmbiguousMap(IOError):
    """An archive holding several maps, with no way to tell which was meant."""


class UnsafeArchive(IOError):
    """An archive whose entry names would write outside the unpack directory."""


def resolve_target(target: str, cache_dir: Optional[str] = None,
                   map_name: Optional[str] = None, force: bool = False) -> str:
    """Turn what a user typed into the path of a map file on disk.

    Accepts a URL, an archive, or a `.bsp` that is already unpacked, so the
    viewer's command line does not have to care which it was given.
    """
    if target.startswith(('http://', 'https://')):
        archive = fetch(target, cache_dir=cache_dir)
        return unpack(archive, _unpack_dir(target, cache_dir),
                      map_name=map_name, force=force)
    if not os.path.exists(target):
        raise FileNotFoundError(target)
    if os.path.splitext(target)[1].lower() in ARCHIVE_EXTENSIONS:
        return unpack(target, _unpack_dir(target, cache_dir),
                      map_name=map_name, force=force)
    return target


#: How much larger than its published size a pack is allowed to be.  A size
#: drifts between releases, and a fetch that fails on the last megabyte is
#: worse than one that never started.
SIZE_HEADROOM = 1.5


def fetch_limit(approximate_bytes: int) -> int:
    """The byte cap to fetch a pack of this size under.

    The resolver's own default is the floor: it is the right limit for an asset
    of unknown size, and a pack whose size is known in advance is the one case
    where raising it is warranted.
    """
    return max(int(approximate_bytes * SIZE_HEADROOM),
               resolver.DEFAULT_MAX_RESOURCE_BYTES)


def fetch(url: str, cache_dir: Optional[str] = None,
          max_bytes: Optional[int] = None) -> str:
    """Download ``url`` through the resolver and return the cached file's path."""
    log.info('fetching %s', url)
    if max_bytes is None:
        return resolver.fetch_to_cache(url, cache_dir=cache_dir)
    return resolver.fetch_to_cache(url, cache_dir=cache_dir, max_bytes=max_bytes)


def unpack(archive: str, directory: str, map_name: Optional[str] = None,
           force: bool = False, require_map: bool = True) -> str:
    """Extract ``archive`` into ``directory``; return the map's path.

    With ``require_map`` false the archive is treated as a content pack — a
    texture or model set with no map of its own — and the unpacked root is
    returned instead.
    """
    os.makedirs(directory, exist_ok=True)
    with zipfile.ZipFile(archive) as zip_file:
        names = _safe_names(zip_file, directory)
        maps = [name for name in names
                if name.lower().endswith(MAP_EXTENSION)]
        nested = [name for name in names
                  if os.path.splitext(name)[1].lower() in ARCHIVE_EXTENSIONS]
        chosen = _choose(maps, map_name) if maps else None
        if not maps and not nested and require_map:
            raise NoMapFound('%s contains no %s file' % (archive, MAP_EXTENSION))
        if force or not _already_unpacked(directory, chosen):
            zip_file.extractall(directory)
    if chosen:
        return os.path.join(directory, chosen)
    if nested:
        # Some downloads wrap the .pk3 in an outer .zip; unpack the inner one
        # into the same tree so its content sits beside the map.
        return unpack(os.path.join(directory, nested[0]), directory,
                      map_name=map_name, force=force, require_map=require_map)
    return directory


def _safe_names(zip_file: zipfile.ZipFile, directory: str) -> List[str]:
    """Every entry name, after refusing any that escapes ``directory``."""
    root = os.path.abspath(directory)
    names = []
    for name in zip_file.namelist():
        if name.endswith('/'):
            continue
        target = os.path.abspath(os.path.join(root, name))
        if os.path.isabs(name) or not target.startswith(root + os.sep):
            raise UnsafeArchive(
                'archive entry %r would be written outside %s' % (name, directory))
        names.append(name)
    return names


def _choose(maps: Sequence[str], map_name: Optional[str]) -> str:
    """Pick one map from an archive, or say why that cannot be done."""
    if map_name:
        pattern = map_name if '*' in map_name or '?' in map_name else map_name + '*'
        for name in sorted(maps):
            if fnmatch.fnmatch(os.path.basename(name).lower(), pattern.lower()):
                return name
        raise AmbiguousMap('no map matching %r; the archive holds %s'
                           % (map_name, _listed(maps)))
    if len(maps) > 1:
        raise AmbiguousMap('the archive holds %d maps; name one with --map: %s'
                           % (len(maps), _listed(maps)))
    return maps[0]


def _listed(maps: Sequence[str]) -> str:
    return ', '.join(sorted(os.path.basename(name) for name in maps))


def _already_unpacked(directory: str, chosen: Optional[str]) -> bool:
    """Whether the wanted map is already sitting in ``directory``."""
    return bool(chosen) and os.path.isfile(os.path.join(directory, chosen or ''))


def pack_directory(pack: AssetPack, cache_dir: Optional[str] = None) -> str:
    """Where a pack unpacks, whether or not it is there yet."""
    base = cache_dir or _default_cache()
    return os.path.join(base, CONTENT_SUBDIR, pack.directory)


def pack_root(pack: AssetPack, cache_dir: Optional[str] = None) -> Optional[str]:
    """A pack's unpacked content root, or None if it has not been fetched.

    Checked before anything asks the user or touches the network, so a pack is
    downloaded once per user and every later run simply finds it.

    A pack is unpacked rather than read from its archive: texture lookup lists
    directories to match names whose case differs from the map's, which an
    archive would need a filesystem shim to support, and every read from an
    unpacked tree skips a decompression.
    """
    directory = pack_directory(pack, cache_dir)
    marker = os.path.join(directory, pack.marker) if pack.marker else directory
    return directory if os.path.isdir(marker) and os.listdir(directory) else None


def fetch_pack(pack: AssetPack, cache_dir: Optional[str] = None) -> str:
    """Fetch and unpack ``pack``; return its content root.

    A no-op when it is already unpacked, so a caller may use it as "make sure
    this is available".  A pack carries no map of its own in the `.bsp`-in-an-
    archive sense the map loader expects, so the no-map rule is relaxed.
    """
    existing = pack_root(pack, cache_dir)
    if existing is not None:
        return existing
    archive = fetch(pack.url, cache_dir=cache_dir,
                    max_bytes=fetch_limit(pack.approximate_bytes))
    directory = pack_directory(pack, cache_dir)
    if pack.archive == 'zip':
        unpack(archive, directory, require_map=False)
    else:
        _extract_tar(archive, directory)
    return directory


def _extract_tar(archive: str, directory: str) -> None:
    """Extract a source tarball, refusing any entry that escapes ``directory``.

    Archive content is untrusted whatever its format, so the same rule the zip
    path applies is applied here — ``filter='data'`` additionally refuses
    absolute paths, links out of the tree, and device nodes.
    """
    os.makedirs(directory, exist_ok=True)
    root = os.path.abspath(directory)
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            target = os.path.abspath(os.path.join(root, member.name))
            if os.path.isabs(member.name) or not target.startswith(root + os.sep):
                raise UnsafeArchive(
                    'archive entry %r would be written outside %s'
                    % (member.name, directory))
        tar.extractall(directory, filter='data')




def _unpack_dir(target: str, cache_dir: Optional[str]) -> str:
    """A stable per-archive directory, keyed by what was asked for.

    Keyed by a hash of the URL or path so two archives with the same base name
    do not unpack over one another.
    """
    key = hashlib.sha1(target.encode('utf-8')).hexdigest()[:16]
    base = cache_dir or os.path.join(_default_cache(), CACHE_SUBDIR)
    return os.path.join(base, key)


def _default_cache() -> str:
    """The per-user cache root the rest of OpenGLContext writes under."""
    from OpenGLContext import userpaths
    try:
        return os.path.join(userpaths.appdatadirectory(), 'OpenGLContext')
    except OSError:                             # pragma: no cover - no home dir
        import tempfile
        return tempfile.gettempdir()


def purge(cache_dir: Optional[str] = None) -> None:
    """Delete every unpacked tree, both the per-map ones and shared content."""
    base = cache_dir or _default_cache()
    for subdir in (CACHE_SUBDIR, CONTENT_SUBDIR):
        directory = base if cache_dir else os.path.join(base, subdir)
        if os.path.isdir(directory):
            shutil.rmtree(directory)
            log.info('removed %s', directory)
        if cache_dir:
            break


def main() -> None:
    """Download and unpack a map archive from the command line."""
    import argparse
    parser = argparse.ArgumentParser(
        description='Fetch and unpack a Quake-style map archive')
    parser.add_argument('target', help='a http(s) URL, a .pk3/.zip, or a .bsp')
    parser.add_argument('--map', dest='map_name', default=None,
                        help='which map to use when the archive holds several')
    parser.add_argument('--force', action='store_true',
                        help='unpack again even if the tree already exists')
    parser.add_argument('--cache-dir', default=None,
                        help='where to cache downloads and unpacked trees')
    parser.add_argument('--purge', action='store_true',
                        help='delete the unpacked archive cache and exit')
    options = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if options.purge:
        purge(options.cache_dir)
        return
    path = resolve_target(options.target, cache_dir=options.cache_dir,
                          map_name=options.map_name, force=options.force)
    print(path)
