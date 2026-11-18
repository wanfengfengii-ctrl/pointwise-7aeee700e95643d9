from dataclasses import dataclass
from fractions import Fraction

from freeze.catalog import SealedEvidence


@dataclass(frozen=True)
class PooledAssociation:
    n: int
    q: Fraction | None


def pool_association(seals: tuple[SealedEvidence, ...]):
    n = 0
    sx = sy = sxx = syy = sxy = Fraction(0)
    for seal in seals:
        batch = seal.moments
        n += batch.n
        sx += batch.sx
        sy += batch.sy
        sxx += batch.sxx
        syy += batch.syy
        sxy += batch.sxy
    if n < 2:
        return PooledAssociation(n, None)
    x_variation = n * sxx - sx * sx
    y_variation = n * syy - sy * sy
    if x_variation == 0 or y_variation == 0:
        return PooledAssociation(n, None)
    cross_variation = n * sxy - sx * sy
    q = cross_variation * abs(cross_variation) / (x_variation * y_variation)
    return PooledAssociation(n, q)
