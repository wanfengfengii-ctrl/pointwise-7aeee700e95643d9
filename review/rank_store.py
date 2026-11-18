from dataclasses import dataclass
from fractions import Fraction

from db import require_id
from scales.rationals import decode_rational, encode_rational


@dataclass(frozen=True)
class RankQualityReport:
    report_id: int
    project: str
    seal_ids: tuple[int, ...]
    threshold: Fraction
    n: int
    q: Fraction | None
    passed: bool


def init_rank_review_schema(db):
    db.execute('''
        CREATE TABLE IF NOT EXISTS rank_quality_reports (
            report_id INTEGER PRIMARY KEY,
            project TEXT NOT NULL REFERENCES project_axes(project),
            threshold TEXT NOT NULL,
            pair_count INTEGER NOT NULL CHECK (pair_count >= 0),
            q TEXT,
            passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
            CHECK (q IS NOT NULL OR passed = 0)
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS rank_report_seals (
            report_id INTEGER NOT NULL REFERENCES rank_quality_reports(report_id),
            seal_id INTEGER NOT NULL REFERENCES sealed_evidence(seal_id),
            PRIMARY KEY (report_id, seal_id)
        )
    ''')


def insert_rank_review(db, project, request, association, passed):
    q = None if association.q is None else encode_rational(association.q)
    cursor = db.execute('''
        INSERT INTO rank_quality_reports (project, threshold, pair_count, q, passed)
        VALUES (?, ?, ?, ?, ?)
    ''', (project, encode_rational(request.threshold), association.n, q, int(passed)))
    report_id = cursor.lastrowid
    db.executemany(
        'INSERT INTO rank_report_seals (report_id, seal_id) VALUES (?, ?)',
        ((report_id, seal_id) for seal_id in request.seal_ids),
    )
    return RankQualityReport(report_id, project, request.seal_ids, request.threshold,
                             association.n, association.q, passed)


def load_rank_review(db, report_id):
    require_id(report_id, 'rank report ID')
    row = db.execute(
        'SELECT * FROM rank_quality_reports WHERE report_id = ?', (report_id,),
    ).fetchone()
    if row is None:
        return None
    sources = db.execute('''
        SELECT seal_id FROM rank_report_seals WHERE report_id = ? ORDER BY seal_id
    ''', (report_id,))
    q = None if row['q'] is None else decode_rational(row['q'])
    return RankQualityReport(
        report_id, row['project'], tuple(source['seal_id'] for source in sources),
        decode_rational(row['threshold']), row['pair_count'], q, bool(row['passed']),
    )
