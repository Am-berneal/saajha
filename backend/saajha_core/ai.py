"""Gemini client (REST) with schema validation, one retry, fallbacks and call logging.

The AI only reads (voice, photo, notice) and talks (explanations, drafts).
Amounts, rates and deadlines are recomputed by the rules engine afterwards.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

import requests
from pydantic import BaseModel, Field, ValidationError

from . import db
from .numparse import parse_bill, resolve_buyer

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
TIMEOUT_S = float(os.environ.get("SAAJHA_AI_TIMEOUT", "20"))


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")


def api_key() -> Optional[str]:
    k = os.environ.get("GEMINI_API_KEY", "").strip()
    return k or None


def ai_available() -> bool:
    return api_key() is not None and os.environ.get("SAAJHA_FORCE_OFFLINE", "") != "1"


# ---------------------------------------------------------------------------
# Output schemas (validated with pydantic)
# ---------------------------------------------------------------------------
class HsnOption(BaseModel):
    hsn: str
    p: float = Field(ge=0, le=1)


class ItemOut(BaseModel):
    description: str
    hsn: str
    qty: Optional[float] = None
    rate: Optional[float] = None
    confidence: dict = Field(default_factory=dict)
    hsn_options: list[HsnOption] = Field(default_factory=list)


class InvoiceOut(BaseModel):
    buyer_name: Optional[str] = None
    items: list[ItemOut] = Field(default_factory=list)
    transcript: Optional[str] = None
    language: Optional[str] = None
    questions: list[str] = Field(default_factory=list)
    buyer_confidence: float = 0.0


class NoticeOut(BaseModel):
    form: Optional[str] = None
    notice_date: Optional[str] = Field(None, description="YYYY-MM-DD as printed")
    reply_within_days: Optional[int] = None
    amount: Optional[float] = None
    sections: list[str] = Field(default_factory=list)
    summary_hi: str
    summary_en: str
    next_steps_hi: list[str] = Field(default_factory=list)
    needs_signature: bool = False


class PlanOut(BaseModel):
    steps: list[str]
    reason: str


INVOICE_PROMPT = """You read a micro supplier's bill (spoken Hindi/Hinglish or a photo of a handwritten bill).
Return ONLY JSON with this shape:
{"buyer_name": str|null, "buyer_confidence": 0..1, "transcript": str, "language": "hi"|"hi-Latn"|"en"|other,
 "items": [{"description": str (short English, e.g. "Cotton kurta"), "hsn": str (4 digits),
            "qty": number|null, "rate": number|null (price per piece in rupees, before GST),
            "confidence": {"item":0..1,"qty":0..1,"rate":0..1},
            "hsn_options": [{"hsn": str, "p": 0..1}] (top 3)}],
 "questions": [str] (short Hindi questions for anything unclear)}
Rules: convert Hindi number words (pachaas=50, dhai sau=250, dedh hazaar=1500). Do NOT compute GST or totals.
If a value is unclear, set it null and add a question. Never invent a buyer or item.
Known HSN examples: kurta 6204, saree 5208, shirt 6205, dupatta 6214, carton 4819, bolts/screws 7318."""

NOTICE_PROMPT = """You explain an Indian GST/tax notice to a micro business owner with limited literacy.
Return ONLY JSON: {"form": str|null, "notice_date": "YYYY-MM-DD"|null, "reply_within_days": int|null,
"amount": number|null, "sections": [str], "summary_hi": "2-3 simple Hindi sentences",
"summary_en": "same in simple English", "next_steps_hi": ["3 short Hindi steps"], "needs_signature": bool}
Be calm and accurate. Do not give legal advice beyond the notice; suggest showing it to their CA.
Do NOT calculate deadlines yourself beyond copying numbers printed on the notice."""


def _log(feature: str, engine: str, latency_ms: int, valid: bool, retried: bool, fallback: str,
         confidence: float | None, summary: str, error: str = "", language: str = "") -> None:
    db.exec_("INSERT INTO ai_calls(ts,feature,engine,model,language,latency_ms,valid,retried,fallback,confidence,summary,error)"
             " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
             (datetime.now(timezone.utc).isoformat(timespec="seconds"), feature, engine,
              model_name() if engine == "gemini" else "-", language, latency_ms, int(valid), int(retried),
              fallback, confidence, summary[:200], error[:300]))


def _call_gemini(parts: list[dict]) -> str:
    url = API_URL.format(model=model_name())
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"}}
    r = requests.post(url, headers={"x-goog-api-key": api_key() or ""}, json=body, timeout=TIMEOUT_S)
    if r.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _json_from(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    return json.loads(m.group(0) if m else text)


def generate(feature: str, parts: list[dict], schema: type[BaseModel], language: str = "") -> tuple[BaseModel, dict]:
    """Call Gemini, validate against `schema`, retry once with the validation error."""
    t0 = time.time()
    retried, last_err = False, ""
    for attempt in range(2):
        try:
            p = parts if attempt == 0 else parts + [{"text": f"Your previous JSON was invalid: {last_err}. Return valid JSON only."}]
            out = schema.model_validate(_json_from(_call_gemini(p)))
            meta = {"engine": "gemini", "model": model_name(), "latency_ms": int((time.time() - t0) * 1000),
                    "retried": retried, "valid_first_try": not retried}
            return out, meta
        except (ValidationError, json.JSONDecodeError, KeyError) as e:
            retried, last_err = True, str(e)[:300]
    raise ValueError(f"invalid output after retry: {last_err}")


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------
def _draft_from_ai(out: InvoiceOut) -> dict:
    buyer = resolve_buyer(out.buyer_name or "")
    if out.buyer_name and not buyer["name"]:
        buyer = {"name": out.buyer_name, "gstin": None, "match_score": 0.5}
    return {"buyer": buyer, "items": [i.model_dump() for i in out.items], "questions": out.questions,
            "transcript": out.transcript, "language": out.language}


def invoice_from_text(text: str) -> dict:
    t0 = time.time()
    if ai_available():
        try:
            out, meta = generate("voice-text", [{"text": INVOICE_PROMPT}, {"text": f"Bill: {text}"}], InvoiceOut)
            d = _draft_from_ai(out)
            d["transcript"] = d.get("transcript") or text
            d.update(source="gemini-text", meta=meta)
            _log("voice", "gemini", meta["latency_ms"], True, meta["retried"], "none",
                 _avg_conf(d), _summ(d), language=d.get("language") or "")
            return d
        except Exception as e:  # fall back to rules
            err = str(e)
    else:
        err = "no API key"
    d = parse_bill(text)
    ms = int((time.time() - t0) * 1000)
    d["meta"] = {"engine": "rule-parser", "latency_ms": ms, "fallback_reason": err}
    _log("voice", "rule-parser", ms, bool(d["items"]), False, "rule-parser", _avg_conf(d), _summ(d), err)
    return d


def invoice_from_media(data: bytes, mime: str, feature: str, transcript_hint: str = "") -> dict:
    """Audio or image → invoice. Falls back to the transcript (if the browser sent one) or asks to type."""
    t0 = time.time()
    if ai_available():
        try:
            parts = [{"text": INVOICE_PROMPT},
                     {"inline_data": {"mime_type": (mime or "application/octet-stream").split(";")[0],
                                      "data": base64.b64encode(data).decode()}}]
            out, meta = generate(feature, parts, InvoiceOut)
            d = _draft_from_ai(out)
            d.update(source=f"gemini-{feature}", meta=meta)
            _log(feature, "gemini", meta["latency_ms"], True, meta["retried"], "none", _avg_conf(d), _summ(d),
                 language=d.get("language") or "")
            return d
        except Exception as e:
            err = str(e)
    else:
        err = "no API key"
    if transcript_hint and ai_available():
        # e.g. the audio format was rejected: still use Gemini on the browser's transcript
        d = invoice_from_text(transcript_hint)
        d.setdefault("meta", {})["fallback_reason"] = f"audio not used ({err[:80]}); Gemini read the browser transcript"
        return d
    if transcript_hint:
        d = parse_bill(transcript_hint)
        d["meta"] = {"engine": "rule-parser", "latency_ms": int((time.time() - t0) * 1000),
                     "fallback_reason": f"{err}; used browser transcript"}
        _log(feature, "rule-parser", d["meta"]["latency_ms"], bool(d["items"]), False, "browser-speech+rules",
             _avg_conf(d), _summ(d), err)
        return d
    _log(feature, "none", int((time.time() - t0) * 1000), False, False, "ask-owner", None, "no engine", err)
    return {"buyer": {"name": None}, "items": [], "questions": ["कृपया बिल बोलकर या लिखकर बताइए (AI key not set)."],
            "source": "unavailable", "meta": {"engine": "none", "fallback_reason": err}}


def explain_notice(data: bytes | None, mime: str | None, text: str | None) -> dict:
    t0 = time.time()
    if ai_available():
        try:
            parts = [{"text": NOTICE_PROMPT}]
            if data:
                parts.append({"inline_data": {"mime_type": mime or "image/jpeg", "data": base64.b64encode(data).decode()}})
            if text:
                parts.append({"text": text})
            out, meta = generate("notice", parts, NoticeOut)
            _log("notice", "gemini", meta["latency_ms"], True, meta["retried"], "none", None, out.summary_en)
            return {**out.model_dump(), "source": "gemini", "meta": meta}
        except Exception as e:
            err = str(e)
    else:
        err = "no API key"
    # Offline fallback: keyword reading of typed text
    t = (text or "").lower()
    fm = re.search(r"\b(drc|asmt|reg|cmp|pmt|mov)[\s-]?(\d{2}[a-z]?)\b", t)
    form = f"{fm.group(1).upper()}-{fm.group(2).upper()}" if fm else None
    amt = re.search(r"(?:rs\.?|₹|inr)\s*([\d,]+(?:\.\d+)?)", text or "", re.I)
    date_m = re.search(r"(\d{2})[/.-](\d{2})[/.-](\d{4})", text or "")
    iso_m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text or "")
    within = re.search(r"within\s+(\d{1,3})\s+days|(\d{1,3})\s+दिन", t)
    secs = sorted({f"Sec {m}" for m in re.findall(r"(?:section|sec\.?|धारा)\s*(\d{2,3}[a-z]?)", t)})
    notice_date = (f"{date_m.group(3)}-{date_m.group(2)}-{date_m.group(1)}" if date_m
                   else (iso_m.group(0) if iso_m else None))
    out = {"form": form, "amount": float(amt.group(1).replace(",", "")) if amt else None,
           "notice_date": notice_date,
           "reply_within_days": int(next(g for g in within.groups() if g)) if within else (30 if form else None),
           "sections": secs,
           "summary_hi": "यह GST विभाग का नोटिस है। इसे अपने CA को दिखाइए; Saajha ने ज़रूरी तारीख और रकम निकाल दी है।",
           "summary_en": "This is a GST department notice. Show it to your CA; Saajha extracted the date and amount.",
           "next_steps_hi": ["CA को नोटिस भेजें", "तारीख से पहले जवाब दें", "हस्ताक्षर के लिए JanAI Café जाएँ"],
           "needs_signature": True, "source": "keyword-fallback",
           "meta": {"engine": "keyword-fallback", "fallback_reason": err}}
    _log("notice", "keyword-fallback", int((time.time() - t0) * 1000), True, False, "keywords", None, out["summary_en"], err)
    return out


def draft_reminder(buyer: str, invoice_id: str, amount: float, due: str, tone: str = "polite Hindi") -> dict:
    template = (f"नमस्ते {buyer} जी 🙏 बिल {invoice_id} (₹{amount:,.0f}) का भुगतान {due} तक करने पर आपकी टैक्स कटौती "
                f"(आयकर अधिनियम 2025, धारा 37(2)(g)) सुरक्षित रहती है। धन्यवाद।")
    if not ai_available():
        return {"text": template, "source": "template"}
    t0 = time.time()
    try:
        r = _call_gemini([{"text": f"Rewrite this payment reminder in {tone}, under 45 words, keep every number and the "
                                   f"legal reference exactly. Return JSON {{\"text\": str}}.\n{template}"}])
        txt = _json_from(r).get("text") or template
        # guardrail: every number from the template must survive
        for n in re.findall(r"[\d,]{3,}|37\(2\)\(g\)", template):
            if n not in txt:
                txt = template
                break
        _log("agent-draft", "gemini", int((time.time() - t0) * 1000), True, False, "none", None, txt)
        return {"text": txt, "source": "gemini"}
    except Exception as e:
        _log("agent-draft", "template", int((time.time() - t0) * 1000), True, False, "template", None, template, str(e))
        return {"text": template, "source": "template"}


def _avg_conf(d: dict) -> float | None:
    vals = [v for it in d.get("items", []) for v in (it.get("confidence") or {}).values() if isinstance(v, (int, float))]
    return round(sum(vals) / len(vals), 3) if vals else None


def _summ(d: dict) -> str:
    b = (d.get("buyer") or {}).get("name") or "?"
    return f"{b}: " + "; ".join(f"{i.get('qty')} × {i.get('description')} @ {i.get('rate')}" for i in d.get("items", []))


def recent_calls(limit: int = 50) -> list[dict]:
    return [dict(r) for r in db.q("SELECT * FROM ai_calls ORDER BY id DESC LIMIT ?", (limit,))]


def call_stats() -> dict:
    rows = db.q("SELECT engine, COUNT(*) n, AVG(latency_ms) lat, SUM(valid) v, SUM(retried) r FROM ai_calls GROUP BY engine")
    return {r["engine"]: {"calls": r["n"], "avg_latency_ms": int(r["lat"] or 0), "valid": r["v"], "retried": r["r"]}
            for r in rows}
