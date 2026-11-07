// Real source backend and filesystem; only the native folder picker is simulated.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const meta=JSON.parse(fs.readFileSync('tmp/content-settings-host.json','utf8')),checks=[];
function check(name,value){assert(value,name);checks.push(name);console.log('PASS '+name);}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const errors=[];let folder='';
 try{
  const page=await browser.newPage({viewport:{width:1540,height:1050}});page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/browse',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({path:folder})}));
  await page.goto(meta.launch+'#text');await page.locator('.content-ai-trigger').waitFor();
  await page.locator('#edit-name').fill('保留客户改写');await page.locator('#edit-intro').fill('保留正在编辑的简介内容。');
  await page.locator('.content-ai-trigger').click();await page.locator('#content-text-key').fill('unsaved-storage-ui-secret');
  await page.locator('#content-ai-tab-storage').click();
  check('storage_tab_has_visible_labeled_folder_picker',await page.getByLabel('文件保存位置',{exact:true}).isVisible()&&await page.locator('[data-action="content-ai-storage-pick"]').count()===2);
  folder=path.join(meta.base,'客户选择的文件夹');await page.locator('[data-target="content-storage-output"]').click();
  await page.waitForFunction(value=>document.querySelector('#content-storage-output').value===value,folder);
  check('picked_folder_is_shown_before_saving',await page.locator('#content-storage-output').inputValue()===folder&&!fs.existsSync(folder));
  await page.locator('#content-storage-jianying').fill('');await page.locator('[data-action="content-ai-storage-save"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-storage-result').textContent.includes('存储位置已保存'));
  check('storage_save_uses_real_backend_and_creates_writable_directories',fs.existsSync(path.join(folder,'剪映工程'))&&fs.existsSync(path.join(folder,'工程图')));
  check('saving_storage_keeps_dialog_and_unsaved_project_text',await page.locator('#content-ai-settings').isVisible()&&await page.locator('#edit-name').inputValue()==='保留客户改写'&&await page.locator('#edit-intro').inputValue()==='保留正在编辑的简介内容。');
  await page.locator('#content-ai-tab-text').click();check('storage_save_preserves_unsaved_api_form',await page.locator('#content-text-key').inputValue()==='unsaved-storage-ui-secret');
  await page.locator('#content-ai-tab-storage').click();const bad=path.join(meta.base,'不能当文件夹.txt');fs.writeFileSync(bad,'keep');
  await page.locator('#content-storage-output').fill(bad);await page.locator('[data-action="content-ai-storage-save"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-storage-result').classList.contains('error'));
  check('invalid_folder_error_is_inline_and_last_saved_setting_is_kept',(await page.locator('#content-storage-result').textContent()).includes('无法写入')&&await page.evaluate(()=>state.config.output)===folder);
  await page.keyboard.press('Escape');await page.locator('.content-ai-trigger').click();
  check('reopening_settings_restores_saved_path_after_invalid_draft',await page.locator('#content-storage-output').inputValue()===folder);
  await page.locator('#content-ai-tab-storage').click();await page.screenshot({path:path.join(meta.base,'存储位置设置.png')});
  for(const width of [1024,390]){await page.setViewportSize({width,height:900});check('storage_dialog_fits_width_'+width,await page.locator('#content-ai-settings').evaluate(e=>e.scrollWidth<=e.clientWidth+1));}
  await page.setViewportSize({width:1540,height:1050});await page.keyboard.press('Escape');
  const src=path.join(meta.base,'source'),moved=path.join(meta.base,'客户移动后的素材');assert(path.dirname(src)===meta.base&&path.dirname(moved)===meta.base);fs.renameSync(src,moved);folder=moved;
  await page.locator('[data-action="relink-project"]').click();await page.waitForFunction(()=>state.projects[0].source.includes('客户移动后的素材'));
  check('source_relink_button_updates_real_project_paths',await page.locator('#edit-name').inputValue()==='保留客户改写'&&await page.locator('#edit-intro').inputValue()==='保留正在编辑的简介内容。'&&await page.evaluate(()=>state.projects[0].videos.every(v=>v.path.includes('客户移动后的素材'))));
  await page.reload();await page.locator('.content-ai-trigger').click();await page.locator('#content-ai-tab-storage').click();
  check('storage_path_persists_across_page_reload',await page.locator('#content-storage-output').inputValue()===path.join(meta.base,'客户选择的文件夹'));
  await page.keyboard.press('Escape');await page.evaluate(()=>location.hash='tracks');await page.locator('[data-jianying="settings-open"]').click();
  check('project_save_paths_visible_without_advanced_settings',await page.locator('#jy-storage-output').isVisible()&&await page.locator('#jy-output').isVisible()&&!await page.locator('#jy-output').evaluate(e=>Boolean(e.closest('details'))));
  folder=path.join(meta.base,'工程页面选择的位置');await page.locator('[data-jianying="storage-pick"]').click();
  await page.waitForFunction(value=>document.querySelector('#jy-storage-output').value===value,folder);
  const draftFolder=path.join(meta.base,'独立剪映工程');folder=draftFolder;await page.locator('[data-jianying="path"][data-key="output"]').click();
  await page.waitForFunction(value=>document.querySelector('#jy-output').value===value,folder);
  await page.locator('[data-jianying="settings-save"]').click();await page.waitForFunction(()=>!document.querySelector('#jy-settings-dialog').open);
  check('project_settings_save_both_folders_in_automatic_mode',await page.evaluate(()=>!state.jianyingCustom&&state.config.output.endsWith('工程页面选择的位置')&&state.jianyingOptions.output.endsWith('独立剪映工程'))&&fs.existsSync(draftFolder));
  await page.locator('.jy-row-details summary').click();folder=meta.movedDraft;await page.locator('[data-jianying="reconnect"]').click();
  await page.waitForFunction(()=>state.jobs.some(j=>j.id==='moved-draft'&&j.jianyingResults[0].directory.includes('移动后的工程')));
  check('project_reconnect_button_updates_real_job_record',fs.readFileSync(path.join(meta.base,'data/jobs.json'),'utf8').includes('移动后的工程'));
  await page.locator('[data-jianying="settings-open"]').click();await page.screenshot({path:path.join(meta.base,'工程图保存位置设置.png')});
  await page.locator('#jy-storage-output').fill(bad);await page.locator('[data-jianying="settings-save"]').click();await page.waitForFunction(()=>document.querySelector('#jy-settings-result').classList.contains('error'));
  check('project_settings_failure_stays_open_with_inline_error',await page.locator('#jy-settings-dialog').isVisible()&&(await page.locator('#jy-settings-result').textContent()).includes('无法写入'));
  check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(meta.base,'storage-ui-report.json'),JSON.stringify({ok:true,checks,errors,folderPicker:'simulated; settings and relinking use real backend'},null,2));
  fs.writeFileSync('tmp/storage-ui-latest.json',JSON.stringify({ok:true,checks,base:meta.base},null,2));console.log(JSON.stringify({ok:true,checks:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
