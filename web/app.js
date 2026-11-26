'use strict';
const $=s=>document.querySelector(s), esc=x=>String(x??'').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m]));

const icons={landmark:'M3 9l9-5 9 5M4 10h16M6 10v8m4-8v8m4-8v8m4-8v8M3 20h18',home:'M3 11l9-8 9 8v9h-6v-6H9v6H3z',chat:'M4 4h16v12H9l-5 4z',book:'M4 4h7l1 2 1-2h7v15h-7l-1 2-1-2H4z',inbox:'M4 4h16l2 12v4H2v-4zM2 16h6l2 2h4l2-2h6',search:'M15 15l5 5M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14',file:'M5 3h9l5 5v13H5zM14 3v6h5M8 13h8m-8 4h8',check:'M4 12l5 5L20 6',list:'M8 5h13M8 12h13M8 19h13M3 5h1m-1 7h1m-1 7h1',shield:'M12 2l9 4v6c0 5-5 8-9 10-4-2-9-5-9-10V6zM8 12l3 3 5-6',users:'M9 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8M2 21v-3a5 5 0 0 1 5-5h4a5 5 0 0 1 5 5v3M16 4a4 4 0 0 1 0 8m2 2a5 5 0 0 1 4 5v2',chart:'M3 3v18h18M7 17v-6m5 6V7m5 10V4',settings:'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6M10 15v6',arrow:'M5 12h14m-6-6 6 6-6 6',login:'M14 4h6v16h-6M3 12h12m-5-5 5 5-5 5',compare:'M4 5h7v14H4zM14 5h6v14h-6z',plus:'M12 4v16M4 12h16',clock:'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20M12 6v6l4 2',menu:'M4 6h16M4 12h16M4 18h16'};

const icon=k=>`<span class="ico"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><path d="${icons[k]||icons.file}"/></svg></span>`;

const S={
    user:null,
    token:sessionStorage.getItem('gi_token')||'',
    page:'home',
    chat:[],
    health:null,
    appId:null
};

try{
    S.user=JSON.parse(sessionStorage.getItem('gi_user')||'null')
}catch{};

const staff=()=>!!S.user,admin=()=>S.user?.role==='admin';

const btn=(text,action,style='secondary')=>`<button class="btn ${style}" onclick="${action}">${text}</button>`;

const tag=x=>`<span class="pill ${/Likely|Approved|Pass|Active|Resolved|Public/.test(x)?'green':/Not eligible|Declined|Fail|Restricted/.test(x)?'red':/Review|review|Pending|Draft|Superseded|Awaiting|More information/.test(x)?'amber':'blue'}">${esc(x||'—')}</span>`;

const head=(label,title,desc,extra='')=>`<div class="heading"><div><div class="eyebrow">${label}</div><h1>${title}</h1><p>${desc}</p></div>${extra}</div>`;

const field=(label,control)=>`<div class="field"><label>${label}</label>${control}</div>`;

const sel=(name,values,selected='')=>`<select name="${name}">${values.map(v=>{let [val,label]=Array.isArray(v)?v:[v,v];return `<option value="${esc(val)}" ${String(val)===String(selected)?'selected':''}>${esc(label)}</option>`}).join('')}</select>`;

const input=(name,value='',type='text',extra='')=>`<input name="${name}" type="${type}" value="${esc(value)}" ${extra}>`;

const table=(heads,rows)=>`<div class="tablewrap"><table><thead><tr>${heads.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${heads.length}" class="empty">No records found.</td></tr>`}</tbody></table></div>`;

const formData=id=>Object.fromEntries(new FormData($('#'+id)));

async function api(path,method='GET',data){
    let headers={};
    if(S.token)headers.Authorization='Bearer '+S.token;
    let body;
    if(data instanceof FormData)body=data;
    else if(data!==undefined){
        headers['Content-Type']='application/json';
        body=JSON.stringify(data)
    }
    let r=await fetch('/api'+path,{method,headers,body});
    let j=await r.json();
    if(!r.ok){
        if(r.status===401&&S.token&&path!='/auth/login'){
            logout();
            throw Error('Session expired. Sign in again.')
        }
        throw Error(typeof j.detail==='string'?j.detail:JSON.stringify(j.detail||j))
    }
    return j
}

function toast(t){
    $('#toast').textContent=t;
    $('#toast').style.display='block';
    clearTimeout(window.toastTimer);
    window.toastTimer=setTimeout(()=>$('#toast').style.display='none',4500)
}

async function act(fn){
    try{await fn()}catch(e){toast(e.message)}
}

function dialog(title,html){
    $('#modal').innerHTML=`<div class="modalshade"><div class="modalbody"><div class="flex between"><h2>${title}</h2>${btn('Close','closeModal()')}</div><div class="divider"></div>${html}</div></div>`
}

function closeModal(){
    $('#modal').innerHTML=''
}


// PUBLIC NAVIGATION

const navPublic=[
    ['PUBLIC PORTAL',[
        ['home','Overview','home'],
        ['citizen','Citizen Assistant','chat'],
        ['services','Service Directory','book'],
        ['submit','Submit Enquiry','inbox'],
        ['track','Track Enquiry','search']
    ]]
];


// OFFICIAL AND ADMIN NAVIGATION

const navStaff=()=>[
    ['WORKSPACE',[
        ['dashboard','Dashboard','home']
    ]],
    ['CITIZEN SERVICES',[
        ['citizen','Citizen Assistant','chat'],
        ['services','Service Directory','book'],
        ['submit','Submit Enquiry','plus'],
        ['track','Track Enquiry','search'],
        ['enquiries','Enquiry Management','inbox']
    ]],
    ['GRANTS & BENEFITS',[
        ['applications','Applications','list'],
        ['queue','Decision Queue','check'],
        ['rules','Eligibility Rules','settings']
    ]],
    ['GOVERNANCE',[
        ['analytics','Analytics','chart'],
        ['audit','Audit Trail','shield'],
        ...(admin()?[
            ['users','Users & Roles','users']
        ]:[])
    ]]
];


// APPLICATION LAYOUT

function layout(){
    let groups=staff()?navStaff():navPublic;
    let label=groups.flatMap(g=>g[1]).find(x=>x[0]===S.page)?.[1]||'Workspace';

    $('#app').innerHTML=`
        <div class="shell">
            <aside class="side">
                <div class="brand" onclick="go('${staff()?'dashboard':'home'}')">
                    <div class="mark">${icon('landmark')}</div>
                    <div>
                        <strong>Gov<span>Intel AI</span></strong>
                        <small>GOVERNMENT INTELLIGENCE</small>
                    </div>
                </div>

                ${groups.map(([group,items])=>`
                    <div class="navgroup">
                        <div class="navlabel">${group}</div>
                        ${items.map(([p,t,i])=>`
                            <button class="nav ${S.page===p?'active':''}" onclick="go('${p}')">
                                ${icon(i)}${t}
                            </button>
                        `).join('')}
                    </div>
                `).join('')}

                <div class="sidefoot">
                    <button class="nav" onclick="accounts()">
                        ${icon('users')} Demo login notepad
                    </button>
                    <button class="nav" onclick="${staff()?'logout()':"go('login')"}">
                        ${icon('login')}${staff()?'Sign out':'Official sign in'}
                    </button>
                    <div class="tiny" style="color:#9bb7c7;padding:9px">
                        InnovAIte 2026 · Demonstration
                    </div>
                </div>
            </aside>

            <div class="work">
                <header class="topbar">
                    <div class="flex">
                        <button class="btn secondary small mobile" onclick="$('.shell').classList.toggle('open')">
                            ${icon('menu')}
                        </button>
                        <span class="crumb">GovIntel AI / ${label}</span>
                    </div>
                    <div class="topright">
                        <span class="pill green">
                            <span class="statusdot"></span> Demo environment
                        </span>
                        <button class="btn secondary small" onclick="accounts()">
                            ${staff()?'Switch role':'Demo logins'}
                        </button>
                        <div class="user">
                            <div class="avatar">
                                ${staff()?esc(S.user.display_name.slice(0,2).toUpperCase()):'GI'}
                            </div>
                            <div>
                                <strong style="font-size:12px">
                                    ${staff()?esc(S.user.display_name.split(' (')[0]):'Citizen portal'}
                                </strong>
                                <small>${staff()?esc(S.user.role):'Public access'}</small>
                            </div>
                        </div>
                    </div>
                </header>

                <main class="content" id="content">
                    <div class="card">Loading…</div>
                </main>
            </div>
        </div>`;
}

let generation=0;

async function go(p,id){
    if(!Object.prototype.hasOwnProperty.call(pages,p))
        p=staff()?'dashboard':'home';

    if(id)S.appId=id;
    S.page=p;

    let g=++generation;

    layout();

    try{
        let html=await pages[p]();

        if(g===generation){
            $('#content').innerHTML=html+
                '<div class="footnote">GovIntel AI · Government Intelligence & Service Delivery Platform · Synthetic data only. Not an official government service.</div>';

            window.scrollTo(0,0)
        }
    }catch(e){
        if(g===generation)
            $('#content').innerHTML=`<div class="card"><h2>Unable to load</h2><p>${esc(e.message)}</p>${btn('Try again',`go('${p}')`)}</div>`
    }
}


// DEMO ACCOUNTS

function accounts(){
    dialog('Demo login notepad',`
        <p>Local demonstration accounts only. Do not deploy these passwords in production.</p>

        <div class="stack" style="margin-top:16px">
            ${[
                ['Citizen portal','No username or password required','',"logout()"],
                ['Government official','staff','staff123',"demoLogin('staff','staff123')"],
                ['Administrator','admin','admin123',"demoLogin('admin','admin123')"]
            ].map(([role,u,p,a])=>`
                <div class="demoaccount flex between">
                    <div>
                        <h3>${role}</h3>
                        <code>${esc(u)} ${p?' / '+p:''}</code>
                    </div>
                    ${btn('Open workspace',a,'')}
                </div>
            `).join('')}
        </div>

        <div class="divider"></div>

        <p>
            Administrator: manage eligibility rules, applications, enquiries and users.
            Official: manage citizen enquiries, assess applications and record decisions.
        </p>
    `)
}

async function demoLogin(username,password){
    await act(async()=>{
        let u=await api('/auth/login','POST',{username,password});
        S.token=u.token;
        S.user=u;

        sessionStorage.setItem('gi_token',u.token);
        sessionStorage.setItem('gi_user',JSON.stringify(u));

        closeModal();
        await go('dashboard');
        toast('Signed in as '+u.role)
    })
}

function logout(){
    S.token='';
    S.user=null;

    sessionStorage.removeItem('gi_token');
    sessionStorage.removeItem('gi_user');

    closeModal();
    go('home')
}


// SHARED COMPONENTS

const metrics=(arr)=>`
    <div class="grid ${arr.length===3?'g3':'g4'}">
        ${arr.map(([n,v,i])=>`
            <div class="card metric">
                <div class="ico">${icon(i)}</div>
                <div class="num">${esc(v)}</div>
                <small>${n}</small>
            </div>
        `).join('')}
    </div>`;

const tiles=(arr)=>`
    <div class="grid ${arr.length===2?'g2':'g3'}">
        ${arr.map(([i,t,d,p])=>`
            <article class="card tile">
                <div class="ico">${icon(i)}</div>
                <h2>${t}</h2>
                <p>${d}</p>
                ${btn('Open '+t,`go('${p}')`)}
            </article>
        `).join('')}
    </div>`;

const pages={};


// PUBLIC HOME PAGE

pages.home=async()=>`
    <div class="hero">
        <div class="eyebrow">Connected government · Better public services</div>
        <h1>Government services, made easier.</h1>
        <p>
            Find information, explore government services and submit or track enquiries in one place.
            Our source-grounded assistant helps you find the next step.
        </p>
        ${btn('Ask GovIntel AI '+icon('arrow'),"go('citizen')",'light')}
    </div>

    <div class="section">
        <h2>How can we help?</h2>
    </div>

    ${tiles([
        ['chat','Citizen Assistant','Ask a question and see the documents behind each answer.','citizen'],
        ['book','Service Directory','Browse services and official department links.','services'],
        ['inbox','Enquiries','Submit a question or report a service issue.','submit']
    ])}

    <div class="section">
        <h2>For government officials</h2>
    </div>

    <div class="card">
        <div class="eyebrow">Challenge 1</div>
        <h2>Grant & Benefits Eligibility</h2>
        <p>Extract documents, apply approved rules and record accountable human decisions.</p>
        <div class="divider"></div>
        ${btn('Official sign in',"go('login')",'')}
    </div>

    <div class="notice">
        This prototype uses fictional applications and synthetic policy documents.
        Do not submit real personal information.
    </div>
`;


// LOGIN PAGE

pages.login=async()=>`
    <div class="loginwrap">
        <div class="card login">
            <div class="eyebrow">Official workspace</div>
            <h1>Welcome back</h1>
            <p>Sign in to GovIntel AI.</p>

            <div class="divider"></div>

            <form id="loginForm" onsubmit="event.preventDefault();let f=formData('loginForm');demoLogin(f.username,f.password)">
                ${field('Username',input('username','','text','required autocomplete="username"'))}
                ${field('Password',input('password','','password','required autocomplete="current-password"'))}
                <button class="btn">Sign in</button>
            </form>

            <div class="divider"></div>
            ${btn('View demo credentials','accounts()')}
        </div>
    </div>
`;


// GOVERNMENT OFFICIAL DASHBOARD

pages.dashboard=async()=>{
    let d=await api('/intel/overview'),
        a=await api('/intel/applications');

    return `
        <div class="hero">
            <div class="eyebrow">Official workspace · InnovAIte 2026</div>
            <h1>Welcome, ${esc(S.user.display_name.split(' ')[0])}.</h1>
            <p>Manage citizen enquiries and review benefit applications from a unified workspace.</p>
            ${btn('Review decision queue '+icon('arrow'),"go('queue')",'light')}
        </div>

        ${metrics([
            ['Benefit applications',d.applications,'list'],
            ['Pending decisions',d.pending,'clock'],
            ['Citizen enquiries',d.enquiries,'inbox']
        ])}

        <div class="section">
            <h2>Explore your workspaces</h2>
            <span class="muted">Two integrated modules</span>
        </div>

        ${tiles([
            ['users','Citizen Services','Manage public enquiries and service routing.','enquiries'],
            ['check','Grants & Benefits','Verify documents, apply rules and record decisions.','applications']
        ])}

        <div class="section">
            <h2>Recent benefit applications</h2>
            ${btn('View all',"go('applications')")}
        </div>

        <div class="card">
            ${appTable(a.slice(0,5))}
        </div>
    `
};


// CITIZEN AI ASSISTANT

function renderChat(){
    let list=S.chat;

    return list.map(m=>`
        <div class="bubble ${m.me?'me':'ai'}">
            ${esc(m.text)}

            ${m.warning?`
                <div class="notice">${esc(m.warning)}</div>
            `:''}

            ${m.mode?`
                <div class="tiny" style="margin-top:8px">${esc(m.mode)}</div>
            `:''}

            ${m.sources?.length?`
                <div class="sources">
                    ${m.sources.map((s,i)=>`
                        <div class="source">
                            <div class="flex between">
                                <strong>[${i+1}] ${esc(s.title)}</strong>
                                ${tag(s.status||'Active')}
                            </div>

                            <div class="tiny">
                                ${esc(s.section||'General')} · Page ${esc(s.page)} · Version ${esc(s.version||'demo')}
                            </div>

                            <p>${esc(s.excerpt?.slice(0,300))}</p>

                            ${s.id?`
                                <button class="linkbtn" onclick="openSource(${s.id},true)">
                                    Open and verify source →
                                </button>
                            `:''}
                        </div>
                    `).join('')}
                </div>
            `:''}
        </div>
    `).join('')
}

function chatPage(){
    let prompts=[
        'How do I replace my lost ID?',
        'How do I check my SRD grant status?',
        'How can I claim UIF?',
        'What is the capital of France?'
    ];

    return head(
        'Citizen Services',
        'Citizen Assistant',
        'Ask about government services and receive source-grounded guidance.',
        btn('New conversation',"S.chat=[];go('citizen')")
    )+`
        <div class="split">
            <div class="card chat">
                <div class="flex between">
                    <div class="flex">
                        ${icon('chat')}
                        <h3 style="margin:0">GovIntel AI Assistant</h3>
                    </div>
                    <span class="pill green">Source grounded</span>
                </div>

                <div class="divider"></div>

                <div class="messages" id="messages">
                    ${renderChat()||`
                        <div class="bubble ai">
                            Hello! I can help you navigate government services.
                            Ask a question or select an example on the right.
                        </div>
                    `}
                </div>

                <form id="chatForm" onsubmit="event.preventDefault();sendChat()">
                    <div class="flex">
                        ${field('Language',sel('language',[
                            ['en','English'],
                            ['xh','isiXhosa'],
                            ['zu','isiZulu'],
                            ['st','Sesotho']
                        ]))}
                    </div>

                    <div class="flex" style="flex-wrap:nowrap">
                        <input name="question" id="question" placeholder="Type your question here…" maxlength="1000" required>
                        <button class="btn" id="send">Send ${icon('arrow')}</button>
                    </div>
                </form>
            </div>

            <div class="stack">
                <div class="card">
                    <h2>Try an example</h2>

                    <div class="stack">
                        ${prompts.map((p,i)=>`
                            <button class="prompt" data-prompt="${esc(p)}" onclick="$('#question').value=this.dataset.prompt;$('#question').focus()">
                                ${esc(p)} →
                            </button>
                        `).join('')}
                    </div>
                </div>

                <div class="card">
                    <h3>How answers work</h3>
                    <p>
                        Retrieval searches permitted documents. Each answer shows supporting passages and source versions.
                        If the evidence is insufficient, the assistant declines to answer.
                    </p>
                    <div class="notice info">
                        Only active public documents are used. The department makes final decisions.
                    </div>
                </div>
            </div>
        </div>
    `
}

pages.citizen=async()=>chatPage();

async function sendChat(){
    let f=formData('chatForm'),
        q=f.question.trim();

    if(!q)return;

    let target=S.chat;

    target.push({me:true,text:q});

    $('#messages').innerHTML=renderChat();
    $('#question').value='';
    $('#send').disabled=true;

    try{
        let r=await api('/chat','POST',{
            question:q,
            language:f.language
        });

        target.push({
            text:r.answer,
            sources:r.sources,
            warning:r.warning||r.notices?.join(' '),
            mode:r.mode||r.generated_by
        });

    }catch(e){
        target.push({text:e.message})
    }

    if($('#messages')&&S.chat===target){
        $('#messages').innerHTML=renderChat();
        $('#messages').scrollTop=$('#messages').scrollHeight;
        $('#send').disabled=false
    }
}


// SOURCE VERIFICATION
// Retained for Citizen Assistant and eligibility assessments.

async function openSource(id,pub=false){
    await act(async()=>{
        let r=await api('/intel/'+(pub?'public-source/':'source/')+id);

        dialog(esc(r.document.title),`
            <div class="flex">
                ${tag(r.document.status)}
                ${tag(r.document.classification)}
                <span class="muted">
                    Version ${esc(r.document.version)} · ${esc(r.document.repository)}
                </span>
            </div>

            <p>${esc(r.document.owner)} · ${esc(r.document.review_date||'No review date')}</p>

            <div class="notice">
                Extracted source text. Synthetic demo material unless explicitly marked otherwise.
            </div>

            ${r.pages.map(p=>`
                <h3>Page ${p.page}</h3>
                <pre>${esc(p.text)}</pre>
            `).join('')}
        `)
    })
}


// GOVERNMENT SERVICE DIRECTORY

pages.services=async()=>{
    let d=await api('/services');

    return head(
        'Citizen Services',
        'Service Directory',
        'Explore government services and find the responsible department.'
    )+`
        <div class="card" style="margin-bottom:16px">
            <input placeholder="Search services…" oninput="filterCards(this.value)">
        </div>

        <div class="grid g3" id="servicecards">
            ${d.map(s=>`
                <div class="card tile" data-search="${esc((s.name+' '+s.department+' '+s.description).toLowerCase())}">
                    <div class="ico">${icon('landmark')}</div>
                    <span class="pill">${esc(s.category)}</span>
                    <h2>${esc(s.name)}</h2>
                    <p>${esc(s.description)}</p>
                    <div class="muted">${esc(s.department)}</div>
                    <a class="btn secondary" href="${esc(/^https?:\/\//i.test(s.info_url)?s.info_url:'#')}" target="_blank" rel="noopener">
                        Official website ↗
                    </a>
                </div>
            `).join('')}
        </div>
    `
};

function filterCards(q){
    document.querySelectorAll('[data-search]').forEach(x=>
        x.hidden=!x.dataset.search.includes(q.toLowerCase())
    )
}


// SUBMIT CITIZEN ENQUIRY

pages.submit=async()=>head(
    'Citizen Services',
    'Submit an enquiry',
    'Tell us what you need help with. A routing recommendation will be reviewed by an official.'
)+`
    <div class="split">
        <div class="card">
            <form id="enqForm" onsubmit="event.preventDefault();submitEnq()">
                ${field('Describe the enquiry','<textarea name="description" minlength="10" maxlength="2000" required placeholder="Example: My grant payment has not arrived…"></textarea>')}

                <div class="notice">
                    Use fictional information only; do not include ID numbers, medical or banking details.
                </div>

                <button class="btn">Submit enquiry</button>
            </form>
        </div>

        <div class="card">
            <h2>What happens next?</h2>
            <p>
                1. The system suggests a department.<br>
                2. You receive a tracking reference.<br>
                3. An official confirms routing and updates the status.
            </p>
        </div>
    </div>
`;

async function submitEnq(){
    await act(async()=>{
        let r=await api('/enquiries','POST',formData('enqForm'));

        dialog('Enquiry submitted',`
            <p>Keep this reference number for tracking:</p>
            <h1 style="margin:12px 0">${esc(r.reference_number)}</h1>
            <p>Suggested department: ${esc(r.suggested_department)}</p>
            ${tag(r.status)}
            <div class="divider"></div>
            ${btn('Track enquiry',`closeModal();go('track')`,'')}
        `);

        $('#enqForm').reset()
    })
}


// TRACK ENQUIRY

pages.track=async()=>head(
    'Citizen Services',
    'Track your enquiry',
    'Enter the reference number issued when you submitted your enquiry.'
)+`
    <div class="card">
        <form id="trackForm" onsubmit="event.preventDefault();trackEnq()">
            ${field('Reference number',input('reference','','text','required placeholder="GA-YYYYMMDD-XXXXXX"'))}
            <button class="btn">Find enquiry</button>
        </form>
        <div id="trackResult"></div>
    </div>
`;

async function trackEnq(){
    await act(async()=>{
        let r=await api('/enquiries/track/'+encodeURIComponent(formData('trackForm').reference));

        $('#trackResult').innerHTML=`
            <div class="divider"></div>
            <h2>${esc(r.reference_number)}</h2>
            ${tag(r.status)}
            <p>Department: ${esc(r.department)} · ${esc(r.category)}</p>
            <p>Last updated: ${esc(r.updated_at)}</p>
        `
    })
}


// ENQUIRY MANAGEMENT

pages.enquiries=async()=>{
    let r=await api('/enquiries');

    return head(
        'Citizen Services',
        'Enquiry Management',
        'Review routing recommendations and update enquiry status.'
    )+`
        <div class="card">
            <input placeholder="Filter enquiries…" oninput="filterRows(this.value)">
            <div class="divider"></div>

            ${table(
                ['Reference / enquiry','Suggested department','Status','Action'],
                r.map(e=>[
                    `<strong>${esc(e.reference_number)}</strong><div class="muted">${esc(e.description)}</div>`,
                    esc(e.confirmed_department||e.suggested_department),
                    tag(e.status),
                    btn('Review',`editEnquiry(${e.id})`,'secondary small')
                ])
            )}
        </div>
    `
};

function filterRows(q){
    document.querySelectorAll('tbody tr').forEach(x=>
        x.hidden=!x.textContent.toLowerCase().includes(q.toLowerCase())
    )
}

async function editEnquiry(id){
    await act(async()=>{
        let e=(await api('/enquiries')).find(x=>x.id===id);

        dialog('Review '+esc(e.reference_number),`
            <p>${esc(e.description)}</p>

            <form id="editEnq" onsubmit="event.preventDefault();updateEnquiry(${id})">
                ${field('Status',sel('status',[
                    'Submitted',
                    'Under Review',
                    'Referred',
                    'Resolved',
                    'Closed'
                ],e.status))}

                ${field('Confirmed department',input('confirmed_department',e.confirmed_department||e.suggested_department))}

                ${field('Internal note','<textarea name="note"></textarea>')}

                <div class="muted wraptext">
                    ${esc(e.staff_notes||'No previous notes')}
                </div>

                <button class="btn">Save update</button>
            </form>
        `)
    })
}

async function updateEnquiry(id){
    await act(async()=>{
        await api('/enquiries/'+id,'PATCH',formData('editEnq'));

        closeModal();
        go('enquiries');
        toast('Enquiry updated')
    })
}


// GRANTS AND BENEFITS APPLICATIONS

function appTable(a){
    return table(
        ['Reference / applicant','Programme','Recommendation','Status','Action'],
        a.map(x=>[
            `<strong>${esc(x.reference)}</strong><div class="muted">${esc(x.applicant)}</div>`,
            esc(x.programme),
            tag(x.recommendation),
            tag(x.status),
            btn('Open case',`go('case',${x.id})`,'secondary small')
        ])
    )
}

pages.applications=async()=>{
    let a=await api('/intel/applications');

    return head(
        'Grants & Benefits',
        'Applications',
        'Capture synthetic applications, extract evidence and assess eligibility.',
        btn('+ New application','newApplication()','')
    )+`
        <div class="notice">
            All names, policy thresholds and supporting documents are fictional.
            No real personal information may be entered.
        </div>

        <div class="card">
            <input placeholder="Search applications…" oninput="filterRows(this.value)">
            <div class="divider"></div>
            ${appTable(a)}
        </div>
    `
};


// DECISION QUEUE

pages.queue=async()=>{
    let a=(await api('/intel/applications')).filter(
        x=>!['Approved','Declined'].includes(x.status)
    );

    return head(
        'Grants & Benefits',
        'Decision Queue',
        'An authorised official must review every recommendation. No automatic declines.'
    )+`
        <div class="card">${appTable(a)}</div>
    `
};


// CREATE NEW APPLICATION

async function newApplication(){
    await act(async()=>{
        let p=await api('/intel/programmes');

        dialog('New synthetic application',`
            <form id="newApp" onsubmit="event.preventDefault();createApplication()">

                ${field('Programme',sel('programme_id',p.map(x=>[x.id,x.name])))}

                ${field('Fictional applicant name',input('applicant','Demo Applicant E','text','required'))}

                <div class="grid g2">
                    ${field('Declared age',input('age','30','number','min="0" max="120" required'))}

                    ${field('Declared monthly income (R)',input('income','2800','number','min="0" step="0.01" required'))}
                </div>

                <div class="notice">Synthetic data only.</div>

                <button class="btn">Create application</button>
            </form>
        `)
    })
}

async function createApplication(){
    await act(async()=>{
        let f=formData('newApp');

        let r=await api('/intel/applications','POST',{
            ...f,
            programme_id:+f.programme_id,
            age:+f.age,
            income:+f.income
        });

        closeModal();
        go('case',r.id);
        toast('Application created')
    })
}


// APPLICATION DETAILS AND ELIGIBILITY ASSESSMENT

pages.case=async()=>{
    let a=await api('/intel/applications/'+S.appId),
        s=a.assessments[0],
        final=['Approved','Declined'].includes(a.status);

    return head(
        'Grants & Benefits / Applications',
        esc(a.reference),
        `${esc(a.applicant)} · ${esc(a.programme)}`,
        btn('Back to applications',"go('applications')")
    )+`
        <div class="grid g3" style="margin-bottom:16px">
            <div class="card">
                <div class="eyebrow">Declared age</div>
                <h2>${esc(a.declared.age)} years</h2>
            </div>

            <div class="card">
                <div class="eyebrow">Declared income</div>
                <h2>R ${Number(a.declared.income).toLocaleString('en-ZA')}</h2>
            </div>

            <div class="card">
                <div class="eyebrow">Application status</div>
                <h2>${tag(a.status)}</h2>
            </div>
        </div>

        <div class="split">
            <div class="stack">

                <div class="card">
                    <div class="step">STEP 01 · DOCUMENT VERIFICATION</div>

                    <div class="flex between">
                        <h2>Supporting evidence</h2>

                        ${!final?btn('+ Upload evidence',`evidenceDialog(${a.id})`,''):''}
                    </div>

                    <p>
                        OCR extracts fields from scans. Text files and text PDFs are parsed directly.
                        Latest document per type is used.
                    </p>

                    <div class="divider"></div>

                    ${table(
                        ['Type / file','Extracted fields','Extraction score','Action'],
                        a.evidence.map((e,i)=>[
                            `<strong>${esc(e.kind)}</strong><div class="muted">${esc(e.filename)}</div>`,
                            esc(JSON.stringify(e.fields)),
                            Math.round(e.confidence*100)+'%',
                            btn('Inspect',`evidenceView(${a.id},${e.id})`,'secondary small')
                        ])
                    )}
                </div>


                <div class="card">
                    <div class="step">STEP 02 · DETERMINISTIC RULES</div>

                    <div class="flex between">
                        <h2>Eligibility assessment</h2>
                        ${!final?btn('Run assessment',`runAssessment(${a.id})`,''):''}
                    </div>

                    ${s?`
                        <div class="notice ${s.recommendation==='Likely eligible'?'info':''}">
                            <div class="flex between">
                                <h2>${esc(s.recommendation)}</h2>
                                <strong>${Math.round(s.confidence*100)}% evidence-quality score</strong>
                            </div>

                            <p>
                                Rule v${esc(s.rule_version)} · Policy v${esc(s.policy_version)} · ${esc(s.created_at)}
                            </p>

                            <p>This score is a heuristic, not a calibrated probability.</p>

                            ${a.status==='Submitted'?'<strong>Evidence changed: rerun before deciding.</strong>':''}
                        </div>

                        ${table(
                            ['Rule / policy clause','Outcome','Evidence & explanation'],
                            s.results.map(r=>[
                                `<strong>${esc(r.rule)}</strong><div class="muted">${esc(r.clause)}</div>`,
                                tag(r.outcome),
                                `${esc(r.detail)}${r.evidence_id?`<div class="muted">Evidence #${r.evidence_id}</div>`:''}`
                            ])
                        )}

                        ${btn('Verify policy source',`openSource(${s.policy_document})`)}

                        <div class="divider"></div>

                        <details>
                            <summary>Assessment history (${a.assessments.length})</summary>

                            ${a.assessments.map(h=>`
                                <div class="listrow">
                                    <span>${esc(h.created_at)} · Rule v${h.rule_version}</span>
                                    ${tag(h.recommendation)}
                                    ${btn('Snapshot',`snapshot(${a.id},${h.id})`,'secondary small')}
                                </div>
                            `).join('')}
                        </details>

                    `:'<p>No assessment yet. Upload evidence and run the rules.</p>'}

                </div>
            </div>

            <div class="stack">
                <div class="card">

                    <div class="step">STEP 03 · HUMAN REVIEW</div>

                    <h2>Official decision</h2>

                    <p>
                        The AI and rules engine provide recommendations only.
                        Record your independent decision and reason.
                    </p>

                    <div class="divider"></div>

                    ${final?`
                        <div class="notice info">
                            ${tag(a.status)} Final decision recorded.
                        </div>

                    `:a.status==='Awaiting decision'?`

                        <form id="decision" onsubmit="event.preventDefault();saveDecision(${a.id})">

                            ${field('Decision',sel('decision',[
                                'More information required',
                                'Approved',
                                'Declined'
                            ]))}

                            ${field('Reason (required)','<textarea name="reason" minlength="8" required placeholder="Explain the evidence and why you agree or override…"></textarea>')}

                            <button class="btn">Record official decision</button>
                        </form>

                    `:'<div class="notice">Run an assessment on the latest evidence before recording a decision.</div>'}

                    <div class="divider"></div>

                    <h3>Decision history</h3>

                    ${a.decisions.length?a.decisions.map(d=>`
                        <div class="listrow">
                            <div>
                                ${tag(d.decision)}
                                <p class="wraptext">${esc(d.reason)}</p>
                                <div class="tiny">${esc(d.actor)} · ${esc(d.created_at)}</div>
                            </div>
                        </div>
                    `).join(''):'<p>No decisions recorded.</p>'}

                </div>

                <div class="card">
                    <h2>Audit & governance</h2>
                    <p>All extractions, rule versions, assessment snapshots and official actions are logged.</p>

                    <div class="divider"></div>

                    ${btn('Open audit trail',"go('audit')")}
                </div>
            </div>
        </div>
    `
};


// SUPPORTING DOCUMENT UPLOAD AND OCR

function evidenceDialog(id){
    dialog('Upload synthetic supporting evidence',`
        <form id="evidence" onsubmit="event.preventDefault();sendEvidence(${id})">

            ${field('Document type',sel('kind',[
                'Identity',
                'Payslip',
                'Residence'
            ]))}

            ${field('PDF, PNG, JPG or TXT','<input name="file" type="file" required accept=".pdf,.png,.jpg,.jpeg,.txt">')}

            <p>
                Sample evidence files are included in the project under <code>web/samples</code>.
                Download a matching sample:
            </p>

            <div class="flex">
                <a href="/samples/identity.png" download>Identity scan</a>
                <a href="/samples/payslip.png" download>Payslip scan</a>
                <a href="/samples/residence.png" download>Residence scan</a>
                <a href="/samples/payslip_mismatch.txt" download>Mismatch text</a>
            </div>

            <div class="notice">
                Actual OCR requires Tesseract; no fake extraction is used.
            </div>

            <button class="btn">Extract & save evidence</button>
        </form>
    `)
}

async function sendEvidence(id){
    await act(async()=>{
        let f=$('#evidence');

        f.classList.add('loading');

        try{
            let r=await api(
                '/intel/applications/'+id+'/evidence',
                'POST',
                new FormData(f)
            );

            closeModal();
            go('case',id);
            toast('Evidence extracted: '+JSON.stringify(r.fields))

        }finally{
            f.classList.remove('loading')
        }
    })
}

async function evidenceView(id,eid){
    await act(async()=>{
        let a=await api('/intel/applications/'+id),
            e=a.evidence.find(x=>x.id===eid);

        dialog(esc(e.kind)+' evidence',`
            <p>${esc(e.filename)} · Extraction score ${Math.round(e.confidence*100)}%</p>

            <pre>${esc(e.text)}</pre>

            <h3>Extracted fields</h3>

            <pre>${esc(JSON.stringify(e.fields,null,2))}</pre>
        `)
    })
}

async function snapshot(id,sid){
    await act(async()=>{
        let a=await api('/intel/applications/'+id),
            s=a.assessments.find(x=>x.id===sid);

        dialog('Immutable assessment snapshot',`
            <pre>${esc(JSON.stringify(s.snapshot,null,2))}</pre>
        `)
    })
}

async function runAssessment(id){
    await act(async()=>{
        let r=await api(
            '/intel/applications/'+id+'/assess',
            'POST',
            {}
        );

        go('case',id);
        toast('Assessment: '+r.recommendation)
    })
}

async function saveDecision(id){
    await act(async()=>{
        if(!confirm('Record this official decision with the supplied reason?'))return;

        let r=await api(
            '/intel/applications/'+id+'/decision',
            'POST',
            formData('decision')
        );

        go('case',id);
        toast('Official decision: '+r.status)
    })
}


// ELIGIBILITY RULES

pages.rules=async()=>{
    let p=await api('/intel/programmes');

    return head(
        'Grants & Benefits',
        'Eligibility Rules',
        'Version-controlled, human-approved rules linked to synthetic policies.'
    )+`
        <div class="notice">
            These illustrative thresholds are not South African government eligibility criteria.
            Policy owners must verify rules against the cited source before publishing.
        </div>

        <div class="grid g3">
            ${p.map(x=>`
                <div class="card tile">
                    <div class="ico">${icon('settings')}</div>

                    <h2>${esc(x.name)}</h2>

                    <p>${esc(x.description)} · Rule version ${x.rule.version}</p>

                    <div class="divider" style="width:100%;margin:4px 0"></div>

                    <p>Minimum age: <strong>${x.rule.criteria.min_age}</strong></p>

                    <p>Maximum monthly income: <strong>R ${x.rule.criteria.max_income}</strong></p>

                    <p>Required evidence: ${esc(x.rule.criteria.required.join(', '))}</p>

                    <div class="flex">
                        ${btn('Source policy',`openSource(${x.rule.policy_document})`)}

                        ${admin()?btn('Edit rules',`ruleDialog(${x.id})`,''):''}
                    </div>
                </div>
            `).join('')}
        </div>
    `
};

async function ruleDialog(id){
    await act(async()=>{
        let [ps,docs]=await Promise.all([
            api('/intel/programmes'),
            api('/documents')
        ]),

        p=ps.find(x=>x.id===id),

        d=docs.filter(x=>
            x.policy_key===p.policy_key&&
            x.status==='Active'&&
            x.classification!=='Restricted'
        );

        dialog('Create new rule version',`
            <p>
                ${esc(p.name)} · Editing creates a new version;
                historical assessments remain unchanged.
            </p>

            <form id="rule" onsubmit="event.preventDefault();saveRule(${id})">

                ${field('Policy document',sel(
                    'policy_document',
                    d.map(x=>[x.id,`${x.title} v${x.version}`]),
                    p.rule.policy_document
                ))}

                ${btn('Extract draft rules from selected policy',`draftRules(${id})`)}

                ${field('Minimum age — clause 2',input(
                    'min_age',
                    p.rule.criteria.min_age,
                    'number',
                    'min="0" max="120" required'
                ))}

                ${field('Maximum monthly income — clause 3',input(
                    'max_income',
                    p.rule.criteria.max_income,
                    'number',
                    'min="0" step="0.01" required'
                ))}

                <div class="notice">
                    Identity, payslip and residence evidence are mandatory in this prototype.
                    Verify all thresholds against your selected policy.
                </div>

                <button class="btn">Publish new rule version</button>
            </form>
        `)
    })
}

async function saveRule(id){
    await act(async()=>{
        let f=formData('rule');

        await api('/intel/programmes/'+id+'/rules','POST',{
            min_age:+f.min_age,
            max_income:+f.max_income,
            policy_document:+f.policy_document,
            required:['Identity','Payslip','Residence']
        });

        closeModal();
        go('rules');
        toast('New rule version published')
    })
}


// GOVERNANCE AND ANALYTICS

pages.analytics=async()=>{
    let [d,s]=await Promise.all([
        api('/intel/overview'),
        api('/dashboard/stats')
    ]);

    let bar=(arr)=>arr.map(([k,v])=>`
        <div class="chartrow">
            <span>${esc(k)}</span>

            <div class="bar">
                <i style="width:${Math.round(v/Math.max(1,...arr.map(x=>x[1]))*100)}%"></i>
            </div>

            <strong>${v}</strong>
        </div>
    `).join('');

    return head(
        'Governance',
        'Analytics',
        'Live metrics calculated from the local prototype database.'
    )+

    metrics([
        ['Total enquiries',s.total_enquiries,'inbox'],
        ['Open enquiries',s.open_enquiries,'clock'],
        ['Citizen questions',s.questions_asked,'chat'],
        ['Answered',s.questions_answered,'check']
    ])+`

        <div class="grid g2" style="margin-top:16px">

            <div class="card stack">
                <h2>Enquiries by status</h2>
                ${bar(Object.entries(s.by_status))}
            </div>

            <div class="card stack">
                <h2>Latest eligibility recommendations</h2>
                ${bar(d.recommendations.map(x=>[x.recommendation,x.n]))}
            </div>

            <div class="card stack">
                <h2>Enquiries by category</h2>
                ${bar(Object.entries(s.by_category))}
            </div>

            <div class="card stack">
                <h2>Enquiries in last 14 days</h2>
                ${bar(s.trend.map(x=>[x.date,x.enquiries]))}
            </div>

        </div>
    `
};


// AUDIT TRAIL

pages.audit=async()=>{
    let a=await api('/audit?limit=200');

    return head(
        'Governance',
        'Audit Trail',
        'Review recorded system actions, eligibility decisions and evidence references.',
        btn('Export CSV','exportAudit()')
    )+`

        <div class="card">
            <input placeholder="Search audit events…" oninput="filterRows(this.value)">

            <div class="divider"></div>

            ${table(
                ['Time','Actor','Action','Record','Detail'],
                a.map(x=>[
                    esc(x.timestamp),
                    esc(x.actor),
                    `<strong>${esc(x.action)}</strong>`,
                    esc((x.record_type||'')+' '+(x.record_id||'')),
                    `<details>
                        <summary>View detail</summary>
                        <div class="wraptext">${esc(x.detail||'—')}</div>
                    </details>`
                ])
            )}
        </div>
    `
};

async function exportAudit(){
    await act(async()=>{
        let a=await api('/audit?limit=200'),

        keys=[
            'timestamp',
            'actor',
            'action',
            'record_type',
            'record_id',
            'detail'
        ],

        safe=v=>{
            let t=String(v??'');

            if(/^[=+\-@\t\r]/.test(t))t="'"+t;

            return '"'+t.replaceAll('"','""')+'"'
        };

        let csv=[
            keys.join(','),
            ...a.map(x=>keys.map(k=>safe(x[k])).join(','))
        ].join('\n'),

        u=URL.createObjectURL(new Blob([csv],{type:'text/csv'})),
        el=document.createElement('a');

        el.href=u;
        el.download='govintel-audit.csv';
        el.click();

        URL.revokeObjectURL(u)
    })
}


// USERS AND ROLES

pages.users=async()=>{
    let d=await api('/intel/users');

    return head(
        'Governance',
        'Users & Roles',
        'Review the prototype accounts and their server-enforced permissions.'
    )+`

        <div class="card">
            ${table(
                ['Username','Display name','Role','Created'],
                d.map(x=>[
                    esc(x.username),
                    esc(x.display_name),
                    tag(x.role),
                    esc(x.created_at)
                ])
            )}
        </div>

        <div class="grid g2" style="margin-top:16px">

            <div class="card">
                <h2>Official</h2>
                <p>
                    Enquiries, applications, supporting evidence,
                    assessments and decisions.
                </p>
            </div>

            <div class="card">
                <h2>Administrator</h2>
                <p>
                    All official functions plus eligibility rule publishing
                    and access to the users and roles overview.
                </p>
            </div>

        </div>

        <div class="notice">
            Demo accounts are seeded, not a full identity management system.
            Production would require SSO, department scoping and access reviews.
        </div>

        ${btn('Demo login notepad','accounts()')}
    `
};


// INITIALISE APPLICATION

go(staff()?'dashboard':'home');


// EXTRACT DRAFT ELIGIBILITY RULES

async function draftRules(id){
    await act(async()=>{
        let f=$('#rule');

        let r=await api(
            '/intel/programmes/'+id+'/draft-rules?document='+
            encodeURIComponent(f.elements.policy_document.value)
        );

        f.elements.min_age.value=r.min_age;
        f.elements.max_income.value=r.max_income;

        toast(r.notice)
    })
}