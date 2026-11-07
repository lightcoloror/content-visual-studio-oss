"""Actual hash-bound inspection and production blocking, not completed research."""
import importlib.util
import json
import os
from pathlib import Path
import unittest
import uuid
from unittest.mock import Mock, patch

import context_manifest_consumer as consumer
from context_manifest_consumer import consume_step_handoff

SELF_MEDIA_ROOT=Path(os.environ.get('SELF_MEDIA_SYSTEM_ROOT',str(Path(__file__).resolve().parents[2]/'self-media-creation-system')))

class ContextManifestConsumerTests(unittest.TestCase):
    def test_inspection_preserves_status_and_hash_drift_blocks(self):
        spec=importlib.util.spec_from_file_location('public_context_test_agent',SELF_MEDIA_ROOT/'scripts/self_media_agent.py')
        agent=importlib.util.module_from_spec(spec);spec.loader.exec_module(agent)
        root=Path(os.environ.get('TEST_TMP_ROOT',str(SELF_MEDIA_ROOT/'.runtime')))/('consumer-'+uuid.uuid4().hex)
        root.mkdir(parents=True)
        request=agent.load_json(agent.RECIPE_FIXTURES['xhs-evidence-graphic'])
        capsule=agent.resolve_request(request)
        capsule_path=root/'capsule.json';agent.write_or_print(capsule,capsule_path)
        source=root/'synthetic.json'
        source.write_text('{"synthetic_only":true,"scope":"inspection only; no research or author approval"}',encoding='utf-8')
        step=next(row for row in capsule['step_index'] if row['step_id']=='build-evidence-draft')
        manifest=root/'context.json'
        manifest.write_text(json.dumps(dict(schema_version='self-media-context-input.v1',task_id=request['request_id'],
            stage=step['context_stage'],budget=dict(max_inline_bytes=4096),artifacts=[dict(
                artifact_id='source-'+str(i),role='source_manifest',source_role=role,path=source.name,
                load_mode='reference',expected_sha256=agent.sha256_file(source)) for i,role in enumerate(step['input_roles'])])),encoding='utf-8')
        handoff=root/'handoff.json'
        agent.prepare_step_handoff(capsule_path,step['step_id'],manifest,root/'context-receipt.json',handoff,inspection_only=True)
        value=agent.validate_step_handoff(handoff,allow_inspection=True)
        self.assertEqual(value['status'],'inspection_only')
        self.assertEqual(value['tool_contract']['registry_tool_id'],'content-creation-system')
        self.assertNotEqual(value['status'],'ready_for_existing_owner')
        with self.assertRaisesRegex(Exception,'inspection handoff cannot authorize'):
            consume_step_handoff(handoff)
        # The same placeholder context is not accepted as a production handoff.
        with self.assertRaises(agent.AgentEntryError):
            agent.prepare_step_handoff(capsule_path,step['step_id'],manifest,root/'production-context.json',root/'production-handoff.json')
        source.write_text('drift',encoding='utf-8')
        with self.assertRaisesRegex(Exception,'context_receipt_drift'):
            agent.validate_step_handoff(handoff,allow_inspection=True)

    def test_consumer_delegates_to_the_registered_execution_validator(self):
        owner=Mock()
        owner.validate_step_handoff.return_value={'status':'synthetic-delegation-only'}
        path=Path('synthetic-handoff.json')
        with patch.object(consumer,'_agent',return_value=owner):
            self.assertEqual(consume_step_handoff(path),{'status':'synthetic-delegation-only'})
        owner.validate_step_handoff.assert_called_once_with(path,expected_tool_id='content-studio-poc')
