"""PDF utilities — xlsx→PDF via LibreOffice."""

import os, shutil, subprocess, tempfile, random, io
from PIL import Image
import numpy as np
import openpyxl


def _find_soffice():
    for p in ["/opt/homebrew/bin/soffice", "soffice", "/usr/bin/soffice"]:
        if shutil.which(p) or os.path.exists(p):
            return p
    return "soffice"


def xlsx_to_pdf(xlsx_path: str, output_dir: str = None) -> str:
    """Convert xlsx to PDF using LibreOffice headless."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    cmd = [_find_soffice(), "--headless", "--convert-to", "pdf", "--outdir", output_dir, xlsx_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed: {result.stderr}")
    base = os.path.splitext(os.path.basename(xlsx_path))[0]
    pdf_path = os.path.join(output_dir, base + ".pdf")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not created: {pdf_path}")
    return pdf_path


def jittered_anchor(img, col: int, row: int, x_pct: float = 0.08, y_pct: float = 0.08):
    """在指定单元格锚点附近加随机偏移（默认 ±8%），让每张单据的盖章位置略有不同、更自然。
    col/row 为 0-based（A=0、第 1 行=0）。返回 openpyxl 的 OneCellAnchor。"""
    from openpyxl.drawing.spreadsheet_drawing import OneCellAnchor, AnchorMarker
    from openpyxl.drawing.xdr import XDRPositiveSize2D
    from openpyxl.utils.units import pixels_to_EMU
    w = pixels_to_EMU(img.width)
    h = pixels_to_EMU(img.height)
    return OneCellAnchor(
        _from=AnchorMarker(
            col=col, colOff=random.randint(-int(w * x_pct), int(w * x_pct)),
            row=row, rowOff=random.randint(-int(h * y_pct), int(h * y_pct)),
        ),
        ext=XDRPositiveSize2D(cx=w, cy=h),
    )


def generate_stamped_pdf(xlsx_path: str, output_path: str, stamp_path: str = None, add_signature: bool = False) -> str:
    """Embed stamp into xlsx, then convert to PDF via LibreOffice. Works on cloud."""
    # Find stamp
    if stamp_path is None:
        for p in [
            os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp", "stamp_final.png"),
            "/Users/vincy/Documents/Wellcome/invoice-app/stamp/stamp_final.png",
        ]:
            if os.path.exists(p):
                stamp_path = p
                break

    # Open xlsx and insert stamp
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    if stamp_path and os.path.exists(stamp_path):
        # Get stamp dimensions
        stamp_img = Image.open(stamp_path)
        sw, sh = stamp_img.size

        # Insert stamp image near bottom-right (row ~30, column E-F)
        img = openpyxl.drawing.image.Image(stamp_path)
        # Enlarged: target width ~350px for visibility
        img.width = 350
        img.height = int(350 * sh / sw)
        # Position OVER the Wellcome company name area (row 33)
        # 加随机偏移（±8%），避免每张发票盖章位置一模一样
        img.anchor = jittered_anchor(img, 3, 31)  # D32 = col 3, row 31
        ws.add_image(img)

    # Save modified xlsx
    xlsx_buf = io.BytesIO()
    wb.save(xlsx_buf)
    xlsx_buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        f.write(xlsx_buf.read())
        xlsx_stamped = f.name

    # Convert to PDF
    try:
        outdir = tempfile.mkdtemp()
        pdf_tmp = xlsx_to_pdf(xlsx_stamped, outdir)

        # Add signature for Infinix projects
        if add_signature:
            sig_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "signature.png")
            if os.path.exists(sig_path):
                _overlay_signature(pdf_tmp, output_path)
            else:
                with open(pdf_tmp, 'rb') as src, open(output_path, 'wb') as dst:
                    dst.write(src.read())
        else:
            with open(pdf_tmp, 'rb') as src, open(output_path, 'wb') as dst:
                dst.write(src.read())
    finally:
        try: os.unlink(xlsx_stamped)
        except: pass

    return output_path


def _overlay_signature(pdf_path: str, output_path: str):
    """Overlay signature image to the left of the stamp on the PDF."""
    sig_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "signature.png")
    if not os.path.exists(sig_path):
        with open(pdf_path, 'rb') as src, open(output_path, 'wb') as dst:
            dst.write(src.read())
        return

    from PIL import Image as PILImg
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.lib.utils import ImageReader
    sig_img = PILImg.open(sig_path).convert("RGBA")
    pw, ph = float(A4[0]), float(A4[1])

    # Same position as invoice stamp: bottom-right, sig left of stamp
    stamp_w = pw * 0.30
    stamp_x = pw - stamp_w - int(pw * 0.05)
    stamp_y = int(ph * 0.10)

    sig_w = pw * 0.20
    sig_h = sig_img.height * sig_w / sig_img.width
    sig_x = stamp_x - sig_w - 5
    sig_y = stamp_y

    # Random float ±10%
    import random
    stamp_x += random.randint(-int(stamp_w*0.1), int(stamp_w*0.1))
    stamp_y += random.randint(-int(stamp_h*0.1), int(stamp_h*0.1))
    sig_x += random.randint(-int(sig_w*0.1), int(sig_w*0.1))
    sig_y += random.randint(-int(sig_h*0.1), int(sig_h*0.1))

    buf = io.BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=(pw, ph))
    c.drawImage(ImageReader(sig_img), sig_x, sig_y, sig_w, sig_h, mask='auto')
    c.save(); buf.seek(0)

    reader = pypdf.PdfReader(pdf_path)
    writer = pypdf.PdfWriter()
    overlay = pypdf.PdfReader(buf).pages[0]
    for page in reader.pages:
        page.merge_page(overlay, over=True)
        writer.add_page(page)
    with open(output_path, 'wb') as f:
        writer.write(f)
