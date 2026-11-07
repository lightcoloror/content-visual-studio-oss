"""Consume the existing self-media selection without choosing a platform for research."""
import hashlib
import json
from pathlib import Path
import sys

from registered_self_media import load_module


def selection(path, question):
    if path is None:
        return None
    path=Path(path).resolve()
    raw=path.read_bytes()
    request=json.loads(raw)
    resolved=load_module('self_media_agent').resolve_request(request)
    topic=resolved.get('editorial_context',{}).get('topic_selection',{})
    if topic.get('adoption')!='selected' or topic.get('topic')!=question:
        raise ValueError('research_topic_selection_mismatch')
    if not resolved.get('content_format') or not resolved.get('platform'):
        raise ValueError('research_delivery_selection_incomplete')
    if any(k in resolved.get('missing_inputs',[]) for k in ('topic_decision','current_framework_decision_permits_drafting',
            'topic_adoption_basis_for_selected_task','topic_selection_in_context_manifest','platform')):
        raise ValueError('research_delivery_selection_not_adopted')
    if path.read_bytes()!=raw:
        raise ValueError('research_work_request_drift')
    return dict(request_ref=dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()),
                request_id=request['request_id'],topic_selection=topic,
                requested_output=request['requested_output'],content_format=resolved['content_format'],platform=resolved['platform'])
