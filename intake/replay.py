import hashlib
import json

from intake.store import load_batch_rows


def submission_fingerprint(scale_id, predecessor_id, rows):
    payload = [scale_id, predecessor_id, [row.encoded() for row in rows]]
    canonical = json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode('ascii')
    return hashlib.sha256(canonical).hexdigest()


def check_replay(db, previous, scale_id, predecessor_id, fingerprint, rows):
    if (previous.scale_id, previous.predecessor_id, previous.fingerprint) != (
        scale_id, predecessor_id, fingerprint
    ):
        raise ValueError('conflicting submission replay')
    if not previous.expired and load_batch_rows(db, previous.batch_id) != rows:
        raise ValueError('conflicting submission replay')
    return previous.batch_id
