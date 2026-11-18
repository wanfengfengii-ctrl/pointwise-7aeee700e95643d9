from db import transaction
from review.decision import decide_gate
from review.pool import pool_association
from review.request import make_review_request, resolve_review_seals
from review.store import insert_review, load_review


def issue_review(db, seal_ids, threshold):
    request = make_review_request(seal_ids, threshold)
    with transaction(db):
        seals = resolve_review_seals(db, request)
        association = pool_association(seals)
        passed = decide_gate(association, request.threshold)
        return insert_review(db, seals[0].project, request, association, passed)


def get_review(db, report_id):
    return load_review(db, report_id)
