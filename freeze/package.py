from db import transaction
from freeze.catalog import find_seal_for_batch, insert_seal
from freeze.cohort import iter_valid_pairs, prepare_cohort
from freeze.evidence import build_rank_evidence
from freeze.moments import moments_in_project_axes


def seal_batch(db, batch_id):
    with transaction(db):
        cohort = prepare_cohort(db, batch_id)
        existing = find_seal_for_batch(db, batch_id)
        if existing is not None:
            # 原始行仍可用时重复封存，沿用 V1 的原件领取语义（缺证件保持缺证）。
            return existing
        valid_pairs = tuple(iter_valid_pairs(cohort))
        moments = moments_in_project_axes(iter(valid_pairs), cohort.scale.x, cohort.scale.y)
        rank_evidence = build_rank_evidence(valid_pairs, cohort.scale.x, cohort.scale.y)
        return insert_seal(db, cohort.batch, moments, rank_evidence)
