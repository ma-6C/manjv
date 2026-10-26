// Actual local HTTP + real FFmpeg jobs. No mocked flow responses or platform calls.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||path.resolve(path.dirname(process.execPath),'../node_modules/playwright'));
const meta=JSON.parse(fs.readFileSync(path.join(__dirname,'tmp/studio-flow-ui-host.json'),'utf8'));
assert(meta.realFlow===true&&meta.sourceOnly===true);
const checks=[],check=(label,value)=>{assert(value,label);checks.push(label);};
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:960}}),errors=[];page.on('pageerror',e=>errors.push(String(e)));
  let jobPosts=0;page.on('request',r=>{if(r.method()==='POST'&&new URL(r.url()).pathname==='/api/jobs')jobPosts++;});
  await page.goto(meta.launch+'#studio');await page.getByRole('heading',{name:'开始工作',exact:true}).waitFor();
  await page.locator('[data-flow="select-all"]').click();
  const count=await page.locator('[data-flow-video]:checked').count();assert(count>1);
  await page.locator('.studio-plan-details').evaluate(e=>e.open=true);
  await page.locator('[data-flow-option="withJianying"]').uncheck();
  await page.locator('[data-flow-option="withExport"]').uncheck();
  check('关闭可选外部步骤后保留一键本地制作',await page.locator('[data-flow-option="withPublish"]').isChecked()===false);
  await page.screenshot({path:path.join(meta.base,'flow-live-start.png'),fullPage:true});
  const flowRequest=page.waitForResponse(r=>new URL(r.url()).pathname==='/api/studio-flows/start');
  await page.locator('#start-pipeline').click();const response=await flowRequest;assert(response.ok());const flow=await response.json();
  check('真实后台接收精确自由选集',flow.selectionCount===count&&Object.values(flow.sourceVideoPaths).flat().length===count);
  await page.waitForURL('**/#progress');
  check('实际任务启动后自动进入进度页',await page.evaluate(()=>current)==='progress');
  await page.waitForFunction(async id=>{const r=await fetch('/api/studio-flows');const v=await r.json();return v.flows.find(f=>f.id===id)?.status==='completed';},flow.id,{timeout:90000});
  await page.waitForURL('**/#studio',{timeout:12000});
  const result=await page.evaluate(async id=>{const state=await(await fetch('/api/state')).json();return {flow:state.studioFlows.flows.find(f=>f.id===id),jobs:state.jobs};},flow.id);
  const production=result.flow.stages.find(s=>s.key==='production'),job=result.jobs.find(j=>j.id===production.ref.id);
  check('实际FFmpeg制作完成后自动回到整套结果',result.flow.status==='completed'&&job?.status==='completed');
  check('结果登记本次每一集的实际成品',production.result.videos[meta.projectId].length===count);
  check('界面导航没有另发制作任务',jobPosts===0);
  check('完成后明确区分跳过的外部步骤',result.flow.stages.slice(1).every(s=>s.status==='skipped'));
  const ids=result.jobs.map(j=>j.id);await page.evaluate(()=>refresh(false));await page.evaluate(()=>refresh(false));
  check('刷新结果页不重复制作',JSON.stringify(ids)===JSON.stringify(await page.evaluate(()=>state.jobs.map(j=>j.id))));
  check('实际流程浏览器无脚本异常',errors.length===0);
  await page.screenshot({path:path.join(meta.base,'flow-live-completed.png'),fullPage:true});
  fs.writeFileSync(path.join(__dirname,'tmp/studio-flow-live-ui-report.json'),JSON.stringify({passed:checks.length,checks,errors,realMedia:true,mockedFlow:false,nativeEditorOpened:false,platformSubmitted:false,packaged:false,base:meta.base},null,2));
  console.log(JSON.stringify({passed:checks.length,errors,realMedia:true,mockedFlow:false}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
