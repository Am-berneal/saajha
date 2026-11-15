# 3-minute pitch and demo script

Tech4Bharat 2026 · Theme 3.1. Open `index.html`, go full screen, press **Play guided demo**, and speak over the captions.

| Time | Screen | What to say |
|---|---|---|
| 0:00 | Landing | "Since April, when a micro supplier files late, its buyer loses tax credit. So why is the micro supplier still the only one doing the paperwork?" |
| 0:15 | Home | "Meena runs a 6-person tailoring unit. Her whole interface is one button: speak your bill." |
| 0:25 | Speak a bill | "She speaks in Hindi. Speech recognition and a strict invoice schema build the GST invoice. Rules check the rate; she confirms." |
| 0:45 | Buyer confirms | "The buyer's store manager taps once. The acceptance date, the fact the 45-day law depends on, is signed by both sides at delivery." |
| 1:05 | Invoice & clock | "Both see one pay-by clock. Interest under MSMED Sec 16 is computed by rules code, never by the AI." |
| 1:15 | Agent | "This is an agent, not a form. It remembers this buyer answers calls after 6 pm, recovers when WhatsApp fails, and asks Meena before any legal step." |
| 1:20 | Purchase bills | "20 of 23 purchase bills match automatically. She decides only 3 exceptions." |
| 1:35 | Loss Statement | "Every month: what paperwork cost her. 1 hour 10 minutes and ₹340, down from 9 hours and ₹4,860." |
| 1:45 | JanAI Café | "Signing a notice reply needs her DSC. The agent books the nearest JanAI Café; Pooja, a Saajha Sathi, does it with her and earns for it." |
| 1:55 | Buyer dashboard | "The buyer pays for this because it protects their ITC and their deduction, and predicts late filers early." |
| 2:10 | CA cockpit | "Her CA approves 142 prepared filings in one batch, every flag cited." |
| 2:25 | Proof | "Anyone she shares it with can verify the signed record: lender, auditor, dispute officer." |
| 2:40 | Close | "Saajha: the buyer funds it, the supplier just speaks, every invoice gets paid on time." |

## Likely judge questions

- **Will buyers pay?** ITC protected per month for a 300-supplier anchor; CPSEs must already use TReDS.
- **What's actually built?** Show the simulated-integrations table in the README.
- **Is it really agentic?** Show case memory, the WhatsApp → SMS → call recovery, and the approval gate.
- **Jobs?** One Saajha Sathi per ~150 micro businesses; CAs scale.
- **AI errors?** Deterministic rules, citations, CA approval.

## Live demo for the technical judges (3 minutes, backend running)

1. **System status** — "Everything on this page is read from the backend: Gemini connected, 21 tests passing, signed ledger intact. This panel lists exactly what is simulated."
2. **Speak a bill** — tap the mic, say *"sharma ji ko pachaas kurte chaar sau wale aur paanch saree aath sau wali"*. Point at the engine chip (Gemini, latency), the HSN codes and that **GST was computed by the rules engine with a citation**, not by the model.
3. Ask a judge to say a bill in their own words. If something is unclear, Saajha asks a question instead of guessing.
4. **Sign & send → Simulate buyer's tap** — the due date comes from MSMED Sec 15 with the citation.
5. **Bill from photo** — *Use this sample bill* (handwritten). Gemini reads it; the rules engine totals it.
6. **Agent** — *Run the agent on the backend*: WhatsApp fails, the agent learns it, falls back to SMS and a voice call at the time it remembers, starts the clock, then **stops and waits for approval** before a legal reminder.
7. **Tamper test** — change ₹21,000 to ₹12,000: the altered block and every later block light up. The real ledger stays intact.
8. **AI monitoring** — "Rule parser: 100% on its own set, 60% on the hold-out. Gemini on the same hold-out: [your measured number]. Every call is logged; the recent calls you just made are here."

If the Wi-Fi fails: set `SAAJHA_FORCE_OFFLINE=1`, restart, and show that every live screen still works on level 2 of the fallback ladder.
