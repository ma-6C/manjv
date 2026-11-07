'use strict';
// Isolated browser contract checks. All APIs are in-memory fixtures; no uploads,
// paid cloud calls, customer data or production configuration are used.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const http=require('node:http'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=__dirname,web=path.join(root,'web'),out=path.join(root,'tmp','promotion-engines-ui');
const clone=value=>JSON.parse(JSON.stringify(value));
const engineSettings={
 settings:{mediakit:{base:'https://mediakit.cn-beijing.volces.com',cutMode:'Mixed'},dramaclip:{root:'',python:'',mode:'highlight'}},
 mediakit:{hasKey:false},dramaclip:{ready:false,message:'未检测到 DramaClip 增强环境，将使用现有本地混剪能力。',missing:['独立规划运行环境'],prepareScript:'D:/fixture/tools/prepare_dramaclip.py'}
};
const fixture={config:{source:'D:/fixture/source',output:'D:/fixture/output',costRows:[],segmentSeconds:40},
 projects:[{id:'fixture-project',name:'演示短剧',originalName:'演示短剧',intro:'仅用于隔离浏览器验证。',rights:true,source:'D:/fixture/source',
  videos:[{path:'D:/fixture/source/01.mp4',name:'第0001集.mp4',duration:90,audio:true,width:720,height:1280},{path:'D:/fixture/source/02.mp4',name:'第0002集.mp4',duration:80,audio:true,width:720,height:1280}],
  artifacts:[],promotionStudio:{engine:'local',count:2,seconds:60,sourcePaths:['D:/fixture/source/01.mp4','D:/fixture/source/02.mp4']},promotionClips:[],promotionAnalysis:null}],
 accounts:[],jobs:[],logs:[],secrets:{},aiProviders:[],connectionKeyStatus:{},promotionTasks:[]};
const project=()=>fixture.projects[0];
const firstPath=project().videos[0].path,secondPath=project().videos[1].path;
const local={engine:'local',count:3,seconds:77,direction:'本地：保留反转和情绪高潮',cta:'本地：点击入口继续观看完整剧情',sourcePaths:[firstPath]};
const cloud={engine:'mediakit',count:4,seconds:44,direction:'云端：突出人物冲突',cta:'云端：继续看全集',sourcePaths:[secondPath]};
const requests=[],studioRequests=[],jobs=[],pageErrors=[],externalRequests=[],checks=[];
let failSave=false,failStudioSave=false,readDelay=0;
// Match the real endpoint: normalize values, migrate the legacy single record,
// merge by engine, and return both settings and settingsByEngine.
function rememberStudioSettings(target,value){
 assert.ok(['local','mediakit'].includes(value.engine));
 assert.ok(value.sourcePaths?.length&&value.sourcePaths.every(p=>target.videos.some(v=>v.path===p)));
 const clean={engine:value.engine,sourcePaths:clone(value.sourcePaths),count:Number(value.count??2),seconds:Number(value.seconds??60),
  direction:value.direction??'冲突、反转、悬念，结尾保留看全集的动机',cta:value.cta??'点击下方入口看全集',
  publishMode:value.publishMode||'draft',autoDispatch:false,targets:{},matrixPath:value.matrixPath||''};
 const previous=target.promotionStudio||{},byEngine=clone(target.promotionStudioByEngine||{});
 if(Object.keys(previous).length&&['local','mediakit'].includes(previous.engine||'local')&&!byEngine[previous.engine||'local'])byEngine[previous.engine||'local']=clone(previous);
 byEngine[clean.engine]=clone(clean);target.promotionStudioByEngine=byEngine;target.promotionStudio=clone(clean);
 return {settings:clone(clean),settingsByEngine:clone(byEngine)};
}
function jobFixture(id,engine,status='completed',projectId=project().id){return {id,kind:'promotion_auto',ids:[projectId],project:projectId===project().id?project().name:'另一部剧',status,
 stage:'任务标记 '+id,progress:status==='completed'?100:30,options:{studio:{engine}},created:'2026-11-07 12:00:00'};}
const types={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'};
const server=http.createServer((req,res)=>{
 const url=new URL(req.url,'http://127.0.0.1');
 if(url.pathname.startsWith('/api/')){res.writeHead(500,{'Content-Type':'application/json'});res.end(JSON.stringify({error:'Fixture API was not intercepted'}));return;}
 const target=path.resolve(web,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));
 if(!target.startsWith(web+path.sep)){res.writeHead(404);res.end();return;}
 fs.readFile(target,(err,data)=>{res.writeHead(err?404:200,{'Content-Type':types[path.extname(target)]||'application/octet-stream','Cache-Control':'no-store'});res.end(err?'':data);});
});
async function eventually(fn,label){for(let i=0;i<100;i++){if(await fn())return;await new Promise(resolve=>setTimeout(resolve,30));}throw Error('Timed out: '+label);}
(async()=>{
 fs.mkdirSync(out,{recursive:true});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const base='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1050}});
 page.on('pageerror',e=>pageErrors.push(e.message));
 await page.route('**/*',route=>{if(new URL(route.request().url()).origin===base)return route.continue();externalRequests.push(route.request().url());return route.abort('blockedbyclient');});
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url()),endpoint=url.pathname.slice(5),body=request.postDataJSON();
  const respond=(data,status=200)=>route.fulfill({status,contentType:'application/json',body:JSON.stringify(clone(data))});
  if(endpoint==='state')return respond(fixture);
  if(endpoint==='environment')return respond({ffmpeg:true,fonts:true,cpu:4,python:'3.12',gpu:{available:false,detail:'隔离验证环境'}});
  if(endpoint==='file')return route.fulfill({status:204,body:''});
  if(endpoint==='promotion/engines'){if(readDelay)await new Promise(resolve=>setTimeout(resolve,readDelay));return respond(engineSettings);}
  if(endpoint==='promotion/engines/settings'){
   requests.push(clone(body));if(failSave){failSave=false;return respond({error:'模拟保存失败：请稍后重试'},503);}
   engineSettings.settings=clone(body.settings);
   if(body.clearMediakitKey)engineSettings.mediakit.hasKey=false;else if(body.mediakitKey)engineSettings.mediakit.hasKey=true;
   engineSettings.dramaclip={...engineSettings.dramaclip,ready:!!body.settings.dramaclip.root,message:body.settings.dramaclip.root?'DramaClip 剧情规划增强已就绪。':'未检测到增强环境，将使用现有本地混剪能力。'};
   return respond(engineSettings);
  }
  if(endpoint==='promotion/studio-settings'){const target=fixture.projects.find(p=>p.id===body.projectId);assert.ok(target);studioRequests.push(clone(body));if(failStudioSave){failStudioSave=false;return respond({error:'模拟模块参数保存失败'},503);}return respond(rememberStudioSettings(target,body.settings));}
  if(endpoint==='project'){Object.assign(fixture.projects[0],body);return respond({project:fixture.projects[0]});}
  if(endpoint==='jobs'){jobs.push(clone(body));const id='submitted-'+jobs.length;fixture.jobs.push({...jobFixture(id,body.studio.engine,'queued',body.ids[0]),options:{studio:clone(body.studio)}});return respond({id});}
  if(endpoint==='browse')return respond({path:body.mode==='python'?'D:/fixture/venv/python.exe':'D:/fixture/DramaClip'});
  return respond({});
 });
 async function switchModule(engine){
  await page.locator('#studio-module-'+engine).click();
  await eventually(async()=>await page.locator('#studio-module-'+engine).getAttribute('aria-selected')==='true','module '+engine+' selected');
  assert.equal(await page.locator('#studio-engine').inputValue(),engine);
  await eventually(()=>project().promotionStudio.engine===engine,'module '+engine+' persisted');
 }
 async function fillModule(values){
  for(const key of ['count','seconds','direction','cta'])await page.locator('#studio-'+key).fill(String(values[key]));
  await page.locator('#studio-cta').press('Tab');
  if(!await page.locator('.studio-sources').evaluate(el=>el.open))await page.locator('.studio-sources summary').click();
  for(const input of await page.locator('[data-studio-source]').all())await input.setChecked(values.sourcePaths.includes(await input.getAttribute('data-studio-source')));
  await eventually(()=>{const saved=project().promotionStudioByEngine?.[values.engine];return saved&&['count','seconds','direction','cta','sourcePaths'].every(key=>JSON.stringify(saved[key])===JSON.stringify(values[key]));},values.engine+' independent settings saved');
 }
 async function assertModule(values){
  assert.equal(await page.locator('#studio-engine').inputValue(),values.engine);
  for(const key of ['count','seconds','direction','cta'])assert.equal(await page.locator('#studio-'+key).inputValue(),String(values[key]),values.engine+' '+key);
  assert.deepEqual(await page.locator('[data-studio-source]:checked').evaluateAll(inputs=>inputs.map(input=>input.dataset.studioSource)),values.sourcePaths,values.engine+' sources');
 }
 try{
  await page.goto(base+'/#promotion');await page.locator('#studio-module-local').waitFor();
  assert.deepEqual(await page.locator('[data-studio="module"][role="tab"]').evaluateAll(tabs=>tabs.map(tab=>tab.dataset.engine)),['local','mediakit']);
  assert.equal(await page.locator('#studio-engine').isVisible(),false);
  assert.equal(await page.locator('[data-studio="analyse"],[data-studio="render"]').count(),0);
  assert.match(await page.locator('#studio-engine-hint').innerText(),/DramaClip.*剧情规划/);
  assert.equal(project().promotionStudioByEngine,undefined,'fixture starts with legacy configuration');
  checks.push('two_independent_modules_one_click_only_legacy_configuration_loaded');
  await fillModule(local);await switchModule('mediakit');
  assert.equal(await page.locator('#studio-count').inputValue(),'2','new cloud module does not inherit local parameters');
  assert.notEqual(await page.locator('#studio-direction').inputValue(),local.direction);
  assert.deepEqual(await page.locator('[data-studio-source]:checked').evaluateAll(inputs=>inputs.map(input=>input.dataset.studioSource)),[firstPath,secondPath]);
  await fillModule(cloud);
  assert.match(await page.locator('#studio-target-hint').innerText(),/20字.*目标范围/);
  assert.equal(await page.locator('#studio-analysis').count(),0,'cloud does not contain the local planning area');
  assert.match(await page.locator('#studio-cloud-selection').innerText(),/1 集.*30集.*45分钟/);
  await switchModule('local');await assertModule(local);await switchModule('mediakit');await assertModule(cloud);
  checks.push('module_parameters_and_episode_selection_saved_separately');
  await page.reload();await page.locator('#studio-module-mediakit').waitFor();await assertModule(cloud);
  await switchModule('local');await assertModule(local);
  await page.reload();await page.locator('#studio-module-local').waitFor();await assertModule(local);
  checks.push('both_module_configs_and_last_module_survive_reload');
  failStudioSave=true;
  await page.locator('#studio-direction').fill(local.direction+'（待重试）');await page.locator('#studio-direction').press('Tab');
  await eventually(async()=>/模拟模块参数保存失败/.test(await page.locator('#studio-save-state').innerText()),'module save error is actionable');
  assert.equal(project().promotionStudioByEngine.local.direction,local.direction,'failed save does not replace persisted parameters');
  assert.equal(await page.locator('#studio-direction').inputValue(),local.direction+'（待重试）');
  await switchModule('mediakit');await assertModule(cloud);await switchModule('local');
  assert.equal(await page.locator('#studio-direction').inputValue(),local.direction+'（待重试）','module draft retained across switching');
  await page.locator('#studio-direction').fill(local.direction);await page.locator('#studio-direction').press('Tab');
  await eventually(()=>project().promotionStudioByEngine.local.direction===local.direction,'local recovered parameters saved');
  checks.push('module_save_error_retains_draft_and_switch_does_not_overwrite_other_engine');

  if(!await page.locator('.studio-sources').evaluate(el=>el.open))await page.locator('.studio-sources summary').click();
  const beforeEmpty=studioRequests.length;await page.locator('[data-studio="clear-selection"]').click();
  await eventually(async()=>/未保存/.test(await page.locator('#studio-save-state').innerText()),'empty selection shows unsaved state');
  assert.equal(await page.locator('[data-studio-source]:checked').count(),0);assert.equal(studioRequests.length,beforeEmpty,'empty selection is not posted');
  await switchModule('mediakit');await assertModule(cloud);
  await page.locator('#studio-module-local').click();
  await eventually(async()=>await page.locator('#studio-module-local').getAttribute('aria-selected')==='true','empty local draft restored');
  assert.equal(await page.locator('[data-studio-source]:checked').count(),0,'empty draft kept independently');
  if(!await page.locator('.studio-sources').evaluate(el=>el.open))await page.locator('.studio-sources summary').click();
  await page.locator('[data-studio-source]').first().check();
  await eventually(()=>project().promotionStudio.engine==='local','restored selection saved');await assertModule(local);
  checks.push('empty_source_draft_is_not_posted_or_filled_from_other_module');
  await page.evaluate(()=>{window._studioDirection=document.querySelector('#studio-direction');window._studioSource=document.querySelector('#promo-source');});
  assert.equal(await page.locator('#promo-source').count(),1);
  readDelay=150;
  await page.locator('[data-studio="settings-open"][data-tab="dramaclip"]').first().click();
  await page.locator('#studio-settings-tab-mediakit').click();
  await page.locator('[data-target="studio-mediakit-download-folder"]').click();
  await eventually(async()=>await page.getByLabel('成片保存文件夹').inputValue()==='D:/fixture/DramaClip','cloud folder selected');
  await page.locator('#studio-mediakit-key').fill('FAKE-UI-ONLY-KEY');
  await page.waitForTimeout(180);
  assert.equal(await page.locator('#studio-mediakit-key').inputValue(),'FAKE-UI-ONLY-KEY');
  await page.locator('#studio-settings-tab-mediakit').press('ArrowUp');
  assert.equal(await page.locator('#studio-settings-tab-dramaclip').getAttribute('aria-selected'),'true');
  await page.locator('#studio-settings-tab-dramaclip').press('End');
  assert.equal(await page.locator('#studio-settings-tab-mediakit').getAttribute('aria-selected'),'true');
  assert.equal(await page.locator('#studio-mediakit-key').inputValue(),'FAKE-UI-ONLY-KEY');
  await page.evaluate(async()=>{await poll();});
  assert.equal(await page.locator('#studio-mediakit-key').inputValue(),'FAKE-UI-ONLY-KEY');
  assert.equal(await page.evaluate(()=>window._studioDirection===document.querySelector('#studio-direction')),true);
  assert.equal(await page.evaluate(()=>window._studioSource===document.querySelector('#promo-source')),true);
  assert.equal(await page.locator('#studio-direction').inputValue(),local.direction);
  checks.push('late_get_tabs_and_poll_preserve_unsaved_key_form_and_video_node');

  failSave=true;await page.locator('[data-studio="settings-save"]').click();
  await page.getByText('模拟保存失败：请稍后重试',{exact:true}).waitFor();
  assert.equal(await page.locator('#studio-mediakit-key').inputValue(),'FAKE-UI-ONLY-KEY');
  assert.equal(await page.locator('#studio-settings-dialog').evaluate(dialog=>dialog.open),true);
  checks.push('save_error_inline_preserves_key_and_open_dialog');

  await page.locator('[data-studio="settings-save"]').click();
  await eventually(()=>engineSettings.mediakit.hasKey,'key saved');
  await eventually(async()=>await page.locator('#studio-mediakit-key').inputValue()==='','key cleared');
  assert.equal(requests.at(-1).mediakitKey,'FAKE-UI-ONLY-KEY');
  assert.equal(engineSettings.settings.mediakit.downloadFolder,'D:/fixture/DramaClip');
  assert.equal(fixture.config.output,'D:/fixture/output');
  assert.equal(await page.locator('#studio-mediakit-key').getAttribute('type'),'password');
  assert.equal(JSON.stringify(fixture).includes('FAKE-UI-ONLY-KEY'),false);
  assert.equal(JSON.stringify(engineSettings).includes('FAKE-UI-ONLY-KEY'),false);
  checks.push('key_saved_separately_cleared_not_echoed_or_in_project');

  await page.locator('#studio-settings-tab-dramaclip').click();
  assert.match(await page.locator('#studio-dramaclip-tools').innerText(),/独立规划运行环境.*需要安装配套本地引擎包/);
  assert.equal((await page.locator('#studio-settings-dialog').innerText()).includes('prepare_dramaclip.py'),false);
  await page.locator('.studio-engine-advanced summary').click();
  await page.locator('[data-target="studio-dramaclip-root"]').click();
  await eventually(async()=>await page.locator('#studio-dramaclip-root').inputValue()==='D:/fixture/DramaClip','folder selected');
  assert.equal(await page.locator('#studio-dramaclip-root').inputValue(),'D:/fixture/DramaClip');
  await page.locator('[data-target="studio-dramaclip-python"]').click();
  await eventually(async()=>await page.locator('#studio-dramaclip-python').inputValue()==='D:/fixture/venv/python.exe','python selected');
  assert.equal(await page.locator('#studio-dramaclip-python').inputValue(),'D:/fixture/venv/python.exe');
  await page.locator('#studio-dramaclip-root').fill('D:/fixture/unsaved-engine');
  await page.locator('[data-studio="settings-refresh"]').click();
  await page.getByText('状态已刷新；当前修改尚未保存。',{exact:true}).waitFor();
  assert.equal(await page.locator('#studio-dramaclip-root').inputValue(),'D:/fixture/unsaved-engine');
  checks.push('native_browse_contract_and_refresh_preserve_unsaved_paths');

  await page.locator('[data-studio="settings-save"]').click();
  await eventually(()=>engineSettings.settings.dramaclip.root==='D:/fixture/unsaved-engine','local settings saved');
  await eventually(async()=>!(await page.locator('[data-studio="settings-save"]').isDisabled()),'save finished');
  assert.equal(requests.at(-1).mediakitKey,undefined);
  assert.match(await page.locator('#studio-dramaclip-status').innerText(),/已就绪/);
  assert.equal(await page.locator('#studio-dramaclip-tools').isVisible(),false);
  assert.equal(await page.locator('#studio-count').inputValue(),'3');assert.equal(await page.locator('#studio-seconds').inputValue(),'77');
  await page.screenshot({path:path.join(out,'settings-local.png')});
  checks.push('local_settings_save_preserves_main_parameters');

  for(const width of [1024,390]){
   await page.setViewportSize({width,height:850});
   assert.equal(await page.locator('#studio-settings-dialog').evaluate(dialog=>dialog.scrollWidth>dialog.clientWidth),false,'dialog overflow at '+width);
   await page.locator('#studio-settings-tab-mediakit').click();
   assert.equal(await page.locator('.studio-settings-panels').evaluate(panel=>panel.scrollWidth>panel.clientWidth),false,'panel overflow at '+width);
   assert.equal(await page.locator('[data-studio="settings-save"]').isVisible(),true);
  }
  await page.screenshot({path:path.join(out,'settings-cloud-mobile.png')});
  checks.push('settings_responsive_at_1024_and_390');

  await page.setViewportSize({width:1440,height:1050});
  await page.locator('#studio-settings-tab-mediakit').press('Escape');
  assert.equal(await page.locator('#studio-settings-dialog').evaluate(dialog=>dialog.open),false);
  assert.equal(await page.evaluate(()=>document.activeElement?.dataset.studio),'settings-open');
  checks.push('escape_closes_dialog_and_restores_focus');

  await page.locator('[data-studio="auto"]').click();await eventually(()=>jobs.length===1,'local one-click queued');
  assert.equal(jobs[0].kind,'promotion_auto');assert.equal(jobs[0].studio.engine,'local');
  for(const key of ['count','seconds','direction','cta','sourcePaths'])assert.deepEqual(jobs[0].studio[key],local[key]);
  assert.deepEqual(fixture.jobs[0].options.studio,jobs[0].studio);
  fixture.jobs[0].status='completed';await page.evaluate(async()=>{await poll();});
  await switchModule('mediakit');await assertModule(cloud);
  await page.locator('#start-pipeline').click();await eventually(()=>jobs.length===2,'cloud taskbar one-click queued');
  assert.equal(jobs[1].kind,'promotion_auto');assert.equal(jobs[1].studio.engine,'mediakit');
  for(const key of ['count','seconds','direction','cta','sourcePaths'])assert.deepEqual(jobs[1].studio[key],cloud[key]);
  assert.equal(JSON.stringify(jobs).includes('FAKE-UI-ONLY-KEY'),false);
  checks.push('both_one_click_actions_submit_independent_engine_snapshots_without_secrets');

  fixture.jobs=[jobFixture('local-result','local'),jobFixture('cloud-result','mediakit'),jobFixture('legacy-dramaclip','dramaclip'),jobFixture('foreign-running','local','running','other-project')];
  project().promotionAnalysis={id:'fixture-analysis',model:'演示文字模型',sources:[clone(project().videos[0])],clips:[{title:'仅本地历史高光方案',reason:'演示历史编排',seconds:24,segments:[{source:0,start:0,end:24,reason:'保留冲突'}]}]};
  project().promotionClips=[
   {id:'local-clip',title:'本地成片 A',seconds:77,engine:'local',sourceKind:'ai_mix',path:'D:/fixture/output/local.mp4'},
   {id:'cloud-clip',title:'云端成片 B',seconds:44,engine:'mediakit',sourceKind:'ai_mix',path:'D:/fixture/output/cloud.mp4'},
   {id:'legacy-fused-clip',title:'旧融合成片 C',seconds:60,engine:'manju-dramaclip',sourceKind:'ai_mix',path:'D:/fixture/output/legacy-fused.mp4'},
   {id:'legacy-local-clip',title:'旧本地成片 D',seconds:60,sourceKind:'ai_mix',path:'D:/fixture/output/legacy-local.mp4'}
  ];
  await page.evaluate(async()=>{await poll();});
  await eventually(async()=>/云端成片 B/.test(await page.locator('#studio-clips').innerText()),'cloud result appears');
  assert.equal(await page.locator('#studio-analysis').count(),0);
  assert.doesNotMatch(await page.locator('#studio-clips').innerText(),/本地成片|旧融合成片/);
  assert.match(await page.locator('#studio-jobs').innerText(),/cloud-result/);
  assert.doesNotMatch(await page.locator('#studio-jobs').innerText(),/local-result|legacy-dramaclip|foreign-running/);
  assert.equal(await page.locator('[data-studio="auto"]').isDisabled(),false,'another project does not block current cloud task');
  checks.push('cloud_results_jobs_are_isolated_and_local_plan_is_absent');

  const cloudResult=fixture.jobs.find(job=>job.id==='cloud-result');
  cloudResult.options.studio.seconds=60;
  cloudResult.status='running';
  cloudResult.progress=45;
  cloudResult.mediakitTask={taskId:'amk-fixture-cloud-task',status:'running'};
  const cloudClip=project().promotionClips.find(clip=>clip.id==='cloud-clip');
  cloudClip.analysisId=cloudResult.id;
  cloudClip.seconds=81.77;
  await page.evaluate(async()=>{await poll();});
  const cloudLink=page.getByRole('link',{name:'打开火山任务',exact:true});
  assert.equal(await cloudLink.getAttribute('href'),'https://console.volcengine.com/imp/ai-mediakit/tool-experience?toolkey=generate-highlights-microdrama&taskid=amk-fixture-cloud-task');
  assert.equal(await cloudLink.getAttribute('target'),'_blank');
  assert.equal(await page.getByLabel('等待火山处理完成').getAttribute('value'),null);
  assert.doesNotMatch(await page.locator('#studio-jobs').innerText(),/45%/);
  cloudResult.status='completed';
  cloudResult.progress=100;
  cloudResult.mediakitTask={taskId:'amk-fixture-cloud-task',status:'completed_local',downloadedCount:2};
  await page.evaluate(async()=>{await poll();});
  assert.match(await page.locator('#studio-jobs').innerText(),/已下载并校验成片 · 2 条/);
  assert.match(await page.locator('#studio-clips').innerText(),/81\.77 秒/);
  assert.match(await page.locator('#studio-clips').innerText(),/比本次设定的 60 秒长 21\.77 秒/);
  checks.push('cloud_task_links_indeterminate_wait_and_reports_actual_duration');

  await switchModule('local');await assertModule(local);
  assert.equal(await page.locator('#studio-analysis').count(),1);
  assert.match(await page.locator('#studio-analysis').textContent(),/仅本地历史高光方案/);
  assert.match(await page.locator('#studio-clips').innerText(),/本地成片 A/);
  assert.match(await page.locator('#studio-clips').innerText(),/旧融合成片 C/);
  assert.match(await page.locator('#studio-clips').innerText(),/旧本地成片 D/);
  assert.doesNotMatch(await page.locator('#studio-clips').innerText(),/云端成片 B/);
  assert.match(await page.locator('#studio-jobs').innerText(),/local-result/);
  assert.match(await page.locator('#studio-jobs').innerText(),/legacy-dramaclip/);
  assert.doesNotMatch(await page.locator('#studio-jobs').innerText(),/cloud-result|foreign-running/);
  assert.equal(await page.locator('#start-pipeline').isDisabled(),false);
  checks.push('local_results_include_legacy_outputs_and_exclude_cloud_or_other_projects');

  await page.evaluate(()=>{window._studioDirection=document.querySelector('#studio-direction');window._studioSource=document.querySelector('#promo-source');});
  project().promotionClips.push({id:'local-polled',title:'轮询新增本地成片 E',seconds:77,engine:'local',path:'D:/fixture/output/local-new.mp4'});
  await page.evaluate(async()=>{await poll();});await page.getByText('轮询新增本地成片 E',{exact:true}).waitFor();
  assert.equal(await page.evaluate(()=>window._studioDirection===document.querySelector('#studio-direction')),true);
  assert.equal(await page.evaluate(()=>window._studioSource===document.querySelector('#promo-source')),true);await assertModule(local);
  checks.push('job_poll_updates_outputs_without_replacing_form_or_video');

  const beforePause=jobs.length;fixture.jobs.push(jobFixture('local-failed','local','failed'),jobFixture('cloud-paused','mediakit','paused'));
  await page.evaluate(async()=>{await poll();});
  await eventually(async()=>await page.locator('[data-studio="auto"]').isDisabled(),'paused same project blocks local button');
  assert.equal(await page.locator('#start-pipeline').isDisabled(),true);
  assert.equal(await page.locator('[data-control="resume"][data-id="local-failed"]').isDisabled(),true,'old failure cannot restart over another same-project paused job');
  assert.doesNotMatch(await page.locator('#studio-jobs').innerText(),/cloud-paused/);
  await page.locator('[data-studio="auto"]').evaluate(button=>button.click());
  await switchModule('mediakit');assert.match(await page.locator('#studio-jobs').innerText(),/cloud-paused/);
  assert.equal(await page.locator('[data-control="resume"][data-id="cloud-paused"]').isDisabled(),false,'original paused task remains resumable');
  assert.equal(await page.locator('[data-studio="auto"]').isDisabled(),true);assert.equal(await page.locator('#start-pipeline').isDisabled(),true);
  await page.locator('#start-pipeline').evaluate(button=>button.click());
  assert.equal(jobs.length,beforePause,'paused same project blocks duplicates in both modules');
  fixture.jobs=fixture.jobs.filter(job=>job.id!=='cloud-paused');await page.evaluate(async()=>{await poll();});
  await eventually(async()=>!(await page.locator('[data-studio="auto"]').isDisabled()),'removing blocker reenables submit');
  checks.push('paused_same_project_blocks_both_submissions_other_project_does_not');

  await page.locator('[data-studio="settings-open"][data-tab="mediakit"]').first().click();
  assert.equal(await page.locator('#studio-settings-tab-mediakit').getAttribute('aria-selected'),'true');
  await page.locator('[data-studio="settings-clear-key"]').click();await eventually(()=>!engineSettings.mediakit.hasKey,'session key cleared');
  await eventually(async()=>!(await page.locator('[data-studio="settings-save"]').isDisabled()),'clear complete');
  assert.equal(requests.at(-1).clearMediakitKey,true);assert.equal(requests.at(-1).mediakitKey,undefined);
  assert.equal(await page.locator('#studio-mediakit-key-status').innerText(),'尚未设置');
  checks.push('session_key_clear_explicit_and_status_updated');

  await page.locator('#studio-settings-tab-mediakit').press('Escape');
  fixture.jobs=fixture.jobs.filter(job=>!['foreign-running','local-failed'].includes(job.id));await page.evaluate(async()=>{await poll();});
  await page.locator('#toast').waitFor({state:'hidden'});
  await page.evaluate(()=>window.scrollTo(0,0));
  await page.mouse.move(500,30);await page.waitForTimeout(350);
  await page.screenshot({path:path.join(out,'promotion-cloud-module.png'),fullPage:true});
  await switchModule('local');await page.evaluate(()=>window.scrollTo(0,0));
  await page.mouse.move(500,30);await page.waitForTimeout(350);
  await page.screenshot({path:path.join(out,'promotion-local-module.png'),fullPage:true});
  fixture.jobs=[];await page.evaluate(async()=>{await poll();});
  await page.locator('#nav a[href="#logs"]').click();
  await page.locator('#log-query').waitFor();
  assert.equal(await page.locator('[data-studio="settings-open"]').count(),0);
  fixture.projects=[];
  await page.goto(base+'/#promotion');await page.reload();await page.locator('#studio-module-local').waitFor();
  for(const engine of ['local','mediakit']){
   await page.locator('#studio-module-'+engine).click();
   assert.equal(await page.locator('#studio-module-'+engine).getAttribute('aria-selected'),'true');
   assert.equal(await page.locator('#studio-count,[data-studio="auto"]').count(),0,'empty module has no runnable production form');
   assert.equal(await page.locator('#start-pipeline').isDisabled(),true);
   const tab=engine==='local'?'dramaclip':'mediakit';
   await page.locator('[data-studio="settings-open"][data-tab="'+tab+'"]').first().click();
   assert.equal(await page.locator('#studio-settings-tab-'+tab).getAttribute('aria-selected'),'true');
   await page.locator('#studio-settings-tab-'+tab).press('Escape');
  }
  checks.push('both_empty_modules_remain_configurable_without_sources_or_submit_actions');
  assert.deepEqual(pageErrors,[]);assert.deepEqual(externalRequests,[]);checks.push('page_scoped_setting_no_browser_errors_or_external_requests');
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({ok:true,checks,pageErrors,cloudCalls:0,fixtureOnly:true,studioSettingsSaves:studioRequests.length,screenshots:['promotion-local-module.png','promotion-cloud-module.png','settings-local.png','settings-cloud-mobile.png']},null,2));
  console.log('PROMOTION_ENGINES_UI_OK '+checks.length+' checks; '+out);
 }catch(error){console.error('Browser runtime errors:',pageErrors);await page.screenshot({path:path.join(out,'failure.png'),fullPage:true}).catch(()=>{});throw error;}
 finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
