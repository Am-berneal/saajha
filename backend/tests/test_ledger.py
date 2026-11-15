from saajha_core import ledger


def test_chain_and_tamper_detection():
    ledger.append("T-1", "InvoiceCreated", {"amount": 21000}, "supplier")
    ledger.append("T-1", "BuyerAccepted", {"amount": 21000}, "buyer")
    assert ledger.verify_invoice("T-1")["ok"]
    t = ledger.tamper_test("T-1", "amount", 12000)
    assert t["detected"] is True
    assert t["real_ledger_ok"] is True  # tamper test never touches the real ledger
    statuses = [b["status"] for b in t["blocks"]]
    assert "altered" in statuses


def test_signatures_are_ed25519_and_verify():
    ev = ledger.append("T-2", "InvoiceCreated", {"amount": 5}, "supplier")
    assert len(ev["signature"]) == 128
    v = ledger.verify_invoice("T-2")
    assert all(b["signature_ok"] for b in v["blocks"])
