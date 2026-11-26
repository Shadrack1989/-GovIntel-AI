"""Integrated workflow and permissions regression tests (local, no model needed)."""
from test_api import client, login
from pathlib import Path

def test_policy_permissions_and_currency(client):
    staff=login(client,'staff','staff123'); admin=login(client,'admin','admin123')
    docs=client.get('/api/documents',headers=admin).json(); restricted=next(x for x in docs if x['classification']=='Restricted'); old=next(x for x in docs if x['policy_key']=='housing' and x['status']=='Superseded')
    assert client.get('/api/intel/source/'+str(restricted['id']),headers=staff).status_code==404
    assert client.get('/api/intel/public-source/'+str(restricted['id'])).status_code==404
    assert client.get('/api/intel/public-source/'+str(old['id'])).status_code==404
    assert all(x['id']!=restricted['id'] for x in client.get('/api/documents',headers=staff).json())
    for h in (staff,admin):
        r=client.post('/api/intel/policy/chat',headers=h,json={'question':'What is the maximum monthly income for Housing Support?'}).json(); assert r['answered'] and r['sources']; assert all(x['status']=='Active' for x in r['sources'])
        r=client.post('/api/intel/policy/chat',headers=h,json={'question':'What is the capital of France?'}).json(); assert not r['answered']
    r=client.post('/api/intel/policy/chat',headers=staff,json={'question':'What is ORCHID-47 pilot verification code?'}).json(); assert 'ORCHID-47' not in r['answer'] and all(x['id']!=restricted['id'] for x in r['sources'])
    r=client.post('/api/intel/policy/chat',headers=admin,json={'question':'What is ORCHID-47 pilot verification code?'}).json(); assert r['answered'] and any(x['id']==restricted['id'] for x in r['sources'])
    assert client.post('/api/intel/policy/chat',json={'question':'Policy?'}).status_code==401

def test_application_full_workflow(client):
    h=login(client,'staff','staff123')
    a=client.post('/api/intel/applications',headers=h,json={'applicant':'Synthetic test','programme_id':1,'age':30,'income':2800}).json(); path='/api/intel/applications/'+str(a['id'])
    assert client.post(path+'/decision',headers=h,json={'decision':'Approved','reason':'Human reviewed'}).status_code==409
    for kind,text in [('Identity','Age: 30'),('Payslip','Monthly income: R2800'),('Residence','Address: Demo district')]:
        r=client.post(path+'/evidence',headers=h,data={'kind':kind},files={'file':('sample.txt',text.encode())}); assert r.status_code==200,r.text
    r=client.post(path+'/assess',headers=h).json(); assert r['recommendation']=='Likely eligible'
    r=client.post(path+'/evidence',headers=h,data={'kind':'Payslip'},files={'file':('sample.txt',b'Monthly income: R4200')}); assert r.status_code==200
    assert client.post(path+'/decision',headers=h,json={'decision':'Approved','reason':'Human reviewed'}).status_code==409
    assert client.post(path+'/assess',headers=h).json()['recommendation']=='Needs review'
    assert client.post(path+'/decision',headers=h,json={'decision':'Declined','reason':'Human reviewed discrepancy'}).status_code==200
    detail=client.get(path,headers=h).json(); assert len(detail['assessments'])==2 and detail['decisions'][0]['actor']=='staff'; assert detail['status']=='Declined'
    assert client.post(path+'/assess',headers=h).status_code==409

def test_real_ocr(client):
    import shutil,os,pytest
    if not shutil.which('tesseract') and not os.getenv('TESSERACT_CMD'): pytest.skip('Tesseract not installed')
    h=login(client,'staff','staff123'); a=client.post('/api/intel/applications',headers=h,json={'applicant':'Synthetic OCR','programme_id':1,'age':30,'income':2800}).json(); path='/api/intel/applications/'+str(a['id'])
    for k in ('Identity','Payslip','Residence'):
        p=Path(__file__).parents[1]/'web'/'samples'/(k.lower()+'.png'); r=client.post(path+'/evidence',headers=h,data={'kind':k},files={'file':(p.name,p.read_bytes(),'image/png')}); assert r.status_code==200,r.text; assert r.json()['fields'],r.text
    assert client.post(path+'/assess',headers=h).json()['recommendation']=='Likely eligible'

def test_rule_versions_and_upload_formats(client):
    from io import BytesIO
    from docx import Document
    admin=login(client,'admin','admin123'); staff=login(client,'staff','staff123')
    d=Document(); d.add_heading('Clause 1',1); d.add_paragraph('A fictional violet permit requires an authorised reviewer.'); b=BytesIO(); d.save(b)
    r=client.post('/api/documents/upload',headers=admin,data={'title':'Violet permit','classification':'Internal','repository':'DMS (simulated)'},files={'file':('demo.docx',b.getvalue())}); assert r.status_code==201,r.text
    i=r.json()['id']; assert client.get('/api/intel/public-source/'+str(i)).status_code==404; assert client.get('/api/intel/source/'+str(i),headers=staff).status_code==200
    p=client.get('/api/intel/programmes',headers=admin).json()[0]; rule={'min_age':18,'max_income':3500,'required':['Identity','Payslip','Residence'],'policy_document':p['rule']['policy_document']}
    assert client.post('/api/intel/programmes/1/rules',headers=staff,json=rule).status_code==403
    r=client.post('/api/intel/programmes/1/rules',headers=admin,json=rule); assert r.status_code==200 and r.json()['version']==2
    assert client.delete('/api/documents/'+str(rule['policy_document']),headers=admin).status_code==409
