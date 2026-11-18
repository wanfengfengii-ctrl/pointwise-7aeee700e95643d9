from dataclasses import dataclass
from fractions import Fraction

from scales.axes import AxisTransform


@dataclass(frozen=True)
class PairedMoments:
    n: int = 0
    sx: Fraction = Fraction(0)
    sy: Fraction = Fraction(0)
    sxx: Fraction = Fraction(0)
    syy: Fraction = Fraction(0)
    sxy: Fraction = Fraction(0)


def moments_in_project_axes(pairs, x_axis: AxisTransform, y_axis: AxisTransform):
    n = 0
    sx = sy = sxx = syy = sxy = Fraction(0)
    for x, y in pairs:
        u = x_axis.apply(x)
        v = y_axis.apply(y)
        n += 1
        sx += u
        sy += v
        sxx += u * u
        syy += v * v
        sxy += u * v
    return PairedMoments(n, sx, sy, sxx, syy, sxy)
