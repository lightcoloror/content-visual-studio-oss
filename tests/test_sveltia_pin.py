import base64
import hashlib
import importlib.util
import json
import os
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = Path(os.environ["CONTENT_STUDIO_SVELTIA_RUNTIME_PATH"])
VALIDATOR_PATH = ROOT / "scripts" / "validate_sveltia_config.py"
validator_spec = importlib.util.spec_from_file_location("validate_sveltia_config", VALIDATOR_PATH)
sveltia_validator = importlib.util.module_from_spec(validator_spec)
assert validator_spec.loader is not None
validator_spec.loader.exec_module(sveltia_validator)


class ScriptParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))


class SveltiaPinTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))

    def test_admin_uses_exact_version_and_sri(self) -> None:
        parser = ScriptParser()
        parser.feed((ROOT / "admin" / "index.html").read_text(encoding="utf-8"))
        self.assertEqual(1, len(parser.scripts))
        script = parser.scripts[0]
        self.assertEqual(self.runtime["cdn_url"], script["src"])
        self.assertEqual(self.runtime["sri"], script["integrity"])
        self.assertEqual("anonymous", script["crossorigin"])

    def test_sri_matches_verified_npm_bundle(self) -> None:
        bundle = Path(os.environ["CONTENT_STUDIO_SVELTIA_BUNDLE_PATH"])
        self.assertTrue(bundle.exists(), "pinned Sveltia review bundle is missing")
        content = bundle.read_bytes()
        sha256 = hashlib.sha256(content).hexdigest()
        sri = "sha384-" + base64.b64encode(hashlib.sha384(content).digest()).decode("ascii")
        self.assertEqual(self.runtime["bundle_sha256"], sha256)
        self.assertEqual(self.runtime["sri"], sri)

    def test_config_schema_is_version_pinned_and_locally_valid(self) -> None:
        config_path = ROOT / "admin" / "config.yml"
        first_line = config_path.read_text(encoding="utf-8").splitlines()[0]
        self.assertIn(self.runtime["schema_url"], first_line)
        self.assertEqual([], sveltia_validator.validate_config())

    def test_directory_authorization_is_manual_but_post_auth_save_is_automatable(self) -> None:
        boundary = self.runtime["local_workflow_boundary"]
        self.assertEqual("visible-user-action-required", boundary["directory_authorization"])
        self.assertFalse(boundary["automatic_folder_picker"])
        self.assertEqual("browser-automation-allowed", boundary["post_authorization_editing"])
        self.assertEqual("browser-native-click-allowed", boundary["save"])
        self.assertEqual(
            "collection-list-returned-and-disk-diff-observed",
            boundary["save_completion_signal"],
        )
        self.assertEqual("automatic-read-only-validation", boundary["git_diff"])
        self.assertFalse(boundary["automatic_publication"])


if __name__ == "__main__":
    unittest.main()
