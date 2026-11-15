# Saajha: idea brief

**Hackathon:** Tech4Bharat 2026 (Global Accelerators Vision Summit · KAVMS × JanAI × RVCE)
**Theme 3:** MSME Finance & Compliance
**Problem statement 3.1:** Compliance paperwork. Micro enterprises lose time and profit to compliance paperwork
**AI type:** Agentic

## One line

Make the big buyer pay for its micro suppliers' compliance, because since April 2026 the buyer's own GST credit and tax deduction depend on it. The micro owner only sends a voice note.

## Who we serve

A micro enterprise under the MSMED definition (investment up to ₹2.5 crore, turnover up to ₹10 crore), Udyam- and GST-registered, selling B2B, with no accountant on staff.

**Persona:** Meena, 6 tailors, 40–60 B2B invoices a month, files through a local CA.

## Why now (2026)

- **IMS mandatory from 1 April 2026.** ITC in GSTR-3B cannot exceed GSTR-2B; untouched invoices are deemed accepted.
- **CGST Sec 16(2)(aa).** The buyer's ITC depends on the supplier furnishing the invoice in GSTR-1.
- **Income-tax Act 2025, Sec 37(2)(g)** (formerly Sec 43B(h)). Buyer loses the deduction if a micro or small supplier is paid after 15 days (no written terms) or 45 days (written terms).
- **MSMED (Amendment) Act 2026**, in force from 15 Oct 2026: 90-day mediation timelines; delayed-payment claims via the MSME ODR portal. Sec 16 interest is unchanged: compound, monthly rests, 3× RBI bank rate.

## The two losses we measure

**Time:** invoices, sending papers to the CA, return preparation, IMS actions, payment chasing, notices.

**Profit:** late fees and interest, ITC lost in IMS, lost buyers, delayed payments, cost of informal credit, CA data-entry fees.

The **Compliance Loss Statement** reports both every month, per user.

## Solution in seven steps

1. Buyer onboards its micro suppliers (free for them).
2. Supplier speaks or photographs the bill → GST invoice.
3. Buyer taps "Goods received" → acceptance date signed by both (day-zero handshake).
4. Invoice auto-added to GSTR-1/IFF and pre-matched in the buyer's IMS; CA approves in a batch.
5. Shared pay-by clock; polite reminders; Sec 16 interest computed by rules code.
6. "Get paid today" against the confirmed invoice (TReDS / ULI).
7. Notice decoder: photo of a GST notice → plain-language explanation, deadline, draft reply for the CA.

## Agentic by design

The **Munshi agent** owns each invoice as a case: it plans the steps, remembers buyer habits, recovers when a channel fails (WhatsApp → SMS → voice call → JanAI Café) and pauses for the owner's approval before any legal, money or personal-data action.

## Assisted path through JanAI Café

Tasks that need a signature, document or presence (DSC signing, Udyam update, GST registration, bank KYC) go to the nearest JanAI Café, where an operator completes them with the owner.

## Jobs created

- **Saajha Sathi:** local helpers (often JanAI Café operators or commerce students) paid per business onboarded, per assisted task and per active business. Planning assumption: about one Sathi per 150 micro businesses.
- **CA firms** handle more micro clients by reviewing instead of typing, and hire junior staff.
- **Micro suppliers** paid on time can keep workers through payment gaps.

## Five things no competitor combines

1. **Buyer-funded compliance**: the party whose ITC and deduction are at risk pays.
2. **Day-zero acceptance handshake**: the legally decisive date is captured and signed at delivery.
3. **Compliance Loss Statement**: paperwork measured in hours and rupees.
4. **Rules-as-code + regulation watcher**: law as versioned, cited code that updates itself after human approval.
5. **Portable signed proof**: one record serves GST filing, the buyer's audit, the lender and the dispute process.

## Existing players and the gap

| Category | Examples | Gap |
|---|---|---|
| WhatsApp / voice billing and GST | Khatabook, Vyapar, myBillBook, ClearTax WhatsApp agent | Supplier pays and works alone |
| Delayed-payment recovery | Vasuli, Recordent, CredFlow | Adversarial, after the damage |
| Buyer vendor checks | ClearTax vendor compliance | Monitoring only |

## Worked example (illustrative)

- ₹2 lakh invoice paid 90 days late → about ₹8,750 statutory interest (17.25% a year, compounded monthly).
- If the supplier misses GSTR-1 → buyer's ₹36,000 ITC (18%) is stuck.
- Anchor buyer with 300 micro suppliers × ₹1.5 lakh/month = ₹81 lakh GST/month; if 8% of invoices miss the GSTR-1 window, about ₹6.5 lakh ITC is deferred every month. *(8% is an assumption to validate.)*

## Business model

Buyer subscription per active supplier. Supplier: free. CA: free cockpit, paid premium tier. Lender: referral fee on financed invoices. Part of the buyer fee funds Saajha Sathi earnings.

## Field research

See [FIELD-RESEARCH.md](FIELD-RESEARCH.md). Placeholders (hours, rupees, 8% late-filing share) will be replaced with interview findings.

## Risks and answers

| Question | Answer |
|---|---|
| Will buyers pay? | Start with anchors that have hundreds of micro vendors and real exposure: CPSEs (TReDS mandatory), listed companies disclosing MSME payables, large distributors. |
| Legal weight of a WhatsApp tap? | Timestamped evidence of acceptance date and terms, not a substitute for a contract. |
| AI mistakes? | AI only reads and talks; rules code computes; citations on every output; CA signs off. |
| GST filing licence? | Partner with a GST Suvidha Provider. |
| Privacy? | Consent-first under the DPDP Act; buyer sees only invoices addressed to it. |
