# Late-target withdrawal review

Review proposal on top of `0e2791b`; not final acceptance. The main working candidate stays frozen while this branch is reviewed.

Flint independently found that an early withdrawal naming a not-yet-known receipt from a different operation could cause the later valid receipt import to fail. Walpo reproduced it and the related case where an early withdrawal names a later legitimate withdrawal. Rejecting the entire combined dataset lets a mistaken relationship obstruct otherwise valid evidence.

The proposed narrow amendment distinguishes intrinsically invalid records from invalid relationships. Self-retraction, missing fields and prohibited evidence fields still reject the input. Missing targets remain held. Once a target arrives, a wrong-operation relationship or a target that is itself a withdrawal remains stored but inert, and `unresolved` reports it under `invalid_retractions`, with `operation_mismatch` and/or `target_is_retraction` reasons. Such relationships never withdraw a receipt or prevent its arrival. Cyclic withdrawal relationships are therefore inert, not resurrection rules.

A valid withdrawal requires a non-withdrawal target, the same operation and the same observer. Foreign-observer testimony never removes direct evidence. Original records remain available for inspection and export. This changes rejection of an invalid relationship's effect, not the observer-isolation rule.

Seven additional tests cover early wrong-operation references, legitimate late withdrawals, two- and three-node cycles, simultaneous relationship defects, all 24 import permutations of a four-record case, unresolved-to-invalid transition and intrinsic self-retraction. Six new cases fail on the previous candidate; the intrinsic-invalid guard already passes. The complete proposed suite has **152 locally passing tests** on Python 3.13.5 / SQLite 3.46.1 / Linux.

Existing Flint tests that expected relationship-triggered import rejection are explicitly revised to require inertness and later-target recoverability; attribution remains intact. Final contract wording and release status will be reconciled only after both reviewers agree. This proposal does not introduce network execution, new permissions or scheduling.
