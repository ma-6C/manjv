'use strict';

const connectionChannels={text:'文字',image:'封面生图',video:'视频生成',subtitle:'云端字幕'};
const connectionProtocols={text:[['chat','Chat Completions'],['responses','Responses'],['anthropic','Claude Messages'],['gemini','Gemini 原生']],image:[['ark_images','方舟生图'],['openai_images','Images Generations'],['openai_edits','Images Edits'],['gemini_image','Gemini 生图']],video:[['ark_video','方舟视频任务'],['dashscope_video','百炼万相 2.7'],['json_video','自定义异步视频适配器']],subtitle:[['subtitle_json','字幕 JSON 适配器']]};
let connectionFilter='all',editingConnectionId='',connectionModels=[],connectionTests={},generationDraft={name:'我的AI短片',prompt:'',mode:'text',reference:'',duration:5,ratio:'16:9',resolution:'720p'};
function connectionOptions(channel,value='auto',includeLegacy=true){
 const list=(state.config.aiConnections||[]).filter(c=>c.channel===channel&&(c.enabled||c.id===value));
 return `<option value="auto" ${value==='auto'?'selected':''}>自动 · 默认主用 / 按规则备用</option>${includeLegacy&&channel!=='video'?`<option value="legacy" ${value==='legacy'?'selected':''}>沿用原单接口设置</option>`:''}`+list.map(c=>`<option value="${esc(c.id)}" ${value===c.id?'selected':''} ${!c.enabled?'disabled':''}>${esc(c.name)} · ${esc(c.model||'字幕适配器')}${c.enabled?'':'（已停用）'}</option>`).join('');
}
function connectionTaskCard(channels=['text','image','subtitle'],prefix='task-api'){
 return card('本次制作接口','link',`<div class="connection-pickers">${channels.map(c=>`<div class="field"><label for="${prefix}-${c}">${connectionChannels[c]}</label><select id="${prefix}-${c}" data-api-choice="${c}">${connectionOptions(c,state.config.aiSelection?.[c]||'auto')}</select></div>`).join('')}</div><p class="field-hint">直接选择某条连接时只调用这一条；选择“自动”时使用默认主用及已启用的备用顺序。任务开始后保留本次选择。<a href="#api">管理接口</a>。本地字幕与本地排版无需云端接口。</p>`);
}
function apiPage(){
 const all=state.config.aiConnections||[],shown=connectionFilter==='all'?all:all.filter(c=>c.channel===connectionFilter);
 return intro('AI 接口管理','把多条连接集中管理，制作时自由选择。',`<button class="button primary" data-action="connection-new">${icon('plus')}添加连接</button>`)+
 `<div class="connection-overview"><div><strong>${all.length}</strong><span>已配置连接</span></div><div><strong>${Object.values(state.connectionKeyStatus||{}).filter(Boolean).length}</strong><span>本次会话可用密钥</span></div><p>同一平台可添加多个账号或模型。密钥仅存本次运行内存，重启后重新填写。</p></div>`+
 card('连接列表','link',`<div class="connection-toolbar"><div class="connection-tabs">${[['all','全部'],...Object.entries(connectionChannels)].map(([id,label])=>`<button class="region-tab ${connectionFilter===id?'active':''}" data-action="connection-filter" data-channel="${id}" aria-pressed="${connectionFilter===id}">${label}</button>`).join('')}</div><button class="button small" data-action="connection-import">导入当前文字 / 生图设置</button></div><div id="connection-list">${shown.map(connectionRow).join('')||'<div class="connection-empty"><h3>添加你的第一条连接</h3><p>填写服务地址、模型与密钥，再设置主用和备用。</p><button class="button" data-action="connection-new">添加连接</button></div>'}</div>`)+
 card('默认主用与备用顺序','layers',Object.entries(connectionChannels).map(([channel,label])=>routingEditor(channel,label)).join('')+'<p class="field-hint">自动切换用于未获接受的鉴权、限流等失败。视频已经提交后固定查询原任务；提交超时、结果未知时先核对任务ID，避免重复提交。内容过滤、参数错误不会自动改用其他平台。</p>')+
 connectionTaskCard()+card('完整制作自动步骤','spark',toggle('AI 改写剧名与简介','autoText','使用本次选择的文字连接，需填写原始简介。')+toggle('自动制作封面','autoCover','在完整制作流程中生成剧集封面。')+toggle('封面底图使用 AI 生图','autoAICover','同时开启自动制作封面时，调用所选生图连接；关闭时使用本地排版。')+toggle('生成真实工程记录','autoRecords','记录实际素材帧、参数与最终成片。'))+
 `<details class="connection-legacy"><summary>原单接口设置与提示词</summary>${legacyApiPage()}</details>`;
}
function connectionRow(c){
 const rule=state.config.aiRouting?.[c.channel]||{},test=connectionTests[c.id]||state.aiConnectionTests?.[c.id];
 return `<article class="connection-row" data-connection-row="${esc(c.id)}"><div class="connection-row-main"><span class="connection-symbol">${icon(c.channel==='video'?'film':c.channel==='image'?'image':c.channel==='text'?'text':'subtitle')}</span><div><h3>${esc(c.name)} <span class="tag gray">${connectionChannels[c.channel]}</span>${rule.primary===c.id?'<span class="tag">主用</span>':rule.backups?.includes(c.id)?`<span class="tag gray">备用 ${rule.backups.indexOf(c.id)+1}</span>`:''}</h3><p>${esc(c.model||'字幕适配器')} · ${esc(c.base)}</p><small>${c.enabled?'已启用':'已停用'} · ${state.connectionKeyStatus?.[c.id]?'本次密钥已设置':'未设置密钥'}${test?' · '+(test.ok?(test.method==='text_call'?'文字调用通过':'模型列表已验证'):'最近测试失败'):''}</small>${test?.error?`<p class="connection-error">${esc(test.error)}</p>`:''}</div></div><div class="connection-row-actions"><button class="button small" data-action="connection-edit" data-id="${c.id}">编辑 / 密钥</button><button class="button small" data-action="connection-test" data-id="${c.id}">${c.channel==='subtitle'?'试处理入口':'测试连接'}</button><button class="button small" data-action="connection-primary" data-id="${c.id}" ${!c.enabled?'disabled':''}>设为主用</button><button class="button small" data-action="connection-toggle" data-id="${c.id}">${c.enabled?'停用':'启用'}</button><button class="button small subtle" data-action="connection-delete" data-id="${c.id}">移除</button></div></article>`;
}
function routingEditor(channel,label){
 const entries=(state.config.aiConnections||[]).filter(c=>c.channel===channel),rule=state.config.aiRouting?.[channel]||{primary:'',backups:[],autoFallback:false};
 return `<div class="routing-editor"><div class="routing-heading"><strong>${label}</strong><label class="check-label"><input type="checkbox" data-route-fallback="${channel}" ${rule.autoFallback?'checked':''}>失败时自动切换备用</label></div><div class="field"><label for="route-${channel}">默认主用</label><select id="route-${channel}" data-route-primary="${channel}"><option value="">未设置</option>${entries.map(c=>`<option value="${c.id}" ${rule.primary===c.id?'selected':''}>${esc(c.name)}${c.enabled?'':'（已停用）'}</option>`).join('')}</select></div><div class="backup-list">${(rule.backups||[]).map((id,i)=>`<div class="backup-row"><span>${i+1}. ${esc(entries.find(c=>c.id===id)?.name||id)}</span><button class="table-action" data-action="backup-up" data-channel="${channel}" data-index="${i}" ${i===0?'disabled':''} aria-label="上移备用连接">上移</button><button class="table-action" data-action="backup-down" data-channel="${channel}" data-index="${i}" ${i===rule.backups.length-1?'disabled':''} aria-label="下移备用连接">下移</button><button class="table-action" data-action="backup-remove" data-channel="${channel}" data-index="${i}">移除</button></div>`).join('')}</div><div class="backup-add"><select id="backup-add-${channel}" aria-label="选择${label}备用连接"><option value="">选择备用连接…</option>${entries.filter(c=>c.id!==rule.primary&&!rule.backups.includes(c.id)).map(c=>`<option value="${c.id}">${esc(c.name)}</option>`).join('')}</select><button class="button small" data-action="backup-add" data-channel="${channel}">添加备用</button></div></div>`;
}
function connectionInput(label,key,value,type='text',hint=''){
 return `<div class="field"><label for="connection-${key}">${label}</label><input id="connection-${key}" type="${type}" value="${esc(value)}" ${type==='password'?'autocomplete="off"':''} aria-describedby="connection-${key}-error"><p class="connection-inline-error" id="connection-${key}-error"></p>${hint?`<p class="field-hint">${hint}</p>`:''}</div>`;
}
function editConnection(id=''){
 editingConnectionId=id;connectionModels=[];const c=state.config.aiConnections.find(c=>c.id===id)||{name:'',channel:connectionFilter==='all'?'text':connectionFilter,provider:'ark',base:'https://ark.cn-beijing.volces.com/api/v3',model:'',enabled:true,tier:'default',thinking:'default',size:'2K',submitPath:'/videos',pollPath:'/videos/{id}'};
 c.protocol ||= connectionProtocols[c.channel][0][0];
 const select=(label,key,options)=>`<div class="field"><label for="connection-${key}">${label}</label><select id="connection-${key}" ${id&&key==='channel'?'disabled':''}>${options.map(([v,t])=>`<option value="${esc(v)}" ${c[key]===v?'selected':''}>${esc(t)}</option>`).join('')}</select></div>`;
 $('#connection-detail').innerHTML=`<div class="dialog-top"><div><h2>${id?'编辑连接':'添加 API 连接'}</h2><p class="muted">同一平台的多条连接使用各自的密钥。</p></div><button class="icon-button" data-action="connection-close" aria-label="关闭连接编辑">×</button></div><div id="connection-form-error" class="alert warning" role="alert" tabindex="-1" hidden></div>${connectionInput('连接名称','name',c.name)}<div class="grid-2">${select('用途','channel',Object.entries(connectionChannels))}${select('平台','provider',state.aiProviders.map(p=>[p.id,p.name]))}</div>${select('协议','protocol',connectionProtocols[c.channel])}${connectionInput('Base URL','base',c.base,'url','填写服务根地址；模型与密钥需属于这个服务。')}${connectionInput('模型 ID','model',c.model,'text','视频接口请填写对应的文生或图生模型。字幕适配器可留空。')}<div class="grid-2">${select('服务等级（方舟文字）','tier',[['default','default'],['auto','auto'],['fast','fast'],['flex','flex']])}${select('思考模式（文字）','thinking',[['default','跟随平台'],['disabled','关闭'],['enabled','开启']])}</div>${connectionInput('图片尺寸（生图）','size',c.size)}<div id="connection-custom-paths" ${['json_video','subtitle_json'].includes(c.protocol)?'':'hidden'}><div class="grid-2">${connectionInput('提交路径','submitPath',c.submitPath)}${connectionInput('查询路径','pollPath',c.pollPath)}</div><p class="field-hint">自定义视频：POST {model,prompt,image_url,duration,ratio,resolution} → {task_id}；GET 查询路径 → {status,video_url}，路径含 {id}。字幕适配器：POST {video_base64,filename,region} → {task_id} 或 {video_url}，轮询 POST {task_id}。</p></div>${connectionInput('本次会话密钥','key','','password',state.connectionKeyStatus?.[id]?'已设置；留空保留原密钥。':'保存后仅在当前运行中使用。')}<div class="dialog-bottom"><button class="button subtle" data-action="connection-key-clear" ${!id?'disabled':''}>清除当前密钥</button><button class="button primary" data-action="connection-save">保存连接</button></div>`;
 $('#connection-dialog').showModal();$('#connection-name').focus();
}
function readConnection(){
 const get=k=>$('#connection-'+k).value.trim();return {id:editingConnectionId||undefined,name:get('name'),channel:get('channel'),provider:get('provider'),protocol:get('protocol'),base:get('base'),model:get('model'),enabled:state.config.aiConnections.find(c=>c.id===editingConnectionId)?.enabled??true,tier:get('tier'),thinking:get('thinking'),size:get('size'),submitPath:get('submitPath'),pollPath:get('pollPath')};
}
async function saveConnection(){
 const value=readConnection(),errors=[];for(const k of ['name','base'])if(!value[k])errors.push([k,k==='name'?'填写连接名称':'填写接口根地址']);
 if(value.base&&!/^https:\/\//.test(value.base))errors.push(['base','接口地址需使用 HTTPS']);
 if(value.channel!=='subtitle'&&!value.model)errors.push(['model','填写模型 ID']);
 const secret=$('#connection-key').value.trim();if(secret&&(secret.length>4096||/[\s\u0000-\u001f]/.test(secret)))errors.push(['key','密钥包含空格、换行或长度异常']);
 for(const el of $$('[id^="connection-"][aria-invalid]'))el.removeAttribute('aria-invalid');for(const el of $$('.connection-inline-error'))el.textContent='';
 const box=$('#connection-form-error');
 if(errors.length){for(const [key,message]of errors){$('#connection-'+key).setAttribute('aria-invalid','true');$('#connection-'+key+'-error').textContent=message;}box.innerHTML='<strong>请检查以下信息</strong><ul>'+errors.map(([key,msg])=>`<li><a href="#connection-${key}" data-focus-field="connection-${key}">${msg}</a></li>`).join('')+'</ul>';box.hidden=false;box.focus();return;}
 try{const key=$('#connection-key').value,result=await api('ai/connections',{action:'upsert',connection:value});editingConnectionId=result.id;if(key)await api('ai/connection-key',{id:result.id,value:key});delete connectionTests[result.id];$('#connection-key').value='';$('#connection-dialog').close();await refresh(true);toast('连接已保存');}
 catch(error){box.textContent=error.message;box.hidden=false;box.focus();}
}
function generationPage(){
 const d=generationDraft,jobs=state.jobs.filter(j=>j.kind==='video_generate');
 const input=(label,key,type='text')=>`<div class="field"><label for="generation-${key}">${label}</label><input id="generation-${key}" data-generation="${key}" type="${type}" value="${esc(d[key])}" ${key==='duration'?'min="2" max="15" step="1"':''}></div>`;
 return intro('AI 视频生成','选择连接，用文字或参考图生成新视频。')+connectionTaskCard(['video'])+card('创作设置','film',`<div id="generation-error" class="alert warning" role="alert" tabindex="-1" hidden></div>${input('作品名称','name')}<div class="field"><label for="generation-mode">生成方式</label><select id="generation-mode" data-generation="mode"><option value="text" ${d.mode==='text'?'selected':''}>文生视频</option><option value="image" ${d.mode==='image'?'selected':''}>图生视频 · 首帧参考</option></select></div><div class="field"><label for="generation-prompt">视频提示词</label><textarea id="generation-prompt" data-generation="prompt" rows="5" maxlength="4000" placeholder="描述角色、环境、动作、镜头和画面风格">${esc(d.prompt)}</textarea></div><div ${d.mode==='image'?'':'hidden'}>${input('首帧参考图 · 本地路径或 HTTPS 地址','reference')}<button class="button small" data-action="generation-reference">选择本地图片</button><p class="field-hint">图生视频会将这张参考图发送给所选平台。</p></div><div class="grid-2">${input('生成时长（秒）','duration','number')}<div class="field"><label for="generation-ratio">画幅</label><select id="generation-ratio" data-generation="ratio">${['16:9','9:16','1:1','4:3','3:4'].map(v=>`<option ${d.ratio===v?'selected':''}>${v}</option>`).join('')}</select></div><div class="field"><label for="generation-resolution">分辨率</label><select id="generation-resolution" data-generation="resolution">${['720p','1080p'].map(v=>`<option ${d.resolution===v?'selected':''}>${v}</option>`).join('')}</select></div></div><p class="field-hint">按模型实际支持的时长、画幅和分辨率生成。创建任务将调用所选平台并按其规则计费；完成后下载到本机素材库，可继续分集、字幕处理和包装。</p><div class="actions-row"><button class="button primary" data-action="generation-start">${icon('spark')}生成视频</button><a class="button" href="#logs">查看任务与进度</a></div>`)+card('生成记录','layers',jobs.length?jobs.slice().reverse().map(j=>`<div class="generation-result"><div><strong>${esc(j.options?.video?.name||'AI视频')}</strong><p>${esc(statusLabels[j.status]||j.status)} · ${esc(j.stage)}${j.result?' · '+esc(j.result.connectionName):''}</p>${j.error?`<p class="connection-error">${esc(j.error)}</p>`:''}</div>${j.result?`<button class="button small" data-action="play-output" data-path="${esc(j.result.path)}">播放结果</button><a class="button small" href="${media(j.result.path)}&download=1">下载</a>`:'<a href="#logs">查看任务</a>'}</div>`).join(''):'<p class="blank-inline">生成的视频会出现在这里，也会加入素材库。</p>');
}
function taskAPIDetails(job){
 const events=job.aiAttempts||[],remote=job.remoteVideo;
 return `${events.length?`<details class="ai-attempts"><summary>接口调用记录 · ${events.length} 条</summary>${events.map(e=>`<div>${esc(e.name)} · ${esc(({attempt:'开始调用',failed:'调用失败',fallback:'切换备用',submitted:'已提交',succeeded:'完成',resume:'继续查询'})[e.event]||e.event)}${e.detail?' · '+esc(e.detail):''}</div>`).join('')}</details>`:''}${remote?.taskId?`<p class="ai-attempts">云端任务：${esc(remote.taskId)} · ${esc(remote.connection.name)}</p>`:''}${job.kind==='video_generate'&&remote&&!remote.taskId&&['submitting','submission_unknown'].includes(remote.status)&&['failed','paused','interrupted'].includes(job.status)?`<div class="remote-task-form"><input id="remote-task-${job.id}" placeholder="填入平台已有任务ID，继续查询" aria-label="云端任务ID"><button class="button small" data-action="attach-cloud-task" data-id="${job.id}">绑定并继续</button></div>`:''}`;
}
async function connectionAction(action,b){
 if(action==='task-api-dialog'){$('#task-api-detail').innerHTML=connectionTaskCard(current==='generate'?['video']:['text','image','subtitle'],'dialog-api');$('#task-api-dialog').showModal();return true;}
 if(action==='task-api-close'){$('#task-api-dialog').close();renderPage();return true;}
 if(action==='connection-new'){editConnection();return true;}
 if(action==='connection-filter'){connectionFilter=b.dataset.channel;renderPage();return true;}
 if(action==='connection-edit'){editConnection(b.dataset.id);return true;}
 if(action==='connection-close'){$('#connection-dialog').close();renderPage();return true;}
 if(action==='connection-save'){b.disabled=true;try{await saveConnection();}finally{if(b.isConnected)b.disabled=false;}return true;}
 if(action==='connection-key-clear'){await api('ai/connection-key',{id:editingConnectionId,value:''});delete connectionTests[editingConnectionId];await refresh();$('#connection-key').value='';toast('已清除这条连接的会话密钥');return true;}
 if(action==='connection-import'){
  const cfg=state.config;
  for(const channel of ['text','image']){const model=cfg[channel==='text'?'textModel':'imageModel'];if(!model)continue;const provider=cfg[channel==='text'?'textProvider':'imageProvider'];await api('ai/connections',{connection:{name:'原设置 · '+connectionChannels[channel],channel,provider,protocol:cfg[channel==='text'?'textProtocol':'imageProtocol'],base:cfg[channel==='text'?'apiBase':'imageApiBase'],model,enabled:true,tier:cfg.arkServiceTier,thinking:cfg.textThinking,size:cfg.imageSize}});}
  await refresh(true);toast('已导入连接参数，请为新连接分别设置密钥');return true;
 }
 if(action==='connection-test'){
  const c=state.config.aiConnections.find(c=>c.id===b.dataset.id);if(c.channel==='subtitle'){await updateConfig({subtitleMode:'cloud',aiSelection:{...state.config.aiSelection,subtitle:c.id}});location.hash='#subtitle';return true;}
  const old=b.textContent;b.disabled=true;b.textContent='测试中…';try{const result=await api('ai/connection-test',{id:c.id});connectionTests[c.id]=result;toast(result.method==='text_call'?'文字模型实际调用成功':'模型列表查询成功，生成能力需另行试用');}finally{b.disabled=false;b.textContent=old;await refresh(true);}return true;
 }
 if(['connection-toggle','connection-primary','connection-delete'].includes(action)){
  const c=state.config.aiConnections.find(c=>c.id===b.dataset.id);
  if(action==='connection-toggle')await api('ai/connections',{connection:{...c,enabled:!c.enabled}});
  if(action==='connection-delete')await api('ai/connections',{action:'delete',id:c.id});
  if(action==='connection-primary'){const routing=structuredClone(state.config.aiRouting),rule=routing[c.channel];rule.primary=c.id;rule.backups=rule.backups.filter(id=>id!==c.id);await updateConfig({aiRouting:routing});}
  await refresh(true);return true;
 }
 if(action.startsWith('backup-')){
  const routing=structuredClone(state.config.aiRouting),rule=routing[b.dataset.channel],i=Number(b.dataset.index);
  if(action==='backup-add'){const id=$('#backup-add-'+b.dataset.channel).value;if(!id)throw Error('先选择备用连接');rule.backups.push(id);}
  if(action==='backup-remove')rule.backups.splice(i,1);
  if(action==='backup-up'&&i>0)[rule.backups[i-1],rule.backups[i]]=[rule.backups[i],rule.backups[i-1]];
  if(action==='backup-down'&&i<rule.backups.length-1)[rule.backups[i+1],rule.backups[i]]=[rule.backups[i],rule.backups[i+1]];
  await updateConfig({aiRouting:routing});renderPage();return true;
 }
 if(action==='generation-reference'){const result=await api('browse',{mode:'image'});if(result.path){generationDraft.reference=result.path;renderPage();}return true;}
 if(action==='generation-start'){
  const error=$('#generation-error');b.disabled=true;try{await saving;await api('jobs',{kind:'video_generate',ids:[],video:generationDraft,aiSelection:state.config.aiSelection});await refresh();renderPage();toast('视频生成已加入队列');}catch(e){error.textContent=e.message;error.hidden=false;error.focus();}finally{if(b.isConnected)b.disabled=false;}return true;
 }
 if(action==='attach-cloud-task'){
  const input=$('#remote-task-'+b.dataset.id);await api('jobs/attach-remote',{id:b.dataset.id,taskId:input.value.trim()});await api('jobs/control',{id:b.dataset.id,action:'resume'});await refresh(true);return true;
 }
 return false;
}
document.addEventListener('change',async e=>{
 const el=e.target;try{
  if(el.dataset.apiChoice){const selected={...state.config.aiSelection,[el.dataset.apiChoice]:el.value};await updateConfig({aiSelection:selected});}
  if(el.dataset.routePrimary||el.dataset.routeFallback){const channel=el.dataset.routePrimary||el.dataset.routeFallback,routing=structuredClone(state.config.aiRouting),rule=routing[channel];if(el.dataset.routePrimary){rule.primary=el.value;rule.backups=rule.backups.filter(id=>id!==el.value);}else rule.autoFallback=el.checked;await updateConfig({aiRouting:routing});renderPage();}
  if(el.id==='connection-channel'||el.id==='connection-provider'){
   const channel=$('#connection-channel').value,provider=$('#connection-provider').value,p=state.aiProviders.find(p=>p.id===provider);
   const options=connectionProtocols[channel];$('#connection-protocol').innerHTML=options.map(([v,t])=>`<option value="${v}">${t}</option>`).join('');
   if(channel==='text')$('#connection-protocol').value=p.protocol;
   if(channel==='image')$('#connection-protocol').value=provider==='ark'?'ark_images':provider==='gemini'?'gemini_image':'openai_images';
   if(channel==='video')$('#connection-protocol').value=provider==='ark'?'ark_video':provider==='dashscope'?'dashscope_video':'json_video';
   $('#connection-base').value=channel==='video'&&provider==='dashscope'?'https://dashscope.aliyuncs.com/api/v1':p.base||'';
   $('#connection-model').value='';$('#connection-key').value='';$('#connection-custom-paths').hidden=!['json_video','subtitle_json'].includes($('#connection-protocol').value);
   if(el.id==='connection-channel'){$('#connection-submitPath').value=channel==='subtitle'?'/video/clear':'/videos';$('#connection-pollPath').value=channel==='subtitle'?'/video/status':'/videos/{id}';}
  }
  if(el.id==='connection-protocol')$('#connection-custom-paths').hidden=!['json_video','subtitle_json'].includes(el.value);
  if(el.dataset.generation){generationDraft[el.dataset.generation]=el.type==='number'?Number(el.value):el.value;if(el.dataset.generation==='mode')renderPage();}
 }catch(error){toast(error.message,true);}
});
document.addEventListener('input',e=>{if(e.target.dataset.generation)generationDraft[e.target.dataset.generation]=e.target.type==='number'?Number(e.target.value):e.target.value;});
document.addEventListener('click',e=>{const link=e.target.closest('[data-focus-field]');if(link){e.preventDefault();$('#'+link.dataset.focusField)?.focus();}});
