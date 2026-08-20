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
        """Updating says what to play; posing is what moves the skeleton."""
        import numpy as np
        from twig_bb import characters as charactersmod

        cast = self._cast()
        figure = cast.of('bot0')
        cast.update('bot0', charactersmod.Motion(speed=4.0), 1 / 60.0)
        cast.pose(1 / 60.0)
        settled = _skin_of(figure)

        cast.update('bot0', charactersmod.Motion(speed=4.0), 1 / 60.0)
        assert all(np.allclose(one, other) for one, other
                   in zip(_skin_of(figure), settled, strict=True))

        cast.pose(1 / 60.0)
        assert not all(np.allclose(one, other) for one, other
                       in zip(_skin_of(figure), settled, strict=True))

    def test_posing_the_cast_moves_every_figure_and_skins_it(self):
        import numpy as np
        from twig_bb import characters as charactersmod

        cast = self._cast()
        for _ in range(24):
            for one in self.IDS:
                cast.update(one, charactersmod.Motion(speed=4.0), 1 / 60.0)
            cast.pose(1 / 60.0)

        for one in self.IDS:
            model = cast.of(one).model
            for skin in model.mixer.skins:
                for mesh in skin.meshes:
                    assert mesh._skin_matrices is not None
            # A body that is running is not a body in its bind pose.
            assert any(not np.allclose(matrices, np.eye(4))
                       for matrices in _skin_of(cast.of(one)))

    def test_only_the_joints_something_reaches_are_written(self):
        """Nothing here reads a joint, so writing fifty of them is waste.

        What a figure is holding hangs off its grip point, and the renderer
        walks to it -- so that point, and the joints down to it, are written,
        and the rest are not.
        """
        cast = self._cast()
        bare = len(cast.of('bot0').model.mixer._writable())

        holding = armed(ids=self.IDS)
        written = len(holding.of('bot0').model.mixer._writable())
        joints = holding.of('bot0').model.mixer.rig.n

        assert bare == 0, 'a figure holding nothing has no joint to write'
        assert 0 < written < joints, (written, joints)


def _skin_of(figure):
    return [mesh._skin_matrices for skin in figure.model.mixer.skins
            for mesh in skin.meshes]


class TestFiguresAreDrawnLighterAtRange:
    """The lighter mesh that ships beside each build is actually used.

    Both meshes are posed by the one skeleton, so carrying a second level costs
    a figure nothing per frame; which of them is drawn is the renderer's
    decision, taken from how far away the figure is.
    """

    def test_a_figure_carries_the_lighter_mesh_as_a_level(self):
        from OpenGLContext.scenegraph.lod import LOD
        from twig_bb import characters as charactersmod

        cast = charactersmod.Cast(['bot0'])
        figure = cast.of('bot0')

        assert _levels(figure.group, LOD), 'no level of detail was taken'
        for skin in figure.model.mixer.skins:
            assert len(skin.meshes) == 2, 'both meshes should be posed as one'

    def test_the_level_beyond_the_range_is_the_lighter_of_the_two(self):
        from OpenGLContext.scenegraph.lod import LOD
        from twig_bb import characters as charactersmod

        cast = charactersmod.Cast(['bot0'])
        node = _levels(cast.of('bot0').group, LOD)[0]

        near = sum(len(mesh.positions) for mesh in _skinned(node.level[0]))
        far = sum(len(mesh.positions) for mesh in _skinned(node.level[1]))

        assert far < near, (near, far)

    def test_both_levels_are_posed_together(self):
        import numpy as np
        from twig_bb import characters as charactersmod

        cast = charactersmod.Cast(['bot0'])
        for _ in range(6):
            cast.update('bot0', charactersmod.Motion(speed=4.0), 1 / 60.0)
            cast.pose(1 / 60.0)

        for skin in cast.of('bot0').model.mixer.skins:
            matrices = [mesh._skin_matrices for mesh in skin.meshes]
            assert all(one is not None for one in matrices)
            assert np.allclose(matrices[0], matrices[1])


def _levels(node, kind, seen=None):
    seen = seen if seen is not None else set()
    if id(node) in seen:
        return []
    seen.add(id(node))
    found = [node] if isinstance(node, kind) else []
    for name in ('children', 'level'):
        for child in (getattr(node, name, None) or ()):
            found += _levels(child, kind, seen)
    return found


def _skinned(node, seen=None):
    seen = seen if seen is not None else set()
    if id(node) in seen:
        return []
    seen.add(id(node))
    found = [node] if getattr(node, 'skin_joints', None) is not None else []
    for name in ('children', 'geometry', 'level'):
        value = getattr(node, name, None)
        if value is None:
            continue
        for child in (value if isinstance(value, (list, tuple)) else [value]):
            found += _skinned(child, seen)
    return found
