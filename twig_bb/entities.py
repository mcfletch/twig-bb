"""The entity lump: brace-delimited blocks of quoted key/value pairs.

Both map families store their entity lump as the same plain text, so one parser
serves them: see ``SPEC-BSP38 §10`` for the syntax and ``SPEC-BSP46 §5.1``,
which adopts it unchanged.  An :class:`Entity` is a read-only mapping of the
keys one block carried, plus the conversions every consumer needs — scalars,
xyz vectors, and the ``"*N"`` brush-model reference of ``SPEC-BSP38 §10.5``.

Everything downstream that cares about *what* an entity means — spawn points,
lights, push volumes — reads that meaning off these objects rather than
re-parsing text.
"""

from __future__ import annotations

from typing import Dict, Iterator, List, Mapping, Optional, Tuple, Union

Vector3 = Tuple[float, float, float]

# SPEC-BSP38 §10.5: a brush-model reference is an asterisk then a decimal index
# into the models lump, and the index is always 1 or greater -- model 0 is the
# world and is never referenced this way.
BRUSH_MODEL_PREFIX = '*'
FIRST_BRUSH_MODEL = 1


class Entity(Mapping[str, str]):
    """One entity block: its keys, and the conversions consumers need.

    Immutable and hashable, so entities can be collected in sets and used as
    dictionary keys while a map is being built.
    """

    __slots__ = ('_keys', '_hash')

    def __init__(self, keys: Mapping[str, str]) -> None:
        self._keys: Dict[str, str] = dict(keys)
        self._hash: Optional[int] = None

    # -- mapping protocol ------------------------------------------------
    def __getitem__(self, key: str) -> str:
        return self._keys[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._keys)

    def __len__(self) -> int:
        return len(self._keys)

    def __repr__(self) -> str:
        return 'Entity(%r)' % (self._keys,)

    def __hash__(self) -> int:
        if self._hash is None:
            self._hash = hash(frozenset(self._keys.items()))
        return self._hash

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Entity):
            return self._keys == other._keys
        return NotImplemented

    # -- typed access ----------------------------------------------------
    @property
    def classname(self) -> str:
        """The ``classname`` key (``SPEC-BSP38 §10.4``), or '' when absent."""
        return self._keys.get('classname', '')

    def number(self, key: str, default: float = 0.0) -> float:
        """The key read as a number, or ``default`` when absent or unparsable."""
        try:
            return float(self._keys[key])
        except (KeyError, ValueError):
            return default

    def vector(self, key: str, default: Vector3 = (0.0, 0.0, 0.0)) -> Vector3:
        """The key read as an xyz triple (``SPEC-BSP38 §10.4``).

        A value with fewer than three components is padded with zeroes and one
        with more is truncated, so a malformed key degrades rather than raising.
        """
        raw = self._keys.get(key)
        if raw is None:
            return default
        try:
            values = [float(part) for part in raw.split()]
        except ValueError:
            return default
        if not values:
            return default
        values = (values + [0.0, 0.0, 0.0])[:3]
        return (values[0], values[1], values[2])

    def brush_model(self) -> Optional[int]:
        """The models-lump index this entity's geometry is, or None.

        ``SPEC-BSP38 §10.5``: an asterisk followed by a decimal index of 1 or
        more.  ``SPEC-BSP38 §10.6``: a value with no asterisk names an external
        model asset, which is not a brush model.
        """
        raw = self._keys.get('model', '')
        if not raw.startswith(BRUSH_MODEL_PREFIX):
            return None
        try:
            index = int(raw[1:])
        except ValueError:
            return None
        return index if index >= FIRST_BRUSH_MODEL else None


def parse_entities(source: Union[str, bytes]) -> List[Entity]:
    """Parse an entity lump into its blocks, in file order.

    ``SPEC-BSP38 §10.1``: the lump is text, conventionally ASCII and
    NUL-terminated, and its stored length includes the terminator.  Real maps
    are not reliably ASCII, so bytes are decoded latin-1 — every byte maps to a
    character, so no map is rejected for a stray high byte in a `message` key.

    Malformed input is salvaged rather than rejected (``SPEC-BSP38 §12.1``): an
    unterminated block yields the pairs it did carry, a key with no value is
    dropped, and text outside a block is ignored.
    """
    text = source.decode('latin-1') if isinstance(source, bytes) else source
    entities: List[Entity] = []
    keys: Dict[str, str] = {}
    pending: Optional[str] = None
    in_block = False
    for token in _tokenize(text):
        if token == '{':
            in_block, keys, pending = True, {}, None
        elif token == '}':
            if in_block:
                entities.append(Entity(keys))
            in_block, keys, pending = False, {}, None
        elif in_block and token[0] == '"':
            value = token[1:-1]
            if pending is None:
                pending = value
            else:
                # SPEC-BSP38 §10.3: when a key repeats, the last one wins.
                keys[pending] = value
                pending = None
    if in_block and keys:
        entities.append(Entity(keys))
    return entities


def _tokenize(text: str) -> Iterator[str]:
    """Yield `{`, `}` and quoted strings (quotes included), skipping comments.

    ``SPEC-BSP38 §10.3``: neither a key nor a value may contain a double quote,
    so a quoted run always ends at the next quote.  ``SPEC-BSP38 §10.8``: `//`
    line comments and `/* */` block comments may appear and are skipped — but
    only outside a quoted string, so a value may contain either marker.
    """
    index, length = 0, len(text)
    while index < length:
        char = text[index]
        if char == '"':
            end = text.find('"', index + 1)
            if end < 0:
                return                      # unterminated string: stop cleanly
            yield text[index:end + 1]
            index = end + 1
        elif char in '{}':
            yield char
            index += 1
        elif text.startswith('//', index):
            end = text.find('\n', index)
            index = length if end < 0 else end + 1
        elif text.startswith('/*', index):
            end = text.find('*/', index + 2)
            index = length if end < 0 else end + 2
        else:
            index += 1
