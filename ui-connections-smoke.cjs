// Actual source UI after retiring video generation. No cloud generation calls.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/subtitle-full-ui-host.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),checks=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
 const check=(name,value)=>{if(!value)throw Error(name);checks.push(name);console.log('PASS '+name);};
 try{
  await page.goto(meta.launch);await page.goto(meta.url+'/#api');await page.waitForSelector('[data-action="connection-new"]');
  check('video_generation_navigation_removed',await page.locator('#nav a[href="#generate"]').count()===0);
  check('video_routing_controls_removed',await page.locator('#route-video,[data-channel="video"]').count()===0);
  check('api_page_has_no_video_generation_copy',!(await page.locator('#content').textContent()).includes('视频生成'));
  await page.locator('[data-action="connection-new"]').first().click();
  const channels=await page.locator('#connection-channel option').evaluateAll(es=>es.map(e=>e.value));
  check('only_text_image_subtitle_connection_types_remain',JSON.stringify(channels)===JSON.stringify(['text','image','subtitle']));
  await page.locator('#connection-channel').selectOption('image');
  check('image_protocols_remain_available',(await page.locator('#connection-protocol option').count())>=3);
  await page.locator('#connection-name').fill('保留生图连接');await page.locator('#connection-model').fill('fixture-image-model');
  const submitted=page.waitForResponse(r=>r.url().endsWith('/api/ai/connections')&&r.request().method()==='POST');await page.locator('[data-action="connection-save"]').click();
  check('image_connection_can_be_saved',(await submitted).ok());await page.locator('#connection-dialog').waitFor({state:'hidden'});
  await page.waitForFunction(()=>document.querySelector('#connection-list')?.textContent.includes('保留生图连接'));
  check('new_image_connection_is_listed',(await page.locator('#connection-list').textContent()).includes('保留生图连接'));
  await page.screenshot({path:path.join(meta.base,'移除视频生成-接口管理.png'),fullPage:true});
  await page.goto(meta.url+'/#generate');await page.waitForURL('**/#scan');
  check('old_generation_bookmark_redirects_to_source_library',page.url().endsWith('/#scan'));
  check('taskbar_has_no_generation_submit_action',await page.locator('[data-action="generation-start"]').count()===0);
  for(const id of ['preprocess','subtitle','text','api','logs']){await page.locator(`#nav a[href="#${id}"]`).click();await page.waitForTimeout(100);check('retained_page_renders_'+id,await page.locator('#content h1:visible').count()===1);}
  await page.locator('#nav a[href="#subtitle"]').click();
  check('whole_episode_and_series_subtitle_actions_remain',await page.locator('[data-action="subtitle-full"]').count()===2);
  await page.setViewportSize({width:390,height:844});await page.locator('#nav a[href="#api"]').evaluate(el=>el.click());
  check('api_narrow_layout_has_no_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  check('no_javascript_runtime_errors',errors.length===0);
  fs.writeFileSync(path.join(meta.base,'retirement-ui-report.json'),JSON.stringify({ok:true,checks,errors},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exit(1);});
