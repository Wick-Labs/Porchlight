# Working review: evidence core

Status: prototype, not released or deployed. This public branch is the live review surface; do not wait for a finished implementation to review it.

## Reproduce

From the repository root, using Python 3.11 or later and its standard library:

```sh
python -m unittest discover -s tests -v
python porchlight.py --help
```

The initial source/test checkpoint is `1e6e0d348adcfddd41a8b3b16b73e1f89e191636`. Its 53 tests passed locally on 22 October 2026. Source and test Git blob hashes were read back from GitHub and matched the tested local bytes. These are local results, not CI or third-party certification.

## Current review priorities

1. **Receipt-before-operation imports:** the baseline rejects these. The next change will retain orphan receipts without treating them as evidence of a known operation, expose unresolved references, and resolve them when the operation arrives.
2. **Observer and identity boundaries:** an observer must not borrow another observer's direct evidence; a message's containing thread is not an alias for that message; an acknowledgement must bind to the exact remote object and payload.
3. **Atomicity and replay:** conflicting IDs must roll back the whole import. Equivalent JSON key order must not cause a conflict. Payload bytes must not be normalised. Recovery should be independent of import order.
4. **Time and claims:** tied contradictory observations must remain uncertain. Historical read-back does not establish present availability. Capability observations are not authorisation.

## Contribution route

Review `porchlight.py` and `tests/test_porchlight.py` on `work/evidence-core`. Cite the commit, function, expected behaviour and a minimal synthetic counterexample. Contributors without write access can supply a review note, fixture, replacement function or unified diff; the integrating contributor will preserve attribution and test it. Do not put private conversations or real service identifiers in a public issue or patch.

Flint contributed the adversarial-case design and journal review. The implementation and the interpretations remain open to challenge.

## Limits to keep visible

- No network clients, sends, retries, scheduling, credentials or permission changes.
- Input is trusted-recorder testimony, not authenticated evidence or a tamper-proof audit log.
- SQLite triggers protect against ordinary accidental update/delete, not a database owner modifying the schema.
- Local durability depends on the host retaining the journal. Never claim an unsaved run became a durable pending contribution.
- Runtime journals and explicit exports can contain payloads and must stay outside this public repository.
- No general receipt-retraction protocol or alias inference is implemented in the baseline.
- No compatibility promise, package publication or licence grant has been made.
