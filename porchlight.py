"""Porchlight: offline, observer-scoped evidence for interrupted handoffs.

No network access, action executor, scheduler, authentication, or permission grants.
Input is evidence asserted by a trusted recorder, not independently verified truth.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from typing import Any, Iterator

VERSION = "0.1.0"
APPLICATION_ID = 0x504F5243
MAX_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 10000
KINDS = {"accepted", "readback", "not_found", "timeout", "blocked", "ack_received", "report", "retract"}
EXPECTED = ("expected_action", "expected_context", "expected_destination")
SOURCE = ("source_at", "source_origin", "source_trust")
EVIDENCE = {"attempt_id", "remote_ref", "content_sha256", "observed_destination", "acknowledged_by", *EXPECTED, *SOURCE}
SCOPE = ("author", "recipient", "action", "context", "destination")
TABLES = ("operations", "receipts", "observations")
GUARDS = ("no_deletes", "no_replace", "no_updates")
RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class Invalid(ValueError):
    """Invalid evidence, conflicting identifiers, or unsupported journal."""


def stamp(value: str) -> datetime:
    if not isinstance(value, str) or not RFC3339.fullmatch(value):
        raise Invalid("timestamps must be RFC3339 with seconds and an explicit timezone")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise Invalid("invalid timestamp") from exc


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def digest(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _text(value: Any, field: str, *, empty: bool = False, limit: int = 4096) -> None:
    if not isinstance(value, str) or (not empty and not value.strip()) or len(value) > limit:
        raise Invalid(f"{field}: expected a bounded string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise Invalid(f"{field}: invalid Unicode") from exc


def _fields(record: Any, required: set[str], optional: set[str]) -> None:
    if not isinstance(record, dict):
        raise Invalid("each record must be an object")
    if not required <= record.keys() or record.keys() - required - optional:
        raise Invalid("missing or unsupported record fields")
    for key, value in record.items():
        if key == "supersedes":
            if not isinstance(value, list) or len(value) > MAX_RECORDS:
                raise Invalid("supersedes must be a bounded list of IDs")
            for target in value:
                _text(target, "supersedes ID")
            if len(value) != len(set(value)):
                raise Invalid("duplicate supersession edge")
        else:
            _text(value, key, empty=key == "payload", limit=1048576 if key == "payload" else 4096)
    for key in ("observed_at", "recorded_at", "recheck_after", "source_at"):
        if key in record:
            stamp(record[key])


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict) or data.keys() - {"schema_version", *TABLES}:
        raise Invalid("expected a versioned dataset; unsupported top-level fields")
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise Invalid("schema_version must be the integer 1")
    result: dict[str, Any] = {"schema_version": 1}
    for table in TABLES:
        records = data.get(table, [])
        # A merge can contain a full journal plus a full retry batch. Limit
        # unique records below, after exact-ID deduplication, so a retry at the
        # journal's capacity is still idempotent.
        if not isinstance(records, list) or len(records) > 2 * MAX_RECORDS:
            raise Invalid("record collections must be bounded arrays")
        unique: dict[str, dict[str, Any]] = {}
        for record in records:
            if table == "operations":
                _fields(record, {"id", *SCOPE, "payload"}, {"supersedes"})
                if record["id"] in record.get("supersedes", []):
                    raise Invalid("an operation cannot supersede itself")
            elif table == "receipts":
                _fields(record, {"id", "operation_id", "observer", "kind", "observed_at", "recorded_at", "evidence_ref"},
                        EVIDENCE | {"retracts", "reason"})
                if record["kind"] not in KINDS:
                    raise Invalid("unsupported receipt kind")
                if record["kind"] == "retract":
                    # A retraction is a statement about another receipt, not evidence
                    # about the operation, so it carries none of the evidence fields.
                    if not {"retracts", "reason"} <= record.keys() or record.keys() & EVIDENCE:
                        raise Invalid("a retraction needs retracts and reason and carries no evidence fields")
                    if record["retracts"] == record["id"]:
                        raise Invalid("a receipt cannot retract itself")
                elif record.keys() & {"retracts", "reason"}:
                    raise Invalid("only a retraction may name retracts or reason")
                # Expected scope is all or nothing: a destination alone could match
                # a manual and a scheduled run of the same operation ID.
                if record.keys() & set(EXPECTED) and not set(EXPECTED) <= record.keys():
                    raise Invalid("expected scope needs expected_action, expected_context and expected_destination")
                source_fields = set(SOURCE)
                if source_fields & record.keys() and not source_fields <= record.keys():
                    raise Invalid("source time needs source_at, source_origin and source_trust together")
                if "source_trust" in record and record["source_trust"] not in {"authoritative", "reported", "untrusted"}:
                    raise Invalid("unsupported source timestamp trust")
                if "content_sha256" in record and not SHA256.fullmatch(record["content_sha256"]):
                    raise Invalid("content_sha256 must be lowercase SHA-256 hex")
                if record["kind"] in {"accepted", "blocked", "timeout"} and not record.get("attempt_id"):
                    raise Invalid("attempt evidence needs an attempt_id")
            else:
                _fields(record, {"id", "subject", "observer", "action", "context", "environment", "outcome", "basis",
                                 "observed_at", "recorded_at", "recheck_after", "evidence_ref"}, set())
                if record["outcome"] not in {"worked", "blocked", "unknown"}:
                    raise Invalid("unsupported capability outcome")
                if record["basis"] not in {"direct", "reported", "inferred"}:
                    raise Invalid("unsupported evidence basis")
                if stamp(record["recheck_after"]) < stamp(record["observed_at"]):
                    raise Invalid("recheck_after precedes observation")
            rid = record["id"]
            if rid in unique and canonical(unique[rid]) != canonical(record):
                raise Invalid(f"conflicting ID in {table}")
            unique[rid] = dict(record)
            if len(unique) > MAX_RECORDS:
                raise Invalid("unique record limit exceeded")
        result[table] = sorted(unique.values(), key=lambda r: r["id"])
    operations = {op["id"]: op for op in result["operations"]}
    # A receipt may precede its operation. Preserve it without projecting it
    # as a known handoff; unresolved() exposes it until the operation arrives.
    # Dangling predecessor links are retained: a newer version may arrive first.
    # Validate their scope if/when the predecessor is later imported.
    for op in operations.values():
        for predecessor in op.get("supersedes", []):
            if predecessor in operations and any(op[key] != operations[predecessor][key] for key in SCOPE):
                raise Invalid("supersession cannot cross operation scope")
    # Iterative topological walk: reject cycles without a recursion-depth hazard.
    edges = {key: set(op.get("supersedes", [])) & operations.keys() for key, op in operations.items()}
    degree = dict.fromkeys(operations, 0)
    for targets in edges.values():
        for target in targets:
            degree[target] += 1
    ready = [key for key, count in degree.items() if count == 0]
    visited = 0
    while ready:
        key = ready.pop()
        visited += 1
        for target in edges[key]:
            degree[target] -= 1
            if degree[target] == 0:
                ready.append(target)
    if visited != len(operations):
        raise Invalid("supersession cycle")
    # A retraction may name a receipt that has not arrived yet; it is held, like an
    # orphan. Once both exist they must concern the same operation. Retracting a
    # retraction is not supported in v0.1, which also rules out retraction cycles.
    receipts = {r["id"]: r for r in result["receipts"]}
    for r in receipts.values():
        target = receipts.get(r.get("retracts", ""))
        if target is not None and target["operation_id"] != r["operation_id"]:
            raise Invalid("a retraction cannot cross operations")
        if target is not None and target["kind"] == "retract":
            raise Invalid("a retraction cannot be retracted")
    return result


def _withdrawn(receipts: list[dict[str, Any]]) -> set[str]:
    """IDs withdrawn by a retraction from the receipt's own observer."""
    by_id = {r["id"]: r for r in receipts}
    return {r["retracts"] for r in receipts if r["kind"] == "retract"
            and r["retracts"] in by_id and by_id[r["retracts"]]["observer"] == r["observer"]}


def _scope_mismatch(receipt: dict[str, Any], op: dict[str, Any]) -> list[str]:
    # A hashless receipt cannot detect an unrelated operation reusing its ID; the
    # scope its recorder expected can, for action, context and destination.
    return [key for key in ("action", "context", "destination")
            if "expected_" + key in receipt and receipt["expected_" + key] != op[key]]


def unresolved(data: dict[str, Any]) -> dict[str, Any]:
    """Expose dangling evidence without inventing the missing operation."""
    data = validate(data)
    operations = {op["id"]: op for op in data["operations"]}
    known = operations.keys()
    receipt_ids = {r["id"] for r in data["receipts"]}
    withdrawn = _withdrawn(data["receipts"])
    return {
        "orphan_receipts": [
            {"receipt_id": r["id"], "operation_id": r["operation_id"], "observer": r["observer"]}
            for r in data["receipts"] if r["operation_id"] not in known and r["id"] not in withdrawn
        ],
        "unresolved_predecessors": [
            {"operation_id": op["id"], "predecessor_id": old}
            for op in data["operations"] for old in sorted(op.get("supersedes", [])) if old not in known
        ],
        "unresolved_retractions": [
            {"receipt_id": r["id"], "retracts": r["retracts"], "observer": r["observer"]}
            for r in data["receipts"] if r["kind"] == "retract" and r["retracts"] not in receipt_ids
        ],
        # Held like orphans: the operation that arrived under this ID is not the
        # one the receipt expected, so the receipt is not bound to it.
        "scope_mismatched_receipts": [
            {"receipt_id": r["id"], "operation_id": r["operation_id"], "observer": r["observer"]}
            for r in data["receipts"]
            if r["id"] not in withdrawn and r["operation_id"] in known
            and _scope_mismatch(r, operations[r["operation_id"]])
        ],
    }


def load_json(path: Path) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        obj: dict[str, Any] = {}
        for key, value in items:
            if key in obj:
                raise Invalid("duplicate JSON key")
            obj[key] = value
        return obj

    def constant(_: str) -> None:
        raise Invalid("non-finite JSON numbers are not supported")

    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise Invalid("input exceeds 8 MiB")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise Invalid("invalid UTF-8 JSON") from exc
    # Cross-record validation is done against the whole journal during import.
    if not isinstance(data, dict):
        raise Invalid("expected an object")
    return data


def _latest(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not records:
        return []
    latest = max(stamp(record["observed_at"]) for record in records)
    return sorted((record for record in records if stamp(record["observed_at"]) == latest), key=lambda r: r["id"])


def _ack_timing(ack: dict[str, Any], accepts: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """Compare only declared comparable clocks; these labels are recorder assertions.

    Observation time is not creation time. Missing/untrusted/different-clock source
    times can yield a soft note but cannot reject an otherwise matching ack.
    """
    same_object = [r for r in accepts if r.get("remote_ref") == ack.get("remote_ref")]
    comparable = [r for r in same_object if ack.get("source_trust") == "authoritative"
                  and r.get("source_trust") == "authoritative"
                  and r.get("source_origin") == ack.get("source_origin")]
    if comparable:
        earliest = min(stamp(r["source_at"]) for r in comparable)
        if stamp(ack["source_at"]) < earliest:
            return False, "ack_before_acceptance"
        return True, None
    if same_object and stamp(ack["observed_at"]) < min(stamp(r["observed_at"]) for r in same_object):
        return True, "ack_observation_order_unverified"
    source_accepts = [r for r in same_object if "source_at" in r]
    if "source_at" in ack and source_accepts and stamp(ack["source_at"]) < min(stamp(r["source_at"]) for r in source_accepts):
        return True, "ack_source_order_unverified"
    return True, None


def project(data: dict[str, Any], operation_id: str, observer: str) -> dict[str, Any]:
    data = validate(data)
    operations = {op["id"]: op for op in data["operations"]}
    if operation_id not in operations:
        raise Invalid("unknown operation")
    op = operations[operation_id]
    payload_hash = digest(op["payload"])
    own = sorted((r for r in data["receipts"] if r["operation_id"] == operation_id and r["observer"] == observer),
                 key=lambda r: (stamp(r["observed_at"]), r["id"]))
    withdrawn = _withdrawn(data["receipts"])
    own_ids = {r["id"] for r in own}
    flags: set[str] = set()
    excluded = []
    for r in own:
        mismatched = _scope_mismatch(r, op)
        if r["id"] not in withdrawn:
            flags.update(f"orphan_{key}_mismatch" for key in mismatched)
        if mismatched:
            excluded.append(r["id"])
    out_of_scope = set(excluded)
    # Retracted receipts stay in the journal; projections stop using them. Another
    # observer's retraction is testimony only: labelled, never removes evidence.
    receipts = [r for r in own if r["kind"] != "retract"
                and r["id"] not in withdrawn and r["id"] not in out_of_scope]
    retraction_reports = sorted(r["id"] for r in data["receipts"] if r["kind"] == "retract"
                                and r["operation_id"] == operation_id and r["observer"] != observer
                                and r["retracts"] in own_ids)
    direct = [r for r in receipts if r["kind"] != "report"]
    reads = [r for r in direct if r["kind"] == "readback"]
    accepted = [r for r in direct if r["kind"] == "accepted"]
    notes: set[str] = set()

    def matches(r: dict[str, Any]) -> bool:
        return (r.get("content_sha256") == payload_hash and r.get("observed_destination") == op["destination"]
                and bool(r.get("remote_ref")))

    matched = [r for r in reads if matches(r)]
    # An acceptance that reports different content or a different destination is
    # evidence about some other object: flag it and never let it anchor an ack.
    consistent_accepts = []
    for r in accepted:
        content_mismatch = bool(r.get("content_sha256") and r["content_sha256"] != payload_hash)
        destination_mismatch = bool(r.get("observed_destination") and r["observed_destination"] != op["destination"])
        if content_mismatch:
            flags.add("accepted_content_mismatch")
        if destination_mismatch:
            flags.add("accepted_destination_mismatch")
        if not content_mismatch and not destination_mismatch:
            consistent_accepts.append(r)
    # Only this observer's direct evidence can anchor object identity. No aliases,
    # container refs, matching text, or another observer's receipts are borrowed.
    anchor_records = [r for r in consistent_accepts + matched if r.get("remote_ref")]
    anchors = {r["remote_ref"] for r in anchor_records}
    # Conflicts among this observer's own anchors/reads make visibility uncertain;
    # a stray acknowledgement naming another object must not (it only fails to bind).
    read_conflict = len(anchors) > 1
    if read_conflict:
        flags.add("remote_identity_conflict")
    for r in reads:
        if not r.get("remote_ref") or not r.get("content_sha256") or not r.get("observed_destination"):
            flags.add("incomplete_readback")
        elif r["content_sha256"] != payload_hash:
            flags.add("content_mismatch")
        elif r["observed_destination"] != op["destination"]:
            flags.add("destination_mismatch")
        if anchors and r.get("remote_ref") and r["remote_ref"] not in anchors:
            flags.add("remote_identity_conflict")
            read_conflict = True
    bound_acks = []
    for r in direct:
        if r["kind"] != "ack_received":
            continue
        if r.get("acknowledged_by") != op["recipient"]:
            flags.add("wrong_acknowledger")
        elif not matches(r):
            flags.add("ack_payload_or_destination_mismatch")
        elif not anchors:
            flags.add("unbound_acknowledgement")
        elif len(anchors) != 1 or r["remote_ref"] not in anchors:
            flags.add("remote_identity_conflict")
        else:
            valid_time, timing_note = _ack_timing(r, consistent_accepts)
            if valid_time:
                bound_acks.append(r)
                if timing_note:
                    notes.add(timing_note)
            elif timing_note:
                flags.add(timing_note)
    visibility_records = [r for r in direct if r["kind"] in {"readback", "not_found"}]
    latest_reads = _latest(visibility_records)
    states = {"matching" if r["kind"] == "readback" and matches(r) else
              "mismatch" if r["kind"] == "readback" and all(r.get(k) for k in
                  ("remote_ref", "content_sha256", "observed_destination")) else "uncertain" for r in latest_reads}
    visibility = next(iter(states)) if len(states) == 1 else "uncertain"
    if len(states) > 1:
        flags.add("observation_time_conflict")
    if read_conflict and visibility == "matching":
        visibility = "uncertain"
    attempts: dict[str, set[str]] = {}
    for r in direct:
        if r.get("attempt_id") and r["kind"] in {"accepted", "blocked", "timeout"}:
            attempts.setdefault(r["attempt_id"], set()).add(r["kind"])
    if any({"accepted", "blocked"} <= events for events in attempts.values()):
        flags.add("contradictory_attempt_evidence")
    superseded_by = sorted(key for key, value in operations.items() if operation_id in value.get("supersedes", []))
    # Only explicitly related revisions belong to one lineage. Independent
    # messages to the same destination are NOT conflicting revisions.
    neighbours: dict[str, set[str]] = {}
    for key, value in operations.items():
        for predecessor in value.get("supersedes", []):
            neighbours.setdefault(key, set()).add(predecessor)
            neighbours.setdefault(predecessor, set()).add(key)
    component, todo = set(), [operation_id]
    while todo:
        key = todo.pop()
        if key not in component:
            component.add(key)
            todo.extend(neighbours.get(key, set()) - component)
    referenced = {key for value in operations.values() for key in value.get("supersedes", [])}
    tips = sorted((component & operations.keys()) - referenced)
    if len(tips) > 1:
        flags.add("multiple_current_operations")
    # Resolve each attempt first: a late-recovered acceptance resolves that attempt's
    # timeout even when the service's observed_at precedes the caller's timeout.
    resolved = {key: "uncertain" if {"accepted", "blocked"} <= kinds else "accepted" if "accepted" in kinds
                else "blocked" if "blocked" in kinds else "timeout" for key, kinds in attempts.items()}
    latest_attempt = _latest([r for r in direct if r["kind"] in {"accepted", "blocked", "timeout"}])
    attempt_results = {resolved[r["attempt_id"]] for r in latest_attempt}
    return {
        "operation_id": operation_id, "observer": observer, "payload_sha256": payload_hash,
        "accepted": bool(accepted), "readback_match": bool(matched),
        "readback_receipts": [r["id"] for r in matched],
        "visibility": visibility, "visibility_as_of": latest_reads[0]["observed_at"] if latest_reads else None,
        "visibility_evidence": [r["id"] for r in latest_reads],
        "acknowledged": bool(bound_acks) and not read_conflict,
        "ack_receipts": [r["id"] for r in bound_acks],
        "reports": [r["id"] for r in receipts if r["kind"] == "report"],
        "retracted_receipts": sorted(own_ids & withdrawn),
        "retraction_reports": retraction_reports, "excluded_receipts": excluded,
        # Legacy or hashless evidence bound by operation ID alone, not scoped proof.
        "unscoped_receipts": [r["id"] for r in receipts if r["kind"] != "report"
                              and "content_sha256" not in r and "expected_action" not in r],
        "ever_blocked": any(r["kind"] == "blocked" for r in direct),
        "latest_attempt_result": next(iter(attempt_results)) if len(attempt_results) == 1 else "uncertain",
        "superseded_by": superseded_by, "current_operation_ids": tips,
        "unresolved_predecessors": sorted(set(op.get("supersedes", [])) - operations.keys()),
        "flags": sorted(flags), "notes": sorted(notes), "permission_to_act": None, "automatic_retry": False,
        "interpretation": "As-of evidence from one observer; not delivery, present availability, or permission guarantees.",
    }


def capability(data: dict[str, Any], *, subject: str, observer: str, action: str,
               context: str, environment: str, at: str) -> dict[str, Any]:
    data = validate(data)
    cutoff = stamp(at)
    selection = {"subject": subject, "observer": observer, "action": action, "context": context, "environment": environment}
    rows = sorted((r for r in data["observations"] if all(r[key] == value for key, value in selection.items())
                   and stamp(r["observed_at"]) <= cutoff and stamp(r["recorded_at"]) <= cutoff),
                  key=lambda r: (stamp(r["observed_at"]), r["id"]))
    latest = _latest([r for r in rows if r["basis"] == "direct"])
    outcomes = {r["outcome"] for r in latest}
    outcome = next(iter(outcomes)) if len(outcomes) == 1 else "unknown"
    return {**selection, "as_of": at, "last_observed_outcome": outcome,
            "observation_ids": [r["id"] for r in latest],
            "observed_at": latest[0]["observed_at"] if latest else None,
            "needs_recheck": not latest or any(cutoff >= stamp(r["recheck_after"]) for r in latest),
            "conflicting_observations": len(outcomes) > 1,
            "reports": [r["id"] for r in rows if r["basis"] != "direct"],
            "permission_to_act": None}


SCHEMA = """
CREATE TABLE records (
  kind TEXT NOT NULL CHECK(kind IN ('operations','receipts','observations')),
  id TEXT NOT NULL, body TEXT NOT NULL, imported_at TEXT NOT NULL,
  PRIMARY KEY(kind,id)
);
CREATE TRIGGER no_updates BEFORE UPDATE ON records BEGIN
  SELECT RAISE(ABORT,'append-only journal');
END;
CREATE TRIGGER no_deletes BEFORE DELETE ON records BEGIN
  SELECT RAISE(ABORT,'append-only journal');
END;
CREATE TRIGGER no_replace BEFORE INSERT ON records
WHEN EXISTS (SELECT 1 FROM records WHERE kind = NEW.kind AND id = NEW.id) BEGIN
  SELECT RAISE(ABORT,'append-only journal');
END;
"""


def initialize(path: Path) -> None:
    # Never truncate or accidentally initialise an unrelated database.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    connection = sqlite3.connect(path)
    try:
        with connection:
            connection.execute("PRAGMA synchronous=EXTRA")
            connection.executescript(SCHEMA)
            connection.execute(f"PRAGMA application_id={APPLICATION_ID}")
            connection.execute("PRAGMA user_version=1")
    finally:
        # The transaction context does not close a sqlite3 connection. Close
        # explicitly, also on failure; retain a failed file for inspection.
        connection.close()


# Compare against the exact definitions used by initialize(). SQLite omits the
# statement's trailing semicolon in sqlite_schema. Equivalent hand-edited SQL is
# deliberately not accepted: read/export remain available for explicit recovery.
GUARD_DEFINITIONS = {match.group(1): match.group(0).strip().removesuffix(";")
                     for match in re.finditer(r"CREATE TRIGGER (\w+)\b.*?END;", SCHEMA, re.DOTALL)}


def journal_guards(connection: sqlite3.Connection) -> dict[str, list[str]]:
    """Verify expected guard definitions; not authentication of a hostile file owner."""
    definitions = dict(connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='trigger'"))
    present = sorted(set(GUARDS) & definitions.keys())
    mismatched = [name for name in present if definitions[name] != GUARD_DEFINITIONS[name]]
    return {"present": present, "missing": sorted(set(GUARDS) - definitions.keys()),
            "mismatched": mismatched, "unexpected": sorted(definitions.keys() - set(GUARDS))}


def _require_guards(connection: sqlite3.Connection) -> None:
    guards = journal_guards(connection)
    if guards["missing"] or guards["mismatched"] or guards["unexpected"]:
        raise Invalid("journal guards are missing, changed or unexpected; export and import into a new journal before writing")


@contextmanager
def journal(path: Path, *, write: bool = False) -> Iterator[sqlite3.Connection]:
    mode = "rw" if write else "ro"
    connection = sqlite3.connect(path.resolve().as_uri() + f"?mode={mode}", uri=True, isolation_level=None, timeout=5)
    try:
        if connection.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
            raise Invalid("not a Porchlight journal")
        if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise Invalid("unsupported journal schema")
        if write:
            _require_guards(connection)
        connection.execute("PRAGMA synchronous=EXTRA")
        if not write:
            connection.execute("PRAGMA query_only=ON")
        yield connection
    finally:
        connection.close()


def snapshot(connection: sqlite3.Connection) -> dict[str, Any]:
    data: dict[str, Any] = {"schema_version": 1, **{key: [] for key in TABLES}}
    # One SELECT provides a consistent snapshot across record types.
    for kind, body in connection.execute("SELECT kind, body FROM records ORDER BY kind,id"):
        data[kind].append(json.loads(body))
    return data


def import_data(path: Path, incoming: dict[str, Any]) -> dict[str, int]:
    if not isinstance(incoming, dict) or incoming.keys() - {"schema_version", *TABLES}:
        raise Invalid("invalid dataset envelope")
    if type(incoming.get("schema_version")) is not int or incoming["schema_version"] != 1:
        raise Invalid("schema_version must be the integer 1")
    for table in TABLES:
        if not isinstance(incoming.get(table, []), list) or len(incoming.get(table, [])) > MAX_RECORDS:
            raise Invalid("invalid record collection")
    with journal(path, write=True) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            # Recheck under the write lock, not just before BEGIN IMMEDIATE.
            _require_guards(connection)
            existing = snapshot(connection)
            combined = {"schema_version": 1, **{key: existing[key] + incoming.get(key, []) for key in TABLES}}
            combined = validate(combined)
            inserted = 0
            imported = now()
            for table in TABLES:
                previous = {r["id"] for r in existing[table]}
                for record in combined[table]:
                    if record["id"] not in previous:
                        cursor = connection.execute("INSERT INTO records VALUES (?,?,?,?)",
                                                    (table, record["id"], canonical(record), imported))
                        if cursor.rowcount != 1:
                            raise Invalid("journal insert was not recorded; transaction rolled back")
                        inserted += 1
            connection.execute("COMMIT")
            return {"inserted": inserted, "unchanged": sum(len(v) for k, v in combined.items() if k in TABLES) - inserted}
        except BaseException:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def read_data(path: Path) -> dict[str, Any]:
    with journal(path) as connection:
        return validate(snapshot(connection))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("init", "import", "status", "capability", "export", "check", "unresolved"):
        child = sub.add_parser(command)
        child.add_argument("--db", type=Path, required=True)
        if command == "import":
            child.add_argument("input", type=Path)
        if command == "status":
            child.add_argument("operation_id")
            child.add_argument("--observer", required=True)
        if command == "capability":
            for field in ("subject", "observer", "action", "context", "environment", "at"):
                child.add_argument("--" + field, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            initialize(args.db)
            result: Any = {"initialized": True, "schema_version": 1}
        elif args.command == "import":
            result = import_data(args.db, load_json(args.input))
        else:
            data = read_data(args.db)
            if args.command == "status":
                result = project(data, args.operation_id, args.observer)
            elif args.command == "capability":
                result = capability(data, **{key: getattr(args, key) for key in
                    ("subject", "observer", "action", "context", "environment", "at")})
            elif args.command == "unresolved":
                result = unresolved(data)
            elif args.command == "export":
                result = data  # Explicit command: includes payloads; keep this output private.
            else:
                with journal(args.db) as connection:
                    checks = [row[0] for row in connection.execute("PRAGMA integrity_check")]
                    guards = journal_guards(connection)
                if checks != ["ok"]:
                    raise Invalid("SQLite integrity check failed")
                result = {"integrity": "ok", "append_only_guards": guards,
                          "records": {key: len(data[key]) for key in TABLES}, **unresolved(data)}
        print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
        return 0
    except (Invalid, OSError, sqlite3.Error, ValueError) as exc:
        # Do not echo payloads or SQL parameters in diagnostics.
        print(f"porchlight: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
