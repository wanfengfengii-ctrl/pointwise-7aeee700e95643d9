"""封存联合证据：固定刻度下同一行双非空读数的统一坐标配对及重数。"""

import json
from dataclasses import dataclass
from fractions import Fraction

from scales.rationals import decode_rational, encode_rational


@dataclass(frozen=True)
class RankEvidence:
    """完整的联合证据。pairs 为 ``(u, v, multiplicity)`` 元组，按统一坐标排序。"""

    pairs: tuple[tuple[Fraction, Fraction, int], ...]

    @property
    def pair_count(self):
        return sum(multiplicity for _, _, multiplicity in self.pairs)


def build_rank_evidence(pairs, x_axis, y_axis):
    """把同一行双非空的原始配对换算到项目统一轴，按数值归并重数。

    相等值按数值解释（例如 ``1`` 与 ``2/2`` 相等），归并后的配对按
    ``(u, v)`` 升序排列，保证相同证据有稳定的规范形态。
    """
    grouped = {}
    for x, y in pairs:
        point = (x_axis.apply(x), y_axis.apply(y))
        grouped[point] = grouped.get(point, 0) + 1
    ordered = tuple(
        (u, v, multiplicity)
        for (u, v), multiplicity in sorted(grouped.items(), key=lambda item: item[0])
    )
    return RankEvidence(ordered)


def encode_rank_evidence(evidence):
    payload = [
        [encode_rational(u), encode_rational(v), multiplicity]
        for u, v, multiplicity in evidence.pairs
    ]
    return json.dumps(payload, separators=(',', ':'))


def decode_rank_evidence(payload):
    """解出联合证据；V1 旧封存没有该列或列为 NULL 时返回 ``None``（缺证件）。"""
    if payload is None:
        return None
    raw_pairs = json.loads(payload)
    if not isinstance(raw_pairs, list):
        raise ValueError('invalid rank evidence payload')
    pairs = []
    for item in raw_pairs:
        if not isinstance(item, list) or len(item) != 3 or type(item[2]) is not int or item[2] < 1:
            raise ValueError('invalid rank evidence pair')
        u, v, multiplicity = item
        pairs.append((decode_rational(u), decode_rational(v), multiplicity))
    return RankEvidence(tuple(pairs))
