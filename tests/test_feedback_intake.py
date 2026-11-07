import copy,json,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import feedback_fixture
f=feedback_fixture.f

class FeedbackIntakeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=f.W/'feedback-tests';cls.config=feedback_fixture.create(cls.root/'preview')
    def setUp(self):
        self.out=self.root/self._testMethodName
        row=self.config['candidates'][0]
        self.payload={'key':row['key'],'version':row['binding']['candidate']['sha256'],'action':'edit','reason':'虚构：修正重复句','minutes':None,'baseline_minutes':None}
    def test_unknown_duration_is_not_zero_and_no_publication(self):
        r=f.submit(self.config,self.payload,self.out);p=f.read(r['review_packet'])
        self.assertIsNone(p['outcome_candidate']['edit_effort']['duration_seconds']);self.assertIsNone(r['time_saved_minutes']);self.assertIsNone(p['publication']);self.assertEqual(p['observation_windows'],[]);self.assertEqual(p['scheduled_tasks'],[])
        self.assertFalse(any(p['authority'].values()))
    def test_manual_duration_and_baseline_are_explicit(self):
        self.payload.update(minutes=12.5,baseline_minutes=30)
        r=f.submit(self.config,self.payload,self.out);self.assertEqual(r['time_saved_minutes'],17.5);self.assertEqual(r['savings_source'],'manual_report_comparison')
        self.assertEqual(f.read(r['review_packet'])['outcome_candidate']['edit_effort']['duration_seconds'],750)
    def test_effort_without_baseline_has_unknown_savings(self):
        self.payload['minutes']=10;r=f.submit(self.config,self.payload,self.out);self.assertIsNone(r['time_saved_minutes'])
    def test_three_actions_preserve_hash_binding(self):
        for action,expected in [('adopt','adopted'),('edit','adopted_with_edits'),('reject','discarded')]:
            self.payload['action']=action;r=f.submit(self.config,self.payload,self.out);self.assertEqual(r['decision'],expected);self.assertEqual(r['candidate_sha256'],self.payload['version'])
    def test_repeat_is_byte_and_mtime_stable(self):
        r=f.submit(self.config,self.payload,self.out);before={str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()}
        self.assertTrue(f.submit(self.config,self.payload,self.out)['duplicate']);self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()})
    def test_stale_candidate_rejected_before_write(self):
        self.payload['version']='0'*64
        with self.assertRaisesRegex(ValueError,'stale_candidate_version'):f.submit(self.config,self.payload,self.out)
        self.assertFalse(self.out.exists())
    def test_unknown_candidate_rejected(self):
        self.payload['key']='missing'
        with self.assertRaisesRegex(ValueError,'unknown_candidate'):f.submit(self.config,self.payload,self.out)
    def test_edit_reason_required(self):
        self.payload['reason']=''
        with self.assertRaisesRegex(ValueError,'rework_reason_required'):f.submit(self.config,self.payload,self.out)
    def test_bad_duration_rejected(self):
        for v in [-1,True,float('nan'),float('inf'),1441,'2']:
            self.payload['minutes']=v
            with self.assertRaisesRegex(ValueError,'invalid_minutes'):f.submit(self.config,self.payload,self.out)
    def test_import_deduplicates_across_capture_times(self):
        r=f.import_local(self.config,'wechat',self.out);before={str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()}
        self.assertTrue(f.import_local(self.config,'wechat',self.out)['duplicate']);self.assertEqual(before,{str(p):p.stat().st_mtime_ns for p in self.out.rglob('*') if p.is_file()});self.assertEqual(r['source_grain'],'account_day')
        self.assertTrue(all(x['content_label'] is None and x['attribution_status']=='not-attributed-to-content' for x in r['records']))
        values={m['metric_key']:m['value'] for m in r['records'][1]['metrics']};self.assertIsNone(values['read_users']);self.assertEqual(values['delivered_users'],0);self.assertIsNone(values['open_rate'])
    def test_duration_evidence_cannot_be_forged(self):
        r=f.submit(self.config,self.payload,self.out);req=f.read(Path(r['review_packet']).parent/'request.json');req['outcome']['edits'][0]['duration_seconds']=300
        with self.assertRaisesRegex(ValueError,'time_evidence_drift'):f.link.build(req)
    def test_template_denominator_and_version(self):
        cfg=f.metrics.load_json(f.metrics.MAPPING_PATH)['export_profiles']['wechat_official_template_v1']
        base={'format_version':'wechat-account-day-template.v1','source_grain':'account_day','date':'2026-09-12','read_users':'25','delivered_users':'100','open_rate_percent':'25%'}
        f.metrics.normalize_records('wechat_official_template_v1',[(2,base)],cfg)
        for key,value in [('open_rate_percent','0.25'),('open_rate_percent','101%'),('read_users','101'),('delivered_users','0'),('date','yesterday'),('format_version','official'),('source_grain','content_item')]:
            bad={**base,key:value}
            with self.assertRaises(f.metrics.MetricsIntakeError):f.metrics.normalize_records('wechat_official_template_v1',[(2,bad)],cfg)
    def test_template_cannot_claim_production_compatibility(self):
        r=f.import_local(self.config,'wechat',self.out);value=f.read(r['intake_path']);value['records'][0]['compatibility_status']='production';value.pop('payload_sha256');value['payload_sha256']=f.metrics.hashlib.sha256(f.metrics.canonical_bytes(value)).hexdigest()
        with self.assertRaises(f.metrics.MetricsIntakeError):f.metrics.validate_intake(value)
    def test_arbitrary_path_or_import_fields_rejected(self):
        self.payload['path']='C:/secret'
        with self.assertRaisesRegex(ValueError,'feedback_shape'):f.submit(self.config,self.payload,self.out)
        with self.assertRaisesRegex(ValueError,'unknown_import'):f.import_local(self.config,'../../secret',self.out)
    def test_existing_result_tampering_rejected(self):
        result=f.submit(self.config,self.payload,self.out)
        p=Path(result['review_packet']).parents[1]/'result.json';bad=f.read(p);bad['publication']={'fake':True};p.write_text(f.link.text(bad),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'output_hash_drift'):f.submit(self.config,self.payload,self.out)
    def test_import_result_tampering_rejected(self):
        result=f.import_local(self.config,'wechat',self.out);p=Path(result['intake_path']).parent/'result.json';bad=f.read(p);bad['source_grain']='content_item';p.write_text(f.link.text(bad),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'output_hash_drift'):f.import_local(self.config,'wechat',self.out)
    def test_template_duplicate_headers_and_extra_cells_rejected(self):
        self.out.mkdir(parents=True);p=self.out/'synthetic.csv'
        for text in ['a,a\n1,2\n','a,b\n1,2,3\n']:
            p.write_text(text,encoding='utf-8')
            with self.assertRaises(f.metrics.MetricsIntakeError):f.metrics.read_csv_rows(p,1,strict=True)

if __name__=='__main__':unittest.main()
