from db import transaction, utc_time
from intake.corrections import validate_predecessor
from intake.replay import check_replay, submission_fingerprint
from intake.rows import normalize_rows
from intake.store import find_submission, insert_batch
from scales.projects import require_label
from scales.revisions import require_scale_revision


def submit_batch(db, project, bench, submission_key, scale_id, rows, *,
                 accepted_at, predecessor_id=None):
    require_label(project, 'project')
    require_label(bench, 'bench')
    require_label(submission_key, 'submission key')
    accepted_at = utc_time(accepted_at)
    rows = normalize_rows(rows)
    with transaction(db):
        require_scale_revision(db, scale_id, project=project, bench=bench)
        validate_predecessor(db, predecessor_id, project, bench)
        fingerprint = submission_fingerprint(scale_id, predecessor_id, rows)
        existing = find_submission(db, project, bench, submission_key)
        if existing is not None:
            return check_replay(db, existing, scale_id, predecessor_id, fingerprint, rows)
        return insert_batch(
            db, project, bench, submission_key, scale_id, predecessor_id,
            accepted_at, fingerprint, rows,
        )
