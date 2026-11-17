const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'index.html'),'utf8');const code=html.split('<script>')[1].split('</script>')[0];
const elements={};const el=id=>elements[id]??=( {id,innerHTML:'',textContent:'',value:'',hidden:false,style:{},dataset:{},classList:{toggle(){}},addEventListener(type,fn){this['handler_'+type]=fn},querySelectorAll(){return[]},showModal(){this.open=true},close(){this.open=false},focus(){},after(){},add(){},replaceChildren(){this.innerHTML=''}} );
const handlers={};const storage={};Object.defineProperties(storage,{getItem:{value:k=>storage[k]??null},setItem:{value:(k,v)=>storage[k]=v},removeItem:{value:k=>delete storage[k]}});
let requests=[],delayed=false,pending=[],fail=false;
const makeData=url=>{const u=new URL(url,'https://test');if(u.pathname==='/api/categories')return {categories:['未分類','研究']};if(u.pathname==='/api/folders')return {folders:[{name:'Art',total:120,image:''}]};const p=Number(u.searchParams.get('page')||1);return{items:[{id:'articles:'+p,type:'article',title:'Page '+p,summary:'summary',added:'2026-11-14T00:00:00'}],total:7780,page:p,page_size:30,sources:['Review'],issues:[]}};
const context={confirm:()=>true,console,URL,URLSearchParams,Date,JSON,Set,Map,Math,Number,String,Object,Array,Boolean,RegExp,Promise,AbortController,
 document:{createElement:()=>el('created'),getElementById:el,body:{classList:{toggle(){}}},addEventListener:(type,fn)=>handlers[type]=fn,hidden:false},
 localStorage:storage,location:{replace(path){this.target=path}},setTimeout:()=>1,clearTimeout(){},
 fetch:async (url,opts)=>{requests.push(url);if(delayed)await new Promise(resolve=>pending.push(resolve));if(fail)throw Error('offline');return{ok:true,status:200,json:async()=>makeData(url)}}};
context.window=context;context.MONOREADER_BOOT={expires:Date.now()/1000+43200,cacheKey:'test-db'};context.addEventListener=(k,f)=>handlers[k]=f;
vm.createContext(context);const run=s=>vm.runInContext(s,context),flush=()=>new Promise(r=>setImmediate(r));
(async()=>{
 run(code);await flush();assert.equal(requests.length,1);assert(requests[0].startsWith('/api/browse'));
 assert(el('content').innerHTML.includes('Page 1'));
 run("state.tab='分類存檔';state.page=20;load()");await flush();assert(el('content').innerHTML.includes('Page 20'));
 const before=requests.length;run('load()');await flush();assert.equal(requests.length,before);assert(el('connection').textContent.includes('快取'));
 delayed=true;const task=run('load(true)');assert(el('content').innerHTML.includes('Page 20'));assert(el('connection').textContent.includes('快取'));pending.shift()();await task;delayed=false;
 // Old slow page must not overwrite newer navigation.
 delayed=true;run('state.page=21;load(true)');run('state.page=22;load(true)');pending[1]();await flush();pending[0]();await flush();pending=[];delayed=false;assert(el('content').innerHTML.includes('Page 22'));assert(!el('content').innerHTML.includes('Page 21'));
 fail=true;await run('load(true)');assert(el('connection').textContent.includes('更新失敗'));assert(el('content').innerHTML.includes('Page 22'));fail=false;
 run("state.module='omni';state.tab='分類資料夾';state.folder='';load(true)");await flush();assert(el('content').innerHTML.includes('120 個項目'));
 assert(Object.keys(storage).some(k=>k.startsWith('monoreader-pages-')));
 handlers.submit({target:{matches:()=>true},preventDefault(){}});assert(!Object.keys(storage).some(k=>k.startsWith('monoreader-pages-')));
 run("state.module='mono';state.tab='分類存檔';state.layout='grid'");
 const article=run("renderCard({id:'a',type:'article',title:'Safe <title>',url:'https://example.org/a?x=1&y=2',summary:'text',added:''},0)");
 assert(article.includes('href="https://example.org/a?x=1&amp;y=2"'));
 assert(article.includes('Safe &lt;title&gt;'));
 assert(!article.match(/<h2>.*data-action="edit".*<\/h2>/));
 assert.equal(run("externalUrl('javascript:alert(1)')"),'');
 run("state.module='bib';state.tab='參考書目';state.layout='grid'");
 assert(run('isEntryView()'));
 const entry=run("renderCard({id:'r',type:'reference',title:'Ref',url:'https://example.org',notes:'Line1\\nLine2',rating:'A'},0)");
 assert(entry.includes('class="entry"'));assert(entry.includes('我的筆記／閱讀心得'));assert(entry.includes('Line2'));
 for(const [m,t] of [['bib','網址備存'],['bib','可用資源'],['mono','未來典藏']]){run(`state.module=${JSON.stringify(m)};state.tab=${JSON.stringify(t)}`);assert(run('isEntryView()'))}
 run("state.module='bib';state.tab='個人書庫';state.sub='待讀書架';state.layout='grid';result={total:141,page_size:18};state.page=2;db.items=Array.from({length:18},(_,i)=>({id:String(i),title:'Book',type:'book',shelf:'待讀書架'}));render()");
 assert(el('count').textContent.includes('19–36'));assert(el('pages').innerHTML.includes('2 / 8'));assert.equal(el('content').className,'shelves');
 run("db.items=[{id:'long',type:'reference',title:'Long note',notes:'LONG'.repeat(6000)}];openEditor('long')");
 assert(el('fields').innerHTML.includes('LONG'.repeat(6000)));assert(!el('fields').innerHTML.includes('<textarea'));assert(!el('fields').innerHTML.includes('disabled'));
 run("BOOT.writes=true;state.module='bib';db.items=[{id:'bibliography_notes:1',type:'reference',title:'Reference',notes:'Old note',_revision:'signed-row',_editable:['title','notes']}]");
 await run("openWriter('bibliography_notes:1')");
 el('w_title').value='Reference';el('w_notes').value='New note\nSecond line';
 let mutation=null;const originalFetch=context.fetch;
 context.fetch=async(url,opts)=>{if(url==='/api/update'){mutation=JSON.parse(opts.body);return{ok:false,status:409,json:async()=>({detail:'Conflict: updated elsewhere'})}}return originalFetch(url,opts)};
 await el('writeForm').handler_submit({preventDefault(){}});
 assert.equal(mutation.revision,'signed-row');assert.deepEqual(mutation.changes,{notes:'New note\nSecond line'});
 assert(el('writer').open);assert(el('writeStatus').textContent.includes('Conflict'));assert.equal(el('w_notes').value,'New note\nSecond line');assert(!el('writeSave').disabled);
 context.fetch=async(url,opts)=>url==='/api/update'?{ok:true,status:200,json:async()=>({ok:true})}:originalFetch(url,opts);
 await el('writeForm').handler_submit({preventDefault(){}});assert(!el('writer').open);assert(storage['monoreader-data-updated']);
 context.fetch=originalFetch;

 // Grouped archive folders, latest selection and independent bookmark controls.
 run("state.module='mono';state.tab='分類存檔';state.source='全部';state.layout='grid';result={sources:['e-flux Journal','Review'],issues:[],journals:[{name:'e-flux Journal',issues:4,latest:'e-flux Journal (Issue 110)'}]};db.items=[{id:'articles:one',type:'article',title:'Article',saved:false}];render()");
 assert(el('journalFolders').innerHTML.includes('開啟最新一期'));
 assert(el('source').innerHTML.includes('▣ e-flux Journal'));
 assert(!el('source').innerHTML.includes('Issue 110'));
 const actions=el('content').innerHTML;
 assert(actions.indexOf('詳情與筆記')<actions.indexOf('data-action="bookmark"'));
 run("state.source='e-flux Journal';state.issue='最新';result.grouped_source=true;result.selected_issue='e-flux Journal (Issue 110)';result.issues=['e-flux Journal (Issue 110)','e-flux Journal (Issue 10)'];render()");
 assert(el('journalFolders').innerHTML.includes('Issue 110'));
 assert(el('issue').innerHTML.includes('最新一期'));assert(!el('issue').hidden);
 let bookmarkPayload;
 context.fetch=async(url,opts)=>{if(url==='/api/bookmark'){bookmarkPayload=JSON.parse(opts.body);return{ok:true,status:200,json:async()=>({ok:true,saved:true})}}return originalFetch(url,opts)};
 await run("setBookmark('articles:one')");assert.equal(bookmarkPayload.saved,true);
 assert.equal(bookmarkPayload.id,'articles:one');assert.equal(run('bookmarkPending.size'),0);
 // Lookup must prefill only. No /api/create or /api/update until explicit submit.
 run("state.module='bib';state.tab='個人書庫';state.sub='待讀書架';writeOriginal=null;writeKind='book';writeFields=['title','author','identifier','notes','summary'];capabilities={types:{book:writeFields}};renderWriter();$('writer').showModal()");
 for(const field of ['title','author','identifier','summary'])el('w_'+field).value='';
 el('w_notes').value='My original notes';el('lookupKind').value='isbn';el('lookupValue').value='9780140328721';
 const lookupRequests=[];
 context.fetch=async(url,opts)=>{lookupRequests.push(url);return{ok:true,status:200,json:async()=>({type:'book',provider:'Fixture',fields:{title:'Matilda',author:'Roald Dahl',identifier:'9780140328721',summary:'Summary',image:'https://example/cover'},warnings:[]})}};
 await run('runLookup()');assert.deepEqual(lookupRequests,['/api/lookup']);assert.equal(el('w_title').value,'Matilda');assert.equal(el('w_notes').value,'My original notes');assert(el('lookupStatus').textContent.includes('尚未儲存'));assert(el('lookupStatus').textContent.includes('圖片網址'));assert(!el('writeSave').disabled);
 context.fetch=async()=>({ok:false,status:503,json:async()=>({detail:'Provider unavailable'})});
 await run('runLookup()');assert.equal(el('w_title').value,'Matilda');assert(el('lookupStatus').textContent.includes('Provider unavailable'));
 // Slow lookup must not overwrite text typed while waiting.
 let releaseLookup;
 context.fetch=async()=>{await new Promise(r=>releaseLookup=r);return{ok:true,status:200,json:async()=>({provider:'Fixture',fields:{title:'Overwrite'}})}};
 const lookupTask=run('runLookup()');el('w_title').value='User typed while fetching';releaseLookup();await lookupTask;
 assert.equal(el('w_title').value,'User typed while fetching');assert(el('lookupStatus').textContent.includes('未自動套用'));
 context.fetch=originalFetch;
 // V8 delete confirmation must gate network writes and reset after failure.
 run("writeOriginal={id:'omni_vault:1',title:'Delete fixture',_revision:'revision-1'};state.module='omni';writeBusy=false;lookupBusy=false;renderWriter()");
 assert(el('removeZone').innerHTML.includes('disabled'));
 let deletionCalls=[];
 context.fetch=async(url,options)=>{deletionCalls.push([url,options]);return{ok:false,status:409,json:async()=>({detail:'Changed elsewhere'})}};
 el('removeConfirm').checked=false;await run('removeCurrent()');assert.equal(deletionCalls.length,0);
 el('removeConfirm').checked=true;el('removeConfirm').onchange();assert.equal(el('removeItem').disabled,false);
 await run('removeCurrent()');assert.equal(deletionCalls.length,1);
 assert.equal(JSON.parse(deletionCalls[0][1].body).revision,'revision-1');
 assert.equal(el('removeConfirm').checked,false);assert.equal(el('removeItem').disabled,true);
 assert(el('writeStatus').textContent.includes('Changed elsewhere'));
 run("state.module='bib';state.tab='文獻探索';state.bsource='';state.bkind='';state.bissue='';result={publishers:[{name:'MIT Press',total:2}],journal_folders:[{name:'Test Journal',total:3}]};render()");
 assert(el('content').innerHTML.includes('關注出版社'));assert(el('content').innerHTML.includes('Test Journal'));
 assert(run('endpoint()').startsWith('/api/explore?'));
 run("state.bsource='Test Journal';state.bkind='journal';result={issue_folders:[{key:'issue:Vol 2',label:'Vol 2',total:3}]};render()");
 assert(el('content').innerHTML.includes('Vol 2'));assert(run('endpoint()').includes('source=Test'));
 run("state.bissue='issue:Vol 2';state.blabel='Vol 2';state.sub='期刊論文';render()");
 assert(run('endpoint()').includes('bissue=issue%3AVol+2'));
 assert(el('source').hidden);assert(el('crumb').innerHTML.includes('Vol 2'));
 context.fetch=originalFetch;
 // V10: adjacent prefetch is reusable, and old requests cannot repopulate cleared caches.
 run("state.module='mono';state.tab='分類存檔';state.bsource='';state.bissue='';state.page=100;clearCaches()");
 await run('load()');
 let timer;context.setTimeout=fn=>{timer=fn;return 1};
 run('scheduleNext(endpoint(),result)');assert(timer);timer();await flush();
 const fetched=requests.length;run('state.page=101');await run('load()');assert.equal(requests.length,fetched);
 assert(el('content').innerHTML.includes('Page 101'));
 run('entries[endpoint()].at=Date.now()-5*60*1000');await run('load()');assert.equal(requests.length,fetched);
 context.setTimeout=()=>1;delayed=true;const old=run('state.page=102;load()');
 run('clearCaches()');pending.shift()();await old;delayed=false;
 assert.equal(run('Object.keys(entries).length'),0);
 console.log('PASS V10: next-page prefetch, five-minute cache hit, invalidation blocks old responses');
 console.log('PASS V9: directory entry, publisher and journal sections, issue navigation and query scope');
 console.log('PASS V8: deletion checkbox and disabled state; confirmation payload; conflict reset');
 console.log('PASS: v6 folders, latest issue, bookmark mutation, lookup preview/no-save, failed lookup retention, in-flight edit preservation; inherited layout article link, safe URL, entry views, 18-item paging, complete long notes; initial lazy request; page20; cache reuse; background update; stale request isolation; offline stale label; folder counts; logout clearing');
})().catch(e=>{console.error(e);process.exitCode=1});
