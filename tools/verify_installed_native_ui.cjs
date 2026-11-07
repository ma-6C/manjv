// Inspect the actual installed WebView2 executable through its temporary local debug port.
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),net=require('net'),cp=require('child_process');
const scrollChecks=require('./settings_scroll_checks.cjs');
const installation=JSON.parse(fs.readFileSync('tmp/installer-smoke-latest.json','utf8'));
const base=installation.base,exe=path.join(installation.installationDirectory,'漫剧工坊.exe');
const scan=JSON.parse(fs.readFileSync(path.join('versions',installation.version,'defender-scan.json'),'utf8').replace(/^\uFEFF/,''));
if(!scan.noMatchingDetection||!scan.antivirusEnabled||!scan.realTimeProtectionEnabled)throw Error('Candidate scan not clear');
if(require('crypto').createHash('sha256').update(fs.readFileSync(exe)).digest('hex')!==scan.executableSha256)throw Error('Executable changed after scan');
const report={version:installation.version,executable:exe,actualInstalledExecutable:true,checks:[],browserErrors:[]};
const key=process.env.MANJU_REAL_API_KEY;
function check(name,value){if(!value)throw Error(name);report.checks.push(name);console.log('PASS '+name);}
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function port(){const server=net.createServer();await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const value=server.address().port;await new Promise(resolve=>server.close(resolve));return value;}
function save(){const text=JSON.stringify(report,null,2);fs.writeFileSync(path.join(base,'native-ui-report.json'),text);fs.writeFileSync(path.join('versions',installation.version,'native-ui-report.json'),text);}
(async()=>{
 const debugPort=await port(),data=fs.mkdtempSync(path.join(base,'native-data-'));report.nativeDataDirectory=data;
 const app=cp.spawn(exe,[],{cwd:path.dirname(exe),windowsHide:true,stdio:'ignore',env:{...process.env,MANJU_DATA:data,WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS:'--remote-debugging-port='+debugPort}});
 let browser,page;
 try{
  const until=Date.now()+180000;
  while(Date.now()<until){try{browser=await chromium.connectOverCDP('http://127.0.0.1:'+debugPort,{timeout:1500});break;}catch{if(app.exitCode!==null)throw Error('Installed executable exited before WebView became ready');await delay(500);}}
  if(!browser)throw Error('Installed WebView debug port did not become ready');
  for(let i=0;i<60;i++){page=browser.contexts().flatMap(c=>c.pages()).find(p=>p.url().startsWith('http://127.0.0.1:'));if(page)break;await delay(500);}
  if(!page)throw Error('Installed app page not found');
  page.on('pageerror',e=>report.browserErrors.push(key?e.message.replaceAll(key,'[REDACTED]'):e.message));
  page.on('response',async response=>{if(response.url().endsWith('/api/ai/discover-models')){try{const result=await response.json();report.discoveryResponse={status:response.status(),models:result.models?.length,error:result.error,code:result.code};}catch{}}});
  await page.locator('#machine').waitFor({timeout:45000});
  report.nativeWindow=JSON.parse(cp.execFileSync('powershell',['-NoProfile','-NonInteractive','-Command',"Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; public static class CandidateWindow { [DllImport(\"user32.dll\")] public static extern bool IsZoomed(IntPtr hWnd); }'; $taskWindow=(Get-Process -Id "+Number(app.pid)+").MainWindowHandle; @{handle=$taskWindow.ToInt64();maximized=[CandidateWindow]::IsZoomed($taskWindow)} | ConvertTo-Json -Compress"],{windowsHide:true,encoding:'utf8',timeout:15000}));
  check('installed_native_window_starts_maximized',report.nativeWindow.handle!==0&&report.nativeWindow.maximized);
  check('installed_app_starts_and_enforces_activation',await page.locator('#activation-form').isVisible());
  const machine=await page.locator('#machine').inputValue(),tokenFile=path.join(base,'temporary-test-license.txt');
  const issued=cp.spawnSync(path.resolve('授权管理/当前签发工具-v2/授权签发工具.exe'),['--issue',machine,installation.version+'安装验收','1',tokenFile],{windowsHide:true,stdio:'ignore',timeout:30000});
  check('temporary_test_license_issued',issued.status===0&&fs.existsSync(tokenFile));
  await page.locator('#token').fill(fs.readFileSync(tokenFile,'utf8').replace(/^\uFEFF/,'').trim());await page.locator('#activate').click();
  await page.locator('#content').waitFor({timeout:45000});
  check('installed_app_accepts_signed_license_and_opens_workbench',await page.locator('#nav').isVisible());
  check('packaged_license_status_is_valid',await page.evaluate(async()=>{const v=await api('license');return v.required&&v.valid;}));
  report.promotionRuntime=await page.evaluate(()=>api('promotion/engines'));
  check('installed_dramaclip_portable_runtime_is_ready',report.promotionRuntime.dramaclip.ready&&report.promotionRuntime.dramaclip.runtimeReady);
  check('installed_dramaclip_uses_own_portable_runtime',path.resolve(report.promotionRuntime.dramaclip.root)===path.resolve(path.dirname(exe),'engines/dramaclip')&&path.resolve(report.promotionRuntime.dramaclip.python).startsWith(path.resolve(path.dirname(exe),'engines/dramaclip')+path.sep));
  report.xiaovmiao=await require('./installed_xiaovmiao_checks.cjs')(page,{base,data,exe,check});
  await page.evaluate(()=>location.hash='text');await page.locator('.content-ai-trigger').click();await page.locator('#content-ai-tab-image').click();
  check('installed_image_model_editor_present',await page.locator('#content-image-base').isVisible());
  try{report.loadedSSLModules=JSON.parse(cp.execFileSync('powershell',['-NoProfile','-NonInteractive','-Command',"@((Get-Process -Id "+Number(app.pid)+").Modules | Where-Object { $_.ModuleName -match 'libssl|libcrypto|_ssl' } | Select-Object -ExpandProperty FileName) | ConvertTo-Json -Compress"],{windowsHide:true,encoding:'utf8',timeout:10000}));}catch{}
  if(key){
   await page.locator('#content-image-base').fill('https://ai.yuliapi.com');await page.locator('#content-image-key').fill(key);
   await page.waitForFunction(()=>!document.querySelector('#content-image-model-picker').hidden||document.querySelector('#content-image-models-status').classList.contains('error'),{},{timeout:45000});
   check('installed_image_model_query_returns_data',!await page.locator('#content-image-model-picker').evaluate(e=>e.hidden));
   report.imageModels=await page.locator('#content-image-model-choice option').evaluateAll(nodes=>nodes.map(n=>n.value).filter(Boolean));
   check('installed_compiled_backend_fetches_live_models',report.imageModels.length>0);
   await page.locator('#content-image-model-choice').selectOption('gemini-nano-banana-2.1');
   await page.locator('[data-action="content-ai-save"][data-channel="image"]').click();await page.waitForFunction(()=>document.querySelector('#content-image-result').textContent.includes('已保存封面接口'));
   check('installed_image_settings_save_and_clear_key',await page.locator('#content-image-key').inputValue()==='');
  }
  await page.screenshot({path:path.join(base,'安装版-封面接口.png')});
  await page.locator('#content-ai-tab-storage').click();
  check('installed_storage_tab_and_folder_pickers_present',await page.locator('#content-storage-output').isVisible()&&await page.locator('[data-action="content-ai-storage-pick"]').count()===2);
  const storage=path.join(base,'客户选择的保存位置'),projects=path.join(base,'客户选择的剪映工程');
  await page.locator('#content-storage-output').fill(storage);await page.locator('#content-storage-jianying').fill(projects);
  await page.locator('[data-action="content-ai-storage-save"]').click();await page.waitForFunction(()=>document.querySelector('#content-storage-result').textContent.includes('存储位置已保存'));
  check('installed_compiled_backend_saves_and_creates_selected_folders',fs.existsSync(path.join(storage,'工程图'))&&fs.existsSync(projects));
  check('installed_storage_setting_persisted_to_separate_test_data',JSON.parse(fs.readFileSync(path.join(data,'state.json'),'utf8')).config.output===storage);
  await page.screenshot({path:path.join(base,'安装版-存储位置.png')});await page.keyboard.press('Escape');
  await page.evaluate(()=>location.hash='tracks');await page.locator('[data-jianying="settings-open"]').click();
  check('installed_project_settings_show_storage_without_advanced',await page.locator('#jy-storage-output').isVisible()&&await page.locator('#jy-output').isVisible()&&await page.locator('#jy-output').inputValue()===projects);
  await page.keyboard.press('Escape');
  const testSource=path.join(base,'字幕存储验收素材');fs.mkdirSync(testSource,{recursive:true});const video=path.join(testSource,'第001集.mp4');
  const ffmpegFolder=path.join(path.dirname(exe),'_internal','imageio_ffmpeg','binaries');const ffmpeg=path.join(ffmpegFolder,fs.readdirSync(ffmpegFolder).find(n=>n.endsWith('.exe')));
  const made=cp.spawnSync(ffmpeg,['-hide_banner','-loglevel','error','-f','lavfi','-i','testsrc2=size=320x180:rate=15:duration=2','-f','lavfi','-i','sine=frequency=440:duration=2','-shortest','-c:v','libx264','-preset','ultrafast','-c:a','aac',video],{windowsHide:true,encoding:'utf8',timeout:20000});
  check('native_subtitle_test_clip_created',made.status===0&&fs.existsSync(video));
  await page.evaluate(async video=>{await api('tracks/import',{paths:[video]});await api('config',{subtitleMode:'local',gpu:false});await refresh();},video);
  await page.evaluate(()=>location.hash='subtitle');await page.locator('.subtitle-settings-trigger').click();await page.locator('#subtitle-settings-tab-cloud').click();
  check('installed_subtitle_model_editor_present',await page.locator('#content-subtitle-base').isVisible());
  check('installed_subtitle_fixed_save_button_present',await page.locator('[data-action="subtitle-cloud-save"]').isVisible());
  if(key){
   await page.locator('#content-subtitle-base').fill('https://ai.yuliapi.com');await page.locator('#content-subtitle-key').fill(key);
   await page.waitForFunction(()=>!document.querySelector('#content-subtitle-model-picker').hidden,{},{timeout:45000});
   report.subtitleModels=await page.locator('#content-subtitle-model-choice option').evaluateAll(nodes=>nodes.map(n=>n.value).filter(Boolean));
   check('installed_subtitle_settings_fetch_live_models',report.subtitleModels.length>0);
   await page.keyboard.press('Escape');
   check('closing_installed_settings_clears_key',await page.locator('#content-subtitle-key').inputValue()==='');
   check('test_key_not_saved_to_installed_data',!fs.readFileSync(path.join(data,'state.json'),'utf8').includes(key));
  }
  if(!await page.locator('#subtitle-settings-dialog').isVisible())await page.locator('.subtitle-settings-trigger').click();
  await page.locator('#subtitle-settings-tab-storage').click();
  check('installed_subtitle_storage_tab_is_visible',await page.locator('#subtitle-storage-output').isVisible()&&await page.locator('[data-action="subtitle-storage-pick"]').isVisible());
  const subtitleStorage=path.join(base,'安装版去字幕视频保存位置');await page.locator('#subtitle-storage-output').fill(subtitleStorage);await page.locator('[data-action="subtitle-storage-save"]').click();
  await page.waitForFunction(()=>document.querySelector('#subtitle-storage-result').textContent.includes('存储位置已保存'));
  check('installed_subtitle_storage_directory_saved',JSON.parse(fs.readFileSync(path.join(data,'state.json'),'utf8')).config.output===subtitleStorage&&fs.existsSync(subtitleStorage));
  await page.screenshot({path:path.join(base,'安装版-AI去字幕存储位置.png')});
  await page.locator('#subtitle-settings-tab-local').click();
  report.subtitleScroll=await scrollChecks(page,{dialog:'#subtitle-settings-dialog',panel:'.subtitle-settings-panels',header:'.subtitle-settings-header',footer:'.subtitle-settings-footer',nav:'.subtitle-settings-nav',check,prefix:'installed_subtitle'});
  await page.keyboard.press('Escape');
  const job=await page.evaluate(async()=>{const p=state.projects[0];return api('jobs',{kind:'subtitle',ids:[p.id],sourceVideoPaths:{[p.id]:p.videos.map(v=>v.path)}});});
  await page.waitForFunction(id=>['completed','failed','cancelled'].includes(state.jobs.find(j=>j.id===id)?.status),job.id,{timeout:45000});
  const actual=await page.evaluate(id=>({job:state.jobs.find(j=>j.id===id),paths:state.projects.flatMap(p=>p.artifacts).filter(a=>a.job===id&&a.path.endsWith('.mp4')).map(a=>a.path)}),job.id);
  check('installed_actual_subtitle_video_uses_selected_storage',actual.job.status==='completed'&&actual.paths.length>0&&actual.paths.every(p=>p.startsWith(subtitleStorage+path.sep)&&fs.existsSync(p)));
  report.actualSubtitleFiles=actual.paths;
  await page.screenshot({path:path.join(base,'安装版-工作台.png')});check('installed_ui_has_no_runtime_errors',report.browserErrors.length===0);
  report.ok=true;
 }catch(error){report.ok=false;report.error=String(error);if(page){try{report.modelStatus=await page.locator('#content-image-models-status').textContent();report.modelFields=await page.evaluate(()=>({base:document.querySelector('#content-image-base')?.value,protocol:document.querySelector('#content-image-protocol')?.value,provider:document.querySelector('#content-image-provider')?.value,keyPresent:Boolean(document.querySelector('#content-image-key')?.value)}));if(await page.locator('#content').count())await page.screenshot({path:path.join(base,'安装版-检查反馈.png')});}catch{}}throw error;}
 finally{
  save();
  if(app.exitCode===null){try{cp.execFileSync('taskkill',['/PID',String(app.pid),'/T','/F'],{windowsHide:true,stdio:'ignore',timeout:15000});}catch{app.kill();}}
  if(browser)await browser.close().catch(()=>{});
 }
 console.log(JSON.stringify({ok:report.ok,checks:report.checks.length,base}));
})().catch(error=>{console.error(String(error));process.exitCode=1;});
