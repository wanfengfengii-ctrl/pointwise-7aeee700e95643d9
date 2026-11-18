from intake.store import load_batch_header


def validate_predecessor(db, predecessor_id, project, bench):
    if predecessor_id is None:
        return
    previous = load_batch_header(db, predecessor_id)
    if previous is None:
        raise ValueError('unknown predecessor batch')
    if (previous.project, previous.bench) != (project, bench):
        raise ValueError('predecessor must belong to the same project and bench')
