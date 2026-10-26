'use strict';
jobLabels.jianying_project='剪映可编辑草稿';
let jianyingOptions=null,jianyingSource='original',jianyingStatus='',jianyingJob='',jyStatusInfo=null,jyStatusLoading=false,jyEvidenceLoading=false,jyEvidenceProject='',jyEvidenceItems=[],jyEvidenceTasks=[],jyEvidenceSignature='',jyCaptureTarget=null,jyWindows=[],jyImported=new Map(),jyBusy=false;
const jyOptions=()=>jianyingOptions||(jianyingOptions={output:'',splitScenes:true,executable:'',draftRoot:'',...state.jianyingOptions});
const jyJob=()=>state.jobs.find(j=>j.id===jianyingJob)||state.jobs.filter(j=>j.kind==='jianying_project').at(-1);
const jyProject=()=>state.projects.find(p=>p.id===jyEvidenceProject)||activeProject();
const jyProjectId=()=>jyProject()?.id||'';
const jyStamp=value=>value?new Date(Number(value)*1000).toLocaleString('zh-CN'):'时间未记录';
function jyStatusHTML(){
 if(jyStatusLoading)return icon('refresh')+'正在检查本机剪映与草稿组件…';
 if(!jyStatusInfo)return '先检测本机剪映。草稿文件与官方应用里的实际截图分别记录。';
 const s=jyStatusInfo,installed=s.editorInstalled;
 return `<strong>${installed?'已找到本机剪映':'尚未找到本机剪映'}</strong><span>${installed?esc(s.editorVersion||'版本待核对'):'安装后重新检测，或填写主程序路径'}</span>${s.editorExecutable?`<small>${esc(s.editorExecutable)}</small>`:''}<small>草稿桥接组件：${esc(s.component||'pyJianYingDraft')} ${esc(s.version||'未安装')} · ${s.available?'可建立草稿':'需要安装组件'}</small><small>${esc(s.note||'请在剪映实际打开并检查工程；文件生成不代表编辑器已验证。')}</small>`;
}
function jianyingResults(){
 const job=jyJob();if(!job)return '<p class="blank-inline">选择素材并生成草稿后，工程会按视频顺序列在这里。</p>';
 const rows=job.jianyingResults||[],live=['queued','running','pausing'].includes(job.status);
 return `<div class="jy-job-state"><strong>${esc(jobLabels[job.kind]||'剪映草稿')} · ${esc(statusLabels[job.status]||job.status)}</strong><span>${rows.length} / ${job.options?.jianyingVideos?.length||job.options?.trackOrder?.length||rows.length} 个</span><p>${esc(job.stage||'等待处理')}</p>${live&&typeof monitorBar==='function'?monitorBar(job.telemetry?.current,job):''}${job.error?`<p class="track-error" role="alert">${esc(job.error)}</p>`:''}<div class="actions-row">${live?`<button class="button small" data-jianying="control" data-control="pause" data-id="${job.id}">暂停</button><button class="button small" data-jianying="control" data-control="cancel" data-id="${job.id}">停止</button>`:['paused','interrupted','failed','cancelled'].includes(job.status)?`<button class="button small" data-jianying="control" data-control="resume" data-id="${job.id}">继续未完成部分</button>`:''}<a href="#progress">查看任务进度</a></div></div>`+
 rows.map((r,i)=>{const imported=jyImported.get(job.id+':'+i)||r.editorImport;return `<article class="jianying-result"><div class="jy-result-heading"><strong>${esc(r.name)}</strong><span class="tag ${imported?'green':'gray'}">${imported?'已导入草稿库':'草稿已生成'}</span></div><small>${r.tracks} 条素材轨道 · ${r.segments} 个画面片段 · ${duration(r.duration)}</small><small>${esc(r.directory)}</small>${imported?`<small>剪映草稿库：${esc(imported.directory||imported.draftDirectory||'已复制，等待在剪映打开')}</small>`:''}<p class="jy-result-note">需在剪映打开对应工程并检查素材。当前记录不代表编辑器已成功读取，也不是官方工程截图。</p><div class="actions-row"><button class="button small" data-jianying="install" data-id="${job.id}" data-index="${i}">${icon('download')}导入剪映草稿库</button><button class="button small" data-jianying="launch" data-id="${job.id}" data-index="${i}">${icon('external')}打开剪映</button><button class="button small" data-jianying="capture-project" data-project="${esc(r.projectId||job.ids?.[0]||'')}" data-id="${job.id}" data-index="${i}">${icon('image')}采集实际工程截图</button><button class="button small" data-jianying="open" data-id="${job.id}" data-index="${i}">${icon('folder')}工程目录</button></div></article>`;}).join('');
}
function jyField(label,id,key,placeholder='',browse=''){
 return `<div class="field"><label for="${id}">${label}</label><div class="path-input"><input id="${id}" data-jy-option="${key}" value="${esc(jyOptions()[key]||'')}" placeholder="${esc(placeholder)}">${browse?`<button class="button small" data-jianying="path" data-key="${key}" data-mode="${browse}">${icon('folder')}选择</button>`:''}</div></div>`;
}
function jianyingCard(){
 const o=jyOptions();return card('建立可编辑草稿','layers',`<p class="section-description">按实际素材建立画面、原声音轨；同名 SRT 存在时导入字幕。之后在剪映检查工程，再采集官方应用中的真实界面。</p><div class="field"><label for="jy-source">工程输入</label><select id="jy-source"><option value="original" ${jianyingSource==='original'?'selected':''}>左侧所选视频（按选择顺序）</option><option value="final" ${jianyingSource==='final'?'selected':''}>所选剧集的当前成片</option><option value="subtitle" ${jianyingSource==='subtitle'?'selected':''}>所选剧集的去字幕结果</option></select></div>${jyField('工程输出目录','jy-output','output','留空：导出目录下的剪映工程','folder')}<label class="check-label jy-check"><input id="jy-split" type="checkbox" ${o.splitScenes?'checked':''}>按实际镜头分段建立画面轨</label><details class="jy-connection-settings"><summary>剪映安装与草稿库位置</summary>${jyField('剪映主程序（自动检测，可手动指定）','jy-executable','executable','选择 JianyingPro.exe','editor')}${jyField('剪映草稿库（自动检测，可手动指定）','jy-draftRoot','draftRoot','选择剪映本地草稿库目录','folder')}<button class="button small" data-jianying="status">${icon('refresh')}重新检测剪映</button></details><div class="jy-editor-status" id="jy-editor-status" role="status">${jyStatusHTML()}</div><div class="actions-row"><button class="button primary" data-jianying="generate">${icon('layers')}生成可编辑草稿</button><button class="button" data-jianying="relocate">移动工程后重连素材</button></div><p class="field-hint">草稿通过第三方格式桥接生成；请在剪映核对素材、预览和时间线，再采集实际工程截图。</p><p id="jy-status" role="status" aria-live="polite">${esc(jianyingStatus)}</p><div id="jy-results" class="jianying-results">${jianyingResults()}</div>`,'素材保留在独立工程目录，原片不覆盖')+jyEvidenceCard();
}
function jyEvidenceCard(){
 return card('剪映实际工程截图','image',`<div class="field"><label for="jy-evidence-project">截图归属剧目</label><select id="jy-evidence-project">${state.projects.length?state.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===jyProjectId()?'selected':''}>${esc(p.name)}</option>`).join(''):'<option value="">请先导入素材</option>'}</select></div><p class="field-hint">在剪映中打开本剧工程，让预览和时间线清晰可见。选择窗口后，按提示切换过去，软件采集真实窗口画面。</p><div class="actions-row"><button class="button primary" data-jianying="capture">${icon('image')}选择剪映窗口并截图</button><button class="button small" data-jianying="evidence-refresh">${icon('refresh')}刷新截图</button></div><div id="jy-window-picker"></div><details class="jy-manual-import"><summary>导入已保存的实际截图</summary><p class="field-hint">可选择本机图片。手动导入会标记为「本人确认，来源未核验」，不冒认为本工具已验证的官方窗口截图。</p><div class="field"><label for="jy-evidence-note">截图对应的工程与说明</label><textarea id="jy-evidence-note" rows="2" placeholder="例如：本剧第01集，在剪映中打开后的时间线截图"></textarea></div><label class="check-label jy-check"><input id="jy-evidence-confirm" type="checkbox">我确认所选图片来自本剧的实际剪映工程，内容未伪造。</label><button class="button" data-jianying="import-evidence">${icon('folder')}选择并导入图片</button></details><div id="jy-evidence-status" role="status" aria-live="polite"></div><div id="jy-evidence-tasks"></div><div id="jy-evidence-items" class="jy-evidence-items">${jyEvidenceHTML()}</div>`,'保留截图来源、采集时间及工程关联记录');
}
function jyEvidenceHTML(){
 if(!jyEvidenceItems.length)return `<div class="jy-evidence-empty">${icon('image')}<strong>还没有实际工程截图</strong><p>在剪映打开工程后采集，或导入本人保存的实际截图。</p></div>`;
 return jyEvidenceItems.map(item=>{const supported=item.platform==='jianying',captured=item.source==='window_capture',verified=supported&&captured&&(item.officialEvidence===true||item.officialEvidence?.appVerified===true),source=!supported?'历史来源 · 不参与工程核验':verified?'官方窗口来源已核验':captured?'窗口采集 · 来源待核对':'本人导入 · 来源未核验',label=supported?'剪映':'历史截图',url=item.url||media(item.path),association=item.projectAssociation;return `<article class="jy-evidence-item"><a href="${esc(url)}" target="_blank" rel="noreferrer"><img src="${esc(url)}" alt="${label}实际截图，${esc(source)}" loading="lazy"></a><div><strong>${esc(supported?(item.name||item.title||'工程截图'):'历史截图')}</strong><span class="tag ${verified?'green':'gray'}">${esc(source)}</span><p>${label} · ${esc(jyStamp(item.capturedAt||item.createdAt))}</p>${association?`<p>${esc(typeof association==='string'?association:association.message||association.status||(association.userConfirmed?'工程归属由本人确认；来源核验不代表工程内容或平台审核已通过':'已登记剧目关联，需本人核对画面内容'))}</p>`:''}${item.note?`<p>${esc(item.note)}</p>`:''}<a href="${esc(url)}${url.includes('?')?'&':'?'}download=1">查看原图</a></div></article>`;}).join('');
}
function jyEvidenceTasksHTML(){return jyEvidenceTasks.filter(t=>!t.projectId||t.projectId===jyProjectId()).slice(-3).reverse().map(task=>`<div class="jy-capture-task ${task.status==='failed'?'error':''}"><strong>${esc({waiting_window:'等待切换到官方窗口',capturing:'正在采集窗口',completed:'截图已保存',failed:'未完成截图'}[task.status]||task.status)}</strong><p>${esc(task.message||task.error||'')}</p></div>`).join('');}
function jyWindowPickerHTML(){return `<div class="jy-window-choice"><div class="field"><label for="jy-capture-window">选择需要截图的剪映窗口</label><select id="jy-capture-window">${jyWindows.map((w,i)=>`<option value="${i}">${esc(w.title||w.name||'未命名窗口')} · ${esc(w.processName||w.platform||'')}</option>`).join('')}</select></div><p class="field-hint">选定后请在 30 秒内切换到该窗口，保持工程预览与时间线可见。窗口稳定置前后会采集；等待过程不会生成替代图片。</p><label class="check-label jy-check"><input id="jy-capture-confirm" type="checkbox">我已在所选剪映窗口打开本剧实际工程，预览与时间线清晰可见。</label><div class="actions-row"><button class="button primary" data-jianying="capture-window">开始等待并截图</button><button class="button" data-jianying="capture-cancel">取消选择</button></div></div>`;}
async function jyLoadStatus(){if(jyStatusLoading)return;jyStatusLoading=true;if($('#jy-editor-status'))$('#jy-editor-status').innerHTML=jyStatusHTML();try{jyStatusInfo=await api('jianying/status',{jianying:jyOptions()});}catch(error){jianyingStatus=error.message;}finally{jyStatusLoading=false;if($('#jy-editor-status'))$('#jy-editor-status').innerHTML=jyStatusHTML();if($('#jy-status'))$('#jy-status').textContent=jianyingStatus;}}
async function jyLoadEvidence(){
 const id=jyProjectId();if(!id||jyEvidenceLoading)return;jyEvidenceLoading=true;
 try{const result=await api('project-evidence/list?projectId='+encodeURIComponent(id));if(id!==jyProjectId())return;jyEvidenceItems=result.items||[];jyEvidenceTasks=result.tasks||[];const signature=JSON.stringify([id,jyEvidenceItems,jyEvidenceTasks]);if(signature!==jyEvidenceSignature){jyEvidenceSignature=signature;if($('#jy-evidence-items'))$('#jy-evidence-items').innerHTML=jyEvidenceHTML();if($('#jy-evidence-tasks'))$('#jy-evidence-tasks').innerHTML=jyEvidenceTasksHTML();}}
 catch(error){if($('#jy-evidence-status'))$('#jy-evidence-status').textContent=error.message;}
 finally{jyEvidenceLoading=false;if(id!==jyProjectId()&&current==='tracks')jyLoadEvidence();}
}
const jyBaseRender=renderPage;renderPage=function(){jyBaseRender();if(current==='tracks'){const host=$('#jy-workspace-host');if(host)host.innerHTML=jianyingCard();jyLoadStatus();jyLoadEvidence();}};
const jyBaseRefresh=refresh;refresh=async function(render=false){await jyBaseRefresh(render);if(current==='tracks'&&$('#jy-results')){const html=jianyingResults();if($('#jy-results').innerHTML!==html)$('#jy-results').innerHTML=html;}};
document.addEventListener('input',e=>{const el=e.target;if(el.dataset.jyOption)jyOptions()[el.dataset.jyOption]=el.value;});
document.addEventListener('change',e=>{const el=e.target;if(el.id==='jy-split')jyOptions().splitScenes=el.checked;if(el.id==='jy-source'){jianyingSource=el.value;renderTaskbar();}if(el.id==='jy-evidence-project'){jyEvidenceProject=el.value;jyEvidenceItems=[];jyEvidenceTasks=[];jyEvidenceSignature='';jyLoadEvidence();}});
function jyStatusMessage(text){jianyingStatus=text;if($('#jy-status'))$('#jy-status').textContent=text;}
async function jyChooseWindows(target){
 const projectId=target?.projectId||jyProjectId();if(!projectId)throw Error('请先选择截图归属剧目');
 jyCaptureTarget={...target,projectId,platform:'jianying'};const result=await api('project-evidence/capture',jyCaptureTarget);
 jyWindows=result.windows||result.candidates||[];if(!jyWindows.length)throw Error(result.message||'没有找到可采集的官方窗口，请先打开对应工程。');
 $('#jy-window-picker').innerHTML=jyWindowPickerHTML();$('#jy-capture-window').focus();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-jianying]');if(!b||b.disabled||jyBusy)return;const action=b.dataset.jianying;
 if(action==='capture-cancel'){jyCaptureTarget=null;jyWindows=[];if($('#jy-window-picker'))$('#jy-window-picker').innerHTML='';return;}
 jyBusy=true;const oldButtonHTML=b.innerHTML;b.disabled=true;b.innerHTML=icon('refresh')+'正在处理…';
 try{
  if(action==='path'){const result=await api('browse',{mode:b.dataset.mode});if(result.path){jyOptions()[b.dataset.key]=result.path;const input=$(`[data-jy-option="${b.dataset.key}"]`);if(input)input.value=result.path;}}
  else if(action==='status')await jyLoadStatus();
  else if(action==='generate'){
   const body={...trackSelectionBody(false),kind:'jianying_project',sourceKind:jianyingSource,jianying:{...jyOptions()}};
   if(jianyingSource!=='original'){body.ids=[...new Set(trackVideos().map(v=>v.projectId))];if(!body.ids.length&&activeProject())body.ids=[activeProject().id];delete body.sourceVideoPaths;}
   if(!body.ids.length)throw Error('请先选择工程素材');
   const plan=await api('jianying/plan',body),result=await api('jobs',body);jianyingJob=result.id;jyStatusMessage(`${plan.count} 个可编辑草稿已加入队列，完成后导入剪映核对。`);await refresh();toast(jianyingStatus);
  }else if(action==='open')await api('jianying/open',{id:b.dataset.id,index:Number(b.dataset.index)});
  else if(action==='install'){
   const result=await api('jianying/install',{jobId:b.dataset.id,index:Number(b.dataset.index),options:jyOptions()});jyImported.set(b.dataset.id+':'+b.dataset.index,result);jyStatusMessage(result.message||'已复制到剪映草稿库。请在剪映打开对应工程核对，尚未验证编辑器画面。');await refresh();
  }else if(action==='launch'){
   const result=await api('jianying/launch',{jobId:b.dataset.id,index:Number(b.dataset.index),options:jyOptions()});jyStatusMessage(result.message||result.note||'剪映已启动，请在应用中打开对应工程，再采集实际截图。');
  }else if(action==='relocate'){const result=await api('browse',{mode:'folder'});if(result.path){await api('jianying/relocate',{directory:result.path});jyStatusMessage('素材路径已重新定位。请在剪映打开并核对预览。');}}
  else if(action==='control'){await api('jobs/control',{id:b.dataset.id,action:b.dataset.control});await refresh();}
  else if(action==='capture-project'){jyEvidenceProject=b.dataset.project;const select=$('#jy-evidence-project');if(select)select.value=jyEvidenceProject;jyEvidenceItems=[];jyEvidenceTasks=[];jyLoadEvidence();await jyChooseWindows({projectId:b.dataset.project,jobId:b.dataset.id,index:Number(b.dataset.index),platform:'jianying'});}
  else if(action==='capture')await jyChooseWindows();
  else if(action==='capture-window'){
   const window=jyWindows[Number($('#jy-capture-window').value)];if(!window||!jyCaptureTarget)throw Error('请重新选择官方窗口');
   if(!$('#jy-capture-confirm').checked)throw Error('请先确认所选窗口中已打开本剧的实际工程');
   const result=await api('project-evidence/capture',{...jyCaptureTarget,windowId:window.id??window.windowId,userConfirmed:true});
   $('#jy-window-picker').innerHTML='';jyWindows=[];if($('#jy-evidence-status'))$('#jy-evidence-status').textContent=result.message||'请在 30 秒内切换到选定官方窗口，保持实际工程界面可见。';
   await jyLoadEvidence();
  }else if(action==='import-evidence'){
   const note=$('#jy-evidence-note').value.trim();if(!jyProjectId())throw Error('请先选择截图归属剧目');if(!note)throw Error('请填写截图对应的实际工程说明');if(!$('#jy-evidence-confirm').checked)throw Error('请确认图片来自本剧的实际官方应用工程');
   const chosen=await api('browse',{mode:'images'});if(chosen.paths?.length){await api('project-evidence/import',{projectId:jyProjectId(),platform:'jianying',paths:chosen.paths,note,userConfirmed:true});if($('#jy-evidence-status'))$('#jy-evidence-status').textContent='截图已导入，标记为本人确认、来源未核验。';await jyLoadEvidence();}
  }else if(action==='evidence-refresh')await jyLoadEvidence();
 }catch(error){jyStatusMessage(error.message);toast(error.message,true);if(action.includes('capture')||action.includes('evidence')){const status=$('#jy-evidence-status');if(status)status.textContent=error.message;}}
 finally{jyBusy=false;if(b.isConnected){b.disabled=false;b.innerHTML=oldButtonHTML;}renderTaskbar();}
});
setInterval(()=>{if(current==='tracks'&&jyEvidenceTasks.some(t=>['waiting_window','capturing','queued','running'].includes(t.status)))jyLoadEvidence();},1000);
