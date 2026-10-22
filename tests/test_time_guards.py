"""Walpo's v0.1 source-clock and SQL guard-definition tests. Synthetic only."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import porchlight as p
from test_porchlight import dataset, operation, receipt, T0, T1, T2


def clock(at, origin="fixture:clock", trust="authoritative"):
    return dict(source_at=at, source_origin=origin, source_trust=trust)


class SourceTimeTests(unittest.TestCase):
    def status(self, rows):
        return p.project(dataset(receipts=rows), "op-1", "alpha")

    def test_observation_order_is_only_a_soft_note(self):
        state = self.status([receipt("ack", "ack_received", time=T0), receipt("a", "accepted", time=T1)])
        self.assertTrue(state["acknowledged"])
        self.assertIn("ack_observation_order_unverified", state["notes"])
        self.assertNotIn("ack_before_acceptance", state["flags"])

    def test_comparable_source_clock_can_reject_an_early_ack(self):
        state = self.status([receipt("a", "accepted", **clock(T1)), receipt("ack", "ack_received", time=T2, **clock(T0))])
        self.assertFalse(state["acknowledged"])
        self.assertIn("ack_before_acceptance", state["flags"])

    def test_source_time_wins_over_delayed_observation(self):
        state = self.status([receipt("a", "accepted", time=T2, **clock(T0)),
                             receipt("ack", "ack_received", time=T1, **clock(T1))])
        self.assertTrue(state["acknowledged"])
        self.assertEqual(state["notes"], [])

    def test_different_clocks_cannot_produce_strong_conclusion(self):
        state = self.status([receipt("a", "accepted", **clock(T1, "fixture:clock-one")),
                             receipt("ack", "ack_received", time=T2, **clock(T0, "fixture:clock-two"))])
        self.assertTrue(state["acknowledged"])
        self.assertIn("ack_source_order_unverified", state["notes"])
        self.assertNotIn("ack_before_acceptance", state["flags"])

    def test_reported_or_untrusted_source_cannot_reject_ack(self):
        for trust in ("reported", "untrusted"):
            for side in ("acceptance", "ack"):
                with self.subTest(trust=trust, side=side):
                    state = self.status([receipt("a", "accepted", **clock(T1, trust=trust if side=="acceptance" else "authoritative")),
                                         receipt("ack", "ack_received", time=T2, **clock(T0, trust=trust if side=="ack" else "authoritative"))])
                    self.assertTrue(state["acknowledged"])
                    self.assertNotIn("ack_before_acceptance", state["flags"])

    def test_missing_source_on_one_side_does_not_block(self):
        for side in ("acceptance", "ack"):
            with self.subTest(side=side):
                state = self.status([receipt("a", "accepted", time=T1, **(clock(T1) if side=="acceptance" else {})),
                                     receipt("ack", "ack_received", time=T0, **(clock(T0) if side=="ack" else {}))])
                self.assertTrue(state["acknowledged"])
                self.assertIn("ack_observation_order_unverified", state["notes"])

    def test_equal_source_time_is_not_a_conflict(self):
        state = self.status([receipt("a", "accepted", **clock(T0)), receipt("ack", "ack_received", **clock(T0))])
        self.assertTrue(state["acknowledged"])

    def test_source_offset_equivalence(self):
        state = self.status([receipt("a", "accepted", **clock(T0)),
                             receipt("ack", "ack_received", **clock("2026-01-01T11:00:00+01:00"))])
        self.assertTrue(state["acknowledged"])

    def test_earliest_same_clock_acceptance_used_not_input_order(self):
        rows=[receipt("a1", "accepted", **clock(T0)), receipt("a2", "accepted", **clock(T2)),
              receipt("ack", "ack_received", **clock(T1))]
        self.assertTrue(self.status(rows)["acknowledged"])
        self.assertEqual(self.status(rows), self.status(rows[::-1]))

    def test_readback_time_never_becomes_creation_time(self):
        state=self.status([receipt("read", "readback", time=T2, **clock(T2)), receipt("ack", "ack_received", **clock(T0))])
        self.assertTrue(state["acknowledged"])

    def test_source_triplet_is_all_or_none(self):
        for meta in ({"source_at":T0}, {"source_origin":"fixture:x"}, {"source_trust":"authoritative"},
                     {"source_at":T0,"source_trust":"authoritative"}):
            with self.subTest(meta=meta), self.assertRaises(p.Invalid):
                self.status([receipt("a", "accepted", **meta)])

    def test_source_triplet_validation(self):
        for meta in (clock("2026-01-01T10:00:00"), clock(T0, origin=" "), clock(T0, trust="sure")):
            with self.subTest(meta=meta), self.assertRaises(p.Invalid):
                self.status([receipt("a", "accepted", **meta)])

    def test_reported_receipt_never_enters_comparable_clock_set(self):
        state=self.status([receipt("r", "report", remote_ref="fixture:comment/one", **clock(T2)),
                           receipt("read", "readback"), receipt("ack", "ack_received", **clock(T0))])
        self.assertTrue(state["acknowledged"])
        self.assertEqual(state["reports"], ["r"])


class GuardDefinitionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.db=Path(self.directory.name)/"journal.sqlite3"
        p.initialize(self.db)
        p.import_data(self.db, dataset())

    def tearDown(self):
        self.directory.cleanup()

    def forge(self, name):
        verb={"no_replace":"INSERT", "no_updates":"UPDATE", "no_deletes":"DELETE"}[name]
        with sqlite3.connect(self.db) as con:
            con.execute(f"DROP TRIGGER {name}")
            con.execute(f"CREATE TRIGGER {name} BEFORE {verb} ON records BEGIN SELECT 1; END")

    def test_each_noop_guard_with_right_name_is_rejected(self):
        for name in p.GUARDS:
            with self.subTest(name=name):
                self.forge(name)
                with p.journal(self.db) as con:
                    self.assertIn(name, p.journal_guards(con)["mismatched"])
                before=self.db.read_bytes()
                with self.assertRaisesRegex(p.Invalid, "export and import"):
                    p.import_data(self.db,dataset(operations=[operation("next")]))
                self.assertEqual(before,self.db.read_bytes())
                self.assertEqual(p.read_data(self.db)["operations"], [operation()])

    def test_full_export_recovery_from_changed_guard(self):
        self.forge("no_replace")
        original=self.db.read_bytes()
        data=p.read_data(self.db)
        other=Path(self.directory.name)/"new.sqlite3"
        p.initialize(other)
        p.import_data(other,data)
        self.assertEqual(p.read_data(other),data)
        self.assertEqual(self.db.read_bytes(),original)
        with p.journal(other) as con:
            self.assertEqual(p.journal_guards(con)["mismatched"],[])

    def test_preflight_rechecked_under_transaction_lock(self):
        real_journal=p.journal
        @contextmanager
        def changed_after_preflight(path, *, write=False):
            with real_journal(path,write=write) as con:
                if write:
                    con.execute("DROP TRIGGER no_replace")
                    con.execute("CREATE TRIGGER no_replace BEFORE INSERT ON records BEGIN SELECT 1; END")
                yield con
        with patch.object(p,"journal",changed_after_preflight), self.assertRaises(p.Invalid):
            p.import_data(self.db,dataset(operations=[operation("next")]))
        self.assertEqual(p.read_data(self.db)["operations"],[operation()])

    def test_definitions_are_taken_from_actual_schema_source(self):
        with p.journal(self.db) as con:
            self.assertEqual(p.journal_guards(con), {"present": list(p.GUARDS), "missing": [], "mismatched": []})
        self.assertEqual(set(p.GUARD_DEFINITIONS), set(p.GUARDS))


if __name__=="__main__":
    unittest.main()
