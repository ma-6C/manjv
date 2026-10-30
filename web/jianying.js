'use strict';
jobLabels.jianying_project='剪映工程图';
let jyCustom=null,jySettingsSnapshot=null;
const jyCustomMode=()=>jyCustom??(state.jianyingCustom===true);
const jyLive=()=>state.jobs.some(j=>j.kind==='jianying_project'&&['queued','running','pausing'].includes(j.status));
let jianyingOptions=null,jianyingSource='original',jianyingStatus='',jianyingJob='',jyStatusInfo=null,jyStatusLoading=false,jyEvidenceLoading=false,jyEvidenceProject='',jyEvidenceItems=[],jyEvidenceTasks=[],jyEvidenceSignature='',jyCaptureTarget=null,jyWindows=[],jyImported=new Map(),jyBusy=false;
const jyOptions=()=>jianyingOptions||(jianyingOptions={output:'',splitScenes:true,executable:'',draftRoot:'',timelineMode:'detailed',shotSeconds:10,cameraMotion:true,originalVolume:1,subtitlePath:'',subtitleStyle:'bold',musicPath:'',musicVolume:0.15,soundEffectPath:'',soundEffectVolume:0.35,soundEffectEvery:4,mouseOpen:true,
 editProfile:'cinema',colorAdjust:true,cutMaterials:true,speedPattern:'original',transition:'dissolve',filterStyle:'cinema',filterIntensity:25,visualEffect:'',overlayText:'',
 audioMode:'separate',captionMode:'auto',aiPython:'',aiModelRoot:'',aiDevice:'auto',aiFailure:'stop',cudaLibraries:'auto',asrLanguage:'zh',separationModel:'htdemucs',captionLength:14,materialLibrary:'',mood:'auto',addBgm:false,adjustTrack:true,duckMusic:true,registerIndex:true,timelineZoom:2,previewBeforeCapture:false,...state.jianyingOptions});
const jyJob=()=>state.jobs.find(j=>j.id===jianyingJob)||state.jobs.filter(j=>j.kind==='jianying_project').at(-1);
const jyProject=()=>state.projects.find(p=>p.id===jyEvidenceProject)||activeProject();
const jyProjectId=()=>jyProject()?.id||'';
const jyStamp=value=>value?new Date(Number(value)*1000).toLocaleString('zh-CN'):'时间未记录';
function jyStatusHTML(){
 if(jyStatusLoading)return icon('refresh')+'正在检查本机剪映与草稿组件…';
 if(!jyStatusInfo)return '先检测本机剪映。草稿文件与官方应用里的实际截图分别记录。';
 const s=jyStatusInfo,installed=s.editorInstalled;
 return `<strong>${installed?'已找到本机剪映':'尚未找到本机剪映'}</strong><span>${installed?esc(s.editorVersion||'版本待核对'):'安装后重新检测，或填写主程序路径'}</span>${s.editorExecutable?`<small>${esc(s.editorExecutable)}</small>`:''}<small>草稿桥接组件：${esc(s.component||'pyJianYingDraft')} ${esc(s.version||'未安装')} · ${s.available?'可建立草稿':'需要安装组件'}</small>${s.ai?`<small>AI 引擎路径：${s.ai.runtimeConfigured?'已找到':'未配置'} · 语音模型：${s.ai.asrModelPresent?'文件存在':'未找到'} · 分离模型：${s.ai.separationModelPresent?'文件存在':'未找到'}。这里只检查文件，实际运行能力待处理时确认。</small>`:''}<small>${esc(s.note||'请在剪映实际打开并检查工程；文件生成不代表编辑器已验证。')}</small>`;
}
function jyRowDetails(row,job){
 if(!row)return '';
 const i=job.jianyingResults.indexOf(row),t=row.timeline||{};
 return `<details class="jy-row-details"><summary>详情</summary><p>${row.segments} 个画面片段 · 人声 ${t.vocalSegments||0} 段 · 字幕 ${t.captionSegments||0} 条 · 配乐 ${t.musicSegments||0} 段 · 音效 ${t.soundEffectSegments||0} 处 · 独立调节 ${t.adjustTrackSegments||0} 层</p>${(row.warnings||[]).map(w=>`<p>${esc(w)}</p>`).join('')}<small>${esc(row.directory)}</small><div class="actions-row"><button class="button small" data-jianying="open" data-id="${esc(job.id)}" data-index="${i}">${icon('folder')}工程目录</button><button class="button small" data-jianying="auto-capture" data-project="${esc(row.projectId)}" data-id="${esc(job.id)}" data-index="${i}" ${jyLive()?'disabled':''}>重新采集工程图</button></div></details>`;
}
function jianyingResults(){
 const job=jyJob();if(!job)return '<div class="jy-auto-empty"><strong>选好剧集即可开始</strong><p>默认方案已配好，生成后工程图会显示在这里。</p></div>';
 const rows=job.jianyingResults||[],videos=job.options?.jianyingVideos||rows.map(r=>({path:r.sourcePath,name:r.name,projectId:r.projectId})),episodes=job.jianyingEpisodes||{},live=jyLive();
 const successful=videos.filter((v,i)=>episodes[i]?.status==='completed'||rows.find(r=>r.sourcePath===v.path)?.diagram).length;
 const failures=Object.values(episodes).filter(e=>['failed','waiting_action'].includes(e.status)).length;
 const retry=['paused','interrupted','failed','cancelled'].includes(job.status);
 return `<div class="jy-job-state"><div class="jy-batch-heading"><strong>${live?'正在自动出图':esc(statusLabels[job.status]||job.status)}</strong><span>成功 ${successful} / ${videos.length} 集${failures?' · 未完成 '+failures+' 集':''}</span></div><p role="status" aria-live="polite">${esc(job.stage||'等待开始')}</p>${job.error?`<p class="track-error" role="alert">${esc(job.error)}</p>`:''}<div class="actions-row">${live?`<button class="button small" data-jianying="control" data-control="pause" data-id="${esc(job.id)}">暂停</button><button class="button small" data-jianying="control" data-control="cancel" data-id="${esc(job.id)}">停止</button>`:retry?`<button class="button primary small" data-jianying="control" data-control="resume" data-id="${esc(job.id)}">${icon('refresh')}继续未完成部分</button>`:''}<a href="#logs">查看日志</a></div></div><div class="jy-table-scroll"><table class="jy-episode-table"><thead><tr><th scope="col">剧集</th><th scope="col">状态</th><th scope="col">工程图</th></tr></thead><tbody>${videos.map((v,i)=>{
  const row=rows.find(r=>r.sourcePath===v.path),entry=episodes[i]||{},image=row?.diagram;
  let status=entry.status||(image?'completed':row?'draft':'queued');if(!live&&status==='running')status='paused';
  const title=entry.projectName||state.projects.find(p=>p.id===v.projectId)?.name||'';
  const label={completed:image?'已出图':'草稿已生成',running:entry.step||'正在处理',waiting_action:'等待处理提示',failed:'未完成',paused:'已暂停',queued:'等待处理',draft:'草稿已生成，待出图'}[status]||status;
  return `<tr><td><strong>${esc(title)}</strong><small>${esc(v.name)}</small>${jyRowDetails(row,job)}</td><td><span class="tag ${status==='completed'?'green':'gray'}">${esc(label)}</span>${entry.error?`<p class="jy-episode-error">${esc(entry.step||'')}：${esc(entry.error)}</p>`:''}${row?.timeline?.degraded?`<small class="jy-episode-error">${esc((row.warnings||[]).filter(w=>w.includes('失败')).join('；').slice(0,160)||'AI 处理未完成，已保留可用工程')}</small>`:''}</td><td>${image?`<a class="button small" href="${esc(media(image.path))}" target="_blank" rel="noreferrer">${icon('image')}查看图片</a>`:row&&!live?`<button class="button small" data-jianying="auto-capture" data-project="${esc(row.projectId)}" data-id="${esc(job.id)}" data-index="${rows.indexOf(row)}">生成本集工程图</button>`:'—'}</td></tr>`;
 }).join('')}</tbody></table></div>`;
}
function jyGalleryItems(){
 const job=jyJob();if(!job)return jyEvidenceItems;const items=[...(job.jianyingResults||[]).map(r=>r.diagram).filter(Boolean),...jyEvidenceItems.filter(item=>item.projectAssociation?.jobId===job.id)];return [...new Map(items.map(item=>[item.id||item.path,item])).values()];
}
function jianyingCard(){
 return card('自动生成工程图','image',`<div class="jy-auto-summary"><div><strong>${jyCustomMode()?'使用已保存的自定义方案':'默认方案已配好'}</strong><p>选集后开始，软件会自动建立工程并在剪映中完成出图。${jyCustomMode()?'':'视频素材按 2～10 秒随机分段，完整保留原片。'}</p></div></div><p id="jy-status" role="status" aria-live="polite">${esc(jianyingStatus)}</p><div id="jy-results" class="jianying-results">${jianyingResults()}</div>`)+`<div id="jy-evidence-items" class="jy-evidence-items jy-auto-gallery">${jyEvidenceHTML(jyGalleryItems())}</div>`+jySettingsHTML();
}

function jyField(label,id,key,placeholder='',browse=''){
 return `<div class="field"><label for="${id}">${label}</label><div class="path-input"><input id="${id}" data-jy-option="${key}" value="${esc(jyOptions()[key]||'')}" placeholder="${esc(placeholder)}">${browse?`<button class="button small" data-jianying="path" data-key="${key}" data-mode="${browse}">${icon('folder')}选择</button>`:''}</div></div>`;
}
function jySelect(label,key,choices){
 const o=jyOptions();return `<div class="field"><label for="jy-${key}">${label}</label><select id="jy-${key}" data-jy-option="${key}">${choices.map(([value,text])=>`<option value="${value}" ${o[key]===value?'selected':''}>${text}</option>`).join('')}</select></div>`;
}
function jyNumber(label,key,min,max,step){return `<div class="field"><label for="jy-${key}">${label}</label><input id="jy-${key}" type="number" data-jy-option="${key}" min="${min}" max="${max}" step="${step}" value="${jyOptions()[key]}"></div>`;}
function jyCheck(label,key){return `<label class="check-label jy-check"><input type="checkbox" data-jy-option="${key}" ${jyOptions()[key]?'checked':''}>${label}</label>`;}
function jySettingsHTML(){
 const o=jyOptions();return `<dialog id="jy-settings-dialog" class="jy-settings-dialog" aria-labelledby="jy-settings-title"><div class="dialog-top"><div><h2 id="jy-settings-title">工程图设置</h2><p>默认自动配好，特殊需要时再调整。</p></div><button class="icon-button" data-jianying="settings-close" aria-label="关闭工程图设置">×</button></div>${jySelect('GPU 运行库','cudaLibraries',[['auto','自动 · 优先 PyTorch，失败再尝试 NVIDIA 独立包'],['torch','PyTorch 自带 cuBLAS / cuDNN'],['nvidia','NVIDIA 独立 cuBLAS / cuDNN 包']])}<p class="field-hint">保存后用于新任务。每次切换都会启用新的工作进程，实际使用的库、版本和回退原因保存在任务诊断中。</p><label class="check-label jy-check"><input type="checkbox" id="jy-custom-mode" ${jyCustomMode()?'checked':''}>使用自定义方案（不勾选时自动套用默认方案）</label><details class="jy-advanced-fields"><summary>调整高级参数</summary> <div class="jy-edit-grid">${jySelect('工程方案','timelineMode',[['detailed','完整剪辑 · 分镜、分段音轨与可选包装'],['basic','基础工程 · 分镜画面与整段原声']])}
 <div class="field"><label for="jy-source">工程输入</label><select id="jy-source"><option value="original" ${jianyingSource==='original'?'selected':''}>左侧所选视频（按选择顺序）</option><option value="final" ${jianyingSource==='final'?'selected':''}>所选剧集的当前成片</option><option value="subtitle" ${jianyingSource==='subtitle'?'selected':''}>所选剧集的去字幕结果</option></select></div></div>
 ${jyField('工程输出目录','jy-output','output','留空：导出目录下的剪映工程','folder')}
 <label class="check-label jy-check"><input id="jy-split" type="checkbox" ${o.splitScenes?'checked':''}>识别实际镜头边界</label>
 <div class="jy-edit-grid">${jyNumber('随机切片：最长秒数（最短2秒）','shotSeconds',2,30,0.5)}${jyNumber('原声音量（1为原音量）','originalVolume',0,2,0.05)}</div>
 <label class="check-label jy-check"><input type="checkbox" data-jy-option="cameraMotion" ${o.cameraMotion?'checked':''}>完整剪辑：为每段添加可编辑的轻微推拉运镜</label>
 <details class="jy-connection-settings"><summary>画面剪辑与效果层</summary>
 ${jySelect('剪辑风格','editProfile',[['cinema','电影质感 · 轻微推拉与色彩调整'],['clean','清晰自然 · 克制调整'],['energetic','明快节奏 · 较明显运镜']])}
 ${jyCheck('将每个镜头写成独立视频素材（增加生成时间和磁盘占用）','cutMaterials')}
 ${jyCheck('将风格对应的亮度、对比度和饱和度写入可编辑关键帧','colorAdjust')}
 ${jyCheck('建立独立调节轨（初始中性，可在剪映继续调整）','adjustTrack')}
 <div class="jy-edit-grid">${jySelect('变速方案','speedPattern',[['original','保持原速'],['gentle','轻微变速 · 同步重排字幕和声音']])}${jySelect('画面转场','transition',[['dissolve','短叠化'],['none','不添加']])}</div>
 <div class="jy-edit-grid">${jySelect('独立滤镜层','filterStyle',[['cinema','质感电影'],['none','不添加']])}${jyNumber('滤镜强度','filterIntensity',0,100,1)}</div>
 ${jySelect('独立画面特效层','visualEffect',[['','不添加'],['_1998','1998 复古质感'],['_70s','70s 复古质感']])}
 ${jyField('角标文字（可选）','jy-overlayText','overlayText','最多50字，写入独立文字层')}
 <p class="field-hint">滤镜、转场与特效需要当前剪映版本支持对应资源，首次使用可能需要在剪映下载。</p></details>
 <details class="jy-connection-settings"><summary>语音识别与人声分离</summary>
 <div class="jy-edit-grid">${jySelect('声音处理','audioMode',[['separate','分离人声与背景声'],['original','保留混合原声']])}${jySelect('字幕来源','captionMode',[['auto','优先同名 SRT，否则本地语音识别'],['srt','只读取 SRT'],['none','不生成字幕轨']])}</div>
 ${jyField('剪映 AI 引擎 Python','jy-aiPython','aiPython','留空：使用已配置的本地 AI 引擎 Python','python')}
 ${jyField('剪映 AI 模型目录','jy-aiModelRoot','aiModelRoot','目录内应有 faster-whisper 和 demucs 子文件夹','folder')}
 <div class="jy-edit-grid">${jySelect('推理设备','aiDevice',[['auto','优先 GPU，不兼容时重启进程使用 CPU'],['cpu','CPU']])}${jySelect('AI 处理失败时','aiFailure',[['keep','保留可用工程，明确记录未完成的 AI 步骤'],['stop','停止本集，保留失败原因']])}</div>
 <div class="jy-edit-grid">${jySelect('识别语言','asrLanguage',[['zh','中文'],['','自动识别'],['en','英语'],['ja','日语'],['ko','韩语']])}${jyNumber('识别字幕每行字数','captionLength',6,30,1)}</div>
 ${jySelect('本地分离模型','separationModel',[['htdemucs','htdemucs'],['htdemucs_ft','htdemucs_ft'],['mdx_extra','mdx_extra']])}
 <p class="field-hint">这两项需要含语音识别及音频分离依赖的 AI 引擎和本地模型。去字幕引擎包不一定包含它们；缺少时会按上方规则处理，不会生成空白字幕或假分轨。</p></details>
 <details class="jy-connection-settings"><summary>字幕、配乐与音效</summary>
 ${jyField('字幕 SRT（单个视频可指定；批量使用各视频同名 SRT）','jy-subtitlePath','subtitlePath','留空：查找视频旁的同名 SRT','subtitles')}
 ${jySelect('字幕样式','subtitleStyle',[['bold','大字白色描边'],['yellow','大字黄色描边'],['plain','简洁白字']])}
 ${jyField('剪映素材目录（留空自动检测）','jy-materialLibrary','materialLibrary','可选剪映根目录或 Cache\\music，自动按时长区分','folder')}
 <p class="field-hint">自动读取剪映已下载的声音素材：100秒以上作为配乐，1.5～15秒作为音效，无需另建分类文件夹。</p>
 ${jyCheck('添加背景音乐（默认关闭，避免覆盖原片声音）','addBgm')}
 ${jySelect('声音素材氛围','mood',[['auto','根据剧名关键词匹配'],['tense','紧张悬疑'],['warm','温暖治愈'],['sad','伤感'],['bright','轻松明快']])}
 ${jyField('背景音乐（可选）','jy-musicPath','musicPath','选择本机音频，自动铺满本集并淡入淡出','audio')}
 ${jyNumber('背景音乐音量','musicVolume',0,1,0.05)}
 ${jyCheck('在原声或人声活动区间降低配乐音量','duckMusic')}
 ${jyField('转场音效（可选）','jy-soundEffectPath','soundEffectPath','选择本机音效，按画面切点安排','audio')}
 <div class="jy-edit-grid">${jyNumber('每隔几个画面片段安排音效','soundEffectEvery',1,30,1)}${jyNumber('音效音量','soundEffectVolume',0,1,0.05)}</div>
 <p class="field-hint">未提供字幕或音频时会说明缺少的内容，并保留已有画面与原声。</p></details>
 <details class="jy-connection-settings"><summary>自动打开与剪映位置</summary>
 <label class="check-label jy-check"><input type="checkbox" data-jy-option="mouseOpen" ${o.mouseOpen?'checked':''}>允许自动打开时短暂使用鼠标，双击已确认的工程卡片</label>
 <p class="field-hint">优先调用剪映控件的打开动作；需要鼠标时只点击当前唯一匹配的卡片。其他工程正在编辑时会等待你保存和切换。</p>
 ${jyCheck('剪映退出后备份并登记草稿索引，将本工程置顶并添加临时封面标记','registerIndex')}
 ${jyNumber('自动截图：时间线放大步数','timelineZoom',0,5,1)}
 ${jyCheck('自动截图前短暂播放并暂停预览（需识别到播放控件）','previewBeforeCapture')}
 <p class="field-hint">自动出图会置前剪映、调整时间线并等待画面稳定。请暂时停止操作鼠标；已有工程需要你先保存并退出，本工具不会强制关闭。</p>
 ${jyField('剪映主程序（自动检测，可手动指定）','jy-executable','executable','选择 JianyingPro.exe','editor')}
 ${jyField('剪映草稿库（自动检测，可手动指定）','jy-draftRoot','draftRoot','选择剪映本地草稿库目录','folder')}
 <button class="button small" data-jianying="status">${icon('refresh')}重新检测剪映</button></details>
 <div class="jy-editor-status" id="jy-editor-status" role="status">${jyStatusHTML()}</div>
</details><details class="jy-manual-import"><summary>手动操作与已有截图</summary><div class="actions-row"><button class="button" data-jianying="draft-only">只生成可编辑草稿</button><button class="button" data-jianying="relocate">移动后重连素材</button></div>${jyEvidenceCard()}</details><div class="jy-settings-footer"><button class="button" data-jianying="settings-reset">恢复自动方案</button><button class="button primary" data-jianying="settings-save">完成</button></div></dialog>`;
}

function jyEvidenceCard(){
 return card('剪映实际工程截图','image',`<div class="field"><label for="jy-evidence-project">截图归属剧目</label><select id="jy-evidence-project">${state.projects.length?state.projects.map(p=>`<option value="${esc(p.id)}" ${p.id===jyProjectId()?'selected':''}>${esc(p.name)}</option>`).join(''):'<option value="">请先导入素材</option>'}</select></div><p class="field-hint">在剪映中打开本剧工程，让预览和时间线清晰可见。选择窗口后，按提示切换过去，软件采集真实窗口画面。</p><div class="actions-row"><button class="button primary" data-jianying="capture">${icon('image')}选择剪映窗口并截图</button><button class="button small" data-jianying="evidence-refresh">${icon('refresh')}刷新截图</button></div><div id="jy-window-picker"></div><details class="jy-manual-import"><summary>导入已保存的实际截图</summary><p class="field-hint">可选择本机图片。手动导入会标记为「本人确认，来源未核验」，不冒认为本工具已验证的官方窗口截图。</p><div class="field"><label for="jy-evidence-note">截图对应的工程与说明</label><textarea id="jy-evidence-note" rows="2" placeholder="例如：本剧第01集，在剪映中打开后的时间线截图"></textarea></div><label class="check-label jy-check"><input id="jy-evidence-confirm" type="checkbox">我确认所选图片来自本剧的实际剪映工程，内容未伪造。</label><button class="button" data-jianying="import-evidence">${icon('folder')}选择并导入图片</button></details><div id="jy-evidence-status" role="status" aria-live="polite"></div><div id="jy-evidence-tasks"></div>`,'保留截图来源、采集时间及工程关联记录');
}
function jyEvidenceHTML(items=jyEvidenceItems){
 if(!items.length)return `<div class="jy-evidence-empty">${icon('image')}<strong>还没有工程图</strong><p>选集后点击“生成工程图”，完成的图片会自动保存在这里。</p></div>`;
 return items.map(item=>{const supported=item.platform==='jianying',captured=item.source==='window_capture',verified=supported&&captured&&(item.officialEvidence===true||item.officialEvidence?.appVerified===true),source=!supported?'历史来源 · 不参与工程核验':verified?'官方窗口来源已核验':captured?'窗口采集 · 来源待核对':'本人导入 · 来源未核验',label=supported?'剪映':'历史截图',url=item.url||media(item.path),association=item.projectAssociation;return `<article class="jy-evidence-item"><a href="${esc(url)}" target="_blank" rel="noreferrer"><img src="${esc(url)}" alt="${label}实际截图，${esc(source)}" loading="lazy"></a><div><strong>${esc(supported?(item.name||item.title||'工程截图'):'历史截图')}</strong><span class="tag ${verified?'green':'gray'}">${esc(source)}</span><p>${label} · ${esc(jyStamp(item.capturedAt||item.createdAt))}</p>${association?`<p>${esc(typeof association==='string'?association:association.message||association.status||(association.userConfirmed?'工程归属由本人确认；来源核验不代表工程内容或平台审核已通过':'已登记剧目关联，需本人核对画面内容'))}</p>`:''}${item.note?`<p>${esc(item.note)}</p>`:''}<a href="${esc(url)}${url.includes('?')?'&':'?'}download=1">查看原图</a></div></article>`;}).join('');
}
function jyEvidenceTasksHTML(){return jyEvidenceTasks.filter(t=>!t.projectId||t.projectId===jyProjectId()).slice(-3).reverse().map(task=>`<div class="jy-capture-task ${task.status==='failed'?'error':''}"><strong>${esc({waiting_window:'等待切换到官方窗口',automating:'正在自动打开并准备截图',waiting_action:'需要先处理剪映中的提示',capturing:'正在采集窗口',completed:'截图已保存',failed:'未完成截图'}[task.status]||task.status)}</strong><p>${esc(task.message||task.error||'')}</p></div>`).join('');}
function jyWindowPickerHTML(){return `<div class="jy-window-choice"><div class="field"><label for="jy-capture-window">选择需要截图的剪映窗口</label><select id="jy-capture-window">${jyWindows.map((w,i)=>`<option value="${i}">${esc(w.title||w.name||'未命名窗口')} · ${esc(w.processName||w.platform||'')}</option>`).join('')}</select></div><p class="field-hint">选定后请在 30 秒内切换到该窗口，保持工程预览与时间线可见。窗口稳定置前后会采集；等待过程不会生成替代图片。</p><label class="check-label jy-check"><input id="jy-capture-confirm" type="checkbox">我已在所选剪映窗口打开本剧实际工程，预览与时间线清晰可见。</label><div class="actions-row"><button class="button primary" data-jianying="capture-window">开始等待并截图</button><button class="button" data-jianying="capture-cancel">取消选择</button></div></div>`;}
async function jyLoadStatus(){if(jyStatusLoading)return;jyStatusLoading=true;if($('#jy-editor-status'))$('#jy-editor-status').innerHTML=jyStatusHTML();try{jyStatusInfo=await api('jianying/status',{jianying:jyOptions()});}catch(error){jianyingStatus=error.message;}finally{jyStatusLoading=false;if($('#jy-editor-status'))$('#jy-editor-status').innerHTML=jyStatusHTML();if($('#jy-status'))$('#jy-status').textContent=jianyingStatus;}}
async function jyLoadEvidence(){
 const id=jyProjectId();if(!id||jyEvidenceLoading)return;jyEvidenceLoading=true;
 try{const result=await api('project-evidence/list?projectId='+encodeURIComponent(id));if(id!==jyProjectId())return;jyEvidenceItems=result.items||[];jyEvidenceTasks=result.tasks||[];const signature=JSON.stringify([id,jyEvidenceItems,jyEvidenceTasks]);if(signature!==jyEvidenceSignature){jyEvidenceSignature=signature;if($('#jy-evidence-items'))$('#jy-evidence-items').innerHTML=jyEvidenceHTML(jyGalleryItems());if($('#jy-evidence-tasks'))$('#jy-evidence-tasks').innerHTML=jyEvidenceTasksHTML();}}
 catch(error){if($('#jy-evidence-status'))$('#jy-evidence-status').textContent=error.message;}
 finally{jyEvidenceLoading=false;if(id!==jyProjectId()&&current==='tracks')jyLoadEvidence();}
}
const jyBaseRender=renderPage;renderPage=function(){jyBaseRender();if(current==='tracks'){const host=$('#jy-workspace-host');if(host)host.innerHTML=jianyingCard();jyLoadStatus();jyLoadEvidence();}};
const jyBaseRefresh=refresh;refresh=async function(render=false){await jyBaseRefresh(render);if(current==='tracks'&&$('#jy-results')){const html=jianyingResults();const openDetails=[...$('#jy-results').querySelectorAll('details[open]')].map(el=>el.closest('tr')?.rowIndex);if($('#jy-results').innerHTML!==html){$('#jy-results').innerHTML=html;for(const i of openDetails){const el=$('#jy-results').querySelectorAll('tr')[i]?.querySelector('details');if(el)el.open=true;}}const gallery=$('#jy-evidence-items'),images=jyEvidenceHTML(jyGalleryItems());if(gallery&&gallery.innerHTML!==images)gallery.innerHTML=images;}};
const jyBaseTaskbar=renderTaskbar;renderTaskbar=function(){
 jyBaseTaskbar();if(current!=='tracks')return;
 const ready=trackVideos().length>0||(jianyingSource!=='original'&&activeProject());
 for(const button of document.querySelectorAll('[data-jianying="generate"]'))button.disabled=jyBusy||jyLive()||!ready;
};
document.addEventListener('close',e=>{if(e.target.id==='jy-settings-dialog'&&jySettingsSnapshot){jianyingOptions=jySettingsSnapshot.options;jyCustom=jySettingsSnapshot.custom;jianyingSource=jySettingsSnapshot.source;jySettingsSnapshot=null;renderTaskbar();}},true);
document.addEventListener('input',e=>{const el=e.target;if(el.dataset.jyOption)jyOptions()[el.dataset.jyOption]=el.type==='checkbox'?el.checked:el.type==='number'?el.valueAsNumber:el.value;});
document.addEventListener('change',e=>{const el=e.target;if(el.dataset.jyOption)jyOptions()[el.dataset.jyOption]=el.type==='checkbox'?el.checked:el.type==='number'?el.valueAsNumber:el.value;if(el.id==='jy-custom-mode')jyCustom=el.checked;if(el.id==='jy-split')jyOptions().splitScenes=el.checked;if(el.id==='jy-source'){jianyingSource=el.value;renderTaskbar();}if(el.id==='jy-evidence-project'){jyEvidenceProject=el.value;jyEvidenceItems=[];jyEvidenceTasks=[];jyEvidenceSignature='';jyLoadEvidence();}});
function jyStatusMessage(text,isError=false){jianyingStatus=text;const el=$('#jy-status');if(el){el.textContent=text;el.setAttribute('role',isError?'alert':'status');el.classList.toggle('track-error',isError);}}
async function jyChooseWindows(target){
 const projectId=target?.projectId||jyProjectId();if(!projectId)throw Error('请先选择截图归属剧目');
 jyCaptureTarget={...target,projectId,platform:'jianying'};const result=await api('project-evidence/capture',jyCaptureTarget);
 jyWindows=result.windows||result.candidates||[];if(!jyWindows.length)throw Error(result.message||'没有找到可采集的官方窗口，请先打开对应工程。');
 $('#jy-window-picker').innerHTML=jyWindowPickerHTML();$('#jy-capture-window').focus();
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-jianying]');if(!b||b.disabled||jyBusy)return;const action=b.dataset.jianying;
 if(action==='settings-open'){jySettingsSnapshot={options:{...jyOptions()},custom:jyCustom,source:jianyingSource};for(const el of document.querySelectorAll('#jy-settings-dialog [data-jy-option]')){if(el.type==='checkbox')el.checked=!!jyOptions()[el.dataset.jyOption];else el.value=jyOptions()[el.dataset.jyOption]??'';}$('#jy-custom-mode').checked=jyCustomMode();$('#jy-split').checked=jyOptions().splitScenes;$('#jy-source').value=jianyingSource;$('#jy-settings-dialog').showModal();return;}
 if(action==='settings-close'){$('#jy-settings-dialog').close();return;}
 if(action==='capture-cancel'){jyCaptureTarget=null;jyWindows=[];if($('#jy-window-picker'))$('#jy-window-picker').innerHTML='';return;}
 jyBusy=true;const oldButtonHTML=b.innerHTML;b.disabled=true;b.innerHTML=icon('refresh')+'正在处理…';
 try{
  if(action==='path'){const result=await api('browse',{mode:b.dataset.mode});if(result.path){jyOptions()[b.dataset.key]=result.path;const input=$(`[data-jy-option="${b.dataset.key}"]`);if(input)input.value=result.path;}}
  else if(action==='status')await jyLoadStatus();
  else if(action==='settings-save'||action==='settings-reset'){
   if(action==='settings-reset'){jyCustom=false;const check=$('#jy-custom-mode');if(check)check.checked=false;}
   const saved=await api('jianying/options',{options:jyOptions(),custom:jyCustomMode()});jianyingOptions=saved.options;jySettingsSnapshot=null;$('#jy-settings-dialog').close();await refresh();const main=$('.jy-auto-summary strong');if(main)main.textContent=jyCustomMode()?'使用已保存的自定义方案':'默认方案已配好';
  }else if(action==='generate'||action==='draft-only'){
   if(jyLive())throw Error('当前批次正在处理，请等待完成或先暂停');
   const body={...trackSelectionBody(false),kind:'jianying_project',sourceKind:jianyingSource,jianying:{...jyOptions()},autoDiagram:action==='generate',automatic:action==='generate'&&!jyCustomMode()};
   if(jianyingSource!=='original'){body.ids=[...new Set(trackVideos().map(v=>v.projectId))];if(!body.ids.length&&activeProject())body.ids=[activeProject().id];delete body.sourceVideoPaths;}
   if(!body.ids.length)throw Error('请先选择工程素材');
   const plan=await api('jianying/plan',body),result=await api('jobs',body);jianyingJob=result.id;if($('#jy-settings-dialog')?.open)$('#jy-settings-dialog').close();jyStatusMessage(`${plan.count} 集已开始${action==='generate'?'自动出图，处理中请暂时停止操作鼠标。':'生成可编辑草稿。'}`);await refresh();toast(jianyingStatus);
  }else if(action==='open')await api('jianying/open',{id:b.dataset.id,index:Number(b.dataset.index)});
  else if(action==='install'){
   const result=await api('jianying/install',{jobId:b.dataset.id,index:Number(b.dataset.index),options:jyOptions()});jyImported.set(b.dataset.id+':'+b.dataset.index,result);jyStatusMessage(result.message||'已复制到剪映草稿库。请在剪映打开对应工程核对，尚未验证编辑器画面。');await refresh();
  }else if(action==='auto-open'){
   jyStatusMessage(jyOptions().mouseOpen?'正在定位本工程；需要鼠标点击时请暂时停止移动鼠标。':'正在定位本工程，请保持剪映窗口可见。');
   const result=await api('jianying/auto-open',{jobId:b.dataset.id,index:Number(b.dataset.index),options:jyOptions()});jyStatusMessage(result.message||'请核对剪映中的本次工程',result.reason==='editor_media_missing');
  }else if(action==='auto-capture'){
   jyEvidenceProject=b.dataset.project;const select=$('#jy-evidence-project');if(select)select.value=jyEvidenceProject;
   jyStatusMessage('正在登记并打开本工程，随后调整时间线并采集剪映原始窗口。请暂时停止操作鼠标。');
   const result=await api('jianying/auto-capture',{jobId:b.dataset.id,index:Number(b.dataset.index),projectId:b.dataset.project,options:jyOptions()});
   jyStatusMessage(result.message);await jyLoadEvidence();
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
 }catch(error){jyStatusMessage(error.message,true);toast(error.message,true);if(action.includes('capture')||action.includes('evidence')){const status=$('#jy-evidence-status');if(status)status.textContent=error.message;}}
 finally{jyBusy=false;if(b.isConnected){b.disabled=false;b.innerHTML=oldButtonHTML;}renderTaskbar();}
});
setInterval(()=>{if(current==='tracks'&&jyEvidenceTasks.some(t=>['waiting_window','capturing','automating','queued','running'].includes(t.status)))jyLoadEvidence();},1000);
