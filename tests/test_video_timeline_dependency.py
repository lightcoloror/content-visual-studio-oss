"""Focused dependency-contract regressions; fake code is never render acceptance."""
import importlib.util
import json
import os
import py_compile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import video_timeline_dependency as dep
from temp_workspace import isolated_test_directory


class DependencyTests(unittest.TestCase):
    def setUp(self):
        # Plain project-contained mkdir matches the other targeted tests; the
        # system tempfile helper is avoided because some sandboxed Windows hosts
        # deny child-directory creation inside mkstemp/mkdtemp paths.
        self.cm=isolated_test_directory('video-dependency');self.root=self.cm.__enter__()
        self.package=self.root/'src'/dep.PACKAGE
        self.package.mkdir(parents=True)
        (self.root/'pyproject.toml').write_text('[project]\nname="video-creation-pipeline"\nversion="0.8.1"\n')
        (self.package/'__init__.py').write_text('MARKER="checked source"\n')
        (self.package/'audio_timeline.py').write_text('def compose(*args): return "fixture only"\n')
        (self.package/'contract_io.py').write_text('def artifact_reference(*args): return {}\n')
        self.lock=self.root/'lock.json';self.freeze()
        self.saved_meta=sys.meta_path[:];self.saved_active=dep._active;dep._active=None
        self.patches=[patch.object(dep,'LOCK',self.lock),patch.object(dep.shutil,'which',return_value='fixture-executable')]
        for p in self.patches:p.start()
    def tearDown(self):
        for name in list(sys.modules):
            if name==dep.PACKAGE or name.startswith(dep.PACKAGE+'.'):sys.modules.pop(name)
        sys.meta_path[:]=self.saved_meta;dep._active=self.saved_active
        for p in reversed(self.patches):p.stop()
        self.cm.__exit__(None,None,None)
    def freeze(self):
        self.spec={'schema_version':'content-video-runtime-lock.v1','interface':'audio_timeline.compose/v1',
          'distribution':'video-creation-pipeline','version':'0.8.1',
          'files':{n:dep.digest(p.read_bytes()) for n,p in dep.inventory(self.root).items()}}
        self.lock.write_text(json.dumps(self.spec))
    def test_missing_source_does_not_guess_an_installed_package(self):
        with self.assertRaisesRegex(ValueError,'video_dependency_required'):dep.load_runtime(None)
        with self.assertRaisesRegex(ValueError,'video_dependency_missing'):dep.load_runtime(self.root/'absent')
    def test_same_distribution_wrong_version_is_rejected(self):
        (self.root/'pyproject.toml').write_text('[project]\nname="video-creation-pipeline"\nversion="9.0.0"\n')
        with self.assertRaisesRegex(ValueError,'version_mismatch'):dep.load_runtime(self.root)
    def test_changed_runtime_source_is_rejected(self):
        (self.package/'contract_io.py').write_text('raise RuntimeError("must not execute")\n')
        with self.assertRaisesRegex(ValueError,'implementation_drift.*contract_io.py'):dep.load_runtime(self.root)
    def test_added_or_missing_module_is_rejected(self):
        extra=self.package/'injected.py';extra.write_text('pass\n')
        with self.assertRaisesRegex(ValueError,'file_set_drift'):dep.load_runtime(self.root)
        extra.unlink();(self.package/'contract_io.py').unlink()
        with self.assertRaisesRegex(ValueError,'file_set_drift'):dep.load_runtime(self.root)
    def test_path_escape_is_rejected_before_read(self):
        with self.assertRaisesRegex(ValueError,'path_escape'):dep.checked_path(self.root,self.root.parent/'outside.py')
        with patch.object(Path,'is_symlink',return_value=True):
            with self.assertRaisesRegex(ValueError,'path_escape'):dep.load_runtime(self.root)
    def test_preloaded_provider_is_not_silently_reused(self):
        sys.modules[dep.PACKAGE]=types.ModuleType(dep.PACKAGE)
        with self.assertRaisesRegex(ValueError,'already_loaded'):dep.load_runtime(self.root)
    def test_pyc_is_ignored_and_loaded_origins_are_checked(self):
        poison=self.root/'poison.py';poison.write_text('raise RuntimeError("poison pyc")\n')
        cache=Path(importlib.util.cache_from_source(str(self.package/'__init__.py')));cache.parent.mkdir(parents=True,exist_ok=True)
        py_compile.compile(str(poison),cfile=str(cache),doraise=True)
        runtime=dep.load_runtime(self.root)
        self.assertEqual(sys.modules[dep.PACKAGE].MARKER,'checked source')
        self.assertEqual(runtime.evidence()['verified_file_count'],4)
        self.assertEqual(runtime.evidence()['loader'],'checked_source_bytes_no_pyc')
        self.assertIs(dep.load_runtime(self.root),runtime)
        runtime.audio_timeline.__file__=str(self.root.parent/'unexpected.py')
        with self.assertRaisesRegex(ValueError,'import_origin_drift'):runtime.verify()
    def test_runtime_source_drift_after_binding_is_rejected(self):
        runtime=dep.load_runtime(self.root)
        (self.package/'contract_io.py').write_text('pass\n')
        with self.assertRaisesRegex(ValueError,'implementation_drift'):runtime.verify()
    def test_missing_external_executable_has_actionable_error(self):
        with patch.object(dep.shutil,'which',return_value=None):
            with self.assertRaisesRegex(ValueError,'runtime_executable_missing: ffmpeg'):dep.load_runtime(self.root)
    def test_missing_python_dependency_is_not_source_version_error(self):
        (self.package/'__init__.py').write_text('import definitely_missing_video_test_dependency\n');self.freeze()
        with self.assertRaisesRegex(ValueError,'runtime_unavailable.*definitely_missing'):dep.load_runtime(self.root)
    def test_missing_lock_file_is_reported_not_ignored(self):
        with patch.object(dep,'LOCK',self.root/'absent-lock.json'):
            with self.assertRaisesRegex(ValueError,'video_dependency_lock_missing_or_invalid'):dep.load_runtime(self.root)
    def test_incompatible_lock_schema_is_rejected(self):
        self.spec['schema_version']='other-lock.v9';self.lock.write_text(json.dumps(self.spec))
        with self.assertRaisesRegex(ValueError,'video_dependency_lock_incompatible'):dep.load_runtime(self.root)
    def test_lock_path_can_be_configured_without_patching_the_module(self):
        with patch.object(dep,'LOCK',self.root/'absent-lock.json'):
            with patch.dict(os.environ,{dep.LOCK_ENV:str(self.lock)}):
                self.assertEqual(dep.resolve_lock_path(),self.lock.resolve())
                runtime=dep.load_runtime(self.root)
                self.assertEqual(runtime.evidence()['verified_file_count'],4)
    def test_inventory_ignores_pycache_and_unsupported_suffixes(self):
        cache=self.package/'__pycache__';cache.mkdir()
        (cache/'poison.txt').write_text('must not be inventoried')
        (self.package/'notes.md').write_text('not a runtime source suffix')
        self.freeze()
        self.assertEqual(len(dep.inventory(self.root)),4)
        runtime=dep.load_runtime(self.root)
        self.assertEqual(runtime.evidence()['verified_file_count'],4)


if __name__=='__main__':unittest.main(verbosity=2)
