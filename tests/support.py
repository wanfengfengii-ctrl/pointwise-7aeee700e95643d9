import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from db import initialize, open_database
from freeze.package import seal_batch
from intake.batches import submit_batch
from retention.policy import RetentionPolicy
from scales.projects import BenchAxes, ProjectAxes
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
    if table not in {'sealed_evidence', 'quality_reports', 'expiry_receipts'}:
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
