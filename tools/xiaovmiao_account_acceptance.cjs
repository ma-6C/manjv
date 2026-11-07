'use strict';
const assert=require('node:assert/strict');
const SAMPLE_UID='9000000000000000001',SAMPLE_NAME='测试示例（非真实账号）',PARTITION='persist:manju-local-account-test';
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function run({runtime,bridge,app,fs,path,output}){
 const report={fixture:true,realAccountUsed:false,checks:[]};
 let host,main;
 try{
  const root=path.resolve(process.env.MANJU_XIAOVMIAO_ACCOUNT_TEST_ROOT||'');
  const profile=path.resolve(process.env.MANJU_XIAOVMIAO_PROFILE||'');
  if(!process.env.MANJU_XIAOVMIAO_ACCOUNT_TEST_ROOT||!profile.startsWith(root+path.sep))throw Error('Account acceptance requires an isolated test profile');
  const phase=process.env.MANJU_XIAOVMIAO_ACCOUNT_TEST_PHASE||'save';
  const recoveryMarker=path.join(path.dirname(runtime.Models.Account.sequelize.options.storage),'manju-session-recovery-v1.json');
  if(phase!=='recover')fs.writeFileSync(recoveryMarker,JSON.stringify({completed:true,fixture:true}));
  const {session,BrowserWindow}=require('electron');
  const ses=session.fromPartition(PARTITION);
  await ses.protocol.handle('https',request=>{
   const url=new URL(request.url);
   if(url.hostname!=='creator.douyin.com')return new Response('',{status:403});
   if(url.pathname==='/web/api/media/user/info/'){
    const requestHasSession=Boolean(request.headers.get('cookie')?.includes('sessionid='));
    report.sessionCookieSent=!!report.sessionCookieSent||requestHasSession;
    if(!requestHasSession)return new Response('',{status:401});
    return new Response(JSON.stringify({status_code:0,user_info:{uid:SAMPLE_UID,nickname:SAMPLE_NAME,avatar_url:''}}),{headers:{'content-type':'application/json'}});
   }
   return new Response('<html><body>Isolated platform fixture. No real account.</body></html>',{headers:{'content-type':'text/html'}});
  });
  const windows=BrowserWindow.getAllWindows();main=windows[0];
  if(!main)throw Error('Missing app window');
  const call=(method,...args)=>main.webContents.executeJavaScript('window.CatBridge.getCall('+[method,...args].map(v=>JSON.stringify(v)).join(',')+')');
  if(phase==='prepare_recovery'){
   assert.equal(await runtime.Models.Account.count(),0);
   await ses.cookies.set({url:'https://creator.douyin.com/',name:'sessionid',value:'isolated-test-session-not-a-real-token',expirationDate:Date.now()/1000+3600,httpOnly:true,secure:true});
   await ses.cookies.flushStore();fs.unlinkSync(recoveryMarker);
   report.ok=true;report.phase=phase;report.checks.push('existing_authenticated_session_fixture_prepared_without_account_record');
   fs.writeFileSync(output,JSON.stringify(report,null,2));app.exit(0);return;
  }
  if(phase==='recover'){
   await bridge.recoverExisting();assert.equal(await runtime.Models.Account.count(),1);
   assert.equal(report.sessionCookieSent,true);report.checks.push('existing_session_recovered_without_new_login');
  }
  if(phase==='save'){
   assert.equal(await runtime.Models.Account.count(),0);
   await assert.rejects(call('LocalAccounts.add',{uid:SAMPLE_UID,platform:'Douyin',partition:PARTITION},{groupId:0}),/尚未取得/);
   assert.equal(await runtime.Models.Account.count(),0);report.checks.push('unverified_client_account_is_not_saved');
   await ses.cookies.set({url:'https://creator.douyin.com/',name:'sessionid',value:'isolated-test-session-not-a-real-token',expirationDate:Date.now()/1000+3600,httpOnly:true,secure:true});
   await ses.cookies.flushStore();
   host=new BrowserWindow({show:false,webPreferences:{webviewTag:true,contextIsolation:true,backgroundThrottling:false}});
   const fixtureFile=path.join(profile,'fixture-host.html');
   fs.writeFileSync(fixtureFile,'<html><body><webview partition="'+PARTITION+'" src="https://creator.douyin.com/" style="width:1100px;height:760px"></webview></body></html>');
   const recognized=new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>reject(Error('Account profile was not recognized')),15000);
    runtime.AccountManager.once('webview:'+PARTITION,account=>{clearTimeout(timeout);resolve(account);});
   });
   await host.loadFile(fixtureFile);bridge.listen({platform:'Douyin',partition:PARTITION},main.webContents);
   const account=await recognized;
   assert.equal(account.uid,SAMPLE_UID);assert.equal(account.nickname,SAMPLE_NAME);
   assert.equal(report.sessionCookieSent,true);report.checks.push('official_profile_request_uses_same_session_cookie');
   assert.equal(await call('LocalAccounts.find',SAMPLE_UID,'Douyin'),null);
   await call('LocalAccounts.add',account,{groupId:0,order:1});
   assert.equal(await runtime.Models.Account.count(),1);report.checks.push('verified_profile_saved_to_real_sqlite');
   await call('LocalAccounts.add',account,{groupId:0,order:1});
   assert.equal(await runtime.Models.Account.count(),1);report.checks.push('duplicate_registration_is_idempotent');
   const store=await bridge.registry();await store.loginState(PARTITION,false);
   assert.equal((await store.list())[0].isLogin,false);assert.equal(await runtime.Models.Account.count(),1);
   report.checks.push('expired_login_keeps_account_record');
   await call('LocalAccounts.add',account,{groupId:0,order:1});
   bridge.stop(PARTITION);
  }else{
   assert.equal(await runtime.Models.Account.count(),1);report.checks.push('account_survived_process_restart');
  }
  await call('LocalAccounts.load');
  const list=await call('AccountManager.getAllAccounts');
  assert.equal(list.length,1);assert.equal(list[0].uid,SAMPLE_UID);assert.equal(list[0].nickname,SAMPLE_NAME);assert.equal(list[0].groupId,0);
  report.checks.push('default_group_contains_correct_uid_and_nickname');
  const native=await runtime.AccountManager.getByPartition(PARTITION);
  assert.ok(native);assert.equal(native.uid,SAMPLE_UID);report.checks.push('native_worker_restored_for_existing_partition');
  assert.ok((await ses.cookies.get({url:'https://creator.douyin.com/'})).some(c=>c.name==='sessionid'));
  report.checks.push('session_cookie_preserved');
  let menuClicked=false;
  for(let attempt=0;attempt<40;attempt++){
   menuClicked=await main.webContents.executeJavaScript(`(()=>{const item=[...document.querySelectorAll('*')].find(e=>e.childElementCount===0&&e.textContent.trim()==='账号管理'&&e.getBoundingClientRect().width>0);if(item)item.click();return !!item;})()`);
   if(menuClicked)break;await delay(200);
  }
  report.accountMenuClicked=menuClicked;
  runtime.AccountManager.emit('reloadAccounts');
  for(let attempt=0;attempt<40;attempt++){
   const ready=await main.webContents.executeJavaScript(`(()=>{const group=document.querySelector('.account-group-header[title="默认分组"]');const header=group?.closest('.ant-collapse-header');if(!header)return false;if(header.getAttribute('aria-expanded')==='false')header.click();return true;})()`);
   if(ready)break;await delay(150);
  }
  await delay(150);runtime.AccountManager.emit('reloadAccounts');
  let visible=false;
  for(let attempt=0;attempt<30;attempt++){
   visible=await main.webContents.executeJavaScript(`([...document.querySelectorAll('*')].some(e=>e.childElementCount===0&&e.textContent.includes(${JSON.stringify(SAMPLE_NAME)})&&e.getBoundingClientRect().left<250&&e.getBoundingClientRect().width>0))`);
   if(visible)break;await delay(150);
  }
  assert.equal(visible,true,'Saved fixture account must actually appear in the account-management UI');
  report.checks.push('real_frontend_sidebar_displays_saved_fixture');
  if(phase==='save'){
   const localOwner=runtime.LoginAccount.userInfo;
   assert.equal(localOwner.user_id,0);assert.equal(localOwner.is_vip,false);
   await assert.rejects(call('CommentManager.getCommentPostList',list[0],{page:1}),/评论功能尚未连接.*小v猫软件账号/);
   assert.equal(runtime.LoginAccount.userInfo,localOwner);assert.equal(localOwner.is_vip,false);
   assert.equal(await runtime.Models.Account.count(),1);
   report.checks.push('comment_permission_failure_explained_without_fabricating_software_login');
  }
  fs.writeFileSync(output.replace(/\.json$/,'.png'),(await main.webContents.capturePage()).toPNG());
  report.ok=true;report.phase=phase;
 }catch(error){report.ok=false;report.error=error.message;report.stack=String(error.stack).split('\n').slice(0,5);if(main)try{fs.writeFileSync(output.replace(/\.json$/,'.png'),(await main.webContents.capturePage()).toPNG());}catch(_){}}
 fs.writeFileSync(output,JSON.stringify(report,null,2));app.exit(report.ok?0:1);
}
module.exports={run};
