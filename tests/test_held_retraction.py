"""Held retractions and settled orphan withdrawals. Synthetic values only.

A retraction that names a receipt under a different operation is held, not
applied and not rejected, so a mistaken or foreign retraction that arrives first
cannot block the real receipt's later import. Results must not depend on order.
"""
import copy
from itertools import permutations
from pathlib import Path
import random
import tempfile
import unittest

import porchlight as p
from test_porchlight import dataset, operation, receipt, T1, T2
from test_flint_r2 import retract


OPS = [operation(), operation("op-2")]


class HeldRetractionTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.count = 0

    def tearDown(self):
        self.directory.cleanup()

    def journal(self):
        self.count += 1
        db = Path(self.directory.name) / f"journal-{self.count}.sqlite3"
        p.initialize(db)
        return db

    def replay(self, batches):
        """Import each batch separately into a fresh journal; return what was stored."""
        db = self.journal()
        for batch in batches:
            p.import_data(db, copy.deepcopy(batch))
        return p.read_data(db)

    def outcome(self, data):
        views = {(o, op): p.canonical(p.project(data, op, o))
                 for op in ("op-1", "op-2") for o in ("alpha", "beta")}
        return views, p.canonical(p.unresolved(data))

    def assert_order_independent(self, rows):
        """Every order for up to four batches; otherwise 24 seeded shuffles."""
        batches = [dataset(operations=OPS)] + [dataset(operations=[], receipts=[r]) for r in rows]
        expected = self.outcome(p.validate(dataset(OPS, rows)))
        if len(batches) <= 4:
            orders = list(permutations(batches))
        else:
            orders = []
            for seed in range(24):
                order = list(batches)
                random.Random(seed).shuffle(order)
                orders.append(order)
        for order in orders:
            labels = [b["receipts"][0]["id"] if b["receipts"] else "operations" for b in order]
            with self.subTest(order=labels):
                self.assertEqual(self.outcome(self.replay(order)), expected)
        return expected

    def test_wrong_operation_retraction_first_then_receipt_imports(self):
        # Regression: on 0e2791b the second import raised "a retraction cannot cross
        # operations" and the real receipt could never be stored.
        wrong = retract("x", "r", observer="beta")  # under op-1
        real = receipt("r", "readback", operation("op-2"))
        data = self.replay([dataset(operations=OPS, receipts=[wrong]), dataset(operations=[], receipts=[real])])
        self.assertEqual({r["id"] for r in data["receipts"]}, {"x", "r"})
        held = p.unresolved(data)
        self.assertEqual(held["mismatched_retractions"], [{"receipt_id": "x", "retracts": "r", "observer": "beta"}])
        self.assertEqual(held["unresolved_retractions"], [])
        state = p.project(data, "op-2", "alpha")
        self.assertTrue(state["readback_match"])
        self.assertEqual(state["retracted_receipts"], [])

    def test_same_observer_wrong_operation_retraction_is_held_not_applied(self):
        wrong = retract("x", "r")  # alpha, op-1; target is alpha's on op-2
        real = receipt("r", "readback", operation("op-2"))
        self.assert_order_independent([wrong, real])
        data = p.validate(dataset(OPS, [wrong, real]))
        self.assertTrue(p.project(data, "op-2", "alpha")["readback_match"])
        self.assertEqual([h["receipt_id"] for h in p.unresolved(data)["mismatched_retractions"]], ["x"])

    def test_right_operation_retraction_first_then_receipt_is_withdrawn(self):
        good = retract("x", "r", time=T2)
        real = receipt("r", "readback", time=T1)
        early = self.replay([dataset(operations=OPS, receipts=[good])])
        self.assertEqual(p.unresolved(early)["unresolved_retractions"],
                         [{"receipt_id": "x", "retracts": "r", "observer": "alpha"}])
        self.assert_order_independent([good, real])
        data = self.replay([dataset(operations=OPS, receipts=[good]), dataset(operations=[], receipts=[real])])
        state = p.project(data, "op-1", "alpha")
        self.assertFalse(state["readback_match"])
        self.assertEqual(state["retracted_receipts"], ["r"])
        unresolved = p.unresolved(data)
        self.assertEqual(unresolved["unresolved_retractions"], [])
        self.assertEqual(unresolved["mismatched_retractions"], [])

    def test_mixed_held_and_applied_retractions_are_order_independent(self):
        rows = [receipt("r", "readback", time=T1), receipt("k", "readback", operation("op-2"), time=T1),
                retract("x", "r", time=T2), retract("y", "k", time=T2), retract("z", "k", observer="beta", time=T2)]
        views, unresolved = self.assert_order_independent(rows)
        data = p.validate(dataset(OPS, rows))
        self.assertEqual(p.project(data, "op-1", "alpha")["retracted_receipts"], ["r"])
        self.assertEqual(p.project(data, "op-2", "alpha")["retracted_receipts"], [])
        self.assertEqual(sorted(h["receipt_id"] for h in p.unresolved(data)["mismatched_retractions"]), ["y", "z"])


class SettledOrphanTests(unittest.TestCase):
    def test_own_withdrawal_of_own_orphan_leaves_no_orphan(self):
        ghost = operation("ghost")
        rows = [receipt("o", "readback", ghost), retract("x", "o", operation_id="ghost")]
        for order in (rows, rows[::-1]):
            with self.subTest(first=order[0]["id"]):
                self.assertEqual(p.unresolved(dataset(receipts=order))["orphan_receipts"], [])

    def test_foreign_withdrawal_of_orphan_stays_visible(self):
        ghost = operation("ghost")
        rows = [receipt("o", "readback", ghost), retract("x", "o", observer="beta", operation_id="ghost")]
        self.assertEqual([r["receipt_id"] for r in p.unresolved(dataset(receipts=rows))["orphan_receipts"]], ["o", "x"])

    def test_withdrawal_whose_target_has_not_arrived_is_still_an_orphan(self):
        rows = [retract("x", "o", operation_id="ghost")]
        unresolved = p.unresolved(dataset(receipts=rows))
        self.assertEqual([r["receipt_id"] for r in unresolved["orphan_receipts"]], ["x"])
        self.assertEqual([r["receipt_id"] for r in unresolved["unresolved_retractions"]], ["x"])


if __name__ == "__main__":
    unittest.main()
