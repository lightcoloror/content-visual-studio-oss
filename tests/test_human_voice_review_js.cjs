// Pure draft logic tests. No DOM, browser, localStorage or human interaction.
const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
const api=require('../admin/review.js');
const request=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));const bundle=request;
const copy=x=>JSON.parse(JSON.stringify(x));let tests=0;
function test(name,fn){fn();tests++;console.log('PASS '+name);}
const row=bundle.choices.find(x=>x.id==='word');
const draft=api.empty(bundle);draft.decisions.word={action:'modify',replacement:row.after,binding:copy(row.binding)};
test('two artifacts changed, other topic/upstream inherited',()=>assert.deepEqual(Object.keys(api.project(bundle,draft)).sort(),['a-article.md','a-oral.md']));
test('saved draft round-trip',()=>assert.deepEqual(api.loadState(bundle,JSON.stringify({current:draft,previous:api.empty(bundle)})).current,draft));
test('stale page rejected',()=>{const d=copy(draft);d.bundle_sha256='0'.repeat(64);assert.throws(()=>api.project(bundle,d),/stale_review_page/);});
test('stale body rejected',()=>{const d=copy(draft);d.decisions.word.binding.body_sha256='0'.repeat(64);assert.throws(()=>api.project(bundle,d),/stale_candidate_body/);});
test('real candidate cannot receive choice',()=>{const b=copy(bundle);b.candidates[row.candidate_id].synthetic_only=false;assert.throws(()=>api.project(b,draft),/real_material_read_only/);});
test('undo empty state returns no changes',()=>assert.deepEqual(api.project(bundle,api.empty(bundle)),{}));
test('reject preserves original',()=>{const d=copy(draft);d.decisions.word.action='reject';assert.deepEqual(api.project(bundle,d),{});});
test('repeated projection is deterministic',()=>assert.deepEqual(api.project(bundle,draft),api.project(bundle,draft)));
test('malformed saved state rejected',()=>assert.throws(()=>api.loadState(bundle,'not json')));
test('previous stale revision cannot silently restore',()=>{const prev=api.empty(bundle);prev.version='0';assert.throws(()=>api.loadState(bundle,JSON.stringify({current:draft,previous:prev})),/stale_review_page/);});
console.log(JSON.stringify({tests,passed:true,scope:'pure logic only; not browser interaction'}));
