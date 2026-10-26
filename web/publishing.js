'use strict';
// Keep publishing drafts independent of the polling state. Typing and IME input
// must not replace the form, move its caret, or reset its scroll position.
(()=>{
 const model={tab:'drama',workspace:null,drafts:new Map(),dirty:new Set(),plans:new Map(),accountId:'',browser:null,notice:'',loading:false,polling:false,importRows:[],importSelected:new Set(),busy:false};
 const attachmentGroups=[
  ['coverPath','封面','image','cover','封面图片'],
  ['proofImages','官方工程截图','images','proofImages','从剪映或即梦的实际工程窗口采集，并核对截图归属；手动导入的图片来源仍待核验'],
  ['storyboardImages','分镜证明图片','images','storyboardImages','按本地检查方案准备至少 4 张，平台要求以当前后台为准'],
  ['costImages','成本报告图片','images','costImages','将实际制作成本报告保存为图片后选择'],
  ['copyrightImages','授权证明图片','images','copyrightImages','选择与本剧对应的真实授权资料'],
  ['costReportPaths','成本报告文件','documents','costReports','可选择已有的报告文档或表格']
 ];
 const project=()=>activeProject();
 const pid=()=>project()?.id||'';
 const plan=()=>model.plans.get(pid())||model.workspace?.plans?.[pid()];
 function savedFor(id){const settings=model.workspace?.settings||{};return settings.projects?.[id]||settings[id]||{};}
 function draft(){
  const p=project();if(!p)return {};
  if(!model.drafts.has(p.id)){
   const f=model.plans.get(p.id)?.fields||model.workspace?.plans?.[p.id]?.fields||{};
   model.drafts.set(p.id,{title:f.title||p.name||'',synopsis:f.synopsis??p.intro??'',producer:f.producer||'',trialEpisodes:f.trialEpisodes??1,dramaType:f.dramaType||'animation',episodeCount:f.episodeCount??'',totalCostYuan:f.totalCostYuan??'',rightsConfirmed:f.rightsConfirmed??!!p.rights,...savedFor(p.id)});
  }
  return model.drafts.get(p.id);
 }
 function updateDraft(key,value){if(!pid())return;draft()[key]=value;model.dirty.add(pid());const saved=$('#publishing-save-state');if(saved)saved.textContent='有未保存的修改';}
 const statusLabel=s=>({submitted:'已提交 · 本人记录',approved:'审核通过 · 本人记录',needs_changes:'需修改 · 本人记录'}[s]||s||'待准备');
 function records(){return (model.workspace?.records||[]).filter(x=>x.projectId===pid());}
 function fieldHTML(label,key,{type='text',min,max,step,hint='',textarea=false,required=false}={}){
  const d=draft(),id='publishing-'+key,extra=`${required?'required ':''}${min!==undefined?`min="${min}" `:''}${max!==undefined?`max="${max}" `:''}${step!==undefined?`step="${step}" `:''}`;
  return `<div class="field" id="publishing-field-${key}"><label for="${id}">${label}${required?'<span class="publishing-required">必填</span>':''}</label>${textarea?`<textarea id="${id}" data-publishing-field="${key}" rows="4" ${extra}>${esc(d[key]??'')}</textarea>`:`<input id="${id}" data-publishing-field="${key}" type="${type}" value="${esc(d[key]??'')}" ${extra}>`}${hint?`<p class="field-hint">${esc(hint)}</p>`:''}<p class="publishing-inline-error" id="${id}-error" hidden></p></div>`;
 }
 function stepsHTML(){
  const p=plan(),latest=records().at(-1),browser=model.browser;
  let index=!pid()?0:!p?.ready?1:latest?4:browser?.state==='awaiting_confirmation'?3:2;
  return `<ol class="publishing-steps" aria-label="短剧提审步骤">${['选择剧目','资料检查','后台填表','本人确认','结果记录'].map((label,i)=>`<li ${i===index?'aria-current="step"':''} class="${i<index?'done':i===index?'current':''}"><span>${i<index?icon('check'):i+1}</span><strong>${label}</strong></li>`).join('')}</ol>`;
 }
 function planHTML(){
  const p=plan();
  if(!p)return `<div class="publishing-empty">${icon('shield')}<strong>先检查这部剧的提审资料</strong><p>读取真实成片、封面和制作资料，列出待补充项。原始素材不会自动作为发布成片。</p></div>`;
  const checks=p.checks||[],ready=checks.filter(c=>c.status==='ready').length,missing=checks.filter(c=>c.status==='missing').length;
  const stale=model.dirty.has(pid());
  return `<div class="publishing-check-overview"><div><strong>${stale?'资料已修改，待重新检查':p.ready?'资料已齐全':'资料待补充'}</strong><p>${stale?'下方保留上次检查结果，请保存并重新检查。':`${ready} 项已准备${missing?` · ${missing} 项待补充`:''} · 检查不代表平台审核通过`}</p></div><span class="tag ${p.ready&&!stale?'green':'gray'}">${stale?'待重新检查':p.ready?'可进入后台':'先补齐资料'}</span></div>`+
   `<div class="publishing-checks">${checks.map(c=>`<div class="publishing-check ${esc(c.status)}"><span class="publishing-check-icon">${icon(c.status==='ready'?'check':c.status==='missing'?'clock':'info')}</span><div><strong>${esc(c.label)}</strong><p>${esc(c.message||'')}</p></div><span class="tag ${c.status==='ready'?'green':'gray'}">${{ready:'已准备',missing:'待补充',warning:'需核对'}[c.status]||'需核对'}</span>${c.status==='ready'?'':c.key==='proofImages'?'<a class="button small" href="#tracks">去采集官方截图</a>':`<button class="button small" data-publishing="locate" data-key="${esc(c.key)}">查看</button>`}</div>`).join('')}</div>`+
   ((p.warnings||[]).length?`<details class="publishing-warnings"><summary>${p.warnings.length} 条需要核对的提示</summary><ul>${p.warnings.map(x=>`<li>${esc(typeof x==='string'?x:x.message||JSON.stringify(x))}</li>`).join('')}</ul></details>`:'')+
   `<details class="publishing-video-inventory" id="publishing-videos" tabindex="-1"><summary>本次正片视频 · ${(p.files?.videos||[]).length} 集</summary><p class="field-hint">这里只列出确认的成片。需要重新合并切分时，先返回视频处理完成制作。</p><div class="publishing-selected-files">${attachmentFilesHTML('videos',p.files?.videos||[])}</div>${p.files?.videos?.length?'':'<a class="button small" href="#preprocess">去准备正片</a>'}</details>`;
 }
 function attachmentHTML([key,label,,fileKey,hint]){
  const selected=draft()[key],files=plan()?.files?.[fileKey],items=key==='coverPath'?(selected?[{path:selected}]:files?[files]:[]):Array.isArray(selected)?selected.map(path=>({path})):Array.isArray(files)?files:[];
  return `<div class="publishing-attachment" id="publishing-field-${key}"><div><h3>${label}</h3><p>${hint}</p></div>${key==='proofImages'?'<a class="button small" href="#tracks">打开真实工程与截图</a>':''}<div class="actions-row"><span id="publishing-count-${key}" class="publishing-file-count">${items.length} 个</span><button class="button small" data-publishing="attachment" data-key="${key}">${icon('plus')}选择文件</button><button class="button small" data-publishing="clear-attachment" data-key="${key}">清除</button></div><div class="publishing-selected-files" id="publishing-files-${key}">${attachmentFilesHTML(key,items)}</div><p class="publishing-inline-error" id="publishing-${key}-error" hidden></p></div>`;
 }
 function attachmentFilesHTML(key,items){return items.map(f=>`<div><span title="${esc(f.path||'')}">${esc(f.name||String(f.path||'').split(/[\\/]/).at(-1))}</span><a class="button small" href="/api/publish/file?projectId=${encodeURIComponent(pid())}&path=${encodeURIComponent(f.path||'')}" target="_blank" rel="noreferrer" aria-label="查看${esc(f.name||key)}">查看</a></div>`).join('');}
 function formHTML(){return `<form id="publishing-form" novalidate><div class="publishing-form-grid">${fieldHTML('剧名','title',{required:true})}${fieldHTML('制作方名称','producer',{required:true})}<div class="publishing-wide">${fieldHTML('剧集简介','synopsis',{textarea:true,required:true})}</div>${fieldHTML('总集数','episodeCount',{type:'number',min:1,max:10000,required:true,hint:'应与本次整剧成片清单一致'})}${fieldHTML('制作成本（元）','totalCostYuan',{type:'number',min:0,step:.01,required:true,hint:'填写实际金额，不自动编造制作成本'})}${fieldHTML('试看集数','trialEpisodes',{type:'number',min:1,max:10000,required:true})}<div class="field" id="publishing-field-dramaType"><label for="publishing-dramaType">剧目类型</label><select id="publishing-dramaType" data-publishing-field="dramaType"><option value="animation" ${draft().dramaType==='animation'?'selected':''}>漫剧</option><option value="digital" ${draft().dramaType==='digital'?'selected':''}>数字真人</option></select></div></div><label class="check-label publishing-rights" id="publishing-field-rightsConfirmed"><input id="publishing-rightsConfirmed" type="checkbox" data-publishing-field="rightsConfirmed" ${draft().rightsConfirmed?'checked':''}>我已核对本剧的制作与发布授权，上传资料真实有效</label><p class="publishing-inline-error" id="publishing-rightsConfirmed-error" hidden></p><details class="publishing-attachments"><summary>封面与提审附件 · 查看或补充</summary><p class="field-hint">复用已生成的真实文件，也可手动补充。仿真时间线图片不会被当成真实剪映工程截图。</p>${attachmentGroups.map(attachmentHTML).join('')}</details><div class="publishing-form-footer"><span id="publishing-save-state" role="status">${model.dirty.has(pid())?'有未保存的修改':'配置保存在本机'}</span><button type="button" class="button" data-publishing="save">${icon('save')}保存资料</button><button type="button" class="button primary" data-publishing="inspect">${icon('shield')}保存并检查</button></div></form>`;}
 function browserHTML(){
  const accounts=state.accounts||[];
  if(!model.accountId||!accounts.some(a=>a.id===model.accountId))model.accountId=accounts[0]?.id||'';
  if(!model.browser)model.browser=model.workspace?.browser?.[model.accountId]||null;
  return `<div class="publishing-account-row"><div class="field"><label for="publishing-account">本次提审账号</label><select id="publishing-account" ${accounts.length?'':'disabled'}>${accounts.length?accounts.map(a=>`<option value="${esc(a.id)}" ${a.id===model.accountId?'selected':''}>${esc(a.name)} · ${esc(a.type||'视频号')}</option>`).join(''):'<option>请先添加账号</option>'}</select></div><button class="button" data-publishing="browser-open" ${model.accountId?'':'disabled'}>${icon('external')}打开官方后台</button><button class="button" data-publishing="browser-check" ${model.accountId?'':'disabled'}>${icon('refresh')}检测当前页面</button></div><details class="publishing-add-account"><summary>添加账号备注</summary><div class="publishing-account-row"><div class="field"><label for="publishing-account-name">账号备注名称</label><input id="publishing-account-name" autocomplete="off" placeholder="例如：主账号"></div><button class="button" data-publishing="add-account">${icon('plus')}添加账号</button></div><p class="field-hint">本人在官方页面扫码。提审浏览器资料目录与普通视频上传登录态分别保存。</p></details><div id="publishing-browser-status" class="publishing-browser-status" role="status" aria-live="polite">${browserStatusHTML()}</div><div class="publishing-confirm-note">${icon('info')}<p>在后台打开新增剧目或提审表单后，再辅助填写。填写完成后由本人核对资料并在官方页面确认提交。</p></div><div class="actions-row"><button class="button primary" data-publishing="browser-assist" ${!model.accountId||!plan()?.ready?'disabled':''}>${icon('text')}辅助填写与上传</button><button class="button" data-publishing="browser-close" ${model.accountId?'':'disabled'}>关闭提审窗口</button></div>`;
 }
 function browserStatusHTML(){
  const b=model.browser;if(!b)return '<strong>等待打开后台</strong><p>打开后本人扫码，再检测当前页面的登录状态与可填项。</p>';
  const label=({awaiting_confirmation:'辅助填写结束，等待本人确认',needs_login:'需要本人扫码登录',needs_navigation:'请在后台打开提审表单'}[b.state])||{authenticated:'已识别登录状态',login_required:'需要本人扫码登录',unknown:'当前页面状态待确认'}[b.loginState]||'后台检查结果';
  const filled=b.filled||[],pending=b.pending||[],blockers=b.blockers||[];
  return `<strong>${esc(label)}</strong>${b.pageUrl?`<p class="publishing-page-url">${esc(b.pageUrl)}</p>`:''}${b.message?`<p>${esc(b.message)}</p>`:''}${filled.length?`<p>已处理：${filled.map(x=>esc(typeof x==='string'?x:x.label||x.field||x.key||'字段')).join('、')}</p>`:''}${pending.length?`<p>请本人核对或补充：${pending.map(x=>esc(typeof x==='string'?x:x.label||x.message||x.field||'字段')).join('、')}</p>`:''}${blockers.length?`<ul>${blockers.map(x=>`<li>${esc(typeof x==='string'?x:x.message||'请检查平台提示')}</li>`).join('')}</ul>`:''}<p class="field-hint">此处检测页面与操作状态，不自动认定平台审核通过。</p>`;
 }
 function resultHTML(){return `<p class="section-description">在官方后台核对后记录结果。记录会保留账号、时间和说明，来源标记为本人核对。</p><div class="publishing-form-grid"><div class="field"><label for="publishing-result-status">官方后台实际状态</label><select id="publishing-result-status"><option value="submitted">已提交</option><option value="needs_changes">需修改</option><option value="approved">审核通过</option></select></div><div class="field"><label for="publishing-result-url">后台记录或作品链接（可选）</label><input id="publishing-result-url" type="url" placeholder="https://…"></div><div class="publishing-wide field"><label for="publishing-result-note">核对说明</label><textarea id="publishing-result-note" rows="2" placeholder="填写后台提示、剧目编号或修改要求"></textarea></div></div><button class="button" data-publishing="record">保存本人核对结果</button><div id="publishing-records" class="publishing-records">${recordRowsHTML()}</div>`;}
 function recordRowsHTML(){const rows=records().slice().reverse();return rows.length?rows.map(r=>`<div class="publishing-record"><span class="tag ${r.status==='approved'?'green':'gray'}">${esc(statusLabel(r.status))}</span><div><strong>${esc(r.accountName||state.accounts.find(a=>a.id===r.accountId)?.name||'已移除账号')}</strong><p>${esc(r.note||'')}</p><small>${esc(r.createdAt?new Date(r.createdAt*1000).toLocaleString('zh-CN'):r.time||'')} · 本人核对记录</small></div></div>`).join(''):'<p class="blank-inline">尚无结果记录。完成本地检查后仍需到官方后台提交与核对。</p>';}
 function importHTML(){return `<details class="publishing-import"><summary>${icon('folder')}从已有成品目录导入</summary><p class="field-hint">选择一部剧的成品根目录或包含多部剧的总目录。将先展示识别结果，再由你勾选导入。</p><div class="publishing-folder-row"><div class="field"><label for="publishing-folder">成品目录</label><input id="publishing-folder" placeholder="选择包含剧目资料的文件夹"></div><button class="button" data-publishing="choose-folder">${icon('folder')}选择目录</button><button class="button" data-publishing="discover">识别剧目</button></div><div id="publishing-candidates"></div></details>`;}
 function dramaHTML(){const p=project();return `<div class="publishing-steps-host">${stepsHTML()}</div>`+card('选择提审剧目','layers',`<div class="publishing-selection"><div class="field"><label for="publishing-project">剧目</label><select id="publishing-project">${state.projects.length?state.projects.map(x=>`<option value="${esc(x.id)}" ${x.id===pid()?'selected':''}>${esc(x.name)}</option>`).join(''):'<option value="">请先导入或制作剧目</option>'}</select></div><button class="button" data-publishing="inspect" ${p?'':'disabled'}>${icon('shield')}检查资料</button></div>${importHTML()}`,'已有剧目直接检查；外部目录先核对识别结果')+
  (p?`<div id="publishing-errors" class="publishing-error-summary" tabindex="-1" hidden></div><div class="publishing-layout"><div class="publishing-main">${card('补充提审资料','text',formHTML(),'填写实际信息，附件按用途对应保存')}</div><div class="publishing-side">${card('资料检查清单','shield',`<div id="publishing-check-result" aria-live="polite">${planHTML()}</div><div class="actions-row"><button class="button" data-publishing="export" ${plan()?.ready?'':'disabled'}>${icon('download')}导出提审资料目录</button><button class="button small" data-publishing="open-files">打开成品目录</button></div>`,'检查结果来自当前文件与填写信息')}</div></div>`+card('官方后台辅助提审','external',browserHTML(),'按账号打开独立窗口，识别当前页面后辅助填写')+`<div id="publishing-task-status" aria-live="polite">${tasksHTML()}</div>`+card('本人核对与结果记录','log',resultHTML()):`<div class="publishing-empty"><strong>先准备一部剧</strong><p>可从上方导入成品目录，或到本地素材完成制作。</p><a href="#scan" class="button primary">打开本地素材</a></div>`);}
 function tasksHTML(){
  const rows=(model.workspace?.tasks||[]).filter(t=>t.projectId===pid()).slice(-6).reverse();if(!rows.length)return '';
  return card('提审准备任务','cpu',`<div class="publishing-tasks">${rows.map(t=>`<div class="publishing-task"><span class="tag ${t.status==='completed'?'green':'gray'}">${esc({queued:'排队中',running:'正在处理',completed:'操作完成',failed:'操作失败',interrupted:'已中断'}[t.status]||t.status)}</span><div><strong>${esc({export:'导出提审资料',browser_open:'打开官方后台',browser_check:'检测后台页面',browser_assist:'辅助填写与上传',browser_close:'关闭后台窗口'}[t.kind]||t.kind)}</strong><p>${esc(t.error||t.stage||'')}</p>${t.totalBytes>0?`<progress max="100" value="${Math.max(0,Math.min(100,Number(t.percent)||0))}" aria-label="导出资料复制进度"></progress><small>${esc(size(t.completedBytes||0))} / ${esc(size(t.totalBytes))}</small>`:''}${t.result?.directory?`<small>${esc(t.result.directory)}</small><button class="button small" data-publishing="open-task" data-task="${esc(t.id)}">打开资料目录</button>`:''}</div></div>`).join('')}</div>`,'操作完成仍需本人在官方页面核对提交结果');
 }
 function sliceHTML(){return card('切片发布剧目','layers',picker(),'选择已生成普通视频成片的剧目')+uploadPanel()+card('短剧推广挂载','link','<p class="section-description">需要关联全集入口时，在推广挂载工作区核对钩子素材和推广入口。</p><a class="button" href="#promotion">打开推广挂载工作区</a>');}
 publishPage=function(){return `<div class="publishing-route" data-publishing-project="${esc(pid())}" data-publishing-tab="${model.tab}">`+intro('发布与提审','整理提审资料，连接官方后台，逐项核对提交结果。')+`<div class="publishing-tabs" role="tablist" aria-label="发布类型"><button type="button" role="tab" id="publishing-tab-drama" aria-controls="publishing-panel" aria-selected="${model.tab==='drama'}" data-publishing="tab" data-tab="drama">短剧提审</button><button type="button" role="tab" id="publishing-tab-slice" aria-controls="publishing-panel" aria-selected="${model.tab==='slice'}" data-publishing="tab" data-tab="slice">切片分发</button></div><div id="publishing-notice" role="status" aria-live="polite">${esc(model.notice)}</div><div id="publishing-panel" role="tabpanel" aria-labelledby="publishing-tab-${model.tab}">${model.tab==='drama'?dramaHTML():sliceHTML()}</div></div>`;};
 const originalRender=renderPage;
 const originalTaskbar=renderTaskbar;
 renderTaskbar=function(){
  originalTaskbar();
  const button=$('#start-pipeline');if(!button)return;
  delete button.dataset.publishing;
  if(current!=='publish')return;
  $('#task-title').textContent=model.tab==='drama'?'短剧提审准备':'切片分发';
  $('#task-detail').textContent=project()?`${project().name} · ${model.tab==='drama'?'先检查资料，再到官方后台本人确认':'普通视频上传，提交前核对清单'}`:'选择或导入一部剧目';
  if(model.tab==='drama'){delete button.dataset.action;button.dataset.publishing='inspect';button.innerHTML=icon('shield')+'保存并检查资料';button.disabled=!pid()||model.busy;}
  else{button.dataset.action='upload-review';button.innerHTML=icon('upload')+'核对并上传';button.disabled=!pid()||!!busy();}
 };
 renderPage=function(){
  if(current!=='publish')return originalRender();
  const mounted=$('.publishing-route');
  if(mounted&&mounted.dataset.publishingProject===pid()&&mounted.dataset.publishingTab===model.tab){renderNav();renderTaskbar();updatePanels();return;}
  originalRender();loadWorkspace();
 };
 function redraw(){const y=window.scrollY;$('#content').innerHTML=publishPage();renderNav();renderTaskbar();window.scrollTo(0,y);}
 function updatePanels(){
  if(current!=='publish'||!$('.publishing-route'))return;
  const check=$('#publishing-check-result');if(check)check.innerHTML=planHTML();
  const browser=$('#publishing-browser-status');if(browser)browser.innerHTML=browserStatusHTML();
  const rec=$('#publishing-records');if(rec)rec.innerHTML=recordRowsHTML();
  const tasks=$('#publishing-task-status');if(tasks)tasks.innerHTML=tasksHTML();
  const steps=$('.publishing-steps-host');if(steps)steps.innerHTML=stepsHTML();
  const note=$('#publishing-notice');if(note)note.textContent=model.notice;
  $$('[data-publishing="browser-assist"]').forEach(b=>b.disabled=model.busy||!model.accountId||!plan()?.ready||model.dirty.has(pid()));
  $$('[data-publishing="export"]').forEach(b=>b.disabled=model.busy||!plan()?.ready||model.dirty.has(pid()));
  renderTaskbar();
 }
 async function loadWorkspace(){
  if(model.loading)return;model.loading=true;
  try{
   const result=await api('publish/workspace');model.workspace=result;model.browser=result.browser?.[model.accountId]||model.browser;
   for(const [id,p] of Object.entries(result.plans||{}))if(!model.dirty.has(id))model.plans.set(id,p);
   // Populate saved fields only on initial load. Never replace an active draft.
   const id=pid();if(id&&!model.dirty.has(id)){
    model.drafts.delete(id);
    const form=$('#publishing-form');
    if(form&&!form.contains(document.activeElement)){const y=window.scrollY;form.outerHTML=formHTML();window.scrollTo(0,y);}
   }
   updatePanels();
  }catch(e){model.notice=e.message;updatePanels();}finally{model.loading=false;}
 }
 async function pollTasks(){
  if(model.polling||model.loading||current!=='publish'||model.tab!=='drama')return;
  const pending=(model.workspace?.tasks||[]).some(t=>['queued','running'].includes(t.status));if(!pending)return;
  model.polling=true;
  try{const result=await api('publish/workspace');model.workspace=result;model.browser=result.browser?.[model.accountId]||model.browser;updatePanels();}
  catch(e){model.notice='任务状态读取中断：'+e.message;updatePanels();}finally{model.polling=false;}
 }
 function showErrors(messages){const el=$('#publishing-errors');if(!el)return;el.hidden=!messages.length;el.setAttribute('role','alert');el.innerHTML=messages.length?`<h3>请先补充这些资料</h3><ul>${messages.map(x=>`<li>${esc(typeof x==='string'?x:x.message||'资料不完整')}</li>`).join('')}</ul>`:'';if(messages.length)el.focus();}
 async function saveAndInspect(focusErrors=false){
  const id=pid();if(!id)throw new Error('请先选择剧目');
  const overrides=structuredClone(draft());
  await api('publish/settings',{projectId:id,overrides});
  const result=await api('publish/inspect',{projectId:id});
  model.plans.set(id,result);model.dirty.delete(id);
  if(id!==pid())return result;
  const saved=$('#publishing-save-state');if(saved)saved.textContent='资料已保存到本机';
  $$('[data-publishing-field]').forEach(el=>{el.removeAttribute('aria-invalid');el.removeAttribute('aria-describedby');});
  $$('.publishing-inline-error').forEach(el=>el.hidden=true);
  for(const c of result.checks||[]){if(c.status!=='missing')continue;const key=fieldForCheck(c.key),input=$('#publishing-'+key),error=$('#publishing-'+key+'-error');if(error){error.textContent=c.message||'请补充这一项';error.hidden=false;if(input){input.setAttribute('aria-invalid','true');input.setAttribute('aria-describedby',error.id);}}}
  model.notice=result.ready?'资料检查完成，可打开官方后台辅助填写。':'资料检查完成，请按清单补齐后重新检查。';
  updatePanels();if(focusErrors)showErrors(result.errors||[]);return result;
 }
 function fieldForCheck(key){const map={name:'title',intro:'synopsis',synopsis:'synopsis',rights:'rightsConfirmed',rightsConfirmed:'rightsConfirmed',episodes:'episodeCount',video:'videos',cost:'totalCostYuan',totalCost:'totalCostYuan',producer:'producer',trial:'trialEpisodes',cover:'coverPath',proof:'proofImages',projectProof:'proofImages',storyboard:'storyboardImages',costReport:'costReportPaths',costReports:'costReportPaths',copyright:'copyrightImages'};return map[key]||key;}
 function locate(key){key=fieldForCheck(key);const el=$('#publishing-'+key)||$('#publishing-field-'+key)||$('#publishing-form');if(!el)return;el.closest('details')?.setAttribute('open','');el.scrollIntoView({block:'center',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth'});if(!el.matches('input,textarea,select,button')){el.setAttribute('tabindex','-1');}el.focus({preventScroll:true});}
 function candidatesHTML(){const rows=model.importRows;return rows.length?`<div class="publishing-candidate-summary"><strong>识别到 ${rows.length} 部剧目</strong><button class="button small" data-publishing="select-candidates">全选</button></div><div class="publishing-candidates">${rows.map((x,i)=>`<label><input type="checkbox" data-publishing-candidate="${i}" ${model.importSelected.has(i)?'checked':''}><span><strong>${esc(x.title||'未命名剧目')}</strong><small>${esc(x.folder)} · ${x.videoCount??'待检查'} 个视频</small>${x.warning?`<small>${esc(x.warning)}</small>`:''}</span></label>`).join('')}</div><button class="button primary" data-publishing="import">导入勾选剧目</button>`:'<p class="blank-inline">没有识别到剧目，请选择包含成片与资料的根目录。</p>';}
 document.addEventListener('input',e=>{const el=e.target;if(el.dataset.publishingField){updateDraft(el.dataset.publishingField,el.type==='checkbox'?el.checked:el.type==='number'?(el.value===''?'':Number(el.value)):el.value);updatePanels();}});
 document.addEventListener('change',e=>{const el=e.target;if(el.dataset.publishingField){updateDraft(el.dataset.publishingField,el.type==='checkbox'?el.checked:el.type==='number'?(el.value===''?'':Number(el.value)):el.value);updatePanels();}if(el.id==='publishing-project'){focusId=el.value;model.browser=null;model.notice='';redraw();}if(el.id==='publishing-account'){model.accountId=el.value;model.browser=null;updatePanels();}if(el.dataset.publishingCandidate!==undefined){const n=Number(el.dataset.publishingCandidate);el.checked?model.importSelected.add(n):model.importSelected.delete(n);}});
 document.addEventListener('submit',e=>{if(e.target.id==='publishing-form'){e.preventDefault();$('#publishing-form [data-publishing="inspect"]')?.click();}});
 document.addEventListener('keydown',e=>{const b=e.target.closest('[role="tab"][data-publishing]');if(!b||!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;e.preventDefault();model.tab=(e.key==='Home'||e.key==='ArrowLeft')?'drama':'slice';redraw();$('#publishing-tab-'+model.tab)?.focus();});
 document.addEventListener('click',async e=>{
  const b=e.target.closest('[data-publishing]');if(!b||model.busy)return;
  const action=b.dataset.publishing;
  if(action==='tab'){model.tab=b.dataset.tab;redraw();return;}
  if(action==='locate'){locate(b.dataset.key);return;}
  model.busy=true;const old=b.innerHTML;b.disabled=true;
  try{
   if(action==='save'){await api('publish/settings',{projectId:pid(),overrides:structuredClone(draft())});model.notice='资料已保存。请重新检查后再进入后台。';const status=$('#publishing-save-state');if(status)status.textContent='资料已保存，待重新检查';}
   else if(action==='inspect'){await saveAndInspect(true);}
   else if(action==='attachment'){
    const group=attachmentGroups.find(x=>x[0]===b.dataset.key),r=await api('browse',{mode:group[2]});
    const paths=r.paths||(r.path?[r.path]:[]);if(paths.length){const key=group[0];updateDraft(key,key==='coverPath'?paths[0]:[...new Set([...(draft()[key]||[]),...paths])]);const items=(key==='coverPath'?[draft()[key]]:draft()[key]).map(path=>({path}));$('#publishing-files-'+key).innerHTML=attachmentFilesHTML(key,items);$('#publishing-count-'+key).textContent=items.length+' 个';model.notice='附件已选择，保存并检查后确认文件可用。';}
   }else if(action==='clear-attachment'){const key=b.dataset.key;updateDraft(key,key==='coverPath'?'':[]);$('#publishing-files-'+key).innerHTML='';$('#publishing-count-'+key).textContent='0 个';model.notice='已清除本项手动附件选择，请重新检查。';}
   else if(action==='choose-folder'){const r=await api('browse',{mode:'folder'});if(r.path)$('#publishing-folder').value=r.path;}
   else if(action==='discover'){const folder=$('#publishing-folder').value.trim();if(!folder)throw new Error('请先选择成品根目录');const r=await api('publish/discover',{folder});model.importRows=r.candidates||[];model.importSelected=new Set(model.importRows.map((_,i)=>i));$('#publishing-candidates').innerHTML=candidatesHTML();model.notice='请核对剧名与目录，再导入勾选剧目。';}
   else if(action==='select-candidates'){model.importSelected=new Set(model.importRows.map((_,i)=>i));$('#publishing-candidates').innerHTML=candidatesHTML();}
   else if(action==='import'){const folders=[...model.importSelected].map(i=>model.importRows[i]?.folder).filter(Boolean);if(!folders.length)throw new Error('请勾选要导入的剧目');const r=await api('publish/import',{folders});await refresh();focusId=r.projectIds?.[0]||focusId;model.notice='剧目已导入，请检查资料清单。';redraw();await loadWorkspace();}
   else if(action==='export'){const r=await api('publish/export',{projectId:pid()});model.notice=r.directory?'已导出提审资料目录：'+r.directory:'资料导出已加入任务，请保留源文件。';await loadWorkspace();}
   else if(action==='open-files'){await api('publish/open',{projectId:pid()});}
   else if(action==='open-task'){await api('publish/open',{projectId:pid(),taskId:b.dataset.task});}
   else if(action==='add-account'){const name=$('#publishing-account-name').value.trim();if(!name)throw new Error('请填写账号备注名称');const r=await api('accounts',{name,type:'剧集提审',channelId:''});model.accountId=r.id;await refresh();redraw();model.notice='账号备注已添加，请打开官方后台本人扫码。';}
   else if(action.startsWith('browser-')){
    if(!model.accountId)throw new Error('请先选择提审账号');
    const browserAction=action.slice(8);
    if(browserAction==='assist'){const p=await saveAndInspect(true);if(!p.ready)throw new Error('提审资料尚未齐全，请先补充缺项');}
    model.notice=browserAction==='assist'?'正在识别当前表单并辅助填写，请保留后台窗口。':'正在检查官方后台窗口…';updatePanels();
    const result=await api('publish/browser',{accountId:model.accountId,action:browserAction,projectId:pid()});
    if(result.taskId){model.notice=browserAction==='assist'?'辅助填写任务已开始，完成后请在官方页面核对并由本人确认提交。':'后台操作已加入任务。';await loadWorkspace();}
    else{model.browser=result;model.notice=browserAction==='close'?'提审窗口已关闭。':browserAction==='assist'?'辅助操作结束，请在官方页面核对并由本人确认提交。':'已读取后台窗口状态。';}
   }else if(action==='record'){
    if(!model.accountId)throw new Error('请先选择提审账号');
    const note=$('#publishing-result-note').value.trim(),evidenceUrl=$('#publishing-result-url').value.trim();
    if(!note)throw new Error('请填写核对说明，便于后续追溯');
    await api('publish/record',{projectId:pid(),accountId:model.accountId,status:$('#publishing-result-status').value,evidenceUrl,note});
    model.notice='已保存本人核对结果。';await loadWorkspace();
   }
  }catch(error){model.notice=error.message;toast(error.message,true);}
  finally{model.busy=false;if(document.contains(b)){b.disabled=false;b.innerHTML=old;}updatePanels();}
 });
 setInterval(pollTasks,2000);
})();
