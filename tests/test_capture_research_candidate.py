import json
import os
from pathlib import Path
import sys
import subprocess
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import capture_research_candidate as entry
from saved_research_candidate import inventory, sha

QRP = Path(os.environ.get('CONTENT_STUDIO_QRP_ROOT', str(ROOT.parent / 'question-research-poc'))).resolve()


def setup(root, theme):
    root.mkdir()
    topic = root / 'topic.json'
    topic.write_text(json.dumps({'question': theme, 'audience': 'Reviewers', 'budgets': {}}))
    rows, texts = [], []
    from web_content_fetcher.extractors import extract_content
    for n in (1, 2):
        text = (f'{theme} source {n} documents an explicit recovery procedure and its limits. '
                'A saved result belongs to its recorded input and must be checked before reuse. '
                'Interrupted operations resume only unfinished stages. Completed writes retain '
                'their original identifiers so subsequent runs cannot duplicate observations.')
        body = extract_content('<article><p>' + text + '</p></article>', extractor='builtin').text
        texts.append(body)
        url = f'https://example.org/{theme.lower()}/{n}'
        capture = {'title': f'{theme} source {n}', 'requested_url': url, 'final_url': url,
                   'status': 'partial', 'transport_ok': True, 'content_ok': False, 'http_status': 200,
                   'fetched_at': '2026-10-03T00:00:00Z', 'extracted_text': body,
                   'capture_completeness': {'status': 'complete_against_saved_dom'},
                   'fixture': True}
        file = root / f'capture{n}.json'
        file.write_text(json.dumps(capture))
        rows.append({'url': url, 'path': file.name, 'sha256': sha(file.read_bytes())})
    index = root / 'captures.json'
    index.write_text(json.dumps({'captures': rows}))
    return topic, index, rows, texts


def complete(root, theme, fail_projection=False, cli=False):
    topic, index, rows, texts = setup(root, theme)
    output = root / 'out'
    def run(observation=None):
        if cli:
            command = [sys.executable, '-B', '-X', 'utf8', str(ROOT / 'scripts/capture_research_candidate.py'),
                       '--topic', str(topic), '--captures', str(index), '--output-dir', str(output)]
            if observation:
                command += ['--observation', str(observation)]
            execution = subprocess.run(command, capture_output=True, encoding='utf-8', timeout=30)
            assert execution.returncode in (0, 2), execution.stderr
            assert execution.stdout, execution.stderr
            return json.loads(execution.stdout)
        return entry.advance(topic, index, output, QRP, observation=observation)
    def observe(result, values):
        contract = result['research']['observation_contract']
        path = root / (contract['stage'] + '.json')
        path.write_text(json.dumps({**values, 'stage': contract['stage'],
                                   'basis_artifact_sha256': contract['basis_artifact_sha256']}))
        return path
    first = run()
    assert first['status'] == 'awaiting_observation'
    second = run(observe(first, {'reads': [{'url': rows[0]['url']}]}))
    stage_root = output / 'research/saved-capture-research/artifacts'
    initial = json.loads((stage_root / '02-source_admission.json').read_text(encoding='utf-8'))
    source = initial['captures'][0]['source_id']
    third = run(observe(second, {'subquestions': [{'subquestion_id': 'q1', 'text': theme + ' recovery limits',
                      'depth': 1, 'basis_source_id': source, 'basis_quote': texts[0]}],
                      'reads': [{'url': rows[1]['url'], 'subquestion_id': 'q1'}]}))
    deep = json.loads((stage_root / '03-evidence_analysis.json').read_text(encoding='utf-8'))
    followup = deep['captures'][0]['source_id']
    observation = observe(third, {'claims': [{'subquestion_id': 'q1', 'text': texts[1],
                    'evidence': [{'source_id': followup, 'text': texts[1]}]}]})
    if fail_projection:
        with patch.object(entry, 'project_candidate', side_effect=ValueError('consumer_failed')):
            with pytest.raises(ValueError, match='consumer_failed'):
                run(observation)
        before = inventory(stage_root)
        result = run()
        assert inventory(stage_root) == before
    else:
        result = run(observation)
    assert result['status'] == 'candidate_only', result
    before = inventory(output / 'candidate')
    again = run()
    assert again['reused'] is True
    assert inventory(output / 'candidate') == before
    assert all(json.loads(p.read_text(encoding='utf-8'))['network_called'] is False
               for p in (stage_root.parent / 'receipts').glob('*.json'))
    return result, topic, index, output


def test_two_topics_actual_wcf_qrp_arw_content_chain(tmp_path):
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        first, *_ = complete(tmp_path / 'search', 'Search', cli=True)
        second, *_ = complete(tmp_path / 'backups', 'Backups', fail_projection=True)
    a = Path(first['research_output']).read_text(encoding='utf-8')
    b = Path(second['research_output']).read_text(encoding='utf-8')
    assert 'Search' in a and 'Backups' not in a
    assert 'Backups' in b and 'Search' not in b
    assert first['candidate_dir'] != second['candidate_dir']


def test_missing_archive_never_calls_network(tmp_path):
    topic, index, rows, _ = setup(tmp_path / 'missing', 'Missing')
    output = tmp_path / 'out'
    result = entry.advance(topic, index, output, QRP)
    contract = result['research']['observation_contract']
    observation = tmp_path / 'observation.json'
    observation.write_text(json.dumps({'stage': contract['stage'],
            'basis_artifact_sha256': contract['basis_artifact_sha256'],
            'reads': [{'url': 'https://example.org/not-saved'}]}))
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        with pytest.raises(RuntimeError, match='no network fallback'):
            entry.advance(topic, index, output, QRP, observation=observation)


@pytest.mark.parametrize('point', ['ledger', 'capture', 'reservation'])
def test_saved_import_interruption_accounted_exactly_once(tmp_path, point):
    _, index, rows, _ = setup(tmp_path / 'source', 'Recovery')
    sys.path.insert(0, str(QRP / 'src'))
    from question_research_poc import topic_research as research
    run = tmp_path / 'research'
    (run / 'artifacts').mkdir(parents=True)
    original = research.write_json
    def interrupted(path, value):
        original(path, value)
        match = ('ledger' if path.name == 'acquisition-ledger.json' else
                 'reservation' if path.name.endswith('.request.json') else 'capture')
        if match == point:
            raise RuntimeError('synthetic_interrupt')
    budgets = {'max_sources': 1, 'max_text_bytes': 100000}
    def read():
        return research._wcf_read(run, rows[0]['url'], 1, budgets, None, 1, index)
    with patch.object(research, 'write_json', side_effect=interrupted):
        with pytest.raises(RuntimeError, match='synthetic_interrupt'):
            read()
    with patch('socket.socket.connect', side_effect=AssertionError('offline')):
        read()
        read()
    ledger = json.loads((run / 'acquisition-ledger.json').read_text(encoding='utf-8'))
    assert len(ledger['saved_imports']) == 1
    assert ledger['bytes_read'] == (index.parent / rows[0]['path']).stat().st_size
    assert ledger['requests'] == []
    with pytest.raises(RuntimeError, match='source/byte budget'):
        research._wcf_read(run, rows[1]['url'], 2, budgets, None, 1, index)


def test_workflow_input_drift_and_busy_lock(tmp_path):
    topic, index, rows, _ = setup(tmp_path / 'source', 'Binding')
    output = tmp_path / 'out'
    entry.advance(topic, index, output, QRP)
    from filelock import FileLock, Timeout
    with FileLock(str(output / '.workflow.lock')):
        with pytest.raises(Timeout):
            entry.advance(topic, index, output, QRP)
    capture = index.parent / rows[0]['path']
    capture.write_text('{}')
    with pytest.raises(ValueError, match='capture_input_drift'):
        entry.advance(topic, index, output, QRP)
