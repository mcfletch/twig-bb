#! /usr/bin/env python3
"""Build the art this game fetches, install it here, and publish it.

The characters, the weapons and the pickups are 15 MB, which is most of what an
install would download from an index that should be serving code. They are a
**base pack** instead -- attached to a GitHub release and fetched through
:mod:`OpenGLContext.contentpacks` before the first match. One command covers
the whole of that:

    ./release-assets.py                   # build the archive and its registry
    ./release-assets.py --install         # ...and put it in this machine's store
    ./release-assets.py --reinstall       # ...replacing the copy installed there
    ./release-assets.py --push            # ...attach it to the release tag and
                                          #    write the entry in packs.json

``--install`` is what makes a content release testable before it is a release:
the game then finds the art in its own store and plays as an installed copy
would, with nothing published and no network reached.

Only ``twig-bb/art`` is built here. The other entries in ``twig_bb/packs.json``
are other people's packages on other people's servers, and are kept as they
are; the one entry written is the one whose bytes this command produced, from
the archive it just built. The registry is written beside the archive, and
``twig_bb/packs.json`` only by ``--push`` or ``--write-registry``. The options,
the install and the push are :func:`OpenGLContext.contentpacks.publish.main`'s.
"""

from __future__ import annotations

import os

from OpenGLContext.contentpacks import ContentStore, publish

HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(HERE, 'twig_bb', 'assets')
CATALOG = os.path.join(HERE, 'twig_bb', 'packs.json')


def declare(build: publish.Build) -> list[dict]:
    """Build the art pack; what the registry says about it."""
    if not os.path.isdir(ASSETS):
        raise SystemExit('no art at %s' % (ASSETS,))
    built = build.archive(ASSETS, 'twig-bb-art')
    return [build.entry(
        'art', built, title='twig-bb art', directory='twig-bb-art', base=True,
        # A directory the pack always has at its top.
        marker='characters',
        copyright='The twig-bb project, BSD-3-Clause; characters, weapons '
                  'and pickups modelled for this game.',
        notes='The characters, weapons and pickups the game is played with. '
              'Fetched before the first match, because a game with none of '
              'it has nothing to draw.')]


def store() -> ContentStore:
    """The store the game reads, which is where ``--install`` puts the art."""
    from twig_bb import download
    return download.store()


RELEASE = publish.Release(
    namespace='twig-bb',
    url='https://github.com/mcfletch/twig-bb/releases/download/%s/%s',
    catalog=CATALOG, declare=declare,
    into=os.path.join(HERE, 'dist', 'content'), keep_unbuilt=True,
    store=store, description=__doc__.split('\n\n')[0], title='twig-bb art',
    notes='The characters, weapons and pickups the game is played with, '
          'fetched before the first match.')


if __name__ == '__main__':
    raise SystemExit(publish.main(RELEASE))
