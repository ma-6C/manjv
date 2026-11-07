const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const seed=JSON.parse(fs.readFileSync('tmp/promotion-studio-ui-host.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 async function api(path,body){return page.evaluate(async({path,body})=>{const r=await fetch('/api/'+path,body?{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify(body)}:{});const v=await r.json();if(!r.ok)throw Error(v.error);return v;},{path,body});}
 async function waitFor(check){for(let i=0;i<900;i++){const s=await api('state');if(check(s))return s;await new Promise(r=>setTimeout(r,150));}throw Error('Timed out');}
 try{
  await page.goto(seed.url);await page.locator('#nav a[href="#promotion"]').click();await page.getByRole('heading',{name:'AI 高光与跨集混剪',exact:true}).waitFor();checks.push('replacement_page_visible');
  assert.match(await page.locator('#content').innerText(),/先分析高光/);assert.equal(await page.locator('#start-pipeline').getAttribute('data-action'),'studio-run');checks.push('primary_action_replaced');
  await page.locator('.promo-tabs [data-promo="tab"][data-tab="targets"]').click();
  for(const p of ['hongguo','douyin','weixin'])await page.locator(`#studio-${p}-value`).waitFor();
  await page.locator('#studio-weixin-kind').selectOption('native');await page.locator('#studio-douyin-value').fill('https://example.invalid/ui-mini');await page.locator('[data-studio="save"]').click();
  await waitFor(s=>s.projects[0].promotionStudio.targets.douyin.value==='https://example.invalid/ui-mini');checks.push('three_platform_forms_and_save');
  await page.reload();await page.locator('.promo-tabs [data-promo="tab"][data-tab="targets"]').click();assert.equal(await page.locator('#studio-weixin-kind').inputValue(),'native');assert.equal(await page.locator('#studio-douyin-value').inputValue(),'https://example.invalid/ui-mini');checks.push('platform_settings_survive_reload');
  await page.locator('#studio-publishMode').selectOption('publish');await page.locator('.promo-tabs [data-promo="tab"][data-tab="prepare"]').click();assert.match(await page.locator('[data-studio="auto"]').innerText(),/建立任务/);checks.push('auto_dispatch_disabled_label_matches_behavior');
  await page.locator('#studio-count').fill('1');await page.locator('#studio-seconds').fill('10');await page.locator('[data-studio="analyse"]').click();
  await waitFor(s=>s.projects[0].promotionAnalysis?.model==='LOCAL-UI-MOCK');await page.locator('.promo-tabs [data-promo="tab"][data-tab="tasks"]').click();await page.locator('.promo-tabs [data-promo="tab"][data-tab="prepare"]').click();
  await page.getByText('界面模拟高光',{exact:false}).first().waitFor();checks.push('ui_ai_plan_from_simulated_model');
  await page.locator('[data-studio="preview-segment"]').first().click();await page.locator('#output-dialog').waitFor({state:'visible'});await page.locator('[data-action="close-output"]').click();checks.push('source_segment_preview');
  await page.locator('[data-studio="render"]').click();
  let s=await waitFor(s=>s.projects[0].promotionClips.some(c=>c.title==='界面模拟高光'));const clip=s.projects[0].promotionClips.find(c=>c.title==='界面模拟高光');
  await waitFor(s=>s.promotionTasks.filter(t=>t.clipId===clip.id).length===3&&!s.jobs.some(j=>['queued','running','pausing'].includes(j.status)));checks.push('ui_real_mix_and_three_platform_tasks');
  await page.locator('.promo-tabs [data-promo="tab"][data-tab="tasks"]').click();assert.match(await page.locator('#content').innerText(),/红果社区/);assert.match(await page.locator('#content').innerText(),/抖音/);assert.match(await page.locator('#content').innerText(),/视频号/);checks.push('per_platform_task_results');
  await page.screenshot({path:'tmp/promotion-studio-tasks.png',fullPage:true});
  await page.locator('.promo-tabs [data-promo="tab"][data-tab="prepare"]').click();await page.screenshot({path:'tmp/promotion-studio-prepare.png',fullPage:true});
  for(const width of [1440,1024,390]){await page.setViewportSize({width,height:850});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`prepare overflow ${width}`);await page.locator('.promo-tabs [data-promo="tab"][data-tab="targets"]').click();assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false,`targets overflow ${width}`);await page.locator('.promo-tabs [data-promo="tab"][data-tab="prepare"]').click();}checks.push('responsive_1440_1024_390_no_overflow');
  await page.setViewportSize({width:1440,height:1000});await page.locator('.promo-tabs [data-promo="tab"][data-tab="targets"]').click();await page.screenshot({path:'tmp/promotion-studio-targets.png',fullPage:true});
  assert.deepEqual(errors,[]);checks.push('no_browser_runtime_errors');
  fs.writeFileSync('tmp/promotion-studio-ui-report.json',JSON.stringify({ok:true,checks,pageErrors:errors,model:'simulated',encoding:'real_ffmpeg',remotePublishing:false},null,2));console.log('PROMOTION_STUDIO_UI_OK',checks.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
