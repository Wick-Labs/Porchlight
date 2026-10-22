# Contributing to Porchlight

This repository is public. Use synthetic fixtures only; never commit correspondence, live account identifiers, private workspace links, credentials, client material or runtime journals.

Read README.md, REVIEW.md and docs/EVIDENCE.md, then inspect the current branch and open PR before editing. The working review branch is `work/evidence-core`; do not assume main contains the latest experiment. Keep small, reviewable changes and preserve collaborators' attribution.

Run `python -m unittest discover -s tests -v`. Record the exact commit/runtime and distinguish locally executed checks from another contributor's reports. Keep source available while work is ongoing, not only at completion. Verify publication before claiming a save.

Porchlight is offline. Do not add service calls, retries, scheduling, credential handling, deployment or permission changes as a side effect of this prototype. Capability evidence is not permission. Do not treat tool failures as an invitation to bypass execution boundaries.

Current scope and known limitations are in REVIEW.md. Unfinished work is a recoverable checkpoint, not permission to expand scope or an obligation to create more automation.
