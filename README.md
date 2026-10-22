# Porchlight

An offline evidence checker for interrupted collaboration. It helps answer **what was saved, what was observed, by whom, and for which exact handoff**—without mistaking any of those for permission to act.

**Experimental review prototype.** Working source is on `work/evidence-core`, reviewed in [draft PR #1](https://github.com/Wick-Labs/Porchlight/pull/1). Not released, deployed or connected to any service.

## Start here

Use Python 3.11 or later; there are no third-party dependencies. The test environment so far is Python 3.13.5 with SQLite 3.46.1 on Linux; other environments are not yet verified.

```sh
python -m unittest discover -s tests -v
python porchlight.py --help
```

To try the synthetic example, choose a **new journal path outside the checkout**:

```sh
python porchlight.py init --db ../porchlight-demo.sqlite3
python porchlight.py import --db ../porchlight-demo.sqlite3 examples/handoff.json
python porchlight.py status --db ../porchlight-demo.sqlite3 op-1 --observer alpha
python porchlight.py status --db ../porchlight-demo.sqlite3 op-1 --observer beta
python porchlight.py unresolved --db ../porchlight-demo.sqlite3
python porchlight.py check --db ../porchlight-demo.sqlite3
```

Expected: the sender has recorded acceptance, matching read-back and a bound acknowledgement; the recipient has their own matching read-back, not borrowed sender evidence. `unresolved` reports no dangling records. Reimporting the same file inserts zero new records. `init` refuses to overwrite an existing file.

## What it does

- Imports strict, bounded JSON into a local SQLite journal using an atomic transaction.
- Deduplicates identical IDs; conflicting reuse rejects the entire import.
- Preserves orphan receipts until their operation is available, and reports them explicitly.
- Separates historical matching read-back from the latest observed visibility. Absence from one view means uncertainty, not proven loss.
- Binds acknowledgements to exact content, destination, recipient and remote-object identity. A containing thread or page is not an alias.
- Keeps explicitly linked supersessions from becoming last-import-wins; divergent heads stay visible.
- Scopes capability observations by observer, subject, action, environment and execution context. Stale predictions do not erase historical evidence.

## What it does not do

No mail or Notion client, scheduler, model runner, action executor, permission grant or automatic retry. It does not restore an unavailable integration. Imported records are assertions from a trusted recorder, not independently authenticated truth. A successful test of one context says nothing about permission or availability in another.

The journal is local and unencrypted. It persists only where the host retains it; an unsaved runtime is not durable storage. `export` explicitly includes payloads. Keep real journals, exports, credentials and correspondence outside this repository.

Read [REVIEW.md](REVIEW.md) for tested behaviour, remaining limitations and contribution guidance. Public source contains only engineering material and synthetic examples. No licence has been selected yet; public visibility is not a licence grant.
