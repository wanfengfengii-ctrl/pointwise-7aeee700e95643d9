from dataclasses import dataclass

from freeze.catalog import find_seal_for_batch
from intake.store import load_batch_header


@dataclass(frozen=True)
class ExpiryEligibility:
    batch_id: int
    supporting_seal_id: int


def check_expiry_eligibility(db, batch_id, policy, cutoff):
    batch = load_batch_header(db, batch_id)
    if batch is None or batch.expired:
        raise ValueError('batch source rows are unavailable')
    if not policy.allows_expiry(batch.accepted_at, cutoff):
        raise ValueError('batch has not reached its retention deadline')
    seal = find_seal_for_batch(db, batch_id)
    if seal is None:
        raise ValueError('this batch revision has no committed seal')
    return ExpiryEligibility(batch.batch_id, seal.seal_id)
