# Five-minute recording guide

Aim for 4:40, leaving 20 seconds for pauses. Use synthetic PDFs, hide personal tabs, and keep environment-variable and connection-string pages closed. Warm up the free-hosted site before recording.

## Before recording

Open https://invoice-desk-6smc.onrender.com. The public workspace has no password. Do not enter or display an API key while recording. Your server key is configured privately for the recording; removing it afterward means visitors must provide their own key for new extraction. Existing history remains viewable.

Existing sample invoices were used in verification and will now be duplicates. Generate fresh synthetic invoices for a rehearsal or recording; the suffix changes invoice identities without erasing audit history:

```powershell
python create_samples.py --output recording-kit --invoice-suffix=-REC-002 --only 01_success
```

That creates a new successful invoice and an identical renamed copy. Use a new suffix for another rehearsal. Check the PO's remaining balance first; the successful sample is USD 550.00. Repeated approved rehearsals consume real demo reservations, so do not keep processing fresh identities indefinitely. Use prior successful run details if the remaining balance is insufficient. No payment is sent.

## Recording sequence and narration

### 0:00-0:25: Problem and outcome

Show the dashboard.

“Invoice Desk addresses PS-1: invoice processing from PDF to decision. It reads digital and scanned invoices, compares them with trusted vendor and purchase-order records, and produces an approved, needs-review, or rejected decision with evidence. It supports an accounts-payable reviewer and does not transfer money.”

### 0:25-1:35: Successful flow

Upload a fresh success PDF. Show actual stages, the original document, extracted fields, and the final checks.

“The PDF goes to one Gemini model for document understanding. It returns a fixed JSON structure, which Pydantic validates. Missing or unclear values must remain null. Python then checks required fields, vendor and PO ownership, line items, arithmetic, duplicates, and remaining PO balances. Here, show the actual total and approved decision on screen.”

### 1:35-2:20: Meaningful edge case

Upload the identical renamed copy.

“Changing a filename does not create a new invoice. SHA-256 detects identical content and rejects the duplicate without another extraction request. Vendor plus invoice number is also checked to detect the same identity in a changed PDF.”

Point to the duplicate reason and previous run ID. Do not claim a check ran if the report says extraction was skipped.

### 2:20-3:10: Cumulative limits and review

Open the previously verified PO-2001 runs and purchase-order register.

“This PO starts with a USD 1,000 limit and USD 100 already invoiced. The first USD 600 invoice leaves USD 300. The next USD 400 invoice is rejected, even though USD 400 fits the original PO limit. A transaction lock keeps concurrent requests from consuming the same balance.”

Briefly open the unclear-scan review result: “When readability is uncertain, a person must check the source. The system keeps the uncertainty instead of assuming approval.”

### 3:10-4:05: Architecture and the LLM boundary

Show the dashboard or the repository file list, not private account settings.

“Next.js handles the interface. FastAPI keeps the logic in Python. Gemini 3.5 Flash-Lite reads PDFs into validated fields. Python uses Decimal for money and enforces the policy. The LLM does not generate SQL or make financial decisions. PO headers and lines come from CSV records; SQLite stores local history, and Neon PostgreSQL preserves deployed history across instance replacement. Render hosts the app at one URL.”

### 4:05-4:40: Decisions and limitations

“Arithmetic has an inclusive two-cent USD tolerance. PO limits have zero tolerance. Multiple PO lines are checked separately, and ambiguous matches require review. I tested provider failures, real PDFs, scans, duplicates, cumulative limits, and persistence. This prototype currently supports USD, one invoice per PDF, and exact normalized matching. Production work would add user roles, rate limits, audited corrections, and broader measured extraction accuracy.”

## Interview points to understand

- Schema validation guarantees structure, not that the model read every field correctly. Show source quotes and retain human review.
- An unclear scan and a legible arithmetic discrepancy are different: Gemini reports readability; Python applies tolerance.
- Only approved runs reserve balances. Rejected and review runs remain in the audit trail.
- The deployment failed because a Neon pooler rejected a timeout in connection startup options. Setting it locally inside transactions fixed compatibility without exposing or rotating credentials.
- A public URL alone is not verification. Refer to TEST-STATUS.md and describe only tests actually completed.

Upload the actual video with view access, verify it opens without signing into your account, and submit that video link. An empty Drive folder is not a demo video.
