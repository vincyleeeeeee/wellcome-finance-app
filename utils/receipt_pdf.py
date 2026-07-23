"""Generate cash receipt PDF by rendering the Excel template, then stamping."""

import os
import io
import random
import openpyxl
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.pdfgen import canvas as rl_canvas
from PIL import Image as PILImage
import pypdf


def generate_receipt_pdf(client: dict, receipt_data: dict, output_path: str = None) -> str:
    """
    Generate receipt PDF by:
    1. Filling the Excel template (correct layout)
    2. Rendering it to PDF
    3. Overlaying stamp
    """
    import tempfile
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".pdf")

    # Get app template directory
    app_dir = os.path.dirname(os.path.dirname(__file__))
    tmpl = os.path.join(app_dir, "templates", "Cash-Receipt-Template.xlsx")
    if not os.path.exists(tmpl):
        tmpl = "/Users/vincy/Documents/Wellcome/项目/_模板/Cash-Receipt-Template.xlsx"

    # Fill the template
    wb = openpyxl.load_workbook(tmpl)
    ws = wb.active

    c = client
    rd = receipt_data
    currency = rd.get('currency', 'USD')
    amount = rd.get('payment_amount', rd.get('amount', 0))

    # Fill cells
    ws['C3'] = rd.get('project_name', '')
    ws['C4'] = rd.get('project_date', '')
    ws['C5'] = rd.get('venue', '')
    ws['C7'] = c.get('full_name', '')
    ws['C8'] = c.get('address', '')
    ws['C9'] = c.get('contact', '')
    ws['C10'] = c.get('phone') if c.get('phone') and c['phone'] != '（待补充）' else ''
    ws['C11'] = c.get('email') if c.get('email') and c['email'] != '（待补充）' else ''
    ws['E3'] = rd.get('issuer_name', 'Mr. Terry.Su')
    ws['E8'] = rd.get('project_code', '')
    ws['E9'] = _to_date(rd.get('payment_date'))
    ws['E10'] = _to_date(rd.get('gained_date'))
    ws['E11'] = rd.get('payment_method', 'BANK')

    currency_label = "RMB" if currency == "RMB" else "USD"
    ws['C13'] = (f"Received From  WELLCOME (INTERNATIONAL) LIMITED    "
                 f"The amount of  {currency_label}{amount:,.2f}\n"
                 f"For the {rd.get('project_name', '')}  Project")

    # Signature: write to top-left of merged range D15:D17
    d = rd.get('gained_date', datetime.now())
    if isinstance(d, datetime):
        ds = d.strftime('%Y/%m/%d')
    else:
        ds = str(d)[:10]
    ws['D15'] = f"Name：\n\nDate：{ds}\n\nSignature：\n"

    # Save xlsx to bytes
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_buf.seek(0)
    xlsx_bytes = xlsx_buf.read()

    # Render xlsx to PDF
    _xlsx_to_pdf(xlsx_bytes, output_path)

    # Overlay stamp
    _overlay_stamp_pure(output_path)

    return output_path


def _to_date(val):
    if val is None: return ''
    if isinstance(val, datetime): return val.strftime('%Y-%m-%d')
    return str(val)[:10]


def _xlsx_to_pdf(xlsx_bytes: bytes, pdf_path: str):
    """Render an xlsx file as a PDF using reportlab."""
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    ws = wb.active

    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                           leftMargin=15*mm, rightMargin=15*mm,
                           topMargin=12*mm, bottomMargin=12*mm)

    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('T', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER, spaceAfter=6*mm)
    label_s = ParagraphStyle('L', parent=styles['Normal'], fontSize=8, textColor=colors.Color(0.4,0.4,0.4), leading=10)
    val_s = ParagraphStyle('V', parent=styles['Normal'], fontSize=9, leading=12)
    body_s = ParagraphStyle('B', parent=styles['Normal'], fontSize=10, leading=14, spaceBefore=4*mm, spaceAfter=4*mm)
    sig_s = ParagraphStyle('S', parent=styles['Normal'], fontSize=9, leading=14, alignment=TA_LEFT)

    elements = []
    headings_seen = set()

    for row in ws.iter_rows(min_row=1, max_row=ws.max_row):
        cells = []
        for cell in row:
            v = cell.value
            if v is None or str(v).strip() in ('', '.'):
                cells.append('')
                continue

            txt = str(v).replace('\n', '<br/>')
            co = cell.coordinate
            col_letter = co[0]

            # Title (row 1): centering
            if cell.row == 1:
                elements.append(Paragraph(txt, title_s))
                cells = []
                break
            # Section labels (column A): use gray label style
            elif col_letter == 'A':
                label_key = txt.replace('<br/>', ' ').strip()
                if label_key not in headings_seen:
                    headings_seen.add(label_key)
                cells.append('')
            elif col_letter in ('C', 'D'):
                cells.append(txt)
            elif col_letter == 'E':
                cells.append(txt)
            else:
                cells.append('')

        if cells and any(c for c in cells):
            # Filter empty columns
            non_empty = [c for c in cells if c]
            if non_empty:
                # Check if this is the amount body row (row 13)
                if cell and cell.row == 13:
                    for c in cells:
                        if c:
                            elements.append(Paragraph(c, body_s))
                elif cell and cell.row >= 15:
                    # Signature area
                    for c in cells:
                        if c and 'Name' in c or 'Date' in c or 'Signature' in c:
                            elements.append(Paragraph(c.replace('<br/>', '\n'), sig_s))
                else:
                    # Regular two-column layout
                    if len(cells) >= 2 and cells[0]:
                        row_data = [[Paragraph(cells[0], val_s), Paragraph(cells[1], val_s) if len(cells) > 1 else '']]
                        t = Table(row_data, colWidths=[doc.width*0.55, doc.width*0.45])
                        t.setStyle(TableStyle([
                            ('VALIGN', (0,0), (-1,-1), 'TOP'),
                            ('TOPPADDING', (0,0), (-1,-1), 2),
                            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
                            ('LEFTPADDING', (0,0), (-1,-1), 0),
                        ]))
                        elements.append(t)

    doc.build(elements)


def _overlay_stamp_pure(pdf_path: str):
    """Overlay stamp using pypdf (no poppler needed)."""
    stamp_png = None
    for p in [
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_500.png"),
        os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_final.png"),
        "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_500.png",
    ]:
        if os.path.exists(p):
            stamp_png = p
            break

    if not stamp_png:
        return

    try:
        from reportlab.lib.utils import ImageReader
        stamp_img = PILImage.open(stamp_png).convert("RGBA")
        pw, ph = float(A4[0]), float(A4[1])
        stamp_w = pw * 0.18
        ratio = stamp_w / stamp_img.width
        stamp_h = stamp_img.height * ratio
        mx = pw * 0.04 + random.randint(-15, 15)
        my = ph * 0.06 + random.randint(-10, 10)
        x = pw - stamp_w - mx
        y = my

        stamp_buf = io.BytesIO()
        c = rl_canvas.Canvas(stamp_buf, pagesize=(pw, ph))
        c.drawImage(ImageReader(stamp_img), x, y, stamp_w, stamp_h, mask='auto')
        c.save()
        stamp_buf.seek(0)

        reader = pypdf.PdfReader(pdf_path)
        writer = pypdf.PdfWriter()
        stamp_page = pypdf.PdfReader(stamp_buf).pages[0]
        for page in reader.pages:
            page.merge_page(stamp_page, over=True)
            writer.add_page(page)
        with open(pdf_path, 'wb') as f:
            writer.write(f)
    except Exception:
        pass
