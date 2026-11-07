"""Offline saved capture -> QRP observation stages -> reviewable candidate."""
import argparse
from qrp_owner_binding import default_qrp_root
import hashlib
import json
from pathlib import Path
import sys

from filelock import FileLock
from saved_research_candidate import atomic_json, contained, project_candidate, sha
from reference_intake import assess_reference, write_reference_handoff
from selected_delivery import selection as delivery_selection


def advance(topic, captures, output, qrp_root, *, observation=None, work_request=None):
    topic, captures, output, qrp_root = [Path(p).resolve() for p in (topic, captures, output, qrp_root)]
    from qrp_owner_binding import bind_qrp
    _, core = bind_qrp(qrp_root)
    index = json.loads(captures.read_bytes())
    if not isinstance(index, dict) or not isinstance(index.get('captures'), list) or not index['captures']:
        raise ValueError('capture_index_required')
    for row in index['captures']:
        path = contained(captures.parent, row['path'])
        with path.open('rb') as handle:
            if hashlib.file_digest(handle, 'sha256').hexdigest() != row['sha256']:
                raise ValueError('capture_input_drift')
    reference = assess_reference(index)
    delivery = delivery_selection(work_request, json.loads(topic.read_bytes())['question'])
    binding = {'topic_sha256': sha(topic.read_bytes()), 'index_sha256': sha(captures.read_bytes()),
               'index_path': str(captures), 'qrp_root': str(qrp_root)}
    if delivery is not None:
        binding['delivery_selection'] = delivery
    output.mkdir(parents=True, exist_ok=True)
    with FileLock(str(output / '.workflow.lock'), timeout=0):
        state_path = output / 'workflow-state.json'
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding='utf-8'))
            if state.get('binding') != binding:
                raise ValueError('workflow_input_drift')
        else:
            if any(p.name != '.workflow.lock' for p in output.iterdir()):
                raise ValueError('nonempty_workflow_output')
            state = {'binding': binding}
            atomic_json(state_path, state)
        research = core.run_bounded_deep_loop(topic, output / 'research', closure_run_id='saved-capture-research',
                    resume=True, observation_path=observation, saved_capture_index=captures)
        if research.get('execution_status') == 'awaiting_codex_observation':
            result = {'status': 'awaiting_observation', 'research': research, 'publish_authorized': False}
        else:
            run = output / 'research/saved-capture-research'
            synthesis = run / 'artifacts/04-guarded_synthesis.json'
            material = json.loads(synthesis.read_text(encoding='utf-8'))
            reference = assess_reference(index, material.get('derived_material'))
            if 'derived_material' not in material or material.get('blocking_gates'):
                result = {'status': 'needs_evidence_review', 'research': research, 'publish_authorized': False}
            elif reference and reference['blocking_reasons']:
                result = {'status': 'needs_primary_source', 'research': research, 'publish_authorized': False}
            else:
                result = project_candidate(synthesis, run, output / 'candidate', qrp_root, work_request=work_request)
                result['research'] = research
            if reference:
                result['reference_handoff'] = write_reference_handoff(
                    output, index, material.get('derived_material'), synthesis, result)
        if reference:
            result['reference_intake'] = reference
        state['result'] = result
        atomic_json(state_path, state)
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--topic', type=Path, required=True)
    parser.add_argument('--captures', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--work-request', type=Path, help='Existing self-media topic/form/platform selection, if already decided.')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--observation', type=Path)
    mode.add_argument('--auto-observations', action='store_true',
                      help='Derive bounded mechanical excerpts/gaps from saved captures; semantic analysis remains unexecuted.')
    parser.add_argument('--qrp-root', type=Path, default=default_qrp_root())
    args = parser.parse_args(argv)
    if args.auto_observations:
        from qrp_owner_binding import bind_qrp
        bind_qrp(args.qrp_root)
        from question_research_poc.evidence_autoflow import advance_automatically
        from functools import partial
        result = advance_automatically(args.topic, args.captures, args.output_dir, args.qrp_root,
                                       advance=partial(advance,work_request=args.work_request))
    else:
        result = advance(args.topic, args.captures, args.output_dir, args.qrp_root, observation=args.observation,work_request=args.work_request)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['status'] == 'candidate_only' else 2


if __name__ == '__main__':
    raise SystemExit(main())
