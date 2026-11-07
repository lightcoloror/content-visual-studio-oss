/* Local review drafts. Cue rendering is a separate, source-verified CLI action. */
(function (root) {
  'use strict';
  const VERSION='1.0.0';
  const canonical=v=>Array.isArray(v)?'['+v.map(canonical).join(',')+']':v&&typeof v==='object'?'{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}':JSON.stringify(v);
  const clone=v=>JSON.parse(JSON.stringify(v));
  async function sha(text){return Array.from(new Uint8Array(await root.crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(x=>x.toString(16).padStart(2,'0')).join('');}
  function requireBinding(bundle,draft){
    if(draft.schema_version!=='content-review-draft.v1'||draft.version!==VERSION||draft.bundle_sha256!==bundle.bundle_sha256)throw Error('stale_review_page');
  }
  function validateTrack(t){
    if(t.schema_version!=='content-cue-track.v1')throw Error('cue_track_version');
    const scenes=new Map(),ids=new Set(),intervals=new Map();let end=0;
    for(const s of t.scenes){if(!/^[A-Za-z0-9_-]{1,100}$/.test(s.scene_id)||scenes.has(s.scene_id)||!Number.isSafeInteger(s.start_ms)||!Number.isSafeInteger(s.end_ms)||s.start_ms!==end||s.end_ms<=end)throw Error('invalid_scene_interval');scenes.set(s.scene_id,s);intervals.set(s.scene_id,[]);end=s.end_ms;}
    if(!scenes.size)throw Error('scenes_required');
    for(const c of t.cues){
      if(canonical(Object.keys(c).sort())!==canonical(['cue_id','end_ms','scene_id','start_ms','text']))throw Error('invalid_cue_fields');
      if(typeof c.cue_id!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(c.cue_id)||ids.has(c.cue_id))throw Error('invalid_cue_id');ids.add(c.cue_id);
      const s=scenes.get(c.scene_id);if(!s)throw Error('unknown_scene');
      if(!Number.isSafeInteger(c.start_ms)||!Number.isSafeInteger(c.end_ms)||!(s.start_ms<=c.start_ms&&c.start_ms<c.end_ms&&c.end_ms<=s.end_ms))throw Error('cue_outside_scene');
      if(typeof c.text!=='string'||!c.text.trim()||Array.from(c.text).length>34||/[{}\\\r\n]/.test(c.text))throw Error('invalid_cue_text');
      intervals.get(c.scene_id).push([c.start_ms,c.end_ms]);
    }
    for(const spans of intervals.values()){if(!spans.length)throw Error('scene_requires_cue');spans.sort((a,b)=>a[0]-b[0]);if(spans.some((s,i)=>i&&spans[i-1][1]>s[0]))throw Error('overlapping_cues');}
  }
  function cueProject(bundle,draft){
    const tracks={},seen=new Set();
    for(const [id,d]of Object.entries(draft.decisions)){
      const row=bundle.choices.find(x=>x.id===id);if(!row)throw Error('unknown_choice');if(row.kind!=='cue')continue;
      if(row.targets.length!==1)throw Error('cue_requires_one_track');const key=row.targets[0],a=bundle.artifacts[key],t=JSON.parse(a.text),c=bundle.candidates[row.candidate_id];validateTrack(t);
      if(a.candidate_id!==row.candidate_id)throw Error('cross_candidate_target');
      const before=t.cues.find(x=>x.cue_id===row.cue_id);if(canonical(before)!==canonical(row.before_cue))throw Error('stale_cue');
      if(row.read_only||c.read_only||c.synthetic_only!==true||t.synthetic_only!==true)throw Error('real_material_read_only');
      if(canonical(d.binding)!==canonical(row.binding))throw Error('stale_candidate_body');
      if(!['keep','modify','reject'].includes(d.action))throw Error('invalid_action');if(d.action!=='modify')continue;
      const identity=key+':'+row.cue_id;if(seen.has(identity))throw Error('overlapping_edits');seen.add(identity);
      if(!d.replacement||typeof d.replacement!=='object'||d.replacement.cue_id!==row.cue_id)throw Error('cue_identity_changed');
      tracks[key]??=t;tracks[key].cues=tracks[key].cues.map(c=>c.cue_id===row.cue_id?clone(d.replacement):c);
    }
    const changed={};for(const [key,t]of Object.entries(tracks)){validateTrack(t);if(canonical(t)!==canonical(JSON.parse(bundle.artifacts[key].text)))changed[key]=JSON.stringify(t,null,2)+'\n';}return changed;
  }
  function project(bundle,draft){
    requireBinding(bundle,draft);const edits={},changed={};
    for(const [id,d] of Object.entries(draft.decisions)){
      const row=bundle.choices.find(x=>x.id===id);if(!row)throw Error('unknown_choice');
      const c=bundle.candidates[row.candidate_id];
      if(row.read_only||!c.synthetic_only)throw Error('real_material_read_only');
      if(canonical(d.binding)!==canonical(row.binding))throw Error('stale_candidate_body');
      if(!['keep','modify','reject'].includes(d.action))throw Error('invalid_action');
      if(row.kind==='cue')continue;
      if(d.action!=='modify')continue;
      if(typeof d.replacement!=='string'||d.replacement.length>10000)throw Error('invalid_replacement');
      if(!row.targets.length)throw Error('no_patch_target');
      for(const target of row.targets){
        const a=bundle.artifacts[target];if(a.candidate_id!==row.candidate_id)throw Error('cross_candidate_target');
        const start=a.text.indexOf(row.before);if(!row.before||start<0||a.text.indexOf(row.before,start+row.before.length)>=0)throw Error('span_not_unique');
        const end=start+row.before.length;(edits[target]??=[]);
        if(edits[target].some(e=>start<e.end&&e.start<end))throw Error('overlapping_edits');
        edits[target].push({start,end,replacement:d.replacement});
      }
    }
    for(const [key,operations]of Object.entries(edits)){
      let text=bundle.artifacts[key].text;
      for(const e of operations.sort((a,b)=>b.start-a.start))text=text.slice(0,e.start)+e.replacement+text.slice(e.end);
      if(text!==bundle.artifacts[key].text)changed[key]=text;
    }
    const cues=cueProject(bundle,draft);if(Object.keys(cues).some(k=>edits[k]))throw Error('mixed_cue_text_edits');
    return Object.assign(changed,cues);
  }
  function empty(bundle){return {schema_version:'content-review-draft.v1',version:VERSION,bundle_sha256:bundle.bundle_sha256,decisions:{}};}
  function loadState(bundle,text){
    if(text===null)return {current:empty(bundle),previous:null};
    const state=JSON.parse(text);project(bundle,state.current);if(state.previous)project(bundle,state.previous);
    if(state.events){const computed=replay(bundle,state.events);if(canonical(computed.current)!==canonical(state.current))throw Error('decision_history_drift');return {...state,...computed};}return state;
  }
  function replay(bundle,events){
    let current=empty(bundle),head=null;const undo=[],redo=[],seen=new Set();
    for(const e of events){
      if(e.schema_version!=='content-review-decision.v1'||typeof e.event_id!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(e.event_id)||seen.has(e.event_id))throw Error('invalid_decision_id');
      if(e.bundle_sha256!==bundle.bundle_sha256)throw Error('stale_review_page');if(e.parent_event_id!==head)throw Error('stale_decision_head');
      if(['set','unset'].includes(e.operation)){
        if(!bundle.choices.some(r=>r.id===e.choice_id))throw Error('unknown_choice');const next=clone(current);
        if(e.operation==='set')next.decisions[e.choice_id]=clone(e.decision);else delete next.decisions[e.choice_id];
        project(bundle,next);if(canonical(next)===canonical(current))throw Error('no_decision_change');undo.push(current);current=next;redo.length=0;
      }else if(e.operation==='undo'){if(!undo.length)throw Error('nothing_to_undo');redo.push(current);current=undo.pop();}
      else if(e.operation==='redo'){if(!redo.length)throw Error('nothing_to_redo');undo.push(current);current=redo.pop();}
      else throw Error('invalid_decision_operation');project(bundle,current);seen.add(e.event_id);head=e.event_id;
    }return {current,head,can_undo:!!undo.length,can_redo:!!redo.length,previous:undo.length?undo[undo.length-1]:null};
  }
  const api={canonical,sha,project,empty,loadState,validateTrack,cueProject,replay};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(!root.document)return;
  const $=id=>document.getElementById(id);
  const bundleURL=new URL(new URLSearchParams(location.search).get('bundle')||'bundle.json',location.href);
  const element=(tag,text,cls)=>{const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;};
  let bundle,state,pending,storageKey,savedRaw=null,busy=false,editable=false,blocked=false,cueMode=false;
  function message(text,error=false){$('message').textContent=text;$('message').className=error?'error':'';}
  function refreshButtons(){
    const changed=state&&canonical(pending)!==canonical(state.current);
    $('save').disabled=busy||blocked||!editable||!changed;
    $('undo').disabled=busy||blocked||!state?.previous;
    $('redo').disabled=busy||blocked||!state?.can_redo;
    $('export').disabled=busy||blocked||!state||(cueMode?!state.events?.length:Object.keys(state.current.decisions).length===0);
    $('save-state').textContent=changed?'有未保存的选择':state&&Object.keys(state.current.decisions).length?`已保存 ${Object.keys(state.current.decisions).length} 项选择草稿`:'尚无选择';
  }
  async function fresh(){
    if(location.protocol==='file:'){
      // Embedded snapshot only. CLI apply/decide rechecks actual disk sources.
      const current=JSON.parse($('review-bundle').textContent),claimed=current.bundle_sha256;delete current.bundle_sha256;
      if(claimed!==bundle.bundle_sha256||await sha(canonical(current))!==claimed)throw Error('stale_review_page');
      if(localStorage.getItem(storageKey)!==savedRaw)throw Error('another_tab_changed_draft');return;
    }
    const response=await fetch(bundleURL,{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(5000)});
    if(!response.ok)throw Error('input_unavailable');
    const current=await response.json();const claimed=current.bundle_sha256;delete current.bundle_sha256;
    if(claimed!==bundle.bundle_sha256||await sha(canonical(current))!==claimed)throw Error('stale_review_page');
    if(localStorage.getItem(storageKey)!==savedRaw)throw Error('another_tab_changed_draft');
  }
  function commit(next){
    const text=JSON.stringify(next);localStorage.setItem(storageKey,text);savedRaw=text;state=next;pending=clone(state.current);
  }
  function renderArtifacts(){
    const changes=project(bundle,pending);
    for(const [key,a]of Object.entries(bundle.artifacts)){
      const view=document.querySelector('[data-artifact="'+key+'"]');if(view)view.textContent=changes[key]??a.text;
    }
  }
  function choose(row,action,replacement){
    pending.decisions[row.id]={action,replacement,binding:clone(row.binding)};
    try{renderArtifacts();message('选择尚未保存。');refreshButtons();}catch(e){message('修改无效：'+e.message+'。请调整时间、场景或文本。',true);$('save').disabled=true;}
  }
  function cueCard(row,article){
    const track=JSON.parse(bundle.artifacts[row.targets[0]].text),before=row.before_cue;
    const replacement=clone(pending.decisions[row.id]?.replacement??before);
    const compare=element('div',undefined,'comparison'),left=element('div'),right=element('div');
    const describe=c=>`${c.scene_id} · ${c.start_ms}–${c.end_ms} 毫秒\n${c.text}`;
    left.append(element('span','当前字幕','label'),element('p',describe(before)));const after=element('p',describe(replacement));right.append(element('span','修改后预览','label'),after);compare.append(left,right);article.append(compare);
    if(row.read_only){article.append(element('p','真实材料只读，不能保存字幕或时间修改。','readonly-note'));return article;}
    const controls=element('div',undefined,'cue-controls');
    const fields={};
    for(const [key,label]of [['text','字幕文本'],['start_ms','开始时间（毫秒）'],['end_ms','结束时间（毫秒）'],['scene_id','所属场景']]){
      const wrap=element('label',label),input=element(key==='text'?'textarea':key==='scene_id'?'select':'input');
      if(key==='scene_id')for(const s of track.scenes){const o=element('option',`${s.scene_id} · ${s.start_ms}–${s.end_ms}`);o.value=s.scene_id;input.append(o);}
      if(key.endsWith('_ms')){input.type='number';input.min='0';input.step='1';}
      input.setAttribute('aria-label',row.title+' '+label);input.value=replacement[key];fields[key]=input;wrap.append(input);controls.append(wrap);
      input.addEventListener('input',()=>{const c={cue_id:row.cue_id,text:fields.text.value,start_ms:Number(fields.start_ms.value),end_ms:Number(fields.end_ms.value),scene_id:fields.scene_id.value};after.textContent=describe(c);choose(row,'modify',c);});
    }
    article.append(controls);
    const reset=element('button','撤回这项未保存的修改');reset.type='button';reset.addEventListener('click',()=>{delete pending.decisions[row.id];renderChoices();renderArtifacts();refreshButtons();});article.append(reset);return article;
  }
  function card(row){
    const article=element('article',undefined,'choice');article.dataset.choiceId=row.id;
    const head=element('div',undefined,'choice-heading');head.append(element('h3',row.title),element('span',row.read_only?'待本人判断':'虚构样例','state'));article.append(head);
    article.append(element('p',[bundle.candidates[row.candidate_id].title,row.source_label,row.timecode].filter(Boolean).join(' · '),'meta'));
    if(row.kind==='cue')return cueCard(row,article);
    const compare=element('div',undefined,'comparison');
    for(const [label,text]of [['当前内容',row.before],['建议 / 调整后',row.after]]){const col=element('div');col.append(element('span',label,'label'),element('p',text));compare.append(col);}article.append(compare,element('p',row.reason));
    if(row.read_only){article.append(element('p','只读待审，尚未替你做任何选择。','readonly-note'));return article;}
    const group=element('fieldset',undefined,'choices');group.append(element('legend','你的选择'));
    const edit=element('textarea');edit.setAttribute('aria-label',row.title+'的修改内容');edit.value=pending.decisions[row.id]?.replacement??row.after;edit.hidden=pending.decisions[row.id]?.action!=='modify';
    for(const [value,label]of [['keep','保留原文'],['modify','修改'],['reject','拒绝建议']]){
      const wrap=element('label',undefined,'option'),input=element('input');input.type='radio';input.name=row.id;input.value=value;input.checked=pending.decisions[row.id]?.action===value;
      input.addEventListener('change',()=>{edit.hidden=value!=='modify';choose(row,value,edit.value);});wrap.append(input,document.createTextNode(label));group.append(wrap);
    }
    edit.addEventListener('input',()=>choose(row,'modify',edit.value));
    const reset=element('button','撤回这项选择');reset.type='button';reset.addEventListener('click',()=>{delete pending.decisions[row.id];renderChoices();renderArtifacts();refreshButtons();});
    article.append(group,edit,reset);return article;
  }
  function renderChoices(){
    const selected=$('candidate-filter').value;const rows=bundle.choices.filter(x=>selected==='all'||x.candidate_id===selected);
    $('choices').replaceChildren(...rows.slice(0,5).map(card));$('other-choices').replaceChildren(...rows.slice(5).map(card));
    $('more').hidden=rows.length<=5;$('more-label').textContent=`展开其他 ${Math.max(0,rows.length-5)} 项`;$('count').textContent=`${rows.length} 项待核`;
  }
  function renderMaterials(){
    for(const [id,c]of Object.entries(bundle.candidates)){
      const details=element('details');details.append(element('summary',c.title),element('p',c.status_note));
      for(const note of c.unknowns??[])details.append(element('p',note,'meta'));
      for(const m of bundle.media??[]){if(m.candidate_id!==id)continue;
        if(!/^[a-zA-Z0-9_.-]+$/.test(m.file)||!['audio','video'].includes(m.kind))continue;
        const player=element(m.kind);player.controls=true;player.preload='none';player.src=new URL(m.file,bundleURL).href;
        player.setAttribute('aria-label',m.label);details.append(element('p',m.label),player);
      }
      for(const [key,a]of Object.entries(bundle.artifacts).filter(([,a])=>a.candidate_id===id)){
        const body=element('pre',a.text,'body-preview');body.dataset.artifact=key;details.append(element('h3',a.label),body);
      }
      $('materials').append(details);
    }
  }
  function failure(e){
    const errors={stale_review_page:'候选版本已变化，请重新打开最新审核页；旧草稿没有覆盖新版本。',another_tab_changed_draft:'另一个页面已保存草稿，请刷新后再继续。',input_unavailable:'当前材料无法读取，未保存选择。',real_material_read_only:'真实材料保持只读待审。'};
    message(errors[e.message]??'无法核验或保存本地草稿。请通过已授权的本地预览入口打开，并检查存储权限。',true);
  }
  async function act(kind){
    if(busy||blocked)return;busy=true;refreshButtons();
    try{
      await fresh();
      if(kind==='save'){
        project(bundle,pending);
        if(canonical(pending)===canonical(state.current)){message('草稿未变化。');return;}
        if(cueMode){
          const events=clone(state.events);let current=replay(bundle,events);
          for(const id of new Set([...Object.keys(current.current.decisions),...Object.keys(pending.decisions)])){
            if(canonical(current.current.decisions[id])===canonical(pending.decisions[id]))continue;
            const event={schema_version:'content-review-decision.v1',event_id:crypto.randomUUID(),bundle_sha256:bundle.bundle_sha256,parent_event_id:current.head,operation:pending.decisions[id]?'set':'unset',choice_id:id};
            if(pending.decisions[id])event.decision=clone(pending.decisions[id]);events.push(event);current=replay(bundle,events);
          }commit({...current,events});
        }else commit({current:clone(pending),previous:clone(state.current)});
        message(location.protocol==='file:'?'已保存本地决策；导入 CLI 时会复核原文件是否变化。':'已保存本地选择草稿。');
      }else if(['undo','redo'].includes(kind)&&cueMode){
        const events=[...state.events,{schema_version:'content-review-decision.v1',event_id:crypto.randomUUID(),bundle_sha256:bundle.bundle_sha256,parent_event_id:state.head,operation:kind}];
        commit({...replay(bundle,events),events});renderChoices();renderArtifacts();message(kind==='undo'?'已撤销上一项决策，历史保留。':'已恢复上一项决策，历史保留。');
      }else if(kind==='undo'&&state.previous){commit({current:clone(state.previous),previous:null});renderChoices();renderArtifacts();message('已撤销上次保存，候选原件未改动。');}
      else if(kind==='export'){
        const payload=cueMode?{schema_version:'content-review-session.v1',bundle_sha256:bundle.bundle_sha256,events:state.events}:state.current;
        const url=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'}));const a=element('a');a.href=url;a.download=cueMode?'content-review-session.json':'content-review-draft.json';a.click();URL.revokeObjectURL(url);
      }
    }catch(e){failure(e);}finally{busy=false;refreshButtons();}
  }
  async function init(){
    try{
      if(bundleURL.origin!==location.origin)throw Error('input_unavailable');
      const embedded=$('review-bundle');bundle=embedded?JSON.parse(embedded.textContent):await (await fetch(bundleURL,{cache:'no-store'})).json();
      const body=clone(bundle);delete body.bundle_sha256;
      if(bundle.version!==VERSION||await sha(canonical(body))!==bundle.bundle_sha256)throw Error('stale_review_page');
      for(const a of Object.values(bundle.artifacts))if(await sha(a.text)!==a.body_sha256)throw Error('stale_review_page');
      cueMode=bundle.choices.some(x=>x.kind==='cue');storageKey='content-review-draft:'+bundle.review_id;savedRaw=localStorage.getItem(storageKey);
      try{state=loadState(bundle,savedRaw);}catch(e){blocked=true;state={current:empty(bundle),previous:null};failure(e);}
      if(cueMode&&!state.events){if(Object.keys(state.current.decisions).length){blocked=true;message('旧草稿没有决策历史，不能直接覆盖本版；请保留旧导出并使用新的审核包。',true);}else state={...replay(bundle,[]),events:[]};}
      pending=clone(state.current);editable=bundle.choices.some(x=>!x.read_only);
      $('scope').textContent=editable?'虚构交互样例：保存只生成本地选择草稿。':'两题候选与真人片段均为只读待审。先看前后对照，再由你判断。';
      for(const [id,c]of Object.entries(bundle.candidates)){const option=element('option',c.title);option.value=id;$('candidate-filter').append(option);}
      renderChoices();renderMaterials();renderArtifacts();refreshButtons();
      if(!blocked)message(editable?'请选择需要处理的项，其余可以保持待定。':'来源完整度、证据缺口和未解决冲突仍保留。');
    }catch(e){blocked=true;failure(e);$('scope').textContent='审核材料暂不可用。';refreshButtons();}
  }
  $('candidate-filter').addEventListener('change',renderChoices);
  for(const kind of ['save','undo','redo','export'])$(kind).addEventListener('click',()=>act(kind));
  init();
})(typeof globalThis!=='undefined'?globalThis:this);
