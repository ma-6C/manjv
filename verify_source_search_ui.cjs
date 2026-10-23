// Actual Chromium input/IME regression against the integrated source workspace.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {chromium}=require('C:/Users/yumda/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root=__dirname,meta=JSON.parse(fs.readFileSync(path.join(root,'tmp/source-search-ui-host.json'),'utf8'));
const before=process.argv.includes('--before'),checks=[],errors=[],out=path.join(meta.base,'evidence');fs.mkdirSync(out,{recursive:true});
const check=(name,value=true)=>{assert(value,name);checks.push(name);console.log('PASS '+name)};
const seeds=[['聚宝仙盆之杂灵根才是真BOSS第十四季',['玄幻','逆袭']],['灾荒年，我靠灵泉空间养全家',['种田','年代']],['万倍返还：收徒筑基我直接成仙',['玄幻','修仙']],['AI漫剧 Demo',['科幻']]];
const entries=Array.from({length:24},(_,i)=>({seriesId:String(1000+i),title:seeds[i]?.[0]||`验收剧${String(i+1).padStart(2,'0')}`,tags:seeds[i]?.[1]||[i%2?'都市':'玄幻'],totalEpisodes:60+i,url:`https://hongguoduanju.com/detail?series_id=${1000+i}`}));
(async()=>{
const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
const context=await browser.newContext({viewport:{width:1540,height:1080},locale:'zh-CN'});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
const queries=[];
await page.route('**/api/environment',r=>r.fulfill({json:{ffmpeg:true,gpu:{available:false,name:'CPU',detail:'isolated UI fixture',adapters:[]},cores:4,python:'UI acceptance',font:true}}));
await page.route('**/api/source/tasks',r=>r.fulfill({json:{tasks:[],access:{},native:{available:true}}}));
await page.route('**/api/source/resolve',async r=>{
 const b=r.request().postDataJSON();queries.push(b.text);
 if(b.text.includes('/category/')||b.text.startsWith('guoapp:'))return r.fulfill({json:{kind:'catalog',platform:'hongguo_web',url:b.text.startsWith('guoapp:')?'https://hongguoduanju.com/category/comic-drama':b.text,lastPage:3,entries,fetchedAt:Date.now()/1000}});
 const d=entries.find(d=>d.url===b.text);assert(d,'expected selected actual list row');await r.fulfill({json:{kind:'series',platform:'hongguo_web',...d,intro:'界面回归样例',heat:null,rating:null,coverUrl:'',episodes:[1,2,3].map(number=>({number,playerUrl:`https://hongguoduanju.com/player/${d.seriesId}/${number}`})),fetchedAt:Date.now()/1000}});
});
if(before)await page.route('**/source_workspace.js',r=>r.fulfill({contentType:'application/javascript',body:fs.readFileSync(path.join(root,'tmp/source-search-before.js'),'utf8')}));
try{
 await page.goto(meta.launch);await page.locator('#nav a[href="#sources"]').click();await page.getByRole('button',{name:'浏览列表',exact:true}).click();await page.locator('.drama-row').first().waitFor();
 const search=page.locator('#source-filter');await search.focus();await page.evaluate(()=>{window.originalSearchNode=document.querySelector('#source-filter')});
 await page.keyboard.type('abcdef',{delay:50});
 const typed=await search.inputValue(),caret=await search.evaluate(e=>e.selectionStart),sameNode=await search.evaluate(e=>e===window.originalSearchNode);
 if(before){fs.writeFileSync(path.join(root,'tmp/source-search-before-report.json'),JSON.stringify({typed:'abcdef',actual:typed,caret,sameNode,bugReproduced:typed!=='abcdef'||!sameNode},null,2));console.log(JSON.stringify({typed,caret,sameNode}));return;}
 check('continuous_typing_preserves_character_order',typed==='abcdef');check('typing_keeps_original_input_node',sameNode);check('caret_remains_at_end',caret===6);
 await search.fill('abcd');await search.evaluate(e=>e.setSelectionRange(2,2));await page.keyboard.type('XYZ',{delay:40});check('insert_in_middle_preserves_caret',await search.inputValue()==='abXYZcd');
 await search.evaluate(e=>e.setSelectionRange(2,5));await page.keyboard.type('Q');check('selection_replacement_is_correct',await search.inputValue()==='abQcd');await page.keyboard.press('Backspace');check('backspace_removes_expected_character',await search.inputValue()==='abcd');
 await search.fill('');const cdp=await context.newCDPSession(page);
 await page.evaluate(()=>{window.searchCompositionEvents=[];for(const t of ['compositionstart','compositionupdate','compositionend'])document.querySelector('#source-filter').addEventListener(t,e=>window.searchCompositionEvents.push({type:e.type,data:e.data}));});
 await cdp.send('Input.imeSetComposition',{text:'zhong',selectionStart:5,selectionEnd:5});await cdp.send('Input.imeSetComposition',{text:'zhong tian',selectionStart:10,selectionEnd:10});
 check('ime_composition_does_not_destroy_input_node',await search.evaluate(e=>e===window.originalSearchNode&&e===document.activeElement));
 await cdp.send('Input.insertText',{text:'种田'});check('chinese_ime_commit_is_preserved',await search.inputValue()==='种田');
 await page.waitForFunction(()=>document.querySelectorAll('.drama-row').length===1);check('chinese_tag_filters_expected_drama',(await page.locator('.drama-row strong').textContent()).includes('灾荒年'));
 check('ime_has_start_and_end_events',await page.evaluate(()=>window.searchCompositionEvents.some(e=>e.type==='compositionstart')&&window.searchCompositionEvents.some(e=>e.type==='compositionend')));
 await search.fill('AI');await page.keyboard.press('Home');await cdp.send('Input.imeSetComposition',{text:'man',selectionStart:3,selectionEnd:3});await cdp.send('Input.insertText',{text:'漫剧'});check('ime_insertion_at_start_preserves_existing_suffix',await search.inputValue()==='漫剧AI');
 await search.fill('  ai  ');check('latin_search_ignores_case_and_surrounding_spaces',await page.locator('.drama-row').count()===1&&(await page.locator('.drama-row strong').textContent()).includes('AI漫剧'));
 check('filtered_count_matches_results',(await page.locator('#source-filter-count').textContent()).trim()==='1 / 24 部');
 await search.fill('不存在的剧名');check('no_match_has_explicit_feedback',(await page.locator('#source-drama-list').textContent()).includes('没有匹配'));await page.screenshot({path:path.join(out,'01-无匹配反馈.png')});
 await search.fill('玄幻');const expected=entries.filter(r=>r.tags.includes('玄幻')).length;check('tag_search_keeps_all_matching_rows',await page.locator('.drama-row').count()===expected);
 await page.keyboard.press('Escape');await page.waitForFunction(()=>document.querySelector('#source-filter').value==='');check('native_search_escape_clears_and_restores_list',await page.locator('.drama-row').count()===24);
 await page.keyboard.insertText('灵泉');const localQueryCount=queries.length;await page.waitForTimeout(1900);check('background_polling_preserves_input_and_caret',await search.evaluate(e=>e===window.originalSearchNode&&e===document.activeElement&&e.value==='灵泉'&&e.selectionStart===2));
 check('local_filter_makes_no_extra_source_requests',queries.length===localQueryCount);
 await page.locator('.drama-row').click();await page.getByRole('heading',{name:'灾荒年，我靠灵泉空间养全家',exact:true}).waitFor();check('filtered_result_opens_correct_drama',queries.at(-1)===entries[1].url);
 check('filter_value_and_result_survive_opening_drama',await search.inputValue()==='灵泉'&&await page.locator('.drama-row').count()===1);
 await search.focus();await search.fill('<script>alert(1)</script>');check('query_is_rendered_as_text_without_injection',await page.locator('#source-drama-list script').count()===0);await search.fill('');
 await page.getByRole('button',{name:'下一页',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.list-foot span').textContent.trim()==='2 / 3');check('list_pagination_still_works',queries.at(-1).includes('page=2'));
 await search.fill('灵泉');await page.screenshot({path:path.join(out,'02-中文搜索和筛选结果.png')});
 await page.locator('#source-text').fill('https://hongguoduanju.com/detail?series_id=1001');check('link_field_typing_still_works',await page.locator('#source-text').inputValue()==='https://hongguoduanju.com/detail?series_id=1001');
 await page.locator('#source-native-query').fill('万倍返还');check('native_catalog_query_field_is_unchanged',await page.locator('#source-native-query').inputValue()==='万倍返还');
 await page.locator('#source-expression').fill('3,1');await page.getByRole('button',{name:'应用集号',exact:true}).click();check('free_episode_expression_still_applies',(await page.locator('#source-sequence').textContent()).includes('03 → 01'));
 check('no_browser_javascript_errors',errors.length===0);
 fs.writeFileSync(path.join(root,'tmp/source-search-ui-report.json'),JSON.stringify({sourceOnly:!meta.compiled,compiled:!!meta.compiled,version:meta.version,signedDistributionVerified:!!meta.signedDistributionVerified,passed:checks.length,checks,errors,base:meta.base,screenshots:out,sourceRequests:queries.length,fixture:'24 local catalog entries; source APIs stubbed in browser; no network extraction',ime:'Chromium CDP Input.imeSetComposition and Input.insertText'},null,2));
 console.log(JSON.stringify({passed:checks.length,screenshots:out}));
}finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1)});
