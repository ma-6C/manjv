'use strict';
// Video selection is shared with editable Jianying drafts. Legacy drawn track
// sheets remain in historical artifacts, but no route creates new ones.
pages.splice(pages.findIndex(p=>p[0]==='cost'),0,['tracks','剪映工程与截图','layers']);
navigationLabels.tracks='剪映工程与截图';
jobLabels.track_sheet='历史分轨示意图';
shapes.trackUp='M12 20V4m-6 6 6-6 6 6';shapes.trackDown='M12 4v16m-6-6 6 6 6-6';
let trackMode='batch',trackBatch=[],trackSingle=[],trackOptions=null,trackQuery='',trackErrors=[];
const trackDefaults={tracks:8,device:'auto',gpuIndex:-1,fastPng:true,reuse:true,width:2560,sampleInterval:.75,threshold:24,minScene:1.5,maxSegment:8,output:'',naming:'original',namePrefix:'',startNumber:1,digits:3};
const trackDraft=()=>trackOptions||(trackOptions={...trackDefaults,...state.trackSheetOptions});
const trackAll=()=>state.projects.flatMap(p=>p.videos.map(v=>({...v,projectId:p.id,projectName:p.name})));
const trackSelected=()=>trackBatch;
const trackVideos=()=>{const map=new Map(trackAll().map(v=>[v.path,v]));return trackBatch.map(p=>map.get(p)).filter(Boolean);};
function trackSelectionBody(first=false){
 const videos=first?trackVideos().slice(0,1):trackVideos(),fixed={},ids=[];
 for(const v of videos){if(!fixed[v.projectId]){ids.push(v.projectId);fixed[v.projectId]=[];}fixed[v.projectId].push(v.path);}
 return {kind:'jianying_project',ids,sourceVideoPaths:fixed,trackOrder:videos.map(v=>v.path),trackSheet:{...trackDraft()},sheetMode:'batch'};
}
function trackFileRows(){
 const available=trackAll().filter(v=>(v.name+' '+v.projectName).toLowerCase().includes(trackQuery.toLowerCase()));
 const ordered=[...trackBatch.map(p=>available.find(v=>v.path===p)).filter(Boolean),...available.filter(v=>!trackBatch.includes(v.path))];
 if(!ordered.length)return '<div class="track-files-empty">'+icon('folder')+'<strong>添加工程素材</strong><p>选择本机视频，或使用已导入素材。</p></div>';
 return ordered.slice(0,120).map(v=>{const index=trackBatch.indexOf(v.path);return `<div class="track-file ${index>=0?'selected':''}"><label><input type="checkbox" data-track-path="${esc(v.path)}" ${index>=0?'checked':''}><span><strong title="${esc(v.name)}">${esc(v.name)}</strong><small>${esc(v.projectName)} · ${duration(v.duration)}</small></span></label>${index>=0?`<div class="track-file-order"><span>${String(index+1).padStart(2,'0')}</span><button class="icon-button" data-track="up" data-path="${esc(v.path)}" aria-label="上移${esc(v.name)}" ${index===0?'disabled':''}>${icon('trackUp')}</button><button class="icon-button" data-track="down" data-path="${esc(v.path)}" aria-label="下移${esc(v.name)}" ${index===trackBatch.length-1?'disabled':''}>${icon('trackDown')}</button></div>`:''}</div>`;}).join('')+(ordered.length>120?'<p class="field-hint">显示前120个视频，请搜索文件名缩小范围。</p>':'');
}
function tracksPage(){return `<div class="official-project-route">`+intro('剪映工程与截图','用真实素材建立可编辑草稿，在官方应用里核对并采集实际工程界面。')+`<ol class="official-project-steps" aria-label="真实工程流程"><li><span>1</span>选择素材</li><li><span>2</span>建立草稿</li><li><span>3</span>在剪映打开</li><li><span>4</span>采集实际截图</li></ol><div class="track-workbench"><section class="track-sources"><div class="track-section-title"><h2>工程素材</h2><span id="track-selection-count">已选 ${trackVideos().length} 集</span></div><div class="track-import-buttons"><button class="button primary" data-track="pick">${icon('plus')}选择多个视频</button><button class="button" data-track="select-visible">选择当前列表</button><button class="button subtle" data-track="clear">清空</button></div><label class="track-search-label" for="track-query">搜索素材<input id="track-query" placeholder="搜索视频或剧名" value="${esc(trackQuery)}"></label><div id="track-files">${trackFileRows()}</div><details class="track-path-entry"><summary>粘贴本地视频路径</summary><label for="track-paths">每行一个视频文件路径</label><textarea id="track-paths" rows="4" placeholder="D:\\素材\\第1集.mp4"></textarea><button class="button small" data-track="import-paths">读取视频</button></details><p class="track-selection-hint">按已选顺序生成草稿，每批最多30个视频。工程里的画面与原声来自实际素材。</p></section><div class="official-project-editor" id="jy-workspace-host"></div></div><div id="track-validation" role="alert">${trackErrors.map(x=>`<p>${esc(x)}</p>`).join('')}</div></div>`;}
const trackBaseRender=renderPage;
renderPage=function(){document.body.classList.toggle('tracks-route',current==='tracks');if(current!=='tracks')return trackBaseRender();$('#content').innerHTML=tracksPage();$('#breadcrumb').textContent='剪映工程与截图';renderNav();renderTaskbar();};
const trackBaseTaskbar=renderTaskbar;
renderTaskbar=function(){trackBaseTaskbar();const b=$('#start-pipeline');if(!b)return;delete b.dataset.track;delete b.dataset.jianying;if(current!=='tracks')return;delete b.dataset.action;b.dataset.jianying='generate';b.innerHTML=icon('layers')+'生成可编辑草稿';b.disabled=!trackVideos().length&&!(typeof jianyingSource!=='undefined'&&jianyingSource!=='original'&&activeProject());$('#task-title').textContent='剪映工程与截图';$('#task-detail').textContent=`已选 ${trackVideos().length} 个视频 · 草稿需在剪映实际打开后采集截图`;};
function trackUpdateSelection(){if($('#track-files'))$('#track-files').innerHTML=trackFileRows();if($('#track-selection-count'))$('#track-selection-count').textContent=`已选 ${trackVideos().length} 集`;renderTaskbar();}
async function trackImport(paths){if(!paths.length)return;const chosen=[...trackBatch],normalized=[...new Set(paths.map(p=>p.trim().replace(/^"|"$/g,'')).filter(Boolean))];if(normalized.length>30||new Set([...chosen,...normalized]).size>30)throw Error('每批最多30集，请先清空部分选择');const result=await api('tracks/import',{paths:normalized});await refresh();trackBatch=[...new Set([...chosen,...result.videos.map(v=>v.path)])];trackErrors=[];renderPage();}
document.addEventListener('input',e=>{if(e.target.id==='track-query'){trackQuery=e.target.value;if($('#track-files'))$('#track-files').innerHTML=trackFileRows();}});
document.addEventListener('change',e=>{const el=e.target;if(el.dataset.trackPath){const path=el.dataset.trackPath;if(el.checked){if(trackBatch.length>=30){el.checked=false;toast('每批最多30集',true);return;}trackBatch.push(path);}else trackBatch=trackBatch.filter(p=>p!==path);trackUpdateSelection();}});
document.addEventListener('click',async e=>{const b=e.target.closest('[data-track]');if(!b||b.disabled)return;b.disabled=true;try{const action=b.dataset.track;
 if(action==='pick'){const r=await api('browse',{mode:'videos',multiple:true});await trackImport(r.paths||[]);}
 else if(action==='import-paths')await trackImport($('#track-paths').value.split(/\r?\n/));
 else if(action==='clear'){trackBatch=[];trackUpdateSelection();}
 else if(action==='select-visible'){const rows=trackAll().filter(v=>(v.name+' '+v.projectName).toLowerCase().includes(trackQuery.toLowerCase())),paths=[...new Set([...trackBatch,...rows.map(v=>v.path)])];if(paths.length>30)throw Error('当前列表超过30集，请搜索或逐集勾选');trackBatch=paths;trackUpdateSelection();}
 else if(action==='up'||action==='down'){const i=trackBatch.indexOf(b.dataset.path),j=i+(action==='up'?-1:1);if(i>=0&&j>=0&&j<trackBatch.length)[trackBatch[i],trackBatch[j]]=[trackBatch[j],trackBatch[i]];trackUpdateSelection();}
 }catch(error){trackErrors=[error.message];const box=$('#track-validation');if(box)box.innerHTML=`<p>${esc(error.message)}</p>`;toast(error.message,true);}finally{if(b.isConnected)b.disabled=false;}});
