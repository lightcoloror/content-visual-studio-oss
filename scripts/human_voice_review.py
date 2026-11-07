"""Thin, draft-only review projection over the existing human_voice_gate.

No approval receipts, upstream regeneration, server or media editor are created.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import re
import uuid
from pathlib import Path
import human_voice_gate as gate
import studio_paths

VERSION = '1.0.0'
SCHEMA = 'content-human-voice-review.v1'
# Public, explicit review work root. In source layout the historical default is
# still the studio source root; an installed package must never write review
# artifacts into site-packages/studio_assets, so the caller configures this root.
REVIEW_WORKSPACE_ENV = 'CONTENT_STUDIO_REVIEW_WORKSPACE'
WORKSPACE = gate.WORKSPACE
ADMIN = gate.STUDIO_ROOT / 'admin'

def digest(value):
    return gate._text_sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')))

def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def review_workspace_root():
    override = os.environ.get(REVIEW_WORKSPACE_ENV)
    root = Path(override).expanduser().resolve() if override else Path(gate.WORKSPACE).resolve()
    installed = studio_paths.STUDIO_ROOT != studio_paths.SOURCE_ROOT
    if installed and root.is_relative_to(Path(studio_paths.STUDIO_ROOT).resolve()):
        raise ValueError('review_workspace_outside_source: set '+REVIEW_WORKSPACE_ENV+' to a writable review root; generated review artifacts are never written into the installed studio_assets package')
    return root

def output_root(value):
    return bound_path(review_workspace_root(), str(value))

def bound_path(root, value):
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('path_outside_allowed_root')
    return path

def file_hash(path):
    return gate._file_sha256(Path(path))

def verify_sources(bundle, root):
    for source in bundle['sources']:
        path = bound_path(root, source['path'])
        if file_hash(path) != source['sha256']:
            raise ValueError('stale_input_hash')
    for artifact in bundle['artifacts'].values():
        source=artifact['source_ref'];path=bound_path(root,source['path'])
        if file_hash(path)!=source['sha256'] or path.read_text(encoding='utf-8')!=artifact['text']:
            raise ValueError('artifact_source_drift')
        if source not in bundle['sources']:raise ValueError('artifact_source_unbound')
    for candidate in bundle['candidates'].values():
        if any(source not in bundle['sources'] for source in candidate['source_refs']):raise ValueError('candidate_source_unbound')

def validate_bundle(bundle):
    if bundle.get('schema_version') != SCHEMA or bundle.get('version') != VERSION:
        raise ValueError('review_version_mismatch')
    expected = digest({k:v for k,v in bundle.items() if k != 'bundle_sha256'})
    if bundle.get('bundle_sha256') != expected:
        raise ValueError('stale_bundle_hash')
    ids = set()
    for cid,candidate in bundle['candidates'].items():
        material={k:a['body_sha256'] for k,a in bundle['artifacts'].items() if a['candidate_id']==cid}
        binding={'candidate_id':cid,'candidate_version':candidate['version'],'input_sha256':digest(candidate['source_refs']),'body_sha256':digest(material)}
        if candidate['binding']!=binding:raise ValueError('candidate_binding_drift')
        if not candidate.get('synthetic_only') and not candidate.get('read_only'):raise ValueError('real_material_read_only')
    for row in bundle['choices']:
        if row['id'] in ids: raise ValueError('duplicate_choice_id')
        ids.add(row['id'])
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', row['id']): raise ValueError('invalid_choice_id')
        candidate = bundle['candidates'][row['candidate_id']]
        if row['binding'] != candidate['binding']: raise ValueError('candidate_binding_drift')
        if row.get('kind') == 'cue':
            from cue_review import validate_row
            validate_row(bundle,row)
            continue
        for target in row.get('targets', []):
            artifact = bundle['artifacts'][target]
            if artifact['candidate_id'] != row['candidate_id']: raise ValueError('cross_candidate_target')
            if not row['before'] or artifact['text'].count(row['before']) != 1:
                raise ValueError('span_not_unique')
    for key, artifact in bundle['artifacts'].items():
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+', key) or key in ('.','..'):
            raise ValueError('invalid_artifact_id')
        if gate._text_sha256(artifact['text']) != artifact['body_sha256']:
            raise ValueError('artifact_body_hash_drift')

def build_bundle(request, root):
    bundle = copy.deepcopy(request)
    bundle.update(schema_version=SCHEMA, version=VERSION, publication_authorized=False, human_approval=False)
    bundle.pop('bundle_sha256', None)
    verify_sources(bundle, root)
    for cid, candidate in bundle['candidates'].items():
        material = {k:a['body_sha256'] for k,a in bundle['artifacts'].items() if a['candidate_id']==cid}
        candidate['binding'] = {'candidate_id':cid, 'candidate_version':candidate['version'],
            'input_sha256':digest(candidate['source_refs']), 'body_sha256':digest(material)}
        if not candidate.get('synthetic_only',False): candidate['read_only']=True
    for row in bundle['choices']:
        row['binding'] = bundle['candidates'][row['candidate_id']]['binding']
        row['read_only'] = bool(bundle['candidates'][row['candidate_id']].get('read_only',True))
        row.setdefault('priority',50)
    bundle['choices'].sort(key=lambda r:(-r['priority'],r['id']))
    bundle['bundle_sha256']=digest(bundle)
    validate_bundle(bundle)
    return bundle

def project_decisions(bundle, draft):
    validate_bundle(bundle)
    if draft.get('schema_version')!='content-review-draft.v1' or draft.get('version')!=VERSION:
        raise ValueError('draft_version_mismatch')
    if draft.get('bundle_sha256') != bundle['bundle_sha256']: raise ValueError('stale_review_page')
    rows={x['id']:x for x in bundle['choices']};edits={};decisions=draft.get('decisions',{})
    for key, decision in decisions.items():
        if key not in rows: raise ValueError('unknown_choice')
        row=rows[key];candidate=bundle['candidates'][row['candidate_id']]
        if row['read_only'] or not candidate.get('synthetic_only'): raise ValueError('real_material_read_only')
        if decision.get('binding') != row['binding']: raise ValueError('stale_candidate_body')
        action=decision.get('action')
        if action not in ('keep','modify','reject'): raise ValueError('invalid_action')
        if row.get('kind')=='cue':continue
        if action!='modify':continue
        replacement=decision.get('replacement')
        if not isinstance(replacement,str) or len(replacement)>10000:raise ValueError('invalid_replacement')
        if not row.get('targets'):raise ValueError('no_patch_target')
        for target in row['targets']:
            text=bundle['artifacts'][target]['text'];start=text.index(row['before']);end=start+len(row['before'])
            for s,e,_ in edits.get(target,[]):
                if start<e and s<end:raise ValueError('overlapping_edits')
            edits.setdefault(target,[]).append((start,end,replacement))
    changed={}
    for target,operations in edits.items():
        original=bundle['artifacts'][target]['text'];text=original
        for start,end,replacement in sorted(operations,reverse=True):text=text[:start]+replacement+text[end:]
        if text!=original:changed[target]=text
    from cue_review import project_cues
    cues=project_cues(bundle,draft)
    if set(cues)&set(edits):raise ValueError('mixed_cue_text_edits')
    changed.update(cues)
    return changed

def persist_exact(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=data: raise ValueError('existing_revision_drift')
    else:
        temporary=path.with_name('.'+path.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            with temporary.open('xb') as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            # On Windows rename is no-clobber. The decision writer also serializes commits.
            os.rename(temporary,path)
        finally:
            if temporary.exists():temporary.unlink()

def apply_draft(bundle, draft, root, output, stop_after=None, *, revision_id=None):
    verify_sources(bundle,root)
    changed=project_decisions(bundle,draft)
    output=output_root(str(output));revision=revision_id or digest(draft)
    if not re.fullmatch(r'[a-f0-9]{64}',revision):raise ValueError('invalid_revision_id')
    revision_root=output/'revisions'/revision
    files={key:text.encode('utf-8') for key,text in changed.items()}
    index={'schema_version':'content-review-local-update.v1','revision':revision,'bundle_sha256':bundle['bundle_sha256'],
        'changed_artifacts':list(changed),'inherited_artifacts':{k:v['source_ref'] for k,v in bundle['artifacts'].items() if k not in changed},
        'artifact_sha256':{k:hashlib.sha256(v).hexdigest() for k,v in files.items()},
        'status':'synthetic_draft_only','human_approval':False,'publication_authorized':False,
        'research_regenerated':False,'asr_regenerated':False,'media_modified':False,
        'voice_diagnostics':{k:gate.diagnose_human_voice(v) for k,v in changed.items()}}
    files['decision-draft.json']=(json.dumps(draft,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    files['consumer-index.json']=(json.dumps(index,ensure_ascii=False,sort_keys=True,indent=2)+'\n').encode('utf-8')
    for name,data in files.items():
        p=revision_root/name
        if p.exists() and p.read_bytes()!=data:raise ValueError('existing_revision_drift')
    for n,(name,data) in enumerate(files.items(),1):
        persist_exact(revision_root/name,data)
        if stop_after==n:return {'status':'paused','revision':revision,'path':str(revision_root)}
    return {'status':'complete_draft_only','revision':revision,'path':str(revision_root),'changed_artifacts':list(changed)}

def build_page(bundle, output, root=None):
    output=output_root(str(output));output.mkdir(parents=True,exist_ok=True)
    text=json.dumps(bundle,ensure_ascii=False,sort_keys=True,indent=2)+'\n'
    safe=text.replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    template=(ADMIN/'review.html').read_text(encoding='utf-8')
    html=template.replace('<!-- REVIEW_BUNDLE -->','<script id="review-bundle" type="application/json">'+safe+'</script>')
    html=html.replace('href="review.css"','href="review.css"').replace('src="review.js"','src="review.js"')
    for name,data in {'index.html':html.encode(),'bundle.json':text.encode(),'review.js':(ADMIN/'review.js').read_bytes(),'review.css':(ADMIN/'review.css').read_bytes(),'feedback.js':(ADMIN/'feedback.js').read_bytes()}.items():
        persist_exact(output/name,data)
    for media in bundle.get('media',[]):
        if root is None:raise ValueError('media_root_required')
        if not re.fullmatch(r'[a-zA-Z0-9_.-]+',media['file']) or media['file'] in ('.','..'):raise ValueError('unsafe_media_name')
        path=bound_path(root,media['source_ref']['path'])
        if file_hash(path)!=media['source_ref']['sha256']:raise ValueError('stale_media_hash')
        persist_exact(output/media['file'],path.read_bytes())
    return {'status':'built_pending_browser_validation','entry':str(output/'index.html'),'bundle_sha256':bundle['bundle_sha256']}

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('build');b.add_argument('--request',type=Path,required=True)
    a=sub.add_parser('apply');a.add_argument('--bundle',type=Path,required=True);a.add_argument('--draft',type=Path,required=True);a.add_argument('--stop-after',type=int)
    d=sub.add_parser('decide');d.add_argument('--bundle',type=Path,required=True);d.add_argument('--event',type=Path,required=True)
    s=sub.add_parser('apply-session');s.add_argument('--bundle',type=Path,required=True);s.add_argument('--session',type=Path,required=True)
    t=sub.add_parser('render-cues');t.add_argument('--bundle',type=Path,required=True);t.add_argument('--decisions',type=Path,required=True);t.add_argument('--track',required=True);t.add_argument('--cache',type=Path,required=True)
    t.add_argument('--video-source',type=Path,help='Explicit version-bound Video project root; no automatic checkout fallback')
    for item in (a,b,d,s,t):item.add_argument('--allowed-root',type=Path,required=True);item.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    try:
        if args.command=='build':result=build_page(build_bundle(load(args.request),args.allowed_root),args.output,args.allowed_root)
        elif args.command=='apply':result=apply_draft(load(args.bundle),load(args.draft),args.allowed_root,args.output,args.stop_after)
        elif args.command=='decide':
            from cue_review import commit_event
            result=commit_event(load(args.bundle),load(args.event),args.allowed_root,args.output)
        elif args.command=='apply-session':
            from cue_review import apply_session
            result=apply_session(load(args.bundle),load(args.session),args.allowed_root,args.output)
        else:
            from cue_timeline_adapter import render_revision
            result=render_revision(load(args.bundle),args.decisions,args.track,args.allowed_root,args.cache,args.output,video_source=args.video_source)
        print(json.dumps(result,ensure_ascii=False));return 0
    except (ValueError,OSError,KeyError,gate.HumanVoiceGateError) as e:
        print(json.dumps({'status':'blocked','reason':str(e)},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
