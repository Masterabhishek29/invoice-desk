# Verification status

- November 7 deployment diagnostics update: 21 Python tests pass. Added database readiness (`/api/ready`), sanitized HTTP 503 responses for Postgres connection failures, and tests that credentials never appear in those responses. These tests simulate provider failures; they do not establish a repaired Neon connection. The last live checks returned 500 for history and purchase orders before this update. Live readiness, Gemini success, and restart persistence remain pending.
- Sixteen Python tests passed, including duplicate detection, cumulative and line limits, ambiguity, concurrency, API streaming, key isolation, origin and password protection. HTTP processing tests use explicit extraction fixtures.
- Next.js 16.4.5 production build passed. Browser verified dashboard, connection settings, multiple-line PO register and workspace. Full browser upload/extraction success is not yet verified. Streamlit UI has been removed.
- Clean invoice, clear image-only scan and unclear image-only scan were rendered and visually inspected.
- The configured API key successfully listed models; gemini-3.8-flash was present.
- Actual live PDF extraction returned HTTP 503 UNAVAILABLE from gemini-3.8-flash. A further bounded attempt also failed with ServerError. The application recorded needs-review and reserved no balance. A successful live extraction and the live scenario suite remain unverified; fixture tests do not establish model accuracy.
- Public deployment and restart persistence have not yet been verified.

The key is in an ignored local .env file. Do not include it in archives, commits, recordings or deployment images.

Latest check: restarted local services; frontend and proxied API return HTTP 200. Fixed a proxy idle timeout using stream heartbeats and a 120-second proxy timeout. A real synthetic PDF now completes the full HTTP workflow and records needs-review, because Gemini still returns ServerError. No invoice fields or successful approval were returned. All 16 tests pass after the fix.
