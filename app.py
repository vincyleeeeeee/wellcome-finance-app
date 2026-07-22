"""Wellcome Invoice & Confirmation Letter Generator — Streamlit App."""

import streamlit as st
import os
import sys
from datetime import datetime

# Ensure utils is importable
sys.path.insert(0, os.path.dirname(__file__))
from utils.database import (
    init_db, authenticate, create_user, is_approved, get_connection,
    get_pending_users, approve_user, reject_user, get_all_users,
    get_clients, get_client_by_short_name, get_client_by_id,
    upsert_client, delete_client,
    save_project, get_projects, get_project_by_id,
    submit_for_approval, approve_project, reject_project, get_pending_approvals,
    set_user_role
)
from utils.generate import (
    generate_confirmation_letter, generate_invoice,
    generate_email_confirmation, generate_email_invoice,
    generate_cash_receipt
)
from utils.pdf_utils import generate_stamped_pdf

# ============================================================
# Page config
# ============================================================
st.set_page_config(
    page_title="Wellcome财务自动化平台",
    page_icon="💰",
    layout="wide"
)

# ============================================================
# Init DB
# ============================================================
init_db()

# ============================================================
# Session state
# ============================================================
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "login"

# Auto-restore session using st.session_state (survives reruns)
# For full page refresh, use Streamlit's cookie via extra_streamlit_components
# Simplified: store user_id in session_state, which persists within a browser session

def _save_session(user_id):
    """Store login in session state (works within one browser session)."""
    st.session_state['_logged_in_user_id'] = user_id

def _restore_session():
    """Try to restore user from session state."""
    uid = st.session_state.get('_logged_in_user_id')
    if uid:
        try:
            result = get_connection().table("users").select("*").eq("id", uid).execute()
            if result.data:
                return result.data[0]
        except:
            pass
    return None

def _clear_session():
    if '_logged_in_user_id' in st.session_state:
        del st.session_state['_logged_in_user_id']


def logout():
    _clear_session()
    st.session_state.user = None
    st.session_state.page = "login"


# ============================================================
# Sidebar navigation (when logged in)
# ============================================================
def render_sidebar():
    user = st.session_state.user
    role_labels = {'admin': '🔑 管理员', 'finance': '💰 财务', 'user': '👤 用户'}
    with st.sidebar:
        st.markdown(f"### 👤 {user['username']}")
        st.caption(f"{user['email']}  |  {role_labels.get(user['role'], user['role'])}")

        st.divider()

        if st.button("📄 生成文档", use_container_width=True,
                     type="primary" if st.session_state.page == "generate" else "secondary"):
            st.session_state.page = "generate"

        if st.button("👥 客户管理", use_container_width=True,
                     type="primary" if st.session_state.page == "clients" else "secondary"):
            st.session_state.page = "clients"

        if st.button("📋 项目历史", use_container_width=True,
                     type="primary" if st.session_state.page == "history" else "secondary"):
            st.session_state.page = "history"

        # Finance users see approval + receipt pages
        if user['role'] in ('finance', 'admin'):
            st.divider()
            p = len(get_pending_approvals())
            label = f"💰 财务审核" + (f" ({p})" if p else "")
            if st.button(label, use_container_width=True,
                         type="primary" if st.session_state.page == "finance" else "secondary"):
                st.session_state.page = "finance"
            if st.button("🧾 开具收据", use_container_width=True,
                         type="primary" if st.session_state.page == "receipt" else "secondary"):
                st.session_state.page = "receipt"

        if user['role'] == 'admin':
            pending = len(get_pending_users())
            admin_label = f"🔒 用户审核" + (f" ({pending})" if pending else "")
            if st.button(admin_label, use_container_width=True,
                         type="primary" if st.session_state.page == "admin" else "secondary"):
                st.session_state.page = "admin"

        st.divider()
        st.button("🚪 退出登录", on_click=logout, use_container_width=True)


# ============================================================
# Login / Register page
# ============================================================
def page_login():
    st.title("💰 Wellcome财务自动化平台")
    st.caption("确认函 · Invoice · 收据 — 一键生成")

    tab_login, tab_register = st.tabs(["登录", "注册"])

    with tab_login:
        st.subheader("登录")
        email = st.text_input("邮箱", key="login_email", placeholder="your@email.com")
        password = st.text_input("密码", type="password", key="login_password")
        if st.button("登录", type="primary", use_container_width=True):
            user = authenticate(email, password)
            if user is None:
                st.error("邮箱或密码错误")
            elif user['approved'] == 0:
                st.warning("你的账号尚未通过审核，请等待管理员审批")
            else:
                _save_session(user['id'])
                st.session_state.user = user
                st.session_state.page = "generate"
                st.rerun()

    with tab_register:
        st.subheader("注册")
        st.info("注册后需等待管理员审核通过才能使用")
        new_email = st.text_input("邮箱", key="reg_email", placeholder="your@email.com")
        new_username = st.text_input("用户名", key="reg_username", placeholder="你的名字")
        new_password = st.text_input("密码", type="password", key="reg_password", placeholder="至少6位")
        new_password2 = st.text_input("确认密码", type="password", key="reg_password2", placeholder="再次输入密码")

        if st.button("提交注册", use_container_width=True):
            if not new_email or not new_username or not new_password:
                st.error("请填写所有字段")
            elif new_password != new_password2:
                st.error("两次密码不一致")
            elif len(new_password) < 6:
                st.error("密码至少6位")
            else:
                success, msg = create_user(new_email, new_username, new_password)
                if success:
                    st.success(msg)
                else:
                    st.error(msg)


# ============================================================
# Admin: User Approval
# ============================================================
def page_admin():
    st.title("🔒 用户审核")
    user = st.session_state.user
    if user['role'] != 'admin':
        st.error("无权访问")
        return

    st.subheader("待审核用户")
    pending = get_pending_users()
    if not pending:
        st.success("暂无待审核用户 ✅")
    else:
        for u in pending:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.write(f"**{u['username']}**")
                st.caption(f"{u['email']}  |  注册于 {u['created_at']}")
            with col2:
                if st.button("✅ 通过", key=f"approve_{u['id']}"):
                    approve_user(u['id'])
                    st.rerun()
            with col3:
                if st.button("❌ 拒绝", key=f"reject_{u['id']}"):
                    reject_user(u['id'])
                    st.rerun()
            st.divider()

    st.subheader("所有用户")
    users = get_all_users()
    role_map = {'admin': '🔑 管理员', 'finance': '💰 财务', 'user': '👤 用户'}
    for u in users:
        status = "✅" if u['approved'] else "⏳"
        role = role_map.get(u['role'], u['role'])
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            st.write(f"{status} {u['username']} — {u['email']} — {role} — {u['created_at'][:10]}")
        with col2:
            new_role = st.selectbox(
                "角色", ['user', 'finance', 'admin'],
                index=['user', 'finance', 'admin'].index(u['role']) if u['role'] in ['user', 'finance', 'admin'] else 0,
                key=f"role_{u['id']}",
                label_visibility="collapsed"
            )
        with col3:
            if new_role != u['role']:
                if st.button("💾 保存", key=f"save_role_{u['id']}"):
                    set_user_role(u['id'], new_role)
                    st.rerun()


# ============================================================
# Client Management
# ============================================================
def page_clients():
    st.title("👥 客户管理")

    clients = get_clients()
    client_names = [c['short_name'] for c in clients]
    client_map = {c['short_name']: c for c in clients}

    mode = st.radio("操作", ["查看 / 编辑", "新增客户", "删除客户"], horizontal=True)

    if mode == "新增客户":
        _client_form(None)
    elif mode == "删除客户":
        if not client_names:
            st.info("暂无客户")
        else:
            target = st.selectbox("选择要删除的客户", client_names)
            if st.button("🗑️ 确认删除", type="primary"):
                c = client_map[target]
                st.warning(f"确认删除客户「{target}」({c['full_name']})？")
                if st.button("⚠️ 再次确认删除", type="primary"):
                    success, msg = delete_client(target)
                    if success:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)
    else:  # 查看/编辑
        if not client_names:
            st.info("暂无客户，请先新增")
        else:
            selected = st.selectbox("选择客户", client_names)
            if selected:
                _client_form(client_map[selected])


def _client_form(client: "dict | None"):
    """Render client add/edit form."""
    is_edit = client is not None
    st.subheader("编辑客户" if is_edit else "新增客户")

    short_name = st.text_input("简称 *", value=client['short_name'] if is_edit else "",
                               disabled=is_edit, placeholder="如 AKRA, POP")
    full_name = st.text_input("公司全称 *", value=client['full_name'] if is_edit else "",
                              placeholder="公司完整名称")
    address = st.text_area("公司地址", value=client['address'] if is_edit else "",
                           placeholder="详细地址")
    contact = st.text_input("联系人", value=client['contact'] if is_edit else "",
                            placeholder="联系人姓名")
    phone = st.text_input("电话", value=client['phone'] if is_edit else "",
                          placeholder="(+66) ...")
    email = st.text_input("邮箱", value=client['email'] if is_edit else "",
                          placeholder="contact@company.com")

    btn_label = "💾 保存修改" if is_edit else "➕ 创建客户"
    if st.button(btn_label, type="primary", use_container_width=True):
        if not short_name or not full_name:
            st.error("简称和公司全称为必填项")
        else:
            success, msg = upsert_client(
                short_name, full_name, address, contact, phone, email,
                st.session_state.user['id']
            )
            if success:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)


# ============================================================
# Document Generation
# ============================================================
def page_generate():
    st.title("📄 生成确认函 & Invoice")

    clients = get_clients()
    if not clients:
        st.warning("暂无客户，请先在「客户管理」中添加")
        return

    client_names = [c['short_name'] for c in clients]
    client_map = {c['short_name']: c for c in clients}

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("项目信息")
        selected_client = st.selectbox("客户简称 *", client_names)
        client_info = client_map[selected_client]

        # Show client preview
        phone_email = client_info['phone'] or client_info['email'] or '—'
        st.caption(f"📋 {client_info['full_name']}  |  联系人: {client_info['contact']}  |  {phone_email}")

        application_date = st.date_input("申请日期 *", value=datetime.now())
        project_code = st.text_input("项目编号 *", placeholder="WELL20260701001")
        project_name = st.text_input("项目名称 *", placeholder="品牌名 – 月份UGC 篇数")
        brand_name = st.text_input("客户品牌名 *", placeholder="品牌的社交媒体名")
        currency = st.selectbox("币种", ["USD", "RMB"], index=0)
        amount = st.number_input("项目金额 *", min_value=0.0, step=100.0, value=4400.0)

        venue = st.text_input("执行地点", value="Bangkok", placeholder="城市")
        execution_period = st.text_input("执行周期", placeholder="如 July – September 2026")
        shooting_date = st.text_input("预计拍摄时间", placeholder="如 July 2026")
        total_posts = st.text_input("总发布篇数", placeholder="如 150 PHOTO POSTS")
        due_date = st.date_input("到期日 *", value=datetime.now())

    with col_right:
        st.subheader("额外信息")
        content_type = st.text_input("合作内容", value="UGC铺量",
                                     help="邮件中使用，默认 UGC铺量")
        platform = st.text_input("发布平台", value="小红书",
                                 help="邮件中使用，默认小红书")
        only_invoice = st.checkbox("只要 Invoice（不生成确认函）", value=False)
        submit_approval = st.checkbox("生成后提交财务审核", value=True)
        estimated_cost = st.number_input("预估成本金额", min_value=0.0, step=100.0, value=0.0)
        cost_currency = st.selectbox("成本币种", ["USD", "RMB"], key="cost_currency")
        cost_breakdown = st.text_area("成本构成", placeholder="如：KOL费用 2000, 拍摄 500, 剪辑 300...")

        st.divider()

        if st.button("🚀 生成文档", type="primary", use_container_width=True):
            if not all([project_code, project_name, brand_name, amount > 0]):
                st.error("请填写所有带 * 的必填项")
            else:
                # Build project dict for generation
                proj = {
                    'client_short': selected_client,
                    'project_code': project_code,
                    'project_name': project_name,
                    'brand_name': brand_name,
                    'amount': amount,
                    'currency': currency,
                    'application_date': application_date.strftime("%b %dth, %Y") if application_date else "",
                    'venue': venue,
                    'execution_period': execution_period,
                    'shooting_date': shooting_date,
                    'total_posts': total_posts,
                    'invoice_date': application_date if application_date else datetime.now(),
                    'due_date': due_date if due_date else datetime.now(),
                    'content_type': content_type,
                    'platform': platform,
                    'status': 'pending' if submit_approval else 'draft',
                    'estimated_cost': estimated_cost,
                    'cost_currency': cost_currency,
                    'cost_breakdown': cost_breakdown,
                    'created_by': st.session_state.user['id'],
                    'client_id': client_info['id'],
                }
                proj['invoice_project_name'] = f"{brand_name} – {total_posts} CONTENT PACKAGE"

                with st.spinner("正在生成文档..."):
                    files = {}
                    if not only_invoice:
                        conf_path = generate_confirmation_letter(
                            {k: client_info[k] for k in ['full_name', 'contact']},
                            proj
                        )
                        files['确认函'] = conf_path

                    inv_path = generate_invoice(client_info, proj)
                    files['Invoice'] = inv_path

                    # Save project record
                    project_id = save_project(proj)

                    # Generate emails
                    subj_conf, body_conf = ("", "")
                    if not only_invoice:
                        subj_conf, body_conf = generate_email_confirmation(proj)
                    subj_inv, body_inv = generate_email_invoice(proj)

                st.success("✅ 文档生成完毕！" + (" 已提交财务审核" if submit_approval else ""))
                st.balloons()

                # Store project id for possible later approval
                st.session_state['last_project_id'] = project_id
                st.session_state['last_inv_path'] = inv_path

                # Show downloaded files
                for name, path in files.items():
                    with open(path, "rb") as f:
                        st.download_button(
                            label=f"📥 下载 {name}",
                            data=f,
                            file_name=os.path.basename(path),
                            mime="application/octet-stream",
                            use_container_width=True
                        )

                # Show email copy
                if not only_invoice:
                    with st.expander("📧 邮件一：确认函（发客户确认）", expanded=True):
                        st.text_input("主题", value=subj_conf, key="email_subj_conf")
                        st.text_area("正文", value=body_conf, height=250, key="email_body_conf")

                with st.expander("📧 邮件二：Invoice（发客户查收）", expanded=not only_invoice):
                    st.text_input("主题", value=subj_inv, key="email_subj_inv")
                    st.text_area("正文", value=body_inv, height=200, key="email_body_inv")

                # Allow late submission if not submitted initially
                if not submit_approval:
                    if st.button("📤 补交财务审核", use_container_width=True):
                        submit_for_approval(project_id)
                        st.success("已提交财务审核")
                        st.rerun()


# ============================================================
# Project History
# ============================================================
def page_history():
    st.title("📋 项目历史")
    projects = get_projects(limit=100)

    if not projects:
        st.info("暂无项目记录")
        return

    import pandas as pd
    status_map = {'draft': '草稿', 'pending': '待审核', 'approved': '✅ 已通过', 'rejected': '❌ 已驳回'}
    for p in projects:
        status_label = status_map.get(p.get('status'), p.get('status', '?'))
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.write(f"{status_label} **{p.get('brand_name','?')}** — {p.get('project_code','?')}")
                st.caption(f"客户: {p.get('client_short','?')} | "
                          f"金额: {p.get('currency','USD')} {p.get('amount',0):,.2f} | "
                          f"日期: {p.get('created_at','')[:10]}")
            with col2:
                # Download buttons for approved projects
                if p.get('status') == 'approved' and p.get('stamped_pdf_path'):
                    stamped = p['stamped_pdf_path']
                    if os.path.exists(stamped):
                        with open(stamped, "rb") as f:
                            st.download_button(
                                "📥 盖章PDF", f, file_name=os.path.basename(stamped),
                                key=f"hist_stamped_{p['id']}", use_container_width=True
                            )
                elif p.get('status') == 'pending':
                    st.caption("⏳ 等待审核")


# ============================================================
# Finance Approval Page
# ============================================================
def page_finance():
    st.title("💰 财务审核")
    user = st.session_state.user
    if user['role'] not in ('finance', 'admin'):
        st.error("无权访问，仅财务角色可审核")
        return

    pending = get_pending_approvals()
    if not pending:
        st.success("暂无待审核项目 ✅")
        return

    st.subheader(f"待审核 ({len(pending)} 个)")

    for p in pending:
        with st.container(border=True):
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"**{p['brand_name']}** — {p['project_name']}")
                st.caption(f"编号: {p['project_code']} | 客户: {p['client_short']} | "
                          f"金额: {p.get('currency','USD')} {p['amount']:,.2f} | "
                          f"提交人: {p.get('created_by_name','?')} | "
                          f"提交时间: {p['created_at']}")

                # Show invoice path
                client_short = p['client_short']
                brand = p['brand_name']
                total_posts = p.get('total_posts', '')
                expected_inv = f"{brand}-{total_posts.replace(' ', '-')}-invoice.xlsx"
                inv_path = os.path.join("/Users/vincy/Documents/Wellcome/项目",
                                        client_short, brand, "财务", expected_inv)

                if os.path.exists(inv_path):
                    with open(inv_path, "rb") as f:
                        st.download_button(
                            f"📥 下载 Invoice (审核用)",
                            f, file_name=expected_inv,
                            key=f"dl_{p['id']}"
                        )

            with col2:
                st.write("")  # spacer
                st.write("")
                if st.button("✅ 通过", key=f"approve_{p['id']}", use_container_width=True, type="primary"):
                    output_dir = os.path.dirname(inv_path)
                    stamped_name = f"{brand}-{total_posts.replace(' ', '-')}-stamped.pdf"
                    stamped_path = os.path.join(output_dir, stamped_name)

                    if os.path.exists(inv_path):
                        with st.spinner("正在生成盖章 PDF..."):
                            try:
                                generate_stamped_pdf(inv_path, stamped_path)
                                approve_project(p['id'], user['id'], stamped_path)
                                # Store for immediate download
                                st.session_state['just_approved'] = {
                                    'name': stamped_name,
                                    'path': stamped_path,
                                    'brand': brand,
                                    'code': p['project_code']
                                }
                                st.rerun()
                            except Exception as e:
                                st.error(f"生成失败: {e}")
                    else:
                        st.error(f"找不到 Invoice 文件")

                if st.button("❌ 驳回", key=f"reject_{p['id']}", use_container_width=True):
                    reject_project(p['id'], user['id'])
                    st.warning("已驳回")
                    st.rerun()

    # Show just-approved download banner
    if 'just_approved' in st.session_state and st.session_state['just_approved']:
        ja = st.session_state['just_approved']
        st.divider()
        st.success(f"✅ 审核通过！{ja['brand']} ({ja['code']}) 盖章 PDF 已生成")
        with open(ja['path'], "rb") as f:
            st.download_button(
                f"📥 下载盖章 PDF — {ja['name']}",
                f, file_name=ja['name'],
                key="dl_just_approved",
                use_container_width=True
            )
        if st.button("✅ 已下载，清除提示"):
            st.session_state['just_approved'] = None
            st.rerun()

    # History of approved/rejected
    st.divider()
    st.subheader("审核历史")
    all_projects = get_projects(limit=200)
    approved_rejected = [p for p in all_projects if p.get('status') in ('approved', 'rejected')]
    if approved_rejected:
        for p in approved_rejected[:20]:
            status_icon = "✅" if p['status'] == 'approved' else "❌"
            st.write(f"{status_icon} {p['brand_name']} — {p['project_code']} — {p['created_at'][:10]}")
            if p.get('stamped_pdf_path') and os.path.exists(p['stamped_pdf_path']):
                with open(p['stamped_pdf_path'], "rb") as f:
                    st.download_button(
                        f"📥 下载盖章 PDF", f,
                        file_name=os.path.basename(p['stamped_pdf_path']),
                        key=f"stamped_{p['id']}"
                    )


# ============================================================
# Cash Receipt Page
# ============================================================
def page_receipt():
    st.title("🧾 开具收据")
    user = st.session_state.user
    if user['role'] not in ('finance', 'admin'):
        st.error("无权访问，仅财务角色可操作")
        return

    # Get approved projects to reference
    all_projects = get_projects(limit=200)
    approved = [p for p in all_projects if p.get('status') == 'approved']

    clients = get_clients()
    client_map = {c['id']: c for c in clients}

    mode = st.radio("选择方式", ["从已通过项目生成", "手动填写"], horizontal=True)

    if mode == "从已通过项目生成" and approved:
        proj_options = {f"{p['brand_name']} — {p['project_code']} ({p.get('currency','USD')} {p['amount']:,.0f})": p
                        for p in approved}
        selected_label = st.selectbox("选择已通过的项目", list(proj_options.keys()))
        selected_proj = proj_options[selected_label]
        client = client_map.get(selected_proj['client_id'], {})
        _receipt_form(client, selected_proj)
    elif mode == "从已通过项目生成":
        st.info("暂无已通过的项目，请先审核通过 Invoice 后再开收据")
    else:
        # Manual mode
        client_names = [c['short_name'] for c in clients]
        sel_client = st.selectbox("选择客户", client_names)
        client = {c['short_name']: c for c in clients}.get(sel_client, {})
        _receipt_form(client, None)


def _receipt_form(client, project):
    if not client:
        st.warning("请先选择客户")
        return

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("客户信息")
        st.write(f"**{client.get('full_name', '')}**")
        st.caption(f"联系人: {client.get('contact', '')}")
        st.caption(f"地址: {client.get('address', '')}")

        if project:
            st.subheader("关联项目")
            st.write(f"**{project.get('brand_name', '')}** — {project.get('project_name', '')}")
            st.caption(f"编号: {project.get('project_code', '')}")
            st.caption(f"金额: {project.get('currency','USD')} {project.get('amount',0):,.2f}")
            default_amount = project['amount']
            default_currency = project.get('currency', 'USD')
            default_venue = project.get('venue', '')
            default_period = project.get('execution_period', '')
        else:
            default_amount = 0.0
            default_currency = 'USD'
            default_venue = ''
            default_period = ''

    with col2:
        st.subheader("收款信息")
        issuer = st.text_input("开具人", value="Mr. Terry.Su")
        payment_date = st.date_input("付款日期", value=datetime.now())
        gained_date = st.date_input("到款日期", value=datetime.now())
        payment_method = st.selectbox("付款方式", ["BANK", "CASH", "TRANSFER"])
        payment_amount = st.number_input("实收金额", min_value=0.0,
                                         value=float(default_amount), step=100.0)
        currency = st.selectbox("币种", ["USD", "RMB"],
                                index=0 if default_currency == "USD" else 1)

    st.divider()
    if st.button("🧾 生成收据并盖章", type="primary", use_container_width=True):
        if payment_amount <= 0:
            st.error("请输入收款金额")
            return

        with st.spinner("正在生成收据..."):
            receipt_data = {
                'client_short': client.get('short_name', ''),
                'brand_name': project.get('brand_name', 'N/A') if project else 'Manual',
                'project_code': project.get('project_code', f"MANUAL-{datetime.now().strftime('%Y%m%d')}") if project else f"MANUAL-{datetime.now().strftime('%Y%m%d')}",
                'project_name': project.get('project_name', '') if project else '',
                'amount': project.get('amount', payment_amount) if project else payment_amount,
                'currency': currency,
                'payment_amount': payment_amount,
                'payment_date': payment_date,
                'gained_date': gained_date,
                'payment_method': payment_method,
                'issuer_name': issuer,
                'venue': default_venue,
                'project_date': default_period,
            }

            # Generate receipt xlsx
            xlsx_path = generate_cash_receipt(
                {'full_name': client['full_name'], 'address': client.get('address', ''),
                 'contact': client.get('contact', ''), 'phone': client.get('phone', ''),
                 'email': client.get('email', '')},
                receipt_data
            )

            # Generate stamped PDF
            stamped_dir = os.path.dirname(xlsx_path)
            stamped_name = xlsx_path.replace('.xlsx', '-stamped.pdf')
            try:
                generate_stamped_pdf(xlsx_path, stamped_name)
                st.success("✅ 收据已生成！")
                st.session_state['receipt_stamped'] = stamped_name
                st.rerun()
            except Exception as e:
                st.error(f"PDF 生成失败: {e}")

    # Show download if just generated
    if 'receipt_stamped' in st.session_state and st.session_state['receipt_stamped']:
        path = st.session_state['receipt_stamped']
        if os.path.exists(path):
            with open(path, "rb") as f:
                st.download_button(
                    "📥 下载盖章收据 PDF", f,
                    file_name=os.path.basename(path),
                    use_container_width=True
                )
            st.caption(f"文件位置: {path}")
            if st.button("清除提示"):
                st.session_state['receipt_stamped'] = None
                st.rerun()


# ============================================================
# Main routing
# ============================================================
if st.session_state.user is None:
    restored = _restore_session()
    if restored:
        st.session_state.user = restored
        st.session_state.page = "generate"

if st.session_state.user is None:
    page_login()
else:
    if not is_approved(st.session_state.user['id']) and st.session_state.user['role'] != 'admin':
        st.warning("⏳ 你的账号正在等待管理员审核，审核通过后即可使用。")
        st.button("退出", on_click=logout)
    else:
        render_sidebar()
        pages = {
            "generate": page_generate,
            "clients": page_clients,
            "history": page_history,
            "finance": page_finance,
            "receipt": page_receipt,
            "admin": page_admin,
        }
        page_fn = pages.get(st.session_state.page, page_generate)
        page_fn()
