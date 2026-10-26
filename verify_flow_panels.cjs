// Actual Edge and real source components; account/capture responses are controlled.
// No native capture, publisher upload or task creation occurs in this test.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));
const meta=JSON.parse(fs.readFileSync(path.join(__dirname,'tmp/studio-flow-ui-host.json'),'utf8'));assert(meta.sourceOnly&&meta.realFlow);
const checks=[],check=(label,value)=>{assert(value,label);checks.push(label);};
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  let flow,project,production,jy,workspace,posts=[],captures=[],jobPosts=0,settingsPosts=[];
  await page.route('**/api/studio-flows**',async r=>{if(r.request().method()==='POST')posts.push(r.request().postDataJSON());return r.fulfill({contentType:'application/json',body:JSON.stringify({flows:flow?[flow]:[],activeFlowId:flow?.id||''})});});
  await page.route('**/api/jobs',r=>{jobPosts++;return r.fulfill({status:409,contentType:'application/json',body:'{"error":"panel test blocks job creation"}'});});
  await page.route('**/api/publish/workspace',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(workspace||{settings:{},plans:{},tasks:[],records:[],browser:{}})}));
  await page.route('**/api/publish/settings',r=>{const b=r.request().postDataJSON();settingsPosts.push(b);workspace.settings[b.projectId]=b.overrides;return r.fulfill({contentType:'application/json',body:'{"saved":true}'});});
  await page.route('**/api/publish/inspect',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(workspace.plans[project.id])}));
  await page.route('**/api/project-evidence/list**',r=>r.fulfill({contentType:'application/json',body:'{"items":[],"tasks":[]}'}));
  await page.route('**/api/project-evidence/capture',r=>{const b=r.request().postDataJSON();captures.push(b);return r.fulfill({contentType:'application/json',body:JSON.stringify(b.windowId?{taskId:'controlled-capture',status:'waiting_window'}:{windows:[{id:'controlled-window',title:'剪映工程窗口（受控测试）'}]})});});
  await page.goto(meta.launch+'#studio');await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();
  const state=await page.evaluate(()=>window.eval('state'));project=state.projects.find(p=>p.id===meta.projectId);assert(project);
  production=state.jobs.filter(j=>j.kind==='pipeline'&&j.status==='completed').at(-1);jy=state.jobs.filter(j=>j.kind==='jianying_project'&&j.status==='completed').at(-1);assert(production&&jy);
  const videos={};videos[project.id]=project.finalVideoPaths.map(p=>({path:p}));
  flow={id:'controlled-window-flow',status:'waiting_action',sequence:1,currentStage:'review',route:'progress',projectIds:[project.id],projectNames:{[project.id]:project.name},sourceVideoPaths:{[project.id]:project.videos.map(v=>v.path)},options:{accountId:'controlled-account'},stages:[
   {key:'production',label:'自动制作',status:'completed',ref:{kind:'job',id:production.id},result:{videos}},
   {key:'review',label:'检查成片',status:'waiting_action',reason:'review',result:{}},
   {key:'jianying',label:'生成剪映工程',status:'completed',ref:{kind:'jobs',ids:[jy.id]},result:{}},
   {key:'evidence',label:'工程截图',status:'queued',result:{}},
   {key:'materials',label:'发布资料',status:'queued',result:{}},
   {key:'export',label:'导出资料',status:'queued',result:{}},
   {key:'publish',label:'发布准备',status:'queued',result:{}}
  ]};
  await page.evaluate(()=>refresh(false));await page.locator('#start-pipeline').click();await page.locator('#studio-run-dialog').waitFor({state:'visible'});
  check('独立窗口打开时主工作台地址不变',new URL(page.url()).hash==='#studio');
  const video=page.locator('#sp-output-video');await video.waitFor();await video.evaluate(v=>{window._panelVideo=v;v.currentTime=.3;});await page.evaluate(()=>refresh(false));
  check('同阶段轮询保留原播放器和播放位置',await video.evaluate(v=>v===window._panelVideo&&v.currentTime>=.29));
  check('成片来自本次任务登记输出',await video.getAttribute('src')===await page.evaluate(p=>media(p),videos[project.id][0].path));

  workspace={settings:{[project.id]:{title:'受控资料标题',synopsis:'受控测试简介',producer:'',episodeCount:2,trialEpisodes:1,totalCostYuan:100,dramaType:'animation',rightsConfirmed:false}},plans:{[project.id]:{projectId:project.id,ready:false,fields:{},checks:[{key:'producer',label:'制作方',status:'missing',message:'请填写实际制作方'}],errors:['制作方缺失'],fingerprint:'controlled-plan'}},tasks:[],records:[],browser:{}};
  flow.currentStage='materials';flow.sequence++;flow.stages.find(s=>s.key==='review').status='completed';flow.stages.find(s=>s.key==='materials').status='waiting_action';flow.message='请补充资料';
  await page.evaluate(()=>refresh(false));await page.locator('#sp-material-form[data-loaded]').waitFor();
  check('下一模块显示在同一个窗口内',new URL(page.url()).hash==='#studio'&&await page.locator('#studio-run-dialog').isVisible()&&await page.locator('#sp-material-form').count()===1);
  check('资料读取既有保存值',await page.locator('#sp-field-title').inputValue()==='受控资料标题');
  const title=page.locator('#sp-field-title');await title.fill('abcdef');await title.evaluate(e=>{window._panelInput=e;e.setSelectionRange(3,3);});
  await page.evaluate(()=>refresh(false));check('资料轮询保留输入DOM与光标',await title.evaluate(e=>e===window._panelInput&&e.selectionStart===3&&e.value==='abcdef'));
  await title.pressSequentially('X');await page.locator('#sp-field-producer').fill('受控测试制作方');await page.locator('#sp-field-rightsConfirmed').check();
  await page.locator('#studio-run-footer [data-flow="window-primary"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-save-state')?.textContent==='资料保存在本机');
  check('资料在窗口中保存到原有后端接口',settingsPosts.length===1&&settingsPosts[0].projectId===project.id&&settingsPosts[0].overrides.title==='abcXdef'&&settingsPosts[0].overrides.rightsConfirmed===true);
  check('未用空数组屏蔽自动登记的官方截图',!Object.hasOwn(settingsPosts[0].overrides,'proofImages'));
  await page.screenshot({path:path.join(meta.base,'flow-window-materials.png'),fullPage:true});

  flow.currentStage='evidence';flow.sequence++;flow.stages.find(s=>s.key==='evidence').status='waiting_action';flow.stages.find(s=>s.key==='evidence').reason='evidence';flow.message='请采集本次真实工程截图';
  await page.evaluate(()=>refresh(false));await page.locator('#sp-draft-select').waitFor();
  await page.locator('#studio-run-footer [data-flow="window-primary"]').click();await page.locator('#sp-window-select').waitFor();
  check('读窗口列表不会直接保存或伪造截图',captures.length===1&&!captures[0].userConfirmed&&!captures[0].windowId);
  check('本人确认前采集按钮不可用',await page.locator('#studio-run-footer [data-flow="window-primary"]').isDisabled());
  await page.locator('#sp-window-confirm').check();await page.locator('#studio-run-footer [data-flow="window-primary"]').click();
  await page.waitForFunction(()=>document.querySelector('#sp-notice')?.textContent.includes('30秒'));
  check('采集绑定本次实际工程并保留明确本人确认',captures.length===2&&captures[1].userConfirmed===true&&captures[1].jobId===jy.id&&captures[1].projectId===project.id&&captures[1].windowId==='controlled-window');
  check('采集后清除确认，防止误重复采集',!await page.locator('#sp-window-confirm').isChecked());
  check('模块处理未产生另一份制作任务',jobPosts===0&&posts.length===0);
  await page.screenshot({path:path.join(meta.base,'flow-window-evidence.png'),fullPage:true});
  const outside=await page.locator('#studio-run-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1);check('制作窗口没有横向溢出',outside);
  await page.locator('#studio-run-header [data-flow="window-close"]').click();await page.evaluate(()=>refresh(false));
  check('收起后不被下一轮状态更新强行弹回',!await page.locator('#studio-run-dialog').evaluate(e=>e.open));
  check('实际模块无浏览器脚本异常',errors.length===0);
  fs.writeFileSync(path.join(__dirname,'tmp/flow-panels-report.json'),JSON.stringify({passed:checks.length,checks,errors,controlledResponses:true,nativeCapture:false,platformSubmitted:false,base:meta.base},null,2));
  console.log(JSON.stringify({passed:checks.length,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
