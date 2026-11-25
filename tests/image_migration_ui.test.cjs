const fs=require('fs'),vm=require('vm'),assert=require('node:assert/strict');
const context={window:{fetch:()=>{throw new Error('Unexpected network')}}};vm.createContext(context);
vm.runInContext(fs.readFileSync('public/static/js/image-migration.js','utf8'),context);
function element(){return {hidden:false,disabled:false,textContent:'',events:{},addEventListener(k,v){this.events[k]=v;}};}
function fixture(request){
 const ui={banner:element(),message:element(),migrate:element(),dismiss:element()};
 const state={path:'Folder/a.md',revision:1,dirty:false};const applied=[];const locks=[];let saves=0;
 const api=context.window.VaultedImageMigration.create({...ui,getState:()=>({...state}),save:async()=>{saves++;return true;},
 apply:d=>{applied.push(d);state.revision=d.revision;},lock:b=>locks.push(b),request});
 return {ui,state,api,applied,locks,saves:()=>saves};
}
const reply=d=>({ok:true,json:async()=>({success:true,content:'Updated note',...d})});
(async()=>{
 let requests=0;let f=fixture(async()=>{requests++;return reply({revision:2,migrated:1,remaining:0,deferred:0,failed_urls:[]});});
 f.api.show(0);assert.equal(f.ui.banner.hidden,true);f.api.show(1);assert.equal(f.ui.banner.hidden,false);assert.equal(requests,0);
 f.ui.dismiss.events.click();assert.equal(f.ui.banner.hidden,true);f.api.show(1);assert.equal(f.ui.banner.hidden,true);
 f.state.path='Folder/b.md';f.api.show(1);assert.equal(f.ui.banner.hidden,false);
 await f.api.run();assert.equal(f.applied.length,1);assert.equal(f.state.revision,2);assert.equal(f.locks.at(-1),false);assert.match(f.ui.message.textContent,/saved in Vaulted/);
 let resolve;f=fixture(()=>new Promise(r=>resolve=r));f.api.show(1);const pending=f.api.run();await new Promise(setImmediate);
 assert.equal(f.api.isBusy('Folder/a.md'),true);f.state.path='Other/note.md';f.api.show(2);assert.equal(f.locks.at(-1),false);
 resolve(reply({revision:2,migrated:1,remaining:0,deferred:0,failed_urls:[]}));await pending;assert.equal(f.applied.length,0);assert.equal(f.state.path,'Other/note.md');
 f=fixture(()=>new Promise(r=>resolve=r));f.api.show(1);const changed=f.api.run();await new Promise(setImmediate);f.state.dirty=true;
 resolve(reply({revision:2,migrated:1,remaining:0,deferred:0,failed_urls:[]}));await changed;assert.equal(f.applied.length,0);assert.match(f.ui.message.textContent,/editor text was kept/);
 const bodies=[];f=fixture(async(_,options)=>{bodies.push(JSON.parse(options.body));return bodies.length===1?
 reply({revision:2,migrated:2,remaining:2,deferred:1,failed_urls:['https://bad.example/a.png']}):
 reply({revision:3,migrated:1,remaining:1,deferred:0,failed_urls:[]});});f.api.show(4);await f.api.run();
 assert.equal(bodies.length,2);assert.equal(bodies[1].revision,2);assert.deepEqual(bodies[1].skip_urls,['https://bad.example/a.png']);assert.match(f.ui.message.textContent,/3 images saved/);assert.match(f.ui.message.textContent,/1 could not/);
 f=fixture(async()=>({ok:false,json:async()=>({error:'Page changed. Reload it.'})}));f.api.show(1);await f.api.run();assert.equal(f.applied.length,0);assert.match(f.ui.message.textContent,/Page changed/);assert.equal(f.locks.at(-1),false);
 console.log('Image migration UI: no automatic requests, dismissal, safe navigation, edit protection, batching and conflicts passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
