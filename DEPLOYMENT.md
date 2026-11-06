# Free deployment

For free hosting, use one Render Free web service plus Neon Free PostgreSQL. Next.js exports the client UI during Docker build; Python serves that export and the API from the same HTTPS origin. This is still a real Next.js/React interface. Local development retains the Next.js dev server and SQLite.

Free Render erases local files on restart and sleeps after inactivity. Therefore, configure `DATABASE_URL` to a durable hosted Postgres database; never use local SQLite for this free deployment. Neon currently offers a free Postgres plan without a payment card. Stay on Free; do not add payment methods or activate paid usage. Free quotas/cold starts remain limitations.

1. Create a Neon Free project. Copy its SSL connection string into Render's secret `DATABASE_URL` (never GitHub).
2. Create a Render Free Docker web service using `Dockerfile.render` in this repository. `render.yaml` records the configuration.
3. Configure secret `GEMINI_API_KEY` and a demo `APP_PASSWORD`; `GEMINI_MODEL=gemini-3.8-flash`. `LOCAL_SETUP=0`, `COOKIE_SECURE=1`.
4. The allowed browser origin defaults to Render's `RENDER_EXTERNAL_URL`. For a custom domain, set `APP_ORIGIN` to its exact HTTPS origin.
5. Open the HTTPS URL, sign in with the demo password, run success/edge cases, restart and confirm the stored decisions and PO balances survive.

Backend session keys reset on restart; run history in Postgres does not. Postgres uses a transaction advisory lock around balance validation and reservation. SQLite keeps its `BEGIN IMMEDIATE` behavior locally. The real Postgres connection/concurrency test is required once provisioned; local fixture tests alone do not prove deployed persistence.

Before submission, resolve the currently failing Gemini extraction and verify real invoices end to end. The public source repository and a deployed UI are not by themselves evidence that invoice extraction works.

Official pricing/limitations checked November 7, 2026: https://render.com/docs/free and https://neon.com/pricing.
