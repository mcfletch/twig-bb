#! /usr/bin/env python
"""What a frozen Twitchy GLitchy Bang Bang bundle runs

The bundle holds the game and the fetcher that brings a map down to play it,
in one directory with one copy of the engine, Python and the libraries beneath
them. Each command is an executable of its own beside that directory and is
recognised by the name it was run under -- see
:mod:`OpenGLContext.packaging.multicall`.

No map travels with the bundle. The content is other people's, under licences
of its own (see NOTICES.md), so the game fetches a pack on request and keeps it
under the player's own application data.
"""

import sys

from OpenGLContext.packaging.multicall import command_modules, run

#: Executable name -> the ``module:attribute`` it runs. ``packaging/twig-bb.spec``
#: builds one executable per key and hands ``command_modules(COMMANDS)`` to
#: PyInstaller, so this table is the only place a command is declared.
COMMANDS = {
    'twig-bb': 'twig_bb.viewer:main',
    'twig-bb-fetch': 'twig_bb.download:main',
    'twig-bb-bsp': 'twig_bb.maploader:main',
}

#: The modules to tell a freezer about, since the table above names them as
#: strings. Read from the ``.spec``.
MODULES = command_modules(COMMANDS)

if __name__ == '__main__':
    sys.exit(run(COMMANDS))
