from datetime import date

from saajha_core import rules


def test_apparel_rate_threshold():
    assert rules.gst_rate("6204", 2500).value == 5
    assert rules.gst_rate("6204", 2501).value == 18


def test_invoice_totals_intra_state():
    inv = rules.compute_invoice([{"description": "Cotton kurta", "hsn": "6204", "qty": 50, "rate": 400}],
                                "27AAOFM4821C1Z4", "27AABCS1429P1ZX")
    assert inv["taxable_total"] == 20000 and inv["gst_total"] == 1000 and inv["grand_total"] == 21000
    assert set(inv["lines"][0]["split"]) == {"cgst", "sgst"}


def test_inter_state_igst():
    inv = rules.compute_invoice([{"description": "x", "hsn": "4819", "qty": 1, "rate": 100}],
                                "27AAOFM4821C1Z4", "29AABCS1429P1ZX")
    assert "igst" in inv["lines"][0]["split"]


def test_msmed_due_date_caps_at_45():
    assert rules.payment_due_date(date(2026, 11, 15), 60).value == date(2026, 12, 30)
    assert rules.payment_due_date(date(2026, 11, 15), None).value == date(2026, 11, 30)


def test_interest_three_times_bank_rate_monthly_compound():
    r = rules.delayed_payment_interest(100000, 30, 5.75)
    assert abs(r.value - 1437.5) < 1  # 17.25% / 12 for one month
    assert rules.delayed_payment_interest(100000, 0).value == 0


def test_gstr3b_late_fee_capped():
    assert rules.gstr3b_late_fee(10, False, True).value == 500
    assert rules.gstr3b_late_fee(400, False, True).value == 2000


def test_every_result_has_citation():
    r = rules.payment_due_date(date(2026, 11, 15), 45)
    assert r.citation and r.rule_id and r.version == rules.RULESET_VERSION
