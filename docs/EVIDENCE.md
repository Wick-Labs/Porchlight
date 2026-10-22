# Evidence contract — v0.1

Porchlight derives a conservative view of supplied records; it does not observe remote services itself. A recorder is responsible for truthful provenance, stable identifiers, timestamp meaning and authorised collection. Imported records cannot turn a forbidden or unavailable action into an allowed one.

## Identity and content

The envelope has `schema_version: 1` and optional `operations`, `receipts`, and `observations` arrays. Every record has an ID unique within its collection. Use producer-namespaced opaque IDs. An identical ID and canonical JSON object is an idempotent retry; any changed field under that ID is a conflict, not an update. JSON key order is ignored; strings, including timestamp spelling and payload bytes, are preserved. Offset-equivalent timestamp strings compare as the same instant but are still different record contents under one ID.

An operation declares author, recipient, action, execution context, destination and exact UTF-8 payload. Explicit `supersedes` links relate revisions of the same scope; forks stay visible and later import order does not choose a winner. Parent containers, matching text or hashes do not establish remote-object identity. Aliases are not implemented.

Payload SHA-256 is over exact UTF-8 bytes. There is no silent whitespace or Unicode normalisation. When a recorder uses an application-level payload inside a larger envelope, it must document the extraction rule and the limits of the representation it actually read.

## Receipt evidence and observer isolation

Every receipt names `id`, `operation_id`, `observer`, `kind`, `observed_at`, `recorded_at`, `evidence_ref`.

- `accepted`: recorded service acceptance of an attempt. It needs `attempt_id`; object identity may be returned without echoed content or destination.
- `readback`: the observer records the exact remote object, payload hash and destination returned by a read. An incomplete read cannot verify the intended payload.
- `ack_received`: the observer records an acknowledgement by the intended recipient, with exact object, hash, destination and `acknowledged_by`.
- `not_found`: absence from that observed view, not proof of loss, deletion, failed delivery or denial.
- `timeout`: an uncertain attempt outcome, not failure. It needs `attempt_id`.
- `blocked`: an explicitly blocked attempt observation. It needs `attempt_id` and grants no permission to retry elsewhere.
- `report`: testimony about another observation; it cannot promote direct evidence flags.
- `retract`: withdrawal of an earlier receipt under the rules below.

Projections use only the selected observer's own active receipts. An imported record labelled with another observer is that recorder's testimony; it is not proof the importer personally performed that observation. The schema has no signatures or identity authentication.

`accepted=true` and `latest_attempt_result="accepted"` mean the service reportedly accepted something for an attempt, not that intended content or destination were fulfilled. Supplied acceptance metadata that contradicts the operation raises `accepted_content_mismatch` or `accepted_destination_mismatch` and cannot anchor an acknowledgement. Missing optional echoed metadata is not itself a contradiction.

A bound acknowledgement requires the designated recipient, exact payload hash and destination, and a single consistent remote-object identity anchored by this observer's acceptance or matching read-back. A bad acknowledgement does not erase a separate valid one or a matching read. Conflicting direct anchors or read identities still make identity uncertain. Sender acknowledgement evidence is not the recipient's direct read-back.

`readback_match` is historical non-withdrawn evidence. `visibility` is the latest actual observed view, with `visibility_as_of`, not a guarantee of persistence now. Simultaneous contradictory observations remain uncertain instead of being resolved by arbitrary IDs.

Attempt evidence is grouped by `attempt_id` before summarising. Accepted plus blocked for one attempt is contradictory; otherwise acceptance resolves timeout, and explicit block is stronger than timeout alone. The summary follows attempts represented by the latest supplied attempt-observation time. Tied different results remain uncertain. Unrecorded attempt-start times are not reconstructed.

## Source time and soft ordering notes

Timestamps require RFC3339 seconds and an explicit timezone. `observed_at` dates the observation; `recorded_at` dates the record. Neither is journal import time or automatically service creation time. A late import does not make an old observation newest.

Receipts may include the complete optional triplet `source_at`, `source_origin`, and `source_trust`. Trust is one of `authoritative`, `reported`, or `untrusted`. These are recorder assertions, not verified certificates. `source_origin` is an exact opaque, case-sensitive clock-domain string; it is not normalised. An email header is not automatically an authoritative service clock.

An acknowledgement's source time is compared with consistent acceptance records for that same remote object only when both are declared authoritative and their origins match exactly. Predating the earliest such acceptance raises `ack_before_acceptance` and leaves that acknowledgement unbound. Read-back time never becomes creation time. Equal source times are not a conflict. Weaker or differently sourced acceptances do not override this comparable-clock comparison.

Without comparable source evidence, apparent ordering problems produce `ack_observation_order_unverified` or `ack_source_order_unverified` in `notes` and do not reject an otherwise bound acknowledgement. A strong conflict is a contradiction in the supplied timeline, not proof of impossible real-world causality. An early bad acknowledgement can leave a flag while a separate later valid acknowledgement binds. General clock reconciliation and historical knowledge snapshots are not implemented.

## Retraction and correction

A `retract` receipt requires `retracts` (target receipt ID) and a nonempty `reason`. It carries no operation-evidence fields, including no source-time triplet or expected scope. It is appended; the original is never edited or deleted.

A withdrawal has an effect only when its target is a non-withdrawal receipt for the same operation and observer. Another observer cannot remove direct evidence or clear its warnings. Missing targets are retained under `unresolved_retractions`; no target is invented.

Intrinsic faults, including self-retraction, missing/blank reasons and prohibited evidence fields, reject the input. Relationship defects that depend on another record are instead retained but inert: a different-operation target produces `operation_mismatch`, and a target that is itself a withdrawal produces `target_is_retraction`. `unresolved` exposes these records under `invalid_retractions`, with receipt ID, target ID, observer and deterministic reason list. Both reasons can apply. An early invalid relationship cannot prevent a later legitimate receipt or correction from being imported. Withdrawal cycles are inert, not resurrection rules. Re-record corrected evidence under a new ID instead.

`retraction_reports` preserves cross-observer testimony naming one of the selected observer's receipts in the same operation. It does not assert that the relationship is valid or effective. An inert foreign reference to a withdrawal can appear both in this report list and in `invalid_retractions`; it still removes nothing. Reports are not an action queue. The journal-wide diagnostics, together with `retracted_receipts`, distinguish ineffective relationships from actual withdrawals.

Current projections stop using same-observer withdrawn receipts and list them in `retracted_receipts`. Withdrawing an identity anchor can unbind a dependent acknowledgement. Withdrawing a scope-mismatched receipt clears its active scope flags and active unresolved entry, while historical `excluded_receipts`, `retracted_receipts` and export preserve it. Foreign-observer withdrawal does not clear those warnings. A withdrawal can itself retain a structural missing-operation reference.

There is no handoff-projection as-of cutoff: these rules apply to the journal currently held, independently of import order. A mistaken withdrawal cannot be undone in place. Capability observations are a separate record type and do not use receipt retraction.

## Expected scope and orphans

Receipts may precede operations. Orphan receipts are retained and exposed by `unresolved` without inventing a known-operation projection. A receipt can declare `expected_action`, `expected_context`, and `expected_destination`, all three or none. A mismatch excludes it from the operation's active evidence and raises `orphan_action_mismatch`, `orphan_context_mismatch`, or `orphan_destination_mismatch`. These names describe scope checking, not import order. `scope_mismatched_receipts` lists active mismatches.

Legacy receipts with neither a content hash nor expected scope remain usable by operation ID but are labelled `unscoped_receipts`; they are not silently rewritten or presented as scoped proof. This includes hashless blocked, timeout and not-found evidence. Same-scope ID reuse still requires globally unique IDs and, where available, content hashes. Expected scope is not authentication.

## Capability observations

Capability is scoped by subject, observer, action, execution context and environment. A manual success does not establish scheduled availability or permission. `recheck_after` makes a prediction stale, not the historical observation false. Direct, reported and inferred observations remain distinct. Capability queries consider both observation and recording cutoff; they are not a full historical snapshot of operation declarations. `permission_to_act` stays null and `automatic_retry` stays false.

## Local persistence and guard checks

Imports validate the combined state, then insert in one SQLite transaction. Conflicting IDs or interrupted transactions roll back the whole import. Every new INSERT must report one affected row, or the transaction is rejected. A saved intention exists durably only after commit on a host retaining the journal; an abandoned chat runtime is not persistent storage.

Preflight compares expected trigger SQL with the exact definitions used at initialisation and lists missing, mismatched and unexpected triggers across the main schema. It runs again after `BEGIN IMMEDIATE`. Additional triggers, including ones on other tables, are refused. Even harmless reformatting of expected definitions is treated conservatively as changed; this is not a SQL-equivalence analyser.

Missing, changed or extra guards allow reading/export but refuse imports. Explicit recovery: export privately, initialise a different path, import, verify, retain the original until its owner decides otherwise. No silent schema alteration. Guard checks and insert counts protect against the tested accidental changes; they do not authenticate a hostile database owner, arbitrary schema changes, storage hardware or the runtime itself.

Inputs are capped at 8 MiB each and 10,000 unique records per collection. Validation reads the whole journal. A cumulative export can exceed the single-file input limit and then needs record-preserving partitioned reimport. The tool is not an unbounded archive. Journals are local and unencrypted. Export includes payloads, and status includes possibly sensitive IDs. Keep all live journals, exports, credentials and correspondence outside the public checkout; `.gitignore` is not a privacy boundary.
