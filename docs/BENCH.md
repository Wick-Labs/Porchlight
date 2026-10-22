# Two-way handoff bench

## What is being checked

The live bench exchanges one harmless payload in each direction through email and a Notion comment: four distinct operations, not one object with four aliases. Each sender records acceptance and a read of their own copy. Each recipient independently reads the object through their authorised account, checks the declared payload and acknowledges its exact object ID, hash and destination.

The participants retain their own signed receipt exports in the private collaboration space. Importing those exports preserves the claimed observer; the importer does not claim to have operated the other participant's account. Raw private identifiers, message headers, workspace links and journals are not repository fixtures.

The acceptance procedure is:

1. Define exact payload extraction before sending. Use separate operation IDs per channel and exact object IDs, not containing thread/page IDs.
2. Save actual create/read outcomes and their observation times. Keep source metadata time separate; don't manufacture precision or echoed service fields.
3. Exchange acknowledgements naming object, payload hash, intended recipient and destination. Obtain each participant's own receipt export rather than turning a summary into their direct evidence.
4. Import the records into an offline journal. Project both observers for all four operations: sender acceptance/read-back/acknowledgement, recipient-owned read-back without borrowed acceptance.
5. Reimport identical records and expect zero insertions. Close/reopen, export, import into another new journal, and compare canonical data and projections.
6. Record actual outcomes and limitations on the private bench. A successful exchange is not final code approval; both reviewers must accept the exact final candidate separately.

## Public synthetic replay

```sh
python examples/replay.py
```

This generates no remote messages. It replays `roundtrip.json` (4 operations, 16 receipts), repeats the import, reopens the journal, withdraws two sender anchors with `correction.json`, and restores a binding with a fresh read in `repair.json`. An incorrect outcome raises an error and produces a nonzero exit.

The expected report has four successful sender/recipient checks, `duplicate_inserted: 0`, `retracted_anchor_unbound_ack: true`, `fresh_read_restored_ack: true`, and `original_receipts_preserved: true`.

## Live-run status

Both contributors have sent their harmless payloads through both channels, read the other contributor's payload independently, and sent exact-object acknowledgements. Full private receipt replay and final mutual acceptance of this integrated source are still pending at this checkpoint. The synthetic replay is verified; it must not be represented as the live replay result.

## Representation limits

The live application payload is the text between pre-agreed BEGIN/END markers, excluding the two separating newlines. Email footers and transport envelopes are outside that payload. Notion reads use the connector's rendered text, with its line-break markup decoded; they do not independently authenticate raw backend storage bytes. Observed placement can differ from the requested UI placement, so record actual container and exact object identity separately.

Successful live reads demonstrate these particular authorised interactions, not continuous availability, a restored scheduler, delivery guarantees or cryptographic author identity.
