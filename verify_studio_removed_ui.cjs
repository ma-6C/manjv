// Real Edge, source UI and HTTP backend; real local subtitle output, no cloud/editor/installer.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const meta=JSON.parse(fs.readFileSync('tmp/studio-removed-host.json','utf8'));
const checks=[],check=(name,value)=>{assert(value,name);checks.push(name);console.log('PASS '+name);};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}}),errors=[],flowRequests=[],assets=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/api/studio-flows'))flowRequests.push(p);if(/\/flow(?:_stage)?\.(js|css)$/.test(p))assets.push(p);});
  await page.goto(meta.launch);await page.locator('#library').waitFor();
  check('默认进入本地素材',await page.evaluate(()=>current==='scan')&&await page.locator('#nav a[href="#scan"]').getAttribute('aria-current')==='page');
  check('侧栏没有开始工作和连续制作分组',await page.locator('#nav a[href="#studio"]').count()===0&&!(await page.locator('#nav').innerText()).includes('连续制作'));
  check('没有制作弹窗或顶部流程条',await page.locator('#studio-run-dialog,#studio-flow-strip').count()===0);
  check('独立页面未被流程覆盖',await page.locator('#start-pipeline').getAttribute('data-flow')===null&&!await page.locator('body').evaluate(e=>e.classList.contains('studio-route')));
  await page.goto(meta.url+'/#studio');await page.locator('#library').waitFor();
  check('旧开始工作地址回到本地素材',new URL(page.url()).hash==='#scan'&&await page.evaluate(()=>current==='scan'));
  for(const route of ['sources','scan','subtitle','tracks','text','cost','publish','progress']){
   await page.locator('#nav a[href="#'+route+'"]').click();
   await page.waitForFunction(id=>current===id,route);
   await page.locator('#content h1').waitFor();
   check('独立功能可打开_'+route,await page.locator('#content h1').isVisible()&&await page.locator('#content .error-banner').count()===0);
  }
  await page.locator('#nav a[href="#subtitle"]').click();await page.locator('.subtitle-settings-trigger').click();
  await page.locator('#subtitle-settings-tab-storage').click();
  check('去字幕保留存储位置设置',await page.getByLabel('去字幕文件保存位置').isVisible());
  await page.locator('#subtitle-settings-tab-local').click();
  await page.setViewportSize({width:1024,height:600});
  const scrollChecks=require('./tools/settings_scroll_checks.cjs');
  await scrollChecks(page,{dialog:'#subtitle-settings-dialog',panel:'.subtitle-settings-panels',header:'.subtitle-settings-header',footer:'.subtitle-settings-footer',nav:'.subtitle-settings-nav',check,prefix:'subtitle_1024x600'});
  await page.keyboard.press('Escape');
  check('字幕设置可关闭并返回页面',!await page.locator('#subtitle-settings-dialog').isVisible()&&await page.locator('.subtitle-settings-trigger').isVisible());
  await page.setViewportSize({width:1366,height:768});
  const responsePromise=page.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');
  await page.locator('[data-action="subtitle-full"][data-scope="current"]').click();
  const response=await responsePromise,job=await response.json();
  check('独立去字幕可以提交真实任务',response.ok()&&!!job.id);
  await page.waitForFunction(id=>['completed','failed','cancelled'].includes(state.jobs.find(j=>j.id===id)?.status),job.id,{timeout:45000});
  const result=await page.evaluate(id=>({job:state.jobs.find(j=>j.id===id),files:state.projects.flatMap(p=>p.artifacts).filter(a=>a.job===id&&a.path.endsWith('.mp4')).map(a=>a.path)}),job.id);
  check('独立去字幕生成真实视频文件',result.job.status==='completed'&&result.files.length>0&&result.files.every(f=>f.startsWith(meta.base+path.sep)&&fs.statSync(f).size>0));
  await page.locator('#nav a[href="#scan"]').click();await page.locator('#library').waitFor();
  await page.screenshot({path:path.join(meta.base,'移除开始工作-本地素材.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  check('窄屏无流程残留且不横向溢出',await page.locator('[data-flow],#studio-run-dialog,#studio-flow-strip').count()===0&&await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+2));
  await page.waitForTimeout(1800);
  check('页面与轮询不请求旧流程接口或脚本',flowRequests.length===0&&assets.length===0);
  check('没有浏览器脚本异常',errors.length===0);
  const report={passed:checks.length,checks,files:result.files,errors,scope:'Actual Edge/source HTTP with real local subtitle output. No native editor, external AI or installer.'};
  fs.writeFileSync(path.join(meta.base,'studio-module-removed-ui.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({passed:checks.length,base:meta.base}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
