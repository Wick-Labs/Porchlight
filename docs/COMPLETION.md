# v0.1 completion contract

Agreed by Walpo and Flint on 22 October 2026. This defines completion of the offline evidence/recovery tool, not autonomous delivery or a workaround for integration restrictions.

1. Separate source-event time, source clock domain and recorder-declared trust from observation time. Strong ordering requires comparable authoritative source clocks; other ordering concerns remain soft notes.
2. Append-only receipt retraction: original evidence stays visible in export, withdrawal is observer-scoped, missing targets are explicit, and retraction-of-retraction is rejected.
3. Verify expected SQLite guard SQL definitions before imports, including under the transaction lock. Changed or missing guards allow reading/export but require explicit recovery before writing.
4. Expected receipt action/context/destination prevent out-of-scope orphan binding. Legacy hashless unscoped evidence is explicitly labelled.
5. Record and project a real harmless handoff in each direction through the authorised collaboration channels. Real identifiers remain in the private bench, never public fixtures.
6. Provide a reproducible synthetic CLI counterpart, concise usage documentation, a review record and explicit limits.

Both contributors must review the exact final candidate and explicitly agree it meets this contract before it is described as complete. Earlier test results or scope agreement are not final approval.

## Progress

The source-time and guard-definition checkpoint has 105 locally passing tests on Python 3.13.5 / SQLite 3.46.1 / Linux. Flint's retraction/scope patch has been received for integration, not yet verified in this checkpoint. The real two-way bench run and final mutual acceptance are pending. The PR remains draft.

No new scheduler, credential handling, network executor, deployment, permission change or licence selection is included.
