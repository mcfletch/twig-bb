"""The command-line entry points, and the summaries they print."""

from __future__ import annotations

import numpy as np

import bspbuilder
from twig_bb import download, jumppads, maploader


def _map(tmp_path, lumps=None, name='cli-test.bsp'):
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / name
    path.write_bytes(bspbuilder.build(46, lumps or bspbuilder.v46_quad()))
    return str(path)


def test_the_map_reporter_summarises_a_map(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr('sys.argv', ['twig-bb-bsp', _map(tmp_path)])
    maploader.main()
    printed = capsys.readouterr().out
    assert 'quake3' in printed
    assert 'IBSP version 46' in printed
    assert 'triangles' in printed
    assert 'gravity 800' in printed


def test_the_map_reporter_names_the_push_volumes_it_found(tmp_path, capsys,
                                                          monkeypatch):
    lumps = bspbuilder.v46_quad()
    lumps['entities'] = bspbuilder.entity_text([
        {'classname': 'worldspawn'},
        {'classname': 'trigger_push', 'model': '*1', 'angle': '-1'}])
    lumps['models'] = (bspbuilder.v46_model((0, 0, 0), (64, 64, 0), 0, 1)
                       + bspbuilder.v46_model((0, 0, 0), (64, 64, 8), 0, 0))
    monkeypatch.setattr('sys.argv', ['twig-bb-bsp', _map(tmp_path, lumps),
                                     '--verbose'])
    maploader.main()
    assert '1 trigger_push' in capsys.readouterr().out


def test_the_downloader_prints_the_path_it_resolved(tmp_path, capsys, monkeypatch):
    target = _map(tmp_path)
    monkeypatch.setattr('sys.argv', ['twig-bb-fetch', target])
    download.main()
    assert capsys.readouterr().out.strip() == target


def test_the_downloader_can_purge_its_cache(tmp_path, capsys, monkeypatch):
    cache = tmp_path / 'cache'
    (cache / 'stale').mkdir(parents=True)
    monkeypatch.setattr('sys.argv', ['twig-bb-fetch', 'ignored', '--purge',
                                     '--cache-dir', str(cache)])
    download.main()
    assert not cache.exists()


def test_purging_a_cache_that_is_not_there_is_harmless(tmp_path):
    download.purge(str(tmp_path / 'never-made'))


# -- the push-volume summary --------------------------------------------------

def _volume(velocity, classname=jumppads.PUSH_CLASSNAME):
    return jumppads.PushVolume(mins=np.zeros(3), maxs=np.ones(3),
                               velocity=np.asarray(velocity, dtype='d'),
                               classname=classname)


def test_a_map_with_no_push_volumes_says_so():
    assert jumppads.describe([]) == 'no push volumes'


def test_the_summary_counts_each_kind_of_volume():
    summary = jumppads.describe([
        _volume((0, 0, 1000)),
        _volume((0, 0, 1000), jumppads.MONSTERJUMP_CLASSNAME)])
    assert '1 trigger_push' in summary
    assert '1 trigger_monsterjump' in summary


def test_the_summary_calls_out_freeze_volumes():
    """SPEC-TRIGGER-PUSH §3.6: worth naming, since it looks like a broken pad."""
    summary = jumppads.describe([_volume((0, 0, 0))])
    assert 'freeze volumes' in summary


def test_a_shader_file_that_cannot_be_read_is_skipped(tmp_path, caplog):
    from twig_bb import q3shader
    (tmp_path / 'scripts').mkdir()
    (tmp_path / 'scripts' / 'broken.shader').mkdir()
    with caplog.at_level('WARNING'):
        assert q3shader.load_scripts([str(tmp_path)]) == {}
    assert any('cannot read' in record.message for record in caplog.records)
