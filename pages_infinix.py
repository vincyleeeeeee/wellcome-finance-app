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
    st.subheader("Bank Details PDF 盖章")
    pdf_path = os.path.join(os.path.dirname(__file__), "infinix_bank_details.pdf")
    if not os.path.exists(pdf_path):
        st.error("Bank Details 文件未找到")
        return

    if st.button("🔖 生成盖章版 Bank Details", type="primary", use_container_width=True):
        with st.spinner("正在盖章..."):
            output = tempfile.mktemp(suffix=".pdf")
            _stamp_pdf(pdf_path, output)
            with open(output, 'rb') as f:
                st.download_button("📥 下载盖章 Bank Details", f,
                                  file_name="INFINIX-Bank-Details-stamped.pdf",
                                  key="dl_bank", use_container_width=True)
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
    """Overlay company stamp + optional signature on every page of a PDF."""
    # Find stamp image
    stamp_file = None
    for p in [
        os.path.join(os.path.dirname(__file__), "stamp", "stamp_hq.png"),
        os.path.join(os.path.dirname(__file__), "stamp", "stamp_final.png"),
    ]:
        if os.path.exists(p):
            stamp_file = p
            break
    if not stamp_file:
        raise FileNotFoundError("印章文件未找到")

    # Render PDF pages to images
    from pdf2image import convert_from_path
    images = convert_from_path(input_path, dpi=200)

    stamp_img = PILImage.open(stamp_file).convert("RGBA")
    pw, ph = float(A4[0]), float(A4[1])

    stamped_images = []
    for page_img in images:
        pw_px, ph_px = page_img.size
        # Stamp: ~22% of page width, bottom-right
        stamp_w = int(pw_px * 0.22)
        ratio = stamp_w / stamp_img.width
        stamp_h = int(stamp_img.height * ratio)
        stamp_r = stamp_img.resize((stamp_w, stamp_h), PILImage.LANCZOS)

        mx = int(pw_px * 0.04) + random.randint(-15, 15)
        my = int(ph_px * 0.06) + random.randint(-10, 10)
        x = pw_px - stamp_w - mx
        y = ph_px - stamp_h - my

        page_rgba = page_img.convert("RGBA")
        page_rgba.paste(stamp_r, (x, y), stamp_r)

        # Add signature image if available
        sig_path = os.path.join(os.path.dirname(__file__), "signature.png")
        if os.path.exists(sig_path) and sign_name:
            sig_img = PILImage.open(sig_path).convert("RGBA")
            sig_w = int(pw_px * 0.10)
            sig_ratio = sig_w / sig_img.width
            sig_h = int(sig_img.height * sig_ratio)
            sig_r = sig_img.resize((sig_w, sig_h), PILImage.LANCZOS)
            sig_x = x
            sig_y = y - sig_h - 20
            page_rgba.paste(sig_r, (sig_x, sig_y), sig_r)

        stamped_images.append(page_rgba.convert("RGB"))

    stamped_images[0].save(output_path, "PDF", save_all=True, append_images=stamped_images[1:])
