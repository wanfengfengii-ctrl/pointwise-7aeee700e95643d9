from db import transaction
from review.decision import decide_gate
from review.pool import pool_association
from review.ranking import rank_association
from review.rank_store import insert_rank_review, load_rank_review
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


def _resolve_rank_seals(db, request):
    seals = resolve_review_seals(db, request)
    for seal in seals:
        if seal.rank_evidence is None:
            raise ValueError(f'seal {seal.seal_id} has no joint rank evidence')
    return seals


def issue_rank_review(db, seal_ids, threshold):
    # 选件与门槛非法时在开启写事务前拒发，库里不会留下任何痕迹。
    request = make_review_request(seal_ids, threshold)
    with transaction(db):
        seals = _resolve_rank_seals(db, request)
        association = rank_association(seals)
        passed = decide_gate(association, request.threshold)
        return insert_rank_review(db, seals[0].project, request, association, passed)


def get_rank_review(db, report_id):
    return load_rank_review(db, report_id)
