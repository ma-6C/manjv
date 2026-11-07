'use strict';
// This sidebar entry launches the app directly and leaves the current work open.
(()=>{
pages.push(['xiaovmiao','小v喵','cat']);
shapes.cat='M4 10V3l6 4h4l6-4v7a8 8 0 0 1-16 0ZM8 12h.01M16 12h.01M10 16h4M1 12l4 1m14 0 4-1M1 17l4-1m14 0 4 1';
let opening=false;
const basePageFromHash=pageFromHash;
pageFromHash=function(){
 if(location.hash==='#xiaovmiao'){history.replaceState(null,'','#scan');return 'scan';}
 return basePageFromHash();
};
const baseRenderNav=renderNav;
renderNav=function(){
 baseRenderNav();
 const link=$('#nav a[href="#xiaovmiao"]');
 if(link){link.title='打开小v喵';link.setAttribute('aria-label','打开小v喵');}
};
document.addEventListener('click',async event=>{
 const link=event.target.closest('#nav a[href="#xiaovmiao"]');
 if(!link)return;
 event.preventDefault();event.stopImmediatePropagation();
 if(opening)return;
 opening=true;link.setAttribute('aria-busy','true');link.setAttribute('aria-disabled','true');
 const label=link.querySelector('span');if(label)label.textContent='正在打开…';
 try{const result=await api('xiaovmiao/open',{});toast(result.message);}
 catch(error){toast(error.message,true);}
 finally{
  opening=false;
  const currentLink=$('#nav a[href="#xiaovmiao"]');
  if(currentLink){currentLink.removeAttribute('aria-busy');currentLink.removeAttribute('aria-disabled');const text=currentLink.querySelector('span');if(text)text.textContent='小v喵';}
 }
},true);
})();
