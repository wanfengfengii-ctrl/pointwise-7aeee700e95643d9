from db import transaction, utc_time
from intake.store import remove_source_rows
from retention.eligibility import check_expiry_eligibility
from retention.policy import RetentionPolicy
from retention.receipts import insert_receipt, lookup_receipt


def expire_batch(db, batch_id, policy, cutoff):
    if not isinstance(policy, RetentionPolicy):
        raise ValueError('expected a retention policy')
    cutoff = utc_time(cutoff)
    with transaction(db):
        receipt = lookup_receipt(db, batch_id)
        if receipt is not None:
            return receipt
        eligibility = check_expiry_eligibility(db, batch_id, policy, cutoff)
        removed_rows = remove_source_rows(db, batch_id)
        return insert_receipt(db, eligibility, cutoff, removed_rows)
