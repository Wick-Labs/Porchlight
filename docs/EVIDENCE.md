# Evidence contract

Porchlight derives a conservative view of supplied records. It does not observe services itself. A recorder is responsible for truthful provenance, stable identifiers, timestamp meaning and authorised collection. Records cannot turn an unavailable or forbidden action into an allowed one.

## Identity and content

Every record has a stable ID unique within its collection (`operations`, `receipts`, or `observations`). Use producer-namespaced opaque IDs for real records; short fixture IDs in the example are synthetic. An identical ID and canonical JSON object is an idempotent retry. A changed field under the same ID is a conflict, not an update. JSON key order is ignored; strings—including timestamp spelling and payload bytes—are preserved. Two textual timezone representations of the same instant are therefore conflicting record contents under one ID, even though time comparisons understand their equivalence.

An operation declares author, recipient, action, execution context, destination and exact UTF-8 payload. A replacement is a new operation with explicit `supersedes` links. A link cannot change the declared scope. Forks stay visible; later import order does not choose the truth. The local operation registry is trusted input, not an authenticated authorisation log.

The payload's SHA-256 uses exact UTF-8 bytes. Whitespace and Unicode normalization are not silently changed. A recipient acknowledgement binds to the operation's intended recipient, content hash, destination and the exact remote object supported by the observer's consistent acceptance or read-back evidence. A page containing a comment, or a thread containing a message, is not an alias for that object. No alias inference is implemented.

A service acceptance may legitimately return only an object reference rather than a content hash. Missing hash/destination fields do not themselves contradict the operation. If either is supplied and disagrees, the contradiction is flagged and that acceptance cannot anchor an acknowledgement.

## Separate kinds of evidence

- `accepted`: the observer records service acceptance of an attempt. It is not read-back or recipient visibility; inspect contradiction flags.
- `readback`: the observer records the exact object, payload hash and destination returned by a read. Historical matching evidence remains visible even when a later observation differs.
- `ack_received`: the observer records an acknowledgement by the intended recipient. This is not the recipient's own direct read-back evidence.
- `not_found`: absence from that observed view. It does not prove deletion, loss, failed delivery or denial.
- `timeout`: an uncertain attempt outcome, not proof of failure. Later acceptance for the same attempt can resolve it without an automatic resend.
- `blocked`: an explicit blocked attempt observation. It does not grant permission to retry elsewhere.
- `report`: testimony about another observation. It is retained separately and cannot promote direct evidence flags.
- `retract`: the observer withdraws one earlier receipt, named by `retracts`, with a `reason`. It carries no evidence fields of its own. See "Retraction" below.

`accepted=true` and `latest_attempt_result="accepted"` preserve the reported service-level outcome: something was accepted for that attempt. They do not mean that the intended content or destination was verified. They can therefore coexist with `accepted_content_mismatch` or `accepted_destination_mismatch`; contradictory acceptance remains excluded from acknowledgement anchors, and matching read-back and recipient acknowledgement are separate conclusions.

Projections use only the selected observer's receipts. A bad acknowledgement cannot erase a separate valid acknowledgement or matching read-back. Conflicting direct anchors or direct read identities still make identity uncertain. `readback_match` is historical; `visibility` is the latest view actually observed, with `visibility_as_of`, not a live guarantee.

Attempts are grouped by `attempt_id` before resolving their outcomes. Accepted plus blocked for one attempt is contradictory. Otherwise acceptance resolves its timeout, and an explicit block is stronger than timeout alone. The summary follows the attempt(s) represented by the most recent supplied attempt-observation time; tied different results stay uncertain. It does not reconstruct unrecorded attempt-start times.

## Time and corrections

Timestamps require RFC3339 seconds and an explicit timezone. `observed_at` orders observations; `recorded_at` records when the supplied observation was recorded. Neither is replaced by journal import time. A late-imported older observation does not become newest merely because it arrived last. Different observations at equal instants are retained; contradictory values are not resolved by arbitrary ID ordering.

Acknowledgement timing is compared only with consistent acceptance evidence for the same object, never with read-back time. An acknowledgement predating supplied acceptance is conservatively flagged and left unbound. This is a conflict in the supplied timeline, not proof of real-world causality: delayed observation and clock skew may explain it. General clock reconciliation and a separate authoritative service-event timestamp are not implemented. Preserve the original evidence and investigate rather than inventing a corrected timestamp.

### Retraction

A recorder that finds a receipt was wrong appends a `retract` receipt for the same operation; nothing is edited or deleted. The original stays in the journal and in `export`. Projections stop using it and list it in `retracted_receipts`. Projection has no as-of cutoff: it describes the journal as currently held, so a retraction applies to every projection made after it is imported, whatever order records arrived in.

- Only the receipt's own observer can withdraw it. A retraction by another observer is testimony: it appears in the target observer's `retraction_reports` and never removes direct evidence.
- Retracting a retraction is not supported in v0.1; the journal rejects it whichever arrives first. There are no resurrection rules: a mistaken retraction stays visible, and the evidence can be re-recorded as a new receipt. This also rules out retraction loops.
- A retraction naming a receipt that is not in the journal is held, like an orphan, and listed in `unresolved_retractions`. No target is invented. It applies when that receipt arrives.
- A receipt cannot retract itself, and a retraction and its target must name the same operation. Repeating a retraction is harmless.
- Withdrawing an anchor can unbind an acknowledgement that depended on it. That is intended: the acknowledgement is retained, but nothing direct now ties it to the object.

Capability observations are scoped to subject, observer, action, context and environment. A past manual success is not evidence of scheduled permission. `recheck_after` makes the present-tense prediction stale; it does not erase the historical record. Reports and inferences remain distinct from direct observations, and `permission_to_act` remains null.

## Local persistence and recovery

A receipt may arrive before its operation. Import preserves it as an orphan; `unresolved` lists it and no known-operation projection is invented. When the operation arrives, evidence is evaluated against its actual contents. Unique IDs are essential: hashless orphan evidence cannot by itself detect an unrelated operation reusing that ID. A receipt may record the scope its recorder believed the operation had: `expected_action`, `expected_context` and `expected_destination`, all three or none, because one destination can serve both a manual and a scheduled run. If any differs from the operation, the receipt is not bound to it: the projection excludes it (`excluded_receipts`) and flags `orphan_action_mismatch`, `orphan_context_mismatch` or `orphan_destination_mismatch`, and `unresolved` lists it under `scope_mismatched_receipts`. A receipt with neither a content hash nor an expected scope is bound by operation ID alone; it is still used, unchanged, but listed in `unscoped_receipts` so it is not presented as scoped proof. Reuse of an ID within the same scope still needs a content hash or unique IDs. Expected scope is a recorder assertion, not authentication.

Each import validates the combined state and inserts in one SQLite transaction. On a conflict or interrupted transaction, the entire import is rolled back. An intention exists durably only after a confirmed commit on a retained host. Nothing here saves an abandoned chat runtime automatically.

Expected SQL guards prevent ordinary update, delete and replacement of records. Older files lacking a guard can still be read/exported; imports refuse to proceed. Recovery is explicit: export privately, initialise a different new path, import, verify, and retain the original until its owner decides otherwise. The current preflight checks trigger names, not their SQL definitions. A different trigger installed under an expected name can pass that presence check; the check does not verify its behaviour. Guard presence is not schema authentication or tamper resistance.

The `export` command includes payloads. Status output also includes IDs and may itself be sensitive. Keep journals, exports and diagnostic outputs private. `.gitignore` reduces accidents; it is not a privacy boundary or encryption.
