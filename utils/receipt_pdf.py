"""Generate cash receipt PDF directly using reportlab (no LibreOffice/poppler needed)."""

import os
import random
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from PIL import Image as PILImage

# Fixed Wellcome issuer info
ISSUER = {
    "name": "Mr. Terry.Su",
    "phone": "008613609023860",
    "address": "UNIT 1021, BEVERLEY COMMERCIAL CENTRE, 87-105 CHATHAN ROAD SOUTH, TSIM SHA TSUI, HK",
    "company": "WELLCOME (INTERNATIONAL) LIMITED",
}


def generate_receipt_pdf(client: dict, receipt_data: dict, output_path: str = None) -> str:
    """
    Generate a cash receipt PDF. No external dependencies needed.
    """
    import tempfile
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           leftMargin=20*mm, rightMargin=20*mm,
                           topMargin=15*mm, bottomMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('T', parent=styles['Title'], fontSize=16, spaceAfter=8*mm, alignment=TA_CENTER)
    v = ParagraphStyle('V', parent=styles['Normal'], fontSize=10, leading=14)
    vs = ParagraphStyle('VS', parent=styles['Normal'], fontSize=9, leading=12)
    vl = ParagraphStyle('VL', parent=styles['Normal'], fontSize=8, textColor=colors.grey, leading=10)

    currency = receipt_data.get('currency', 'USD')
    amount = receipt_data.get('payment_amount', receipt_data.get('amount', 0))
    elements = []

    # Title
    elements.append(Paragraph("CASH RECEIPT / 收款收据", title_style))

    # Header table: left=client info, right=issuer+payment info
    c = client
    rd = receipt_data
    header_data = [
        [
            _label_v("Project:", rd.get('project_name', ''), vl, v),
            _label_v("Out by:", rd.get('issuer_name', ISSUER['name']), vl, v),
        ],
        [
            _label_v("Project Date:", rd.get('project_date', ''), vl, v),
            _label_v("Tel:", ISSUER['phone'], vl, v),
        ],
        [
            _label_v("Venue:", rd.get('venue', ''), vl, v),
            _label_v("Adr:", ISSUER['address'], vl, v),
        ],
        [Spacer(1, 4*mm), Spacer(1, 4*mm)],
        [
            _label_v("From:", c.get('full_name', ''), vl, v),
            _label_v("Project Code:", rd.get('project_code', ''), vl, v),
        ],
        [
            _label_v("Address:", c.get('address', ''), vl, v),
            "",
        ],
        [
            _label_v("Atten:", c.get('contact', ''), vl, v),
            _label_v("Payment Date:", _fmt(rd.get('payment_date')), vl, v),
        ],
        [
            _label_v("Tel:", c.get('phone') or c.get('email', ''), vl, v),
            _label_v("Gained Date:", _fmt(rd.get('gained_date')), vl, v),
        ],
        [
            _label_v("Email:", c.get('email', ''), vl, v) if c.get('email') and c['email'] != '（待补充）' else "",
            _label_v("Payment Method:", rd.get('payment_method', 'BANK'), vl, v),
        ],
    ]
    t = Table(header_data, colWidths=[doc.width * 0.55, doc.width * 0.45])
    t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 3)]))
    elements.append(t)
    elements.append(Spacer(1, 10*mm))

    # Body
    body = (
        f"Received From <b>{ISSUER['company']}</b> "
        f"The amount of <b>{currency} {amount:,.2f}</b><br/>"
        f"For the <b>{rd.get('project_name', '')}</b> Project"
    )
    elements.append(Paragraph(body, v))
    elements.append(Spacer(1, 18*mm))

    # Signature
    sig_data = [
        ["Name: ____________________", "", ""],
        [f"Date: {_fmt(rd.get('gained_date'))}", "", ""],
        ["Signature: ____________________", "", ""],
    ]
    st = Table(sig_data, colWidths=[doc.width * 0.33]*3)
    st.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('TOPPADDING', (0, 0), (-1, -1), 6)]))
    elements.append(st)

    doc.build(elements)

    # Overlay stamp directly (no pdf2image/poppler)
    _overlay_stamp_pure(output_path)

    return output_path


def _label_v(label, value, ls, vs):
    return Paragraph(f"<font color='grey' size='8'>{label}</font> <font size='10'>{value}</font>", vs)


def _fmt(val):
    if val is None: return ""
    if isinstance(val, datetime): return val.strftime('%Y/%m/%d')
    return str(val)[:10]


def _overlay_stamp_pure(pdf_path: str):
    """Overlay stamp using PyPDF2 (no poppler needed)."""
    stamp_png = _find_stamp()
    if not stamp_png:
        return

    try:
        import pypdf
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.utils import ImageReader
        import io

        # Load and resize stamp
        stamp_img = PILImage.open(stamp_png).convert("RGBA")
        pw, ph = float(A4[0]), float(A4[1])
        stamp_w = pw * 0.18
        ratio = stamp_w / stamp_img.width
        stamp_h = stamp_img.height * ratio

        # Position: bottom right with variation
        mx = pw * 0.04 + random.randint(-15, 15)
        my = ph * 0.06 + random.randint(-10, 10)
        x = pw - stamp_w - mx
        y = my

        # Create stamp overlay PDF
        stamp_buf = io.BytesIO()
        c = rl_canvas.Canvas(stamp_buf, pagesize=(pw, ph))
        c.drawImage(ImageReader(stamp_img), x, y, stamp_w, stamp_h, mask='auto')
        c.save()
        stamp_buf.seek(0)

        # Merge with original PDF
        reader = pypdf.PdfReader(pdf_path)
        writer = pypdf.PdfWriter()
        stamp_page = pypdf.PdfReader(stamp_buf).pages[0]

        for page in reader.pages:
            page.merge_page(stamp_page, over=True)
            writer.add_page(page)

        with open(pdf_path, 'wb') as f:
            writer.write(f)
    except Exception:
        pass  # Stamp is optional, skip if fails


def _find_stamp():
    for p in [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_500.png"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_final.png"),
        "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_500.png",
    ]:
        if os.path.exists(p):
            return p
    return None
