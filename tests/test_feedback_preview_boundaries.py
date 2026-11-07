import copy,os,subprocess,unittest
from pathlib import Path
from unittest.mock import patch
import feedback_fixture
f=feedback_fixture.f


class FeedbackBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root=f.W/'feedback-boundaries';cls.config=feedback_fixture.create(cls.root/'preview')
    def test_explicit_workspace_is_required(self):
        with patch.object(f,'W',None):
            with self.assertRaisesRegex(ValueError,'workspace_root_required'):f.workspace(self.root/'out')
    def test_config_bundle_escape_refused_before_read(self):
        config=copy.deepcopy(self.config);config['bundle_path']=str(f.W.parent/'not-read.json')
        with self.assertRaisesRegex(ValueError,'path_outside_workspace'):f.validate_config(config)
    def test_mismatched_native_owner_workspace_refused(self):
        other=f.W/'other';other.mkdir()
        with self.assertRaisesRegex(ValueError,'workspace_owner_layout_mismatch'):
            f.configure_workspace(other,f.W/'tool-registry.json')
    def test_review_output_permission_checked_before_any_output(self):
        output=self.root/'not-written'
        with patch.dict(os.environ,{'CONTENT_STUDIO_REVIEW_WORKSPACE':str(self.root/'different-output-root')}):
            with self.assertRaisesRegex(ValueError,'path_outside_allowed_root'):
                f.prepare(self.config['bundle_path'],{},output,{})
        self.assertFalse(output.exists())
    def test_changed_import_profile_cannot_upgrade_template(self):
        config=copy.deepcopy(self.config);config['imports'][0]['profile']='not-a-template-profile'
        with self.assertRaisesRegex(ValueError,'preview_template_only'):f.validate_config(config)
    def test_history_outside_workspace_refused(self):
        with self.assertRaisesRegex(ValueError,'path_outside_workspace'):f.history(f.W.parent)
    def test_synthetic_flag_cannot_be_removed(self):
        config=copy.deepcopy(self.config);config['synthetic_only']=False
        with self.assertRaisesRegex(ValueError,'synthetic_only_required'):f.validate_config(config)
    def test_all_public_main_source_bytes_unchanged(self):
        source=Path(os.environ['CONTENT_STUDIO_PUBLIC_MAIN_ROOT'])
        names=[n for n in subprocess.check_output(['git','-C',str(source),'ls-files','-z']).decode().split('\0') if n]
        self.assertEqual(len(names),509)
        for name in names:self.assertEqual((f.W/name).read_bytes(),(source/name).read_bytes(),name)


if __name__=='__main__':unittest.main()
