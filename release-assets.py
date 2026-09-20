#! /usr/bin/env python3
"""Build the art this game fetches, install it here, and publish it.

The characters, the weapons and the pickups are 15 MB, which is most of what an
install would download from an index that should be serving code. They are a
**base pack** instead -- attached to a GitHub release and fetched through
:mod:`OpenGLContext.contentpacks` before the first match. One command covers
the whole of that:

    ./release-assets.py                 # build the archive, write the registry
    ./release-assets.py --install       # ...and put it in this machine's store
    ./release-assets.py --push          # ...and attach it to the release tag

``--install`` is what makes a content release testable before it is a release:
the game then finds the art in its own store and plays as an installed copy
would, with nothing published and no network reached.

Only ``twig-bb/art`` is built here. The other entries in ``twig_bb/packs.json``
are other people's packages on other people's servers, and this rewrites the
one entry whose bytes are ours -- from the archive it just built, so the digest
cannot describe a file that was never made.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from OpenGLContext.contentpacks import archive, catalog, publish

#: Where a release's artefacts are fetched from.
URL = 'https://github.com/mcfletch/twig-bb/releases/download/%s/%s'

#: The namespace this game's packs sit under.
NAMESPACE = 'twig-bb'

#: The pack this builds: the art the game cannot be played without.
KEY = '%s/art' % (NAMESPACE,)

#: What proves it is unpacked.
MARKER = 'characters'

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'twig_bb', 'assets')
CATALOG = os.path.join(HERE, 'twig_bb', 'packs.json')


def build(where: str, name: str, into: str) -> tuple[str, int, str]:
    """Archive ``where`` as ``name``; return its path, size and digest."""
    path = archive.write(where, os.path.join(into, '%s.tar.gz' % (name,)))
    return path, os.path.getsize(path), archive.digest(path)


def entry(tag: str, path: str, size: int, sha: str) -> dict:
    """What the registry says about the art this built."""
    return {
        'key': KEY,
        'title': 'twig-bb art',
        'url': URL % (tag, os.path.basename(path)),
        'directory': 'twig-bb-art',
        'archive': 'tar',
        'approximate_bytes': size,
        'sha256': sha,
        'base': True,
        'copyright': 'The twig-bb project, BSD-3-Clause; characters, weapons '
                     'and pickups modelled for this game.',
        'notes': 'The characters, weapons and pickups the game is played '
                 'with. Fetched before the first match, because a game with '
                 'none of it has nothing to draw.',
        'marker': MARKER,
    }


def rewrite(declared: dict) -> None:
    """Put ``declared`` in the registry, leaving every other entry alone.

    The rest of the file is eighteen packages on other people's servers, whose
    sizes and terms are theirs to state; the one entry rewritten here is the
    one whose bytes this command produced.
    """
    with open(CATALOG, encoding='utf-8') as handle:
        document = json.load(handle)
    packs = document.get('packs') or []
    for index, one in enumerate(packs):
        if one.get('key') == KEY:
            packs[index] = declared
            break
    else:
        packs.insert(0, declared)
    with open(CATALOG, 'w', encoding='utf-8') as handle:
        json.dump(document, handle, indent=1)
        handle.write('\n')


def install(into: str) -> None:
    """Put what was built into the store the game reads, and say where.

    Through the game's own :mod:`twig_bb.download`, so what is installed is
    what it will look for.
    """
    from twig_bb import download

    store = download.store()
    print('store: %s' % (store.root,))
    pack = catalog.pack_for_key(KEY, catalog.load(CATALOG))
    where = publish.install(pack, store, into)
    print('  %-24s %s' % (pack.key, os.path.relpath(where, store.root)))


def push(tag: str, paths: list[str]) -> None:
    """Attach the built archive to the release the registry names."""
    publish.push(publish.repository(URL % (tag, 'x')), tag, paths,
                 title='twig-bb art %s' % (tag,),
                 notes='The characters, weapons and pickups the game is '
                       'played with, fetched before the first match.')
    print('attached %d file(s) to %s' % (len(paths), tag))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--tag', default='content-v1',
                        help='the release tag the artefact is attached to '
                             '(default: %(default)s)')
    parser.add_argument('--into', default=os.path.join(HERE, 'dist', 'content'),
                        help='where to write the archive')
    parser.add_argument('--install', action='store_true',
                        help="install what was built into this machine's own "
                             'store, so the game runs against it with nothing '
                             'published')
    parser.add_argument('--push', action='store_true',
                        help='attach the archive to the release at --tag, '
                             'creating it if it is not there yet (needs the '
                             'GitHub CLI, and an account that may write here)')
    options = parser.parse_args(argv)
    if not os.path.isdir(ASSETS):
        print('no art at %s' % (ASSETS,), file=sys.stderr)
        return 2
    os.makedirs(options.into, exist_ok=True)

    path, size, sha = build(ASSETS, 'twig-bb-art', options.into)
    rewrite(entry(options.tag, path, size, sha))
    print('twig-bb art: %.1f MB, sha256 %s, registry written to %s'
          % (size / 1048576, sha[:12], os.path.relpath(CATALOG, HERE)))

    if options.install:
        install(options.into)
    if options.push:
        push(options.tag, [path])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
