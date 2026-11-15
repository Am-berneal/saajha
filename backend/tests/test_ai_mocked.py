"""Gemini path with a mocked HTTP layer: schema validation, retry, rules-engine authority, logging."""
import json

from saajha_core import ai

GOOD = {"buyer_name": "Sharma ji", "buyer_confidence": 0.9, "transcript": "sharma ji ko 50 kurta 400 wale",
        "language": "hi-Latn",
        "items": [{"description": "Cotton kurta", "hsn": "6204", "qty": 50, "rate": 400,
                   "confidence": {"item": 0.95, "qty": 0.97, "rate": 0.96}, "hsn_options": [{"hsn": "6204", "p": 0.9}]}],
        "questions": []}


def test_gemini_retry_then_valid(monkeypatch):
    calls = []

    def fake(parts):
        calls.append(parts)
        return "{not json" if len(calls) == 1 else json.dumps(GOOD)
    monkeypatch.setattr(ai, "ai_available", lambda: True)
    monkeypatch.setattr(ai, "_call_gemini", fake)
    d = ai.invoice_from_text("sharma ji ko 50 kurta 400 wale")
    assert len(calls) == 2 and d["meta"]["retried"] is True
    assert d["buyer"]["name"] == "Sharma Traders Pvt Ltd"  # resolved against the buyer master, not trusted blindly
    assert d["source"] == "gemini-text"


def test_gemini_garbage_falls_back_to_rules(monkeypatch):
    monkeypatch.setattr(ai, "ai_available", lambda: True)
    monkeypatch.setattr(ai, "_call_gemini", lambda parts: '{"items": "nope"}')
    d = ai.invoice_from_text("sharma ji ko 50 kurta 400 wale")
    assert d["meta"]["engine"] == "rule-parser" and d["items"][0]["qty"] == 50


def test_audio_rejected_uses_transcript_with_gemini(monkeypatch):
    monkeypatch.setattr(ai, "ai_available", lambda: True)

    def fake(parts):
        if any("inline_data" in p for p in parts):
            raise RuntimeError("Gemini HTTP 400: unsupported mime")
        return json.dumps(GOOD)
    monkeypatch.setattr(ai, "_call_gemini", fake)
    d = ai.invoice_from_media(b"xx", "audio/webm;codecs=opus", "voice", "sharma ji ko 50 kurta 400 wale")
    assert d["source"] == "gemini-text" and "transcript" in d["meta"]["fallback_reason"]


def test_every_call_is_logged(monkeypatch):
    before = ai.call_stats()
    monkeypatch.setattr(ai, "ai_available", lambda: False)
    ai.invoice_from_text("gupta ji ko 20 saree 800 wali")
    after = ai.call_stats()
    assert sum(v["calls"] for v in after.values()) == sum(v["calls"] for v in before.values()) + 1
