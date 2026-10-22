"""Additional integration counterexamples; complements Flint's review patch."""
import sqlite3
from pathlib import Path
import tempfile
import unittest

import porchlight as p
from test_porchlight import dataset, operation, receipt, T0, T1, T2


class EvidenceIsolationTests(unittest.TestCase):
    def test_good_ack_survives_an_unrelated_bad_ack(self):
        rows = [receipt('a', 'accepted'), receipt('r', 'readback'),
                receipt('good', 'ack_received', time=T1),
                receipt('wrong', 'ack_received', time=T2, remote_ref='fixture:copy')]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertTrue(state['acknowledged'])
        self.assertEqual(state['ack_receipts'], ['good'])
        self.assertEqual(state['visibility'], 'matching')
        self.assertIn('remote_identity_conflict', state['flags'])

    def test_ack_before_later_readback_can_be_corroborated(self):
        # Read-back observation time is not object creation time.
        rows = [receipt('ack', 'ack_received', time=T0), receipt('read', 'readback', time=T1)]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertTrue(state['acknowledged'])
        self.assertTrue(state['readback_match'])

    def test_old_attempt_conflict_is_not_reported_as_later_success(self):
        rows = [receipt('accept', 'accepted'), receipt('deny', 'blocked', time=T1)]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertEqual(state['latest_attempt_result'], 'uncertain')
        self.assertIn('contradictory_attempt_evidence', state['flags'])

    def test_later_distinct_attempt_does_not_inherit_old_acceptance(self):
        rows = [receipt('old-accept', 'accepted'),
                receipt('new-timeout', 'timeout', time=T1, attempt_id='attempt-2')]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertTrue(state['accepted'])
        self.assertEqual(state['latest_attempt_result'], 'timeout')

    def test_tied_attempts_with_different_results_remain_uncertain(self):
        rows = [receipt('accept', 'accepted'), receipt('timeout', 'timeout', attempt_id='attempt-2')]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertEqual(state['latest_attempt_result'], 'uncertain')

    def test_acceptance_with_two_contradictions_exposes_both(self):
        rows = [receipt('accept', 'accepted', content_sha256=p.digest('wrong'),
                        observed_destination='fixture:wrong'), receipt('ack', 'ack_received', time=T1)]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertFalse(state['acknowledged'])
        self.assertIn('accepted_content_mismatch', state['flags'])
        self.assertIn('accepted_destination_mismatch', state['flags'])

    def test_matching_readback_is_not_erased_by_contradictory_acceptance(self):
        rows = [receipt('accept', 'accepted', content_sha256=p.digest('wrong')),
                receipt('read', 'readback', time=T1)]
        state = p.project(dataset(receipts=rows), 'op-1', 'alpha')
        self.assertTrue(state['readback_match'])
        self.assertEqual(state['visibility'], 'matching')
        self.assertIn('accepted_content_mismatch', state['flags'])


class JournalGuardTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / 'journal.sqlite3'
        p.initialize(self.db)
        p.import_data(self.db, dataset())

    def tearDown(self):
        self.directory.cleanup()

    def test_new_journal_has_all_expected_guards(self):
        with p.journal(self.db) as con:
            self.assertEqual(p.journal_guards(con), {'present': list(p.GUARDS), 'missing': []})

    def test_legacy_journal_stays_readable_but_write_refused(self):
        with sqlite3.connect(self.db) as con:
            con.execute('DROP TRIGGER no_replace')
        before = self.db.read_bytes()
        self.assertEqual(p.read_data(self.db)['operations'], [operation()])
        with p.journal(self.db) as con:
            self.assertEqual(p.journal_guards(con)['missing'], ['no_replace'])
        with self.assertRaisesRegex(p.Invalid, 'export and import into a new journal'):
            p.import_data(self.db, dataset(operations=[operation('new')]))
        self.assertEqual(self.db.read_bytes(), before)

    def test_legacy_export_can_be_imported_without_mutating_original(self):
        with sqlite3.connect(self.db) as con:
            con.execute('DROP TRIGGER no_replace')
        before = self.db.read_bytes()
        saved = p.read_data(self.db)
        replacement = Path(self.directory.name) / 'new.sqlite3'
        p.initialize(replacement)
        p.import_data(replacement, saved)
        self.assertEqual(p.read_data(replacement), saved)
        self.assertEqual(self.db.read_bytes(), before)

    def test_replace_and_upsert_leave_the_record_unchanged(self):
        statements = [
            "REPLACE INTO records VALUES ('operations','op-1','{}','test')",
            "INSERT INTO records VALUES ('operations','op-1','{}','test') "
            "ON CONFLICT(kind,id) DO UPDATE SET body='{}'",
        ]
        with p.journal(self.db, write=True) as con:
            for sql in statements:
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    con.execute(sql)
        self.assertEqual(p.read_data(self.db)['operations'], [operation()])


if __name__ == '__main__':
    unittest.main()
