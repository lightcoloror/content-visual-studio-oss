// Pure JS contract tests only; no claim of DOM/browser acceptance.
const assert=require('node:assert/strict'),fs=require('node:fs');
const api=require('../admin/review.js');
const bundle=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const clone=x=>JSON.parse(JSON.stringify(x));
const row=bundle.choices[0];let count=0;function test(name,fn){fn();console.log('PASS '+name);count++;}
const change={...row.before_cue,text:'VERIFY SOURCE FILES',start_ms:100,end_ms:900};
const edit={schema_version:'content-review-decision.v1',event_id:'js-edit',bundle_sha256:bundle.bundle_sha256,parent_event_id:null,operation:'set',choice_id:row.id,decision:{action:'modify',replacement:change,binding:row.binding}};
const undo={schema_version:edit.schema_version,event_id:'js-undo',bundle_sha256:bundle.bundle_sha256,parent_event_id:'js-edit',operation:'undo'};
const redo={...undo,event_id:'js-redo',parent_event_id:'js-undo',operation:'redo'};
test('text and timing project to exact cue',()=>{const p=api.project(bundle,api.replay(bundle,[edit]).current);assert.deepEqual(JSON.parse(p['track.json']).cues[0],change);});
test('undo preserves history, redo restores content',()=>{assert.deepEqual(api.project(bundle,api.replay(bundle,[edit,undo]).current),{});assert.deepEqual(api.replay(bundle,[edit,undo,redo]).current,api.replay(bundle,[edit]).current);});
test('old parent rejected',()=>assert.throws(()=>api.replay(bundle,[edit,{...undo,parent_event_id:null}]),/stale_decision_head/));
test('duplicate ID rejected in exported chain',()=>assert.throws(()=>api.replay(bundle,[edit,edit]),/invalid_decision_id/));
test('stale bundle rejected',()=>assert.throws(()=>api.replay(bundle,[{...edit,bundle_sha256:'0'.repeat(64)}]),/stale_review_page/));
test('restored state derived from immutable events',()=>{const state={...api.replay(bundle,[edit,undo,redo]),events:[edit,undo,redo]};assert.deepEqual(api.loadState(bundle,JSON.stringify(state)).current,state.current);state.current.decisions={};assert.throws(()=>api.loadState(bundle,JSON.stringify(state)),/decision_history_drift/);});
test('readonly remains enforced',()=>{const b=clone(bundle);b.candidates[row.candidate_id].synthetic_only=false;assert.throws(()=>api.replay(b,[edit]),/real_material_read_only/);});
test('invalid cue intervals and unknown scene',()=>{for(const patch of [{start_ms:0,end_ms:0},{end_ms:2200},{scene_id:'unknown'},{start_ms:0.5},{text:'bad\\line'}]){const e=clone(edit);Object.assign(e.decision.replacement,patch);assert.throws(()=>api.replay(bundle,[e]));}});
test('scene move is explicit and preserves stable cue id',()=>{const e=clone(edit);Object.assign(e.decision.replacement,{scene_id:'s2',start_ms:2000,end_ms:3000});const p=api.project(bundle,api.replay(bundle,[e]).current);assert.equal(JSON.parse(p['track.json']).cues[0].cue_id,'c1');});
test('branch after undo clears redo',()=>{const branch={...clone(edit),event_id:'branch',parent_event_id:'js-undo'};branch.decision.replacement.text='BRANCH';assert.throws(()=>api.replay(bundle,[edit,undo,branch,{...redo,event_id:'r2',parent_event_id:'branch'}]),/nothing_to_redo/);});
if(process.argv[3])fs.writeFileSync(process.argv[3],JSON.stringify({schema_version:'content-review-session.v1',bundle_sha256:bundle.bundle_sha256,events:[edit,undo,redo]},null,2));
console.log(JSON.stringify({tests:count,passed:true,scope:'pure JS logic; no browser acceptance'}));
