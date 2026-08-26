"""Generate page — DB status-driven, no slider, clear buttons."""

import streamlit as st
from datetime import datetime
import os, json, base64, re
from utils.database import (get_clients, get_client_by_id, get_project_by_id,
                            save_project, get_all_users,
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

        # Persistent confirmation download
        if st.session_state.get('confirmation_path'):
            cf_path = st.session_state['confirmation_path']
            cf = st.session_state['confirmation_proj']
            if not os.path.exists(cf_path):
                # Regenerate if file was cleaned up
                client = get_client_by_id(edit_data.get('client_id')) if edit_data else {}
                cf_path = generate_confirmation_letter({'full_name':client.get('full_name',''),'contact':client.get('contact','')}, cf)
                st.session_state['confirmation_path'] = cf_path
            with st.container(border=True):
                st.success("📄 确认函已生成！下载后点下方按钮进入下一步")
                with open(cf_path, 'rb') as f:
                    st.download_button("📥 下载确认函", f, file_name=f"{cf.get('brand_name','')}-confirmation-letter.docx", key="dlcf_p")
                subj,body = generate_email_confirmation(cf)
                with st.expander("📧 邮件"):
                    st.text_input("主题", value=subj, key="cf_s"); st.text_area("正文", value=body, height=120, key="cf_b")
                if st.button("✅ 已下载，进入下一步", type="primary", use_container_width=True):
                    get_connection().table("projects").update({"status":"confirmation_sent"}).eq("id",edit_data['id']).execute()
                    st.session_state.pop('confirmation_path', None)
                    st.session_state.pop('confirmation_proj', None)
                    st.rerun()
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
            st.text_input("项目编号（开发票时自动分配）", value="", key="qc_code",
                          placeholder="留空，开发票时自动生成")
            from utils.database import generate_project_code
            ref_code = generate_project_code(datetime.now().strftime('%Y-%m-%d'))
            st.caption(f"📝 今天开发票的话，下一个可用：**{ref_code}**")
            st.text_input("项目名称 *", key="qc_name",
                          placeholder="laclef_202606_公寓测评_小红书KOL_4")
            st.caption("格式：品牌_年月_产品类型_小红书UGC/小红书KOL_数量")
            st.text_input("品牌名 *", key="qc_brand")
        with col2:
            cur = st.selectbox("币种", ["USD","RMB"], key="qc_cur")
            st.number_input("金额 *", min_value=0.0, step=100.0, value=None, key="qc_amt")
            # Auto due date by client
            qc_due_default = datetime.now()
            today = datetime.now()
            if sel == 'POP':
                qc_due_default = datetime(today.year, today.month+1, 5) if today.month < 12 else datetime(today.year+1, 1, 5)
            elif sel == 'KLT':
                # KLT pays 50% on next 10th, 50% on next 25th
                if today.day < 10:
                    first = datetime(today.year, today.month, 10)
                    second = datetime(today.year, today.month, 25)
                elif today.day < 25:
                    first = datetime(today.year, today.month, 25)
                    if today.month == 12: second = datetime(today.year+1, 1, 10)
                    else: second = datetime(today.year, today.month+1, 10)
                else:
                    if today.month == 12:
                        first = datetime(today.year+1, 1, 10)
                        second = datetime(today.year+1, 1, 25)
                    else:
                        first = datetime(today.year, today.month+1, 10)
                        second = datetime(today.year, today.month+1, 25)
                qc_due_default = first
            st.date_input("到期日（客户付款时间）", value=qc_due_default, key="qc_due")
            if sel == 'POP': st.caption("💡 POP 默认次月5日付款")
            elif sel == 'KLT':
                f1 = first.strftime('%-m月%-d日') if hasattr(first,'strftime') else str(first)
                f2 = second.strftime('%-m月%-d日') if hasattr(second,'strftime') else str(second)
                st.caption(f"💡 KLT 分两次付款：50% {f1} + 50% {f2}")
            else: st.caption("💡 请与客户确认付款时间")
        if st.button("💾 创建项目", type="primary", use_container_width=True):
            if not st.session_state.get('qc_name') or not st.session_state.get('qc_brand') or (st.session_state.get('qc_amt') or 0) <= 0:
                st.error("客户、项目名称、品牌名、金额为必填项")
                st.stop()
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


def _parse_exec_period(period):
    """从执行周期字符串解析 (start, end) datetime；失败返回 (None, None)。"""
    if not period:
        return None, None
    s = str(period)
    # 数字格式：2026/8/13 - 2026/12/31
    m = re.search(r'(\d{4})/(\d{1,2})/(\d{1,2})\s*[-–~到]\s*(\d{4})/(\d{1,2})/(\d{1,2})', s)
    if m:
        try:
            return (datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                    datetime(int(m.group(4)), int(m.group(5)), int(m.group(6))))
        except (ValueError, IndexError):
            pass
    # 英文格式：Aug - Dec 2026
    _mon = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}
    m = re.search(r'([A-Za-z]{3,})\.?\s*[-–~到]\s*([A-Za-z]{3,})\.?\s*(\d{4})', s)
    if m:
        try:
            y = int(m.group(3))
            mo1 = _mon.get(m.group(1)[:3].lower())
            mo2 = _mon.get(m.group(2)[:3].lower())
            if mo1 and mo2:
                return datetime(y, mo1, 1), datetime(y, mo2, 1)
        except (ValueError, IndexError):
            pass
    return None, None


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
        owner_name = edit_data.get('owner_name','') or user['username']
        dow = unames.index(owner_name) if owner_name in unames else 0
        st.selectbox("负责人", unames, index=dow, key="ei_owner")

        # Project code — show next available for reference, assigned at invoice time
        existing_code = edit_data.get('project_code','')
        st.text_input("项目编号", value=existing_code, key="ei_code",
                      placeholder="留空，开发票时按当天日期自动分配")
        # Show next available code for reference
        if not existing_code:
            from utils.database import generate_project_code
            today_code = generate_project_code(datetime.now().strftime('%Y-%m-%d'))
            st.caption(f"📝 今天开发票的话，下一个可用编号：**{today_code}**（仅供参考，审核时自动分配）")
        st.text_input("项目名称", value=edit_data.get('project_name',''), key="ei_name",
                      placeholder="laclef_202606_公寓测评_小红书KOL_4")
        st.caption("格式：品牌_年月_产品类型_小红书UGC/小红书KOL_数量")
        st.text_input("品牌名", value=edit_data.get('brand_name',''), key="ei_brand")
        ci = 0 if edit_data.get('currency','USD')=='USD' else 1
        st.selectbox("币种", ["USD","RMB"], index=ci, key="ei_cur")
        st.number_input("金额", min_value=0.0, step=100.0, value=float(edit_data.get('amount',0)) if edit_data.get('amount') else None, key="ei_amt")

    with col2:
        st.text_input("执行地点", value=edit_data.get('venue','') or 'Bangkok', key="ei_venue")
        # 从已有执行周期回填起止日期（否则编辑时总是显示今天、保存会覆盖原值）
        exec_start_default, exec_end_default = _parse_exec_period(edit_data.get('execution_period',''))
        exec_start_default = exec_start_default or datetime.now()
        exec_end_default = exec_end_default or datetime.now()
        col_start, col_end = st.columns(2)
        with col_start:
            exec_start = st.date_input("项目开始", value=exec_start_default, key=f"ei_start_{edit_data.get('id')}")
        with col_end:
            exec_end = st.date_input("项目结束", value=exec_end_default, key=f"ei_end_{edit_data.get('id')}")
        # Auto-generate execution period（英文月份缩写，如 Aug - Dec 2026）
        _months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']
        if exec_start.year == exec_end.year:
            exec_period_auto = f"{_months[exec_start.month-1]} - {_months[exec_end.month-1]} {exec_end.year}"
        else:
            exec_period_auto = f"{_months[exec_start.month-1]} {exec_start.year} - {_months[exec_end.month-1]} {exec_end.year}"
        st.caption(f"执行周期：{exec_period_auto}")
        st.text_input("拍摄时间", value=edit_data.get('shooting_date',''), key="ei_shoot")
        st.text_input("总篇数", value=edit_data.get('total_posts',''), key="ei_posts",
                      placeholder="格式：150 photo posts")

        # Due date with client-specific defaults
        def _default_due(short_name):
            today = datetime.now()
            if short_name == 'POP':
                if today.month == 12: return datetime(today.year+1, 1, 5)
                return datetime(today.year, today.month+1, 5)
            elif short_name == 'KLT':
                if today.day < 10: return datetime(today.year, today.month, 10)
                elif today.day < 25: return datetime(today.year, today.month, 25)
                else:
                    if today.month == 12: return datetime(today.year+1, 1, 10)
                    return datetime(today.year, today.month+1, 10)
            return None

        auto_d = _default_due(sel)
        d = edit_data.get('due_date','')
        if d and not hasattr(d,'strftime'):
            try: d = datetime.strptime(str(d)[:10],'%Y-%m-%d')
            except: d = auto_d or datetime.now()
        default_d = d if d and hasattr(d,'strftime') else (auto_d or datetime.now())
        st.date_input("到期日（客户付款时间）", value=default_d, key="ei_due")

        due_note = ""
        if sel == 'POP': due_note = "💡 POP 默认次月5日付款"
        elif sel == 'KLT':
            today2 = datetime.now()
            if today2.day < 10:
                f1, f2 = f"{today2.month}月10日", f"{today2.month}月25日"
            elif today2.day < 25:
                f1 = f"{today2.month}月25日"
                nm = today2.month+1 if today2.month<12 else 1
                f2 = f"{nm}月10日"
            else:
                nm = today2.month+1 if today2.month<12 else 1
                f1, f2 = f"{nm}月10日", f"{nm}月25日"
            due_note = f"💡 KLT 分两次付款：50% {f1} + 50% {f2}"
        else: due_note = "💡 请与客户确认付款时间"
        st.caption(due_note)
        st.text_input("合作内容", value=edit_data.get('content_type','') or 'UGC铺量', key="ei_content")
        st.text_input("发布平台", value=edit_data.get('platform','') or '小红书', key="ei_plat")

    # Cost - pre-fill from edit_data on first load
    st.caption("成本构成")
    R = {"USD":7.2,"RMB":1.0,"THB":0.2,"MYR":1.55}
    items = []; tr = 0.0

    # Init checkboxes from edit data if not yet set
    try:
        existing_costs = json.loads(edit_data.get('cost_breakdown','') or '[]')
        cost_map = {i['name']: i for i in existing_costs}
        for cat in ["拍摄","餐饮交通","兼职执行","发布","补发"]:
            if cat in cost_map and f"ei_cb_{cat}" not in st.session_state:
                st.session_state[f"ei_cb_{cat}"] = True
                st.session_state[f"ei_a_{cat}"] = float(cost_map[cat].get('amount',0))
                st.session_state[f"ei_c_{cat}"] = cost_map[cat].get('currency','RMB')
    except: pass

    ccols = st.columns(5)
    for i, cat in enumerate(["拍摄","餐饮交通","兼职执行","发布","补发"]):
        with ccols[i]:
            if st.checkbox(cat, value=st.session_state.get(f"ei_cb_{cat}", False), key=f"ei_cb_{cat}"):
                a = st.number_input("金额", key=f"ei_a_{cat}", step=100.0)
                cu = st.selectbox("币种", ["RMB","USD","THB","MYR"], key=f"ei_c_{cat}")
                if a and a>0: tr+=a*R.get(cu,1); items.append({"name":cat,"amount":a,"currency":cu})

    if 'ei_custom_n' not in st.session_state: st.session_state['ei_custom_n'] = 0
    for i in range(st.session_state['ei_custom_n']):
        c1,c2,c3=st.columns([2,2,1])
        with c1: cn=st.text_input(f"分类#{i+1}", key=f"ei_cn{i}")
        with c2: ca=st.number_input("金额", key=f"ei_ca{i}", step=100.0)
        with c3: cc=st.selectbox("币种",["RMB","USD","THB","MYR"], key=f"ei_cc{i}")
        if cn and ca and ca>0: tr+=ca*R.get(cc,1); items.append({"name":cn,"amount":ca,"currency":cc})
    if st.button("➕ 添加分类"):
        st.session_state['ei_custom_n'] += 1; st.rerun()

    if tr>0: st.info(f"总成本(RMB): ¥{tr:,.0f}")

    if st.button("💾 保存信息", type="primary", use_container_width=True):
        # Validate required fields
        errors = []
        sel_check = st.session_state.get('ei_sel','')
        if not sel_check: errors.append("请选择客户")
        name_check = st.session_state.get('ei_name','')
        if not name_check: errors.append("请填写项目名称")
        amt_check = st.session_state.get('ei_amt') or 0
        if not amt_check or float(amt_check) <= 0: errors.append("请填写确认函/Invoice金额")
        # Execution period is auto-generated from date pickers, skip check
        if errors:
            for e in errors: st.error(e)
            st.stop()

        due = st.session_state.get('ei_due')
        if hasattr(due,'strftime'): due = due.strftime('%Y-%m-%d')
        data = {
            'project_code':st.session_state.get('ei_code',''),
            'project_name':st.session_state.get('ei_name',''),
            'brand_name':st.session_state.get('ei_brand',''),
            'amount':float(st.session_state.get('ei_amt',0) or 0),
            'currency':st.session_state.get('ei_cur','USD'),
            'venue':st.session_state.get('ei_venue',''),
            'execution_period': exec_period_auto,
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

    col_gen, col_skip = st.columns(2)
    with col_gen:
        if st.button("📄 生成确认函", type="primary", use_container_width=True):
            client = get_client_by_id(ed.get('client_id')) or {}
            proj = {'client_short':client.get('short_name',''),'project_code':ed.get('project_code',''),
                    'project_name':ed.get('project_name',''),'brand_name':ed.get('brand_name',''),
                    'venue':ed.get('venue',''),'execution_period':ed.get('execution_period',''),
                    'shooting_date':ed.get('shooting_date',''),'total_posts':ed.get('total_posts',''),
                    'amount':ed.get('amount',0),'application_date':datetime.now().strftime('%b %d, %Y')}
            path = generate_confirmation_letter({'full_name':client.get('full_name',''),'contact':client.get('contact','')}, proj)
            st.session_state['confirmation_path'] = path
            st.session_state['confirmation_proj'] = proj
            st.rerun()
    with col_skip:
        if st.button("⏭️ 跳过（客户自回传）", use_container_width=True,
                     help="POP等客户会自己回传确认函，无需我们生成"):
            get_connection().table("projects").update({"status":"confirmation_sent"}).eq("id",ed['id']).execute()
            st.success("已跳过，直接进入上传确认函阶段。"); st.rerun()


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

        # Split payment
        total_contract = float(ed.get('amount',0))
        inst_total = st.selectbox("分几次付款", [1,2,3,4,5], key="inst_total",
                                  help="全款选1，分两次选2")
        if inst_total > 1:
            inst_cur = st.selectbox("本次是第几次", list(range(1, inst_total+1)), key="inst_cur")
            inst_amt = round(total_contract / inst_total, 2)
            st.info(f"本次金额：**{ed.get('currency','USD')} {inst_amt:,.2f}** | 第{inst_cur}次/共{inst_total}次")
            default_amt = inst_amt
            inv_type_default = f"服务款-第{inst_cur}次款项"
        else:
            inst_cur = 1
            inst_amt = total_contract
            default_amt = total_contract
            inv_type_default = "服务款-全款"

        # 分期设置变化时，自动同步「本次开票金额」= 总额 ÷ 次数（手动改过则保留手动值）
        _prev_inst = st.session_state.get('_prev_inst')
        _cur_inst = (inst_total, inst_cur)
        if _prev_inst != _cur_inst:
            st.session_state['_prev_inst'] = _cur_inst
            st.session_state['inv_amt'] = default_amt

        inv_type = st.selectbox("发票类型",
                               ["服务款-全款","服务款-前款","服务款-中款","服务款-后款","样品费报销","差旅费报销"],
                               index=0, key="inv_type")
        inv_amount = st.number_input("本次开票金额", value=default_amt if default_amt>0 else None,
                                     step=100.0, key="inv_amt",
                                     help=f"合同总额：{ed.get('currency','USD')} {total_contract:,.2f}（改动开票次数会自动重算）")
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
            st.session_state['_inst_total'] = inst_total
            st.session_state['_inst_cur'] = inst_cur
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
                it = st.session_state.get('_inst_total', 1) or 1
                ic = st.session_state.get('_inst_cur', 1) or 1
                get_connection().table("projects").update({
                    "feishu_approved":f_ok, "status":"pending",
                    "amount": float(inv_amt or ed.get('amount',0)),
                    "content_type": inv_type + (f" [{note}]" if note else ""),
                    "installment_total": it,
                    "installment_current": ic,
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
