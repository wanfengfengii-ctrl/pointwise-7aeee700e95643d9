import sqlite3
from fractions import Fraction

from freeze.catalog import find_seal_for_batch, get_seal
from freeze.moments import PairedMoments
from freeze.package import seal_batch
from intake.store import load_batch_rows
from retention.purge import expire_batch
from retention.receipts import lookup_receipt
from tests.support import DUE, PERIOD, PROJECT, DatabaseCase, failing_commit


class FreezeTests(DatabaseCase):
    def test_duplicate_and_missing(self):
        batch = self.submit('paired', [('a', 1, 3), ('b', 1, 3), ('c', 5, None)])
        seal = seal_batch(self.db, batch)
        self.assertEqual(seal.moments, PairedMoments(2, 2, 6, 2, 18, 6))
        self.assertEqual(get_seal(self.db, seal.seal_id), seal)
        self.assertEqual(seal_batch(self.db, batch), seal)
        self.assertIsNone(get_seal(self.db, 9999))

    def test_complementary_missing(self):
        rows = [('a', 0, 0), ('b', 0, 0), ('c', 9, None), ('d', None, 8)]
        batch = self.submit('paired', rows)
        self.assertEqual(seal_batch(self.db, batch).moments, PairedMoments(2))

    def test_fixed_coordinates(self):
        scale = self.scale(x_offset=2)
        rows = [('a', 0, 0), ('b', 0, 0), ('c', 9, None), ('d', None, 8)]
        batch = self.submit('shifted', rows, scale_id=scale)
        self.scale(x_offset=3)
        seal_id = seal_batch(self.db, batch).seal_id
        self.reopen()
        seal = get_seal(self.db, seal_id)
        self.assertEqual((seal.project, seal.batch_id, seal.scale_id), (PROJECT, batch, scale))
        self.assertEqual(seal.moments, PairedMoments(2, 4, 0, 8, 0, 0))

    def test_fractional_axes_round_trip(self):
        scale = self.scale(x_slope='-1/2', x_offset='1/3', y_slope='2/3', y_offset='-1/2')
        batch = self.submit('fractional', [('a', '1/3', '1/2')], scale_id=scale)
        seal_id = seal_batch(self.db, batch).seal_id
        self.reopen()
        self.assertEqual(get_seal(self.db, seal_id).moments, PairedMoments(
            1, Fraction(1, 6), Fraction(-1, 6), Fraction(1, 36), Fraction(1, 36), Fraction(-1, 36),
        ))

    def test_failed_seal(self):
        batch = self.submit('retry', [('a', 1, 2)])
        before = load_batch_rows(self.db, batch)
        with failing_commit(self.db, 'sealed_evidence'):
            with self.assertRaises(sqlite3.IntegrityError):
                seal_batch(self.db, batch)
        self.reopen()
        self.assertIsNone(find_seal_for_batch(self.db, batch))
        self.assertIsNone(get_seal(self.db, 1))
        self.assertEqual(load_batch_rows(self.db, batch), before)
        with self.assertRaisesRegex(ValueError, 'no committed seal'):
            expire_batch(self.db, batch, PERIOD, DUE)
        self.assertIsNone(lookup_receipt(self.db, batch))
        seal = seal_batch(self.db, batch)
        self.assertEqual(find_seal_for_batch(self.db, batch), seal)
        self.assertEqual(seal.moments, PairedMoments(1, 1, 2, 1, 4, 2))
