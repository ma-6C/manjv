'use strict';

// The page owns these editors. Existing channel-bound credentials and queued
// task snapshots remain compatible with the former connection manager.
const contentAIChannels={text:'文案接口',image:'封面接口',subtitle:'去字幕接口'},contentAIPageChannels=['text','image'];
const contentAISettingsTabs=[...contentAIPageChannels,'storage'];
const contentAIFields={text:{provider:'textProvider',protocol:'textProtocol',base:'apiBase',model:'textModel',tier:'arkServiceTier',thinking:'textThinking'},image:{provider:'imageProvider',protocol:'imageProtocol',base:'imageApiBase',model:'imageModel',size:'imageSize'},subtitle:{}};
const contentAIProtocols={text:[['chat','Chat Completions'],['responses','Responses'],['anthropic','Claude Messages'],['gemini','Gemini 原生']],image:[['ark_images','方舟生图'],['openai_images','Images Generations'],['openai_edits','Images Edits · 参考图'],['gemini_image','Gemini 生图']],subtitle:[['subtitle_json','字幕任务适配器 · JSON']]};
let contentAITab='text',contentAITrigger=null,contentAIQueue=Promise.resolve();
const contentAIEndpoint=values=>JSON.stringify([values.provider,values.protocol,(values.base||'').trim().replace(/\/+$/,'')]);
function contentAISettingsHTML(){
 return `<dialog id="content-ai-settings" aria-labelledby="content-ai-title"><header class="content-ai-header"><div><h2 id="content-ai-title">文案与封面设置</h2><p>配置生成接口，选择文件保存位置。</p></div><button class="icon-button" data-action="content-ai-close" aria-label="关闭文案与封面设置">×</button></header><div class="content-ai-layout"><nav class="content-ai-nav" role="tablist" aria-label="设置分类" aria-orientation="vertical">${contentAISettingsTabs.map(channel=>`<button id="content-ai-tab-${channel}" role="tab" aria-selected="${contentAITab===channel}" aria-controls="content-ai-panel-${channel}" tabindex="${contentAITab===channel?0:-1}" data-action="content-ai-tab" data-channel="${channel}">${icon(channel==='storage'?'folder':channel==='text'?'text':'image')}${channel==='storage'?'存储位置':contentAIChannels[channel]}</button>`).join('')}</nav><div class="content-ai-panels">${contentAISettingsTabs.map(channel=>`<section id="content-ai-panel-${channel}" role="tabpanel" aria-labelledby="content-ai-tab-${channel}" ${contentAITab===channel?'':'hidden'}></section>`).join('')}</div></div><footer class="content-ai-footer"><span>设置保存在本机；接口密钥仅用于本次运行。</span><button class="button" data-action="content-ai-close">完成</button></footer></dialog>`;
}
function contentStorageHTML(){
 return `<h3>存储位置</h3><p class="field-hint">选择有写入权限的文件夹。保存后会记住位置，用于后续生成任务。</p><div class="field"><label for="content-storage-output">文件保存位置</label><div class="path-field"><input id="content-storage-output" value="${esc(state.config.output)}" spellcheck="false"><button class="button" data-action="content-ai-storage-pick" data-target="content-storage-output">${icon('folder')}选择文件夹</button></div><p class="field-hint">文案、封面、处理后的视频保存于此；新截图保存在其「工程图」子文件夹。</p></div><div class="field"><label for="content-storage-jianying">剪映工程保存位置（可选）</label><div class="path-field"><input id="content-storage-jianying" value="${esc(state.jianyingOptions?.output||'')}" placeholder="留空：文件保存位置下的剪映工程" spellcheck="false"><button class="button" data-action="content-ai-storage-pick" data-target="content-storage-jianying">${icon('folder')}选择文件夹</button></div><p class="field-hint">可以单独选择空间更大的磁盘。旧文件不会自动搬移；视频或工程已移动时，请使用页面上的「重新定位」。</p></div><p id="content-storage-result" class="content-ai-result" role="status" aria-live="polite"></p><button class="button primary" data-action="content-ai-storage-save">${icon('save')}保存存储位置</button>`;
}
function subtitleConnectionDraft(){
 const values={provider:'custom',protocol:'subtitle_json',base:'',model:'',submitPath:'/video/clear',pollPath:'/video/status'};
 try{const submit=new URL(state.config.subtitleEndpoint);if(submit.protocol==='https:'){values.base=submit.origin;values.submitPath=submit.pathname;const poll=new URL(state.config.subtitlePoll);if(poll.origin===submit.origin)values.pollPath=poll.pathname;}}catch{}
 return values;
}
function subtitleCloudConnectionHTML(){return `<div id="content-ai-panel-subtitle">${contentAIForm('subtitle')}</div>`;}
function contentAIChoice(channel){
 const chosen=state.config.aiSelection?.[channel]||'auto';
 return chosen==='auto'&&!(state.config.aiConnections||[]).some(c=>c.channel===channel)?'legacy':chosen;
}
function contentAIConnection(channel,chosen){
 const id=chosen==='auto'?state.config.aiRouting?.[channel]?.primary:chosen;
 return (state.config.aiConnections||[]).find(c=>c.id===id&&c.channel===channel);
}
function contentAIForm(channel,chosen=contentAIChoice(channel)){
 const c=contentAIConnection(channel,chosen),direct=chosen==='legacy',fields=contentAIFields[channel];
 const values=c||(channel==='subtitle'?subtitleConnectionDraft():Object.fromEntries(Object.entries(fields).map(([k,key])=>[k,state.config[key]])));
 const entries=(state.config.aiConnections||[]).filter(c=>c.channel===channel);
 const input=(label,key,type='text',hint='')=>`<div class="field"><label for="content-${channel}-${key}">${label}</label><input id="content-${channel}-${key}" data-content-field="${key}" type="${type}" value="${esc(values[key]||'')}" ${type==='url'?'spellcheck="false"':''}>${hint?`<p class="field-hint">${hint}</p>`:''}</div>`;
 const select=(label,key,options)=>`<div class="field"><label for="content-${channel}-${key}">${label}</label><select id="content-${channel}-${key}" data-content-field="${key}">${options.map(([v,t])=>`<option value="${esc(v)}" ${values[key]===v?'selected':''}>${esc(t)}</option>`).join('')}</select></div>`;
 const hasKey=c?state.connectionKeyStatus?.[c.id]:direct&&state.aiKeyStatus?.[channel];
 return `<h3>${contentAIChannels[channel]}</h3><p class="field-hint">${channel==='text'?'用于 AI 改写剧名与简介。':channel==='image'?'用于 AI 封面底图；本地排版封面无需接口。':'填写字幕服务网址和密钥，获取并选择模型。该服务需支持视频去字幕任务；获取模型列表后，请用短片试处理验证效果。'}</p>${entries.length?`<div class="field"><label for="content-${channel}-choice">使用的接口</label><select id="content-${channel}-choice" data-content-choice="${channel}"><option value="legacy" ${direct?'selected':''}>${channel==='subtitle'?'新建字幕接口':'本页单独配置'}</option><option value="auto" ${chosen==='auto'?'selected':''}>沿用已保存的主用 / 备用</option>${entries.map(c=>`<option value="${esc(c.id)}" ${chosen===c.id?'selected':''}>${esc(c.name)}${c.enabled?'':'（已停用）'}</option>`).join('')}</select><p class="field-hint">${chosen==='auto'?'编辑下方参数会更新当前主用连接；已保存的备用顺序保持不变。':'下方参数只保存到当前所选接口。'}</p></div>`:`<input type="hidden" id="content-${channel}-choice" value="legacy">`}
 <form class="content-ai-form" data-content-channel="${channel}" data-connection-id="${esc(c?.id||'')}" data-has-key="${Boolean(hasKey)}" data-key-identity="${esc(contentAIEndpoint(values))}">${c?input('连接名称','name'):''}${input('接口网址','base','url','填写 HTTPS 网址和密钥后自动获取模型；兼容服务的根网址会自动识别 /v1。')}
 <div class="field"><label for="content-${channel}-key">API 密钥 <span class="tag ${hasKey?'green':'gray'}" id="content-${channel}-key-status">${hasKey?'本次运行已设置':'尚未设置'}</span></label><input id="content-${channel}-key" type="password" autocomplete="off" spellcheck="false" placeholder="${hasKey?'留空保留当前接口的密钥':'填写该平台的 API Key'}"><p class="field-hint">密钥仅在本次运行中使用，更换服务后需填写对应密钥。</p></div>
 <div class="content-ai-models"><div class="content-ai-models-heading"><span>获取模型</span><button type="button" class="button subtle" data-action="content-ai-models" data-channel="${channel}">${icon('refresh')}刷新模型</button></div><p id="content-${channel}-models-status" class="content-ai-models-status" role="status" aria-live="polite">填写网址和密钥后，模型会自动显示在这里。</p><div id="content-${channel}-model-picker" hidden><div class="field"><label for="content-${channel}-model-search">搜索模型</label><input id="content-${channel}-model-search" type="search" autocomplete="off" placeholder="输入模型名称或关键词"></div><div class="field"><label for="content-${channel}-model-choice">平台返回的模型</label><select id="content-${channel}-model-choice"><option value="">请选择模型</option></select></div></div></div>
 ${input('模型 ID / 接入点 ID'+(channel==='subtitle'?'（适配器不要求时可留空）':''),'model','text',channel==='subtitle'?'从列表选择或手动填写。选中的模型会随视频提交；列表可能包含其他用途的模型。':'从上方列表选择，或直接填写完整模型 ID。模型列表不代表每个模型都支持当前用途。')}
 <details class="content-ai-advanced"><summary>高级设置 · ${channel==='subtitle'?'字幕任务协议':'平台与协议'}</summary>${select('服务平台','provider',(state.aiProviders||[]).filter(p=>p.id===values.provider||channel==='text'||(channel==='subtitle'?p.id==='custom':p.images)).map(p=>[p.id,p.name]))}${select('调用协议','protocol',contentAIProtocols[channel])}${channel==='text'?`<div class="grid-2">${select('方舟服务等级','tier',[['default','常规 default'],['auto','自动 auto'],['fast','低延迟 fast'],['flex','低优先级 flex']])}${select('思考模式','thinking',[['default','跟随平台'],['disabled','关闭'],['enabled','开启']])}</div>`:channel==='image'?input('模型输出尺寸','size','text','例如 2K、1024x1536，按模型支持的尺寸填写。'):input('字幕任务提交路径','submitPath','text','相对于上方接口网址，例如 /video/clear；按服务商文档填写。')+input('字幕任务查询路径','pollPath','text','例如 /video/status；仅异步任务使用。')+'<p class="field-hint">字幕适配器接收视频、文件名、选区和可选模型 ID，返回处理后的视频或任务编号。模型查询不会更改字幕任务的提交网址。</p>'}</details>
 <p id="content-${channel}-result" class="content-ai-result" role="status" aria-live="polite"></p><div class="actions-row"><button type="button" class="button primary" data-action="content-ai-save" data-channel="${channel}">${icon('save')}保存${contentAIChannels[channel]}</button><button type="button" class="button" data-action="content-ai-test" data-channel="${channel}">${icon('link')}${channel==='text'?'测试文字调用':channel==='image'?'检测生图连接':'检测模型列表'}</button><button type="button" class="button subtle" data-action="content-ai-clear" data-channel="${channel}">清除密钥</button></div><p class="field-hint">${channel==='text'?'测试会发起一次简短文字请求。':channel==='image'?'连接检测查询模型列表；实际生图请使用页面上的「AI 图生图」。':'检测仅查询模型列表，不上传视频；保存后选择云端方式，用页面上的短片试处理验证实际去字幕。'}</p></form>`;
}
function selectContentAITab(channel,focus=false){
 if(!contentAISettingsTabs.includes(channel))return;contentAITab=channel;
 for(const c of contentAISettingsTabs){
  const tab=$('#content-ai-tab-'+c);tab.setAttribute('aria-selected',String(c===channel));tab.tabIndex=c===channel?0:-1;$('#content-ai-panel-'+c).hidden=c!==channel;
 }
 if(focus)$('#content-ai-tab-'+channel).focus();
 if(channel!=='storage')scheduleContentAIModels(channel);
}
function contentAIResult(channel,message,error=false){
 const el=$('#content-'+channel+'-result');if(el){el.textContent=message;el.classList.toggle('error',error);}
}
function readContentAI(channel,requireModel=true){
 const form=$('.content-ai-form',$('#content-ai-panel-'+channel));
 const values=Object.fromEntries($$('[data-content-field]',form).map(el=>[el.dataset.contentField,el.value.trim()]));
 const chosen=$('#content-'+channel+'-choice').value,key=$('#content-'+channel+'-key').value.trim();let invalid;
 for(const el of $$('[data-content-field]',form))el.removeAttribute('aria-invalid');
 for(const field of ['base',...(requireModel?[...(channel==='subtitle'?[]:['model']),...(form.dataset.connectionId?['name']:[])]:[])])if(!values[field]){const el=$('[data-content-field="'+field+'"]',form);el.setAttribute('aria-invalid','true');invalid||=el;}
 if(invalid){if(requireModel)invalid.focus();throw Error(requireModel?'请填写接口地址并选择或填写模型 ID'+(form.dataset.connectionId?'和连接名称':'')+'。':'请先填写接口网址。');}
 if(!/^https:\/\//i.test(values.base))throw Error('接口地址需使用 HTTPS。');
 if(key&&(key.length>4096||/[\s\u0000-\u001f]/.test(key)))throw Error('密钥包含空格、换行或长度异常。');
 if(channel==='subtitle'&&requireModel)for(const field of ['submitPath','pollPath'])if(!/^\/[A-Za-z0-9_./{}-]{0,180}$/.test(values[field])||values[field].startsWith('//')||values[field].includes('..'))throw Error('字幕任务路径需使用同一接口下的相对路径，例如 /video/clear。');
 if(chosen!=='legacy'&&!form.dataset.connectionId)throw Error('原主用连接未设置，请选择「本页单独配置」或一条已有连接。');
 return {values,chosen,key,id:form.dataset.connectionId};
}
function contentAIModelsStatus(channel,message,error=false){
 const el=$('#content-'+channel+'-models-status');if(el){el.textContent=message;el.classList.toggle('error',error);}
}
function cancelContentAIModels(form,reset=false){
 if(!form)return;clearTimeout(form._modelsTimer);form._modelsAbort?.abort();form._modelsRevision=(form._modelsRevision||0)+1;form._modelsPromise=null;
 const channel=form.dataset.contentChannel,button=$('[data-action="content-ai-models"]',form);button.disabled=false;button.innerHTML=icon('refresh')+'刷新模型';$('.content-ai-models',form).removeAttribute('aria-busy');
 if(reset){form._models=[];$('#content-'+channel+'-model-picker').hidden=true;$('#content-'+channel+'-model-search').value='';contentAIModelsStatus(channel,'填写网址和密钥后自动获取；也可以手动填写模型 ID。');}
}
function scheduleContentAIModels(channel){
 const panel=$('#content-ai-panel-'+channel),form=panel&&$('.content-ai-form',panel);if(!form||form.dataset.busy)return;
 clearTimeout(form._modelsTimer);form._modelsTimer=setTimeout(()=>loadContentAIModels(channel),700);
}
function filterContentAIModels(channel){
 const form=$('.content-ai-form',$('#content-ai-panel-'+channel)),query=$('#content-'+channel+'-model-search').value.trim().toLowerCase(),selected=$('#content-'+channel+'-model').value;
 const models=(form._models||[]).filter(model=>model.toLowerCase().includes(query));
 $('#content-'+channel+'-model-choice').innerHTML=`<option value="">${models.length?'请选择模型（'+models.length+' 个）':'没有匹配的模型'}</option>`+models.map(model=>`<option value="${esc(model)}" ${model===selected?'selected':''}>${esc(model)}</option>`).join('');
}
function inferContentAIProvider(form){
 if(form.dataset.contentChannel==='subtitle')return;
 const base=$('[data-content-field="base"]',form).value.trim();let url;try{url=new URL(base);}catch{return;}
 const channel=form.dataset.contentChannel,presets=state.aiProviders||[],known=presets.find(p=>p.base&&new URL(p.base).hostname===url.hostname),provider=$('[data-content-field="provider"]',form),protocol=$('[data-content-field="protocol"]',form);
 const next=known?.id||'custom';if(provider.value===next)return;
 if(![...provider.options].some(o=>o.value===next))return;
 provider.value=next;protocol.value=channel==='text'?(known?.protocol||'chat'):next==='ark'?'ark_images':next==='gemini'?'gemini_image':next==='openai'?'openai_edits':'openai_images';
 if(channel==='text'){$('[data-content-field="tier"]',form).value='default';$('[data-content-field="thinking"]',form).value=next==='ark'?'disabled':'default';}
}
async function loadContentAIModels(channel,manual=false){
 const panel=$('#content-ai-panel-'+channel),form=panel&&$('.content-ai-form',panel);if(!form||!form.closest('dialog')?.open)return;
 clearTimeout(form._modelsTimer);
 if(form._modelsPromise)return form._modelsPromise;
 const revision=form._modelsRevision||0;if(!manual&&form._modelsFinished===revision)return;
 let request;try{request=readContentAI(channel,false);}catch(error){if(manual)contentAIModelsStatus(channel,error.message,true);return;}
 const identity=contentAIEndpoint(request.values),hasKey=request.key||(form.dataset.hasKey==='true'&&form.dataset.keyIdentity===identity)||form._modelCredential===identity;
 if(!hasKey&&!manual)return;
 const controller=new AbortController();form._modelsAbort=controller;
 const button=$('[data-action="content-ai-models"]',form);button.disabled=true;button.innerHTML=icon('refresh')+'获取中…';$('.content-ai-models',form).setAttribute('aria-busy','true');contentAIModelsStatus(channel,'正在获取当前密钥的模型列表…');
 const current=()=>form.isConnected&&form.closest('dialog')?.open&&(form._modelsRevision||0)===revision;
 const operation=(async()=>{
  try{
   const {provider,protocol,base}=request.values,result=await api('ai/discover-models',{channel,id:request.id||undefined,connection:{provider,protocol,base},...(request.key?{key:request.key}:{})},{signal:controller.signal});
   if(!current())return;
   $('[data-content-field="base"]',form).value=result.base;form._modelCredential=request.key?null:contentAIEndpoint({...request.values,base:result.base});form._models=result.models||[];
   $('#content-'+channel+'-model-picker').hidden=!form._models.length;filterContentAIModels(channel);
   contentAIModelsStatus(channel,form._models.length?(channel==='subtitle'?`已获取 ${form._models.length} 个模型。列表查询成功不代表支持去字幕；选择字幕模型并保存后，请用短片试处理验证。`:`已获取 ${form._models.length} 个模型${result.base!==base?'，已识别接口地址 '+result.base:''}。选择模型后保存；实际调用仍取决于权限、余额和协议。`):'平台返回的模型列表为空。请检查令牌的模型权限，或手动填写模型 ID。',!form._models.length);
  }catch(error){if(current()&&error.name!=='AbortError')contentAIModelsStatus(channel,error.message+' 可更正后刷新，或手动填写模型 ID。',true);}
  finally{if(current()){form._modelsFinished=revision;form._modelsPromise=null;button.disabled=false;button.innerHTML=icon('refresh')+'刷新模型';$('.content-ai-models',form).removeAttribute('aria-busy');}}
 })();form._modelsPromise=operation;return operation;
}
function saveContentAI(channel,clear,request,form){
 const operation=contentAIQueue.catch(()=>{}).then(()=>storeContentAI(channel,clear,request,form));contentAIQueue=operation;return operation;
}
async function storeContentAI(channel,clear,{values,chosen,key,id},form){
 await saving.catch(()=>{});
 if(id||channel==='subtitle'){
  const old=state.config.aiConnections.find(c=>c.id===id)||{channel,name:'云端去字幕',provider:'custom',protocol:'subtitle_json'};
  const response=await api('ai/connections',{action:'upsert',connection:{...old,...values,enabled:true}});state.config=response.config;
  if(!id){id=response.id;chosen=id;if(form.isConnected){form.dataset.connectionId=id;const choice=$('#content-'+channel+'-choice');if(choice.tagName==='SELECT')choice.add(new Option('云端去字幕',id));choice.value=id;form.insertAdjacentHTML('afterbegin',`<div class="field"><label for="content-${channel}-name">连接名称</label><input id="content-${channel}-name" data-content-field="name" value="云端去字幕"></div>`);}}
  await updateConfig({aiSelection:{...state.config.aiSelection,[channel]:chosen}});
  if(key&&!clear)await api('ai/connection-key',{id,value:key});
 }else{
  const patch=Object.fromEntries(Object.entries(contentAIFields[channel]).map(([key,field])=>[field,values[key]]));
  await updateConfig({...patch,aiSelection:{...state.config.aiSelection,[channel]:'legacy'}});
  if(key&&!clear)await api('ai/key',{channel,value:key});
 }
 if(clear)await api(id?'ai/connection-key':'ai/key',id?{id,value:''}:{channel,value:''});
 if(form.isConnected)$('#content-'+channel+'-key',form).value='';await refresh();
 if(!form.isConnected)return id;
 const hasKey=id?state.connectionKeyStatus?.[id]:state.aiKeyStatus?.[channel],badge=$('#content-'+channel+'-key-status');
 $('#content-'+channel+'-key').placeholder=hasKey?'留空保留当前接口的密钥':'填写该平台的 API Key';
 form.dataset.hasKey=String(Boolean(hasKey));form.dataset.keyIdentity=contentAIEndpoint(values);if(clear){form._modelCredential=null;cancelContentAIModels(form,true);}
 if(badge){badge.textContent=hasKey?'本次运行已设置':'尚未设置';badge.className='tag '+(hasKey?'green':'gray');}
 contentAIResult(channel,clear?'已清除当前接口的密钥。':'已保存'+contentAIChannels[channel]+(channel==='subtitle'?'，云端去字幕任务将使用此配置；请在完整制作设置中选择云端方式。':'，后续生成任务将使用此配置。'));return id;
}
async function connectionAction(action,b){
 if(!action.startsWith('content-ai-'))return false;
 if(action==='content-ai-open'){
  contentAITrigger=b;for(const channel of contentAIPageChannels)$('#content-ai-panel-'+channel).innerHTML=contentAIForm(channel);
  $('#content-ai-panel-storage').innerHTML=contentStorageHTML();
  $('#content-ai-settings').showModal();selectContentAITab(contentAITab,true);return true;
 }
 if(action==='content-ai-close'){$('#content-ai-settings').close();return true;}
 if(action==='content-ai-tab'){selectContentAITab(b.dataset.channel,true);return true;}
 if(action==='content-ai-storage-pick'){
  b.disabled=true;try{const result=await api('browse',{mode:'folder'});if(result.path)$('#'+b.dataset.target).value=result.path;}finally{b.disabled=false;}return true;
 }
 if(action==='content-ai-storage-save'){
  b.disabled=true;contentAIResult('storage','正在检查文件夹写入权限…');
  try{await saving;const result=await api('storage/settings',{output:$('#content-storage-output').value.trim(),jianyingOutput:$('#content-storage-jianying').value.trim()});state.config=result.config;state.jianyingOptions=result.options;if(typeof jianyingOptions!=='undefined')jianyingOptions=null;$('#content-storage-output').value=result.config.output;$('#content-storage-jianying').value=result.options.output;contentAIResult('storage','存储位置已保存，文件夹可以写入。后续新任务使用此位置。');}
  catch(error){contentAIResult('storage',error.message,true);}finally{b.disabled=false;}return true;
 }
 const channel=b.dataset.channel,panel=$('#content-ai-panel-'+channel),form=$('.content-ai-form',panel);if(!form||form.dataset.busy)return true;
 if(action==='content-ai-models'){await loadContentAIModels(channel,true);return true;}
 let request;try{request=readContentAI(channel,action!=='content-ai-clear');}catch(error){contentAIResult(channel,error.message,true);return true;}
 if(channel==='subtitle'&&action==='content-ai-clear'&&!request.id){$('#content-subtitle-key').value='';cancelContentAIModels(form,true);contentAIResult(channel,'已清除当前输入的密钥。');return true;}
 const controls=$$('input,select,button',panel);form.dataset.busy='true';controls.forEach(el=>el.disabled=true);
 try{
  if(action!=='content-ai-clear'){await loadContentAIModels(channel);request=readContentAI(channel);}else cancelContentAIModels(form,true);
  contentAIResult(channel,action==='content-ai-test'?'正在保存配置并检测连接…':'正在保存…');const id=await saveContentAI(channel,action==='content-ai-clear',request,form);
  if(action==='content-ai-test'){
   const result=await api(id?'ai/connection-test':channel==='text'?'test-api':'ai/models',id?{id}:channel==='image'?{channel}:{});
   if(form.isConnected)contentAIResult(channel,channel==='text'?`文字模型实际调用成功${result.seconds!=null?' · '+result.seconds+' 秒':''}。`:channel==='subtitle'?`已获取模型列表（${result.modelCount??result.models?.length??0} 个）；尚未上传视频，请用短片试处理验证去字幕。`:`已获取模型列表（${result.models?.length||0} 个）；实际生图尚需在页面生成封面。`);
  }
 }catch(error){if(form.isConnected)contentAIResult(channel,error.message,true);}
 finally{delete form.dataset.busy;controls.forEach(el=>el.disabled=false);}
 return true;
}
document.addEventListener('change',e=>{
 const el=e.target;if(el.dataset.contentChoice){const channel=el.dataset.contentChoice;cancelContentAIModels($('.content-ai-form',$('#content-ai-panel-'+channel)));$('#content-ai-panel-'+channel).innerHTML=contentAIForm(channel,el.value);scheduleContentAIModels(channel);return;}
 if(el.id===`content-${el.closest('.content-ai-form')?.dataset.contentChannel}-model-choice`){const channel=el.closest('.content-ai-form').dataset.contentChannel;if(el.value){$('#content-'+channel+'-model').value=el.value;contentAIResult(channel,'已选择模型，请保存'+contentAIChannels[channel]+'。');}return;}
 if(el.dataset.contentField==='provider'){
  const form=el.closest('.content-ai-form'),channel=form.dataset.contentChannel,p=(state.aiProviders||[]).find(p=>p.id===el.value);if(!p)return;
  const set=(key,value)=>{$('[data-content-field="'+key+'"]',form).value=value;};
  set('protocol',channel==='subtitle'?'subtitle_json':channel==='text'?p.protocol:p.id==='ark'?'ark_images':p.id==='gemini'?'gemini_image':p.id==='openai'?'openai_edits':'openai_images');
  if(p.base&&channel!=='subtitle')set('base',p.base);set('model','');$('#content-'+channel+'-key').value='';
  if(channel==='text'){set('tier','default');set('thinking',p.id==='ark'?'disabled':'default');}else if(channel==='image')set('size',p.id==='ark'?'2K':'1024x1536');
 }
 if(['provider','protocol'].includes(el.dataset.contentField)){const form=el.closest('.content-ai-form');cancelContentAIModels(form,true);scheduleContentAIModels(form.dataset.contentChannel);}
 if(el.dataset.contentField){const channel=el.closest('.content-ai-form').dataset.contentChannel;contentAIResult(channel,'修改尚未保存，请点击保存'+contentAIChannels[channel]+'。');if(['provider','protocol','base'].includes(el.dataset.contentField))$('#content-'+channel+'-key-status').textContent='保存后核对密钥状态';}
});
document.addEventListener('input',e=>{
 const el=e.target,form=el.closest('.content-ai-form');if(!form)return;const channel=form.dataset.contentChannel;
 if(el.id==='content-'+channel+'-model-search'){filterContentAIModels(channel);return;}
 if(el.dataset.contentField==='base')inferContentAIProvider(form);
 if(el.dataset.contentField==='base'||el.id==='content-'+channel+'-key'){cancelContentAIModels(form,true);scheduleContentAIModels(channel);}
});
document.addEventListener('submit',e=>{if(e.target.matches('.content-ai-form')){e.preventDefault();e.target.querySelector('[data-action="content-ai-save"]').click();}});
document.addEventListener('keydown',e=>{
 const tab=e.target.closest('#content-ai-settings [role="tab"]');if(!tab)return;const keys=contentAISettingsTabs,i=keys.indexOf(contentAITab);let next;
 if(['ArrowDown','ArrowRight'].includes(e.key))next=keys[(i+1)%keys.length];if(['ArrowUp','ArrowLeft'].includes(e.key))next=keys[(i+keys.length-1)%keys.length];
 if(e.key==='Home')next=keys[0];if(e.key==='End')next=keys[keys.length-1];if(next){e.preventDefault();selectContentAITab(next,true);}
});
document.addEventListener('close',e=>{
 const channels=e.target.id==='content-ai-settings'?contentAIPageChannels:e.target.id==='subtitle-settings-dialog'?['subtitle']:[];
 for(const channel of channels){const panel=$('#content-ai-panel-'+channel);cancelContentAIModels(panel&&$('.content-ai-form',panel));const input=$('#content-'+channel+'-key');if(input)input.value='';}
 if(e.target.id==='content-ai-settings'&&contentAITrigger?.isConnected)contentAITrigger.focus({preventScroll:true});
},true);
function taskAPIDetails(job){
 const events=job.aiAttempts||[],remote=job.remoteVideo;
 return `${events.length?`<details class="ai-attempts"><summary>接口调用记录 · ${events.length} 条</summary>${events.map(e=>`<div>${esc(e.name)} · ${esc(({attempt:'开始调用',failed:'调用失败',fallback:'切换备用',submitted:'已提交',succeeded:'完成',resume:'继续查询'})[e.event]||e.event)}${e.detail?' · '+esc(e.detail):''}</div>`).join('')}</details>`:''}${remote?.taskId?`<p class="ai-attempts">历史云端任务：${esc(remote.taskId)} · ${esc(remote.connection?.name||'')}</p>`:''}${job.moduleRetired?'<p class="field-hint">视频生成已停用，历史记录与已有视频保留；未结束的云端任务请到原服务商核对。</p>':''}`;
}
