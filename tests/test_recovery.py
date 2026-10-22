"""Review-driven recovery tests; all records and identifiers are synthetic."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import porchlight as p
from test_porchlight import dataset, observation, operation, receipt, T0, T1, T2


class OrphanRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "journal.sqlite3"
        p.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def test_receipt_before_operation_is_preserved_and_exposed(self):
        row = receipt("early", "readback")
        p.import_data(self.db, dataset(operations=[], receipts=[row]))
        data = p.read_data(self.db)
        self.assertEqual(data["receipts"], [row])
        self.assertEqual(p.unresolved(data)["orphan_receipts"], [
            {"receipt_id": "early", "operation_id": "op-1", "observer": "alpha"}])
        with self.assertRaises(p.Invalid):
            p.project(data, "op-1", "alpha")
        p.import_data(self.db, dataset())
        data = p.read_data(self.db)
        self.assertEqual(p.unresolved(data)["orphan_receipts"], [])
        self.assertTrue(p.project(data, "op-1", "alpha")["readback_match"])
        self.assertEqual(data["receipts"], [row])

    def test_orphan_report_never_promotes_direct_flags(self):
        p.import_data(self.db, dataset(operations=[], receipts=[receipt("claim", "report")]))
        p.import_data(self.db, dataset())
        status = p.project(p.read_data(self.db), "op-1", "alpha")
        self.assertFalse(status["accepted"])
        self.assertFalse(status["readback_match"])
        self.assertFalse(status["acknowledged"])
        self.assertEqual(status["reports"], ["claim"])

    def test_orphan_resolution_checks_actual_content(self):
        p.import_data(self.db, dataset(operations=[], receipts=[receipt("r", "readback")]))
        p.import_data(self.db, dataset(operations=[operation(payload="Not the expected bytes.")]))
        status = p.project(p.read_data(self.db), "op-1", "alpha")
        self.assertFalse(status["readback_match"])
        self.assertIn("content_mismatch", status["flags"])

    def test_repeated_orphan_import_is_idempotent(self):
        batch = dataset(operations=[], receipts=[receipt("r", "readback")])
        self.assertEqual(p.import_data(self.db, batch)["inserted"], 1)
        self.assertEqual(p.import_data(self.db, batch)["inserted"], 0)
        self.assertEqual(len(p.unresolved(p.read_data(self.db))["orphan_receipts"]), 1)

    def test_conflicting_orphan_import_rolls_back_other_records(self):
        row = receipt("r", "readback")
        p.import_data(self.db, dataset(operations=[], receipts=[row]))
        before = p.read_data(self.db)
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset(receipts=[{**row, "remote_ref": "fixture:wrong"}]))
        self.assertEqual(p.read_data(self.db), before)

    def test_conflict_inside_new_batch_is_atomic(self):
        first = receipt("same", "readback")
        other = {**first, "observer": "beta"}
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset(receipts=[first, other]))
        self.assertEqual(p.read_data(self.db), dataset(operations=[]))

    def test_key_order_is_not_a_conflict(self):
        row = receipt("r", "readback")
        original = dataset(receipts=[row])
        p.import_data(self.db, original)
        reordered = {key: [dict(reversed(list(r.items()))) for r in value] if isinstance(value, list) else value
                     for key, value in reversed(list(original.items()))}
        self.assertEqual(p.import_data(self.db, reordered)["inserted"], 0)
        self.assertEqual(p.read_data(self.db), p.validate(original))

    def test_retry_at_unique_record_limit_remains_idempotent(self):
        with patch.object(p, "MAX_RECORDS", 2):
            batch = dataset(operations=[operation(), operation("other")])
            self.assertEqual(p.import_data(self.db, batch)["inserted"], 2)
            self.assertEqual(p.import_data(self.db, batch)["inserted"], 0)
            with self.assertRaises(p.Invalid):
                p.import_data(self.db, dataset(operations=[operation("third")]))
            self.assertEqual(len(p.read_data(self.db)["operations"]), 2)

    def test_seeded_single_record_import_permutations_are_identical(self):
        old = operation()
        new = operation("new", payload="A newer light.", supersedes=["op-1"])
        data = dataset(operations=[old, new, operation("separate")], receipts=[
            receipt("accepted", "accepted", new),
            receipt("read", "readback", new, time=T1),
            receipt("ack", "ack_received", new, time=T2),
            receipt("remote-read", "readback", new, observer="beta", time=T1),
            receipt("report", "report", new),
        ], observations=[observation(), observation("reported", basis="reported")])
        expected = p.canonical(p.validate(data))
        expected_status = p.canonical(p.project(data, "new", "alpha"))
        events = [(table, row) for table in p.TABLES for row in data[table]]
        for seed in range(16):
            with self.subTest(seed=seed):
                db = Path(self.directory.name) / f"shuffle-{seed}.sqlite3"
                p.initialize(db)
                shuffled = copy.deepcopy(events)
                random.Random(seed).shuffle(shuffled)
                for table, row in shuffled:
                    p.import_data(db, {"schema_version": 1, table: [row]})
                self.assertEqual(p.canonical(p.read_data(db)), expected)
                self.assertEqual(p.canonical(p.project(p.read_data(db), "new", "alpha")), expected_status)

    def test_unresolved_cli_reports_without_fabricating_operation(self):
        p.import_data(self.db, dataset(operations=[], receipts=[receipt("r", "readback")]))
        source = Path(p.__file__).resolve()
        run = subprocess.run([sys.executable, str(source), "unresolved", "--db", str(self.db)],
                             text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["orphan_receipts"][0]["operation_id"], "op-1")
        self.assertEqual(p.read_data(self.db)["operations"], [])


class EdgeValidationTests(unittest.TestCase):
    def test_supersession_ids_are_bounded_valid_strings(self):
        for value in (" ", "\ud800", "x" * 4097):
            with self.subTest(value=repr(value)), self.assertRaises(p.Invalid):
                p.validate(dataset(operations=[operation(supersedes=[value])]))

    def test_invalid_timezone_offset_and_utc_overflow_are_controlled_errors(self):
        for value in ("2026-01-01T10:00:00+00:60", "2026-01-01T10:00:00+24:00", "0001-01-01T00:00:00+01:00"):
            with self.subTest(value=value), self.assertRaises(p.Invalid):
                p.stamp(value)

    def test_capability_reports_use_observation_order_not_input_order(self):
        rows = [observation("z", basis="reported", observed_at=T0),
                observation("a", basis="inferred", observed_at=T1)]
        args = dict(subject="alpha", observer="alpha", action="comment", context="manual",
                    environment="fixture:workspace", at=T2)
        first = p.capability(dataset(observations=rows), **args)
        second = p.capability(dataset(observations=list(reversed(rows))), **args)
        self.assertEqual(first, second)
        self.assertEqual(first["reports"], ["z", "a"])

    def test_unresolved_predecessors_are_explicit(self):
        data = dataset(operations=[operation("new", supersedes=["old"])])
        self.assertEqual(p.unresolved(data), {"orphan_receipts": [], "unresolved_predecessors": [
            {"operation_id": "new", "predecessor_id": "old"}],
            # mismatched_retractions: held retractions naming a receipt under another
            # operation (added with the held-retraction fix; empty here).
            "unresolved_retractions": [], "mismatched_retractions": [], "scope_mismatched_receipts": []})


if __name__ == "__main__":
    unittest.main()
