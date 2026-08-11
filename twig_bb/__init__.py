"""Load and walk through Quake 3 (and OpenArena) maps.

:func:`twig_bb.maploader.load` reads an ``IBSP`` version 46 map, and everything
after that — surface styles, batched geometry, lightmap atlas, PBR materials,
scene, collision mesh, push volumes — is built from it.

The format layer is :mod:`twig_bb.q3bsp`, and the material scripts that decide
what a surface is are read by :mod:`twig_bb.q3shader`.  Every format constant
cites a numbered fact in one of the specifications under ``specs/``; none was
derived from an engine implementation.
"""

__version__ = '3.0.0'
