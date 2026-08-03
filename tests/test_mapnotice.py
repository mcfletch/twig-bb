"""What a running map is, and under whose terms it is being played.

A level is somebody's work, fetched under a licence that asks for attribution.
The acknowledgements screen already credits the *pack*; a player standing in a
map wants to know which map, by whom, and under what terms, without having to
work out which of five packs it came from.

Three separable things, and each has its own tests here: reading what the
mapper embedded in the map, finding the licence documents that travel with the
content, and putting the result at the top of the acknowledgements.
"""

from __future__ import annotations

import os

import pytest

from twig_bb import mapnotice
from twig_bb.assetpack import AssetPack


class _Bsp:
    def __init__(self, entities):
        self.entities = entities


class _Entity(dict):
    @property
    def classname(self):
        return self.get('classname', '')


class _Map:
    """Only what a notice reads, so these tests need no `.bsp` on disk."""

    def __init__(self, name='amap', path='/content/pak/maps/amap.bsp',
                 message=None, roots=()):
        world = {'classname': 'worldspawn'}
        if message is not None:
            world['message'] = message
        self.name = name
        self.path = path
        self.roots = list(roots)
        self.bsp = _Bsp([_Entity(world)])

    @property
    def entities(self):
        return self.bsp.entities


class TestWhatTheMapperEmbedded:
    """`worldspawn`'s `message` is where a Quake map carries its own title."""

    def test_a_bare_title_is_the_title(self):
        assert mapnotice.title_and_author('House of Cheethon') == (
            'House of Cheethon', '')

    def test_by_names_the_author(self):
        assert mapnotice.title_and_author('GalMevish by Armageddon_Man') == (
            'GalMevish', 'Armageddon_Man')

    def test_a_dash_before_by_is_not_part_of_the_title(self):
        assert mapnotice.title_and_author('Aggressor - by Tyrann') == (
            'Aggressor', 'Tyrann')

    def test_trailing_padding_is_not_part_of_the_name(self):
        """Mappers pad these fields to line up in an editor."""
        assert mapnotice.title_and_author('Aggressor    ') == ('Aggressor', '')

    def test_by_inside_a_word_is_not_an_author(self):
        """`Flyby` is a title, not a map by `y`."""
        assert mapnotice.title_and_author('Flyby') == ('Flyby', '')

    def test_nothing_embedded_is_no_title_rather_than_an_error(self):
        assert mapnotice.title_and_author('') == ('', '')

    def test_a_map_with_no_message_still_yields_a_notice(self):
        """Many maps embed nothing; the notice falls back to the file name."""
        notice = mapnotice.for_map(_Map(name='czest1dm', message=None),
                                   packs=[])
        assert notice.name == 'czest1dm'
        assert notice.title == ''
        assert 'czest1dm' in notice.summary


class TestWhichPackItCameFrom:
    """A map's terms are its pack's terms, and the pack is found by path."""

    #: These packs state absolute directories, so the notice is told to read
    #: them as they are rather than to resolve them against a real cache.
    _where = staticmethod(lambda pack: pack.directory)

    def _pack(self, directory, title='OpenArena maps',
              copyright='OpenArena project, CC BY-SA 3.0'):
        return AssetPack(key=title.lower().replace(' ', '-'), title=title,
                         url='https://example.com/m.zip', directory=directory,
                         archive='zip', approximate_bytes=1,
                         copyright=copyright, marker='')

    def test_a_map_under_a_packs_directory_takes_its_terms(self, tmp_path):
        root = tmp_path / 'openarena-maps'
        maps = root / 'pak1' / 'maps'
        maps.mkdir(parents=True)
        notice = mapnotice.for_map(
            _Map(path=str(maps / 'oa_dm1.bsp')),
            packs=[self._pack(str(root))], directory_of=self._where)
        assert notice.pack == 'OpenArena maps'
        assert notice.licence == 'OpenArena project, CC BY-SA 3.0'

    def test_a_map_of_your_own_claims_no_packs_terms(self, tmp_path):
        """Someone playing their own map is told nothing about OpenArena."""
        root = tmp_path / 'openarena-maps'
        root.mkdir()
        mine = tmp_path / 'mine' / 'maps'
        mine.mkdir(parents=True)
        notice = mapnotice.for_map(_Map(path=str(mine / 'mine.bsp')),
                                   packs=[self._pack(str(root))],
                                   directory_of=self._where)
        assert notice.pack == ''
        assert notice.licence == ''

    def test_the_packs_own_terms_are_found_above_the_content_root(self, tmp_path):
        """A release puts its `COPYING` at its top, not beside the paks.

        The map's texture roots start at the pak, so a search that only looked
        where textures resolve would walk past the licence every time.
        """
        root = tmp_path / 'openarena-maps'
        release = root / 'openarena-0.8.5'
        pak = release / 'pak1-maps'
        (pak / 'maps').mkdir(parents=True)
        (release / 'COPYING').write_text('CC BY-SA', encoding='utf-8')
        notice = mapnotice.for_map(
            _Map(path=str(pak / 'maps' / 'oa_dm1.bsp'), roots=[str(pak)]),
            packs=[self._pack(str(root))], directory_of=self._where)
        assert [os.path.basename(p) for p in notice.documents] == ['COPYING']

    def test_a_texture_packs_terms_are_not_the_maps_own(self, tmp_path):
        """A map resolves textures against packs it did not come from.

        Those roots are on the map's list and carry their own `COPYING`. Under
        a heading that says *its own terms* they are someone else's, and the
        one shown is whichever pack sorted first -- so a map from the community
        pack was citing the replacement-texture licence.
        """
        maps_pack = tmp_path / 'openarena-maps'
        (maps_pack / 'pak1' / 'maps').mkdir(parents=True)
        (maps_pack / 'pak1' / 'COPYING').write_text('CC BY-SA', encoding='utf-8')
        textures = tmp_path / 'quake3-core'
        textures.mkdir()
        (textures / 'COPYING.txt').write_text('CC BY-NC-ND', encoding='utf-8')
        notice = mapnotice.for_map(
            _Map(path=str(maps_pack / 'pak1' / 'maps' / 'oa_dm1.bsp'),
                 roots=[str(maps_pack / 'pak1'), str(textures)]),
            packs=[self._pack(str(maps_pack)),
                   self._pack(str(textures), title='Replacement textures',
                              copyright='Kpax, CC BY-NC-ND 3.0')],
            directory_of=self._where)
        assert [os.path.basename(p) for p in notice.documents] == ['COPYING']
        # Not its own terms, but not discarded either: the textures on screen
        # are that pack's, and it says so under its own heading.
        assert notice.drawn_with == (('Replacement textures',
                                      'Kpax, CC BY-NC-ND 3.0'),)

    def test_a_map_of_your_own_claims_no_borrowed_packs_terms(self, tmp_path):
        """Playing your own map against fetched textures cites neither wrongly."""
        textures = tmp_path / 'quake3-core'
        textures.mkdir()
        (textures / 'COPYING.txt').write_text('CC BY-NC-ND', encoding='utf-8')
        mine = tmp_path / 'mine'
        (mine / 'maps').mkdir(parents=True)
        (mine / 'LICENSE').write_text('mine', encoding='utf-8')
        notice = mapnotice.for_map(
            _Map(path=str(mine / 'maps' / 'mine.bsp'),
                 roots=[str(mine), str(textures)]),
            packs=[self._pack(str(textures), title='Replacement textures',
                              copyright='Kpax, CC BY-NC-ND 3.0')],
            directory_of=self._where)
        assert [os.path.basename(p) for p in notice.documents] == ['LICENSE']
        assert notice.drawn_with == (('Replacement textures',
                                      'Kpax, CC BY-NC-ND 3.0'),)

    def test_a_sibling_directory_is_not_a_parent(self, tmp_path):
        """`openarena-maps-old` must not match `openarena-maps`."""
        root = tmp_path / 'openarena-maps'
        root.mkdir()
        other = tmp_path / 'openarena-maps-old' / 'maps'
        other.mkdir(parents=True)
        notice = mapnotice.for_map(_Map(path=str(other / 'x.bsp')),
                                   packs=[self._pack(str(root))],
                                   directory_of=self._where)
        assert notice.pack == ''


class TestTheLicenceDocumentsThatTravelWithIt:
    """A pack ships its own `COPYING`; the notice says where it is."""

    def test_a_licence_file_beside_the_content_is_found(self, tmp_path):
        (tmp_path / 'COPYING').write_text('GPL', encoding='utf-8')
        (tmp_path / 'CREDITS').write_text('everyone', encoding='utf-8')
        found = mapnotice.licence_documents([str(tmp_path)])
        assert sorted(os.path.basename(p) for p in found) == ['COPYING',
                                                              'CREDITS']

    def test_content_that_is_not_a_licence_is_left_out(self, tmp_path):
        (tmp_path / 'COPYING').write_text('GPL', encoding='utf-8')
        (tmp_path / 'pak0.pk3').write_bytes(b'PK')
        found = mapnotice.licence_documents([str(tmp_path)])
        assert [os.path.basename(p) for p in found] == ['COPYING']

    def test_a_root_that_is_not_there_is_not_an_error(self, tmp_path):
        """The notice is wanted most when something is half-built."""
        assert mapnotice.licence_documents([str(tmp_path / 'gone')]) == []

    def test_the_same_document_reached_by_two_roots_is_listed_once(self, tmp_path):
        (tmp_path / 'COPYING').write_text('GPL', encoding='utf-8')
        found = mapnotice.licence_documents([str(tmp_path), str(tmp_path)])
        assert len(found) == 1

    def test_a_documents_directory_is_searched_one_level_down(self, tmp_path):
        """A release commonly wraps its content in a version directory."""
        inner = tmp_path / 'openarena-0.8.5'
        inner.mkdir()
        (inner / 'LICENSE.txt').write_text('CC BY-SA', encoding='utf-8')
        found = mapnotice.licence_documents([str(tmp_path)])
        assert [os.path.basename(p) for p in found] == ['LICENSE.txt']


class TestHowItReads:
    """One line for the screen furniture, a block for the acknowledgements."""

    def test_the_summary_names_the_map_and_its_author(self):
        notice = mapnotice.MapNotice(name='aggressor', title='Aggressor',
                                     author='Tyrann')
        assert 'Aggressor' in notice.summary and 'Tyrann' in notice.summary

    def test_the_summary_stays_inside_the_huds_alphabet(self):
        """The HUD font is ASCII; a dash it has no glyph for draws as `?`."""
        notice = mapnotice.MapNotice(name='aggressor', title='Aggressor',
                                     author='Tyrann')
        assert notice.summary.isascii()

    def test_the_credit_names_the_map_and_states_the_terms(self):
        lines = mapnotice.MapNotice(
            name='oa_dm1', title='Aggressor', author='Tyrann',
            licence='CC BY-SA 3.0').credit_lines()
        assert lines[0] == 'Aggressor, by Tyrann'
        assert 'CC BY-SA 3.0' in ' '.join(lines[1:])

    def test_a_long_licence_is_wrapped_rather_than_cut(self):
        """Truncating would state weaker terms than the content carries."""
        licence = 'OpenArena project, CC BY-SA 3.0 / GPL; Debian main'
        lines = mapnotice.MapNotice(name='oa_dm1',
                                    licence=licence).credit_lines(width=32)
        assert all(len(line) <= 32 for line in lines)
        assert ' '.join(lines[1:]) == licence

    def test_a_map_with_no_terms_credits_only_itself(self):
        assert mapnotice.MapNotice(name='oa_dm1').credit_lines() == ['oa_dm1']

    def test_the_block_keeps_the_terms_in_full(self):
        """The screen abbreviates; the acknowledgements do not."""
        licence = 'OpenArena project, CC BY-SA 3.0 / GPL; Debian main'
        assert licence in mapnotice.MapNotice(name='oa_dm1',
                                              licence=licence).text()

    def test_the_summary_falls_back_to_the_file_name(self):
        assert mapnotice.MapNotice(name='oa_dm1').summary == 'oa_dm1'

    def test_the_block_states_the_terms(self):
        notice = mapnotice.MapNotice(name='oa_dm1', title='Big Arena',
                                     author='Somebody', pack='OpenArena maps',
                                     licence='CC BY-SA 3.0')
        text = notice.text()
        assert 'Big Arena' in text
        assert 'Somebody' in text
        assert 'OpenArena maps' in text
        assert 'CC BY-SA 3.0' in text

    def test_the_block_names_what_it_is_drawn_with_separately(self):
        """A map's textures may be a pack with stricter terms than the map's.

        `xcsv_hires` is CC BY-NC-ND: a player who may not know they are
        looking at it is a player who cannot honour it.
        """
        notice = mapnotice.MapNotice(
            name='oa_dm1', pack='OpenArena maps', licence='CC BY-SA 3.0',
            drawn_with=(('Quake 3 replacement textures', 'CC BY-NC-ND 3.0'),))
        text = notice.text()
        assert 'Quake 3 replacement textures' in text
        assert 'CC BY-NC-ND 3.0' in text
        # Its own terms first, and the borrowed content plainly not those.
        assert text.index('CC BY-SA 3.0') < text.index('CC BY-NC-ND 3.0')

    def test_a_map_drawn_with_nothing_borrowed_grows_no_heading(self):
        assert 'Drawn with' not in mapnotice.MapNotice(name='oa_dm1').text()

    def test_the_block_points_at_the_documents(self):
        notice = mapnotice.MapNotice(name='oa_dm1',
                                     documents=('/content/COPYING',))
        assert '/content/COPYING' in notice.text()

    def test_a_map_with_nothing_known_still_names_itself(self):
        """Better a bare name than a heading with nothing under it."""
        assert 'oa_dm1' in mapnotice.MapNotice(name='oa_dm1').text()


class TestAtTheTopOfTheAcknowledgements:
    """What is being played comes before what it is built on."""

    def test_the_running_map_is_named_before_the_libraries(self):
        from twig_bb import notices
        notice = mapnotice.MapNotice(name='oa_dm1', title='Big Arena',
                                     licence='CC BY-SA 3.0')
        text = notices.full_text(current=notice)
        assert text.index('Big Arena') < text.index(
            'Libraries this program is built on')

    def test_the_terms_of_the_running_map_are_in_it(self):
        from twig_bb import notices
        notice = mapnotice.MapNotice(name='oa_dm1', licence='CC BY-SA 3.0')
        assert 'CC BY-SA 3.0' in notices.full_text(current=notice)

    def test_with_no_map_running_the_screen_is_what_it_was(self):
        from twig_bb import notices
        assert notices.full_text(current=None) == notices.full_text()


class TestCalledOutWhenTheMapStarts:
    """A player is told what they are standing in, on the screen they are on."""

    class _HUD:
        def __init__(self):
            self.posted = []

        def post(self, text):
            self.posted.append(text)

    def _context(self, notice):
        from twig_bb import viewer

        class _Context:
            pass

        context = _Context()
        context.notice = notice
        context.hud = self._HUD()
        viewer.TwigContext._creditMap(context)
        return context.hud.posted

    def test_the_map_names_itself(self):
        posted = self._context(mapnotice.MapNotice(name='oa_dm1',
                                                   title='Big Arena'))
        assert any('Big Arena' in line for line in posted)

    def test_its_terms_are_said_out_loud(self):
        posted = self._context(mapnotice.MapNotice(name='oa_dm1',
                                                   licence='CC BY-SA 3.0'))
        assert any('CC BY-SA 3.0' in line for line in posted)

    def test_what_is_posted_fits_a_line(self):
        """`MessageQueue` does not wrap: a long line runs off the screen."""
        posted = self._context(mapnotice.MapNotice(
            name='oa_dm1', title='Aggressor', author='Tyrann',
            licence='OpenArena project, CC BY-SA 3.0 / GPL; Debian main'))
        assert posted and all(len(line) <= mapnotice.CREDIT_WIDTH
                              for line in posted)

    def test_it_reads_downwards_from_the_map_name(self):
        """The queue shows newest first, so the credit is posted backwards."""
        posted = self._context(mapnotice.MapNotice(
            name='oa_dm1', title='Aggressor', licence='CC BY-SA 3.0'))
        assert posted[-1] == 'Aggressor'

    def test_a_map_that_states_no_terms_says_only_its_name(self):
        posted = self._context(mapnotice.MapNotice(name='mine'))
        assert posted == ['mine']

    def test_no_notice_yet_posts_nothing_rather_than_failing(self):
        assert self._context(None) == []


@pytest.mark.sample
class TestAgainstRealMaps:
    """The embedded titles these rules were written from."""

    def test_a_fetched_map_yields_a_notice_with_its_pack(self):
        from twig_bb import download, maploader
        root = download.pack_root(download.pack_for_key('openarena-maps'))
        if not root:
            pytest.skip('openarena-maps is not fetched')
        import glob
        found = glob.glob(os.path.join(root, '**', 'maps', '*.bsp'),
                          recursive=True)
        if not found:
            pytest.skip('no maps in the fetched pack')
        notice = mapnotice.for_map(maploader.load(sorted(found)[0]))
        assert notice.pack == 'OpenArena maps (50 levels)'
        assert 'CC BY-SA' in notice.licence
        assert 'COPYING' in ' '.join(notice.documents)
