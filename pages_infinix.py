"""Infinix专用工具 — Swift Code签名 / Bank Details盖章 / PO盖章"""

import streamlit as st
import os, io, tempfile, base64, random
from PIL import Image as PILImage
import pypdf
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from datetime import datetime


def page_infinix():
    st.title("📱 Infinix 专用工具")
    tab1, tab2, tab3 = st.tabs(["📄 Bank Details 盖章", "📎 PO 盖章", "✍️ 签名"])

    with tab1:
        _tab_bank_details()

    with tab2:
        _tab_po_stamp()

    with tab3:
        st.info("Swift Code 签名功能：生成 Infinix 发票时自动添加 Swift Code 'XXX' 下划线 + 签名栏")


def _tab_bank_details():
    st.subheader("Bank Details 盖章")
    pdf_path = os.path.join(os.path.dirname(__file__), "infinix_bank_details_base.pdf")
    if not os.path.exists(pdf_path):
        st.error("Bank Details 文件未找到"); return

    if st.button("🔖 生成盖章 Bank Details", type="primary", use_container_width=True):
        with st.spinner("正在盖章..."):
            output = tempfile.mktemp(suffix='.pdf')
            _stamp_pdf(pdf_path, output, 'Terry.Su')
            with open(output, 'rb') as f:
                st.download_button("📥 下载盖章 Bank Details", f,
                                  file_name="INFINIX-Bank-Details-stamped.pdf",
                                  key="dl_bank3", use_container_width=True)
            st.success("✅ 已生成！")


def _tab_po_stamp():
    st.subheader("PO 盖章 + 签字")
    uploaded = st.file_uploader("上传客户 PO (PDF)", type=["pdf"], key="po_upload")
    sign_name = st.text_input("签字人", value="Terry.Su")
    if uploaded and st.button("🔖 生成盖章 PO", type="primary", use_container_width=True):
        with st.spinner("正在处理..."):
            # Save uploaded PO
            po_path = tempfile.mktemp(suffix=".pdf")
            with open(po_path, 'wb') as f:
                f.write(uploaded.read())
            output = tempfile.mktemp(suffix=".pdf")
            _stamp_pdf(po_path, output, sign_name)
            with open(output, 'rb') as f:
                st.download_button("📥 下载盖章 PO", f,
                                  file_name="PO-stamped.pdf",
                                  key="dl_po", use_container_width=True)
            st.success("✅ 已生成！")


def _stamp_pdf(input_path: str, output_path: str, sign_name: str = None):
    """Overlay stamp + signature on PDF using pypdf (no poppler needed)."""
    stamp_png = None
    for p in [
        os.path.join(os.path.dirname(__file__), "stamp", "stamp_hq.png"),
        os.path.join(os.path.dirname(__file__), "stamp", "stamp_final.png"),
    ]:
        if os.path.exists(p): stamp_png = p; break
    if not stamp_png: return

    sig_png = os.path.join(os.path.dirname(__file__), "signature.png") if sign_name else None

    stamp_img = PILImage.open(stamp_png).convert("RGBA")
    pw, ph = float(A4[0]), float(A4[1])
    stamp_w = pw * 0.36  # 2x bigger
    ratio = stamp_w / stamp_img.width
    stamp_h = stamp_img.height * ratio
    # From reference: stamp at ~60% from bottom, centered-right
    stamp_x = int(pw * 0.40)
    stamp_y = int(ph * 0.58)  # Reference position

    # Create stamp overlay PDF
    overlay_buf = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buf, pagesize=(pw, ph))
    c.drawImage(ImageReader(stamp_img), stamp_x, stamp_y, stamp_w, stamp_h, mask='auto')

    if sig_png and os.path.exists(sig_png):
        sig_img = PILImage.open(sig_png).convert("RGBA")
        sig_w = pw * 0.25  # Bigger
        sig_ratio = sig_w / sig_img.width
        sig_h = sig_img.height * sig_ratio
        sig_x = int(pw * 0.06)  # Left side
        sig_y2 = int(ph * 0.58)  # Same as stamp
        c.drawImage(ImageReader(sig_img), sig_x, sig_y2, sig_w, sig_h, mask='auto')

    c.save(); overlay_buf.seek(0)

    # Merge with original PDF
    reader = pypdf.PdfReader(input_path)
    writer = pypdf.PdfWriter()
    overlay_page = pypdf.PdfReader(overlay_buf).pages[0]
    for page in reader.pages:
        page.merge_page(overlay_page, over=True)
        writer.add_page(page)
    with open(output_path, 'wb') as f: writer.write(f)
