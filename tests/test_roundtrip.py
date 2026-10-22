"""Executable public counterpart to the private live handoff bench."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import porchlight as p

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / 'examples'


class RoundtripTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'demo.sqlite3'
        p.initialize(self.db)
        self.data = p.load_json(EXAMPLES / 'roundtrip.json')

    def tearDown(self):
        self.temp.cleanup()

    def test_four_handoffs_are_observer_scoped_and_recoverable(self):
        self.assertEqual(p.import_data(self.db, self.data)['inserted'], 20)
        self.assertEqual(p.import_data(self.db, self.data)['inserted'], 0)
        recovered = p.read_data(self.db)
        for op in recovered['operations']:
            with self.subTest(operation=op['id']):
                sender = p.project(recovered, op['id'], op['author'])
                recipient = p.project(recovered, op['id'], op['recipient'])
                self.assertTrue(sender['acknowledged'])
                self.assertTrue(recipient['readback_match'])
                self.assertFalse(recipient['accepted'])
                self.assertFalse(recipient['acknowledged'])
                self.assertEqual(sender['flags'], [])
                self.assertEqual(sender['unscoped_receipts'], [])
        self.assertTrue(all(not value for value in p.unresolved(recovered).values()))

    def test_receipts_can_arrive_before_operations(self):
        p.import_data(self.db, {'schema_version': 1, 'receipts': self.data['receipts']})
        self.assertEqual(len(p.unresolved(p.read_data(self.db))['orphan_receipts']), 16)
        p.import_data(self.db, {'schema_version': 1, 'operations': self.data['operations']})
        self.assertEqual(p.read_data(self.db), p.validate(self.data))

    def test_correction_withdraws_anchors_and_fresh_receipt_restores(self):
        p.import_data(self.db, self.data)
        p.import_data(self.db, p.load_json(EXAMPLES / 'correction.json'))
        state = p.project(p.read_data(self.db), 'alpha:mail:handoff-1', 'alpha')
        self.assertFalse(state['acknowledged'])
        self.assertFalse(state['readback_match'])
        self.assertEqual(len(state['retracted_receipts']), 2)
        p.import_data(self.db, p.load_json(EXAMPLES / 'repair.json'))
        saved = p.read_data(self.db)
        self.assertTrue(p.project(saved, 'alpha:mail:handoff-1', 'alpha')['acknowledged'])
        self.assertEqual(len(saved['receipts']), 19)

    def test_example_script_is_an_offline_executable_acceptance_check(self):
        run = subprocess.run([sys.executable, str(EXAMPLES / 'replay.py')], text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        report = json.loads(run.stdout)
        self.assertTrue(report['fixture_only'])
        self.assertEqual(len(report['handoffs']), 4)
        self.assertEqual(report['duplicate_inserted'], 0)

    def test_cli_export_import_keeps_exact_record_bytes(self):
        p.import_data(self.db, self.data)
        run = subprocess.run([sys.executable, str(ROOT / 'porchlight.py'), 'export', '--db', str(self.db)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        other = Path(self.temp.name) / 'recovered.sqlite3'
        p.initialize(other)
        p.import_data(other, json.loads(run.stdout))
        self.assertEqual(p.canonical(p.read_data(other)), p.canonical(p.read_data(self.db)))


if __name__ == '__main__':
    unittest.main()
