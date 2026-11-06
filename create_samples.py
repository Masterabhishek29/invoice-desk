"""Rebuild synthetic invoices and matching extraction fixtures for isolated tests."""
import json
import shutil
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).parent


def create():
    out = ROOT / "samples"
    out.mkdir(exist_ok=True)
    cases = [
        ("01_success", "NS-001", "Northstar Office Supplies", "PO-1001", "500.00", "50.00", "550.00"),
        ("03_split_first", "CD-001", "Cedar IT Services", "PO-2001", "600.00", "0.00", "600.00"),
        ("04_split_exceeds", "CD-002", "Cedar IT Services", "PO-2001", "400.00", "0.00", "400.00"),
        ("05_unclear_scan", "NS-002", "Northstar Office Supplies", "PO-3001", "100.00", "10.00", "110.00"),
        ("06_tolerance", "NS-003", "Northstar Office Supplies", "PO-3001", "100.00", "10.00", "110.01"),
        ("07_clear_scan", "NS-004", "Northstar Office Supplies", "PO-1001", "100.00", "10.00", "110.00"),
    ]
    for name, number, vendor, po, subtotal, tax, total in cases:
        fields = dict(vendor_name=vendor, invoice_number=number, invoice_date="2026-11-01", po_reference=po, currency="USD", subtotal=subtotal, tax=tax, total=total)
        fixture = dict(**fields, quality="clear", uncertainties=[], evidence={k: f"Page 1: {v}" for k, v in fields.items()}, line_items=[dict(description="Office supplies" if vendor.startswith("Northstar") else "IT support services", quantity="1", unit_price=subtotal, amount=subtotal, evidence=f"Page 1: 1 x {subtotal} = {subtotal}")])
        pdf = canvas.Canvas(str(out / f"{name}.pdf"), pagesize=(595, 842))
        if "scan" in name:
            im = Image.new("RGB", (1190, 1684), "white")
            from PIL import ImageFont
            font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 30) if Path("C:/Windows/Fonts/arial.ttf").exists() else ImageFont.load_default(size=30)
            draw = ImageDraw.Draw(im)
            lines = [vendor, "INVOICE", f"Invoice number: {number}", "Date: 2026-11-01", f"PO reference: {po}", "Currency: USD", f"Office supplies | Qty 1 | Unit {subtotal} | Amount {subtotal}", f"Subtotal: {subtotal}", f"Tax: {tax}", f"TOTAL USD: {total}"]
            for n, text in enumerate(lines):
                draw.text((80, 130+n*90), text, fill="black", font=font)
            if "unclear" in name:
                # A genuinely illegible source, not a hidden text layer or prompt label.
                im = im.resize((149, 211)).resize((1190, 1684)).filter(ImageFilter.GaussianBlur(4))
                fixture.update(quality="unreadable", total=None, uncertainties=["Critical text illegible"], evidence={})
            pdf.drawImage(ImageReader(im), 0, 0, 595, 842)
        else:
            pdf.setFillColorRGB(.08, .2, .29)
            pdf.setFont("Helvetica-Bold", 22)
            pdf.drawString(44, 780, vendor)
            pdf.setFont("Helvetica", 12)
            lines = ["INVOICE", "Bill to: Harbor Operations Ltd (synthetic)", f"Invoice number: {number}", "Date: 2026-11-01", f"PO reference: {po}", "Currency: USD", "Description                 Quantity     Unit price     Amount", f"{fixture['line_items'][0]['description']}     1       {subtotal}       {subtotal}", f"Subtotal: {subtotal}", f"Tax: {tax}", f"TOTAL USD: {total}", "Payment terms: Net 30", "SYNTHETIC TEST DOCUMENT - no payment required"]
            for n, text in enumerate(lines):
                pdf.drawString(44, 725-n*36, text)
        pdf.save()
        (out / f"{name}.expected.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    shutil.copyfile(out / "01_success.pdf", out / "02_duplicate_renamed.pdf")


if __name__ == "__main__":
    create()
