# Porchlight

An offline evidence checker for interrupted collaboration. It answers **what was saved, what was observed, by whom, and for which exact handoff** without treating evidence as permission to act.

**v0.1 merged.** Walpo and Flint jointly accepted candidate `33d95ec` and its documentation closure `3ab8c18` against [the completion contract](docs/COMPLETION.md). [PR #2](https://github.com/Wick-Labs/Porchlight/pull/2) merged that unchanged file tree into `main` on 22 October 2026 as `8c499be`. **Use `main` for the current source.** Earlier review branches and review records are historical provenance. Porchlight is not a hosted service or autonomous messenger. Branch history was rewritten on 22 October 2026 to fix commit identity metadata without changing the reviewed file trees.

## Run it

Use Python 3.11 or later. No third-party packages, account setup, API keys or installation are required. Local verification so far is Python 3.13.5 / SQLite 3.46.1 / Linux; other environments are not yet verified.

```sh
python -m unittest discover -s tests -v
python examples/replay.py
python porchlight.py --help
```

`examples/replay.py` uses a temporary local journal and synthetic records. It checks four handoffs (two directions, two channels), sender acknowledgement, recipient-owned read-back, an idempotent retry, reopening the journal, an evidence correction and recovery from a fresh read. It contacts no services and exits nonzero when an expected result fails.

## Step through the handoff

Choose a **new journal path outside this checkout**. On Windows, `py -3` can replace `python` when that is your Python launcher.

```sh
python porchlight.py init --db ../porchlight-demo.sqlite3
python porchlight.py import --db ../porchlight-demo.sqlite3 examples/roundtrip.json
python porchlight.py status --db ../porchlight-demo.sqlite3 alpha:mail:handoff-1 --observer alpha
python porchlight.py status --db ../porchlight-demo.sqlite3 alpha:mail:handoff-1 --observer beta
python porchlight.py import --db ../porchlight-demo.sqlite3 examples/roundtrip.json
python porchlight.py unresolved --db ../porchlight-demo.sqlite3
python porchlight.py check --db ../porchlight-demo.sqlite3
```

Expected: the first import inserts 20 records; the repeated import inserts zero. Alpha's sender view is accepted, read back and acknowledged. Beta has its own matching read-back, not borrowed sender acceptance or acknowledgement. All unresolved lists are empty; the SQLite check is `ok`, with no missing, mismatched or unexpected guards.

Now correct a mistaken sender record without erasing it:

```sh
python porchlight.py import --db ../porchlight-demo.sqlite3 examples/correction.json
python porchlight.py status --db ../porchlight-demo.sqlite3 alpha:mail:handoff-1 --observer alpha
python porchlight.py import --db ../porchlight-demo.sqlite3 examples/repair.json
python porchlight.py status --db ../porchlight-demo.sqlite3 alpha:mail:handoff-1 --observer alpha
```

The correction withdraws two identity anchors, so the acknowledgement becomes unbound. The repair adds a new matching read-back and restores that binding. The originals remain in `export` and `retracted_receipts`. No network resend occurred. A correction by a different observer cannot withdraw your evidence.

These files are a synthetic counterpart to the contributors' private live email/Notion experiment, not an export of private accounts. [The bench procedure](docs/BENCH.md) explains how actual observations are recorded and what is and is not established.

## Reading a result

- `accepted` is the recorded service-level attempt outcome, not verified fulfilment. Inspect contradiction flags.
- `readback_match` preserves matching non-withdrawn historical reads. `visibility` and `visibility_as_of` describe the latest observed view, not live availability.
- `acknowledged` binds a recipient's acknowledgement to exact content, destination and remote-object identity. A thread containing a message is not that message.
- `flags` expose active contradictions; `notes` include uncertain clock ordering. Historical excluded and withdrawn IDs stay available separately.

Expected receipt action, context and destination prevent a wrong-scope receipt from binding. Source time, clock origin and recorder-declared trust keep a late observation from masquerading as object creation time. The [evidence contract](docs/EVIDENCE.md) specifies the details.

## Recovery and privacy

Each command opens the selected journal; no hidden global session is required. `init` refuses to overwrite an existing file. Imports are atomic, and exact retries deduplicate. A changed or additional SQL trigger blocks imports, but reading/export remains available for explicit recovery into a different newly initialised journal. Do not delete the original until its owner has verified recovery.

`export` writes JSON to standard output and includes payloads. Keep it private. CLI inputs are limited to 8 MiB each and collections to 10,000 unique records each; a larger cumulative journal may require partitioned export records for reimport. This is a bounded local tool, not an unlimited archive.

No mail/Notion client, scheduler, model runner, credential store, permission grant, automatic retry or deployment is included. It does not restore unavailable integrations. Records are trusted-recorder assertions, not cryptographic proof. Journals are unencrypted and survive only where the host retains the files.

See [REVIEW.md](REVIEW.md) for verified results and remaining limits, and [CREDITS.md](CREDITS.md) for authorship. This public repository contains engineering material and synthetic examples only. No licence has been selected.
