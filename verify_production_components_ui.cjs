const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/subtitle-full-ui-host.json','utf8')),seed=JSON.parse(fs.readFileSync('tmp/production-components-latest.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),page=await browser.newPage({viewport:{width:1540,height:1120}}),checks=[],errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 const check=(name,value)=>{if(!value)throw Error(name);checks.push(name);console.log('PASS '+name);};
 const api=async(name,body)=>{const r=await page.request[body?'post':'get'](meta.url+'/api/'+name,body?{data:body,headers:{'X-Local-Client':'1'}}:{});const data=await r.json();if(!r.ok())throw Error(data.error);return data;};
 async function job(id){const until=Date.now()+60000;while(Date.now()<until){const value=(await api('state')).jobs.find(j=>j.id===id);if(!['queued','running','pausing'].includes(value.status)){check('UI-created '+value.kind+' completes',value.status==='completed');return value;}await page.waitForTimeout(200);}throw Error('Job timed out');}
 async function change(selector,value){await page.locator(selector).fill(value);await page.locator(selector).dispatchEvent('change');await page.evaluate(()=>saving);}
 try{
  await page.goto(meta.launch);await api('config',{gpu:false,highlightLowResource:false,highlightTailEnabled:false,highlightMusic:'',highlightCount:1,highlightRandom:false,highlightFixed:.5,highlightParallel:2,endingText:''});
  await page.goto(meta.url+'/#highlight');await page.reload();await page.waitForSelector('[data-highlight="start"]');
  check('input_output_sections_are_parallel',await page.locator('.highlight-top>.card').count()===2);
  const inBox=await page.locator('.highlight-top>.card').first().boundingBox(),outBox=await page.locator('.highlight-top>.card').last().boundingBox();check('desktop_top_columns_share_same_row',Math.abs(inBox.y-outBox.y)<3&&outBox.x>inBox.x);
  check('configuration_follows_input_and_output',await page.locator('#config-highlightFixed').count()===1&&await page.locator('#config-highlightParallel').count()===1);
  check('music_and_tail_options_are_present',await page.locator('[data-highlight="music"]').count()===1&&await page.locator('[data-config="highlightTailEnabled"]').count()===1);
  await page.locator('[data-highlight="clear"]').click();check('clear_updates_selected_list',await page.locator('.highlight-file').count()===0);
  await page.locator('[data-highlight="current"]').click();check('current_project_adds_both_sources',await page.locator('.highlight-file').count()===2);
  await page.locator('[data-highlight="remove"]').last().click();check('remove_keeps_only_user_selected_source',await page.locator('.highlight-file').count()===1);
  await change('#config-highlightCount','2');await change('#config-highlightFixed','0.5');
  await page.waitForFunction(()=>document.querySelector('#highlight-estimate').textContent.includes('2 个成品'));check('estimate_responds_to_copy_count',true);
  await page.screenshot({path:path.join(seed.base,'高光去重-桌面布局.png'),fullPage:true});
  const submitted=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('[data-highlight="start"]').first().click();const response=await submitted,request=response.request().postDataJSON(),result=await response.json();
  check('highlight_start_submits_exact_selection',request.kind==='highlight'&&Object.values(request.sourceVideoPaths).flat().length===1);
  const rendered=await job(result.id);check('two_outputs_from_selected_source',rendered.completedStages.includes('highlight')&&Object.values(rendered.highlightPlan).length===2&&Object.values(rendered.highlightPlan).every(p=>p.ratio===.5&&!p.tail&&!p.music));
  // The actual backend output records, rather than button feedback alone, prove completion.
  const st=await api('state');check('highlights_registered_as_downloadable_media',st.projects.flatMap(p=>p.artifacts).filter(a=>a.job===result.id&&a.kind==='高光视频').length===2);
  await page.setViewportSize({width:980,height:1000});await page.waitForTimeout(100);const boxes=await page.locator('.highlight-top>.card').evaluateAll(els=>els.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y})));check('narrow_columns_stack',boxes[1].y>boxes[0].y);check('no_document_horizontal_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.setViewportSize({width:1540,height:1120});await page.locator('#nav a[href="#tracks"]').click();await page.waitForSelector('[data-jianying="generate"]');
  await page.locator('[data-jianying="status"]').click();await page.waitForFunction(()=>document.querySelector('#jy-status').textContent.includes('0.3.1'));check('upstream_component_status_is_live',true);
  check('real_draft_and_png_actions_are_distinct',await page.locator('[data-jianying="generate"]').count()===1&&await page.locator('[data-track="generate"]').count()>0);
  await page.locator('[data-track="select-visible"]').click();await page.locator('#jy-split').uncheck();await page.locator('#jy-output').fill(path.join(seed.base,'ui-drafts'));await page.locator('#jy-output').dispatchEvent('input');
  const draftSubmit=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await page.locator('[data-jianying="generate"]').click();const dr=await draftSubmit,dj=await dr.json();check('real_draft_job_submitted_from_UI',dr.request().postDataJSON().kind==='jianying_project');const complete=await job(dj.id);check('draft_results_have_real_paths_and_pending_editor_state',complete.jianyingResults.length===2&&complete.jianyingResults.every(r=>r.path.endsWith('draft_content.json')&&r.editorValidated===false));
  await page.waitForFunction(()=>document.querySelectorAll('#jy-results .jianying-result').length===2);await page.screenshot({path:path.join(seed.base,'剪映真实工程-导出结果.png'),fullPage:true});
  const manifest=await page.request.get(meta.url+'/api/file?path='+encodeURIComponent(complete.jianyingResults[0].manifest));check('exported_manifest_is_accessible_as_registered_artifact',manifest.ok()&&(await manifest.json()).kind==='jianying_project');
  const unauthorized=await page.request.post(meta.url+'/api/jianying/plan',{data:{ids:[]}});check('mutating_API_requires_local_client_header',unauthorized.status()===403);
  await page.locator('#nav a[href="#subtitle"]').click();check('whole_video_subtitle_controls_retained',await page.locator('[data-action="subtitle-full"]').count()===2);check('persistent_model_option_visible',await page.locator('[data-config="vsrReuseWorker"]').count()===1);
  check('no_javascript_runtime_errors',errors.length===0);fs.writeFileSync(path.join(seed.base,'ui-report.json'),JSON.stringify({ok:true,checks,errors,highlightJob:result.id,draftJob:dj.id},null,2));
  console.log(JSON.stringify({ok:true,checks:checks.length,base:seed.base}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
