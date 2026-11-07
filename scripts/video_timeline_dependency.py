"""Version-bound Video source loading for Content; no implicit checkout lookup."""
from __future__ import annotations

import hashlib
import importlib
import importlib.abc
import importlib.util
import json
import os
import shutil
import sys
import tomllib
from pathlib import Path

from studio_paths import STUDIO_ROOT

PACKAGE = 'video_creation_pipeline'
# Resolution: explicit env override, else the reviewed lock shipped with the
# source tree or installed studio_assets package. There is never a checkout guess.
LOCK_ENV = 'CONTENT_STUDIO_VIDEO_TIMELINE_LOCK'
LOCK = Path(os.environ.get(LOCK_ENV, str(STUDIO_ROOT/'config/video-timeline-runtime.v1.lock.json'))).expanduser().resolve()
SUFFIXES = {'.py','.json','.html','.css','.ts','.tsx','.txt'}
_active = None


def digest(data):
    return hashlib.sha256(data).hexdigest()


def resolve_lock_path():
    override = os.environ.get(LOCK_ENV)
    return Path(override).expanduser().resolve() if override else Path(LOCK)


def checked_path(root, path):
    # Check directories too: junctions/symlinks must not add an unlocked import root.
    for part in (path, *path.parents):
        if part == root:
            break
        if part.is_symlink() or (hasattr(part,'is_junction') and part.is_junction()):
            raise ValueError('video_dependency_path_escape: '+str(path))
    if not path.resolve().is_relative_to(root):
        raise ValueError('video_dependency_path_escape: '+str(path))
    return path


def inventory(root):
    package = checked_path(root,root/'src'/PACKAGE)
    if not package.is_dir():
        raise ValueError('video_dependency_missing: expected src/video_creation_pipeline')
    files = {'pyproject.toml':checked_path(root,root/'pyproject.toml')}
    for path in package.rglob('*'):
        if '__pycache__' in path.parts:
            continue
        checked_path(root,path)
        if path.is_file() and path.suffix in SUFFIXES:
            files[path.relative_to(root).as_posix()] = path
    return files


def checked_snapshot(root, lock):
    if lock.get('schema_version')!='content-video-runtime-lock.v1' or lock.get('interface')!='audio_timeline.compose/v1':
        raise ValueError('video_dependency_lock_incompatible')
    if not root.is_dir() or not (root/'pyproject.toml').is_file():
        raise ValueError('video_dependency_missing: source must be a Video project root')
    project = tomllib.loads(checked_path(root,root/'pyproject.toml').read_text(encoding='utf-8'))['project']
    if project.get('name')!=lock['distribution'] or project.get('version')!=lock['version']:
        raise ValueError('video_dependency_version_mismatch: expected '+lock['distribution']+' '+lock['version'])
    files = inventory(root)
    if set(files)!=set(lock['files']):
        missing=sorted(set(lock['files'])-set(files));extra=sorted(set(files)-set(lock['files']))
        raise ValueError('video_dependency_file_set_drift: '+json.dumps({'missing':missing,'extra':extra}))
    snapshot = {}
    for name,path in files.items():
        data=path.read_bytes()
        if digest(data)!=lock['files'][name]:
            raise ValueError('video_dependency_implementation_drift: '+name)
        snapshot[name]=data
    return snapshot


class _PinnedLoader(importlib.abc.Loader):
    def __init__(self,path,data):self.path,self.data=path,data
    def create_module(self,spec):return None
    def exec_module(self,module):
        # Execute the checked source bytes, never an unverified timestamp-based pyc.
        exec(compile(self.data,str(self.path),'exec',dont_inherit=True),module.__dict__)


class _PinnedFinder(importlib.abc.MetaPathFinder):
    def __init__(self,root,snapshot):self.root,self.snapshot=root,snapshot
    def find_spec(self,fullname,path=None,target=None):
        if fullname!=PACKAGE and not fullname.startswith(PACKAGE+'.'):return None
        base='src/'+fullname.replace('.','/')
        for name,is_package in ((base+'/__init__.py',True),(base+'.py',False)):
            if name in self.snapshot:
                source=self.root/name
                return importlib.util.spec_from_file_location(fullname,source,
                    loader=_PinnedLoader(source,self.snapshot[name]),
                    submodule_search_locations=[str(source.parent)] if is_package else None)
        raise ModuleNotFoundError('video_dependency_unlocked_module: '+fullname)


class Runtime:
    def __init__(self,root,lock,lock_hash,snapshot):
        self.root,self.lock,self.lock_hash,self.snapshot=root,lock,lock_hash,snapshot
        self.audio_timeline=None;self.artifact_reference=None
    def verify(self):
        checked_snapshot(self.root,self.lock)
        for name,module in list(sys.modules.items()):
            if name==PACKAGE or name.startswith(PACKAGE+'.'):
                origin=getattr(module,'__file__',None)
                if origin is None or not Path(origin).resolve().is_relative_to(self.root):
                    raise ValueError('video_dependency_import_origin_drift: '+name)
                relative=Path(origin).resolve().relative_to(self.root).as_posix()
                if relative not in self.snapshot or not isinstance(getattr(module,'__loader__',None),_PinnedLoader):
                    raise ValueError('video_dependency_import_origin_drift: '+name)
    def evidence(self):
        return {'distribution':self.lock['distribution'],'version':self.lock['version'],
                'runtime_lock_sha256':self.lock_hash,'source_root':str(self.root),
                'timeline_implementation_sha256':self.lock['files']['src/'+PACKAGE+'/audio_timeline.py'],
                'verified_file_count':len(self.snapshot),'loader':'checked_source_bytes_no_pyc',
                'imported_module_origins':{name:str(Path(module.__file__).resolve()) for name,module in sorted(sys.modules.items())
                    if name==PACKAGE or name.startswith(PACKAGE+'.')}}


def load_runtime(source_root):
    global _active
    if source_root is None:
        raise ValueError('video_dependency_required: pass --video-source <version-bound Video project root>; no automatic fallback')
    root=Path(source_root).expanduser().resolve()
    try:raw=resolve_lock_path().read_bytes();lock=json.loads(raw)
    except (OSError,ValueError) as exc:raise ValueError('video_dependency_lock_missing_or_invalid') from exc
    snapshot=checked_snapshot(root,lock)
    for executable in ('ffmpeg','ffprobe'):
        if not shutil.which(executable):raise ValueError('video_runtime_executable_missing: '+executable)
    if _active is not None:
        if _active.root!=root or _active.lock_hash!=digest(raw):
            raise ValueError('video_dependency_already_loaded: restart the process to switch provider')
        _active.verify();return _active
    if any(name==PACKAGE or name.startswith(PACKAGE+'.') for name in sys.modules):
        raise ValueError('video_dependency_already_loaded: unverified Video modules were imported before dependency binding')
    finder=_PinnedFinder(root,snapshot);sys.meta_path.insert(0,finder)
    candidate=Runtime(root,lock,digest(raw),snapshot)
    try:
        timeline=importlib.import_module(PACKAGE+'.audio_timeline')
        contract=importlib.import_module(PACKAGE+'.contract_io')
        candidate.audio_timeline=timeline;candidate.artifact_reference=contract.artifact_reference
        candidate.verify()
    except ImportError as exc:
        raise ValueError('video_dependency_runtime_unavailable: '+str(exc)) from exc
    _active=candidate
    return candidate
