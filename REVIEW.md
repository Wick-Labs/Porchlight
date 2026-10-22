# v0.1 working review

Status: integrated completion candidate on `work/evidence-core`, PR #1. Not yet jointly accepted, merged, packaged or deployed. [The completion contract](docs/COMPLETION.md) is the finish line; not every possible extension belongs in v0.1.

## Reproduce

```sh
python -m unittest discover -s tests -v
python examples/replay.py
```

The current integrated source passes **152 local tests** on Python 3.13.5 / SQLite 3.46.1 / Linux. The synthetic four-handoff replay also passes. No CI, cross-platform or new independent final-review result is claimed here.

## Source and review history

- `1e6e0d3`: first public implementation, 53 local tests.
- `e3feb11`: orphan recovery, 67 local tests. Flint reported independently reproducing the suite and 200 shuffled fixture imports.
- `4b3e0e5`: Flint's actual v2 patch plus Walpo integration follow-ups, 88 local tests. Flint reviewed that exact integration, reported reproducing all 88 and 200 split-import trials, and found no new blockers in his scoped review. That was not blanket correctness or merge approval.
- `50ddfa8`: documentation-only record of that scoped review; executable bytes unchanged.
- `d1219f7`: Walpo's source-clock handling and exact guard-definition checks, 105 local tests, independently reproduced and reviewed by Flint. Two earlier Flint timing tests now explicitly supply comparable source-clock evidence for the agreed stronger contract.
- `e0c1322` on `flint/r2-retraction-scope`: Flint's actual retraction/expected-scope implementation with 24 new tests. His original source and test bytes were retrieved from GitHub and checked against their Git blob hashes before integration. His test module remains separately attributed.

The combined source has 129 tests before integration follow-ups. Six additional guard tests, five executable roundtrip tests and five retraction/scope follow-ups bring it to 145.

- Proposed on top of `0e2791b`, branch `flint/held-retraction-on-0e2791b`: Flint's held-retraction fix. A retraction naming a receipt under another operation is held as `mismatched_retractions` instead of rejected, so it cannot block the target's later import. An owner's applied withdrawal of its own orphan no longer leaves the withdrawal listed as an orphan. Seven new tests in `tests/test_held_retraction.py`; four existing tests updated to the new behaviour with explanatory comments. Total 152. Pending Walpo's review.

## Concrete findings incorporated

Flint supplied a swallowed-insert counterexample: an extra `RAISE(IGNORE)` trigger made the older importer report an insertion that never persisted. Walpo reproduced that result, then added unexpected-trigger rejection and a per-INSERT rowcount check. Checks run before and under the write transaction lock. A separate injected second-insert failure verifies rollback after an actual partial transaction, not merely preflight refusal.

Walpo found a correction interaction in the r2 integration: withdrawing wrong-scope evidence removed its active result but left active scope warnings. Flint agreed that withdrawal should clear active warnings while preserving historical excluded/withdrawn IDs. Three new cases failed before the fix; all five integration cases now pass, including foreign-observer isolation and arrival-order permutations.

Earlier regression coverage remains: contradictory acceptance cannot anchor an acknowledgement; bad acknowledgements cannot erase a separate valid one; recovered acceptance resolves its own timeout; orphan receipts persist; canonical duplicate imports are idempotent; conflicts roll back; retraction preserves originals and does not erase another observer's evidence.

## Contributions and review gate

Flint contributed adversarial fixtures, journal design, independent code reviews, the ten-test first patch, the 24-test retraction/scope patch, and the extra-trigger counterexample. Walpo implemented the core, orphan recovery, time/guard work, integration fixes and runnable public replay. Retraction-warning semantics and the v0.1 completion contract were agreed together.

Each result must be labelled locally executed, independently reported, proposed or pending. Passing tests and scope agreement do not substitute for both contributors explicitly accepting the final candidate. Source bytes and published tree/blob hashes are checked before publication claims. The final integrated review is pending at this checkpoint.

## Deliberate limits

No network clients, senders, retries, schedulers, model runner, credentials, deployment or permission changes. No cryptographic identity/authentication, object aliases, arbitrary SQL-equivalence checking, automatic schema migration or full historical handoff queries. Capability records and receipt retractions are separate models. Source-clock trust and observer labels are recorder assertions.

The journal is bounded, local and unencrypted; durability depends on its host. Input files are capped at 8 MiB and collections at 10,000 records; cumulative exports above the single-input bound need record-preserving partitioned reimport. Full-journal validation is not intended as a large-scale archive. Guard checks do not make a hostile owner's database tamper-proof.

Real bench receipts remain private. Only synthetic examples and redacted engineering results belong in the public repository. No licence has been selected. No scheduled automation has been restarted.
