"""Fixture tests verify rules/storage, not Gemini extraction accuracy."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).parents[1]))
from models import Invoice
from rules import validate
from service import process, history

ROOT = Path(__file__).parents[1]


def fixture(name):
    return Invoice.model_validate_json((ROOT / "samples" / f"{name}.expected.json").read_text())


def run(name, db, filename=None):
    return process((ROOT / "samples" / f"{name}.pdf").read_bytes(), filename or f"{name}.pdf", db, "test", "fixture-not-a-model", extractor=lambda *args: (fixture(name), {}))


def test_happy_duplicate(tmp_path):
    db = tmp_path / "history.sqlite3"
    assert run("01_success", db)["decision"] == "approved"
    assert run("01_success", db, "different-name.pdf")["decision"] == "rejected"
    assert len(history(db)) == 2


def test_cumulative(tmp_path):
    db = tmp_path / "history.sqlite3"
    assert run("03_split_first", db)["decision"] == "approved"
    second = run("04_split_exceeds", db)
    assert second["decision"] == "rejected"
    limit = next(c for c in second["checks"] if c["code"] == "cumulative_limit")
    assert limit["values"]["remaining_before"] == "300.00"


def test_review_and_tolerance(tmp_path):
    db = tmp_path / "history.sqlite3"
    assert run("05_unclear_scan", db)["decision"] == "needs-review"
    assert run("06_tolerance", db)["decision"] == "approved"


def test_identity_duplicate_changed_pdf(tmp_path):
    first = run("01_success", tmp_path / "h.db")
    decision, checks = validate(fixture("01_success"), [first])
    assert decision == "rejected"
    assert next(c for c in checks if c["code"] == "duplicate_identity")["status"] == "reject"


@pytest.mark.parametrize("delta,expected", [("110.02", "approved"), ("110.03", "needs-review")])
def test_tolerance_boundary(delta, expected):
    inv = fixture("06_tolerance").model_copy(update={"total": delta})
    assert validate(inv, [])[0] == expected


def test_tolerance_never_overrides_unclear_extraction():
    inv = fixture('06_tolerance').model_copy(update={'quality': 'uncertain', 'uncertainties': ['Printed total is blurry']})
    assert validate(inv, [])[0] == 'needs-review'


def test_failure_and_invalid_pdf(tmp_path):
    result = process(b"not PDF", "bad.pdf", tmp_path / "h.db", "", "test")
    assert result["decision"] == "needs-review"
    def fail(*args):
        raise TimeoutError("secret-like-message-must-not-persist")
    result = process((ROOT / "samples/01_success.pdf").read_bytes(), "valid.pdf", tmp_path / "h.db", "x", "test", extractor=fail)
    assert "secret-like" not in json.dumps(result)
    assert result["decision"] == "needs-review"


def test_concurrent_reservation(tmp_path):
    db = tmp_path / "h.db"
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: run(name, db), ["03_split_first", "04_split_exceeds"]))
    assert sorted(r["decision"] for r in results) == ["approved", "rejected"]
