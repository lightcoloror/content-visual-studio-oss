"""Content-side cue binding adapter; reuse Video Owner audio_timeline unchanged."""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import human_voice_review as review
from cue_review import encoded, read_history, track_from, validate_track

MAX_BYTES=128*1024*1024


def budget(paths):
    used=sum(p.stat().st_size for root in set(Path(x).resolve() for x in paths) if root.exists()
             for p in root.rglob('*') if p.is_file())
    if used>MAX_BYTES or shutil.disk_usage(review.review_workspace_root()).free<512*1024*1024:
        raise ValueError('cue_render_disk_budget')
    return used


def render_revision(bundle,decisions,track_key,root,cache,output,*,video_source=None):
    review.validate_bundle(bundle);review.verify_sources(bundle,root)
    artifact=bundle['artifacts'][track_key]
    candidate=bundle['candidates'][artifact['candidate_id']]
    original=track_from(artifact)
    if candidate.get('synthetic_only') is not True or candidate.get('read_only') or original.get('synthetic_only') is not True:
        raise ValueError('real_material_read_only')
    decisions=review.output_root(str(decisions))
    records,events,state=read_history(decisions,bundle)
    changed=review.project_decisions(bundle,state['current'])
    track=json.loads(changed.get(track_key,artifact['text']));validate_track(track)
    cache=review.output_root(str(cache));out=review.output_root(str(output))
    if out==cache or out.is_relative_to(cache) or cache.is_relative_to(out):
        raise ValueError('separate_cache_and_output_required')
    budget([cache,out])
    # Copy only explicitly hash-bound inputs. Consumers use these checked bytes,
    # never reopen a mutable original after validation.
    refs={str(review.bound_path(root,s['path'])):s['sha256'] for s in bundle['sources']}
    def read_bound(ref):
        path=review.bound_path(root,ref['path'])
        if refs.get(str(path))!=ref['sha256']:raise ValueError('timeline_source_unbound')
        if path.stat().st_size>16*1024*1024:raise ValueError('cue_source_too_large')
        data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('stale_input_hash')
        return data
    pp=json.loads(read_bound(original['packaging_ref']))
    binding=json.loads(read_bound(original['binding_ref']))
    if binding.get('synthetic_only') is not True:raise ValueError('real_material_read_only')
    if binding['packaging']['sha256']!=original['packaging_ref']['sha256']:
        raise ValueError('packaging_binding_drift')
    output_spec=pp['output']
    if any(type(output_spec[k]) is not int or not 0<output_spec[k]<=limit for k,limit in [('width',540),('height',960),('fps',30)]):
        raise ValueError('cue_render_geometry_budget')
    if original['scenes']!=[{'scene_id':s['scene_id'],'start_ms':round(s['start_s']*1000),'end_ms':round(s['end_s']*1000)} for s in pp['scenes']]:
        raise ValueError('cue_scene_binding_drift')
    if track['scenes'][-1]['end_ms']>6000:raise ValueError('cue_render_duration_budget')
    from video_timeline_dependency import load_runtime
    runtime=load_runtime(video_source)
    audio_timeline=runtime.audio_timeline;artifact_reference=runtime.artifact_reference
    dependency=runtime.evidence()
    source_hash=dependency['timeline_implementation_sha256']
    segment_cache=cache/'segments'/runtime.lock_hash
    rejected=segment_cache/'runtime-rejected.json'
    if rejected.exists():
        raise ValueError('video_dependency_cache_quarantined: a prior render observed runtime drift; use a new cache directory and preserve this evidence')
    identity={'bundle_sha256':bundle['bundle_sha256'],'track':track_key,
              'head':state['head'],'draft_sha256':review.digest(state['current']),
              'timeline_implementation_sha256':source_hash,
              'video_runtime_lock_sha256':dependency['runtime_lock_sha256']}
    receipt=out/'render-result.json'
    if receipt.exists():
        saved=review.load(receipt)
        if saved['identity']!=identity:raise ValueError('existing_render_revision_drift')
        for path,h in saved['output_hashes'].items():
            if review.file_hash(Path(path))!=h:raise ValueError('existing_render_output_drift')
        runtime.verify()
        return {**saved,'status':'reused_complete_render','validated_video_dependency':runtime.evidence()}
    inputs=cache/'checked-inputs'
    def snapshot(ref):
        data=read_bound(ref)
        path=inputs/(ref['sha256']+Path(ref['path']).suffix.lower())
        review.persist_exact(path,data)
        return artifact_reference(path,'checked source')
    # Validate all input bytes before writing the derived binding/rendering.
    bound_refs=[binding['audio']]
    for segment in binding['segments']:bound_refs += [segment['visual'],segment['provenance']]
    for ref in bound_refs:read_bound(ref)
    packaging=inputs/(original['packaging_ref']['sha256']+'.json')
    review.persist_exact(packaging,read_bound(original['packaging_ref']))
    binding['packaging']=artifact_reference(packaging,'packaging')
    binding['audio']=snapshot(binding['audio'])
    for segment in binding['segments']:
        segment['visual']=snapshot(segment['visual']);segment['provenance']=snapshot(segment['provenance'])
        segment['subtitles']=[{'start_s':c['start_ms']/1000,'end_s':c['end_ms']/1000,'text':c['text']}
                              for c in sorted(track['cues'],key=lambda c:(c['start_ms'],c['cue_id'])) if c['scene_id']==segment['scene_id']]
    binding_path=out/'derived-binding.json'
    review.persist_exact(binding_path,encoded(binding))
    review.verify_sources(bundle,root)
    budget([cache,out])
    # Incomplete attempts remain evidence. Reusing complete scene-cache entries is
    # handled by the existing composer; only final concat/QA needs another attempt.
    attempt=1
    while (out/f'attempt-{attempt:03d}').exists():attempt+=1
    # A reviewed lock update may change helper code without changing audio_timeline.
    # Keep those scene caches separate as well as binding the final receipt.
    try:
        result=audio_timeline.compose(packaging,binding_path,segment_cache,out/f'attempt-{attempt:03d}')
    finally:
        try:
            runtime.verify()
        except (ValueError,OSError) as exc:
            # Keep previous outputs and failed-attempt evidence. Never reuse new
            # cache entries from an attempt whose dependency changed in flight.
            review.persist_exact(rejected,encoded({'runtime_lock_sha256':runtime.lock_hash,
                'reason':str(exc),'attempt':str(out/f'attempt-{attempt:03d}')}))
            raise
    hashes={str(Path(result['candidate']['path'])):result['candidate']['sha256']}
    hashes[str(out/f'attempt-{attempt:03d}'/'manifest.json')]=review.file_hash(out/f'attempt-{attempt:03d}'/'manifest.json')
    answer={'status':'rendered_synthetic_candidate','identity':identity,'video_dependency':runtime.evidence(),'output_hashes':hashes,
            'rendered_segments':result['rendered_segments'],'reused_segments':result['reused_segments'],
            'manifest':str(out/f'attempt-{attempt:03d}'/'manifest.json'),
            'candidate':result['candidate'],'duration_s':result['duration_s'],
            'decoded_frames':result['decoded_frames'],'synthetic_only':True,'publication_authorized':False,
            'output_bytes':budget([cache,out])}
    review.persist_exact(receipt,encoded(answer))
    return answer
