const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const meta=JSON.parse(fs.readFileSync('tmp/native-fullseries-ui-host.json','utf8'));
const checks=[],errors=[];const check=(name,value=true)=>{assert.ok(value,name);checks.push(name);console.log('PASS '+name)};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:960},locale:'zh-CN'});page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/environment',route=>route.fulfill({json:{ffmpeg:true,gpu:{available:false,name:'CPU',detail:'fixture',adapters:[]},cores:4,python:'fixture',font:true}}));
 try{
  await page.goto(meta.launch);await page.locator('#nav a[href="#sources"]').click();
  await page.waitForFunction(()=>document.querySelectorAll('[data-source-task^="scroll-fixture-"]').length===20);
  check('long_live_queue_loaded_from_real_local_api');
  check('batch_and_confirmation_controls_absent',await page.locator('#source-batch,#source-confirm-batches').count()===0&&!/每批处理|暂停确认/.test(await page.locator('#source-live-queue').innerText()));
  const initial=await page.evaluate(()=>{
   const panel=document.querySelector('.activity'),select=document.querySelector('#source-concurrency');
   select.focus({preventScroll:true});panel.scrollTop=900;
   window.scrollTestSelect=select;window.scrollTestRoot=document.querySelector('#source-live-queue');
   return {top:panel.scrollTop,max:panel.scrollHeight-panel.clientHeight};
  });
  check('right_panel_is_actually_scrollable',initial.top>500&&initial.max>1000);
  for(let i=0;i<6;i++){await page.waitForTimeout(160);await page.evaluate(async()=>{while(sourcePolling)await new Promise(r=>setTimeout(r,10));await sourcePoll()});}
  let stable=await page.evaluate(()=>({top:document.querySelector('.activity').scrollTop,sameRoot:window.scrollTestRoot===document.querySelector('#source-live-queue'),sameSelect:window.scrollTestSelect===document.querySelector('#source-concurrency'),sameFocus:document.activeElement===window.scrollTestSelect}));
  check('progress_refresh_keeps_scroll_position',Math.abs(stable.top-initial.top)<=2);
  check('queue_root_and_concurrency_control_are_not_recreated',stable.sameRoot&&stable.sameSelect);
  check('focused_control_does_not_pull_queue_to_top',stable.sameFocus&&stable.top>500);
  await page.evaluate(()=>{
   document.activeElement.blur();const panel=document.querySelector('.activity');
   const details=document.querySelector('[data-source-task="scroll-fixture-18"] details');
   details.open=false;window.scrollTestDetails=details;
   const card=details.closest('[data-source-task]');panel.scrollTop+=card.getBoundingClientRect().top-panel.getBoundingClientRect().top+20;
   window.scrollTestCard=card;
   window.scrollTestOffset=card.getBoundingClientRect().top-panel.getBoundingClientRect().top;
  });
  for(let i=0;i<4;i++){await page.waitForTimeout(160);await page.evaluate(async()=>{while(sourcePolling)await new Promise(r=>setTimeout(r,10));await sourcePoll()});}
  stable=await page.evaluate(()=>({detailsSame:window.scrollTestDetails===document.querySelector('[data-source-task="scroll-fixture-18"] details'),closed:!window.scrollTestDetails.open,cardSame:window.scrollTestCard===document.querySelector('[data-source-task="scroll-fixture-18"]'),offset:window.scrollTestCard.getBoundingClientRect().top-document.querySelector('.activity').getBoundingClientRect().top,oldOffset:window.scrollTestOffset}));
  check('manually_collapsed_errors_stay_collapsed',stable.detailsSame&&stable.closed);
  check('visible_task_card_is_updated_in_place',stable.cardSame);
  check('reading_position_stays_on_same_task',Math.abs(stable.offset-stable.oldOffset)<=2);
  await page.evaluate(async directory=>{const r=await fetch('/api/source/start',{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify({url:'guoapp://hongguo/detail/123456789',directory,video:false})});if(!r.ok)throw Error(await r.text());while(sourcePolling)await new Promise(r=>setTimeout(r,10));await sourcePoll()},meta.base);
  await page.waitForTimeout(300);await page.evaluate(async()=>{while(sourcePolling)await new Promise(r=>setTimeout(r,10));await sourcePoll()});
  stable=await page.evaluate(()=>({same:window.scrollTestCard===document.querySelector('[data-source-task="scroll-fixture-18"]'),offset:window.scrollTestCard.getBoundingClientRect().top-document.querySelector('.activity').getBoundingClientRect().top,oldOffset:window.scrollTestOffset,top:document.querySelector('.activity').scrollTop}));
  check('new_task_at_top_does_not_move_current_reading_anchor',stable.same&&Math.abs(stable.offset-stable.oldOffset)<=2&&stable.top>100);
  await page.setViewportSize({width:1280,height:768});await page.evaluate(()=>{const panel=document.querySelector('.activity');document.querySelector('#source-concurrency').focus({preventScroll:true});panel.scrollTop=700;window.narrowQueueTop=panel.scrollTop});
  check('narrow_window_queue_is_visible_and_scrolled',await page.locator('.activity').isVisible()&&await page.evaluate(()=>document.querySelector('.activity').clientHeight>100&&window.narrowQueueTop>500));
  await page.waitForTimeout(1700);
  check('automatic_poll_preserves_narrow_window_scroll',await page.evaluate(()=>Math.abs(document.querySelector('.activity').scrollTop-window.narrowQueueTop)<=2));
  const evidence=path.join(meta.base,'evidence');fs.mkdirSync(evidence,{recursive:true});await page.screenshot({path:path.join(evidence,'连续下载-右侧滚动保持.png')});
  check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync('tmp/source-queue-scroll-report.json',JSON.stringify({fixture:true,compiled:!!meta.compiled,version:meta.version,signedDistributionVerified:!!meta.signedDistributionVerified,passed:checks.length,checks,errors,base:meta.base,initial,final:stable,note:'真实本机接口、受控进度与历史记录；不是外部源站下载证明。'},null,2));
  console.log(JSON.stringify({passed:checks.length,base:meta.base}));
 }catch(error){await page.screenshot({path:path.join(meta.base,'queue-scroll-failure.png'),fullPage:true});throw error}finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
