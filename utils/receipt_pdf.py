"""Cash receipt PDF — generates xlsx from template, converts via LibreOffice, stamps."""

import os, io, shutil, subprocess, tempfile
from datetime import datetime
import openpyxl

ISSUER = {
    "name": "Mr. Terry.Su", "phone": "008613609023860",
    "addr": "UNIT 1021, BEVERLEY COMMERCIAL CENTRE, 87-105 CHATHAN ROAD SOUTH, TSIM SHA TSUI, HK",
    "company": "WELLCOME (INTERNATIONAL) LIMITED",
}


def _find_soffice():
    for p in ["/opt/homebrew/bin/soffice", "soffice", "/usr/bin/soffice"]:
        if shutil.which(p) or os.path.exists(p):
            return p
    return "soffice"


def generate_receipt_pdf(client: dict, receipt_data: dict, output_path: str = None) -> str:
    """Generate stamped receipt PDF via LibreOffice xlsx→PDF conversion."""
    if output_path is None:
        output_path = tempfile.mktemp(suffix=".pdf")

    app_dir = os.path.dirname(os.path.dirname(__file__))
    tmpl = os.path.join(app_dir, "templates", "Cash-Receipt-Template.xlsx")
    if not os.path.exists(tmpl):
        tmpl = "/Users/vincy/Documents/Wellcome/项目/_模板/Cash-Receipt-Template.xlsx"

    # Fill template
    wb = openpyxl.load_workbook(tmpl)
    ws = wb.active
    c, rd = client, receipt_data
    cur = rd.get('currency', 'USD')
    amt = rd.get('payment_amount', rd.get('amount', 0))
    cl = "RMB" if cur == "RMB" else "USD"

    ws['C3'] = rd.get('project_name', '')
    ws['C4'] = rd.get('project_date', '')
    ws['C5'] = rd.get('venue', '')
    ws['C7'] = c.get('full_name', '')
    ws['C8'] = c.get('address', '')
    ws['C9'] = c.get('contact', '')
    ws['C10'] = c.get('phone') if c.get('phone') and c['phone'] != '（待补充）' else ''
    ws['C11'] = c.get('email') if c.get('email') and c['email'] != '（待补充）' else ''
    ws['E3'] = rd.get('issuer_name', ISSUER['name'])
    ws['E8'] = rd.get('project_code', '')
    ws['E9'] = _dt(rd.get('payment_date'))
    ws['E10'] = _dt(rd.get('gained_date'))
    ws['E11'] = rd.get('payment_method', 'BANK')
    ws['C13'] = (f"Received From  WELLCOME (INTERNATIONAL) LIMITED    "
                 f"The amount of  {cl}{amt:,.2f}\n"
                 f"For the {rd.get('project_name', '')}  Project")
    d = rd.get('gained_date', datetime.now())
    ds = d.strftime('%Y/%m/%d') if isinstance(d, datetime) else str(d)[:10]
    ws['D16'] = f"Name：\n\nDate：{ds}\n\nSignature：\n"

    # Insert stamp image directly into the xlsx
    stamp_file = None
    for p in [
        os.path.join(app_dir, "stamp", "stamp_final.png"),
        "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_final.png",
    ]:
        if os.path.exists(p):
            stamp_file = p
            break

    if stamp_file:
        stamp_img = openpyxl.drawing.image.Image(stamp_file)
        stamp_img.width = 180  # pixels in Excel
        stamp_img.height = stamp_img.width * 471 / 1172  # maintain aspect ratio
        # Place near rows 13-15, columns E-F (right side, above Name)
        stamp_img.anchor = 'E13'
        ws.add_image(stamp_img)

    # Save filled xlsx with stamp embedded
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        f.write(xlsx_buf.read())
        xlsx_path = f.name

    # Convert to PDF via LibreOffice (stamp rendered natively, perfect quality)
    try:
        outdir = tempfile.mkdtemp()
        subprocess.run([_find_soffice(), "--headless", "--convert-to", "pdf",
                       "--outdir", outdir, xlsx_path],
                      capture_output=True, text=True, timeout=60)
        base = os.path.splitext(os.path.basename(xlsx_path))[0]
        pdf_tmp = os.path.join(outdir, base + ".pdf")
        if os.path.exists(pdf_tmp):
            # Copy to output
            with open(pdf_tmp, 'rb') as src, open(output_path, 'wb') as dst:
                dst.write(src.read())
        else:
            raise RuntimeError("LibreOffice conversion failed")
    finally:
        try: os.unlink(xlsx_path)
        except: pass

    return output_path


def _dt(val):
    if val is None: return ''
    if isinstance(val, datetime): return val.strftime('%Y-%m-%d')
    return str(val)[:10]


