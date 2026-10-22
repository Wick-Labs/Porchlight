# Working review: evidence core

Status: prototype, not released or deployed. `work/evidence-core` and draft PR #1 are the live review surfaces, not a finished-code drop.

## Reproduce and results

```sh
python -m unittest discover -s tests -v
```

The initial source/test checkpoint `1e6e0d348adcfddd41a8b3b16b73e1f89e191636` passed 53 local tests on 22 October 2026. GitHub blob hashes were matched against the tested local bytes.

The next checkpoint adds orphan recovery and passes 67 local tests on Python 3.13.5 / SQLite 3.46.1 / Linux. This includes 16 seeded permutations importing each record separately, including receipt-before-operation ordering. These are executed local tests, not CI or independent certification. No other platform is claimed tested.

## Changes from the baseline

- Keep orphan receipts without inventing their missing operations; expose them through `unresolved` and `check`.
- Canonically order records and capability reports so arrival order does not affect projections.
- Count unique records after deduplication so an exact retry at capacity remains idempotent.
- Bound supersession IDs, reject invalid timezone offsets, handle timestamp overflow as a controlled input error, and explicitly close the initialization connection.

## Current review priorities

1. Observer and identity boundaries: never borrow another observer's direct evidence; reject acknowledgements for copies, containers or the wrong content revision.
2. Recovery: conflicting IDs must roll back the whole import; retained orphans must resolve only against the actual operation. Canonical JSON key order must not change payload bytes.
3. Time and claims: tied conflicting observations remain uncertain. Historical read-back is not present availability. Capability observations are not authorisation.
4. Usability and boundedness: error messages must be useful without echoing payloads. Test failures are evidence of a remaining problem, not a reason to weaken the invariant.

## Contribution route

Review `porchlight.py`, `tests/test_porchlight.py` and `tests/test_recovery.py`. Cite the commit, function, expected behaviour and minimal synthetic counterexample. A contributor without write access can supply a review note, fixture, replacement function or unified diff; the integrating contributor preserves attribution and tests the change. Do not post private conversations or live service identifiers in a public issue or patch.

Flint contributed adversarial-case design and journal review, including orphan recovery and the correction that containment is not object identity. The implementation and interpretations remain open to challenge.

## Limits to keep visible

- No network clients, sends, retries, scheduling, credentials or permission changes.
- Input is trusted-recorder testimony, not an authenticated or tamper-proof audit log. SQLite triggers prevent ordinary accidental updates/deletes; a database owner can alter the schema.
- Local durability depends on the host and filesystem retaining the journal. An unsaved run is not a durable pending contribution.
- Journals are unencrypted and exports include payloads. Runtime data stays outside the public checkout; `.gitignore` is a convenience, not a privacy guarantee.
- The prototype rereads/validates the bounded journal on import and projection; it is not intended for large-scale storage.
- General receipt retraction, cryptographic provenance, schema migration, cross-channel object aliases and external adapters are not implemented.
- Supersession operates on the supplied local operation registry; it does not authenticate who authorised a replacement.
- No compatibility promise, package publication, deployment or licence grant has been made.
