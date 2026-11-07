# Verification status - November 7, 2026

## Passed

- 23 Python tests: monetary policy, duplicates, cumulative and PO-line limits, concurrent reservations, uncertain extraction, streaming API, key isolation, origin/password checks, credential-safe storage errors, readiness, and pooled Postgres compatibility. Automated extraction tests explicitly use fixtures, not Gemini.
- Actual public deployment: database readiness, history and PO endpoints return HTTP 200. Fixed the Neon pooler rejecting a startup timeout by using a transaction-local timeout. Existing database credentials were retained.
- Real deployed Gemini 3.5 Flash-Lite extraction and Python validation: a digital USD 550 invoice approved; the identical renamed PDF rejected with extraction skipped; USD 600 approved against PO-2001; a following USD 400 rejected against its USD 300 remainder; unclear image-only scan routed to review; clear image-only scan approved.
- A real local extraction using the revised readability-only prompt approved a clearly printed one-cent discrepancy within the USD 0.02 tolerance. Genuinely unclear extraction remains reviewable regardless of arithmetic tolerance.
- The earlier Next.js production build passed. Prior browser checks covered dashboard, settings, PO register and workspace. Current live scenario verification uses the deployed HTTP API; a fresh full browser recording remains the owner's next step.
- Publication files and fetched Git history were scanned for the known private Gemini key/demo password and credential patterns; no matches were found. Secrets remain excluded from source and archives.

## Pending final release checks

- Deploy the updated extraction prompt and verify the fresh tolerance PDF against the deployed model.
- Replace the running Render instance and verify run IDs and PO balances survive unchanged.

## Measured limitations

Gemini 3.8 Flash repeatedly returned provider ServerError responses from the deployed host, despite one successful local extraction. Gemini 3.5 Flash-Lite succeeded in the deployed workflow and is now the configurable default. No automatic model fallback is used.

An earlier tolerance run was sent to review because the model treated an arithmetic discrepancy as extraction uncertainty. The revised prompt separates legibility from accounting checks; Python retains model-reported readability uncertainty and enforces tolerance itself. Earlier failed/review runs remain in the audit history, not erased or relabeled.

The public demo deliberately has no workspace password; use synthetic data. Visitors can consume the privately configured server key's quota. Remove that Gemini key after recording if reviewers should supply their own. Do not expose Render environment values or Neon connection strings in a recording. A code scan is not a full penetration test.
