from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import unittest
import tempfile
import os
from pathlib import Path

from contextlib import contextmanager

@contextmanager
def isolated_test_directory(prefix):
    with tempfile.TemporaryDirectory(prefix=prefix) as directory:
        yield Path(directory)



ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
MODULE_PATH = ROOT / "scripts" / "wechat_article_format_adapter.py"
SOURCE = Path(os.environ.get("RYAN_WECHAT_PUBLISHER_SOURCE", str(WORKSPACE / "external/ryan-wechat-publisher")))
BASE_ITEM = ROOT / "fixtures" / "wechat-article-format-v1" / "content-item.synthetic.json"
ARTICLE = ROOT / "fixtures" / "wechat-article-format-v1" / "article.md"
CHECKED_AT = "2026-08-21T12:00:00+08:00"

spec = importlib.util.spec_from_file_location("wechat_adapter", MODULE_PATH)
adapter = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(adapter)


def synthetic_item(markdown_path: Path) -> dict:
    item = json.loads(BASE_ITEM.read_text(encoding="utf-8"))
    body = markdown_path.read_text(encoding="utf-8").strip()
    item["content_id"] = "synthetic-wechat-format-fixture-20260821"
    item["title"] = "合成公众号排版测试"
    item["status"] = "publish-ready"
    item["tags"] = [*item["tags"], "synthetic-only"]
    item["composition"]["canonical_body"] = body
    item["channels"]["wechat_article"].update(
        {"status": "ready", "title": item["title"], "body_ref": str(markdown_path)}
    )
    for gate in item["gates"].values():
        gate.update({"status": "pass", "reviewed_by": "synthetic-reviewer", "reviewed_at": CHECKED_AT})
    item["qa"]["human_review"].update(
        {"status": "approved", "reviewer": "synthetic-reviewer", "reviewed_at": CHECKED_AT}
    )
    item["publication"] = {"boundary": "manual-only", "receipts": []}
    return item


class WechatArticleFormatAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = isolated_test_directory("wechat-format")
        self.root = self.temp.__enter__()
        self.markdown = self.root / "article.md"
        self.markdown.write_text(ARTICLE.read_text(encoding="utf-8"), encoding="utf-8")
        self.item_path = self.root / "content-item.json"
        self.item = synthetic_item(self.markdown)
        self._write_item()

    def tearDown(self) -> None:
        self.temp.__exit__(None, None, None)

    def _write_item(self) -> None:
        self.item_path.write_text(json.dumps(self.item, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def _run(self, output_name: str = "out", extra: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "render",
                "--item", str(self.item_path),
                "--markdown", str(self.markdown),
                "--source-root", str(SOURCE),
                "--output-dir", str(self.root / output_name),
                "--checked-at", CHECKED_AT,
                *extra,
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )

    @unittest.skipUnless(SOURCE.is_dir(), "Pinned external formatter checkout not supplied; actual render unverified")
    def test_render_is_manual_only_and_idempotent(self) -> None:
        first = self._run("first")
        second = self._run("second")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        for name in ("body", "preview", "dark-preview"):
            left = (self.root / "first" / f"render-receipt-{name}.json").read_bytes()
            right = (self.root / "second" / f"render-receipt-{name}.json").read_bytes()
            self.assertEqual(left, right)
        manifest = json.loads((self.root / "first" / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["publication_boundary"], "manual-only")
        self.assertFalse(manifest["remote_actions_performed"])

    def test_requires_synthetic_tag(self) -> None:
        self.item["tags"].remove("synthetic-only")
        self._write_item()
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("synthetic_only_required", result.stdout)

    def test_blocks_gate_and_human_review(self) -> None:
        for mutate, message in (
            (lambda item: item["gates"]["fact"].update({"status": "needs-review"}), "gate_not_pass:fact"),
            (lambda item: item["qa"]["human_review"].update({"status": "required"}), "human_review_not_approved"),
        ):
            candidate = copy.deepcopy(self.item)
            mutate(candidate)
            self.item_path.write_text(json.dumps(candidate, ensure_ascii=False), encoding="utf-8")
            result = self._run()
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stdout)

    def test_blocks_body_drift_and_remote_images(self) -> None:
        self.markdown.write_text(self.markdown.read_text(encoding="utf-8") + "\n新增事实。", encoding="utf-8")
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("canonical_body_drift", result.stdout)
        self.markdown.write_text(self.item["composition"]["canonical_body"] + "\n\n![x](https://example.com/x.png)", encoding="utf-8")
        self.item["composition"]["canonical_body"] = self.markdown.read_text(encoding="utf-8").strip()
        self._write_item()
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("remote_or_data_image_not_allowed", result.stdout)

    def test_blocks_unapproved_source_commit(self) -> None:
        args = adapter.build_parser().parse_args(
            [
                "render", "--item", str(self.item_path), "--markdown", str(self.markdown),
                "--source-root", str(SOURCE), "--output-dir", str(self.root / "out"),
                "--checked-at", CHECKED_AT, "--expected-source-commit", "0" * 40,
            ]
        )
        with self.assertRaisesRegex(adapter.AdapterBlocked, "expected_source_commit_not_approved"):
            adapter.render(args)

    def test_blocks_arbitrary_preset_and_image_path_escape(self) -> None:
        args = adapter.build_parser().parse_args(
            [
                "render", "--item", str(self.item_path), "--markdown", str(self.markdown),
                "--source-root", str(SOURCE), "--output-dir", str(self.root / "out"),
                "--checked-at", CHECKED_AT, "--preset", str(self.root / "arbitrary.js"),
            ]
        )
        with self.assertRaisesRegex(adapter.AdapterBlocked, "preset_not_allowlisted"):
            adapter.render(args)

        self.markdown.write_text(self.item["composition"]["canonical_body"] + "\n\n![x](../outside.png)", encoding="utf-8")
        self.item["composition"]["canonical_body"] = self.markdown.read_text(encoding="utf-8").strip()
        self._write_item()
        result = self._run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("image_path_escape_not_allowed", result.stdout)

    def test_no_upload_clone_or_publish_action(self) -> None:
        parser = adapter.build_parser()
        for action in ("upload", "clone", "publish"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parser.parse_args([action])

    def _public_item(self, tail: str = "") -> tuple[str, ...]:
        body = '# 公开材料待审稿\n\n**保留原文**，不代填确认。\n\n## 来源\n\n[Git 文档](https://git-scm.com/docs/git-push)\n' + tail
        self.markdown.write_text(body, encoding="utf-8")
        self.item = synthetic_item(self.markdown)
        self.item.update({"title": "公开材料待审稿", "status": "review", "tags": ["public-material-review"]})
        self.item["composition"]["canonical_body"] = body.strip()
        self.item["channels"]["wechat_article"].update({"title": self.item["title"], "status": "review"})
        for gate in ("fact", "rights", "compliance"):
            self.item["gates"][gate]["status"] = "needs-review"
        self.item["qa"]["human_review"] = {"status": "required"}
        self._write_item()
        return ("--mode", "public-review", "--markdown-sha256", adapter._sha256(self.markdown))

    @unittest.skipUnless(SOURCE.is_dir(), "Pinned external formatter checkout not supplied; actual render unverified")
    def test_public_review_keeps_pending_state_links_and_source(self) -> None:
        extra = self._public_item()
        before = (self.markdown.read_bytes(), self.item_path.read_bytes())
        result = self._run(extra=extra)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, (self.markdown.read_bytes(), self.item_path.read_bytes()))
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["author_review"], "required")
        self.assertEqual(manifest["content_gates"]["fact"], "needs-review")
        self.assertFalse(manifest["publication_authorized"])
        self.assertEqual(manifest["mode"], "public-review-candidate-only")
        body = (self.root / "out/wechat-article-body.html").read_text(encoding="utf-8")
        preview = (self.root / "out/wechat-article-preview.html").read_text(encoding="utf-8")
        self.assertNotIn("<h1", body)
        self.assertIn('<h1', preview)
        self.assertIn('href="https://git-scm.com/docs/git-push"', body)
        self.assertIn('（https://git-scm.com/docs/git-push）', body)
        self.assertIn('Content-Security-Policy', preview)
        self.assertNotIn("○●", preview)
        receipt = json.loads((self.root / "out/render-receipt-body.json").read_text(encoding="utf-8"))
        self.assertFalse(receipt["policy"]["rights_verified"])
        self.assertEqual(receipt["qa"]["needs_review_count"], 3)
        self.assertNotIn("human-review-approved", [c["name"] for c in receipt["qa"]["hard_checks"]])

    def test_public_review_hash_required_and_drift_rejected(self) -> None:
        self._public_item()
        for extra in (("--mode", "public-review"), ("--mode", "public-review", "--markdown-sha256", "0" * 64)):
            result = self._run(extra=extra)
            self.assertEqual(result.returncode, 2)
            self.assertIn("sha256_required_or_drifted", result.stdout)
            self.assertFalse((self.root / "out").exists())

    def test_public_review_does_not_overwrite_outputs(self) -> None:
        extra = self._public_item()
        (self.root / "out").mkdir()
        sentinel = self.root / "out/old.txt"
        sentinel.write_text("keep", encoding="utf-8")
        result = self._run(extra=extra)
        self.assertEqual(result.returncode, 2)
        self.assertIn("output_must_be_new", result.stdout)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "keep")

    def test_public_review_refuses_undeclared_private_or_blocked_material(self) -> None:
        for mutate, error in (
            (lambda item: item.update(tags=[]), "public_material_declaration_required"),
            (lambda item: item["gates"]["privacy"].update(status="needs-review"), "public_review_privacy_not_pass"),
            (lambda item: item["gates"]["rights"].update(status="blocked"), "blocked_gate_cannot_preview"),
            (lambda item: item.update(status="publish-ready"), "review_draft_required"),
            (lambda item: item["qa"]["human_review"].update(status="blocked"), "blocked_human_review"),
        ):
            with self.subTest(error=error):
                extra = self._public_item()
                mutate(self.item)
                self._write_item()
                result = self._run(extra=extra)
                self.assertEqual(result.returncode, 2)
                self.assertIn(error, result.stdout)

    def test_public_review_rejects_active_html_and_media(self) -> None:
        for tail in ('\n<script>alert(1)</script>', '\n<iframe src="https://example.org"></iframe>',
                     '\n<img src="https://example.org/a.png">', '\n![x](https://example.org/a.png)',
                     '\n![[secret.png]]'):
            with self.subTest(tail=tail):
                extra = self._public_item(tail)
                result = self._run(extra=extra)
                self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                self.assertFalse((self.root / "out").exists())

    def test_public_review_wrong_title_and_file_link_rejected(self) -> None:
        extra = self._public_item('\n[private](/private/file.txt)')
        result = self._run(extra=extra)
        self.assertIn("link_not_public_http", result.stdout)
        extra = self._public_item()
        self.item["title"] = "wrong title"
        self._write_item()
        result = self._run(extra=extra)
        self.assertIn("title_must_match_first_h1", result.stdout)


if __name__ == "__main__":
    unittest.main()
