"""Walpo's independent regressions for Flint's late-target poisoning finding."""
import itertools
from pathlib import Path
import tempfile
import unittest

import porchlight as p
from test_porchlight import dataset, operation, receipt
from test_flint_r2 import retract


class RetractionArrivalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def journal(self, name='case'):
        db = self.root / (name + '.sqlite3')
        p.initialize(db)
        return db

    def test_wrong_operation_early_withdrawal_cannot_block_valid_target(self):
        for author in ('alpha', 'beta'):
            with self.subTest(author=author):
                db = self.journal(author)
                wrong = retract('wrong', 'good', observer=author, operation_id='op-2')
                p.import_data(db, dataset(operations=[operation(), operation('op-2')], receipts=[wrong]))
                p.import_data(db, dataset(operations=[], receipts=[receipt('good', 'readback')]))
                stored = p.read_data(db)
                status = p.project(stored, 'op-1', 'alpha')
                self.assertTrue(status['readback_match'])
                self.assertEqual(status['retracted_receipts'], [])
                invalid = p.unresolved(stored)['invalid_retractions']
                self.assertEqual(invalid[0]['receipt_id'], 'wrong')
                self.assertIn('operation_mismatch', invalid[0]['reasons'])

    def test_late_valid_withdrawal_is_not_blocked_by_an_early_reference_to_it(self):
        for observer in ('alpha', 'beta'):
            with self.subTest(observer=observer):
                db = self.journal(observer)
                p.import_data(db, dataset(receipts=[receipt('good', 'readback'),
                    retract('premature', 'legitimate', observer=observer)]))
                p.import_data(db, dataset(operations=[], receipts=[retract('legitimate', 'good')]))
                stored = p.read_data(db)
                state = p.project(stored, 'op-1', 'alpha')
                self.assertFalse(state['readback_match'])
                self.assertEqual(state['retracted_receipts'], ['good'])
                self.assertEqual(p.unresolved(stored)['invalid_retractions'][0]['reasons'], ['target_is_retraction'])

    def test_withdrawal_cycles_are_inert_not_resurrection_or_import_blocks(self):
        for count in (2, 3):
            with self.subTest(count=count):
                db = self.journal(str(count))
                p.import_data(db, dataset(receipts=[receipt('good', 'readback')]))
                rows = [retract(f'x{i}', f'x{(i+1)%count}') for i in range(count)]
                for r in rows:
                    p.import_data(db, dataset(operations=[], receipts=[r]))
                state = p.project(p.read_data(db), 'op-1', 'alpha')
                self.assertTrue(state['readback_match'])
                self.assertEqual(state['retracted_receipts'], [])
                invalid = p.unresolved(p.read_data(db))['invalid_retractions']
                self.assertEqual(len(invalid), count)
                self.assertTrue(all(r['reasons'] == ['target_is_retraction'] for r in invalid))

    def test_both_relationship_problems_are_reported(self):
        data = dataset(operations=[operation(), operation('op-2')], receipts=[
            receipt('good', 'readback'), retract('legitimate', 'good'),
            retract('wrong', 'legitimate', operation_id='op-2')])
        stored = p.validate(data)
        invalid = p.unresolved(stored)['invalid_retractions']
        self.assertEqual(invalid, [{'receipt_id': 'wrong', 'retracts': 'legitimate', 'observer': 'alpha',
                                    'reasons': ['operation_mismatch', 'target_is_retraction']}])
        self.assertEqual(p.project(stored, 'op-1', 'alpha')['retracted_receipts'], ['good'])

    def test_all_import_orders_preserve_valid_correction(self):
        data = dataset(receipts=[receipt('good', 'readback'), retract('valid', 'good'),
                                 retract('bad', 'valid', observer='beta')])
        events = [('operations', data['operations'][0])] + [('receipts', r) for r in data['receipts']]
        expected = p.canonical(p.validate(data))
        expected_status = p.project(data, 'op-1', 'alpha')
        expected_unresolved = p.unresolved(data)
        for i, order in enumerate(itertools.permutations(events)):
            with self.subTest(order=i):
                db = self.journal('order-' + str(i))
                for table, row in order:
                    p.import_data(db, {'schema_version': 1, table: [row]})
                stored = p.read_data(db)
                self.assertEqual(p.canonical(stored), expected)
                self.assertEqual(p.project(stored, 'op-1', 'alpha'), expected_status)
                self.assertEqual(p.unresolved(stored), expected_unresolved)
                self.assertEqual(p.import_data(db, data)['inserted'], 0)

    def test_unknown_target_transitions_to_invalid_without_discarding_either(self):
        db = self.journal()
        wrong = retract('wrong', 'good', operation_id='op-2')
        p.import_data(db, dataset(operations=[operation(), operation('op-2')], receipts=[wrong]))
        before = p.unresolved(p.read_data(db))
        self.assertEqual(len(before['unresolved_retractions']), 1)
        self.assertEqual(before['invalid_retractions'], [])
        p.import_data(db, dataset(operations=[], receipts=[receipt('good', 'readback')]))
        stored = p.read_data(db)
        after = p.unresolved(stored)
        self.assertEqual(after['unresolved_retractions'], [])
        self.assertEqual(len(after['invalid_retractions']), 1)
        self.assertEqual({r['id'] for r in stored['receipts']}, {'wrong', 'good'})

    def test_intrinsic_self_retraction_is_still_rejected_atomically(self):
        db = self.journal()
        with self.assertRaises(p.Invalid):
            p.import_data(db, dataset(receipts=[retract('self', 'self')]))
        self.assertEqual(p.read_data(db)['operations'], [])


if __name__ == '__main__':
    unittest.main()
