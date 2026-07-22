"""PDF generation: convert xlsx to PDF and overlay electronic stamp."""

import os
import subprocess
import tempfile
import random
from PIL import Image
import numpy as np

STAMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stamp")
STAMP_PATH = os.path.join(STAMP_DIR, "stamp_final.png")


def xlsx_to_pdf(xlsx_path: str, output_dir: str = None) -> str:
    """Convert xlsx to PDF using LibreOffice headless. Returns PDF path."""
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    cmd = [
        "/opt/homebrew/bin/soffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", output_dir,
        xlsx_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed: {result.stderr}")

    base = os.path.splitext(os.path.basename(xlsx_path))[0]
    pdf_path = os.path.join(output_dir, base + ".pdf")
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF not created: {pdf_path}")
    return pdf_path


def overlay_stamp_on_pdf(pdf_path: str, output_path: str, stamp_path: str = None) -> str:
    """
    Overlay electronic stamp onto PDF pages at bottom-right.
    Renders PDF to image, overlays stamp, saves back to PDF.
    """
    if stamp_path is None:
        stamp_path = STAMP_PATH

    if not os.path.exists(stamp_path):
        raise FileNotFoundError(f"印章文件不存在: {stamp_path}")

    from pdf2image import convert_from_path

    stamp_img = Image.open(stamp_path).convert("RGBA")

    # Render PDF pages at high DPI
    images = convert_from_path(pdf_path, dpi=200)

    stamped_images = []
    for page_img in images:
        pw, ph = page_img.size

        # Stamp size: ~19% of page width, keep aspect ratio
        stamp_w = int(pw * 0.19)
        ratio = stamp_w / stamp_img.width
        stamp_h = int(stamp_img.height * ratio)
        stamp_resized = stamp_img.resize((stamp_w, stamp_h), Image.LANCZOS)

        # Position: bottom-right corner, above the company name
        margin_x = int(pw * 0.04) + random.randint(-15, 15)
        margin_y = int(ph * 0.06) + random.randint(-10, 10)
        x = pw - stamp_w - margin_x
        y = ph - stamp_h - margin_y

        # Paste stamp at calculated position
        page_rgba = page_img.convert("RGBA")
        page_rgba.paste(stamp_resized, (x, y), stamp_resized)
        stamped_images.append(page_rgba)

    # Save as PDF (multi-page if needed)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    first = stamped_images[0].convert("RGB")
    rest = [img.convert("RGB") for img in stamped_images[1:]]
    first.save(output_path, "PDF", save_all=True, append_images=rest)

    return output_path


def generate_stamped_pdf(xlsx_path: str, output_path: str, stamp_path: str = None) -> str:
    """Full pipeline: xlsx → PDF → stamp → stamped PDF."""
    pdf_dir = tempfile.mkdtemp()
    try:
        pdf_path = xlsx_to_pdf(xlsx_path, pdf_dir)
        result = overlay_stamp_on_pdf(pdf_path, output_path, stamp_path)
        return result
    finally:
        import shutil
        shutil.rmtree(pdf_dir, ignore_errors=True)
