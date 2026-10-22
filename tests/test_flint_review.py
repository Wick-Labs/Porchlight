"""Flint's v2 review tests, relocated unchanged from his submitted patch."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import porchlight as p
from test_porchlight import dataset, operation, receipt, T0, T1, T2


class FlintReviewTests(unittest.TestCase):
    """Counterexamples from Flint's independent review of e3feb11. Synthetic values only."""

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.db = Path(self.directory.name) / "journal.sqlite3"
        p.initialize(self.db)

    def tearDown(self):
        self.directory.cleanup()

    def status(self, rows):
        return p.project(dataset(receipts=rows), "op-1", "alpha")

    def test_accept_with_other_content_cannot_anchor_an_ack(self):
        rows = [receipt("a", "accepted", content_sha256=p.digest("Other words.")), receipt("k", "ack_received", time=T1)]
        state = self.status(rows)
        self.assertFalse(state["acknowledged"])
        self.assertIn("accepted_content_mismatch", state["flags"])

    def test_accept_at_other_destination_cannot_anchor_an_ack(self):
        rows = [receipt("a", "accepted", observed_destination="fixture:elsewhere"), receipt("k", "ack_received", time=T1)]
        state = self.status(rows)
        self.assertFalse(state["acknowledged"])
        self.assertIn("accepted_destination_mismatch", state["flags"])

    def test_accept_without_hash_still_anchors(self):
        accepted = receipt("a", "accepted")
        del accepted["content_sha256"], accepted["observed_destination"]
        self.assertTrue(self.status([accepted, receipt("k", "ack_received", time=T1)])["acknowledged"])

    def test_ack_before_acceptance_is_flagged_and_not_bound(self):
        state = self.status([receipt("k", "ack_received", time=T0), receipt("a", "accepted", time=T1)])
        self.assertFalse(state["acknowledged"])
        self.assertIn("ack_before_acceptance", state["flags"])

    def test_later_ack_still_binds_after_an_early_one(self):
        rows = [receipt("k0", "ack_received", time=T0), receipt("a", "accepted", time=T1), receipt("k1", "ack_received", time=T2)]
        state = self.status(rows)
        self.assertTrue(state["acknowledged"])
        self.assertEqual(state["ack_receipts"], ["k1"])
        self.assertIn("ack_before_acceptance", state["flags"])

    def test_ack_before_later_readback_without_acceptance_binds(self):
        # Walpo's case: a read-back time is not object creation time.
        state = self.status([receipt("k", "ack_received", time=T0), receipt("r", "readback", time=T1)])
        self.assertTrue(state["acknowledged"])
        self.assertNotIn("ack_before_acceptance", state["flags"])

    def test_late_acceptance_resolves_earlier_timeout_of_same_attempt(self):
        # The service accepted at T0; the caller timed out at T1; the receipt was recovered at T2.
        state = self.status([receipt("t", "timeout", time=T1), receipt("a", "accepted", time=T0, recorded_at=T2)])
        self.assertTrue(state["accepted"])
        self.assertEqual(state["latest_attempt_result"], "accepted")

    def test_stray_ack_does_not_unverify_own_readback(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback"),
                receipt("k", "ack_received", time=T1, remote_ref="fixture:comment/copy")]
        state = self.status(rows)
        self.assertFalse(state["acknowledged"])
        self.assertIn("remote_identity_conflict", state["flags"])
        self.assertEqual(state["visibility"], "matching")

    def test_conflicting_own_anchors_still_make_visibility_uncertain(self):
        rows = [receipt("a", "accepted"), receipt("r", "readback", remote_ref="fixture:comment/two")]
        self.assertEqual(self.status(rows)["visibility"], "uncertain")

    def test_insert_or_replace_cannot_rewrite_history(self):
        p.import_data(self.db, dataset())
        with p.journal(self.db, write=True) as con, self.assertRaises(sqlite3.IntegrityError):
            con.execute("INSERT OR REPLACE INTO records VALUES ('operations','op-1','{}','test')")
        self.assertEqual(p.read_data(self.db)["operations"], [operation()])


if __name__ == "__main__":
    unittest.main()
