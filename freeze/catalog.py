from dataclasses import dataclass

from db import require_id
from freeze.codec import decode_seal_moments, encode_seal_moments
from freeze.moments import PairedMoments


@dataclass(frozen=True)
class SealedEvidence:
    seal_id: int
    project: str
    batch_id: int
    scale_id: int
    moments: PairedMoments


def init_seal_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS sealed_evidence (
            seal_id INTEGER PRIMARY KEY,
            project TEXT NOT NULL REFERENCES project_axes(project),
            batch_id INTEGER NOT NULL UNIQUE REFERENCES observation_batches(batch_id),
            scale_id INTEGER NOT NULL REFERENCES scale_revisions(scale_id),
            payload TEXT NOT NULL
        )
    ''')


def insert_seal(db, batch, moments):
    cursor = db.execute('''
        INSERT INTO sealed_evidence (project, batch_id, scale_id, payload) VALUES (?, ?, ?, ?)
    ''', (batch.project, batch.batch_id, batch.scale_id, encode_seal_moments(moments)))
    return SealedEvidence(cursor.lastrowid, batch.project, batch.batch_id, batch.scale_id, moments)


def _evidence(row):
    if row is None:
        return None
    return SealedEvidence(
        row['seal_id'], row['project'], row['batch_id'], row['scale_id'],
        decode_seal_moments(row['payload']),
    )


def get_seal(db, seal_id):
    require_id(seal_id, 'seal ID')
    row = db.execute('SELECT * FROM sealed_evidence WHERE seal_id = ?', (seal_id,)).fetchone()
    return _evidence(row)


def find_seal_for_batch(db, batch_id):
    require_id(batch_id, 'batch ID')
    row = db.execute('SELECT * FROM sealed_evidence WHERE batch_id = ?', (batch_id,)).fetchone()
    return _evidence(row)
