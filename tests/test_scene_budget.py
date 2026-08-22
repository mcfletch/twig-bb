"""How much scene a level is allowed to put in front of the renderer.

The flat render pass charges per **node-path**, not per visible shape: every
Rendering path in the scene gets a world matrix, a sort key, a bounding volume
and a frustum test on every frame, whether or not anything comes of it. A body
parked out of sight is therefore not free, and a level that mounts thousands of
them spends its frame deciding not to draw them.

That cost is invisible to a test that asks whether a thing looks right, and
invisible to one that times a ratio between two render modes, since both modes
pay it. What it is visible to is counting, so these count. The numbers are
budgets rather than measurements of the moment: a scene that grows past one is
not wrong on screen, it is a frame rate nobody has spent yet.

Counting uses :func:`OpenGLContext.visitor.find`, which walks the scenegraph the
way the render pass does, so the number here is the number the pass will pay. No
GL is involved -- these run headless with the rest of the suite.
"""

from __future__ import annotations

import pytest

from OpenGLContext import visitor
from vrml.vrml97 import nodetypes

from twig_bb import game, maploader, projectiles, rules, viewer, weapons

#: What one frame at sixty a second affords, in node-paths.  The pass spends on
#: the order of six microseconds of Python per path per frame gathering and
#: culling; 16.7ms therefore buys a few thousand before the gather alone is the
#: whole frame.  A level is allowed a fraction of that, because the gather is
#: overhead -- nothing on screen is any better for it.
LEVEL_PATH_BUDGET = 1500

#: What the bodies for things in flight may cost.  A projectile model has parts,
#: and the number of parts is the artist's business; how many *slots* are drawn
#: is this game's, and it is the only lever here that does not touch the art.
#: The batch's own capacity is a simulation budget and can stay far larger --
#: what is bounded is how much of it is standing in the scenegraph.
POOL_PATH_BUDGET = 512


def rendering_paths(node) -> int:
    """How many Rendering paths ``node`` presents to the render pass."""
    return len(visitor.find(node, nodetypes.Rendering))


def config(**over):
    options = viewer.build_parser().parse_args([])
    for key, value in over.items():
        setattr(options, key, value)
    return options


class TestTheBodiesForThingsInFlight:
    """What a match mounts to draw things in flight, however many there are."""

    def a_full_sky(self, bodies, count):
        """Put ``count`` rockets in the air and draw them."""
        table = projectiles.default_table()
        flight = projectiles.Projectiles(table, capacity=count)
        for index in range(count):
            flight.launch(table.by_key(projectiles.ROCKET),
                          origin=(float(index), 0.0, 0.0),
                          direction=(1, 0, 0), owner='player')
        game.move_projectiles(flight, bodies)

    def test_the_pool_a_match_mounts_stays_within_budget(self):
        group, _bodies = game.projectile_bodies()
        paths = rendering_paths(group)
        assert paths <= POOL_PATH_BUDGET, (
            '%d node-paths of projectile bodies: every one of them is '
            'gathered and frustum-tested on every frame' % (paths,))

    def test_a_sky_full_of_rockets_costs_no_more_than_an_empty_one(self):
        """The property the budget rests on: copies are matrices, not nodes."""
        group, bodies = game.projectile_bodies()
        empty = rendering_paths(group)
        self.a_full_sky(bodies, 200)
        assert rendering_paths(group) == empty


class TestWhatALevelPresents:
    """The whole drawable scene, counted the way the pass counts it."""

    def _level(self, path, bots=0):
        return viewer.load_level(config(bots=bots), weapons.default_table(), path)

    def _drawables(self, bundle):
        """The groups a mounted level contributes, each built without a window."""
        return {
            'map': bundle.loaded.scene(None),
            'bots': bundle.botGroup,
            'pickups': game.item_bodies(bundle.rules.pickups)[0],
            'effects': bundle.effects.group,
            'projectiles': bundle.projectileGroup,
        }

    def test_a_real_map_stays_within_budget(self, quake3_map):
        bundle = self._level(quake3_map, bots=4)
        counted = {name: rendering_paths(node)
                   for name, node in self._drawables(bundle).items()}
        total = sum(counted.values())
        assert total <= LEVEL_PATH_BUDGET, (
            '%d node-paths in the level: %s' % (total, counted))

    def test_the_map_geometry_is_a_small_part_of_it(self, quake3_map):
        """A level's own walls are batched, and a batch is one path.

        Said out loud because it is what makes the budget above reasonable: the
        geometry a player is actually looking at is tens of paths, so anything
        in the thousands is something else.
        """
        bundle = self._level(quake3_map)
        assert rendering_paths(bundle.loaded.scene(None)) < 200
