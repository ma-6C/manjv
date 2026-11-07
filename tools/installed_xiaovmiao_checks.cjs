// Exercise the module shipped inside the actual installed desktop application.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const delay=ms=>new Promise(r=>setTimeout(r,ms));
module.exports=async function(page,{base,data,exe,check}){
 const originalDatabase='D:\\小v喵\\本地初始化修复_20261103\\本地数据\\.vcat\\offline-local\\vcat.db';
 const originalHash=fs.existsSync(originalDatabase)?crypto.createHash('sha256').update(fs.readFileSync(originalDatabase)).digest('hex'):null;
 const bundle=path.join(path.dirname(exe),'modules','xiaovmiao');
 const manifest=JSON.parse(fs.readFileSync(path.join(bundle,'module.json'),'utf8'));
 const configuredSettings=path.resolve(__dirname,'../data/xiaovmiao.json');
 const profileBefore=[];
 if(fs.existsSync(configuredSettings)){
  const config=JSON.parse(fs.readFileSync(configuredSettings,'utf8'));
  if(config.profile)for(const suffix of ['workspace/.vcat/offline-local/vcat.db','.vcat/offline-local/vcat.db']){
   const file=path.join(config.profile,...suffix.split('/'));
   if(fs.existsSync(file))profileBefore.push({file,sha:crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex')});
  }
 }
 const api=(name)=>page.evaluate(name=>api(name),name);
 const before=await api('xiaovmiao');
 check('installed_xiaovmiao_prefers_shipped_program',before.available&&before.bundled&&before.localMode);
 check('installed_review_entry_is_simplified',(await page.locator('#nav a[href="#publish"]').innerText()).includes('短剧提审'));
 await page.locator('#nav a[href="#promotion"]').click();await page.locator('.promo-flow').waitFor();
 check('installed_promotion_retains_three_local_stages',JSON.stringify(await page.locator('.promo-flow span').allTextContents())===JSON.stringify(['识别剧情','AI 高光与混剪','生成推广视频']));
 check('installed_promotion_has_no_retired_publish_stages',!/(三平台发布挂载|点击跳转核对)/.test(await page.locator('#content').innerText()));
 const workspace=await page.locator('#content').innerText(),hash=await page.evaluate(()=>location.hash);
 const link=page.locator('#nav a[href="#xiaovmiao"]');
 check('installed_xiaovmiao_direct_entry_present',await link.count()===1);
 const response=page.waitForResponse(r=>r.url().endsWith('/api/xiaovmiao/open')&&r.request().method()==='POST',{timeout:240000});
 await link.click();const result=await response;const opened=await result.json();
 check('installed_xiaovmiao_real_launch_succeeds',result.status()===200&&opened.launchRequested);
 await page.waitForFunction(()=>!document.querySelector('#nav a[href="#xiaovmiao"]')?.hasAttribute('aria-busy'));
 check('installed_xiaovmiao_preserves_workspace',await page.locator('#content').innerText()===workspace&&await page.evaluate(()=>location.hash)===hash);
 const files=manifest.files;
 const home=path.join(data,'components','xiaovmiao');
 const roots=fs.readdirSync(home).map(n=>path.join(home,n)).filter(n=>fs.existsSync(path.join(n,'ready.json')));
 check('installed_xiaovmiao_has_private_writable_runtime',roots.length===1);
 const runtime=path.join(roots[0],'程序');
 for(const [name,sha] of Object.entries(files)){
  const actual=crypto.createHash('sha256').update(fs.readFileSync(path.join(runtime,...name.split('/')))).digest('hex');
  if(actual!==sha)throw Error('Private runtime differs from shipped manifest: '+name);
 }
 check('installed_xiaovmiao_private_runtime_files_verified',true);
 const profileRoot=path.join(roots[0],'本地数据');
 const database=manifest.profileLayout==='workspace'?path.join(profileRoot,'workspace','.vcat','offline-local','vcat.db'):
  path.join(profileRoot,'.vcat','offline-local','vcat.db');
 for(let n=0;n<180&&!fs.existsSync(database);n++)await delay(500);
 check('installed_xiaovmiao_initializes_its_own_local_database',fs.existsSync(database)&&fs.readFileSync(database).subarray(0,16).toString()==='SQLite format 3\u0000');
 check('installed_xiaovmiao_keeps_shipped_directory_clean',!fs.existsSync(path.join(bundle,'本地数据')));
 check('installed_xiaovmiao_process_stays_running',(await api('xiaovmiao')).processRunning);
 const selected=JSON.parse(fs.readFileSync(path.join(data,'xiaovmiao.json'),'utf8'));
 check('installed_xiaovmiao_persists_profile_for_future_updates',path.resolve(selected.profile)===path.resolve(path.join(roots[0],'本地数据')));
 if(originalHash)check('installed_xiaovmiao_preserves_original_database',crypto.createHash('sha256').update(fs.readFileSync(originalDatabase)).digest('hex')===originalHash);
 if(profileBefore.length)check('installed_xiaovmiao_preserves_configured_profile_databases',profileBefore.every(p=>crypto.createHash('sha256').update(fs.readFileSync(p.file)).digest('hex')===p.sha));
 await page.screenshot({path:path.join(base,'安装版-小v喵启动入口.png')});
 return {bundledFiles:Object.keys(files).length,runtime,database,mode:manifest.mode,realBundledLaunch:true,
  originalDatabaseChecked:Boolean(originalHash),originalDatabaseUnchanged:originalHash?true:null,
  configuredProfileDatabasesChecked:profileBefore.length,configuredProfileDatabasesUnchanged:profileBefore.length?true:null,platformPublishingTested:false};
};
