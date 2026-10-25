const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path');
(async()=>{const meta=JSON.parse(fs.readFileSync('tmp/subtitle-full-ui-host.json','utf8'));const b=await chromium.launch({headless:true,executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'}),p=await b.newPage({viewport:{width:1440,height:1080}}),checks=[],errors=[];p.on('pageerror',e=>errors.push(e.message));
const check=(n,v)=>{if(!v)throw Error(n);checks.push(n);console.log('PASS '+n);};const api=async(name,body)=>{const r=await p.request[body?'post':'get'](meta.url+'/api/'+name,body?{data:body,headers:{'X-Local-Client':'1'}}:{});const j=await r.json();if(!r.ok())throw Error(j.error);return j;};
async function wait(id){const end=Date.now()+90000;while(Date.now()<end){const s=await api('state'),j=s.jobs.find(j=>j.id===id);if(!['queued','running','pausing'].includes(j.status)){check('UI '+j.result?.engine+' preview completes',j.status==='completed');return j;}await p.waitForTimeout(200);}throw Error('job timed out');}
async function choose(value){await p.locator('#config-vsrMode').selectOption(value);await p.evaluate(()=>saving);await p.waitForFunction(value=>document.querySelector('#config-vsrMode')?.value===value,value);}
async function preview(){const pending=p.waitForResponse(r=>r.url().endsWith('/api/jobs')&&r.request().method()==='POST');await p.locator('[data-action="subtitle-preview"][data-seconds="5"]').click();const r=await pending,j=await r.json();if(!r.ok())throw Error(j.error);return wait(j.id);}
try{await p.goto(meta.launch);await api('config',{subtitleMode:'cloud',vsrMode:'lama-box',lamaDevice:'auto'});await p.goto(meta.url+'/#subtitle');await p.reload();await p.waitForSelector('#config-vsrMode');
check('two_distinct_local_repair_options',await p.locator('#config-vsrMode option[value="sttn-auto"]').count()===1&&await p.locator('#config-vsrMode option[value="lama-box"]').count()===1);
check('recognition_models_not_mislabeled_as_repair_engines',!(await p.locator('#config-vsrMode').textContent()).match(/Whisper|RapidOCR|超人/));
await choose('sttn-auto');check('choosing_local_engine_selects_local_AI_processing',(await api('state')).config.subtitleMode==='vsr');
const first=await preview();check('first_preview_records_STTN_engine',first.result.engine==='sttn-auto');
await p.waitForFunction(()=>document.querySelector('#subtitle-preview-result')?.textContent.includes('STTN 时序修复'));
await choose('lama-box');await p.waitForFunction(()=>document.querySelector('#subtitle-preview-result')?.textContent.includes('修复引擎已改变'));
check('old_preview_is_marked_stale_after_engine_change',true);check('old_preview_retains_its_actual_engine_label',(await p.locator('#subtitle-preview-result').textContent()).includes('STTN 时序修复'));
const second=await preview();check('second_preview_records_LaMa_engine',second.result.engine==='lama-box');await p.waitForFunction(()=>document.querySelector('#subtitle-preview-result')?.textContent.includes('LaMa 逐帧修复'));
await p.waitForFunction(()=>{const v=document.querySelector('#preview-after');return v&&v.readyState>=2&&v.videoWidth>0;});check('LaMa_H264_output_decodes_in_actual_Edge',true);
await p.locator('#preview-after').evaluate(async v=>{v.muted=true;await v.play();});await p.waitForFunction(()=>document.querySelector('#preview-after').currentTime>.1);check('LaMa_output_can_play',true);await p.locator('#preview-after').evaluate(v=>v.pause());
await p.locator('#config-vsrMode').scrollIntoViewIfNeeded();await p.screenshot({path:path.join(meta.base,'本地双引擎-实际界面.png'),fullPage:true});
await p.reload();await p.waitForSelector('#config-vsrMode');check('selected_engine_survives_page_reload',await p.locator('#config-vsrMode').inputValue()==='lama-box');
check('whole_episode_and_series_actions_remain',await p.locator('[data-action="subtitle-full"]').count()===2);check('original_STTN_job_stays_STTN_after_switch',(await api('state')).jobs.find(j=>j.id===first.id).result.engine==='sttn-auto');
await p.setViewportSize({width:980,height:800});check('narrow_layout_no_document_overflow',await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));check('no_runtime_errors',errors.length===0);
fs.writeFileSync(path.join(meta.base,'two-engines-ui-report.json'),JSON.stringify({ok:true,checks,errors,STTN:first.id,LaMa:second.id},null,2));console.log(JSON.stringify({ok:true,checks:checks.length,base:meta.base}));
}finally{await b.close();}})().catch(e=>{console.error(e);process.exit(1);});
