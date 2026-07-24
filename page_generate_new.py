"""Generate page — DB status-driven, no slider, clear buttons."""

import streamlit as st
from datetime import datetime
import os, json, base64
from utils.database import (get_clients, get_client_by_id, get_project_by_id,
                            save_project, get_next_code_for_month, get_all_users,
                            get_connection)
from utils.generate import (generate_confirmation_letter, generate_invoice,
                            generate_email_confirmation)

def page_generate():
    st.title("📄 生成文档")
    user = st.session_state.user
    edit_id = st.session_state.get('edit_project_id')
    edit_data = get_project_by_id(edit_id) if edit_id else None
    if edit_id and not edit_data:
        st.session_state.pop('edit_project_id', None); st.rerun()

    status = edit_data.get('status','draft') if edit_data else 'draft'
    status_labels = {'draft':0,'confirmation_sent':1,'stamped_uploaded':2,'pending':3,'approved':4}
    stage_idx = status_labels.get(status, 0)

    all_labels = ['📝 基本信息','📄 确认函','📎 盖章确认函','🧾 申请发票','💰 开收据']

    if edit_data:
        st.info(f"📌 **{edit_data.get('brand_name','')}** ({edit_data.get('project_code','')}) — 状态：{all_labels[stage_idx]}")
        if st.button("❌ 返回工作台"):
            st.session_state.pop('edit_project_id', None); st.session_state.page = "workspace"; st.rerun()

    st.progress((stage_idx + 1) / 5, text=f"进度：{all_labels[stage_idx]}")
    st.caption(" → ".join(all_labels))
    st.divider()

    clients = get_clients()
    client_names = [c['short_name'] for c in clients]
    cmap = {c['short_name']: c for c in clients}

    if edit_data:
        _show_info(edit_data, client_names, cmap, user)
        st.divider()
        _stage_actions(edit_data, user)
    else:
        st.info("从「📝 项目工作台」选择一个项目，或新建一个项目")
        # Quick create
        _quick_create(client_names, cmap, user)


def _quick_create(client_names, cmap, user):
    with st.expander("➕ 快速创建新项目", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            sel = st.selectbox("客户简称", client_names, key="qc_sel")
            code = get_next_code_for_month(datetime.now().year, datetime.now().month)
            st.text_input("项目编号", value=code, key="qc_code")
            st.text_input("项目名称 *", key="qc_name")
            st.text_input("品牌名 *", key="qc_brand")
        with col2:
            cur = st.selectbox("币种", ["USD","RMB"], key="qc_cur")
            st.number_input("金额 *", min_value=0.0, step=100.0, value=None, key="qc_amt")
            st.date_input("到期日", value=datetime.now(), key="qc_due")
        if st.button("💾 创建项目", type="primary", use_container_width=True):
            data = {
                'project_code': st.session_state.get('qc_code',''),
                'project_name': st.session_state.get('qc_name',''),
                'brand_name': st.session_state.get('qc_brand',''),
                'amount': float(st.session_state.get('qc_amt',0) or 0),
                'currency': st.session_state.get('qc_cur','USD'),
                'due_date': str(st.session_state.get('qc_due','')),
                'client_id': cmap.get(sel,{}).get('id'),
                'client_short': sel,
                'created_by': user['id'],
                'owner_name': user['username'],
                'status': 'draft',
                'total_posts': '', 'venue': '', 'execution_period': '',
                'invoice_date': str(datetime.now().date()),
            }
            pid = save_project(data)
            st.session_state['edit_project_id'] = pid
            st.success("✅ 已创建！"); st.rerun()


def _show_info(edit_data, client_names, cmap, user):
    st.subheader("📝 项目基本信息")
    col1, col2 = st.columns(2)
    with col1:
        didx = 0
        ec = get_client_by_id(edit_data.get('client_id'))
        if ec and ec.get('short_name') in client_names:
            didx = client_names.index(ec['short_name'])
        sel = st.selectbox("客户简称", client_names, index=didx, key="ei_sel")
        c = cmap.get(sel,{})
        if c: st.caption(f"{c.get('full_name','')} | {c.get('contact','')}")

        users_list = get_all_users()
        unames = [u['username'] for u in users_list]
        dow = unames.index(edit_data.get('owner_name','')) if edit_data.get('owner_name') in unames else 0
        st.selectbox("负责人", unames, index=dow, key="ei_owner")

        # Project code with month selector
        from utils.database import get_next_code_for_month
        cm = st.selectbox("编号月份", list(range(1,13)),
                          index=datetime.now().month-1,
                          format_func=lambda m:f"{m}月", key="ei_month")
        default_code = edit_data.get('project_code','')
        if not default_code:
            try: default_code = get_next_code_for_month(datetime.now().year, cm)
            except: pass
        st.text_input("项目编号", value=default_code, key="ei_code")
        st.caption(f"💡 自动生成，可直接修改。{cm}月当前下一个编号已显示。")
        st.text_input("项目名称", value=edit_data.get('project_name',''), key="ei_name")
        st.text_input("品牌名", value=edit_data.get('brand_name',''), key="ei_brand")
        ci = 0 if edit_data.get('currency','USD')=='USD' else 1
        st.selectbox("币种", ["USD","RMB"], index=ci, key="ei_cur")
        st.number_input("金额", min_value=0.0, step=100.0, value=float(edit_data.get('amount',0)) if edit_data.get('amount') else None, key="ei_amt")

    with col2:
        st.text_input("执行地点", value=edit_data.get('venue','') or 'Bangkok', key="ei_venue")
        st.text_input("执行周期", value=edit_data.get('execution_period',''), key="ei_period")
        st.text_input("拍摄时间", value=edit_data.get('shooting_date',''), key="ei_shoot")
        st.text_input("总篇数", value=edit_data.get('total_posts',''), key="ei_posts")
        d = edit_data.get('due_date','')
        if d and not hasattr(d,'strftime'):
            try: d = datetime.strptime(str(d)[:10],'%Y-%m-%d')
            except: d = datetime.now()
        st.date_input("到期日", value=d if d and hasattr(d,'strftime') else datetime.now(), key="ei_due")
        st.text_input("合作内容", value=edit_data.get('content_type','') or 'UGC铺量', key="ei_content")
        st.text_input("发布平台", value=edit_data.get('platform','') or '小红书', key="ei_plat")

    # Cost
    st.caption("成本构成")
    R = {"USD":7.2,"RMB":1.0,"THB":0.2,"MYR":1.55}
    items = []; tr = 0.0
    ccols = st.columns(4)
    for i, cat in enumerate(["拍摄","餐饮交通","发布","补发"]):
        with ccols[i]:
            if st.checkbox(cat, key=f"ei_cb_{cat}"):
                a = st.number_input("金额", key=f"ei_a_{cat}", value=None, step=100.0)
                cu = st.selectbox("币种", ["RMB","USD","THB","MYR"], key=f"ei_c_{cat}")
                if a and a>0: tr+=a*R.get(cu,1); items.append({"name":cat,"amount":a,"currency":cu})

    if 'ei_custom_n' not in st.session_state: st.session_state['ei_custom_n'] = 0
    for i in range(st.session_state['ei_custom_n']):
        c1,c2,c3=st.columns([2,2,1])
        with c1: cn=st.text_input(f"分类#{i+1}", key=f"ei_cn{i}")
        with c2: ca=st.number_input("金额", key=f"ei_ca{i}", value=None, step=100.0)
        with c3: cc=st.selectbox("币种",["RMB","USD","THB","MYR"], key=f"ei_cc{i}")
        if cn and ca and ca>0: tr+=ca*R.get(cc,1); items.append({"name":cn,"amount":ca,"currency":cc})
    if st.button("➕ 添加分类"):
        st.session_state['ei_custom_n'] += 1; st.rerun()

    if tr>0: st.info(f"总成本(RMB): ¥{tr:,.0f}")

    if st.button("💾 保存信息", type="primary", use_container_width=True):
        due = st.session_state.get('ei_due')
        if hasattr(due,'strftime'): due = due.strftime('%Y-%m-%d')
        data = {
            'project_code':st.session_state.get('ei_code',''),
            'project_name':st.session_state.get('ei_name',''),
            'brand_name':st.session_state.get('ei_brand',''),
            'amount':float(st.session_state.get('ei_amt',0) or 0),
            'currency':st.session_state.get('ei_cur','USD'),
            'venue':st.session_state.get('ei_venue',''),
            'execution_period':st.session_state.get('ei_period',''),
            'shooting_date':st.session_state.get('ei_shoot',''),
            'total_posts':st.session_state.get('ei_posts',''),
            'due_date':str(due or ''),
            'content_type':st.session_state.get('ei_content',''),
            'platform':st.session_state.get('ei_plat',''),
            'estimated_cost':float(tr),
            'cost_currency':'RMB',
            'cost_breakdown':json.dumps(items, ensure_ascii=False) if items else '',
            'client_id':c.get('id'),
            'owner_name':st.session_state.get('ei_owner',''),
            'created_by':user['id'],
        }
        try:
            get_connection().table("projects").update(data).eq("id",edit_data['id']).execute()
            st.success("✅ 已保存！")
        except Exception as e:
            st.error(f"保存失败: {e}")


def _stage_actions(edit_data, user):
    status = edit_data.get('status','draft')
    st.subheader("📌 当前操作")

    if status == 'draft':
        _act_confirmation(edit_data, user)
    elif status == 'confirmation_sent':
        _act_upload(edit_data, user)
    elif status == 'stamped_uploaded':
        _act_submit(edit_data, user)
    elif status == 'pending':
        st.info("⏳ 已提交，等待财务审核通过...")
    elif status == 'approved':
        _act_approved(edit_data, user)
    elif status == 'rejected':
        st.warning("已驳回，请修改信息后重新提交")
        _act_submit(edit_data, user)


def _act_confirmation(ed, user):
    st.write("📄 生成确认函，发给客户盖章")
    if st.button("📄 生成确认函", type="primary", use_container_width=True):
        client = get_client_by_id(ed.get('client_id')) or {}
        proj = {'project_code':ed.get('project_code',''),'project_name':ed.get('project_name',''),
                'brand_name':ed.get('brand_name',''),'venue':ed.get('venue',''),
                'execution_period':ed.get('execution_period',''),'shooting_date':ed.get('shooting_date',''),
                'total_posts':ed.get('total_posts',''),'amount':ed.get('amount',0),
                'application_date':datetime.now().strftime('%b %d, %Y')}
        path = generate_confirmation_letter({'full_name':client.get('full_name',''),'contact':client.get('contact','')}, proj)
        get_connection().table("projects").update({"status":"confirmation_sent"}).eq("id",ed['id']).execute()
        with open(path,'rb') as f:
            st.download_button("📥 下载确认函", f, file_name=f"{ed.get('brand_name','')}-confirmation-letter.docx", key="dlcf4")
        subj,body = generate_email_confirmation(proj)
        with st.expander("📧 邮件"):
            st.text_input("主题", value=subj); st.text_area("正文", value=body, height=120)
        st.success("已生成！请发给客户盖章。"); st.rerun()


def _act_upload(ed, user):
    st.write("📎 客户盖章后，上传确认函")
    up = st.file_uploader("上传盖章确认函", type=["png","jpg","jpeg","pdf"], key=f"uu_{ed['id']}")
    if up:
        b64 = base64.b64encode(up.read()).decode()
        get_connection().table("projects").update({"stamped_confirmation":b64,"status":"stamped_uploaded"}).eq("id",ed['id']).execute()
        st.success("✅ 已上传！"); st.rerun()
    if ed.get('stamped_confirmation'):
        st.success("✅ 已上传")


def _act_submit(ed, user):
    st.write("🧾 确认信息，提交财务审核开发票")

    errs = []
    if not ed.get('stamped_confirmation'): errs.append("❌ 未上传盖章确认函")
    if not ed.get('estimated_cost'): errs.append("❌ 成本构成为空")
    if errs:
        for e in errs: st.error(e)
        return

    # Step 1: Review and confirm info
    if 'invoice_confirmed' not in st.session_state:
        st.session_state['invoice_confirmed'] = False

    if not st.session_state['invoice_confirmed']:
        st.success("✅ 条件满足，请核对信息并补充")
        client = get_client_by_id(ed.get('client_id')) or {}

        # Invoice type
        inv_type = st.selectbox("发票类型", ["服务款-全款","服务款-前款","服务款-后款","样品费报销","差旅费报销"],
                               key="inv_type")
        default_amt = float(ed.get('amount',0))
        inv_amount = st.number_input("本次开票金额", value=default_amt if default_amt>0 else None,
                                     step=100.0, key="inv_amt",
                                     help=f"合同总额：{ed.get('currency','USD')} {ed.get('amount',0):,.2f}")
        inv_note = st.text_area("备注", key="inv_note", placeholder="说明本次开票内容...")

        c1,c2=st.columns(2)
        with c1:
            st.write(f"项目：{ed.get('project_name','')}")
            st.write(f"品牌：{ed.get('brand_name','')}")
            st.write(f"编号：{ed.get('project_code','')}")
        with c2:
            st.write(f"总金额：{ed.get('currency','USD')} {ed.get('amount',0):,.2f}")
            st.write(f"成本(RMB)：¥{ed.get('estimated_cost',0):,.0f}")
            st.write(f"到期：{str(ed.get('due_date',''))[:10]}")

        if st.button("✅ 确认信息无误，进入提交", type="primary", use_container_width=True):
            st.session_state['invoice_confirmed'] = True
            st.rerun()
    else:
        # Step 2: Submit
        st.success("✅ 信息已确认，请点击下方按钮提交")
        f_ok = st.checkbox("已在飞书立项", value=ed.get('feishu_approved',False))
        inv_type = st.session_state.get('inv_type','服务款-前款')
        inv_amt = st.session_state.get('inv_amt',ed.get('amount',0))
        st.write(f"发票类型：**{inv_type}** | 金额：{ed.get('currency','USD')} {inv_amt:,.2f}")

        col_back, col_submit = st.columns(2)
        with col_back:
            if st.button("← 返回修改信息", use_container_width=True):
                st.session_state['invoice_confirmed'] = False
                st.rerun()
        with col_submit:
            if st.button("📤 提交财务审核", type="primary", use_container_width=True):
                note = st.session_state.get('inv_note','')
                get_connection().table("projects").update({
                    "feishu_approved":f_ok, "status":"pending",
                    "amount": float(inv_amt or ed.get('amount',0)),
                    "content_type": inv_type + (f" [{note}]" if note else ""),
                }).eq("id",ed['id']).execute()
                st.session_state['invoice_confirmed'] = False
                st.success(f"✅ {inv_type} 已提交！等待财务审核。")
                st.balloons(); st.rerun()


def _act_approved(ed, user):
    st.success("✅ 财务已通过！")
    if ed.get('payment_received'):
        if st.button("🧾 开收据", type="primary", use_container_width=True):
            st.session_state['receipt_project_id'] = ed['id']
            st.session_state.page = "receipt"; st.rerun()
    else:
        st.write("等待客户付款后点击下方按钮")
        if st.button("💰 客户已付款，标记到账", type="primary", use_container_width=True):
            get_connection().table("projects").update({
                "payment_received": True,
                "received_date": datetime.now().strftime('%Y-%m-%d'),
            }).eq("id",ed['id']).execute()
            st.success("已标记！"); st.rerun()
