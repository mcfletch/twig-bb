"""Shared fixtures: synthetic maps on disk, and the real sample map if present."""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

import pytest

import bspbuilder

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
QUAKE3_MAP = os.path.join(WORKSPACE, 'tmp', 'q3', 'ztn', 'maps', 'ztn3dm1.bsp')


# Two test modules define an OpenGLContext window class at import time, which
# needs a real GL backend: with none present (a headless box, plain `tox`) the
# class body raises a metaclass conflict before any test is collected, and the
# whole run errors out.  Skip *collecting* those files when the viewer will not
# import, so the suite is green headless and still runs them where GL is up.
try:
    from twig_bb import viewer as _viewer  # noqa: F401
except Exception:
    collect_ignore = ['test_viewer.py', 'test_hudsample.py']


@pytest.fixture
def write_map(tmp_path) -> Callable[..., str]:
    """Write a synthetic map and return its path."""
    def write(version: int, lumps: Dict[str, bytes], name: str = 'test.bsp') -> str:
        maps = tmp_path / 'maps'
        maps.mkdir(exist_ok=True)
        path = maps / name
        path.write_bytes(bspbuilder.build(version, lumps))
        return str(path)
    return write


def _sample(path: str, what: str) -> Optional[str]:
    if not os.path.exists(path):
        pytest.skip('%s not present at %s' % (what, path))
    return path


@pytest.fixture
def quake3_map() -> Optional[str]:
    """A Quake 3 sample map (``IBSP`` v46), or skip."""
    return _sample(QUAKE3_MAP, 'Quake 3 sample map')
