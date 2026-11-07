'use strict';
// Source-only UI check, all APIs are fixtures and no production state is loaded.
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('assert/strict');
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=__dirname,web=path.join(root,'web'),out=path.join(root,'tmp','library-advanced-ui');
const fixture={config:{source:'D:/fixture',output:'D:/fixture/output',costRows:[],subtitleRegion:{x:.05,y:.7,w:.9,h:.18},subtitleRegions:[],subtitleMethod:'vsr',vsrModel:'sttn-auto',vsrDevice:'auto',segmentSeconds:40,regroup:true,width:1080,height:1920,subtitleAuto:false,autoText:false,autoCover:false,autoRecords:false,autoCost:false,pipelineHighlight:false,speed:1,highlightCount:1,highlightFixed:1,highlightMin:.5,highlightMax:1,highlightRandom:true,highlightTailChoice:'random',aiConnections:[],aiSelection:{},trackSheet:{}},projects:[{id:'fixture-project',name:'演示剧集',originalName:'演示剧集',source:'D:/fixture',intro:'隔离检查',rights:true,videos:[{name:'第0001集.mp4',path:'D:/fixture/01.mp4',duration:90,bytes:12345,width:720,height:1280,audio:true}],artifacts:[],promotionStudio:{engine:'local',count:2,seconds:60},promotionClips:[]}],jobs:[],logs:[],accounts:[],secrets:{},aiProviders:[],connectionKeyStatus:{}};
const submissions=[];
fixture.projects.push({...structuredClone(fixture.projects[0]),id:'second-project',name:'另一部剧',originalName:'另一部剧'});
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8'};
const server=http.createServer((req,res)=>{const url=new URL(req.url,'http://127.0.0.1');const target=path.resolve(web,'.'+(url.pathname==='/'?'/index.html':decodeURIComponent(url.pathname)));if(!target.startsWith(web+path.sep)){res.writeHead(404).end();return;}fs.readFile(target,(err,data)=>{res.writeHead(err?404:200,{'Content-Type':types[path.extname(target)]||'text/plain'});res.end(err?'':data);});});
(async()=>{
 fs.mkdirSync(out,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:950}}),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/api/**',route=>{const endpoint=new URL(route.request().url()).pathname.slice(5);let result={};
  if(endpoint==='state')result=fixture;
  else if(endpoint==='environment')result={ffmpeg:true,cores:8,python:'3.12',font:true,gpu:{available:false,adapters:[],detail:'隔离环境'}};
  else if(endpoint==='component')result={active:{},progress:{}};
  else if(endpoint==='license')result={valid:true,customer:'隔离演示'};
  else if(endpoint==='source/tasks')result={tasks:[],access:{},native:{}};
  else if(endpoint==='promotion/engines')result={settings:{dramaclip:{},mediakit:{}},dramaclip:{ready:false,missing:[]},mediakit:{hasKey:false}};
  else if(endpoint==='publish/workspace')result={accounts:[],tasks:[],browser:{}};
  else if(endpoint==='config'){Object.assign(fixture.config,route.request().postDataJSON());result={config:fixture.config};}
  else if(endpoint==='jobs'){submissions.push(route.request().postDataJSON());result={id:'fixture-task-'+submissions.length};}
  else if(endpoint==='file')return route.fulfill({status:204,body:''});
  return route.fulfill({json:result});
 });
 function check(name,value){assert(value,name);checks.push(name);}
 try{
  const base='http://127.0.0.1:'+server.address().port;
  await page.goto(base+'/#scan');await page.locator('#scan-advanced-processing').waitFor({state:'attached'});
  check('preprocess_navigation_and_renderer_removed',await page.evaluate(()=>!pages.some(p=>p[0]==='preprocess')&&typeof preprocessPage==='undefined'));
  check('no_preprocess_links',await page.locator('[href="#preprocess"]').count()===0);
  check('advanced_closed_by_default',!await page.locator('#scan-advanced-processing').evaluate(e=>e.open));
  await page.locator('#scan-advanced-processing>summary').click();
  check('saved_regroup_options_available',await page.locator('[data-config=regroup]').isChecked()&&await page.locator('#config-segmentSeconds').inputValue()==='40');
  await page.locator('#config-segmentSeconds').fill('63');await page.locator('#config-segmentSeconds').press('Tab');
  await page.waitForFunction(()=>state.config.segmentSeconds===63);
  check('moved_controls_save_original_keys',fixture.config.segmentSeconds===63);
  await page.locator('[data-config=subtitleAuto]').check();await page.waitForFunction(()=>state.config.subtitleAuto===true);
  await page.evaluate(()=>updateWorkflowUI());
  check('continuous_plan_updates_in_new_location',(await page.locator('#production-run-summary').innerText()).includes('先修复字幕'));
  check('batch_disabled_until_library_selection',await page.locator('[data-production-batch]').isDisabled());
  await page.locator('#select-all').check();check('library_selection_updates_batch',await page.locator('[data-production-batch]').isEnabled()&&(await page.locator('#production-batch-count').innerText()).includes('2 部'));
  await page.locator('[data-production-batch]').click();await page.waitForFunction(()=>current==='progress');
  check('batch_job_keeps_selected_order',submissions.at(-1).kind==='pipeline'&&JSON.stringify(submissions.at(-1).ids)===JSON.stringify(['fixture-project','second-project']));
  await page.goto(base+'/#preprocess');await page.waitForFunction(()=>current==='scan'&&document.querySelector('#scan-advanced-processing')?.open);
  check('old_bookmark_redirects_and_opens_advanced',page.url().endsWith('/#scan'));
  await page.locator('#project-picker').selectOption('second-project');
  await page.locator('[data-action=job][data-kind=transcode]').click();await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('单步任务'));
  check('regroup_only_uses_current_project',submissions.at(-1).kind==='transcode'&&JSON.stringify(submissions.at(-1).ids)===JSON.stringify(['second-project']));
  await page.goto(base+'/#processing');await page.waitForFunction(()=>document.querySelector('#scan-advanced-processing')?.open);
  check('new_deep_link_opens_advanced',page.url().endsWith('/#scan'));
  check('saved_options_survive_reload',await page.locator('#config-segmentSeconds').inputValue()==='63');
  await page.locator('[data-preset=source]').click();await page.waitForFunction(()=>state.config.width===720&&state.config.height===1280);
  check('source_size_preset_preserved',await page.locator('#config-width').inputValue()==='720');
  for(const id of ['subtitle','transform','highlight','tracks','text','cost','promotion','publish','progress','logs','parallel','license','sources']){
   await page.evaluate(id=>{current=id;renderPage();},id);check(id+'_independent_module_available',await page.locator('#content').innerText().then(t=>t.trim().length>0));
  }
  await page.goto(base+'/#processing');await page.waitForFunction(()=>document.querySelector('#scan-advanced-processing')?.open);
  await page.waitForTimeout(150);await page.mouse.move(0,0);await page.screenshot({path:path.join(out,'advanced-desktop.png'),fullPage:true});
  for(const width of [1024,390]){
   await page.setViewportSize({width,height:950});
   check('advanced_no_horizontal_overflow_'+width,await page.locator('#scan-advanced-processing').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  }
  await page.screenshot({path:path.join(out,'advanced-mobile.png'),fullPage:true});
  check('no_browser_errors',errors.length===0||(()=>{console.error(JSON.stringify({browserErrors:errors}));return false;})());
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({checks,errors},null,2));
  console.log(JSON.stringify({passed:checks.length,errors,out}));
 }finally{await browser.close();await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
