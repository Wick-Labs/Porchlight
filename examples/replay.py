"""Replay synthetic handoffs locally; does not contact mail, Notion or any service."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import porchlight as p


def replay() -> dict[str, object]:
    examples = Path(__file__).resolve().parent
    data = p.load_json(examples / 'roundtrip.json')
    with tempfile.TemporaryDirectory(prefix='porchlight-demo-') as directory:
        db = Path(directory) / 'evidence.sqlite3'
        p.initialize(db)
        first = p.import_data(db, data)
        retry = p.import_data(db, data)
        # Each read reopens the file; no global in-memory state is required.
        recovered = p.read_data(db)
        results = []
        for op in recovered['operations']:
            sender = p.project(recovered, op['id'], op['author'])
            recipient = p.project(recovered, op['id'], op['recipient'])
            results.append({'operation': op['id'], 'sender_acknowledged': sender['acknowledged'],
                            'recipient_matching_read': recipient['readback_match'],
                            'recipient_did_not_borrow_acceptance': not recipient['accepted']})
        p.import_data(db, p.load_json(examples / 'correction.json'))
        after_correction = p.project(p.read_data(db), 'alpha:mail:handoff-1', 'alpha')
        p.import_data(db, p.load_json(examples / 'repair.json'))
        after_repair = p.project(p.read_data(db), 'alpha:mail:handoff-1', 'alpha')
        report = {'fixture_only': True, 'initial_inserted': first['inserted'],
                  'duplicate_inserted': retry['inserted'], 'handoffs': results,
                  'retracted_anchor_unbound_ack': not after_correction['acknowledged'],
                  'fresh_read_restored_ack': after_repair['acknowledged'],
                  'original_receipts_preserved': len(after_repair['retracted_receipts']) == 2}
        if (retry['inserted'] or not all(all(row[k] for k in (
                'sender_acknowledged', 'recipient_matching_read', 'recipient_did_not_borrow_acceptance')) for row in results)
                or not report['retracted_anchor_unbound_ack'] or not report['fresh_read_restored_ack']
                or not report['original_receipts_preserved']):
            raise p.Invalid('synthetic replay did not match its expected outcomes')
        return report


if __name__ == '__main__':
    try:
        print(json.dumps(replay(), indent=2))
    except (p.Invalid, OSError) as exc:
        print(f'replay failed: {exc}', file=sys.stderr)
        raise SystemExit(2)
