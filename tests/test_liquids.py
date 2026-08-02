"""Liquid volumes: where the avatar is under water rather than in air.

Which leaves hold a liquid is a format fact and differs by family, so the two
readings are tested against built maps; what a viewer asks — "am I in one?" —
is the same question either way.
"""

from __future__ import annotations

import numpy as np
import pytest

import bspbuilder
from twitchoglc import liquids, maploader, q2bsp
from twitchoglc.worldgeometry import SCENE_SCALE, to_scene_points


def _volumes(*boxes):
    return liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array(lo, 'd'), maxs=np.array(hi, 'd'))
        for lo, hi in boxes])


def test_a_point_inside_a_volume_is_submerged():
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert volumes.contains((5, 2, 5))


def test_a_point_outside_every_volume_is_not():
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert not volumes.contains((5, 8, 5))
    assert not volumes.contains((-1, 2, 5))


def test_the_faces_of_a_volume_count_as_inside():
    """A camera exactly on the surface should read as in the water rather than
    flickering between modes as it bobs."""
    volumes = _volumes(((0, 0, 0), (10, 5, 10)))
    assert volumes.contains((0, 0, 0))
    assert volumes.contains((10, 5, 10))


def test_any_of_several_volumes_counts():
    volumes = _volumes(((0, 0, 0), (1, 1, 1)), ((20, 0, 20), (30, 5, 30)))
    assert volumes.contains((25, 1, 25))


def test_a_map_with_no_liquid_is_never_submerged():
    assert not liquids.LiquidVolumes([]).contains((0, 0, 0))
    assert not liquids.LiquidVolumes([])


def test_volumes_report_how_many_there_are():
    assert len(_volumes(((0, 0, 0), (1, 1, 1)))) == 1


# -- reading them out of a map ------------------------------------------------

def _v38_map(tmp_path, contents, name='liquid.bsp'):
    """A version 38 map with one leaf carrying ``contents``."""
    lumps = bspbuilder.v38_quad(size=512.0)
    leaves = np.zeros(2, dtype=q2bsp.LEAF)
    leaves[0]['contents'] = q2bsp.CONTENTS_SOLID
    leaves[1]['contents'] = contents
    leaves[1]['mins'] = (0, 0, 0)
    leaves[1]['maxs'] = (128, 256, 64)
    lumps['leafs'] = leaves.tobytes()
    path = tmp_path / name
    path.write_bytes(bspbuilder.build(38, lumps))
    return str(path)


@pytest.mark.parametrize('contents', [q2bsp.CONTENTS_WATER, q2bsp.CONTENTS_SLIME,
                                      q2bsp.CONTENTS_LAVA])
def test_a_version_38_leaf_of_liquid_becomes_a_volume(tmp_path, contents):
    """`SPEC-BSP38 §9.4`: water, slime and lava are the liquids."""
    loaded = maploader.load(_v38_map(tmp_path, contents))
    volumes = liquids.from_map(loaded)
    assert len(volumes) == 1


def test_a_version_38_solid_leaf_is_not_a_volume(tmp_path):
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_SOLID))
    assert not liquids.from_map(loaded)


def test_a_leaf_that_is_both_liquid_and_something_else_still_counts(tmp_path):
    """`SPEC-BSP38 §9.1`: contents bits combine freely."""
    loaded = maploader.load(
        _v38_map(tmp_path, q2bsp.CONTENTS_WATER | q2bsp.CONTENTS_TRANSLUCENT))
    assert len(liquids.from_map(loaded)) == 1


def test_the_volume_is_in_scene_space(tmp_path):
    """Map units are inches on a Z-up axis; the scene is metres and Y-up
    (`SPEC-BSP38 §3.2`), so a volume read in map units puts the swimmer in the
    wrong place by a factor of forty."""
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_WATER))
    volume = liquids.from_map(loaded)._volumes[0]
    extent = volume.maxs - volume.mins
    assert sorted(np.round(extent, 6)) == pytest.approx(
        sorted(np.round(np.array([128.0, 256.0, 64.0]) * SCENE_SCALE, 6)))


def test_the_volume_bounds_are_ordered_after_the_axis_swap(tmp_path):
    """The axis convention negates a coordinate, so a min can come out above a
    max and the box would contain nothing at all."""
    loaded = maploader.load(_v38_map(tmp_path, q2bsp.CONTENTS_WATER))
    volume = liquids.from_map(loaded)._volumes[0]
    assert (volume.maxs >= volume.mins).all()


def _v46_map(tmp_path, lumps, shader=''):
    """A version 46 map in a content tree, with an optional shader script."""
    maps = tmp_path / 'maps'
    maps.mkdir(parents=True, exist_ok=True)
    path = maps / 'liquid.bsp'
    path.write_bytes(bspbuilder.build(46, lumps))
    if shader:
        scripts = tmp_path / 'scripts'
        scripts.mkdir(exist_ok=True)
        (scripts / 'liquids.shader').write_text(shader)
    return maploader.load(str(path))


WATER_SHADER = """
textures/liquids/water
{
    surfaceparm water
    {
        map textures/liquids/water.tga
    }
}
"""


def test_a_map_whose_family_has_no_leaf_contents_reads_its_brushes(tmp_path):
    """`SPEC-BSP46 §4.4.1`: a version 46 leaf carries no contents word, so the
    liquid is found through the brushes the leaf holds and the material script
    that says what their texture is (`SPEC-Q3SHADER §2.2`)."""
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), WATER_SHADER)
    assert len(liquids.from_map(loaded)) == 1


def test_a_version_46_brush_whose_texture_is_not_a_liquid_is_no_volume(tmp_path):
    loaded = _v46_map(tmp_path, bspbuilder.v46_water())    # no script: not water
    assert not liquids.from_map(loaded)


def test_a_version_46_map_with_no_brushes_has_no_volumes(tmp_path):
    loaded = _v46_map(tmp_path, bspbuilder.v46_quad(), WATER_SHADER)
    assert not liquids.from_map(loaded)


def test_a_version_46_map_read_with_no_material_scripts_has_no_liquids(tmp_path):
    """A brush names a texture and only a script says whether that texture is
    water, so nothing is liquid without one."""
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), WATER_SHADER)
    loaded.style_for = None
    assert not liquids.from_map(loaded)


def test_a_leaf_holding_no_brushes_is_skipped(tmp_path):
    """Most leaves hold none, and indexing a zero-length run would read the
    brush belonging to the next leaf."""
    lumps = bspbuilder.v46_water()
    lumps['leafs'] = (bspbuilder.v46_leaf(cluster=0)          # no brushes
                      + bspbuilder.v46_leaf(cluster=1, mins=(0, 0, -32),
                                            maxs=(64, 64, 0),
                                            leafbrush=0, n_leafbrushes=1))
    loaded = _v46_map(tmp_path, lumps, WATER_SHADER)
    assert len(liquids.from_map(loaded)) == 1


def test_a_version_38_map_with_no_leaves_has_no_liquids(tmp_path):
    lumps = bspbuilder.v38_quad(size=512.0)
    lumps['leafs'] = b''
    path = tmp_path / 'noleaves.bsp'
    path.write_bytes(bspbuilder.build(38, lumps))
    assert not liquids.from_map(maploader.load(str(path)))


# -- which liquid it is -------------------------------------------------------
#
# A volume that only knows it is "a liquid" cannot tint the view its own colour
# and will not be able to hurt the swimmer the right amount; both want the kind.

def _kinded(kind, lo=(0, 0, 0), hi=(10, 5, 10)):
    return liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array(lo, 'd'), maxs=np.array(hi, 'd'),
                             kind=kind)])


def test_the_kind_of_the_volume_a_point_is_in_is_reported():
    assert _kinded(liquids.LAVA).kind_at((5, 2, 5)) == liquids.LAVA


def test_a_point_in_no_volume_has_no_kind(self=None):
    assert _kinded(liquids.WATER).kind_at((99, 99, 99)) == ''


def test_the_innermost_liquid_wins_where_two_overlap():
    """A pool of slime inside a water volume should read as slime.

    Overlap is not hypothetical: a leaf's box is its own bound rather than the
    liquid's exact shape, so neighbouring pools of different liquids overlap at
    their edges, and the more dangerous answer is the one a player needs.
    """
    volumes = liquids.LiquidVolumes([
        liquids.LiquidVolume(mins=np.array((0, 0, 0), 'd'),
                             maxs=np.array((10, 10, 10), 'd'),
                             kind=liquids.WATER),
        liquids.LiquidVolume(mins=np.array((4, 4, 4), 'd'),
                             maxs=np.array((6, 6, 6), 'd'),
                             kind=liquids.LAVA),
    ])
    assert volumes.kind_at((5, 5, 5)) == liquids.LAVA
    assert volumes.kind_at((1, 1, 1)) == liquids.WATER


@pytest.mark.parametrize('contents,kind', [
    (q2bsp.CONTENTS_WATER, liquids.WATER),
    (q2bsp.CONTENTS_SLIME, liquids.SLIME),
    (q2bsp.CONTENTS_LAVA, liquids.LAVA),
])
def test_a_version_38_leaf_says_which_liquid_it_holds(tmp_path, contents, kind):
    """`SPEC-BSP38 §9.4`: the contents word names it outright."""
    loaded = maploader.load(_v38_map(tmp_path, contents))
    assert liquids.from_map(loaded)._volumes[0].kind == kind


def test_a_version_38_leaf_of_two_liquids_reports_the_worse_one(tmp_path):
    """`SPEC-BSP38 §9.1`: the bits combine, and lava is what matters."""
    loaded = maploader.load(
        _v38_map(tmp_path, q2bsp.CONTENTS_WATER | q2bsp.CONTENTS_LAVA))
    assert liquids.from_map(loaded)._volumes[0].kind == liquids.LAVA


#: The same surface the map's brush names, declared as slime instead.  Only the
#: `surfaceparm` differs, which is the point: the texture name says nothing
#: about what the volume is.
SLIME_SHADER = WATER_SHADER.replace('surfaceparm water', 'surfaceparm slime')


def test_a_version_46_brush_says_which_liquid_through_its_material(tmp_path):
    """`SPEC-Q3SHADER §2.2`: the surfaceparm is the only thing that knows."""
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), SLIME_SHADER)
    volumes = liquids.from_map(loaded)
    assert volumes._volumes[0].kind == liquids.SLIME


class TestTheVolumeIsTheLiquidRatherThanTheLeaf:
    """A leaf's bound is far bigger than the pool in it.

    Standing in ankle-deep water fogged the whole view, because the *leaf*
    holding the pool reaches up to the ceiling and the camera was inside that
    long before it was inside the water.  A liquid brush states its own extent
    in its planes, and that is the box a swimmer should be tested against.
    """

    def shallow(self, tmp_path):
        """A leaf reaching the ceiling with a shin-deep pool of water in it."""
        import bspbuilder
        lumps = bspbuilder.v46_water(brush_maxs=(64, 64, -16))
        return _v46_map(tmp_path, lumps, WATER_SHADER)

    def test_the_volume_stops_at_the_top_of_the_water(self, tmp_path):
        volumes = liquids.from_map(self.shallow(tmp_path))
        assert len(volumes) == 1
        top = float(volumes._volumes[0].maxs[1])       # scene +Y is map +Z
        assert top < 0.0

    def test_standing_in_it_with_your_head_out_is_not_submerged(self, tmp_path):
        """The bug: the air went foggy while the water was round your ankles."""
        volumes = liquids.from_map(self.shallow(tmp_path))
        eye = np.array([32.0, 40.0, 32.0]) * SCENE_SCALE   # map z=+40, well above
        assert not volumes.contains((eye[0], eye[1], eye[2]))

    def test_being_under_the_surface_still_is(self, tmp_path):
        volumes = liquids.from_map(self.shallow(tmp_path))
        inside = to_scene_points(np.array([[32.0, 32.0, -24.0]], dtype='f'))[0]
        assert volumes.contains(inside)


def test_a_version_46_water_brush_reads_as_water(tmp_path):
    loaded = _v46_map(tmp_path, bspbuilder.v46_water(), WATER_SHADER)
    assert liquids.from_map(loaded)._volumes[0].kind == liquids.WATER


class TestWhatStandingInItCosts:
    """Slime and lava hurt; water does not.  The rates are ours and declared."""

    def volumes(self, kind, low=(-5.0, -5.0, -5.0), high=(5.0, 0.0, 5.0)):
        return liquids.LiquidVolumes([
            liquids.LiquidVolume(mins=np.array(low), maxs=np.array(high),
                                 kind=kind)])

    def match(self, where=(0.0, -1.0, 0.0)):
        from twitchoglc import arena, weapons
        made = arena.Arena(weapons=weapons.default_table())
        made.add('player', position=where, name='You')
        return made

    def harm(self, kind, seconds=1.0, step=0.1, where=(0.0, -1.0, 0.0)):
        found = self.match(where)
        hurting = liquids.LiquidHarm(self.volumes(kind))
        for _ in range(int(round(seconds / step))):
            hurting.advance(found, step)
        return found

    def test_lava_hurts(self):
        assert self.harm('lava').combatant('player').health < 100

    def test_slime_hurts_less_than_lava(self):
        assert self.harm('slime').combatant('player').health \
            > self.harm('lava').combatant('player').health

    def test_water_does_not_hurt(self):
        assert self.harm('water').combatant('player').health == 100

    def test_standing_clear_of_it_does_not_hurt(self):
        assert self.harm('lava', where=(0.0, 40.0, 0.0)) \
            .combatant('player').health == 100

    def test_it_is_a_periodic_tick_rather_than_a_trickle(self):
        """A number sliding down by one is not a warning; a bite is."""
        found = self.match()
        hurting = liquids.LiquidHarm(self.volumes('lava'))
        hurting.advance(found, liquids.HARM_INTERVAL / 4.0)
        assert found.combatant('player').health == 100
        hurting.advance(found, liquids.HARM_INTERVAL)
        assert found.combatant('player').health < 100

    def test_long_enough_in_lava_kills(self):
        assert not self.harm('lava', seconds=8.0).combatant('player').alive

    def test_the_death_says_what_did_it(self):
        from twitchoglc import arena
        found = self.harm('lava', seconds=8.0)
        deaths = [event for event in found.events
                  if isinstance(event, arena.Death)]
        assert deaths and deaths[-1].cause == 'lava'

    def test_dying_in_it_costs_a_frag(self):
        """The arena's own rule: the quickest route up the board is not the lava."""
        assert self.harm('lava', seconds=8.0).score('player') == -1

    def test_the_dead_are_not_burned_further(self):
        found = self.harm('lava', seconds=12.0)
        assert found.combatant('player').health == 0

    def test_a_map_with_no_liquids_costs_nothing(self):
        found = self.match()
        liquids.LiquidHarm(liquids.LiquidVolumes([])).advance(found, 1.0)
        assert found.combatant('player').health == 100

    def test_the_rates_are_a_declared_table(self):
        """The numbers are ours, so the table is where the design is written."""
        assert liquids.HARM['lava'] > liquids.HARM['slime'] > 0
        assert liquids.HARM.get('water', 0.0) == 0.0

    def test_a_body_standing_under_the_pool_still_burns(self):
        """The one that made lava look as though it only hurt while moving.

        A liquid brush is not solid, so somebody who falls into a pool goes
        through it and stands on whatever is underneath — and a map's floor is
        commonly a hair below where the liquid brush stops.  Asking about the
        *feet* then answers "not in any liquid" for somebody standing waist
        deep in lava, and every step that bobbed them up a centimetre bit them
        once, which is exactly what was reported.
        """
        found = self.match(where=(0.0, -0.05, 0.0))
        hurting = liquids.LiquidHarm(self.volumes(
            'lava', low=(-5.0, 0.0, -5.0), high=(5.0, 3.0, 5.0)))
        for _ in range(10):
            hurting.advance(found, 0.1)
        assert found.combatant('player').health < 100

    def test_standing_beside_a_pool_does_not_burn(self):
        """The body is its own axis, not a radius: a toe over the edge is dry."""
        found = self.match(where=(6.0, 0.0, 0.0))
        hurting = liquids.LiquidHarm(self.volumes(
            'lava', low=(-5.0, 0.0, -5.0), high=(5.0, 3.0, 5.0)))
        for _ in range(10):
            hurting.advance(found, 0.1)
        assert found.combatant('player').health == 100

    def test_the_worst_liquid_a_body_crosses_is_the_one_that_bites(self):
        """Waist deep in lava under a sheet of water is a death, not a swim.

        The *innermost* rule :meth:`kind_at` uses is right for a point and
        wrong for a body: a body spans several volumes at once and what
        matters then is the one that will kill it.
        """
        volumes = liquids.LiquidVolumes([
            liquids.LiquidVolume(mins=np.array((-5.0, 0.0, -5.0)),
                                 maxs=np.array((5.0, 4.0, 5.0)),
                                 kind=liquids.WATER),
            liquids.LiquidVolume(mins=np.array((-1.0, 0.0, -1.0)),
                                 maxs=np.array((1.0, 0.5, 1.0)),
                                 kind=liquids.LAVA),
        ])
        assert volumes.kind_along((0.0, 0.0, 0.0),
                                  liquids.BODY_HEIGHT) == liquids.LAVA

    def test_a_body_clear_of_every_volume_is_in_nothing(self):
        assert _kinded(liquids.LAVA).kind_along((99.0, 99.0, 99.0),
                                                liquids.BODY_HEIGHT) == ''

    def test_a_map_with_no_volumes_answers_nothing_for_a_body(self):
        assert liquids.LiquidVolumes([]).kind_along((0.0, 0.0, 0.0), 1.8) == ''

    def test_every_combatant_is_burned_not_only_the_player(self):
        from twitchoglc import arena, weapons
        found = arena.Arena(weapons=weapons.default_table())
        found.add('player', position=(0.0, -1.0, 0.0))
        found.add('bot1', position=(1.0, -1.0, 0.0), bot=True)
        hurting = liquids.LiquidHarm(self.volumes('lava'))
        for _ in range(10):
            hurting.advance(found, 0.1)
        assert found.combatant('bot1').health < 100
