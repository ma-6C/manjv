// Run test_publish_ui_host.py first. This test writes only to its isolated test
// data: it exports a local packet and adds an explicitly labelled manual record.
// No official browser login, upload, or final submission is executed here.
const fs=require('fs'),path=require('path'),assert=require('assert');
function playwright(){
 if(process.env.PLAYWRIGHT_MODULE)return require(process.env.PLAYWRIGHT_MODULE);
 try{return require('playwright');}
 catch{return require(path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));}
}
const {chromium}=playwright();
const metadata=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tmp/publish-ui-host.json'),'utf8'));
assert(metadata.sourceOnly===true,'Only an isolated source UI host may be tested');
assert(metadata.base&&metadata.launch,'The isolated UI host metadata is incomplete');
const browserExecutable=process.env.EDGE_EXE||[
 path.join(process.env['PROGRAMFILES(X86)']||'C:/Program Files (x86)','Microsoft/Edge/Application/msedge.exe'),
 path.join(process.env.PROGRAMFILES||'C:/Program Files','Microsoft/Edge/Application/msedge.exe')
].find(file=>fs.existsSync(file));
const checks=[],check=(name,ok)=>{assert(ok,name);checks.push({name,passed:true});};
(async()=>{
 const browser=await chromium.launch({...browserExecutable?{executablePath:browserExecutable}:{},headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(String(e)));
  await page.goto(metadata.launch+'#publish');
  await page.getByRole('heading',{name:'发布与提审',exact:true}).waitFor();
  await page.locator('#publishing-title').waitFor();
  await page.waitForTimeout(700);
  check('two publishing routes',await page.getByRole('tab',{name:'短剧提审',exact:true}).count()===1&&await page.getByRole('tab',{name:'切片分发',exact:true}).count()===1);
  check('five distinct workflow steps',await page.locator('.publishing-steps li').count()===5);
  check('footer action matches publishing workflow',await page.locator('#start-pipeline').getAttribute('data-publishing')==='inspect'&&(await page.locator('#task-title').textContent())==='短剧提审准备');
  const producer=page.locator('#publishing-producer'),original=await producer.inputValue();
  await producer.fill('甲乙丙丁');await producer.evaluate(el=>{window.publishingInputProbe=el;el.focus();el.setSelectionRange(2,2);});
  await page.keyboard.type('XYZ');await page.waitForTimeout(2300);
  await page.evaluate(()=>renderPage());
  const stable=await producer.evaluate(el=>({same:window.publishingInputProbe===el,value:el.value,caret:el.selectionStart}));
  check('typing preserves element and middle caret through state refresh',stable.same&&stable.value==='甲乙XYZ丙丁'&&stable.caret===5);
  check('dirty form blocks stale export',await page.locator('[data-publishing="export"]').isDisabled());
  await producer.fill('');await page.locator('#publishing-form [data-publishing="inspect"]').click();
  await page.waitForFunction(()=>document.querySelector('#publishing-errors')&&!document.querySelector('#publishing-errors').hidden);
  check('missing producer is an inline error',await producer.getAttribute('aria-invalid')==='true'&&await page.locator('#publishing-producer-error').isVisible());
  check('validation summary receives keyboard focus',await page.locator('#publishing-errors').evaluate(el=>document.activeElement===el));
  await page.locator('[data-publishing="locate"][data-key="producer"]').click();
  check('missing item links to matching field',await producer.evaluate(el=>document.activeElement===el));
  await producer.fill(original||'UI 验收制作方');await page.locator('#publishing-form [data-publishing="inspect"]').click();
  await page.waitForFunction(()=>document.querySelector('#publishing-save-state')?.textContent==='资料已保存到本机');
  check('saved changes persist in backend',await page.evaluate(async()=>{const r=await api('publish/workspace');return Object.values(r.settings||{}).some(x=>x.producer==='UI 验收制作方'||x.producer===document.querySelector('#publishing-producer')?.value);}));
  check('attachments have six native file selectors',await page.locator('[data-publishing="attachment"]').count()===6);
  check('no final platform submit button exists',await page.locator('[data-publishing="submit"]').count()===0);
  const beforeCount=await page.evaluate(async()=>{const w=await api('publish/workspace');return w.tasks.length;});
  await page.locator('[data-publishing="export"]').click();
  await page.waitForFunction(async before=>{const w=await api('publish/workspace');return w.tasks.length>before&&w.tasks.at(-1).status==='completed';},beforeCount);
  await producer.focus();await producer.evaluate(el=>{window.publishingExportInputProbe=el;el.setSelectionRange(1,1);});
  const scrollBefore=await page.evaluate(()=>{window.scrollTo(0,350);return window.scrollY;});
  await page.waitForTimeout(2600);
  check('export task polling preserves input and scroll',await producer.evaluate(el=>window.publishingExportInputProbe===el)&&Math.abs((await page.evaluate(()=>window.scrollY))-scrollBefore)<2);
  check('real export task reports completion without submission',await page.locator('#publishing-task-status').textContent().then(x=>x.includes('导出提审资料')&&x.includes('操作完成')&&x.includes('本人在官方页面核对')));
  await page.locator('#publishing-result-note').fill('UI 验收：模拟本人核对记录，不是官方提审成功证明。');
  await page.locator('[data-publishing="record"]').click();
  await page.waitForFunction(()=>document.querySelector('#publishing-records')?.textContent.includes('UI 验收：模拟本人核对记录'));
  check('manual record source remains explicitly labelled',await page.locator('#publishing-records').textContent().then(x=>x.includes('本人核对记录')&&x.includes('已提交 · 本人记录')));
  await page.getByRole('tab',{name:'切片分发',exact:true}).click();
  check('slice route retains previous ordinary-video uploader',await page.getByRole('heading',{name:'普通视频批量上传',exact:true}).count()===1&&await page.locator('[data-action="upload-review"]').count()>=1);
  check('slice footer points to its confirmation list',await page.locator('#start-pipeline').getAttribute('data-action')==='upload-review');
  await page.getByRole('tab',{name:'短剧提审',exact:true}).click();
  check('returning to drama retains entered producer',await page.locator('#publishing-producer').inputValue()===(original||'UI 验收制作方'));
  const screenshot=path.join(metadata.base,'发布工作区-实际界面.png');await page.screenshot({path:screenshot,fullPage:true});
  await page.setViewportSize({width:650,height:1000});await page.waitForTimeout(300);
  check('narrow layout has no horizontal page overflow',await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  check('all browser script paths run without errors',errors.length===0);
  const report={passed:checks.length,checks,screenshot,scope:'Real Edge UI against isolated app backend; no external submission was executed'};
  fs.writeFileSync(path.join(metadata.base,'publishing-ui-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
 }finally{await browser.close();}
})().catch(e=>{
 // Playwright may embed the navigation URL in errors; never echo a launch token.
 const message=String(e.stack||e).split(metadata.launch).join('[local launch]')
  .replace(/\/launch\/[^\s'"#?]+/g,'/launch/[redacted]');
 console.error(message);process.exitCode=1;
});
