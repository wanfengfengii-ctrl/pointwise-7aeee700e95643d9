import json
import sqlite3
from fractions import Fraction

from freeze.package import seal_batch
from intake.store import load_batch_rows
from retention.purge import expire_batch
from review.reports import get_review, issue_review
from tests.support import DUE, PERIOD, PROJECT, DatabaseCase, failing_commit


class ReviewTests(DatabaseCase):
    def _seal(self, key, rows, **kwargs):
        return seal_batch(self.db, self.submit(key, rows, **kwargs)).seal_id

    def test_pooled_shift(self):
        left, right = self.shifted_pair_of_batches()
        for seal in (left, right):
            expire_batch(self.db, seal.batch_id, PERIOD, DUE)
            self.assertIsNone(load_batch_rows(self.db, seal.batch_id))
        selected = (left.seal_id, right.seal_id)
        report = issue_review(self.db, selected, '1/2')
        self.assertEqual((report.n, report.q, report.passed), (3, Fraction(0), False),
                         'POOL_SCALE_MISMATCH')
        stored = get_review(self.db, report.report_id)
        self.assertEqual(stored, report)
        self.assertEqual((stored.project, stored.seal_ids, stored.threshold),
                         (PROJECT, selected, Fraction(1, 2)))
        expected = {'n': 3, 'q': '0', 'passed': False}
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'V5',
            'input': {'a': [[0, 0], [1, 1]], 'b': [[0, 0]], 'b_x_offset': 2,
                      'threshold': '1/2', 'sources_expired': True},
            'expected': expected,
            'actual': {'n': report.n, 'q': str(report.q), 'passed': report.passed},
            'downstream_expected': expected,
            'downstream_actual': {'n': stored.n, 'q': str(stored.q), 'passed': stored.passed},
            'code_paths': ['freeze/moments.py', 'review/pool.py', 'review/store.py'],
            'oracle': 'Cross-product about the means is (-1)*(-1/3)+0*(2/3)+1*(-1/3)=0.',
        }, sort_keys=True))

    def test_selected_only(self):
        left, right = self.shifted_pair_of_batches()
        extra = self._seal('extra', [('c', 3, 3)], bench='c')
        selected = (left.seal_id, right.seal_id)
        for ids in (selected, selected[::-1]):
            report = issue_review(self.db, ids, '1/2')
            self.assertEqual((report.seal_ids, report.n, report.q, report.passed), (selected, 3, 0, False))
        all_three = issue_review(self.db, (*selected, extra), '1/2')
        self.assertEqual((all_three.n, all_three.q, all_three.passed), (4, Fraction(8, 15), True))

    def test_constant_batches(self):
        first = self._seal('constant-a', [('a', 0, 2), ('b', 0, 2)])
        second = self._seal('constant-b', [('c', 2, 0), ('d', 2, 0)], bench='b')
        result = issue_review(self.db, [first, second], -1)
        self.assertEqual((result.n, result.q, result.passed), (4, Fraction(-1), True))

    def test_undefined(self):
        zero = self._seal('zero', [])
        one = self._seal('one', [('a', 2, 0), ('b', None, 2)])
        constant_x = self._seal('constant-x', [('a', 2, 1), ('b', 2, 3)])
        constant_y = self._seal('constant-y', [('a', 0, 2), ('b', 1, 2)])
        for selected, count in (([zero], 0), ([zero, one], 1),
                                ([one, constant_x], 3), ([constant_y], 2)):
            with self.subTest(selected=selected):
                report = issue_review(self.db, selected, -1)
                self.assertEqual((report.n, report.q, report.passed), (count, None, False))
                self.assertEqual(get_review(self.db, report.report_id), report)
        diagonal = self._seal('diagonal', [('a', 0, 0), ('b', 1, 1)])
        with_zero = issue_review(self.db, [zero, diagonal], 1)
        self.assertEqual((with_zero.n, with_zero.q, with_zero.passed), (2, Fraction(1), True))

    def test_signed_slope(self):
        rows = [('a', 0, 0), ('b', 0, 0), ('c', 1, 1), ('d', 9, None), ('e', None, 8)]
        positive = self._seal('positive', rows)
        negative = self._seal('negative', rows, scale_id=self.scale(y_slope=-1))
        pos = issue_review(self.db, [positive], 1)
        neg = issue_review(self.db, [negative], -1)
        self.assertEqual((pos.n, pos.q, pos.passed), (3, Fraction(1), True))
        self.assertEqual((neg.n, neg.q, neg.passed), (3, Fraction(-1), True))
        self.assertFalse(issue_review(self.db, [negative], 0).passed)

    def test_exact_gate(self):
        n = 2 ** 26
        seal = self._seal('near', [('a', 0, 0), ('b', n, n), ('c', 2 * n, 2 * n + 1)])
        expected = Fraction(54043196333752323, 54043196333752324)
        self.assertEqual(expected, Fraction((6 * n * n + 3 * n) ** 2,
                                            6 * n * n * (6 * n * n + 6 * n + 2)))
        strict = issue_review(self.db, [seal], 1)
        equal = issue_review(self.db, [seal], expected)
        self.assertEqual((strict.n, strict.q, strict.passed), (3, expected, False))
        self.assertEqual((equal.threshold, equal.q, equal.passed), (expected, expected, True))
        self.reopen()
        self.assertEqual(get_review(self.db, strict.report_id), strict)
        self.assertEqual(get_review(self.db, equal.report_id), equal)

    def test_request_rejection(self):
        seal = self._seal('main', [('a', 0, 0), ('b', 1, 1)])
        foreign = self._seal('foreign', [('a', 0, 0)], project='crosscheck')
        original = issue_review(self.db, [seal], 1)
        invalid = (([], 0), ([seal, seal], 0), ([seal, 9999], 0), ([seal, foreign], 0),
                   ([seal], '1001/1000'), ([seal], '-2'), ([seal], 0.5), ([True], 0), ('1', 0))
        for ids, threshold in invalid:
            with self.subTest(ids=ids, threshold=threshold), self.assertRaises(ValueError):
                issue_review(self.db, ids, threshold)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM quality_reports').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM report_seals').fetchone()[0], 1)
        self.assertEqual(get_review(self.db, original.report_id), original)
        self.assertIsNone(get_review(self.db, 9999))

    def test_failed_report(self):
        a, b = self.shifted_pair_of_batches()
        old = issue_review(self.db, [a.seal_id, b.seal_id], '1/2')
        with failing_commit(self.db, 'quality_reports'):
            with self.assertRaises(sqlite3.IntegrityError):
                issue_review(self.db, [a.seal_id], 1)
        self.reopen()
        self.assertEqual(get_review(self.db, old.report_id), old)
        self.assertIsNone(get_review(self.db, old.report_id + 1))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM report_seals').fetchone()[0], 2)
        successful = issue_review(self.db, [a.seal_id], 1)
        self.assertEqual((successful.n, successful.q, successful.passed), (2, 1, True))
