// Run test_content_settings_host.py first. This checks real config endpoints.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),assert=require('assert');
const meta=JSON.parse(fs.readFileSync('tmp/content-settings-host.json','utf8')),checks=[];
const check=(name,value)=>{assert(value,name);checks.push(name);console.log('PASS '+name);};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'});
 try{
  const page=await browser.newPage({viewport:{width:1540,height:1050}}),errors=[],jobs=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/api/jobs',route=>{jobs.push(route.request().postDataJSON());return route.fulfill({status:409,json:{error:'No real jobs in UI settings check'}});});
  await page.goto(meta.launch+'#cost');await page.locator('#config-costOrganization').waitFor();
  check('report_signature_fields_are_on_cost_page',await page.locator('#config-costRepresentative,#config-costReportDate').count()===2);
  check('old_actor_row_is_recognized',await page.locator('[data-cost-actor="0"]').isChecked());
  await page.locator('[data-cost-amount="0"]').fill('3000');await page.locator('[data-cost-amount="0"]').dispatchEvent('change');await page.waitForFunction(()=>state.config.costRows[0].amount===3000);
  await page.locator('[data-cost-amount="1"]').fill('7000');await page.locator('[data-cost-amount="1"]').dispatchEvent('change');await page.waitForFunction(()=>state.config.costRows[1].amount===7000);
  check('actor_summary_is_calculated_from_amounts',(await page.locator('#cost-actor-summary').textContent()).includes('30.00%'));
  await page.locator('[data-cost-name="0"]').fill('自定义演员费用');await page.locator('[data-cost-name="0"]').dispatchEvent('change');await page.waitForFunction(()=>state.config.costRows[0].name==='自定义演员费用');
  check('renaming_preserves_actor_classification',await page.evaluate(()=>state.config.costRows[0].actor===true));
  await page.locator('[data-cost-actor="1"]').check();await page.waitForFunction(()=>state.config.costRows[1].actor===true);check('explicit_checkbox_updates_actor_total',(await page.locator('#cost-actor-summary').textContent()).includes('100.00%'));
  await page.locator('[data-cost-actor="1"]').uncheck();await page.waitForFunction(()=>state.config.costRows[1].actor===false);
  for(const [key,value] of [['costOrganization','样式核验单位'],['costRepresentative','样式核验人'],['costReportDate','2026-10-31']]){await page.locator('#config-'+key).fill(value);await page.locator('#config-'+key).dispatchEvent('change');await page.waitForFunction(([k,v])=>state.config[k]===v,[key,value]);}
  await page.reload();await page.locator('#config-costOrganization').waitFor();check('organization_and_date_persist_after_reload',await page.locator('#config-costOrganization').inputValue()==='样式核验单位'&&await page.locator('#config-costReportDate').inputValue()==='2026-10-31');
  await page.screenshot({path:path.join(meta.base,'成本报告-页面.png'),fullPage:true});
  await page.evaluate(()=>location.hash='tracks');await page.waitForSelector('[data-jianying="settings-open"]');await page.locator('[data-jianying="settings-open"]').click();
  check('first_draft_mouse_click_option_is_removed',!(await page.locator('#jy-settings-dialog').textContent()).includes('双击已确认的工程卡片')&&!(await page.locator('#jy-settings-dialog').textContent()).includes('临时封面标记'));
  check('manual_open_guidance_is_present',(await page.locator('#jy-settings-dialog').textContent()).includes('手动打开对应工程'));
  check('editing_never_starts_tasks',jobs.length===0);check('no_browser_runtime_errors',errors.length===0);
  fs.writeFileSync('tmp/cost-ui-report.json',JSON.stringify({ok:true,checks,errors},null,2));console.log(JSON.stringify({ok:true,passed:checks.length}));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
