from dataclasses import dataclass
from datetime import datetime

from db import require_id
from intake.rows import ObservationRow
from scales.rationals import decode_rational


@dataclass(frozen=True)
class BatchHeader:
    batch_id: int
    project: str
    bench: str
    submission_key: str
    scale_id: int
    predecessor_id: int | None
    accepted_at: datetime
    fingerprint: str
    expired: bool


def init_intake_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS observation_batches (
            batch_id INTEGER PRIMARY KEY,
            project TEXT NOT NULL, bench TEXT NOT NULL,
            submission_key TEXT NOT NULL,
            scale_id INTEGER NOT NULL REFERENCES scale_revisions(scale_id),
            predecessor_id INTEGER REFERENCES observation_batches(batch_id),
            accepted_at TEXT NOT NULL, fingerprint TEXT NOT NULL,
            expired INTEGER NOT NULL DEFAULT 0 CHECK (expired IN (0, 1)),
            UNIQUE (project, bench, submission_key),
            FOREIGN KEY (project, bench) REFERENCES bench_axes(project, bench)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS observation_rows (
            batch_id INTEGER NOT NULL REFERENCES observation_batches(batch_id),
            row_key TEXT NOT NULL, x TEXT, y TEXT,
            PRIMARY KEY (batch_id, row_key)
        )
    ''')


def _batch_header(row):
    if row is None:
        return None
    return BatchHeader(
        row['batch_id'], row['project'], row['bench'], row['submission_key'],
        row['scale_id'], row['predecessor_id'], datetime.fromisoformat(row['accepted_at']),
        row['fingerprint'], bool(row['expired']),
    )


def find_submission(db, project, bench, submission_key):
    row = db.execute('''
        SELECT * FROM observation_batches WHERE project = ? AND bench = ? AND submission_key = ?
    ''', (project, bench, submission_key)).fetchone()
    return _batch_header(row)


def load_batch_header(db, batch_id):
    require_id(batch_id, 'batch ID')
    row = db.execute('SELECT * FROM observation_batches WHERE batch_id = ?', (batch_id,)).fetchone()
    return _batch_header(row)


def load_batch_rows(db, batch_id):
    require_id(batch_id, 'batch ID')
    rows = db.execute('''
        SELECT r.row_key, r.x, r.y FROM observation_batches AS b
        LEFT JOIN observation_rows AS r ON r.batch_id = b.batch_id
        WHERE b.batch_id = ? AND b.expired = 0 ORDER BY r.row_key
    ''', (batch_id,)).fetchall()
    if not rows:
        return None
    if rows[0]['row_key'] is None:
        return ()
    return tuple(
        ObservationRow(key, None if x is None else decode_rational(x),
                       None if y is None else decode_rational(y))
        for key, x, y in rows
    )


def insert_batch(db, project, bench, submission_key, scale_id, predecessor_id,
                 accepted_at, fingerprint, rows):
    cursor = db.execute('''
        INSERT INTO observation_batches
            (project, bench, submission_key, scale_id, predecessor_id, accepted_at, fingerprint)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (project, bench, submission_key, scale_id, predecessor_id, accepted_at.isoformat(), fingerprint))
    batch_id = cursor.lastrowid
    db.executemany('''
        INSERT INTO observation_rows (batch_id, row_key, x, y) VALUES (?, ?, ?, ?)
    ''', ((batch_id, *row.encoded()) for row in rows))
    return batch_id


def remove_source_rows(db, batch_id):
    changed = db.execute('''
        UPDATE observation_batches SET expired = 1 WHERE batch_id = ? AND expired = 0
    ''', (batch_id,)).rowcount
    if changed != 1:
        raise ValueError('batch source rows are unavailable')
    return db.execute('DELETE FROM observation_rows WHERE batch_id = ?', (batch_id,)).rowcount
