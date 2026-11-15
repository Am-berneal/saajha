# Architecture

Saajha is an **agentic system** (Tech4Bharat definition: plans and acts across steps, keeps case memory, recovers from failures, and seeks human approval before money, legal or personal-data actions), built on seven layers. The language model never computes money, dates or deadlines.

## The Munshi agent

Each invoice becomes a **case** with a goal (e.g., "delivery confirmed, then paid by the due date").

| Part | What it does |
|---|---|
| Planner | Breaks the goal into steps: confirm delivery → start clock → remind → escalate |
| Tools | WhatsApp, SMS, voice call (IVR), rules engine, ledger, GSP (simulated), JanAI Café queue |
| Case memory | Per-case and per-buyer facts: preferred channel and time, payment history, bounced numbers, owner's tone and language |
| Recovery policies | Channel fallback (WhatsApp → SMS → voice call → JanAI Café), retries with backoff, mark disputed after N attempts |
| Approval gates | Owner approves legal reminders and signs with DSC; buyer confirms delivery; CA approves filings; consent before bank data |
| Audit | Every plan, action, failure and approval is written to the signed ledger |

```
goal ─► plan ─► act (tool) ─► observe ─► success? ─► next step
                     ▲             │ no
                     └─ recover ◄──┘  (fallback channel / retry / escalate)
   money · legal · personal data ─► pause ─► ask human ─► continue
```

## Assisted path (JanAI Café)

When a step needs a document, authentication or physical presence (DSC signature, Udyam update, GST registration, bank KYC), the agent creates a café task. The operator (a Saajha Sathi) completes it **with** the owner: OTP on the owner's phone, only task documents scanned, owner signs, files deleted from the café PC afterwards.

## Consent and data minimisation

- Voice-read consent at first use; revocable by voice.
- Required: invoices and GST returns. Optional, off by default: bank data (only for "Get paid today").
- Never collected: contacts, location, photo gallery, full bank statements, Aadhaar number.
- Buyers see only invoices addressed to them.

## Layers

```
 WhatsApp / IVR / SMS
        │
 [1] Capture ── speech (Bhashini / IndicConformer) · OCR for bill photos
        │
 [2] Understanding ── LLM → strict e-invoice JSON schema
        │               ├─ buyer resolver (fuzzy + phonetic)
        │               ├─ HSN classifier (top-3 + confidence)
        │               └─ Indian number parser ("dhai hazaar")
        │
 [3] Rules engine (no LLM) ── GST · MSMED Act · Income-tax Act 2025
        │                       versioned rules, effective dates, citations, tests
        │
 [4] Regulation watcher ── reads CBIC / GSTN / MSME notices → drafts rule diff → human approves
        │
 [5] Signed ledger ── InvoiceCreated → BuyerAccepted → AddedToGSTR1 → MatchedInIMS → PaymentReceived
        │               hash-chained, signed by supplier + buyer, exportable as verifiable credential
        │
 [6] Payment reconciliation ── Account Aggregator bank data matched to open invoices
        │
 [7] Prediction ── model forecasts which suppliers will miss GSTR-1; early nudges
        │
 Integrations: GSP (GSTR-1/IFF, IMS) · TReDS · ULI · MSME ODR · Udyam
 Surfaces: supplier app (WhatsApp-first) · buyer dashboard · CA cockpit · public proof page
```

## Guardrails

- LLM output must validate against the schema; failures retry or go to a human.
- Every computed value carries a rule ID and citation.
- Confidence below threshold → one voice question to the owner, or the CA.
- PII encrypted per field, India-region storage, DPDP consent records.
- Buyer sees only invoices addressed to it.

## Evaluation harness

- Test set: 100 voice notes (3 languages) + 50 bill photos.
- Metrics: field accuracy, buyer-match accuracy, HSN top-1/top-3, seconds per invoice, rule-test coverage.

## Hackathon build plan

| Build for real | Mock, clearly labelled SIMULATED |
|---|---|
| Munshi agent loop with case memory + fallback (WhatsApp → SMS) | Voice-call fallback |
| Voice → invoice (2–3 languages) | GST filing (show GSTR-1 JSON) |
| Rules engine with tests (45-day clock, Sec 16 interest) | TReDS / ULI lender quote |
| Signed handshake ledger | ODR submission (evidence PDF) |
| WhatsApp test number | Account Aggregator consent screens |


## What is built now (backend/)

The prototype is no longer only animation. `backend/` contains working code for the AI layer (Gemini with schema validation, retry and fallback), the rules engine with citations, the signed hash-chained ledger with a tamper test, the Munshi agent loop (plan, tools, memory, recovery, approval gate), IMS matching, an evaluation harness with a hold-out set, and 21 automated tests. See `backend/README.md`.
