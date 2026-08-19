"""The half of an armed combatant that only a real driver can settle.

Which clip a body plays and what it is carrying are arithmetic, and are tested
without a window in :mod:`tests.test_characters`.  What is left is what a
player would notice and no headless test can see: that a bot actually appears
holding its weapon, and that several bots holding the same one all do.

That second case is the trap this file exists for.  One weapon model is loaded
per key and **shared** between everybody carrying it, so a subtree that were
drawn once, or drawn at only one of its parents, would leave one bot armed and
the rest waving empty hands -- with every arithmetic test still green.  The
pickups were bitten by exactly this (see :mod:`tests.test_items_gl`).

Deliberately shallow, like its neighbours: it asserts that pixels appeared
where they should have and nothing about how any of it looks.
"""

from __future__ import annotations

import numpy as np
import pytest

# Imported for its side effects as much as for the fixture: it selects the
# renderer, profile and backend the game itself uses, before any GL import.
from test_combat_gl import AHEAD, _lit, render        # noqa: F401

from OpenGLContext.scenegraph.transform import Transform

from twig_bb import characters, weapons

pytestmark = [pytest.mark.gl]


def armed(weapon='rifle', ids=('bot0',)):
    """A cast holding one weapon each, posed as if carrying it."""
    cast = characters.Cast(list(ids),
                           armoury=characters.Armoury(weapons.default_table()))
    for id in ids:
        cast.update(id, characters.Motion(weapon=weapon), 0.1)
    return cast


def standing(cast, ids, at=AHEAD):
    """Each figure on its own transform, spread across the view."""
    spread = np.linspace(-1.2, 1.2, len(ids)) if len(ids) > 1 else [0.0]
    return [Transform(translation=(float(x), -1.0, at),
                      children=[cast.subtree(id)])
            for id, x in zip(ids, spread, strict=True)]


def test_a_cast_parses_each_build_once(monkeypatch):
    """Four bots of two builds read two files, not four.

    The cast draws everyone from the same handful of builds, so a file read and
    JSON-parsed once per figure is most of the loading cost paid over and over.
    One :class:`~OpenGLContext.loaders.gltf.SharedDocument` per build is parsed
    once and every figure of that build is built from it.
    """
    seen = []
    real = characters._parse_document
    monkeypatch.setattr(characters, '_parse_document',
                        lambda name: seen.append(name) or real(name))
    characters.Cast(['bot0', 'bot1', 'bot2', 'bot3'])
    assert seen == list(characters.BUILDS)          # each build, once, in order


class TestABotHoldingItsWeapon:
    def test_a_figure_reaches_the_framebuffer(self, render):
        cast = armed()
        assert _lit(render(standing(cast, ['bot0']))) > 0

    def test_the_weapon_draws_as_well_as_the_body(self, render):
        """More is lit with a rifle in the hand than without one.

        The *pose* is held while the weapon is taken away, because a figure
        that stopped carrying would also stop playing the carry clip -- and a
        difference that is really a change of stance would prove nothing about
        whether the rifle ever reached the framebuffer.
        """
        cast = armed()
        scene = standing(cast, ['bot0'])
        with_weapon = _lit(render(scene))
        cast.of('bot0').drop()
        assert _lit(render(scene)) < with_weapon

    def test_every_bot_carrying_one_is_drawn_with_it(self, render):
        """The shared subtree is drawn at each of its parents, not one of them."""
        ids = ['bot0', 'bot1', 'bot2']
        cast = armed(ids=ids)
        held = [cast.of(one)._held for one in ids]
        assert len({id(node) for node in held}) == 1, 'one model, shared'
        scene = standing(cast, ids)
        three = _lit(render(scene))
        for one in ids[1:]:
            cast.of(one).drop()
        assert _lit(render(scene)) < three


class TestTheCastIsPosedTogether:
    """A cast poses its figures in one run, not one each.

    What a figure plays is still its own decision; turning all of those
    decisions into skeletons is one pass over
    :class:`~OpenGLContext.character.crowd.Crowd`, which is what lets a room of
    them cost about what one of them used to.
    """

    IDS = ['bot0', 'bot1', 'bot2', 'bot3']

    def _cast(self):
        from twig_bb import characters as charactersmod
        return charactersmod.Cast(self.IDS)

    def test_figures_of_a_build_share_one_crowd(self):
        cast = self._cast()

        assert cast.crowds, 'a cast with figures should have crowds'
        assert sum(len(crowd) for crowd in cast.crowds.values()) == len(self.IDS)
        for one in self.IDS:
            assert cast.of(one).crowd is not None

    def test_a_figure_updated_alone_is_not_posed_until_the_cast_is(self):
        """Updating says what to play; posing is what moves the joints."""
        from twig_bb import characters as charactersmod

        cast = self._cast()
        figure = cast.of('bot0')
        rig = figure.model.mixer.rig
        cast.update('bot0', charactersmod.Motion(speed=4.0), 1 / 60.0)
        settled = [tuple(x.rotation) for x in rig.transforms]

        cast.update('bot0', charactersmod.Motion(speed=4.0), 1 / 60.0)
        assert [tuple(x.rotation) for x in rig.transforms] == settled

        cast.pose(1 / 60.0)
        assert [tuple(x.rotation) for x in rig.transforms] != settled

    def test_posing_the_cast_moves_every_figure_and_skins_it(self):
        import numpy as np
        from twig_bb import characters as charactersmod

        cast = self._cast()
        rigs = [cast.of(one).model.mixer.rig for one in self.IDS]
        before = [np.array([list(x.rotation) for x in rig.transforms])
                  for rig in rigs]

        for _ in range(24):
            for one in self.IDS:
                cast.update(one, charactersmod.Motion(speed=4.0, weapon='rifle'),
                            1 / 60.0)
            cast.pose(1 / 60.0)

        for rig, rest in zip(rigs, before, strict=True):
            posed = np.array([list(x.rotation) for x in rig.transforms])
            assert (np.abs(posed - rest).max(axis=1) > 1e-6).sum() > 10
        for one in self.IDS:
            model = cast.of(one).model
            assert all(mesh._skin_matrices is not None
                       for skin in model.mixer.skins for mesh in skin.meshes)
