"""Synthetic draft projection tests; never claim browser or human acceptance."""
import copy,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import human_voice_review as r
from temp_workspace import isolated_test_directory

class MinimalReviewTests(unittest.TestCase):
    def setUp(self):
        self.cm=isolated_test_directory('minimal-review');self.root=self.cm.__enter__()
        self.request=r.load(ROOT/'fixtures/minimal-review/request.json')
        for source in self.request['sources']:
            old=ROOT/source['path'];p=self.root/old.name;p.write_bytes(old.read_bytes())
            source['path']=str(p);source['sha256']=r.file_hash(p)
        refs={Path(x['path']).name:x for x in self.request['sources']}
        for a in self.request['artifacts'].values():a['source_ref']=refs[Path(a['source_ref']['path']).name]
        for c in self.request['candidates'].values():c['source_refs']=[refs[Path(x['path']).name] for x in c['source_refs']]
        self.bundle=r.build_bundle(self.request,self.root)
        self.draft={'schema_version':'content-review-draft.v1','version':r.VERSION,'bundle_sha256':self.bundle['bundle_sha256'],'decisions':{}}
    def tearDown(self):self.cm.__exit__(None,None,None)
    def choose(self,id='word',action='modify',replacement=None):
        row=next(x for x in self.bundle['choices'] if x['id']==id)
        self.draft['decisions'][id]={'action':action,'replacement':row['after'] if replacement is None else replacement,'binding':copy.deepcopy(row['binding'])}
    def test_local_update_only_affected_texts(self):
        self.choose();result=r.apply_draft(self.bundle,self.draft,self.root,self.root/'out');p=Path(result['path']);idx=r.load(p/'consumer-index.json')
        self.assertEqual(set(idx['changed_artifacts']),{'a-article.md','a-oral.md'})
        self.assertIn('research.json',idx['inherited_artifacts']);self.assertIn('asr.json',idx['inherited_artifacts'])
        self.assertFalse((p/'b-article.md').exists());self.assertFalse(idx['asr_regenerated']);self.assertFalse(idx['human_approval'])
    def test_video_suggestion_changes_only_sidecar(self):
        self.choose('video-repeat');changed=r.project_decisions(self.bundle,self.draft);self.assertEqual(list(changed),['video-notes.md'])
    def test_keep_and_reject_do_not_modify(self):
        for action in ['keep','reject']:
            self.choose(action=action);self.assertEqual(r.project_decisions(self.bundle,self.draft),{})
    def test_undo_creates_empty_revision_without_deleting_history(self):
        self.choose();first=r.apply_draft(self.bundle,self.draft,self.root,self.root/'out');self.draft['decisions']={}
        undo=r.apply_draft(self.bundle,self.draft,self.root,self.root/'out');self.assertEqual(undo['changed_artifacts'],[]);self.assertTrue(Path(first['path']).is_dir())
    def test_partial_resume_and_repeated_apply_preserve_mtimes(self):
        self.choose();first=r.apply_draft(self.bundle,self.draft,self.root,self.root/'out',1);p=Path(first['path']);self.assertFalse((p/'consumer-index.json').exists())
        r.apply_draft(self.bundle,self.draft,self.root,self.root/'out');before={x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in p.iterdir()}
        r.apply_draft(self.bundle,self.draft,self.root,self.root/'out');self.assertEqual(before,{x.name:(x.read_bytes(),x.stat().st_mtime_ns) for x in p.iterdir()})
    def test_stale_review_hash_rejected(self):
        self.draft['bundle_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'stale_review_page'):r.project_decisions(self.bundle,self.draft)
    def test_stale_body_rejected(self):
        self.choose();self.draft['decisions']['word']['binding']['body_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'stale_candidate_body'):r.project_decisions(self.bundle,self.draft)
    def test_source_drift_rejected_before_write(self):
        self.choose();(self.root/'a-article.md').write_text('changed',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'stale_input_hash'):r.apply_draft(self.bundle,self.draft,self.root,self.root/'out')
        self.assertFalse((self.root/'out').exists())
    def test_missing_path_rejected(self):
        self.bundle['sources'][0]['path']=str(self.root/'absent.md')
        with self.assertRaises(r.gate.HumanVoiceGateError):r.verify_sources(self.bundle,self.root)
    def test_path_escape_rejected(self):
        with self.assertRaisesRegex(ValueError,'path_outside'):r.bound_path(self.root,'../escape')
    def test_real_material_rejects_all_decisions(self):
        self.request['candidates']['fiction-a']['synthetic_only']=False;self.bundle=r.build_bundle(self.request,self.root);self.draft['bundle_sha256']=self.bundle['bundle_sha256']
        for action in ['keep','modify','reject']:
            self.choose(action=action)
            with self.assertRaisesRegex(ValueError,'real_material_read_only'):r.project_decisions(self.bundle,self.draft)
    def test_unknown_choice_rejected(self):
        self.choose();self.draft['decisions']['unknown']=self.draft['decisions'].pop('word')
        with self.assertRaisesRegex(ValueError,'unknown_choice'):r.project_decisions(self.bundle,self.draft)
    def test_overlapping_spans_rejected(self):
        row=copy.deepcopy(self.request['choices'][0]);row['id']='overlap';self.request['choices'].append(row);self.bundle=r.build_bundle(self.request,self.root);self.draft['bundle_sha256']=self.bundle['bundle_sha256'];self.choose();self.choose('overlap')
        with self.assertRaisesRegex(ValueError,'overlapping'):r.project_decisions(self.bundle,self.draft)
    def test_ambiguous_span_rejected(self):
        self.request['choices'][0]['before']='。'
        with self.assertRaisesRegex(ValueError,'span_not_unique'):r.build_bundle(self.request,self.root)
    def test_candidate_binding_recomputed(self):
        self.bundle['candidates']['fiction-a']['binding']['body_sha256']='0'*64;self.bundle['bundle_sha256']=r.digest({k:v for k,v in self.bundle.items() if k!='bundle_sha256'})
        with self.assertRaisesRegex(ValueError,'candidate_binding_drift'):r.validate_bundle(self.bundle)
    def test_stale_bundle_hash_rejected(self):
        self.bundle['bundle_sha256']='0'*64
        with self.assertRaisesRegex(ValueError,'stale_bundle_hash'):r.validate_bundle(self.bundle)
    def test_artifact_source_unbound_rejected(self):
        self.request['sources']=self.request['sources'][1:]
        self.request['candidates']['fiction-a']['source_refs']=self.request['candidates']['fiction-a']['source_refs'][1:]
        with self.assertRaisesRegex(ValueError,'artifact_source_unbound'):r.build_bundle(self.request,self.root)
    def test_invalid_artifact_id_rejected(self):
        ref=self.request['sources'][1]
        self.request['artifacts']['..']={'candidate_id':'fiction-a','source_ref':ref,'text':Path(ref['path']).read_text(encoding='utf-8'),'body_sha256':r.gate._text_sha256(Path(ref['path']).read_text(encoding='utf-8'))}
        with self.assertRaisesRegex(ValueError,'invalid_artifact_id'):r.build_bundle(self.request,self.root)
    def test_partial_revision_drift_not_overwritten(self):
        self.choose();result=r.apply_draft(self.bundle,self.draft,self.root,self.root/'out',1);p=Path(result['path'])/'a-article.md';p.write_text('external change',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'existing_revision_drift'):r.apply_draft(self.bundle,self.draft,self.root,self.root/'out')
        self.assertEqual(p.read_text(encoding='utf-8'),'external change')
    def test_default_top_five_order_and_other_choices_preserved(self):
        self.assertEqual(len(self.bundle['choices']),7);self.assertEqual(self.bundle['choices'][0]['id'],'word');self.assertEqual(self.bundle['choices'][5]['id'],'name')
    def test_script_injection_escaped_in_embedded_bundle(self):
        self.request['choices'][0]['reason']='</script><script>alert(1)</script>';bundle=r.build_bundle(self.request,self.root);r.build_page(bundle,self.root/'page');html=(self.root/'page/index.html').read_text(encoding='utf-8')
        self.assertNotIn('</script><script>alert(1)',html);self.assertIn('\\u003c/script\\u003e',html)
    def test_artifact_text_cannot_detach_from_source(self):
        a=self.request['artifacts']['a-article.md'];a['text']='invented';a['body_sha256']=r.gate._text_sha256(a['text'])
        with self.assertRaisesRegex(ValueError,'artifact_source_drift'):r.build_bundle(self.request,self.root)
    def test_noop_replacement_does_not_rebuild(self):
        self.choose(replacement='资料哈');self.assertEqual(r.project_decisions(self.bundle,self.draft),{})
    def test_build_page_copies_review_assets_and_marks_pending_browser(self):
        result=r.build_page(self.bundle,self.root/'page',self.root)
        page=self.root/'page'
        self.assertEqual(result['status'],'built_pending_browser_validation')
        for name in ('index.html','bundle.json','review.js','review.css','feedback.js'):
            self.assertTrue((page/name).is_file(),name)
        html=(page/'index.html').read_text(encoding='utf-8')
        self.assertIn('id="review-bundle"',html);self.assertIn('src="review.js"',html);self.assertIn('href="review.css"',html)
        self.assertEqual(r.load(page/'bundle.json'),self.bundle)
    def test_configured_review_workspace_is_external_configuration(self):
        ws=self.root/'review-workspace'
        with patch.dict(os.environ,{r.REVIEW_WORKSPACE_ENV:str(ws)}):
            self.assertEqual(r.review_workspace_root(),ws.resolve())
            self.choose();result=r.apply_draft(self.bundle,self.draft,self.root,ws/'out')
            self.assertTrue((ws/'out'/'revisions'/result['revision']).is_dir())
            with self.assertRaisesRegex(ValueError,'path_outside_allowed_root'):
                r.apply_draft(self.bundle,self.draft,self.root,self.root/'outside')
    def test_default_review_workspace_is_source_root_when_unset(self):
        with patch.dict(os.environ,{r.REVIEW_WORKSPACE_ENV:''}):
            self.assertEqual(r.review_workspace_root(),Path(r.gate.WORKSPACE).resolve())
    def test_installed_layout_never_defaults_into_package_assets(self):
        fake=Path(self.root/'site-packages'/'studio_assets');fake.mkdir(parents=True)
        source=Path(self.root/'source');source.mkdir()
        with patch.dict(os.environ,{r.REVIEW_WORKSPACE_ENV:''}):
            with patch.object(r.studio_paths,'STUDIO_ROOT',fake),patch.object(r.studio_paths,'SOURCE_ROOT',source),patch.object(r.gate,'WORKSPACE',fake):
                with self.assertRaisesRegex(ValueError,'review_workspace_outside_source'):r.review_workspace_root()
                with patch.dict(os.environ,{r.REVIEW_WORKSPACE_ENV:str(self.root/'review')}):
                    self.assertEqual(r.review_workspace_root(),(self.root/'review').resolve())
    def test_build_page_reports_stale_media_hash(self):
        self.request['media']=[{'file':'media-note.md','source_ref':{'path':str(self.root/'a-article.md'),'sha256':'0'*64}}]
        self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'stale_media_hash'):r.build_page(self.bundle,self.root/'media-page',self.root)
        self.assertFalse((self.root/'media-page'/'media-note.md').exists())
    def test_build_page_rejects_unsafe_media_name(self):
        self.request['media']=[{'file':'../escape.md','source_ref':{'path':str(self.root/'a-article.md'),'sha256':r.file_hash(self.root/'a-article.md')}}]
        self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'unsafe_media_name'):r.build_page(self.bundle,self.root/'media-page',self.root)
    def test_build_page_rejects_media_path_escape(self):
        self.request['media']=[{'file':'outside.md','source_ref':{'path':str(self.root.parent/'outside.md'),'sha256':'0'*64}}]
        self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'path_outside_allowed_root'):r.build_page(self.bundle,self.root/'media-page',self.root)
    def test_build_page_requires_media_root(self):
        self.request['media']=[{'file':'a-article.md','source_ref':{'path':str(self.root/'a-article.md'),'sha256':r.file_hash(self.root/'a-article.md')}}]
        self.bundle=r.build_bundle(self.request,self.root)
        with self.assertRaisesRegex(ValueError,'media_root_required'):r.build_page(self.bundle,self.root/'media-page')

if __name__=='__main__':unittest.main()
