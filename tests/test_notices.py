"""Acknowledgements: what this is built from, and what it is playing.

Not decoration. This project plays freely-licensed content under licences with
attribution requirements, and depends on libraries whose licences ask to be
reproduced. The screen is how a distributed application meets that.

**The content half is generated and the code half is checked.** A pack added to
the catalogue appears in the notices without anyone remembering to add it; a
dependency added to `pyproject.toml` and not to `NOTICES.md` fails this suite
rather than shipping unattributed. Those are the two ways an acknowledgement
goes missing, and each has a test here.
"""

from __future__ import annotations

import os

from twitchoglc import notices


class TestTheContentHalf:
    """Generated from the catalogue, so a pack cannot be forgotten."""

    def test_every_registered_pack_appears(self):
        text = notices.content_notices()
        from twitchoglc import catalog
        for pack in catalog.load():
            assert pack.title in text

    def test_each_pack_is_shown_with_its_terms(self):
        text = notices.content_notices()
        from twitchoglc import catalog
        for pack in catalog.load():
            assert pack.copyright in text

    def test_a_pack_added_to_the_catalogue_needs_no_edit_here(self):
        """The whole reason `copyright` is a mandatory field."""
        from twitchoglc.assetpack import AssetPack
        extra = AssetPack(key='new', title='A brand new pack',
                          url='https://example.com/n.zip', directory='new',
                          archive='zip', approximate_bytes=1,
                          copyright='Somebody, CC0', marker='')
        text = notices.content_notices(packs=[extra])
        assert 'A brand new pack' in text and 'CC0' in text

    def test_the_shipped_art_is_credited_too(self):
        """CC0 asks for nothing; it is credited anyway, as the rule here is."""
        assert '3dmodelscc0' in notices.content_notices()


class TestTheCodeHalf:
    """Checked against what is installed, so it cannot drift."""

    def test_the_manifest_is_checked_in(self):
        assert os.path.isfile(notices.NOTICES_PATH)

    def test_every_declared_dependency_is_acknowledged(self):
        """The test that makes an unattributed dependency a failing build.

        A new entry in `pyproject.toml` that nobody adds to `NOTICES.md` is a
        library shipped without its licence reproduced, and it is exactly the
        kind of omission nobody notices until someone else does.
        """
        missing = notices.unacknowledged()
        assert not missing, ('not in NOTICES.md: %s' % (', '.join(missing),))

    def test_each_acknowledgement_names_a_licence(self):
        for entry in notices.acknowledged():
            assert entry.licence, entry.name

    def test_each_acknowledgement_names_a_home_a_user_could_visit(self):
        """The manifest is markdown; its <angle brackets> are not an address."""
        for entry in notices.acknowledged():
            assert entry.home.startswith('http'), entry.name

    def test_the_optional_audio_backend_is_marked_optional(self):
        """A notice has to be accurate about what a given install contains."""
        entries = {entry.name: entry for entry in notices.acknowledged()}
        assert entries['miniaudio'].optional

    def test_a_required_dependency_is_not_marked_optional(self):
        entries = {entry.name: entry for entry in notices.acknowledged()}
        assert not entries['numpy'].optional


class TestReadingTheDependencies:

    def write(self, tmp_path, text):
        path = tmp_path / 'pyproject.toml'
        path.write_text(text)
        return str(path)

    def test_the_required_ones_are_found(self, tmp_path):
        path = self.write(tmp_path, '''
[project]
dependencies = [
    "numpy>=2.0",
    "pillow",
]
''')
        assert notices.declared_dependencies(path) == {'numpy', 'pillow'}

    def test_the_optional_ones_are_found_too(self, tmp_path):
        """An optional dependency still ships its licence when it is installed."""
        path = self.write(tmp_path, '''
[project]
dependencies = ["numpy"]

[project.optional-dependencies]
audio = ["miniaudio"]
''')
        assert 'miniaudio' in notices.declared_dependencies(path)

    def test_the_development_extra_is_left_out(self, tmp_path):
        """pytest and ruff are not shipped, so they are not acknowledged."""
        path = self.write(tmp_path, '''
[project]
dependencies = ["numpy"]

[project.optional-dependencies]
dev = ["pytest", "ruff"]
''')
        assert notices.declared_dependencies(path) == {'numpy'}

    def test_a_version_specifier_is_not_part_of_the_name(self, tmp_path):
        path = self.write(tmp_path, '''
[project]
dependencies = ["OpenGLContext>=2.3.0a1", "omi_physics >= 0.2.1"]
''')
        assert notices.declared_dependencies(path) == {'openglcontext',
                                                       'omi_physics'}


class TestTheProvenanceStatement:
    """The truest thing about this project, where a user can read it."""

    def test_it_says_no_engine_source_was_read(self):
        assert 'no engine source' in notices.provenance().lower()

    def test_it_names_where_the_format_knowledge_came_from(self):
        assert 'specs/' in notices.provenance()

    def test_it_names_the_procedure(self):
        assert 'CLEAN-ROOM' in notices.provenance()


class TestTheWholeDocument:

    def test_it_holds_all_three_parts(self):
        text = notices.full_text()
        assert 'OpenArena' in text            # content
        assert 'numpy' in text                # code
        assert 'CLEAN-ROOM' in text           # provenance

    def test_it_can_be_printed_from_the_command_line(self, capsys):
        """For anyone packaging this, who has no window to open."""
        notices.main([])
        assert 'CLEAN-ROOM' in capsys.readouterr().out


class TestTheScreen:

    def test_it_is_a_panel_a_user_can_close(self):
        panel = notices.screen()
        assert panel.closeOnEscape

    def test_it_holds_the_text(self):
        panel = notices.screen()
        found = []

        def walk(node):
            found.append(getattr(node, 'text', ''))
            for child in getattr(node, 'children', ()) or ():
                walk(child)
        walk(panel)
        assert any('OpenArena' in text for text in found)
