from datetime import timedelta
from fractions import Fraction

from intake.rows import ObservationRow
from intake.store import find_submission, load_batch_header, load_batch_rows
from scales.revisions import require_scale_revision, set_scale
from tests.support import ACCEPTED, PROJECT, DatabaseCase, axis_specs


class IntakeTests(DatabaseCase):
    def test_exact_replay(self):
        scale = self.scale()
        original = self.submit('morning', [('r2', '2/4', 0), ('r1', 0, None)], scale_id=scale)
        replay = self.submit(
            'morning', [('r1', '0', None), ('r2', Fraction(1, 2), '0')],
            scale_id=scale, accepted_at=ACCEPTED + timedelta(hours=3),
        )
        self.assertEqual(replay, original)
        self.assertEqual(load_batch_header(self.db, original).accepted_at, ACCEPTED)
        self.assertEqual(load_batch_rows(self.db, original), (
            ObservationRow('r1', Fraction(0), None), ObservationRow('r2', Fraction(1, 2), Fraction(0)),
        ))

    def test_scale_binding(self):
        left_scale = self.scale('a')
        right_scale = self.scale('b', x_offset=2)
        for bench, scale in (('a', left_scale), ('b', right_scale)):
            with self.subTest(bench=bench):
                rows = [('row', 0, 0)]
                batch = self.submit('shift', rows, bench=bench, scale_id=scale)
                self.assertEqual(self.submit('shift', rows, bench=bench, scale_id=scale), batch)
                head = load_batch_header(self.db, batch)
                self.assertEqual((head.project, head.bench, head.scale_id), (PROJECT, bench, scale))
        with self.assertRaisesRegex(ValueError, 'another bench'):
            self.submit('wrong-bench', [('r', 0, 0)], bench='b', scale_id=left_scale)
        self.assertIsNone(find_submission(self.db, PROJECT, 'b', 'wrong-bench'))

    def test_scale_validation(self):
        scale = self.scale(x_slope='-3/2', x_offset='1/3')
        self.assertEqual(require_scale_revision(self.db, scale).x.apply(Fraction(2)), Fraction(-8, 3))
        before = self.db.execute('SELECT COUNT(*) FROM scale_revisions').fetchone()[0]
        x, y = axis_specs()
        invalid_x = (dict(x, output_axis='reference_y'), dict(x, input_unit='mm'),
                     dict(x, slope=0), dict(x, offset=0.1), dict(x, slope=True))
        for bad in invalid_x:
            with self.subTest(x=bad), self.assertRaises(ValueError):
                set_scale(self.db, PROJECT, 'a', x=bad, y=y)
        with self.assertRaises(ValueError):
            set_scale(self.db, 'unknown', 'a', x=x, y=y)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM scale_revisions').fetchone()[0], before)

    def test_conflicting_replay(self):
        scale = self.scale()
        batch = self.submit('fixed', [('one', 0, 1)], scale_id=scale)
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.submit('fixed', [('one', 0, 2)], scale_id=scale)
        self.assertEqual(load_batch_rows(self.db, batch), (ObservationRow('one', 0, 1),))
        self.assertEqual(find_submission(self.db, PROJECT, 'a', 'fixed').batch_id, batch)

    def test_null_vs_zero(self):
        scale = self.scale()
        rows = [('one', 1, None)]
        batch = self.submit('fixed', rows, scale_id=scale)
        self.assertEqual(self.submit('fixed', rows, scale_id=scale), batch)
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.submit('fixed', [('one', 1, 0)], scale_id=scale)
        self.assertEqual(load_batch_rows(self.db, batch), (ObservationRow('one', 1, None),))

    def test_foreign_scale(self):
        valid = self.scale()
        original = self.submit('original', [('r', 3, 4)], scale_id=valid)
        foreign = self.scale(project='crosscheck', x_offset=10)
        with self.assertRaisesRegex(ValueError, 'another project'):
            self.submit('foreign', [('r', 3, 4)], scale_id=foreign)
        self.assertIsNone(find_submission(self.db, PROJECT, 'a', 'foreign'))
        self.assertEqual(load_batch_rows(self.db, original), (ObservationRow('r', 3, 4),))
        good = self.submit('foreign', [('r', 3, 4)], scale_id=valid)
        self.assertEqual(load_batch_header(self.db, good).scale_id, valid)

    def test_bad_predecessor(self):
        first = self.submit('previous', [('r', 1, 2)], bench='b')
        scale = self.scale()
        with self.assertRaisesRegex(ValueError, 'same project and bench'):
            self.submit('corrected', [('r', 2, 3)], scale_id=scale, predecessor_id=first)
        with self.assertRaisesRegex(ValueError, 'unknown predecessor'):
            self.submit('corrected', [('r', 2, 3)], scale_id=scale, predecessor_id=9999)
        self.assertIsNone(find_submission(self.db, PROJECT, 'a', 'corrected'))
        self.assertEqual(load_batch_rows(self.db, first), (ObservationRow('r', 1, 2),))

    def test_invalid_rows_leave_no_partial_batch(self):
        scale = self.scale()
        invalid = ([('r', 1, 2), ('r', 2, 3)], [('r', 1, '1/0')], [('r', False, 2)],
                   [('r', 0.5, 1)], [('r', 1)], [('', 1, 2)])
        for rows in invalid:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                self.submit('invalid', rows, scale_id=scale)
        self.assertIsNone(find_submission(self.db, PROJECT, 'a', 'invalid'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observation_rows').fetchone()[0], 0)
