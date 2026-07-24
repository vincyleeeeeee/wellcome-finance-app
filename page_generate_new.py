"""New generate page with progress bar and staged workflow."""

import streamlit as st
from datetime import datetime
import os, json, base64
from utils.database import (get_clients, get_client_by_id, get_client_by_short_name,
                            get_project_by_id, save_project, get_next_code_for_month,
                            get_all_users, get_connection)
from utils.generate import (generate_confirmation_letter, generate_invoice,
                            generate_email_confirmation, generate_email_invoice)

def page_generate():
    st.title("📄 生成文档")
    user = st.session_state.user
    edit_id = st.session_state.get('edit_project_id')
    edit_data = get_project_by_id(edit_id) if edit_id else None
    if edit_id and not edit_data:
        st.session_state.pop('edit_project_id', None)

    current_status = edit_data.get('status', 'draft') if edit_data else 'draft'
    stage_map = {'draft': 0, 'confirmation_sent': 1, 'stamped_uploaded': 2, 'pending': 3, 'approved': 4}
    stage_idx = stage_map.get(current_status, 0)

    if edit_data:
        st.info(f"📌 项目：**{edit_data.get('brand_name','')}** ({edit_data.get('project_code','')})")
        # Stage labels above slider
        all_labels = ['📝 信息','📄 确认函','📎 客户盖章确认函','🧾 发票','💰 收据']
        st.caption("   ".join(all_labels))
        # Use session_state to persist slider value across reruns
        slider_key = f"stage_slider_{edit_id}"
        if slider_key not in st.session_state:
            st.session_state[slider_key] = stage_idx

        all_labels = ['📝 信息','📄 确认函','📎 客户盖章确认函','🧾 发票','💰 收据']
        st.caption("   ".join(all_labels))
        target = st.select_slider(
            "👇 拖动到当前需要操作的步骤",
            options=[0,1,2,3,4],
            value=st.session_state[slider_key],
            format_func=lambda x: '',
            label_visibility="collapsed",
            key=slider_key
        )
        st.caption(f"当前：**{all_labels[target]}**")
        stage_idx = target

        c_left, c_right = st.columns(2)
        with c_left:
            if st.button("❌ 取消", use_container_width=True):
                st.session_state.pop('edit_project_id', None)
                st.session_state.pop(slider_key, None)
                st.rerun()
        with c_right:
            next_step = min(stage_idx + 1, 4)
            if st.button(f"下一步 → {all_labels[next_step]}", use_container_width=True, type="primary"):
                st.session_state[slider_key] = next_step
                st.rerun()
    else:
        st.info("填一次基本信息，后续各阶段按流程推进")

    labels = ['📝 信息','📄 确认函','📎 客户盖章确认函','🧾 发票','💰 收据']
    st.progress((stage_idx + 1) / len(labels), text=f"当前进度：{labels[stage_idx]}")
    st.caption(" → ".join(f"**{l}**" if i == stage_idx else l for i, l in enumerate(labels)))
    st.divider()

    clients = get_clients()
    client_names = [c['short_name'] for c in clients]
    cmap = {c['short_name']: c for c in clients}

    # Always show info form (editable)
    _show_info_section(edit_data, clients, client_names, cmap, user)
    st.divider()

    # Stage-specific actions
    if stage_idx == 0:
        pass  # info already shown above
    elif stage_idx == 1:
        _stage_confirmation(edit_data, user)
    elif stage_idx == 2:
        _stage_stamped(edit_data, user)
    elif stage_idx == 3:
        _stage_invoice(edit_data, user)
    elif stage_idx == 4:
        _stage_receipt(edit_data, user)



def _stage_info(edit_data, clients, client_names, cmap, user):
    st.subheader("📝 基本信息")
    _show_info_fields(edit_data, client_names, cmap, user)
    if st.button("💾 保存信息", type="primary", use_container_width=True):
        _save_info(edit_data, client_names, cmap, user)
        st.success("✅ 已保存！"); st.rerun()


def _stage_confirmation(edit_data, user):
    st.subheader("📄 确认函")
    if not edit_data:
        st.warning("请先填写基本信息")
        return
    st.success("✅ 基本信息已就绪")
    if st.button("📄 生成确认函", type="primary", use_container_width=True):
        client = get_client_by_id(edit_data.get('client_id')) or {}
        proj = {'project_code':edit_data.get('project_code',''),'project_name':edit_data.get('project_name',''),
                'brand_name':edit_data.get('brand_name',''),'venue':edit_data.get('venue',''),
                'execution_period':edit_data.get('execution_period',''),'shooting_date':edit_data.get('shooting_date',''),
                'total_posts':edit_data.get('total_posts',''),'amount':edit_data.get('amount',0),
                'application_date':datetime.now().strftime('%b %d, %Y')}
        path = generate_confirmation_letter({'full_name':client.get('full_name',''),'contact':client.get('contact','')}, proj)
        get_connection().table("projects").update({"status":"confirmation_sent"}).eq("id",edit_data['id']).execute()
        with open(path,'rb') as f:
            st.download_button("📥 下载确认函", f, file_name=f"{edit_data.get('brand_name','')}-confirmation-letter.docx", key="dl_cf2")
        subj,body = generate_email_confirmation(proj)
        with st.expander("📧 邮件文案"):
            st.text_input("主题", value=subj); st.text_area("正文", value=body, height=200)


def _stage_stamped(edit_data, user):
    st.subheader("📎 上传客户盖章确认函")
    if not edit_data:
        st.warning("请先完成前面阶段"); return
    uid = edit_data['id']
    up = st.file_uploader("上传盖章确认函", type=["png","jpg","jpeg","pdf"], key=f"s_{uid}")
    if up:
        b64 = base64.b64encode(up.read()).decode()
        get_connection().table("projects").update({"stamped_confirmation":b64,"status":"stamped_uploaded"}).eq("id",uid).execute()
        st.success("✅ 已上传！"); st.rerun()
    if edit_data.get('stamped_confirmation'):
        st.success("✅ 已上传盖章确认函")
        # Show image preview if it's an image, otherwise download button
        try:
            st.image(base64.b64decode(edit_data['stamped_confirmation']))
        except:
            st.download_button("📥 下载查看盖章确认函",
                              base64.b64decode(edit_data['stamped_confirmation']),
                              file_name="盖章确认函.pdf",
                              mime="application/pdf")


def _stage_invoice(edit_data, user):
    st.subheader("🧾 申请开发票")
    if not edit_data: st.warning("请先完成前面阶段"); return

    # Check prerequisites
    errors = []
    if not edit_data.get('stamped_confirmation'):
        errors.append("❌ 尚未上传客户盖章确认函（请回「📎 客户盖章确认函」阶段上传）")
    if not edit_data.get('estimated_cost') or edit_data.get('estimated_cost') == 0:
        errors.append("❌ 成本构成为空（请编辑基本信息添加成本细项）")

    if errors:
        for e in errors: st.error(e)
        return

    # === Review card ===
    st.success("✅ 所有前置条件已满足，请确认以下信息：")
    client = get_client_by_id(edit_data.get('client_id')) or {}

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            st.write(f"**项目**：{edit_data.get('project_name','')}")
            st.write(f"**品牌**：{edit_data.get('brand_name','')}")
            st.write(f"**编号**：{edit_data.get('project_code','')}")
            st.write(f"**客户**：{client.get('full_name','')}")
        with c2:
            st.write(f"**金额**：{edit_data.get('currency','USD')} {edit_data.get('amount',0):,.2f}")
            st.write(f"**总成本(RMB)**：¥{edit_data.get('estimated_cost',0):,.0f}")
            st.write(f"**执行周期**：{edit_data.get('execution_period','')}")
            st.write(f"**到期日**：{str(edit_data.get('due_date',''))[:10]}")
        # Cost breakdown
        try:
            import json as _j
            ci = _j.loads(edit_data.get('cost_breakdown','') or '[]')
            if ci:
                cost_str = "、".join(f"{i['name']}({i.get('currency','RMB')}{i.get('amount',0):,.0f})" for i in ci)
                st.caption(f"**成本构成**：{cost_str}")
        except: pass

    # Stamped confirmation
    with st.expander("📎 查看盖章确认函"):
        try: st.image(base64.b64decode(edit_data['stamped_confirmation']))
        except: st.download_button("📥 下载确认函", base64.b64decode(edit_data['stamped_confirmation']),
                                  file_name="盖章确认函.pdf")

    st.divider()
    f_ok = st.checkbox("已在飞书立项", value=edit_data.get('feishu_approved',False))
    if st.button("📤 确认无误，提交财务审核", type="primary", use_container_width=True):
        # Regenerate invoice
        inv_path = generate_invoice(client, {
            'client_short':edit_data.get('client_short',client.get('short_name','')),
            'project_code':edit_data.get('project_code',''),'project_name':edit_data.get('project_name',''),
            'brand_name':edit_data.get('brand_name',''),'amount':edit_data.get('amount',0),
            'currency':edit_data.get('currency','USD'),'venue':edit_data.get('venue',''),
            'execution_period':edit_data.get('execution_period',''),'shooting_date':edit_data.get('shooting_date',''),
            'total_posts':edit_data.get('total_posts',''),'invoice_date':datetime.now().date(),
            'due_date':edit_data.get('due_date'),'content_type':edit_data.get('content_type','UGC铺量'),
            'platform':edit_data.get('platform','小红书'),
            'invoice_project_name':f"{edit_data.get('brand_name','')} – {edit_data.get('total_posts','')} CONTENT PACKAGE",
        })
        get_connection().table("projects").update({
            "feishu_approved":f_ok, "status":"pending"
        }).eq("id",edit_data['id']).execute()
        with open(inv_path,'rb') as f:
            st.download_button("📥 下载发票(未盖章)", f, file_name=f"{edit_data.get('brand_name','')}-invoice.xlsx")
        st.success("✅ 已提交财务审核！财务通过后可下载盖章发票。")
        st.balloons()


def _stage_receipt(edit_data, user):
    st.subheader("💰 收据")
    if edit_data and edit_data.get('status')=='approved':
        if st.button("🧾 开收据", type="primary", use_container_width=True):
            st.session_state['receipt_project_id'] = edit_data['id']
            st.session_state.page = "receipt"; st.rerun()
    else:
        st.info("请等待财务审核通过")


def _show_info_section(edit_data, clients, client_names, cmap, user):
    if not edit_data: return
    st.subheader("📝 项目基本信息")
    _show_info_fields(edit_data, client_names, cmap, user)


def _show_info_fields(edit_data, client_names, cmap, user):
    col1,col2 = st.columns(2)
    with col1:
        didx = 0
        if edit_data:
            ec = get_client_by_id(edit_data.get('client_id'))
            if ec and ec.get('short_name') in client_names: didx = client_names.index(ec['short_name'])
        sel = st.selectbox("客户简称 *", client_names, index=didx, key="nf_sel")
        c = cmap.get(sel,{})
        if c: st.caption(f"{c.get('full_name','')} | {c.get('contact','')}")

        users_list = get_all_users()
        owner_names = [u['username'] for u in users_list]
        default_owner = edit_data.get('owner_name','') if edit_data else st.session_state.user['username']
        dow = owner_names.index(default_owner) if default_owner in owner_names else 0
        st.selectbox("项目负责人 *", owner_names, index=dow, key="nf_owner")

        cm_m = st.selectbox("编号月份", list(range(1,13)), index=datetime.now().month-1, format_func=lambda m:f"{m}月")
        code = get_next_code_for_month(datetime.now().year, cm_m) if not edit_data else edit_data.get('project_code','')
        st.text_input("项目编号 *", value=code, key="nf_code")
        st.text_input("项目名称 *", value=edit_data.get('project_name','') if edit_data else '', key="nf_name")
        st.text_input("客户品牌名 *", value=edit_data.get('brand_name','') if edit_data else '', key="nf_brand")
        cur_idx = 0 if (edit_data.get('currency','USD') if edit_data else 'USD')=='USD' else 1
        st.selectbox("币种", ["USD","RMB"], index=cur_idx, key="nf_cur")
        st.number_input("项目金额 *", min_value=0.0, step=100.0, value=float(edit_data.get('amount',0)) if edit_data else None, key="nf_amt")

    with col2:
        st.text_input("执行地点", value=edit_data.get('venue','Bangkok') if edit_data else 'Bangkok', key="nf_venue")
        st.text_input("执行周期", value=edit_data.get('execution_period','') if edit_data else '', key="nf_period")
        st.text_input("预计拍摄时间", value=edit_data.get('shooting_date','') if edit_data else '', key="nf_shoot")
        st.text_input("总发布篇数", value=edit_data.get('total_posts','') if edit_data else '', key="nf_posts")
        st.date_input("到期日", value=datetime.now(), key="nf_due_date")
        st.text_input("合作内容", value="UGC铺量", key="nf_content")
        st.text_input("发布平台", value="小红书", key="nf_plat")

    # Cost
    st.caption("成本构成")
    R = {"USD":7.2,"RMB":1.0,"THB":0.2,"MYR":1.55}
    items = []; tr = 0.0
    ccols = st.columns(4)
    for i, cat in enumerate(["拍摄","餐饮交通","发布","补发"]):
        with ccols[i]:
            if st.checkbox(cat, key=f"nf_cb_{cat}"):
                a = st.number_input("金额", key=f"nf_a_{cat}", value=None, step=100.0)
                cu = st.selectbox("币种", ["RMB","USD","THB","MYR"], key=f"nf_c_{cat}")
                if a and a>0: tr+=a*R.get(cu,1); items.append({"name":cat,"amount":a,"currency":cu})
    # Dynamic custom cost items
    if 'custom_cost_count' not in st.session_state:
        st.session_state['custom_cost_count'] = 0
    for i in range(st.session_state['custom_cost_count']):
        cc1,cc2,cc3 = st.columns([2,2,1])
        with cc1:
            cname = st.text_input(f"分类名#{i+1}", key=f"nf_cn{i}", placeholder="如KOL费用、场地费、道具...")
        with cc2:
            camt = st.number_input("金额", key=f"nf_ca{i}", value=None, step=100.0)
        with cc3:
            ccur = st.selectbox("币种",["RMB","USD","THB","MYR"], key=f"nf_cc{i}")
        if cname and camt and camt > 0:
            tr += camt * R.get(ccur,1)
            items.append({"name":cname,"amount":camt,"currency":ccur})
    col_add, _ = st.columns([1,4])
    with col_add:
        if st.button("➕ 添加分类", use_container_width=True):
            st.session_state['custom_cost_count'] += 1
            st.rerun()
    if tr>0: st.info(f"总成本(RMB): ¥{tr:,.0f}")

    if st.button("💾 保存信息", type="primary", use_container_width=True):
        ok = _save_info(edit_data, client_names, cmap, user)
        if ok:
            st.success("✅ 信息已保存！点「下一步」推进到下一阶段")


def _save_info(edit_data, client_names, cmap, user):
    try:
        import json as _j
        sel = st.session_state.get('nf_sel','')
        c = cmap.get(sel,{})
        cost_items = _j.dumps(_collect_cost(), ensure_ascii=False)
        total = sum(i['amount']*{"USD":7.2,"RMB":1.0,"THB":0.2,"MYR":1.55}.get(i['currency'],1) for i in (_collect_cost() or []))
        due_d = st.session_state.get('nf_due_date')
        if hasattr(due_d, 'strftime'): due_d = due_d.strftime('%Y-%m-%d')
        data = {
            'client_short':sel,'project_code':st.session_state.get('nf_code',''),
            'project_name':st.session_state.get('nf_name',''),'brand_name':st.session_state.get('nf_brand',''),
            'amount':float(st.session_state.get('nf_amt',0) or 0),'currency':st.session_state.get('nf_cur','USD'),
            'venue':st.session_state.get('nf_venue',''),'execution_period':st.session_state.get('nf_period',''),
            'shooting_date':st.session_state.get('nf_shoot',''),'total_posts':st.session_state.get('nf_posts',''),
            'invoice_date':str(datetime.now().date()),'due_date':str(due_d or ''),
            'content_type':st.session_state.get('nf_content','UGC铺量'),'platform':st.session_state.get('nf_plat','小红书'),
            'estimated_cost':float(total),'cost_currency':'RMB','cost_breakdown':cost_items,
            'created_by':user['id'],'client_id':c.get('id'),
            'owner_name':st.session_state.get('nf_owner',''),
            'invoice_project_name':f"{st.session_state.get('nf_brand','')} – {st.session_state.get('nf_posts','')} CONTENT PACKAGE",
        }
        if edit_data:
            get_connection().table("projects").update(data).eq("id",edit_data['id']).execute()
        else:
            data['status']='draft'; save_project(data)
        return True
    except Exception as e:
        st.error(f"保存失败: {e}")
        return False


def _collect_cost():
    items = []
    R = {"USD":7.2,"RMB":1.0,"THB":0.2,"MYR":1.55}
    for cat in ["拍摄","餐饮交通","发布","补发"]:
        if st.session_state.get(f'nf_cb_{cat}'):
            items.append({"name":cat,"amount":st.session_state.get(f'nf_a_{cat}',0),"currency":st.session_state.get(f'nf_c_{cat}','RMB')})
    if st.session_state.get('nf_cn'):
        items.append({"name":st.session_state.get('nf_cn',''),"amount":st.session_state.get('nf_ca',0),"currency":st.session_state.get('nf_cc','RMB')})
    return items
