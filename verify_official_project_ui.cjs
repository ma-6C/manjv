// Actual Edge UI checks against an isolated source host. No official capture,
// application launch, file import, upload or submission is triggered.
const fs=require('fs'),path=require('path'),assert=require('assert');
const runtime=path.resolve(path.dirname(process.execPath),'../node_modules/playwright');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||runtime);
const metadata=JSON.parse(fs.readFileSync(process.argv[2]||path.join(__dirname,'tmp/publish-ui-host.json'),'utf8'));
assert(metadata.sourceOnly===true,'Only isolated source hosts may be tested');
const checks=[],check=(name,value)=>{assert(value,name);checks.push(name);};
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.EDGE_EXE||'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage(),errors=[],captures=[],imports=[];
  page.on('pageerror',error=>errors.push(String(error)));
  await page.route('**/api/project-evidence/capture',route=>{captures.push(route.request().postDataJSON());return route.fulfill({contentType:'application/json',body:JSON.stringify({windows:[],note:'受控测试，不枚举真实窗口'})});});
  await page.route('**/api/browse',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({paths:['C:/controlled-source-test/manual.png']})}));
  await page.route('**/api/project-evidence/import',route=>{imports.push(route.request().postDataJSON());return route.fulfill({contentType:'application/json',body:'{"items":[]}'});});
  await page.goto(metadata.launch+'#tracks');
  await page.getByRole('heading',{name:'剪映工程与截图',exact:true}).waitFor();
  check('真实工程入口替换原绘图入口',await page.getByRole('link',{name:'剪映工程与截图',exact:true}).count()===1);
  check('四步实际工程流程',await page.locator('.official-project-steps li').count()===4);
  check('移除仿真轨道布局和PNG生成按钮',await page.locator('.track-layouts,[data-track="generate"],[data-track="preview-one"],.track-preview-image').count()===0);
  check('第三方草稿桥接明确标示',await page.getByText('草稿通过第三方格式桥接生成；请在剪映核对素材、预览和时间线，再采集实际工程截图。',{exact:true}).count()===1);
  const search=page.locator('#track-query');await search.focus();await search.pressSequentially('abcdef');
  await page.evaluate(()=>{window._officialSearch=document.querySelector('#track-query');const input=window._officialSearch;input.setSelectionRange(3,3);});
  await page.evaluate(()=>refresh(false));
  check('搜索框保留DOM与中间光标',await page.evaluate(()=>document.querySelector('#track-query')===window._officialSearch&&window._officialSearch.selectionStart===3));
  await search.pressSequentially('X');check('输入中间插入正常',await search.inputValue()==='abcXdef');
  await search.fill('');await page.locator('[data-track-path]').first().check();
  check('底部主操作为建立真实草稿',await page.locator('#start-pipeline').getAttribute('data-jianying')==='generate');
  check('工程截图固定剪映且移除来源切换',await page.locator('#jy-evidence-platform').count()===0&&await page.getByRole('heading',{name:'剪映实际工程截图',exact:true}).count()===1);
  check('即梦入口和提示已移除',await page.locator('[data-jianying="jimeng"]').count()===0&&!(await page.locator('#content').textContent()).includes('即梦'));
  await page.locator('[data-jianying="capture"]').click();
  await page.waitForFunction(()=>document.querySelector('#jy-evidence-status')?.textContent.includes('没有找到'));
  check('采集请求只使用剪映来源且不触发真实采集',captures.length===1&&captures[0].platform==='jianying'&&!captures[0].windowId);
  const legacy=await page.evaluate(()=>{const previous=jyEvidenceItems;try{jyEvidenceItems=[{platform:'jimeng',source:'window_capture',officialEvidence:{appVerified:true},url:'data:image/png;base64,',capturedAt:1}];return jyEvidenceHTML();}finally{jyEvidenceItems=previous;}});
  check('历史其他来源保留历史标记且不冒充剪映核验',legacy.includes('历史来源 · 不参与工程核验')&&!legacy.includes('tag green')&&!legacy.includes('官方窗口来源已核验'));
  const retired=await page.evaluate(async()=>{try{await api('project-evidence/open',{platform:'removed_platform'});return '';}catch(e){return e.message;}});
  check('旧网页打开接口明确停用',retired.includes('网页工程入口已停用'));
  check('手动图片来源边界说明',await page.getByText('可选择本机图片。手动导入会标记为「本人确认，来源未核验」，不冒认为本工具已验证的官方窗口截图。',{exact:true}).count()===1);
  await page.locator('.jy-manual-import summary').click();
  await page.locator('#jy-evidence-note').fill('本机界面验收，不用于平台提交。');
  await page.evaluate(()=>window.scrollTo(0,700));const scroll=await page.evaluate(()=>window.scrollY);
  await page.evaluate(()=>refresh(false));
  check('刷新保留截图说明与滚动位置',await page.locator('#jy-evidence-note').inputValue()==='本机界面验收，不用于平台提交。'&&Math.abs(await page.evaluate(()=>window.scrollY)-scroll)<2);
  await page.locator('#jy-evidence-confirm').check();await page.locator('[data-jianying="import-evidence"]').click();
  await page.waitForFunction(()=>document.querySelector('#jy-evidence-status')?.textContent.includes('截图已导入'));
  check('手动导入固定剪映来源且保留本人确认',imports.length===1&&imports[0].platform==='jianying'&&imports[0].userConfirmed===true);
  check('没有以旧分轨图填充截图区域',await page.locator('.track-preview-image,.track-result').count()===0);
  await page.setViewportSize({width:390,height:844});await page.waitForTimeout(100);
  check('窄屏不横向溢出',await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+2));
  check('实际浏览器没有JS异常',errors.length===0);
  await page.setViewportSize({width:1440,height:1000});
  const checkedPlan=await page.evaluate(()=>api('publish/inspect',{projectId:activeProject().id}));
  await page.goto(metadata.url+'/#publish');
  if(checkedPlan.files.proofImages.length){
   const proofLabel=checkedPlan.checks.find(c=>c.key==='proofImages').label;
   const proofRow=page.locator('.publishing-check').filter({has:page.getByText(proofLabel,{exact:true})});await proofRow.waitFor();
   check('已登记官方截图反映在发布清单',await proofRow.evaluate(e=>e.classList.contains('ready')));
   await page.goto(metadata.url+'/#tracks');await page.getByRole('heading',{name:'剪映工程与截图',exact:true}).waitFor();
   await page.locator('.jy-evidence-item img').first().waitFor();
   await page.waitForFunction(()=>[...document.querySelectorAll('.jy-evidence-item img')].some(e=>e.complete&&e.naturalWidth>0));
   check('真实采集原图在工作区可读取',await page.getByText('官方窗口来源已核验',{exact:true}).count()>0);
  }else{
   const proofLink=page.getByRole('link',{name:'去采集官方截图',exact:true});await proofLink.waitFor();
   check('发布缺项直达实际工程采集',await proofLink.getAttribute('href')==='#tracks');
   check('未核验工程图不会显示已准备',await proofLink.evaluate(a=>!a.closest('.publishing-check').classList.contains('ready')));
   await proofLink.click();await page.getByRole('heading',{name:'剪映工程与截图',exact:true}).waitFor();
  }
  await page.evaluate(()=>window.scrollTo(0,0));
  const screenshot=path.join(metadata.base,'真实工程工作区-实际界面.png');await page.screenshot({path:screenshot,fullPage:true});
  const report={passed:checks.length,checks,screenshot,scope:'Actual Edge source UI only; no official editor screenshot or submission claimed'};
  fs.writeFileSync(path.join(metadata.base,'official-project-ui-report.json'),JSON.stringify(report,null,2));
  console.log(JSON.stringify({passed:checks.length,report:path.join(metadata.base,'official-project-ui-report.json')}));
 }finally{await browser.close();}
})().catch(error=>{console.error(String(error).split(metadata.launch).join('[local launch]'));process.exitCode=1;});
