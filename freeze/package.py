from db import transaction
from freeze.catalog import find_seal_for_batch, insert_seal
from freeze.cohort import iter_valid_pairs, prepare_cohort
from freeze.moments import moments_in_project_axes


def seal_batch(db, batch_id):
    with transaction(db):
        cohort = prepare_cohort(db, batch_id)
        existing = find_seal_for_batch(db, batch_id)
        if existing is not None:
            return existing
        moments = moments_in_project_axes(iter_valid_pairs(cohort), cohort.scale.x, cohort.scale.y)
        return insert_seal(db, cohort.batch, moments)
