"""Saajha backend (FastAPI).

Run:  python app.py   → open http://localhost:8000
Serves the prototype (../index.html) and the live API on the same origin.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
except Exception:
    pass
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, File, Form, HTTPException, UploadFile  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from saajha_core import agent, ai, db, ims, ledger, rules  # noqa: E402

SUPPLIER_GSTIN = "27AAOFM4821C1Z4"  # Meena Tailoring Works (sample)
STARTED = datetime.now()
WEB_ROOT = ROOT.parent

app = FastAPI(title="Saajha API", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ------------------------------------------------------------------ helpers
def _finalise_invoice(draft: dict) -> dict:
    """AI/parser draft → rules engine computes rates, tax and totals (never the AI)."""
    buyer = draft.get("buyer") or {}
    items = [i for i in draft.get("items", []) if i.get("qty") and i.get("rate")]
    computed = rules.compute_invoice(items, SUPPLIER_GSTIN, buyer.get("gstin") or SUPPLIER_GSTIN)
    overrides = []
    for line, src in zip(computed["lines"], items):
        ai_rate = src.get("gst_rate")
        if ai_rate is not None and ai_rate != line["gst_rate"]:
            overrides.append({"item": line["description"], "ai_said": ai_rate, "rules_say": line["gst_rate"]})
    return {**draft, "invoice": computed, "rule_overrides": overrides}


# ------------------------------------------------------------------ status
@app.get("/api/status")
def status():
    test_report = db.DATA_DIR / "test_report.json"
    tests = json.loads(test_report.read_text()) if test_report.exists() else None
    cases = agent.list_cases()
    return {
        "backend": "running", "started": STARTED.isoformat(timespec="seconds"),
        "uptime_s": int((datetime.now() - STARTED).total_seconds()),
        "ai": {"provider": "Google Gemini", "configured": ai.api_key() is not None, "available": ai.ai_available(),
               "model": ai.model_name(), "stats": ai.call_stats()},
        "rules": {"version": rules.RULESET_VERSION, "rules": len(rules.RULE_REGISTRY), "tests": tests},
        "ledger": ledger.stats(),
        "agent": {"cases": len(cases), "waiting_approval": sum(c["status"] == "waiting_approval" for c in cases)},
        "simulated": ["GST portal / GSP filing", "IMS portal data", "TReDS / lender", "WhatsApp / SMS / voice delivery",
                      "Account Aggregator"],
    }


# ------------------------------------------------------------------ invoices
class TextIn(BaseModel):
    text: str


@app.post("/api/invoice/from-text")
def invoice_from_text(body: TextIn):
    return _finalise_invoice(ai.invoice_from_text(body.text))


@app.post("/api/invoice/from-audio")
async def invoice_from_audio(file: UploadFile = File(...), transcript: str = Form("")):
    data = await file.read()
    if len(data) > 8_000_000:
        raise HTTPException(413, "Audio too long; keep voice notes under 1 minute.")
    return _finalise_invoice(ai.invoice_from_media(data, file.content_type or "audio/webm", "voice", transcript))


@app.post("/api/invoice/from-image")
async def invoice_from_image(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > 10_000_000:
        raise HTTPException(413, "Image too large.")
    return _finalise_invoice(ai.invoice_from_media(data, file.content_type or "image/jpeg", "photo"))


class IssueIn(BaseModel):
    invoice_id: str
    buyer: str
    buyer_gstin: Optional[str] = None
    amount: float
    terms_days: Optional[int] = 45


@app.post("/api/invoice/issue")
def issue_invoice(body: IssueIn):
    ev = ledger.append(body.invoice_id, "InvoiceCreated",
                       {"amount": body.amount, "buyer": body.buyer, "buyer_gstin": body.buyer_gstin,
                        "terms_days": body.terms_days}, "supplier")
    return {"event": ev}


class AcceptIn(BaseModel):
    invoice_id: str
    accepted_on: Optional[str] = None


@app.post("/api/invoice/accept")
def accept_invoice(body: AcceptIn):
    evs = ledger.invoice_events(body.invoice_id)
    created = next((e for e in evs if e["type"] == "InvoiceCreated"), None)
    if not created:
        raise HTTPException(404, "Invoice not issued yet")
    acc = date.fromisoformat(body.accepted_on) if body.accepted_on else date.today()
    terms = created["payload"].get("terms_days")
    due = rules.payment_due_date(acc, terms)
    ev = ledger.append(body.invoice_id, "BuyerAccepted",
                       {"amount": created["payload"]["amount"], "accepted_on": acc.isoformat(), "channel": "app",
                        "terms_days": terms}, "buyer")
    return {"event": ev, "due": due.to_dict(), "verify": ledger.verify_invoice(body.invoice_id)}


# ------------------------------------------------------------------ rules
@app.get("/api/rules/payment")
def rules_payment(amount: float, accepted_on: str, terms_days: Optional[int] = 45, today: Optional[str] = None,
                  bank_rate: float = rules.DEFAULT_BANK_RATE):
    acc = date.fromisoformat(accepted_on)
    due = rules.payment_due_date(acc, terms_days)
    t = date.fromisoformat(today) if today else date.today()
    late = max(0, (t - due.value).days)
    return {"due": due.to_dict(), "days_left": rules.days_left(due.value, t), "days_late": late,
            "interest": rules.delayed_payment_interest(amount, late, bank_rate).to_dict()}


@app.get("/api/rules/interest")
def rules_interest(amount: float, days_late: int, bank_rate: float = rules.DEFAULT_BANK_RATE):
    return rules.delayed_payment_interest(amount, days_late, bank_rate).to_dict()


# ------------------------------------------------------------------ notice
@app.post("/api/notice/explain")
async def notice_explain(file: Optional[UploadFile] = File(None), text: str = Form("")):
    data = await file.read() if file else None
    out = ai.explain_notice(data, file.content_type if file else None, text or None)
    if out.get("notice_date"):
        try:
            d = rules.notice_reply_deadline(date.fromisoformat(out["notice_date"]), out.get("reply_within_days") or 30)
            out["deadline"] = d.to_dict()
            out["days_left"] = (d.value - date.today()).days
        except ValueError:
            pass
    return out


# ------------------------------------------------------------------ ledger / proof
@app.get("/api/ledger/verify/{invoice_id}")
def verify(invoice_id: str):
    return ledger.verify_invoice(invoice_id)


class TamperIn(BaseModel):
    invoice_id: str
    field: str = "amount"
    value: float = 12000


@app.post("/api/ledger/tamper-test")
def tamper(body: TamperIn):
    return ledger.tamper_test(body.invoice_id, body.field, body.value)


@app.get("/api/ledger/events/{invoice_id}")
def events(invoice_id: str):
    return ledger.invoice_events(invoice_id)


# ------------------------------------------------------------------ agent
class CaseIn(BaseModel):
    invoice_id: str = "INV-0151"
    buyer: str = "Gupta Retail"
    buyer_gstin: str = "27AAGFG7710K1Z2"
    amount: float = 12500
    terms_days: Optional[int] = 45


@app.post("/api/agent/cases")
def new_case(body: CaseIn):
    inv = body.invoice_id
    if ledger.invoice_events(inv):  # fresh invoice id per demo run
        inv = f"{inv}-{int(time.time()) % 100000}"
    return agent.create_case(inv, body.buyer, body.buyer_gstin, body.amount, body.terms_days)


@app.post("/api/agent/cases/{case_id}/run")
def run_case(case_id: str):
    try:
        return agent.run(case_id)
    except KeyError:
        raise HTTPException(404, "case not found")


class DecisionIn(BaseModel):
    approve: bool
    text: Optional[str] = None


@app.post("/api/agent/cases/{case_id}/decision")
def decide(case_id: str, body: DecisionIn):
    try:
        return agent.decide(case_id, body.approve, body.text)
    except KeyError:
        raise HTTPException(404, "no pending approval")


@app.get("/api/agent/cases")
def cases():
    return agent.list_cases()


# ------------------------------------------------------------------ IMS
@app.get("/api/ims/match")
def ims_match():
    p, b, r = ims.sample_data()
    return ims.match(p, b, r)


# ------------------------------------------------------------------ AI monitoring / eval
@app.get("/api/ai/calls")
def ai_calls(limit: int = 30):
    return {"calls": ai.recent_calls(limit), "stats": ai.call_stats()}


@app.get("/api/eval/latest")
def eval_latest():
    out = {}
    for eng in ("rules", "gemini"):
        p = db.DATA_DIR / f"eval_{eng}.json"
        out[eng] = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {
            "measured": False, "message": f"Not measured yet. Run: python eval/run_eval.py --engine {eng}"}
    return out


# ------------------------------------------------------------------ demo seed
def seed_demo() -> None:
    """Make sure the demo invoice INV-0142 exists and is signed by both parties."""
    if not ledger.invoice_events("INV-0142"):
        ledger.append("INV-0142", "InvoiceCreated",
                      {"amount": 21000, "buyer": "Sharma Traders Pvt Ltd", "buyer_gstin": "27AABCS1429P1ZX",
                       "terms_days": 45}, "supplier")
        ledger.append("INV-0142", "BuyerAccepted",
                      {"amount": 21000, "accepted_on": "2026-11-15", "channel": "WhatsApp button", "terms_days": 45},
                      "buyer")
        ledger.append("INV-0142", "AddedToGSTR1", {"period": "2026-11", "simulated": True}, "saajha")


seed_demo()


# ------------------------------------------------------------------ static prototype
@app.get("/")
def index():
    return FileResponse(WEB_ROOT / "index.html")


if (WEB_ROOT / "assets").exists():
    app.mount("/assets", StaticFiles(directory=WEB_ROOT / "assets"), name="assets")
app.mount("/samples", StaticFiles(directory=ROOT / "samples"), name="samples")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8000"))
    print(f"\n  Saajha running → http://localhost:{port}\n  Gemini key: {'set' if ai.api_key() else 'NOT set (offline fallbacks active)'}\n")
    uvicorn.run(app, host="127.0.0.1", port=port)
