"""Cash receipt PDF — matches the Excel template layout exactly."""

import os, io, random
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from PIL import Image as PILImage
import pypdf
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

PAGE_W, PAGE_H = A4

ISSUER_FIXED = {
    "name": "Mr. Terry.Su",
    "phone": "008613609023860",
    "addr": "UNIT 1021, BEVERLEY COMMERCIAL CENTRE, 87-105 CHATHAN ROAD SOUTH, TSIM SHA TSUI, HK",
    "company": "WELLCOME (INTERNATIONAL) LIMITED",
}


def generate_receipt_pdf(client: dict, receipt_data: dict, output_path: str = None) -> str:
    import tempfile
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           leftMargin=18*mm, rightMargin=18*mm,
                           topMargin=14*mm, bottomMargin=14*mm)

    # Styles
    s = getSampleStyleSheet()
    title = ParagraphStyle('T', fontSize=16, alignment=TA_CENTER, spaceAfter=6*mm)
    label = ParagraphStyle('L', fontSize=8, textColor=colors.HexColor('#888888'), leading=10)
    value = ParagraphStyle('V', fontSize=9, leading=12)
    body = ParagraphStyle('B', fontSize=10, leading=14, spaceBefore=4*mm, spaceAfter=4*mm)
    sig = ParagraphStyle('S', fontSize=9, leading=15)

    c = client; rd = receipt_data
    cur = rd.get('currency', 'USD')
    amt = rd.get('payment_amount', rd.get('amount', 0))
    cl = "RMB" if cur == "RMB" else "USD"

    elements = [Paragraph("CASH RECEIPT / 收款收据", title)]

    # Two-column header data
    left_data = [
        ("項目 / Project", rd.get('project_name','')),
        ("項目日期 / Project Date", rd.get('project_date','')),
        ("地点 / Venue", rd.get('venue','')),
        ("", ""),
        ("来自 / From", c.get('full_name','')),
        ("地址 / Address", c.get('address','')),
        ("聯繫人 / Atten", c.get('contact','')),
        ("電話 / Tel", c.get('phone') or c.get('email','')),
        ("電子郵箱 / Email", c.get('email','') if c.get('email') and c['email'] != '（待补充）' else ''),
    ]

    right_data = [
        ("開具人 / Out by", rd.get('issuer_name', ISSUER_FIXED['name'])),
        ("电话 / ID", ISSUER_FIXED['phone']),
        ("联系地址 / Adr", ISSUER_FIXED['addr']),
        ("", ""),
        ("項目編號 / Project Code", rd.get('project_code','')),
        ("付款日期 / Payment Date", _dt(rd.get('payment_date'))),
        ("到款日期 / Gained Date", _dt(rd.get('gained_date'))),
        ("付款方式 / Payment Method", rd.get('payment_method','BANK')),
    ]

    # Build table rows
    table_rows = []
    max_rows = max(len(left_data), len(right_data))
    for i in range(max_rows):
        l_label, l_val = left_data[i] if i < len(left_data) else ("", "")
        r_label, r_val = right_data[i] if i < len(right_data) else ("", "")

        if not l_label and not r_label:
            table_rows.append([Spacer(1, 4*mm), Spacer(1, 4*mm)])
        else:
            l_cell = Paragraph(f'<font size="8" color="#888888">{l_label}</font><br/><font size="9">{l_val}</font>', value) if l_label else ""
            r_cell = Paragraph(f'<font size="8" color="#888888">{r_label}</font><br/><font size="9">{r_val}</font>', value) if r_label else ""
            table_rows.append([l_cell, r_cell])

    tbl = Table(table_rows, colWidths=[doc.width * 0.54, doc.width * 0.46])
    tbl.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
    ]))
    elements.append(tbl)

    # Body text
    body_txt = (
        f"Received From <b>{ISSUER_FIXED['company']}</b>    "
        f"The amount of <b>{cl} {amt:,.2f}</b><br/>"
        f"For the <b>{rd.get('project_name','')}</b> Project"
    )
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(body_txt, body))

    # Signature
    d = rd.get('gained_date', datetime.now())
    ds = d.strftime('%Y/%m/%d') if isinstance(d, datetime) else str(d)[:10]
    sig_txt = f"Name：<br/><br/>Date：{ds}<br/><br/>Signature：<br/>"
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph(sig_txt, sig))

    doc.build(elements)

    # Overlay stamp at Name area
    _overlay_stamp(output_path, at_name=True)

    return output_path


def _dt(val):
    if val is None: return ''
    if isinstance(val, datetime): return val.strftime('%Y-%m-%d')
    return str(val)[:10]


def _overlay_stamp(pdf_path: str, at_name: bool = False):
    """Overlay blue stamp. at_name=True places near the signature area."""
    for p in [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_500.png"),
        "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_500.png",
    ]:
        if os.path.exists(p):
            stamp_file = p
            break
    else:
        return

    stamp_img = PILImage.open(stamp_file).convert("RGBA")
    pw, ph = float(PAGE_W), float(PAGE_H)

    stamp_w = pw * 0.20
    ratio = stamp_w / stamp_img.width
    stamp_h = stamp_img.height * ratio

    if at_name:
        # Near the Name/Signature area: left side, bottom portion
        x = int(pw * 0.12) + random.randint(-15, 15)
        y = int(ph * 0.15) + random.randint(-10, 10)
    else:
        x = pw - stamp_w - int(pw * 0.04) - random.randint(-15, 15)
        y = int(ph * 0.06) + random.randint(-10, 10)

    stamp_r = stamp_img.resize((int(stamp_w), int(stamp_h)), PILImage.LANCZOS)

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
    c.drawImage(ImageReader(stamp_r), x, y, stamp_w, stamp_h, mask='auto')
    c.save()
    buf.seek(0)

    reader = pypdf.PdfReader(pdf_path)
    writer = pypdf.PdfWriter()
    overlay = pypdf.PdfReader(buf).pages[0]
    for page in reader.pages:
        page.merge_page(overlay, over=True)
        writer.add_page(page)
    with open(pdf_path, 'wb') as f:
        writer.write(f)
