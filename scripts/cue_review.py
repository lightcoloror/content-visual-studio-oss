"""Cue projection and immutable decisions for the existing review entry.

Content-owned glue only. Video rendering is delegated to audio_timeline.
"""
from __future__ import annotations

import copy
import json
import os
import re
from contextlib import contextmanager
from pathlib import Path

import human_voice_review as review

SESSION = 'content-review-session.v1'
EVENT = 'content-review-decision.v1'
TRACK = 'content-cue-track.v1'
SAFE_ID = re.compile(r'[A-Za-z0-9_-]{1,100}')


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2)+'\n').encode('utf-8')


def track_from(artifact):
    track = json.loads(artifact['text'])
    validate_track(track)
    return track


def validate_track(track):
    if track.get('schema_version') != TRACK:
        raise ValueError('cue_track_version')
    scenes = {}
    previous = 0
    for scene in track['scenes']:
        sid, a, b = scene['scene_id'], scene['start_ms'], scene['end_ms']
        if not SAFE_ID.fullmatch(sid) or sid in scenes or type(a) is not int or type(b) is not int or a != previous or b <= a:
            raise ValueError('invalid_scene_interval')
        scenes[sid] = scene
        previous = b
    if not scenes:
        raise ValueError('scenes_required')
    ids, intervals = set(), {sid: [] for sid in scenes}
    for cue in track['cues']:
        if set(cue) != {'cue_id','scene_id','start_ms','end_ms','text'}:
            raise ValueError('invalid_cue_fields')
        cid, sid, a, b, text = (cue[k] for k in ('cue_id','scene_id','start_ms','end_ms','text'))
        if not isinstance(cid,str) or not SAFE_ID.fullmatch(cid) or cid in ids:
            raise ValueError('invalid_cue_id')
        ids.add(cid)
        if sid not in scenes:
            raise ValueError('unknown_scene')
        scene=scenes[sid]
        if type(a) is not int or type(b) is not int or not scene['start_ms'] <= a < b <= scene['end_ms']:
            raise ValueError('cue_outside_scene')
        if not isinstance(text,str) or not text.strip() or len(text)>34 or any(c in text for c in '{}\\\r\n'):
            raise ValueError('invalid_cue_text')
        intervals[sid].append((a,b))
    for values in intervals.values():
        if not values:
            raise ValueError('scene_requires_cue')
        ordered=sorted(values)
        if any(b > c for (_,b),(c,_) in zip(ordered,ordered[1:])):
            raise ValueError('overlapping_cues')


def validate_row(bundle,row):
    if len(row.get('targets',[])) != 1:
        raise ValueError('cue_requires_one_track')
    target=row['targets'][0]
    artifact=bundle['artifacts'][target]
    if artifact['candidate_id'] != row['candidate_id']:
        raise ValueError('cross_candidate_target')
    track=track_from(artifact)
    matches=[c for c in track['cues'] if c['cue_id']==row['cue_id']]
    if len(matches)!=1 or matches[0]!=row['before_cue']:
        raise ValueError('stale_cue')
    return track


def project_cues(bundle,draft):
    tracks={}
    seen=set()
    for key,decision in draft.get('decisions',{}).items():
        row=next((x for x in bundle['choices'] if x['id']==key),None)
        if row is None:
            raise ValueError('unknown_choice')
        if row.get('kind')!='cue':
            continue
        original=validate_row(bundle,row)
        candidate=bundle['candidates'][row['candidate_id']]
        if row['read_only'] or candidate.get('read_only') or candidate.get('synthetic_only') is not True or original.get('synthetic_only') is not True:
            raise ValueError('real_material_read_only')
        if decision.get('binding')!=row['binding']:
            raise ValueError('stale_candidate_body')
        if decision.get('action') not in ('keep','modify','reject'):
            raise ValueError('invalid_action')
        if decision['action']!='modify':
            continue
        target=row['targets'][0]
        identity=(target,row['cue_id'])
        if identity in seen:
            raise ValueError('overlapping_edits')
        seen.add(identity)
        replacement=decision.get('replacement')
        if not isinstance(replacement,dict) or replacement.get('cue_id')!=row['cue_id']:
            raise ValueError('cue_identity_changed')
        track=tracks.setdefault(target,copy.deepcopy(original))
        track['cues']=[copy.deepcopy(replacement) if c['cue_id']==row['cue_id'] else c for c in track['cues']]
    changed={}
    for target,track in tracks.items():
        validate_track(track)
        if track!=track_from(bundle['artifacts'][target]):
            changed[target]=encoded(track).decode('utf-8')
    return changed


def empty_draft(bundle):
    return {'schema_version':'content-review-draft.v1','version':review.VERSION,
            'bundle_sha256':bundle['bundle_sha256'],'decisions':{}}


def replay(bundle,events):
    current=empty_draft(bundle);undo=[];redo=[];head=None;seen=set()
    for event in events:
        eid=event.get('event_id')
        if event.get('schema_version')!=EVENT or not isinstance(eid,str) or not SAFE_ID.fullmatch(eid) or eid in seen:
            raise ValueError('invalid_decision_id')
        if event.get('bundle_sha256')!=bundle['bundle_sha256']:
            raise ValueError('stale_review_page')
        if event.get('parent_event_id')!=head:
            raise ValueError('stale_decision_head')
        op=event.get('operation')
        if op in ('set','unset'):
            if event.get('choice_id') not in {r['id'] for r in bundle['choices']}:
                raise ValueError('unknown_choice')
            updated=copy.deepcopy(current)
            if op=='set':updated['decisions'][event['choice_id']]=copy.deepcopy(event['decision'])
            else:updated['decisions'].pop(event['choice_id'],None)
            review.project_decisions(bundle,updated)
            if updated==current:raise ValueError('no_decision_change')
            undo.append(current);current=updated;redo=[]
        elif op=='undo':
            if not undo:raise ValueError('nothing_to_undo')
            redo.append(current);current=undo.pop()
        elif op=='redo':
            if not redo:raise ValueError('nothing_to_redo')
            undo.append(current);current=redo.pop()
        else:raise ValueError('invalid_decision_operation')
        review.project_decisions(bundle,current)
        seen.add(eid);head=eid
    return {'current':current,'head':head,'can_undo':bool(undo),'can_redo':bool(redo)}


def read_history(output,bundle):
    commits=[];events=[];previous=None
    for n,path in enumerate(sorted((Path(output)/'decisions').glob('*.json')),1):
        record=review.load(path)
        if record['sequence']!=n or record['parent_commit_sha256']!=previous:
            raise ValueError('decision_history_drift')
        claimed=record.get('commit_sha256')
        if claimed!=review.digest({k:v for k,v in record.items() if k!='commit_sha256'}):
            raise ValueError('decision_history_drift')
        events.append(record['event'])
        state=replay(bundle,events)
        revision=review.digest({'event':record['event'],'draft':state['current']})
        if record['revision']!=revision or record['draft_sha256']!=review.digest(state['current']):
            raise ValueError('decision_revision_drift')
        draft_path=Path(output)/'revisions'/revision/'decision-draft.json'
        if review.load(draft_path)!=state['current']:
            raise ValueError('decision_revision_drift')
        revision_root=draft_path.parent
        expected=review.project_decisions(bundle,state['current'])
        index=review.load(revision_root/'consumer-index.json')
        if index.get('revision')!=revision or index.get('bundle_sha256')!=bundle['bundle_sha256'] or set(index.get('changed_artifacts',[]))!=set(expected):
            raise ValueError('decision_revision_drift')
        for name,text in expected.items():
            path=revision_root/name
            if path.read_bytes()!=text.encode('utf-8') or review.file_hash(path)!=index.get('artifact_sha256',{}).get(name):
                raise ValueError('decision_revision_drift')
        commits.append(record);previous=claimed
    return commits,events,replay(bundle,events)


@contextmanager
def writer_lock(output):
    output.mkdir(parents=True,exist_ok=True)
    path=output/'.decision-writer.lock'
    # Kernel-held locks release after process death; a leftover file is not an
    # active lock and does not require deleting another writer's evidence.
    handle=path.open('a+b')
    if path.stat().st_size==0:handle.write(b'0');handle.flush()
    handle.seek(0)
    if os.name=='nt':
        import msvcrt
        lock=lambda:msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
        unlock=lambda:msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
    else:
        import fcntl
        lock=lambda:fcntl.flock(handle.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        unlock=lambda:fcntl.flock(handle.fileno(),fcntl.LOCK_UN)
    try:lock()
    except OSError as exc:
        handle.close();raise ValueError('decision_writer_busy') from exc
    try:
        yield
    finally:
        handle.seek(0);unlock();handle.close()


def commit_event(bundle,event,root,output,*,stop_before_commit=False):
    review.validate_bundle(bundle);review.verify_sources(bundle,root)
    output=review.output_root(str(output))
    with writer_lock(output):
        records,events,state=read_history(output,bundle)
        existing=next((r for r in records if r['event']['event_id']==event.get('event_id')),None)
        if existing:
            if existing['event']!=event:raise ValueError('decision_id_conflict')
            return {'status':'reused','revision':existing['revision'],'head':state['head'],'event_id':event['event_id']}
        state=replay(bundle,[*events,event])
        revision=review.digest({'event':event,'draft':state['current']})
        review.apply_draft(bundle,state['current'],root,output,revision_id=revision)
        if stop_before_commit:return {'status':'paused_before_commit','revision':revision}
        # Recheck the source immediately before committing; no stale decision becomes current.
        review.verify_sources(bundle,root)
        record={'sequence':len(records)+1,'event':event,'revision':revision,
                'draft_sha256':review.digest(state['current']),
                'parent_commit_sha256':records[-1]['commit_sha256'] if records else None}
        record['commit_sha256']=review.digest(record)
        path=output/'decisions'/f"{record['sequence']:06d}-{event['event_id']}.json"
        review.persist_exact(path,encoded(record))
        return {'status':'committed','revision':revision,'head':state['head'],'event_id':event['event_id']}


def apply_session(bundle,session,root,output):
    if session.get('schema_version')!=SESSION or session.get('bundle_sha256')!=bundle['bundle_sha256']:
        raise ValueError('stale_review_page')
    review.verify_sources(bundle,root)
    records,events,state=read_history(output,bundle)
    incoming=session['events']
    if len(incoming)<len(events) or incoming[:len(events)]!=events:
        raise ValueError('stale_decision_history')
    replay(bundle,incoming)
    results=[commit_event(bundle,e,root,output) for e in incoming]
    return {'status':'complete_draft_only','decisions':len(incoming),'new_decisions':sum(x['status']=='committed' for x in results),
            'revision':results[-1]['revision'] if results else None}
