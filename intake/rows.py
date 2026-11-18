from dataclasses import dataclass
from fractions import Fraction

from scales.projects import require_label
from scales.rationals import encode_rational, parse_rational


@dataclass(frozen=True)
class ObservationRow:
    row_key: str
    x: Fraction | None
    y: Fraction | None

    def encoded(self):
        return (
            self.row_key,
            None if self.x is None else encode_rational(self.x),
            None if self.y is None else encode_rational(self.y),
        )


def normalize_rows(rows):
    if isinstance(rows, (str, bytes, dict)):
        raise ValueError('expected an iterable of observation triples')
    try:
        items = iter(rows)
    except TypeError as exc:
        raise ValueError('expected an iterable of observation triples') from exc
    by_key = {}
    for item in items:
        if not isinstance(item, (list, tuple)) or len(item) != 3:
            raise ValueError('expected a row key and two axis values')
        key, x, y = item
        require_label(key, 'row key')
        if key in by_key:
            raise ValueError(f'duplicate row key: {key}')
        by_key[key] = ObservationRow(
            key,
            None if x is None else parse_rational(x),
            None if y is None else parse_rational(y),
        )
    return tuple(by_key[key] for key in sorted(by_key))
