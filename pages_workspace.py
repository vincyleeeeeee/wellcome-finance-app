"""Project Workspace — simple card list showing progress."""

import streamlit as st
from datetime import datetime
from utils.database import get_projects, get_client_by_id, get_connection

STAGES = {
    'draft': '📝 信息已填',
    'confirmation_sent': '📨 确认函已发',
    'stamped_uploaded': '📎 已上传盖章',
    'pending': '⏳ 审核中',
    'approved': '✅ 已开发票',
}


def page_workspace():
    st.title("📝 项目工作台")
    user = st.session_state.user

    projects = get_projects(limit=200)
    show_all = st.checkbox("显示所有项目", value=(user['role'] in ('admin','finance')))
    if not show_all:
        projects = [p for p in projects if p.get('created_by') == user['id']]

    if not projects:
        st.info("暂无项目。去「📄 生成文档」创建第一个项目吧！")
        return

    for p in projects:
        stage = STAGES.get(p.get('status','draft'), '❓')
        paid = ' 💰已到账' if p.get('payment_received') else ''

        with st.container(border=True):
            c1,c2 = st.columns([4,1])
            with c1:
                st.markdown(f"**{stage}**{paid} — **{p.get('brand_name','')}** | {p.get('project_code','')}")
                owner = p.get('owner_name','') or '未指定'
                st.caption(f"{p.get('currency','USD')} {p.get('amount',0):,.2f} | {p.get('client_short','')} | 👤 {owner} | {(p.get('created_at','') or '')[:10]}")
            with c2:
                if st.button("📄 操作", key=f"go_{p['id']}", use_container_width=True):
                    st.session_state['edit_project_id'] = p['id']
                    st.session_state.page = "generate"
                    st.rerun()
