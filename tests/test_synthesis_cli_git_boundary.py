"""Host-added source/CLI and real synthetic Git checks; no remotes."""
import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import original_synthesis_adapter as synthesis
import document_render_artifact_lifecycle as lifecycle
from temp_workspace import prepare_test_temp_root


class EntrypointAndGitTests(unittest.TestCase):
    def test_synthesis_console_target_is_callable_and_help_does_not_bind_owners(self):
        with patch.object(synthesis, 'bind_owners', side_effect=AssertionError('not for help')):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                with self.assertRaises(SystemExit) as raised:
                    synthesis.main(['--help'])
        self.assertEqual(raised.exception.code, 0)
        self.assertIn('--workspace-root', output.getvalue())

    def test_git_and_process_probe_exceptions_remain_unknown(self):
        for error in (OSError('synthetic unavailable'), subprocess.TimeoutExpired('synthetic', 10)):
            with self.subTest(error=type(error).__name__):
                with patch.object(lifecycle.subprocess, 'run', side_effect=error):
                    self.assertEqual(lifecycle._workspace_git_state(ROOT), 'unknown')
                    self.assertEqual(lifecycle._process_probe()['state'], 'unknown')

    def test_real_local_synthetic_git_clean_then_dirty(self):
        # Retain synthetic Git evidence: Windows marks object files read-only.
        # This test does not change permissions or recursively delete a repository.
        root = prepare_test_temp_root() / ('git-evidence-' + uuid.uuid4().hex[:8])
        root.mkdir()
        with self.subTest(root=str(root)):
            env = dict(os.environ, GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_CONFIG_COUNT='1', GIT_CONFIG_KEY_0='core.longpaths', GIT_CONFIG_VALUE_0='true',
                       GIT_AUTHOR_NAME='Synthetic Test', GIT_AUTHOR_EMAIL='synthetic@example.invalid',
                       GIT_COMMITTER_NAME='Synthetic Test', GIT_COMMITTER_EMAIL='synthetic@example.invalid')
            def git(*args):
                result = subprocess.run(['git', '-C', str(root), *args], env=env,
                    capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stderr)
            git('init', '-q')
            (root / 'synthetic.txt').write_text('fictional local test only\n', encoding='utf-8')
            git('add', '--', 'synthetic.txt')
            git('-c', 'commit.gpgsign=false', 'commit', '-q', '-m', 'Synthetic test snapshot')
            with patch.dict(os.environ, env):
                self.assertEqual(lifecycle._workspace_git_state(root), 'clean')
                (root / 'synthetic.txt').write_text('changed fictional data\n', encoding='utf-8')
                self.assertEqual(lifecycle._workspace_git_state(root), 'dirty')


if __name__ == '__main__':
    unittest.main()
