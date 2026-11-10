"""Deterministic test driver for candidate precheck_inputs."""
import argparse
import ast
import sys
from pathlib import Path
from typing import Any


def extract_precheck_symbols(candidate_path: Path) -> tuple[Any, Any, Any]:
    text = candidate_path.read_text(encoding="utf-8")
    tree = ast.parse(text, filename=str(candidate_path))
    nodes = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_REQUIRED_SOURCE_KEYS":
                    nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in ("_resolve", "precheck_inputs"):
            nodes.append(node)
    if len(nodes) < 3:
        raise RuntimeError("Failed to extract _REQUIRED_SOURCE_KEYS, _resolve, precheck_inputs")
    mod = ast.Module(body=nodes, type_ignores=[])
    code = compile(mod, filename="<extracted>", mode="exec")
    env: dict[str, Any] = {"Path": Path, "Any": Any}
    exec(code, env)
    return env["_REQUIRED_SOURCE_KEYS"], env["_resolve"], env["precheck_inputs"]


def setup_fixtures(workspace: Path) -> dict[str, Path]:
    base = workspace / "test_driver_fixtures"
    base.mkdir(parents=True, exist_ok=False)
    f: dict[str, Path] = {"base": base}
    for k in ("article", "social-card", "infographic", "pptx", "web"):
        p = base / f"src_{k}.dat"
        with p.open("x", encoding="utf-8") as fp:
            fp.write("ok")
        f[f"src:{k}"] = p
    for k in (
        "ppt_receipt",
        "protected_baseline_manifest",
        "data_visual_spec_schema",
        "runtime_config",
        "normalized_data_fixture",
        "typography_script",
    ):
        p = base / f"{k}.json"
        with p.open("x", encoding="utf-8") as fp:
            fp.write("{}")
        f[k] = p
    pr = base / "prot_root"
    pr.mkdir(exist_ok=False)
    f["protected_root"] = pr
    br = base / "brand_root"
    br.mkdir(exist_ok=False)
    f["brand_root"] = br
    im = base / "input_map.json"
    with im.open("x", encoding="utf-8") as fp:
        fp.write("{}")
    f["input_map"] = im
    return f


def build_input_map(f: dict[str, Path], out: Path) -> dict[str, Any]:
    return {
        "sources": {k: str(f[f"src:{k}"]) for k in ("article", "social-card", "infographic", "pptx", "web")},
        "ppt_receipt": str(f["ppt_receipt"]),
        "protected_baseline_manifest": str(f["protected_baseline_manifest"]),
        "data_visual_spec_schema": str(f["data_visual_spec_schema"]),
        "runtime_config": str(f["runtime_config"]),
        "normalized_data_fixture": str(f["normalized_data_fixture"]),
        "typography_script": str(f["typography_script"]),
        "output_dir": str(out),
        "protected_root": str(f["protected_root"]),
        "personal_brand_root": str(f["brand_root"]),
    }


def run_case_pure_valid(precheck: Any, f: dict[str, Path]) -> None:
    target_out = f["base"] / "pure_valid_out"
    if target_out.exists():
        raise AssertionError(f"Target output directory already exists prior to precheck: {target_out}")
    res = precheck(build_input_map(f, target_out), input_map_path=f["input_map"])
    if target_out.exists():
        raise AssertionError("pure precheck failed: output_dir was created during precheck")
    if not isinstance(res, dict) or "output_dir" not in res:
        raise AssertionError("precheck did not return expected resolved dictionary")
    print("PASS: valid no directory creation")


def run_all_cases(precheck: Any, f: dict[str, Path]) -> None:
    run_case_pure_valid(precheck, f)

    def assert_fails(m: dict[str, Any], label: str, imp: Path, expected: str | None = None, out_check: Path | None = None) -> None:
        failed = False
        try:
            precheck(m, input_map_path=imp)
        except RuntimeError as e:
            failed = True
            if expected and expected not in str(e):
                raise AssertionError(f"Case '{label}': expected '{expected}' in error, got: {e}")
        if not failed:
            raise AssertionError(f"Case '{label}' unexpectedly passed")
        if out_check and out_check.exists():
            raise AssertionError(f"Case '{label}': output path was created on failure")
        print(f"PASS: {label}")

    # 2. missing source no output write
    out2 = f["base"] / "missing_src_out"
    m2 = build_input_map(f, out2)
    m2["sources"]["article"] = str(f["base"] / "missing.dat")
    assert_fails(m2, "missing source no output write", f["input_map"], "source article does not exist", out2)

    # 3. missing scalar
    m3 = build_input_map(f, f["base"] / "missing_scalar_out")
    del m3["ppt_receipt"]
    assert_fails(m3, "missing scalar", f["input_map"], "ppt_receipt is missing")

    # 4. output file
    file_out = f["base"] / "existing_file_out.txt"
    file_out.write_text("file", encoding="utf-8")
    m4 = build_input_map(f, file_out)
    assert_fails(m4, "output file", f["input_map"], "not a directory")

    # 5. output ancestor of file
    m5 = build_input_map(f, f["base"])
    assert_fails(m5, "output ancestor of file", f["input_map"], "must not contain or equal input path")

    # 6. output inside protected_root
    m6 = build_input_map(f, f["protected_root"] / "nested_out")
    assert_fails(m6, "output inside protected_root", f["input_map"], "protected_root")

    # 7. output ancestor protected_root
    sub_prot_parent = f["base"] / "prot_nest"
    sub_prot = sub_prot_parent / "deep_prot"
    sub_prot.mkdir(parents=True, exist_ok=True)
    m7 = build_input_map(f, sub_prot_parent)
    m7["protected_root"] = str(sub_prot)
    assert_fails(m7, "output ancestor protected_root", f["input_map"], "protected_root")

    # 8. output inside brand root
    m8 = build_input_map(f, f["brand_root"] / "nested_out")
    assert_fails(m8, "output inside brand root", f["input_map"], "personal_brand_root")

    # 9. input_map itself in output
    im_nest = f["base"] / "im_nest_dir"
    im_nest.mkdir(parents=True, exist_ok=True)
    im_file = im_nest / "input_map.json"
    im_file.write_text("{}", encoding="utf-8")
    m9 = build_input_map(f, im_nest)
    assert_fails(m9, "input_map itself in output", im_file, "input_map_path")

    # 10. missing/empty keys
    m10 = build_input_map(f, f["base"] / "empty_keys_out")
    m10["sources"]["web"] = "   "
    assert_fails(m10, "missing/empty keys", f["input_map"], "sources.web is missing or empty")


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic precheck test driver")
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--assert-pure-valid", action="store_true")
    args = parser.parse_args()

    _, _, precheck = extract_precheck_symbols(args.candidate.expanduser().resolve())
    fixtures = setup_fixtures(args.workspace.expanduser().resolve())
    if args.assert_pure_valid:
        run_case_pure_valid(precheck, fixtures)
    else:
        run_all_cases(precheck, fixtures)
    return 0


if __name__ == "__main__":
    sys.exit(main())
