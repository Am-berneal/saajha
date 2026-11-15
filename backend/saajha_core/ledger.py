"""Signed, hash-chained event ledger.

Every event is canonicalised to JSON, chained to the previous event with SHA-256,
and signed with the Ed25519 key of the party who performed it (supplier or buyer).
Changing any earlier byte breaks the hash and the signature, and orphans every later block.

Demo keys are generated locally in data/keys. In production each party would hold its own key.
"""
from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from . import db

GENESIS = "0" * 64
KEY_DIR = db.DATA_DIR / "keys"
PARTIES = ("supplier", "buyer", "saajha")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _key(party: str) -> Ed25519PrivateKey:
    KEY_DIR.mkdir(parents=True, exist_ok=True)
    path = KEY_DIR / f"{party}.pem"
    if path.exists():
        return serialization.load_pem_private_key(path.read_bytes(), password=None)
    k = Ed25519PrivateKey.generate()
    path.write_bytes(k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                     serialization.NoEncryption()))
    return k


def public_key_hex(party: str) -> str:
    pub = _key(party).public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return pub.hex()


def _block_hash(prev_hash: str, body: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(body)).encode("utf-8")).hexdigest()


def append(invoice_id: str, type_: str, payload: dict, signer: str) -> dict:
    if signer not in PARTIES:
        raise ValueError("unknown signer")
    rows = db.q("SELECT hash FROM events ORDER BY seq DESC LIMIT 1")
    prev = rows[0]["hash"] if rows else GENESIS
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    body = {"invoice_id": invoice_id, "type": type_, "payload": payload, "ts": ts, "signer": signer}
    h = _block_hash(prev, body)
    sig = _key(signer).sign(bytes.fromhex(h)).hex()
    seq = db.exec_("INSERT INTO events(invoice_id,type,payload,ts,signer,prev_hash,hash,signature) VALUES (?,?,?,?,?,?,?,?)",
                   (invoice_id, type_, canonical(payload), ts, signer, prev, h, sig))
    return {"seq": seq, **body, "prev_hash": prev, "hash": h, "signature": sig}


def _rows_to_events(rows) -> list[dict]:
    return [{"seq": r["seq"], "invoice_id": r["invoice_id"], "type": r["type"], "payload": json.loads(r["payload"]),
             "ts": r["ts"], "signer": r["signer"], "prev_hash": r["prev_hash"], "hash": r["hash"],
             "signature": r["signature"]} for r in rows]


def all_events() -> list[dict]:
    return _rows_to_events(db.q("SELECT * FROM events ORDER BY seq"))


def invoice_events(invoice_id: str) -> list[dict]:
    return _rows_to_events(db.q("SELECT * FROM events WHERE invoice_id=? ORDER BY seq", (invoice_id,)))


def verify_events(events: list[dict], full_chain: bool = True) -> dict:
    """Recompute hashes and check signatures. Returns per-block status."""
    blocks, ok, broken_at = [], True, None
    prev_expected = events[0]["prev_hash"] if events and not full_chain else GENESIS
    for i, e in enumerate(events):
        body = {k: e[k] for k in ("invoice_id", "type", "payload", "ts", "signer")}
        recomputed = _block_hash(e["prev_hash"], body)
        hash_ok = recomputed == e["hash"]
        link_ok = (e["prev_hash"] == prev_expected) if (full_chain or i > 0) else True
        try:
            Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex(e["signer"]))).verify(
                bytes.fromhex(e["signature"]), bytes.fromhex(recomputed))
            sig_ok = True
        except (InvalidSignature, ValueError):
            sig_ok = False
        good = hash_ok and link_ok and sig_ok and ok
        if not (hash_ok and link_ok and sig_ok) and broken_at is None:
            broken_at = i
        status = "intact" if good else ("altered" if broken_at == i else "orphaned")
        blocks.append({"seq": e.get("seq"), "type": e["type"], "signer": e["signer"], "hash": e["hash"],
                       "recomputed": recomputed, "hash_ok": hash_ok, "link_ok": link_ok, "signature_ok": sig_ok,
                       "status": status})
        ok = good
        prev_expected = e["hash"]
    return {"ok": ok and broken_at is None, "broken_at": broken_at, "blocks": blocks}


def verify_invoice(invoice_id: str) -> dict:
    chain = verify_events(all_events())
    mine = [b for b in chain["blocks"] if b["seq"] in {e["seq"] for e in invoice_events(invoice_id)}]
    return {"invoice_id": invoice_id, "ok": chain["ok"] and all(b["status"] == "intact" for b in mine) and bool(mine),
            "blocks": mine, "chain_ok": chain["ok"], "chain_length": len(chain["blocks"]),
            "public_keys": {p: public_key_hex(p) for p in ("supplier", "buyer")}}


def tamper_test(invoice_id: str, field: str = "amount", new_value=12000) -> dict:
    """Simulate an attacker editing an event in a COPY of the ledger. The real ledger is untouched."""
    events = copy.deepcopy(all_events())
    target = None
    for e in events:
        if e["invoice_id"] == invoice_id and field in e["payload"]:
            target = e
    if target is None:
        return {"error": f"No event for {invoice_id} has field '{field}'"}
    old = target["payload"][field]
    target["payload"][field] = new_value
    result = verify_events(events)
    seqs = {e["seq"] for e in events if e["invoice_id"] == invoice_id}
    return {"invoice_id": invoice_id, "field": field, "old_value": old, "new_value": new_value,
            "altered_seq": target["seq"], "detected": not result["ok"],
            "blocks": [b for b in result["blocks"] if b["seq"] in seqs or b["status"] != "intact"],
            "real_ledger_ok": verify_events(all_events())["ok"]}


def stats() -> dict:
    ev = all_events()
    v = verify_events(ev)
    return {"events": len(ev), "chain_ok": v["ok"], "head": ev[-1]["hash"] if ev else GENESIS}
