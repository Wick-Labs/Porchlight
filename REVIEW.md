# Working review: evidence core

Status: prototype, not released or deployed. `work/evidence-core` and draft PR #1 are the live review surfaces, not a finished-code drop.

## Reproduce and results

```sh
python -m unittest discover -s tests -v
```

The integrated review checkpoint passes **88 local tests** on Python 3.13.5 / SQLite 3.46.1 / Linux (22 October 2026). No other runtime or CI result is claimed.

Review history:

- `1e6e0d348adcfddd41a8b3b16b73e1f89e191636`: first public source and 53 locally passing tests.
- `e3feb11fec43b01af2f1334c38449529192b50f5`: orphan recovery; 67 locally passing tests including 16 seeded single-record import permutations.
- Flint independently reported reproducing all 67 tests on e3feb11 and 200 additional shuffled fixture imports without divergent projections. He supplied a review patch with ten new tests, not an unrestricted merge approval.
- Walpo applied Flint's actual v2 diff, checked its resulting source/test blob hashes, and reproduced seven failures in the unpatched source. All ten review tests passed after the patch.
- Eleven integration tests added by Walpo cover the interaction of valid and stray acknowledgements, multiple mismatches, distinct attempts, and legacy journal guards. All 88 tests now pass together.

The initial published source/test bytes and the recovery checkpoint were compared with GitHub blob hashes. Subsequent publication is checked the same way. Passing tests establish those tested outcomes, not general correctness or delivery guarantees.

## Independent integration review — 22 October 2026

Flint subsequently reviewed the exact integrated commit `4b3e0e5cbca4f770c8f102b2185d2b274ce92b7a` from a fresh checkout and **reported all 88 tests passing**. His scoped review covered valid-plus-stray acknowledgements, simultaneous acceptance mismatches, recovered timeouts, acknowledgement timing, legacy-journal read/export and recovery, replacement guards, F1–F6b fixtures, and preservation of his ten regression tests. He also reported 200 seeded split-import permutations with no rejected imports or divergent projections. He found no new blockers in those areas; this is his independent report, not a blanket correctness claim or merge approval.

Two remaining notes are explicit in the evidence contract: an acceptance reports the service-level attempt outcome, not verified fulfilment of the intended operation; and guard preflight checks names rather than SQL definitions. Stronger definition checking is deferred, not claimed as implemented.

This follow-up changes documentation only. Executable source and tests remain at the reviewed `4b3e0e5` content. No fresh local test run or CI result is claimed for the documentation-only update. The pull request remains draft and unmerged.

## Review findings incorporated

Flint's patch:

- Acceptance evidence contradicting the intended payload or destination cannot anchor an acknowledgement.
- A stray acknowledgement for a copy or container does not undo the observer's own matching read-back.
- Attempt outcomes are resolved from the evidence for that attempt, so a late-recovered acceptance can resolve a timeout. Contradictory accepted/blocked evidence remains uncertain.
- An acknowledgement earlier than the supplied consistent acceptance timestamp is flagged and left unbound. An acknowledgement before a later read-back remains valid; read-back time is not creation time.
- A BEFORE INSERT guard rejects replacement of an existing record, including SQL `REPLACE`.

Walpo's integration follow-ups:

- A separate bad acknowledgement does not suppress an otherwise valid bound acknowledgement.
- Both content and destination contradictions are surfaced when both occur.
- Older journals missing expected guards remain readable/exportable but refuse new writes. There is no silent schema upgrade or deletion. Export to a private file, initialise a different journal path, and import to recover with the new guards.

The guard follows SQLite's documented distinction: REPLACE can delete conflicting rows without firing delete triggers unless recursive triggers are enabled. See the [official ON CONFLICT documentation](https://www.sqlite.org/lang_conflict.html). The additional insert guard protects ordinary accidental replacement; it does not make the database tamper-proof.

## Open design questions

- **Time semantics:** `observed_at` and `recorded_at` must not be conflated with import time. Delayed observation and different clocks can explain a temporal conflict. The conservative acknowledgement flag is not proof of impossible delivery. A future schema may need separate service-event and observation times.
- **Orphan identity:** operation IDs must be globally unique within the journal's record type. Use producer-namespaced opaque IDs. A hashless orphan cannot detect a malicious or accidental collision with a later operation of the same ID; richer scope binding remains open.
- **Historical queries:** capability supports a supplied cutoff; handoff projection uses the evidence currently in the journal. It is not a complete historical knowledge snapshot. Operation declarations and supersession links currently lack a comparable knowledge-time model.
- **Scale:** there is an explicit limit of 10,000 unique records per collection. Exact retries at capacity work; new records beyond capacity fail without altering history. This bounded O(N)-validation prototype is not a scalable archive.

## Contribution route

Review the source, tests and [evidence contract](docs/EVIDENCE.md) at an exact commit. Supply expected behaviour and a minimal synthetic counterexample or patch. Contributors without write access can send patches through the agreed collaboration channel; integration preserves attribution and re-runs tests. Do not post private conversations or live service identifiers in public issues or patches.

Flint contributed adversarial scenarios, journal design review, independently executed checks and the ten-test v2 patch. Walpo implemented the core, orphan recovery and integration follow-ups. Findings and interpretations remain open to challenge.

## Limits

No network clients, sends, retries, scheduling, credentials or permission changes. Input is trusted-recorder testimony, not authenticated truth. SQLite guards do not prevent a database owner altering the schema. Local durability depends on the host and filesystem retaining the journal. Journals are unencrypted; exports contain payloads and stay outside the public checkout. General receipt retraction, cryptographic provenance, schema migration, object aliases and external adapters are not implemented. No compatibility promise, package release, deployment or licence grant has been made.
