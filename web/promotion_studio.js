'use strict';
(()=>{
Object.assign(jobLabels,{promotion_analyse:'AI 分析推广高光',promotion_render:'生成混剪成片',promotion_auto:'智能推广混剪'});
const studioDrafts=new Map(),studioActiveEngines=new Map(),studioSubmitting=new Set(),studioSaveMessages=new Map();
const studioEngines={local:'本地智能混剪',mediakit:'火山云端'};
const studioEngineDefaults={mediakit:{base:'https://mediakit.cn-beijing.volces.com',cutMode:'Mixed',downloadFolder:''},dramaclip:{root:'',python:'',mode:'highlight'}};
let studioEngineState=null,studioSettingsTab='dramaclip',studioSettingsTrigger=null,studioEngineRead=0,studioSettingsSaving=false,studioEngineSave=Promise.resolve(),studioEmptyEngine='local',studioInitialEngineRead=null;
function studioEngineName(engine){return engine==='mediakit'?'mediakit':'local';}
function studioSelectedEngine(){const p=activeProject();return p?(studioActiveEngines.get(p.id)||studioEngineName(p.promotionStudio?.engine)):studioEmptyEngine;}
function studioDraft(engine=studioSelectedEngine()){
 const p=activeProject();if(!p)return {};
 engine=studioEngineName(engine);const key=p.id+'|'+engine;
 if(!studioDrafts.has(key)){
  const previous=p.promotionStudio||{},saved=p.promotionStudioByEngine?.[engine]||(studioEngineName(previous.engine)===engine?previous:{}),paths=new Set(p.videos.map(v=>v.path));
  studioDrafts.set(key,{count:2,seconds:60,direction:'冲突、反转、悬念，结尾保留看全集的动机',cta:'点击下方入口看全集',...saved,engine,sourcePaths:(saved.sourcePaths||p.videos.map(v=>v.path)).filter(x=>paths.has(x)),targets:{},autoDispatch:false});
 }
 return studioDrafts.get(key);
}
function studioField(label,key,type='text',min='',max=''){
 const d=studioDraft(),id='studio-'+key;
 return `<div class="field"><label for="${id}">${label}</label>${type==='textarea'?`<textarea id="${id}" data-studio-field="${key}" rows="2">${esc(d[key]??'')}</textarea>`:`<input id="${id}" data-studio-field="${key}" type="${type}" value="${esc(d[key]??'')}" ${min!==''?`min="${min}"`:''} ${max!==''?`max="${max}"`:''}>`}${key==='cta'?`<p id="studio-target-hint" class="field-hint">${esc(studioTargetHint())}</p>`:''}</div>`;
}
function studioTargetHint(){return studioDraft().engine==='mediakit'?'云端引导文字最多20字，超出会截取前20字；数量与秒数为算法目标范围。':'数量与时长作为生成目标；本地引导文字最多80字。';}
function studioEngineHint(engine=studioDraft().engine){
 if(engine==='mediakit')return '原始带中文字幕素材上传云端处理，按输入和输出时长计费；完成后自动下载到本机。';
 return '融合 DramaClip 剧情规划、语音识别与文字 AI，在本机生成混剪，支持任务记录与断点恢复。';
}
function studioSourcePicker(){const p=activeProject(),d=studioDraft();return `<details class="studio-sources"><summary id="studio-source-count">选择原片 · 已选 ${d.sourcePaths.length} / ${p.videos.length} 集</summary><div class="actions-row"><button class="button small" data-studio="select-all">全部选择</button><button class="button small" data-studio="clear-selection">清空选择</button></div><div class="studio-source-list">${p.videos.map(v=>`<label class="check-label"><input type="checkbox" data-studio-source="${esc(v.path)}" ${d.sourcePaths.includes(v.path)?'checked':''}><span>${esc(v.name)} · ${duration(v.duration)}</span></label>`).join('')}</div></details>`;}
function studioModuleTabs(){const engine=studioSelectedEngine();return `<div class="studio-module-tabs" role="tablist" aria-label="推广制作模块">${[['local','cpu','剧情编排与本机混剪'],['mediakit','link','云端智剪与任务下载']].map(([key,ico,desc])=>`<button type="button" id="studio-module-${key}" role="tab" data-studio="module" data-engine="${key}" aria-controls="studio-module-panel" aria-selected="${engine===key}" tabindex="${engine===key?0:-1}"><span>${icon(ico)}${studioEngines[key]}</span><small>${desc}</small></button>`).join('')}</div><select id="studio-engine" data-studio-field="engine" aria-label="当前推广模块" hidden>${Object.entries(studioEngines).map(([key,label])=>`<option value="${key}" ${key===engine?'selected':''}>${esc(label)}</option>`).join('')}</select>`;}
function studioModuleSettings(engine){return `<button type="button" class="button small" data-studio="settings-open" data-tab="${engine==='mediakit'?'mediakit':'dramaclip'}">${icon('settings')}${engine==='mediakit'?'云端服务设置':'本地引擎设置'}</button>`;}
function studioSourceCard(){
 const p=activeProject(),d=studioDraft(),cloud=d.engine==='mediakit';
 const context=cloud?`<div id="studio-cloud-selection" class="studio-source-check" role="status">${esc(studioCloudSelection())}</div><div class="studio-module-method"><span>剪辑方式</span><strong id="studio-cloud-cut-mode">${esc(studioCutModeLabel())}</strong><button type="button" class="button subtle small" data-studio="settings-open" data-tab="mediakit">调整</button></div>`:`<div class="studio-local-method"><span>${icon('subtitle')}原片字幕 / 本地转写</span><span>${icon('text')}<span id="studio-local-planner">${esc(studioLocalPlannerLabel())}</span></span><span>${icon('film')}本机编码</span></div>`;
 return card(cloud?'云端高光智剪':'本地智能混剪',cloud?'link':'cpu',`<p id="studio-engine-hint" class="field-hint studio-module-hint">${esc(studioEngineHint())}</p>${studioSourcePicker()}${context}<div class="grid-2">${studioField(cloud?'最多生成条数':'推广视频数量','count','number',1,6)}${studioField(cloud?'成片目标时长（秒）':'每条目标时长（秒）','seconds','number',10,180)}</div>${studioField(cloud?'剧情高光提示':'高光与剧情要求','direction','textarea')}${studioField(cloud?'画面引导文字':'结尾引导文字','cta')}<label class="check-label"><input id="studio-rights" type="checkbox" ${p.rights?'checked':''}>确认拥有所选素材的剪辑与推广授权${cloud?'，允许上传所选原片到火山云端':''}</label><div class="actions-row"><button class="button primary" data-studio="auto" ${studioBlockingJob()||studioSubmitting.has(p.id)?'disabled':''}>${icon(cloud?'upload':'film')}${cloud?'提交云端并生成成片':'一键生成本地混剪'}</button><span id="studio-engine-status" class="field-hint" role="status">${esc(studioEngineSummary())}</span></div>`, '',studioModuleSettings(d.engine));
}
function studioCutModeLabel(){return !studioEngineState?'使用已保存的云端剪辑方式':studioEngineState.settings?.mediakit?.cutMode==='Sequential'?'顺剪 · 保持时间顺序':'混剪 · 按剧情高光编排';}
function studioLocalPlannerLabel(){return !studioEngineState?'DramaClip / 台词剧情编排':studioEngineState.dramaclip?.ready?'DramaClip 剧情编排':'内置台词剧情编排';}
function studioCloudSelection(){
 const p=activeProject(),d=studioDraft(),videos=p.videos.filter(v=>d.sourcePaths.includes(v.path)),seconds=videos.reduce((total,v)=>total+Number(v.duration||0),0),problems=[];
 if(!videos.length)problems.push('请选择原片');if(videos.length>30)problems.push('每次最多30集');if(seconds>2700)problems.push('合计时长不能超过45分钟');
 if(videos.some(v=>v.audio===false))problems.push('包含无音轨视频');if(videos.some(v=>Math.max(v.width||0,v.height||0)>1920||Math.min(v.width||0,v.height||0)>1080))problems.push('包含超过1080p的视频');if(videos.some(v=>(v.bytes||v.stat?.bytes||0)>5*1024**3))problems.push('包含超过5GB的视频');
 return `已选 ${videos.length} 集 · ${duration(seconds)}。${problems.length?problems.join('；')+'。':'单次限制：30集 / 45分钟 / 1080p / 每集5GB。'}素材需含清晰中文对白与下半部居中的中文字幕。`;
}
function studioEngineSummary(){
 const engine=studioDraft().engine;
 if(engine==='mediakit')return studioEngineState?(studioEngineState.mediakit?.hasKey?'云端密钥已在本次运行中设置。':'请在本页设置中填写 MediaKit 密钥。'):'MediaKit 密钥在本页设置中单独配置。';
 return studioEngineState?.dramaclip?.message||'自动选择可用的本地能力；环境状态可在本页设置中查看，错误与完成记录保存在任务中。';
}
function studioUpdateEngineUI(){
 const d=studioDraft();
 if($('#studio-engine-hint'))$('#studio-engine-hint').textContent=studioEngineHint();
 if($('#studio-engine-status'))$('#studio-engine-status').textContent=studioEngineSummary();
 if($('#studio-target-hint'))$('#studio-target-hint').textContent=studioTargetHint();
 if($('#studio-analysis'))$('#studio-analysis').hidden=d.engine!=='local';
 if($('#studio-cloud-cut-mode'))$('#studio-cloud-cut-mode').textContent=studioCutModeLabel();
 if($('#studio-local-planner'))$('#studio-local-planner').textContent=studioLocalPlannerLabel();
 renderTaskbar();
}
function studioAnalysisCard(){
 const a=activeProject().promotionAnalysis;
 if(!a)return card('剧情编排与计划预览','text','<p class="field-hint">开始生成后，自动读取原片字幕；无字幕时使用本地语音识别，再规划冲突、反转与跨集故事线。生成的选段计划会保存在这里。</p>');
 const plans=a.clips.map((c,i)=>`<details class="studio-plan"><summary>${i+1}. ${esc(c.title)} <span class="tag gray">${Number(c.seconds).toFixed(1)}秒</span></summary><p>${esc(c.reason)}</p><ol>${c.segments.map(seg=>`<li><button class="button small" data-studio="preview-segment" data-path="${esc(a.sources[seg.source]?.path)}" data-start="${seg.start}" data-end="${seg.end}">${esc(a.sources[seg.source]?.name)} · ${Number(seg.start).toFixed(1)}～${Number(seg.end).toFixed(1)}秒</button><span>${esc(seg.reason)}</span></li>`).join('')}</ol></details>`).join('');
 return card('剧情编排与计划预览','text',`<p class="field-hint">${esc(a.model||'文字模型')} · ${a.sources.length} 集 · ${a.clips.length} 条计划</p>${plans}`);
}
function studioClipsCard(){
 const engine=studioSelectedEngine(),clips=(activeProject().promotionClips||[]).filter(c=>studioEngineName(c.engine||c.sourceKind)===engine);
 const description=c=>studioEngineName(c.engine||c.sourceKind)==='mediakit'?'火山云端':['dramaclip','manju-dramaclip'].includes(c.engine)?'本地智能混剪 · DramaClip 融合':c.engine&&studioEngines[c.engine]?studioEngines[c.engine]:c.sourceKind==='ai_mix'?`${c.segments?.length||0}段 AI 混剪`:'手选钩子';
 const contents=clips.slice().reverse().slice(0,12).map(c=>{
  const actual=Number(c.seconds);
  const requested=engine==='mediakit'?Number(c.requestedSeconds??studioProjectJobs().find(job=>job.id===c.analysisId)?.options?.studio?.seconds):NaN;
  const durationNote=Number.isFinite(requested)&&actual>requested+.25
   ?`<small class="studio-job-error">比本次设定的 ${requested} 秒长 ${(actual-requested).toFixed(2)} 秒</small>`:'';
  return `<article class="promo-clip"><div><strong>${esc(c.title)}</strong>
   <small>${actual.toFixed(engine==='mediakit'?2:1)} 秒 · ${esc(description(c))}</small>
   ${durationNote}${engine==='mediakit'&&c.remoteTaskId?`<small>云端任务 ${esc(c.remoteTaskId)}</small>`:''}
  </div><div class="actions-row"><button class="button small" data-action="play-output" data-path="${esc(c.path)}">预览</button><a class="button small" href="${media(c.path)}&download=1">保存成片</a></div></article>`;
 }).join('');
 return card(engine==='mediakit'?'云端成片与下载':'本地混剪成片','film',contents||`<p class="field-hint">${engine==='mediakit'?'云端完成后会自动下载并校验成片，已下载的视频在这里预览或保存。':'本机编码完成的视频在这里预览或保存，保留对应制作记录。'}</p>`);
}
function studioProjectJobs(){const p=activeProject();return (state.jobs||[]).filter(j=>j.kind?.startsWith('promotion_')&&j.ids?.includes(p?.id));}
function studioBlockingJob(){return studioProjectJobs().find(j=>['queued','running','pausing','paused'].includes(j.status));}
function studioJobCard(){
 const engine=studioSelectedEngine(),cloud=engine==='mediakit',rows=studioProjectJobs().filter(j=>studioEngineName(j.options?.studio?.engine)===engine).slice().reverse().slice(0,5),blocking=studioBlockingJob(),other=blocking&&studioEngineName(blocking.options?.studio?.engine)!==engine;
 const labels={queued:'排队中',running:'处理中',pausing:'正在暂停',paused:'已暂停',interrupted:'连接中断待恢复',failed:'失败',completed:'已完成',cancelled:'已停止'};
 const cloudStages={
  uploading:'正在上传原片',submitting:'正在提交火山高光智剪',submission_unknown:'云端提交结果待核对',
  submitted:'火山已接收任务',pending:'云端排队中',queued:'云端排队中',
  running:'云端正在分析和剪辑',processing:'云端正在分析和剪辑',
  completed:'云端已生成成片',downloading:'正在下载并校验成片',completed_local:'已下载并校验成片',
  rejected:'云端拒绝提交',failed:'云端处理失败',cancelled:'云端已取消',canceled:'云端已取消'
 };
 const contents=rows.map(j=>{
  const stopped=['paused','interrupted','failed','cancelled'].includes(j.status);
  const active=['queued','running','pausing'].includes(j.status);
  const progress=Number(j.progress),resumeBlocked=blocking&&blocking.id!==j.id||studioSubmitting.has(activeProject().id);
  const cloudTask=cloud?j.mediakitTask:null;
  const remoteId=cloudTask?.taskId;
  const waitingOnCloud=active&&['submitted','pending','queued','running','processing'].includes(cloudTask?.status);
  const remoteStage=cloudTask&&Object.hasOwn(cloudStages,cloudTask.status)?cloudStages[cloudTask.status]:'';
  const consoleLink=remoteId?`<a class="button small" href="https://console.volcengine.com/imp/ai-mediakit/tool-experience?toolkey=generate-highlights-microdrama&amp;taskid=${encodeURIComponent(remoteId)}" target="_blank" rel="noopener noreferrer">${icon('external')}打开火山任务</a>`:'';
  return `<article class="studio-job">
   <div class="studio-job-heading"><strong>${esc(labels[j.status]||j.status)}</strong><small>任务 ${esc(j.id)}</small></div>
   <p>${esc(waitingOnCloud?remoteStage:j.stage||'等待处理')}</p>
   ${waitingOnCloud?`<div class="studio-job-progress"><progress aria-label="等待火山处理完成"></progress></div>`:Number.isFinite(progress)?`<div class="studio-job-progress"><progress max="100" value="${Math.max(0,Math.min(100,progress))}" aria-label="本机任务进度"></progress><span>${Math.round(progress)}%</span></div>`:''}
   ${j.error?`<p class="studio-job-error">${esc(j.diagnostic?.reason||j.error)}</p>`:''}
   ${!waitingOnCloud&&remoteStage?`<p class="field-hint">${esc(remoteStage)}${Number.isInteger(cloudTask.downloadedCount)?` · ${cloudTask.downloadedCount} 条`:''}</p>`:''}
   ${remoteId?`<p class="field-hint">云端任务 ${esc(remoteId)}</p>`:''}
   <div class="actions-row">
    ${stopped&&j.resumable!==false?`<button type="button" class="button small" data-studio="job-control" data-control="resume" data-id="${esc(j.id)}" ${resumeBlocked?'disabled title="本剧已有另一任务，先继续或停止该任务"':''}>${icon('play')}${cloud?'继续原云端任务':'继续本地任务'}</button>`:''}
    ${active&&j.status!=='pausing'?`<button type="button" class="button small" data-studio="job-control" data-control="pause" data-id="${esc(j.id)}">暂停</button>`:''}
    ${['queued','running','pausing','paused','interrupted'].includes(j.status)?`<button type="button" class="button small" data-studio="job-control" data-control="cancel" data-id="${esc(j.id)}">${cloud?'停止本机处理':'停止任务'}</button>`:''}
    ${consoleLink}<a class="button small" href="#progress" data-studio="job-detail" data-id="${esc(j.id)}">查看详细进度</a>
    <a class="button small" href="#logs" data-studio="job-logs" data-id="${esc(j.id)}">任务日志</a>
   </div>
  </article>`;
 }).join('');
 return card(cloud?'云端提交与恢复进度':'本地任务与恢复','clock',`${other?`<div class="studio-job-other">本剧已有${esc(studioEngines[studioEngineName(blocking.options?.studio?.engine)])}任务${esc(labels[blocking.status]||blocking.status)}，先继续或停止该任务。<button type="button" class="button small" data-studio="module" data-engine="${studioEngineName(blocking.options?.studio?.engine)}">查看该模块</button></div>`:''}${contents||'<p class="field-hint">当前模块还没有本剧的制作任务。</p>'}${cloud?'<p class="studio-cloud-recovery">暂停或停止仅停止本机处理，已提交的云端任务可能继续运行与计费。继续会恢复原任务查询，提交结果未知时不会自动重交。</p>':''}`);
}
function studioModuleHTML(){const p=activeProject();if(!p)return card(studioEngines[studioSelectedEngine()],'film','<p class="blank-inline">先导入一部剧，再选择素材开始混剪。</p>','',studioModuleSettings(studioSelectedEngine()));const local=studioSelectedEngine()==='local';return studioSourceCard()+`<p id="studio-save-state" class="studio-save-state" role="status">${esc(studioSaveMessages.get(p.id+'|'+studioSelectedEngine())?.text||'参数按模块自动保存到本机。')}</p><div id="studio-jobs">${studioJobCard()}</div>`+(local?`<div id="studio-analysis">${studioAnalysisCard()}</div>`:'')+`<div id="studio-clips">${studioClipsCard()}</div>`+(local?`<details class="studio-legacy"><summary>手动截取单段钩子</summary>${promoHookCard()}</details>`:'');}
function studioSettingsHTML(){
 return `<dialog id="studio-settings-dialog" class="studio-settings-dialog" aria-labelledby="studio-settings-title">
 <header class="studio-settings-header"><div><h2 id="studio-settings-title">推广挂载设置</h2><p>配置本页面的本地引擎与火山云端。</p></div><button type="button" class="icon-button" data-studio="settings-close" aria-label="关闭推广挂载设置">×</button></header>
 <div class="studio-settings-layout"><nav class="studio-settings-nav" role="tablist" aria-label="推广引擎设置" aria-orientation="vertical">${[['dramaclip','本地引擎','cpu'],['mediakit','火山云端','link']].map(([key,label,ico])=>`<button type="button" id="studio-settings-tab-${key}" role="tab" data-studio="settings-tab" data-tab="${key}" aria-controls="studio-settings-panel-${key}" aria-selected="${studioSettingsTab===key}" tabindex="${studioSettingsTab===key?0:-1}">${icon(ico)}${label}</button>`).join('')}</nav>
 <div class="studio-settings-panels"><section id="studio-settings-panel-mediakit" role="tabpanel" aria-labelledby="studio-settings-tab-mediakit" ${studioSettingsTab==='mediakit'?'':'hidden'}>
 <h3>火山 AI MediaKit</h3><p class="field-hint">上传原始短剧素材，由云端识别剧情并生成推广视频。</p>
 <div class="field"><label for="studio-mediakit-base">服务地址</label><input id="studio-mediakit-base" type="url" readonly value="https://mediakit.cn-beijing.volces.com"></div>
 <div class="field"><label for="studio-mediakit-key">MediaKit API 密钥 <span class="tag gray" id="studio-mediakit-key-status">尚未读取</span></label><input id="studio-mediakit-key" type="password" autocomplete="off" spellcheck="false" placeholder="留空保留本次运行中已设置的密钥"><p class="field-hint">使用 AI MediaKit 服务的密钥；仅保存在本次运行内存中。</p></div>
 <div class="field"><label for="studio-mediakit-cut-mode">剪辑方式</label><select id="studio-mediakit-cut-mode"><option value="Mixed">混剪 · 按剧情高光编排</option><option value="Sequential">顺剪 · 保持剧情时间顺序</option></select></div>
 <div class="field"><label for="studio-mediakit-download-folder">成片保存文件夹</label><div class="path-input"><input id="studio-mediakit-download-folder" placeholder="留空使用全局导出目录" aria-describedby="studio-mediakit-download-hint" spellcheck="false"><button type="button" class="button" data-studio="settings-browse" data-target="studio-mediakit-download-folder" data-mode="folder">${icon('folder')}选择文件夹</button></div><p class="field-hint" id="studio-mediakit-download-hint">火山成片会下载到该文件夹下对应剧集的任务子目录。设置用于之后创建的任务。</p></div>
 <p class="studio-engine-notice">单次最多30个视频，合计45分钟，最高1080p；素材需含音轨、清晰中文对白及下半部居中的中文字幕。云端按输入与输出时长计费。</p><button type="button" class="button subtle" data-studio="settings-clear-key">清除本次密钥</button>
 </section><section id="studio-settings-panel-dramaclip" role="tabpanel" aria-labelledby="studio-settings-tab-dramaclip" ${studioSettingsTab==='dramaclip'?'':'hidden'}>
 <h3>本地智能混剪</h3><p class="field-hint">融合 DramaClip 剧情规划与现有语音识别、文字 AI、FFmpeg；自动选择本机可用能力。</p>
 <details class="studio-engine-advanced"><summary>高级配置 · 已有 DramaClip 环境</summary>
 <div class="field"><label for="studio-dramaclip-root">DramaClip 程序目录（可选）</label><div class="path-input"><input id="studio-dramaclip-root" placeholder="留空自动检测" spellcheck="false"><button type="button" class="button" data-studio="settings-browse" data-target="studio-dramaclip-root" data-mode="folder">${icon('folder')}浏览</button></div></div>
 <div class="field"><label for="studio-dramaclip-python">引擎 Python（可选）</label><div class="path-input"><input id="studio-dramaclip-python" placeholder="留空使用独立引擎环境" spellcheck="false"><button type="button" class="button" data-studio="settings-browse" data-target="studio-dramaclip-python" data-mode="python">${icon('folder')}浏览</button></div></div></details>
 <input id="studio-dramaclip-mode" type="hidden" value="highlight"><div id="studio-dramaclip-status" class="studio-engine-readiness" role="status">打开设置后读取引擎状态。</div><p id="studio-dramaclip-tools" class="field-hint"></p><button type="button" class="button" data-studio="settings-refresh">${icon('refresh')}刷新引擎状态</button>
 </section></div></div><footer class="studio-settings-footer"><span id="studio-settings-result" role="status" aria-live="polite">参数保存在本机，保存后用于新建任务。</span><div class="actions-row"><button type="button" class="button" data-studio="settings-close">完成</button><button type="button" class="button primary" data-studio="settings-save">${icon('save')}保存设置</button></div></footer></dialog>`;
}
function studioSettingsResult(message,error=false){const box=$('#studio-settings-result');if(box){box.textContent=message;box.classList.toggle('error',error);}}
function studioSettingsTabSelect(tab,focus=false){
 if(!['mediakit','dramaclip'].includes(tab))return;studioSettingsTab=tab;
 for(const id of ['mediakit','dramaclip']){const button=$('#studio-settings-tab-'+id);if(!button)continue;button.setAttribute('aria-selected',String(id===tab));button.tabIndex=id===tab?0:-1;$('#studio-settings-panel-'+id).hidden=id!==tab;}
 if(focus)$('#studio-settings-tab-'+tab)?.focus();
}
function studioPopulateSettings(value){
 const settings=value?.settings||studioEngineDefaults,mediakit=settings.mediakit||studioEngineDefaults.mediakit,drama=settings.dramaclip||studioEngineDefaults.dramaclip;
 const values={'studio-mediakit-base':mediakit.base||studioEngineDefaults.mediakit.base,'studio-mediakit-cut-mode':mediakit.cutMode||'Mixed','studio-mediakit-download-folder':mediakit.downloadFolder||'','studio-dramaclip-root':drama.root||'','studio-dramaclip-python':drama.python||'','studio-dramaclip-mode':drama.mode||'highlight'};
 for(const [id,value]of Object.entries(values)){const input=$('#'+id);if(input)input.value=value;}
}
function studioSettingsStatus(value){
 const badge=$('#studio-mediakit-key-status');if(badge){badge.textContent=value?.mediakit?.hasKey?'本次运行已设置':'尚未设置';badge.className='tag '+(value?.mediakit?.hasKey?'green':'gray');}
 const status=$('#studio-dramaclip-status');if(status){status.textContent=value?.dramaclip?.message||(value?.dramaclip?.ready?'DramaClip 本地引擎已就绪。':'DramaClip 本地引擎尚未就绪。');status.classList.toggle('ready',value?.dramaclip?.ready===true);}
 const tools=$('#studio-dramaclip-tools');if(tools){const status=value?.dramaclip;tools.hidden=!status||status.ready===true;tools.textContent=status&&!status.ready?(status.missing?.length?'增强组件缺少：'+status.missing.join('、')+'。':'')+'增强功能需要安装配套本地引擎包。':'';}
 studioUpdateEngineUI();
}
async function studioLoadEngineSettings(populate=false){
 const seq=++studioEngineRead,dialog=$('#studio-settings-dialog');
 try{
  const result=await api('promotion/engines');if(seq!==studioEngineRead)return;
  studioEngineState=result;
  if(dialog?.isConnected){if(populate&&!dialog.dataset.dirty&&!studioSettingsSaving)studioPopulateSettings(result);studioSettingsStatus(result);}
  return result;
 }catch(error){if(seq===studioEngineRead){studioSettingsResult(error.message,true);if($('#studio-engine-status'))$('#studio-engine-status').textContent=error.message;}throw error;}
}
async function studioSaveEngineSettings(clear=false){
 const dialog=$('#studio-settings-dialog');if(!dialog||studioSettingsSaving)return;
 const key=$('#studio-mediakit-key').value.trim();
 if(!clear&&key&&(key.length>4096||/[\s\u0000-\u001f]/.test(key))){studioSettingsResult('密钥包含空白、换行或长度异常，请核对后保存。',true);$('#studio-mediakit-key').focus();return;}
 const body={settings:{mediakit:{base:$('#studio-mediakit-base').value,cutMode:$('#studio-mediakit-cut-mode').value,downloadFolder:$('#studio-mediakit-download-folder').value.trim()},dramaclip:{root:$('#studio-dramaclip-root').value.trim(),python:$('#studio-dramaclip-python').value.trim(),mode:$('#studio-dramaclip-mode').value}}};
 if(clear)body.clearMediakitKey=true;else if(key)body.mediakitKey=key;
 studioSettingsSaving=true;++studioEngineRead;
 const controls=$$('.studio-settings-panels input,.studio-settings-panels select,.studio-settings-panels button,[data-studio="settings-save"]',dialog);controls.forEach(el=>el.disabled=true);
 studioSettingsResult(clear?'正在清除会话密钥…':'正在保存设置…');
 try{
  const result=await api('promotion/engines/settings',body);studioEngineState=result;
  if(dialog.isConnected){$('#studio-mediakit-key').value='';delete dialog.dataset.dirty;studioPopulateSettings(result);studioSettingsStatus(result);studioSettingsResult(clear?'本次密钥已清除。':'设置已保存，后续新建任务使用此配置。');}
 }catch(error){if(dialog.isConnected)studioSettingsResult(error.message,true);}
 finally{studioSettingsSaving=false;controls.forEach(el=>el.disabled=false);}
}
async function studioSettingsAction(action,button){
 if(!action.startsWith('settings-'))return false;
 const dialog=$('#studio-settings-dialog');
 if(action==='settings-open'){
  studioSettingsTrigger=button;studioSettingsTab=button.dataset.tab||(studioSelectedEngine()==='mediakit'?'mediakit':'dramaclip');delete dialog.dataset.dirty;studioPopulateSettings(studioEngineState);$('#studio-mediakit-key').value='';studioSettingsResult('正在读取引擎设置…');dialog.showModal();studioSettingsTabSelect(studioSettingsTab,true);
  try{await studioLoadEngineSettings(true);if(dialog.open&&!dialog.dataset.dirty)studioSettingsResult('参数保存在本机，保存后用于新建任务。');}catch{}
 }else if(action==='settings-close')dialog.close();
 else if(action==='settings-tab')studioSettingsTabSelect(button.dataset.tab,true);
 else if(action==='settings-save')await studioSaveEngineSettings();
 else if(action==='settings-clear-key')await studioSaveEngineSettings(true);
 else if(action==='settings-refresh'){studioSettingsResult('正在读取已保存的引擎状态…');try{await studioLoadEngineSettings(false);studioSettingsResult(dialog.dataset.dirty?'状态已刷新；当前修改尚未保存。':'引擎状态已刷新。');}catch{}}
 else if(action==='settings-browse'){
  button.disabled=true;try{const result=await api('browse',{mode:button.dataset.mode});if(result.path&&dialog.isConnected){$('#'+button.dataset.target).value=result.path;dialog.dataset.dirty='true';studioSettingsResult('目录已选择，点击保存后生效。');}}finally{if(button.isConnected)button.disabled=false;}
 }
 return true;
}
promotionPage=function(){queueMicrotask(()=>{if(!studioEngineState&&!studioInitialEngineRead)studioInitialEngineRead=studioLoadEngineSettings(false).catch(()=>{}).finally(()=>studioInitialEngineRead=null);});return intro('推广挂载','')+picker()+studioModuleTabs()+`<section id="studio-module-panel" role="tabpanel" aria-labelledby="studio-module-${studioSelectedEngine()}">${studioModuleHTML()}</section>`+studioSettingsHTML();};
const studioBaseTaskbar=renderTaskbar;
renderTaskbar=function(){studioBaseTaskbar();if(current!=='promotion')return;const p=activeProject(),d=studioDraft(),engine=studioSelectedEngine(),blocked=!p||!d.sourcePaths?.length||!!studioBlockingJob()||studioSubmitting.has(p.id),b=$('#start-pipeline');b.dataset.action='studio-run';b.innerHTML=icon(engine==='mediakit'?'upload':'film')+(engine==='mediakit'?'提交云端生成':'生成本地混剪');b.disabled=blocked;for(const button of $$('[data-studio="auto"]'))button.disabled=blocked;$('#task-detail').textContent=p?`${studioEngines[engine]} · ${studioBlockingJob()?'本剧已有任务，先继续或停止':'按当前模块参数生成成片'}`:'选择素材开始生成推广视频';};
function studioSaveState(projectId,engine,text,error=false){const key=projectId+'|'+engine;studioSaveMessages.set(key,{text,error});if(activeProject()?.id===projectId&&studioSelectedEngine()===engine){const node=$('#studio-save-state');if(node){node.textContent=text;node.classList.toggle('error',error);}}}
async function studioSave(draft=studioDraft(),project=activeProject(),strict=true){
 const request=structuredClone(draft),pid=project.id,engine=studioEngineName(request.engine);
 if(!request.sourcePaths?.length){const message='选集为空，当前修改尚未保存；请选择原片后继续。';studioSaveState(pid,engine,message,true);if(strict)throw Error(message);return;}
 studioSaveState(pid,engine,'正在保存'+studioEngines[engine]+'参数…');
 const save=studioEngineSave.catch(()=>{}).then(()=>api('promotion/studio-settings',{projectId:pid,settings:request}));studioEngineSave=save;
 try{const result=await save,currentProject=state.projects.find(p=>p.id===pid);if(currentProject){currentProject.promotionStudio=result.settings;currentProject.promotionStudioByEngine=result.settingsByEngine||{...currentProject.promotionStudioByEngine,[engine]:result.settings};}
  for(const [key,value]of Object.entries(result.settings||{}))if(JSON.stringify(draft[key])===JSON.stringify(request[key]))draft[key]=value;
  const changed=['sourcePaths','count','seconds','direction','cta','engine'].some(key=>JSON.stringify(draft[key])!==JSON.stringify(result.settings?.[key]));studioSaveState(pid,engine,changed?'参数已有新修改，正在保留当前输入。':studioEngines[engine]+'参数已保存。');return result.settings;
 }catch(error){studioSaveState(pid,engine,studioEngines[engine]+'保存失败：'+error.message,true);throw error;}
}
async function studioSwitchModule(engine){
 engine=studioEngineName(engine);const p=activeProject(),oldEngine=studioSelectedEngine();if(oldEngine===engine)return;
 const oldDraft=p?studioDraft():null;if(p)studioActiveEngines.set(p.id,engine);else studioEmptyEngine=engine;
 for(const video of $$('#studio-module-panel video'))video.pause();
 if($('#studio-engine'))$('#studio-engine').value=engine;
 for(const tab of $$('.studio-module-tabs [role="tab"]')){const selected=tab.dataset.engine===engine;tab.setAttribute('aria-selected',String(selected));tab.tabIndex=selected?0:-1;}
 const panel=$('#studio-module-panel');if(panel){panel.setAttribute('aria-labelledby','studio-module-'+engine);panel.innerHTML=studioModuleHTML();}
 renderTaskbar();
 if(p){const previous=studioSave(oldDraft,p,false),next=studioSave(studioDraft(),p,false);for(const result of await Promise.allSettled([previous,next]))if(result.status==='rejected')toast(result.reason.message,true);}
}
function studioSourceCount(){const p=activeProject(),d=studioDraft();if($('#studio-source-count'))$('#studio-source-count').textContent=`选择原片 · 已选 ${d.sourcePaths.length} / ${p.videos.length} 集`;if($('#studio-cloud-selection'))$('#studio-cloud-selection').textContent=studioCloudSelection();renderTaskbar();}
document.addEventListener('input',e=>{
 const el=e.target;if(el.closest('#studio-settings-dialog')){el.closest('dialog').dataset.dirty='true';studioSettingsResult('修改尚未保存。');return;}
 if(el.dataset.studioField&&!['checkbox','select-one'].includes(el.type)){const k=el.dataset.studioField;studioDraft()[k]=['count','seconds'].includes(k)?Number(el.value):el.value;}
});
document.addEventListener('change',async e=>{const el=e.target;try{
 if(el.closest('#studio-settings-dialog')){el.closest('dialog').dataset.dirty='true';studioSettingsResult('修改尚未保存。');return;}
 if(el.dataset.studioField){const k=el.dataset.studioField;if(k==='engine'){await studioSwitchModule(el.value);return;}const draft=studioDraft();draft[k]=el.type==='checkbox'?el.checked:['count','seconds'].includes(k)?Number(el.value):el.value;await studioSave(draft,activeProject(),false);}
 if(el.dataset.studioSource){const d=studioDraft();d.sourcePaths=d.sourcePaths.filter(p=>p!==el.dataset.studioSource);if(el.checked)d.sourcePaths.push(el.dataset.studioSource);const order=activeProject().videos.map(v=>v.path);d.sourcePaths.sort((a,b)=>order.indexOf(a)-order.indexOf(b));studioSourceCount();await studioSave(d,activeProject(),false);}
 if(el.id==='studio-rights'){await api('project',{id:activeProject().id,rights:el.checked});await refresh();}
 }catch(error){toast(error.message,true);}});
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-studio],[data-action="studio-run"]');if(!b||b.disabled)return;const action=b.dataset.studio||'auto';
 if(action.startsWith('settings-')){try{await studioSettingsAction(action,b);}catch(error){studioSettingsResult(error.message,true);}return;}
 if(action==='module'){await studioSwitchModule(b.dataset.engine);return;}
 if(action==='job-detail'||action==='job-logs'){e.preventDefault();if(action==='job-detail'){if(typeof monitorId!=='undefined')monitorId=b.dataset.id;location.hash='progress';}else{logJob=b.dataset.id;location.hash='logs';}return;}
 b.disabled=true;try{
  const p=activeProject(),d=studioDraft();
  if(action==='save'){await studioSave();toast('混剪设置已保存');}
  else if(action==='select-all'||action==='clear-selection'){d.sourcePaths=action==='select-all'?p.videos.map(v=>v.path):[];for(const input of $$('[data-studio-source]'))input.checked=d.sourcePaths.includes(input.dataset.studioSource);studioSourceCount();await studioSave(d,p,false);}
  else if(action==='job-control'){await api('jobs/control',{id:b.dataset.id,action:b.dataset.control});await refresh();toast(b.dataset.control==='resume'?'已加入原任务恢复队列':b.dataset.control==='pause'?'正在暂停本机处理':'正在停止本机处理');}
  else if(['analyse','auto','render'].includes(action)){
   if(action!=='auto')throw Error('请直接使用「一键生成推广视频」。');
   if(studioBlockingJob()||studioSubmitting.has(p.id))throw Error('本剧已有任务，请先继续或停止原任务。');
   studioSubmitting.add(p.id);renderTaskbar();const request=structuredClone(d),rights=$('#studio-rights')?.checked??p.rights;
   try{await api('project',{id:p.id,rights});const saved=await studioSave(request,p);const r=await api('jobs',{kind:'promotion_auto',ids:[p.id],studio:saved});await refresh();toast(`${studioEngines[request.engine]}已进入队列，任务 ${r.id}`);}finally{studioSubmitting.delete(p.id);renderTaskbar();}
  }else if(action==='preview-segment'){const v=$('#output-video');$('#output-dialog').showModal();v.src=media(b.dataset.path);v.onloadedmetadata=()=>{v.currentTime=Number(b.dataset.start);};v.ontimeupdate=()=>{if(v.currentTime>=Number(b.dataset.end))v.pause();};}
 }catch(error){toast(error.message,true);}finally{if(b.isConnected)b.disabled=false;renderTaskbar();}
});
document.addEventListener('keydown',e=>{
 if(e.target.closest('.studio-module-tabs [role="tab"]')){let engine;if(['ArrowLeft','ArrowRight'].includes(e.key))engine=studioSelectedEngine()==='local'?'mediakit':'local';if(e.key==='Home')engine='local';if(e.key==='End')engine='mediakit';if(engine){e.preventDefault();studioSwitchModule(engine).catch(error=>toast(error.message,true));$('#studio-module-'+engine)?.focus();}return;}
 if(!e.target.closest('#studio-settings-dialog [role="tab"]'))return;
 let tab;if(['ArrowDown','ArrowRight','ArrowUp','ArrowLeft'].includes(e.key))tab=studioSettingsTab==='mediakit'?'dramaclip':'mediakit';if(e.key==='Home')tab='dramaclip';if(e.key==='End')tab='mediakit';if(tab){e.preventDefault();studioSettingsTabSelect(tab,true);}
});
document.addEventListener('close',e=>{if(e.target.id==='studio-settings-dialog'){++studioEngineRead;const input=$('#studio-mediakit-key');if(input)input.value='';if(studioSettingsTrigger?.isConnected)studioSettingsTrigger.focus({preventScroll:true});}},true);
document.addEventListener('click',e=>{if(e.target.closest('[data-action="play-output"]')){const v=$('#output-video');v.onloadedmetadata=null;v.ontimeupdate=null;}},true);
const studioBaseRefresh=refresh;
refresh=async function(render=false){
 await studioBaseRefresh(render);if(current!=='promotion'||!activeProject())return;
 const sections=[
  ['studio-jobs',JSON.stringify(studioProjectJobs().map(j=>[j.id,j.status,j.stage,j.progress,j.error,j.result,j.mediakitTask])),studioJobCard],
  ['studio-analysis',activeProject().promotionAnalysis?.id||'empty',studioAnalysisCard],
  ['studio-clips',JSON.stringify(activeProject().promotionClips?.map(c=>[c.id,c.path,c.engine,c.sourceKind,c.seconds,c.requestedSeconds,c.analysisId])),studioClipsCard]
 ];
 for(const [id,signature,renderSection]of sections){const target=$('#'+id);if(target&&target.dataset.signature!==signature){target.dataset.signature=signature;target.innerHTML=renderSection();}}
};
})();
