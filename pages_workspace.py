"""Project Workspace — unified project management page (merges workspace + history)."""

import streamlit as st
import os
from datetime import datetime
from utils.database import (get_projects, get_client_by_id, get_connection,
                            submit_for_approval)

STAGES = {
    'draft': '📝 信息已填', 'confirmation_sent': '📨 确认函已发',
    'stamped_uploaded': '📎 已上传盖章', 'pending': '⏳ 审核中',
    'approved': '✅ 已开发票', 'rejected': '❌ 已驳回',
}
CLOSURE_MAP = {'active': '🟢 进行中', 'pending_payment': '🟡 待付款', 'closed': '🔵 已结案'}


def page_workspace():
    st.title("📝 项目工作台")
    user = st.session_state.user

    projects = get_projects(limit=300)
    show_all = st.checkbox("显示所有项目", value=(user['role'] in ('admin','finance')))
    if not show_all:
        projects = [p for p in projects if p.get('created_by') == user['id']]

    if not projects:
        st.info("暂无项目。去「📄 生成文档」创建第一个！")
        return

    # === Rejected warnings ===
    rejected_mine = [p for p in projects if p.get('status') == 'rejected' and p.get('created_by') == user['id']]
    for rp in rejected_mine:
        st.warning(f"⚠️ {rp.get('brand_name','')} ({rp.get('project_code','')}) 已被驳回")
        if st.button("📤 修改重提", key=f"resub_{rp['id']}"):
            st.session_state['edit_project_id'] = rp['id']
            st.session_state.page = "generate"; st.rerun()

    # === Batch select ===
    if '_sel' not in st.session_state: st.session_state['_sel'] = set()
    sel = st.session_state['_sel']
    if sel:
        c1,c2,c3 = st.columns(3)
        with c1:
            if st.button(f"📤 批量提交({len(sel)})", use_container_width=True):
                for pid in list(sel):
                    submit_for_approval(pid)
                sel.clear(); st.success("已提交"); st.rerun()
        with c2:
            if st.button(f"🗑️ 批量删除({len(sel)})", use_container_width=True):
                for pid in list(sel):
                    get_connection().table("projects").delete().eq("id",pid).execute()
                sel.clear(); st.success("已删除"); st.rerun()
        with c3:
            if st.button("❌ 取消选择", use_container_width=True):
                sel.clear(); st.rerun()

    # === Project cards ===
    for p in projects:
        stage = STAGES.get(p.get('status','draft'), '❓')
        closure = CLOSURE_MAP.get(p.get('closure_status','active') or 'active', '')
        paid = ' 💰已到账' if p.get('payment_received') else ''

        with st.container(border=True):
            # Checkbox + basic info
            cc0, cc1, cc2 = st.columns([0.5, 3.5, 1.5])
            pid = p['id']
            with cc0:
                if st.checkbox("", key=f"ws_sel_{pid}", label_visibility="collapsed",
                               value=pid in sel):
                    sel.add(pid)
                else:
                    sel.discard(pid)
            with cc1:
                st.write(f"{stage}{paid} **{p.get('brand_name','')}** — {p.get('project_code','')}")
                st.caption(f"{p.get('currency','USD')} {p.get('amount',0):,.2f} | {p.get('client_short','')} | 👤 {p.get('owner_name','') or '未指定'} | {closure} | {(p.get('created_at','') or '')[:10]}")
            with cc2:
                # Action buttons
                if p.get('status') == 'approved' and p.get('stamped_pdf_path'):
                    stamped = p['stamped_pdf_path']
                    # Regenerate if path doesn't exist
                    if os.path.exists(stamped):
                        with open(stamped, 'rb') as f:
                            code_p = p.get('project_code','')
                            ms = code_p[6:8] if len(code_p)>=8 else ''
                            M = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                                 '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
                            fname = f"{p.get('brand_name','')}-{M.get(ms,'')}-invoice.pdf"
                            st.download_button("📥 盖章PDF", f, file_name=fname,
                                             key=f"ws_stamp_{pid}", use_container_width=True)
                elif p.get('status') in ('draft','rejected') and user['id'] == p.get('created_by'):
                    if st.button("📤 提交审核", key=f"ws_sub_{pid}", use_container_width=True):
                        submit_for_approval(pid); st.success("已提交"); st.rerun()

                # Operations button
                if st.button("📄 操作", key=f"ws_op_{pid}", use_container_width=True):
                    st.session_state['edit_project_id'] = pid
                    st.session_state.page = "generate"; st.rerun()

            # Editable status (owner or finance/admin)
            if user['id'] == p.get('created_by') or user['role'] in ('finance','admin'):
                with st.expander("✏️ 编辑状态", expanded=False):
                    ce1,ce2,ce3 = st.columns(3)
                    cur_closure = p.get('closure_status','active') or 'active'
                    with ce1:
                        nc = st.selectbox("结案", ['active','pending_payment','closed'],
                                         index=['active','pending_payment','closed'].index(cur_closure),
                                         format_func=lambda x: CLOSURE_MAP.get(x,x),
                                         key=f"wsc_{pid}")
                    with ce2:
                        epd = p.get('expected_payment_date','')
                        if epd and 'T' in str(epd): epd = str(epd)[:10]
                        ne = st.text_input("预计付款", value=str(epd) if epd else '', key=f"wse_{pid}")
                    with ce3:
                        if st.button("💾 保存", key=f"wss_{pid}", use_container_width=True):
                            get_connection().table("projects").update({
                                "closure_status": nc,
                                "expected_payment_date": ne if ne else None,
                            }).eq("id", pid).execute()
                            st.success("已保存"); st.rerun()
                    # Mark paid
                    if p.get('status') == 'approved' and not p.get('payment_received') and user['role'] in ('finance','admin'):
                        if st.button("💰 标记到账", key=f"wsp_{pid}", use_container_width=True):
                            get_connection().table("projects").update({
                                "payment_received": True,
                                "received_date": datetime.now().strftime('%Y-%m-%d'),
                            }).eq("id", pid).execute()
                            st.rerun()
