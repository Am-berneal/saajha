"""Munshi agent: plans a case, acts through tools, keeps case memory, recovers from failures,
and pauses for human approval before any legal, money or personal-data action.

Channels (WhatsApp, SMS, voice call) are SIMULATED in the hackathon build: the buyer's
behaviour comes from BUYER_WORLD below, so the demo is repeatable. The agent logic,
memory, recovery and approval gates are real code.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from . import ai, db, ledger, rules

ALLOWED_ACTIONS = ["confirm_delivery", "start_clock", "schedule_legal_reminder"]
CHANNEL_ORDER = ["whatsapp", "sms", "voice_call", "janai_cafe"]
NEEDS_APPROVAL = {"schedule_legal_reminder": "legal commitment", "early_cash": "money", "share_bank_data": "personal data"}

# Simulated outside world (labelled SIMULATED in the UI)
BUYER_WORLD = {
    "Gupta Retail": {"whatsapp": False, "sms_reply": False, "call_after_hour": 18, "answers_call": True},
    "Sharma Traders Pvt Ltd": {"whatsapp": True, "sms_reply": True, "call_after_hour": 10, "answers_call": True},
    "Bansal Stores": {"whatsapp": True, "sms_reply": False, "call_after_hour": 11, "answers_call": False},
}
SEED_MEMORY = {
    "Gupta Retail": [
        {"key": "best_call_time", "fact": "Buyer answers calls after 6 pm", "source": "past calls"},
        {"key": "pays_on_day", "fact": "Last 3 invoices paid on day 41–44", "source": "ledger history"},
        {"key": "tone", "fact": "Meena prefers reminders in Hindi, polite tone", "source": "owner setting"},
    ],
}


def _now(case) -> datetime:
    return datetime.fromisoformat(case["clock"])


def _save(case) -> dict:
    db.exec_("INSERT OR REPLACE INTO cases(id,data,updated) VALUES (?,?,?)",
             (case["id"], db.dumps(case), datetime.now().isoformat(timespec="seconds")))
    return case


def get(case_id: str) -> dict | None:
    rows = db.q("SELECT data FROM cases WHERE id=?", (case_id,))
    import json
    return json.loads(rows[0]["data"]) if rows else None


def list_cases() -> list[dict]:
    import json
    return [json.loads(r["data"]) for r in db.q("SELECT data FROM cases ORDER BY updated DESC")]


def _log(case, action, tool, status, detail, **extra):
    case["log"].append({"n": len(case["log"]) + 1, "action": action, "tool": tool, "status": status,
                        "detail": detail, "at": case["clock"], **extra})


def _remember(case, key, fact, source):
    if not any(m["key"] == key for m in case["memory"]):
        case["memory"].append({"key": key, "fact": fact, "source": source, "learned": case["clock"]})


def _has(case, key) -> bool:
    return any(m["key"] == key for m in case["memory"])


def create_case(invoice_id: str, buyer: str, buyer_gstin: str, amount: float, agreed_days: int | None = 45,
                start: str | None = None) -> dict:
    case = {
        "id": "C-" + uuid.uuid4().hex[:6].upper(), "invoice_id": invoice_id, "buyer": buyer,
        "buyer_gstin": buyer_gstin, "amount": amount, "agreed_days": agreed_days,
        "goal": "Get delivery confirmed, start the 45-day clock, then get paid by the due date",
        "status": "planned", "clock": start or datetime(2026, 11, 15, 10, 5).isoformat(),
        "memory": [dict(m, learned="before case") for m in SEED_MEMORY.get(buyer, [])],
        "plan": None, "log": [], "approval": None, "accepted_on": None, "due": None,
    }
    if not ledger.invoice_events(invoice_id):
        ledger.append(invoice_id, "InvoiceCreated",
                      {"amount": amount, "buyer": buyer, "buyer_gstin": buyer_gstin, "terms_days": agreed_days},
                      "supplier")
    _plan(case)
    return _save(case)


def _plan(case) -> None:
    plan, planner, reason = list(ALLOWED_ACTIONS), "policy", "Default policy for a new B2B invoice."
    if ai.ai_available():
        try:
            out, _ = ai.generate("agent-plan", [{"text": (
                "You are the planner of a compliance agent for an Indian micro supplier. Choose an ordered subset of "
                f"these actions only: {ALLOWED_ACTIONS}. Case: {db.dumps({k: case[k] for k in ('buyer', 'amount', 'memory')})}. "
                "Return JSON {\"steps\": [..], \"reason\": \"one sentence\"}.")}], ai.PlanOut)
            steps = [s for s in out.steps if s in ALLOWED_ACTIONS]
            if steps and steps[0] == "confirm_delivery":
                plan, planner, reason = steps, "gemini (validated by policy)", out.reason
        except Exception as e:  # planner failure → policy
            reason = f"AI planner unavailable ({str(e)[:60]}); used default policy."
    case["plan"] = {"steps": plan, "planner": planner, "reason": reason}
    _log(case, "plan", planner, "ok", " → ".join(plan), reason=reason)


# ---------------------------------------------------------------- tools (simulated channels)
def _tool_whatsapp(case):
    w = BUYER_WORLD.get(case["buyer"], {})
    if not w.get("whatsapp", True):
        raise RuntimeError("Number not on WhatsApp")
    return {"confirmed": True, "via": "WhatsApp button"}


def _tool_sms(case):
    w = BUYER_WORLD.get(case["buyer"], {})
    case["clock"] = (_now(case) + timedelta(hours=24)).isoformat()
    if not w.get("sms_reply", True):
        return {"confirmed": False, "note": "No reply in 24 hours"}
    return {"confirmed": True, "via": "SMS link"}


def _tool_voice_call(case):
    w = BUYER_WORLD.get(case["buyer"], {})
    now = _now(case)
    hour = w.get("call_after_hour", 10) if _has(case, "best_call_time") else now.hour
    call_at = now.replace(hour=max(now.hour, hour), minute=15 if hour >= 18 else now.minute)
    case["clock"] = call_at.isoformat()
    if not w.get("answers_call", True) or call_at.hour < w.get("call_after_hour", 0):
        return {"confirmed": False, "note": f"No answer at {call_at:%H:%M}"}
    return {"confirmed": True, "via": f"Voice call at {call_at:%H:%M}, buyer pressed 1"}


def _tool_janai_cafe(case):
    return {"confirmed": False, "note": "Task created for the nearest JanAI Café operator", "handoff": True}


TOOLS = {"whatsapp": _tool_whatsapp, "sms": _tool_sms, "voice_call": _tool_voice_call, "janai_cafe": _tool_janai_cafe}


# ---------------------------------------------------------------- actions
def _confirm_delivery(case) -> bool:
    for ch in CHANNEL_ORDER:
        if ch == "whatsapp" and _has(case, "whatsapp_invalid"):
            _log(case, "confirm_delivery", ch, "skipped", "Skipped: memory says this number is not on WhatsApp")
            continue
        for attempt in (1, 2):
            try:
                res = TOOLS[ch](case)
            except Exception as e:
                if attempt == 1 and "timeout" in str(e).lower():
                    continue  # transient → retry once
                _log(case, "confirm_delivery", ch, "fail", str(e), recovered_by="next channel")
                if ch == "whatsapp":
                    _remember(case, "whatsapp_invalid", "Buyer's number is not on WhatsApp", "learned from failure")
                break
            if res.get("confirmed"):
                _log(case, "confirm_delivery", ch, "ok", res["via"],
                     memory_used="best_call_time" if ch == "voice_call" and _has(case, "best_call_time") else None)
                case["accepted_on"] = _now(case).date().isoformat()
                ledger.append(case["invoice_id"], "BuyerAccepted",
                              {"amount": case["amount"], "accepted_on": case["accepted_on"], "channel": ch,
                               "terms_days": case["agreed_days"]}, "buyer")
                return True
            _log(case, "confirm_delivery", ch, "wait" if not res.get("handoff") else "handoff", res.get("note", ""))
            if res.get("handoff"):
                return False
            break
    return False


def _start_clock(case) -> None:
    due = rules.payment_due_date(date.fromisoformat(case["accepted_on"]), case["agreed_days"])
    case["due"] = due.value.isoformat()
    _log(case, "start_clock", "rules-engine", "ok", f"Pay by {due.value:%d %b %Y}", rule=due.to_dict())


def _schedule_legal_reminder(case) -> None:
    due = date.fromisoformat(case["due"])
    send_on = due - timedelta(days=5)
    draft = ai.draft_reminder(case["buyer"], case["invoice_id"], case["amount"], f"{due:%d %b %Y}")
    case["approval"] = {"action": "schedule_legal_reminder", "reason": NEEDS_APPROVAL["schedule_legal_reminder"],
                        "send_on": send_on.isoformat(), "text": draft["text"], "drafted_by": draft["source"],
                        "legal_basis": "Income-tax Act 2025 Sec 37(2)(g); MSMED Act Sec 15"}
    case["status"] = "waiting_approval"
    _log(case, "schedule_legal_reminder", "approval-gate", "lock",
         f"Waiting for the owner's OK (legal commitment). Proposed send date {send_on:%d %b}.")


def run(case_id: str) -> dict:
    case = get(case_id)
    if case is None:
        raise KeyError(case_id)
    if case["status"] in ("waiting_approval", "scheduled", "done"):
        return case
    case["status"] = "running"
    for step in case["plan"]["steps"]:
        if step == "confirm_delivery" and not case["accepted_on"]:
            if not _confirm_delivery(case):
                case["status"] = "handed_off"
                return _save(case)
        elif step == "start_clock" and not case["due"]:
            _start_clock(case)
        elif step == "schedule_legal_reminder":
            _schedule_legal_reminder(case)
            return _save(case)
    case["status"] = "done"
    return _save(case)


def decide(case_id: str, approve: bool, edited_text: str | None = None) -> dict:
    case = get(case_id)
    if case is None or not case.get("approval"):
        raise KeyError(case_id)
    if approve:
        text = edited_text or case["approval"]["text"]
        ledger.append(case["invoice_id"], "ReminderApproved",
                      {"send_on": case["approval"]["send_on"], "text": text}, "supplier")
        _log(case, "schedule_legal_reminder", "owner", "ok",
             f"Approved by owner · reminder scheduled for {date.fromisoformat(case['approval']['send_on']):%d %b}")
        case["status"] = "scheduled"
    else:
        _log(case, "schedule_legal_reminder", "owner", "skipped", "Owner declined · no reminder will be sent")
        case["status"] = "done"
    case["approval"] = None
    return _save(case)
