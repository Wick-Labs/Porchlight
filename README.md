# Porchlight

An experimental, offline handoff-evidence checker for collaborators who do not share the same execution context or availability.

**Work in progress.** Implementation and tests are being developed on [`work/evidence-core`](https://github.com/Wick-Labs/Porchlight/tree/work/evidence-core). The branch is a review surface, not a release.

Porchlight records intentions and receipts, then derives what a particular observer has evidence for. Service acceptance, matching read-back, recipient visibility and acknowledgement are deliberately separate. Historical capability observations do not grant permission to act.

The prototype has no network client, sender, scheduler or tool executor. It does not restore unavailable integrations or bypass execution restrictions.

## Public repository boundary

Only source, engineering documentation and synthetic examples belong here. Do not commit credentials, live inbox addresses, private workspace links or identifiers, correspondence, runtime journals or client material. Keep runtime data outside this checkout.

Contributors can review the working branch and send concrete findings or patches through the channels available to them. Preserve authorship and distinguish proposed changes from verified results.

No release or deployment has been made. Licensing is not yet selected.
