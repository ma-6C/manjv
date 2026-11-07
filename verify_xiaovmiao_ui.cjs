const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),assert=require('node:assert/strict');
(async()=>{
 const seed=JSON.parse(fs.readFileSync('tmp/xiaovmiao-check-host.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[],checks=[];
 page.on('pageerror',e=>errors.push(e.message));
 async function api(path,body){return page.evaluate(async({path,body})=>{
  const r=await fetch('/api/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Local-Client':'1'},body:JSON.stringify(body)});
  return {status:r.status,body:await r.json()};
 },{path,body});}
 try{
  await page.goto(seed.url);const link=page.locator('#nav a[href="#xiaovmiao"]');await link.waitFor();
  assert.equal(await link.count(),1);assert.equal(await link.getAttribute('aria-label'),'打开小v喵');checks.push('single_direct_launcher_entry');
  const configured=await api('xiaovmiao/settings',{executable:'D:\\小v喵\\本地初始化修复_20261103\\程序\\vcat_local_init.exe'});
  assert.equal(configured.status,200);assert.equal(configured.body.bundled,false);checks.push('selected_repaired_program_uses_existing_profile');
  const before=await page.locator('#content').innerText(),hash=await page.evaluate(()=>location.hash);
  const response=page.waitForResponse(r=>r.url().endsWith('/api/xiaovmiao/open')&&r.request().method()==='POST');
  await link.click();const opened=await response;const result=await opened.json();
  assert.equal(opened.status(),200);assert.equal(result.launchRequested,true);
  await page.waitForFunction(()=>!document.querySelector('#nav a[href="#xiaovmiao"]')?.hasAttribute('aria-busy'));
  assert.equal(await page.locator('#content').innerText(),before);assert.equal(await page.evaluate(()=>location.hash),hash);
  assert.equal(await page.locator('#nav a[href="#xiaovmiao"] span').first().innerText(),'小v喵');checks.push('real_direct_launch_keeps_current_workspace');
  assert.equal(await page.locator('.taskbar').isVisible(),true);assert.equal(await page.locator('#xvm-open').count(),0);checks.push('no_intermediate_page');
  let calls=0;await page.route('**/api/xiaovmiao/open',async route=>{
   calls++;await new Promise(r=>setTimeout(r,350));await route.fulfill({status:400,contentType:'application/json',body:JSON.stringify({error:'启动检查：测试错误反馈'})});
  });
  await page.locator('#nav a[href="#xiaovmiao"]').dblclick();
  await page.waitForFunction(()=>document.querySelector('#toast')?.textContent.includes('测试错误反馈'));
  assert.equal(calls,1);checks.push('duplicate_click_suppressed_and_error_visible');
  await page.unroute('**/api/xiaovmiao/open');
  await page.goto(new URL('/#xiaovmiao',seed.url).href);await page.locator('#nav a[href="#scan"][aria-current="page"]').waitFor();checks.push('old_hash_recovers_to_workspace');
  for(const width of [1440,1024,390]){await page.setViewportSize({width,height:900});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);}checks.push('responsive_navigation');
  const forbidden=await page.evaluate(async()=>{const r=await fetch('/api/xiaovmiao/open',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});return r.status;});assert.equal(forbidden,403);checks.push('mutation_requires_local_client_header');
  const other=await browser.newContext();const p=await other.newPage();const r=await p.goto(new URL('/api/xiaovmiao',seed.url).href);assert.equal(r.status(),403);await other.close();checks.push('launcher_requires_local_session');
  assert.deepEqual(errors,[]);checks.push('no_page_errors');
  fs.writeFileSync('tmp/xiaovmiao-ui-report.json',JSON.stringify({ok:true,checks,pageErrors:errors,launch:'real-selected-original-repaired-program',remotePublishing:false},null,2));console.log('XIAOVMIAO_DIRECT_UI_OK',checks.length);
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
