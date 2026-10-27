'use strict';
pages.splice(pages.findIndex(p=>p[0]==='logs'),0,['progress','制作进度','chart','任务监控']);
let monitorId='',monitorFilter='all',monitorStatusSignature='',monitorReceivedAt=Date.now(),monitorConnectionLost=false;
const monitorLive=new Set(['running','pausing']),monitorResume=new Set(['paused','interrupted','failed','cancelled']);
const monitorClock=value=>{value=Math.max(0,Math.floor(value||0));return `${Math.floor(value/3600)?Math.floor(value/3600).toString().padStart(2,'0')+':':''}${Math.floor(value/60)%60===0?'00':String(Math.floor(value/60)%60).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`;};
const monitorJob=()=>state.jobs.find(j=>j.id===monitorId)||busy()||state.jobs.at(-1);
const monitorPercent=row=>row?.percent==null?null:Math.min(100,Math.max(0,Number(row.percent)));
function monitorBar(row,job,label='当前处理进度'){
 const value=monitorPercent(row),running=job.status==='running',unknown=value==null;
 return `<div class="monitor-track ${unknown&&running?'unknown':''} ${job.status==='failed'?'failed':job.status==='completed'?'completed':''}" role="progressbar" aria-label="${esc(label)}" aria-valuemin="0" aria-valuemax="100" ${unknown?'aria-valuetext="当前阶段未提供准确百分比"':`aria-valuenow="${value}"`}><span style="width:${value??0}%"></span></div>`;
}
function monitorUnits(row){
 if(!row)return '当前阶段暂无可测量的百分比';
 const value=row.completed||0,total=row.total;
 if(row.unit==='seconds')return `已处理 ${monitorClock(value)}${total?' / '+monitorClock(total):''}`;
 if(row.unit==='bytes')return `已下载 ${size(value)}${total?' / '+size(total):''}`;
 return `已处理 ${Math.floor(value).toLocaleString()}${total?' / '+Math.floor(total).toLocaleString():''} 帧`;
}
function monitorSpeed(row,job){
 if(job.status!=='running'||!row?.speed||row.status==='finalizing')return '—';
 return row.unit==='seconds'?row.speed.toFixed(2)+' 倍速':row.unit==='bytes'?size(row.speed)+'/秒':row.speed.toFixed(1)+' 帧/秒';
}
function monitorTaskControls(job){
 const live=monitorLive.has(job.status),cloud=job.kind==='video_generate';let html='';
 if(job.status==='completed')html+=`<button class="button primary" data-progress-action="output" data-id="${job.id}">${icon('folder')}打开输出文件夹</button>`;
 else if(live&&job.resumable)html+=`<button class="button primary" data-progress-action="pause" data-id="${job.id}" ${job.status==='pausing'?'disabled':''}>${job.status==='pausing'?'正在暂停…':cloud?'暂停本机查询':'暂停任务'}</button>`;
 else if(job.resumable&&monitorResume.has(job.status))html+=`<button class="button primary" data-progress-action="resume" data-id="${job.id}">${icon('play')}${cloud?'继续查询原任务':job.status==='failed'?'重试未完成部分':'继续处理'}</button>`;
 if(live||job.status==='queued')html+=`<button class="button" data-progress-action="stop" data-id="${job.id}">${cloud?'停止本机查询':job.status==='queued'?'取消排队':'停止任务'}</button>`;
 return html+`<button class="button" data-progress-action="logs" data-id="${job.id}">${icon('log')}查看日志</button><button class="button" data-progress-action="report" data-id="${job.id}">${icon('download')}导出诊断摘要</button>`;
}
function monitorNotice(job){
 const cloud=job.kind==='video_generate',r=job.telemetry?.current;
 if(monitorConnectionLost)return ['warning','暂时无法获取最新状态',`上次成功获取状态：${new Date(monitorReceivedAt).toLocaleTimeString('zh-CN')}。保留上次进度，请检查服务连接；不会自动重新提交云端任务。`];
 if(job.status==='failed')return ['error',job.diagnostic?.stage||'任务未完成',job.diagnostic?.reason||job.error||'旧任务没有保存具体报错'];
 if(['paused','interrupted','cancelled'].includes(job.status))return ['warning',cloud?'本机查询已停止，云端任务可能继续':'已完成结果与检查点保留',cloud?'继续时查询原云端任务，不重复提交。云端可能继续生成和计费，取消云端任务需到对应平台核对。':'继续后跳过有效检查点，当前未完成视频重新处理；不承诺帧级续跑。'];
 if(job.status==='pausing')return ['warning','正在处理暂停请求','等待当前进程退出后才会显示已暂停。当前未完成视频不计入完成数量。'];
 if(job.gpuFallback)return ['warning','已自动切换 CPU 编码',`${job.gpuFallback.detail}。${job.status==='completed'?'制作已完成，可核对输出结果。':'已完成视频和队列保留，继续处理剩余部分。'}下载队列不受此编码设置影响。`];
 if(job.status==='completed')return ['success','制作任务已完成','输出和制作记录保留在本机，可以打开文件夹核对结果。'];
 if(cloud)return ['',job.remoteVideo?.taskId?'原云端任务已记录':'正在提交或查询生成任务','平台未提供百分比时只展示真实状态；请勿重复点击生成。网络异常时可核对原任务 ID 后继续。'];
 if(r&&job.status==='running'&&Date.now()/1000-(r.progressAt||r.startedAt)>25)return ['','此阶段暂未返回新进度','服务仍在响应，模型或编码进程可能正在进行耗时操作。请查看最后反馈时间与日志，未因此自动判定失败。'];
 return ['','原始素材保留',r?.percent==null?'模型加载或当前步骤没有可测量总量时，显示阶段与耗时；收到实际数据后再显示百分比。':'当前进度来自实际处理时长、帧数或下载字节。预计时间仅适用于当前步骤，会随速度变化。'];
}
function monitorDetailHTML(job){
 if(!job)return '<div class="monitor-empty">'+icon('layers')+'<h2>还没有制作任务</h2><p>导入素材后开始制作，处理进度会显示在这里。</p><a class="button primary" href="#scan">导入素材</a></div>';
 const t=job.telemetry||{},r=t.current,value=monitorPercent(r),live=job.status==='running',cloud=job.kind==='video_generate',title=job.project||job.ids.map(id=>state.projects.find(p=>p.id===id)?.name||'素材已移除').join('、')||jobLabels[job.kind]||job.kind;
 const observedNow=monitorConnectionLost?monitorReceivedAt/1000:Date.now()/1000;
 const seconds=(job.runSeconds||0)+(live&&job.runStarted?Math.max(0,observedNow-job.runStarted):0),notice=monitorNotice(job),eta=!monitorConnectionLost&&live&&r?.etaSeconds!=null&&r.status!=='finalizing'?`约 ${duration(r.etaSeconds)}`:live&&!monitorConnectionLost?'估算中':'—';
 const phase=r&&['running','finalizing'].includes(r.status)?r.label:t.phase||job.stage;
 const status=statusLabels[job.status]||job.status,other=(t.rows||[]).filter(row=>row.id!==r?.id&&['running','finalizing'].includes(row.status));
 return `<div class="monitor-current-heading"><div><h2>${esc(title)}</h2><p>${esc(jobLabels[job.kind]||job.kind)} · ${r?.name?esc(r.name)+' · ':''}任务 ${esc(job.id)}</p></div><span class="tag ${job.status==='completed'?'green':job.status==='failed'?'red':'gray'}">${esc(status)}</span></div>
 <div class="monitor-main"><div><h3>${esc(job.status==='completed'?'全部完成':job.status==='running'?phase:job.stage)}</h3><p>${esc(cloud?job.remoteVideo?.connection?.name||'当前视频连接':r?.encoder|| (r?.unit==='frames'?'本地 AI 引擎':r?.unit==='seconds'?'媒体编码引擎':'本地制作步骤'))}${job.remoteVideo?.taskId?' · 云端任务 '+esc(job.remoteVideo.taskId):''}</p></div><strong class="monitor-number ${value==null?'unknown':''}">${job.status==='completed'?'100<small>%</small>':value==null?'等待反馈':value+'<small>%</small>'}</strong></div>
 ${monitorBar(job.status==='completed'?{percent:100}:r,job)}<div class="monitor-caption"><span>${esc(monitorUnits(r))}</span><span>${r?.progressAt?'最近进度 '+new Date(r.progressAt*1000).toLocaleTimeString('zh-CN'):'执行阶段反馈'}</span></div>
 <div class="monitor-metrics"><div><small>任务累计运行</small><strong>${monitorClock(seconds)}</strong></div><div><small>${r?.unit==='bytes'?'下载速度':'处理速度'}</small><strong>${esc(monitorSpeed(r,job))}</strong></div><div><small>当前步骤预计剩余</small><strong>${esc(eta)}</strong></div></div>
 ${other.length?`<div class="monitor-parallel"><h3>并行处理中的其他视频</h3>${other.map(row=>`<div class="monitor-parallel-row"><span>${esc(row.name||row.label)}</span><strong>${row.percent==null?'等待反馈':row.percent+'%'}</strong>${monitorBar(row,job,row.name)}</div>`).join('')}</div>`:''}
 ${job.status==='failed'?taskFailureHTML(job):`<div class="monitor-notice ${notice[0]}" role="note">${icon('info')}<div><strong>${esc(notice[1])}</strong><p>${esc(notice[2])}</p></div></div>`}
 <div class="monitor-actions">${monitorTaskControls(job)}${job.status==='failed'&&/401|403|密钥|鉴权|unauthorized/i.test(job.error||'')?'<a class="button" href="#api">检查接口设置</a>':''}</div>`;
}
function monitorBatchHTML(job){
 const b=job?.telemetry?.batch;
 const total=b?.total??(job?.ids.length||1),done=b?.done??(job?.status==='completed'?total:job?.completedProjects||0),value=total?Math.min(100,done/total*100):0;
 return `<div class="monitor-batch-head"><strong>${esc(b?.label||(job?.kind==='video_generate'?'生成任务完成度':'已完整完成的剧集'))}</strong><span>${done} / ${total} · ${value.toFixed(0)}%</span></div><div class="monitor-track batch" role="progressbar" aria-label="本阶段完成度" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${value}"><span style="width:${value}%"></span></div><p class="field-hint">${b?'按本阶段已完成并写入检查点的源视频计算。重组后输出集数可能不同，其他制作步骤单独记录。':'仅全部处理成功的剧集或生成任务计为完成；当前步骤的百分比不代表整批进度。'}</p>`;
}
function monitorRows(){
 const rows=state.jobs.slice().reverse().filter(j=>monitorFilter==='all'||monitorFilter==='active'&&monitorLive.has(j.status)||monitorFilter==='queued'&&j.status==='queued'||monitorFilter==='failed'&&['failed','interrupted','paused'].includes(j.status));
 return rows.map(j=>`<article class="monitor-queue-row ${monitorJob()?.id===j.id?'selected':''}"><span class="monitor-file">${icon(j.kind==='video_generate'?'spark':'film')}</span><div><strong>${esc(j.project||j.ids.map(id=>state.projects.find(p=>p.id===id)?.name||'素材已移除').join('、')||jobLabels[j.kind]||j.kind)}</strong><p>${esc(jobLabels[j.kind]||j.kind)} · ${esc(j.stage)}</p></div><span class="tag ${j.status==='failed'?'red':j.status==='completed'?'green':'gray'}">${esc(statusLabels[j.status]||j.status)}</span><button class="button small" data-progress-action="select" data-id="${j.id}">查看详情</button></article>`).join('')||'<p class="blank-inline">当前筛选下没有任务</p>';
}
function monitorPage(){return intro('制作进度','查看真实处理状态、当前视频与整批完成情况。')+`<div class="monitor-stats" id="monitor-stats"></div>`+card('当前任务','cpu','<div id="monitor-detail"></div>')+card('阶段完成情况','layers','<div id="monitor-batch"></div>')+card('任务队列','layers',`<div class="monitor-filters" role="group" aria-label="筛选制作任务">${[['all','全部'],['active','运行中'],['queued','排队中'],['failed','需关注']].map(([v,l])=>`<button class="button small ${monitorFilter===v?'primary':''}" data-progress-action="filter" data-value="${v}" aria-pressed="${monitorFilter===v}">${l}</button>`).join('')}</div><div id="monitor-queue"></div>`);}
function updateMonitor(){
 if(current!=='progress'||!$('#monitor-detail'))return;
 const job=monitorJob(),focus=document.activeElement?.closest('[data-progress-action]'),focusAction=focus?.dataset.progressAction,focusId=focus?.dataset.id;
 $('#monitor-stats').innerHTML=[['任务总数',state.jobs.length],['正在运行',state.jobs.filter(j=>monitorLive.has(j.status)).length],['已完成',state.jobs.filter(j=>j.status==='completed').length],['需关注',state.jobs.filter(j=>['failed','paused','interrupted'].includes(j.status)).length]].map(([label,n])=>`<div><small>${label}</small><strong>${n}<span> 个任务</span></strong></div>`).join('');
 setDiagnosticHTML($('#monitor-detail'),monitorDetailHTML(job));$('#monitor-batch').innerHTML=job?monitorBatchHTML(job):'<p class="blank-inline">暂无阶段进度</p>';$('#monitor-queue').innerHTML=monitorRows();
 if(focusAction)$$('[data-progress-action]').find(b=>b.dataset.progressAction===focusAction&&b.dataset.id===focusId&&!b.disabled)?.focus({preventScroll:true});
 const signature=job?.id+':'+job?.status+':'+job?.telemetry?.phase;
 if(signature!==monitorStatusSignature){monitorStatusSignature=signature;$('#monitor-announcement').textContent=job?`${job.project||'制作任务'}，${statusLabels[job.status]||job.status}。${job.telemetry?.phase||job.stage}`:'暂无制作任务';}
}
const monitorBasePage=renderPage;renderPage=function(){if(current!=='progress')return monitorBasePage();$('#content').innerHTML=monitorPage();$('#breadcrumb').textContent='制作进度';renderNav();renderTaskbar();updateMonitor();};
const monitorBaseUpdate=updateWorkflowUI;updateWorkflowUI=function(){monitorBaseUpdate();updateMonitor();};
const monitorBaseRefresh=refresh;refresh=async function(...args){const wasDisconnected=monitorConnectionLost;const value=await monitorBaseRefresh(...args);monitorReceivedAt=Date.now();monitorConnectionLost=false;if(wasDisconnected)$('#service-status').innerHTML='本地引擎已连接<small>素材与工程保存在本机</small>';return value;};
const monitorBasePoll=poll;poll=async function(){await monitorBasePoll();if(Date.now()-monitorReceivedAt>5000){monitorConnectionLost=true;updateMonitor();}};
const monitorBaseActivity=renderActivity;renderActivity=function(){monitorBaseActivity();const job=busy()||state.jobs.at(-1),target=$('.job-idle');if(job&&target){const r=job.telemetry?.current;target.innerHTML=`<div class="job-current-title">${esc(job.project||jobLabels[job.kind]||'制作任务')}</div>${monitorBar(job.status==='completed'?{percent:100}:r,job)}<div class="progress-row"><span>${esc(job.telemetry?.phase||job.stage)}</span><span>${job.status==='completed'?'100%':r?.percent==null?'阶段反馈':r.percent+'%'}</span></div>${job.error?`<p class="monitor-error">${esc(job.error).slice(0,200)}</p>`:''}<a class="button small monitor-view" href="#progress">查看制作进度 →</a>`;}};
const monitorBaseTaskbar=renderTaskbar;renderTaskbar=function(){monitorBaseTaskbar();const job=busy();if(job){const r=job.telemetry?.current;$('#task-detail').textContent=(r?.label||job.stage)+(r?.percent!=null?' · '+r.percent+'%':'');if(job.kind==='video_generate'){$('#pause-job').textContent='暂停本机查询';$('#cancel-job').textContent='停止查询';}else{$('#pause-job').textContent='暂停';$('#cancel-job').textContent='停止任务';}}if(current==='progress'){const b=$('#start-pipeline');b.dataset.action='monitor-current';b.textContent='查看当前任务';b.disabled=!state.jobs.length;}};
const monitorDialog=document.createElement('dialog');monitorDialog.id='monitor-dialog';monitorDialog.setAttribute('aria-labelledby','monitor-dialog-title');document.body.append(monitorDialog);
const monitorAnnouncement=document.createElement('div');monitorAnnouncement.id='monitor-announcement';monitorAnnouncement.className='monitor-sr';monitorAnnouncement.setAttribute('role','status');monitorAnnouncement.setAttribute('aria-live','polite');document.body.append(monitorAnnouncement);
function monitorStop(job){monitorDialog.innerHTML=`<div class="dialog-top"><h2 id="monitor-dialog-title">${job.kind==='video_generate'?'停止本机查询？':'停止当前任务？'}</h2><button class="button" data-progress-action="close">返回</button></div><p class="section-description">${job.kind==='video_generate'?'云端可能继续生成并计费。此操作仅停止本机查询，不会取消云端任务；可到对应平台核对。':'已完成结果和检查点会保留。当前未完成视频恢复时重新处理，不删除原始素材。'}</p><div class="actions-row"><button class="button" data-progress-action="close">继续等待</button><button class="button danger" data-progress-action="confirm-stop" data-id="${job.id}">确认停止</button></div>`;monitorDialog.showModal();}
const monitorBaseWorkflowAction=workflowAction;workflowAction=async function(action,b){if(action==='monitor-current'){monitorId='';if(current==='progress')updateMonitor();else location.hash='progress';return true;}if(action==='cancel'){if(busy())monitorStop(busy());return true;}if(action==='control-job'&&b.dataset.control==='cancel'){const j=state.jobs.find(j=>j.id===b.dataset.id);if(j)monitorStop(j);return true;}return monitorBaseWorkflowAction(action,b);};
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-progress-action]');if(!b||b.disabled)return;const action=b.dataset.progressAction,job=state.jobs.find(j=>j.id===b.dataset.id);
 try{
  if(action==='select'){monitorId=job.id;updateMonitor();$('#monitor-detail').scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
  if(action==='filter'){monitorFilter=b.dataset.value;$$('.monitor-filters button').forEach(el=>{el.classList.toggle('primary',el===b);el.setAttribute('aria-pressed',el===b?'true':'false');});$('#monitor-queue').innerHTML=monitorRows();}
  if(action==='pause'||action==='resume'||action==='confirm-stop'){b.disabled=true;await api('jobs/control',{id:job.id,action:action==='confirm-stop'?'cancel':action});if(monitorDialog.open)monitorDialog.close();await refresh();updateMonitor();toast(action==='resume'?'已加入恢复队列':'任务状态已更新');}
  if(action==='stop')monitorStop(job);
  if(action==='close')monitorDialog.close();
  if(action==='output')await api('open-output',{id:job.result?.projectId||job.ids[0]||null});
  if(action==='logs'){const logs=state.logs.filter(l=>l.job===job.id);monitorDialog.innerHTML=`<div class="dialog-top"><h2 id="monitor-dialog-title">任务日志 · ${esc(job.id)}</h2><button class="button" data-progress-action="close">关闭</button></div>${taskFailureHTML(job)}<div class="monitor-log">${logs.map(l=>`<p><time>${esc(l.time)}</time> ${esc(l.message)}</p>`).join('')||'<p>暂无日志</p>'}</div>`;monitorDialog.showModal();}
  if(action==='report'){const report=await api('jobs/report?id='+encodeURIComponent(job.id)),url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`漫剧工坊-任务诊断-${job.id}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),2000);toast('已导出诊断摘要，不含接口密钥、授权码和完整文件路径');}
 }catch(err){toast(err.message,true);}finally{if(b.isConnected)b.disabled=false;}
});
