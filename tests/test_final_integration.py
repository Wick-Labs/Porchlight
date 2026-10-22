"""Review counterexamples: Flint's extra-trigger finding and Walpo integration."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import porchlight as p
from test_porchlight import dataset, operation, receipt


class ExtraTriggerReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'journal.sqlite3'
        p.initialize(self.db)
        p.import_data(self.db, dataset())

    def tearDown(self):
        self.temp.cleanup()

    def swallow(self):
        with sqlite3.connect(self.db) as con:
            con.execute('CREATE TRIGGER zz_swallow BEFORE INSERT ON records BEGIN SELECT RAISE(IGNORE); END')

    def test_silently_swallowed_insert_is_not_reported_as_saved(self):
        # Flint's independently supplied counterexample against d1219f7.
        self.swallow()
        before = self.db.read_bytes()
        with p.journal(self.db) as con:
            self.assertEqual(p.journal_guards(con)['unexpected'], ['zz_swallow'])
        with self.assertRaisesRegex(p.Invalid, 'unexpected'):
            p.import_data(self.db, dataset(operations=[operation('new')]))
        self.assertEqual(p.read_data(self.db)['operations'], [operation()])
        self.assertEqual(self.db.read_bytes(), before)

    def test_trigger_on_another_table_is_also_reported(self):
        with sqlite3.connect(self.db) as con:
            con.execute('CREATE TABLE other (value TEXT)')
            con.execute('CREATE TRIGGER unexpected_other AFTER INSERT ON other BEGIN SELECT 1; END')
        with p.journal(self.db) as con:
            self.assertEqual(p.journal_guards(con)['unexpected'], ['unexpected_other'])
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset())

    def test_real_row_count_check_detects_swallow_even_without_preflight(self):
        self.swallow()
        # Fault injection, not an operational bypass: demonstrates a separate check.
        with patch.object(p, '_require_guards'), self.assertRaisesRegex(p.Invalid, 'insert was not recorded'):
            p.import_data(self.db, dataset(operations=[operation('new')]))
        self.assertEqual(p.read_data(self.db)['operations'], [operation()])

    def test_injected_sql_failure_after_first_insert_rolls_back(self):
        real_journal = p.journal
        class FaultConnection:
            def __init__(self, connection):
                self.connection = connection
                self.inserts = 0
            def __getattr__(self, key):
                return getattr(self.connection, key)
            def execute(self, sql, *args):
                if sql.startswith('INSERT INTO records'):
                    self.inserts += 1
                    if self.inserts == 2:
                        raise sqlite3.OperationalError('synthetic mid-import fault')
                return self.connection.execute(sql, *args)
        @contextmanager
        def fault(path, *, write=False):
            with real_journal(path, write=write) as con:
                yield FaultConnection(con) if write else con
        new = operation('new')
        before = p.read_data(self.db)
        with patch.object(p, 'journal', fault), self.assertRaises(sqlite3.OperationalError):
            p.import_data(self.db, dataset(operations=[new], receipts=[receipt('read', 'readback', new)]))
        self.assertEqual(p.read_data(self.db), before)

    def test_recovery_preserves_original_with_extra_trigger(self):
        self.swallow()
        old = self.db.read_bytes()
        data = p.read_data(self.db)
        other = Path(self.temp.name) / 'recovered.sqlite3'
        p.initialize(other)
        p.import_data(other, data)
        self.assertEqual(p.read_data(other), data)
        self.assertEqual(self.db.read_bytes(), old)
        with p.journal(other) as con:
            self.assertEqual(p.journal_guards(con)['unexpected'], [])

    def test_new_journal_import_count_matches_actual_records(self):
        result = p.import_data(self.db, dataset(operations=[operation('new')]))
        self.assertEqual(result, {'inserted': 1, 'unchanged': 1})
        self.assertEqual(len(p.read_data(self.db)['operations']), 2)


class RetractionScopeIntegrationTests(unittest.TestCase):
    """Joint Walpo/Flint decision: withdrawals clear active warnings, not history."""
    def rows(self, observer='alpha'):
        from test_flint_r2 import retract, SCOPE
        return [receipt('wrong-scope', 'blocked', **{**SCOPE, 'expected_context': 'scheduled'}),
                retract('withdraw', 'wrong-scope', observer=observer)]

    def test_same_observer_retraction_clears_active_scope_warning(self):
        data = dataset(receipts=self.rows())
        before = p.canonical(p.validate(data))
        state = p.project(data, 'op-1', 'alpha')
        self.assertNotIn('orphan_context_mismatch', state['flags'])
        self.assertEqual(p.unresolved(data)['scope_mismatched_receipts'], [])
        self.assertFalse(state['ever_blocked'])
        self.assertEqual(state['excluded_receipts'], ['wrong-scope'])
        self.assertEqual(state['retracted_receipts'], ['wrong-scope'])
        self.assertEqual(p.canonical(p.validate(data)), before)

    def test_other_observer_retraction_keeps_scope_warning(self):
        data = dataset(receipts=self.rows('beta'))
        state = p.project(data, 'op-1', 'alpha')
        self.assertIn('orphan_context_mismatch', state['flags'])
        self.assertEqual(len(p.unresolved(data)['scope_mismatched_receipts']), 1)
        self.assertEqual(state['retraction_reports'], ['withdraw'])
        self.assertEqual(state['retracted_receipts'], [])

    def test_withdrawn_orphan_no_longer_appears_as_active_receipt(self):
        data = dataset(operations=[], receipts=self.rows())
        unresolved = p.unresolved(data)
        # The withdrawal still has a structural reference to the missing operation.
        self.assertEqual([r['receipt_id'] for r in unresolved['orphan_receipts']], ['withdraw'])
        self.assertEqual(unresolved['unresolved_retractions'], [])

    def test_scope_withdrawal_is_independent_of_arrival_order(self):
        import itertools
        data = dataset(receipts=self.rows())
        events = [('operations', data['operations'][0])] + [('receipts', r) for r in data['receipts']]
        expected = p.project(data, 'op-1', 'alpha')
        with tempfile.TemporaryDirectory() as directory:
            for i, order in enumerate(itertools.permutations(events)):
                db = Path(directory) / f'order-{i}.sqlite3'
                p.initialize(db)
                for table, row in order:
                    p.import_data(db, {'schema_version': 1, table: [row]})
                saved = p.read_data(db)
                self.assertEqual(p.project(saved, 'op-1', 'alpha'), expected)
                self.assertEqual(p.unresolved(saved)['scope_mismatched_receipts'], [])

    def test_source_time_fields_on_withdrawal_are_rejected(self):
        rows = self.rows()
        rows[1].update(source_at='2026-01-01T10:00:00Z', source_origin='fixture:clock',
                       source_trust='authoritative')
        with self.assertRaisesRegex(p.Invalid, 'carries no evidence fields'):
            p.validate(dataset(receipts=rows))


if __name__ == '__main__':
    unittest.main()
