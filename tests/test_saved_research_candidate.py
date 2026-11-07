import hashlib
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import saved_research_candidate as entry

QRP = Path(os.environ.get('CONTENT_STUDIO_QRP_ROOT', str(ROOT.parent / 'question-research-poc'))).resolve()


def material(root, topic='Search'):
    text = topic + ' stores explicit criteria and keeps the original source available for review.'
    capture = {'requested_url': 'https://example.org/doc', 'final_url': 'https://example.org/doc',
               'status': 'partial', 'transport_ok': True, 'content_ok': False, 'http_status': 200,
               'fetched_at': '2026-10-03T00:00:00Z', 'extracted_text': text,
               'capture_completeness': {'status': 'complete_against_saved_dom'}}
    archive = root / 'capture.json'
    archive.write_text(json.dumps(capture), encoding='utf-8')
    payload = {'schema': 'question-research-public-archive-input.v1', 'fixture_id': 'test',
        'question': topic, 'audience': 'readers', 'observed_at': '2026-10-03T00:00:00Z',
        'budgets': {'max_subquestions': 3, 'max_depth': 2, 'max_sources': 3,
                    'max_tokens': 1000, 'max_expansions_per_round': 3},
        'subquestions': [{'subquestion_id': 'q', 'text': topic, 'depth': 1, 'gap_score': 1}],
        'sources': [{'source_id': 's', 'title': topic, 'canonical_ref': 'https://example.org/doc',
                     'source_type': 'web', 'quality': 'good', 'review_status': 'candidate',
                     'freshness': 'current', 'content': text, 'content_sha256': entry.sha(text.encode()),
                     'archive_path': 'capture.json', 'archive_sha256': entry.sha(archive.read_bytes()),
                     'capture_scope': 'excerpt_only', 'token_cost': 50}],
        'claims': [{'claim_id': 'c', 'subquestion_id': 'q', 'text': text, 'claim_origin': 'agent_interpretation'}],
        'evidence': [{'evidence_id': 'e', 'claim_id': 'c', 'source_id': 's', 'evidence_type': 'source_claim',
                      'status': 'candidate', 'review_status': 'candidate', 'relation': 'supports', 'text': text}]}
    path = root / 'input.json'
    path.write_text(json.dumps(payload), encoding='utf-8')
    return path


@pytest.mark.parametrize('topic', ['Search', 'Backups'])
def test_two_topics_repeat_without_duplicate_import(tmp_path, topic):
    path = material(tmp_path, topic)
    out = tmp_path / 'out'
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        first = entry.project_candidate(path, tmp_path, out, QRP)
        before = entry.inventory(out)
        again = entry.project_candidate(path, tmp_path, out, QRP)
    assert first['publish_authorized'] is False
    assert again['reused'] is True
    assert before == entry.inventory(out)
    assert len(list((out / 'attempts').glob('*/project'))) == 1
    assert topic in Path(first['research_output']).read_text(encoding='utf-8')


def test_consumer_failure_resumes_without_reimport(tmp_path):
    path = material(tmp_path)
    out = tmp_path / 'out'
    with patch.object(entry, 'consume', side_effect=ValueError('synthetic_failure')):
        with pytest.raises(ValueError, match='synthetic_failure'):
            entry.project_candidate(path, tmp_path, out, QRP)
    state = json.loads((out / 'candidate-state.json').read_text(encoding='utf-8'))
    before = entry.inventory(out / state['project'])
    result = entry.project_candidate(path, tmp_path, out, QRP)
    assert result['status'] == 'candidate_only'
    assert entry.inventory(out / state['project']) == before
    assert len(list((out / 'attempts').glob('*/project'))) == 1


def test_changed_input_rejected_before_reuse(tmp_path):
    path = material(tmp_path)
    out = tmp_path / 'out'
    entry.project_candidate(path, tmp_path, out, QRP)
    changed = json.loads(path.read_text(encoding='utf-8'))
    changed['question'] = 'Changed'
    path.write_text(json.dumps(changed))
    with pytest.raises(ValueError, match='input_binding_drift'):
        entry.project_candidate(path, tmp_path, out, QRP)


@pytest.mark.parametrize('payload', [[], None, {'derived_material': []}])
def test_invalid_payload_rejected_without_output(tmp_path, payload):
    path = tmp_path / 'input.json'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='public_archive_input_required'):
        entry.project_candidate(path, tmp_path, tmp_path / 'out', QRP)
    assert not (tmp_path / 'out').exists()


def test_recovery_project_escape_rejected_before_native_entry(tmp_path):
    path = material(tmp_path)
    out = tmp_path / 'out'
    with patch.object(entry, 'consume', side_effect=ValueError('synthetic_failure')):
        with pytest.raises(ValueError):
            entry.project_candidate(path, tmp_path, out, QRP)
    state_path = out / 'candidate-state.json'
    state = json.loads(state_path.read_text(encoding='utf-8'))
    state['project'] = '../../outside'
    state_path.write_text(json.dumps(state))
    with patch.object(entry, 'call', side_effect=AssertionError('must_not_call')):
        with pytest.raises(ValueError, match='invalid_stage_path'):
            entry.project_candidate(path, tmp_path, out, QRP)


def test_completed_candidate_drift_rejected(tmp_path):
    path = material(tmp_path)
    out = tmp_path / 'out'
    result = entry.project_candidate(path, tmp_path, out, QRP)
    Path(result['research_output']).write_text('{}')
    with pytest.raises(ValueError, match='saved_stage_artifact_drift'):
        entry.project_candidate(path, tmp_path, out, QRP)


def test_empty_hash_manifest_is_not_verified(tmp_path):
    with pytest.raises(ValueError, match='invalid_stage_hashes'):
        entry.verify(tmp_path, {})
