from dataclasses import dataclass
from fractions import Fraction

from db import require_id
from freeze.catalog import get_seal
from scales.rationals import parse_rational


@dataclass(frozen=True)
class ReviewRequest:
    seal_ids: tuple[int, ...]
    threshold: Fraction


def make_review_request(seal_ids, threshold):
    if isinstance(seal_ids, (str, bytes, dict)):
        raise ValueError('expected a collection of seal IDs')
    try:
        ids = tuple(seal_ids)
    except TypeError as exc:
        raise ValueError('expected a collection of seal IDs') from exc
    for seal_id in ids:
        require_id(seal_id, 'seal ID')
    if not ids or len(set(ids)) != len(ids):
        raise ValueError('a nonempty selection of distinct seals is required')
    threshold = parse_rational(threshold)
    if not -1 <= threshold <= 1:
        raise ValueError('threshold must be in [-1, 1]')
    return ReviewRequest(tuple(sorted(ids)), threshold)


def resolve_review_seals(db, request):
    seals = []
    for seal_id in request.seal_ids:
        seal = get_seal(db, seal_id)
        if seal is None:
            raise ValueError(f'unknown seal: {seal_id}')
        if seals and seal.project != seals[0].project:
            raise ValueError('all seals must belong to the same project')
        seals.append(seal)
    return tuple(seals)
