import os, io, tempfile, pypdf, subprocess
from PIL import Image as PILImg
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.pagesizes import A4
from utils.generate import generate_invoice
from supabase import create_client

sb=create_client('https://iadfdtpjnemswwtnkygj.supabase.co','eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlhZGZkdHBqbmVtc3d3dG5reWdqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODQ3MTA4NzAsImV4cCI6MjEwMDI4Njg3MH0.nWMuVuT80fNKujtl7Cgrojx2uD55Oe8URGLdfo1FxGo')
stamp=PILImg.open('stamp/stamp_hq.png').convert('RGBA')
pw,ph=float(A4[0]),float(A4[1]); sw=pw*0.30; sh=stamp.height*sw/stamp.width
sx=pw-sw-int(pw*0.05); sy=int(ph*0.10)

for code in ['WELL20260801002','WELL20260801003']:
    r=sb.table('projects').select('*').eq('project_code',code).execute(); p=r.data[0]
    c=sb.table('clients').select('*').eq('id',p['client_id']).execute(); client=c.data[0]
    proj={'client_short':client['short_name'],'project_code':p['project_code'],'project_name':p.get('project_name',''),'brand_name':p.get('brand_name',''),'amount':p.get('amount',0),'currency':p.get('currency','USD'),'venue':p.get('venue',''),'execution_period':p.get('execution_period',''),'shooting_date':p.get('shooting_date',''),'total_posts':p.get('total_posts',''),'invoice_date':p.get('created_at'),'due_date':p.get('due_date'),'content_type':'服务款-前款','invoice_project_name':p.get('brand_name','')}
    inv=generate_invoice(client,proj)
    pdf_dir=tempfile.mkdtemp()
    subprocess.run(['/opt/homebrew/bin/soffice','--headless','--convert-to','pdf','--outdir',pdf_dir,inv],capture_output=True,timeout=60)
    pdf_tmp=os.path.join(pdf_dir,os.path.splitext(os.path.basename(inv))[0]+'.pdf')
    buf=io.BytesIO(); cv=canvas.Canvas(buf,pagesize=(pw,ph))
    cv.drawImage(ImageReader(stamp),sx,sy,sw,sh,mask='auto'); cv.save(); buf.seek(0)
    reader=pypdf.PdfReader(pdf_tmp); writer=pypdf.PdfWriter()
    for page in reader.pages: page.merge_page(pypdf.PdfReader(buf).pages[0],over=True); writer.add_page(page)
    out=f'/Users/vincy/Documents/Wellcome/项目/KLT/{p["brand_name"]}/财务/{p["brand_name"]}-前款-stamped.pdf'
    os.makedirs(os.path.dirname(out),exist_ok=True)
    with open(out,'wb') as f: writer.write(f)
    sb.table('projects').update({'stamped_pdf_path':out}).eq('project_code',code).execute()
    os.system(f'open "{out}"')
    print(f'✅ {p["brand_name"]}')
