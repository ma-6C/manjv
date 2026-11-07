'use strict';

const PROFILE_URL='https://creator.douyin.com/web/api/media/user/info/';
const own=o=>o&&typeof o==='object'&&!Array.isArray(o);
function explainFeatureError(error,method,hasSoftwareUser){
 if(!hasSoftwareUser&&typeof method==='string'&&method.startsWith('CommentManager.')&&
    error?.name==='TypeError'&&/Cannot read properties of null \(reading ['"]is_vip['"]\)/.test(error.message||'')){
  const message='评论功能尚未连接：当前本地模式没有小v猫软件账号的有效登录信息。抖音账号与小v猫软件账号是分别登录的；可先在账号管理中打开抖音创作者中心处理评论。';
  const result=new Error(message);result.code='LOCAL_SOFTWARE_LOGIN_REQUIRED';return result;
 }
 return error;
}
function allowsProfileRequest(input){
 try{const url=new URL(typeof input==='string'?input:input?.url);return url.protocol==='https:'&&url.hostname==='creator.douyin.com'&&url.pathname==='/web/api/media/user/info/';}catch(_){return false;}
}
function normalizeProfile(body){
 if(!own(body))return null;
 const status=body.status_code??body.code;
 if(status!==undefined&&status!==0&&status!=='0')return null;
 const candidates=[body.user_info,body.user,body.data?.user_info,body.data?.user,body.data,body];
 for(const user of candidates){
  if(!own(user))continue;
  const raw=user.uid??user.user_id;
  if(typeof raw==='number'&&!Number.isSafeInteger(raw))continue;
  const uid=String(raw??'');const nickname=user.nickname??user.nick_name;
  if(!/^\d{5,30}$/.test(uid)||typeof nickname!=='string'||!nickname.trim())continue;
  const avatar=user.avatar_url??user.avatar?.url_list?.[0]??user.avatar_thumb?.url_list?.[0]??user.avatar;
  return {uid,platform:'Douyin',nickname:nickname.trim().slice(0,200),
   avatar:typeof avatar==='string'&&/^https:\/\//.test(avatar)?avatar:'',
   originData:{uid,nickname:nickname.trim().slice(0,200)}};
 }
 return null;
}

function createRegistry(runtime,{fs,path,log=()=>{}}){
 const model=runtime.Models.Account,manager=runtime.AccountManager;
 let writes=Promise.resolve(),backupDone=false;
 function plain(row){return typeof row?.get==='function'?row.get({plain:true}):row;}
 function snapshot(row){const item=plain(row);return {...item,accountInfo:item,isLogin:!!item.isLogin};}
 async function load(){
  const rows=await model.findAll({order:[['order','ASC'],['id','ASC']]});
  if(!Array.isArray(manager.allAccounts))throw Error('本地账号列表结构不兼容，已保留数据库');
  for(const record of rows){
   const row=plain(record);
   let worker=manager.allAccounts.find(w=>w.platform===row.platform&&w.partition===row.partition);
   if(!worker){worker=await manager.newWorker(row.platform,row.partition);manager.allAccounts.push(worker);}
   // Use persisted, factual fields. Native initFromDb also assumes cloud proxy
   // configuration, which this isolated local edition does not initialize.
   Object.assign(worker,{accountInfo:row,uid:row.uid,nickname:row.nickname,avatar:row.avatar,
    partition:row.partition,_isLogin:!!row.isLogin});
  }
  return {localAccountCount:rows.length};
 }
 async function list(){await load();return (await model.findAll({order:[['order','ASC'],['id','ASC']]})).map(snapshot);}
 async function find(uid,platform){
  if(typeof uid!=='string'||typeof platform!=='string')throw Error('账号标识无效');
  const row=await model.findOne({where:{uid,platform}});return row?{uid:row.uid,platform:row.platform}:null;
 }
 async function backup(){
  if(backupDone)return;
  const storage=model.sequelize.options.storage;
  if(typeof storage!=='string'||storage===':memory:')throw Error('无法确定本地数据库备份位置');
  const folder=path.join(path.dirname(storage),'manju-backups');fs.mkdirSync(folder,{recursive:true});
  const file=path.join(folder,'before-account-save-'+Date.now()+'.db');
  await model.sequelize.query('VACUUM INTO $backup',{bind:{backup:file}});
  backupDone=true;log({event:'local-account-backup-ready'});
 }
 function save(profile,partition,options={}){
  if(!profile||profile.platform!=='Douyin'||!/^\d{5,30}$/.test(profile.uid)||!profile.nickname)throw Error('尚未识别到有效抖音账号，不能保存');
  if(typeof partition!=='string'||!partition.startsWith('persist:')||partition.length>512)throw Error('抖音登录会话分区无效');
  const run=async()=>{
   await backup();
   const byUid=await model.findOne({where:{platform:'Douyin',uid:profile.uid}});
   const byPartition=await model.findOne({where:{platform:'Douyin',partition}});
   if(byUid&&byPartition&&byUid.id!==byPartition.id)throw Error('此登录分区已绑定另一条账号记录，请在账号列表中核对');
   const existing=byUid||byPartition;
   if(existing&&existing.uid!==profile.uid&&!String(existing.uid).startsWith('laterLogin_'))throw Error('当前登录与已有账号不同，请使用添加账号建立独立会话');
   const values={...profile,partition,isLogin:true,isLoginFront:true,lastLogin:new Date(),
    groupId:existing?.groupId??(Number.isInteger(options.groupId)?options.groupId:0),
    order:existing?.order??(Number.isInteger(options.order)?options.order:(await model.count())+1)};
   const row=existing?await existing.update(values):await model.create(values);
   await load();manager.emit('reloadAccounts');
   log({event:'local-account-saved',platform:'Douyin',created:!existing});
   return snapshot(row);
  };
  const pending=writes.then(run,run);writes=pending.catch(()=>{});return pending;
 }
 function loginState(partition,value){
  const run=async()=>{
   const row=await model.findOne({where:{platform:'Douyin',partition}});
   if(row&&Boolean(row.isLogin)!==value){await row.update({isLogin:value,isLoginFront:value});await load();manager.emit('reloadAccounts');}
  };
  const pending=writes.then(run,run);writes=pending.catch(()=>{});return pending;
 }
 return {load,list,find,save,backup,loginState};
}

function install({app,session,webContents,fs,path,ready,log=()=>{}}){
 const watches=new Map(),verified=new Map();let registryPromise,recoveryPromise;
 const registry=()=>registryPromise||(registryPromise=Promise.resolve().then(ready).then(runtime=>createRegistry(runtime,{fs,path,log})));
 async function readProfile(ses,userAgent){
  const cookies=await ses.cookies.get({url:PROFILE_URL});
  if(!cookies.some(c=>['sessionid','sessionid_ss','sid_guard','sid_tt'].includes(c.name)&&!!c.value))return {state:'waiting_login'};
  const headers={Cookie:cookies.map(cookie=>cookie.name+'='+cookie.value).join('; '),Referer:'https://creator.douyin.com/'};
  if(userAgent)headers['User-Agent']=userAgent;
  const response=await ses.fetch(PROFILE_URL,{credentials:'include',cache:'no-store',redirect:'error',headers,signal:AbortSignal.timeout(10000)});
  if(!response.ok)return {state:'http_error',status:response.status};
  const text=await response.text();if(text.length>2*1024*1024)throw Error('账号资料响应过大');
  const body=JSON.parse(text.replace(/("(?:uid|user_id)"\s*:\s*)(\d{16,})(?=\s*[,}])/g,'$1"$2"'));
  const profile=normalizeProfile(body);
  if(profile)return {state:'identified',profile};
  const status=body?.status_code??body?.code;
  if(status!==undefined&&status!==0&&status!=='0')return {state:'not_authenticated'};
  log({event:'local-profile-schema-unrecognized',keys:Object.keys(body||{}).slice(0,12)});
  return {state:'unsupported_profile'};
 }
 function recoverExisting(){
  return recoveryPromise||(recoveryPromise=(async()=>{
   const runtime=await ready(),store=await registry();
   if(await runtime.Models.Account.count())return;
   const storage=runtime.Models.Account.sequelize.options.storage;
   const marker=path.join(path.dirname(storage),'manju-session-recovery-v1.json');
   if(fs.existsSync(marker))return;
   const partitions=path.join(app.getPath('userData'),'Partitions');
   if(!fs.existsSync(partitions))return;
   let recovered=0,failed=false,candidates=0;
   for(const item of fs.readdirSync(partitions,{withFileTypes:true})){
    if(!item.isDirectory()||!/^[-A-Za-z0-9_.]{1,128}$/.test(item.name))continue;
    const folder=path.join(partitions,item.name);if(fs.lstatSync(folder).isSymbolicLink())continue;
    if(!fs.existsSync(path.join(folder,'Network','Cookies'))&&!fs.existsSync(path.join(folder,'Cookies')))continue;
    const partition='persist:'+item.name,ses=session.fromPartition(partition);
    if(path.resolve(ses.getStoragePath()).toLowerCase()!==path.resolve(folder).toLowerCase())continue;
    candidates++;
    try{
     const result=await readProfile(ses,ses.getUserAgent());
     if(result.state==='identified'){
      const exists=await store.find(result.profile.uid,'Douyin');
      if(!exists){await store.save(result.profile,partition,{groupId:0});recovered++;}
     }else if(result.state==='unsupported_profile'||result.state==='http_error'&&result.status!==401&&result.status!==403)failed=true;
    }catch(_){failed=true;}
   }
   if(!failed)fs.writeFileSync(marker,JSON.stringify({completed:true,recovered,at:new Date().toISOString()}));
   log({event:'local-existing-session-recovery',candidates,recovered,retryNeeded:failed});
  })());
 }
 function report(watch,stage,message){
  if(watch.stage===stage)return;watch.stage=stage;
  log({event:'local-account-status',platform:'Douyin',stage});
  const owner=watch.owner;if(!owner||owner.isDestroyed())return;
  const payload=JSON.stringify({partition:watch.partition,message,stage});
  const script=`(()=>{const s=${payload};const v=[...document.querySelectorAll('webview')].find(e=>e.getAttribute('partition')===s.partition);if(!v)return;const parent=v.parentElement;if(!parent)return;let el=parent.querySelector('[data-manju-account-status]');if(!el){el=document.createElement('div');el.dataset.manjuAccountStatus='1';el.setAttribute('role','status');el.setAttribute('aria-live','polite');el.style.cssText='padding:8px 12px;background:#fff7e6;border:1px solid #ffe0a3;color:#874d00;line-height:1.7;white-space:normal';parent.insertBefore(el,v);}el.textContent=s.message;})()`;
  void owner.executeJavaScript(script).catch(()=>{});
 }
 async function tick(watch){
  if(watch.busy||watch.stopped)return;watch.busy=true;
  try{
   const ses=session.fromPartition(watch.partition);
   const guest=webContents.getAllWebContents().find(c=>!c.isDestroyed()&&c.getType()==='webview'&&c.session===ses);
   if(!guest||!/^https:\/\/creator\.douyin\.com(?:\/|$)/i.test(guest.getURL()))return;
   if(!watch.emittedUid)report(watch,'recognizing','正在检查抖音登录会话与账号资料…');
   const result=await readProfile(ses,guest.getUserAgent());
   if(result.state==='waiting_login'){await(await registry()).loginState(watch.partition,false);report(watch,'waiting_login','等待完成抖音登录；尚未检测到抖音登录会话。');return;}
   if(result.state==='http_error'){if(result.status===401||result.status===403)await(await registry()).loginState(watch.partition,false);report(watch,'http_error','抖音账号资料读取失败（HTTP '+result.status+'），登录会话已保留。');return;}
   if(result.state==='unsupported_profile'){report(watch,'unsupported_profile','抖音返回了账号资料，但格式暂未识别；登录会话已保留。');return;}
   if(result.state!=='identified'){await(await registry()).loginState(watch.partition,false);report(watch,'not_authenticated','抖音尚未返回有效账号资料；请确认当前页面已进入你的创作者中心。');return;}
   const profile=result.profile;
   verified.set(watch.partition,{profile,at:Date.now()});
   if(watch.emittedUid===profile.uid&&Date.now()-watch.emittedAt<30000)return;
   watch.emittedUid=profile.uid;watch.emittedAt=Date.now();
   await ses.cookies.flushStore();
   const runtime=await ready();const store=await registry();
   const existing=await runtime.Models.Account.findOne({where:{platform:'Douyin',partition:watch.partition}});
   let account={...profile,partition:watch.partition,isLogin:true,accountInfo:profile};
   if(existing){account=await store.save(profile,watch.partition,{groupId:existing.groupId});report(watch,'saved','抖音账号已识别并保存，可在左侧分组中查看。');}
   else report(watch,'identified','已识别抖音账号，正在加入本地账号列表…');
   runtime.AccountManager.emit('webview:'+watch.partition,account);
  }catch(error){
   report(watch,'failed','账号识别未完成：'+String(error.message).slice(0,160));
   log({event:'local-account-recognition-error',platform:'Douyin',kind:error.name||'Error'});
  }finally{watch.busy=false;}
 }
 function listen(spec,owner){
  if(!spec||spec.platform!=='Douyin'||typeof spec.partition!=='string'||!spec.partition.startsWith('persist:'))return;
  stop(spec.partition);const watch={partition:spec.partition,owner,stage:'',busy:false,stopped:false};watches.set(spec.partition,watch);
  watch.timer=setInterval(()=>void tick(watch),2500);void tick(watch);
 }
 function stop(partition){const watch=watches.get(partition);if(watch){watch.stopped=true;clearInterval(watch.timer);watches.delete(partition);}}
 async function call(method,args){
  const store=await registry();
  if(method==='LocalAccounts.find')return store.find(args[0],args[1]);
  if(method==='LocalAccounts.add'){
   const input=args[0],match=verified.get(input?.partition);
   if(!match||Date.now()-match.at>300000||match.profile.uid!==input?.uid)throw Error('尚未取得当前会话的抖音账号资料，请在创作者中心完成登录后重试');
   const saved=await store.save(match.profile,input.partition,args[1]);
   const watch=watches.get(input.partition);if(watch)report(watch,'saved','账号已保存到本地，可在左侧分组中查看。');
   return saved;
  }
  if(method==='LocalAccounts.list')return store.list();
  if(method==='LocalAccounts.load'){await recoverExisting();return store.load();}
  if(method==='LocalAccounts.proxies'){
   const runtime=await ready(),model=runtime.Models.LocalProxy||runtime.Models.Proxy;
   return model?(await model.findAll()).map(row=>row.get({plain:true})):[];
  }
  if(method==='LocalAccounts.owners')return [];
  throw Error('不支持的本地账号操作');
 }
 app.on('before-quit',()=>{for(const key of watches.keys())stop(key);});
 return {listen,stop,call,registry,verified,recoverExisting};
}
module.exports={normalizeProfile,createRegistry,install,allowsProfileRequest,PROFILE_URL,explainFeatureError};
