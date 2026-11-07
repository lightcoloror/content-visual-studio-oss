#!/usr/bin/env python3
"""Targeted synthetic-only unit test: social_card_runtime.py.

Negative cases for env/path/hash/HTML-source guards plus one normal synthetic
input. No service, browser, rendering or network access.
"""
from __future__ import annotations

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKSPACE = Path(os.environ.get("CANDIDATE_TEST_WORKSPACE", str(ROOT.parent / "synthetic")))
sys.path.insert(0, str(SCRIPTS))

import social_card_runtime as runtime  # noqa: E402

ENV_NAME = "CANDIDATE_TEST_SOCIAL_CARD_HTML"

SAFE_HTML = """<!doctype html>
<html lang="zh" data-design-direction="editorial">
<head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body><section class="poster board"><h1>Synthetic card</h1></section></body>
</html>
"""


def html(head: str, body: str, direction: str = "editorial", viewport: bool = True) -> str:
    meta = '<meta name="viewport" content="width=device-width">' if viewport else ""
    return f'<!doctype html><html data-design-direction="{direction}"><head>{meta}{head}</head><body>{body}</body></html>'


class SocialCardRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        WORKSPACE.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=str(WORKSPACE), prefix="socialcard-")
        self.dir = Path(self.temp.name)
        self.approved = self.dir / "approved"
        self.outside = self.dir / "outside"
        self.approved.mkdir()
        (self.approved / "nested").mkdir()
        self.outside.mkdir()
        self.card = self.approved / "card.html"
        self.card.write_text(SAFE_HTML, encoding="utf-8")
        self.digest = hashlib.sha256(self.card.read_bytes()).hexdigest()
        self.outside_card = self.outside / "outside.html"
        self.outside_card.write_text(SAFE_HTML, encoding="utf-8")
        os.environ.pop(ENV_NAME, None)
        self.addCleanup(self.clean)

    def clean(self) -> None:
        os.environ.pop(ENV_NAME, None)
        self.temp.cleanup()

    # --- env / path / hash guards ---

    def test_missing_env_name_contract_is_rejected(self) -> None:
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "environment-variable contract"):
            runtime.resolve_external_file_from_env(None, "synthetic card")

    def test_unset_env_var_is_rejected(self) -> None:
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "is not configured"):
            runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card")

    def test_missing_file_is_rejected(self) -> None:
        os.environ[ENV_NAME] = str(self.approved / "absent.html")
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "is missing"):
            runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card")

    def test_sha256_drift_is_rejected(self) -> None:
        os.environ[ENV_NAME] = str(self.card)
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "checksum drift"):
            runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card", "0" * 64)

    def test_correct_env_path_and_hash_resolve(self) -> None:
        os.environ[ENV_NAME] = str(self.card)
        resolved = runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card", self.digest.upper())
        self.assertEqual(resolved, self.card.resolve())

    def test_path_escape_outside_allowed_root_is_rejected(self) -> None:
        os.environ[ENV_NAME] = str(self.outside_card)
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "escapes the approved root"):
            runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card", allowed_root=self.approved)

    def test_lexical_parent_traversal_inside_allowed_root_is_accepted(self) -> None:
        os.environ[ENV_NAME] = str(self.approved / "nested" / ".." / "card.html")
        resolved = runtime.resolve_external_file_from_env(
            ENV_NAME, "synthetic card", self.digest, allowed_root=self.approved
        )
        self.assertEqual(resolved, self.card.resolve())

    def test_symlink_escape_outside_allowed_root_is_rejected(self) -> None:
        link = self.approved / "escape.html"
        try:
            os.symlink(str(self.outside_card), str(link))
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlink creation unavailable on this host: {error}")
        os.environ[ENV_NAME] = str(link)
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "escapes the approved root"):
            runtime.resolve_external_file_from_env(ENV_NAME, "synthetic card", allowed_root=self.approved)

    # --- HTML source guards ---

    def test_normal_synthetic_html_is_accepted(self) -> None:
        result = runtime.validate_social_card_html_source(SAFE_HTML, required_direction="editorial")
        self.assertTrue(result["script_free_html"])
        self.assertTrue(result["local_assets_only"])
        self.assertEqual(result["html_design_direction"], "editorial")
        self.assertEqual(result["poster_count"], 1)

    def test_class_list_with_extra_poster_token_is_accepted(self) -> None:
        text = html("", '<section class="board poster extra">ok</section>')
        self.assertEqual(runtime.validate_social_card_html_source(text)["poster_count"], 1)

    def test_script_and_active_document_tags_are_rejected(self) -> None:
        for body in ('<script>alert(1)</script><section class="poster">x</section>',
                     '<iframe src="local.html"></iframe><section class="poster">x</section>',
                     '<object data="local.svg"></object><section class="poster">x</section>'):
            with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "script-free"):
                runtime.validate_social_card_html_source(html("", body))

    def test_inline_event_handler_is_rejected(self) -> None:
        text = html("", '<section class="poster" onload="doThing()">x</section>')
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "event-handler"):
            runtime.validate_social_card_html_source(text)

    def test_remote_asset_references_are_rejected(self) -> None:
        for body in ('<section class="poster"><img src="https://example.invalid/a.png"></section>',
                     '<section class="poster"><a href="//example.invalid/a">x</a></section>',
                     '<section class="poster" style="background:url(//example.invalid/a.png)">x</section>'):
            with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "remote assets"):
                runtime.validate_social_card_html_source(html("", body))

    def test_missing_viewport_is_rejected(self) -> None:
        text = html("", '<section class="poster">x</section>', viewport=False)
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "responsive viewport"):
            runtime.validate_social_card_html_source(text)

    def test_wrong_design_direction_is_rejected(self) -> None:
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "data-design-direction"):
            runtime.validate_social_card_html_source(SAFE_HTML, required_direction="other-theme")

    def test_missing_poster_board_is_rejected(self) -> None:
        with self.assertRaisesRegex(runtime.SocialCardRuntimeError, "section.poster"):
            runtime.validate_social_card_html_source(html("", "<p>no board</p>"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
