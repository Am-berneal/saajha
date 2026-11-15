from saajha_core import agent, ledger


def test_agent_recovers_from_channel_failure_and_waits_for_approval():
    c = agent.create_case("A-1", "Gupta Retail", "27AAGFG7710K1Z2", 12500, 45)
    c = agent.run(c["id"])
    tools = [s["tool"] for s in c["log"]]
    assert "whatsapp" in tools and "voice_call" in tools  # failed, then recovered
    assert any(m["key"] == "whatsapp_invalid" for m in c["memory"])  # learned from failure
    assert c["status"] == "waiting_approval"  # never sends a legal reminder by itself
    types = [e["type"] for e in ledger.invoice_events("A-1")]
    assert "BuyerAccepted" in types and "ReminderApproved" not in types
    c = agent.decide(c["id"], True, None)
    assert c["status"] == "scheduled"
    assert "ReminderApproved" in [e["type"] for e in ledger.invoice_events("A-1")]


def test_agent_reject_keeps_reminder_unsent():
    c = agent.run(agent.create_case("A-2", "Gupta Retail", "27AAGFG7710K1Z2", 9000, 30)["id"])
    c = agent.decide(c["id"], False, None)
    assert "ReminderApproved" not in [e["type"] for e in ledger.invoice_events("A-2")]
