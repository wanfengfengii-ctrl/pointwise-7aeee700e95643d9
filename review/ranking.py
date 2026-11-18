"""秩一致性计算：跨封存件展开配对、平均秩与有符号平方秩相关。"""

from dataclasses import dataclass
from fractions import Fraction

from freeze.catalog import SealedEvidence


@dataclass(frozen=True)
class RankAssociation:
    n: int
    q: Fraction | None


def _expand_occurrences(seals: tuple[SealedEvidence, ...]) -> list[tuple[Fraction, Fraction]]:
    """把所选封存件的联合证据全量展开为带重数的统一坐标观测。

    同值异行各自保留：不同封存件、不同原始行即使坐标相同也逐次计入；
    同一封存件内归并的重数按次数展开。
    """
    occurrences: list[tuple[Fraction, Fraction]] = []
    for seal in seals:
        for u, v, multiplicity in seal.rank_evidence.pairs:
            for _ in range(multiplicity):
                occurrences.append((u, v))
    return occurrences


def average_ranks(values: list[Fraction]) -> list[Fraction]:
    """按精确值升序赋秩，位置从 1 开始；等值组取连续位置的平均秩。"""
    order = sorted(range(len(values)), key=lambda index: values[index])
    ranks: list[Fraction] = [Fraction(0)] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        value = values[order[start]]
        while end < len(order) and values[order[end]] == value:
            end += 1
        mean_rank = Fraction(start + 1 + end, 2)
        for position in range(start, end):
            ranks[order[position]] = mean_rank
        start = end
    return ranks


def rank_association(seals: tuple[SealedEvidence, ...]) -> RankAssociation:
    occurrences = _expand_occurrences(seals)
    n = len(occurrences)
    if n < 2:
        return RankAssociation(n, None)
    x_ranks = average_ranks([u for u, _ in occurrences])
    y_ranks = average_ranks([v for _, v in occurrences])
    sx = sy = Fraction(0)
    sxx = syy = sxy = Fraction(0)
    for rx, ry in zip(x_ranks, y_ranks):
        sx += rx
        sy += ry
        sxx += rx * rx
        syy += ry * ry
        sxy += rx * ry
    x_variation = n * sxx - sx * sx
    y_variation = n * syy - sy * sy
    # 任一轴的秩没有离散（全部并列）时相关无定义。
    if x_variation == 0 or y_variation == 0:
        return RankAssociation(n, None)
    cross_variation = n * sxy - sx * sy
    q = cross_variation * abs(cross_variation) / (x_variation * y_variation)
    return RankAssociation(n, q)
