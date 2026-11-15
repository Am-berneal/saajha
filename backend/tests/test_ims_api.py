from fastapi.testclient import TestClient

from saajha_core import ims


def test_ims_flags_three_exceptions():
    out = ims.match(*ims.sample_data())
    assert out["matched"] == 20 and len(out["exceptions"]) == 3
    assert {e["suggest"] for e in out["exceptions"]} == {"accept", "pending", "reject"}


def test_api_end_to_end_offline():
    import app
    c = TestClient(app.app)
    s = c.get("/api/status").json()
    assert s["backend"] == "running" and s["ai"]["available"] is False
    inv = c.post("/api/invoice/from-text", json={"text": "sharma ji ko 50 kurta 400 wale"}).json()
    assert inv["invoice"]["grand_total"] == 21000 and inv["invoice"]["computed_by"] == "rules-engine"
    assert c.get("/api/ledger/verify/INV-0142").json()["ok"]
    assert c.post("/api/ledger/tamper-test", json={"invoice_id": "INV-0142"}).json()["detected"]
    n = c.post("/api/notice/explain", data={"text": "ASMT-10 dated 02/11/2026 Rs 18,400 reply within 30 days"}).json()
    assert n["form"] == "ASMT-10" and n["deadline"]["value"] == "2026-12-02"
    assert c.get("/").status_code == 200
