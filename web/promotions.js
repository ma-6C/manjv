'use strict';
pages.splice(pages.findIndex(p=>p[0]==='publish'),0,['promotion','推广挂载','link']);
Object.assign(jobLabels,{hook:'制作推广钩子',promotion_package:'导出推广挂载任务'});

const promoDrafts=new Map();
let promotionPage;

function promoDraft(){
 const project=activeProject();
 if(!project)return {};
 if(!promoDrafts.has(project.id)){
  promoDrafts.set(project.id,{sourceKind:'original',videoIndex:0,start:0,
   seconds:Math.min(30,project.videos[0]?.duration||30),title:project.name+' · 高光钩子',cta:'点击下方入口看全集'});
 }
 return promoDrafts.get(project.id);
}

function promoField(label,key,opts={}){const d=promoDraft(),id='promo-'+key;return `<div class="field"><label for="${id}">${label}</label>${opts.textarea?`<textarea id="${id}" rows="2" data-promo-field="${key}">${esc(d[key]||'')}</textarea>`:`<input id="${id}" data-promo-field="${key}" type="${opts.type||'text'}" value="${esc(d[key]??'')}" ${opts.min!==undefined?`min="${opts.min}"`:''} ${opts.max!==undefined?`max="${opts.max}"`:''} ${opts.step?`step="${opts.step}"`:''} placeholder="${esc(opts.placeholder||'')}">`}${opts.hint?`<p class="field-hint">${opts.hint}</p>`:''}</div>`;}
function promoHookCard(){const p=activeProject(),d=promoDraft(),inputs=d.sourceKind==='original'?p.videos:(d.inputVideos||[]),v=inputs[d.videoIndex]||inputs[0];return card('制作剧情钩子','spark',`<p class="section-description">选择原片、去字幕结果或当前成片，预览后设置冲突或悬念的起止位置。保留选段音轨，在结尾叠加引导文字。</p><div class="field"><label for="promo-sourceKind">输入版本</label><select id="promo-sourceKind" data-promo-field="sourceKind">${[['original','原始素材'],['subtitle','去字幕结果'],['final','当前成片']].map(([k,n])=>`<option value="${k}" ${d.sourceKind===k?'selected':''}>${n}</option>`).join('')}</select></div><div class="field"><label for="promo-videoIndex">选择该版本视频</label><select id="promo-videoIndex" data-promo-field="videoIndex">${inputs.map((v,i)=>`<option value="${i}" ${i===Number(d.videoIndex)?'selected':''}>${esc(v.name)} · ${duration(v.duration)}</option>`).join('')}</select></div><video class="promo-video" id="promo-source" controls preload="metadata" src="${v?media(v.path):''}"></video><div class="actions-row"><button class="button small" data-promo="mark-start">当前时间设为起点</button><button class="button small" data-promo="mark-end">当前时间设为终点</button></div><div class="grid-2">${promoField('选段起点（秒）','start',{type:'number',min:0,max:v?.duration||0,step:.1})}${promoField('选段时长（秒，最长180）','seconds',{type:'number',min:1,max:180,step:.1})}</div>${promoField('钩子标题／素材备注','title',{placeholder:'例如：身份揭晓前一秒'})}${promoField('最后2秒引导文字（可留空）','cta',{hint:'字幕引导文字不会创建平台挂载入口，发布时仍需关联剧集。'})}<label class="check-label"><input id="promo-rights" type="checkbox" ${p.rights?'checked':''}>确认拥有这部剧的剪辑与推广授权</label><div class="actions-row"><button class="button primary" data-promo="hook" ${!v?'disabled':''}>${icon('film')}制作钩子视频</button></div>`);}
const promotionBaseRender=renderPage;renderPage=function(){if(current!=='promotion'||typeof promotionPage!=='function')return promotionBaseRender();$$('#content video').forEach(v=>v.pause());$('#content').innerHTML=promotionPage();$('#breadcrumb').textContent='推广挂载';renderNav();renderTaskbar();};
document.addEventListener('input',e=>{if(e.target.dataset.promoField){const key=e.target.dataset.promoField;promoDraft()[key]=['start','seconds','videoIndex'].includes(key)?Number(e.target.value):e.target.value;}});

document.addEventListener('change',async e=>{
 const input=e.target,field=input.dataset.promoField;
 if(!field&&input.id!=='promo-rights')return;
 try{
  const project=activeProject();
  if(!project)return;
  if(input.id==='promo-rights'){
   await api('project',{id:project.id,rights:input.checked});
   await refresh();
   return;
  }
  const draft=promoDraft();
  draft[field]=['start','seconds','videoIndex'].includes(field)?Number(input.value):input.value;
  if(field==='sourceKind'){
   draft.inputVideos=[];draft.videoIndex=0;renderPage();
   const result=await api('promotion/inputs',{projectId:project.id,sourceKind:draft.sourceKind});
   draft.inputVideos=result.videos;
   draft.start=0;draft.seconds=Math.min(30,result.videos[0]?.duration||30);
   if(activeProject()?.id===project.id){
    renderPage();
    if(!result.videos.length)toast('此版本暂无视频，请先完成对应制作');
   }
  }else if(field==='videoIndex'){
   const videos=draft.sourceKind==='original'?project.videos:draft.inputVideos||[];
   draft.start=0;draft.seconds=Math.min(30,videos[draft.videoIndex]?.duration||30);
   renderPage();
  }
 }catch(error){toast(error.message,true);}
});

document.addEventListener('click',async e=>{
 const button=e.target.closest('[data-promo]');
 if(!button||button.disabled)return;
 const project=activeProject();
 if(!project)return;
 const draft=promoDraft(),action=button.dataset.promo;
 if(action==='mark-start'||action==='mark-end'){
  const time=$('#promo-source').currentTime||0;
  if(action==='mark-start')draft.start=Number(time.toFixed(2));
  else draft.seconds=Math.max(1,Number((time-Number(draft.start)).toFixed(2)));
  $('#promo-start').value=draft.start;
  $('#promo-seconds').value=draft.seconds;
  return;
 }
 if(action!=='hook')return;
 button.disabled=true;
 try{
  const videos=draft.sourceKind==='original'?project.videos:draft.inputVideos||[];
  const request={kind:'hook',ids:[project.id],videoIndex:Number(draft.videoIndex),sourceKind:draft.sourceKind,
   sourcePath:videos[draft.videoIndex]?.path,start:Number(draft.start),seconds:Number(draft.seconds),title:draft.title,cta:draft.cta};
  await api('project',{id:project.id,rights:$('#promo-rights').checked});
  await api('jobs',request);
  await refresh();
  toast('钩子已加入制作队列，完成后可选择生成素材');
 }catch(error){toast(error.message,true);}
 finally{if(button.isConnected)button.disabled=false;}
});

const promoRefresh=refresh;
let promoJobSignature='';
refresh=async function(render=false){
 await promoRefresh(render);
 if(current!=='promotion')return;
 const jobs=(state.jobs||[]).filter(job=>job.kind==='hook');
 const signature=jobs.map(job=>job.id+':'+job.status).join(',');
 if(promoJobSignature!==signature){
  promoJobSignature=signature;
  if(jobs.some(job=>job.status==='completed')&&!$('dialog[open]'))renderPage();
 }
};
