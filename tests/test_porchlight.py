"""Synthetic cases co-designed with Flint; no production accounts or records."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

import porchlight as p

ROOT = Path(__file__).resolve().parents[1]
T0 = "2026-01-01T10:00:00Z"
T1 = "2026-01-01T10:01:00Z"
T2 = "2026-01-01T10:02:00Z"


def operation(oid="op-1", **kwargs):
    return {"id": oid, "author": "alpha", "recipient": "beta", "action": "comment",
            "context": "manual", "destination": "fixture:page/comments", "payload": "A small light.", **kwargs}


def receipt(rid, kind, op=None, observer="alpha", time=T0, **kwargs):
    op = op or operation()
    data = {"id": rid, "operation_id": op["id"], "observer": observer, "kind": kind,
            "observed_at": time, "recorded_at": time, "evidence_ref": "fixture:evidence/" + rid}
    if kind in {"accepted", "blocked", "timeout"}:
        data["attempt_id"] = "attempt-1"
    if kind in {"accepted", "readback", "ack_received"}:
        data.update(remote_ref="fixture:comment/one", content_sha256=p.digest(op["payload"]),
                    observed_destination=op["destination"])
    if kind == "ack_received":
        data["acknowledged_by"] = "beta"
    return {**data, **kwargs}


def observation(oid="cap-1", **kwargs):
    return {"id": oid, "subject": "alpha", "observer": "alpha", "action": "comment", "context": "manual",
            "environment": "fixture:workspace", "outcome": "worked", "basis": "direct",
            "observed_at": T0, "recorded_at": T0, "recheck_after": T2, "evidence_ref": "fixture:capability", **kwargs}


def dataset(operations=None, receipts=None, observations=None):
    return {"schema_version": 1, "operations": [operation()] if operations is None else operations,
            "receipts": receipts or [], "observations": observations or []}


class ProjectionTests(unittest.TestCase):
    def status(self, rows, observer="alpha", operations=None, oid="op-1"):
        return p.project(dataset(operations, rows), oid, observer)

    def test_saved_intention_is_not_publication(self):
        state = self.status([])
        self.assertFalse(state["accepted"])
        self.assertFalse(state["readback_match"])
        self.assertIsNone(state["visibility_as_of"])
        self.assertFalse(state["automatic_retry"])
        self.assertIsNone(state["permission_to_act"])

    def test_f1_absence_is_not_loss_or_denial(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback"), receipt("n", "not_found", observer="beta", time=T1)]
        state = self.status(rows, "beta")
        self.assertEqual(state["visibility"], "uncertain")
        self.assertFalse(state["ever_blocked"])
        self.assertFalse(state["accepted"])
        rows.append(receipt("full", "readback", observer="beta", time=T2))
        self.assertEqual(self.status(rows, "beta")["visibility"], "matching")

    def test_f2a_truncated_payload(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback", content_sha256=p.digest("A small"))]
        state = self.status(rows)
        self.assertTrue(state["accepted"])
        self.assertFalse(state["readback_match"])
        self.assertIn("content_mismatch", state["flags"])

    def test_f2b_wrong_destination(self):
        state = self.status([receipt("r", "readback", observed_destination="fixture:other-discussion")])
        self.assertFalse(state["readback_match"])
        self.assertIn("destination_mismatch", state["flags"])

    def test_f2c_body_signature_is_not_event_time(self):
        op = operation(payload="Written at 11:35, says the body.")
        row = receipt("r", "readback", op, time=T0)
        state = self.status([row], operations=[op])
        self.assertEqual(state["visibility_as_of"], T0)
        self.assertTrue(state["readback_match"])

    def test_f3_verified_then_changed_is_observer_scoped(self):
        rows = [receipt("a", "readback"), receipt("b", "readback", observer="beta"),
                receipt("c", "readback", observer="beta", time=T1, content_sha256=p.digest("Changed"))]
        self.assertEqual(self.status(rows)["visibility"], "matching")
        other = self.status(rows, "beta")
        self.assertEqual(other["visibility"], "mismatch")
        self.assertTrue(other["readback_match"])
        self.assertEqual(other["readback_receipts"], ["b"])

    def test_f4_ack_for_wrong_version(self):
        old, new = operation(), operation("op-2", payload="New light.", supersedes=["op-1"])
        rows = [receipt("a", "accepted", new), receipt("ack", "ack_received", new, content_sha256=p.digest(old["payload"]))]
        state = self.status(rows, operations=[old, new], oid="op-2")
        self.assertFalse(state["acknowledged"])
        self.assertIn("ack_payload_or_destination_mismatch", state["flags"])

    def test_f5_hearsay_cannot_promote_direct_state(self):
        state = self.status([receipt("report-yes", "report"), receipt("report-no", "report", time=T1)])
        self.assertFalse(state["accepted"])
        self.assertFalse(state["readback_match"])
        self.assertFalse(state["ever_blocked"])
        self.assertEqual(len(state["reports"]), 2)

    def test_f6_same_text_different_remote_object(self):
        state = self.status([receipt("r", "readback"), receipt("a", "ack_received", remote_ref="fixture:comment/copy")])
        self.assertFalse(state["acknowledged"])
        self.assertIn("remote_identity_conflict", state["flags"])

    def test_f6_parent_is_not_an_object_alias(self):
        state = self.status([receipt("r", "readback"), receipt("a", "ack_received", remote_ref="fixture:discussion/parent")])
        self.assertFalse(state["acknowledged"])

    def test_valid_ack_is_not_recipient_direct_read(self):
        rows = [receipt("r", "readback"), receipt("a", "ack_received")]
        self.assertTrue(self.status(rows)["acknowledged"])
        self.assertEqual(self.status(rows, "beta")["visibility"], "uncertain")
        self.assertFalse(self.status(rows, "beta")["readback_match"])

    def test_ack_without_anchor_stays_unbound(self):
        state = self.status([receipt("a", "ack_received")])
        self.assertFalse(state["acknowledged"])
        self.assertIn("unbound_acknowledgement", state["flags"])

    def test_wrong_acknowledger(self):
        state = self.status([receipt("r", "readback"), receipt("a", "ack_received", acknowledged_by="gamma")])
        self.assertFalse(state["acknowledged"])
        self.assertIn("wrong_acknowledger", state["flags"])

    def test_acceptance_alone_is_not_readback(self):
        state = self.status([receipt("a", "accepted")])
        self.assertTrue(state["accepted"])
        self.assertFalse(state["readback_match"])
        self.assertFalse(state["acknowledged"])

    def test_late_receipt_recovers_timeout_without_resend(self):
        rows = [receipt("t", "timeout"), receipt("a", "accepted", time=T1), receipt("r", "readback", time=T2)]
        state = self.status(rows)
        self.assertTrue(state["accepted"])
        self.assertTrue(state["readback_match"])
        self.assertFalse(state["automatic_retry"])

    def test_incomplete_readback_does_not_verify(self):
        row = receipt("r", "readback")
        del row["content_sha256"]
        state = self.status([row])
        self.assertEqual(state["visibility"], "uncertain")
        self.assertFalse(state["readback_match"])
        self.assertIn("incomplete_readback", state["flags"])

    def test_later_absence_keeps_history_but_not_current_match(self):
        state = self.status([receipt("r", "readback"), receipt("n", "not_found", time=T1)])
        self.assertTrue(state["readback_match"])
        self.assertEqual(state["visibility"], "uncertain")

    def test_observation_time_not_import_or_recording_time(self):
        rows = [receipt("late-old", "not_found", time=T0, recorded_at=T2), receipt("new", "readback", time=T1)]
        self.assertEqual(self.status(rows)["visibility"], "matching")
        self.assertEqual(self.status(rows), self.status(list(reversed(rows))))

    def test_equal_time_conflict_not_arbitrary_tiebreak(self):
        state = self.status([receipt("a", "not_found"), receipt("b", "readback")])
        self.assertEqual(state["visibility"], "uncertain")
        self.assertIn("observation_time_conflict", state["flags"])

    def test_different_observers_dont_leak(self):
        state = self.status([receipt("r", "readback", observer="beta")])
        self.assertFalse(state["readback_match"])

    def test_different_attempts_can_have_different_outcomes(self):
        state = self.status([receipt("b", "blocked"), receipt("a", "accepted", time=T1, attempt_id="attempt-2")])
        self.assertTrue(state["accepted"])
        self.assertTrue(state["ever_blocked"])
        self.assertNotIn("contradictory_attempt_evidence", state["flags"])

    def test_same_attempt_inconsistent_outcomes_are_flagged(self):
        state = self.status([receipt("b", "blocked"), receipt("a", "accepted", time=T1)])
        self.assertIn("contradictory_attempt_evidence", state["flags"])

    def test_exact_utf8_hash_no_whitespace_normalisation(self):
        self.assertNotEqual(p.digest("hello"), p.digest("hello\n"))
        self.assertNotEqual(p.digest("é"), p.digest("e\u0301"))

    def test_supersession_beats_arrival_order(self):
        old, new = operation(), operation("new", supersedes=["op-1"])
        state = self.status([], operations=[new, old])
        self.assertEqual(state["superseded_by"], ["new"])
        self.assertEqual(state["current_operation_ids"], ["new"])

    def test_forks_are_not_last_writer_wins(self):
        ops = [operation(), operation("left", supersedes=["op-1"]), operation("right", supersedes=["op-1"])]
        state = self.status([], operations=ops)
        self.assertEqual(state["current_operation_ids"], ["left", "right"])
        self.assertIn("multiple_current_operations", state["flags"])

    def test_independent_messages_not_mislabelled_forks(self):
        state = self.status([], operations=[operation(), operation("independent")])
        self.assertNotIn("multiple_current_operations", state["flags"])
        self.assertEqual(state["current_operation_ids"], ["op-1"])

    def test_dangling_predecessor_is_visible(self):
        new = operation("new", supersedes=["missing"])
        state = self.status([], operations=[new], oid="new")
        self.assertEqual(state["unresolved_predecessors"], ["missing"])


class CapabilityTests(unittest.TestCase):
    def query(self, rows, **kwargs):
        args = dict(subject="alpha", observer="alpha", action="comment", context="manual",
                    environment="fixture:workspace", at=T1)
        return p.capability(dataset(observations=rows), **{**args, **kwargs})

    def test_manual_is_not_scheduled(self):
        state = self.query([observation()], context="scheduled")
        self.assertEqual(state["last_observed_outcome"], "unknown")
        self.assertIsNone(state["permission_to_act"])

    def test_environment_and_observer_are_exact(self):
        for field in ("observer", "environment", "action", "subject"):
            with self.subTest(field=field):
                self.assertEqual(self.query([observation()], **{field: "different"})["last_observed_outcome"], "unknown")

    def test_expiry_does_not_erase_history(self):
        state = self.query([observation()], at=T2)
        self.assertTrue(state["needs_recheck"])
        self.assertEqual(state["last_observed_outcome"], "worked")
        self.assertEqual(state["observation_ids"], ["cap-1"])

    def test_fresh_evidence_is_not_permission(self):
        state = self.query([observation()])
        self.assertFalse(state["needs_recheck"])
        self.assertIsNone(state["permission_to_act"])

    def test_reported_outcome_never_promotes_direct(self):
        state = self.query([observation(basis="reported")])
        self.assertEqual(state["last_observed_outcome"], "unknown")
        self.assertEqual(state["reports"], ["cap-1"])

    def test_conflicting_equal_time_outcomes(self):
        state = self.query([observation(), observation("b", outcome="blocked")])
        self.assertTrue(state["conflicting_observations"])
        self.assertEqual(state["last_observed_outcome"], "unknown")

    def test_future_record_not_known_yet(self):
        self.assertEqual(self.query([observation(recorded_at=T2)])["observation_ids"], [])


class ValidationTests(unittest.TestCase):
    def test_duplicate_identical_records_deduplicated(self):
        row = receipt("r", "readback")
        self.assertEqual(len(p.validate(dataset(receipts=[row, dict(row)]))["receipts"]), 1)

    def test_conflicting_id_rejected(self):
        a, b = receipt("r", "readback"), receipt("r", "not_found")
        with self.assertRaises(p.Invalid):
            p.validate(dataset(receipts=[a, b]))

    def test_malformed_records(self):
        variants = [dataset(receipts=[receipt("r", "invented")]), dataset(receipts=[receipt("r", "readback", content_sha256="fake")]),
                    dataset(receipts=[receipt("r", "readback", observed_at="2026-01-01")]),
                    {"schema_version": True}, {"schema_version": 1, "surprise": []}, dataset(operations=[operation(payload=42)]),
                    dataset(observations=[observation(recheck_after="2025-01-01T00:00:00Z")])]
        for value in variants:
            with self.subTest(value=value), self.assertRaises(p.Invalid):
                p.validate(value)

    def test_invalid_unicode_rejected(self):
        with self.assertRaises(p.Invalid):
            p.validate(dataset(operations=[operation(payload="\ud800")]))

    def test_cycles_and_scope_crossing(self):
        for ops in ([operation(supersedes=["op-1"])],
                    [operation(supersedes=["b"]), operation("b", supersedes=["op-1"])],
                    [operation(), operation("b", context="scheduled", supersedes=["op-1"])]):
            with self.subTest(ops=ops), self.assertRaises(p.Invalid):
                p.validate(dataset(operations=ops))

    def test_timezone_equivalence(self):
        self.assertEqual(p.stamp(T0), p.stamp("2026-01-01T11:00:00+01:00"))


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.db = self.root / "journal.sqlite3"
        p.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def test_init_never_overwrites(self):
        before = self.db.read_bytes()
        with self.assertRaises(FileExistsError):
            p.initialize(self.db)
        self.assertEqual(self.db.read_bytes(), before)

    def test_read_never_creates_a_database(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(sqlite3.OperationalError):
            p.read_data(missing)
        self.assertFalse(missing.exists())

    def test_journal_reopen_and_idempotent_import(self):
        data = dataset(receipts=[receipt("r", "readback")])
        self.assertEqual(p.import_data(self.db, data)["inserted"], 2)
        self.assertEqual(p.import_data(self.db, data)["inserted"], 0)
        self.assertTrue(p.project(p.read_data(self.db), "op-1", "alpha")["readback_match"])

    def test_partial_import_conflict_rolls_back(self):
        p.import_data(self.db, dataset())
        before = p.read_data(self.db)
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset(operations=[operation("fresh"), operation(payload="conflict")]))
        self.assertEqual(p.read_data(self.db), before)

    def test_unexpected_trigger_blocks_import_before_writing(self):
        with p.journal(self.db, write=True) as con:
            con.execute("CREATE TRIGGER injected BEFORE INSERT ON records WHEN NEW.kind='receipts' BEGIN SELECT RAISE(ABORT,'test fault'); END")
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset(receipts=[receipt("r", "readback")]))
        self.assertEqual(p.read_data(self.db)["operations"], [])

    def test_process_dies_before_commit(self):
        script = "import sqlite3,os; c=sqlite3.connect(__import__('sys').argv[1]); c.execute('BEGIN IMMEDIATE'); c.execute(\"INSERT INTO records VALUES ('operations','unsaved','{}','test')\"); os._exit(0)"
        subprocess.run([sys.executable, "-c", script, str(self.db)], check=True)
        self.assertEqual(p.read_data(self.db)["operations"], [])

    def test_duplicate_concurrent_imports(self):
        data = dataset(receipts=[receipt("r", "readback")])
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: p.import_data(self.db, data), range(2)))
        self.assertEqual(sum(r["inserted"] for r in results), 2)
        self.assertEqual(len(p.read_data(self.db)["receipts"]), 1)

    def test_late_predecessor_cannot_revive_old_version(self):
        p.import_data(self.db, dataset(operations=[operation("new", supersedes=["op-1"])]))
        p.import_data(self.db, dataset())
        state = p.project(p.read_data(self.db), "op-1", "alpha")
        self.assertEqual(state["superseded_by"], ["new"])

    def test_late_cross_scope_predecessor_rejected_atomically(self):
        p.import_data(self.db, dataset(operations=[operation("new", supersedes=["op-1"])]))
        with self.assertRaises(p.Invalid):
            p.import_data(self.db, dataset(operations=[operation(context="scheduled")]))
        self.assertEqual(len(p.read_data(self.db)["operations"]), 1)

    def test_update_delete_triggers(self):
        p.import_data(self.db, dataset())
        with p.journal(self.db, write=True) as con:
            for sql in ("UPDATE records SET body='{}'", "DELETE FROM records"):
                with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError):
                    con.execute(sql)

    def test_wrong_database_and_future_schema(self):
        other = self.root / "other.sqlite3"
        sqlite3.connect(other).close()
        with self.assertRaises(p.Invalid):
            p.read_data(other)
        with sqlite3.connect(self.db) as con:
            con.execute("PRAGMA user_version=99")
        with self.assertRaises(p.Invalid):
            p.read_data(self.db)

    def test_strict_json_duplicate_keys_and_constants(self):
        for text in ('{"schema_version":1,"schema_version":1}', '{"schema_version":NaN}', '[1,2]', '{bad}'):
            path = self.root / "bad.json"
            path.write_text(text)
            with self.subTest(text=text), self.assertRaises(p.Invalid):
                p.load_json(path)

    def test_cli_smoke_and_nonzero_errors(self):
        source = self.root / "example.json"
        source.write_text(json.dumps(dataset(receipts=[receipt("r", "readback")])))
        def cli(*args):
            return subprocess.run([sys.executable, str(ROOT / "porchlight.py"), *args], capture_output=True, text=True)
        run = cli("import", "--db", str(self.db), str(source))
        self.assertEqual(run.returncode, 0, run.stderr)
        run = cli("status", "--db", str(self.db), "op-1", "--observer", "alpha")
        self.assertTrue(json.loads(run.stdout)["readback_match"])
        run = cli("check", "--db", str(self.db))
        self.assertEqual(json.loads(run.stdout)["integrity"], "ok")
        run = cli("status", "--db", str(self.db), "missing", "--observer", "alpha")
        self.assertEqual(run.returncode, 2)


if __name__ == "__main__":
    unittest.main()
