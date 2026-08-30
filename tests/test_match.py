"""What a match is: the level, the opponents and the rules that end it.

A declared node with typed fields rather than a bag of arguments, for the same
reason the movement modes and the weapon table are: a settings screen can
present it with no knowledge of this game, a variant can retune it by setting
fields, and it can be saved and read back.

It is also the record §6's bots and §7's scoring both read, so it is worth
getting right before either exists.
"""

from __future__ import annotations

import json

import pytest

from twig_bb import match


class TestTheDefaults:
    """Launching with nothing chosen has to be a reasonable thing to do."""

    def test_a_fresh_setup_is_playable(self):
        assert match.MatchSetup().bots >= 1

    def test_the_default_difficulty_is_a_named_preset(self):
        assert match.MatchSetup().difficulty in match.DIFFICULTIES

    def test_the_default_is_neither_the_easiest_nor_the_hardest(self):
        """Nightmare unasked-for is a bad first impression; so is near-passive."""
        index = match.DIFFICULTIES.index(match.MatchSetup().difficulty)
        assert 0 < index < len(match.DIFFICULTIES) - 1

    def test_a_match_ends_by_default(self):
        """A deathmatch with no limit at all never finishes."""
        setup = match.MatchSetup()
        assert setup.fragLimit > 0 or setup.timeLimit > 0


class TestTheRange:

    def test_the_difficulties_run_from_near_passive_to_nightmare(self):
        assert match.DIFFICULTIES[0] == 'near-passive'
        assert match.DIFFICULTIES[-1] == 'nightmare'

    def test_the_bot_count_is_bounded(self):
        """A number field a settings screen can present needs a range."""
        hints = match.MatchSetup.UI_HINTS['bots']
        assert hints['minimum'] >= 0
        assert hints['maximum'] >= 1

    def test_no_bots_is_allowed(self):
        """Walking a level with nothing shooting at you is a real thing to want."""
        assert match.MatchSetup(bots=0).bots == 0


class TestValidating:

    def test_a_difficulty_nobody_declared_is_refused(self):
        with pytest.raises(ValueError):
            match.validate(match.MatchSetup(difficulty='impossible'))

    def test_a_negative_bot_count_is_refused(self):
        with pytest.raises(ValueError):
            match.validate(match.MatchSetup(bots=-1))

    def test_a_match_with_no_end_is_refused(self):
        with pytest.raises(ValueError):
            match.validate(match.MatchSetup(fragLimit=0, timeLimit=0))

    def test_a_time_limit_alone_is_an_end(self):
        match.validate(match.MatchSetup(fragLimit=0, timeLimit=10.0))

    def test_the_defaults_validate(self):
        match.validate(match.MatchSetup())


class TestRememberingTheLastChoice:
    """Offered again first, because it is what a returning player wants."""

    def test_a_saved_setup_reads_back(self, tmp_path):
        path = str(tmp_path / 'match.json')
        match.save(match.MatchSetup(level='openarena-maps:oa_dm1', bots=3,
                                    difficulty='hard'), path)
        recalled = match.recall(path)
        assert (recalled.level, recalled.bots, recalled.difficulty) == \
            ('openarena-maps:oa_dm1', 3, 'hard')

    def test_recalling_nothing_gives_the_defaults(self, tmp_path):
        """A first launch must not be a failure to start."""
        recalled = match.recall(str(tmp_path / 'never-written.json'))
        assert recalled.bots == match.MatchSetup().bots

    def test_a_corrupt_file_gives_the_defaults(self, tmp_path):
        """A settings file nobody can parse must not be a game nobody can start."""
        path = tmp_path / 'match.json'
        path.write_text('{ not json')
        assert match.recall(str(path)).bots == match.MatchSetup().bots

    def test_a_saved_difficulty_that_is_no_longer_declared_is_dropped(self, tmp_path):
        """A preset removed between versions must not poison a saved choice."""
        path = tmp_path / 'match.json'
        path.write_text(json.dumps({'difficulty': 'retired-setting', 'bots': 2}))
        recalled = match.recall(str(path))
        assert recalled.difficulty in match.DIFFICULTIES
        assert recalled.bots == 2

    def test_a_saved_file_that_is_not_an_object_gives_the_defaults(self, tmp_path):
        path = tmp_path / 'match.json'
        path.write_text('[1, 2, 3]')
        assert match.recall(str(path)).bots == match.MatchSetup().bots

    def test_a_key_nobody_declared_is_ignored_rather_than_fatal(self, tmp_path):
        path = tmp_path / 'match.json'
        path.write_text(json.dumps({'bots': 2, 'colourOfTheSky': 'blue'}))
        assert match.recall(str(path)).bots == 2

    def test_saving_is_all_or_nothing(self, tmp_path):
        """A save interrupted half-way must not leave a file that will not parse."""
        path = str(tmp_path / 'match.json')
        match.save(match.MatchSetup(bots=2), path)
        before = open(path).read()
        with pytest.raises(TypeError):
            match.save(object(), path)          # not a setup at all
        assert open(path).read() == before

    def test_the_default_path_is_under_the_users_own_directory(self):
        assert match.setup_path().endswith(match.SETUP_FILE)


class TestWhatCanBePlayedNow:

    def test_a_pack_that_is_not_fetched_offers_no_levels(self, tmp_path):
        levels = match.levels_available(cache_dir=str(tmp_path))
        assert levels == []

    def test_a_fetched_pack_offers_its_maps(self, tmp_path, monkeypatch):
        from twig_bb import download
        pack = download.pack_for_key('openarena-maps')
        root = tmp_path / 'twig-bb-content' / pack.directory / 'maps'
        root.mkdir(parents=True)
        for name in ('oa_dm1.bsp', 'oa_dm4.bsp'):
            (root / name).write_bytes(b'IBSP')
        levels = match.levels_available(cache_dir=str(tmp_path))
        assert [level.name for level in levels] == ['oa_dm1', 'oa_dm4']
        assert levels[0].target == 'openarena-maps:oa_dm1'

    def test_a_level_knows_which_pack_it_came_from(self, tmp_path):
        from twig_bb import download
        pack = download.pack_for_key('openarena-maps')
        root = tmp_path / 'twig-bb-content' / pack.directory / 'maps'
        root.mkdir(parents=True)
        (root / 'oa_dm1.bsp').write_bytes(b'IBSP')
        assert match.levels_available(cache_dir=str(tmp_path))[0].pack == pack.key


class TestWhereALevelsPictureLives:
    """Two conventions, because the content this reads uses two.

    Quake 3 puts every map's picture in one shared `levelshots/`; Unvanquished
    puts each map's in a metadata directory named after the map
    (``SPEC-UNVASSETS §3.3``). A reader that knows only the first lists the
    second's levels blank.
    """

    def _picture(self, path, size=(4, 2)):
        from PIL import Image
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new('RGB', size, (10, 20, 30)).save(path)

    def test_the_shared_directory_still_works(self, tmp_path):
        self._picture(tmp_path / 'levelshots' / 'oa_dm1.jpg')
        assert match._levelshots(str(tmp_path))['oa_dm1'].endswith('oa_dm1.jpg')

    def test_a_picture_in_a_metadata_directory_is_found(self, tmp_path):
        self._picture(tmp_path / 'meta' / 'plat23' / 'plat23.webp')
        assert match._levelshots(str(tmp_path))['plat23'].endswith('plat23.webp')

    def test_only_the_file_named_for_its_directory_counts(self, tmp_path):
        """A metadata directory holds other things, and they are not portraits.

        The name is the whole of the rule here: unlike `levelshots/`, where
        every file is a picture of the map it is named for, `meta/<map>/` is a
        directory of oddments that happens to contain one.
        """
        self._picture(tmp_path / 'meta' / 'plat23' / 'plat23.webp')
        self._picture(tmp_path / 'meta' / 'plat23' / 'loading_bar.png')
        found = match._levelshots(str(tmp_path))
        assert set(found) == {'plat23'}

    def test_a_picture_loose_under_meta_is_not_a_levelshot(self, tmp_path):
        """One directory deep is the rule; `meta/x.png` names no map."""
        self._picture(tmp_path / 'meta' / 'banner.png')
        assert match._levelshots(str(tmp_path)) == {}

    def test_the_shared_directory_wins_where_a_map_has_both(self, tmp_path):
        """First wins, and `os.walk` reaches `levelshots/` first by name."""
        self._picture(tmp_path / 'levelshots' / 'plat23.jpg')
        self._picture(tmp_path / 'meta' / 'plat23' / 'plat23.webp')
        assert match._levelshots(str(tmp_path))['plat23'].endswith('.jpg')

    def test_the_formats_the_content_actually_ships_are_searched(self):
        """Two of the three Unvanquished maps ship Crunch, one ships WebP."""
        assert '.webp' in match.LEVELSHOT_EXTENSIONS
        assert '.crn' in match.LEVELSHOT_EXTENSIONS


class TestReadingThosePictures:
    """The toolkit decodes through the imaging library, which has no Crunch."""

    def test_registering_teaches_the_picture_cache_crunch(self):
        from OpenGLContext.ui import pictures
        saved = dict(pictures._decoders)
        try:
            pictures._decoders.clear()
            assert pictures.decoderFor('x.crn') is None
            match.register_picture_decoders()
            assert pictures.decoderFor('x.crn') is not None
        finally:
            pictures._decoders.clear()
            pictures._decoders.update(saved)

    def test_registering_twice_is_harmless(self):
        match.register_picture_decoders()
        match.register_picture_decoders()
        from OpenGLContext.ui import pictures
        assert pictures.decoderFor('x.crn') is not None

    def test_webp_is_left_to_the_imaging_library(self):
        """It reads WebP already; a decoder here would be a layer for nothing."""
        from OpenGLContext.ui import pictures
        match.register_picture_decoders()
        assert pictures.decoderFor('x.webp') is None
