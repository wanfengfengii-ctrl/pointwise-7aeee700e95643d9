import unittest
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from db import initialize, open_database
from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.batches import submit_batch
from intake.store import load_batch_header, load_batch_rows
from retention.purge import expire_batch
from retention.receipts import lookup_receipt
from review.reports import get_review, issue_review
from scales.projects import BenchAxes, ProjectAxes
from scales.revisions import require_scale_revision, set_scale
from scales.store import load_bench_axes, load_project_axes
from tests.support import ACCEPTED, DUE, PERIOD, PROJECT


class InitializationTests(unittest.TestCase):
    def test_init_again(self):
        project_axes = ProjectAxes(PROJECT, 'custom_x', 'um', 'custom_y', 'um')
        bench_axes = BenchAxes('a', 'encoder_x', 'count', 'encoder_y', 'count')
        x = dict(input_axis='encoder_x', input_unit='count', output_axis='custom_x',
                 output_unit='um', slope=1, offset=0)
        y = dict(input_axis='encoder_y', input_unit='count', output_axis='custom_y',
                 output_unit='um', slope=1, offset=0)
        with TemporaryDirectory(prefix='yuchuan-init-') as directory:
            path = Path(directory) / 'initialized.sqlite3'
            with closing(open_database(path)) as db:
                initialize(db, projects=((project_axes, (bench_axes,)),))
                scale = set_scale(db, PROJECT, 'a', x=x, y=y)
                original = submit_batch(db, PROJECT, 'a', 'first', scale,
                                        [('a', 0, 0), ('b', 1, 1)], accepted_at=ACCEPTED)
                evidence = seal_batch(db, original)
                report = issue_review(db, [evidence.seal_id], 1)
                receipt = expire_batch(db, original, PERIOD, DUE)
                initialize(db)
                new_scale = set_scale(db, PROJECT, 'a', x=dict(x, offset=3), y=y)
                replacement = submit_batch(db, PROJECT, 'a', 'second', new_scale,
                                           [('a', 2, 3)], accepted_at=DUE, predecessor_id=original)
                initialize(db)
            with closing(open_database(path)) as db:
                self.assertEqual(load_project_axes(db, PROJECT), project_axes)
                self.assertEqual(load_bench_axes(db, PROJECT, 'a'), bench_axes)
                self.assertIsNotNone(load_bench_axes(db, PROJECT, 'b'))
                self.assertEqual(require_scale_revision(db, scale).x.offset, 0)
                self.assertEqual(require_scale_revision(db, new_scale).x.offset, 3)
                self.assertEqual(load_batch_header(db, replacement).predecessor_id, original)
                self.assertEqual(load_batch_rows(db, replacement)[0].y, 3)
                self.assertIsNone(load_batch_rows(db, original))
                self.assertEqual(lookup_receipt(db, original), receipt)
                self.assertEqual(get_seal(db, evidence.seal_id), evidence)
                self.assertEqual(get_review(db, report.report_id), report)
                self.assertEqual((report.n, report.q, report.passed), (2, 1, True))
