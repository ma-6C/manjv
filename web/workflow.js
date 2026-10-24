'use strict';

let studioIndex=0,regionIndex=0,studioDraft=null,studioDrag=null,previewSignature='';
const studioTimes=new Map();
const jobLabels={pipeline:'完整制作',transcode:'重组分集',subtitle:'去字幕',preview:'短片试处理',playback:'兼容播放预览',video_generate:'历史视频生成（已停用）',highlight:'高光包装',cover:'制作封面',coverAI:'AI封面',rewrite:'AI文案',records:'工程记录',cost:'成本报告',package:'材料包',upload:'视频上传',login:'账号登录'};
const statusLabels={queued:'排队中',running:'处理中',pausing:'正在暂停',paused:'已暂停',interrupted:'待恢复',completed:'已完成',failed:'失败',cancelled:'已停止'};
function regions(){return studioDraft||state.config.subtitleRegions?.length&&state.config.subtitleRegions||[state.config.subtitleRegion];}
function studioVideo(){const p=activeProject();return p?.videos[Math.min(studioIndex,p.videos.length-1)];}
function studioSource(){const v=studioVideo(),proxy=activeProject()?.sourcePreviewPaths?.[v?.path];return proxy?.bytes===v?.bytes&&(!v.mtime||proxy.mtime===v.mtime)?proxy.path:v?.path;}
function timecode(t){t=Math.max(0,t||0);return `${Math.floor(t/60)}:${(t%60).toFixed(2).padStart(5,'0')}`;}
function pipelineActivitySteps(job=null){
 if(job)return job.workflowPlan||[[jobLabels[job.kind]||'当前任务',job.kind==='transcode'?'单步完成后结束':'按本次任务执行',job.kind==='transcode'?['video']:[]]];
 const c=state.config,steps=[];
 if(c.autoText)steps.push(['AI 剧名与简介','根据原始简介生成',['text']]);
 if(c.subtitleAuto)steps.push(['先修复字幕',c.subtitleMode==='vsr'?'本地 AI · 全部源视频':'全部源视频',['subtitle']]);
 steps.push(['画面处理与分集',c.regroup?`每集 ${c.segmentSeconds} 秒`:'保持源分集',['video']]);
 if(c.pipelineHighlight)steps.push(['成片包装','使用处理后的最终分集',['highlight']]);
 if(c.autoCover)steps.push(['封面','生成剧集封面',['cover']]);
 if(c.autoRecords)steps.push(['工程记录','保存真实帧与文件校验值',['records']]);
 if(c.autoCost)steps.push(['成本报告','按实际支出生成',['cost']]);
 return steps;
}
function productionPlanItemsHTML(){return pipelineActivitySteps().map(([title,desc])=>`<li><strong>${esc(title)}</strong><span>${esc(desc)}</span></li>`).join('');}
function productionRunHTML(){return card('运行当前剧集','film',picker()+`<div class="production-run-actions">${jobButton('pipeline','开始连续制作')}${jobButton('transcode','仅合并切分',false)}</div><p id="production-run-summary" class="field-hint">本次将执行：${pipelineActivitySteps().map(s=>esc(s[0])).join(' → ')}</p><p class="field-hint">连续制作会自动执行下方已开启的步骤；仅合并切分会在分集保存后结束。</p><div id="production-handoff">${productionHandoffHTML()}</div>`);}
function productionSetupHTML(){
 return card('连续制作步骤','layers',`<p class="section-description">开始后按以下顺序自动执行已开启的步骤，合并切分完成后继续后续任务。</p><ol id="production-config-plan" class="production-plan" aria-label="连续制作顺序">${productionPlanItemsHTML()}</ol><div class="production-options">`+
 toggle('先修复字幕','subtitleAuto','使用 AI 去字幕页配置的模式和选区，处理全部所选视频后再合并。')+
 toggle('AI 剧名与简介','autoText','使用已选择的文字接口；缺少配置时在开始前提示。')+
 toggle('合并后生成高光包装','pipelineHighlight','直接使用本次分集结果继续包装。')+
 toggle('自动制作封面','autoCover','使用本地排版；生图方式沿用 AI 接口页的封面配置。')+
 toggle('生成工程记录','autoRecords','记录实际源帧、参数和成片校验值。')+
 toggle('生成成本报告','autoCost','按成本报告页填写的实际金额生成。')+`</div><p class="field-hint">字幕选区在 <a href="#subtitle">AI 去字幕</a> 调整，文案接口在 <a href="#api">AI 接口</a> 配置。完成所选步骤后可核对发布材料。</p>`);
}
function productionContinuationButton(job){
 if(job?.kind!=='transcode'||job.status!=='completed')return '';
 const child=state.jobs.find(j=>j.options?.continueFromJob===job.id&&j.status!=='cancelled');
 return child?`<button class="button small" data-action="production-view" data-id="${esc(child.id)}">查看后续制作</button>`:`<button class="button small primary" data-action="continue-production" data-id="${esc(job.id)}">继续后续制作</button>`;
}
function productionHandoffHTML(){
 const p=activeProject(),job=[...state.jobs].reverse().find(j=>j.ids.includes(p?.id)&&['pipeline','transcode'].includes(j.kind));
 if(!job)return '';
 const single=job.kind==='transcode',done=job.status==='completed';
 return `<div class="production-handoff ${job.status==='failed'?'failed':''}" role="status"><strong>${single?'合并切分任务':'连续制作任务'} · ${esc(statusLabels[job.status]||job.status)}</strong><p>${esc(job.error||(done?(single?'分集已保存；本次只执行了合并切分，可复用这些文件继续已启用的后续步骤。':'本次所选制作步骤已完成，可以核对成片和发布材料。'):job.stage))}</p><div class="actions-row">${productionContinuationButton(job)}<button class="button small" data-action="production-view" data-id="${esc(job.id)}">查看制作进度</button>${done&&!single?'<a class="button small" href="#publish">核对发布材料</a>':''}</div>${done&&single?'<p class="field-hint">接续使用当前勾选的文案、包装、封面、工程与成本设置，保留原选集和分集文件。字幕修复应从连续制作入口在合并前完成。</p>':''}</div>`;
}
function subtitleWorkspaceHTML(){
 const p=activeProject();if(p)studioIndex=Math.min(studioIndex,p.videos.length-1);
 studioDraft=structuredClone(state.config.subtitleRegions?.length?state.config.subtitleRegions:[state.config.subtitleRegion]);
 regionIndex=Math.min(regionIndex,regions().length-1);
 const v=studioVideo(),r=regions()[regionIndex],f=(label,key)=>`<div class="field"><label for="region-${key}">${label}</label><input id="region-${key}" data-region="${key}" type="number" min="0" max="1" step="0.001" value="${r[key]}"></div>`;
 const editor=v?`<div class="studio-source-row"><label for="studio-video">源视频</label><select id="studio-video">${p.videos.map((v,i)=>`<option value="${i}" ${i===studioIndex?'selected':''}>${esc(v.name)}</option>`).join('')}</select><span>${v.width} × ${v.height}</span></div>
  <p id="studio-compatibility" class="field-hint">${v.codec==='hevc'?'HEVC 素材会先准备兼容播放副本。':''}<button class="table-action" data-action="studio-proxy">画面无法显示时，生成兼容预览</button><span id="studio-proxy-status"></span></p>
  <div class="studio-stage"><div class="studio-frame" style="--ratio:${v.width/v.height};aspect-ratio:${v.width}/${v.height}"><video id="subtitle-source" src="${media(studioSource())}" preload="metadata" muted playsinline></video><div id="subtitle-selection-layer" aria-label="在画面上拖动框选字幕，或使用下方数字输入"></div></div></div>
  <div class="studio-transport"><button class="button small" data-action="studio-play" aria-label="播放或暂停源视频">${icon('play')}播放</button><button class="button small" data-action="studio-step" data-offset="-1" aria-label="后退1秒">−1s</button><input id="studio-seek" type="range" min="0" max="${v.duration}" step="0.033333" value="0" aria-label="视频时间轴"><button class="button small" data-action="studio-step" data-offset="1" aria-label="前进1秒">+1s</button><output id="studio-clock">0:00.00 / ${timecode(v.duration)}</output></div>
  <div class="region-toolbar"><div id="region-tabs"></div><button class="button small" data-action="region-add">${icon('plus')}添加选区</button><button class="button small" data-action="region-remove">${icon('trash')}删除当前</button></div><p class="field-hint">拖动画面空白处重画当前选区；拖动选区可移动，右下角可缩放。也可用下方比例输入精确调整，最多保存 8 个选区。</p>
  <div class="grid-2">${f('左侧位置比例 x','x')}${f('顶部位置比例 y','y')}${f('区域宽度比例 w','w')}${f('区域高度比例 h','h')}</div>`:'<p class="blank-inline">先导入视频，即可在真实画面中框选字幕。</p>';
 return intro('AI 去字幕','框选字幕区域后，可直接处理完整一集或连续处理整部剧；5 秒和 10 秒仅用于试处理。')+picker()+
  card('整片去字幕','film',`<p class="section-description">只修复框选区域，覆盖每集从 0 秒到结尾的全部时长，保留原片音轨。多集会自动接着处理，无需逐集确认。</p><p id="subtitle-full-scope" class="field-hint">${v?`当前整集：${esc(v.name)} · ${timecode(v.duration)}；整剧：${p.videos.length} 集 · 合计 ${duration(p.videos.reduce((sum,item)=>sum+item.duration,0))}。`:'先导入素材，再选择要处理的剧集。'}当前方式：${esc(({vsr:'本地 AI 修复',local:'本地区域修补',cloud:'云端 AI 适配器'})[state.config.subtitleMode]||'未选择')}。</p><div class="actions-row subtitle-full-actions"><button class="button primary" data-action="subtitle-full" data-scope="current" ${!v?'disabled':''}>${icon('film')}当前整集去字幕</button><button class="button" data-action="subtitle-full" data-scope="series" ${!v?'disabled':''}>${icon('layers')}整剧连续去字幕 · ${p?.videos.length||0} 集</button></div><div id="subtitle-full-error" class="source-read-error" role="alert" tabindex="-1" hidden></div><div id="subtitle-full-result" aria-live="polite"></div>`)+
  card('画面与字幕选区','subtitle',editor+saveFooter())+
  card('短片试处理','play',`<p class="section-description">从当前播放位置截取短片，使用本页设置处理。两侧同步播放，可直接检查字幕残留与背景修复。</p><div class="actions-row"><button class="button primary" data-action="subtitle-preview" data-seconds="5" ${v?'':'disabled'}>${icon('play')}试处理 5 秒</button><button class="button" data-action="subtitle-preview" data-seconds="10" ${v?'':'disabled'}>试处理 10 秒</button><a class="button subtle" href="#logs">查看任务队列</a></div><div id="subtitle-preview-result"></div>`)+
  connectionTaskCard(['subtitle'])+card('完整制作设置','layers',field('字幕处理方式','subtitleMode',{options:[['vsr','本地 AI · VSR'],['local','本地区域修补 · delogo'],['cloud','云端 AI 适配器']]})+
   alert(state.config.subtitleMode==='local'?'区域修补用周围像素填充，复杂背景可能变平滑。请先检查试处理效果。':state.config.subtitleMode==='vsr'?'本地神经网络修复使用已安装的 VSR 引擎，无需云端密钥。':'云端需要配置服务适配器；当前契约只支持一个字幕选区。')+
   toggle('完整流水线先去字幕','subtitleAuto','开启后，全部源视频先去字幕，再调色、变速、合并与分集；最终分集用于包装、材料包和上传。')+
   '<p class="field-hint">上方「当前整集」处理源视频下拉框选中的完整视频；「整剧连续」处理当前剧集的全部已导入视频。自由选集可从红果素材页发起「仅去字幕 · 全部所选集」。</p>'+saveFooter())+
  card('本地 AI 引擎','cpu',field('VSR 项目目录','vsrRoot',{browse:true})+field('引擎 Python','vsrPython',{browse:true})+field('修补模型','vsrMode',{options:[['sttn-auto','STTN 自动模式'],['sttn-det','STTN · 字幕检测模式'],['lama','LaMa'],['propainter','ProPainter']]})+toggle('批量复用 AI 模型','vsrReuseWorker','STTN 自动模式连续多集共用工作进程与模型，空闲2分钟释放；暂停会终止当前修复。关闭后逐集启动，其他模型沿用原方式。')+'<p class="field-hint">只选择已安装完整依赖与权重的模型。本机已实测 STTN 自动模式；其他模型需单独准备检测依赖。</p>'+saveFooter())+
  card('云端服务连接','link',field('字幕适配器 HTTPS 地址','subtitleEndpoint',{placeholder:'https://你的服务/video/clear'})+field('异步任务轮询地址','subtitlePoll',{placeholder:'https://你的服务/video/status'})+`<div class="field"><label for="subtitle-key">字幕服务密钥</label><input id="subtitle-key" type="password" autocomplete="off" placeholder="仅在本次服务进程中保存"></div><button class="button" data-action="save-subtitle-key">设置本次会话密钥</button><p class="field-hint">POST {video_base64, filename, region}；同步响应 {status, video_url}，异步响应 {task_id, status}。文件上限 80MB。</p>`)+filesCard(['AI字幕处理','字幕处理']);
}
function updateFullSubtitleResult(){
 const target=$('#subtitle-full-result');if(!target)return;
 const p=activeProject(),job=state.jobs.filter(j=>j.kind==='subtitle'&&j.ids.includes(p?.id)).at(-1);
 if(!job){target.innerHTML='<p class="field-hint">整片处理结果会在这里显示，也可在任务与日志中暂停或恢复。</p>';return;}
 const files=p.artifacts.filter(a=>a.job===job.id&&['AI字幕处理','字幕处理'].includes(a.kind)),total=job.options?.sourceVideoPaths?.[p.id]?.length||p.videos.length;
 const html=`<div class="production-handoff ${job.status==='failed'?'failed':''}"><strong>整片去字幕 · ${esc(statusLabels[job.status]||job.status)}</strong><p>已完成 ${files.length} / ${total} 集 · ${esc(job.error||job.stage)}</p>${typeof monitorBar==='function'?monitorBar(job.status==='completed'?{percent:100}:job.telemetry?.current,job):''}<div class="actions-row"><button class="button small" data-action="production-view" data-id="${esc(job.id)}">查看详细进度</button>${['failed','paused','interrupted'].includes(job.status)?`<button class="button small" data-action="control-job" data-id="${esc(job.id)}" data-control="resume">继续未完成集数</button>`:''}</div>${files.length?`<div class="file-list">${files.slice(-10).map(fileItem).join('')}</div>`:''}</div>`;
 if(target.innerHTML!==html)target.innerHTML=html;
}
function drawRegions(){
 const layer=$('#subtitle-selection-layer');if(!layer)return;
 layer.innerHTML=regions().map((r,i)=>`<div class="studio-region ${regionIndex===i?'active':''}" data-studio-region="${i}" style="left:${r.x*100}%;top:${r.y*100}%;width:${r.w*100}%;height:${r.h*100}%"><span>选区 ${i+1}</span>${i===regionIndex?'<i data-resize-region="1" aria-hidden="true"></i>':''}</div>`).join('');
 $('#region-tabs').innerHTML=regions().map((r,i)=>`<button class="region-tab ${i===regionIndex?'active':''}" data-action="region-select" data-index="${i}" aria-pressed="${i===regionIndex}">选区 ${i+1}</button>`).join('');
 const r=regions()[regionIndex];for(const key of ['x','y','w','h']){const el=$('#region-'+key);if(el&&document.activeElement!==el)el.value=Number(r[key].toFixed(5));}
 $('[data-action="region-add"]').disabled=regions().length>=8;
 $('[data-action="region-remove"]').disabled=regions().length<=1;
}
async function saveRegions(){
 const value=structuredClone(regions());
 await updateConfig({subtitleRegion:value[0],subtitleRegions:value});drawRegions();updatePreviewResult(true);
}
async function changeRegionNumber(key,value){
 if(!Number.isFinite(value))throw Error('请输入有效的字幕比例');
 const r=regions()[regionIndex];r[key]=Math.max((key==='w'||key==='h') ? .002 : 0,Math.min(1,value));
 r.x=Math.min(r.x,.998);r.y=Math.min(r.y,.998);r.w=Math.max(.002,Math.min(r.w,1-r.x));r.h=Math.max(.002,Math.min(r.h,1-r.y));
 await saveRegions();
}
function pointInStudio(e){const b=$('#subtitle-selection-layer').getBoundingClientRect();return{x:Math.max(0,Math.min(1,(e.clientX-b.left)/b.width)),y:Math.max(0,Math.min(1,(e.clientY-b.top)/b.height))};}
function mountSubtitleStudio(){
 const video=$('#subtitle-source'),layer=$('#subtitle-selection-layer');if(!video||!layer)return;
 const key=activeProject().id+':'+studioIndex;
 video.addEventListener('loadedmetadata',()=>{video.currentTime=Math.min(studioTimes.get(key)||0,Math.max(0,video.duration-.01));});
 video.addEventListener('timeupdate',()=>{if(!video.isConnected)return;studioTimes.set(key,video.currentTime);const seek=$('#studio-seek'),clock=$('#studio-clock');if(seek)seek.value=video.currentTime;if(clock)clock.textContent=timecode(video.currentTime)+' / '+timecode(video.duration);});
 const updatePlay=()=>{if(!video.isConnected)return;const button=$('[data-action="studio-play"]');if(button)button.innerHTML=icon('play')+(video.paused?'播放':'暂停');};
 video.addEventListener('play',updatePlay);video.addEventListener('pause',updatePlay);
 video.addEventListener('error',()=>{const hint=$('#studio-proxy-status');if(hint)hint.textContent=' 原片编码暂不支持，请生成兼容预览。';});
 $('#studio-seek').addEventListener('input',e=>{video.currentTime=Number(e.target.value);});
 layer.addEventListener('pointerdown',e=>{
  if(e.button!==0)return;e.preventDefault();video.pause();
  const target=e.target.closest('[data-studio-region]');if(target)regionIndex=Number(target.dataset.studioRegion);
  studioDrag={pointer:e.pointerId,start:pointInStudio(e),rect:{...regions()[regionIndex]},type:e.target.closest('[data-resize-region]')?'resize':target?'move':'draw'};
  layer.setPointerCapture(e.pointerId);drawRegions();
 });
 layer.addEventListener('pointermove',e=>{
  if(!studioDrag||studioDrag.pointer!==e.pointerId)return;
  const q=pointInStudio(e),d=studioDrag,a=d.start,o=d.rect;let r;
  if(d.type==='move')r={...o,x:Math.max(0,Math.min(1-o.w,o.x+q.x-a.x)),y:Math.max(0,Math.min(1-o.h,o.y+q.y-a.y))};
  else if(d.type==='resize')r={...o,w:Math.max(.002,Math.min(1-o.x,q.x-o.x)),h:Math.max(.002,Math.min(1-o.y,q.y-o.y))};
  else r={x:Math.min(a.x,q.x,.998),y:Math.min(a.y,q.y,.998),w:Math.max(.002,Math.abs(q.x-a.x)),h:Math.max(.002,Math.abs(q.y-a.y))};
  r.w=Math.min(r.w,1-r.x);r.h=Math.min(r.h,1-r.y);studioDraft[regionIndex]=r;drawRegions();
 });
 const finish=async e=>{if(!studioDrag||studioDrag.pointer!==e.pointerId)return;studioDrag=null;try{await saveRegions();}catch(err){toast(err.message,true);}};
 layer.addEventListener('pointerup',finish);layer.addEventListener('pointercancel',finish);
 drawRegions();updatePreviewResult(true);updateStudioProxy();updateFullSubtitleResult();
 if(studioVideo().codec==='hevc'&&studioSource()===studioVideo().path)prepareStudioProxy().catch(e=>toast(e.message,true));
}
async function prepareStudioProxy(){
 const p=activeProject();if(state.jobs.some(j=>j.kind==='playback'&&j.ids.includes(p.id)&&j.options?.videoIndex===studioIndex&&['queued','running','pausing'].includes(j.status)))return;
 await api('jobs',{kind:'playback',ids:[p.id],videoIndex:studioIndex});await refresh();updateStudioProxy();
}
function updateStudioProxy(){
 const v=$('#subtitle-source');if(!v)return;
 const source=studioSource();if(v.getAttribute('src')!==media(source)){const t=v.currentTime;v.src=media(source);v.addEventListener('loadedmetadata',()=>{v.currentTime=t;},{once:true});}
 const job=state.jobs.filter(j=>j.kind==='playback'&&j.ids.includes(activeProject()?.id)&&j.options?.videoIndex===studioIndex).at(-1);
 const hint=$('#studio-proxy-status');if(hint)hint.textContent=job?` ${statusLabels[job.status]}${job.status==='completed'?' · 使用兼容播放副本，制作仍读取原片':job.error?' · '+job.error:' · '+job.stage}`:'';
}
function updatePreviewResult(force=false){
 const target=$('#subtitle-preview-result');if(!target)return;
 const p=activeProject(),job=state.jobs.filter(j=>j.kind==='preview'&&j.ids.includes(p?.id)&&j.options?.videoIndex===studioIndex).at(-1);
 const signature=JSON.stringify([job?.id,job?.status,job?.error,job?.result,regions(),state.config.subtitleMode]);
 if(!force&&signature===previewSignature)return;previewSignature=signature;
 if(!job){target.innerHTML='<p class="field-hint">试处理完成后会在这里显示原片与处理结果。</p>';return;}
 if(job.status!=='completed'){
  target.innerHTML=`<div class="preview-wait"><strong>${statusLabels[job.status]||job.status}</strong><span>${esc(job.error||job.stage)}</span><a href="#logs">查看任务</a></div>`;return;
 }
 const result=job.result,stale=JSON.stringify(result.regions)!==JSON.stringify(regions())||result.mode!==state.config.subtitleMode;
 target.innerHTML=`<div class="preview-summary"><strong>试处理完成</strong><span>${timecode(result.start)} 起 · ${result.seconds.toFixed(2)} 秒</span>${stale?'<b>选区或模式已改变，请重新试处理</b>':''}</div><div class="preview-pair"><div><span>处理前 · 原片</span><video id="preview-before" src="${media(result.before)}" controls preload="metadata" playsinline></video></div><div><span>处理后 · ${result.mode==='vsr'?'AI 修复':result.mode==='local'?'区域修补':'云端 AI'}</span><video id="preview-after" src="${media(result.after)}" preload="metadata" muted playsinline></video></div></div><p class="field-hint">用左侧播放器控制两侧播放和拖动；声音来自左侧原片。</p><div class="actions-row"><button class="button small" data-action="play-output" data-path="${esc(result.after)}">${icon('play')}单独查看处理结果</button><a href="${media(result.after)}&download=1">下载试处理视频</a></div>`;
 const before=$('#preview-before'),after=$('#preview-after');
 const sync=()=>{if(Number.isFinite(after.duration))after.currentTime=Math.min(before.currentTime,after.duration);};
 before.addEventListener('play',()=>{sync();after.play().catch(()=>{});});before.addEventListener('pause',()=>after.pause());
 before.addEventListener('seeking',sync);before.addEventListener('ratechange',()=>{after.playbackRate=before.playbackRate;});
 before.addEventListener('timeupdate',()=>{if(Math.abs(after.currentTime-before.currentTime)>.2)sync();});
}
function taskHistoryHTML(){return card('任务队列与历史','layers',`<p class="section-description">任务与参数会保存在本机。暂停或重启后，从已完成的视频和制作阶段继续；未完成的视频会重做。上传与登录任务需重新核对。</p><div id="task-history">${taskRows()}</div>`);}
function taskRows(){
 if(!state.jobs.length)return '<p class="blank-inline">暂无任务。开始制作后可在这里暂停、恢复或重试。</p>';
 return state.jobs.slice().reverse().map(j=>{
  const active=['running','pausing','queued'].includes(j.status),resume=j.resumable&&['paused','interrupted','failed','cancelled'].includes(j.status);
  const seconds=(j.runSeconds||0)+(j.status==='running'&&j.runStarted?Date.now()/1000-j.runStarted:0);
  return `<article class="task-row" data-task-id="${j.id}"><div class="task-row-top"><strong>${esc(j.project||j.ids.map(id=>state.projects.find(p=>p.id===id)?.name||'已移除素材').join('、')||'账号操作')}</strong><span class="tag ${j.status==='completed'?'green':j.status==='failed'?'red':'gray'}">${statusLabels[j.status]||j.status}</span></div><div class="task-row-info">${jobLabels[j.kind]||j.kind} · ${j.ids.length} 部剧集 · ${j.checkpointCount||0} 个检查点${seconds?` · 已运行 ${Math.floor(seconds)} 秒`:''} · ${esc(j.id)}</div>${typeof monitorBar==='function'?monitorBar(j.status==='completed'?{percent:100}:j.telemetry?.current,j):''}<p>${esc(j.error||j.stage)}</p><div class="task-row-actions">${productionContinuationButton(j)}${active&&j.resumable&&j.status!=='pausing'?`<button class="button small" data-action="control-job" data-id="${j.id}" data-control="pause">暂停</button>`:''}${resume?`<button class="button small primary" data-action="control-job" data-id="${j.id}" data-control="resume">${j.status==='failed'?'重试未完成部分':'从检查点继续'}</button>`:''}${active?`<button class="button small" data-action="control-job" data-id="${j.id}" data-control="cancel">${j.status==='queued'?'取消排队':'停止'}</button>`:''}</div>${taskAPIDetails(j)}</article>`;
 }).join('');
}
function mountWorkflow(){if(current==='subtitle')mountSubtitleStudio();}
function updateWorkflowUI(){
 if(current==='subtitle'){updatePreviewResult();updateStudioProxy();updateFullSubtitleResult();}
 if(current==='logs'&&$('#task-history'))$('#task-history').innerHTML=taskRows();
 if(current==='preprocess'&&$('#production-config-plan')){const html=productionPlanItemsHTML();if($('#production-config-plan').innerHTML!==html)$('#production-config-plan').innerHTML=html;}
 if(current==='preprocess'&&$('#production-run-summary'))$('#production-run-summary').textContent='本次将执行：'+pipelineActivitySteps().map(s=>s[0]).join(' → ');
 if(current==='preprocess'&&$('#production-handoff')){const html=productionHandoffHTML();if($('#production-handoff').innerHTML!==html)$('#production-handoff').innerHTML=html;}
}
async function workflowAction(action,button){
 if(action==='subtitle-full'){
  const p=activeProject(),v=studioVideo();if(!p||!v)throw Error('请先导入并选择源视频');
  const paths=button.dataset.scope==='current'?[v.path]:p.videos.map(item=>item.path);
  const error=$('#subtitle-full-error');if(error)error.hidden=true;
  button.disabled=true;
  try{await saving;await saveConfig();await saveRegions();const result=await api('jobs',{kind:'subtitle',ids:[p.id],sourceVideoPaths:{[p.id]:paths}});await refresh();updateFullSubtitleResult();toast(`整片去字幕已加入队列：${paths.length} 集，自动连续处理至片尾`);}
  catch(e){if(error){error.innerHTML=`${esc(e.message)}<p>核对下方字幕方式、引擎和保存位置后重试。</p>`;error.hidden=false;error.focus();}throw e;}
  finally{if(button.isConnected)button.disabled=false;}
  return true;
 }
 if(action==='production-view'){if(typeof monitorId!=='undefined')monitorId=button.dataset.id;location.hash='progress';return true;}
 if(action==='continue-production'){
  const parent=state.jobs.find(j=>j.id===button.dataset.id);if(!parent)throw Error('请刷新任务列表');
  button.disabled=true;
  try{await saving;await saveConfig();const result=await api('jobs',{kind:'pipeline',ids:parent.ids,continueFromJob:parent.id});await refresh();if(typeof monitorId!=='undefined')monitorId=result.id;location.hash='progress';toast(result.reused?'已打开这次接续任务':'后续制作已加入队列，保留已完成分集');}
  finally{if(button.isConnected)button.disabled=false;}
  return true;
 }
 if(action==='studio-proxy'){await prepareStudioProxy();return true;}
 if(action==='studio-play'){const v=$('#subtitle-source');if(v.paused)await v.play();else v.pause();return true;}
 if(action==='studio-step'){const v=$('#subtitle-source');v.pause();v.currentTime=Math.max(0,Math.min(v.duration-.01,v.currentTime+Number(button.dataset.offset)));return true;}
 if(action==='region-select'){regionIndex=Number(button.dataset.index);drawRegions();return true;}
 if(action==='region-add'){
  if(regions().length>=8)throw Error('最多8个选区');studioDraft.push({x:.1,y:.75,w:.8,h:.1});regionIndex=studioDraft.length-1;await saveRegions();return true;
 }
 if(action==='region-remove'){if(regions().length<=1)return true;studioDraft.splice(regionIndex,1);regionIndex=Math.min(regionIndex,studioDraft.length-1);await saveRegions();return true;}
 if(action==='subtitle-preview'){
  const v=$('#subtitle-source');if(!v)throw Error('请先导入源视频');v.pause();await saving;await saveConfig();await saveRegions();
  await api('jobs',{kind:'preview',ids:[activeProject().id],videoIndex:studioIndex,start:Math.min(v.currentTime,Math.max(0,v.duration-.25)),seconds:Number(button.dataset.seconds)});
  await refresh();updatePreviewResult(true);toast('试处理已加入队列');return true;
 }
 if(action==='control-job'){
  await api('jobs/control',{id:button.dataset.id,action:button.dataset.control});await refresh();updateWorkflowUI();toast(button.dataset.control==='resume'?'已加入恢复队列':'任务状态已更新');return true;
 }
 if(action==='pause-job'){
  const job=busy();if(job)await api('jobs/control',{id:job.id,action:'pause'});await refresh();toast('正在暂停，已完成检查点会保留');return true;
 }
 if(action==='play-output'){
  $('#output-video').src=media(button.dataset.path);$('#output-dialog').showModal();return true;
 }
 if(action==='close-output'){$('#output-video').pause();$('#output-dialog').close();return true;}
 return false;
}
document.addEventListener('change',e=>{if(e.target.id==='studio-video'){studioIndex=Number(e.target.value);renderPage();}});
document.addEventListener('close',e=>{if(e.target.id==='output-dialog')$('#output-video').pause();},true);
