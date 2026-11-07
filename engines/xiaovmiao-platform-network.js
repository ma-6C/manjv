'use strict';
// Restore ordinary browsing only for platform webviews. The app's main session
// and its existing backend/cloud restrictions remain outside this policy.
function install({app,log=()=>{}}){
 const guests=new WeakSet();
 app.on('web-contents-created',(_event,contents)=>{
  if(contents.getType()!=='webview')return;
  guests.add(contents.session);
  log({event:'platform-webview-created'});
  const hostname=url=>{try{return new URL(url).hostname;}catch(_){return '';}};
  contents.on('did-finish-load',()=>log({event:'platform-page-loaded',host:hostname(contents.getURL())}));
  contents.on('did-fail-load',(_event,code,_description,url,isMainFrame)=>{
   if(isMainFrame&&code!==-3)log({event:'platform-page-failed',host:hostname(url),code});
  });
 });
 return {canRequest(session,url,details={}){
  if(guests.has(session)&&/^(https?|wss?):/i.test(url))return true;
  try{
   const u=new URL(url);
   if(u.protocol!=='https:')return false;
   if(u.hostname==='creator.douyin.com'&&u.pathname==='/web/api/media/user/info/')return true;
   return details.resourceType==='image'&&['douyinpic.com','byteimg.com','pstatp.com'].some(d=>u.hostname===d||u.hostname.endsWith('.'+d));
  }catch(_){return false;}
 }};
}

// An isolated public-page load check: no existing cookies, no account sign-in,
// and no interaction with the user's currently running application.
function smoke(){
 const {app,BrowserWindow}=require('electron'),fs=require('node:fs'),path=require('node:path');
 const profile=process.env.MANJU_XIAOVMIAO_PROFILE;
 const output=process.env.MANJU_XIAOVMIAO_NETWORK_REPORT;
 if(!profile||!output)throw Error('Missing isolated network-check paths');
 fs.mkdirSync(profile,{recursive:true});app.setPath('userData',profile);
 const events=[];const policy=install({app,log:event=>events.push(event)});
 app.on('session-created',session=>session.webRequest.onBeforeRequest((details,callback)=>{
  const remote=/^(https?|wss?|ftp):/i.test(details.url),allow=policy.canRequest(session,details.url);
  if(remote&&details.resourceType==='mainFrame')events.push({event:'page-request',host:new URL(details.url).hostname,allow});
  callback({cancel:remote&&!allow});
 }));
 let timer,window,finished=false,poll;
 const finish=value=>{
  if(finished)return;finished=true;
  fs.writeFileSync(output,JSON.stringify({...value,events},null,2));
  if(timer)clearTimeout(timer);if(poll)clearInterval(poll);app.exit(value.ok?0:1);
 };
 app.on('web-contents-created',(_event,contents)=>{
  events.push({event:'contents-created',type:contents.getType()});
  if(contents.getType()!=='webview')return;
  contents.debugger.attach('1.3');
  contents.on('dom-ready',()=>events.push({event:'guest-dom-ready',host:new URL(contents.getURL()).hostname}));
  // Analytics and streaming resources can keep 'did-finish-load' pending even
  // when the creator page is already visible; inspect the rendered public DOM.
  poll=setInterval(async()=>{
   if(finished||contents.isDestroyed())return;
   try{
    const evaluated=await contents.debugger.sendCommand('Runtime.evaluate',{expression:'({textLength:document.body?.innerText?.trim().length||0,loadedImages:[...document.images].filter(x=>x.complete&&x.naturalWidth>0).length})',returnByValue:true});
    const dom=evaluated.result.value;if(!dom) return;
    if(dom.textLength<80)return;
    const screenshot=output.replace(/\.json$/,'.png');
    fs.writeFileSync(screenshot,(await contents.capturePage()).toPNG());
    finish({ok:true,host:new URL(contents.getURL()).hostname,guestType:contents.getType(),existingProfileUsed:false,dom,screenshot});
   }catch(_){}
  },1000);
  contents.on('did-fail-load',(_event,code,description,url,isMainFrame)=>{
   if(isMainFrame&&code!==-3)finish({ok:false,code,description,host:(()=>{try{return new URL(url).hostname;}catch(_){return '';}})()});
  });
 });
 app.whenReady().then(async()=>{
  window=new BrowserWindow({show:false,webPreferences:{webviewTag:true,backgroundThrottling:false,contextIsolation:true,nodeIntegration:false}});
  window.webContents.on('console-message',(_event,_level,message)=>events.push({event:'host-console',message:String(message).slice(0,240)}));
  timer=setTimeout(()=>finish({ok:false,error:'Public page load timed out'}),45000);
  const target='https://creator.douyin.com/';
  const html='<html><body><webview style="width:1200px;height:800px" partition="xvm-network-check" src="'+target+'"></webview></body></html>';
  const htmlPath=path.join(profile,'network-check.html');fs.writeFileSync(htmlPath,html);
  await window.loadFile(htmlPath);
  events.push({event:'host-loaded',guestTag:await window.webContents.executeJavaScript('!!document.querySelector("webview")')});
 }).catch(error=>finish({ok:false,error:error.message}));
}
module.exports={install,smoke};
