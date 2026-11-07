"""Public MVP binding plan: real byte binding of the fixed public-video package.

The static checks in this file are real. The optional loader test only imports the
checked source bytes; it never composes, renders or writes media. Point
CONTENT_STUDIO_PUBLIC_VIDEO_ROOT at an externally supplied copy of the fixed
public source to run the binding checks. Set
CONTENT_STUDIO_PUBLIC_VIDEO_RUNTIME=1 to additionally exercise the checked source
loader (requires ffmpeg/ffprobe on PATH). Neither variable is a fallback: without
them the corresponding checks are explicit skips, never silent passes.
"""
import json
import os
import shutil
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import video_timeline_dependency as dep

PUBLIC_VIDEO_COMMIT = "9f55b12864df642f08fcbd96df15acb0f97652d5"
PUBLIC_VIDEO_ROOT_ENV = "CONTENT_STUDIO_PUBLIC_VIDEO_ROOT"
PUBLIC_VIDEO_RUNTIME_ENV = "CONTENT_STUDIO_PUBLIC_VIDEO_RUNTIME"
REAL_ROOT = (
    Path(os.environ[PUBLIC_VIDEO_ROOT_ENV]).expanduser().resolve()
    if os.environ.get(PUBLIC_VIDEO_ROOT_ENV)
    else None
)


class PublicVideoBindingTests(unittest.TestCase):
    def lock(self):
        path = dep.resolve_lock_path()
        self.assertTrue(path.is_file(), "candidate runtime lock is missing: %s" % path)
        return json.loads(path.read_text(encoding="utf-8"))

    def test_candidate_does_not_vendor_the_video_runtime(self):
        self.assertFalse((ROOT / "src" / "video_creation_pipeline").exists())
        vendors = [
            path for path in ROOT.rglob("*")
            if path.is_dir() and path.name in ("video_creation_pipeline", "mvp-video-pipeline")
        ]
        self.assertEqual(vendors, [])
        self.assertFalse((ROOT / "mvp-video-pipeline").exists())

    def test_lock_is_a_relative_byte_binding_without_private_paths(self):
        lock = self.lock()
        self.assertEqual(lock["schema_version"], "content-video-runtime-lock.v1")
        self.assertEqual(lock["interface"], "audio_timeline.compose/v1")
        self.assertEqual(lock["distribution"], "video-creation-pipeline")
        self.assertEqual(lock["version"], "0.8.1")
        self.assertIn("pyproject.toml", lock["files"])
        self.assertIn("src/video_creation_pipeline/audio_timeline.py", lock["files"])
        for name, digest in lock["files"].items():
            self.assertNotIn("\\", name)
            self.assertNotIn("..", Path(name).parts)
            self.assertFalse(Path(name).is_absolute())
            self.assertEqual(len(digest), 64)
        self.assertEqual(lock["provenance"]["declared_source_commit"], PUBLIC_VIDEO_COMMIT)
        self.assertNotIn("git_head", lock["provenance"])
        for value in lock["provenance"].values():
            if isinstance(value, str):
                self.assertNotIn("\\", value)
        self.assertEqual(lock["provenance"]["file_count"], len(lock["files"]))

    @unittest.skipUnless(REAL_ROOT, "set " + PUBLIC_VIDEO_ROOT_ENV + " to the supplied fixed public-video root")
    def test_real_public_video_bytes_are_bound_by_the_lock(self):
        root = REAL_ROOT
        project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["name"], "video-creation-pipeline")
        self.assertEqual(project["version"], "0.8.1")
        lock = self.lock()
        files = dep.inventory(root)
        self.assertEqual(set(files), set(lock["files"]))
        for name, path in files.items():
            self.assertEqual(dep.digest(path.read_bytes()), lock["files"][name], name)
        self.assertEqual(len(files), lock["provenance"]["file_count"])
        self.assertEqual(lock["provenance"]["declared_source_commit"], PUBLIC_VIDEO_COMMIT)

    @unittest.skipUnless(REAL_ROOT, "set " + PUBLIC_VIDEO_ROOT_ENV + " to the supplied fixed public-video root")
    @unittest.skipUnless(os.environ.get(PUBLIC_VIDEO_RUNTIME_ENV) == "1", "set " + PUBLIC_VIDEO_RUNTIME_ENV + "=1 to import the checked source bytes")
    def test_checked_loader_binds_the_real_runtime_without_rendering(self):
        if not all(shutil.which(name) for name in ("ffmpeg", "ffprobe")):
            self.skipTest("ffmpeg/ffprobe are absent; the checked loader requires the existing executables")
        lock = self.lock()
        runtime = dep.load_runtime(REAL_ROOT)
        try:
            evidence = runtime.evidence()
            self.assertEqual(evidence["distribution"], "video-creation-pipeline")
            self.assertEqual(evidence["version"], "0.8.1")
            self.assertEqual(evidence["verified_file_count"], len(lock["files"]))
            self.assertEqual(evidence["loader"], "checked_source_bytes_no_pyc")
            self.assertEqual(evidence["timeline_implementation_sha256"],
                             lock["files"]["src/video_creation_pipeline/audio_timeline.py"])
            for origin in evidence["imported_module_origins"].values():
                self.assertTrue(Path(origin).is_relative_to(REAL_ROOT), origin)
            self.assertIs(dep.load_runtime(REAL_ROOT), runtime)
        finally:
            for name in list(sys.modules):
                if name == dep.PACKAGE or name.startswith(dep.PACKAGE + "."):
                    sys.modules.pop(name, None)
            dep._active = None
            sys.meta_path[:] = [finder for finder in sys.meta_path if not isinstance(finder, dep._PinnedFinder)]


if __name__ == "__main__":
    unittest.main(verbosity=2)
