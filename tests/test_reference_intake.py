"""Fictional local captures; no upstream HowToLiveBetter content or real study."""
import json
import os
from pathlib import Path
import socket
import sys
from unittest.mock import patch

import pytest
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import capture_research_candidate as entry
from reference_intake import assess_reference
from saved_research_candidate import sha
from research_output_adapter import adapt_research_output, AdapterError

QRP = Path(os.environ.get('CONTENT_STUDIO_QRP_ROOT', str(ROOT.parent / 'question-research-poc'))).resolve()


def fixture(root, kind='official_policy'):
    root.mkdir(parents=True)
    topic = root / 'topic.json'
    topic.write_text(json.dumps({'question': 'What limits apply to the fictional archive rule?',
                                'audience': 'Synthetic contract reviewers', 'budgets': {}}), encoding='utf-8')
    texts = [
        'SYNTHETIC lead, not actual HowToLiveBetter content. An author rates a fictional archive rule A. '
        'The author suggests that all archived documents are always reusable. This is an unverified '
        'proposal, not a fact. Check the cited original document, effective period and conditions. '
        'This fixture has no people, health records, clinical findings or product advice.',
        'SYNTHETIC original document, not a real policy or paper. The fictional archive rule permits '
        'reuse only after an input identity check. A changed input requires a new review. This example '
        'does not establish automatic permission or universal reuse. Its author and scope are fictional. '
        'It is written solely for offline evidence contract testing, never public advice.']
    rows = []
    for i, body in enumerate(texts):
        url = f'https://example.org/synthetic/{kind}/{i}'
        path = root / f'capture-{i}.json'
        path.write_text(json.dumps({'title': 'SYNTHETIC ' + kind, 'requested_url': url, 'final_url': url,
            'status': 'partial', 'transport_ok': True, 'content_ok': False, 'http_status': 200,
            'fetched_at': '2026-10-12T00:00:00Z', 'extracted_text': body,
            'capture_completeness': {'status': 'complete_against_saved_dom'}, 'fixture': True}), encoding='utf-8')
        rows.append({'url': url, 'path': path.name, 'sha256': sha(path.read_bytes())})
    index = {'captures': rows, 'reference_intake': {
        'provider': 'HowToLiveBetter', 'lead_url': rows[0]['url'],
        'recorded_at': '2026-10-12T00:00:00Z', 'lead_claim': texts[0], 'author_rating': 'A',
        'rating_system': 'author_defined_not_clinical_GRADE',
        'original_sources': [{'url': rows[1]['url'], 'kind': kind}]}}
    captures = root / 'captures.json'
    captures.write_text(json.dumps(index), encoding='utf-8')
    return topic, captures, index, texts


def drive(root, kind='official_policy', lead_support=False):
    topic, captures, index, texts = fixture(root, kind)
    output = root / 'workflow'
    def run(values=None, previous=None):
        observation = None
        if values is not None:
            contract = previous['research']['observation_contract']
            observation = root / (contract['stage'] + '.json')
            observation.write_text(json.dumps({**values, 'stage': contract['stage'],
                'basis_artifact_sha256': contract['basis_artifact_sha256']}), encoding='utf-8')
        return entry.advance(topic, captures, output, QRP, observation=observation)
    first = run()
    assert first['reference_intake']['verified_fact_promotion_allowed'] is False
    second = run({'reads': [{'url': index['captures'][0]['url']}]}, first)
    artifacts = output / 'research/saved-capture-research/artifacts'
    initial_id = json.loads((artifacts / '02-source_admission.json').read_text('utf-8'))['captures'][0]['source_id']
    third = run({'subquestions': [{'subquestion_id': 'q1', 'text': 'Check original archive rule limits',
                     'depth': 1, 'basis_source_id': initial_id, 'basis_quote': texts[0]}],
                 'reads': [{'url': index['captures'][1]['url'], 'subquestion_id': 'q1'}]}, second)
    original_id = json.loads((artifacts / '03-evidence_analysis.json').read_text('utf-8'))['captures'][0]['source_id']
    text = texts[0] if lead_support else texts[1]
    result = run({'claims': [{'subquestion_id': 'q1', 'text': text,
                 'evidence': [{'source_id': initial_id if lead_support else original_id, 'text': text}]}]}, third)
    assert all(json.loads(p.read_text('utf-8'))['network_called'] is False
               for p in (artifacts.parent / 'receipts').glob('*.json'))
    assert 'arw_quality' in json.loads((artifacts / '04-guarded_synthesis.json').read_text('utf-8'))
    return result, run, output


@pytest.fixture(autouse=True)
def offline():
    with patch.object(socket.socket, 'connect', side_effect=AssertionError('network forbidden')):
        yield


@pytest.mark.parametrize('kind', ['original_paper', 'official_policy'])
def test_qrp_arw_candidate_and_fact_handoff(tmp_path, kind):
    result, rerun, output = drive(tmp_path / kind, kind)
    assert result['status'] == 'candidate_only'
    assert result['reference_intake']['status'] == 'needs_primary_review'
    assert result['reference_intake']['clinical_GRADE_assessed'] is False
    handoff = result['reference_handoff']
    card_path = Path(handoff['fact_card_path'])
    card = json.loads(card_path.read_text('utf-8'))
    Draft202012Validator(json.loads((ROOT / 'schemas/content-fact-card.v0.schema.json').read_text('utf-8'))).validate(card)
    assert card['synthetic_only'] is True
    assert card['gates']['fact'] == 'blocked'
    assert card['canonical_status'] == 'draft'
    assert all(f['status'] == 'excluded' for f in card['facts'])
    for fact in card['facts']:
        source_path, pointer = fact['evidence_refs'][0]['ref_id'].split('#', 1)
        source_claim = json.loads(Path(source_path).read_text('utf-8'))
        for key in pointer.lstrip('/').split('/'):
            source_claim = source_claim[int(key)] if isinstance(source_claim, list) else source_claim[key]
        assert source_claim['text'] == fact['text']
    assert sha(card_path.read_bytes()) == handoff['fact_card_sha256']
    assert not handoff['story_drafting_allowed']
    candidate = json.loads(next(Path(result['candidate_dir']).glob('*.content-item.json')).read_text('utf-8'))
    assert candidate['provenance']['verified_facts'] == []
    assert candidate['gates']['fact']['status'] == 'blocked'
    with pytest.raises(AdapterError) as rejected:
        adapt_research_output(Path(result['research_output']), tmp_path / 'must-not-draft',
                              QRP / 'schemas/research-output.v1.schema.json')
    assert not (tmp_path / 'must-not-draft').exists()
    again = rerun()
    assert again['reused'] is True
    assert again['reference_handoff'] == handoff
    retained = os.environ.get('SELECTIVE_REFERENCE_EVIDENCE_DIR')
    if retained:
        # Preserve actual run outputs; absolute references continue pointing to this test's retained base temp.
        report = Path(retained) / (kind + '-result.json')
        report.write_text(json.dumps({'result': result, 'verified_adapter_rejection': rejected.value.code,
                                    'test_output': str(output)}, indent=2), encoding='utf-8')


def test_lead_cannot_support_claim_even_with_primary_capture(tmp_path):
    result, _, output = drive(tmp_path / 'lead', lead_support=True)
    assert 'claim_without_saved_primary_support' in result['reference_intake']['blocking_reasons']
    assert result['status'] in {'needs_primary_source', 'needs_evidence_review'}
    assert not (output / 'candidate').exists()
    assert result['reference_handoff']['status'] == 'blocked_pending_fact_review'


@pytest.mark.parametrize('rating', ['A', 'B', 'C'])
def test_author_ratings_never_grade(tmp_path, rating):
    _, _, index, _ = fixture(tmp_path / rating)
    index['reference_intake']['author_rating'] = rating
    assert not assess_reference(index)['clinical_GRADE_assessed']
    index['reference_intake']['clinical_GRADE'] = 'high'
    with pytest.raises(ValueError, match='reference_intake_invalid'):
        assess_reference(index)


def test_missing_original_is_requirement_not_network(tmp_path):
    topic, captures, index, _ = fixture(tmp_path / 'missing')
    index['captures'] = index['captures'][:1]
    captures.write_text(json.dumps(index), encoding='utf-8')
    result = entry.advance(topic, captures, tmp_path / 'out', QRP)
    assert result['reference_intake']['status'] == 'needs_source'
    assert result['reference_intake']['blocking_reasons'] == ['original_capture_missing']
    index['reference_intake']['original_sources'] = []
    assert 'original_paper_or_official_policy_required' in assess_reference(index)['blocking_reasons']


def test_lead_self_citation_and_unknown_source_kind_rejected(tmp_path):
    _, _, index, _ = fixture(tmp_path / 'self')
    index['reference_intake']['original_sources'][0]['url'] = index['reference_intake']['lead_url']
    with pytest.raises(ValueError, match='reference_original_must_be_distinct'):
        assess_reference(index)
    index['reference_intake']['original_sources'][0]['kind'] = 'blog_summary'
    with pytest.raises(ValueError, match='reference_intake_invalid'):
        assess_reference(index)


def test_metadata_drift_requires_new_run(tmp_path):
    topic, captures, index, _ = fixture(tmp_path / 'drift')
    output = tmp_path / 'out'
    entry.advance(topic, captures, output, QRP)
    index['reference_intake']['author_rating'] = 'B'
    captures.write_text(json.dumps(index), encoding='utf-8')
    with pytest.raises(ValueError, match='workflow_input_drift'):
        entry.advance(topic, captures, output, QRP)


def test_fact_card_drift_not_silently_overwritten(tmp_path):
    result, rerun, _ = drive(tmp_path / 'card-drift')
    path = Path(result['reference_handoff']['fact_card_path'])
    changed = json.loads(path.read_text('utf-8'))
    changed['gates']['fact'] = 'pass'
    path.write_text(json.dumps(changed), encoding='utf-8')
    with pytest.raises(ValueError, match='reference_handoff_drift'):
        rerun()
    assert json.loads(path.read_text('utf-8')) == changed
