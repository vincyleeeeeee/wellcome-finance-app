"""Finance pages — simplified for older colleagues."""

import streamlit as st
import pandas as pd
from datetime import datetime
import os

from utils.database import (
    get_projects, get_clients, get_client_by_id, get_pending_approvals,
    approve_project, reject_project, set_user_role
)
from utils.receipt_pdf import generate_receipt_pdf
from utils.generate import generate_cash_receipt


def _fmt_cost_line(cost_json: str) -> str:
    """Format cost breakdown as a single sentence."""
    if not cost_json:
        return ""
    try:
        import json
        items = json.loads(cost_json)
        return "、".join(f"{i['name']}({i.get('currency','RMB')}{i.get('amount',0):,.0f})" for i in items)
    except Exception:
        return cost_json

# Status mapping with clear labels
STAGE_MAP = {
    'draft': '📝 草稿',
    'pending': '⏳ 待财务审核',
    'approved': '✅ 已开发票',
    'rejected': '❌ 已驳回',
}

CLOSURE_MAP = {
    'active': '进行中',
    'pending_payment': '待收款',
    'closed': '🔒 已结案',
}


def page_overview():
    """Big project overview — everything finance needs in one page."""
    st.title("📊 项目总览")

    projects = get_projects(limit=500)
    if not projects:
        st.info("暂无项目")
        return

    # === Summary cards at top ===
    pending_count = sum(1 for p in projects if p.get('status') == 'pending')
    approved_count = sum(1 for p in projects if p.get('status') == 'approved')
    received_count = sum(1 for p in projects if p.get('payment_received'))
    closed_count = sum(1 for p in projects if p.get('closure_status') == 'closed')

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⏳ 待审核", pending_count)
    c2.metric("✅ 已开发票", approved_count)
    c3.metric("💰 已到账", received_count)
    c4.metric("🔒 已结案", closed_count)

    st.divider()

    # === Project list as expandable cards ===
    st.subheader("项目明细")
    for p in projects:
        stage = STAGE_MAP.get(p.get('status', ''), p.get('status', '?'))
        closure = CLOSURE_MAP.get(p.get('closure_status', 'active'), '')
        paid = '💰已到账 ' if p.get('payment_received') else ''
        feishu = ' 📋飞书' if p.get('feishu_approved') else ''

        # Parse cost breakdown
        try:
            import json
            cost_items = json.loads(p.get('cost_breakdown', '') or '[]')
        except Exception:
            cost_items = []

        cost_summary = f" | 成本{len(cost_items)}项: RMB {p.get('estimated_cost',0):,.0f}" if p.get('estimated_cost') else ""

        label = f"{stage} {paid}**{p.get('brand_name','')}** — {p.get('project_code','')} | {p.get('currency','USD')} {p.get('amount',0):,.0f}{cost_summary} {feishu} {closure}"

        with st.expander(label, expanded=False):
            c1, c2 = st.columns([3, 1])
            with c1:
                st.caption(f"客户: {p.get('client_short','')} | 提交: {(p.get('created_at','') or '')[:10]}")
                if cost_items:
                    st.caption("**成本明细：**")
                    for item in cost_items:
                        st.write(f"• {item.get('name','')} — {item.get('currency','RMB')} {item.get('amount',0):,.0f}")
                elif p.get('estimated_cost'):
                    st.caption(f"成本: RMB {p.get('estimated_cost',0):,.0f}")

            with c2:
                if p.get('status') == 'approved' and p.get('stamped_pdf_path'):
                    # Download button will be added later
                    pass
                if p.get('status') == 'approved' and not p.get('payment_received'):
                    if st.button("💰 标记到账", key=f"paid_{p['id']}", use_container_width=True):
                        from utils.database import get_connection
                        sb = get_connection()
                        sb.table("projects").update({
                            "payment_received": True,
                            "received_date": datetime.now().strftime('%Y-%m-%d'),
                        }).eq("id", p['id']).execute()
                        st.rerun()



def page_approval():
    """Simple approval page — big buttons for finance."""
    st.title("💰 待审核")
    pending = get_pending_approvals()

    if not pending:
        st.success("✅ 没有需要审核的项目，太好了！")
        return

    st.subheader(f"共 {len(pending)} 个项目等你审核")
    user = st.session_state.user

    for p in pending:
        with st.container(border=True):
            # Big clear display
            st.markdown(f"### {p.get('brand_name','')} — {p.get('project_name','')}")

            feishu_ok = p.get('feishu_approved')
            feishu_badge = "✅ 飞书已立项" if feishu_ok else "⚠️ 未确认飞书立项"

            col_info, col_btn = st.columns([3, 2])
            with col_info:
                st.write(f"**{p.get('client_short','')}** | "
                         f"{p.get('currency','USD')} **{p.get('amount',0):,.2f}** | "
                         f"提交人: {p.get('created_by_name','?')} | "
                         f"{feishu_badge}")
                if p.get('estimated_cost'):
                    cost_detail = _fmt_cost_line(p.get('cost_breakdown', '') or '')
                    st.caption(f"预估成本: RMB {p.get('estimated_cost',0):,.0f}" + (f"（{cost_detail}）" if cost_detail else ""))
                st.caption(f"提交时间: {p.get('created_at','')[:10]} | 预计到账: {str(p.get('expected_payment_date',''))[:10] if p.get('expected_payment_date') else '未填写'}")

            with col_btn:
                # Regenerate invoice for download
                try:
                    from utils.generate import TEMPLATE_DIR as _TD
                    import openpyxl, io
                    client = get_client_by_id(p.get('client_id')) or {}
                    if client:
                        wb = openpyxl.load_workbook(os.path.join(_TD, "Invoice-Template.xlsx"))
                        ws = wb.active
                        ws['C3'] = f"{p.get('brand_name','')} – {p.get('total_posts','')} CONTENT PACKAGE"
                        ws['C7'] = client.get('full_name','')
                        ws['C9'] = client.get('contact','')
                        ws['E8'] = p.get('project_code','')
                        ws['D15'] = p.get('amount',0); ws['E15'] = 1; ws['G15'] = p.get('amount',0)
                        ws['E11'] = p.get('project_code','')
                        ws['E10'] = str(p.get('due_date',''))[:10]
                        buf = io.BytesIO(); wb.save(buf); buf.seek(0)
                        st.download_button("📥 下载Invoice核对", buf, file_name=f"{p.get('project_code','')}.xlsx",
                                          key=f"invdl_{p['id']}", use_container_width=True,
                                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                except: pass

                st.write("")  # spacer
                if st.button("✅ 通过", key=f"ok_{p['id']}", use_container_width=True, type="primary"):
                    with st.spinner("生成盖章PDF..."):
                        try:
                            regen_invoice_and_stamp(p, user['id'])
                            st.success("已通过！")
                            st.rerun()
                        except Exception as e:
                            st.error(f"失败: {e}")

                if st.button("❌ 驳回", key=f"no_{p['id']}", use_container_width=True):
                    reject_project(p['id'], user['id'])
                    st.warning("已驳回")
                    st.rerun()


def regen_invoice_and_stamp(p, user_id):
    """Regenerate invoice + stamped PDF, approve project."""
    import io, tempfile, openpyxl, os as _os
    from utils.pdf_utils import generate_stamped_pdf
    from utils.generate import TEMPLATE_DIR as _TD

    client = get_client_by_id(p.get('client_id')) or {}
    # Build xlsx
    wb = openpyxl.load_workbook(_os.path.join(_TD, "Invoice-Template.xlsx"))
    ws = wb.active
    ws['C3'] = f"{p.get('brand_name','')} – {p.get('total_posts','')} CONTENT PACKAGE"
    ws['C7'] = client.get('full_name','')
    ws['C8'] = client.get('address','')
    ws['C9'] = client.get('contact','')
    ws['C10'] = client.get('phone') if client.get('phone') and client['phone'] != '（待补充）' else None
    ws['C11'] = client.get('email') if client.get('email') and client['email'] != '（待补充）' else None
    ws['E8'] = p.get('project_code','')
    ws['E10'] = str(p.get('due_date',''))[:10]
    ws['E11'] = p.get('project_code','')
    ws['D15'] = p.get('amount',0); ws['E15'] = 1; ws['G15'] = p.get('amount',0)
    from utils.generate import _amount_chinese
    cn_amt = _amount_chinese(p.get('amount',0), p.get('currency','USD'))
    ws['C18'] = f"總付款金額為{cn_amt}\nFull payment of {p.get('currency','USD')} {p.get('amount',0):,.2f}"

    buf = io.BytesIO(); wb.save(buf); buf.seek(0)

    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f:
        f.write(buf.read()); xlsx_path = f.name

    stamped_path = tempfile.mktemp(suffix='.pdf')
    generate_stamped_pdf(xlsx_path, stamped_path)
    approve_project(p['id'], user_id, stamped_path)
    _os.unlink(xlsx_path)
