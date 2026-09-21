from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text as sql_text
from starlette.middleware.trustedhost import TrustedHostMiddleware

from personal_injury.infrastructure.database import create_engine_for_url, create_session_factory, init_db
from personal_injury.infrastructure.seeding import seed_legal_sources
from personal_injury.infrastructure.settings import Settings, get_settings
from personal_injury.web.routes import auth, cases, sources


def create_app(
    database_url: str | None = None,
    *,
    settings_override: Settings | None = None,
) -> FastAPI:
    settings = settings_override or get_settings()
    if database_url:
        settings = replace(
            settings,
            database_url=database_url,
            environment="test",
            auto_create_schema=True,
            allow_demo_standards=True,
            cookie_secure=False,
            allow_open_bootstrap=True,
        )
    engine = create_engine_for_url(settings.database_url)
    session_factory = create_session_factory(engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.auto_create_schema:
            init_db(engine)
        with session_factory() as seed_session:
            seed_legal_sources(seed_session)
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title="人身损害赔偿律师团队系统",
        version="0.1.0",
        description="案件、证据、赔偿试算、规则来源和律师复核协作接口。",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.trusted_hosts))
    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        if (
            request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.cookies.get("access_token")
            and not request.headers.get("Authorization")
        ):
            origin = (request.headers.get("Origin") or "").rstrip("/")
            expected_origin = settings.public_origin or (
                f"{request.url.scheme}://{request.headers.get('host', '')}"
            )
            if origin and origin != expected_origin:
                return JSONResponse(status_code=403, content={"detail": "跨站请求已被拒绝"})

        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path in {"/", "/workspace"}:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; object-src 'none'; frame-ancestors 'none'; "
                "base-uri 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"
            )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if settings.cookie_secure:
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        return response
    app.include_router(auth.router)
    app.include_router(auth.users_router)
    app.include_router(cases.router)
    app.include_router(sources.router)

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def home():
        docs_hint = (
            '开发接口文档：<a href="/docs">/docs</a>。'
            if settings.docs_enabled
            else "接口文档已按生产环境配置关闭。"
        )
        return f"""
        <!doctype html>
        <html lang="zh-CN">
          <head><meta charset="utf-8"><title>人身损害赔偿律师团队系统</title></head>
          <body>
            <h1>人身损害赔偿律师团队系统</h1>
            <p>API 已启动。{docs_hint}</p>
            <p>当前版本重点支持案件、证据、赔偿项目、计算快照、复核任务和审计日志。</p>
          </body>
        </html>
        """

    @app.get("/workspace", response_class=HTMLResponse, include_in_schema=False)
    def workspace():
        return """
        <!doctype html>
        <html lang="zh-CN"><head><meta charset="utf-8"><title>律师工作台</title>
        <style>body{font-family:system-ui;max-width:1100px;margin:2rem auto;padding:0 1rem}input,select,button{padding:.55rem;margin:.25rem}section{border:1px solid #ddd;padding:1rem;margin:1rem 0;border-radius:8px}.muted{color:#666}pre{white-space:pre-wrap}.standard{border-top:1px solid #ddd;padding:1rem 0}.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem}.evidence-grid p{overflow-wrap:anywhere}.review-warning{color:#8a4800}.review-blocker{color:#a21d27}blockquote{margin:1rem 0;padding:1rem;background:#f4f7fa;white-space:pre-wrap}textarea{display:block;width:95%;min-height:4rem;margin:.5rem 0}summary{cursor:pointer}a{margin-right:1rem}@media(max-width:700px){.evidence-grid{grid-template-columns:1fr}}</style>
        </head><body><h1>律师团队人身损害赔偿工作台</h1>
        <section><h2>登录</h2><input id="username" placeholder="用户名"><input id="password" type="password" placeholder="密码"><button onclick="login()">登录</button><span id="loginState" class="muted"></span></section>
        <section><h2>案件</h2><button onclick="loadCases()">刷新案件</button><div id="cases"></div>
        <h3>新建案件</h3><input id="caseNumber" placeholder="案件编号"><input id="caseTitle" placeholder="案件标题"><select id="caseType"><option value="traffic_accident">交通事故</option><option value="employment_service">雇佣劳务</option><option value="general_personal_injury">一般人身损害</option></select><input id="region" placeholder="统计地区"><button onclick="createCase()">创建</button></section>
        <section><h2>统计标准复核</h2><p class="muted">核对地区、统计年度、口径和原文后批准。批准后的标准可供案件引用。</p><input id="standardRegion" aria-label="筛选统计地区" placeholder="统计地区（精确名称）"><input id="standardYear" aria-label="筛选统计年度" type="number" placeholder="统计年度"><label><input id="pendingOnly" type="checkbox" checked>仅未批准</label><button onclick="loadStandards()">查询标准</button><div id="standards" aria-live="polite">登录后可查询待复核标准。</div></section>
        <section><h2>接口提示</h2><p class="muted">此页面使用 HttpOnly 会话 Cookie；正式部署必须通过内网 HTTPS 访问。</p><pre id="output"></pre></section>
        <script>
        let currentUser=null;
        const out=x=>document.getElementById('output').textContent=typeof x==='string'?x:JSON.stringify(x,null,2);
        async function login(){const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:username.value,password:password.value})}); const d=await r.json(); currentUser=r.ok?d.user:null; loginState.textContent=r.ok?' 已登录：'+d.user.display_name:' 登录失败'; out(d); if(r.ok){loadCases();loadStandards();}}
        async function loadCases(){const r=await fetch('/api/cases'); const d=await r.json(); const box=document.getElementById('cases'); box.replaceChildren(); if(!r.ok){box.textContent='请先登录';out(d);return;} d.forEach(x=>{const p=document.createElement('p');const b=document.createElement('b');const small=document.createElement('small');b.textContent=x.case_number;small.textContent=x.status;p.append(b,document.createTextNode(' '+x.title+' '),small);box.appendChild(p);});out(d);}
        async function createCase(){const body={case_number:caseNumber.value,title:caseTitle.value,case_type:caseType.value,statistical_region:region.value||null}; const r=await fetch('/api/cases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); out(await r.json()); if(r.ok) loadCases();}
        const fieldNames={urban_disposable_income:'城镇居民人均可支配收入',urban_consumption_expenditure:'城镇居民人均消费支出',urban_non_private_wage:'城镇非私营单位就业人员年平均工资',urban_private_wage:'城镇私营单位就业人员年平均工资',service_industry_wage:'居民服务等行业非私营就业人员年平均工资',urban_on_duty_wage:'城镇单位在岗职工年平均工资'};
        const evidenceLabels={population:'统计人群',employment:'人员类别',ownership:'单位性质',industry:'行业',metric:'指标',page:'页码',table:'表格',row:'行',column:'列',cell:'单元格',sheet:'工作表',paragraph:'段落',header:'表头',headers:'表头',row_label:'行标题',column_label:'列标题',footnotes:'脚注',type:'类型',method:'方法',factor:'换算系数',from:'原单位',to:'目标单位',operation:'换算公式',json_pointer:'数据位置'};
        const make=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node;};
        function evidenceText(value){if(value===null||value===undefined||value==='')return '未记录';if(Array.isArray(value))return value.map(evidenceText).join('；');if(typeof value==='object')return Object.entries(value).map(([k,v])=>(evidenceLabels[k]||k)+'：'+evidenceText(v)).join('；');return String(value);}
        function evidenceLine(parent,label,value){const p=make('p');p.append(make('strong',label+'：'),document.createTextNode(evidenceText(value)));parent.append(p);}
        function officialLink(parent,value){try{const url=new URL(value);if(!['http:','https:'].includes(url.protocol))return;const a=make('a','打开来源网页');a.href=url.href;a.target='_blank';a.rel='noopener noreferrer';parent.append(a);}catch(_){}}
        function candidateDetails(parent,label,candidates){
          if(!Array.isArray(candidates)||!candidates.length)return;
          const group=make('details');group.append(make('summary',label+'（'+candidates.length+'）'));
          candidates.forEach(c=>{if(!c||typeof c!=='object'){group.append(make('p',evidenceText(c)));return;}const block=make('div');evidenceLine(block,'候选原值',evidenceText(c.raw_value??c.value)+' '+(c.raw_unit||c.unit||'单位待确认'));evidenceLine(block,'地区 / 年度',evidenceText(c.region)+' / '+evidenceText(c.statistical_year));evidenceLine(block,'统计口径',c.scope);evidenceLine(block,'原文位置',c.locator);if(c.snippet)block.append(make('blockquote',c.snippet));if((c.review_messages||c.review_reasons||[]).length)evidenceLine(block,'待复核原因',c.review_messages||c.review_reasons);group.append(block);});parent.append(group);
        }
        function renderStandard(x){
          const e=(x.source_record||{}).evidence||{},card=make('article',undefined,'standard');
          card.append(make('h3',x.region+' · '+x.year+' 年 · '+(fieldNames[x.field_name]||x.field_name)));
          const stateLabel=x.status==='approved'?'已批准':x.status==='invalidated'?'已失效，需重新采集':'待审核';
          card.append(make('p',(x.status==='invalidated'?'上次候选值（不可采用）：':'')+String(x.value)+' '+(e.unit||'元')+' · '+stateLabel));
          if(x.status==='invalidated'&&(x.source_record||{}).invalidated_reason)card.append(make('p',(x.source_record||{}).invalidated_reason,'review-blocker'));
          const details=make('details'),summary=make('summary','查看数值、原文与复核依据');details.append(summary);
          const grid=make('div',undefined,'evidence-grid'),left=make('div'),right=make('div');grid.append(left,right);details.append(grid);
          evidenceLine(left,'原始数值',e.raw_value);evidenceLine(left,'原始单位',e.raw_unit);evidenceLine(left,'换算过程',e.conversion);evidenceLine(left,'原文地区',e.region);evidenceLine(left,'统计年度',e.statistical_year);evidenceLine(left,'统计口径',e.scope);
          evidenceLine(right,'来源标题',x.source_title);evidenceLine(right,'发布日期',x.publish_date);evidenceLine(right,'原文位置',e.locator);evidenceLine(right,'表头',e.headers||(e.locator||{}).headers);evidenceLine(right,'脚注',e.footnotes||(e.locator||{}).footnotes);
          right.append(make('blockquote',e.snippet||'尚无原文片段，请打开官方来源核实。'));officialLink(right,x.source_url);
          if(x.archive_url){const a=make('a','下载留存原文');a.href='/api/statistical-standards/'+encodeURIComponent(x.id)+'/original';right.append(a);}
          evidenceLine(right,'原文 SHA-256',e.archive_sha256||e.content_sha256);evidenceLine(right,'抽取版本',e.extractor_version);
          candidateDetails(details,'冲突候选',e.conflicts);
          candidateDetails(details,'抽取候选',e.candidates||(x.source_record||{}).candidates);
          card.append(details);
          const warnings=x.review_warnings||[],blockers=x.approval_blockers||[];
          warnings.forEach(w=>card.append(make('p','待复核：'+w,'review-warning')));
          blockers.forEach(w=>card.append(make('p','暂不可批准：'+w,'review-blocker')));
          if(x.status!=='approved'){
            const reason=make('textarea');reason.placeholder='人工核验说明：核实了哪些口径、原文位置，以及冲突如何处理';reason.setAttribute('aria-label','人工核验说明');card.append(reason);
            const b=make('button','确认并批准');b.disabled=x.status==='invalidated'||blockers.length>0||!currentUser||!['admin','lawyer'].includes(currentUser.role);card.append(b);
            if(b.disabled&&!blockers.length)card.append(make('p','由律师或管理员批准标准。','muted'));
            b.onclick=async()=>{if(warnings.length&&!reason.value.trim()){out('请先填写人工核验说明。');reason.focus();return;}b.disabled=true;try{const r=await fetch('/api/statistical-standards/'+encodeURIComponent(x.id)+'/approve',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({reason:reason.value.trim()||null})});const d=await r.json();out(r.ok?'统计标准已批准。':d.detail||d);if(r.ok)await loadStandards();else b.disabled=false;}catch(_){out('请求失败，请稍后重试。');b.disabled=false;}};
          }
          return card;
        }
        async function loadStandards(){
          const box=document.getElementById('standards');box.textContent='正在加载统计标准…';
          try{const me=await fetch('/api/auth/me');currentUser=me.ok?await me.json():null;
            const params=new URLSearchParams();const regionValue=document.getElementById('standardRegion').value.trim(),yearValue=document.getElementById('standardYear').value;
            if(regionValue)params.set('region',regionValue);if(yearValue)params.set('year',yearValue);
            const r=await fetch('/api/statistical-standards?'+params),d=await r.json();box.replaceChildren();if(!r.ok){box.textContent='请先登录后查询标准。';out(d);return;}
            const rows=document.getElementById('pendingOnly').checked?d.filter(x=>x.status!=='approved'):d;
            if(!rows.length){box.textContent='暂无符合条件的统计标准。';return;}rows.forEach(x=>box.append(renderStandard(x)));
          }catch(_){box.textContent='加载失败，请稍后重试。';}
        }
        </script></body></html>
        """

    @app.get("/health", include_in_schema=False)
    def health():
        return {"status": "ok", "service": "personal-injury"}

    @app.get("/ready", include_in_schema=False)
    def ready():
        with session_factory() as db:
            db.execute(sql_text("SELECT 1"))
        return {"status": "ready", "service": "personal-injury"}

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("personal_injury.web.app:app", host="127.0.0.1", port=8000, reload=False)
