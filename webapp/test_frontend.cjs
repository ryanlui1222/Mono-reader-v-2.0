const fs=require('fs'),vm=require('vm'),assert=require('assert');
const html=fs.readFileSync(require('path').join(__dirname,'index.html'),'utf8');const code=html.split('<script>')[1].split('</script>')[0];
const elements={};const el=id=>elements[id]??=( {id,innerHTML:'',textContent:'',value:'',hidden:false,style:{},dataset:{},classList:{toggle(){}},querySelectorAll(){return[]},showModal(){this.open=true},close(){this.open=false},replaceChildren(){this.innerHTML=''}} );
const handlers={};const storage={};Object.defineProperties(storage,{getItem:{value:k=>storage[k]??null},setItem:{value:(k,v)=>storage[k]=v},removeItem:{value:k=>delete storage[k]}});
let requests=[],delayed=false,pending=[],fail=false;
const makeData=url=>{const u=new URL(url,'https://test');if(u.pathname==='/api/folders')return {folders:[{name:'Art',total:120,image:''}]};const p=Number(u.searchParams.get('page')||1);return{items:[{id:'articles:'+p,type:'article',title:'Page '+p,summary:'summary',added:'2026-11-14T00:00:00'}],total:7780,page:p,page_size:30,sources:['Review'],issues:[]}};
const context={console,URL,URLSearchParams,Date,JSON,Set,Map,Math,Number,String,Object,Array,Boolean,RegExp,Promise,AbortController,
 document:{getElementById:el,body:{classList:{toggle(){}}},addEventListener:(type,fn)=>handlers[type]=fn,hidden:false},
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
 console.log('PASS: layout-v4 article link, safe URL, entry views, 18-item paging, complete long notes; initial lazy request; page20; cache reuse; background update; stale request isolation; offline stale label; folder counts; logout clearing');
})().catch(e=>{console.error(e);process.exitCode=1});
