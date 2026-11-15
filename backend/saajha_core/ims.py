"""IMS matcher: compares purchase invoices uploaded by suppliers to the GST portal (IMS)
against the owner's own purchase book, and suggests Accept / Reject / Keep pending.

The portal data is SIMULATED in the hackathon build (no open GSTN API for students).
The matching logic is real and deterministic.
"""
from __future__ import annotations

import difflib

AMOUNT_TOLERANCE = 1.0  # rupees


def _key(gstin: str, inv: str) -> str:
    return f"{(gstin or '').upper()}|{(inv or '').upper().replace(' ', '').replace('-', '')}"


def match(portal: list[dict], book: list[dict], returns_register: list[dict] | None = None) -> dict:
    returns_register = returns_register or []
    book_by_key = {_key(b["gstin"], b["invoice_no"]): b for b in book}
    results = []
    for p in portal:
        k = _key(p["gstin"], p["invoice_no"])
        b = book_by_key.get(k)
        if p.get("type") == "credit_note":
            ok = any(_key(r["gstin"], r["ref"]) == _key(p["gstin"], p.get("against", "")) for r in returns_register)
            results.append({**p, "status": "exception", "suggest": "accept" if ok else "pending",
                            "reason": "Credit note matches your returns register" if ok else "Credit note with no matching return",
                            "itc_effect": -p["tax"]})
            continue
        if b is None:
            # fuzzy: same supplier, invoice number typo?
            cands = [x for x in book if x["gstin"].upper() == p["gstin"].upper()]
            close = difflib.get_close_matches(p["invoice_no"], [c["invoice_no"] for c in cands], n=1, cutoff=0.8)
            if close:
                b = next(c for c in cands if c["invoice_no"] == close[0])
            else:
                results.append({**p, "status": "exception", "suggest": "reject",
                                "reason": "No purchase, delivery or payment in your records", "itc_effect": 0})
                continue
        diff = round(p["amount"] - b["amount"], 2)
        if abs(diff) <= AMOUNT_TOLERANCE:
            results.append({**p, "status": "matched", "suggest": "accept", "reason": "Matches your book", "itc_effect": p["tax"]})
        else:
            results.append({**p, "status": "exception", "suggest": "pending", "book_amount": b["amount"],
                            "reason": f"Amount differs by ₹{diff:,.0f} from your book; ask supplier to correct",
                            "itc_effect": 0})
    matched = [r for r in results if r["status"] == "matched"]
    return {"total": len(results), "matched": len(matched), "exceptions": [r for r in results if r["status"] == "exception"],
            "itc_safe": round(sum(r["tax"] for r in matched), 2), "results": results,
            "engine": "rules (deterministic)", "portal_data": "SIMULATED"}


def sample_data() -> tuple[list[dict], list[dict], list[dict]]:
    sup = [("08AAACR5521K1Z1", "Ravi Yarn Store"), ("27AAFCJ1180P1Z3", "Jaipur Textiles"),
           ("27AAECS7782R1Z6", "Shree Ganesh Fabrics"), ("27AAHCM3301L1Z8", "Mahalaxmi Threads")]
    portal, book = [], []
    amounts = [12400, 8600, 15200, 9800, 22100, 6700, 18400, 11300, 7600, 26800,
               9900, 14700, 5600, 19300, 8800, 12600, 30200, 7100, 16900, 10400]
    for i, amt in enumerate(amounts):
        g, name = sup[i % 4]
        inv = f"{name.split()[0][:3].upper()}-{1100 + i}"
        tax = round(amt * 0.05, 2) if i % 3 else round(amt * 0.12, 2)
        portal.append({"gstin": g, "supplier": name, "invoice_no": inv, "amount": amt, "tax": tax, "type": "invoice"})
        book.append({"gstin": g, "invoice_no": inv, "amount": amt})
    # the 3 exceptions shown in the app
    portal.append({"gstin": "08AAACR5521K1Z1", "supplier": "Ravi Yarn Store", "invoice_no": "RAV-1188",
                   "amount": 6200, "tax": 310, "type": "invoice"})
    book.append({"gstin": "08AAACR5521K1Z1", "invoice_no": "RAV-1188", "amount": 5900})
    portal.append({"gstin": "27AAKCB9001Q1Z7", "supplier": "Shree Balaji Traders", "invoice_no": "SBT-0091",
                   "amount": 14000, "tax": 700, "type": "invoice"})
    portal.append({"gstin": "27AAFCJ1180P1Z3", "supplier": "Jaipur Textiles", "invoice_no": "CN-042",
                   "amount": 1100, "tax": 55, "type": "credit_note", "against": "JAI-1101"})
    returns = [{"gstin": "27AAFCJ1180P1Z3", "ref": "JAI-1101", "qty": 4}]
    return portal, book, returns
