"""GovIntel policy and benefits modules. Synthetic demonstrations only."""
import json, re, secrets, os
from io import BytesIO
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from . import db, retrieval, security, llm, config
from .textutil import tokens
router=APIRouter(prefix='/api/intel')
J=json.dumps
L=json.loads
ALLOWED={'public':['Public'],'staff':['Public','Internal'],'admin':['Public','Internal','Restricted']}

def ocr_image(img):
    import pytesseract
    if os.getenv('TESSERACT_CMD'): pytesseract.pytesseract.tesseract_cmd=os.getenv('TESSERACT_CMD')
    elif os.name=='nt' and Path(r'C:\Program Files\Tesseract-OCR\tesseract.exe').exists(): pytesseract.pytesseract.tesseract_cmd=r'C:\Program Files\Tesseract-OCR\tesseract.exe'
    if img.width*img.height>20_000_000: raise ValueError('Image exceeds pixel limit')
    data=pytesseract.image_to_data(img,output_type=pytesseract.Output.DICT,timeout=25)
    values=[float(c) for c,t in zip(data['conf'],data['text']) if t.strip() and float(c)>=0]
    lines={}
    for i,t in enumerate(data['text']):
        if t.strip(): lines.setdefault(tuple(data[k][i] for k in ('block_num','par_num','line_num')),[]).append(t)
    return '\n'.join(' '.join(v) for v in lines.values()), round(sum(values)/len(values)/100,2) if values else 0

def fail(msg,code=422): raise HTTPException(code,msg)
def doc_access(i,role):
    d=db.one('SELECT * FROM documents WHERE id=?',(i,))
    if not d or d['classification'] not in ALLOWED[role]: fail('Source not available',404)
    return d

def seed_demo():
    if db.one('SELECT id FROM programmes LIMIT 1'): return
    specs=[('Housing Support','Demo housing subsidy','housing',3500,18),('Study Bursary','Demo education assistance','bursary',6000,18),('Social Support','Demo social benefit','social',2500,18)]
    for name,desc,key,income,age in specs:
        for ver,limit,status in [('1.0',income-500,'Superseded'),('2.0',income,'Active')]:
            text=f'# Clause 1 — Scope\n{name} is a fictional programme for demonstration only. No real eligibility decisions are made.\n\n# Clause 2 — Age\nApplicants must be at least {age} years old.\n\n# Clause 3 — Income\nThe maximum monthly income is R{limit}. The income declared must match the payslip.\n\n# Clause 4 — Documents\nAn identity document, a payslip and proof of residence are required.\n\n# Clause 5 — Decision\nAn authorised official must review every recommendation and record reasons. No automatic declines.'
            d=retrieval.ingest_document(key+'-'+ver+'.md',text.encode(),{'title':name+' Eligibility Policy','department':'Demo Social Services','version':ver,'classification':'Public','repository':'SharePoint (simulated)','policy_key':key,'status':status,'review_date':'2026-11-26'})
        pid=db.execute('INSERT INTO programmes(name,description,policy_key) VALUES(?,?,?)',(name,desc,key))
        db.execute('INSERT INTO rules(programme_id,version,policy_document,criteria,actor) VALUES(?,?,?,?,?)',(pid,1,d['id'],J({'min_age':age,'max_income':income,'required':['Identity','Payslip','Residence']}),'system'))
    for title,cl,txt in [('Operations Review Handbook','Internal','# Section 7 — Review queue\nThe demo operations review queue is checked every weekday. Supervisors record review findings in the internal register.'),('Restricted Pilot Control Note','Restricted','# Section 9 — Pilot code\nThe fictional internal pilot verification code is ORCHID-47. Only authorised administrators may view this demo document.')]:
        retrieval.ingest_document(title+'.md',txt.encode(),{'title':title,'classification':cl,'repository':'DMS (simulated)','version':'1.0','review_date':'2026-11-26'})
    for i,(name,income,pay,age) in enumerate([('Demo Applicant A',2800,2800,30),('Demo Applicant B',2900,4200,28),('Demo Applicant C',4800,4800,45),('Demo Applicant D',2000,2000,22)]):
        a=db.execute('INSERT INTO applications(reference,programme_id,applicant,declared) VALUES(?,?,?,?)',(f'GI-DEMO-00{i+1}',1,name,J({'age':age,'income':income})))
        for kind,fields in [('Identity',{'age':age}),('Payslip',{'income':pay}),('Residence',{'residence':'Demo district'})]:
            if i==3 and kind=='Residence': continue
            db.execute('INSERT INTO evidence(application_id,kind,filename,text,fields,confidence) VALUES(?,?,?,?,?,?)',(a,kind,'Synthetic seed',J(fields),J(fields),1.0))
        assess(a,'system')

class Question(BaseModel):
    question:str=Field(min_length=1,max_length=1000)
    context:str=Field(default='',max_length=1000)
    historical:bool=False
    language:str='en'

@router.post('/policy/chat')
def policy_chat(body:Question,user=Depends(security.require_staff)):
    q=body.question.strip(); role=user['role']
    query=(body.context+' '+q).strip() if body.context and len(tokens(q))<6 else q
    # Scope explicit programme questions before retrieval to avoid mixing thresholds.
    matches=[p for p in db.rows('SELECT * FROM programmes') if p['name'].lower() in query.lower()]
    hits,ev,mode=retrieval.search(query,role=role,historical=body.historical,policy_key=matches[0]['policy_key'] if len(matches)==1 else None)
    if retrieval.looks_like_injection(q) or not hits or ev<config.MIN_EVIDENCE:
        db.audit(user['username'],'policy.refused',detail='Insufficient authorised evidence or unsafe instruction')
        return {'answer':"I don't have enough authorised, verified information to answer. Ask the responsible policy owner or consult the document library.",'sources':[],'mode':'Refusal','answered':False}
    answer=llm.generate(q if query==q else query,hits,body.language) if body.language in llm.LANG_NAMES else None
    mode_name='Ollama' if answer else 'Extractive fallback'
    answer=answer or llm.extractive_answer(query,hits)
    if not answer: return {'answer':'No supported answer. Contact the policy owner.','sources':[],'mode':'Refusal','answered':False}
    src=[{'id':p['document_id'],'title':p['title'],'section':p['section'],'page':p['page_number'],'version':p['version'],'status':p['status'],'repository':p['repository'],'excerpt':p['text']} for p in hits]
    db.audit(user['username'],'policy.answered',detail=J({'source_ids':[s['id'] for s in src],'mode':mode_name}))
    return {'answer':answer,'sources':src,'mode':mode_name,'answered':True,'warning':'Historical or draft material included. Verify current policy.' if any(s['status']!='Active' for s in src) else 'Synthetic demo sources; verify with the policy owner.'}

@router.get('/source/{i}')
def source(i:int,user=Depends(security.require_staff)):
    d=doc_access(i,user['role']); pages=db.rows('SELECT page,text FROM source_pages WHERE document_id=? ORDER BY page',(i,))
    if not pages: pages=db.rows('SELECT page_number page,text FROM chunks WHERE document_id=? ORDER BY id',(i,))
    return {'document':d,'pages':pages}

@router.get('/public-source/{i}')
def public_source(i:int):
    d=doc_access(i,'public')
    if d['status']!='Active': fail('Source not available',404)
    return {'document':d,'pages':db.rows('SELECT page,text FROM source_pages WHERE document_id=? ORDER BY page',(i,))}

@router.get('/programmes')
def programmes(user=Depends(security.require_staff)):
    out=db.rows('SELECT * FROM programmes')
    for p in out:
        p['rule']=db.one('SELECT * FROM rules WHERE programme_id=? ORDER BY version DESC LIMIT 1',(p['id'],)); p['rule']['criteria']=L(p['rule']['criteria'])
    return out

class Rule(BaseModel):
    min_age:int=Field(ge=0,le=120)
    max_income:float=Field(ge=0,le=10000000)
    required:list[str]
    policy_document:int
@router.post('/programmes/{i}/rules')
def save_rules(i:int,body:Rule,user=Depends(security.require_admin)):
    p=db.one('SELECT * FROM programmes WHERE id=?',(i,)); d=doc_access(body.policy_document,'admin')
    if not p or d['policy_key']!=p['policy_key'] or d['status']!='Active' or d['classification']=='Restricted': fail('Select an active matching public/internal policy')
    if not set(body.required)<=set(['Identity','Payslip','Residence']) or not {'Identity','Payslip','Residence'}<=set(body.required): fail('All three verification types are required in this demo')
    last=db.one('SELECT max(version) v FROM rules WHERE programme_id=?',(i,))['v'] or 0
    rid=db.execute('INSERT INTO rules(programme_id,version,policy_document,criteria,actor) VALUES(?,?,?,?,?)',(i,last+1,body.policy_document,J(body.model_dump(exclude={'policy_document'})),user['username']))
    db.audit(user['username'],'rules.version_created','rule',rid,J(body.model_dump())); return {'id':rid,'version':last+1}

class Application(BaseModel):
    applicant:str=Field(min_length=2,max_length=80)
    programme_id:int
    age:int=Field(ge=0,le=120)
    income:float=Field(ge=0,le=10000000)
@router.post('/applications')
def new_app(body:Application,user=Depends(security.require_staff)):
    if not db.one('SELECT id FROM programmes WHERE id=?',(body.programme_id,)): fail('Programme not found')
    ref='GI-'+secrets.token_hex(4).upper(); a=db.execute('INSERT INTO applications(reference,programme_id,applicant,declared) VALUES(?,?,?,?)',(ref,body.programme_id,body.applicant,J({'age':body.age,'income':body.income})))
    db.audit(user['username'],'application.created','application',a,ref); return {'id':a,'reference':ref}

def get_app(i):
    a=db.one('SELECT a.*,p.name programme FROM applications a JOIN programmes p ON p.id=a.programme_id WHERE a.id=?',(i,))
    if not a: fail('Application not found',404)
    a['declared']=L(a['declared']); return a
@router.get('/applications')
def apps(user=Depends(security.require_staff)):
    return db.rows('SELECT a.id,a.reference,a.applicant,a.status,p.name programme,(SELECT recommendation FROM assessments WHERE application_id=a.id ORDER BY id DESC LIMIT 1) recommendation FROM applications a JOIN programmes p ON p.id=a.programme_id ORDER BY a.id DESC')
@router.get('/applications/{i}')
def detail(i:int,user=Depends(security.require_staff)):
    a=get_app(i); a['evidence']=db.rows('SELECT * FROM evidence WHERE application_id=? ORDER BY id DESC',(i,)); a['assessments']=db.rows('SELECT a.*,r.version rule_version,r.policy_document,d.version policy_version FROM assessments a JOIN rules r ON r.id=a.rule_id JOIN documents d ON d.id=r.policy_document WHERE application_id=? ORDER BY a.id DESC',(i,)); a['decisions']=db.rows('SELECT * FROM decisions WHERE application_id=? ORDER BY id DESC',(i,))
    for e in a['evidence']: e['fields']=L(e['fields'])
    for s in a['assessments']: s['results']=L(s['results']); s['snapshot']=L(s['snapshot'])
    return a

@router.post('/applications/{i}/evidence')
async def upload_evidence(i:int,kind:str=Form(...),file:UploadFile=File(...),user=Depends(security.require_staff)):
    a=get_app(i)
    if a['status'] in ('Approved','Declined'): fail('Final decision already recorded',409)
    if kind not in ('Identity','Payslip','Residence'): fail('Unsupported evidence type')
    raw=await file.read(config.MAX_UPLOAD_BYTES+1)
    if len(raw)>config.MAX_UPLOAD_BYTES: fail('File too large',413)
    ext=Path(file.filename or '').suffix.lower(); conf=1.0
    try:
        if ext in ('.png','.jpg','.jpeg'):
            from PIL import Image
            text,conf=ocr_image(Image.open(BytesIO(raw)))
        elif ext=='.pdf':
            import fitz
            from PIL import Image
            parts=[]; scores=[]
            with fitz.open(stream=raw,filetype='pdf') as pdf:
                if len(pdf)>10: raise ValueError('Maximum 10 pages')
                for pg in pdf:
                    t=pg.get_text().strip()
                    if not t:
                        pix=pg.get_pixmap(matrix=fitz.Matrix(2,2),alpha=False); t,c=ocr_image(Image.frombytes('RGB',(pix.width,pix.height),pix.samples)); scores.append(c)
                    parts.append(t)
            text='\n'.join(parts); conf=min(scores) if scores else 1
        elif ext=='.txt': text=raw.decode('utf-8')
        else: fail('Use PDF, PNG, JPG or TXT')
    except HTTPException: raise
    except Exception as exc: fail('Extraction failed; check Tesseract installation and file: '+str(exc)[:200])
    if not text.strip(): fail('No text extracted')
    fields={}; pattern={'Identity':('age',r'\bage\s*[:=]?\s*(\d{1,3})'),'Payslip':('income',r'(?:monthly income|gross pay|monthly salary)\s*[:=]?\s*R?\s*([\d,]+(?:\.\d{1,2})?)'),'Residence':('residence',r'(?:address|residence)\s*[:=]\s*([^\n]+)')}[kind]
    m=re.search(pattern[1],text,re.I)
    if m: fields[pattern[0]]=m.group(1).strip() if kind=='Residence' else float(m.group(1).replace(',',''))
    eid=db.execute('INSERT INTO evidence(application_id,kind,filename,text,fields,confidence) VALUES(?,?,?,?,?,?)',(i,kind,Path(file.filename).name[:100],text[:12000],J(fields),conf)); db.execute("UPDATE applications SET status='Submitted' WHERE id=?",(i,)); db.audit(user['username'],'evidence.extracted','application',i,J({'evidence_id':eid,'fields':fields,'confidence':conf})); return {'id':eid,'fields':fields,'confidence':conf,'text':text[:12000]}

def assess(i,actor):
    a=get_app(i)
    if a['status'] in ('Approved','Declined'): fail('Final decision already recorded',409)
    r=db.one('SELECT r.*,d.status policy_status,d.version policy_version FROM rules r JOIN documents d ON d.id=r.policy_document WHERE programme_id=? ORDER BY r.version DESC LIMIT 1',(a['programme_id'],)); c=L(r['criteria']); ev={}
    for e in db.rows('SELECT * FROM evidence WHERE application_id=? ORDER BY id',(i,)): e['fields']=L(e['fields']); ev[e['kind']]=e
    results=[]
    def add(rule,clause,outcome,detail,e=None): results.append({'rule':rule,'clause':clause,'outcome':outcome,'detail':detail,'evidence_id':e['id'] if e else None})
    for k in c['required']:
        e=ev.get(k); add(k+' document','Clause 4','Pass' if e and e['fields'] and e['confidence']>=.7 else 'Review','Readable evidence available' if e and e['fields'] and e['confidence']>=.7 else 'Missing or uncertain evidence',e)
    for k,field,limit,op,clause in [('Identity','age',c['min_age'],lambda x,y:x>=y,'Clause 2'),('Payslip','income',c['max_income'],lambda x,y:x<=y,'Clause 3')]:
        e=ev.get(k); val=e['fields'].get(field) if e else None; declared=a['declared'][field]
        outcome='Review' if val is None or e['confidence']<.7 or abs(val-declared)>.01 else ('Pass' if op(val,limit) else 'Fail')
        add(field.title()+' threshold',clause,outcome,f'Declared: {declared}; extracted: {val}; policy limit: {limit}. '+('Verify missing, low-confidence or inconsistent data.' if outcome=='Review' else 'Rule evaluated against extracted evidence.'),e)
    if r['policy_status']!='Active': add('Policy currency','Policy metadata','Review','Rule references a non-current policy')
    rec='Needs review' if any(x['outcome']=='Review' for x in results) else ('Not eligible' if any(x['outcome']=='Fail' for x in results) else 'Likely eligible')
    conf=round(min([ev[k]['confidence'] if k in ev else 0 for k in c['required']]+[1])*sum(x['outcome']!='Review' for x in results)/len(results),2)
    sid=db.execute('INSERT INTO assessments(application_id,rule_id,recommendation,confidence,results,snapshot) VALUES(?,?,?,?,?,?)',(i,r['id'],rec,conf,J(results),J({'declared':a['declared'],'evidence':ev,'criteria':c,'policy_version':r['policy_version']})))
    db.execute("UPDATE applications SET status='Awaiting decision' WHERE id=?",(i,)); db.audit(actor,'assessment.completed','application',i,J({'assessment_id':sid,'rule_id':r['id'],'recommendation':rec,'results':results})); return {'id':sid,'recommendation':rec,'confidence':conf,'results':results}
@router.post('/applications/{i}/assess')
def run_assessment(i:int,user=Depends(security.require_staff)): return assess(i,user['username'])
class Decision(BaseModel):
    decision:str
    reason:str=Field(min_length=8,max_length=1000)
@router.post('/applications/{i}/decision')
def decide(i:int,body:Decision,user=Depends(security.require_staff)):
    a=get_app(i)
    if a['status']!='Awaiting decision': fail('Run a fresh assessment first',409)
    if body.decision not in ('Approved','Declined','More information required') or len(body.reason.strip())<8: fail('A valid human decision and reason are required')
    s=db.one('SELECT * FROM assessments WHERE application_id=? ORDER BY id DESC LIMIT 1',(i,))
    with db.conn() as con:
        updated=con.execute("UPDATE applications SET status=? WHERE id=? AND status='Awaiting decision'",(body.decision,i))
        if not updated.rowcount: fail('Application already decided',409)
        did=con.execute('INSERT INTO decisions(application_id,assessment_id,decision,reason,actor) VALUES(?,?,?,?,?)',(i,s['id'],body.decision,body.reason.strip(),user['username'])).lastrowid
        con.execute('INSERT INTO audit_events(actor,action,record_type,record_id,detail) VALUES(?,?,?,?,?)',(user['username'],'decision.recorded','application',str(i),J({'decision_id':did,'decision':body.decision,'reason':body.reason.strip(),'recommendation':s['recommendation']})))
    return {'id':did,'status':body.decision}
@router.get('/users')
def users(user=Depends(security.require_admin)): return db.rows('SELECT username,display_name,role,created_at FROM users')
@router.get('/overview')
def overview(user=Depends(security.require_staff)):
    return {'applications':db.one('SELECT count(*) n FROM applications')['n'],'pending':db.one("SELECT count(*) n FROM applications WHERE status NOT IN ('Approved','Declined')")['n'],'documents':db.one("SELECT count(*) n FROM documents WHERE classification!='Restricted' OR ?='admin'",(user['role'],))['n'],'enquiries':db.one('SELECT count(*) n FROM enquiries')['n'],'recommendations':db.rows('SELECT recommendation,count(*) n FROM assessments WHERE id IN (SELECT max(id) FROM assessments GROUP BY application_id) GROUP BY recommendation')}

class Metadata(BaseModel):
    status:str
    classification:str
    owner:str=Field(max_length=120)
@router.patch('/documents/{i}')
def metadata(i:int,body:Metadata,user=Depends(security.require_admin)):
    old=doc_access(i,'admin')
    if body.status not in ('Active','Draft','Superseded') or body.classification not in ALLOWED['admin']: fail('Invalid metadata')
    if body.classification=='Restricted' and db.one('SELECT id FROM rules WHERE policy_document=?',(i,)): fail('Policy linked to benefit rules cannot become restricted')
    db.execute('UPDATE documents SET status=?,classification=?,owner=? WHERE id=?',(body.status,body.classification,body.owner,i)); retrieval.invalidate(); db.audit(user['username'],'document.metadata','document',i,J({'before':{k:old[k] for k in ('status','classification','owner')},'after':body.model_dump()})); return {'updated':i}

@router.get('/programmes/{i}/draft-rules')
def draft_rules(i:int,document:int,user=Depends(security.require_admin)):
    p=db.one('SELECT * FROM programmes WHERE id=?',(i,)); d=doc_access(document,'admin')
    if not p or d['policy_key']!=p['policy_key'] or d['status']!='Active' or d['classification']=='Restricted': fail('Choose an active matching policy')
    text='\n'.join(x['text'] for x in db.rows('SELECT text FROM source_pages WHERE document_id=? ORDER BY page',(document,)))
    age=re.search(r'at least\s+(\d+)\s+years',text,re.I); income=re.search(r'maximum monthly income is\s*R\s*([\d,]+(?:\.\d+)?)',text,re.I)
    if not age or not income: fail('Could not confidently map the sample policy clauses. Enter verified criteria manually.')
    return {'min_age':int(age.group(1)),'max_income':float(income.group(1).replace(',','')),'notice':'Draft extracted from sample clause wording. Human review required.'}
