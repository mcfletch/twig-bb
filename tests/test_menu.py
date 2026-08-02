"""The screens around the outside of the render loop.

Everything worth asserting about a menu is structural — which buttons it has,
what each does to the draft, which levels it offers — so none of this needs a
window.  Building a panel touches no GL.
"""

from __future__ import annotations


from twitchoglc import match, menu
from twitchoglc.assetpack import AssetPack


def widget(panel, name):
    """The named widget somewhere under ``panel``, or None."""
    def walk(node):
        if getattr(node, 'name', None) == name:
            return node
        for child in getattr(node, 'children', ()) or ():
            found = walk(child)
            if found is not None:
                return found
        return None
    return walk(panel)


def names(panel):
    found = []

    def walk(node):
        name = getattr(node, 'name', '')
        if name:
            found.append(name)
        for child in getattr(node, 'children', ()) or ():
            walk(child)
    walk(panel)
    return found


def levels(*names_):
    return [match.Level(name=name, target='openarena-maps:' + name,
                        pack='openarena-maps') for name in names_]


def pack(**named):
    values = dict(key='sample', title='A sample pack',
                  url='https://example.com/s.zip', directory='sample',
                  archive='zip', approximate_bytes=41_711_739,
                  copyright='Somebody, CC BY-SA 3.0', marker='')
    values.update(named)
    return AssetPack(**values)


class TestTheMainMenu:

    def test_it_offers_play_first(self):
        panel = menu.main_menu()
        assert widget(panel, 'play') is not None
        assert names(panel).index('play') < names(panel).index('quit')

    def test_play_is_the_primary_action(self):
        """Enter on the first screen should start a game."""
        assert widget(menu.main_menu(), 'play').role == 'primary'

    def test_it_offers_settings(self):
        assert widget(menu.main_menu(), 'settings') is not None

    def test_it_offers_the_acknowledgements(self):
        """Reachable from the menu, which is half of what they are for."""
        assert widget(menu.main_menu(), 'credits') is not None

    def test_it_offers_a_way_to_get_content(self):
        assert widget(menu.main_menu(), 'content') is not None

    def test_it_offers_quit(self):
        assert widget(menu.main_menu(), 'quit') is not None

    def test_each_button_calls_its_handler(self):
        called = []
        panel = menu.main_menu(
            on_play=lambda: called.append('play'),
            on_settings=lambda: called.append('settings'),
            on_content=lambda: called.append('content'),
            on_credits=lambda: called.append('credits'),
            on_quit=lambda: called.append('quit'))
        for name in ('play', 'settings', 'content', 'credits', 'quit'):
            widget(panel, name).on_activate(widget(panel, name))
        assert called == ['play', 'settings', 'content', 'credits', 'quit']

    def test_a_button_with_no_handler_is_harmless(self):
        """A menu built for a test, or one whose action is not wired yet."""
        panel = menu.main_menu()
        assert widget(panel, 'play').on_activate is None

    def test_it_cannot_be_dismissed(self):
        """There is nothing behind it; leaving is what Quit is for."""
        assert not menu.main_menu().closeOnEscape

    def test_the_title_appears_once_and_from_one_constant(self):
        """A working title has to be changeable in one edit."""
        assert widget(menu.main_menu(), 'title').text == menu.GAME_TITLE


class TestThePlayScreen:

    def setup_of(self, **named):
        return match.MatchSetup(**named)

    def test_it_lists_the_levels_on_disk(self):
        panel = menu.play_screen(self.setup_of(), levels('oa_dm1', 'oa_dm4'))
        assert widget(panel, 'level').optionLabels == ['oa_dm1', 'oa_dm4']

    def test_choosing_a_level_reaches_the_draft(self):
        setup = self.setup_of()
        panel = menu.play_screen(setup, levels('oa_dm1', 'oa_dm4'))
        chooser = widget(panel, 'level')
        chooser.value = 'openarena-maps:oa_dm4'
        chooser.on_change(chooser)
        widget(panel, 'start').on_activate(None)
        assert setup.level == 'openarena-maps:oa_dm4'

    def test_the_remembered_level_is_the_one_selected(self):
        """Offered again first, because it is what a returning player wants."""
        setup = self.setup_of(level='openarena-maps:oa_dm4')
        panel = menu.play_screen(setup, levels('oa_dm1', 'oa_dm4'))
        assert widget(panel, 'level').value == 'openarena-maps:oa_dm4'

    def test_a_remembered_level_that_is_gone_falls_back_to_the_first(self):
        """A pack deleted between runs must not leave an unstartable choice."""
        setup = self.setup_of(level='openarena-maps:deleted')
        panel = menu.play_screen(setup, levels('oa_dm1'))
        assert widget(panel, 'level').value == 'openarena-maps:oa_dm1'

    def test_with_nothing_fetched_it_says_so_rather_than_being_empty(self):
        panel = menu.play_screen(self.setup_of(), [])
        chooser = widget(panel, 'level')
        assert chooser.optionLabels == [menu.NO_LEVELS]
        assert not chooser.enabled

    def test_the_rules_editors_are_generated_from_the_node(self):
        """A field added to MatchSetup appears here with no edit to the menu."""
        panel = menu.play_screen(self.setup_of(), levels('oa_dm1'))
        assert widget(panel, 'bots') is not None
        assert widget(panel, 'difficulty') is not None

    def test_start_hands_back_the_setup(self):
        got = []
        setup = self.setup_of()
        panel = menu.play_screen(setup, levels('oa_dm1'),
                                 on_start=got.append)
        widget(panel, 'start').on_activate(None)
        assert got == [setup]

    def test_cancel_changes_nothing(self):
        """Editing a draft is what makes Cancel real rather than decorative."""
        setup = self.setup_of(bots=1)
        panel = menu.play_screen(setup, levels('oa_dm1'))
        widget(panel, 'bots').write(7)
        widget(panel, 'cancel').on_activate(None)
        assert setup.bots == 1

    def test_start_keeps_the_edits(self):
        setup = self.setup_of(bots=1)
        panel = menu.play_screen(setup, levels('oa_dm1'))
        widget(panel, 'bots').write(7)
        widget(panel, 'start').on_activate(None)
        assert setup.bots == 7

    def test_closing_without_answering_is_a_cancel(self):
        cancelled = []
        setup = self.setup_of(bots=1)
        panel = menu.play_screen(setup, levels('oa_dm1'),
                                 on_cancel=lambda: cancelled.append(True))
        widget(panel, 'bots').write(7)
        panel.on_close(panel)
        assert setup.bots == 1
        assert cancelled == [True]

    def test_answering_twice_is_answered_once(self):
        got = []
        panel = menu.play_screen(self.setup_of(), levels('oa_dm1'),
                                 on_start=got.append)
        widget(panel, 'start').on_activate(None)
        widget(panel, 'start').on_activate(None)
        panel.on_close(panel)
        assert len(got) == 1


class TestTheDownloadConsent:

    def test_the_size_is_on_the_screen_that_asks(self):
        """Not only in --list-packs: it is what the answer turns on."""
        panel = menu.download_screen([pack()])
        assert '42 MB' in widget(panel, 'question').text

    def test_the_licence_is_on_the_screen_that_asks(self):
        panel = menu.download_screen([pack()])
        assert 'CC BY-SA' in widget(panel, 'pack-sample').text

    def test_several_packs_are_asked_about_at_once(self):
        """A question that must be answered again next launch is a worse one."""
        panel = menu.download_screen([pack(key='a'), pack(key='b')])
        assert widget(panel, 'pack-a') is not None
        assert widget(panel, 'pack-b') is not None

    def test_the_total_is_the_sum(self):
        panel = menu.download_screen([pack(key='a', approximate_bytes=1_000_000),
                                      pack(key='b', approximate_bytes=3_000_000)])
        assert '4 MB' in widget(panel, 'question').text

    def test_accepting_starts_it(self):
        started = []
        panel = menu.download_screen([pack()], on_start=lambda: started.append(1))
        widget(panel, 'download').on_activate(None)
        assert started == [1]

    def test_declining_does_not(self):
        started, declined = [], []
        panel = menu.download_screen([pack()], on_start=lambda: started.append(1),
                                     on_cancel=lambda: declined.append(1))
        widget(panel, 'cancel').on_activate(None)
        assert (started, declined) == ([], [1])

    def test_closing_it_declines(self):
        declined = []
        panel = menu.download_screen([pack()],
                                     on_cancel=lambda: declined.append(1))
        panel.on_close(panel)
        assert declined == [1]


class FakeJob:
    def __init__(self, **named):
        self.finished = False
        self.cancelled = False
        self.failed = None
        self.state = 'A sample pack — 40% of 42 MB'
        self.__dict__.update(named)

    def cancel(self):
        self.cancelled = True


class TestTheProgressScreen:

    def test_it_shows_what_the_job_is_doing(self):
        panel = menu.progress_screen(FakeJob())
        assert '40%' in widget(panel, 'progress').text

    def test_it_cannot_be_dismissed_by_accident(self):
        """Escape closing it would leave a download running with no way back."""
        assert not menu.progress_screen(FakeJob()).closeOnEscape

    def test_stopping_cancels_the_job(self):
        job = FakeJob()
        panel = menu.progress_screen(job)
        widget(panel, 'stop').on_activate(None)
        assert job.cancelled

    def test_refreshing_updates_the_line(self):
        job = FakeJob()
        panel = menu.progress_screen(job)
        job.state = 'A sample pack — 90% of 42 MB'
        assert menu.refresh_progress(panel, job)
        assert '90%' in widget(panel, 'progress').text

    def test_refreshing_with_nothing_new_reports_no_change(self):
        """A redraw per frame for a bar that has not moved is a waste."""
        job = FakeJob()
        panel = menu.progress_screen(job)
        menu.refresh_progress(panel, job)
        assert not menu.refresh_progress(panel, job)

    def test_a_finished_job_reads_as_done(self):
        assert menu.progress_line(FakeJob(finished=True)) == 'Done.'

    def test_a_cancelled_job_does_not_read_as_an_error(self):
        """Nothing went wrong; the user changed their mind."""
        line = menu.progress_line(FakeJob(finished=True, cancelled=True))
        assert 'Stopped' in line and 'error' not in line.lower()

    def test_a_failed_job_says_what_went_wrong(self):
        line = menu.progress_line(FakeJob(finished=True,
                                          failed=IOError('the network went away')))
        assert 'network' in line


class TestListingPacksInASentence:

    def test_one_pack_is_its_title(self):
        assert menu._listed([pack(title='Maps')]) == 'Maps'

    def test_two_packs_are_joined_with_and(self):
        assert menu._listed([pack(title='Maps'), pack(title='Art')]) == \
            'Maps and Art'

    def test_three_packs_read_as_a_list(self):
        found = menu._listed([pack(title='A'), pack(title='B'), pack(title='C')])
        assert found == 'A, B and C'

    def test_no_packs_is_not_an_empty_sentence(self):
        assert menu._listed([]) == 'nothing'
