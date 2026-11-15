const vm = require('node:vm');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const events = {};
const added = [];
const deleted = [];
const offline = new Response('offline');
let networkFails = false;
const context = {URL,Response,self:{location:{origin:'https://testserver'},clients:{claim:async()=>{}},addEventListener:(name,fn)=>events[name]=fn},
  caches:{open:async()=>({addAll:async paths=>added.push(...paths)}),match:async()=>offline,keys:async()=>['monoreader-public-pwa-0','unrelated'],delete:async name=>deleted.push(name)},
  fetch:async()=>{if(networkFails) throw Error('offline'); return new Response('private-page');}};
vm.runInNewContext(fs.readFileSync(__dirname+'/pwa/sw.js','utf8'), context);
(async()=>{
  let task;
  events.install({waitUntil:p=>task=p}); await task;
  assert(added.includes('/offline.html'));
  assert(!added.includes('/') && !added.some(p=>p.startsWith('/api')));
  events.activate({waitUntil:p=>task=p}); await task;
  assert.deepEqual(deleted,['monoreader-public-pwa-0']);
  function request(path,method='GET',mode='cors') {
    let response;
    events.fetch({request:{url:'https://testserver'+path,method,mode},respondWith:p=>response=p});
    return response;
  }
  for (const path of ['/api/browse','/api/item','/api/session','/logout']) assert.equal(request(path),undefined);
  assert.equal(request('/login','POST','navigate'),undefined);
  assert.equal(await (await request('/','GET','navigate')).text(),'private-page');
  networkFails = true;
  assert.equal(await request('/','GET','navigate'),offline);
  assert.equal(await request('/login','GET','navigate'),offline);
  console.log('PASS: public-only cache; API/POST bypass; authenticated navigation network-only; offline fallback; scoped cache cleanup');
})().catch(e=>{console.error(e);process.exit(1)});
