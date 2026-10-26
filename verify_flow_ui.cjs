// Real Edge interaction with the real source UI. Only orchestration responses
// and a second UI-only project are mocked; no production, editor launch,
// file export or publishing is run.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));
const metadata=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tmp/official-project-ui-host.json'),'utf8'));
assert(metadata.sourceOnly===true,'Use an isolated source host');
const checks=[],check=(name,value)=>{assert(value,name);checks.push(name);};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  let flows=[],activeFlowId='',starts=[],controls=[],jobsPosts=0,additionalProject=false;
  const secondId='ui-second-project';
  await page.route('**/api/state',async r=>{const response=await r.fetch(),body=await response.json();if(additionalProject&&body.projects?.length){const p=structuredClone(body.projects[0]);p.id=secondId;p.name='界面测试第二剧目（模拟）';p.cover='';p.videos=p.videos.slice(0,1).map(v=>({...v,path:'D:\\ui-test-only\\second.mp4',name:'第二部测试视频.mp4'}));body.projects.push(p);}await r.fulfill({response,json:body});});
  await page.route('**/api/jobs',r=>{if(r.request().method()==='POST'){jobsPosts++;return r.fulfill({status:409,contentType:'application/json',body:JSON.stringify({error:'UI test blocks dispatch'})});}return r.continue();});
  await page.route('**/api/studio-flows**',async r=>{
   const req=r.request(),url=new URL(req.url()),body=req.postDataJSON();
   if(url.pathname==='/api/studio-flows/start'){
    starts.push(body);activeFlowId='ui-flow-one';
    flows=[{id:activeFlowId,projectIds:body.projectIds,sourceVideoPaths:body.sourceVideoPaths,options:body.options,status:'running',currentStage:'production',route:'progress',sequence:1,message:'正在制作测试素材',stages:[{key:'production',label:'自动制作',route:'progress',status:'running',ref:{kind:'job',id:'ui-production-job'},message:'测试响应，未运行制作'},{key:'jianying',label:'生成剪映工程',route:'tracks',status:'queued',ref:{}},{key:'materials',label:'核对发布资料',route:'publish',status:'queued',ref:{}}]}];
    return r.fulfill({contentType:'application/json',body:JSON.stringify(flows[0])});
   }
   if(url.pathname==='/api/studio-flows/control'){controls.push(body);if(body.action==='pause')flows[0].status='paused';if(['continue','resume'].includes(body.action))flows[0].status='running';return r.fulfill({contentType:'application/json',body:JSON.stringify(flows[0])});}
   return r.fulfill({contentType:'application/json',body:JSON.stringify({flows,activeFlowId})});
  });
  await page.goto(metadata.launch+'#studio');await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();
  const startScreenshot=path.join(metadata.base,'flow-start-ui.png'),progressScreenshot=path.join(metadata.base,'flow-progress-ui.png'),completedScreenshot=path.join(metadata.base,'flow-completed-ui.png');
  await page.screenshot({path:startScreenshot,fullPage:true});
  check('五阶段流程清晰展示',await page.locator('.studio-five-stages li').count()===5);
  check('后续步骤默认折叠',!await page.locator('.studio-plan-details').evaluate(e=>e.open));
  check('保留单步素材与工程入口',await page.locator('#nav a[href="#scan"]').count()===1&&await page.locator('#nav a[href="#tracks"]').count()===1);
  check('只有一个开始主操作',await page.locator('button.primary[data-flow="start"]').count()===1);
  check('方案摘要按实际配置列出步骤',await page.evaluate(()=>{const old=state.config;state.config={...old,subtitleAuto:false,regroup:false,pipelineHighlight:false,autoText:false,autoCover:false,autoRecords:false,autoCost:false};renderPage();const first=document.querySelector('#studio-plan-summary').textContent;state.config={...old,subtitleAuto:true,regroup:true,pipelineHighlight:true};renderPage();const second=document.querySelector('#studio-plan-summary').textContent;state.config=old;renderPage();return !first.includes('字幕修复')&&!first.includes('高光包装')&&first.includes('逐集画面处理')&&second.includes('字幕修复')&&second.includes('合并切分')&&second.includes('高光包装');}));
  for(const [hash,attribute,value] of [['scan','data-action','pipeline'],['tracks','data-jianying','generate'],['highlight','data-highlight','start'],['publish','data-publishing','inspect'],['progress','data-action','monitor-current']]){
   await page.evaluate(h=>location.hash='#'+h,hash);await page.waitForFunction(h=>current===h,hash);
   check('离开流程后保留单步操作 '+hash,await page.locator('#start-pipeline').getAttribute(attribute)===value&&await page.locator('#start-pipeline').getAttribute('data-flow')===null);
  }
  await page.evaluate(()=>location.hash='#studio');await page.locator('#studio-flow-query').waitFor();
  const search=page.locator('#studio-flow-query');await search.fill('abcdef');await search.evaluate(e=>{window._flowInput=e;e.setSelectionRange(3,3);});
  await page.evaluate(()=>refresh(false));
  check('轮询保留搜索框与光标',await search.evaluate(e=>e===window._flowInput&&e.value==='abcdef'&&e.selectionStart===3));
  await search.pressSequentially('X');check('中间插入输入正常',await search.inputValue()==='abcXdef');await search.fill('');
  additionalProject=true;await page.evaluate(()=>refresh(false));check('新导入项目可进入连续流程选择',await page.locator(`[data-flow-project="${secondId}"]`).count()===1);
  await page.locator('[data-flow="select-all"]').click();
  const selection=await page.locator('[data-flow-video]:checked').count();check('可以一次选择已导入全部集数',selection>0);
  if(selection>1){await page.locator('.studio-project details').first().locator('summary').click();await page.locator('[data-flow-video]').first().uncheck();check('可自由排除任意集数',await page.locator('[data-flow-video]:checked').count()===selection-1);await page.locator('[data-flow-video]').first().check();}
  const selectedCount=await page.locator('[data-flow-video]:checked').count();
  await page.locator('#start-pipeline').click();await page.waitForURL('**/#progress');await page.waitForFunction(()=>current==='progress');
  check('一次启动立即进入真实任务进度页',starts.length===1&&await page.evaluate(()=>current)==='progress');
  check('启动提交精确选择范围',!Array.isArray(starts[0].sourceVideoPaths)&&Object.values(starts[0].sourceVideoPaths).flat().length===selectedCount);
  check('前端没有从导航或轮询直接创建制作任务',jobsPosts===0);
  check('启动开启页面跟随',await page.locator('#studio-flow-strip').getAttribute('data-following')==='true');
  flows[0].stages[0].status='completed';flows[0].stages[1].status='running';flows[0].stages[1].ref={kind:'jobs',ids:['ui-jianying-job']};Object.assign(flows[0],{currentStage:'jianying',route:'tracks',sequence:2,message:'生成剪映工程'});
  await page.evaluate(()=>refresh(false));await page.waitForURL('**/#tracks');await page.waitForFunction(()=>current==='tracks');
  check('后台阶段变化自动进入剪映工程页',await page.evaluate(()=>current)==='tracks');
  check('关联本次制作与工程任务',await page.evaluate(()=>monitorId==='ui-production-job'&&jianyingJob==='ui-jianying-job'));
  flows[0].stages.push({key:'evidence',label:'保存真实工程截图',route:'tracks',status:'waiting_action',result:{missingProjectIds:[secondId]}});Object.assign(flows[0],{currentStage:'evidence',route:'tracks',sequence:3,status:'waiting_action',message:'第二部剧需要截图'});
  await page.evaluate(()=>refresh(false));check('同页切换到缺少截图的实际剧目',await page.evaluate(id=>focusId===id&&jyEvidenceProject===id&&document.querySelector('#jy-evidence-project').value===id,secondId));
  await page.locator('#nav a[href="#scan"]').click();await page.waitForURL('**/#scan');
  check('手动导航暂停页面跟随',await page.locator('#studio-flow-strip').getAttribute('data-following')==='false');
  Object.assign(flows[0],{currentStage:'materials',route:'publish',sequence:4,status:'waiting_action',message:'缺少授权证明'});flows[0].stages[1].status='completed';flows[0].stages.at(-1).status='completed';Object.assign(flows[0].stages[2],{status:'waiting_action',message:'缺少授权证明',result:{missing:[{projectId:secondId,errors:['缺少授权证明']}]}});
  await page.evaluate(()=>refresh(false));check('新阶段不把手动查看的页面拉走',new URL(page.url()).hash==='#scan');
  await page.locator('#studio-flow-strip [data-flow="follow"]').click();await page.waitForURL('**/#publish');
  check('显式继续跟随定位到待补充步骤',await page.locator('#studio-flow-strip').getAttribute('data-following')==='true');
  check('发布资料定位到缺项剧目',await page.evaluate(id=>focusId===id&&document.querySelector('#publishing-project')?.value===id,secondId));
  await page.locator('#studio-flow-strip a[href="#studio"]').click();await page.waitForURL('**/#studio');await page.locator('.studio-current-card').waitFor();
  check('当前流程优先显示且不用重选素材',await page.locator('.studio-current-card').count()===1&&await page.locator('#studio-flow-detail').innerText().then(t=>t.includes('缺少授权证明')));
  const detail=page.locator('.studio-stage-details');await detail.locator('summary').click();await page.evaluate(()=>refresh(false));check('刷新保持已展开步骤清单',await detail.evaluate(e=>e.open));
  check('当前步骤主操作为检查并继续',await page.locator('#start-pipeline').getAttribute('data-flow')==='continue');
  await page.screenshot({path:progressScreenshot,fullPage:true});
  await page.reload();await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();await page.evaluate(()=>refresh(false));
  check('重开历史流程不突然跳页',new URL(page.url()).hash==='#studio'&&await page.locator('#studio-flow-strip').getAttribute('data-following')==='false');
  flows[0].stages=[flows[0].stages[0],...['review','jianying','editor_import','evidence','materials','export','publish'].map(key=>({key,label:key==='publish'?'发布准备与确认':key,route:key==='publish'?'publish':'tracks',status:'skipped',message:'本次未选择',ref:{}}))];Object.assign(flows[0],{status:'completed',currentStage:'',sequence:5,message:'所选流程已完成'});
  await page.evaluate(()=>refresh(false));check('完成流程不把最后跳过的发布步骤当作当前步骤',await page.locator('#studio-flow-detail h2').textContent()==='所选流程已完成');
  check('完成与跳过分别统计',await page.locator('.studio-flow-total').innerText().then(t=>t.includes('已完成 1 步')&&t.includes('本次跳过 7 步')&&!t.includes('8 / 8')));
  await page.reload();await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();await page.screenshot({path:completedScreenshot,fullPage:true});
  check('完成后主操作先准备下一批',await page.locator('#start-pipeline').getAttribute('data-flow')==='prepare-next'&&await page.locator('#studio-flow-detail [data-flow="visit"]').count()===0);
  await page.locator('#studio-flow-detail [data-flow="view-output"]').click();await page.waitForFunction(()=>current==='progress');check('查看成品关联本次制作任务',await page.evaluate(()=>monitorId==='ui-production-job'));
  await page.locator('#studio-flow-strip a[href="#studio"]').click();await page.locator('.studio-current-card').waitFor();await page.locator('#start-pipeline').click();
  check('明确准备下一批后展开并清空旧选择',await page.locator('.studio-new-batch').evaluate(e=>e.open)&&await page.locator('[data-flow-video]:checked').count()===0&&await page.locator('#start-pipeline').getAttribute('data-flow')==='start'&&await page.locator('#start-pipeline').isDisabled());
  await page.locator('[data-flow-project]').first().check();check('下一批重新选材后才可再次开始',await page.locator('#start-pipeline').isEnabled()&&starts.length===1);
  await page.setViewportSize({width:390,height:844});
  check('窄屏不横向溢出',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2));
  check('没有浏览器脚本异常',errors.length===0);check('没有重复启动或平台提交',starts.length===1&&jobsPosts===0&&controls.length===0);
  const report={passed:checks.length,checks,screenshots:[startScreenshot,progressScreenshot,completedScreenshot],scope:'Actual Edge UI with mocked orchestration and one added UI-only project; no real jobs/editor/export/platform actions'};
  fs.writeFileSync(path.join(metadata.base,'flow-ui-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(e=>{console.error(String(e).split(metadata.launch).join('[local launch]'));process.exitCode=1;});
