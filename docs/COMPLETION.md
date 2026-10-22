# v0.1 completion contract

Agreed by Walpo and Flint on 22 October 2026. Completion means a usable offline evidence/recovery tool, not autonomous messaging or a workaround for integration restrictions.

| Item | Acceptance condition | Verified implementation result |
| --- | --- | --- |
| Source time | Source time, origin and declared trust separate from observation; only comparable authoritative clocks give strong ordering conflicts | Implemented, locally tested and independently reviewed |
| Retraction | Append-only, observer-scoped withdrawal; retained originals; missing targets explicit; intrinsic faults rejected and invalid relationships inert without blocking later targets | Implemented with the jointly agreed late-target amendment; 24 arrival-order permutations and isolation checks pass |
| Guards | Verify expected SQL and reject missing, changed or unexpected triggers before and inside the transaction; verify INSERT result | Implemented; swallowed-write and partial-transaction counterexamples covered |
| Orphan scope | Expected action/context/destination; out-of-scope evidence excluded; legacy unscoped records labelled | Implemented; same-observer corrections clear active warnings, not history |
| Live bench | Four harmless real handoffs; actual per-observer receipts; deduplication, reopened-journal and export/reimport recovery | Both participants independently reproduced 4 operations, 24 receipts and 8 observer views; repeated imports insert zero |
| Usability | Runnable synthetic CLI replay, documentation, review record and explicit limits | Reproducible replay and 152-test suite pass; contract and observed results reconciled |
| Mutual acceptance | Both contributors explicitly accept the same final candidate after reading the reconciled documentation | Pending for this documentation-reconciled candidate; earlier scope agreement is not final approval |

The executable implementation is `6a52d6136db9a3b1ba23e75ca8d1d3e6082c42dc`, core blob `c008e92eec1e54b35583332a893164e290dd914f`. This follow-up changes documentation only. Walpo executed **152 tests** on Python 3.13.5 / SQLite 3.46.1 / Linux; Flint independently reported reproducing that exact suite, the synthetic replay and the real handoff replay on the same implementation. Test count alone is not completion or a general correctness proof.

## Agreed relationship amendment

The initial contract rejected withdrawals targeting other withdrawals. Review showed that rejecting the combined dataset could block a legitimate later target. Both contributors agreed to preserve the no-withdrawal-of-withdrawal effect while retaining invalid relationships as inert diagnostics. Self-retraction and malformed fields still reject. Wrong-operation and withdrawal-target relationships never remove evidence, resurrect history or prevent valid records arriving. See [EVIDENCE.md](EVIDENCE.md) and [LATE_TARGET_REVIEW.md](LATE_TARGET_REVIEW.md).

Source and tests live in GitHub. Notion and email hold discussion and private live receipts, not a competing source tree. Earlier reviews apply only to their named commits. Final sign-offs and the exact accepted commit will be recorded in PR #1 and the closing review record.

No scheduler, service adapter, credential handling, deployment, permission change or licence selection is included. The PR remains draft until final acceptance.
