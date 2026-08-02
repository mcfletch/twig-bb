"""Resolving a map's ``noise`` path to a sound file in the content packs.

Facts under test are SPEC-Q3ENTITIES §1.2.2 (three spellings), §1.2.3 (the
extension is advisory), §1.2.5 (the ``*`` prefix is not a path) and §1.2.7 (a
miss is a silence, not a failure).
"""

from __future__ import annotations

import logging
import os

import pytest

from twitchoglc.sounds import SOUND_EXTENSIONS, SoundLibrary


def write(root, relative):
    path = os.path.join(str(root), *relative.split('/'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as handle:
        handle.write(b'RIFF')
    return path


@pytest.fixture
def content(tmp_path):
    """A content root with the sounds a real pack lays out."""
    write(tmp_path, 'sound/world/wind1.wav')
    write(tmp_path, 'sound/world/ambient/x_ominous.wav')
    return tmp_path


def library(content):
    return SoundLibrary([str(content)])


def test_a_bare_path_resolves(content):
    """SPEC-Q3ENTITIES §1.2.2: 344 of 381 speakers spell it this way."""
    found = library(content).resolve('sound/world/wind1.wav')
    assert found == os.path.join(str(content), 'sound', 'world', 'wind1.wav')


def test_a_leading_slash_is_the_same_path(content):
    """SPEC-Q3ENTITIES §1.2.2: the same file is spelled both ways in content."""
    both = library(content)
    assert both.resolve('/sound/world/wind1.wav') == both.resolve('sound/world/wind1.wav')


def test_a_name_with_no_extension_still_finds_its_file(content):
    """SPEC-Q3ENTITIES §1.2.3: three real values carry no extension at all."""
    assert library(content).resolve('sound/world/wind1') is not None


def test_an_ogg_is_found_when_the_name_says_wav(content):
    """SPEC-Q3ENTITIES §1.2.3/§1.2.4: whatever it says, the search decides."""
    write(content, 'sound/world/drone6.ogg')
    assert library(content).resolve('sound/world/drone6.wav').endswith('.ogg')


def test_wav_is_preferred_over_ogg(content):
    """The content is overwhelmingly .wav; look there first."""
    write(content, 'sound/world/both.wav')
    write(content, 'sound/world/both.ogg')
    assert library(content).resolve('sound/world/both').endswith('.wav')


def test_the_supported_extensions_are_the_ones_the_content_ships(content):
    """SPEC-Q3ENTITIES §2.1: 255 .wav and 98 .ogg, and nothing else."""
    assert SOUND_EXTENSIONS == ('.wav', '.ogg')


def test_a_star_prefixed_name_is_not_looked_up_at_all(content):
    """SPEC-Q3ENTITIES §1.2.5: it names an entity's own model, not a path.

    Not merely absent: the viewer must not go looking, because the name has no
    meaning as a path and a file that happened to match would be the wrong
    sound rather than the right one.
    """
    write(content, 'falling1.wav')
    assert library(content).resolve('*falling1.wav') is None


def test_a_sound_that_is_simply_absent_resolves_to_nothing(content):
    """SPEC-Q3ENTITIES §1.2.7: a normal condition of loading real content."""
    assert library(content).resolve('sound/world/lava1.wav') is None


def test_a_miss_warns_once_however_often_it_is_asked(content, caplog):
    """381 speakers naming one absent sound is one warning, not 381."""
    found = library(content)
    with caplog.at_level(logging.WARNING):
        for _ in range(5):
            found.resolve('sound/world/lava1.wav')
    assert len([record for record in caplog.records
                if 'lava1' in record.getMessage()]) == 1


def test_a_star_prefixed_name_is_reported_as_unresolvable_not_as_missing(
        content, caplog):
    """The two failures are different and the message must say which."""
    with caplog.at_level(logging.WARNING):
        library(content).resolve('*falling1.wav')
    assert 'model' in ' '.join(record.getMessage() for record in caplog.records)


def test_an_empty_name_resolves_to_nothing(content):
    assert library(content).resolve('') is None


def test_the_answer_is_remembered(content, monkeypatch):
    """A resolved sound must not touch the disk once per frame."""
    found = library(content)
    first = found.resolve('sound/world/wind1.wav')
    monkeypatch.setattr(os.path, 'isfile', _never)
    assert found.resolve('sound/world/wind1.wav') == first


def test_a_name_may_not_escape_the_content_root(content, tmp_path):
    write(tmp_path.parent, 'outside.wav')
    assert library(content).resolve('../outside.wav') is None


def _never(*args, **named):
    return False
