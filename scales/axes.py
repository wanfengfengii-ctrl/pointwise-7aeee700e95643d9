from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction

from scales.projects import validate_axis_mapping
from scales.rationals import parse_rational


MAPPING_KEYS = ('input_axis', 'input_unit', 'output_axis', 'output_unit')
TRANSFORM_KEYS = {*MAPPING_KEYS, 'slope', 'offset'}


@dataclass(frozen=True)
class AxisTransform:
    slope: Fraction
    offset: Fraction

    def apply(self, value):
        return self.slope * value + self.offset


def _mapping(spec):
    if not isinstance(spec, Mapping) or spec.keys() != TRANSFORM_KEYS:
        raise ValueError('expected an axis mapping with units, slope and offset')
    return tuple(spec[key] for key in MAPPING_KEYS)


def _transform(spec):
    slope = parse_rational(spec['slope'])
    offset = parse_rational(spec['offset'])
    if slope == 0:
        raise ValueError('axis slope must be nonzero')
    return AxisTransform(slope, offset)


def make_axis_transforms(project, bench, x, y):
    validate_axis_mapping(project, bench, _mapping(x), _mapping(y))
    return _transform(x), _transform(y)
