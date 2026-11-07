/* Optional synthetic feedback form; existing native validators own all contracts. */
(async function(){
  'use strict';
  if(new URLSearchParams(location.search).get('feedback')!=='1')return;
  const $=id=>document.getElementById(id),el=(tag,text)=>{const e=document.createElement(tag);e.textContent=text;return e;};
  let context,busy=false,records=[];
  const actions=['adopt','edit','reject'];
  function lock(on){busy=on;for(const k of actions)$('feedback-'+k).disabled=on;$('feedback-import').disabled=on||!context?.imports.length;}
  function selected(){return context.candidates.find(c=>c.key===$('feedback-candidate').value);}
  const number=id=>$(id).value===''?null:Number($(id).value);
  function render(){
    const c=selected();$('feedback-version').textContent=`候选版本 ${c.candidate_version} · ${c.version.slice(0,12)}`;
    const labels={adopted:'采用',adopted_with_edits:'修改后采用',discarded:'弃用'};
    $('feedback-history').replaceChildren(...records.filter(r=>r.key===c.key).map(r=>{
      const d=el('details','');d.append(el('summary',`${labels[r.decision]} · 版本 ${r.candidate_version}`),el('p',`返工原因：${r.reason==='unknown'?'未知':r.reason}`),el('p',`人工修改投入：${r.modification_minutes===null?'未知':r.modification_minutes+' 分钟（人工报告）'}`),el('p',`节省时间：${r.time_saved_minutes===null?'unknown（缺少可比较基线或投入）':r.time_saved_minutes+' 分钟（人工报告差值）'}`),el('p','未发布 · 无观察任务'),el('p',`候选 SHA256：${r.candidate_sha256}`));return d;
    }));
  }
  async function post(path,payload){
    const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Feedback-Token':context.token},body:JSON.stringify(payload),credentials:'omit',signal:AbortSignal.timeout(10000)});
    const value=await response.json();if(!response.ok)throw Error(value.error||'save_failed');return value;
  }
  const errors={rework_reason_required:'请填写修改原因；耗时可以留空。',invalid_minutes:'分钟数需在 0–1440 之间。',stale_candidate_version:'候选版本已变化，请重新准备审核页。',stale_review_page:'审核材料已变化，请重新准备审核页。',source_hash_drift:'本地导出文件已变化，请重新准备导入。'};
  async function act(action){
    if(busy)return;lock(true);
    try{
      const c=selected(),p={key:c.key,version:c.version,action,reason:$('feedback-reason').value.trim(),minutes:action==='edit'?number('feedback-minutes'):null,baseline_minutes:action==='edit'?number('feedback-baseline'):null};
      const result=await post('/feedback/submit',p);if(!records.some(r=>r.event_id===result.event_id))records.push(result);render();
      $('feedback-status').textContent=result.duplicate?'该反馈已存在，没有重复录入。':'已生成本地反馈待审记录，自动关联此候选版本。';
    }catch(e){$('feedback-status').textContent=errors[e.message]||'未能保存反馈，请检查材料与本地预览状态。';}finally{lock(false);}
  }
  try{
    const response=await fetch('/feedback/context',{cache:'no-store',credentials:'omit',signal:AbortSignal.timeout(5000)});if(!response.ok)throw Error('context_unavailable');context=await response.json();records=context.history;
    for(const c of context.candidates){const option=el('option',c.title);option.value=c.key;$('feedback-candidate').append(option);}
    for(const f of context.imports){const option=el('option',f.label);option.value=f.key;$('feedback-file').append(option);}
    $('feedback-panel').hidden=false;render();lock(false);
    $('feedback-candidate').addEventListener('change',()=>{for(const id of ['feedback-reason','feedback-minutes','feedback-baseline'])$(id).value='';$('feedback-status').textContent='';render();});
    for(const action of actions)$('feedback-'+action).addEventListener('click',()=>act(action));
    $('feedback-import').addEventListener('click',async()=>{
      if(busy)return;lock(true);
      try{
        const result=await post('/feedback/import',{key:$('feedback-file').value});
        $('feedback-import-status').textContent=result.duplicate?'同一文件已导入，没有重复记录。':`已导入 ${result.records.length} 行。template_only · 账户日数据 · 未归因到单篇。`;
        $('feedback-metrics').textContent=result.records.map(r=>`${r.observed_time}\n`+r.metrics.map(m=>`${m.source_metric_key}：${m.value===null?'缺测（非 0）':m.value+(m.unit==='percent'?'%':'')}`).join('\n')).join('\n\n');
      }catch(e){$('feedback-import-status').textContent=errors[e.message]||'导入未通过校验，未生成记录。';}finally{lock(false);}
    });
  }catch(e){$('feedback-panel').hidden=false;$('feedback-status').textContent='反馈入口暂不可用，请通过已准备的本地虚构预览打开。';lock(true);}
})();
