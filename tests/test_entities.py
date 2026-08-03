"""Entity-lump text parsing, against SPEC-BSP38 §10."""

import pytest

from twig_bb.entities import Entity, parse_entities


def test_a_block_becomes_an_entity_with_its_keys():
    """SPEC-BSP38 §10.2: a block is `{`, quoted key/value pairs, `}`."""
    entities = parse_entities(
        '{\n"classname" "light"\n"origin" "128 -64 192"\n"light" "300"\n}\n')
    assert len(entities) == 1
    assert entities[0].classname == 'light'
    assert entities[0].get('light') == '300'


def test_whitespace_and_line_breaks_between_tokens_are_insignificant():
    """SPEC-BSP38 §10.3."""
    entities = parse_entities('{"classname"\n\t"info_player_start" "origin"   "1 2 3"}')
    assert entities[0].classname == 'info_player_start'
    assert entities[0].vector('origin') == (1.0, 2.0, 3.0)


def test_a_repeated_key_keeps_the_last_occurrence():
    """SPEC-BSP38 §10.3: the parsing convention is last-one-wins."""
    entities = parse_entities('{"classname" "a" "speed" "100" "speed" "250"}')
    assert entities[0].get('speed') == '250'


def test_several_blocks_parse_in_file_order():
    """SPEC-BSP38 §10.7: the first block is conventionally worldspawn."""
    entities = parse_entities('{"classname" "worldspawn"}{"classname" "light"}')
    assert [e.classname for e in entities] == ['worldspawn', 'light']


def test_a_nul_terminator_and_trailing_padding_are_ignored():
    """SPEC-BSP38 §10.1: the lump length includes any terminator."""
    entities = parse_entities(b'{"classname" "worldspawn"}\x00\x00\x00')
    assert [e.classname for e in entities] == ['worldspawn']


def test_line_and_block_comments_are_skipped():
    """SPEC-BSP38 §10.8: `//` and `/* */` may appear and must be skipped."""
    text = ('// leading note\n'
            '{\n"classname" "light"\n/* a block\n   comment */\n"light" "50"\n}\n')
    entities = parse_entities(text)
    assert len(entities) == 1
    assert entities[0].get('light') == '50'


def test_a_comment_marker_inside_a_quoted_value_is_kept():
    """Quoting wins over commenting: `//` inside a value is data, not a comment."""
    entities = parse_entities('{"classname" "light" "note" "a // b"}')
    assert entities[0].get('note') == 'a // b'


def test_unknown_keys_are_tolerated_and_preserved():
    """SPEC-BSP38 §10.4: a reader must tolerate keys it does not recognise."""
    entities = parse_entities('{"classname" "x" "_lightmapscale" "0.5"}')
    assert entities[0].get('_lightmapscale') == '0.5'


def test_a_missing_key_reads_as_the_supplied_default():
    entities = parse_entities('{"classname" "x"}')
    assert entities[0].get('nope') is None
    assert entities[0].get('nope', 'fallback') == 'fallback'


def test_vector_values_are_whitespace_separated_decimals():
    """SPEC-BSP38 §10.4: vector values hold whitespace-separated decimals, x y z."""
    entities = parse_entities('{"origin" "-1072 154.5 -40"}')
    assert entities[0].vector('origin') == (-1072.0, 154.5, -40.0)


def test_a_short_vector_is_padded_and_a_long_one_truncated():
    """A malformed vector must not raise; a reader converts what is there."""
    entities = parse_entities('{"a" "5" "b" "1 2 3 4"}')
    assert entities[0].vector('a') == (5.0, 0.0, 0.0)
    assert entities[0].vector('b') == (1.0, 2.0, 3.0)


def test_a_nonnumeric_vector_falls_back_to_the_default():
    entities = parse_entities('{"origin" "not numbers"}')
    assert entities[0].vector('origin', default=(9.0, 9.0, 9.0)) == (9.0, 9.0, 9.0)


def test_number_reads_a_scalar_key():
    entities = parse_entities('{"speed" "0"}')
    assert entities[0].number('speed') == 0.0
    assert entities[0].number('missing', 7.0) == 7.0
    assert entities[0].number('speed', 7.0) == 0.0


def test_a_nonnumeric_scalar_falls_back_to_the_default():
    entities = parse_entities('{"speed" "fast"}')
    assert entities[0].number('speed', 3.0) == 3.0


def test_a_brush_model_reference_yields_its_model_index():
    """SPEC-BSP38 §10.5: `"model" "*3"` indexes the models lump; index >= 1."""
    entities = parse_entities('{"classname" "func_door" "model" "*3"}')
    assert entities[0].brush_model() == 3


def test_an_external_model_name_is_not_a_brush_model():
    """SPEC-BSP38 §10.6: a value with no asterisk names an external asset."""
    entities = parse_entities('{"classname" "misc_model" "model" "models/tree.md2"}')
    assert entities[0].brush_model() is None


def test_a_malformed_brush_model_reference_is_not_a_brush_model():
    entities = parse_entities('{"model" "*"}{"model" "*x"}{"model" "*0"}')
    assert [e.brush_model() for e in entities] == [None, None, None]


def test_an_entity_without_a_classname_reads_as_empty():
    entities = parse_entities('{"origin" "0 0 0"}')
    assert entities[0].classname == ''


def test_an_empty_lump_yields_no_entities():
    assert parse_entities('') == []
    assert parse_entities(b'\x00') == []


def test_an_unterminated_block_still_yields_the_pairs_it_had():
    """Truncated lumps exist; salvage rather than raise (SPEC-BSP38 §12.1)."""
    entities = parse_entities('{"classname" "light" "light" "200"')
    assert entities[0].classname == 'light'


def test_a_dangling_key_with_no_value_is_dropped():
    entities = parse_entities('{"classname" "light" "orphan"}')
    assert entities[0].get('orphan') is None
    assert entities[0].classname == 'light'


def test_text_outside_a_block_is_ignored():
    entities = parse_entities('junk "stray" {"classname" "light"} more junk')
    assert [e.classname for e in entities] == ['light']


def test_entities_are_hashable_value_objects():
    a = Entity({'classname': 'light'})
    b = Entity({'classname': 'light'})
    assert a == b
    assert len({a, b}) == 1


def test_non_utf8_bytes_decode_without_raising():
    """SPEC-BSP38 §10.1 calls the lump ASCII by convention; real maps stray."""
    entities = parse_entities(b'{"classname" "light" "message" "caf\xe9"}')
    assert entities[0].classname == 'light'


def test_iterating_an_entity_yields_its_keys():
    entity = parse_entities('{"classname" "light" "light" "300"}')[0]
    assert set(entity) == {'classname', 'light'}
    assert len(entity) == 2


@pytest.mark.parametrize('value,expected', [
    ('0', 0.0), ('-1', -1.0), ('1e3', 1000.0), ('.5', 0.5), ('360', 360.0),
])
def test_numeric_formats_seen_in_maps_parse(value, expected):
    entities = parse_entities('{"speed" "%s"}' % value)
    assert entities[0].number('speed') == expected
