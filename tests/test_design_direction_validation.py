"""Meaningful admission and resource-lookup cases, without rendering or style claims."""
from pathlib import Path
import copy,json,os,sys,unittest
from unittest.mock import patch
C=Path(__file__).resolve().parents[1]
from temp_workspace import isolated_test_directory
sys.path.insert(0,str(C/'scripts'))
import design_direction_validation as d

def item(direction='editorial-field-guide',adapter='article'):
    return {'visual':{'visual_profile':'visual/insurance-observational-advisor','visual_profile_version':'0.2.0',
        'route':'explanatory','design_system':{'media_adapter':adapter,'design_direction':{'direction_id':direction,'version':'1.0.0'}},
        'render_artifacts':[{'media_adapter':adapter,'theme':direction,'layout_intent':'sequence','renderer_options':{'design_direction_id':direction}}]}}

class DirectionTests(unittest.TestCase):
    def setUp(self):
        d.clear_design_direction_cache()
        self.temp=self.enterContext(isolated_test_directory('design-direction'))
    def tearDown(self):d.clear_design_direction_cache()
    def test_default_source_and_packaged_contract_bytes(self):
        self.assertEqual(d.resolve_design_directions_path(),(C/'config/design-directions.v1.json').resolve())
        self.assertEqual((C/'config/design-directions.v1.json').read_bytes(),(C/'scripts/studio_assets/config/design-directions.v1.json').read_bytes())
    def test_both_registered_themes_and_supported_adapters(self):
        for direction,adapters in [('editorial-field-guide',['article','web','social-card','pptx']),('reflective-personal-essay',['article','social-card','pptx'])]:
            for adapter in adapters:
                with self.subTest(direction=direction,adapter=adapter):self.assertEqual(d.validate_design_direction(item(direction,adapter)),[])
    def test_direction_is_required_for_registered_theme(self):
        x=item();x['visual']['design_system'].pop('design_direction')
        self.assertTrue(any('require' in message for _,message in d.validate_design_direction(x)))
    def test_unselected_unregistered_theme_is_not_implicitly_enabled(self):
        x={'visual':{'render_artifacts':[{'theme':'plain'}]}}
        self.assertEqual(d.validate_design_direction(x),[])
    def test_unknown_direction_rejected(self):self.assertTrue(d.validate_design_direction(item('unknown')))
    def test_wrong_direction_version_rejected(self):
        x=item();x['visual']['design_system']['design_direction']['version']='9.0.0';self.assertTrue(d.validate_design_direction(x))
    def test_unmapped_profile_rejected(self):
        x=item();x['visual']['visual_profile']='fictional-unmapped';self.assertTrue(d.validate_design_direction(x))
    def test_unknown_medium_rejected(self):self.assertTrue(d.validate_design_direction(item(adapter='unregistered')))
    def test_excluded_visual_route_and_photo_mode_rejected(self):
        x=item();x['visual']['route']='data_visualization';self.assertTrue(d.validate_design_direction(x))
        x=item();x['visual']['article_visual_plan']={'visual_mode':'editorial-photo-mix'};self.assertTrue(d.validate_design_direction(x))
    def test_wrong_artifact_theme_rejected(self):
        x=item();x['visual']['render_artifacts'][0]['theme']='plain';self.assertTrue(d.validate_design_direction(x))
    def test_explicit_renderer_selection_required_for_social(self):
        x=item(adapter='social-card');x['visual']['render_artifacts'][0]['renderer_options']={};self.assertTrue(d.validate_design_direction(x))
    def test_unregistered_layout_intent_rejected(self):
        x=item(adapter='pptx');x['visual']['render_artifacts'][0]['layout_intent']='data-chart';self.assertTrue(d.validate_design_direction(x))
    def test_missing_contract_fails_closed_and_override_is_explicit(self):
        absent=self.temp/'no-such-contract.json'
        with patch.dict(os.environ,{d.CONTRACT_ENV_VAR:str(absent)}):
            self.assertEqual(d.resolve_design_directions_path(),absent)
            self.assertTrue(d.validate_design_direction(item()))
            self.assertEqual(d.resolve_design_directions_path(C/'config/design-directions.v1.json'),(C/'config/design-directions.v1.json').resolve())
    def test_invalid_json_and_version_are_rejected(self):
        tmp=self.temp/'synthetic-contract-cases';tmp.mkdir(exist_ok=True)
        for name,body in [('malformed','{'),('wrong-version',json.dumps({'schema_version':'bad','directions':{}})),('wrong-types',json.dumps({'schema_version':'shared-design-directions.v1','directions':[]}))]:
            path=tmp/(name+'.json');path.write_text(body,encoding='utf-8')
            self.assertTrue(d.validate_design_direction(item(),path),name)
    def test_no_item_mutation(self):
        x=item();before=copy.deepcopy(x);d.validate_design_direction(x);self.assertEqual(x,before)

if __name__=='__main__':unittest.main(verbosity=2)
