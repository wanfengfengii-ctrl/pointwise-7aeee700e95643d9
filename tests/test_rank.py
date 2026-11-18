import sqlite3
from fractions import Fraction
from pathlib import Path
from tempfile import TemporaryDirectory

from db import initialize, open_database
from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.store import load_batch_rows
from rank_examples import (
    CROSS_LEFT,
    CROSS_RIGHT,
    MOMENT_A,
    MOMENT_B,
    REPEATED,
    ZERO_PAIRS,
    submit_fixture,
)
from retention.purge import expire_batch
from review.reports import get_rank_review, issue_rank_review, issue_review
from review.reports import get_review
from tests.support import (
    ACCEPTED,
    DUE,
    PERIOD,
    PROJECT,
    DatabaseCase,
    build_legacy_v1_database,
    failing_commit,
)


class RankReviewTests(DatabaseCase):
    def _rank_seal(self, key, rows, *, bench='a', expire=False, **scale_options):
        batch = submit_fixture(self.db, key, rows, bench=bench, **scale_options)
        seal = seal_batch(self.db, batch)
        if expire:
            expire_batch(self.db, batch, PERIOD, DUE)
            self.assertIsNone(load_batch_rows(self.db, batch))
        return seal

    def test_moment_reports_after_purge(self):
        expected = {
            'moment-a': (MOMENT_A, Fraction(1, 10), True),
            'moment-b': (MOMENT_B, Fraction(-1, 10), False),
        }
        for key, (rows, q, passed) in expected.items():
            with self.subTest(key=key):
                seal = self._rank_seal(key, rows, expire=True)
                # 清理后仅凭封存联合证据签发。
                report = issue_rank_review(self.db, [seal.seal_id], 0)
                self.assertEqual((report.n, report.q, report.passed), (4, q, passed))
                self.assertEqual((report.project, report.seal_ids, report.threshold),
                                 (PROJECT, (seal.seal_id,), Fraction(0)))
                self.assertEqual(get_rank_review(self.db, report.report_id), report)
                ordinary = issue_review(self.db, [seal.seal_id], 0)
                self.assertEqual((ordinary.n, ordinary.q, ordinary.passed), (4, Fraction(0), True))
                self.assertEqual(get_review(self.db, ordinary.report_id), ordinary)

    def test_cross_batch_ties_with_relabelled_axes(self):
        left = self._rank_seal('cross-left', CROSS_LEFT)
        right = self._rank_seal(
            'cross-right', CROSS_RIGHT, bench='b', x_slope=-1, x_offset=2,
        )
        ordered = (left.seal_id, right.seal_id)
        for selection in (ordered, ordered[::-1]):
            with self.subTest(selection=selection):
                report = issue_rank_review(self.db, selection, '1/2')
                self.assertEqual(report.seal_ids, ordered)
                self.assertEqual((report.n, report.q, report.threshold, report.passed),
                                 (4, Fraction(1, 2), Fraction(1, 2), True))
                self.assertEqual(get_rank_review(self.db, report.report_id), report)
        # 统一坐标配对为 (0,0),(1,1),(1,0),(2,1)，其中 (1,*) 跨批并列。
        pooled = tuple(
            (u, v)
            for seal in (get_seal(self.db, left.seal_id), get_seal(self.db, right.seal_id))
            for u, v, multiplicity in seal.rank_evidence.pairs
            for _ in range(multiplicity)
        )
        self.assertEqual(sorted(pooled),
                         [(Fraction(0), Fraction(0)), (Fraction(1), Fraction(0)),
                          (Fraction(1), Fraction(1)), (Fraction(2), Fraction(1))])

    def test_repeated_pairs_keep_multiplicity(self):
        seal = self._rank_seal('repeated', REPEATED)
        self.assertEqual(seal.rank_evidence.pair_count, 4)
        report = issue_rank_review(self.db, [seal.seal_id], 0)
        self.assertEqual((report.n, report.q, report.passed),
                         (4, Fraction(2, 27), True))
        # 两个 (0,0) 都以重数 2 保存在证据里，缺测行不入样。
        origin = next(item for item in seal.rank_evidence.pairs if item[:2] == (Fraction(0), Fraction(0)))
        self.assertEqual(origin[2], 2)

    def test_zero_pair_new_seal_succeeds_after_purge(self):
        seal = self._rank_seal('zero-pairs', ZERO_PAIRS, expire=True)
        self.assertEqual(seal.rank_evidence.pairs, ())
        report = issue_rank_review(self.db, [seal.seal_id], 0)
        self.assertEqual((report.n, report.q, report.passed), (0, None, False))
        self.assertEqual(get_rank_review(self.db, report.report_id), report)

    def test_constant_axis_is_undefined(self):
        constant_x = self._rank_seal('constant-x', [('a', 2, 1), ('b', 2, 3)])
        constant_y = self._rank_seal('constant-y', [('a', 0, 2), ('b', 1, 2)])
        diagonal = self._rank_seal('diagonal', [('a', 0, 0), ('b', 1, 1)])
        # 单封存单轴全部并列时，该轴秩无离散，q 无定义。
        for selected in ((constant_x.seal_id,), (constant_y.seal_id,)):
            with self.subTest(selected=selected):
                report = issue_rank_review(self.db, selected, -1)
                self.assertIsNone(report.q)
                self.assertFalse(report.passed)
                self.assertEqual(get_rank_review(self.db, report.report_id), report)
        # 与对角批合批后两轴都有离散，相关恢复定义。
        pooled = issue_rank_review(self.db, [constant_x.seal_id, diagonal.seal_id], -1)
        self.assertEqual(pooled.n, 4)
        self.assertIsNotNone(pooled.q)
        self.assertTrue(pooled.passed)

    def test_single_pair_is_undefined(self):
        one = self._rank_seal('one', [('a', 2, 0), ('b', None, 2)])
        report = issue_rank_review(self.db, [one.seal_id], -1)
        self.assertEqual((report.n, report.q, report.passed), (1, None, False))

    def test_request_rejection_and_missing_evidence(self):
        seal = self._rank_seal('main', [('a', 0, 0), ('b', 1, 1)])
        # 跨项目封存件
        from intake.batches import submit_batch
        from scales.revisions import set_scale
        from tests.support import OTHER_PROJECT, axis_specs
        x, y = axis_specs()
        other_scale = set_scale(self.db, OTHER_PROJECT[0].project, 'a', x=x, y=y)
        other_batch = submit_batch(
            self.db, OTHER_PROJECT[0].project, 'a', 'other', other_scale,
            [('a', 0, 0)], accepted_at=ACCEPTED,
        )
        other = seal_batch(self.db, other_batch)
        invalid = (
            ([], 0),
            ([seal.seal_id, seal.seal_id], 0),
            ([seal.seal_id, 9999], 0),
            ([seal.seal_id, other.seal_id], 0),
            ([seal.seal_id], '1001/1000'),
            ([seal.seal_id], '-2'),
            ([seal.seal_id], 0.5),
            ([True], 0),
            ('1', 0),
        )
        for ids, threshold in invalid:
            with self.subTest(ids=ids, threshold=threshold), self.assertRaises(ValueError):
                issue_rank_review(self.db, ids, threshold)
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM rank_quality_reports').fetchone()[0], 0)
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM rank_report_seals').fetchone()[0], 0)
        # 合法编号在秩报告表查无记录返回 None；非法编号抛 ValueError。
        self.assertIsNone(get_rank_review(self.db, 9999))
        with self.assertRaises(ValueError):
            get_rank_review(self.db, 0)
        with self.assertRaises(ValueError):
            get_rank_review(self.db, 1.5)

    def test_legacy_missing_evidence_seal_rejects_whole_issue(self):
        with TemporaryDirectory(prefix='yuchuan-legacy-') as directory:
            path = Path(directory) / 'legacy.sqlite3'
            build_legacy_v1_database(path)
            self.db.close()
            self.db = open_database(path)
            # 新版 initialize 在 V1 库上补表升级，旧记录原样可读。
            initialize(self.db)
            legacy = get_seal(self.db, 1)
            self.assertIsNone(legacy.rank_evidence)
            ordinary = get_review(self.db, 1)
            self.assertEqual((ordinary.n, ordinary.q, ordinary.passed), (0, None, False))
            # 缺证旧件单选即整次拒发。
            with self.assertRaisesRegex(ValueError, 'rank evidence'):
                issue_rank_review(self.db, [1], 0)
            # 续写新批次并封存，新空件拥有完整（零对）证据。
            new_seal = self._rank_seal('new-zero', ZERO_PAIRS)
            # 缺证旧件与零对新件混选同样整次拒发。
            with self.assertRaisesRegex(ValueError, 'rank evidence'):
                issue_rank_review(self.db, [1, new_seal.seal_id], 0)
            self.assertEqual(
                self.db.execute('SELECT COUNT(*) FROM rank_quality_reports').fetchone()[0], 0)
            # 零对新件单选成功签发。
            report = issue_rank_review(self.db, [new_seal.seal_id], 0)
            self.assertEqual((report.n, report.q, report.passed), (0, None, False))
            self.assertEqual(get_rank_review(self.db, report.report_id), report)

    def test_failed_rank_report_rolls_back_and_retries(self):
        left = self._rank_seal('left', [('a', 0, 0), ('b', 1, 1)])
        right = self._rank_seal('right', [('a', 0, 1), ('b', 1, 0)], bench='b')
        with failing_commit(self.db, 'rank_quality_reports'):
            with self.assertRaises(sqlite3.IntegrityError):
                issue_rank_review(self.db, [left.seal_id, right.seal_id], 0)
        self.reopen()
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM rank_quality_reports').fetchone()[0], 0)
        self.assertEqual(
            self.db.execute('SELECT COUNT(*) FROM rank_report_seals').fetchone()[0], 0)
        report = issue_rank_review(self.db, [left.seal_id, right.seal_id], 0)
        self.assertEqual(report.n, 4)
        self.assertEqual(get_rank_review(self.db, report.report_id), report)

    def test_failed_seal_rolls_back_rank_evidence_and_retries(self):
        batch = self.submit('retry-rank', [('a', 1, 2), ('b', 2, 1)])
        with failing_commit(self.db, 'sealed_evidence'):
            with self.assertRaises(sqlite3.IntegrityError):
                seal_batch(self.db, batch)
        self.reopen()
        self.assertIsNone(get_seal(self.db, 1))
        seal = seal_batch(self.db, batch)
        self.assertEqual(seal.rank_evidence.pair_count, 2)
        report = issue_rank_review(self.db, [seal.seal_id], -1)
        self.assertEqual((report.n, report.q, report.passed), (2, Fraction(-1), True))

    def test_persistence_across_reopen_and_correction(self):
        seal = self._rank_seal('persist', MOMENT_A, expire=True)
        report = issue_rank_review(self.db, [seal.seal_id], 0)
        self.reopen()
        # 清理、重开后按原号领取已签发结果。
        self.assertEqual(get_rank_review(self.db, report.report_id), report)
        self.assertEqual(get_seal(self.db, seal.seal_id), seal)
