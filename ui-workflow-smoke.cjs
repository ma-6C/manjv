const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/workflow-ui-service.json','utf8'));
 const out=path.join(meta.base,'ui');fs.mkdirSync(out,{recursive:true});
 const engine=JSON.parse(fs.readFileSync('engines/vsr-install.json','utf8'));
 const backend=JSON.parse(fs.readFileSync(meta.report,'utf8'));
 async function api(name,body){const r=await fetch(meta.url+'/api/'+name+(body?'':'?test='+Date.now()+Math.random()),body?{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify(body)}:{cache:'no-store'});const j=await r.json();if(!r.ok)throw Error(JSON.stringify(j));return j;}
 async function waitApi(predicate,timeout=180000){const end=Date.now()+timeout;while(Date.now()<end){const s=await api('state');if(predicate(s))return s;await new Promise(r=>setTimeout(r,150));}throw Error('Timed out waiting for backend condition');}
 for(const j of (await api('state')).jobs)if(['queued','running','pausing'].includes(j.status))await api('jobs/control',{id:j.id,action:'cancel'});
 await api('config',{subtitleMode:'vsr',vsrRoot:engine.root,vsrPython:engine.python,vsrMode:'sttn-auto',subtitleAuto:false,pipelineHighlight:false,autoText:false,autoCover:false,autoRecords:false,width:1254,height:720});
 const recovery=(await api('state')).projects.find(p=>p.id===backend.recoveryProjectId);
 await api('scan',{source:recovery.source});
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});const errors=[];page.on('pageerror',e=>errors.push(e.message));
 try{
  await page.goto(meta.url);await page.locator('#content h1').waitFor();
  for(const id of ['scan','preprocess','transform','parallel','subtitle','cost','api','text','highlight','publish','logs']){
   await page.locator(`#nav a[href="#${id}"]`).click();await page.waitForFunction(id=>location.hash==='#'+id,id);
   if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Overflow: '+id);
  }
  await page.locator('#nav a[href="#scan"]').click();await page.locator(`[data-select="${backend.recoveryProjectId}"]`).check();
  await page.locator('#nav a[href="#subtitle"]').click();await page.locator('#project-picker').selectOption(backend.recoveryProjectId);
  await page.locator('#studio-video').selectOption('1');
  await waitApi(s=>s.projects.find(p=>p.id===backend.recoveryProjectId).sourcePreviewPaths?.[recovery.videos[1].path]);
  await page.waitForFunction(()=>document.querySelector('#subtitle-source')?.getAttribute('src')?.includes('playback'));
  await page.waitForFunction(()=>document.querySelector('#subtitle-source')?.readyState>=2);
  await page.locator('[data-action="studio-play"]').click();await page.waitForFunction(()=>document.querySelector('#subtitle-source').currentTime>.15);await page.locator('[data-action="studio-play"]').click();
  await page.locator('#studio-seek').evaluate(el=>{el.value='1';el.dispatchEvent(new Event('input',{bubbles:true}));});
  await page.waitForFunction(()=>{const v=document.querySelector('#subtitle-source'),c=document.createElement('canvas');c.width=32;c.height=18;c.getContext('2d').drawImage(v,0,0,32,18);return [...c.getContext('2d').getImageData(0,0,32,18).data].filter((_,i)=>i%4!==3).reduce((a,b)=>a+b,0)>10000;});
  const visiblePixels=true;
  const layer=page.locator('#subtitle-selection-layer');await layer.scrollIntoViewIfNeeded();let box=await layer.boundingBox();
  await page.mouse.move(box.x+box.width*.28,box.y+box.height*.825);await page.mouse.down();await page.mouse.move(box.x+box.width*.73,box.y+box.height*.902,{steps:12});await page.mouse.up();
  await waitApi(s=>s.config.subtitleRegions.length===1&&Math.abs(s.config.subtitleRegions[0].x-.28)<.02);
  await page.locator('[data-action="region-add"]').click();await waitApi(s=>s.config.subtitleRegions.length===2);
  await page.locator('[data-action="region-remove"]').click();await waitApi(s=>s.config.subtitleRegions.length===1);
  await page.locator('#region-x').fill('0.285');await page.locator('#region-x').press('Tab');
  await waitApi(s=>Math.abs(s.config.subtitleRegions[0].x-.285)<.001);
  // Exercise the resize handle in real displayed video coordinates.
  const handle=page.locator('[data-resize-region]');await handle.scrollIntoViewIfNeeded();const hb=await handle.boundingBox();
  await page.mouse.move(hb.x+hb.width/2,hb.y+hb.height/2);await page.mouse.down();await page.mouse.move(hb.x+hb.width/2+4,hb.y+hb.height/2+2,{steps:4});await page.mouse.up();
  await page.locator('.card').first().screenshot({path:path.join(out,'字幕画面框选.png')});
  const previewResponse=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('[data-action="subtitle-preview"][data-seconds="5"]').click();
  const preview=await(await previewResponse).json();if(!preview.id)throw Error(JSON.stringify(preview));
  const pipelineResponse=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('#start-pipeline').click();
  const pipeline=await(await pipelineResponse).json();if(!pipeline.id)throw Error(JSON.stringify(pipeline));
  let state;
  await page.locator('#nav a[href="#logs"]').click();
  await page.locator(`[data-task-id="${pipeline.id}"] [data-control="pause"]`).click();
  await page.locator(`[data-task-id="${pipeline.id}"] [data-control="resume"]`).waitFor();
  await page.screenshot({path:path.join(out,'任务队列与恢复.png'),fullPage:true});
  await page.locator(`[data-task-id="${pipeline.id}"] [data-control="resume"]`).click();
  state=await waitApi(s=>['completed','failed'].includes(s.jobs.find(j=>j.id===preview.id)?.status));
  const done=state.jobs.find(j=>j.id===preview.id);if(done.status!=='completed')throw Error(done.error||JSON.stringify(done));
  await waitApi(s=>s.jobs.find(j=>j.id===pipeline.id)?.status==='completed',120000);
  await page.locator('#nav a[href="#subtitle"]').click();
  await page.locator('#preview-before').waitFor();await page.waitForFunction(()=>document.querySelector('#preview-after').readyState>=2);
  await page.locator('#preview-before').evaluate(v=>{v.muted=true;return v.play()});
  await page.waitForFunction(()=>document.querySelector('#preview-before').currentTime>.3&&document.querySelector('#preview-after').currentTime>.2);
  await page.locator('#preview-before').evaluate(v=>{v.pause();v.currentTime=2});
  await page.waitForFunction(()=>Math.abs(document.querySelector('#preview-before').currentTime-document.querySelector('#preview-after').currentTime)<.25);
  await page.locator('#subtitle-preview-result').screenshot({path:path.join(out,'AI短片试处理对比.png')});
  await page.locator('[data-action="play-output"]').first().click();await page.locator('#output-dialog').waitFor({state:'visible'});
  await page.locator('#output-video').evaluate(v=>{v.muted=true;return v.play()});await page.waitForFunction(()=>document.querySelector('#output-video').currentTime>.2);
  await page.locator('[data-action="close-output"]').click();
  await page.setViewportSize({width:1024,height:768});if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('1024px overflow');
  if(errors.length)throw Error(errors.join('\n'));
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({ok:true,mode:'headless Edge application frontend',nativeDesktopWindow:false,all11Pages:true,sourcePlayback:true,sourceRenderedPixels:visiblePixels,hevcCompatibilityProxy:true,dragRegion:true,resizeRegion:true,multipleRegions:true,numericAlternative:true,previewJob:done,queuePauseResume:true,synchronizedPreview:true,outputPlayback:true,minimumWidth1024:true,errors},null,2));
  console.log(JSON.stringify({ok:true,preview:done.id,seconds:done.runSeconds,output:out}));
 }catch(e){await page.screenshot({path:path.join(out,'failure.png'),fullPage:true});throw e;}
 finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
