"""Run the game: ``python -m twig_bb``.

Equivalent in every way to the ``twig-bb`` console script, and the form that
needs no ``PATH`` entry -- ``python -m twig_bb`` reaches the game from any
interpreter that can import it, which is what a checkout, a virtual environment
that has not been activated, and an embedded interpreter all have in common.
The arguments are the viewer's; :func:`twig_bb.viewer.build_parser` describes
them and ``python -m twig_bb --help`` prints them.
"""

from .viewer import main

if __name__ == '__main__':
    main()
