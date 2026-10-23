'use strict';
pages.splice(0,0,['sources','红果采集','link','素材导入']);
const sourceStatuses={queued:'排队中',running:'采集中',awaiting_confirmation:'等待继续',completed:'已完成',failed:'失败',cancelled:'已停止',interrupted:'已中断',limited:'访问暂停'};
let sourceNativeQuery='',sourceNativeCategory='',sourceNativeStatus={};
let sourceStarting=false,sourceReadSequence=0,sourceReadController=null,sourceReadStatus='';
let sourceText='guoapp://hongguo/catalog?page=1',sourceData=null,sourceCatalog=null,sourceDirectory='',sourceBusy=false,sourceError='',sourceTasks=[],sourceFilter='',sourcePolling=false,sourceAccess={},sourceTab='episodes',sourceRange=1,sourceFocused=1,sourceSelected=[],sourceOrder='chosen',sourceConcurrency=5,sourceAdaptive=true,sourceSegmented=false,sourceQuality=0,sourceExpression='',sourceNotice='',sourceStateFilter='all',sourceLocalSignature='';
const sourceNumbers=()=>sourceData?.episodes||[];
const sourceRootKey=value=>String(value||'').replaceAll('/','\\').replace(/\\+$/,'').toLowerCase();
function sourceProject(){if(!sourceData)return null;const root=sourceRootKey(sourceDirectory);if(!root)return null;return state.projects.find(p=>{const m=p.sourceMetadata;if(!['hongguo_web','guoapp_hongguo'].includes(m?.platform)||m.platform!==sourceData.platform||m.seriesId!==sourceData.seriesId)return false;const stored=m.importRoot||p.source.replaceAll('/','\\').split('\\').slice(0,-2).join('\\');return sourceRootKey(stored)===root;})||null;}
function sourceLocals(){const p=sourceProject();return new Map((p?.videos||[]).map(v=>[v.sourceEpisode||p.sourceMetadata.downloadRecords?.find(r=>v.name===r.filename)?.episode||0,v]).filter(([n])=>n>0));}
function sourceEpisodeState(n){if(sourceLocals().has(n))return 'downloaded';if(sourceTasks.some(t=>t.url===sourceData?.url&&sourceRootKey(t.directory)===sourceRootKey(sourceDirectory)&&['queued','running','awaiting_confirmation','limited'].includes(t.status)&&t.items?.some(i=>i.number===n&&['pending','running'].includes(i.status))))return 'queued';if(sourceData?.lockedEpisodes?.includes(n)||sourceTasks.some(t=>t.url===sourceData?.url&&t.items?.some(i=>i.number===n&&i.errorCode==='source_locked')))return 'locked';return sourceNumbers().some(e=>e.number===n)?'candidate':'unknown';}
const sourceStateName=n=>({downloaded:'已入库',candidate:'来源入口',unknown:'未提供入口',locked:'已锁定',queued:'采集中'})[sourceEpisodeState(n)];
function sourceFilteredRows(){
 const query=sourceFilter.trim().toLocaleLowerCase();
 return (sourceCatalog?.entries||[]).filter(r=>String(r.title).toLocaleLowerCase().includes(query)||(r.tags||[]).some(t=>String(t).toLocaleLowerCase().includes(query)));
}
function sourceFilterCount(rows){return sourceFilter.trim()?`${rows.length} / ${sourceCatalog?.entries.length||0} 部`:`${sourceCatalog?.entries.length||0} 部`;}
function sourceCoverURL(d){return d.coverUrl?'/api/source/cover?id='+encodeURIComponent(d.seriesId)+'&platform='+encodeURIComponent(d.platform||'hongguo_web'):'';}
function sourceListHTML(rows){
 if(!rows.length)return `<p class="queue-empty">${!sourceCatalog?'点击“浏览列表”，或粘贴一部剧的详情链接。':sourceFilter.trim()?'没有匹配的剧集，请换个剧名或题材。':'当前列表暂无剧集。'}</p>`;
 return rows.map(d=>`<button class="drama-row ${d.seriesId===sourceData?.seriesId?'active':''}" data-source="detail" data-url="${esc(d.url)}"><span class="drama-poster">${icon('film')}${d.coverUrl?`<img src="${esc(sourceCoverURL(d))}" loading="lazy" decoding="async" alt="" width="38" height="53">`:''}</span><span><strong>${esc(d.title)}</strong><small>${d.totalEpisodes?'全'+d.totalEpisodes+'集':'集数未提供'} · ${esc((d.tags||[]).slice(0,2).join('/'))}</small></span></button>`).join('');
}
function sourceUpdateFilter(){
 const rows=sourceFilteredRows(),list=$('#source-drama-list'),count=$('#source-filter-count');
 // Keep the native search input alive: replacing it resets the caret and IME.
 if(list){list.innerHTML=sourceListHTML(rows);list.scrollTop=0;}
 if(count)count.textContent=sourceFilterCount(rows);
}
function sourceSidebar(){const rows=sourceFilteredRows();return `<aside class="drama-panel"><div class="panel-heading"><h2>剧集列表</h2><span class="subtle" id="source-filter-count" role="status" aria-live="polite" aria-atomic="true">${sourceFilterCount(rows)}</span></div><label class="search">${icon('scan')}<input id="source-filter" type="search" placeholder="搜索当前页剧名或题材" aria-label="搜索当前页剧名或题材" aria-controls="source-drama-list" value="${esc(sourceFilter)}"></label><div class="catalog-source"><span class="source-dot"></span>${sourceCatalog?.platform==='guoapp_hongguo'?'红果原生目录':'红果网站公开列表'}</div><div class="drama-list" id="source-drama-list">${sourceListHTML(rows)}</div>${sourceCatalog?`<div class="list-foot"><button class="text-button" data-source="previous" ${Number(new URL(sourceCatalog.url).searchParams.get('page')||1)<=1?'disabled':''}>上一页</button><span>${new URL(sourceCatalog.url).searchParams.get('page')||1} / ${sourceCatalog.lastPage}</span><button class="text-button" data-source="next" ${Number(new URL(sourceCatalog.url).searchParams.get('page')||1)>=sourceCatalog.lastPage?'disabled':''}>下一页</button></div>`:''}</aside>`;}
function sourceHeader(){const d=sourceData;return `<section class="drama-header"><div class="hero-poster">${icon('film')}${d.coverUrl?`<img src="${esc(sourceCoverURL(d))}" decoding="async" alt="原始封面">`:''}</div><div class="hero-content"><div class="source-platform"><span>红果</span>剧集ID ${esc(d.seriesId)}</div><h1>${esc(d.title)}</h1><div class="hero-tags">${d.tags.map(t=>`<span>${esc(t)}</span>`).join('')}</div><p class="hero-brief">${esc(d.intro||'简介未提供')}</p></div></section>`;}
function sourceFacts(){return `<div class="drama-facts">${[['平台总集数',sourceData.totalEpisodes??'—','集'],[sourceData.platform==='guoapp_hongguo'?'原生分集入口':'网页播放入口',sourceNumbers().length,'个'],['已下载入库',sourceLocals().size,'集'],['本地可剪辑',sourceLocals().size,'集']].map(([l,n,u],i)=>`<div class="fact"><small>${l}</small><strong class="${i>1?'good':''}">${n}<em>${u}</em></strong></div>`).join('')}</div>`;}
function sourceEpisodePanel(){const total=sourceData.totalEpisodes||Math.max(1,...sourceNumbers().map(e=>e.number));const ranges=[];for(let n=1;n<=total;n+=50)ranges.push(n);const numbers=[];for(let n=sourceRange;n<=Math.min(total,sourceRange+49);n++)if(sourceStateFilter==='all'||sourceEpisodeState(n)===sourceStateFilter)numbers.push(n);const v=sourceLocals().get(sourceFocused);return sourceFacts()+`<div class="episode-tools"><div class="ranges" role="group" aria-label="集数范围">${ranges.map(n=>`<button class="${sourceRange===n?'active':''}" data-source="range" data-number="${n}">${n}–${Math.min(total,n+49)}</button>`).join('')}</div><select id="source-state-filter" aria-label="集数状态筛选">${[['all','全部状态'],['candidate','来源入口'],['downloaded','已入库'],['queued','采集中'],['unknown','未提供入口'],['locked','已锁定']].map(([k,n])=>`<option value="${k}" ${k===sourceStateFilter?'selected':''}>${n}</option>`).join('')}</select></div><div class="free-select"><label for="source-expression">自由选集</label><div><input id="source-expression" value="${esc(sourceExpression)}" placeholder="例如：1,3,8,12-15"><button class="button small" data-source="expression">应用集号</button></div><p>支持不连续集号与范围。只处理页面实际提供的入口，下载时逐集验证。</p></div>${sourceNotice?`<p class="source-selection-notice" role="status">${esc(sourceNotice)}</p>`:''}<div class="episode-toolbar"><label><input id="source-select-page" type="checkbox">选择本页来源入口</label><button class="text-button" data-source="select-local">选择已下载集</button><button class="text-button" data-source="clear">清空</button><span class="subtle">支持跨页选择</span></div><div class="episode-grid">${numbers.map(n=>`<button class="episode ${sourceEpisodeState(n)} ${sourceSelected.includes(n)?'selected':''} ${sourceFocused===n?'focused':''}" data-source="episode" data-number="${n}" aria-pressed="${sourceSelected.includes(n)}" aria-label="第${n}集，${sourceStateName(n)}"><span>${String(n).padStart(2,'0')}</span><small>${sourceStateName(n)}</small></button>`).join('')}</div><div class="episode-legend"><span><i class="legend-box done"></i>已入库</span><span><i class="legend-box chosen"></i>已选择</span><span><i class="legend-box"></i>来源入口</span><span><i class="legend-box unknown"></i>暂无入口</span><span>已锁定：需在来源平台核对访问权限</span></div><div class="episode-inspector"><div class="inspector-icon">${icon(v?'play':'film')}</div><div><strong>第${String(sourceFocused).padStart(3,'0')}集</strong><p>${v?duration(v.duration)+' · '+v.width+'×'+v.height+' · '+(v.audio?'有音轨':'无音轨')+' · '+size(v.bytes):sourceEpisodeState(sourceFocused)==='candidate'?'来源提供此集入口；下载时验证视频和真实集号':'当前没有可用于下载的公开入口或已有任务'}</p></div>${v?`<button class="button small" data-source="preview" data-number="${sourceFocused}">${icon('play')}本地预览</button>`:''}</div><p class="local-note">总集数不代表可下载集数。已入库的完整视频可先制作；只处理当前来源返回并校验的分集。</p>`;}
function sourceLocalPanel(){return sourceFacts()+`<p class="local-note">校验成功的视频才进入素材库。勾选后可仅处理这些集数，后续补集不会改变本次制作范围。</p><div class="table-scroll"><table class="local-table"><thead><tr><th>选择</th><th>集数</th><th>时长</th><th>分辨率</th><th>音轨</th><th>操作</th></tr></thead><tbody>${[...sourceLocals()].sort((a,b)=>a[0]-b[0]).map(([n,v])=>`<tr><td><input type="checkbox" data-source-local="${n}" ${sourceSelected.includes(n)?'checked':''} aria-label="选择第${n}集"></td><td>第${String(n).padStart(3,'0')}集</td><td>${duration(v.duration)}</td><td>${v.width}×${v.height}</td><td>${v.audio?'有':'无'}</td><td><button class="text-button" data-source="preview" data-number="${n}">预览</button></td></tr>`).join('')||'<tr><td colspan="6" class="empty-main">还没有已入库视频。选择来源入口并下载后显示在这里。</td></tr>'}</tbody></table></div>`;}
function sourceMetadataPanel(){const d=sourceData;return `<div class="metadata"><dl>${[['平台',d.platform==='guoapp_hongguo'?'红果原生来源':'红果网站'],['原始剧名',d.title],['剧集ID',d.seriesId],['标签',d.tags.join('、')],['热度',d.heat?.display||'未提供'],['评分',d.rating||'未提供'],['播放量','未提供'],['整剧发布时间','未提供'],['获取时间',new Date(d.fetchedAt*1000).toLocaleString('zh-CN')]].map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl><h3>原始简介</h3><p>${esc(d.intro||'未提供')}</p></div>`;}
function sourceOrdered(){return sourceOrder==='number'?sourceSelected.slice().sort((a,b)=>a-b):sourceSelected.slice();}
// Resolve the whole source list, independently of the visible range and filters.
function sourceDownloadConcurrency(){return sourceData?.platform==='hongguo_web'?Math.min(2,sourceConcurrency):sourceConcurrency;}
function sourcePendingNumbers(){
 const locals=sourceLocals(),queued=new Set(),locked=new Set(sourceData?.lockedEpisodes||[]);
 for(const task of sourceTasks){
  if(task.url!==sourceData?.url)continue;
  for(const item of task.items||[]){
   if(item.errorCode==='source_locked')locked.add(item.number);
   if(sourceRootKey(task.directory)===sourceRootKey(sourceDirectory)&&['queued','running','awaiting_confirmation','limited'].includes(task.status)&&['pending','running'].includes(item.status))queued.add(item.number);
  }
 }
 return [...new Set(sourceNumbers().map(e=>e.number))].filter(n=>Number.isInteger(n)&&n>0&&!locals.has(n)&&!queued.has(n)&&!locked.has(n)).sort((a,b)=>a-b);
}
function sourceSelectionBar(){
 const ordered=sourceOrdered(),locals=ordered.filter(n=>sourceLocals().has(n)),pending=ordered.filter(n=>sourceEpisodeState(n)==='candidate'),whole=sourcePendingNumbers(),busy=sourceBusy||sourceStarting;
 return `<div class="selection-top"><label class="source-directory-field" for="source-directory">${icon('folder')}<input id="source-directory" placeholder="选择素材保存根目录" value="${esc(sourceDirectory)}" ${sourceStarting?'disabled':''}></label><button class="text-button" data-source="browse" ${sourceStarting?'disabled':''}>选择目录</button><button class="text-button" data-source="save" ${busy?'disabled':''}>保存资料</button></div><div class="selected-order"><span>处理顺序</span><select id="source-order"><option value="chosen" ${sourceOrder==='chosen'?'selected':''}>按勾选顺序</option><option value="number" ${sourceOrder==='number'?'selected':''}>按集数排序</option></select><strong id="source-sequence">${ordered.map(n=>String(n).padStart(2,'0')).join(' → ')||'尚未选择集数'}</strong></div><div class="selection-actions"><span class="selection-summary">已选<strong>${sourceSelected.length}</strong>集${locals.length?'，'+locals.length+'集已在本地':''}</span><button class="button" data-source="produce" ${!locals.length||busy?'disabled':''}>${icon('sliders')}使用已选${locals.length||''}集制作</button><button class="button" data-source="download" ${!pending.length||busy?'disabled':''}>${icon('download')}下载所选集${pending.length?'（'+pending.length+'）':''}</button><button class="button primary" data-source="download-all" aria-describedby="source-whole-hint" ${!whole.length||busy?'disabled':''}>${icon('download')}${sourceStarting?'正在加入下载…':'下载全集（'+whole.length+'）'}</button></div><p id="source-whole-hint" class="source-whole-hint">全集下载：全剧 ${sourceData.totalEpisodes??sourceNumbers().length} 集，本次可加入 ${whole.length} 集。跨所有分集页按集号连续处理，已入库或队列中的集数自动跳过；已锁定、暂无入口的集数需另行核对。</p>`;
}
async function sourceStartImport(action){
 if(sourceBusy||sourceStarting)return;
 if(!sourceData)throw Error('请先读取剧集链接');
 if(!sourceDirectory)throw Error('请选择保存目录');
 const all=action==='download-all',video=action!=='save',numbers=all?sourcePendingNumbers():sourceOrdered().filter(n=>sourceEpisodeState(n)==='candidate');
 if(video&&!numbers.length)throw Error(all?'没有待加入的分集，请核对已入库素材和下载队列':'请选择尚未下载的来源入口');
 const request={url:sourceData.url,directory:sourceDirectory,video,episodes:numbers,downloadConcurrency:sourceDownloadConcurrency(),adaptiveDownloads:sourceAdaptive,segmentedDownload:sourceData.platform==='guoapp_hongguo'&&sourceSegmented,downloadQuality:sourceData.platform==='guoapp_hongguo'?sourceQuality:0,order:all?'number':sourceOrder};
 sourceStarting=true;sourceRenderMain();
 try{
  await updateConfig({sourceImportRoot:request.directory});
  const task=await api('source/start',request);
  if(task?.id)sourceTasks=[...sourceTasks.filter(t=>t.id!==task.id),task];
  if(all){sourceNotice=`全集下载已加入队列：${numbers.length} 集，按集号连续处理，可在右侧查看进度或停止。`;}
  await sourcePoll();
  toast(all?'已加入全集下载，共 '+numbers.length+' 集':'已加入真实采集队列');
 }finally{sourceStarting=false;if(current==='sources'){sourceRenderMain();renderActivity();}}
}

function sourceMain(){if(!sourceData)return '<div class="source-intro-empty">'+icon('link')+'<h1>选择一部剧，开始整理素材</h1><p>浏览原生剧库、搜索剧名，或粘贴红果官方分享链接。<br>读取后可直接下载全集，也可指定集数下载。</p></div>';return sourceHeader()+`<div class="tabs" role="tablist" aria-label="剧集工作区">${[['episodes','选集下载'],['local','已下载素材'],['metadata','原始资料']].map(([k,n])=>`<button role="tab" data-source="tab" data-tab="${k}" aria-selected="${sourceTab===k}">${n}${k==='local'?` <span>${sourceLocals().size}</span>`:''}</button>`).join('')}</div><section id="source-tab-content" role="tabpanel">${sourceTab==='episodes'?sourceEpisodePanel():sourceTab==='local'?sourceLocalPanel():sourceMetadataPanel()}</section><div class="selection-bar">${sourceSelectionBar()}</div>`;}
function sourceRenderMain(){const panel=$('#source-tab-content'),scroll=panel?.scrollTop||0;const el=$('#source-editor');if(!el)return;const focused=document.activeElement?.id,pos=document.activeElement?.selectionStart;el.innerHTML=sourceMain();if($('#source-tab-content'))$('#source-tab-content').scrollTop=scroll;if(focused&&$('#'+focused)){const input=$('#'+focused);input.focus({preventScroll:true});if(typeof pos==='number'&&input.setSelectionRange)try{input.setSelectionRange(pos,pos);}catch{}}}
function sourceRefreshDirectory(){if(!sourceData)return;sourceSelected=[];sourceNotice='';const replacePart=(selector,html)=>{const old=$(selector);if(!old)return;const box=document.createElement('div');box.innerHTML=html;const next=box.querySelector(selector);if(next)old.replaceWith(next);};if(sourceTab==='local')$('#source-tab-content').innerHTML=sourceLocalPanel();else if(sourceTab==='episodes'){replacePart('.drama-facts',sourceFacts());replacePart('.episode-grid',sourceEpisodePanel());replacePart('.episode-inspector',sourceEpisodePanel());}replacePart('.selection-actions',sourceSelectionBar());replacePart('#source-whole-hint',sourceSelectionBar());const sequence=$('#source-sequence');if(sequence)sequence.textContent='尚未选择集数';renderActivity();}
function sourceTaskCounts(t){const items=t.items||[];return [['completed','下载入库'],['skipped','复用入库'],['pending','待处理'],['running','处理中'],['failed','失败待恢复']].map(([k,label])=>{const n=items.filter(i=>i.status===k).length;return n?label+' '+n:'';}).filter(Boolean).join(' / ');}
function sourceItemProgress(t){const active=(t.items||[]).filter(i=>i.status==='running'),failed=(t.items||[]).filter(i=>i.status==='failed');return `<div class="source-transfer-list">${active.map(i=>`<div class="source-transfer" data-source-episode="${i.number}"><strong>第${i.number}集</strong><span>${esc(i.stage||'处理中')}</span>${i.totalBytes?`<progress aria-label="第${i.number}集下载进度" max="100" value="${Math.min(99.9,(i.bytes||0)/i.totalBytes*100)}"></progress>`:''}<small>${size(i.bytes||0)}${i.totalBytes?' / '+size(i.totalBytes):''}${i.bytesPerSecond?' · '+size(i.bytesPerSecond)+'/秒':''}${i.etaSeconds!=null?' · 约剩余'+duration(i.etaSeconds):''}</small></div>`).join('')}${failed.length?`<details class="source-missing-list" ${['failed','completed'].includes(t.status)?'open':''}><summary>未完成 ${failed.length} 集：${failed.map(i=>i.number).join('、')}</summary>${failed.map(i=>`<p><strong>第${i.number}集</strong> · ${esc(i.error||'本集未完成')}</p>`).join('')}</details>`:''}</div>`;}
function sourceDownloadOptions(){const native=sourceData?.platform!=='hongguo_web';return `<div class="source-download-options"><strong>下载加速与画质</strong><label class="option-check" for="source-adaptive"><input id="source-adaptive" type="checkbox" ${sourceAdaptive?'checked':''}>自动调整并行数量</label><label class="option-check" for="source-segmented"><input id="source-segmented" type="checkbox" ${sourceSegmented?'checked':''} ${native?'':'disabled'}>单集分段加速</label><label for="source-quality">新下载集的目标画质</label><select id="source-quality" ${native?'':'disabled'}>${[[0,'最高可用'],[1080,'1080p'],[720,'720p']].map(([value,label])=>`<option value="${value}" ${sourceQuality===value?'selected':''}>${label}</option>`).join('')}</select><p class="field-hint">设置用于新任务。自动并行不超过上方数量；原生媒体传输最多6个连接。支持分段的较大MP4使用2段，其余使用单连接。画质以来源实际提供为准，已保存文件保留。</p></div>`;}
function sourcePhaseSummary(t){if(!t.phaseSeconds)return '';const phases=[['lookup','取地址'],['download','下载'],['materialize','转存'],['verify','校验'],['import','入库']];return `<div class="source-pipeline-status">传输并行 ${t.downloadConcurrencyActual||t.downloadConcurrency||1} / ${t.downloadConcurrency||1} · 后台处理 ${t.processingJobs||0}${t.downloadQuality?' · 目标'+t.downloadQuality+'p':''}</div><details class="source-phase-details" id="source-phases-${esc(t.id)}"><summary>查看耗时明细</summary><dl>${phases.map(([key,label])=>`<dt>${label}</dt><dd>${Number(t.phaseSeconds[key]||0).toFixed(1)} 秒</dd>`).join('')}</dl><p>各集累计时间，含并行处理；任务总耗时以实际运行时间为准。</p>${t.concurrencyChanges?.length?`<p>${esc(t.concurrencyChanges.at(-1).reason)}：${t.concurrencyChanges.at(-1).from} → ${t.concurrencyChanges.at(-1).to} 集</p>`:''}</details>`;}
function sourceQueueHtml(){return `<div id="source-live-queue"><div class="queue-panel"><div class="panel-heading"><h2>采集队列</h2><span class="status-pill">${sourceAccess.paused?'访问暂停':sourceTasks.some(t=>t.status==='running')?'处理中':'待机'}</span></div><p class="queue-explain">按所选顺序自动连续下载全部已选集，无需逐集确认。</p><div class="queue-settings"><label for="source-concurrency">同时下载</label><select id="source-concurrency">${(sourceData?.platform==='hongguo_web'?[1,2]:[1,2,3,5]).map(n=>`<option value="${n}" ${sourceDownloadConcurrency()===n?'selected':''}>${n}集 · ${n===1?'单路':'并行'}</option>`).join('')}</select><p class="field-hint">原生来源最多5集并行，下载器与队列同步设置。文件按集号归档，来源限制仍会暂停任务。</p></div>${sourceDownloadOptions()}${sourceAccess.paused?`<div class="source-access-notice" role="alert"><strong>来源访问暂停</strong><p>${esc(sourceAccess.message)}${sourceAccess.retryAt?'，最早可继续时间：'+new Date(sourceAccess.retryAt*1000).toLocaleString('zh-CN'):''}</p><button class="button small" data-source="access-resume" ${sourceAccess.retryAt>Date.now()/1000?'disabled':''}>核对后继续</button></div>`:''}<div class="source-live-tasks">${sourceTasks.slice().reverse().map(t=>`<article class="queue-item" data-source-task="${esc(t.id)}"><div class="source-task-heading"><strong>${esc(t.title||'红果资料采集')}</strong><span>${sourceStatuses[t.status]||t.status}</span></div><p role="status">${esc(t.stage)}</p>${t.episodes?.length?`<p>已处理 ${t.done||0} / ${t.episodes.length} 集 · ${sourceTaskCounts(t)} · 顺序 ${t.episodes.join('、')}</p>`:''}${t.status==='running'&&t.bytes?`<div class="source-file-progress">${t.totalBytes?`<progress aria-label="当前传输总进度" max="100" value="${Math.min(99.9,t.bytes/t.totalBytes*100)}"></progress>`:''}<span>${size(t.bytes)}${t.totalBytes?' / '+size(t.totalBytes):' · 总大小未知'}${t.bytesPerSecond?' · '+size(t.bytesPerSecond)+'/秒':''}${t.etaSeconds!=null?' · 当前文件约剩余'+duration(t.etaSeconds):''}</span></div>`:''}${sourceItemProgress(t)}${sourcePhaseSummary(t)}${t.items?.filter(i=>i.status==='pending').length&&['queued','awaiting_confirmation','interrupted'].includes(t.status)?`<div class="source-queue-pending">${t.items.filter(i=>i.status==='pending').map((i,index,all)=>`<div><span>第${i.number}集</span><button class="text-button" data-source="move" data-id="${t.id}" data-number="${i.number}" data-offset="-1" ${index===0?'disabled':''}>上移</button><button class="text-button" data-source="move" data-id="${t.id}" data-number="${i.number}" data-offset="1" ${index===all.length-1?'disabled':''}>下移</button></div>`).join('')}</div>`:''}${t.warnings?.length?`<p class="source-warning">${esc(t.warnings.join('；'))}</p>`:''}<div class="source-task-buttons"><a class="text-button" href="/api/source/report?id=${t.id}" download="采集诊断.json">导出采集诊断</a>${['queued','running','awaiting_confirmation','limited','interrupted'].includes(t.status)?`<button class="text-button" data-source="stop" data-id="${t.id}">停止</button>`:''}${['awaiting_confirmation','limited','interrupted','failed','cancelled'].includes(t.status)?`<button class="text-button" data-source="resume" data-id="${t.id}">继续剩余集</button>`:''}${t.savedDirectory?`<button class="text-button" data-source="open" data-id="${t.id}">打开目录</button>`:''}${t.projectId?`<button class="text-button" data-source="project" data-id="${t.projectId}">素材库</button>`:''}</div></article>`).join('')||`<div class="queue-empty">${icon('log')}还没有采集任务。<br>选择一部剧，再选择要下载的集数。</div>`}</div><div class="queue-policy">${icon('shield')}<div><strong>访问受限时暂停</strong><p>仅在来源要求等待或手动停止时暂停，已下载的完整文件会保留。</p></div></div><div class="archive-summary"><strong>一部剧，一个素材项目</strong><p>补集归入同一目录，已校验的文件默认跳过。</p></div></div></div>`;}
function sourcesPage(){sourceDirectory=sourceDirectory||state.config.sourceImportRoot||'';return `<div id="source-workbench">${sourceNativeToolbar()}<div class="source-link-toolbar"><label for="source-text">红果链接</label><input id="source-text" value="${esc(sourceText)}" placeholder="粘贴红果官方分享链接，也支持原生剧集和网站链接"><button class="button small primary" data-source="resolve" ${sourceBusy?'disabled':''}>${sourceBusy?'读取中…':'读取链接'}</button><button class="button small" data-source="catalog" ${sourceBusy?'disabled':''}>浏览列表</button><button class="text-button" data-source="refresh" ${sourceBusy||sourceStarting?'disabled':''}>刷新</button></div><p id="source-read-status" class="source-read-status" role="status" aria-live="polite" ${sourceReadStatus?'':'hidden'}>${esc(sourceReadStatus)}</p><p id="source-read-error" class="source-read-error" role="alert" ${sourceError?'':'hidden'}>${esc(sourceError)}</p><div class="source-workspace-grid">${sourceSidebar()}<div class="editor" id="source-editor">${sourceMain()}</div></div></div>`;}
const sourceBaseRender=renderPage;renderPage=function(){document.body.classList.toggle('source-page',current==='sources');if(current!=='sources')return sourceBaseRender();$('#content').innerHTML=sourcesPage();$('#breadcrumb').textContent='红果采集';renderNav();renderTaskbar();renderActivity();sourcePoll();};
const sourceBaseTaskbar=renderTaskbar;renderTaskbar=function(){sourceBaseTaskbar();if(current==='sources')$('#task-title').textContent='链接导入';};
function sourceQueueKey(node){
 if(node.nodeType!==Node.ELEMENT_NODE)return '';
 if(node.id)return 'id:'+node.id;
 if(node.dataset.sourceTask)return 'task:'+node.dataset.sourceTask;
 if(node.dataset.sourceEpisode)return 'episode:'+node.dataset.sourceEpisode;
 if(node.dataset.source)return ['action',node.dataset.source,node.dataset.id||'',node.dataset.number||'',node.dataset.offset||''].join(':');
 return '';
}
function sourcePatchQueueNode(current,next){
 if(current.nodeType!==next.nodeType||current.nodeName!==next.nodeName){current.replaceWith(next);return;}
 if(current.nodeType===Node.TEXT_NODE){if(current.data!==next.data)current.data=next.data;return;}
 if(current.nodeType!==Node.ELEMENT_NODE)return;
 const keepOpen=current.tagName==='DETAILS',nextValue=current.tagName==='SELECT'?next.value:null;
 for(const attr of [...current.attributes])if(!(keepOpen&&attr.name==='open')&&!next.hasAttribute(attr.name))current.removeAttribute(attr.name);
 for(const attr of [...next.attributes])if(!(keepOpen&&attr.name==='open')&&current.getAttribute(attr.name)!==attr.value)current.setAttribute(attr.name,attr.value);
 const keyed=new Map([...current.childNodes].map(node=>[sourceQueueKey(node),node]).filter(([key])=>key));
 let cursor=current.firstChild;
 for(const wanted of [...next.childNodes]){
  const key=sourceQueueKey(wanted);
  let match=key?keyed.get(key):cursor&&!sourceQueueKey(cursor)&&cursor.nodeType===wanted.nodeType&&cursor.nodeName===wanted.nodeName?cursor:null;
  if(match){
   if(match!==cursor)current.insertBefore(match,cursor);
   sourcePatchQueueNode(match,wanted);cursor=match.nextSibling;
  }else{current.insertBefore(wanted,cursor);}
 }
 while(cursor){const stale=cursor;cursor=cursor.nextSibling;stale.remove();}
 if(current.tagName==='SELECT'&&current!==document.activeElement&&current.value!==nextValue)current.value=nextValue;
}
function sourceRenderQueue(){
 const host=$('#activity-content');if(!host)return;
 const panel=host.closest('.activity'),top=panel?.scrollTop||0,bounds=panel?.getBoundingClientRect(),focused=document.activeElement;
 const taskArea=host.querySelector('.source-live-tasks');
 const anchor=top>0&&bounds&&taskArea?.getBoundingClientRect().top<=bounds.top?[...host.querySelectorAll('[data-source-task]')].find(node=>{const box=node.getBoundingClientRect();return box.bottom>bounds.top&&box.top<bounds.bottom;}):null;
 const offset=anchor?anchor.getBoundingClientRect().top-bounds.top:0;
 const template=document.createElement('template');template.innerHTML=sourceQueueHtml();
 const next=template.content.firstElementChild,current=host.querySelector('#source-live-queue');
 if(current)sourcePatchQueueNode(current,next);else host.replaceChildren(next);
 if(focused&&host.contains(focused)&&focused.isConnected&&document.activeElement!==focused)focused.focus({preventScroll:true});
 if(panel){
  if(top===0)panel.scrollTop=0;
  else if(anchor?.isConnected)panel.scrollTop+=anchor.getBoundingClientRect().top-panel.getBoundingClientRect().top-offset;
  else panel.scrollTop=top;
 }
}
const sourceBaseActivity=renderActivity;renderActivity=function(){if(current!=='sources')return sourceBaseActivity();sourceRenderQueue();};
function sourceUpdateReadState(){
 if(current!=='sources')return;
 const toolbar=$('.source-native-toolbar'),status=$('#source-read-status'),error=$('#source-read-error');
 toolbar?.setAttribute('aria-busy',String(sourceBusy));
 if(status){status.textContent=sourceReadStatus;status.hidden=!sourceReadStatus;}
 if(error){error.textContent=sourceError;error.hidden=!sourceError;}
 if(sourceBusy)for(const button of document.querySelectorAll('[data-source="download-all"],[data-source="download"],[data-source="produce"]'))button.disabled=true;
 const link=$('#source-text');if(link&&document.activeElement!==link)link.value=sourceText;
 for(const button of document.querySelectorAll('[data-source="resolve"],[data-source="catalog"],[data-source="refresh"],[data-source="native-search"]')){
  button.disabled=sourceStarting;
  if(!button.dataset.idleLabel)button.dataset.idleLabel=button.textContent;
  button.textContent=sourceBusy&&button.dataset.source==='native-search'?'搜索中…':button.dataset.source==='native-search'?(sourceNativeQuery.trim()?'搜索':'浏览原生目录'):button.dataset.idleLabel;
 }
}
function sourceUpdateCatalog(){
 if(current!=='sources')return;
 sourceUpdateFilter();
 const panel=$('#source-workbench .drama-panel'),label=panel?.querySelector('.catalog-source');
 if(label)label.innerHTML='<span class="source-dot"></span>'+(sourceCatalog?.platform==='guoapp_hongguo'?'红果原生目录':'红果网站公开列表');
 if(panel){
  const template=document.createElement('template');template.innerHTML=sourceSidebar();
  const foot=template.content.querySelector('.list-foot'),old=panel.querySelector('.list-foot');
  if(foot){if(old)old.replaceWith(foot);else panel.append(foot);}else old?.remove();
 }
}
async function sourceRead(text,refresh=false){
 if(sourceStarting)return;
 const sequence=++sourceReadSequence;sourceReadController?.abort();
 const controller=new AbortController();sourceReadController=controller;
 sourceText=text;sourceBusy=true;sourceError='';
 sourceReadStatus=(text.includes('novelquickapp.com/')?'正在解析官方分享链接并匹配剧集…':text.includes('/catalog')?'正在读取原生剧库…':'正在读取剧集…')+(sourceCatalog||sourceData?' 当前结果仍可查看。':'');
 const begun=performance.now();let changedDetail=false;sourceUpdateReadState();
 try{
  const data=await api('source/resolve',{text,refresh},{signal:controller.signal});
  if(sequence!==sourceReadSequence)return;
  if(data.shareCatalog){sourceCatalog=data.shareCatalog;sourceUpdateCatalog();}
  if(data.officialShare&&!data.officialShare.matched)sourceError=data.warning||'请核对并选择官方链接对应的剧集。';
  if(data.kind==='catalog'){sourceCatalog=data;sourceUpdateCatalog();}
  else{changedDetail=true;sourceData=data;sourceTab='episodes';sourceRange=1;sourceFocused=1;sourceSelected=[];sourceExpression='';sourceNotice='';
   for(const row of document.querySelectorAll('.drama-row'))row.classList.toggle('active',row.dataset.id===data.seriesId);
  }
  sourceReadStatus=(data.officialShare?.matched?'已通过官方分享链接定位':data.cacheHit?'已载入缓存':'已读取')+' · '+(data.kind==='catalog'?data.entries.length+' 部剧':data.totalEpisodes+' 集')+' · '+((performance.now()-begun)/1000).toFixed(2)+'秒';
 }catch(error){if(sequence===sourceReadSequence&&error.name!=='AbortError'){sourceError=error.message;sourceReadStatus='读取失败，已保留当前结果。';}}
 finally{if(sequence===sourceReadSequence){sourceBusy=false;sourceReadController=null;if(current==='sources'){if(changedDetail)sourceRenderMain();else{const bar=$('#source-editor .selection-bar');if(bar)bar.innerHTML=sourceSelectionBar();}sourceUpdateReadState();renderActivity();}}}
}

async function sourcePoll(){if(sourcePolling)return;sourcePolling=true;try{const r=await api('source/tasks');sourceTasks=r.tasks;sourceAccess=r.access||{};sourceNativeStatus=r.native||{};const finished=JSON.stringify(sourceTasks.map(t=>[t.id,t.done,t.status]));if(sourceLocalSignature!==finished){sourceLocalSignature=finished;await refresh();if(current==='sources')sourceRenderMain();}else if(current==='sources')renderActivity();}catch(e){if(current==='sources'){$('#activity-content').innerHTML='<p class="source-read-error" role="alert">采集状态连接中断，正在重新连接。请勿重复提交下载。</p>';}}finally{sourcePolling=false;}}
setInterval(()=>{if(current==='sources')sourcePoll();},1500);
function sourceToggle(n){sourceFocused=n;const status=sourceEpisodeState(n);if(status==='candidate'||status==='downloaded'){sourceSelected=sourceSelected.includes(n)?sourceSelected.filter(x=>x!==n):[...sourceSelected,n];sourceNotice='';}else sourceNotice=status==='queued'?'这集已有采集任务，请在右侧队列继续。':status==='locked'?`第${n}集已锁定。请在来源平台核对访问权限或使用平台提供的素材导出入口。`:`第${n}集未提供公开播放入口，暂不能加入下载队列。`;sourceRenderMain();}
function sourceApplyExpression(){const total=sourceData.totalEpisodes||10000,result=[];for(const part of sourceExpression.replaceAll('，',',').replaceAll('、',',').split(/[,\s]+/).filter(Boolean)){const m=part.match(/^(\d+)(?:[-–~](\d+))?$/);if(!m)throw Error('集号格式有误，例如 1,3,8,12-15');const a=Number(m[1]),b=Number(m[2]||a);if(a<1||b<a||b>total)throw Error('集数需在1至'+total+'之间');for(let n=a;n<=b;n++)if(!result.includes(n))result.push(n);}if(!result.length)throw Error('请先输入集号');const eligible=result.filter(n=>['candidate','downloaded'].includes(sourceEpisodeState(n))),blocked=result.filter(n=>!eligible.includes(n));sourceSelected=eligible;sourceNotice=blocked.length?'未加入的集数：'+blocked.join('、')+'。这些集数暂无公开入口、已锁定或已有任务。':'';sourceFocused=eligible[0]||1;sourceRange=Math.floor((sourceFocused-1)/50)*50+1;sourceRenderMain();}
async function sourceProduction(){const p=sourceProject(),paths=sourceOrdered().map(n=>sourceLocals().get(n)?.path).filter(Boolean);if(!p||!paths.length)throw Error('请选择已下载入库的集数');let d=$('#source-produce-dialog');if(!d){d=document.createElement('dialog');d.id='source-produce-dialog';document.body.append(d);}d.innerHTML=`<div class="dialog-top"><h2>核对本次选集制作</h2><button class="icon-button" data-source="close-produce" aria-label="关闭">×</button></div><p>${esc(p.name)}</p><p class="field-hint">已选 ${paths.length} 集，按当前顺序制作；后续补集不会加入本任务。</p><div class="field"><label for="source-produce-kind">制作方式</label><select id="source-produce-kind"><option value="pipeline">使用当前配置运行制作流水线</option><option value="transcode">画面处理与分集</option><option value="subtitle">仅去字幕 · 全部所选集</option></select></div><div id="source-preflight" role="status" aria-live="polite">正在核对素材与保存位置…</div><button class="button primary" data-source="confirm-produce" disabled>确认加入制作队列</button>`;d.sourceRequest={projectId:p.id,paths};d.showModal();await sourceRefreshPreflight();}
async function sourceRefreshPreflight(){const d=$('#source-produce-dialog');if(!d?.open)return;const request=d.sourceRequest,seq=(d.checkSeq||0)+1;d.checkSeq=seq;const button=d.querySelector('[data-source="confirm-produce"]');button.disabled=true;try{const r=await api('jobs/preflight',{kind:$('#source-produce-kind').value,ids:[request.projectId],sourceVideoPaths:{[request.projectId]:request.paths}});if(!d.open||d.checkSeq!==seq)return;$('#source-preflight').innerHTML=`<div class="source-preflight-facts"><p><strong>实际输入 ${r.count} 集</strong> · ${esc(r.files.join(' → '))}</p><p>输出：${esc(r.output)}</p><p>画面：${r.width}×${r.height} · ${r.regroup?'重组后分集':'逐集处理'}</p><p>${r.subtitle?'去字幕：'+esc(({vsr:'本地AI引擎',cloud:'云端接口',local:'区域修补'})[r.subtitleMode]||r.subtitleMode)+' · 全部所选集 · '+r.subtitleRegions.length+'个选区':'本任务未开启去字幕'}</p><p>接口：${r.interfaces?.length?r.interfaces.map(esc).join('；'):'当前方式无需AI接口'}</p><p>估算所需 ${size(r.estimatedBytes)} · 可用 ${r.freeBytes===null?'无法读取':size(r.freeBytes)}</p></div>${r.errors.length?`<div role="alert" tabindex="-1" class="source-read-error"><strong>请先处理以下问题</strong><ul>${r.errors.map(e=>`<li>${esc(e)}</li>`).join('')}</ul><p>可返回AI去字幕或预处理页面修改配置后重新核对。</p></div>`:''}<p class="field-hint">${r.warnings.map(esc).join('；')}</p>`;button.disabled=!r.ok;}catch(e){if(d.checkSeq===seq)$('#source-preflight').innerHTML='<p role="alert" class="source-read-error">'+esc(e.message)+'</p>';}}

document.addEventListener('input',e=>{const el=e.target;if(el.id==='source-native-query')sourceNativeQuery=el.value;if(el.id==='source-text')sourceText=el.value;if(el.id==='source-directory')sourceDirectory=el.value;if(el.id==='source-expression')sourceExpression=el.value;if(el.id==='source-filter'){sourceFilter=el.value;if(!e.isComposing)sourceUpdateFilter();}});
document.addEventListener('compositionend',e=>{if(e.target.id==='source-filter'){sourceFilter=e.target.value;sourceUpdateFilter();}});
document.addEventListener('change',e=>{const el=e.target;if(el.id==='source-adaptive')sourceAdaptive=el.checked;if(el.id==='source-segmented')sourceSegmented=el.checked;if(el.id==='source-quality')sourceQuality=Number(el.value);if(el.id==='source-native-category')sourceNativeCategory=el.value;if(el.id==='source-produce-kind')sourceRefreshPreflight();if(el.id==='source-directory')sourceRefreshDirectory();if(el.id==='source-state-filter'){sourceStateFilter=el.value;sourceRenderMain();}if(el.id==='source-order'){sourceOrder=el.value;sourceRenderMain();}if(el.id==='source-concurrency')sourceConcurrency=Number(el.value);if(el.dataset.sourceLocal)sourceToggle(Number(el.dataset.sourceLocal));if(el.id==='source-select-page'){for(let n=sourceRange;n<sourceRange+50&&n<=(sourceData.totalEpisodes||0);n++){if(sourceEpisodeState(n)==='candidate'){if(el.checked&&!sourceSelected.includes(n))sourceSelected.push(n);if(!el.checked)sourceSelected=sourceSelected.filter(x=>x!==n);}}sourceRenderMain();}});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-source]');if(!b||b.disabled)return;const action=b.dataset.source;b.disabled=true;try{
 if(action==='native-catalog'||action==='native-search')await sourceRead(sourceNativeURL());
 if(action==='resolve')await sourceRead(sourceText);
 if(action==='catalog')await sourceRead(sourceCatalogURL());
 if(action==='refresh')await sourceRead(sourceText,true);
 if(action==='detail')await sourceRead(b.dataset.url);
 if(action==='previous'||action==='next'){const n=Number(new URL(sourceCatalog.url).searchParams.get('page')||1)+(action==='next'?1:-1);const next=new URL(sourceCatalog.url);next.searchParams.set('page',String(n));await sourceRead(next.toString());}
 if(action==='tab'){sourceTab=b.dataset.tab;sourceRenderMain();}
 if(action==='range'){sourceRange=Number(b.dataset.number);sourceRenderMain();}
 if(action==='episode')sourceToggle(Number(b.dataset.number));
 if(action==='expression')sourceApplyExpression();
 if(action==='clear'){sourceSelected=[];sourceNotice='';sourceRenderMain();}
 if(action==='select-local'){sourceSelected=[...new Set([...sourceSelected,...sourceLocals().keys()])];sourceRenderMain();}
 if(action==='browse'){const r=await api('browse',{mode:'folder'});if(r.path){sourceDirectory=r.path;await updateConfig({sourceImportRoot:r.path});sourceRenderMain();}}
 if(['download','download-all','save'].includes(action))await sourceStartImport(action);
 if(action==='stop'){await api('source/cancel',{id:b.dataset.id});await sourcePoll();}
 if(action==='resume'){await api('source/control',{id:b.dataset.id,action:'resume'});await sourcePoll();}
 if(action==='move'){const t=sourceTasks.find(t=>t.id===b.dataset.id),numbers=t.items.filter(i=>i.status==='pending').map(i=>i.number),i=numbers.indexOf(Number(b.dataset.number)),j=i+Number(b.dataset.offset);[numbers[i],numbers[j]]=[numbers[j],numbers[i]];await api('source/control',{id:t.id,action:'reorder',episodes:numbers});await sourcePoll();}
 if(action==='access-resume'){await api('source/access-resume',{});await sourcePoll();}
 if(action==='open')await api('source/open',{id:b.dataset.id});
 if(action==='project'){await refresh();focusId=b.dataset.id;selected.add(focusId);location.hash='scan';}
 if(action==='preview'){const v=sourceLocals().get(Number(b.dataset.number));if(!v)throw Error('本地视频不存在');$('#output-video').src=media(v.path);$('#output-dialog').showModal();}
 if(action==='produce')await sourceProduction();
 if(action==='close-produce')$('#source-produce-dialog').close();
 if(action==='confirm-produce'){const d=$('#source-produce-dialog'),request=d.sourceRequest;await api('jobs',{kind:$('#source-produce-kind').value,ids:[request.projectId],sourceVideoPaths:{[request.projectId]:request.paths}});d.close();await refresh();location.hash='progress';toast('已按所选集数加入制作队列');}
}catch(err){toast(err.message,true);}finally{if(b.isConnected)b.disabled=false;}});
document.addEventListener('error',e=>{if(e.target.matches?.('#source-workbench .hero-poster img,#source-workbench .drama-poster img')){e.target.hidden=true;e.target.parentElement.setAttribute('aria-label','封面暂未载入');}},true);

function sourceCatalogURL(query=''){const q=new URLSearchParams({page:'1',query,category:sourceNativeCategory});return 'guoapp://hongguo/catalog?'+q;}
function sourceNativeURL(){if(/https:\/\/novelquickapp\.com\//.test(sourceNativeQuery))return sourceNativeQuery;return sourceCatalogURL(sourceNativeQuery.trim());}
function sourceNativeToolbar(){return `<form class="source-native-toolbar" aria-label="红果原生剧库" aria-busy="${sourceBusy}"><div class="source-native-title"><strong>原生剧库</strong><small>目录 · 搜索 · 选集导入</small></div><label class="source-native-query" for="source-native-query"><span>剧名</span><input id="source-native-query" type="search" placeholder="搜索剧名或粘贴官方分享链接" value="${esc(sourceNativeQuery)}" ${sourceStarting?'disabled':''}></label><label for="source-native-category" class="source-native-category"><span>分类</span><select id="source-native-category" ${sourceStarting?'disabled':''}>${[['','全部'],['short_play','真人剧'],['comic_series','漫剧'],['ai_series','AI剧']].map(([v,n])=>`<option value="${v}" ${sourceNativeCategory===v?'selected':''}>${n}</option>`).join('')}</select></label><button type="button" class="button primary small" data-source="native-search" ${sourceBusy?'disabled':''}>${sourceBusy?'读取中…':sourceNativeQuery.trim()?'搜索':'浏览原生目录'}</button><span class="source-native-note">${sourceNativeStatus.available===false?'组件暂不可用':'已接入 guoapp'}</span></form>`;}
document.addEventListener('submit',e=>{if(e.target.matches('.source-native-toolbar')){e.preventDefault();if(!sourceStarting)sourceRead(sourceNativeURL());}});
