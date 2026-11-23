import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

from run_wound_visual_e2e import (  # noqa: E402
    EXPECTED_PROTECTED_CANONICAL_HASHES,
    _assert_protected_bytes_unchanged,
    _assert_protected_content,
    _canonical_json_value_sha256,
)


class WoundAcceptanceProtectionTests(unittest.TestCase):
    def test_committed_protected_content_matches_canonical_contract(self) -> None:
        actual = _assert_protected_content()
        expected = {
            str(path): digest
            for path, digest in EXPECTED_PROTECTED_CANONICAL_HASHES.items()
        }
        self.assertEqual(expected, actual)

    def test_canonical_hash_ignores_json_formatting_and_line_endings(self) -> None:
        payload = {"title": "敷料观察", "signals": ["湿透", "松脱"]}
        compact = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        pretty_crlf = (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").replace(
            "\n", "\r\n"
        )
        self.assertEqual(
            _canonical_json_value_sha256(json.loads(compact)),
            _canonical_json_value_sha256(json.loads(pretty_crlf)),
        )

    def test_runtime_byte_guard_detects_any_in_run_change(self) -> None:
        before = {"protected.json": "before"}
        _assert_protected_bytes_unchanged(before, dict(before))
        with self.assertRaisesRegex(RuntimeError, "protected.json"):
            _assert_protected_bytes_unchanged(
                before,
                {"protected.json": "after"},
            )


if __name__ == "__main__":
    unittest.main()
