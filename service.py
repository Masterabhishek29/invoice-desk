"""Orchestration and atomic history: the balance check and insert share one lock."""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from extraction import extract, inspect_pdf, PROMPT_VERSION
from rules import validate, RULE_VERSION


class StorageUnavailable(Exception):
    """Safe deployment diagnostic; never include a DSN or provider error text."""
    def __init__(self, code="database_unavailable"):
        self.code = code
        super().__init__(code)


class PostgresHistory:
    """Same narrow history interface; deployed rows outlive the web container."""
    def __init__(self, url):
        import psycopg
        self.db = psycopg.connect(url, connect_timeout=10, options='-c statement_timeout=30000')
        try:
            self.db.execute('SELECT pg_advisory_xact_lock(73451021)')
            self.db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL, seq BIGSERIAL UNIQUE)')
            self.db.commit()
        except Exception:
            self.db.close()
            raise

    def execute(self, sql, params=()):
        if sql == 'BEGIN IMMEDIATE':
            # Serialize balance validation + reservation across backend processes.
            return self.db.execute('SELECT pg_advisory_xact_lock(73451022)')
        return self.db.execute(sql.replace('rowid', 'seq').replace('?', '%s'), params)

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        try:
            self.db.rollback() if kind else self.db.commit()
        finally:
            self.db.close()


def connect(path):
    if os.getenv('DATABASE_URL'):
        import psycopg
        try:
            return PostgresHistory(os.environ['DATABASE_URL'])
        except psycopg.Error as error:
            # Provider messages may contain credentials. Only expose a fixed code.
            auth_failed = (error.sqlstate or '').startswith('28') or 'password authentication failed' in str(error).lower()
            raise StorageUnavailable('database_authentication_failed' if auth_failed else 'database_unavailable') from None
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=30)
    # First-time initialization can race before either connection establishes WAL.
    for attempt in range(30):
        try:
            db.execute("PRAGMA journal_mode=WAL")
            break
        except sqlite3.OperationalError as error:
            if 'locked' not in str(error).lower() or attempt == 29:
                db.close()
                raise
            time.sleep(0.05)
    db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT NOT NULL, payload TEXT NOT NULL)")
    db.commit()
    return db


def history(path):
    with connect(path) as db:
        return [json.loads(row[0]) for row in db.execute("SELECT payload FROM runs ORDER BY created DESC, rowid DESC")]


def process(pdf, filename, path, key, model, stage=lambda text: None, extractor=extract):
    start = time.monotonic()
    run = dict(id=uuid.uuid4().hex[:12], created=datetime.now(timezone.utc).isoformat(), filename=Path(filename).name,
               sha256=hashlib.sha256(pdf).hexdigest(), model=model, prompt_version=PROMPT_VERSION,
               rule_version=RULE_VERSION, invoice=None, usage={}, decision="needs-review", checks=[], stages=[])

    def emit(text):
        run["stages"].append(dict(stage=text, elapsed_seconds=round(time.monotonic()-start, 2)))
        stage(text)

    try:
        emit("1 / 5 · Checking PDF")
        run["pages"] = inspect_pdf(pdf)
        emit("2 / 5 · Checking file fingerprint")
        old = next((r for r in history(path) if r["sha256"] == run["sha256"] and r.get("invoice")), None)
        if old:
            run["invoice"] = old["invoice"]
            run["decision"] = "rejected"
            run["checks"] = [dict(code="duplicate_file", status="reject", reason="Identical PDF bytes already processed, regardless of filename", values={"prior_run": old["id"]})]
            emit("3 / 5 · Duplicate found; extraction skipped")
        else:
            emit("3 / 5 · Gemini reading document and validating structure")
            invoice, run["usage"] = extractor(pdf, key, model)
            run["invoice"] = invoice.model_dump(mode="json")
            emit("4 / 5 · Running Python rules and reserving PO balance")
    except Exception as error:
        # Never persist raw API errors: they can contain sensitive request details.
        run["checks"] = [dict(code="processing_failure", status="review", reason="Document/API/schema processing failed. Check server key, quota, model access and PDF; retry after fixing. No balance reserved.", values={"error_type": type(error).__name__})]
        emit("Processing interrupted; routing to human review")

    with connect(path) as db:
        db.execute("BEGIN IMMEDIATE")
        prior = [json.loads(row[0]) for row in db.execute("SELECT payload FROM runs ORDER BY created DESC, rowid DESC")]
        # Recheck bytes under lock: two simultaneous requests cannot both reserve.
        same = next((r for r in prior if r["sha256"] == run["sha256"] and r.get("invoice")), None)
        if same:
            run["decision"] = "rejected"
            run["checks"] = [dict(code="duplicate_file", status="reject", reason="Identical PDF already processed", values={"prior_run": same["id"]})]
        elif run["invoice"] and not any(c["code"] == "processing_failure" for c in run["checks"]):
            from models import Invoice
            run["decision"], run["checks"] = validate(Invoice.model_validate(run["invoice"]), prior)
        run["duration_seconds"] = round(time.monotonic()-start, 2)
        emit("5 / 5 · Saving audit report")
        db.execute("INSERT INTO runs (id, created, payload) VALUES (?, ?, ?)", (run["id"], run["created"], json.dumps(run)))
    return run
