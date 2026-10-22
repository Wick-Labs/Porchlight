# Contributing to Porchlight

This repository is public. Use synthetic fixtures only; never commit correspondence, live account identifiers, private workspace links, credentials, client material or runtime journals.

Read README.md, REVIEW.md and docs/EVIDENCE.md, then inspect the current branch and open PR before editing. The accepted v0.1 source is on `main`; `work/evidence-core` is retained as a historical review branch. Check actual refs and open reviews before new work. Keep small, reviewable changes and preserve collaborators' attribution.

Walpo and Flint jointly maintain Porchlight and coordinate routine project decisions directly. Involve Bun when an external account or permission requires the owner's action. This does not expand access to unrelated repositories or services, spending, or publication of private data.

Run `python -m unittest discover -s tests -v`. Record the exact commit/runtime and distinguish locally executed checks from another contributor's reports. Keep source available while work is ongoing, not only at completion. Verify publication before claiming a save.

Porchlight is offline. Do not add service calls, retries, scheduling, credential handling, deployment or permission changes as a side effect of this prototype. Capability evidence is not permission. Do not treat tool failures as an invitation to bypass execution boundaries.

Current scope and known limitations are in REVIEW.md. Unfinished work is a recoverable checkpoint, not permission to expand scope or an obligation to create more automation.

## Public commit metadata and rewritten history

Public-file scans do not cover commit metadata. Before creating or publishing a commit, verify that its intended author and committer identities use approved non-personal/no-reply addresses. A remote connector may choose its own defaults; local Git configuration does not configure that remote writer. Do not use an identity-uncontrolled commit path while its defaults are unsafe. Never paste credentials to obtain another write route.

After an authorised metadata/history rewrite, refresh actual refs and use only the clean ancestry. Never push or merge an old local branch back into the repository. Verify content by tree/blob hashes and inspect both author and committer on replacement commits. Keep detailed old-to-new mappings and privacy-audit records private. Rewriting reachable history is not proof of removing every cached view, pull-request ref, fork or clone.
