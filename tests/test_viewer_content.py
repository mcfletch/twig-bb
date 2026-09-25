"""What the game does when a download on its content screen ends.

The methods are the context's own, bound to a stand-in holding only what they
read, since a context proper opens a window.
"""

import os
import types

from twig_bb import download, menu, viewer


class _Marks:
    def __init__(self):
        self.said = []

    def downloaded(self, job):
        self.said.append(job)


def a_context(tmp_path):
    context = types.SimpleNamespace(
        config=types.SimpleNamespace(content=[], cache_dir=str(tmp_path)),
        marks=_Marks(), _content=None)
    for name in ('_downloadFinished', '_missingPacks'):
        setattr(context, name,
                getattr(viewer.TwigContext, name).__get__(context))
    return context


def test_what_arrived_is_added_to_the_content_searched(tmp_path):
    root = tmp_path / 'packs' / 'twig-bb' / 'maps'
    (root / 'maps').mkdir(parents=True)
    context = a_context(tmp_path)
    job = types.SimpleNamespace(roots=[str(root)], failed=None,
                                cancelled=False)
    context._downloadFinished(job)
    assert context.config.content == [str(root)]
    assert context.marks.said == [job]


def test_the_offer_loses_what_arrived(tmp_path):
    context = a_context(tmp_path)
    everything = context._missingPacks()
    context._content = menu.download_screen(everything)
    pack = everything[0]
    # On disk as a download leaves it: its marker, or anything at all.
    where = download.store(str(tmp_path)).directory_for(pack)
    os.makedirs(os.path.join(where, pack.marker or 'something'))
    context._downloadFinished(types.SimpleNamespace(
        roots=[], failed=None, cancelled=False))
    assert pack not in context._content.packs
