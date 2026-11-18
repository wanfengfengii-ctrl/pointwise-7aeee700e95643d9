import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone


SQLITE_MAX_ID = (1 << 63) - 1


def open_database(path):
    db = sqlite3.connect(path, isolation_level=None)
    try:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
    except BaseException:
        db.close()
        raise
    return db


@contextmanager
def transaction(db):
    db.execute('BEGIN IMMEDIATE')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def require_id(value, name):
    if type(value) is not int or not 1 <= value <= SQLITE_MAX_ID:
        raise ValueError(f'{name} must be a positive SQLite integer')
    return value


def utc_time(value):
    if not isinstance(value, datetime) or value.utcoffset() is None:
        raise ValueError('a timezone-aware datetime is required')
    return value.astimezone(timezone.utc)


def initialize(db, projects=None):
    from freeze.catalog import init_seal_schema
    from intake.store import init_intake_schema
    from retention.receipts import init_receipt_schema
    from review.rank_store import init_rank_review_schema
    from review.store import init_review_schema
    from scales.projects import INITIAL_AXES
    from scales.store import init_scale_schema, register_initial_axes

    with transaction(db):
        init_scale_schema(db)
        init_intake_schema(db)
        init_seal_schema(db)
        init_review_schema(db)
        init_rank_review_schema(db)
        init_receipt_schema(db)
        definitions = INITIAL_AXES if projects is None else projects
        for project, benches in definitions:
            register_initial_axes(db, project, benches)
