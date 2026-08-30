"""The content catalogue: what this build offers to download, and on what terms.

A data file rather than a list in the code, so a pack can be added or corrected
without touching Python.  What is tested here is the loading, the validation
that keeps a pack from being offered without stating its terms, and the two
promises §10's acknowledgements screen is generated against.
"""

from __future__ import annotations

import json

import pytest

from twig_bb import catalog, download


class TestTheShippedCatalogue:

    def test_it_loads(self):
        assert catalog.load()

    def test_every_pack_states_its_terms(self):
        """§10 is generated from this field, so a blank one ships art unattributed.

        The reason `copyright` is mandatory rather than a comment: a pack added
        without it would appear in the download list and *not* in the notices,
        which is the one failure mode the notices exist to prevent.
        """
        assert all(pack.copyright.strip() for pack in catalog.load())

    def test_every_pack_states_a_size_before_anything_is_fetched(self):
        """The user consents to a number of megabytes, so there has to be one."""
        assert all(pack.approximate_bytes > 0 for pack in catalog.load())

    def test_every_pack_has_a_distinct_key(self):
        keys = [pack.key for pack in catalog.load()]
        assert len(set(keys)) == len(keys)

    def test_every_pack_has_a_distinct_directory(self):
        """Two packs unpacking into one directory would overwrite each other."""
        directories = [pack.directory for pack in catalog.load()]
        assert len(set(directories)) == len(directories)

    def test_every_companion_names_a_registered_pack(self):
        """A dangling companion key is a download that silently does half a job."""
        keys = {pack.key for pack in catalog.load()}
        for pack in catalog.load():
            assert set(pack.companions) <= keys, pack.key

    def test_every_url_is_https(self):
        """Content is untrusted either way, but plain http is a free downgrade."""
        assert all(pack.url.startswith('https://') for pack in catalog.load())

    def test_the_community_map_pack_is_registered(self):
        """Identified as available and unoffered for long enough."""
        assert catalog.pack_for_key('openarena-oacmp1') is not None

    def test_no_pack_offers_alien_arena_base_art(self):
        """Its art is licensed for its own engine only; the symmetry is false."""
        assert not [pack for pack in catalog.load()
                    if 'alien' in (pack.key + pack.title).lower()]


class TestLoadingAFile:

    def write(self, tmp_path, packs):
        path = tmp_path / 'packs.json'
        path.write_text(json.dumps({'packs': packs}))
        return str(path)

    def minimal(self, **named):
        entry = {
            'key': 'sample', 'title': 'A sample pack',
            'url': 'https://example.com/sample.zip', 'directory': 'sample',
            'archive': 'zip', 'approximate_bytes': 1000,
            'copyright': 'Nobody, public domain', 'marker': '',
        }
        entry.update(named)
        return entry

    def test_a_pack_reads_back_with_its_fields(self, tmp_path):
        packs = catalog.load(self.write(tmp_path, [self.minimal()]))
        assert packs[0].key == 'sample'
        assert packs[0].approximate_bytes == 1000

    def test_the_optional_fields_have_defaults(self, tmp_path):
        pack = catalog.load(self.write(tmp_path, [self.minimal()]))[0]
        assert pack.companions == ()
        assert pack.family is None

    def test_companions_read_back_as_a_tuple(self, tmp_path):
        """Frozen, because a pack is hashable and lives in sets."""
        entry = self.minimal(companions=['other'])
        assert catalog.load(self.write(tmp_path, [entry]))[0].companions == ('other',)

    def test_a_pack_with_no_copyright_is_refused(self, tmp_path):
        path = self.write(tmp_path, [self.minimal(copyright='')])
        with pytest.raises(catalog.BadCatalog):
            catalog.load(path)

    def test_a_pack_missing_a_required_field_is_refused(self, tmp_path):
        entry = self.minimal()
        del entry['url']
        with pytest.raises(catalog.BadCatalog):
            catalog.load(self.write(tmp_path, [entry]))

    def test_a_pack_with_a_field_nobody_declared_is_refused(self, tmp_path):
        """A typo in a key would otherwise be silently ignored for ever."""
        with pytest.raises(catalog.BadCatalog):
            catalog.load(self.write(tmp_path, [self.minimal(copyrite='oops')]))

    def test_a_file_that_is_not_json_says_so(self, tmp_path):
        path = tmp_path / 'packs.json'
        path.write_text('{not json')
        with pytest.raises(catalog.BadCatalog):
            catalog.load(str(path))

    def test_a_missing_file_says_so(self, tmp_path):
        with pytest.raises(catalog.BadCatalog):
            catalog.load(str(tmp_path / 'absent.json'))

    def test_the_comment_key_is_not_a_pack(self, tmp_path):
        """The file documents itself; that must not become an entry."""
        path = tmp_path / 'packs.json'
        path.write_text(json.dumps({'_comment': ['notes'],
                                    'packs': [self.minimal()]}))
        assert len(catalog.load(str(path))) == 1


class TestWhatTheRestOfTheViewerSees:
    """The catalogue is the source; ``download`` keeps its existing interface."""

    def test_the_registered_packs_come_from_the_catalogue(self):
        assert {pack.key for pack in download.ASSET_PACKS} == \
            {pack.key for pack in catalog.load()}

    def test_a_pack_is_still_found_by_key(self):
        assert download.pack_for_key('openarena-maps') is not None

    def test_an_unregistered_key_is_still_none(self):
        assert download.pack_for_key('nothing-of-the-sort') is None

    def test_packs_are_still_filtered_by_family(self):
        assert all(pack.family in ('quake3', None)
                   for pack in download.packs_for('quake3'))

    def test_the_short_name_still_reaches_the_maps_pack(self):
        found = download.parse_pack_target('openarena:oa_dm1')
        assert found is not None and found[0].key == 'openarena-maps'


# -- the Unvanquished family -------------------------------------------------

def _unvanquished():
    return [pack for pack in catalog.load() if pack.family == 'unvanquished']


def test_the_unvanquished_packs_are_registered():
    """SPEC-UNVDIST §3.1: the packages whose terms are stated in the archive."""
    keys = {pack.key for pack in _unvanquished()}
    assert 'unvanquished-plat23' in keys
    assert 'unvanquished-tex-pk02' in keys


def test_no_unvanquished_pack_lacks_stated_terms():
    """SPEC-UNVDIST §1.5, §3.4: nine packages state no licence anywhere.

    They hold the player, buildable and weapon models, the voices and the
    soundtrack, and they are deliberately absent. A pack that cannot state its
    terms would be offered for download and left out of the acknowledgements,
    which is the one thing `copyright` exists to prevent.
    """
    unlicensed = ('res-players', 'res-buildables', 'res-weapons', 'res-voices',
                  'res-soundtrack', 'res-ambient', 'res-legacy', 'tex-all')
    urls = ' '.join(pack.url for pack in catalog.load())
    for name in unlicensed:
        assert name not in urls, '%s states no licence and must not be offered' % (name,)


def test_the_base_package_is_not_offered():
    """SPEC-UNVDIST §1.4: a mixed tree carrying GPLv3 game-logic binaries."""
    assert 'unvanquished_0.56' not in ' '.join(pack.url for pack in catalog.load())


def test_every_unvanquished_map_names_the_art_it_needs():
    """SPEC-DPK §4: a map package carries no art, so it is nothing on its own."""
    packs = {pack.key: pack for pack in catalog.load()}
    for pack in _unvanquished():
        if pack.marker != 'maps':
            continue
        assert pack.companions, '%s would render in grey' % (pack.key,)
        for key in pack.companions:
            assert key in packs, '%s names %s, which is not registered' % (pack.key, key)


def test_the_smallest_playable_set_is_the_measured_size():
    """SPEC-UNVDIST §4.5: Platform 23 and its closure, 43890648 bytes."""
    packs = {pack.key: pack for pack in catalog.load()}
    plat23 = packs['unvanquished-plat23']
    total = plat23.approximate_bytes + sum(
        packs[key].approximate_bytes for key in plat23.companions)
    assert total == 43890648
