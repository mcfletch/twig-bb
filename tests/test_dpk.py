"""`.dpk` package names, versions and dependency resolution — ``SPEC-DPK``.

The cases are the spec's own observations: the real filenames and the real
`DEPS` contents it tabulates, so a passing test says this reader agrees with
what was measured rather than with itself.
"""

from __future__ import annotations

import io
import os
import zipfile

import pytest

from twig_bb import dpk


def _package(tmp_path, filename: str, deps: str = None) -> str:
    """A `.dpk` on disk, holding a `DEPS` if one is given."""
    path = tmp_path / filename
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.writestr('README.md', 'x')
        if deps is not None:
            archive.writestr(dpk.DEPS_NAME, deps)
    path.write_bytes(buffer.getvalue())
    return str(path)


# -- names and versions ------------------------------------------------------

@pytest.mark.parametrize('filename,name,version', [
    # SPEC-DPK §C.1 -- the corpus filenames.
    ('map-plat23_1.14.dpk', 'map-plat23', '1.14'),
    ('tex-all_2.3.dpk', 'tex-all', '2.3'),
    ('res-buildables_0.54.1.dpk', 'res-buildables', '0.54.1'),
    ('unvanquished_0.56.2.dpk', 'unvanquished', '0.56.2'),
    # §2.8 -- a bare integer version.
    ('map-yocto_1.dpk', 'map-yocto', '1'),
    # §2.9 -- `-` lives *inside* a version and must not split the name.
    ('res-weapons_0.54-dirty.dpk', 'res-weapons', '0.54-dirty'),
    ('bugfix_0.52.1-20210624-032404-b3fe650-slipher.dpk',
     'bugfix', '0.52.1-20210624-032404-b3fe650-slipher'),
    # §2.6 -- `-` is an ordinary name character too.
    ('map-methane-beta1_1.0.dpk', 'map-methane-beta1', '1.0'),
])
def test_a_package_filename_splits_into_name_and_version(filename, name, version):
    """SPEC-DPK §2.1, §2.2: `<name>_<version>.dpk`, one separator."""
    assert dpk.split_name(filename) == (name, version)


def test_a_filename_with_no_separator_has_no_version():
    """SPEC-DPK §2.2: the published listing carries two such non-packages."""
    assert dpk.split_name('PAKSERVER') == ('PAKSERVER', '')


def test_the_full_path_is_accepted_as_well_as_the_bare_name():
    assert dpk.split_name('/a/b/map-plat23_1.14.dpk') == ('map-plat23', '1.14')


# -- version ordering --------------------------------------------------------

def test_versions_compare_component_wise_as_integers():
    """SPEC-DPK §3.2: the ordering the whole published population agrees with."""
    assert dpk.version_key('1') < dpk.version_key('1.0.1')
    assert dpk.version_key('1.0.4') < dpk.version_key('1.1')
    assert dpk.version_key('0.56.0') < dpk.version_key('0.56.1')


def test_the_ordering_holds_where_a_string_comparison_would_break():
    """SPEC-DPK §3.7: two digits beside one is where strings go wrong.

    No *published* pair disagrees (``§3.6``), so this is the case the rule
    exists for rather than one it currently fixes — which is precisely why it
    needs a test: nothing in the shipped content would catch a regression.
    """
    assert dpk.version_key('1.9') < dpk.version_key('1.10')
    assert '1.9' > '1.10', 'the string comparison this rule exists to avoid'


def test_a_version_that_is_not_purely_numeric_is_incomparable():
    """SPEC-DPK §3.5: not coerced to something that merely looks adjacent."""
    assert dpk.version_key('0.54-dirty') is None
    assert dpk.version_key('') is None


def test_the_newest_package_wins_and_prefers_a_parseable_version():
    """SPEC-DPK §3.4, §3.5."""
    versions = ['tex-vega_1.4.dpk', 'tex-vega_1.4.1.dpk', 'tex-vega_1.4.3.dpk',
                'tex-vega_1.5.dpk', 'tex-vega_1.4.4.dpk']
    assert dpk.newest(versions) == 'tex-vega_1.5.dpk'
    assert dpk.newest(['a_0.54-dirty.dpk', 'a_0.53.dpk']) == 'a_0.53.dpk'
    assert dpk.newest([]) is None


def test_only_unparseable_versions_still_yield_an_answer():
    assert dpk.newest(['a_x.dpk', 'a_y.dpk']) == 'a_x.dpk'


# -- the DEPS grammar --------------------------------------------------------

def test_a_bare_name_is_a_requirement_with_no_version():
    """SPEC-DPK §4.5: 35 of the corpus's 39 lines are this shape."""
    assert dpk.parse_deps('tex-common\ntex-pk02\ntex-space\n') == [
        dpk.Requirement('tex-common'), dpk.Requirement('tex-pk02'),
        dpk.Requirement('tex-space')]


def test_a_name_and_a_version_are_separated_by_one_space():
    """SPEC-DPK §4.5, §4.6: the four versioned lines the corpus holds."""
    assert dpk.parse_deps('unvanquished 0.56.0\n') == [
        dpk.Requirement('unvanquished', '0.56.0')]


def test_the_file_order_is_preserved():
    """SPEC-DPK §4.11, §4.12: unsorted, and the order is kept in case it means
    something."""
    text = ('tex-common\nres-players\nres-weapons\nres-buildables\n'
            'res-voices\nres-soundtrack\nres-legacy\n')
    assert [r.name for r in dpk.parse_deps(text)] == [
        'tex-common', 'res-players', 'res-weapons', 'res-buildables',
        'res-voices', 'res-soundtrack', 'res-legacy']


def test_blank_lines_are_skipped_and_whitespace_stripped():
    """SPEC-DPK §4.14: tolerant of hand editing, mis-handling nothing observed."""
    assert dpk.parse_deps('\n  tex-common  \n\n\ttex-pk02\n\n') == [
        dpk.Requirement('tex-common'), dpk.Requirement('tex-pk02')]


def test_no_comment_syntax_is_invented():
    """SPEC-DPK §4.14: the observed grammar makes this a package name."""
    assert dpk.parse_deps('#tex-common\n') == [dpk.Requirement('#tex-common')]


def test_a_package_with_no_deps_file_depends_on_nothing(tmp_path):
    """SPEC-DPK §4.2: ordinary, and not an error; 4 of 15 are like this."""
    assert dpk.read_deps(_package(tmp_path, 'tex-common_2.5.dpk')) == []


def test_deps_are_read_from_an_archive(tmp_path):
    path = _package(tmp_path, 'map-plat23_1.14.dpk', 'tex-common\ntex-pk02\n')
    assert [r.name for r in dpk.read_deps(path)] == ['tex-common', 'tex-pk02']


def test_deps_are_read_from_an_unpacked_package(tmp_path):
    """A package already extracted answers the same as its archive."""
    directory = tmp_path / 'map-plat23_1.14'
    directory.mkdir()
    (directory / dpk.DEPS_NAME).write_text('tex-common\n')
    assert dpk.read_deps(str(directory)) == [dpk.Requirement('tex-common')]


def test_an_unreadable_package_reports_no_dependencies(tmp_path):
    broken = tmp_path / 'broken_1.0.dpk'
    broken.write_bytes(b'not a zip')
    assert dpk.read_deps(str(broken)) == []


# -- resolution --------------------------------------------------------------

def test_dependencies_resolve_transitively(tmp_path):
    """SPEC-DPK §4.15: `map-yocto` -> `tex-all` -> nine texture packages."""
    _package(tmp_path, 'tex-common_2.5.dpk')
    _package(tmp_path, 'tex-pk02_1.3.2.dpk')
    _package(tmp_path, 'tex-all_2.3.dpk', 'tex-common\ntex-pk02\n')
    top = _package(tmp_path, 'map-yocto_1.1.dpk', 'tex-all\n')
    order, missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    assert [dpk.split_name(p)[0] for p in order] == [
        'map-yocto', 'tex-all', 'tex-common', 'tex-pk02']
    assert missing == []


def test_the_package_itself_comes_first(tmp_path):
    """The viewer's own precedence choice (``SPEC-DPK §7.4``): a map's content
    shadows the art packs it draws from."""
    _package(tmp_path, 'tex-common_2.5.dpk')
    top = _package(tmp_path, 'map-plat23_1.14.dpk', 'tex-common\n')
    order, _missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    assert order[0] == top


def test_a_cycle_terminates(tmp_path):
    """SPEC-DPK §4.16: nothing in the data forbids one, so it must not hang."""
    _package(tmp_path, 'a_1.dpk', 'b\n')
    _package(tmp_path, 'b_1.dpk', 'a\n')
    top = _package(tmp_path, 'top_1.dpk', 'a\n')
    order, missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    assert [dpk.split_name(p)[0] for p in order] == ['top', 'a', 'b']
    assert missing == []


def test_a_diamond_is_collected_once(tmp_path):
    _package(tmp_path, 'shared_1.dpk')
    _package(tmp_path, 'left_1.dpk', 'shared\n')
    _package(tmp_path, 'right_1.dpk', 'shared\n')
    top = _package(tmp_path, 'top_1.dpk', 'left\nright\n')
    order, _missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    names = [dpk.split_name(p)[0] for p in order]
    assert names.count('shared') == 1
    assert names == ['top', 'left', 'right', 'shared']


def test_an_absent_dependency_is_reported_not_fatal(tmp_path):
    """A map with some of its art draws better than no map at all."""
    top = _package(tmp_path, 'map-plat23_1.14.dpk', 'tex-common\ntex-pk02\n')
    order, missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    assert order == [top]
    assert missing == ['tex-common', 'tex-pk02']


def test_the_highest_version_of_a_dependency_is_chosen(tmp_path):
    _package(tmp_path, 'tex-vega_1.4.dpk')
    _package(tmp_path, 'tex-vega_1.5.dpk')
    _package(tmp_path, 'tex-vega_1.4.4.dpk')
    top = _package(tmp_path, 'map-vega_1.0.dpk', 'tex-vega\n')
    order, _missing = dpk.resolve(top, dpk.available(str(tmp_path)))
    assert os.path.basename(order[1]) == 'tex-vega_1.5.dpk'


def test_available_finds_archives_and_unpacked_packages(tmp_path):
    _package(tmp_path, 'tex-common_2.5.dpk')
    (tmp_path / 'tex-pk02_1.3.2').mkdir()
    found = dpk.available(str(tmp_path))
    assert set(found) == {'tex-common', 'tex-pk02'}
