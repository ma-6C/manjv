// Actual Edge and real source components; account/capture responses are controlled.
// No native capture, editor launch, publisher upload or task creation occurs in this test.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));
const meta=JSON.parse(fs.readFileSync(path.join(__dirname,'tmp/studio-flow-ui-host.json'),'utf8'));assert(meta.sourceOnly&&meta.realFlow);
const checks=[],check=(label,value)=>{assert(value,label);checks.push(label);};
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  let flow,project,production,jy,workspace,posts=[],flowPostPaths=[],captures=[],jobPosts=0,settingsPosts=[],launchPosts=[];
  await page.route('**/api/studio-flows**',async r=>{if(r.request().method()==='POST'){posts.push(r.request().postDataJSON());flowPostPaths.push(new URL(r.request().url()).pathname);}return r.fulfill({contentType:'application/json',body:JSON.stringify({flows:flow?[flow]:[],activeFlowId:flow?.id||''})});});
  await page.route('**/api/jobs',r=>{jobPosts++;return r.fulfill({status:409,contentType:'application/json',body:'{"error":"panel test blocks job creation"}'});});
  await page.route('**/api/jianying/launch',r=>{launchPosts.push(r.request().postDataJSON());return r.fulfill({contentType:'application/json',body:'{"appLaunched":false,"projectOpened":false,"note":"panel test blocks native editor launch"}'});});
  await page.route('**/api/publish/workspace',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(workspace||{settings:{},plans:{},tasks:[],records:[],browser:{}})}));
  await page.route('**/api/publish/settings',r=>{const b=r.request().postDataJSON();settingsPosts.push(b);workspace.settings[b.projectId]=b.overrides;return r.fulfill({contentType:'application/json',body:'{"saved":true}'});});
  await page.route('**/api/publish/inspect',r=>r.fulfill({contentType:'application/json',body:JSON.stringify(workspace.plans[project.id])}));
  await page.route('**/api/project-evidence/list**',r=>r.fulfill({contentType:'application/json',body:'{"items":[],"tasks":[]}'}));
  await page.route('**/api/project-evidence/capture',r=>{const b=r.request().postDataJSON();captures.push(b);return r.fulfill({contentType:'application/json',body:JSON.stringify(b.windowId?{taskId:'controlled-capture',status:'waiting_window'}:{windows:[{id:'controlled-window',title:'剪映工程窗口（受控测试）'}]})});});
  await page.goto(meta.launch+'#studio');await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();
  const state=await page.evaluate(()=>window.eval('state'));project=state.projects.find(p=>p.id===meta.projectId);assert(project);
  production=state.jobs.filter(j=>j.kind==='pipeline'&&j.status==='completed').at(-1);jy=state.jobs.filter(j=>j.kind==='jianying_project'&&j.status==='completed').at(-1);assert(production&&jy);
  // Keep actual host jobs/media, adding only controlled import names to the
  // response. A copied draft is deliberately not an opened editor project.
  const imports=jy.jianyingResults.map((r,index)=>({jobId:jy.id,index,projectId:r.projectId,name:r.name+'_导入_受控UI',directory:r.directory,editorValidated:false,indexModified:false}));
  assert(imports.length);
  await page.route('**/api/state',async r=>{const response=await r.fetch(),body=await response.json();const j=body.jobs.find(j=>j.id===jy.id);assert(j);j.jianyingResults.forEach((r,index)=>{r.editorImport=imports[index];});return r.fulfill({response,contentType:'application/json',body:JSON.stringify(body)});});
  const videos={};videos[project.id]=project.finalVideoPaths.map(p=>({path:p}));
  flow={id:'controlled-window-flow',status:'waiting_action',sequence:1,currentStage:'review',route:'progress',projectIds:[project.id],projectNames:{[project.id]:project.name},sourceVideoPaths:{[project.id]:project.videos.map(v=>v.path)},options:{accountId:'controlled-account'},stages:[
   {key:'production',label:'自动制作',status:'completed',ref:{kind:'job',id:production.id},result:{videos}},
   {key:'review',label:'检查成片',status:'waiting_action',reason:'review',result:{}},
   {key:'jianying',label:'生成剪映工程',status:'completed',ref:{kind:'jobs',ids:[jy.id]},result:{}},
   {key:'editor_import',label:'导入并打开剪映',status:'queued',result:{}},
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

  flow.currentStage='editor_import';flow.sequence++;flow.stages.find(s=>s.key==='review').status='completed';flow.message='工程已导入草稿库，等待打开核验';
  const editorStage=flow.stages.find(s=>s.key==='editor_import');editorStage.status='waiting_action';editorStage.reason='editor_project';editorStage.result={imports,editor:{status:'waiting_action',projectOpened:false,timelineVerified:false,projectTitleVerified:false,message:'请在剪映打开本次实际导入工程'}};
  await page.evaluate(()=>refresh(false));await page.locator('#sp-editor-checks').waitFor();
  const editorCheck=key=>page.locator(`#sp-editor-checks [data-editor-check="${key}"]`);
  check('剪映交接检查清单有草稿、导入、打开三个实际步骤',await page.locator('#sp-editor-checks [data-editor-check]').count()===3);
  check('实际工程生成与复制状态显示已完成',await editorCheck('draft').getAttribute('data-state')==='ready'&&await editorCheck('import').getAttribute('data-state')==='ready');
  check('复制成功不能冒充剪映已打开对应工程',await editorCheck('open').getAttribute('data-state')==='waiting');
  check('剪映交接显示实际导入标题',await page.locator('#sp-draft-list').textContent().then(t=>t.includes(imports[0].name)));
  check('交接步骤留在同一个制作窗口',new URL(page.url()).hash==='#studio'&&await page.locator('#studio-run-dialog').isVisible());
  const recheck=page.locator('#studio-run-footer [data-flow="continue"]');
  check('等待打开时底部提供明确重检操作',await recheck.textContent()==='重新检测并继续');
  const editorPanel=page.locator('#studio-run-panel');
  await editorPanel.evaluate(e=>{window._editorPanel=e;window._editorStage=e.querySelector('.sp-stage');window._editorChecks=e.querySelector('#sp-editor-checks');window._editorPanelStyle=e.getAttribute('style');e.style.maxHeight='220px';e.style.overflowY='auto';e.scrollTop=80;window._editorScroll=e.scrollTop;});
  check('交接面板滚动测试确实存在可滚动内容',await editorPanel.evaluate(e=>e.scrollHeight>e.clientHeight&&window._editorScroll>0));
  await page.evaluate(()=>refresh(false));await page.evaluate(()=>refresh(false));
  check('交接纯轮询保留模块DOM和滚动位置',await editorPanel.evaluate(e=>e===window._editorPanel&&e.querySelector('.sp-stage')===window._editorStage&&e.querySelector('#sp-editor-checks')===window._editorChecks&&e.scrollTop===window._editorScroll));
  check('交接纯轮询不发控制、启动剪映或创建任务',posts.length===0&&launchPosts.length===0&&jobPosts===0);
  await recheck.click();await page.waitForFunction(()=>{const b=document.querySelector('#studio-run-footer [data-flow="continue"]');return b&&!b.disabled;});
  check('明确点重检仅调用一次流程控制接口',posts.length===1&&flowPostPaths[0]==='/api/studio-flows/control'&&posts[0].id===flow.id&&posts[0].action==='continue');
  check('重检不另外创建制作任务或直接启动剪映',jobPosts===0&&launchPosts.length===0);
  const verified={status:'completed',projectOpened:true,timelineVerified:true,projectTitleVerified:true};
  editorStage.result.editor={...verified,status:'waiting_action'};await page.evaluate(()=>refresh(false));
  check('核验标志齐全但结果仍等待时不显示打开完成',await editorCheck('open').getAttribute('data-state')==='waiting');
  for(const missing of ['projectOpened','timelineVerified','projectTitleVerified']){
   editorStage.result.editor={...verified,[missing]:false};await page.evaluate(()=>refresh(false));
   check(`缺少${missing}时打开状态仍待核对`,await editorCheck('open').getAttribute('data-state')==='waiting');
  }
  editorStage.result.editor={...verified};await page.evaluate(()=>refresh(false));
  check('工程打开、标题和时间线同时核验才显示打开完成',await editorCheck('open').getAttribute('data-state')==='ready');
  check('核验结果轮询没有重复派发交接动作',posts.length===1&&jobPosts===0&&launchPosts.length===0);
  await editorPanel.evaluate(e=>{if(window._editorPanelStyle===null)e.removeAttribute('style');else e.setAttribute('style',window._editorPanelStyle);});
  await page.screenshot({path:path.join(meta.base,'flow-window-editor-import.png'),fullPage:true});

  workspace={settings:{[project.id]:{title:'受控资料标题',synopsis:'受控测试简介',producer:'',episodeCount:2,trialEpisodes:1,totalCostYuan:100,dramaType:'animation',rightsConfirmed:false}},plans:{[project.id]:{projectId:project.id,ready:false,fields:{},checks:[{key:'producer',label:'制作方',status:'missing',message:'请填写实际制作方'}],errors:['制作方缺失'],fingerprint:'controlled-plan'}},tasks:[],records:[],browser:{}};
  flow.currentStage='materials';flow.sequence++;editorStage.status='completed';flow.stages.find(s=>s.key==='materials').status='waiting_action';flow.message='请补充资料';
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
  check('模块处理未产生另一份制作任务或额外交接控制',jobPosts===0&&posts.length===1&&posts[0].action==='continue'&&launchPosts.length===0);
  await page.screenshot({path:path.join(meta.base,'flow-window-evidence.png'),fullPage:true});
  const outside=await page.locator('#studio-run-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1);check('制作窗口没有横向溢出',outside);
  await page.locator('#studio-run-header [data-flow="window-close"]').click();await page.evaluate(()=>refresh(false));
  check('收起后不被下一轮状态更新强行弹回',!await page.locator('#studio-run-dialog').evaluate(e=>e.open));
  check('实际模块无浏览器脚本异常',errors.length===0);
  fs.writeFileSync(path.join(__dirname,'tmp/flow-panels-report.json'),JSON.stringify({passed:checks.length,checks,errors,controlledResponses:true,editorStateFixture:true,nativeCapture:false,nativeLaunch:false,platformSubmitted:false,base:meta.base},null,2));
  console.log(JSON.stringify({passed:checks.length,errors}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
