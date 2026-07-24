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


def generate_stamped_pdf(xlsx_path: str, output_path: str, stamp_path: str = None) -> str:
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
        img.anchor = 'D32'
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
        with open(pdf_tmp, 'rb') as src, open(output_path, 'wb') as dst:
            dst.write(src.read())
    finally:
        try: os.unlink(xlsx_stamped)
        except: pass

    return output_path
