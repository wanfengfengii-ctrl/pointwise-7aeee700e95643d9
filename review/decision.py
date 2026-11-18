from fractions import Fraction

from review.pool import PooledAssociation


def decide_gate(association: PooledAssociation, threshold: Fraction) -> bool:
    return association.q is not None and association.q >= threshold
