"""Measure invoice-extraction accuracy on the synthetic Hindi/Hinglish set.

    python eval/run_eval.py                 # auto: Gemini if GEMINI_API_KEY is set, else rule parser
    python eval/run_eval.py --engine rules  # rule parser only (offline baseline)
    python eval/run_eval.py --engine gemini # Gemini only

Writes data/eval_latest.json, which the AI-monitoring screen reads. Every number shown
in the app comes from this file — nothing is typed in by hand.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
import sys as _sys
try:
    _sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
except Exception:
    pass
sys.path.insert(0, str(HERE.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(HERE.parent / ".env")

from saajha_core import ai, db, rules  # noqa: E402
from saajha_core.numparse import ITEMS, parse_bill  # noqa: E402

HSN_OF = {d.split(" (")[0].lower(): h for d, h, _ in ITEMS}


def _same_item(a: str, b: str) -> bool:
    a, b = a.lower(), b.lower()
    return a == b or a in b or b in a


def score(pred: dict, gold: dict) -> dict:
    p_items = [i for i in pred.get("items", []) if i.get("qty") and i.get("rate")]
    g_items = [g for g in gold["items"] if g["rate"] is not None]
    needs_question = len(g_items) < len(gold["items"])
    buyer_ok = (pred.get("buyer") or {}).get("name") == gold["buyer"]
    matched = 0
    field_hits = field_total = 0
    used = set()
    for g in g_items:
        field_total += 3
        best = None
        for k, p in enumerate(p_items):
            if k in used:
                continue
            if _same_item(p.get("description", ""), g["item"]):
                best = k
                break
        if best is None:
            continue
        used.add(best)
        p = p_items[best]
        hits = 1 + (float(p["qty"]) == g["qty"]) + (g["rate"] is not None and float(p["rate"]) == g["rate"])
        field_hits += hits
        if hits == 3:
            matched += 1
    exact = buyer_ok and matched == len(g_items) and len(p_items) == len(g_items)
    if needs_question:
        exact = exact and bool(pred.get("questions"))
    # money check: rules engine total from prediction vs from gold
    gold_total = rules.compute_invoice([{"description": g["item"], "qty": g["qty"], "rate": g["rate"],
                                         "hsn": HSN_OF.get(g["item"].lower())} for g in g_items], "27AAOFM4821C1Z4", "27AAOFM4821C1Z4")["grand_total"]
    try:
        pred_total = rules.compute_invoice(p_items, "27AAOFM4821C1Z4", "27AAOFM4821C1Z4")["grand_total"] if p_items else 0
    except Exception:
        pred_total = 0
    return {"buyer_ok": buyer_ok, "exact": exact, "field_hits": field_hits + buyer_ok, "field_total": field_total + 1,
            "total_ok": abs(pred_total - gold_total) < 0.5, "asked": bool(pred.get("questions"))}


def _rate(results, pick):
    sel = [s for s in results if pick(s)]
    return round(sum(s["exact"] for s in sel) / len(sel), 3) if sel else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["auto", "rules", "gemini"], default="auto")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--sleep", type=float, default=6.5, help="seconds between Gemini calls (free tier is ~10 requests/minute)")
    ap.add_argument("--set", choices=["dev", "holdout", "both"], default="both")
    args = ap.parse_args()
    engine = args.engine
    if engine == "auto":
        engine = "gemini" if ai.ai_available() else "rules"
    if engine == "gemini" and not ai.ai_available():
        sys.exit("GEMINI_API_KEY is not set. Put it in backend/.env or use --engine rules.")

    files = {"dev": ["dataset.jsonl"], "holdout": ["holdout.jsonl"], "both": ["dataset.jsonl", "holdout.jsonl"]}[args.set]
    rows = [json.loads(l) for fn in files for l in (HERE / fn).read_text(encoding="utf-8").splitlines() if l.strip()]
    if args.limit:
        rows = rows[: args.limit]
    results, lat = [], []
    for r in rows:
        t0 = time.time()
        pred = parse_bill(r["utterance"]) if engine == "rules" else ai.invoice_from_text(r["utterance"])
        ms = int((time.time() - t0) * 1000)
        lat.append(ms)
        s = score(pred, r)
        s.update(id=r["id"], style=r["style"], utterance=r["utterance"], engine=pred.get("source", engine), ms=ms,
                 why=(pred.get("meta") or {}).get("fallback_reason", ""))
        results.append(s)
        if engine == "gemini" and not str(s["engine"]).startswith("gemini"):
            print(f"    !! Gemini NOT used for {r['id']} -> fell back to rules. Reason: {s['why'][:160]}")
            if len(results) == 3 and all(not str(x["engine"]).startswith("gemini") for x in results):
                sys.exit("\nStopped: the first 3 calls all fell back, so this would only measure the rule parser.\n"
                         "Fix the reason above (key, model name, or rate limit) and run again.")
        mark = "OK " if s["exact"] else ("ASK" if s["asked"] else "ERR")
        print(f"{mark} {r['id']} [{r['style']:8}] {r['utterance'][:60]}")
        if engine == "gemini":
            time.sleep(args.sleep)  # stay under free-tier rate limits

    n = len(results)
    by_style = {}
    for s in results:
        b = by_style.setdefault(s["style"], {"n": 0, "exact": 0})
        b["n"] += 1
        b["exact"] += s["exact"]
    fallbacks = sum(1 for s in results if engine == "gemini" and not str(s["engine"]).startswith("gemini"))
    report = {
        "measured": True,
        "engine": engine,
        "model": ai.model_name() if engine == "gemini" else "rule-parser (no AI)",
        "dataset": f"{', '.join(files)} — {n} SYNTHETIC utterances written by the team (not field data)",
        "n": n,
        "exact_match": round(sum(s["exact"] for s in results) / n, 3),
        "field_accuracy": round(sum(s["field_hits"] for s in results) / sum(s["field_total"] for s in results), 3),
        "buyer_accuracy": round(sum(s["buyer_ok"] for s in results) / n, 3),
        "money_total_accuracy": round(sum(s["total_ok"] for s in results) / n, 3),
        "asked_when_wrong": sum(1 for s in results if not s["exact"] and s["asked"]),
        "silent_errors": sum(1 for s in results if not s["exact"] and not s["asked"]),
        "fallbacks": fallbacks,
        "latency_ms_p50": sorted(lat)[n // 2],
        "latency_ms_p95": sorted(lat)[min(n - 1, int(n * 0.95))],
        "dev_exact": _rate(results, lambda s: s["style"] != "holdout"),
        "holdout_exact": _rate(results, lambda s: s["style"] == "holdout"),
        "by_style": {k: {**v, "rate": round(v["exact"] / v["n"], 3)} for k, v in by_style.items()},
        "failures": [s for s in results if not s["exact"]][:15],
        "run_at": datetime.now().isoformat(timespec="seconds"),
    }
    out = db.DATA_DIR / "eval_latest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    hist = db.DATA_DIR / f"eval_{engine}.json"
    hist.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    used = f"Gemini used {n - fallbacks}/{n} · " if engine == "gemini" else ""
    print(f"\nEngine {engine}: exact {report['exact_match']:.0%} · fields {report['field_accuracy']:.0%} · {used}"
          f"dev {report['dev_exact']} · HOLD-OUT {report['holdout_exact']} · money total {report['money_total_accuracy']:.0%} · "
          f"silent errors {report['silent_errors']} → {out}")


if __name__ == "__main__":
    main()