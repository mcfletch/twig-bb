"""The screens around the outside of the render loop.

Starting the game with no arguments should be a reasonable thing to do, and
this is what makes it one: a menu that offers what can be played, fetches what
is missing, and starts a match.

Three screens, and each is a plain ``Panel`` built from OpenGLContext's overlay
UI, so they take the player's interface scale, their skin and their key
handling without knowing anything about any of it:

:func:`main_menu`
    Play, Settings, Acknowledgements, Quit.
:func:`play_screen`
    The level, the opponents and the rules — editing a **draft**, so Cancel
    genuinely cancels and the match that was running is not half-changed by a
    screen that was closed.
:func:`download_screen`
    What a pack costs and what its terms are, then a bar that moves and a
    button that stops it: the engine's content screen.

Everything a test needs to know about these is structural — which buttons a
screen has, what each one does to the draft, which levels it offers — so all of
it is exercised with no window at all.  Building a panel touches no GL.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from OpenGLContext.ui import generate
from OpenGLContext.ui.contentscreen import ContentScreen
from OpenGLContext.ui.gallery import Carousel
from OpenGLContext.ui.layout import Column, Row
from OpenGLContext.ui.panel import Panel
from OpenGLContext.ui.session import SettingsSession
from OpenGLContext.ui.widgets import (
    BoundWidget, Button, Label, Select, Separator, Spacer,
)

from . import match
from .assetpack import AssetPack

log = logging.getLogger(__name__)

__all__ = ['GAME_TITLE', 'download_screen', 'first_run_screen', 'main_menu',
           'play_screen', 'wanted_from']

#: The working title, in exactly one place.  Nothing stored is keyed to it —
#: the settings namespace and the content cache belong to ``twig_bb``, the
#: library, which is not being renamed — so this can change the week before
#: release without touching anything else.
GAME_TITLE = 'Twitchy GLitchy Bang Bang'

#: How wide the menus are, in characters.
MENU_COLUMNS = 44

#: What a level chooser shows when nothing has been fetched.  Not an error: a
#: fresh install is exactly this, and the answer is the download screen.
NO_LEVELS = 'No levels yet — choose Get content'

#: How many levels the band shows at once.  Odd, so the chosen one has a
#: middle to sit in; five is enough to see what is either side without making
#: each picture too small to judge.
LEVELS_SHOWN = 5


def main_menu(on_play: Optional[Callable[[], None]] = None,
              on_settings: Optional[Callable[[], None]] = None,
              on_content: Optional[Callable[[], None]] = None,
              on_credits: Optional[Callable[[], None]] = None,
              on_quit: Optional[Callable[[], None]] = None,
              on_resume: Optional[Callable[[], None]] = None,
              subtitle: str = '') -> Panel:
    """The first screen, and the one Escape brings up mid-match.

    From a standing start there is nothing behind it, so Escape does nothing
    and leaving is what Quit is for.  **Mid-match there is**, and
    ``on_resume`` is then offered first and Escape leaves the screen — because
    a player who pressed Escape meaning "close this" must never find they have
    thrown the match away instead.
    """
    playing = on_resume is not None
    buttons = [
        ('resume', 'Resume', on_resume, True) if playing else None,
        ('play', 'Play', on_play, not playing),
        ('content', 'Get content', on_content, False),
        ('settings', 'Settings', on_settings, False),
        ('credits', 'Acknowledgements', on_credits, False),
        ('quit', 'Quit', on_quit, False),
    ]
    children: List[Any] = [Label(text=GAME_TITLE, name='title')]
    if subtitle:
        children.append(Label(text=subtitle, wrap=True, name='subtitle'))
    children.append(Separator(top=6))
    for entry in buttons:
        if entry is None:
            continue
        name, text, handler, primary = entry
        widget = Button(text=text, name=name,
                        role='primary' if primary else '')
        if handler is not None:
            widget.on_activate = lambda _widget, call=handler: call()
        children.append(widget)
    panel = Panel(title='', scrim=True, modal=True, closeOnEscape=playing,
                  preferredColumns=MENU_COLUMNS,
                  children=[Column(children=children, spacing=4)])
    if on_resume is not None:
        # Escaping out of the menu means what the Resume button means.
        panel.on_close = lambda _closing, resume=on_resume: resume()
    return panel


def play_screen(setup: match.MatchSetup, levels: Sequence[match.Level],
                on_start: Optional[Callable[[match.MatchSetup], None]] = None,
                on_cancel: Optional[Callable[[], None]] = None) -> Panel:
    """Choose the level, the opponents and the rules, then start.

    **Edits a draft.** The setup handed in is left alone until Start is
    pressed, so Cancel is real: a player who opens this mid-match and thinks
    better of it has changed nothing.  The rules' editors are *generated* from
    the node's own fields and hints, so a field added to
    :class:`~twig_bb.match.MatchSetup` appears here with no edit to this
    function.
    """
    session = SettingsSession(setup)
    draft = session.draft

    chooser = _level_chooser(draft, levels)
    rules = generate.page_for(draft, hints=match.MatchSetup.UI_HINTS)
    start = Button(text='Start', name='start', role='primary')
    cancel = Button(text='Cancel', name='cancel')

    panel = Panel(title='Play', scrim=True, modal=True,
                  # Wider than the other screens: a band of five pictures
                  # needs the room, and cramping them defeats the point of
                  # showing art at all.
                  preferredColumns=MENU_COLUMNS * 2,
                  children=[Column(spacing=4, children=[
                      Label(text='Level', name='level-label'),
                      chooser,
                      Separator(top=6),
                      rules,
                      Row(children=[Spacer(), cancel, start], spacing=8, top=8,
                          name='buttons'),
                  ])])

    answered: List[bool] = []

    def finish(started: bool) -> None:
        if answered:
            return
        answered.append(started)
        if started:
            session.commit()
        else:
            session.revert()
        session.close()
        panel.close(started)
        if started and on_start is not None:
            on_start(setup)
        elif not started and on_cancel is not None:
            on_cancel()

    start.on_activate = lambda _widget: finish(True)
    cancel.on_activate = lambda _widget: finish(False)
    # Escape leaves the setup as it was, which is what closing without
    # answering means everywhere else in this UI.
    panel.on_close = lambda _closing: finish(False)
    return panel


def _level_chooser(draft: match.MatchSetup,
                   levels: Sequence[match.Level]) -> BoundWidget:
    """A band of the levels on disk, shown by their own art.

    A drop-down is the wrong control here.  What tells one arena from another
    is what it *looks* like, and a list of names — `aggressor`, `ce1m7`,
    `oa_dm4` — makes a player start each in turn to find out which is which.
    Most of the levels this can fetch ship a picture of themselves, so the
    chooser shows them: several at a time, the arrows rolling the band along,
    and the name under each.
    """
    if not levels:
        empty = Select(name='level', options=[''], optionLabels=[NO_LEVELS])
        empty.enabled = False
        return empty
    chooser = Carousel(
        name='level', visibleCount=LEVELS_SHOWN,
        options=[level.target for level in levels],
        optionLabels=[level.name for level in levels],
        # Empty for a level that ships none, which the band draws as a plate.
        optionImages=[level.art for level in levels],
        value=draft.level)
    draft.level = chooser.value

    def chosen(widget: Any) -> None:
        draft.level = widget.value
    chooser.on_change = chosen
    return chooser


def download_screen(packs: Sequence[AssetPack],
                    on_fetch: Optional[Callable[[AssetPack], Any]] = None,
                    on_finished: Optional[Callable[[Any], None]] = None,
                    on_close: Optional[Callable[[], None]] = None,
                    job: Any = None) -> ContentScreen:
    """What one download costs and on what terms, then how far it has got.

    The engine's :class:`~OpenGLContext.ui.contentscreen.ContentScreen`, as
    this game shows it. The size and the licence are **on the screen that
    asks**, not only in ``--list-packs``: a user consenting to hundreds of
    megabytes of CC BY-SA content should be able to see that is what they are
    agreeing to at the moment they agree to it.

    **One set at a time**, chosen with the arrows, since a screen is a fixed
    shape and a catalogue is not; the line above it says what the whole
    catalogue comes to. ``packs`` is what is not on disk. Choosing one fetches
    it and whichever of ``packs`` it needs (:func:`wanted_from`), since a map
    fetched without its art renders in grey. ``on_fetch(pack)`` returns the
    job it started; the screen shows it, with Stop, until the player closes it.
    ``job`` is one a previous screen started, which carries on when its screen
    is closed.
    """
    packs = list(packs)
    catalogue = sum(pack.approximate_bytes for pack in packs)
    return ContentScreen(
        packs, on_fetch=on_fetch, wanted=wanted_from(packs),
        on_finished=on_finished, on_close=on_close, title='Content',
        columns=MENU_COLUMNS + 12, job=job,
        heading='%d %s to choose from, %d MB in all.  One at a time:'
                % (len(packs), 'set' if len(packs) == 1 else 'sets',
                   round(catalogue / 1e6)))


def first_run_screen(packs: Sequence[AssetPack],
                     on_fetch: Optional[Callable[[AssetPack], Any]] = None,
                     on_finished: Optional[Callable[[Any], None]] = None,
                     on_close: Optional[Callable[[], None]] = None
                     ) -> ContentScreen:
    """The download a game with none of its own art needs before a match.

    The art pack and what it needs, offered as one set with the size and the
    terms. ``on_fetch(pack)`` returns the job that fetches the set.
    """
    return ContentScreen(packs, on_fetch=on_fetch, on_finished=on_finished,
                         on_close=on_close, together=True,
                         title='%s needs its art' % (GAME_TITLE,),
                         columns=MENU_COLUMNS + 12)


def wanted_from(packs: Sequence[AssetPack]
                ) -> Callable[[AssetPack], List[AssetPack]]:
    """Given the packs on offer, the set choosing one of them fetches.

    The pack and those of ``packs`` it names in ``needs``. A need not among
    them is on disk already, so it is not fetched again.
    """
    offered = list(packs)

    def wanted(pack: AssetPack) -> List[AssetPack]:
        return [pack] + [other for other in offered
                         if other.key in pack.needs]
    return wanted
