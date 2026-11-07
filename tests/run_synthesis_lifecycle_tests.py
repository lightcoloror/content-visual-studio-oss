"""Serial, isolated runner for the synthesis/lifecycle candidate tests.

It copies this candidate to a throw-away runtime root, points the explicit
public-owner and Artifact-Core roots at the supplied public inputs, runs the
targeted unittest modules one at a time and records each command, environment,
exit code and first failure. It never installs anything, never touches the
candidate source tree being reviewed, and never exercises a real output,
service, model or network.

Usage (from the candidate root):
  set CONTENT_STUDIO_PUBLIC_OWNERS_ROOT=<dir with public-qrp, public-main>
  set ARTIFACT_LIFECYCLE_CORE_ROOT=<public-lifecycle root>
  python -B tests/run_synthesis_lifecycle_tests.py --receipt <path.json>

A missing explicit owner root is a blocked result, never an implicit skip that
is reported as success.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

CANDIDATE_ROOT = Path(__file__).resolve().parents[1]
TEST_MODULES = (
    "tests/test_original_synthesis_adapter.py",
    "tests/test_document_render_artifact_lifecycle.py",
    "tests/test_multi_owner_native_integration.py",
)
SKIP_DIRS = {"outputs", "__pycache__", ".git", ".tmp"}


def copy_candidate(destination: Path) -> None:
    def ignore(directory, names):
        ignored = {name for name in names if name in SKIP_DIRS or name.endswith(".pyc")}
        return ignored

    shutil.copytree(CANDIDATE_ROOT, destination, ignore=ignore)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owners-root", type=Path,
                        default=Path(os.environ["CONTENT_STUDIO_PUBLIC_OWNERS_ROOT"])
                        if os.environ.get("CONTENT_STUDIO_PUBLIC_OWNERS_ROOT") else None,
                        help="Explicit directory containing public-qrp/ and public-main/.")
    parser.add_argument("--core-root", type=Path,
                        default=Path(os.environ["ARTIFACT_LIFECYCLE_CORE_ROOT"])
                        if os.environ.get("ARTIFACT_LIFECYCLE_CORE_ROOT") else None,
                        help="Explicit public artifact-lifecycle-core root.")
    parser.add_argument("--run-root", type=Path,
                        help="Explicit runtime root; defaults under the candidate outputs test root.")
    parser.add_argument("--receipt", type=Path, help="Where to write the JSON test receipt.")
    args = parser.parse_args(argv)
    if not args.owners_root or not args.owners_root.is_dir():
        print(json.dumps({"status": "blocked", "code": "public_owners_root_required",
                          "detail": "CONTENT_STUDIO_PUBLIC_OWNERS_ROOT must point at the public owner inputs"}))
        return 2
    owners = args.owners_root.expanduser().resolve()
    core = args.core_root.expanduser().resolve() if args.core_root else owners / "public-lifecycle"
    if not (core / "artifact_lifecycle_core.py").is_file():
        print(json.dumps({"status": "blocked", "code": "artifact_core_root_required",
                          "detail": str(core)}))
        return 2

    run_root = (args.run_root.expanduser().resolve() if args.run_root
                else CANDIDATE_ROOT / "outputs" / ".test-runtime" / f"runner-{os.getpid()}-{uuid.uuid4().hex[:8]}")
    run_root.mkdir(parents=True, exist_ok=False)
    copy_root = run_root / "candidate"
    copy_candidate(copy_root)
    temp_root = run_root / "tmp"
    temp_root.mkdir()
    test_temp = copy_root / "outputs" / ".test-runtime" / "temp"
    environment = dict(os.environ)
    environment.update({
        "PYTHONDONTWRITEBYTECODE": "1",
        "TEMP": str(temp_root),
        "TMP": str(temp_root),
        "TMPDIR": str(temp_root),
        "CONTENT_STUDIO_TEST_TEMP_ROOT": str(test_temp),
        "CONTENT_STUDIO_PUBLIC_OWNERS_ROOT": str(owners),
        "ARTIFACT_LIFECYCLE_CORE_ROOT": str(core),
    })
    environment.pop("CONTENT_STUDIO_HUMAN_VOICE_ROOT", None)

    results = []
    started = time.time()
    for module in TEST_MODULES:
        command = [sys.executable, "-B", module]
        process = subprocess.run(command, cwd=copy_root, env=environment,
                                 capture_output=True, text=True, encoding="utf-8", errors="replace")
        log_path = run_root / (Path(module).stem + ".log")
        log_path.write_text((process.stdout or "") + (process.stderr or ""), encoding="utf-8")
        first_failure = ""
        for line in (process.stdout + "\n" + process.stderr).splitlines():
            if line.strip().startswith(("FAIL:", "ERROR:")):
                first_failure = line.strip()
                break
        results.append({
            "module": module,
            "argv": command,
            "exit_code": process.returncode,
            "first_failure": first_failure,
            "log": str(log_path),
            "skipped": "skipped" in (process.stderr or "").casefold() or "skipped" in (process.stdout or "").casefold(),
        })
    receipt = {
        "schema_version": "content-studio.synthesis-lifecycle-test-receipt.v1",
        "status": ("failed" if any(row["exit_code"] != 0 for row in results)
                   else "blocked" if any(row["skipped"] for row in results) else "passed"),
        "run_root": str(run_root),
        "copy_root": str(copy_root),
        "owners_root": str(owners),
        "core_root": str(core),
        "python": sys.executable,
        "python_version": sys.version,
        "environment": {key: environment[key] for key in
                        ("PYTHONDONTWRITEBYTECODE", "TEMP", "TMP", "TMPDIR",
                         "CONTENT_STUDIO_TEST_TEMP_ROOT", "CONTENT_STUDIO_PUBLIC_OWNERS_ROOT",
                         "ARTIFACT_LIFECYCLE_CORE_ROOT")},
        "serial": True,
        "started_at_local": time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started)),
        "duration_seconds": round(time.time() - started, 3),
        "results": results,
        "notes": [
            "Unit mocks are never reported as native owner integration.",
            "A skipped owner test is not a pass; the receipt keeps the explicit skip reason in the log.",
            "No wheel build, install, network, model, media, browser or real output is used.",
        ],
    }
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "run_root": str(run_root),
                      "receipt": str(args.receipt) if args.receipt else None,
                      "results": [{k: row[k] for k in ("module", "exit_code", "first_failure", "skipped")}
                                  for row in results]}, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
