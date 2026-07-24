"""Finance pages — simplified for older colleagues."""

import streamlit as st
import pandas as pd
from datetime import datetime
import os, io, json, tempfile

from utils.database import (
    get_projects, get_clients, get_client_by_id, get_pending_approvals,
    approve_project, reject_project
)
from utils.receipt_pdf import generate_receipt_pdf
from utils.generate import generate_cash_receipt

STAGE_MAP = {'draft': '草稿', 'pending': '待审核', 'approved': '已开发票', 'rejected': '已驳回'}
CLOSURE_MAP = {'active': '进行中', 'pending_payment': '待收款', 'closed': '已结案'}


def _fmt_date_val(val):
    """Consistent YYYY-MM-DD format."""
    if val is None: return ''
    if hasattr(val, 'strftime'): return val.strftime('%Y-%m-%d')
    return str(val)[:10]


def _fmt_cost_line(cost_json: str) -> str:
    if not cost_json: return ""
    try:
        items = json.loads(cost_json)
        return "、".join(f"{i['name']}({i.get('currency','RMB')}{i.get('amount',0):,.0f})" for i in items)
    except: return cost_json


def _inject_large_font_css():
    st.markdown("""
    <style>
    html, body, [class*="css"] { font-size: 16px !important; }
    div[data-testid="stMetricValue"] { font-size: 28px !important; }
    h1 { font-size: 28px !important; }
    h2 { font-size: 22px !important; }
    h3 { font-size: 18px !important; }
    button { font-size: 16px !important; padding: 10px 14px !important; }
    input, select { font-size: 16px !important; }
    table { font-size: 14px !important; }
    </style>
    """, unsafe_allow_html=True)


def page_overview():
    _inject_large_font_css()
    st.title("📊 项目总览")
    projects = get_projects(limit=500)
    if not projects: st.info("暂无项目"); return

    # Year-month filter
    months = sorted(set(
        f"20{p.get('project_code','')[4:6]}-{p.get('project_code','')[6:8]}"
        for p in projects if len(p.get('project_code','')) >= 8
    ), reverse=True)
    months = ['全部'] + months
    sel_month = st.selectbox("筛选年月", months)
    if sel_month != '全部':
        projects = [p for p in projects
                    if f"20{p.get('project_code','')[4:6]}-{p.get('project_code','')[6:8]}" == sel_month
                    and len(p.get('project_code','')) >= 8]

    # Summary cards
    pending_count = sum(1 for p in projects if p.get('status') == 'pending')
    approved_count = sum(1 for p in projects if p.get('status') == 'approved')
    received_count = sum(1 for p in projects if p.get('payment_received'))
    closed_count = sum(1 for p in projects if p.get('closure_status') == 'closed')
    total_cost = sum(p.get('estimated_cost',0) or 0 for p in projects)
    total_revenue = sum(p.get('amount',0) or 0 for p in projects)
    need_receipt = sum(1 for p in projects if p.get('payment_received') and p.get('status')=='approved')
    c1,c2,c3,c4,c5,c6,c7 = st.columns(7)
    c1.metric("⏳ 待审核", pending_count)
    c2.metric("✅ 已开发票", approved_count)
    c3.metric("💰 已到账", received_count)
    c4.metric("🧾 待开收据", need_receipt)
    c5.metric("🔒 已结案", closed_count)
    c6.metric("💸 总成本", f"¥{total_cost:,.0f}")
    c7.metric("📈 总收入", f"${total_revenue:,.0f}")

    # Quick action: projects needing receipt
    need_rec_projects = [p for p in projects if p.get('payment_received') and p.get('status')=='approved']
    if need_rec_projects:
        st.divider()
        st.subheader("🧾 待开收据项目")
        for p in need_rec_projects[:5]:
            c1,c2 = st.columns([4,1])
            with c1:
                st.write(f"**{p.get('brand_name','')}** — {p.get('project_code','')} | {p.get('currency','USD')} {p.get('amount',0):,.0f}")
            with c2:
                if st.button("🧾 开收据", key=f"rec_{p['id']}", use_container_width=True):
                    st.session_state['receipt_project_id'] = p['id']
                    st.session_state.page = "receipt"
                    st.rerun()
    st.divider()

    # === Excel download ===
    if st.button("📥 下载成本明细表", use_container_width=True):
        _export_excel(projects)

    # === Table with merged cells ===
    st.subheader("项目明细")
    _render_table(projects)


def _render_table(projects):
    """Render HTML table with merged cells for same-project rows."""
    rows_html = ""
    for p in projects:
        stage = STAGE_MAP.get(p.get('status', ''), p.get('status', '?'))
        closure = CLOSURE_MAP.get(p.get('closure_status', 'active'), '')
        paid = '✅' if p.get('payment_received') else ''
        feishu = '是' if p.get('feishu_approved') else '否'
        total_cost = p.get('estimated_cost',0) or 0
        exec_period = p.get('execution_period','') or ''
        exp_pay = str(p.get('expected_payment_date','') or '')[:10]
        # Extract year-month: handle both formats
        # WELL260801001 (13 chars) or WELL20260717012 (15 chars)
        code = p.get('project_code','')
        if len(code) >= 15:  # old format WELL20260717012
            year_month = f"{code[4:8]}-{code[8:10]}"
        elif len(code) >= 8:  # new format WELL260801001
            year_month = f"20{code[4:6]}-{code[6:8]}"
        else:
            year_month = ''

        try: cost_items = json.loads(p.get('cost_breakdown','') or '[]')
        except: cost_items = []

        if cost_items:
            n = len(cost_items)
            for idx, item in enumerate(cost_items):
                rows_html += "<tr>"
                if idx == 0:
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{stage}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{year_month}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{code}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{p.get('brand_name','')}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{p.get('client_short','')}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{p.get('currency','USD')} {p.get('amount',0):,.0f}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{exec_period}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{exp_pay}</td>"
                rows_html += f"<td>{item.get('name','')}</td>"
                rows_html += f"<td style='text-align:right'>{item.get('amount',0):,.0f}</td>"
                if idx == 0:
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{total_cost:,.0f}</td>"
                if idx == 0:
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{feishu}</td>"
                if idx == 0:
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{paid}</td>"
                    rows_html += f"<td rowspan='{n}' style='text-align:center;vertical-align:middle'>{closure}</td>"
                rows_html += "</tr>"
        else:
            rows_html += "<tr>"
            rows_html += f"<td style='text-align:center'>{stage}</td>"
            rows_html += f"<td style='text-align:center'>{year_month}</td>"
            rows_html += f"<td style='text-align:center'>{code}</td>"
            rows_html += f"<td style='text-align:center'>{p.get('brand_name','')}</td>"
            rows_html += f"<td style='text-align:center'>{p.get('client_short','')}</td>"
            rows_html += f"<td style='text-align:center'>{p.get('currency','USD')} {p.get('amount',0):,.0f}</td>"
            rows_html += f"<td style='text-align:center'>{exec_period}</td>"
            rows_html += f"<td style='text-align:center'>{exp_pay}</td>"
            rows_html += f"<td></td><td style='text-align:right'>{total_cost:,.0f}</td>"
            rows_html += f"<td style='text-align:center'>{total_cost:,.0f}</td>"
            rows_html += f"<td style='text-align:center'>{feishu}</td>"
            rows_html += f"<td style='text-align:center'>{paid}</td>"
            rows_html += f"<td style='text-align:center'>{closure}</td>"
            rows_html += "</tr>"

    html = f"""
    <style>
    table {{ border-collapse: collapse; width: 100%; font-size: 14px; font-family: -apple-system, sans-serif; }}
    th, td {{ border: 1px solid #ddd; padding: 8px 8px; font-size: 14px; }}
    th {{ background: #f5f5f5; text-align: center; font-size: 14px; }}
    tr:nth-child(even) {{ background: #fafafa; }}
    </style>
    <table>
    <tr><th>阶段</th><th>年月</th><th>编号</th><th>品牌</th><th>客户</th><th>金额</th>
    <th>执行周期</th><th>预计付款</th><th>成本细项</th><th>成本金额</th><th>总成本</th><th>立项</th><th>到账</th><th>结案</th></tr>
    {rows_html}
    </table>
    """
    st.markdown(html, unsafe_allow_html=True)

    # Quick action: mark as paid for approved but unpaid projects
    st.divider()
    unpaid = [p for p in projects if p.get('status')=='approved' and not p.get('payment_received')]
    if unpaid:
        st.subheader("💰 到账操作")
        cols = st.columns(min(len(unpaid), 5))
        for i, p in enumerate(unpaid[:10]):
            with cols[i % 5]:
                with st.container(border=True):
                    st.caption(f"**{p.get('brand_name','')}**")
                    st.caption(f"{p.get('project_code','')}")
                    if st.button("✅ 标记到账", key=f"paid_quick_{p['id']}", use_container_width=True):
                        from utils.database import get_connection
                        get_connection().table("projects").update({
                            "payment_received": True,
                            "received_date": datetime.now().strftime('%Y-%m-%d'),
                        }).eq("id", p['id']).execute()
                        st.rerun()


def _export_excel(projects):
    import openpyxl as xl
    from openpyxl.styles import Font, Alignment, Border, Side
    wb = xl.Workbook(); ws = wb.active; ws.title = "成本明细"
    hs = ['项目编号','品牌','客户','阶段','金额','成本细项','成本金额','币种','到账','结案']
    thin = Side(style='thin')
    for c,h in enumerate(hs,1):
        cell=ws.cell(1,c,h); cell.font=Font(bold=True); cell.alignment=Alignment(horizontal='center',vertical='center')
        cell.border=Border(bottom=thin)
    row=2
    for p in projects:
        stage=STAGE_MAP.get(p.get('status',''),'')
        closure=CLOSURE_MAP.get(p.get('closure_status',''),'')
        paid='是' if p.get('payment_received') else '否'
        try: items=json.loads(p.get('cost_breakdown','') or '[]')
        except: items=[]
        start_row = row
        if items:
            for it in items:
                ws.cell(row,6,it.get('name','')); ws.cell(row,7,it.get('amount',0))
                ws.cell(row,8,it.get('currency','RMB'))
                row+=1
        else:
            ws.cell(row,7,p.get('estimated_cost',0)); ws.cell(row,8,'RMB')
            row+=1
        end_row = row - 1

        # Write merged project info and merge cells if multiple rows
        ws.cell(start_row,1,p.get('project_code','')); ws.cell(start_row,2,p.get('brand_name',''))
        ws.cell(start_row,3,p.get('client_short','')); ws.cell(start_row,4,stage)
        ws.cell(start_row,5,f"{p.get('currency','USD')} {p.get('amount',0):,.0f}")
        ws.cell(start_row,9,paid); ws.cell(start_row,10,closure)

        # Center everything
        for c in range(1,11):
            ws.cell(start_row,c).alignment=Alignment(horizontal='center',vertical='center')

        # Merge cells if project has multiple cost rows
        if end_row > start_row:
            for c in [1,2,3,4,5,9,10]:  # columns to merge
                ws.merge_cells(start_row=start_row, start_column=c, end_row=end_row, end_column=c)

        # Borders
        for r in range(start_row, end_row+1):
            for c in range(1,11):
                ws.cell(r,c).border=Border(bottom=Side(style='hair'))

    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    st.download_button("📥 下载 Excel", buf, file_name="项目成本明细.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def page_approval():
    _inject_large_font_css()
    st.title("⏳ 待审核")
    pending = get_pending_approvals()
    user=st.session_state.user

    if pending:
        st.subheader(f"共 {len(pending)} 个项目等你审核")
        for p in pending:
            with st.container(border=True):
                st.markdown(f"### {p.get('brand_name','')} — {p.get('project_name','')}")
                feishu_badge = "✅ 飞书已立项" if p.get('feishu_approved') else "⚠️ 未确认飞书立项"
                col_info,col_btn=st.columns([3,2])
                with col_info:
                    st.write(f"**{p.get('client_short','')}** | {p.get('currency','USD')} **{p.get('amount',0):,.2f}** | {feishu_badge}")
                    if p.get('estimated_cost'):
                        cd=_fmt_cost_line(p.get('cost_breakdown','') or '')
                        st.caption(f"预估成本: {p.get('estimated_cost',0):,.0f}"+(f"（{cd}）" if cd else ""))
                    st.caption(f"提交: {(p.get('created_at','') or '')[:10]}")
                with col_btn:
                    # Show stamped confirmation for download
                    if p.get('stamped_confirmation'):
                        with st.expander("📎 盖章确认函"):
                            import base64
                            st.download_button("📥 下载盖章确认函",
                                              base64.b64decode(p['stamped_confirmation']),
                                              file_name=f"{p.get('brand_name','')}-盖章确认函.pdf",
                                              mime="application/pdf")
                            try: st.image(base64.b64decode(p['stamped_confirmation']))
                            except: pass
                    with st.expander("📄 预览Invoice", expanded=True):
                        _show_invoice_preview(p)
                    _gen_invoice_dl(p)
                    if st.button("✅ 通过", key=f"ok_{p['id']}", use_container_width=True, type="primary"):
                        with st.spinner("生成盖章PDF..."):
                            try:
                                _regen_and_approve(p, user['id'])
                                st.success("已通过！")
                                code = p.get('project_code','')
                                month_str = code[6:8] if len(code)>=8 else ''
                                MONTHS = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                                          '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
                                m = MONTHS.get(month_str,'')
                                subj = f"Invoice for {p.get('brand_name','')} {m} Campaign / {p.get('project_code','')}"
                                body = (f"Dear all,\n\n"
                                        f"Please find attached the invoice for {p.get('brand_name','')} {p.get('project_name','')} Project.\n\n"
                                        f"Amount: {p.get('currency','USD')} {p.get('amount',0):,.2f}\n"
                                        f"Invoice No: {p.get('project_code','')}\n\n"
                                        f"Please review at your convenience and let us know if you have any questions.\n"
                                        f"Thank you for your kind attention.")
                                st.session_state['just_approved'] = {
                                    'name': f"{p.get('brand_name','')}-{m}-invoice.pdf",
                                    'path': tempfile.mktemp(suffix='.pdf'),
                                    'brand': p.get('brand_name',''),
                                    'code': p.get('project_code',''),
                                    'email_subj': subj, 'email_body': body,
                                }
                                _gen_stamped_only(p, st.session_state['just_approved']['path'])
                                st.rerun()
                            except Exception as e: st.error(f"失败: {e}")
                    if st.button("❌ 驳回", key=f"no_{p['id']}", use_container_width=True):
                        reject_project(p['id'], user['id']); st.warning("已驳回"); st.rerun()
    else:
        st.success("✅ 没有需要审核的项目")

    # Show just-approved banner with download + email
    if 'just_approved' in st.session_state and st.session_state.get('just_approved'):
        ja = st.session_state['just_approved']
        st.divider()
        st.success(f"✅ 审核通过！{ja['brand']} ({ja['code']})")
        col_dl, col_email = st.columns([1, 2])
        with col_dl:
            if os.path.exists(ja['path']):
                with open(ja['path'], "rb") as f:
                    st.download_button("📥 下载盖章发票PDF", f, file_name=ja['name'],
                                      key="dl_ja", use_container_width=True)
        with col_email:
            with st.expander("📧 邮件文案（发送给客户）", expanded=True):
                st.text_input("主题", value=ja.get('email_subj',''), key="ja_subj")
                st.text_area("正文", value=ja.get('email_body',''), height=180, key="ja_body")
        if st.button("✅ 已处理"):
            st.session_state['just_approved'] = None; st.rerun()

    # Approved projects with download
    st.divider()
    all_p = get_projects(limit=100)
    approved_list = [p for p in all_p if p.get('status')=='approved']
    if approved_list:
        st.subheader(f"✅ 已通过项目（{len(approved_list)}个，可下载盖章PDF）")
        for p in approved_list[:20]:
            col1, col2 = st.columns([3,1])
            with col1:
                st.write(f"**{p.get('brand_name','')}** — {p.get('project_code','')}")
            with col2:
                try:
                    stamped_path = tempfile.mktemp(suffix='.pdf')
                    _gen_stamped_only(p, stamped_path)
                    code = p.get('project_code','')
                    month_str = code[6:8] if len(code)>=8 else ''
                    MONTH_NAMES = {'01':'Jan','02':'Feb','03':'Mar','04':'Apr','05':'May','06':'Jun',
                                   '07':'Jul','08':'Aug','09':'Sep','10':'Oct','11':'Nov','12':'Dec'}
                    month_name = MONTH_NAMES.get(month_str, '')
                    fname = f"{p.get('brand_name','')}-{month_name}-invoice.pdf"
                    with open(stamped_path, 'rb') as f:
                        st.download_button("📥 盖章发票PDF", f, file_name=fname,
                                          key=f"stamped_{p['id']}", use_container_width=True)
                except:
                    st.caption("重新生成失败")
    else:
        st.info("暂无已通过的项目")


def _show_invoice_preview(p):
    """Show a preview of invoice content inline."""
    client = get_client_by_id(p.get('client_id')) or {}
    cur = p.get('currency','USD')
    amt = p.get('amount',0)

    st.markdown(f"""
    <div style="border:1px solid #ddd;border-radius:8px;padding:12px;margin:8px 0;background:#fafafa">
    <b>📄 Invoice 预览</b><br>
    <table style="width:100%;font-size:13px;border-collapse:collapse">
    <tr><td style="padding:3px 8px;color:#888">项目</td><td>{p.get('project_name','')}</td></tr>
    <tr><td style="padding:3px 8px;color:#888">编号</td><td>{p.get('project_code','')}</td></tr>
    <tr><td style="padding:3px 8px;color:#888">客户</td><td>{client.get('full_name','')}</td></tr>
    <tr><td style="padding:3px 8px;color:#888">金额</td><td><b>{cur} {amt:,.2f}</b></td></tr>
    <tr><td style="padding:3px 8px;color:#888">到期日</td><td>{str(p.get('due_date',''))[:10]}</td></tr>
    </table>
    </div>
    """, unsafe_allow_html=True)


def _gen_invoice_dl(p):
    """Generate invoice download button for approval preview."""
    try:
        import openpyxl as xl
        from utils.generate import TEMPLATE_DIR as TD
        client=get_client_by_id(p.get('client_id')) or {}
        if not client: return
        wb=xl.load_workbook(os.path.join(TD,"Invoice-Template.xlsx")); ws=wb.active
        ws['C3']=f"{p.get('brand_name','')} – {p.get('total_posts','')} CONTENT PACKAGE"
        ws['C7']=client.get('full_name',''); ws['C8']=client.get('address','')
        ws['C9']=client.get('contact',''); ws['C10']=client.get('phone') or ''
        ws['C11']=client.get('email') or ''
        ws['E8']=p.get('project_code',''); ws['E11']=p.get('project_code','')
        ws['D15']=p.get('amount',0); ws['E15']=1; ws['G15']=p.get('amount',0)
        ws['E9']=_fmt_date_val(p.get('invoice_date'))
        ws['E10']=_fmt_date_val(p.get('due_date'))
        _write_c18(ws, p.get('amount',0), p.get('currency','USD'))
        buf=io.BytesIO(); wb.save(buf); buf.seek(0)
        st.download_button("📥 下载Invoice", buf, file_name=f"{p.get('brand_name','')}-invoice.xlsx",
                          key=f"invdl_{p['id']}", use_container_width=True,
                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except: pass


def _write_c18(ws, amount, currency):
    """Write C18 with Chinese uppercase + English amount."""
    from utils.generate import _amount_chinese
    cl = "RMB" if currency=="RMB" else "USD"
    cn = _amount_chinese(amount, currency)
    ws['C18'] = f"總付款金額為{cn}\nFull payment of {cl} {amount:,.2f}"


def _gen_stamped_only(p, output_path):
    """Generate stamped PDF without approving (for re-download)."""
    import openpyxl as xl
    from utils.pdf_utils import generate_stamped_pdf
    from utils.generate import TEMPLATE_DIR as TD
    client=get_client_by_id(p.get('client_id')) or {}
    wb=xl.load_workbook(os.path.join(TD,"Invoice-Template.xlsx")); ws=wb.active
    ws['C3']=f"{p.get('brand_name','')} – {p.get('total_posts','')} CONTENT PACKAGE"
    ws['C7']=client.get('full_name',''); ws['C8']=client.get('address','')
    ws['C9']=client.get('contact',''); ws['C10']=client.get('phone') or ''
    ws['C11']=client.get('email') or ''; ws['E8']=p.get('project_code','')
    ws['E9']=_fmt_date_val(p.get('invoice_date')); ws['E10']=_fmt_date_val(p.get('due_date'))
    ws['E11']=p.get('project_code',''); ws['D15']=p.get('amount',0); ws['E15']=1; ws['G15']=p.get('amount',0)
    _write_c18(ws, p.get('amount',0), p.get('currency','USD'))
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as f: f.write(buf.read()); xlsx_path=f.name
    generate_stamped_pdf(xlsx_path, output_path)
    try: os.unlink(xlsx_path)
    except: pass


def _regen_and_approve(p, user_id):
    """Regenerate stamped invoice PDF and approve."""
    import openpyxl as xl
    from utils.pdf_utils import generate_stamped_pdf
    from utils.generate import TEMPLATE_DIR as TD
    client=get_client_by_id(p.get('client_id')) or {}
    wb=xl.load_workbook(os.path.join(TD,"Invoice-Template.xlsx")); ws=wb.active
    ws['C3']=f"{p.get('brand_name','')} – {p.get('total_posts','')} CONTENT PACKAGE"
    ws['C7']=client.get('full_name',''); ws['C8']=client.get('address','')
    ws['C9']=client.get('contact','')
    ws['C10']=client.get('phone') if client.get('phone') and client['phone']!='（待补充）' else None
    ws['C11']=client.get('email') if client.get('email') and client['email']!='（待补充）' else None
    ws['E8']=p.get('project_code',''); ws['E9']=_fmt_date_val(p.get('invoice_date'))
    ws['E10']=_fmt_date_val(p.get('due_date'))
    ws['E11']=p.get('project_code',''); ws['D15']=p.get('amount',0)
    ws['E15']=1; ws['G15']=p.get('amount',0)
    _write_c18(ws, p.get('amount',0), p.get('currency','USD'))
    buf=io.BytesIO(); wb.save(buf); buf.seek(0)
    xlsx_path=tempfile.mktemp(suffix='.xlsx')
    with open(xlsx_path,'wb') as f: f.write(buf.read())
    stamped_path=tempfile.mktemp(suffix='.pdf')
    generate_stamped_pdf(xlsx_path, stamped_path)
    approve_project(p['id'], user_id, stamped_path)
    try: os.unlink(xlsx_path)
    except: pass
