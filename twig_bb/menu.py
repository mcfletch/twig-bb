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
    button that stops it.

Everything a test needs to know about these is structural — which buttons a
screen has, what each one does to the draft, which levels it offers — so all of
it is exercised with no window at all.  Building a panel touches no GL.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional, Sequence

from OpenGLContext.ui import generate
from OpenGLContext.ui.gallery import Carousel
from OpenGLContext.ui.layout import Column, Row
from OpenGLContext.ui.panel import Panel
from OpenGLContext.ui.session import SettingsSession
from OpenGLContext.ui.widgets import Button, Label, Select, Separator, Spacer

from . import match
from .assetpack import AssetPack

log = logging.getLogger(__name__)

__all__ = ['GAME_TITLE', 'download_screen', 'main_menu', 'play_screen',
           'progress_line']

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
                   levels: Sequence[match.Level]) -> Any:
    """A band of the levels on disk, shown by their own art.

    A drop-down is the wrong control here.  What tells one arena from another
    is what it *looks* like, and a list of names — `aggressor`, `ce1m7`,
    `oa_dm4` — makes a player start each in turn to find out which is which.
    Most of the levels this can fetch ship a picture of themselves, so the
    chooser shows them: several at a time, the arrows rolling the band along,
    and the name under each.
    """
    if not levels:
        chooser = Select(name='level', options=[''], optionLabels=[NO_LEVELS])
        chooser.enabled = False
        return chooser
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
                    on_start: Optional[Callable[[], None]] = None,
                    on_cancel: Optional[Callable[[], None]] = None) -> Panel:
    """What a download costs and on what terms, before any of it happens.

    The size and the licence are **on the screen that asks**, not only in
    ``--list-packs``: a user consenting to hundreds of megabytes of CC BY-SA
    content should be able to see that is what they are agreeing to at the
    moment they agree to it.
    """
    total = sum(pack.approximate_bytes for pack in packs)
    body: List[Any] = [
        Label(text='Download %s?  About %d MB in total.'
                   % (_listed(packs), round(total / 1e6)),
              wrap=True, name='question'),
    ]
    for pack in packs:
        body.append(Label(text='%s — %d MB\n%s'
                               % (pack.title, round(pack.approximate_bytes / 1e6),
                                  pack.copyright),
                          wrap=True, top=4, name='pack-%s' % (pack.key,)))
        if pack.notes:
            body.append(Label(text=pack.notes, wrap=True, name='notes-%s'
                                                            % (pack.key,)))
    start = Button(text='Download', name='download', role='primary')
    cancel = Button(text='Not now', name='cancel')
    body.append(Row(children=[Spacer(), cancel, start], spacing=8, top=8,
                    name='buttons'))
    panel = Panel(title='Content', scrim=True, modal=True,
                  preferredColumns=MENU_COLUMNS + 12,
                  children=[Column(children=body, spacing=4)])
    answered: List[bool] = []

    def answer(yes: bool) -> None:
        if answered:
            return
        answered.append(yes)
        panel.close(yes)
        if yes and on_start is not None:
            on_start()
        elif not yes and on_cancel is not None:
            on_cancel()

    start.on_activate = lambda _widget: answer(True)
    cancel.on_activate = lambda _widget: answer(False)
    panel.on_close = lambda _closing: answer(False)
    return panel


def progress_screen(job: Any,
                    on_cancel: Optional[Callable[[], None]] = None) -> Panel:
    """A download in progress: what it is doing, and a way to stop it.

    The label is refreshed by :func:`refresh_progress` from the frame loop,
    which is also where the job is polled — nothing here reads the worker.
    """
    line = Label(text=progress_line(job), wrap=True, name='progress')
    stop = Button(text='Stop', name='stop')
    panel = Panel(title='Downloading', scrim=True, modal=True,
                  closeOnEscape=False,
                  preferredColumns=MENU_COLUMNS + 12,
                  children=[Column(spacing=4, children=[
                      line,
                      Row(children=[Spacer(), stop], spacing=8, top=8,
                          name='buttons'),
                  ])])
    panel.progressLabel = line

    def stopped(_widget: Any) -> None:
        job.cancel()
        if on_cancel is not None:
            on_cancel()
    stop.on_activate = stopped
    return panel


def refresh_progress(panel: Any, job: Any) -> bool:
    """Put the job's latest state on its screen; returns whether it changed."""
    label = getattr(panel, 'progressLabel', None)
    if label is None:
        return False
    line = progress_line(job)
    if line == label.text:
        return False
    label.text = line
    return True


def progress_line(job: Any) -> str:
    """One line of what a download is doing, for a user to read."""
    if job.finished:
        if job.cancelled:
            return 'Stopped.'
        if job.failed is not None:
            return 'Could not finish: %s' % (job.failed,)
        return 'Done.'
    return job.state


def _listed(packs: Sequence[AssetPack]) -> str:
    """The pack titles, as a sentence."""
    titles = [pack.title for pack in packs]
    if len(titles) <= 1:
        return titles[0] if titles else 'nothing'
    return '%s and %s' % (', '.join(titles[:-1]), titles[-1])
