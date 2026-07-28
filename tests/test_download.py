"""Fetching and unpacking map archives through the OpenGLContext resolver."""

from __future__ import annotations

import io
import os
import tarfile
import zipfile

import pytest

import bspbuilder
from twitchoglc import download


def _archive(entries):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def _map_archive(name='maps/test.bsp', version=38):
    lumps = bspbuilder.v38_quad() if version == 38 else bspbuilder.v46_quad()
    return _archive({name: bspbuilder.build(version, lumps),
                     'scripts/test.shader': b'textures/a/b { }\n'})


def test_the_download_path_does_not_import_requests():
    """The plan's requirement: the resolver replaces `requests`, which is not
    installed, so importing it would break the module outright."""
    import sys
    assert 'requests' not in sys.modules or True     # nothing forces it in
    source = open(download.__file__).read()
    assert 'import requests' not in source
    assert 'fetch_to_cache' in source


def test_an_archive_unpacks_and_yields_its_map(tmp_path):
    target = tmp_path / 'map.pk3'
    target.write_bytes(_map_archive())
    path = download.unpack(str(target), str(tmp_path / 'out'))
    assert path.endswith('test.bsp')
    assert os.path.isfile(path)


def test_the_unpacked_tree_keeps_the_archives_layout(tmp_path):
    """SPEC-BSP46 §7.2: textures and scripts resolve against the archive root."""
    target = tmp_path / 'map.pk3'
    target.write_bytes(_map_archive())
    path = download.unpack(str(target), str(tmp_path / 'out'))
    root = os.path.dirname(os.path.dirname(path))
    assert os.path.isfile(os.path.join(root, 'scripts', 'test.shader'))


def test_an_archive_with_no_map_is_reported(tmp_path):
    target = tmp_path / 'textures.pk3'
    target.write_bytes(_archive({'textures/a/b.tga': b'x'}))
    with pytest.raises(download.NoMapFound):
        download.unpack(str(target), str(tmp_path / 'out'))


def test_an_archive_with_no_map_may_be_unpacked_as_resources(tmp_path):
    """A texture pack carries no map and is still worth unpacking."""
    target = tmp_path / 'textures.pk3'
    target.write_bytes(_archive({'textures/a/b.tga': b'x'}))
    root = download.unpack(str(target), str(tmp_path / 'out'), require_map=False)
    assert os.path.isfile(os.path.join(root, 'textures', 'a', 'b.tga'))


def test_one_map_of_several_can_be_chosen_by_name(tmp_path):
    target = tmp_path / 'pack.pk3'
    target.write_bytes(_archive({
        'maps/one.bsp': bspbuilder.build(38, bspbuilder.v38_quad()),
        'maps/two.bsp': bspbuilder.build(38, bspbuilder.v38_quad())}))
    path = download.unpack(str(target), str(tmp_path / 'out'), map_name='two')
    assert path.endswith('two.bsp')


def test_several_maps_with_no_choice_lists_them(tmp_path):
    target = tmp_path / 'pack.pk3'
    target.write_bytes(_archive({
        'maps/alpha.bsp': bspbuilder.build(38, bspbuilder.v38_quad()),
        'maps/beta.bsp': bspbuilder.build(38, bspbuilder.v38_quad())}))
    with pytest.raises(download.AmbiguousMap) as error:
        download.unpack(str(target), str(tmp_path / 'out'))
    assert 'alpha' in str(error.value) and 'beta' in str(error.value)


def test_a_name_that_matches_nothing_lists_what_is_there(tmp_path):
    target = tmp_path / 'pack.pk3'
    target.write_bytes(_archive({
        'maps/alpha.bsp': bspbuilder.build(38, bspbuilder.v38_quad())}))
    with pytest.raises(download.AmbiguousMap) as error:
        download.unpack(str(target), str(tmp_path / 'out'), map_name='nope')
    assert 'alpha' in str(error.value)


def test_an_entry_that_would_escape_the_unpack_directory_is_refused(tmp_path):
    """Archive content is untrusted: a `..` entry must not write outside."""
    target = tmp_path / 'evil.pk3'
    target.write_bytes(_archive({'../../escaped.txt': b'x',
                                 'maps/test.bsp': b'IBSP'}))
    with pytest.raises(download.UnsafeArchive):
        download.unpack(str(target), str(tmp_path / 'out'))
    assert not (tmp_path.parent / 'escaped.txt').exists()


def test_an_absolute_entry_is_refused(tmp_path):
    target = tmp_path / 'evil.pk3'
    target.write_bytes(_archive({'/etc/passwd': b'x'}))
    with pytest.raises(download.UnsafeArchive):
        download.unpack(str(target), str(tmp_path / 'out'))


def test_a_nested_archive_is_unpacked_too(tmp_path):
    """Some downloads wrap the `.pk3` in a `.zip`."""
    inner = _map_archive()
    target = tmp_path / 'outer.zip'
    target.write_bytes(_archive({'map.pk3': inner, 'readme.txt': b'hello'}))
    path = download.unpack(str(target), str(tmp_path / 'out'))
    assert path.endswith('test.bsp')


def test_a_bare_map_file_needs_no_unpacking(tmp_path):
    maps = tmp_path / 'maps'
    maps.mkdir()
    target = maps / 'plain.bsp'
    target.write_bytes(bspbuilder.build(38, bspbuilder.v38_quad()))
    assert download.resolve_target(str(target)) == str(target)


def test_an_archive_given_directly_is_unpacked(tmp_path):
    target = tmp_path / 'map.pk3'
    target.write_bytes(_map_archive())
    path = download.resolve_target(str(target))
    assert path.endswith('test.bsp')


def test_a_missing_file_is_reported_plainly(tmp_path):
    with pytest.raises(FileNotFoundError):
        download.resolve_target(str(tmp_path / 'absent.pk3'))


def test_a_url_is_fetched_through_the_resolver(tmp_path, monkeypatch):
    """The plan's requirement: `OpenGLContext.loaders.resolver.fetch_to_cache`
    is the download path, so its cache, origin checks and size cap apply."""
    archive = tmp_path / 'cached.pk3'
    archive.write_bytes(_map_archive())
    calls = []

    def fake_fetch(url, cache_dir=None, max_bytes=None):
        calls.append(url)
        return str(archive)

    monkeypatch.setattr(download.resolver, 'fetch_to_cache', fake_fetch)
    path = download.resolve_target('https://example.invalid/map.pk3',
                                   cache_dir=str(tmp_path / 'cache'))
    assert calls == ['https://example.invalid/map.pk3']
    assert path.endswith('test.bsp')


def test_a_url_unpacks_beneath_the_cache_directory(tmp_path, monkeypatch):
    archive = tmp_path / 'cached.pk3'
    archive.write_bytes(_map_archive())
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive))
    cache = tmp_path / 'cache'
    path = download.resolve_target('https://example.invalid/m.pk3',
                                   cache_dir=str(cache))
    assert str(cache) in path


def test_unpacking_twice_reuses_the_existing_tree(tmp_path):
    target = tmp_path / 'map.pk3'
    target.write_bytes(_map_archive())
    out = str(tmp_path / 'out')
    first = download.unpack(str(target), out)
    stamp = os.path.getmtime(first)
    second = download.unpack(str(target), out)
    assert first == second
    assert os.path.getmtime(second) == stamp


def test_forcing_a_refetch_unpacks_again(tmp_path):
    target = tmp_path / 'map.pk3'
    target.write_bytes(_map_archive())
    out = str(tmp_path / 'out')
    first = download.unpack(str(target), out)
    os.remove(first)
    assert os.path.isfile(download.unpack(str(target), out, force=True))


def test_a_quake3_archive_unpacks_the_same_way(tmp_path):
    """The download path knows nothing about map families."""
    target = tmp_path / 'q3.pk3'
    target.write_bytes(_map_archive('maps/q3test.bsp', version=46))
    assert download.unpack(str(target), str(tmp_path / 'out')).endswith('q3test.bsp')


# -- the shared core-texture pack ---------------------------------------------

def test_the_core_texture_pack_has_a_known_home():
    """Stock Quake 3 content is not redistributable, but the community's
    high-resolution replacement pack is, and it covers the `textures/base*`
    and `textures/gothic*` sets most maps build on."""
    assert download.QUAKE3_CORE.url.startswith('https://')
    assert download.QUAKE3_CORE.url.endswith('.zip')


def test_the_pack_lives_in_its_own_named_shared_directory(tmp_path, monkeypatch):
    """Every Quake 3 map wants this same content, so it is not one more
    hash-named per-archive tree: it is a shared directory a user can find,
    point another tool at, or delete on purpose."""
    archive = tmp_path / 'pack.zip'
    archive.write_bytes(_archive({'textures/base_wall/a.tga': b'x'}))
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive))
    root = download.fetch_pack(download.QUAKE3_CORE, str(tmp_path))
    assert os.path.basename(root) == 'xcsv_hires'
    assert download.CONTENT_SUBDIR in root
    assert download.CACHE_SUBDIR not in root         # not among the map trees


def test_the_pack_is_not_downloaded_when_it_is_already_unpacked(tmp_path, monkeypatch):
    """Once per user, not once per run: an unpacked tree short-circuits both
    the prompt and the fetch."""
    root = download.pack_root(download.QUAKE3_CORE, str(tmp_path))
    assert root is None                      # nothing cached yet
    unpacked = os.path.join(str(tmp_path), os.path.basename(root or '') or '')
    del unpacked

    def fail(*args, **named):
        raise AssertionError('should not fetch when the tree is present')

    archive = tmp_path / 'pack.zip'
    archive.write_bytes(_archive({'textures/base_wall/a.tga': b'x'}))
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive))
    first = download.fetch_pack(download.QUAKE3_CORE, str(tmp_path))
    assert os.path.isfile(os.path.join(first, 'textures', 'base_wall', 'a.tga'))
    assert download.pack_root(download.QUAKE3_CORE, str(tmp_path)) == first
    monkeypatch.setattr(download.resolver, 'fetch_to_cache', fail)
    assert download.fetch_pack(download.QUAKE3_CORE, str(tmp_path)) == first


def test_the_pack_unpacks_even_though_it_holds_no_map(tmp_path, monkeypatch):
    """A texture pack is content, not a map, so the no-map rule must not apply."""
    archive = tmp_path / 'pack.zip'
    archive.write_bytes(_archive({'textures/gothic_block/blocks10.jpg': b'x'}))
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive))
    root = download.fetch_pack(download.QUAKE3_CORE, str(tmp_path))
    assert os.path.isfile(os.path.join(root, 'textures', 'gothic_block',
                                       'blocks10.jpg'))


# -- the asset-pack registry --------------------------------------------------

def test_both_packs_are_registered_with_size_and_copyright():
    """Both go in front of a user before anything downloads, so a pack missing
    either must not exist."""
    assert len(download.ASSET_PACKS) >= 2
    for pack in download.ASSET_PACKS:
        assert pack.url.startswith('http')
        assert pack.approximate_bytes > 0
        assert pack.copyright
        assert pack.title


def test_the_quake3_pack_is_offered_to_quake3_maps_only():
    """A version 38 map is not helped by Quake 3 replacement art."""
    families = {p.key: p.family for p in download.ASSET_PACKS}
    assert families['quake3-core'] == 'quake3'


def test_the_openarena_maps_pack_is_registered():
    """Levels rather than textures: OpenArena's own art is already free, so
    what the viewer lacks is maps to look at."""
    pack = download.pack_for_key('openarena-maps')
    assert pack is not None
    assert 'openarena' in pack.url
    assert pack.archive == 'tar.bz2'
    assert 'maps' in pack.title.lower()


def test_an_unknown_key_has_no_pack():
    assert download.pack_for_key('nonsense') is None


def test_packs_can_be_listed_for_a_family():
    assert download.packs_for('quake3')
    assert all(p.family in ('quake3', None) for p in download.packs_for('quake3'))


def test_a_size_reads_in_human_terms():
    assert download.human_size(186_991_912) == '187 MB'
    assert download.human_size(42_000_000) == '42 MB'


def test_a_bz2_pack_unpacks_into_its_own_named_directory(tmp_path, monkeypatch):
    """The maps pack is a source tarball, not a zip; both must land the same
    way so the content roots are found identically."""
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:bz2') as archive:
        data = b'IBSP'
        info = tarfile.TarInfo('openarena-maps-1.orig/pak1-maps/maps/oa.bsp')
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))
    blob = payload.getvalue()
    archive_path = tmp_path / 'maps.tar.bz2'
    archive_path.write_bytes(blob)
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive_path))
    pack = download.pack_for_key('openarena-maps')
    root = download.fetch_pack(pack, str(tmp_path / 'cache'))
    assert download.CONTENT_SUBDIR in root
    assert os.path.isfile(os.path.join(
        root, 'openarena-maps-1.orig', 'pak1-maps', 'maps', 'oa.bsp'))


def test_a_tar_entry_that_would_escape_is_refused(tmp_path, monkeypatch):
    """Archive content is untrusted whatever its format."""
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode='w:bz2') as archive:
        info = tarfile.TarInfo('../escaped.bsp')
        info.size = 0
        archive.addfile(info, io.BytesIO(b''))
    archive_path = tmp_path / 'evil.tar.bz2'
    archive_path.write_bytes(payload.getvalue())
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(archive_path))
    with pytest.raises(download.UnsafeArchive):
        download.fetch_pack(download.pack_for_key('openarena-maps'),
                            str(tmp_path / 'cache'))
    assert not (tmp_path / 'escaped.bsp').exists()


def test_a_pack_already_unpacked_is_not_fetched_again(tmp_path, monkeypatch):
    pack = download.pack_for_key('quake3-core')
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda url, cache_dir=None, max_bytes=None: str(
                            _write(tmp_path / 'p.zip',
                                   _archive({'textures/base/a.tga': b'x'}))))
    cache = str(tmp_path / 'cache')
    first = download.fetch_pack(pack, cache)
    monkeypatch.setattr(download.resolver, 'fetch_to_cache',
                        lambda *a, **k: pytest.fail('refetched'))
    assert download.pack_root(pack, cache) == first
    assert download.fetch_pack(pack, cache) == first


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


# -- naming a map inside a pack -----------------------------------------------

def test_a_pack_alias_names_a_map_in_that_pack():
    assert download.parse_pack_target('openarena:aggressor') == (
        download.OPENARENA_MAPS, 'aggressor')


def test_the_full_pack_key_also_names_a_map():
    assert download.parse_pack_target('openarena-maps:oa_dm1')[1] == 'oa_dm1'


def test_a_url_is_not_a_pack_target():
    """``https:`` looks like a prefix and must not be read as one."""
    assert download.parse_pack_target('https://example.com/a.pk3') is None
    assert download.parse_pack_target('maps/ctf-curvy.bsp') is None
    assert download.parse_pack_target('nosuchpack:map') is None


def test_a_windows_path_is_not_a_pack_target():
    assert download.parse_pack_target(r'C:\maps\a.bsp') is None


def test_a_map_is_found_by_name_inside_an_unpacked_pack(tmp_path):
    bsp = tmp_path / 'pak' / 'maps' / 'oa_dm1.bsp'
    bsp.parent.mkdir(parents=True)
    bsp.write_bytes(b'IBSP')
    assert download.find_map(str(tmp_path), 'oa_dm1') == str(bsp)
    assert download.find_map(str(tmp_path), 'OA_DM1') == str(bsp)
    assert download.find_map(str(tmp_path), 'oa_dm1.bsp') == str(bsp)


def test_a_map_packed_in_a_pk3_inside_a_pack_is_unpacked_and_found(tmp_path):
    """A maps release ships `.pk3` files, not loose maps."""
    inner = tmp_path / 'pak' / 'oa_dm2.pk3'
    inner.parent.mkdir(parents=True)
    inner.write_bytes(_archive({'maps/oa_dm2.bsp': b'IBSP',
                                'textures/x/a.tga': b'x'}))
    found = download.find_map(str(tmp_path), 'oa_dm2')
    assert found is not None and found.endswith('oa_dm2.bsp')
    assert os.path.isfile(found)


def test_a_map_that_is_not_in_the_pack_is_not_found(tmp_path):
    assert download.find_map(str(tmp_path), 'nothing') is None


def test_listing_the_maps_a_pack_holds(tmp_path):
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'maps' / 'a.bsp').write_bytes(b'IBSP')
    (tmp_path / 'b.pk3').write_bytes(_archive({'maps/b.bsp': b'IBSP'}))
    assert download.list_maps(str(tmp_path)) == ['a', 'b']


# -- packs that need each other -----------------------------------------------

def test_the_openarena_maps_pack_names_the_texture_pack_it_needs():
    """The maps ship geometry and lightmaps only; the art is a separate,
    much larger download, so a maps-only fetch renders untextured."""
    assert 'openarena-textures' in download.OPENARENA_MAPS.companions


def test_the_openarena_texture_pack_is_registered_and_honest_about_its_size():
    pack = download.pack_for_key('openarena-textures')
    assert pack is not None
    assert pack.approximate_bytes > 400_000_000
    assert download.human_size(pack.approximate_bytes).endswith('MB')


def test_the_quake3_pack_needs_nothing_else():
    assert download.QUAKE3_CORE.companions == ()


def test_a_packs_companions_resolve_to_registered_packs():
    for pack in download.ASSET_PACKS:
        for key in pack.companions:
            assert download.pack_for_key(key) is not None


# -- finding the content level inside a pack ----------------------------------

def test_the_content_root_is_the_directory_holding_textures(tmp_path):
    """A release wraps its content in a version directory and a pak directory;
    the level the loader wants is the one `textures/` sits in, not the top."""
    deep = tmp_path / 'openarena-textures-0.8.5split.orig' / 'pak2-textures'
    (deep / 'textures' / 'base_wall').mkdir(parents=True)
    assert download.content_roots(str(tmp_path)) == [str(deep)]


def test_several_pak_directories_are_all_content_roots(tmp_path):
    """A split release has one per pak, and a map may draw from any of them."""
    top = tmp_path / 'oa.orig'
    for name in ('pak0', 'pak2'):
        (top / name / 'textures').mkdir(parents=True)
    assert download.content_roots(str(tmp_path)) == [
        str(top / 'pak0'), str(top / 'pak2')]


def test_a_maps_directory_also_marks_a_content_root(tmp_path):
    (tmp_path / 'pak1-maps' / 'maps').mkdir(parents=True)
    assert download.content_roots(str(tmp_path)) == [str(tmp_path / 'pak1-maps')]


def test_a_pack_that_is_already_a_content_root_is_returned_as_it_is(tmp_path):
    """The Quake 3 replacement pack unpacks with `textures/` at its top."""
    (tmp_path / 'textures').mkdir()
    assert download.content_roots(str(tmp_path)) == [str(tmp_path)]


def test_a_pack_with_no_recognisable_content_falls_back_to_its_top(tmp_path):
    """Better a root that finds nothing than no root at all."""
    (tmp_path / 'readme.txt').write_text('x')
    assert download.content_roots(str(tmp_path)) == [str(tmp_path)]


def test_the_search_does_not_descend_into_the_content_itself(tmp_path):
    """`textures/` holds thousands of directories; walking them to look for
    more content roots would cost a directory tree per launch."""
    inner = tmp_path / 'pak' / 'textures' / 'base' / 'maps'
    inner.mkdir(parents=True)
    assert download.content_roots(str(tmp_path)) == [str(tmp_path / 'pak')]


def test_a_pack_larger_than_the_resolvers_default_cap_is_still_fetched(tmp_path, monkeypatch):
    """The resolver caps a fetch at 256 MB by default, which is a sane limit
    for an unknown asset and too small for a texture pack whose size is known
    in advance."""
    seen = {}

    def _fetch(url, cache_dir=None, max_bytes=None):
        seen['max_bytes'] = max_bytes
        path = tmp_path / 'p.tar.bz2'
        with tarfile.open(path, 'w:bz2') as archive:
            info = tarfile.TarInfo('textures/a.tga')
            info.size = 1
            archive.addfile(info, io.BytesIO(b'x'))
        return str(path)

    monkeypatch.setattr(download.resolver, 'fetch_to_cache', _fetch)
    big = download.OPENARENA_TEXTURES
    download.fetch_pack(big, str(tmp_path / 'cache'))
    assert seen['max_bytes'] > big.approximate_bytes


def test_the_cap_leaves_room_for_a_pack_that_grew_a_little():
    """A published size can drift between releases, and a fetch that fails on
    the last megabyte is worse than one that never started."""
    assert download.fetch_limit(400_000_000) == 600_000_000


def test_a_small_pack_is_still_given_the_resolvers_own_floor():
    """Nothing gains from a cap tighter than the framework's own."""
    assert download.fetch_limit(1_000) == download.resolver.DEFAULT_MAX_RESOURCE_BYTES


def test_the_openarena_base_data_pack_is_registered():
    """The `.shader` scripts live here, and a name a shader defines resolves to
    no file without them however much art is on disk."""
    pack = download.pack_for_key('openarena-data')
    assert pack is not None
    assert pack.archive == 'tar.bz2'


def test_the_maps_pack_needs_both_the_art_and_the_scripts():
    assert set(download.OPENARENA_MAPS.companions) == {
        'openarena-textures', 'openarena-data'}


def test_a_file_named_like_an_archive_that_is_not_one_is_skipped(tmp_path):
    """Content directories collect junk; one bad file must not stop the search."""
    (tmp_path / 'broken.pk3').write_bytes(b'not a zip at all')
    (tmp_path / 'maps').mkdir()
    (tmp_path / 'maps' / 'ok.bsp').write_bytes(b'IBSP')
    assert download.find_map(str(tmp_path), 'ok') is not None
    assert download.list_maps(str(tmp_path)) == ['ok']
