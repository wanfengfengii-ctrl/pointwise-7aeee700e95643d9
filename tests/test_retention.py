import sqlite3
from datetime import timedelta, timezone
from fractions import Fraction

from freeze.catalog import get_seal
from freeze.package import seal_batch
from intake.store import load_batch_header, load_batch_rows
from retention.purge import expire_batch
from retention.receipts import lookup_receipt
from review.reports import get_review, issue_review
from scales.revisions import require_scale_revision
from tests.support import ACCEPTED, DUE, PERIOD, DatabaseCase, failing_commit


class RetentionTests(DatabaseCase):
    def test_review_after_expiry(self):
        a, b = self.shifted_pair_of_batches()
        ids = (a.seal_id, b.seal_id)
        old_review = issue_review(self.db, ids, '1/2')
        a_receipt = expire_batch(self.db, a.batch_id, PERIOD, DUE)
        b_receipt = expire_batch(self.db, b.batch_id, PERIOD, DUE)
        changed_scale = self.scale('b', x_offset=3)
        self.reopen()
        self.assertIsNone(load_batch_rows(self.db, a.batch_id))
        self.assertIsNone(load_batch_rows(self.db, b.batch_id))
        self.assertEqual(get_review(self.db, old_review.report_id), old_review)
        self.assertEqual((old_review.n, old_review.q, old_review.passed), (3, Fraction(0), False))
        reversed_review = issue_review(self.db, reversed(ids), '1/2')
        self.assertEqual((reversed_review.seal_ids, reversed_review.n, reversed_review.q,
                          reversed_review.passed), (ids, 3, Fraction(0), False))
        self.assertEqual(get_seal(self.db, b.seal_id), b)
        self.assertEqual(require_scale_revision(self.db, b.scale_id).x.offset, 2)
        self.assertEqual(require_scale_revision(self.db, changed_scale).x.offset, 3)
        self.assertEqual(expire_batch(self.db, a.batch_id, PERIOD, DUE), a_receipt)
        self.assertEqual(expire_batch(self.db, b.batch_id, PERIOD, DUE), b_receipt)

    def test_replacement_history(self):
        a, old_b = self.shifted_pair_of_batches()
        old = issue_review(self.db, [a.seal_id, old_b.seal_id], '1/2')
        expire_batch(self.db, old_b.batch_id, PERIOD, DUE)
        scale = self.scale('b', x_offset=3)
        replacement = self.submit('b-correction', [('b0', 0, 0)], bench='b', scale_id=scale,
                                  accepted_at=DUE, predecessor_id=old_b.batch_id)
        new_b = seal_batch(self.db, replacement)
        self.reopen()
        head = load_batch_header(self.db, replacement)
        self.assertEqual((head.predecessor_id, head.scale_id), (old_b.batch_id, scale))
        self.assertEqual(load_batch_header(self.db, old_b.batch_id).scale_id, old_b.scale_id)
        self.assertEqual(get_seal(self.db, old_b.seal_id), old_b)
        self.assertEqual(get_review(self.db, old.report_id), old)
        self.assertEqual(expire_batch(self.db, old_b.batch_id, PERIOD, ACCEPTED).supporting_seal_id,
                         old_b.seal_id)
        repeated = self.submit('shift-right', [('b0', 0, 0)], bench='b', scale_id=old_b.scale_id)
        self.assertEqual(repeated, old_b.batch_id)
        with self.assertRaisesRegex(ValueError, 'conflicting'):
            self.submit('shift-right', [('b0', 2, 0)], bench='b', scale_id=old_b.scale_id)
        new = issue_review(self.db, [a.seal_id, new_b.seal_id], 0)
        self.assertEqual((new.n, new.q, new.passed), (3, Fraction(-1, 28), False))
        self.assertEqual(old.q, 0)

    def test_deadline_and_retry(self):
        batch = self.submit('due', [('a', 0, 1), ('b', None, 1)])
        seal = seal_batch(self.db, batch)
        self.assertEqual(PERIOD.deadline(ACCEPTED), DUE)
        equivalent_cutoff = DUE.astimezone(timezone(timedelta(hours=8)))
        original = expire_batch(self.db, batch, PERIOD, equivalent_cutoff)
        self.assertEqual((original.batch_id, original.supporting_seal_id, original.cutoff,
                          original.removed_rows), (batch, seal.seal_id, DUE, 2))
        self.reopen()
        self.assertEqual(expire_batch(self.db, batch, PERIOD, ACCEPTED), original)
        self.assertEqual(expire_batch(self.db, batch, PERIOD, DUE + timedelta(days=1)), original)
        self.assertEqual(lookup_receipt(self.db, batch), original)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM expiry_receipts').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM observation_rows WHERE batch_id = ?',
                                         (batch,)).fetchone()[0], 0)
        with self.assertRaisesRegex(ValueError, 'unavailable'):
            seal_batch(self.db, batch)

    def test_atomic_expiry(self):
        seal, other = self.shifted_pair_of_batches()
        report = issue_review(self.db, [seal.seal_id, other.seal_id], '1/2')
        previous = load_batch_rows(self.db, seal.batch_id)
        with failing_commit(self.db, 'expiry_receipts'):
            with self.assertRaises(sqlite3.IntegrityError):
                expire_batch(self.db, seal.batch_id, PERIOD, DUE)
        self.reopen()
        self.assertFalse(load_batch_header(self.db, seal.batch_id).expired)
        self.assertEqual(load_batch_rows(self.db, seal.batch_id), previous)
        self.assertIsNone(lookup_receipt(self.db, seal.batch_id))
        self.assertEqual(get_review(self.db, report.report_id), report)
        self.assertEqual(get_seal(self.db, seal.seal_id), seal)
        self.assertEqual(expire_batch(self.db, seal.batch_id, PERIOD, DUE).removed_rows, 2)

    def test_unsealed_expiry(self):
        batch = self.submit('unsealed', [('a', 0, 1)])
        previous = load_batch_rows(self.db, batch)
        with self.assertRaisesRegex(ValueError, 'no committed seal'):
            expire_batch(self.db, batch, PERIOD, DUE)
        self.assertEqual(load_batch_rows(self.db, batch), previous)
        self.assertIsNone(lookup_receipt(self.db, batch))
        self.assertEqual(seal_batch(self.db, batch).moments.n, 1)

    def test_wrong_revision(self):
        batch = self.submit('first', [('a', 0, 1)])
        first = seal_batch(self.db, batch)
        replacement = self.submit('second', [('a', 0, 2)], predecessor_id=batch)
        previous = load_batch_rows(self.db, replacement)
        with self.assertRaisesRegex(ValueError, 'no committed seal'):
            expire_batch(self.db, replacement, PERIOD, DUE)
        self.assertEqual(load_batch_rows(self.db, replacement), previous)
        self.assertIsNone(lookup_receipt(self.db, replacement))
        second = seal_batch(self.db, replacement)
        receipt = expire_batch(self.db, replacement, PERIOD, DUE)
        self.assertEqual(receipt.supporting_seal_id, second.seal_id)
        self.assertNotEqual(receipt.supporting_seal_id, first.seal_id)
        self.assertEqual(get_seal(self.db, first.seal_id), first)

    def test_not_due(self):
        batch = self.submit('early', [('a', 0, 1)])
        seal_batch(self.db, batch)
        previous = load_batch_rows(self.db, batch)
        with self.assertRaisesRegex(ValueError, 'deadline'):
            expire_batch(self.db, batch, PERIOD, DUE - timedelta(microseconds=1))
        self.assertEqual(load_batch_rows(self.db, batch), previous)
        self.assertIsNone(lookup_receipt(self.db, batch))
