"""Finding the art a table names, and painting one model four ways.

A table names its model as a relative path and expects a subtree back.  Two
things about that are worth pinning: a name that resolves to nothing must not
take the match down with it, and a recolour must move the *colour* without
flattening the material — a glass bubble repainted into opaque plastic is a
recolour that has repainted the wrong thing.
"""

from __future__ import annotations

import os

from OpenGLContext.scenegraph.appearance import Appearance
from OpenGLContext.scenegraph.box import Box
from OpenGLContext.scenegraph.group import Group
from OpenGLContext.scenegraph.material import Material
from OpenGLContext.scenegraph.shape import Shape
from OpenGLContext.scenegraph.transform import Transform

from twig_bb import art, items


def painted(colour=(1.0, 1.0, 1.0)):
    """A two-shape subtree, so a walk that stops at the first one is caught."""
    def shape():
        return Shape(geometry=Box(size=(1.0, 1.0, 1.0)),
                     appearance=Appearance(material=Material(
                         diffuseColor=colour, emissiveColor=(0.0, 0.0, 0.0))))
    return Group(children=[shape(), Transform(children=[shape()])])


class TestWhereTheArtIs:
    def test_a_relative_name_lands_inside_the_package(self):
        assert art.path_for('items/medpack.glb').startswith(art.ASSETS)

    def test_the_medikit_is_shipped_with_us(self):
        assert os.path.exists(art.path_for(items.MEDPACK['model']))

    def test_the_weapons_agree_about_where_that_is(self):
        from twig_bb import weapons
        assert weapons.ASSETS == art.ASSETS


class TestEveryShippedModelIsCredited:
    """The rule from CREDITS.md, swept across *all* of the art rather than one
    pack of it.

    ``tests/test_weapons.py`` pins the weapons' own credits, including the
    author link their pack asked for.  This is the general form: whatever
    directory art turns up in next, it arrives with a CREDITS.md naming it, or
    this fails.  §10 generates an acknowledgements screen from those files, and
    art nobody is named for is a screen that is silently wrong.
    """

    def art_directories(self):
        return sorted(
            os.path.join(art.ASSETS, name)
            for name in os.listdir(art.ASSETS)
            if os.path.isdir(os.path.join(art.ASSETS, name)))

    def test_there_is_more_than_one_kind_of_art_to_sweep(self):
        assert len(self.art_directories()) > 1

    def test_every_directory_of_art_has_a_credits_file(self):
        for directory in self.art_directories():
            assert os.path.exists(os.path.join(directory, 'CREDITS.md')), \
                directory

    def test_every_model_in_them_is_named_by_its_own_credits(self):
        for directory in self.art_directories():
            with open(os.path.join(directory, 'CREDITS.md'),
                      encoding='utf-8') as source:
                text = source.read()
            shipped = [name for name in os.listdir(directory)
                       if name.endswith('.glb')]
            assert shipped, directory
            for name in shipped:
                assert name in text, os.path.join(directory, name)

    def test_every_directory_says_who_made_its_art_and_under_what_terms(self):
        for directory in self.art_directories():
            with open(os.path.join(directory, 'CREDITS.md'),
                      encoding='utf-8') as source:
                text = source.read()
            assert '**Author**' in text, directory
            assert '**Licence**' in text, directory

    def test_the_medikit_is_small_enough_to_belong_in_a_repository(self):
        """A stand-in that costs a megabyte is a stand-in nobody will replace."""
        size = os.path.getsize(art.path_for(items.MEDPACK['model']))
        assert size < 1e6, size


class TestAModelThatWillNotLoad:
    """An item's rules decide the match; its model only decides how it looks."""

    def test_a_missing_file_is_none_rather_than_an_error(self, caplog):
        assert art.load('items/there-is-no-such-model.glb') is None

    def test_and_it_says_so(self, caplog):
        art.load('items/there-is-no-such-model.glb')
        assert 'there-is-no-such-model' in caplog.text

    def test_a_model_that_loads_is_a_subtree(self):
        assert art.load(items.MEDPACK['model']) is not None


class TestPaintingOneModelFourWays:
    def test_every_material_in_the_subtree_is_repainted(self):
        node = painted()
        assert art.recolour(node, (0.2, 0.4, 0.6)) == 2

    def test_the_colour_is_the_one_asked_for(self):
        node = painted()
        art.recolour(node, (0.2, 0.4, 0.6))
        for shape in art.shapes(node):
            assert tuple(shape.appearance.material.diffuseColor) == (0.2, 0.4, 0.6)

    def test_glow_is_a_fraction_of_that_colour(self):
        node = painted()
        art.recolour(node, (0.2, 0.4, 0.6), glow=0.5)
        for shape in art.shapes(node):
            assert tuple(shape.appearance.material.emissiveColor) == (0.1, 0.2, 0.3)

    def test_no_glow_asked_for_is_no_glow_given(self):
        node = painted()
        art.recolour(node, (0.2, 0.4, 0.6))
        for shape in art.shapes(node):
            assert tuple(shape.appearance.material.emissiveColor) == (0.0, 0.0, 0.0)

    def test_a_subtree_with_no_materials_is_harmless(self):
        assert art.recolour(Group(children=[]), (1.0, 0.0, 0.0)) == 0

    def test_the_medikits_glass_stays_glass(self):
        """The bubble is transmissive and 85% transparent; only its hue moves."""
        node = art.load(items.MEDPACK['model'])
        before = [(shape.appearance.material.transparency,
                   shape.appearance.material.alphaMode,
                   shape.appearance.material.metallic,
                   shape.appearance.material.roughness)
                  for shape in art.shapes(node)]
        art.recolour(node, (0.2, 0.55, 0.95), glow=0.45)
        after = [(shape.appearance.material.transparency,
                  shape.appearance.material.alphaMode,
                  shape.appearance.material.metallic,
                  shape.appearance.material.roughness)
                 for shape in art.shapes(node)]
        assert before == after

    def test_brightening_leaves_every_colour_where_it_was(self):
        """For art that came coloured: it needs the light, not the paint."""
        node = painted()
        before = [tuple(shape.appearance.material.diffuseColor)
                  for shape in art.shapes(node)]
        art.brighten(node, 0.5)
        assert [tuple(shape.appearance.material.diffuseColor)
                for shape in art.shapes(node)] == before

    def test_brightening_glows_in_each_materials_own_colour(self):
        """One glow colour for a model of several would flatten it towards that."""
        node = painted()
        art.brighten(node, 0.5)
        for shape in art.shapes(node):
            own = tuple(shape.appearance.material.diffuseColor)
            lit = tuple(shape.appearance.material.emissiveColor)
            assert all(abs(a - b * 0.5) < 1e-6 for a, b in zip(lit, own, strict=True))

    def test_brightening_reports_what_it_touched(self):
        assert art.brighten(painted(), 0.4) == 2
        assert art.brighten(Group(children=[]), 0.4) == 0

    def test_nothing_in_a_pickup_is_left_dark(self):
        """Not the contents *and not the shell*.

        A level bakes its lighting and places no lamps, so anything left
        without a floor of its own has nothing to show but what is behind it —
        and a pickup whose shell was skipped read as a black ball from across
        a room, whatever was floating inside it.
        """
        node = art.load(items.LAUNCHER_PICKUP['model'])
        art.brighten(node, 0.45)
        for shape in art.shapes(node):
            assert max(shape.appearance.material.emissiveColor) > 0.0, shape

    def test_both_of_the_medikits_materials_are_repainted(self):
        """The bubble and the cross: a coloured cross in a red bubble is two
        pickups' worth of signal disagreeing with each other."""
        node = art.load(items.MEDPACK['model'])
        assert art.recolour(node, (0.2, 0.55, 0.95)) == 2
        for shape in art.shapes(node):
            assert tuple(shape.appearance.material.baseColor) == (0.2, 0.55, 0.95)
