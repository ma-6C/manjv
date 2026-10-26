'use strict';
// The server owns dispatch and checkpoints. This module follows real stages; it
// never starts a production job from a polling or navigation callback.
(()=>{
 const ui={flows:[],activeFlowId:'',following:false,preparingNext:false,seen:new Map(),expectedHash:'',pending:null,busy:false,error:'',query:'',projectIds:new Set(),paths:new Set(),selectionReady:false,projectSignature:'',detailSignature:'',stripSignature:'',options:{withJianying:true,withEvidence:true,withExport:true,withPublish:false,reviewRequired:false,accountId:''}};
 const labels={queued:'待开始',dispatching:'正在启动',running:'进行中',waiting_action:'等待操作',waiting_confirmation:'等待本人确认',paused:'已暂停',interrupted:'需要恢复',failed:'未完成',completed:'已完成',cancelled:'已停止',pending:'待处理',skipped:'已跳过'};
 const terminal=new Set(['completed','cancelled']);
 pages.unshift(['studio','开始工作','play']);navigationSections.unshift(['连续制作',['studio']]);navigationLabels.studio='开始工作';
 const basePageFromHash=pageFromHash;pageFromHash=function(){return !location.hash||location.hash==='#'?'studio':basePageFromHash();};
 const active=()=>ui.flows.find(f=>f.id===ui.activeFlowId)||null;
 const stages=f=>Array.isArray(f?.stages)?f.stages:[];
 const stage=f=>f?.status==='completed'?{key:'completed',label:'所选流程已完成',route:'studio',status:'completed',message:f.message}:stages(f).find(s=>(s.key||s.name)===f?.currentStage)||stages(f).find(s=>['dispatching','running','waiting_action','waiting_confirmation','failed','interrupted'].includes(s.status))||stages(f).filter(s=>s.status!=='skipped').at(-1)||{};
 const route=f=>f?.status==='completed'?'studio':String(f?.route||stage(f).route||'studio').replace(/^#/, '');
 const selectedVideos=()=>state.projects.flatMap(p=>ui.projectIds.has(p.id)?p.videos.filter(v=>ui.paths.has(v.path)):[]);
 const selectedProjects=()=>state.projects.filter(p=>ui.projectIds.has(p.id)&&p.videos.some(v=>ui.paths.has(v.path)));
 function overview(f){
  const s=stage(f),key=s.key||s.name,index=!f?(selectedVideos().length?1:0):f.status==='completed'?5:['production','produce'].includes(key)?2:['review','jianying','drafts','project','editor_import','evidence'].includes(key)?3:4;
  const groupKeys={3:['review','jianying','drafts','project','editor_import','evidence'],4:['materials','material_check','export','publish']};
  return `<ol class="studio-five-stages" aria-label="五阶段工作流程">${['准备素材','确认方案','自动制作','检查成品','发布准备'].map((label,i)=>{const skipped=f&&groupKeys[i]&&!stages(f).some(x=>groupKeys[i].includes(x.key||x.name)&&x.status!=='skipped');return `<li class="${skipped?'skipped':i<index?'done':i===index?'current':''}" ${i===index&&!skipped?'aria-current="step"':''}><span>${skipped?'—':i<index?icon('check'):i+1}</span><strong>${label}${skipped?'<small>本次跳过</small>':''}</strong></li>`;}).join('')}</ol>`;
 }
 function initialSelection(){if(ui.selectionReady)return;ui.selectionReady=true;for(const p of state.projects)if(selected.has(p.id)){ui.projectIds.add(p.id);p.videos.forEach(v=>ui.paths.add(v.path));}}
 function controls(f,compact=false){
  if(!f)return '';
  if(f.status==='completed')return '<div class="studio-flow-actions"><button class="button small" data-flow="view-output">查看成品</button></div>';
  const waiting=['waiting_action','waiting_confirmation','failed','interrupted','paused'].includes(f.status),s=stage(f),needs=waiting||['waiting_action','failed','interrupted','paused'].includes(s.status);
  return `<div class="studio-flow-actions">${!terminal.has(f.status)?`<button class="button small" data-flow="${needs?(s.key==='review'?'review-confirm':'continue'):'pause'}" data-id="${esc(f.id)}">${needs?(f.status==='paused'?'恢复流程':s.key==='review'?'我已检查成片，继续':'检查并继续'):'暂停流程'}</button>`:''}${compact?'':`<button class="button small" data-flow="visit" data-id="${esc(f.id)}">进入当前步骤</button>`}${!terminal.has(f.status)?`<button class="button subtle small" data-flow="cancel" data-id="${esc(f.id)}">停止流程</button>`:''}</div>`;
 }
 function flowDetail(f){
  if(!f)return '<div class="studio-flow-empty"><strong>选好素材后，一次启动整套制作</strong><p>软件会按所选步骤自动交接成品。这里逐项显示完成情况、当前任务和需要你补充的内容。</p></div>';
  const s=stage(f),completed=stages(f).filter(x=>x.status==='completed').length,skipped=stages(f).filter(x=>x.status==='skipped').length,pending=stages(f).length-completed-skipped;
  const ids=f.projectIds||f.ids||[],names=ids.map(id=>state.projects.find(p=>p.id===id)?.name||id).join('、'),raw=f.sourceVideoPaths||f.selectedPaths||[],paths=Array.isArray(raw)?raw:Object.values(raw).flat();
  return overview(f)+`<div class="studio-flow-heading"><div><span class="studio-flow-kicker">本次素材 · ${esc(names)}${paths.length?' · '+paths.length+' 集':''}</span><h2>${esc(s.label||'连续制作')}</h2><p>${esc(f.status==='completed'?'可查看成品和步骤明细，或准备下一批素材。':f.message||s.message||'按所选制作方案执行')}</p></div><span class="tag ${f.status==='completed'?'green':f.status==='failed'?'red':'gray'}">${esc(labels[f.status]||f.status)}</span></div><div class="studio-flow-total"><span>步骤完成情况</span><strong>已完成 ${completed} 步${skipped?` · 本次跳过 ${skipped} 步`:''}${pending?` · 待处理 ${pending} 步`:''}</strong></div>${controls(f)}<details class="studio-stage-details"><summary>查看各步完成情况与待补充项</summary><ol class="studio-flow-stages" aria-label="整套制作步骤">${stages(f).map((x,i)=>`<li class="${esc(x.status||'pending')}" ${(x.key||x.name)===f.currentStage?'aria-current="step"':''}><span class="studio-stage-marker">${x.status==='completed'?icon('check'):x.status==='skipped'?'—':i+1}</span><div><strong>${esc(x.label||x.name||x.key)}</strong><p>${esc(x.message||labels[x.status]||'等待前一步完成')}</p></div><span class="studio-stage-status">${esc(labels[x.status]||x.status||'待处理')}</span></li>`).join('')}</ol></details><p class="field-hint">${f.status==='completed'?'成品和实际记录保存在本机；发布与审核结果以官方后台为准。':'恢复后继续未完成的步骤；最终平台提交由本人确认。'}</p>`;
 }
 function projectListHTML(){return state.projects.length?state.projects.map(p=>`<article class="studio-project" data-flow-project-row="${esc(p.id)}" data-search="${esc((p.name+' '+p.videos.map(v=>v.name||'').join(' ')).toLowerCase())}"><div class="studio-project-heading"><label><input type="checkbox" data-flow-project="${esc(p.id)}" ${ui.projectIds.has(p.id)?'checked':''}><strong>${esc(p.name)}</strong></label><span>${p.videos.length} 集 · ${duration(p.videos.reduce((n,v)=>n+(v.duration||0),0))}</span></div><details><summary>自由选集 <span data-flow-project-count="${esc(p.id)}"></span></summary><div class="studio-episodes">${p.videos.map((v,i)=>`<label title="${esc(v.name||v.path)}"><input type="checkbox" data-flow-video="${esc(v.path)}" data-project="${esc(p.id)}" ${ui.paths.has(v.path)?'checked':''}><span>${esc(v.name||'第'+(i+1)+'集')}</span></label>`).join('')}</div></details></article>`).join(''):'<div class="studio-flow-empty"><strong>先导入一部剧的完整素材</strong><p>下载任务完成后会进入素材库，也可以直接导入本地素材文件夹。</p><a class="button primary" href="#scan">导入本地素材</a><a class="button" href="#sources">去采集素材</a></div>';}
 function accountsHTML(){return '<option value="">开始前选择发布账号</option>'+(state.accounts||[]).map(a=>`<option value="${esc(a.id)}" ${ui.options.accountId===a.id?'selected':''}>${esc(a.name||a.id)}</option>`).join('');}
 function option(key,label,description){return `<label class="studio-flow-option"><input type="checkbox" data-flow-option="${key}" ${ui.options[key]?'checked':''}><span><strong>${label}</strong><small>${description}</small></span></label>`;}
 function planSummary(){
  const c=state.config,steps=[];
  if(c.autoText)steps.push('AI 文案');if(c.subtitleAuto)steps.push('字幕修复');steps.push(c.regroup?'合并切分':'逐集画面处理');if(c.pipelineHighlight)steps.push('高光包装');if(c.autoCover)steps.push('封面');if(c.autoRecords)steps.push('制作记录');if(c.autoCost)steps.push('成本报告');
  const rows=[['film',steps.join(' → ')]];
  if(ui.options.reviewRequired)rows.push(['check','由我检查成片']);
  if(ui.options.withJianying)rows.push(['layers',ui.options.withEvidence?'剪映工程与真实截图':'剪映可编辑工程']);
  if(ui.options.withExport)rows.push(['upload','资料检查与导出']);else if(ui.options.withPublish)rows.push(['upload','发布资料检查']);
  if(ui.options.withPublish)rows.push(['external','官方后台辅助填写与本人确认']);
  return rows.map(([ico,text])=>`<span>${icon(ico)}${esc(text)}</span>`).join('');
 }
 function page(){
  initialSelection();const f=active();
  const setup=`<div class="studio-flow-layout"><section class="studio-flow-setup"><h2>选择素材</h2><p class="studio-panel-note">整剧或自由选集，只处理这次勾选的视频。</p><div class="studio-select-tools"><label for="studio-flow-query">搜索素材<input id="studio-flow-query" type="search" value="${esc(ui.query)}" placeholder="输入剧名或视频名"></label><div class="actions-row"><button class="button small" data-flow="select-all">全选素材</button><button class="button small" data-flow="clear-selection">清空选择</button><a href="#scan">导入素材</a></div></div><div id="studio-projects">${projectListHTML()}</div><p class="studio-selection-count" id="studio-selection-count"></p></section><section class="studio-flow-setup"><h2>确认方案</h2><p class="studio-panel-note">沿用已保存的制作参数，完成后自动交接下一步。</p><div class="studio-config-links"><a href="#preprocess">制作设置</a><a href="#subtitle">字幕区域</a><a href="#highlight">高光包装</a></div><div class="studio-plan-summary" id="studio-plan-summary">${planSummary()}</div><details class="studio-plan-details"><summary>调整后续步骤与发布账号</summary>${option('reviewRequired','先由我检查成片','开启后等待本人检查，再继续工程步骤。')}${option('withJianying','生成并导入剪映工程','使用本次制作的实际成片。')}${option('withEvidence','保存官方应用工程截图','来源和工程归属分别核对。')}${option('withExport','检查并导出提审资料','缺项时停在资料检查，补齐后继续。')}${option('withPublish','接着进入官方发布后台','检查登录、辅助填写，提交由本人确认。')}<div class="field studio-flow-account"><label for="studio-flow-account">本次发布账号</label><select id="studio-flow-account">${accountsHTML()}</select><p class="field-hint"><a href="#publish">管理发布账号与资料</a></p></div></details><div class="studio-start-block"><p id="studio-start-description">选择素材后即可开始。</p><p id="studio-flow-error" class="studio-flow-error" role="alert"></p></div><p class="studio-boundary-note">缺少素材、需要登录或本人核对时，流程会列出原因，保留已完成结果。</p></section></div>`;
  return intro('开始工作','选素材 → 确认方案 → 自动制作，完成一步就交接下一步。')+(f?`<section class="card studio-current-card"><div class="card-body" id="studio-flow-detail">${flowDetail(f)}</div></section><details class="studio-new-batch"><summary data-flow="prepare-next">准备下一批素材</summary>${setup}</details>`:`<div id="studio-flow-overview">${overview(null)}</div>`+setup+'<section id="studio-flow-detail" hidden></section>')+'<section class="studio-flow-history" id="studio-flow-history"></section>';
 }

 function setHTML(el,html,key){if(el&&el.dataset.flowSignature!==key){const opened=[...el.querySelectorAll('details')].map(d=>d.open),focus=document.activeElement?.closest('[data-flow]'),action=focus&&el.contains(focus)?focus.dataset.flow:'';el.innerHTML=html;el.dataset.flowSignature=key;[...el.querySelectorAll('details')].forEach((d,i)=>{if(opened[i])d.open=true;});if(action)el.querySelector(`[data-flow="${CSS.escape(action)}"]`)?.focus({preventScroll:true});}}
 function updateSelection(){
  const videos=selectedVideos(),projects=selectedProjects(),count=$('#studio-selection-count');if(count)count.textContent=`已选 ${projects.length} 部剧集 · ${videos.length} 集 · ${duration(videos.reduce((s,v)=>s+(v.duration||0),0))}`;
  setHTML($('#studio-flow-overview'),overview(null),String(videos.length>0));
  const plan=planSummary();setHTML($('#studio-plan-summary'),plan,plan);
  for(const p of state.projects){const n=p.videos.filter(v=>ui.paths.has(v.path)).length,b=$(`[data-flow-project="${CSS.escape(p.id)}"]`),c=$(`[data-flow-project-count="${CSS.escape(p.id)}"]`);if(b){b.checked=n>0;b.indeterminate=n>0&&n<p.videos.length;}if(c)c.textContent=`已选 ${n} / ${p.videos.length} 集`;}
  const description=$('#studio-start-description');if(description)description.textContent=videos.length?`本次按所选顺序制作 ${videos.length} 集；后续步骤使用本次成片。`:'请至少选择一部剧中的一集视频。';
  $$('[data-flow="start"]').forEach(b=>b.disabled=ui.busy||!videos.length);
  const account=$('.studio-flow-account');if(account)account.hidden=!ui.options.withPublish;
  const evidence=$('[data-flow-option="withEvidence"]');if(evidence)evidence.disabled=!ui.options.withJianying;
  const error=$('#studio-flow-error');if(error)error.textContent=ui.error;
  if(current==='studio')renderTaskbar();
 }
 function bindContext(f){
  const before=[focusId,typeof monitorId!=='undefined'?monitorId:'',typeof jianyingJob!=='undefined'?jianyingJob:'',typeof jyEvidenceProject!=='undefined'?jyEvidenceProject:''].join('|');
  const ids=f?.projectIds||f?.ids||[],result=stage(f).result||{},target=result.projectId||result.missingProjectIds?.[0]||result.missing?.[0]?.projectId||result.imports?.[0]?.projectId||ids[0],pid=ids.includes(target)?target:ids[0];if(pid)focusId=pid;
  const all=stages(f),production=all.find(x=>['production','produce'].includes(x.key||x.name)),draft=all.find(x=>['jianying','drafts','project'].includes(x.key||x.name));
  const refId=x=>x?.ref?.id||x?.ref?.ids?.[0]||x?.jobId||x?.result?.jobId;
  const job=refId(production);if(job&&typeof monitorId!=='undefined')monitorId=job;
  const jy=refId(draft);if(jy&&typeof jianyingJob!=='undefined')jianyingJob=jy;
  if(pid&&typeof jyEvidenceProject!=='undefined')jyEvidenceProject=pid;
  return before!==[focusId,typeof monitorId!=='undefined'?monitorId:'',typeof jianyingJob!=='undefined'?jianyingJob:'',typeof jyEvidenceProject!=='undefined'?jyEvidenceProject:''].join('|');
 }
 function go(f,force=false){
  if(!f)return;const destination=route(f),sequence=Number(f.sequence??f.routeVersion??0),old=ui.seen.get(f.id);ui.seen.set(f.id,sequence);
  if(!force&&(!ui.following||old===sequence))return;
  const changed=bindContext(f);if(!pages.some(p=>p[0]===destination))return;
  const hash='#'+destination;if(location.hash!==hash){ui.expectedHash=hash;location.hash=hash;}else if(force||changed){const y=window.scrollY;current=destination;renderPage();if(!force)window.scrollTo(0,y);}
 }
 function strip(){
  let el=$('#studio-flow-strip');if(!el){el=document.createElement('section');el.id='studio-flow-strip';el.className='studio-flow-strip';el.setAttribute('aria-label','连续流程状态');$('.topbar')?.after(el);}
  const f=active();el.hidden=!f;if(!f)return;
  const s=stage(f),signature=JSON.stringify([f.id,f.status,f.currentStage,f.message,s.message,s.status,ui.following]),done=f.status==='completed',completed=stages(f).filter(x=>x.status==='completed').length,skipped=stages(f).filter(x=>x.status==='skipped').length;
  const html=`<div class="studio-strip-state"><span class="studio-strip-dot ${terminal.has(f.status)?'done':''}"></span><div role="status" aria-live="polite"><strong>${done?'本次流程已完成':esc(s.label||'连续制作')+' · '+esc(labels[f.status]||f.status)}</strong><p>${done?`已完成 ${completed} 步${skipped?` · 本次跳过 ${skipped} 步`:''}`:esc(f.message||s.message||'正在按流程交接')}</p></div></div><div class="studio-strip-actions"><a class="button small" href="#studio">整套进度</a>${done?'':`<button class="button small" data-flow="follow" aria-pressed="${ui.following}">${ui.following?'暂停页面跟随':'继续跟随当前步骤'}</button>`}${controls(f,true)}</div>`;
  setHTML(el,html,signature);el.dataset.flowId=f.id;el.dataset.following=String(ui.following);
 }
 function update(){
  strip();if(current!=='studio')return;
  const f=active();setHTML($('#studio-flow-detail'),flowDetail(f),JSON.stringify(f));
  const inventory=JSON.stringify(state.projects.map(p=>[p.id,p.name,p.videos.map(v=>[v.path,v.name,v.duration])]));setHTML($('#studio-projects'),projectListHTML(),inventory);filterProjects();
  const history=$('#studio-flow-history'),rows=ui.flows.filter(x=>x.id!==f?.id).slice().reverse();
  setHTML(history,rows.length?`<h2>已有流程</h2>${rows.map(x=>`<article><div><strong>${esc(x.name||x.title||x.id)}</strong><p>${esc(labels[x.status]||x.status)} · ${esc(stage(x).label||'等待开始')}</p></div><button class="button small" data-flow="activate" data-id="${esc(x.id)}">查看此流程</button></article>`).join('')}`:'',JSON.stringify(rows));
  updateSelection();
 }
 async function load(){
  if(ui.pending)return ui.pending;
  ui.pending=(async()=>{try{const result=await api('studio-flows');ui.flows=result.flows||[];ui.activeFlowId=result.activeFlowId||ui.activeFlowId;const f=active();if(f){if(!ui.seen.has(f.id))ui.seen.set(f.id,Number(f.sequence??f.routeVersion??0));else go(f);}update();}catch(error){ui.error=error.message;update();}finally{ui.pending=null;}})();return ui.pending;
 }
 const baseRender=renderPage;renderPage=function(){document.body.classList.toggle('studio-route',current==='studio');if(current!=='studio'){const r=baseRender();strip();return r;}$('#content').innerHTML=page();$('#breadcrumb').textContent='开始工作';renderNav();renderTaskbar();update();filterProjects();};
 const baseTaskbar=renderTaskbar;renderTaskbar=function(){
  baseTaskbar();const b=$('#start-pipeline');if(current!=='studio'){delete b.dataset.flow;if(ui.flows.some(f=>f.id===b.dataset.id))delete b.dataset.id;return;}
  delete b.dataset.action;delete b.dataset.jianying;delete b.dataset.track;
  const f=active(),s=stage(f),ongoing=f&&!terminal.has(f.status),finished=f?.status==='completed'&&!ui.preparingNext,waiting=ongoing&&['waiting_action','waiting_confirmation','failed','interrupted','paused'].includes(f.status);
  b.dataset.flow=finished?'prepare-next':ongoing?(waiting?(s.key==='review'?'review-confirm':'continue'):'visit'):'start';
  if(ongoing)b.dataset.id=f.id;else delete b.dataset.id;
  b.innerHTML=icon(finished?'plus':ongoing?'layers':'play')+(finished?'准备下一批':ongoing?(waiting?(s.key==='review'?'我已检查成片，继续':f.status==='paused'?'恢复流程':'检查并继续'):'进入当前步骤'):'开始整套流程');
  b.disabled=ui.busy||(!finished&&!ongoing&&!selectedVideos().length);
  $('#task-title').textContent=finished?'本次流程已完成':ongoing?s.label||'连续制作流程':'连续制作流程';
  $('#task-detail').textContent=finished?'查看成品，或重新选择下一批素材':ongoing?f.message||s.message||'自动交接下一步':`已选 ${selectedProjects().length} 部 · ${selectedVideos().length} 集，自动交接下一步`;
 };

 const baseRefresh=refresh;refresh=async function(...args){const result=await baseRefresh(...args);await load();return result;};
 function filterProjects(){for(const row of $$('[data-flow-project-row]'))row.hidden=!row.dataset.search.includes(ui.query.toLowerCase());}
 window.addEventListener('hashchange',()=>{if(ui.expectedHash===location.hash){ui.expectedHash='';return;}ui.expectedHash='';ui.following=false;strip();});
 document.addEventListener('input',e=>{if(e.target.id==='studio-flow-query'){ui.query=e.target.value;filterProjects();}});
 document.addEventListener('change',e=>{
  const el=e.target;if(el.dataset.flowProject){const p=state.projects.find(x=>x.id===el.dataset.flowProject);if(p){if(el.checked){ui.projectIds.add(p.id);p.videos.forEach(v=>ui.paths.add(v.path));}else{ui.projectIds.delete(p.id);p.videos.forEach(v=>ui.paths.delete(v.path));}$$('[data-flow-video]',el.closest('.studio-project')).forEach(b=>b.checked=el.checked);}}
  if(el.dataset.flowVideo){el.checked?ui.paths.add(el.dataset.flowVideo):ui.paths.delete(el.dataset.flowVideo);const p=state.projects.find(x=>x.id===el.dataset.project);if(p?.videos.some(v=>ui.paths.has(v.path)))ui.projectIds.add(p.id);else ui.projectIds.delete(p?.id);}
  if(el.dataset.flowOption){ui.options[el.dataset.flowOption]=el.checked;if(el.dataset.flowOption==='withJianying'&&!el.checked){ui.options.withEvidence=false;const b=$('[data-flow-option="withEvidence"]');if(b)b.checked=false;}}
  if(el.id==='studio-flow-account')ui.options.accountId=el.value;
  if(el.dataset.flowProject||el.dataset.flowVideo||el.dataset.flowOption||el.id==='studio-flow-account')updateSelection();
 });
 document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-flow]');if(!b||b.disabled)return;const action=b.dataset.flow,f=active();
  if(action==='prepare-next'){
   if(b.tagName==='SUMMARY'&&ui.preparingNext)return;e.preventDefault();ui.preparingNext=true;ui.projectIds.clear();ui.paths.clear();$$('[data-flow-video]').forEach(x=>x.checked=false);updateSelection();
   const next=$('.studio-new-batch');if(next){next.open=true;next.scrollIntoView({block:'start',behavior:'auto'});}return;
  }
  if(action==='view-output'){ui.following=false;bindContext(f);if(location.hash!=='#progress'){ui.expectedHash='#progress';location.hash='#progress';}else{current='progress';renderPage();}strip();return;}
  if(action==='follow'){ui.following=!ui.following;if(ui.following)go(f,true);strip();return;}
  if(action==='visit'){ui.following=true;go(f,true);strip();return;}
  if(action==='clear-selection'||action==='select-all'){ui.projectIds.clear();ui.paths.clear();if(action==='select-all')for(const p of state.projects){ui.projectIds.add(p.id);p.videos.forEach(v=>ui.paths.add(v.path));}$$('[data-flow-video]').forEach(x=>x.checked=ui.paths.has(x.dataset.flowVideo));updateSelection();return;}
  if(ui.busy)return;ui.busy=true;ui.error='';b.disabled=true;updateSelection();
  try{
   let result;
   if(action==='start'){
    const projects=selectedProjects(),videos=selectedVideos();if(!videos.length)throw Error('请先选择素材');if(ui.options.withPublish&&!ui.options.accountId)throw Error('请选择本次发布账号，或关闭进入发布后台');
    const sourceVideoPaths=Object.fromEntries(projects.map(p=>[p.id,p.videos.filter(v=>ui.paths.has(v.path)).map(v=>v.path)]));
    selected=new Set(projects.map(p=>p.id));result=await api('studio-flows/start',{projectIds:projects.map(p=>p.id),sourceVideoPaths,options:{...ui.options}});
    ui.activeFlowId=result.flow?.id||result.id||result.flowId||result.activeFlowId||ui.activeFlowId;ui.following=true;ui.preparingNext=false;
   }else{
    const id=b.dataset.id||f?.id;if(!id)return;
    const controlAction=action==='review-confirm'?'continue':action==='continue'&&f?.status==='paused'?'resume':action;
    result=await api('studio-flows/control',{id,action:controlAction,...(action==='review-confirm'?{reviewConfirmed:true}:{})});
    if(action==='activate'){ui.activeFlowId=id;ui.following=true;ui.preparingNext=false;}
    if(['continue','review-confirm'].includes(action))ui.following=true;
   }
   await load();if(['start','activate','continue','review-confirm'].includes(action))go(active(),true);toast(action==='start'?'连续流程已启动':'流程状态已更新');
  }catch(error){ui.error=error.message;toast(error.message,true);}finally{ui.busy=false;if(b.isConnected)b.disabled=false;update();renderTaskbar();}
 });
})();
