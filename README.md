# Invoice Desk

ASA PS-1: **Next.js UI + Python/FastAPI backend + one Gemini model + CSV reference records + SQLite history.** No Streamlit interface, Zamp, Pace, agent framework or payment execution.

For a free hosted deployment with durable history, see [DEPLOYMENT.md](DEPLOYMENT.md): the optional PostgreSQL backend preserves local SQLite for development.

Live demo: https://invoice-desk-6smc.onrender.com. For a recording walkthrough, see [DEMO.md](DEMO.md). Current measured results and remaining checks are recorded in [TEST-STATUS.md](TEST-STATUS.md).

## Local setup

Python 3.11+, Node 20.9+ and npm. In this folder:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
# Preserve an existing .env. Otherwise copy .env.example to .env.
$env:LOCAL_SETUP='1'
.venv/Scripts/python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

In a second terminal, in `web`:

```powershell
npm ci
npm run dev
```

Open http://127.0.0.1:3000. Next.js forwards `/api/*` to Python on 8000. Port 8501 was the obsolete prototype.

**Connection** always offers your own password-masked Gemini key entry and model ID. A session key overrides the server key, stays in backend memory and is identified by an HttpOnly cookie. It is never returned by the API or placed in localStorage, source or history. An entered key necessarily passes through the password field and request to our backend; remote hosting must use HTTPS. Optional local saving writes ignored `.env` only with `LOCAL_SETUP=1`. Never enable that mode on public hosting. “Use server key instead” clears only the session override, not a persisted key. Server restart clears session keys. Saving settings does not verify API access or enable billing.

## How extraction becomes a decision

1. Browser uploads a PDF. The local object-URL preview shows its original pages.
2. Python checks PDF validity, size/pages/encryption and SHA-256 duplicates.
3. Gemini receives the PDF and JSON schema. Native document vision handles digital PDFs and scans; separate OCR is not yet justified by testing.
4. Gemini returns fixed fields: vendor, invoice number/date, PO reference, currency, line items, subtotal, tax, total, quotes and uncertainty. Missing or illegible values must be null; no missing printed values may be calculated or guessed.
5. Pydantic validates shape and types. Valid JSON is not proof of factual correctness.
6. Python matches trusted CSV vendors/POs using extracted values. **The LLM does not generate or execute SQL.** SQLite stores run history; reference records remain CSV.
7. Python checks arithmetic using Decimal, required fields, vendor approval, PO ownership/status/currency, individual/aggregate balances, line allocations and duplicates.
8. SQLite validation plus insertion share `BEGIN IMMEDIATE`: concurrent runs cannot both consume the same remaining balance. Only approved decisions reserve balance, never transfer money.
9. FastAPI streams actual stage messages and the final report to Next.js. History shows status, checks, source evidence, usage and downloadable JSON.

Code: `web/app/page.js` / `globals.css` are the interface; `api.py` is HTTP/session/streaming; `models.py` is the extraction contract; `extraction.py` calls Gemini; `rules.py` enforces policy; `service.py` orchestrates atomic history.

## Multiple rows under one PO

`purchase_orders.csv`: one header per ID, vendor, currency, tax-inclusive limit, opening invoiced amount, status. `purchase_order_lines.csv`: many lines per ID, each with a line ID, description, net ceiling and opening invoiced amount. PO-1001 has Office supplies (10) and Printer paper (20). Never sum repeated header limits as separate commitments.

Python matches unique exact normalized descriptions, aggregates invoice items targeting the same line, checks prior approved net consumption per line, then checks overall tax-inclusive PO balance. Different wording, multiple candidate lines or duplicate headers need review. LLM semantic candidate suggestions are **not implemented**. They could help a reviewer later, without deciding financial allocations or overriding limits.

Opening amounts are a baseline; do not also insert those historical invoices into app history. Keep reference records fixed during testing. Net line and tax-inclusive header limits are independent constraints. No PO amendment/version workflow yet.

## Policy and limitations

One invoice per PDF, 1–10 pages, 10 MB. USD non-negative debit invoices only; no FX, credits or discounts. Exact vendor name matching is an assumption, not independent identity verification.

Arithmetic tolerance: **absolute USD 0.02 inclusive** per quantity × price, line sum and subtotal + tax comparison. Printed values remain unchanged. **PO header and line limits have zero tolerance.**

Duplicates use bytes plus normalized vendor/invoice number. Even prior extracted review/rejected identities block reuse. No correction/resubmission override; use a fresh database path for clean rehearsals. PDFs are not retained in history: re-upload to compare old runs to original pages.

Quotes and clarity flags are model-reported and can be wrong. Missing evidence/uncertainty blocks approval, but silent hallucinations remain possible. No calibrated confidence or independent OCR check. Human review is a queue/status, not a correction editor or manual approval workflow. Provider failures save needs-review with no reservation; no raw errors/keys in history. One provider attempt per processing run.

This is a **shared interview workspace**, not multi-tenant SaaS. Session keys are isolated, history is shared. One backend worker, in-memory sessions reset on restart. The public demo deliberately has its optional workspace password disabled; use synthetic data only. Visitors can consume a configured server key's quota without seeing the key. Remove the server Gemini key when the owner finishes recording; visitors can then supply their own session key. Database credentials remain private on the backend. Future production work: proper identity/roles, session expiry/rate limiting, audited corrections, stronger vendor IDs and measured extraction accuracy.

## Verify

```powershell
.venv/Scripts/python create_samples.py
.venv/Scripts/python -m pytest -q
# In web:
npm run build
```

Twenty-three backend tests pass, including streamed fixture processing, key isolation, password/origin checks, concurrency, multiple lines, ambiguity, sanitized database failures, and the Neon pooler regression. The Next.js production build previously passed. Real deployed Gemini extraction has succeeded for digital and clear scanned PDFs; see [TEST-STATUS.md](TEST-STATUS.md) for current scenario results. Fixtures alone do not establish Gemini accuracy.

| PDF, in order on fresh history | Expected | Reason |
|---|---|---|
| 01_success | approved | 550 fits PO-1001 and its supplies line |
| 02_duplicate_renamed | rejected | Same bytes, different filename |
| 03_split_first | approved | PO-2001: 100 opening + 600 |
| 04_split_exceeds | rejected | 400 exceeds remaining 300 |
| 05_unclear_scan | needs-review | Illegible image-only source; verify real model behavior |
| 06_tolerance | approved | 100 + 10 vs 110.01 |
| 07_clear_scan | approved | Legible image-only native vision test |

`.expected.json` files are explicit test fixtures; the live app never loads them. Record actual fields, status, latency and usage versus each original. Never fake scan quality based on filename.

## One-week plan

1. Process map, understand contract, notify coordinator of PS-1 yourself.
2. Get real Gemini success and clear-scan extraction working; inspect every field.
3. Explain and modify rules yourself, including Decimal and matching.
4. Run four edge cases; understand header/line balances and reservations.
5. Rehearse UI, audit reports, provider failure behavior.
6. Deploy with durable history; verify after restart; practice narration.
7. Record under five minutes; submit runnable URL and video URL, no slides.

## 4:45 demo script

- 0:00–0:25: AP comparison problem; decision support, no payment execution.
- 0:25–1:45: Run success live; stages, original, fields/evidence, balances.
- 1:45–2:25: Renamed duplicate; prior run and skipped extraction.
- 2:25–3:15: Split invoices: 900 available, 600 reserved, next 400 rejected.
- 3:15–3:50: Review queue, JSON export, multi-line PO register.
- 3:50–4:45: Architecture, tolerance, scan/model limitations and persistence. Allow actual API latency.

Interview: Next.js controls UX; FastAPI retains understandable Python logic. LLM understands documents, Python enforces policy. SQLite provides transactions for a small single-server demo. OCR comes only after measured native-vision failures. Next improvements: audited corrections, SKU matching, stronger identity and extraction accuracy evaluation.

## Durable deployment

The live free deployment uses Render plus Neon PostgreSQL, described in [DEPLOYMENT.md](DEPLOYMENT.md). The following is an alternative local/server Docker setup: `compose.yaml` runs Next.js and one internal Python API, with SQLite on the named `invoice_history` volume.

1. Choose a host that preserves volumes through redeploys. Do not assume serverless/local cloud SQLite persists.
2. Configure host secrets / ignored `.env`: `GEMINI_API_KEY`, `GEMINI_MODEL`, strong `APP_PASSWORD`, `APP_ORIGIN=https://your-domain`, `COOKIE_SECURE=1`. Keep `LOCAL_SETUP=0`.
3. `docker compose up --build -d`; expose only web port 3000 behind HTTPS. API remains internal; Next build forwards to `http://api:8000`.
4. One backend worker. Back up SQLite consistently; do not run `docker compose down -v` unless erasing history intentionally.
5. Test success/duplicate, restart/redeploy, verify history/balances survive. Proxy must permit streaming without buffering and at least 120 seconds per extraction.
6. Ask before paid hosting, publication or billing. Use synthetic interview data.

Local Docker uses `APP_ORIGIN=http://127.0.0.1:3000`, `COOKIE_SECURE=0`; secure cookies require HTTPS. Sessions reset on restart, SQLite history survives with the volume.

## Model / cost reference

Checked November 7, 2026: stable `gemini-3.5-flash-lite`, PDF input and structured output, listed by the configured key and successful in deployed extraction tests. It is the configurable default. Earlier `gemini-3.8-flash` requests repeatedly returned provider errors from the deployment; there is no automatic multi-model fallback. Official sources: https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite, https://ai.google.dev/gemini-api/docs/document-processing, https://ai.google.dev/gemini-api/docs/pricing.

Published standard paid rates: $0.30/million input, $2.50/million output including thinking. Illustrative 3,000 input + 2,000 billable output = $0.0059/request (~$0.59/100), excluding hosting/taxes. The model has a free tier subject to quotas. Actual vision/thinking usage varies. Free-tier data-use terms differ from the paid tier: use synthetic invoices for this public demo. No paid plan or billing activation was added.
