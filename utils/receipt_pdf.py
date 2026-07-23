"""Generate cash receipt PDF directly using reportlab (no LibreOffice needed)."""

import os
import tempfile
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm, cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from PIL import Image as PILImage
import numpy as np

PAGE_W, PAGE_H = A4  # 595.27 x 841.89 points

# Fixed Wellcome issuer info
ISSUER = {
    "name": "Mr. Terry.Su",
    "phone": "008613609023860",
    "address": "UNIT 1021, BEVERLEY COMMERCIAL CENTRE, 87-105 CHATHAN ROAD SOUTH, TSIM SHA TSUI, HK",
    "company": "WELLCOME (INTERNATIONAL) LIMITED",
}


def generate_receipt_pdf(client: dict, receipt_data: dict, output_path: str = None) -> str:
    """
    Generate a cash receipt PDF directly.

    client: {'full_name': ..., 'address': ..., 'contact': ..., 'phone': ..., 'email': ...}
    receipt_data: {
        'project_name', 'project_code', 'amount', 'currency',
        'payment_date', 'gained_date', 'payment_method',
        'issuer_name', 'venue', 'project_date'
    }
    """
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".pdf")

    doc = SimpleDocTemplate(output_path, pagesize=A4,
                           leftMargin=20*mm, rightMargin=20*mm,
                           topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=16, spaceAfter=6*mm, alignment=TA_CENTER)
    label_style = ParagraphStyle('Label', parent=styles['Normal'], fontSize=8, textColor=colors.grey, leading=10)
    value_style = ParagraphStyle('Value', parent=styles['Normal'], fontSize=10, leading=13)
    right_style = ParagraphStyle('Right', parent=styles['Normal'], fontSize=10, alignment=TA_RIGHT, leading=13)

    currency = receipt_data.get('currency', 'USD')
    currency_symbol = '$' if currency == 'USD' else '¥'
    amount = receipt_data.get('payment_amount', receipt_data.get('amount', 0))

    elements = []

    # === HEADER TABLE ===
    header_data = [
        # Row 1
        [
            Paragraph("CASH RECEIPT / 收款收据", title_style),
            "",
        ],
        # Spacer
        ["", ""],
        # Row 2 - Left info
        [
            Paragraph(f"<b>Project:</b> {receipt_data.get('project_name', '')}", value_style),
            Paragraph(f"<b>Out by:</b> {receipt_data.get('issuer_name', ISSUER['name'])}", value_style),
        ],
        [
            Paragraph(f"<b>Project Date:</b> {receipt_data.get('project_date', '')}", value_style),
            Paragraph(f"<b>Tel:</b> {ISSUER['phone']}", value_style),
        ],
        [
            Paragraph(f"<b>Venue:</b> {receipt_data.get('venue', '')}", value_style),
            Paragraph(f"<b>Adr:</b> {ISSUER['address']}", value_style),
        ],
        ["", ""],
        # Client info
        [
            Paragraph(f"<b>From:</b> {client.get('full_name', '')}", value_style),
            Paragraph(f"<b>Project Code:</b> {receipt_data.get('project_code', '')}", value_style),
        ],
        [
            Paragraph(f"<b>Address:</b> {client.get('address', '')}", value_style),
            "",
        ],
        [
            Paragraph(f"<b>Atten:</b> {client.get('contact', '')}", value_style),
            Paragraph(f"<b>Payment Date:</b> {_fmt_date(receipt_data.get('payment_date'))}", value_style),
        ],
        [
            Paragraph(f"<b>Tel:</b> {client.get('phone', '') or client.get('email', '')}", value_style),
            Paragraph(f"<b>Gained Date:</b> {_fmt_date(receipt_data.get('gained_date'))}", value_style),
        ],
        [
            Paragraph(f"<b>Email:</b> {client.get('email', '')}", value_style) if client.get('email') and client['email'] != '（待补充）' else "",
            Paragraph(f"<b>Payment Method:</b> {receipt_data.get('payment_method', 'BANK')}", value_style),
        ],
    ]

    header_table = Table(header_data, colWidths=[doc.width * 0.55, doc.width * 0.45])
    header_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('SPAN', (0, 0), (1, 0)),  # Title spans both columns
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 8*mm))

    # === BODY ===
    body_text = (
        f"Received From <b>{ISSUER['company']}</b> "
        f"The amount of <b>{currency} {amount:,.2f}</b><br/>"
        f"For the <b>{receipt_data.get('project_name', '')}</b> Project"
    )
    elements.append(Paragraph(body_text, value_style))
    elements.append(Spacer(1, 15*mm))

    # === SIGNATURE ===
    sig_data = [
        [Paragraph(f"<b>Name:</b> ____________________", value_style), "", ""],
        [Paragraph(f"<b>Date:</b> {_fmt_date(receipt_data.get('gained_date'))}", value_style), "", ""],
        [Paragraph("<b>Signature:</b> ____________________", value_style), "", ""],
    ]
    sig_table = Table(sig_data, colWidths=[doc.width * 0.33, doc.width * 0.33, doc.width * 0.33])
    sig_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
    ]))
    elements.append(sig_table)

    # === STAMP OVERLAY ===
    # Add stamp at bottom right after building
    doc.build(elements)

    # Now overlay stamp
    _overlay_stamp(output_path)

    return output_path


def _fmt_date(val):
    """Format date value for display."""
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime('%Y/%m/%d')
    return str(val)[:10]


def _overlay_stamp(pdf_path: str):
    """Overlay blue stamp at bottom-right of the first page."""
    stamp_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_500.png")
    if not os.path.exists(stamp_path):
        stamp_path = "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_500.png"
    if not os.path.exists(stamp_path):
        return  # No stamp available

    from pdf2image import convert_from_path
    from PIL import Image as PILImg

    images = convert_from_path(pdf_path, dpi=150)
    stamp_img = PILImg.open(stamp_path).convert("RGBA")

    stamped_images = []
    import random
    for page_img in images[:1]:  # First page only
        pw, ph = page_img.size
        stamp_w = int(pw * 0.18)
        ratio = stamp_w / stamp_img.width
        stamp_h = int(stamp_img.height * ratio)
        stamp_resized = stamp_img.resize((stamp_w, stamp_h), PILImg.LANCZOS)

        margin_x = int(pw * 0.04) + random.randint(-15, 15)
        margin_y = int(ph * 0.06) + random.randint(-10, 10)
        x = pw - stamp_w - margin_x
        y = ph - stamp_h - margin_y

        page_rgba = page_img.convert("RGBA")
        page_rgba.paste(stamp_resized, (x, y), stamp_resized)
        stamped_images.append(page_rgba.convert("RGB"))

    if stamped_images:
        stamped_images[0].save(pdf_path, "PDF")
