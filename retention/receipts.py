from dataclasses import dataclass
from datetime import datetime

from db import require_id


@dataclass(frozen=True)
class ExpiryReceipt:
    batch_id: int
    supporting_seal_id: int
    cutoff: datetime
    removed_rows: int


def init_receipt_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS expiry_receipts (
            batch_id INTEGER PRIMARY KEY REFERENCES observation_batches(batch_id),
            supporting_seal_id INTEGER NOT NULL REFERENCES sealed_evidence(seal_id),
            cutoff TEXT NOT NULL,
            removed_rows INTEGER NOT NULL CHECK (removed_rows >= 0)
        )
    ''')


def lookup_receipt(db, batch_id):
    require_id(batch_id, 'batch ID')
    row = db.execute('SELECT * FROM expiry_receipts WHERE batch_id = ?', (batch_id,)).fetchone()
    if row is None:
        return None
    return ExpiryReceipt(row['batch_id'], row['supporting_seal_id'],
                         datetime.fromisoformat(row['cutoff']), row['removed_rows'])


def insert_receipt(db, eligibility, cutoff, removed_rows):
    db.execute('''
        INSERT INTO expiry_receipts (batch_id, supporting_seal_id, cutoff, removed_rows)
        VALUES (?, ?, ?, ?)
    ''', (eligibility.batch_id, eligibility.supporting_seal_id, cutoff.isoformat(), removed_rows))
    return ExpiryReceipt(eligibility.batch_id, eligibility.supporting_seal_id, cutoff, removed_rows)
