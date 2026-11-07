"""Offline saved-research projection through QRP and the existing content adapter.

Completed stages are hash-bound. Partial import attempts remain isolated and are
never appended to on retry. This command does not acquire sources or publish.
"""
from __future__ import annotations

import argparse
from qrp_owner_binding import default_qrp_root
import contextlib
import hashlib
import io
import json
import os
import sys
import uuid
from pathlib import Path

from filelock import FileLock
from research_output_adapter import main as consume
from selected_delivery import selection as delivery_selection


def sha(data):
    return hashlib.sha256(data).hexdigest()


def atomic_json(path, value):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def call(entry, args):
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        code = entry(args)
    if code != 0:
        raise ValueError(f'entrypoint_failed:{code}')
    return json.loads(stdout.getvalue())


def inventory(root):
    return {p.relative_to(root).as_posix(): sha(p.read_bytes())
            for p in sorted(root.rglob('*')) if p.is_file()}


def verify(root, hashes):
    if not isinstance(hashes, dict) or not hashes:
        raise ValueError('invalid_stage_hashes')
    for name, expected in hashes.items():
        path = contained(root, name)
        if not path.is_file() or sha(path.read_bytes()) != expected:
            raise ValueError('saved_stage_artifact_drift')


def contained(root, name):
    if not isinstance(name, str) or not name or Path(name).is_absolute():
        raise ValueError('invalid_stage_path')
    path = (root / name).resolve()
    if path == root.resolve() or not path.is_relative_to(root.resolve()):
        raise ValueError('invalid_stage_path')
    return path


def project_candidate(input_path, capture_root, output_root, qrp_root, *, work_request=None):
    input_path, capture_root, output_root, qrp_root = [Path(p).resolve() for p in
                                                    (input_path, capture_root, output_root, qrp_root)]
    from qrp_owner_binding import bind_qrp
    qrp, core = bind_qrp(qrp_root)
    raw = input_path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError('public_archive_input_required')
    material = payload.get('derived_material', payload)
    if not isinstance(material, dict) or material.get('schema') != core.PUBLIC_INPUT_CONTRACT:
        raise ValueError('public_archive_input_required')
    core._validate_fixture_semantics(material)
    core._validate_public_archives(material, capture_root)
    delivery = delivery_selection(work_request, material['question'])
    binding = {'input_sha256': sha(raw), 'capture_root': str(capture_root),
               'qrp_root': str(qrp_root), 'captures': {s['archive_path']: s['archive_sha256'] for s in material['sources']}}
    if delivery is not None:
        binding['delivery_selection'] = delivery
    output_root.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output_root / '.candidate.lock'), timeout=0):
        state_path = output_root / 'candidate-state.json'
        state = json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else {'binding': binding}
        if not isinstance(state, dict) or state.get('binding') != binding:
            raise ValueError('input_binding_drift_use_new_output')
        if state.get('complete'):
            verify(output_root, state['hashes'])
            result = {**state['result'], 'reused': True}
            if delivery is None:
                result.update(artifact_role='intermediate_research_draft',platform_selected=None,delivery_selection=None)
            return result
        if 'project' in state:
            project = contained(output_root, state['project'])
            verify(output_root, state['project_hashes'])
            if not project.is_dir() or not any(
                contained(output_root, name).is_relative_to(project) for name in state['project_hashes']
            ):
                raise ValueError('invalid_stage_project')
            trace = state['trace']
        else:
            # A partial native import is isolated, not retried by appending rows.
            project = output_root / 'attempts' / uuid.uuid4().hex / 'project'
            trace = {'sources': {}, 'claims': {}, 'evidence': {}}
            call(qrp, ['init', material['question'], '--project', str(project)])
            for source in material['sources']:
                body = project / 'sources' / (sha(source['source_id'].encode()) + '.txt')
                body.parent.mkdir(exist_ok=True)
                body.write_text(source['content'], encoding='utf-8')
                capture = capture_root / source['archive_path']
                notes = '\n'.join(['verification_status: candidate_excerpt_only',
                    'source_path: ' + str(body), 'artifact_sha256: ' + sha(body.read_bytes()),
                    'capture_path: ' + str(capture), 'capture_sha256: ' + source['archive_sha256'],
                    'fetched_at: ' + source['capture_fetched_at'],
                    'capture_status: ' + source['capture_status'],
                    'capture_scope: ' + source['capture_scope'],
                    'Candidate source; no independent fact review or publication authority.'])
                row = call(qrp, ['add-source', '--project', str(project), '--title', source['title'],
                    '--url', source['canonical_ref'], '--path', str(body), '--source-type', 'web',
                    '--quality', 'mixed', '--notes', notes])
                trace['sources'][source['source_id']] = row['id']
            for claim in material['claims']:
                row = call(qrp, ['add-claim', '--project', str(project), '--text', claim['text'],
                    '--notes', 'Candidate interpretation, not a verified fact.'])
                trace['claims'][claim['claim_id']] = row['id']
            for evidence in material['evidence']:
                row = call(qrp, ['add-evidence', '--project', str(project),
                    '--claim-id', trace['claims'][evidence['claim_id']],
                    '--source-id', trace['sources'][evidence['source_id']],
                    '--quote-or-note', evidence['text'], '--relation', evidence['relation'],
                    '--confidence', 'candidate', '--notes', 'Exact saved excerpt; candidate only.'])
                trace['evidence'][evidence['evidence_id']] = row['id']
            state.update(project=project.relative_to(output_root).as_posix(), trace=trace,
                         project_hashes={p.relative_to(output_root).as_posix(): sha(p.read_bytes())
                                         for p in project.rglob('*') if p.is_file()})
            atomic_json(state_path, state)
        exported = output_root / 'research-output.v1.json'
        if 'export_sha256' not in state:
            call(qrp, ['export-research-output', '--project', str(project), '--output', str(exported),
                '--scope', material['question'], '--audience', material['audience'],
                '--requested-output', delivery['requested_output'] if delivery else 'guarded_answer',
                '--scope-constraint', 'Saved excerpts, unreviewed, no publication authority.'])
            state['export_sha256'] = sha(exported.read_bytes())
            atomic_json(state_path, state)
        elif sha(exported.read_bytes()) != state['export_sha256']:
            raise ValueError('export_drift')
        def verify_inputs():
            if sha(input_path.read_bytes()) != binding['input_sha256']:
                raise ValueError('input_changed_during_projection')
            if delivery_selection(work_request, material['question']) != delivery:
                raise ValueError('delivery_selection_changed_during_projection')
            core._validate_public_archives(material, capture_root)
        if delivery and delivery['requested_output'] != 'article':
            verify_inputs()
            result = dict(status='needs_format_adapter',research_output=str(exported),delivery_selection=delivery,
                          publish_authorized=False,reused=False,
                          next_action=dict(kind='existing_cli',argv=['python',
                              str(Path(sys.modules['self_media_agent'].__file__)), 'resolve','--request',str(work_request),
                              '--output','<new-selection.json>']),
                          completion_boundary='Research export only; selected format has not been produced.')
            state.update(complete=True,result=result,hashes={**state['project_hashes'],
                'research-output.v1.json':sha(exported.read_bytes())})
            atomic_json(state_path,state)
            return result
        candidate = output_root / 'candidates' / uuid.uuid4().hex
        result = call(consume, ['--research-output', str(exported), '--output-dir', str(candidate),
                               '--allow-unverified-draft'])
        # Recheck immutable inputs before declaring the projection complete.
        verify_inputs()
        atomic_json(output_root / 'projection-trace.json', {'binding': binding, **trace})
        result = {'status': 'candidate_only', 'consumer': result, 'candidate_dir': str(candidate),
                  'research_output': str(exported), 'publish_authorized': False, 'reused': False}
        result.update(delivery_selection=delivery,artifact_role='selected_article_candidate' if delivery else 'intermediate_research_draft',
            platform_selected=delivery['platform'] if delivery else None,
            completion_boundary='Candidate only; no topic adoption or platform decision is inferred from the draft shape.')
        state.update(complete=True, result=result,
                     hashes={**state['project_hashes'],
                             **{p.relative_to(output_root).as_posix(): sha(p.read_bytes())
                                for p in candidate.rglob('*') if p.is_file()},
                             'research-output.v1.json': sha(exported.read_bytes()),
                             'projection-trace.json': sha((output_root / 'projection-trace.json').read_bytes())})
        atomic_json(state_path, state)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--capture-root', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--work-request', type=Path, help='Optional existing adopted self-media request; not inferred from research.')
    parser.add_argument('--qrp-root', type=Path, default=default_qrp_root())
    args = parser.parse_args(argv)
    try:
        print(json.dumps(project_candidate(args.input, args.capture_root, args.output_dir, args.qrp_root, work_request=args.work_request), ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print(json.dumps({'status': 'failed', 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
