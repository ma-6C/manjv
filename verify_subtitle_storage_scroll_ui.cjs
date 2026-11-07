const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const scrollChecks=require('./tools/settings_scroll_checks.cjs');
const meta=JSON.parse(fs.readFileSync('tmp/subtitle-settings-ui-host.json','utf8')),checks=[],metrics=[];
function check(name,value){assert(value,name);checks.push(name);console.log('PASS '+name);}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const errors=[];let folder='';
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/browse',route=>route.fulfill({status:200,json:{path:folder}}));
  await page.goto(meta.launch+'#subtitle');await page.locator('.subtitle-settings-trigger').click();await page.locator('#subtitle-settings-tab-storage').click();
  check('subtitle_storage_category_and_folder_picker_visible',await page.getByLabel('去字幕文件保存位置').isVisible()&&await page.locator('[data-action="subtitle-storage-pick"]').isVisible());
  const savedBefore=await page.evaluate(()=>state.config.output);folder=path.join(meta.base,'客户选择的去字幕保存文件夹-'+Date.now());await page.locator('[data-action="subtitle-storage-pick"]').click();
  await page.waitForFunction(value=>document.querySelector('#subtitle-storage-output').value===value,folder);
  check('folder_selection_is_a_draft_until_explicit_save',await page.evaluate(()=>state.config.output)===savedBefore&&(await page.locator('#subtitle-settings-save-state').textContent()).includes('尚未保存'));
  await page.locator('[data-action="subtitle-storage-save"]').click();await page.waitForFunction(()=>document.querySelector('#subtitle-storage-result').textContent.includes('存储位置已保存'));
  check('subtitle_storage_save_checks_real_directory_and_persists',fs.existsSync(folder)&&JSON.parse(fs.readFileSync(path.join(meta.base,'data/state.json'),'utf8')).config.output===folder);
  const bad=path.join(meta.base,'不是文件夹.txt');fs.writeFileSync(bad,'keep');await page.locator('#subtitle-storage-output').fill(bad);await page.locator('[data-action="subtitle-storage-save"]').click();
  await page.waitForFunction(()=>document.querySelector('#subtitle-storage-result').classList.contains('error'));
  check('invalid_storage_error_keeps_dialog_and_saved_path',await page.locator('#subtitle-settings-dialog').isVisible()&&await page.evaluate(()=>state.config.output)===folder&&(await page.locator('#subtitle-storage-result').textContent()).includes('无法写入'));
  await page.locator('#subtitle-storage-output').fill(folder);await page.locator('[data-action="subtitle-storage-save"]').click();await page.waitForFunction(()=>document.querySelector('#subtitle-storage-result').textContent.includes('存储位置已保存'));
  await page.screenshot({path:path.join(meta.base,'AI去字幕-存储位置.png')});
  await page.locator('#subtitle-settings-tab-local').click();
  for(const size of [{width:1366,height:768},{width:1024,height:600},{width:390,height:700}]){
   await page.setViewportSize(size);metrics.push(await scrollChecks(page,{dialog:'#subtitle-settings-dialog',panel:'.subtitle-settings-panels',header:'.subtitle-settings-header',footer:'.subtitle-settings-footer',nav:'.subtitle-settings-nav',check,prefix:'subtitle_'+size.width+'x'+size.height}));
   check('subtitle_dialog_has_no_horizontal_overflow_'+size.width,await page.locator('#subtitle-settings-dialog').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
  }
  await page.setViewportSize({width:1366,height:768});await page.screenshot({path:path.join(meta.base,'AI去字幕-设置内部滚动.png')});
  await page.keyboard.press('Escape');check('closing_settings_restores_trigger_focus',await page.locator('.subtitle-settings-trigger').evaluate(el=>el===document.activeElement));
  await page.locator('#content').hover();await page.mouse.wheel(0,500);await page.waitForTimeout(200);check('main_page_scroll_restored_after_closing',await page.evaluate(()=>scrollY>0));
  await page.evaluate(()=>scrollTo(0,0));
  const old=await page.evaluate(()=>state.projects[0].artifacts.filter(a=>a.path.endsWith('.mp4')).map(a=>a.path));
  await page.evaluate(()=>updateConfig({subtitleMode:'local',gpu:false}));
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('[data-action="subtitle-full"][data-scope="current"]').click();const response=await responsePromise;
  check('actual_subtitle_job_can_be_started_with_saved_folder',response.ok());const job=await response.json();
  await page.waitForFunction(id=>['completed','failed','cancelled'].includes(state.jobs.find(j=>j.id===id)?.status),job.id,{timeout:45000});
  const generated=await page.evaluate(id=>({job:state.jobs.find(j=>j.id===id),files:state.projects.flatMap(p=>p.artifacts).filter(a=>a.job===id&&a.path.endsWith('.mp4')).map(a=>a.path)}),job.id);
  check('actual_subtitle_video_is_written_to_selected_folder',generated.job.status==='completed'&&generated.files.length>0&&generated.files.every(p=>p.startsWith(folder+path.sep)&&fs.existsSync(p)));
  check('previous_subtitle_outputs_are_preserved',old.length>0&&old.every(p=>fs.existsSync(p)));
  await page.reload();await page.locator('.subtitle-settings-trigger').click();await page.locator('#subtitle-settings-tab-storage').click();
  check('subtitle_storage_path_is_loaded_after_reload',await page.locator('#subtitle-storage-output').inputValue()===folder);
  await page.keyboard.press('Escape');await page.evaluate(()=>location.hash='text');await page.locator('.content-ai-trigger').click();
  metrics.push(await scrollChecks(page,{dialog:'#content-ai-settings',panel:'.content-ai-panels',header:'.content-ai-header',footer:'.content-ai-footer',nav:'.content-ai-nav',check,prefix:'content_settings'}));
  await page.keyboard.press('Escape');await page.evaluate(()=>location.hash='tracks');await page.locator('[data-jianying="settings-open"]').click();
  await page.locator('.jy-advanced-fields > summary').click();const background=await page.evaluate(()=>scrollY);await page.locator('#jy-settings-dialog').hover();await page.mouse.wheel(0,500);await page.waitForTimeout(200);
  check('project_settings_scroll_in_dialog_and_keep_background',await page.locator('#jy-settings-dialog').evaluate(el=>el.scrollTop>0)&&await page.evaluate(()=>scrollY)===background);
  check('no_browser_runtime_errors',errors.length===0);
  const report={ok:true,checks,metrics,base:meta.base,actualSubtitleFiles:generated.files,actualJobId:job.id,nativeFolderPicker:'simulated selection; real filesystem, API and processing'};
  fs.writeFileSync('tmp/subtitle-storage-scroll-latest.json',JSON.stringify(report,null,2));fs.writeFileSync(path.join(meta.base,'subtitle-storage-scroll-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({ok:true,checks:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
