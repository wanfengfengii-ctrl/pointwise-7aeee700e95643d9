from dataclasses import dataclass

from intake.rows import ObservationRow
from intake.store import BatchHeader, load_batch_header, load_batch_rows
from scales.revisions import require_scale_revision
from scales.store import ScaleRevision


@dataclass(frozen=True)
class SealCohort:
    batch: BatchHeader
    scale: ScaleRevision
    rows: tuple[ObservationRow, ...]


def prepare_cohort(db, batch_id):
    batch = load_batch_header(db, batch_id)
    if batch is None:
        raise ValueError('unknown batch')
    rows = load_batch_rows(db, batch_id)
    if rows is None:
        raise ValueError('batch source rows are unavailable')
    scale = require_scale_revision(db, batch.scale_id, project=batch.project, bench=batch.bench)
    return SealCohort(batch, scale, rows)


def iter_valid_pairs(cohort):
    for row in cohort.rows:
        if row.x is not None and row.y is not None:
            yield row.x, row.y
