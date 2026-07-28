"""Load and walk through Quake 2 and Quake 3 maps.

Two map families share one entry point: :func:`twitchoglc.maploader.load`
sniffs the ``IBSP`` version and dispatches, and everything after that — surface
styles, batched geometry, lightmap atlas, PBR materials, scene, collision mesh,
push volumes — is the same objects whichever family the file came from.

The format layers are :mod:`twitchoglc.q2bsp` (``IBSP`` version 38) and
:mod:`twitchoglc.q3bsp` (version 46), and version 46's material scripts are
read by :mod:`twitchoglc.q3shader`.  Every format constant cites a numbered
fact in one of the specifications under ``specs/``; none was derived from an
engine implementation.
"""

__version__ = '3.0.0'
