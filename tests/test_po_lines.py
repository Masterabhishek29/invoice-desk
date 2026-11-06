import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]))
from models import Invoice, LineItem
import rules


def invoice():
    return Invoice.model_validate_json((Path(__file__).parents[1] / 'samples/01_success.expected.json').read_text())


def test_two_lines_under_one_po():
    inv = invoice()
    inv.line_items.append(LineItem(description='Printer paper', quantity='1', unit_price='100.00', amount='100.00', evidence='Page 1: Printer paper 1 100.00'))
    inv.subtotal, inv.tax, inv.total = '600.00', '60.00', '660.00'
    decision, checks = rules.validate(inv, [])
    assert decision == 'approved'
    assert [c['values']['po_line_id'] for c in checks if c['code'] == 'line_match'] == ['10', '20']


def test_line_cap_even_when_header_has_capacity():
    inv = invoice()
    inv.line_items[0].description = 'Printer paper'
    inv.line_items[0].unit_price = inv.line_items[0].amount = '501.00'
    inv.subtotal, inv.tax, inv.total = '501.00', '0.00', '501.00'
    decision, checks = rules.validate(inv, [])
    assert decision == 'rejected'
    assert any(c['code'] == 'po_line_balance' and c['status'] == 'reject' for c in checks)


def test_ambiguous_description_requires_review(monkeypatch):
    original = rules.records
    def duplicate(name):
        rows = original(name)
        if name == 'purchase_order_lines.csv':
            rows.append(dict(rows[0], line_id='30'))
        return rows
    monkeypatch.setattr(rules, 'records', duplicate)
    assert rules.validate(invoice(), [])[0] == 'needs-review'


def test_aggregate_same_line_does_not_bypass_limit():
    inv = invoice()
    inv.line_items[0].description = 'Printer paper'
    inv.line_items[0].unit_price = inv.line_items[0].amount = '300.00'
    inv.line_items.append(inv.line_items[0].model_copy())
    inv.subtotal, inv.tax, inv.total = '600.00', '0.00', '600.00'
    assert rules.validate(inv, [])[0] == 'rejected'
