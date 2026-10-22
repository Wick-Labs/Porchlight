"""Flint's round-2 drafts: receipt retraction and orphan scope. Synthetic values only."""
import copy
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest

import porchlight as p
from test_porchlight import dataset, operation, receipt, T0, T1, T2


def retract(rid, target, observer="alpha", time=T1, reason="fixture: recorded against the wrong object", **kwargs):
    row = receipt(rid, "retract", observer=observer, time=time, retracts=target, reason=reason)
    return {**row, **kwargs}


SCOPE = {"expected_action": "comment", "expected_context": "manual", "expected_destination": "fixture:page/comments"}


def hashless(rid, kind, **kwargs):
    row = receipt(rid, kind, **kwargs)
    for key in ("content_sha256", "observed_destination"):
        row.pop(key, None)
    return row


class RetractionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "journal.sqlite3"
        p.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def status(self, rows, observer="alpha", operations=None):
        return p.project(dataset(operations, rows), "op-1", observer)

    def test_own_retraction_stops_projection_but_keeps_journal_record(self):
        rows = [receipt("r", "readback"), retract("x", "r")]
        p.import_data(self.db, dataset(receipts=rows))
        data = p.read_data(self.db)
        self.assertEqual({r["id"] for r in data["receipts"]}, {"r", "x"})
        state = p.project(data, "op-1", "alpha")
        self.assertFalse(state["readback_match"])
        self.assertEqual(state["visibility"], "uncertain")
        self.assertEqual(state["visibility_evidence"], [])
        self.assertEqual(state["retracted_receipts"], ["r"])

    def test_retracted_acknowledgement_no_longer_binds(self):
        rows = [receipt("a", "accepted"), receipt("k", "ack_received", time=T1), retract("x", "k", time=T2)]
        state = self.status(rows)
        self.assertTrue(state["accepted"])
        self.assertFalse(state["acknowledged"])
        self.assertEqual(state["ack_receipts"], [])

    def test_retracting_the_anchor_unbinds_the_ack(self):
        rows = [receipt("a", "accepted"), receipt("k", "ack_received", time=T1), retract("x", "a", time=T2)]
        state = self.status(rows)
        self.assertFalse(state["accepted"])
        self.assertFalse(state["acknowledged"])
        self.assertIn("unbound_acknowledgement", state["flags"])

    def test_retracting_a_conflicting_readback_clears_the_conflict(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback", remote_ref="fixture:comment/two"),
                retract("x", "r")]
        state = self.status(rows)
        self.assertNotIn("remote_identity_conflict", state["flags"])

    def test_own_retraction_of_a_report_removes_it(self):
        self.assertEqual(self.status([receipt("s", "report"), retract("x", "s")])["reports"], [])

    def test_other_observers_retraction_is_a_labelled_report_only(self):
        rows = [receipt("r", "readback"), retract("x", "r", observer="beta")]
        state = self.status(rows)
        self.assertTrue(state["readback_match"])
        self.assertEqual(state["visibility"], "matching")
        self.assertEqual(state["retracted_receipts"], [])
        self.assertEqual(state["retraction_reports"], ["x"])
        self.assertFalse(self.status(rows, observer="beta")["readback_match"])

    def test_duplicate_retractions_of_one_receipt_are_harmless(self):
        state = self.status([receipt("r", "readback"), retract("x1", "r"), retract("x2", "r")])
        self.assertFalse(state["readback_match"])
        self.assertEqual(state["retracted_receipts"], ["r"])

    def test_retracting_a_retraction_is_inert_in_either_arrival_order(self):
        # Revised with the late-target fix: no resurrection and no poisoned imports.
        for observer in ("alpha", "beta"):
            for reverse in (False, True):
                with self.subTest(observer=observer, reverse=reverse):
                    db = Path(self.directory.name) / f"late-{observer}-{reverse}.sqlite3"
                    p.initialize(db)
                    rows = [receipt("r", "readback"), retract("x", "r"),
                            retract("y", "x", observer=observer, time=T2)]
                    p.import_data(db, dataset())
                    for row in reversed(rows) if reverse else rows:
                        p.import_data(db, dataset(operations=[], receipts=[row]))
                    data = p.read_data(db)
                    self.assertEqual({r["id"] for r in data["receipts"]}, {"r", "x", "y"})
                    self.assertEqual(p.project(data, "op-1", "alpha")["retracted_receipts"], ["r"])
                    self.assertEqual(p.unresolved(data)["invalid_retractions"], [
                        {"receipt_id": "y", "retracts": "x", "observer": observer,
                         "reasons": ["target_is_retraction"]}])

    def test_unknown_target_is_held_then_applies_when_target_arrives(self):
        p.import_data(self.db, dataset(receipts=[retract("x", "late")]))
        data = p.read_data(self.db)
        self.assertEqual(p.unresolved(data)["unresolved_retractions"], [
            {"receipt_id": "x", "retracts": "late", "observer": "alpha"}])
        self.assertEqual(p.project(data, "op-1", "alpha")["retracted_receipts"], [])
        p.import_data(self.db, dataset(receipts=[receipt("late", "readback")]))
        data = p.read_data(self.db)
        self.assertEqual(p.unresolved(data)["unresolved_retractions"], [])
        state = p.project(data, "op-1", "alpha")
        self.assertFalse(state["readback_match"])
        self.assertEqual(state["retracted_receipts"], ["late"])

    def test_retraction_before_its_operation_is_an_orphan_too(self):
        p.import_data(self.db, dataset(operations=[], receipts=[retract("x", "r")]))
        self.assertEqual([r["receipt_id"] for r in p.unresolved(p.read_data(self.db))["orphan_receipts"]], ["x"])

    def test_intrinsically_invalid_retractions_are_rejected(self):
        cases = {
            "self": [retract("x", "x")],
            "no reason": [{k: v for k, v in retract("x", "r").items() if k != "reason"}],
            "blank reason": [retract("x", "r", reason=" ")],
            "no target": [{k: v for k, v in retract("x", "r").items() if k != "retracts"}],
            "evidence field": [retract("x", "r", remote_ref="fixture:comment/one")],
            "expected scope": [retract("x", "r", **SCOPE)],
            "retracts on readback": [receipt("r", "readback", retracts="q")],
            "reason on report": [receipt("s", "report", reason="fixture")],
        }
        for name, rows in cases.items():
            with self.subTest(name), self.assertRaises(p.Invalid):
                p.validate(dataset(operations=[operation(), operation("op-2")], receipts=rows))

    def test_cross_operation_target_arriving_later_is_not_blocked(self):
        p.import_data(self.db, dataset(operations=[operation(), operation("op-2")], receipts=[retract("x", "r")]))
        p.import_data(self.db, dataset(receipts=[receipt("r", "readback", operation("op-2"))]))
        data = p.read_data(self.db)
        self.assertTrue(p.project(data, "op-2", "alpha")["readback_match"])
        self.assertEqual(p.project(data, "op-2", "alpha")["retracted_receipts"], [])
        self.assertEqual(p.unresolved(data)["invalid_retractions"], [
            {"receipt_id": "x", "retracts": "r", "observer": "alpha", "reasons": ["operation_mismatch"]}])

    def test_seeded_single_record_import_permutations_are_identical(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback", time=T1), receipt("k", "ack_received", time=T2),
                receipt("s", "report"), retract("x", "k", time=T2), retract("x2", "k", time=T2),
                retract("w", "r", observer="beta"), retract("q", "missing"),
                receipt("b", "readback", observer="beta"), retract("v", "b", observer="beta")]
        data = dataset(receipts=rows)
        expected = {o: p.canonical(p.project(data, "op-1", o)) for o in ("alpha", "beta")}
        expected_unresolved = p.canonical(p.unresolved(data))
        events = [(table, row) for table in p.TABLES for row in data[table]]
        for seed in range(24):
            with self.subTest(seed=seed):
                db = Path(self.directory.name) / f"retract-{seed}.sqlite3"
                p.initialize(db)
                shuffled = copy.deepcopy(events)
                random.Random(seed).shuffle(shuffled)
                for table, row in shuffled:
                    p.import_data(db, {"schema_version": 1, table: [row]})
                stored = p.read_data(db)
                for o in ("alpha", "beta"):
                    self.assertEqual(p.canonical(p.project(stored, "op-1", o)), expected[o])
                self.assertEqual(p.canonical(p.unresolved(stored)), expected_unresolved)
        state = p.project(data, "op-1", "alpha")
        self.assertFalse(state["acknowledged"])
        self.assertEqual(state["retracted_receipts"], ["k"])
        self.assertEqual(state["retraction_reports"], ["w"])

    def test_status_cli_shows_retraction(self):
        p.import_data(self.db, dataset(receipts=[receipt("r", "readback"), retract("x", "r")]))
        source = Path(p.__file__).resolve()
        command = [sys.executable, str(source), "status", "op-1", "--observer", "alpha", "--db", str(self.db)]
        run = subprocess.run(command, text=True, capture_output=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)["retracted_receipts"], ["r"])


class OrphanScopeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "journal.sqlite3"
        p.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def test_hashless_orphan_does_not_bind_to_an_operation_at_another_destination(self):
        early = [hashless("a", "accepted", **SCOPE), hashless("k", "ack_received", time=T1, **SCOPE)]
        p.import_data(self.db, dataset(operations=[], receipts=early))
        p.import_data(self.db, dataset(operations=[operation(destination="fixture:other/comments")]))
        data = p.read_data(self.db)
        state = p.project(data, "op-1", "alpha")
        self.assertFalse(state["accepted"])
        self.assertFalse(state["acknowledged"])
        self.assertEqual([f for f in state["flags"] if f.startswith("orphan_")], ["orphan_destination_mismatch"])
        self.assertEqual(state["excluded_receipts"], ["a", "k"])
        self.assertEqual(p.unresolved(data)["scope_mismatched_receipts"], [
            {"receipt_id": "a", "operation_id": "op-1", "observer": "alpha"},
            {"receipt_id": "k", "operation_id": "op-1", "observer": "alpha"}])
        self.assertEqual(p.unresolved(data)["orphan_receipts"], [])

    def test_same_destination_in_another_context_does_not_bind(self):
        # Walpo's case: one destination used by both a manual and a scheduled run.
        rows = [hashless("a", "accepted", **SCOPE), hashless("k", "ack_received", time=T1, **SCOPE)]
        state = p.project(dataset(operations=[operation(context="scheduled")], receipts=rows), "op-1", "alpha")
        self.assertFalse(state["acknowledged"])
        self.assertIn("orphan_context_mismatch", state["flags"])
        self.assertNotIn("orphan_destination_mismatch", state["flags"])

    def test_other_action_does_not_bind(self):
        rows = [hashless("a", "accepted", **SCOPE)]
        state = p.project(dataset(operations=[operation(action="reply")], receipts=rows), "op-1", "alpha")
        self.assertFalse(state["accepted"])
        self.assertIn("orphan_action_mismatch", state["flags"])

    def test_matching_expected_scope_binds_as_before_and_is_not_unscoped(self):
        rows = [hashless("a", "accepted", **SCOPE), receipt("k", "ack_received", time=T1, **SCOPE)]
        state = p.project(dataset(receipts=rows), "op-1", "alpha")
        self.assertTrue(state["acknowledged"])
        self.assertFalse([f for f in state["flags"] if f.startswith("orphan_")])
        self.assertEqual(state["excluded_receipts"], [])
        self.assertEqual(state["unscoped_receipts"], [])

    def test_legacy_hashless_receipt_is_labelled_unscoped_not_rewritten(self):
        rows = [hashless("a", "accepted"), receipt("r", "readback"), receipt("t", "timeout", attempt_id="attempt-2"),
                receipt("s", "report")]
        p.import_data(self.db, dataset(receipts=rows))
        data = p.read_data(self.db)
        state = p.project(data, "op-1", "alpha")
        self.assertTrue(state["accepted"])
        self.assertEqual(state["unscoped_receipts"], ["a", "t"])
        self.assertEqual(data["receipts"], sorted(rows, key=lambda r: r["id"]))

    def test_partial_expected_scope_is_rejected(self):
        for missing in SCOPE:
            partial = {k: v for k, v in SCOPE.items() if k != missing}
            with self.subTest(missing=missing), self.assertRaises(p.Invalid):
                p.validate(dataset(receipts=[hashless("a", "accepted", **partial)]))

    def test_out_of_scope_receipt_cannot_erase_separate_valid_evidence(self):
        stray = hashless("stray", "accepted", attempt_id="attempt-2", time=T2,
                         **{**SCOPE, "expected_destination": "fixture:else"})
        rows = [receipt("a", "accepted"), receipt("k", "ack_received", time=T1), stray]
        state = p.project(dataset(receipts=rows), "op-1", "alpha")
        self.assertTrue(state["acknowledged"])
        self.assertEqual(state["latest_attempt_result"], "accepted")
        self.assertIn("orphan_destination_mismatch", state["flags"])

    def test_out_of_scope_report_is_not_listed_as_testimony_for_this_operation(self):
        rows = [receipt("s", "report", **{**SCOPE, "expected_context": "scheduled"})]
        self.assertEqual(p.project(dataset(receipts=rows), "op-1", "alpha")["reports"], [])

    def test_expected_scope_values_are_bounded_strings(self):
        for value in ("", " ", "x" * 4097, 7):
            with self.subTest(value=repr(value)), self.assertRaises(p.Invalid):
                p.validate(dataset(receipts=[hashless("a", "accepted", **{**SCOPE, "expected_action": value})]))

    def test_seeded_import_permutations_are_identical(self):
        op = operation(destination="fixture:other/comments")
        rows = [hashless("a", "accepted", **SCOPE), hashless("k", "ack_received", time=T1, **SCOPE),
                hashless("ok", "accepted", attempt_id="attempt-2",
                         **{**SCOPE, "expected_destination": op["destination"]}),
                hashless("legacy", "accepted", attempt_id="attempt-3", time=T1), retract("x", "a", time=T2)]
        data = dataset(operations=[op], receipts=rows)
        expected = p.canonical(p.project(data, "op-1", "alpha"))
        expected_unresolved = p.canonical(p.unresolved(data))
        events = [(table, row) for table in p.TABLES for row in data[table]]
        for seed in range(16):
            with self.subTest(seed=seed):
                db = Path(self.directory.name) / f"scope-{seed}.sqlite3"
                p.initialize(db)
                shuffled = copy.deepcopy(events)
                random.Random(seed).shuffle(shuffled)
                for table, row in shuffled:
                    p.import_data(db, {"schema_version": 1, table: [row]})
                stored = p.read_data(db)
                self.assertEqual(p.canonical(p.project(stored, "op-1", "alpha")), expected)
                self.assertEqual(p.canonical(p.unresolved(stored)), expected_unresolved)
        state = p.project(data, "op-1", "alpha")
        self.assertTrue(state["accepted"])
        self.assertEqual(state["excluded_receipts"], ["a", "k"])
        self.assertEqual(state["retracted_receipts"], ["a"])
        self.assertEqual(state["unscoped_receipts"], ["legacy"])


if __name__ == "__main__":
    unittest.main()
