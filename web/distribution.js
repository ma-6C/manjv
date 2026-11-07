'use strict';
pages.push(['license','本地组件','cpu']);
function licensePage(){
 return intro('本地组件','按需安装本地 AI 字幕修复引擎。')+card('可选离线 AI 引擎','cpu','<p class="section-description">选择软件提供方随安装包提供的 AI 引擎 ZIP。导入时会校验签名和全部文件，需要约 8 GB 可用空间。无需另外安装 Python。</p><div class="actions-row"><button class="button primary" data-distribution="engine">导入离线 AI 引擎包</button></div><p id="component-info" role="status" aria-live="polite">正在读取组件状态…</p>');
}
const baseRenderPage=renderPage;
renderPage=function(){
 if(current!=='license')return baseRenderPage();
 $('#content').innerHTML=licensePage();$('#breadcrumb').textContent='本地组件';
 renderNav();renderTaskbar();loadDistribution();
};
async function loadDistribution(){
 try{
  const c=await api('component'),info=$('#component-info');if(!info)return;
  info.textContent=(c.active.id?'已安装：'+c.active.id+'。':'尚未安装离线 AI 引擎。')+' '+(c.progress.message||'')+(['verifying','installing'].includes(c.progress.status)?' '+c.progress.percent+'%':'');
  if(c.progress.status==='completed')await refresh();
 }catch(e){toast(e.message,true);}
}
document.addEventListener('click',async e=>{
 const b=e.target.closest('[data-distribution="engine"]');if(!b)return;b.disabled=true;
 try{
  const r=await api('browse',{mode:'engine'});
  if(r.path){await api('component/import',{path:r.path});toast('开始校验并导入 AI 组件，请保留窗口。');await loadDistribution();}
 }catch(error){toast(error.message,true);}finally{b.disabled=false;}
});
setInterval(()=>{if(current==='license')loadDistribution();},2200);
