'use strict';
// Actual Edge rendering and client scripts; API failures are deliberately simulated.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=__dirname,web=path.join(root,'web'),out=path.join(root,'tmp','connection-recovery-ui');
const fixture={config:{source:'',output:'',costRows:[],subtitleRegion:{x:.05,y:.7,w:.9,h:.18},subtitleRegions:[],segmentSeconds:40,width:1080,height:1920,aiConnections:[],aiSelection:{}},projects:[{id:'fixture',name:'原剧名',originalName:'原剧名',intro:'原简介',videos:[],artifacts:[],rights:true}],jobs:[],logs:[],accounts:[],secrets:{},aiProviders:[],connectionKeyStatus:{}};
let stateFailures=0,stateCalls=0,environmentFailure=false,stateGate=null,stateReached=null,configGate=null,configReached=null;
const server=http.createServer((req,res)=>{const target=path.resolve(web,'.'+new URL(req.url,'http://localhost').pathname.replace(/^\/$/,'/index.html'));if(!target.startsWith(web+path.sep)){res.writeHead(404).end();return;}fs.readFile(target,(error,data)=>{res.writeHead(error?404:200,{'Content-Type':target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html; charset=utf-8'});res.end(error?'':data);});});
const checks=[],errors=[];
function check(name,condition){assert.ok(condition,name);checks.push(name);console.log('PASS '+name);}
(async()=>{
 fs.mkdirSync(out,{recursive:true});await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:950}});page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
   const endpoint=new URL(route.request().url()).pathname.slice(5);let result={};
   if(endpoint==='state'){stateCalls++;if(stateGate){stateReached();await stateGate;}if(stateFailures>0){stateFailures--;return route.fulfill({status:503,json:{error:'模拟：引擎启动未完成'}});}result=structuredClone(fixture);}
   else if(endpoint==='environment'){if(environmentFailure)return route.fulfill({status:503,json:{error:'模拟：硬件检测失败'}});result={ffmpeg:true,cores:4,python:'fixture',font:true,gpu:{available:false,adapters:[],detail:'isolated'}};}
   else if(endpoint==='config'){if(configGate){configReached();await configGate;}Object.assign(fixture.config,route.request().postDataJSON());result={config:fixture.config};}
   else if(endpoint==='source/tasks')result={tasks:[],access:{},native:{}};
   else if(endpoint==='promotion/engines')result={settings:{dramaclip:{},mediakit:{}},dramaclip:{ready:false,missing:[]},mediakit:{hasKey:false}};
   else if(endpoint==='malformed')return route.fulfill({status:502,contentType:'text/html',body:'<p>Unavailable</p>'});
   else if(endpoint==='slow')return route.abort('timedout');
   return route.fulfill({json:result});
  });
  const base='http://127.0.0.1:'+server.address().port;
  environmentFailure=true;await page.goto(base+'/#text');await page.locator('#edit-name').waitFor();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('环境检测未完成'));
  check('environment_failure_keeps_workspace_usable',await page.locator('#edit-name').isVisible()&&await page.locator('#content .error-banner').count()===0);
  const previous=stateCalls;await page.evaluate(()=>poll());check('environment_failure_does_not_stop_state_updates',stateCalls>previous);
  stateFailures=1;await page.evaluate(()=>poll());check('connection_failure_is_visible',(await page.locator('#service-status').innerText()).includes('自动重连'));
  await page.evaluate(()=>poll());check('connection_recovery_restores_status_text',(await page.locator('#service-status').innerText()).includes('本地引擎已连接'));
  check('non_json_http_failure_has_actionable_message',(await page.evaluate(async()=>{try{await api('malformed');}catch(error){return error.message;}})).includes('HTTP 502'));
  environmentFailure=false;stateFailures=1;await page.reload();await page.locator('[data-action="retry-connection"]').waitFor();
  check('initial_failure_offers_retry',await page.locator('#content [role="alert"]').isVisible());
  await page.locator('[data-action="retry-connection"]').click();await page.locator('#edit-name').waitFor();check('manual_retry_recovers_without_restart',await page.locator('#edit-name').inputValue()==='原剧名');
  stateFailures=1;await page.reload();await page.locator('#edit-name').waitFor({timeout:8000});check('initial_failure_automatically_retries',await page.locator('#content .error-banner').count()===0);
  fixture.jobs=[{id:'background',kind:'cover',status:'running',ids:['fixture'],created:Date.now()/1000,progress:5,stage:'后台制作',config:{}}];
  await page.evaluate(()=>poll());await page.locator('#edit-name').fill('尚未保存的剧名');await page.locator('#edit-intro').fill('正在编写的新简介');await page.locator('#edit-intro').blur();
  fixture.jobs[0].status='completed';fixture.jobs[0].progress=100;await page.evaluate(()=>poll());
  check('background_completion_preserves_unsaved_project_text',await page.locator('#edit-name').inputValue()==='尚未保存的剧名'&&await page.locator('#edit-intro').inputValue()==='正在编写的新简介');
  fixture.jobs[0].status='running';await page.reload();await page.locator('#edit-name').waitFor();
  let releaseState;stateGate=new Promise(resolve=>releaseState=resolve);const reached=new Promise(resolve=>stateReached=resolve);
  const pendingPoll=page.evaluate(()=>poll());await reached;
  await page.locator('#edit-name').fill('等待状态响应时输入的剧名');await page.locator('#edit-name').blur();fixture.jobs[0].status='completed';
  const release=releaseState;stateGate=null;release();await pendingPoll;
  check('editing_during_inflight_poll_is_preserved',await page.locator('#edit-name').inputValue()==='等待状态响应时输入的剧名');
  await page.evaluate(()=>window._draftNode=document.querySelector('#edit-name'));
  fixture.projects[0].name='等待状态响应时输入的剧名';await page.evaluate(()=>refresh());await page.evaluate(()=>poll());
  check('deferred_completion_refreshes_after_draft_is_saved',await page.locator('#edit-name').evaluate(element=>element!==window._draftNode));
  fixture.config.costRows=[{name:'验收成本',amount:1}];fixture.jobs[0].status='running';await page.evaluate(()=>refresh());await page.goto(base+'/#cost');await page.locator('[data-cost-amount="0"]').waitFor();
  let releaseConfig;configGate=new Promise(resolve=>releaseConfig=resolve);const savingReached=new Promise(resolve=>configReached=resolve);
  await page.locator('[data-cost-amount="0"]').fill('250');await page.locator('[data-cost-amount="0"]').blur();await savingReached;
  fixture.jobs[0].status='completed';await page.evaluate(()=>poll());
  check('completion_preserves_values_while_autosave_is_pending',await page.locator('[data-cost-amount="0"]').inputValue()==='250');
  const finishSaving=releaseConfig;configGate=null;finishSaving();await page.waitForFunction(()=>configSavesPending===0);await page.evaluate(()=>poll());
  check('deferred_refresh_uses_successfully_saved_cost',await page.locator('[data-cost-amount="0"]').inputValue()==='250');
  check('caller_abort_works_without_abortsignal_any',await page.evaluate(async()=>{const previous=AbortSignal.any;try{AbortSignal.any=undefined;const controller=new AbortController();controller.abort();try{await api('state',undefined,{signal:controller.signal});}catch(error){return error.name==='AbortError';}return false;}finally{AbortSignal.any=previous;}}));
  Object.assign(fixture.config,{subtitleMode:'vsr',vsrMode:'lama-box',subtitlePreserveTailSeconds:0,sttnDevice:'auto',lamaDevice:'auto'});
  fixture.projects[0].videos=[{path:'fixture-before.mp4',name:'示例.mp4',duration:12,width:320,height:180,audio:true,codec:'h264',bytes:1024}];
  fixture.jobs.push({id:'old-preview',kind:'preview',status:'completed',ids:['fixture'],options:{videoIndex:0},result:{before:'fixture-before.mp4',after:'fixture-after.mp4',start:0,seconds:5,regions:[fixture.config.subtitleRegion],mode:'vsr',engine:'lama-box'}});
  await page.evaluate(async()=>{await refresh();studioIndex=0;});await page.goto(base+'/#subtitle');
  await page.locator('#subtitle-preview-result .preview-summary').waitFor();
  check('legacy_preview_defaults_to_zero_tail_setting',await page.locator('#subtitle-preview-result .preview-summary b').count()===0);
  await page.locator('[data-action="subtitle-settings-open"]').click();await page.locator('[data-tab="local"]').click();
  const tail=page.locator('#config-subtitlePreserveTailSeconds');
  await tail.fill('2');await tail.blur();await page.waitForFunction(()=>configSavesPending===0);
  check('subtitle_tail_setting_saves_from_real_control',fixture.config.subtitlePreserveTailSeconds===2&&await tail.inputValue()==='2');
  await page.evaluate(()=>updatePreviewResult());
  check('changed_tail_setting_marks_existing_preview_stale',(await page.locator('#subtitle-preview-result .preview-summary b').innerText()).includes('片尾保留'));
  fixture.jobs.at(-1).result.configuredPreserveTailSeconds=2;
  await page.evaluate(async()=>{await refresh();updatePreviewResult();});
  check('matching_tail_setting_keeps_preview_current',await page.locator('#subtitle-preview-result .preview-summary b').count()===0);
  await page.locator('#config-vsrMode').selectOption('lama-text');await page.waitForFunction(()=>configSavesPending===0);
  check('white_caption_mode_preserves_tail_setting',fixture.config.vsrMode==='lama-text'&&fixture.config.subtitlePreserveTailSeconds===2&&await tail.isVisible());
  Object.assign(fixture.jobs.at(-1).result,{engine:'lama-text',inferredFrames:0});
  await page.evaluate(async()=>{await refresh();updatePreviewResult();});
  check('white_caption_preview_reports_no_matching_text',(await page.locator('#subtitle-preview-result .preview-summary').innerText()).includes('未匹配到深色描边白字'));
  await page.locator('#config-vsrMode').selectOption('sttn-det');await page.waitForFunction(()=>configSavesPending===0);
  check('unsupported_subtitle_model_resets_tail_setting',fixture.config.subtitlePreserveTailSeconds===0&&await tail.count()===0);
  await page.locator('#config-vsrMode').selectOption('lama-box');await page.waitForFunction(()=>configSavesPending===0);
  check('returning_to_supported_model_restores_tail_control',await tail.isVisible()&&await tail.inputValue()==='0');
  await tail.fill('2');await tail.blur();await page.waitForFunction(()=>configSavesPending===0);
  await page.locator('[data-tab="production"]').click();await page.locator('#config-subtitleMode').selectOption('local');await page.waitForFunction(()=>configSavesPending===0);
  check('switching_subtitle_mode_clears_inapplicable_tail_setting',fixture.config.subtitlePreserveTailSeconds===0&&await tail.count()===0);
  await page.screenshot({path:path.join(out,'recovered-workspace.png')});check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({ok:true,passed:checks.length,checks,errors,scope:'Client recovery with simulated API failures; no real accounts or model requests.'},null,2));
  console.log(JSON.stringify({passed:checks.length,out}));
 }finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(error=>{console.error(error);server.close();process.exitCode=1;});
