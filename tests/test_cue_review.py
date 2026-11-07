"""Cue revision correctness; synthetic files only, separate from browser/FFmpeg QA."""
import copy,json,sys,unittest,subprocess,time,os
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import human_voice_review as r
import cue_review as c
from temp_workspace import isolated_test_directory

def request_at(root):
    track={'schema_version':c.TRACK,'synthetic_only':True,'scenes':[
        {'scene_id':'s1','start_ms':0,'end_ms':2000},{'scene_id':'s2','start_ms':2000,'end_ms':4000}],
        'cues':[{'cue_id':'c1','scene_id':'s1','start_ms':0,'end_ms':900,'text':'Collect sources'},
                {'cue_id':'c2','scene_id':'s1','start_ms':1000,'end_ms':2000,'text':'Check sources'},
                {'cue_id':'c3','scene_id':'s2','start_ms':3000,'end_ms':4000,'text':'Save revision'}]}
    path=root/'track.json';path.write_bytes(c.encoded(track));ref={'path':str(path),'sha256':r.file_hash(path)}
    request={'review_id':'synthetic-cue-test','sources':[ref],
       'candidates':{'fixture':{'title':'Synthetic','version':'1','synthetic_only':True,'read_only':False,'source_refs':[ref]}},
       'artifacts':{'track.json':{'candidate_id':'fixture','source_ref':ref,'text':path.read_text(encoding='utf-8'),'body_sha256':r.gate._text_sha256(path.read_text(encoding='utf-8'))}},
       'choices':[{'id':'edit-'+cue['cue_id'],'candidate_id':'fixture','kind':'cue','cue_id':cue['cue_id'],
                   'before_cue':cue,'targets':['track.json']} for cue in track['cues']]}
    return request

class CueReviewTests(unittest.TestCase):
    def setUp(self):
        self.cm=isolated_test_directory('cue-review');self.root=self.cm.__enter__()
        self.request=request_at(self.root);self.bundle=r.build_bundle(self.request,self.root);self.out=self.root/'out'
    def tearDown(self):self.cm.__exit__(None,None,None)
    def event(self,eid='a',parent=None,op='set',text='Checked sources'):
        row=self.bundle['choices'][0];cue={**row['before_cue'],'text':text}
        e={'schema_version':c.EVENT,'event_id':eid,'bundle_sha256':self.bundle['bundle_sha256'],'parent_event_id':parent,'operation':op}
        if op=='set':e.update(choice_id=row['id'],decision={'action':'modify','replacement':cue,'binding':row['binding']})
        return e
    def commit(self,e,**kw):return c.commit_event(self.bundle,e,self.root,self.out,**kw)
    def test_retry_old_event_does_not_rewind_new_head(self):
        a=self.event();first=self.commit(a);self.commit(self.event('b','a',text='Keep checking'))
        repeated=self.commit(a);self.assertEqual(repeated['status'],'reused');self.assertEqual(repeated['head'],'b');self.assertEqual(first['revision'],repeated['revision'])
        with self.assertRaisesRegex(ValueError,'decision_id_conflict'):self.commit(self.event(text='Conflict'))
    def test_undo_redo_are_new_commits_retry_once_and_branch_clears_redo(self):
        a=self.commit(self.event());u=self.event('u','a','undo');ur=self.commit(u)
        self.assertNotEqual(a['revision'],ur['revision']);self.assertEqual(self.commit(u)['status'],'reused')
        redo=self.event('r','u','redo');self.commit(redo);self.assertEqual(self.commit(redo)['status'],'reused')
        self.commit(self.event('u2','r','undo'));self.commit(self.event('b','u2',text='New branch'))
        with self.assertRaisesRegex(ValueError,'nothing_to_redo'):self.commit(self.event('r2','b','redo'))
    def test_stale_parent_and_stale_session(self):
        a=self.event();self.commit(a)
        with self.assertRaisesRegex(ValueError,'stale_decision_head'):self.commit(self.event('b'))
        with self.assertRaisesRegex(ValueError,'stale_decision_history'):c.apply_session(self.bundle,{'schema_version':c.SESSION,'bundle_sha256':self.bundle['bundle_sha256'],'events':[]},self.root,self.out)
    def test_partial_before_commit_resume_no_duplicate(self):
        e=self.event();p=self.commit(e,stop_before_commit=True);self.assertFalse((self.out/'decisions').exists())
        paths=list((self.out/'revisions'/p['revision']).iterdir());times={x.name:x.stat().st_mtime_ns for x in paths}
        self.commit(e);self.commit(e);self.assertEqual(times,{x.name:x.stat().st_mtime_ns for x in paths});self.assertEqual(len(list((self.out/'decisions').glob('*.json'))),1)
    def test_writer_lock_rejects_competing_request(self):
        with c.writer_lock(self.out):
            with self.assertRaisesRegex(ValueError,'decision_writer_busy'):self.commit(self.event())
    def test_process_death_releases_lock_without_history_deletion(self):
        ready=self.root/'lock-ready'
        code='import sys,time;from pathlib import Path;sys.path.insert(0,sys.argv[1]);import cue_review as c\nwith c.writer_lock(Path(sys.argv[2])):\n Path(sys.argv[3]).write_text("ready");time.sleep(10)'
        child=subprocess.Popen([sys.executable,'-B','-c',code,str(ROOT/'scripts'),str(self.out),str(ready)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            until=time.monotonic()+3
            while not ready.exists() and time.monotonic()<until:time.sleep(.01)
            self.assertTrue(ready.exists())
            with self.assertRaisesRegex(ValueError,'decision_writer_busy'):self.commit(self.event())
        finally:
            child.terminate();child.wait(timeout=3);child.stderr.close()
        self.assertEqual(self.commit(self.event())['status'],'committed')
    def test_drift_rejected_even_for_duplicate_event(self):
        e=self.event();self.commit(e);(self.root/'track.json').write_text('drift')
        with self.assertRaisesRegex(ValueError,'stale_input_hash'):self.commit(e)
    def test_real_flag_cannot_be_overridden_by_choice(self):
        self.request['candidates']['fixture']['synthetic_only']=False;self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'real_material_read_only'):self.commit(self.event())
    def test_track_real_even_if_candidate_says_synthetic(self):
        a=self.request['artifacts']['track.json'];t=json.loads(a['text']);t['synthetic_only']=False;p=self.root/'track.json';p.write_bytes(c.encoded(t))
        ref={'path':str(p),'sha256':r.file_hash(p)};a.update(text=p.read_text(encoding='utf-8'),body_sha256=r.gate._text_sha256(p.read_text(encoding='utf-8')),source_ref=ref)
        self.request['sources']=[ref];self.request['candidates']['fixture']['source_refs']=[ref];self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'real_material_read_only'):self.commit(self.event())
    def test_cue_move_and_boundaries(self):
        for change,error in [({'start_ms':0,'end_ms':0},'cue_outside_scene'),({'end_ms':2100},'cue_outside_scene'),({'scene_id':'missing'},'unknown_scene'),({'start_ms':True},'cue_outside_scene'),({'end_ms':1100},'overlapping_cues'),({'text':'bad\\line'},'invalid_cue_text')]:
            with self.subTest(change=change):
                e=self.event();e['decision']['replacement'].update(change)
                with self.assertRaisesRegex(ValueError,error):c.replay(self.bundle,[e])
        e=self.event();e['decision']['replacement'].update(scene_id='s2',start_ms=2000,end_ms=3000)
        projected=r.project_decisions(self.bundle,c.replay(self.bundle,[e])['current']);t=json.loads(projected['track.json'])
        self.assertEqual(t['cues'][0]['cue_id'],'c1');self.assertEqual(t['cues'][0]['scene_id'],'s2')
    def test_session_resume_is_idempotent(self):
        session={'schema_version':c.SESSION,'bundle_sha256':self.bundle['bundle_sha256'],'events':[self.event()]}
        self.assertEqual(c.apply_session(self.bundle,session,self.root,self.out)['new_decisions'],1)
        self.assertEqual(c.apply_session(self.bundle,session,self.root,self.out)['new_decisions'],0)
    def test_tampered_history_rejected(self):
        self.commit(self.event());p=next((self.out/'decisions').glob('*.json'));x=r.load(p);x['event']['operation']='undo';p.write_bytes(c.encoded(x))
        with self.assertRaisesRegex(ValueError,'decision_history_drift'):c.read_history(self.out,self.bundle)
    def test_tampered_revision_content_rejected(self):
        receipt=self.commit(self.event());(self.out/'revisions'/receipt['revision']/'track.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'decision_revision_drift'):self.commit(self.event())
    def test_history_is_replayable_and_events_are_never_rewritten(self):
        self.commit(self.event());self.commit(self.event('b','a',text='Keep checking'))
        records,events,state=c.read_history(self.out,self.bundle)
        self.assertEqual(events,[record['event'] for record in records])
        self.assertEqual(state,c.replay(self.bundle,events))
        before={p.name:p.read_bytes() for p in (self.out/'decisions').glob('*.json')}
        self.commit(self.event('u','b','undo'))
        after={p.name:p.read_bytes() for p in (self.out/'decisions').glob('*.json') if p.name in before}
        self.assertEqual(before,after)
    def test_duplicate_event_commits_one_record(self):
        e=self.event();self.assertEqual(self.commit(e)['status'],'committed');self.assertEqual(self.commit(e)['status'],'reused')
        self.assertEqual(len(list((self.out/'decisions').glob('*.json'))),1)
    def test_configured_review_workspace_is_external_configuration(self):
        ws=self.root/'review-workspace'
        with patch.dict(os.environ,{r.REVIEW_WORKSPACE_ENV:str(ws)}):
            self.assertEqual(c.commit_event(self.bundle,self.event(),self.root,ws/'out')['status'],'committed')
            self.assertTrue((ws/'out'/'decisions').is_dir())
            with self.assertRaisesRegex(ValueError,'path_outside_allowed_root'):
                c.commit_event(self.bundle,self.event('outside'),self.root,self.out)
    def test_shipped_minimal_cue_fixture_projects_fixture_track(self):
        request=r.load(ROOT/'fixtures/minimal-cue-review/request.json')
        bundle=r.build_bundle(request,ROOT)
        self.assertEqual([row['id'] for row in bundle['choices']],['edit-c1','edit-c2','edit-c3'])
        row=bundle['choices'][0];replacement={**row['before_cue'],'text':'Checked sources'}
        event={'schema_version':c.EVENT,'event_id':'fixture','bundle_sha256':bundle['bundle_sha256'],'parent_event_id':None,
               'operation':'set','choice_id':row['id'],'decision':{'action':'modify','replacement':replacement,'binding':row['binding']}}
        changed=r.project_decisions(bundle,c.replay(bundle,[event])['current'])
        self.assertIn('track.json',changed)
        self.assertEqual(json.loads(changed['track.json'])['cues'][0],replacement)
        out=self.root/'fixture-out';result=c.commit_event(bundle,event,ROOT,out)
        self.assertEqual(result['status'],'committed');self.assertEqual(len(list((out/'decisions').glob('*.json'))),1)

if __name__=='__main__':unittest.main()
