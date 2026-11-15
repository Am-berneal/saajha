# Saajha backend

FastAPI + SQLite + Google Gemini. Serves the prototype (`../index.html`) and the live API on **http://localhost:8000**.

## Run (Windows PowerShell, one line at a time)

```powershell
cd saajha\backend
copy .env.example .env
notepad .env
.\run.bat
```

Put your free key from https://aistudio.google.com/apikey after `GEMINI_API_KEY=` and save.
`run.bat` makes a virtual environment, installs `requirements.txt`, runs the tests, runs the baseline evaluation and starts the server.

Manual steps if you prefer:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
python eval\run_eval.py --engine rules
python app.py
```

If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `run.bat`.

## Measure AI quality with your key

```powershell
python eval\run_eval.py --engine gemini
```

80 calls (about 1–2 minutes on the free tier). Results go to `data/eval_gemini.json` and appear on the **AI monitoring** screen. Compare with the rule-parser baseline in `data/eval_rules.json`.

## Fallback ladder

| Level | When | What runs |
|---|---|---|
| 1 | Key set, Gemini reachable | Gemini reads audio / photo / text → JSON schema (pydantic) → 1 retry on invalid output |
| 2 | No key, network down, or invalid output twice | Browser speech (hi-IN) transcript + rule-based Hindi/Hinglish parser; asks the owner when unsure |
| 3 | No backend | `index.html` demo mode with sample data |

Set `SAAJHA_FORCE_OFFLINE=1` in `.env` to show level 2 on purpose.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | Backend, AI, ledger, tests, agent, simulated list |
| POST | `/api/invoice/from-text` | `{text}` → invoice draft + rules-engine totals |
| POST | `/api/invoice/from-audio` | multipart `file`, optional `transcript` |
| POST | `/api/invoice/from-image` | multipart `file` (photo of a bill) |
| POST | `/api/invoice/issue` | sign `InvoiceCreated` with the supplier key |
| POST | `/api/invoice/accept` | sign `BuyerAccepted`, compute MSMED due date |
| GET | `/api/rules/payment` | due date, days late, Sec 16 interest |
| POST | `/api/notice/explain` | notice photo / PDF / text → plain Hindi + deadline |
| GET | `/api/ledger/verify/{invoice}` | recompute hashes and verify signatures |
| POST | `/api/ledger/tamper-test` | edit a copy, show what breaks (real ledger untouched) |
| POST | `/api/agent/cases` · `/run` · `/decision` | Munshi agent case, run loop, owner approval |
| GET | `/api/ims/match` | purchase-bill matching on sample portal data (simulated) |
| GET | `/api/ai/calls` · `/api/eval/latest` | AI call log and evaluation results |

## What is real and what is simulated

Real: AI extraction, rules engine, ledger + Ed25519 signatures, tamper detection, agent planning/memory/recovery/approval, IMS matching logic, evaluation, tests.
Simulated (labelled in the UI): GST portal / GSP filing, IMS portal data, TReDS, WhatsApp/SMS/voice delivery (the agent's channel results come from a scripted "buyer world"), Account Aggregator.

Private keys for the ledger are created on first run in `data/keys/` and never leave your machine. `data/` and `.env` are git-ignored.
