"""Self-contained topic isolation checks; all in-memory evidence is synthetic.

The public compiler needs an explicit QRP candidate owner. The module binds the
operator-supplied public source root once through the existing
``qrp_owner_binding.bind_qrp`` helper and then uses the real public
``qrp_candidate_adapter``; a missing or mixed owner fails this class instead of
being skipped or mocked. No Main consistency gate or tool registry is needed by
``compile_candidate`` or ``reviewed_policy``.
"""
import importlib,json,os,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import original_synthesis_adapter as a
from qrp_owner_binding import bind_qrp
from temp_workspace import isolated_test_directory
QRP_ROOT_ENV='CONTENT_STUDIO_QRP_ROOT'

def case(topic='字幕校验'):
    sources=[{'source_id':sid,'title':topic+' 来源 '+sid,'canonical_ref':'https://example.org/'+topic+'/'+sid,
        'source_type':'official_documentation','content':'A short exact quotation.',
        'content_sha256':a.sha((topic+sid).encode()),'archive_path':sid+'.json','archive_sha256':'a'*64,
        'capture_scope':'captured_text','capture_status':'success','capture_content_ok':True} for sid in ['s1','s2']]
    research={'question':topic,'sources':sources,
        'claims':[{'claim_id':'c'+str(i),'text':topic+'的合成规则'+str(i)} for i in range(1,6)],
        'evidence':[{'evidence_id':'e'+str(i),'claim_id':'c'+str(i),'source_id':'s1','text':'A short exact quotation.','relation':'supports'} for i in range(1,6)]}
    units=[{'id':'u'+str(i),'type':'agent_inference','assertion_kind':'source_interpretation','claim_id':'c'+str(i),
        'text':c['text'],'evidence_ids':['e'+str(i)]} for i,c in enumerate(research['claims'],1)]
    units.append({'id':'q','type':'verified_quote','assertion_kind':'quotation','quote_evidence_id':'e1',
        'quote_source_id':'s1','text':'A short exact quotation.'})
    plan={'schema_version':'content-original-editorial-plan.v2','status':'candidate_only','human_approved':False,
        'synthetic_only':True,
        'title':topic+'：'+'中文长标题，用于检查无固定图框的结构输出。'*5,
        'claim_ids':[c['claim_id'] for c in research['claims']],'units':units,
        'article_order':[u['id'] for u in units],'oral_order':[u['id'] for u in units[:-1]],
        'unknowns':['Synthetic fixture only'],'withheld':[{'status':'needs_source','text':'Unverified effects'}]}
    return plan,research

class GeneralizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root_value=os.environ.get(QRP_ROOT_ENV)
        if not root_value:
            raise RuntimeError(QRP_ROOT_ENV+' must name the explicit public question-research-poc source root; a missing owner is a failure, not a skip')
        root=Path(root_value).expanduser().resolve()
        source_path=str(root/'src')
        if source_path not in sys.path:sys.path.insert(0,source_path)
        try:bind_qrp(root)
        except (ValueError,OSError) as exc:raise RuntimeError('QRP owner binding failed for '+str(root)+': '+str(exc)) from exc
        cls.qrp=importlib.import_module('qrp_candidate_adapter')

    def test_same_local_ids_different_topics(self):
        p1,r1=case('资料组织');p2,r2=case('字幕校验')
        t1,c1,_=a.compile_candidate(p1,r1,qrp=self.qrp);t2,c2,_=a.compile_candidate(p2,r2,qrp=self.qrp)
        self.assertNotEqual(c1['content_id'],c2['content_id']);self.assertNotEqual(c1['fact_card_id'],c2['fact_card_id'])
        self.assertNotIn('资料组织',t2['article.md']);self.assertNotIn('Zotero',json.dumps([t2,c2]))
    def test_long_title_five_claims_no_fixed_canvas(self):
        p,r=case();texts,card,_=a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(len(card['facts']),5);self.assertEqual(set(texts),{'article.md','oral-script.md'})
        self.assertIn(p['title'],texts['article.md']);self.assertNotIn('<svg',texts['article.md'])
    def test_same_quote_wrong_source_rejected(self):
        p,r=case();p['units'][-1]['quote_source_id']='s2'
        with self.assertRaises(a.SynthesisError) as e:a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(e.exception.code,'quote_source_drift')
    def test_full_capture_is_not_verified_fact(self):
        p,r=case();p['units'][0]['type']='source_fact'
        with self.assertRaises(a.SynthesisError) as e:a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(e.exception.code,'source_fact_not_admitted')
    def test_capture_status_preserved(self):
        p,r=case();_,_,trace=a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(trace['source_snapshot'][0]['capture_status'],'success')
        self.assertTrue(trace['source_snapshot'][0]['content_ok']);self.assertEqual(trace['source_fact'],[])
    def test_missing_evidence_rejected(self):
        p,r=case();r['evidence']=r['evidence'][1:]
        with self.assertRaises(a.SynthesisError) as e:a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(e.exception.code,'evidence_link_drift')
    def test_authority_promotion_rejected(self):
        p,r=case();p['human_approved']=True
        with self.assertRaises(a.SynthesisError) as e:a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(e.exception.code,'authority_escalation')
    def test_unknown_topic_has_no_fallback(self):
        p,r=case();r['claims']=[]
        with self.assertRaises(a.SynthesisError) as e:a.compile_candidate(p,r,qrp=self.qrp)
        self.assertEqual(e.exception.code,'unknown_claim')
    def test_read_only_partial_recovery(self):
        root=self.enterContext(isolated_test_directory('original-synthesis-generalization-resume'))/'output'
        a.persist(root,{'a.txt':'a','b.txt':'b'},stop_after=1);a.persist(root,{'a.txt':'a','b.txt':'b'})
        with self.assertRaises(a.SynthesisError):a.persist(root,{'new.txt':'new','a.txt':'changed'})
        self.assertFalse((root/'new.txt').exists())
    def test_reviewed_native_policy_positive_and_binding(self):
        # Reuse the committed native validator fixture, without representing it as real review.
        native=a.read(ROOT/'fixtures/case-video-script-v1/synthetic-research-output.v1.json')
        for s in native['sources']:s['url']='https://example.org/synthetic-reviewed-source'
        policy=self.qrp.adapter.validate_research_semantics(native)
        temp=self.enterContext(isolated_test_directory('original-synthesis-generalization-reviewed'))
        path=temp/'native.json';path.write_text(a.json_text(native),encoding='utf-8')
        raw={'claims':native['claims'],'sources':[{'source_id':s['source_id'],'canonical_ref':s['url'],
            'content_sha256':s['hash']['value'],'capture_content_ok':True,'title':'Synthetic reviewed source',
            'source_type':'official_documentation','content':' '.join(e['excerpt'] for e in native['evidence']),
            'archive_path':'synthetic.json','archive_sha256':'a'*64} for s in native['sources']],
            'evidence':[{**e,'text':e['excerpt']} for e in native['evidence']], 'question':'Synthetic reviewed policy check'}
        plan={'reviewed_research':{'path':'native.json','sha256':a.sha(path.read_bytes())}}
        self.assertEqual(a.reviewed_policy(plan,raw,temp,self.qrp)['verified_claims'],policy['verified_claims'])
        units=[{'id':'u'+str(i),'claim_id':c['claim_id'],'text':c['text'],'type':'source_fact',
            'assertion_kind':'reviewed_source_fact','evidence_ids':c['supporting_evidence_ids']} for i,c in enumerate(native['claims'])]
        editor={'schema_version':'content-original-editorial-plan.v2','status':'candidate_only','human_approved':False,
            'synthetic_only':True,
            'title':'Synthetic reviewed facts','claim_ids':[c['claim_id'] for c in native['claims']], 'units':units,
            'article_order':[u['id'] for u in units],'oral_order':[u['id'] for u in units],
            'unknowns':[],'withheld':[{'status':'needs_source','text':'real use unverified'}]}
        _,_,trace=a.compile_candidate(editor,raw,policy,qrp=self.qrp)
        self.assertEqual(len(trace['source_fact']),len(units))
        raw['sources'][0]['capture_content_ok']=False
        with self.assertRaises(a.SynthesisError) as e:a.reviewed_policy(plan,raw,temp,self.qrp)
        self.assertEqual(e.exception.code,'source_fact_requires_complete_capture')

if __name__=='__main__':unittest.main()
