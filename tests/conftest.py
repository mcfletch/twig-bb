"""Shared fixtures: synthetic maps on disk, and the real sample maps if present."""

from __future__ import annotations

import os
from typing import Callable, Dict, Optional

import pytest

import bspbuilder

WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARENA_MAP = os.path.join(WORKSPACE, 'tmp', 'arena', 'maps', 'ctf-curvy.bsp')
QUAKE3_MAP = os.path.join(WORKSPACE, 'tmp', 'q3', 'ztn', 'maps', 'ztn3dm1.bsp')


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
def arena_map() -> Optional[str]:
    """The Alien Arena sample map (``IBSP`` v38), or skip."""
    return _sample(ARENA_MAP, 'Alien Arena sample map')


@pytest.fixture
def quake3_map() -> Optional[str]:
    """A Quake 3 sample map (``IBSP`` v46), or skip."""
    return _sample(QUAKE3_MAP, 'Quake 3 sample map')
