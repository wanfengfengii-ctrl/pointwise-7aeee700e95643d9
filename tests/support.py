import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from db import initialize, open_database
from freeze.codec import encode_seal_moments
from freeze.moments import PairedMoments
from freeze.package import seal_batch
from intake.batches import submit_batch
from retention.policy import RetentionPolicy
from scales.projects import BenchAxes, ProjectAxes
from scales.rationals import encode_rational
from scales.revisions import set_scale


PROJECT = 'repeatability'
ACCEPTED = datetime(2026, 5, 11, 8, tzinfo=timezone.utc)
PERIOD = RetentionPolicy(timedelta(days=1))
DUE = ACCEPTED + timedelta(days=1)
OTHER_PROJECT = (
    ProjectAxes('crosscheck', 'reference_x', 'mm', 'reference_y', 'mm'),
    (BenchAxes('a', 'dial_x', 'tick', 'dial_y', 'tick'),),
)


def axis_specs(*, x_slope=1, x_offset=0, y_slope=1, y_offset=0):
    return (
        dict(input_axis='dial_x', input_unit='tick', output_axis='reference_x',
             output_unit='mm', slope=x_slope, offset=x_offset),
        dict(input_axis='dial_y', input_unit='tick', output_axis='reference_y',
             output_unit='mm', slope=y_slope, offset=y_offset),
    )


@contextmanager
def failing_commit(db, table):
    if table not in {'sealed_evidence', 'quality_reports', 'rank_quality_reports',
                     'expiry_receipts'}:
        raise ValueError('unknown fixture target')
    db.execute('CREATE TEMP TABLE fault_parent (id INTEGER PRIMARY KEY)')
    db.execute('''
        CREATE TEMP TABLE fault_child (
            parent_id INTEGER REFERENCES fault_parent(id) DEFERRABLE INITIALLY DEFERRED
        )
    ''')
    db.execute(f'''
        CREATE TEMP TRIGGER fault_at_commit AFTER INSERT ON main.{table}
        BEGIN
            INSERT INTO fault_child (parent_id) VALUES (1);
        END
    ''')
    try:
        yield
    finally:
        db.execute('DROP TRIGGER temp.fault_at_commit')
        db.execute('DROP TABLE temp.fault_child')
        db.execute('DROP TABLE temp.fault_parent')


class DatabaseCase(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='yuchuan-test-')
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'workshop.sqlite3'
        self.db = open_database(self.path)
        self.addCleanup(self.close_database)
        initialize(self.db)
        initialize(self.db, projects=(OTHER_PROJECT,))

    def close_database(self):
        self.db.close()

    def reopen(self):
        self.db.close()
        self.db = open_database(self.path)

    def scale(self, bench='a', *, project=PROJECT, **options):
        x, y = axis_specs(**options)
        return set_scale(self.db, project, bench, x=x, y=y)

    def submit(self, key, rows, *, bench='a', project=PROJECT, scale_id=None,
               accepted_at=ACCEPTED, predecessor_id=None):
        if scale_id is None:
            scale_id = self.scale(bench, project=project)
        return submit_batch(self.db, project, bench, key, scale_id, rows,
                            accepted_at=accepted_at, predecessor_id=predecessor_id)

    def shifted_pair_of_batches(self):
        left = self.submit('shift-left', [('a0', 0, 0), ('a1', 1, 1)])
        right_scale = self.scale('b', x_offset=2)
        right = self.submit('shift-right', [('b0', 0, 0)], bench='b', scale_id=right_scale)
        return seal_batch(self.db, left), seal_batch(self.db, right)


def build_legacy_v1_database(path):
    """用派生的 V1 表结构手工建库并写入零对封存和普通报告。

    该库不含联合证据列与秩报告表，用于核对新版 initialize 的续写能力、
    V1 旧件读取以及缺证件整次拒发。
    """
    db = open_database(path)
    try:
        db.execute('''
            CREATE TABLE project_axes (
                project TEXT PRIMARY KEY NOT NULL,
                x_axis TEXT NOT NULL, x_unit TEXT NOT NULL,
                y_axis TEXT NOT NULL, y_unit TEXT NOT NULL,
                CHECK (x_axis <> y_axis)
            )
        ''')
        db.execute('''
            CREATE TABLE bench_axes (
                project TEXT NOT NULL REFERENCES project_axes(project),
                bench TEXT NOT NULL,
                x_axis TEXT NOT NULL, x_unit TEXT NOT NULL,
                y_axis TEXT NOT NULL, y_unit TEXT NOT NULL,
                PRIMARY KEY (project, bench),
                CHECK (x_axis <> y_axis)
            )
        ''')
        db.execute('''
            CREATE TABLE scale_revisions (
                scale_id INTEGER PRIMARY KEY,
                project TEXT NOT NULL, bench TEXT NOT NULL,
                x_slope TEXT NOT NULL, x_offset TEXT NOT NULL,
                y_slope TEXT NOT NULL, y_offset TEXT NOT NULL,
                FOREIGN KEY (project, bench) REFERENCES bench_axes(project, bench)
            )
        ''')
        db.execute('''
            CREATE TABLE observation_batches (
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
            CREATE TABLE observation_rows (
                batch_id INTEGER NOT NULL REFERENCES observation_batches(batch_id),
                row_key TEXT NOT NULL, x TEXT, y TEXT,
                PRIMARY KEY (batch_id, row_key)
            )
        ''')
        db.execute('''
            CREATE TABLE sealed_evidence (
                seal_id INTEGER PRIMARY KEY,
                project TEXT NOT NULL REFERENCES project_axes(project),
                batch_id INTEGER NOT NULL UNIQUE REFERENCES observation_batches(batch_id),
                scale_id INTEGER NOT NULL REFERENCES scale_revisions(scale_id),
                payload TEXT NOT NULL
            )
        ''')
        db.execute('''
            CREATE TABLE quality_reports (
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
            CREATE TABLE report_seals (
                report_id INTEGER NOT NULL REFERENCES quality_reports(report_id),
                seal_id INTEGER NOT NULL REFERENCES sealed_evidence(seal_id),
                PRIMARY KEY (report_id, seal_id)
            )
        ''')
        db.execute('''
            CREATE TABLE expiry_receipts (
                batch_id INTEGER PRIMARY KEY REFERENCES observation_batches(batch_id),
                supporting_seal_id INTEGER NOT NULL REFERENCES sealed_evidence(seal_id),
                cutoff TEXT NOT NULL,
                removed_rows INTEGER NOT NULL CHECK (removed_rows >= 0)
            )
        ''')
        one = encode_rational(Fraction(1))
        zero = encode_rational(Fraction(0))
        db.execute(
            'INSERT INTO project_axes VALUES (?, ?, ?, ?, ?)',
            (PROJECT, 'reference_x', 'mm', 'reference_y', 'mm'),
        )
        db.execute(
            'INSERT INTO bench_axes VALUES (?, ?, ?, ?, ?, ?)',
            (PROJECT, 'a', 'dial_x', 'tick', 'dial_y', 'tick'),
        )
        db.execute(
            'INSERT INTO scale_revisions VALUES (?, ?, ?, ?, ?, ?, ?)',
            (1, PROJECT, 'a', one, zero, one, zero),
        )
        db.execute('''
            INSERT INTO observation_batches
                (batch_id, project, bench, submission_key, scale_id, predecessor_id,
                 accepted_at, fingerprint, expired)
            VALUES (?, ?, ?, ?, ?, NULL, ?, ?, 0)
        ''', (1, PROJECT, 'a', 'legacy-zero-pairs', 1, ACCEPTED.isoformat(),
              'legacy-fingerprint'))
        db.execute('INSERT INTO observation_rows (batch_id, row_key, x, y) VALUES (?, ?, ?, ?)',
                   (1, 'r0', zero, None))
        db.execute('INSERT INTO observation_rows (batch_id, row_key, x, y) VALUES (?, ?, ?, ?)',
                   (1, 'r1', None, zero))
        moments = PairedMoments(0)
        db.execute('''
            INSERT INTO sealed_evidence (project, batch_id, scale_id, payload)
            VALUES (?, ?, ?, ?)
        ''', (PROJECT, 1, 1, encode_seal_moments(moments)))
        db.execute('''
            INSERT INTO quality_reports (project, threshold, pair_count, q, passed)
            VALUES (?, ?, ?, NULL, 0)
        ''', (PROJECT, zero, 0))
        db.execute('INSERT INTO report_seals (report_id, seal_id) VALUES (?, ?)', (1, 1))
        db.commit()
    finally:
        db.close()
    return path
