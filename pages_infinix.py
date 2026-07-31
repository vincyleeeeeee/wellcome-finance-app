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
    from docx import Document as DocxDoc

    if st.button("🔖 生成 Bank Details（填日期+盖章+签名）", type="primary", use_container_width=True):
        with st.spinner("正在处理..."):
            from datetime import datetime
            today = datetime.now().strftime('%Y/%m/%d')

            # Fill template
            template_path = os.path.join(os.path.dirname(__file__), "infinix_bank_details.docx")
            if not os.path.exists(template_path):
                st.error("模板文件未找到，请联系管理员")
                return

            doc = DocxDoc(template_path)
            highlight_count = 0
            for p in doc.paragraphs:
                for run in p.runs:
                    if run.font.highlight_color is not None:
                        highlight_count += 1
                        run.font.highlight_color = None  # Remove yellow
                        if highlight_count == 1:  # First: DATE
                            run.text = today
                        # Second highlight (P19): stamp area, keep empty
            st.info(f"已处理 {highlight_count} 处标记：日期已填 {today}，盖章区域留空待PDF叠加")

            # Save docx
            docx_tmp = tempfile.mktemp(suffix='.docx')
            doc.save(docx_tmp)

            # Convert to PDF (LibreOffice)
            import subprocess
            pdf_dir = tempfile.mkdtemp()
            subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', pdf_dir, docx_tmp],
                          capture_output=True, timeout=60)
            base = os.path.splitext(os.path.basename(docx_tmp))[0]
            pdf_tmp = os.path.join(pdf_dir, base + '.pdf')

            if not os.path.exists(pdf_tmp):
                st.error("PDF 转换失败")
                return

            # Overlay stamp + signature
            output = tempfile.mktemp(suffix='.pdf')
            _stamp_pdf(pdf_tmp, output, 'Terry.Su')
            with open(output, 'rb') as f:
                st.download_button("📥 下载盖章 Bank Details", f,
                                  file_name="INFINIX-Bank-Details-stamped.pdf",
                                  key="dl_bank2", use_container_width=True)
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
    stamp_w = pw * 0.18
    ratio = stamp_w / stamp_img.width
    stamp_h = stamp_img.height * ratio
    # Dashed line at y=250 from TOP = ph-250 from BOTTOM ≈ ph*0.70
    stamp_x = pw - stamp_w - int(pw * 0.06)
    stamp_y = int(ph * 0.70)  # On the dashed signature line

    # Create stamp overlay PDF
    overlay_buf = io.BytesIO()
    c = rl_canvas.Canvas(overlay_buf, pagesize=(pw, ph))
    c.drawImage(ImageReader(stamp_img), stamp_x, stamp_y, stamp_w, stamp_h, mask='auto')

    if sig_png and os.path.exists(sig_png):
        sig_img = PILImage.open(sig_png).convert("RGBA")
        sig_w = pw * 0.25  # 2.5x bigger
        sig_ratio = sig_w / sig_img.width
        sig_h = sig_img.height * sig_ratio
        sig_x = int(pw * 0.06)  # Left side of dashed line
        sig_y2 = int(ph * 0.70)  # On the dashed line
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
