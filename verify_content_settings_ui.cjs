// Isolated source UI and real config endpoints; provider replies are fixtures.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const meta=JSON.parse(fs.readFileSync('tmp/content-settings-host.json','utf8')),checks=[];
function check(name,value){assert(value,name);checks.push(name);console.log('PASS '+name);}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1540,height:1050}}),errors=[];let failSave=false;
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/config',route=>{if(failSave){failSave=false;return route.fulfill({status:503,json:{error:'测试：配置保存失败，请重试'}});}return route.continue();});
  await page.goto(meta.launch+'#text');await page.locator('.content-ai-trigger').waitFor();
  check('task_system_api_navigation_and_task_picker_removed',await page.locator('#nav a[href="#api"],[data-action="task-api-dialog"],#task-api-dialog').count()===0);
  check('settings_button_is_on_content_page_top_right',await page.locator('#content>.page-actions>.content-ai-trigger').count()===1);
  check('main_page_has_no_task_interface_card',!(await page.locator('#content').textContent()).includes('本次制作接口'));
  await page.locator('#edit-name').fill('尚未保存的剧名');await page.locator('#edit-intro').fill('尚未保存的简介草稿。');
  await page.locator('.content-ai-trigger').click();const dialog=page.locator('#content-ai-settings');
  check('independent_api_and_storage_settings_tabs',JSON.stringify(await dialog.locator('[role="tab"]').allTextContents())===JSON.stringify(['文案接口','封面接口','存储位置']));
  check('existing_named_connections_are_loaded',await page.locator('#content-text-model').inputValue()==='old-text'&&await page.locator('#content-text-choice').inputValue()==='auto');
  const before=await page.evaluate(()=>structuredClone(state.config));
  await page.locator('#content-text-key').fill('fixture-memory-text');await page.locator('#content-text-model').fill('fixture-text-new');
  await page.locator('#content-ai-tab-image').click();await page.locator('#content-image-key').fill('fixture-memory-image');await page.locator('#content-ai-tab-text').click();
  await page.evaluate(()=>poll());
  check('poll_and_tab_switch_preserve_unsaved_forms',await dialog.isVisible()&&await page.locator('#content-text-model').inputValue()==='fixture-text-new'&&await page.locator('#content-text-key').inputValue()==='fixture-memory-text');
  await page.locator('[data-action="content-ai-save"][data-channel="text"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-text-result').textContent.includes('已保存文案接口'));
  const saved=await page.evaluate(()=>structuredClone(state.config));
  check('text_save_updates_selected_connection',saved.aiConnections.find(c=>c.id==='saved-text').model==='fixture-text-new');
  check('text_save_keeps_image_and_subtitle_config',JSON.stringify(saved.aiConnections.filter(c=>c.channel!=='text'))===JSON.stringify(before.aiConnections.filter(c=>c.channel!=='text'))&&saved.subtitleEndpoint===before.subtitleEndpoint&&saved.aiSelection.subtitle===before.aiSelection.subtitle);
  check('saving_keeps_dialog_and_project_input',await dialog.isVisible()&&await page.locator('#edit-name').inputValue()==='尚未保存的剧名'&&await page.locator('#edit-intro').inputValue()==='尚未保存的简介草稿。');
  check('saved_key_is_cleared_from_form',await page.locator('#content-text-key').inputValue()===''&&(await page.locator('#content-text-key-status').textContent()).includes('已设置'));
  await page.locator('[data-action="content-ai-test"][data-channel="text"]').click();await page.waitForFunction(()=>document.querySelector('#content-text-result').textContent.includes('实际调用成功'));
  const calls=fs.readFileSync(path.join(meta.base,'calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  check('text_test_uses_saved_model_and_key',calls.at(-1).model==='fixture-text-new'&&calls.at(-1).keyPresent);
  await page.locator('#content-ai-tab-image').click();
  check('text_save_does_not_clear_image_key_input',await page.locator('#content-image-key').inputValue()==='fixture-memory-image');
  await page.locator('#content-image-choice').selectOption('legacy');await page.locator('#content-ai-panel-image summary').click();await page.locator('#content-image-provider').selectOption('custom');
  await page.locator('#content-image-base').fill('https://images.fixture.invalid/v1');await page.locator('#content-image-protocol').selectOption('openai_images');await page.locator('#content-image-model').fill('fixture-image-new');await page.locator('#content-image-key').fill('fixture-image-direct');
  await page.locator('[data-action="content-ai-save"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已保存封面接口'));
  check('image_has_its_own_endpoint_model_and_selection',await page.evaluate(()=>state.config.imageApiBase==='https://images.fixture.invalid/v1'&&state.config.imageModel==='fixture-image-new'&&state.config.aiSelection.image==='legacy'&&state.config.aiConnections.find(c=>c.id==='saved-text').model==='fixture-text-new'));
  await page.locator('[data-action="content-ai-test"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已获取模型列表'));
  check('image_test_does_not_claim_real_image_generation',(await page.locator('#content-image-result').textContent()).includes('实际生图尚需'));
  failSave=true;await page.locator('#content-image-model').fill('fixture-retry-image');await page.locator('[data-action="content-ai-save"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').classList.contains('error'));
  check('save_failure_is_visible_and_preserves_input',(await page.locator('#content-image-result').textContent()).includes('保存失败')&&await page.locator('#content-image-model').inputValue()==='fixture-retry-image'&&await dialog.isVisible());
  await page.locator('[data-action="content-ai-save"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已保存封面接口'));
  await page.locator('#content-ai-tab-image').focus();await page.keyboard.press('ArrowUp');check('keyboard_switches_settings_tabs',await page.locator('#content-ai-tab-text').getAttribute('aria-selected')==='true');
  await page.keyboard.press('Escape');check('escape_restores_settings_trigger_focus',!await dialog.isVisible()&&await page.locator('.content-ai-trigger').evaluate(e=>e===document.activeElement));
  await page.reload();await page.locator('.content-ai-trigger').click();
  check('settings_persist_after_reload',await page.locator('#content-text-model').inputValue()==='fixture-text-new');await page.locator('#content-ai-tab-image').click();check('image_settings_persist_after_reload',await page.locator('#content-image-model').inputValue()==='fixture-retry-image');
  await page.setViewportSize({width:1540,height:1050});await page.screenshot({path:path.join(meta.base,'文案与封面-设置.png')});
  for(const width of [1024,390]){await page.setViewportSize({width,height:900});check('dialog_no_horizontal_overflow_'+width,await dialog.evaluate(e=>e.scrollWidth<=e.clientWidth+1));}
  await page.keyboard.press('Escape');await page.evaluate(()=>location.hash='processing');await page.waitForFunction(()=>current==='scan');check('settings_are_not_added_to_other_pages',await page.locator('.content-ai-trigger,#content-ai-settings').count()===0);
  await page.goto(meta.url+'/#api');await page.waitForFunction(()=>current==='text');check('old_api_bookmark_redirects_to_content_page',page.url().endsWith('/#text'));
  check('session_keys_not_written_to_disk',!fs.readFileSync(path.join(meta.base,'data/state.json'),'utf8').includes('fixture-memory')&&!fs.readFileSync(path.join(meta.base,'data/state.json'),'utf8').includes('fixture-image-direct'));
  check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(meta.base,'report.json'),JSON.stringify({ok:true,checks,errors,providerResponses:'simulated'},null,2));console.log(JSON.stringify({ok:true,passed:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
