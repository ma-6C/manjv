// Real Edge and source shell. Controlled orchestration and panel adapter only;
// this test never runs media/native/editor/export/platform operations.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));
const meta=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tmp/studio-flow-ui-host.json'),'utf8'));
assert(meta.sourceOnly===true);const checks=[],check=(name,ok)=>{assert(ok,name);checks.push(name);};
(async()=>{const browser=await chromium.launch({executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
 let flows=[],activeFlowId='',starts=[],controls=[],jobPosts=0;
 await page.route('**/api/jobs',r=>{if(r.request().method()==='POST'){jobPosts++;return r.fulfill({status:409,json:{error:'UI test blocks dispatch'}});}return r.continue();});
 await page.route('**/api/studio-flows**',r=>{const req=r.request(),url=new URL(req.url()),body=req.postDataJSON();
  if(url.pathname.endsWith('/start')){starts.push(body);activeFlowId='ui-flow-one';flows=[{id:activeFlowId,projectIds:body.projectIds,sourceVideoPaths:body.sourceVideoPaths,options:body.options,status:'running',currentStage:'production',route:'progress',sequence:1,message:'窗口测试素材正在处理',stages:[{key:'production',label:'自动制作',status:'running',ref:{kind:'job',id:'ui-production-job'}},{key:'jianying',label:'生成剪映工程',status:'queued',ref:{}},{key:'evidence',label:'真实工程截图',status:'queued',ref:{}},{key:'materials',label:'核对发布资料',status:'queued',ref:{}}]}];return r.fulfill({json:flows[0]});}
  if(url.pathname.endsWith('/control')){controls.push(body);flows[0].status=body.action==='pause'?'paused':'running';return r.fulfill({json:flows[0]});}
  return r.fulfill({json:{flows,activeFlowId}});
 });
 await page.goto(meta.launch+'#studio');await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();
 check('初次打开不会自动弹历史窗口',await page.locator('#studio-run-dialog[open]').count()===0);
 check('五阶段与默认折叠方案保留',await page.locator('.studio-five-stages li').count()===5&&!await page.locator('.studio-plan-details').evaluate(e=>e.open));
 for(const [hash,key,value] of [['scan','data-action','pipeline'],['tracks','data-jianying','generate'],['highlight','data-highlight','start'],['publish','data-publishing','inspect'],['progress','data-action','monitor-current']]){await page.evaluate(h=>location.hash='#'+h,hash);await page.waitForFunction(h=>current===h,hash);check('保留独立工具 '+hash,await page.locator('#start-pipeline').getAttribute(key)===value&&await page.locator('#start-pipeline').getAttribute('data-flow')===null);}
 await page.evaluate(()=>location.hash='#studio');await page.locator('#studio-flow-query').waitFor();
 await page.locator('#studio-flow-query').fill('abcde');await page.locator('#studio-flow-query').evaluate(e=>{window._search=e;e.setSelectionRange(2,2);});await page.evaluate(()=>refresh(false));check('搜索光标不会被轮询重建',await page.locator('#studio-flow-query').evaluate(e=>e===window._search&&e.selectionStart===2));await page.locator('#studio-flow-query').fill('');
 await page.locator('[data-flow="select-all"]').click();const n=await page.locator('[data-flow-video]:checked').count();check('可选择全部本地集数',n>0);
 // Stub only stage content so the shell's DOM lifetime and sole-primary
 // contract can be observed independently from each real integration.
 await page.evaluate(()=>{window._renders=0;window._primaryCalls=0;window._valid=false;window.StudioFlowPanels={
  render:(f,s)=>{window._renders++;return `<div class="studio-run-fallback"><h2>${s.label||'制作结果'}</h2><p>窗口受控测试，未执行本模块。</p><label for="shell-input">待补充内容<input id="shell-input" value="abcde"></label><video id="shell-video" controls aria-label="窗口保留测试播放器"></video><div id="shell-message"></div></div>`;},
  update:(f,s)=>{const e=document.getElementById('shell-message');if(e)e.textContent=s.message||f.message||'';},
  primary:(f,s)=>s.key==='materials'?{label:'保存并检查资料',disabled:!window._valid}:null,runPrimary:async()=>window._primaryCalls++};});
 await page.locator('#start-pipeline').click();await page.locator('#studio-run-dialog[open]').waitFor();
 check('开始打开独立制作窗口',await page.locator('#studio-run-dialog').getAttribute('aria-labelledby')==='studio-run-title');
 check('启动不会跳走主工作台',new URL(page.url()).hash==='#studio'&&await page.evaluate(()=>current)==='studio');
 check('精确选集只启动一次',starts.length===1&&Object.values(starts[0].sourceVideoPaths).flat().length===n&&jobPosts===0);
 check('模块内容在窗口内',await page.locator('#studio-run-panel').getAttribute('data-stage')==='production');
 check('未开始步骤不能点击执行',await page.locator('[data-flow="window-stage"][data-stage="materials"]').isDisabled());
 await page.evaluate(()=>{window._dialog=document.querySelector('#studio-run-dialog');window._input=document.querySelector('#shell-input');window._video=document.querySelector('#shell-video');window._input.focus();window._input.setSelectionRange(2,2);window._renderCount=window._renders;});
 await page.evaluate(()=>refresh(false));check('同阶段刷新保留窗口输入光标和播放器',await page.evaluate(()=>window._dialog===document.querySelector('#studio-run-dialog')&&window._input===document.querySelector('#shell-input')&&window._video===document.querySelector('#shell-video')&&window._input.selectionStart===2&&window._renders===window._renderCount));
 await page.locator('#studio-run-footer [data-flow="pause"]').click();await page.waitForFunction(()=>document.querySelector('#studio-run-footer [data-flow="continue"]'));
 check('制作窗口可以暂停整套流程',controls.at(-1).action==='pause');await page.locator('#studio-run-footer [data-flow="continue"]').click();await page.waitForFunction(()=>document.querySelector('#studio-run-footer [data-flow="pause"]'));
 check('恢复不重新创建流程',controls.at(-1).action==='resume'&&starts.length===1);
 flows[0].stages[0].status='completed';Object.assign(flows[0].stages[1],{status:'running',ref:{kind:'jobs',ids:['ui-jianying-job']}});Object.assign(flows[0],{currentStage:'jianying',route:'tracks',sequence:2,message:'自动交接剪映工程'});await page.evaluate(()=>refresh(false));
 check('下一模块在同一窗口自动推进',await page.locator('#studio-run-panel').getAttribute('data-stage')==='jianying'&&new URL(page.url()).hash==='#studio'&&await page.evaluate(()=>window._dialog===document.querySelector('#studio-run-dialog')));
 check('模块关联本次实际任务编号',await page.evaluate(()=>monitorId==='ui-production-job'&&jianyingJob==='ui-jianying-job'));
 await page.locator('[data-flow="window-stage"][data-stage="production"]').click();check('查看完成模块不会重做',await page.locator('#studio-run-panel').getAttribute('data-stage')==='production'&&starts.length===1);
 flows[0].stages[1].status='completed';flows[0].stages[2].status='waiting_action';Object.assign(flows[0],{currentStage:'evidence',route:'tracks',sequence:3,status:'waiting_action',message:'请确认实际工程截图'});await page.evaluate(()=>refresh(false));
 check('查看历史模块时不被新阶段抢走',await page.locator('#studio-run-panel').getAttribute('data-stage')==='production');await page.locator('[data-flow="window-current"]').click();check('一键回到当前待处理模块',await page.locator('#studio-run-panel').getAttribute('data-stage')==='evidence');
 await page.locator('#studio-run-header [data-flow="window-close"]').click();check('后台运行按钮只收起窗口',!await page.locator('#studio-run-dialog').evaluate(e=>e.open)&&controls.length===2);
 flows[0].stages[2].status='completed';flows[0].stages[3].status='waiting_action';Object.assign(flows[0],{currentStage:'materials',route:'publish',sequence:4,status:'waiting_action',message:'缺少授权证明'});await page.evaluate(()=>refresh(false));check('收起后不强制弹出下一模块',!await page.locator('#studio-run-dialog').evaluate(e=>e.open)&&new URL(page.url()).hash==='#studio');
 await page.locator('#nav a[href="#scan"]').click();await page.waitForURL('**/#scan');await page.evaluate(()=>refresh(false));check('后台流程不打断其他工具',new URL(page.url()).hash==='#scan');
 await page.locator('#studio-flow-strip [data-flow="visit"]').click();check('任何工具页可重新打开制作窗口',await page.locator('#studio-run-dialog').evaluate(e=>e.open)&&await page.locator('#studio-run-panel').getAttribute('data-stage')==='materials'&&new URL(page.url()).hash==='#scan');
 check('待补资料只有一个具体主操作',await page.locator('#studio-run-footer .primary').count()===1&&await page.locator('#studio-run-footer .primary').textContent()==='保存并检查资料'&&await page.locator('#studio-run-footer .primary').isDisabled());
 await page.evaluate(()=>{window._valid=true;window.dispatchEvent(new CustomEvent('studio-flow-panel-change'));});await page.locator('#studio-run-footer .primary').click();check('窗口主操作调用模块适配器',await page.evaluate(()=>window._primaryCalls===1));
 await page.keyboard.press('Escape');check('Escape关闭不取消流程',!await page.locator('#studio-run-dialog').evaluate(e=>e.open)&&controls.length===2);
 await page.reload();await page.waitForFunction(()=>document.querySelector('#studio-flow-strip [data-flow="visit"]'));check('重新进入历史流程不突然弹窗',await page.locator('#studio-run-dialog[open]').count()===0&&new URL(page.url()).hash==='#scan');
 await page.evaluate(()=>location.hash='#studio');await page.locator('.studio-current-card').waitFor();
 flows[0].stages=[{...flows[0].stages[0],status:'completed'},...['review','jianying','editor_import','evidence','materials','export','publish'].map(key=>({key,label:key,status:'skipped',message:'本次未选择',ref:{}}))];Object.assign(flows[0],{status:'completed',currentStage:'',sequence:5,message:'所选流程已完成'});await page.evaluate(()=>refresh(false));
 check('完成和跳过分别统计',await page.locator('.studio-flow-total').innerText().then(t=>t.includes('已完成 1 步')&&t.includes('本次跳过 7 步')));
 await page.locator('#studio-flow-detail [data-flow="view-output"]').click();check('查看成品留在同一流程窗口',await page.locator('#studio-run-panel').getAttribute('data-stage')==='production'&&new URL(page.url()).hash==='#studio');await page.locator('[data-flow="window-current"]').click();check('结果也有窗口内独立模块',await page.locator('#studio-run-panel').getAttribute('data-stage')==='completed');
 const screenshot=path.join(meta.base,'flow-window-shell-ui.png');await page.screenshot({path:screenshot,fullPage:true});await page.setViewportSize({width:390,height:844});check('窄屏流程窗口不横向溢出',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2&&document.querySelector('#studio-run-dialog').getBoundingClientRect().width<=innerWidth+2));
 await page.locator('#studio-run-footer [data-flow="window-close"]').click();await page.locator('#start-pipeline').click();check('下一批清除旧范围后再开始',await page.locator('.studio-new-batch').evaluate(e=>e.open)&&await page.locator('[data-flow-video]:checked').count()===0&&await page.locator('#start-pipeline').isDisabled());
 check('无脚本异常和重复制作提交',errors.length===0&&starts.length===1&&jobPosts===0);
 const report={passed:checks.length,checks,screenshots:[screenshot],scope:'Actual Edge source window shell; mocked orchestration and panel adapter; no media/native/editor/export/platform operations'};fs.writeFileSync(path.join(meta.base,'flow-ui-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({passed:checks.length,errors,screenshot}));
}finally{await browser.close();}})().catch(e=>{console.error(String(e).split(meta.launch).join('[local launch]'));process.exitCode=1;});
