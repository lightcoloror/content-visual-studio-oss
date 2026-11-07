"""Resolve shared self-media code from the authority registry, never an old checkout."""
import importlib
import os
import json
from pathlib import Path
import sys

REGISTRY = Path(os.environ.get('SELF_MEDIA_TOOL_REGISTRY', str(Path.cwd() / 'tool-registry.json'))).resolve()


def tool_record(name, registry=REGISTRY):
    return json.loads(Path(registry).read_text(encoding='utf-8-sig'))['tools'][name]


def scripts_root(registry=REGISTRY):
    record = tool_record('content-creation-system', registry)
    root = Path(record['self_media_path']).resolve()
    registered = Path(record['runtime_main']['repositories']['self']['path']).resolve()
    if root != registered or not (root/'scripts/self_media_agent.py').is_file():
        raise ValueError('registered_self_media_root_mismatch')
    return root/'scripts'


def load_module(name, registry=REGISTRY):
    root = scripts_root(registry)
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve() != root/(name+'.py'):
        raise ValueError('mixed_self_media_module_root:'+name)
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    module = importlib.import_module(name)
    if Path(module.__file__).resolve() != root/(name+'.py'):
        raise ValueError('mixed_self_media_module_root:'+name)
    return module
