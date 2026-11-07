const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs');
(async()=>{
 const meta=JSON.parse(fs.readFileSync('tmp/subtitle-settings-ui-host.json','utf8'));
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1366,height:768}});await page.goto(meta.launch+'#subtitle');
  await page.locator('.subtitle-settings-trigger').click();await page.locator('#subtitle-settings-tab-local').click();
  const state=()=>page.evaluate(()=>({background:scrollY,panel:document.querySelector('.subtitle-settings-panels').scrollTop,
   clientHeight:document.querySelector('.subtitle-settings-panels').clientHeight,scrollHeight:document.querySelector('.subtitle-settings-panels').scrollHeight,
   dialogHeight:document.querySelector('#subtitle-settings-dialog').getBoundingClientRect().height}));
  const before=await state();await page.locator('.subtitle-settings-panels').hover();await page.mouse.wheel(0,650);await page.waitForTimeout(250);
  const after=await state();await page.mouse.wheel(0,5000);await page.waitForTimeout(250);await page.mouse.wheel(0,500);await page.waitForTimeout(250);
  const bottom=await state();await page.locator('.subtitle-settings-header h2').hover();await page.mouse.wheel(0,500);await page.waitForTimeout(250);
  const header=await state();const report={before,after,bottom,header};fs.writeFileSync(process.argv[2]||'tmp/subtitle-scroll-probe.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
