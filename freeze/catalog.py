from dataclasses import dataclass

from db import require_id
from freeze.codec import decode_seal_moments, encode_seal_moments
from freeze.evidence import RankEvidence, decode_rank_evidence, encode_rank_evidence
from freeze.moments import PairedMoments


@dataclass(frozen=True)
class SealedEvidence:
    seal_id: int
    project: str
    batch_id: int
    scale_id: int
    moments: PairedMoments
    rank_evidence: RankEvidence | None = None


def init_seal_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS sealed_evidence (
            seal_id INTEGER PRIMARY KEY,
            project TEXT NOT NULL REFERENCES project_axes(project),
            batch_id INTEGER NOT NULL UNIQUE REFERENCES observation_batches(batch_id),
            scale_id INTEGER NOT NULL REFERENCES scale_revisions(scale_id),
            payload TEXT NOT NULL,
            rank_payload TEXT
        )
    ''')
    columns = {row['name'] for row in db.execute('PRAGMA table_info(sealed_evidence)')}
    if 'rank_payload' not in columns:
        # V1 工作库升级：旧封存没有联合证据列，补列后旧行按缺证件处理。
        db.execute('ALTER TABLE sealed_evidence ADD COLUMN rank_payload TEXT')


def insert_seal(db, batch, moments, rank_evidence):
    cursor = db.execute('''
        INSERT INTO sealed_evidence (project, batch_id, scale_id, payload, rank_payload)
        VALUES (?, ?, ?, ?, ?)
    ''', (batch.project, batch.batch_id, batch.scale_id,
          encode_seal_moments(moments), encode_rank_evidence(rank_evidence)))
    return SealedEvidence(cursor.lastrowid, batch.project, batch.batch_id, batch.scale_id,
                          moments, rank_evidence)


def _evidence(row):
    if row is None:
        return None
    return SealedEvidence(
        row['seal_id'], row['project'], row['batch_id'], row['scale_id'],
        decode_seal_moments(row['payload']), decode_rank_evidence(row['rank_payload']),
    )


def get_seal(db, seal_id):
    require_id(seal_id, 'seal ID')
    row = db.execute('SELECT * FROM sealed_evidence WHERE seal_id = ?', (seal_id,)).fetchone()
    return _evidence(row)


def find_seal_for_batch(db, batch_id):
    require_id(batch_id, 'batch ID')
    row = db.execute('SELECT * FROM sealed_evidence WHERE batch_id = ?', (batch_id,)).fetchone()
    return _evidence(row)
