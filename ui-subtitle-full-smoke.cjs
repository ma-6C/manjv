const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/subtitle-full-ui-host.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1100}}),checks=[],errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 const check=(name,value)=>{if(!value)throw Error(name);checks.push(name);console.log('PASS '+name);};
 const request=async(name,body)=>{const r=await page.request[body?'post':'get'](meta.url+'/api/'+name,body?{data:body,headers:{'X-Local-Client':'1'}}:{});const j=await r.json();if(!r.ok())throw Error(j.error);return j;};
 async function waitJob(id){const end=Date.now()+120000;while(Date.now()<end){const s=await request('state'),j=s.jobs.find(j=>j.id===id);if(!['queued','running','pausing'].includes(j.status)){check('UI job completed '+id,j.status==='completed');return {s,j};}await page.waitForTimeout(200);}throw Error('UI job timed out');}
 try{
  await page.goto(meta.launch);await request('config',{subtitleMode:'local',subtitleFirst:1});await page.goto(meta.url+'/#subtitle');
  await page.waitForSelector('[data-action="subtitle-full"]');
  await page.locator('#project-picker').selectOption(meta.realProjectId);
  await page.waitForFunction(()=>document.querySelector('#subtitle-full-scope')?.textContent.includes('36'));
  check('whole_video_actions_visible_above_preview',(await page.locator('[data-action="subtitle-full"]').count())===2);
  check('legacy_first_N_control_removed',await page.locator('#config-subtitleFirst').count()===0);
  check('5_and_10_second_previews_retained',await page.locator('[data-action="subtitle-preview"]').count()===2);
  check('full_duration_summary_exceeds_10_seconds',(await page.locator('#subtitle-full-scope').textContent()).includes('0:36'));
  const before=await request('state'),project=before.projects.find(p=>p.id===meta.realProjectId);
  const submit=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('[data-action="subtitle-full"][data-scope="current"]').click();const response=await submit,body=response.request().postDataJSON(),one=await response.json();
  check('current_button_submits_one_exact_full_source',body.kind==='subtitle'&&body.sourceVideoPaths[project.id].length===1&&body.sourceVideoPaths[project.id][0]===project.videos[0].path);
  const oneDone=await waitJob(one.id);
  check('current_job_covers_full_video_not_preview',oneDone.j.kind==='subtitle'&&oneDone.j.options.subtitleAllSelected&&oneDone.j.options.sourceVideoPaths[project.id].length===1);
  await page.waitForFunction(()=>document.querySelector('#subtitle-full-result')?.textContent.includes('已完成 1 / 1 集'));
  check('completed_result_has_play_and_download',await page.locator('#subtitle-full-result [data-action="play-output"]').count()===1&&await page.locator('#subtitle-full-result a[download],#subtitle-full-result a[href*="download=1"]').count()>0);
  const seriesResponse=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('[data-action="subtitle-full"][data-scope="series"]').click();const sr=await seriesResponse,series=await sr.json(),seriesBody=sr.request().postDataJSON();
  check('series_button_submits_every_episode_in_order',JSON.stringify(seriesBody.sourceVideoPaths[project.id])===JSON.stringify(project.videos.map(v=>v.path)));
  const done=await waitJob(series.id);
  check('series_job_has_two_outputs_without_confirmation',done.s.projects.find(p=>p.id===project.id).artifacts.filter(a=>a.job===series.id).length===2);
  await page.waitForFunction(()=>document.querySelector('#subtitle-full-result')?.textContent.includes('已完成 2 / 2 集'));
  // Failure appears inline and focuses a readable recovery message.
  await request('config',{subtitleMode:'vsr',vsrRoot:'',vsrPython:''});await page.reload();await page.waitForSelector('[data-action="subtitle-full"]');
  await page.locator('[data-action="subtitle-full"][data-scope="current"]').click();
  await page.waitForSelector('#subtitle-full-error:visible');
  check('missing_engine_error_is_inline_and_focusable',await page.locator('#subtitle-full-error').evaluate(el=>el===document.activeElement&&el.textContent.includes('引擎')));
  await page.waitForTimeout(2200);check('error_remains_visible_across_background_refresh',await page.locator('#subtitle-full-error').isVisible());
  const engine=JSON.parse(fs.readFileSync('engines/vsr-install.json','utf8'));await request('config',{subtitleMode:'vsr',vsrRoot:engine.root,vsrPython:engine.python,vsrMode:'sttn-auto'});
  await page.reload();await page.waitForSelector('[data-action="subtitle-full"]');
  await page.locator('#project-picker').selectOption(meta.realProjectId);await page.screenshot({path:path.join(meta.base,'整片去字幕-桌面界面.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});await page.screenshot({path:path.join(meta.base,'整片去字幕-窄窗口.png'),fullPage:true});
  check('narrow_layout_has_no_horizontal_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
  check('no_javascript_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(meta.base,'ui-report.json'),JSON.stringify({ok:true,checks,errors,modelCalls:'local delogo used for UI scope checks; real STTN coverage is recorded separately in report.json'},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
