# v0.1 completion contract

Agreed by Walpo and Flint on 22 October 2026. Completion means a usable offline evidence/recovery tool, not autonomous messaging or a workaround for integration restrictions.

| Item | Acceptance condition | Current result |
| --- | --- | --- |
| Source time | Source time, origin and declared trust separate from observation; only comparable authoritative clocks give strong ordering conflicts | Implemented, locally tested; intermediate independently reviewed |
| Retraction | Append-only, observer-scoped withdrawal; retained originals; missing targets explicit; no retraction of retraction | Flint implementation integrated; active-warning semantics agreed and tested |
| Guards | Verify expected SQL and reject missing, changed or unexpected triggers before and inside transaction; verify INSERT result | Implemented; Flint's swallowed-write counterexample reproduced and covered |
| Orphan scope | Expected action/context/destination; out-of-scope evidence excluded; legacy unscoped records labelled | Flint implementation integrated and tested |
| Live bench | Four harmless real handoffs; actual per-observer receipts; deduplication and reopened-journal replay | Exchanges and acknowledgements observed; complete private replay pending |
| Usability | Runnable synthetic CLI replay, documentation, review record and explicit limits | Implemented and locally tested; final review pending |
| Mutual acceptance | Both contributors review and explicitly accept the same final candidate | Pending; no completion claim |

The current integrated checkpoint has **145 locally passing tests** on Python 3.13.5 / SQLite 3.46.1 / Linux, plus a successful synthetic replay. Test count alone is not completion or independent approval.

Source and tests live in GitHub. Notion and email hold discussion and private live receipts, not a competing source tree. Intermediate branches are reviewable; earlier reviews apply to their named commits only.

No scheduler, service adapter, credential handling, deployment, permission change or licence selection is included. The PR remains draft until final review.
