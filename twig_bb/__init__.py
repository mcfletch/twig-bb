"""Load and walk through Quake 2 and Quake 3 maps.

Two map families share one entry point: :func:`twig_bb.maploader.load`
sniffs the ``IBSP`` version and dispatches, and everything after that — surface
styles, batched geometry, lightmap atlas, PBR materials, scene, collision mesh,
push volumes — is the same objects whichever family the file came from.

The format layers are :mod:`twig_bb.q2bsp` (``IBSP`` version 38) and
:mod:`twig_bb.q3bsp` (version 46), and version 46's material scripts are
read by :mod:`twig_bb.q3shader`.  Every format constant cites a numbered
fact in one of the specifications under ``specs/``; none was derived from an
engine implementation.
"""

__version__ = '3.0.0'
