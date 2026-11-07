'use strict';

const fs=require('node:fs');
const path=require('node:path');
const http=require('node:http');
const assert=require('node:assert/strict');
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');

const root=path.resolve(__dirname,'..');
const web=path.join(root,'web');
const out=fs.mkdtempSync(path.join(root,'tmp','activation-removed-ui-'));
const browserPath='C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const fixture={
 config:{source:'',output:'',costRows:[],subtitleRegion:{x:.05,y:.7,w:.9,h:.18},subtitleRegions:[],segmentSeconds:40,width:1080,height:1920,aiConnections:[],aiSelection:{}},
 projects:[],jobs:[],logs:[],accounts:[],secrets:{},aiProviders:[],connectionKeyStatus:{}
};
const checks=[];
const errors=[];
const calls=[];
let component={active:{id:''},progress:{status:'idle',message:''}};

function check(name,condition){
 assert.ok(condition,name);
 checks.push(name);
 console.log('PASS '+name);
}

const server=http.createServer((req,res)=>{
 const pathname=new URL(req.url,'http://localhost').pathname;
 const target=path.resolve(web,'.'+(pathname==='/'?'/index.html':pathname));
 if(!target.startsWith(web+path.sep)){
  res.writeHead(404).end();
  return;
 }
 fs.readFile(target,(error,data)=>{
  const type=target.endsWith('.js')?'text/javascript':target.endsWith('.css')?'text/css':'text/html; charset=utf-8';
  res.writeHead(error?404:200,{'Content-Type':type});
  res.end(error?'':data);
 });
});

(async()=>{
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 const browser=await chromium.launch({headless:true,executablePath:browserPath});
 const report={ok:false,out,browserPath,browserVersion:browser.version(),checks,errors,calls,
  scope:'Actual Edge loads current product HTML and JavaScript. Component API responses and the file picker are isolated fixtures; no customer data or package installation.'};
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/api/**',async route=>{
   const endpoint=new URL(route.request().url()).pathname.slice(5);
   const body=route.request().method()==='POST'?route.request().postDataJSON():undefined;
   calls.push({endpoint,body});
   let result={};
   if(endpoint==='state')result=structuredClone(fixture);
   else if(endpoint==='environment')result={ffmpeg:true,cores:4,python:'fixture',font:true,gpu:{available:false,adapters:[],detail:'isolated'}};
   else if(endpoint==='source/tasks')result={tasks:[],access:{},native:{}};
   else if(endpoint==='promotion/engines')result={settings:{dramaclip:{},mediakit:{}},dramaclip:{ready:false,missing:[]},mediakit:{hasKey:false}};
   else if(endpoint==='component')result=structuredClone(component);
   else if(endpoint==='browse')result={path:'D:/isolated/engine-fixture.zip'};
   else if(endpoint==='component/import'){
    component={active:{id:''},progress:{status:'verifying',message:'正在校验隔离引擎包',percent:37}};
    result={started:true};
   }
   return route.fulfill({json:result});
  });
  const base='http://127.0.0.1:'+server.address().port;
  await page.goto(base+'/');
  await page.locator('#content .page-heading').waitFor();
  check('fresh_workbench_has_no_activation_form',await page.locator('#activation-form,#token,#machine').count()===0);
  check('navigation_labels_component_page',await page.locator('#nav a[href="#license"]').innerText()==='本地组件');
  await page.locator('#nav a[href="#license"]').click();
  await page.locator('#component-info').waitFor();
  check('legacy_route_renders_component_page',new URL(page.url()).hash==='#license'&&await page.locator('#breadcrumb').innerText()==='本地组件');
  check('device_and_renewal_fields_absent',await page.locator('#license-info,#renew-token,#machine,#activation-form,[data-distribution="renew"]').count()===0);
  check('component_status_visible',(await page.locator('#component-info').innerText()).includes('尚未安装离线 AI 引擎'));
  check('component_import_control_visible',await page.locator('[data-distribution="engine"]').isVisible());
  await page.locator('[data-distribution="engine"]').click();
  await page.waitForFunction(()=>document.querySelector('#component-info').textContent.includes('37%'));
  check('browse_and_import_use_existing_api',calls.some(row=>row.endpoint==='browse'&&row.body?.mode==='engine')&&calls.some(row=>row.endpoint==='component/import'&&row.body?.path==='D:/isolated/engine-fixture.zip'));
  check('component_progress_renders_in_real_dom',(await page.locator('#component-info').innerText()).includes('正在校验隔离引擎包'));
  check('import_button_enabled_after_submission',await page.locator('[data-distribution="engine"]').isEnabled());
  component={active:{id:'lama-isolated-fixture'},progress:{status:'completed',message:'导入完成',percent:100}};
  await page.waitForFunction(()=>document.querySelector('#component-info').textContent.includes('lama-isolated-fixture'));
  check('installed_component_status_renders',(await page.locator('#component-info').innerText()).includes('导入完成'));
  await page.screenshot({path:path.join(out,'component-page.png'),fullPage:true});
  await page.goto(base+'/activation.html');
  await page.waitForURL(base+'/');
  await page.locator('#content .page-heading').waitFor();
  check('legacy_activation_page_redirects_to_workbench',new URL(page.url()).pathname==='/'&&await page.locator('#activation-form,#token,#machine').count()===0);
  check('no_license_endpoint_requested',!calls.some(row=>row.endpoint==='license'||row.endpoint==='license/activate'));
  check('no_browser_runtime_errors',errors.length===0);
  await page.screenshot({path:path.join(out,'direct-workbench.png'),fullPage:true});
  report.ok=true;
 }finally{
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify(report,null,2));
  fs.writeFileSync(path.join(root,'tmp','activation-removed-ui-latest.json'),JSON.stringify(report,null,2));
  await browser.close();
  await new Promise(resolve=>server.close(resolve));
 }
 console.log(JSON.stringify({ok:report.ok,passed:checks.length,report:path.join(out,'report.json')}));
})().catch(error=>{
 console.error(error);
 server.close();
 process.exitCode=1;
});
