// App UI acceptance. Cloud replies are explicitly simulated by test_connections_host.py.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/current-connections-test.json','utf8')),service=JSON.parse(fs.readFileSync(path.join(meta.base,'service.json'),'utf8'));
 const out=path.join(meta.base,'ui');fs.mkdirSync(out,{recursive:true});
 async function api(name,body){const r=await fetch(meta.url+'/api/'+name,body?{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify(body)}:{cache:'no-store'});const j=await r.json();if(!r.ok)throw Error(j.error);return j;}
 async function wait(predicate,timeout=60000){const end=Date.now()+timeout;while(Date.now()<end){const s=await api('state');if(predicate(s))return s;await new Promise(r=>setTimeout(r,100));}throw Error('Backend condition timeout');}
 for(const j of (await api('state')).jobs)if(['queued','running','pausing'].includes(j.status))await api('jobs/control',{id:j.id,action:'cancel'});
 await wait(s=>!s.jobs.some(j=>['queued','running','pausing'].includes(j.status)));
 for(const c of (await api('state')).config.aiConnections)await api('ai/connections',{action:'delete',id:c.id});
 await api('config',{source:service.source,output:path.join(meta.base,'output'),width:320,height:180,segmentSeconds:1,subtitleAuto:false,subtitleMode:'local',autoText:false,autoCover:false,autoRecords:true});
 const project=(await api('scan',{source:service.source})).projects[0];
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
 const report={simulation:true,realCloudGeneration:false,checks:[]};
 try{
  await page.goto(meta.url);await page.locator('#content h1').waitFor();
  for(const id of ['scan','preprocess','transform','parallel','subtitle','generate','cost','api','text','highlight','publish','logs']){await page.locator(`#nav a[href="#${id}"]`).click();if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow: '+id);}
  report.checks.push('all_12_pages_render_without_horizontal_overflow');
  await page.locator('#nav a[href="#api"]').click();await page.locator('[data-action="connection-new"]').first().click();await page.locator('[data-action="connection-save"]').click();await page.locator('#connection-form-error').waitFor({state:'visible'});if(await page.locator('#connection-name').getAttribute('aria-invalid')!=='true')throw Error('Missing form error');await page.locator('[data-action="connection-close"]').click();report.checks.push('accessible_validation_summary_and_field_error');
  async function add(name,channel,key,model){
   await page.locator('[data-action="connection-new"]').first().click();await page.locator('#connection-channel').selectOption(channel);
   await page.locator('#connection-name').fill(name);await page.locator('#connection-base').fill('https://mock.invalid/v1');await page.locator('#connection-model').fill(model);await page.locator('#connection-key').fill(key);
   const response=page.waitForResponse(r=>r.url().endsWith('/api/ai/connections')&&r.request().method()==='POST');await page.locator('[data-action="connection-save"]').click();const j=await(await response).json();if(!j.id)throw Error(JSON.stringify(j));await page.locator('#connection-dialog').waitFor({state:'hidden'});await page.locator(`[data-connection-row="${j.id}"]`).waitFor();return j.id;
  }
  const primary=await add('文字主用','text','fixture-secret-primary','fixture-text'),backup=await add('文字备用','text','fixture-secret-backup','fixture-text');
  const videoA=await add('视频主用','video','fixture-secret-video-a','fixture-video-a'),videoB=await add('视频备用','video','fixture-secret-video-b','fixture-video-b'),image=await add('封面服务','image','fixture-secret-image','fixture-image');
  report.connectionIds={primary,backup,videoA,videoB,image};report.checks.push('add_multiple_connections_same_platform_and_separate_keys');
  await page.locator('#backup-add-text').selectOption(backup);await page.locator('[data-action="backup-add"][data-channel="text"]').click();await page.locator('[data-route-fallback="text"]').check();await wait(s=>s.config.aiRouting.text.autoFallback);
  await page.locator('#backup-add-video').selectOption(videoB);await page.locator('[data-action="backup-add"][data-channel="video"]').click();await page.locator('[data-route-fallback="video"]').check();await wait(s=>s.config.aiRouting.video.autoFallback);
  await page.locator(`[data-action="connection-test"][data-id="${backup}"]`).click();await wait(s=>s.aiConnectionTests?.[backup]?.ok===true);
  await page.locator(`[data-connection-row="${backup}"]`).getByText('文字调用通过',{exact:false}).waitFor();
  await page.locator('.connection-row').first().waitFor();await page.locator('#connection-list').screenshot({path:path.join(out,'多API连接列表.png')});
  await api('config',{autoText:true,autoCover:true,autoAICover:true});
  await page.locator('#nav a[href="#scan"]').click();await page.locator(`[data-select="${project.id}"]`).check();
  await page.locator('[data-action="task-api-dialog"]').click();await page.locator('#dialog-api-text').selectOption('auto');await page.locator('[data-action="task-api-close"]').click();
  let response=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('#start-pipeline').click();const pipeline=(await(await response).json()).id;
  let s=await wait(s=>['completed','failed'].includes(s.jobs.find(j=>j.id===pipeline)?.status)),job=s.jobs.find(j=>j.id===pipeline);if(job.status!=='completed')throw Error(JSON.stringify(job));if(!job.aiAttempts.some(x=>x.event==='fallback'&&x.connectionId===primary)||!job.aiAttempts.some(x=>x.event==='succeeded'&&x.connectionId===backup)||!job.aiAttempts.some(x=>x.channel==='image'&&x.event==='succeeded'))throw Error('Missing actual routed pipeline stages');report.checks.push('pipeline_primary_rate_limit_then_backup_and_selected_ai_cover');
  await page.locator('#nav a[href="#text"]').click();await page.locator('#task-api-text').selectOption(backup);await wait(s=>s.config.aiSelection.text===backup);
  response=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('[data-action="job"][data-kind="rewrite"]').click();const fixed=(await(await response).json()).id;s=await wait(s=>['completed','failed'].includes(s.jobs.find(j=>j.id===fixed)?.status));job=s.jobs.find(j=>j.id===fixed);if(job.status!=='completed'||job.aiAttempts.some(x=>x.connectionId!==backup))throw Error('Fixed API selection not respected');report.checks.push('per_task_explicit_connection_does_not_use_other_accounts');
  await page.locator('#nav a[href="#generate"]').click();await page.locator('#task-api-video').selectOption(videoB);await wait(s=>s.config.aiSelection.video===videoB);
  await page.locator('#generation-name').fill('图生视频接口验收');await page.locator('#generation-prompt').fill('小猫坐在窗边，镜头缓慢推进，温暖夕阳。');await page.locator('#generation-mode').selectOption('image');await page.locator('#generation-reference').fill(service.reference);
  await page.locator('#content').screenshot({path:path.join(out,'生成视频自由选择接口.png')});
  response=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('#content [data-action="generation-start"]').click();const generated=(await(await response).json()).id;if(!generated)throw Error('Video job missing');
  s=await wait(s=>['completed','failed'].includes(s.jobs.find(j=>j.id===generated)?.status));job=s.jobs.find(j=>j.id===generated);if(job.status!=='completed'||job.result.connectionId!==videoB)throw Error(JSON.stringify(job));
  if(!s.projects.some(p=>p.id===job.result.projectId&&p.finalVideoPaths.includes(job.result.path)))throw Error('Result missing from library');report.checks.push('image_to_video_selected_api_polls_downloads_imports_into_library');
  await page.locator('[data-action="play-output"]').first().click();await page.locator('#output-video').evaluate(v=>{v.muted=true;return v.play()});await page.waitForFunction(()=>document.querySelector('#output-video').currentTime>.15);await page.locator('[data-action="close-output"]').click();report.checks.push('downloaded_result_really_plays');
  await page.locator('#nav a[href="#logs"]').click();await page.locator('.ai-attempts').first().waitFor();await page.screenshot({path:path.join(out,'主备切换与任务记录.png'),fullPage:true});
  await page.setViewportSize({width:1024,height:768});for(const id of ['api','generate','preprocess','logs']){await page.locator(`#nav a[href="#${id}"]`).click();if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('1024px overflow: '+id);}report.checks.push('minimum_desktop_width_1024');
  if(errors.length)throw Error(errors.join('\n'));report.ok=true;report.jobs={pipeline,fixed,generated};report.errors=errors;
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify({ok:true,base:meta.base,checks:report.checks}));
 }catch(error){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({...report,ok:false,error:error.message,errors},null,2));throw error;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
