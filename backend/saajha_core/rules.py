"""Deterministic rules engine.

Every rupee, date and deadline in Saajha is computed here, never by the AI model.
Each function returns the value together with the rule ID and legal citation so the
UI can show *why* a number is what it is.

These are simplified encodings for a hackathon prototype. Verify current
notifications and rates with a Chartered Accountant before real use.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, timedelta
from typing import Optional

RULESET_VERSION = "2026.11-r1"

# RBI Bank Rate used for MSMED Sec 16 interest. Configurable; verify the current rate.
DEFAULT_BANK_RATE = 5.75


@dataclass
class RuleResult:
    value: object
    rule_id: str
    citation: str
    explanation: str
    version: str = RULESET_VERSION

    def to_dict(self) -> dict:
        d = asdict(self)
        if isinstance(self.value, date):
            d["value"] = self.value.isoformat()
        return d


# ---------------------------------------------------------------------------
# HSN master (small demo subset) and GST rates
# ---------------------------------------------------------------------------
HSN_MASTER = {
    "6204": {"desc": "Women's suits, dresses, kurtas (woven)", "chapter": "62", "kind": "apparel"},
    "6211": {"desc": "Other garments (woven)", "chapter": "62", "kind": "apparel"},
    "6206": {"desc": "Women's blouses and shirts", "chapter": "62", "kind": "apparel"},
    "6205": {"desc": "Men's shirts (woven)", "chapter": "62", "kind": "apparel"},
    "6214": {"desc": "Shawls, scarves, dupattas", "chapter": "62", "kind": "apparel"},
    "5208": {"desc": "Woven cotton fabrics (incl. cotton sarees)", "chapter": "52", "kind": "fabric"},
    "4819": {"desc": "Cartons, boxes of paper or paperboard", "chapter": "48", "kind": "goods18"},
    "7318": {"desc": "Screws, bolts, nuts and fasteners", "chapter": "73", "kind": "goods18"},
}


def gst_rate(hsn: str, unit_price: float) -> RuleResult:
    """GST rate for a line item. Apparel: 5% up to Rs 2,500 per piece, 18% above."""
    info = HSN_MASTER.get(str(hsn))
    if info is None:
        return RuleResult(None, "GST.RATE.UNKNOWN", "CGST rate schedule",
                          f"HSN {hsn} not in the demo rate table: ask the CA.")
    if info["kind"] == "apparel":
        rate = 5 if unit_price <= 2500 else 18
        return RuleResult(rate, "GST.RATE.APPAREL", "CGST rate schedule (apparel, Sept 2025 rationalisation)",
                          f"Apparel at Rs {unit_price:,.0f} per piece is {'up to' if rate == 5 else 'above'} Rs 2,500 → {rate}%.")
    if info["kind"] == "fabric":
        return RuleResult(5, "GST.RATE.FABRIC", "CGST rate schedule (cotton fabrics)", "Cotton fabric → 5%.")
    return RuleResult(18, "GST.RATE.STD18", "CGST rate schedule", f"HSN {hsn} → 18%.")


def place_of_supply(supplier_gstin: str, buyer_gstin: str) -> RuleResult:
    same = (supplier_gstin or "")[:2] == (buyer_gstin or "")[:2]
    return RuleResult("intra" if same else "inter", "GST.POS.STATECODE", "IGST Act Sec 10",
                      "Same state code → CGST + SGST." if same else "Different states → IGST.")


def compute_invoice(items: list[dict], supplier_gstin: str, buyer_gstin: str) -> dict:
    """Compute taxable value, GST split and total. `items`: [{description, hsn, qty, rate}]."""
    pos = place_of_supply(supplier_gstin, buyer_gstin)
    lines, taxable_total, tax_total = [], 0.0, 0.0
    for it in items:
        qty, rate = float(it.get("qty") or 0), float(it.get("rate") or 0)
        taxable = round(qty * rate, 2)
        r = gst_rate(str(it.get("hsn") or ""), rate)
        pct = r.value or 0
        tax = round(taxable * pct / 100, 2)
        split = ({"cgst": round(tax / 2, 2), "sgst": round(tax / 2, 2)} if pos.value == "intra" else {"igst": tax})
        lines.append({**it, "qty": qty, "rate": rate, "taxable": taxable, "gst_rate": pct,
                      "gst": tax, "split": split, "rate_rule": r.to_dict()})
        taxable_total += taxable
        tax_total += tax
    return {
        "lines": lines,
        "taxable_total": round(taxable_total, 2),
        "gst_total": round(tax_total, 2),
        "grand_total": round(taxable_total + tax_total, 2),
        "place_of_supply": pos.to_dict(),
        "computed_by": "rules-engine",
        "ruleset": RULESET_VERSION,
    }


# ---------------------------------------------------------------------------
# MSMED Act: payment deadline and interest
# ---------------------------------------------------------------------------
def payment_due_date(accepted_on: date, agreed_days: Optional[int]) -> RuleResult:
    """MSMED Sec 15: pay by agreed date (max 45 days) or within 15 days if no written agreement."""
    if agreed_days is None:
        days, why = 15, "No written agreement → 15 days from acceptance."
    else:
        days = min(int(agreed_days), 45)
        why = (f"Written terms of {agreed_days} days → {days} days"
               + (" (capped at 45)." if agreed_days > 45 else "."))
    return RuleResult(accepted_on + timedelta(days=days), "MSMED.S15.DUE", "MSMED Act 2006, Sec 15", why)


def days_left(due: date, today: date) -> int:
    return (due - today).days


def delayed_payment_interest(principal: float, days_late: int, bank_rate: float = DEFAULT_BANK_RATE) -> RuleResult:
    """MSMED Sec 16: compound interest, monthly rests, at three times the RBI bank rate."""
    days_late = max(0, int(days_late))
    annual = 3 * bank_rate / 100
    interest = principal * ((1 + annual / 12) ** (days_late / 30) - 1)
    return RuleResult(round(interest), "MSMED.S16.INTEREST", "MSMED Act 2006, Sec 16",
                      f"3 × bank rate {bank_rate}% = {3 * bank_rate:.2f}% a year, compounded monthly, for {days_late} days.")


def buyer_deduction_status(due: date, paid_on: Optional[date], fy_end: date) -> RuleResult:
    """Income-tax Act 2025 Sec 37(2)(g) (earlier Sec 43B(h), Income-tax Act 1961)."""
    cite = "Income-tax Act 2025, Sec 37(2)(g)"
    if paid_on is not None and paid_on <= due:
        return RuleResult("allowed", "ITA.S37_2_G", cite, "Paid within the MSMED time limit → deduction allowed this year.")
    if paid_on is None and fy_end < due:
        return RuleResult("not_yet_due", "ITA.S37_2_G", cite, "Still within the time limit at year end.")
    return RuleResult("deferred", "ITA.S37_2_G", cite,
                      "Paid late (or unpaid past the limit) → deduction only in the year of actual payment.")


# ---------------------------------------------------------------------------
# GST return dates and late fees
# ---------------------------------------------------------------------------
def gstr1_due(period_year: int, period_month: int, iff: bool = False) -> RuleResult:
    ny, nm = (period_year + 1, 1) if period_month == 12 else (period_year, period_month + 1)
    day = 13 if iff else 11
    return RuleResult(date(ny, nm, day), "GST.GSTR1.DUE" if not iff else "GST.IFF.DUE", "CGST Rules, Rule 59",
                      f"{'IFF' if iff else 'GSTR-1'} for {period_month:02d}/{period_year} is due on the {day}th of the next month.")


def gstr3b_late_fee(days_late: int, nil_return: bool = False, turnover_upto_1_5cr: bool = True) -> RuleResult:
    """Late fee (CGST + SGST). Simplified encoding of Notf. 19/2021-CT; verify current notification."""
    per_day = 20 if nil_return else 50
    cap = 500 if nil_return else (2000 if turnover_upto_1_5cr else 5000)
    fee = min(per_day * max(0, days_late), cap)
    return RuleResult(fee, "GST.3B.LATEFEE", "CGST Act Sec 47; Notf. 19/2021-CT (verify current)",
                      f"Rs {per_day}/day, capped at Rs {cap:,}.")


def notice_reply_deadline(issued_on: date, days: int = 30) -> RuleResult:
    """Reply window for an intimation (DRC-01A style). Uses the date printed on the notice."""
    return RuleResult(issued_on + timedelta(days=days), "GST.NOTICE.REPLY", "Reply period printed on the notice (e.g. ASMT-10 under Rule 99; DRC-01A under Rule 142(1A))",
                      f"Reply window of {days} days from the notice date (check the notice for the exact period).")


RULE_REGISTRY = [
    "GST.RATE.APPAREL", "GST.RATE.FABRIC", "GST.RATE.STD18", "GST.RATE.UNKNOWN", "GST.POS.STATECODE",
    "MSMED.S15.DUE", "MSMED.S16.INTEREST", "ITA.S37_2_G", "GST.GSTR1.DUE", "GST.IFF.DUE",
    "GST.3B.LATEFEE", "GST.NOTICE.REPLY",
]
