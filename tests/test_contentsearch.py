"""Finding a content-named file under the map's content roots.

The search itself — root precedence, advisory extensions, case-insensitive
recovery, and refusing to leave the root — is shared by every kind of asset a
map names, so it is tested once here rather than once per asset type.  Facts
under test are SPEC-BSP46 §7.3, SPEC-Q3SHADER §1.6 and SPEC-Q3ENTITIES §1.2.4.
"""

from __future__ import annotations

import os

import pytest

from twig_bb.contentsearch import ContentSearch


@pytest.fixture
def roots(tmp_path):
    """Two content roots, the first taking precedence over the second."""
    for name in ('first', 'second'):
        (tmp_path / name).mkdir()
    return [str(tmp_path / 'first'), str(tmp_path / 'second')]


def write(root, relative, data=b'x'):
    path = os.path.join(root, *relative.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(data)
    return path


def test_a_file_is_found_by_its_relative_path(roots):
    wanted = write(roots[0], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_the_extensions_are_tried_in_order(roots):
    """SPEC-Q3SHADER §1.6: the first supported extension that exists wins."""
    write(roots[0], 'sound/world/wind1.ogg')
    wanted = write(roots[0], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav', '.ogg')) == wanted


def test_a_later_extension_is_found_when_the_first_is_absent(roots):
    wanted = write(roots[0], 'sound/world/wind1.ogg')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav', '.ogg')) == wanted


def test_the_roots_are_searched_in_precedence_order(roots):
    """SPEC-BSP46 §7.3: an earlier root shadows a later one."""
    wanted = write(roots[0], 'sound/world/wind1.wav')
    write(roots[1], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_an_earlier_root_wins_even_with_a_less_preferred_extension(roots):
    """Root precedence is decided before extension preference.

    A content tree that overrides a base asset does so whichever format it
    chose; an extension preference that could reach past a root would let a
    stale base `.wav` beat an override's `.ogg`.
    """
    wanted = write(roots[0], 'sound/world/wind1.ogg')
    write(roots[1], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav', '.ogg')) == wanted


def test_a_second_root_is_reached_when_the_first_has_nothing(roots):
    wanted = write(roots[1], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_a_name_that_exists_nowhere_resolves_to_nothing(roots):
    assert ContentSearch(roots).find('sound/world/absent', ('.wav',)) is None


def test_a_differently_cased_file_is_still_found(roots):
    """Quake content is authored as though the filesystem ignored case."""
    wanted = write(roots[0], 'sound/world/Wind1.WAV')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_a_differently_cased_directory_is_still_found(roots):
    wanted = write(roots[0], 'Sound/World/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_an_exact_match_beats_a_case_insensitive_one(roots):
    """The cheap lookup must never be displaced by the directory scan."""
    write(roots[0], 'sound/world/WIND1.wav')
    wanted = write(roots[0], 'sound/world/wind1.wav')
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) == wanted


def test_a_name_may_not_escape_its_content_root(roots, tmp_path):
    """Map content is untrusted: a name from the internet must stay inside."""
    write(str(tmp_path), 'secret.wav')
    assert ContentSearch(roots).find('../secret', ('.wav',)) is None


def test_an_absolute_name_is_refused(roots, tmp_path):
    outside = write(str(tmp_path), 'secret.wav')
    assert ContentSearch(roots).find(os.path.splitext(outside)[0], ('.wav',)) is None


def test_a_directory_is_listed_once_however_many_names_miss(roots, monkeypatch):
    """A miss must not cost a directory scan per lookup.

    Fifty names missing in the same directory is one scan, not fifty: a map
    naming a hundred absent textures should not walk the tree a hundred times.
    """
    write(roots[0], 'sound/world/wind1.wav')
    scans = []
    real = os.listdir
    monkeypatch.setattr(os, 'listdir', lambda path: (scans.append(path), real(path))[1])
    search = ContentSearch(roots)
    for index in range(50):
        search.find('sound/world/absent%d' % index, ('.wav',))
    assert len(set(scans)) == len(scans) <= 4


def test_an_unreadable_directory_is_a_miss_rather_than_an_error(roots, monkeypatch):
    monkeypatch.setattr(os, 'listdir', _raise_oserror)
    assert ContentSearch(roots).find('sound/world/wind1', ('.wav',)) is None


def _raise_oserror(*args, **named):
    raise OSError('unreadable')
