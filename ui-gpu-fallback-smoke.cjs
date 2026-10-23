const {chromium,request}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/gpu-ui-host.json','utf8')),checks=[],errors=[];
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1600,height:1000}});page.on('pageerror',e=>errors.push(e.message));
 const shot=path.join(meta.base,'screenshots');fs.mkdirSync(shot,{recursive:true});
 try{
  const unauth=await request.newContext();assert.equal((await unauth.get(meta.url+'/api/environment/report')).status(),403);await unauth.dispose();checks.push('environment_diagnostic_requires_local_session');
  await page.goto(meta.launch);await page.locator('#nav a[href="#parallel"]').click();await page.locator('[data-action="environment-report"]').waitFor();
  await page.waitForFunction(()=>document.querySelector('#content')?.textContent.includes('显卡驱动'));checks.push('gpu_model_driver_and_test_result_visible');
  assert.ok((await page.locator('#content').textContent()).includes('自动使用 CPU'));checks.push('automatic_cpu_fallback_explained_next_to_setting');
  const fresh=page.waitForResponse(r=>r.url().includes('/api/environment?refresh=1'));await page.locator('#content [data-action="environment"]').click();assert.equal((await fresh).status(),200);await page.locator('#environment-dialog[open]').waitFor();checks.push('manual_refresh_really_reprobes_backend');
  await page.locator('[data-action="close-environment"]').click();await page.screenshot({path:path.join(shot,'编码与并行-GPU诊断.png')});
  const downloading=page.waitForEvent('download');await page.locator('[data-action="environment-report"]').click();const download=await downloading;const diagnostic=JSON.parse(fs.readFileSync(await download.path(),'utf8'));
  assert.ok(diagnostic.gpu.code);assert.ok(Array.isArray(diagnostic.gpu.adapters));assert.equal(diagnostic.data,undefined);assert.equal(diagnostic.config,undefined);assert.equal(diagnostic.secrets,undefined);checks.push('actual_environment_json_download_without_paths_or_secrets');
  await page.locator('#nav a[href="#progress"]').click();await page.locator('[data-progress-action="select"][data-id="'+meta.fallbackJobId+'"]').click();
  assert.ok((await page.locator('#monitor-detail').textContent()).includes('已自动切换 CPU 编码'));assert.ok((await page.locator('#monitor-detail').textContent()).includes('制作已完成'));checks.push('completed_cpu_recovery_is_visible_with_reason');
  await page.screenshot({path:path.join(shot,'GPU失败自动CPU完成.png')});
  await page.setViewportSize({width:1024,height:800});await page.locator('#nav a[href="#parallel"]').click();assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));checks.push('gpu_diagnostic_narrow_layout_without_horizontal_overflow');
  assert.deepEqual(errors,[]);checks.push('no_browser_runtime_errors');
  fs.writeFileSync(meta.compiled?'tmp/gpu-ui-compiled-report.json':'tmp/gpu-ui-source-report.json',JSON.stringify({sourceOnly:!meta.compiled,compiled:!!meta.compiled,installerBuilt:false,passed:checks.length,checks,errors,base:meta.base},null,2));console.log(JSON.stringify({passed:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
