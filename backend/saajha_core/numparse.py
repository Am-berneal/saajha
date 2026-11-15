"""Rule-based Hindi / Hinglish bill parser.

This is the offline fallback when no AI key or internet is available, and the baseline
the AI is measured against. It understands phrases like:

    "शर्मा ट्रेडर्स को 50 कुर्ते, 400 वाले"
    "sharma traders ko pachaas kurte chaar sau wale aur paanch saree aath sau ke"
    "Gupta Retail 20 shirt dhai sau each"
"""
from __future__ import annotations

import difflib
import re
import unicodedata

DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

UNITS = {
    # romanised
    "ek": 1, "do": 2, "teen": 3, "tin": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "che": 6, "saat": 7, "sat": 7, "aath": 8, "ath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "baarah": 12,
    "pandrah": 15, "bees": 20, "bis": 20, "pachchees": 25, "pachees": 25, "pachis": 25, "पच्चीस": 25, "tees": 30, "chalees": 40, "chalis": 40,
    "pachaas": 50, "pachas": 50, "pachaas.": 50, "saath": 60, "sattar": 70, "assi": 80, "nabbe": 90,
    # devanagari
    "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5, "छह": 6, "छः": 6, "सात": 7, "आठ": 8, "नौ": 9,
    "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20, "पच्चीस": 25, "तीस": 30, "चालीस": 40,
    "पचास": 50, "साठ": 60, "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}
MULTS = {"sau": 100, "सौ": 100, "hazaar": 1000, "hazar": 1000, "hajar": 1000, "हज़ार": 1000,
         "हजार": 1000, "lakh": 100000, "लाख": 100000}
FRACS = {"dedh": 1.5, "डेढ़": 1.5, "डेढ": 1.5, "dhai": 2.5, "dhaai": 2.5, "ढाई": 2.5}
PLUS_HALF = {"saadhe", "sadhe", "साढ़े", "साढे"}
NUMBER_WORDS = set(UNITS) | set(MULTS) | set(FRACS) | PLUS_HALF

RATE_MARKERS = {"wale", "waale", "vale", "wali", "waali", "वाले", "वाला", "वाली", "ke", "का", "के", "ka", "rupaye", "rupay", "rs", "रुपये",
                "रुपए", "each", "per", "@", "at", "rate", "दाम", "piece", "pc", "पीस"}
BUYER_MARKERS = [" को ", " ko ", " के लिए ", " ke liye ", " for "]
ITEM_SPLIT = re.compile(r"\s*(?:,|\baur\b|\bor\b|\band\b|और|तथा|;|\n)\s*", re.IGNORECASE)

ITEMS = [
    # (canonical description, hsn, aliases)
    ("Cotton kurta", "6204", ["kurta", "kurte", "kurtas", "kurti", "kurtis", "कुर्ता", "कुर्ते", "कुर्ती"]),
    ("Cotton saree", "5208", ["saree", "sari", "sarees", "saris", "साड़ी", "साड़ियाँ", "साड़ियां", "साडी"]),
    ("Shirt", "6205", ["shirt", "shirts", "kameez", "शर्ट", "कमीज़", "कमीज"]),
    ("Dupatta", "6214", ["dupatta", "dupatte", "दुपट्टा", "दुपट्टे"]),
    ("Carton box", "4819", ["carton", "cartons", "dabba", "dabbe", "box", "boxes", "डिब्बा", "डिब्बे", "कार्टन"]),
    ("Fasteners (screws/bolts)", "7318", ["fastener", "fasteners", "bolt", "bolts", "screw", "screws", "pench", "पेंच", "बोल्ट", "फास्टनर"]),
    ("Cotton fabric (metre)", "5208", ["kapda", "kapde", "कपड़ा", "कपड़े", "fabric", "metre", "meter", "मीटर"]),
]
ALIAS_TO_ITEM = {a: (d, h) for d, h, al in ITEMS for a in al}

BUYERS = [
    {"name": "Sharma Traders Pvt Ltd", "gstin": "27AABCS1429P1ZX",
     "aliases": ["sharma traders", "sharma trader", "sharma ji", "sharma", "शर्मा ट्रेडर्स", "शर्मा जी", "शर्मा"]},
    {"name": "Gupta Retail", "gstin": "27AAGFG7710K1Z2",
     "aliases": ["gupta retail", "gupta ji", "gupta", "गुप्ता रिटेल", "गुप्ता जी", "गुप्ता"]},
    {"name": "Bansal Stores", "gstin": "27AAKFB3302M1Z9",
     "aliases": ["bansal stores", "bansal store", "bansal", "बंसल स्टोर्स", "बंसल स्टोर", "बंसल"]},
    {"name": "Jain Garments", "gstin": "27AAPFJ5518Q1Z4",
     "aliases": ["jain garments", "jain garment", "jain", "जैन गारमेंट्स", "जैन"]},
]


def norm(text: str) -> str:
    t = unicodedata.normalize("NFC", text or "").translate(DEV_DIGITS)
    t = t.replace("₹", " rs ").replace("@", " @ ").replace("/-", " ").replace("×", " x ")
    t = re.sub(r"(\d),(\d{3})", r"\1\2", t)  # 2,500 -> 2500
    t = re.sub(r"(\d)([^\d\s.])", r"\1 \2", t)  # 400wale -> 400 wale
    t = re.sub(r"([^\d\s.])(\d)", r"\1 \2", t)
    return re.sub(r"\s+", " ", t).strip().lower()


def _is_num_token(tok: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?", tok)) or tok in NUMBER_WORDS


def parse_number(tokens: list[str], i: int) -> tuple[float | None, int]:
    """Parse a number expression starting at tokens[i]. Returns (value, next_index)."""
    total, current, used, frac, half = 0.0, 0.0, False, None, False
    j = i
    while j < len(tokens):
        t = tokens[j]
        if re.fullmatch(r"\d+(?:\.\d+)?", t):
            current += float(t); used = True
        elif t in UNITS:
            current += UNITS[t]; used = True
        elif t in FRACS:
            frac = FRACS[t]; used = True
        elif t in PLUS_HALF:
            half = True; used = True
        elif t in MULTS:
            m = MULTS[t]
            base = frac if frac is not None else (current + 0.5 if half else (current or 1))
            if m >= 1000:
                total += base * m; current = 0
            else:
                current = base * m
            frac, half, used = None, False, True
        else:
            break
        j += 1
    if not used:
        return None, i
    value = total + current
    if frac is not None and value == 0:
        value = frac
    return value, j


def find_numbers(segment: str) -> list[tuple[float, int, int]]:
    toks = segment.split()
    out, i = [], 0
    while i < len(toks):
        if _is_num_token(toks[i]):
            v, j = parse_number(toks, i)
            if v is not None:
                out.append((v, i, j)); i = j; continue
        i += 1
    return out


def resolve_buyer(text: str) -> dict:
    t = norm(text)
    best, best_score = None, 0.0
    for b in BUYERS:
        for a in b["aliases"]:
            a2 = norm(a)
            if a2 and a2 in t:
                score = 0.97 if len(a2.split()) > 1 else 0.85
            else:
                score = difflib.SequenceMatcher(None, a2, t[: len(a2) + 6]).ratio() * 0.9
            if score > best_score:
                best, best_score = b, score
    if best is None or best_score < 0.6:
        return {"name": None, "gstin": None, "match_score": round(best_score, 2)}
    return {"name": best["name"], "gstin": best["gstin"], "match_score": round(best_score, 2)}


def _find_item(tokens: list[str]) -> tuple[int, str, str] | None:
    for k, tok in enumerate(tokens):
        if tok in ALIAS_TO_ITEM:
            d, h = ALIAS_TO_ITEM[tok]
            return k, d, h
        close = difflib.get_close_matches(tok, ALIAS_TO_ITEM.keys(), n=1, cutoff=0.82)
        if close and not _is_num_token(tok):
            d, h = ALIAS_TO_ITEM[close[0]]
            return k, d, h
    return None


def parse_bill(text: str) -> dict:
    """Parse a spoken or typed bill into a draft invoice (no AI)."""
    raw = text or ""
    t = " " + norm(raw) + " "
    buyer_part, rest = "", t
    for m in BUYER_MARKERS:
        if m in t:
            buyer_part, rest = t.split(m, 1)
            break
    buyer = resolve_buyer(buyer_part or t)
    segments = [s for s in ITEM_SPLIT.split(rest) if s.strip()]
    # merge segments that hold only a rate ("50 kurte, 400 wale") into the previous one
    merged: list[str] = []
    for s in segments:
        toks = s.split()
        if merged and _find_item(toks) is None:
            merged[-1] = merged[-1] + " " + s
        else:
            merged.append(s)
    items, questions = [], []
    for seg in merged:
        toks = seg.split()
        found = _find_item(toks)
        if not found:
            continue
        k, desc, hsn = found
        nums = find_numbers(seg)
        stoks = seg.split()

        def is_rate(n):
            nxt = stoks[n[2]] if n[2] < len(stoks) else ""
            prv = stoks[n[1] - 1] if n[1] > 0 else ""
            return nxt in RATE_MARKERS or prv in {"@", "rs", "at", "rate", "दाम"}

        rates = [n for n in nums if is_rate(n)]
        others = [n for n in nums if not is_rate(n)]
        rate = rates[0][0] if rates else None
        before = [n for n in others if n[2] <= k]
        after = [n for n in others if n[1] > k]
        qty = before[-1][0] if before else (after[0][0] if after else None)
        if rate is None:
            if before and after:
                rate = after[0][0]
            elif len(before) >= 2:
                qty, rate = before[-2][0], before[-1][0]
            elif len(after) >= 2:
                qty, rate = after[0][0], after[1][0]
            if rate is not None and qty == rate and len(others) == 1:
                rate = None
        conf = 0.92 if (qty and rate) else 0.5
        if not qty:
            questions.append(f"How many {desc}?")
        if not rate:
            questions.append(f"What is the rate for {desc}?")
        items.append({"description": desc, "hsn": hsn, "qty": qty, "rate": rate,
                      "confidence": {"item": 0.9, "qty": conf if qty else 0.0, "rate": conf if rate else 0.0},
                      "hsn_options": [{"hsn": hsn, "p": 0.9}]})
    if not buyer["name"]:
        questions.append("Who is the buyer?")
    if not items:
        questions.append("Which items and how many?")
    return {"buyer": buyer, "items": items, "questions": questions, "source": "rule-parser",
            "language": "hi" if re.search(r"[ऀ-ॿ]", raw) else "hi-Latn/en", "transcript": raw}
