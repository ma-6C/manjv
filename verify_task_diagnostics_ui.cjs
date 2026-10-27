// Edge reads actual failed FFmpeg tasks from the isolated diagnostics host.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const meta=JSON.parse(fs.readFileSync('tmp/diagnostic-ui-host.json','utf8')),checks=[];
const check=(name,value)=>{assert(value,name);checks.push(name);};
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1050}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(meta.launch+'#logs');await page.locator('#log-job').waitFor();
  check('default_shows_issues_without_success_noise',await page.locator('#log-level').inputValue()==='issues'&&!(await page.locator('#logs-list').textContent()).includes('任务完成'));
  check('sidebar_prioritizes_actionable_issues',(await page.locator('#activity-content').textContent()).includes('错误与提醒')&&(await page.locator('#activity-content .mini-log').textContent()).includes('滤镜')&&!(await page.locator('#activity-content .mini-log').textContent()).includes('任务完成'));
  const task=page.locator(`[data-task-id="${meta.failedJobId}"]`);
  check('real_failure_shows_stage_video_reason_and_action',(await task.textContent()).includes('第002集.mp4')&&(await task.textContent()).includes('no_such_diagnostic_filter')&&(await task.textContent()).includes('下一步'));
  await task.locator('summary').filter({hasText:'技术详情'}).click();await page.evaluate(()=>poll());
  check('poll_preserves_expanded_technical_details',await task.locator('[data-failure-details]').getAttribute('open')!==null);
  check('technical_details_include_exit_code_and_stack',(await task.textContent()).includes('退出码')&&(await task.locator('pre').textContent()).includes('ProcessFailure'));
  await task.locator('summary').filter({hasText:'技术详情'}).click();
  await page.screenshot({path:'tmp/diagnostic-logs-desktop.png',fullPage:false});
  await task.locator('[data-action="filter-job-logs"]').click();
  check('task_filter_selects_only_chosen_task',await page.locator('#log-job').inputValue()===meta.failedJobId&&await page.locator('#log-level').inputValue()==='all'&&!(await page.locator('#logs-list').textContent()).includes(meta.passedJobId));
  await page.locator('#log-query').fill('no_such_diagnostic_filter');
  check('search_finds_original_error',(await page.locator('#logs-list').textContent()).includes('no_such_diagnostic_filter'));
  await page.locator('#log-query').fill('不存在的日志关键词');check('empty_filter_explains_no_matching_records',(await page.locator('#logs-list').textContent()).includes('暂无匹配日志'));
  await page.locator('#log-query').fill('');await page.locator('#log-level').selectOption('error');
  check('error_filter_hides_information',await page.locator('#logs-list .log-line.info').count()===0);
  const exported=await page.evaluate(async id=>await(await fetch('/api/logs/download?job='+encodeURIComponent(id))).text(),meta.failedJobId);
  check('actual_task_log_download_has_full_failure_context',exported.includes('ProcessFailure')&&exported.includes('第002集.mp4')&&!exported.includes(meta.passedJobId));
  const downloadWait=page.waitForEvent('download');await page.locator(`[data-task-id="${meta.failedJobId}"] [data-progress-action="report"]`).click();
  const download=await downloadWait;await download.saveAs(path.join(meta.base,'diagnostic-export.json'));
  const report=JSON.parse(fs.readFileSync(path.join(meta.base,'diagnostic-export.json'),'utf8'));
  check('diagnostic_download_includes_real_failure',report.failure.code==='FILTER'&&report.failure.video==='第002集.mp4'&&!JSON.stringify(report).includes(meta.base));
  await page.evaluate(id=>{monitorId=id;location.hash='progress';},meta.failedJobId);await page.locator('#monitor-detail .task-failure').waitFor();
  check('progress_page_uses_same_failure_details',(await page.locator('#monitor-detail .task-failure').textContent()).includes('no_such_diagnostic_filter'));
  await page.locator('#monitor-detail summary').click();await page.evaluate(()=>poll());
  check('progress_poll_preserves_expanded_details',await page.locator('#monitor-detail details').getAttribute('open')!==null);
  for(const width of [1024,390]){await page.setViewportSize({width,height:1000});check('progress_no_horizontal_overflow_'+width,await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));}
  await page.evaluate(()=>location.hash='logs');await page.locator('#log-job').waitFor();
  check('logs_narrow_layout_no_horizontal_overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:'tmp/diagnostic-logs-narrow.png',fullPage:true});
  check('no_browser_errors',errors.length===0);
  fs.writeFileSync('tmp/task-diagnostics-ui-latest.json',JSON.stringify({ok:true,checks,passed:checks.length,realProcessFailure:true},null,2));console.log(JSON.stringify({ok:true,checks,passed:checks.length},null,2));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
