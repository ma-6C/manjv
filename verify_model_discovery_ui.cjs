// Real local routes and settings persistence; upstream provider replies are fixtures.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const meta=JSON.parse(fs.readFileSync('tmp/content-settings-host.json','utf8')),checks=[];
function check(name,value){assert(value,name);checks.push(name);console.log('PASS '+name);}
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1080}}),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(meta.launch+'#text');await page.locator('.content-ai-trigger').click();
  await page.locator('#content-ai-tab-text').click();await page.locator('#content-text-choice').selectOption('legacy');
  const before=await page.evaluate(()=>JSON.stringify(state.config));
  await page.locator('#content-text-model').fill('');
  await page.locator('#content-text-base').fill('https://catalog.fixture.invalid');
  await page.locator('#content-text-key').fill('fixture-catalog-key');
  await page.waitForFunction(()=>document.querySelector('#content-text-model-choice').options.length===604);
  check('only_url_and_key_load_models_before_model_or_save',await page.locator('#content-text-model').inputValue()==='');
  check('bare_origin_normalised_to_v1',await page.locator('#content-text-base').inputValue()==='https://catalog.fixture.invalid/v1');
  check('custom_gateway_automatically_uses_compatible_protocol',await page.locator('#content-text-provider').inputValue()==='custom'&&await page.locator('#content-text-protocol').inputValue()==='chat');
  check('discovery_does_not_save_draft_configuration',before===await page.evaluate(()=>JSON.stringify(state.config)));
  check('catalogue_over_500_is_not_truncated',(await page.locator('#content-text-models-status').textContent()).includes('603'));
  await page.locator('#content-text-model-search').fill('text-beta');
  check('model_search_filters_options',await page.locator('#content-text-model-choice option').count()===2);
  await page.locator('#content-text-model-choice').selectOption('fixture-text-beta');
  check('select_model_fills_model_id',await page.locator('#content-text-model').inputValue()==='fixture-text-beta');
  await page.locator('#content-text-model-search').fill('no-such-model');
  check('empty_search_preserves_selection',await page.locator('#content-text-model-choice option').count()===1&&await page.locator('#content-text-model').inputValue()==='fixture-text-beta');
  await page.locator('#content-text-model-search').fill('');
  await page.screenshot({path:path.join(meta.base,'模型自动获取-桌面.png')});
  await page.locator('[data-action="content-ai-save"][data-channel="text"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-text-result').textContent.includes('已保存文案接口'));
  check('save_uses_resolved_endpoint_and_selected_model',await page.evaluate(()=>state.config.apiBase==='https://catalog.fixture.invalid/v1'&&state.config.textModel==='fixture-text-beta'&&state.config.aiSelection.text==='legacy'));
  check('save_clears_key_input',await page.locator('#content-text-key').inputValue()==='');
  await page.locator('[data-action="content-ai-models"][data-channel="text"]').click();
  await page.waitForFunction(()=>!document.querySelector('#content-ai-panel-text .content-ai-models').hasAttribute('aria-busy'));
  check('refresh_works_with_saved_session_key',(await page.locator('#content-text-models-status').textContent()).includes('603'));
  await page.locator('[data-action="content-ai-test"][data-channel="text"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-text-result').textContent.includes('实际调用成功'));
  const calls=fs.readFileSync(path.join(meta.base,'calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  check('generation_uses_normalised_base_and_selected_model',calls.some(c=>c.url==='https://catalog.fixture.invalid/v1/chat/completions'&&c.model==='fixture-text-beta'&&c.keyPresent));

  await page.locator('#content-text-key').fill('fixture-invalid');
  await page.waitForFunction(()=>document.querySelector('#content-text-models-status').textContent.includes('401'));
  check('invalid_key_has_specific_error_and_hides_old_models',(await page.locator('#content-text-models-status').textContent()).includes('密钥无效')&&!await page.locator('#content-text-model-picker').isVisible());
  check('invalid_key_error_does_not_echo_secret',!(await page.locator('#content-text-models-status').textContent()).includes('fixture-invalid'));
  await page.locator('#content-text-key').fill('fixture-catalog-key');
  await page.waitForFunction(()=>document.querySelector('#content-text-model-choice').options.length===604&&!document.querySelector('#content-text-model-picker').hidden);
  check('correcting_key_automatically_recovers',!(await page.locator('#content-text-models-status').getAttribute('class')).includes('error'));

  await page.locator('#content-text-base').fill('https://empty.fixture.invalid/v1');
  await page.waitForFunction(()=>document.querySelector('#content-text-models-status').textContent.includes('列表为空'));
  check('empty_catalogue_has_actionable_message',!await page.locator('#content-text-model-picker').isVisible());
  await page.locator('#content-text-base').fill('https://unsupported.fixture.invalid/v1');
  await page.waitForFunction(()=>document.querySelector('#content-text-models-status').textContent.includes('不支持模型查询'));
  await page.locator('#content-text-model').fill('manual-private-model');
  await page.locator('[data-action="content-ai-save"][data-channel="text"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-text-result').textContent.includes('已保存文案接口'));
  check('unsupported_catalogue_still_allows_manual_model_save',await page.evaluate(()=>state.config.textModel==='manual-private-model'));

  const slowRequest=page.waitForRequest(r=>r.url().endsWith('/api/ai/discover-models')&&r.postDataJSON().connection.base.includes('slow.fixture.invalid'));
  await page.locator('#content-text-base').fill('https://slow.fixture.invalid/v1');await page.locator('#content-text-key').fill('fixture-slow-key');
  await slowRequest;
  check('loading_feedback_visible_without_freezing_inputs',(await page.locator('#content-text-models-status').textContent()).includes('正在获取')&&await page.locator('#content-text-base').isEnabled());
  await page.locator('#content-text-base').fill('https://catalog.fixture.invalid');
  await page.waitForFunction(()=>document.querySelector('#content-text-models-status').textContent.includes('603'));
  await page.waitForTimeout(1700);
  check('late_response_cannot_overwrite_new_endpoint_or_models',await page.locator('#content-text-base').inputValue()==='https://catalog.fixture.invalid/v1'&&(await page.locator('#content-text-models-status').textContent()).includes('603'));

  const anotherSlowRequest=page.waitForRequest(r=>r.url().endsWith('/api/ai/discover-models')&&r.postDataJSON().connection.base.includes('slow.fixture.invalid'));
  await page.locator('#content-text-base').fill('https://slow.fixture.invalid/v1');await anotherSlowRequest;
  await page.locator('#content-text-choice').selectOption('saved-text');
  const namedModel=await page.locator('#content-text-model').inputValue();await page.waitForTimeout(1700);
  check('switching_connection_cancels_old_query',await page.locator('#content-text-model').inputValue()===namedModel&&await page.locator('#content-text-base').inputValue()==='https://fixture.invalid/v1');

  const textBefore=await page.evaluate(()=>JSON.stringify({model:state.config.textModel,base:state.config.apiBase,selection:state.config.aiSelection.text}));
  await page.locator('#content-ai-tab-image').click();await page.locator('#content-image-choice').selectOption('legacy');
  await page.locator('#content-image-base').fill('https://catalog.fixture.invalid');await page.locator('#content-image-key').fill('fixture-image-discovery');await page.locator('#content-image-model').fill('');
  await page.waitForFunction(()=>document.querySelector('#content-image-model-choice').options.length===604);
  await page.locator('#content-image-model-search').fill('image-one');await page.locator('#content-image-model-choice').selectOption('fixture-image-one');
  await page.locator('[data-action="content-ai-save"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已保存封面接口'));
  check('image_has_independent_discovery_and_saved_selection',await page.evaluate(()=>state.config.imageApiBase==='https://catalog.fixture.invalid/v1'&&state.config.imageModel==='fixture-image-one'&&state.config.imageProtocol==='openai_images'));
  check('image_discovery_does_not_change_text_settings',textBefore===await page.evaluate(()=>JSON.stringify({model:state.config.textModel,base:state.config.apiBase,selection:state.config.aiSelection.text})));
  await page.setViewportSize({width:390,height:900});
  check('mobile_model_picker_has_no_horizontal_overflow',await page.locator('#content-ai-settings').evaluate(e=>e.scrollWidth<=e.clientWidth+1)&&await page.locator('#content-ai-panel-image').evaluate(e=>e.scrollWidth<=e.clientWidth+1));
  await page.locator('#content-image-base').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(meta.base,'模型自动获取-手机.png')});
  await page.locator('[data-action="content-ai-clear"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已清除'));
  check('clear_key_resets_model_picker_and_session_status',!await page.locator('#content-image-model-picker').isVisible()&&(await page.locator('#content-image-key-status').textContent()).includes('尚未设置'));
  await page.locator('[data-action="content-ai-models"][data-channel="image"]').click();
  await page.waitForFunction(()=>document.querySelector('#content-image-models-status').textContent.includes('请先填写'));
  check('missing_key_has_actionable_error',(await page.locator('#content-image-models-status').textContent()).includes('密钥'));
  await page.keyboard.press('Escape');
  check('close_clears_draft_secrets',await page.locator('#content-text-key').inputValue()===''&&await page.locator('#content-image-key').inputValue()==='');
  const stateFile=fs.readFileSync(path.join(meta.base,'data/state.json'),'utf8');
  check('discovery_keys_not_written_to_disk',!['fixture-catalog-key','fixture-invalid','fixture-image-discovery','fixture-slow-key'].some(key=>stateFile.includes(key)));
  const denied=await browser.newContext();const deniedPage=await denied.newPage();await deniedPage.goto(meta.url);
  const status=await deniedPage.evaluate(async()=>{const r=await fetch('/api/ai/discover-models',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify({channel:'text'})});return r.status;});
  check('discovery_endpoint_requires_local_session',status===403);await denied.close();
  check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(meta.base,'model-discovery-report.json'),JSON.stringify({ok:true,checks,errors,providerResponses:'simulated'},null,2));
  console.log(JSON.stringify({ok:true,passed:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
