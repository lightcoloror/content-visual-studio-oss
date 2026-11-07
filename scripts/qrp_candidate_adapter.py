"""Hash-bound, offline QRP candidate projection; no rendering or execution.

Reuses research_output_adapter's explicit unverified-draft validator and builder.
The pack hash must come from the caller's reviewed handoff, never from this tool.
"""
from __future__ import annotations
from studio_paths import STUDIO_ROOT, HUMAN_VOICE_ROOT, research_schema_path

import argparse
import copy
import hashlib
import json
from pathlib import Path

import research_output_adapter as adapter

VERSION = "1.0.0"
STAGES = ("intake", "source_admission", "evidence_analysis", "guarded_synthesis", "article_brief")


def require(condition, code):
    if not condition:
        raise adapter.AdapterError(code, code)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound_object(root, relative, expected, *, canonical_payload=False):
    path = (root / relative).resolve()
    require(path.is_relative_to(root) and path != root, "input_path_escape")
    require(path.is_file(), "input_or_receipt_missing")
    value = adapter.load_json(path)
    observed = adapter.sha256_value(value) if canonical_payload else digest(path)
    require(observed == expected, "input_or_receipt_hash_drift")
    return value


def convert_pack(pack_path: Path, expected_pack_sha256: str, *, allow_unverified_draft=False):
    """Pure conversion. All checks finish before any output is written."""
    require(allow_unverified_draft is True, "candidate_opt_in_required")
    pack_path = pack_path.resolve()
    root = pack_path.parent
    require(digest(pack_path) == expected_pack_sha256, "pack_hash_drift")
    pack = adapter.load_json(pack_path)
    require(pack.get("schema") == "question-research-offline-evidence-brief.v1"
            and pack.get("schema_version") == "1.0.0", "pack_version_unsupported")
    require(pack.get("artifact_state") == "candidate_only" and pack.get("review_required") is True
            and pack.get("finalization_authorized") is False, "authority_escalation")
    binding = {k: pack[k] for k in ("closure_run_id", "input_sha256")}
    require(all(isinstance(v, str) and v for v in binding.values()), "missing_binding")
    core = bound_object(root, pack["core"]["manifest_path"], pack["core"]["manifest_sha256"])
    require(core.get("schema") == "question-research-bounded-deep-loop.v1"
            and core.get("schema_version") == "1.0.0", "core_version_unsupported")
    require(all(core.get(k) == v for k, v in binding.items()), "closure_binding_drift")
    require(core.get("execution_status") == "complete", "core_incomplete")
    rows = core["stage_receipts"]
    require(rows == pack["core"]["stage_receipts"] and [x["stage_id"] for x in rows] == list(STAGES),
            "stage_chain_mismatch")
    previous = None
    stages = {}
    for index, row in enumerate(rows, 1):
        # QRP stage receipts bind canonical JSON; projection/artifact rows bind bytes.
        receipt = bound_object(root, row["path"], row["receipt_sha256"], canonical_payload=True)
        require(receipt.get("schema") == "question-research-bounded-deep-loop-stage-receipt.v1"
                and receipt.get("contract_version") == "1.0.0", "receipt_version_unsupported")
        require(all(receipt.get(k) == v for k, v in binding.items())
                and receipt.get("stage_index") == index and receipt.get("stage_id") == row["stage_id"]
                and receipt.get("previous_receipt_sha256") == previous, "receipt_binding_drift")
        expected_state = {"guarded_synthesis": "candidate_for_human_review", "article_brief": "pending_human_review"}.get(row["stage_id"], "candidate_only")
        require(receipt.get("execution_status") == "complete" and receipt.get("research_state") == expected_state,
                "stage_not_candidate")
        require(all(receipt.get(k) is False for k in ("network_called", "provider_called", "external_write_performed")),
                "non_offline_receipt")
        require(receipt["artifact"] == {"path": row["artifact_path"], "sha256": row["artifact_sha256"]},
                "artifact_binding_drift")
        stages[row["stage_id"]] = bound_object(root, row["artifact_path"], row["artifact_sha256"])
        previous = row["receipt_sha256"]
    projection = pack["projection_receipt"]
    receipt = bound_object(root, projection["path"], projection["sha256"])
    require(receipt.get("schema") == "question-research-offline-projection-receipt.v1"
            and receipt.get("schema_version") == "1.0.0", "projection_version_unsupported")
    require(all(receipt.get(k) == v for k, v in binding.items())
            and receipt.get("core_manifest_sha256") == pack["core"]["manifest_sha256"]
            and receipt.get("core_receipt_chain_sha256") == adapter.sha256_value(rows), "projection_binding_drift")
    require(receipt.get("status") == "candidate_only" and all(receipt.get(k) is False for k in
            ("network_called", "provider_called", "external_write_performed")), "authority_escalation")
    require(receipt["artifacts"] == pack["deliverables"], "deliverable_binding_drift")
    payloads = {row["name"]: bound_object(root, row["path"], row["sha256"]) for row in pack["deliverables"]}
    require(len(payloads) == len(pack["deliverables"]) == 6, "deliverable_set_mismatch")
    brief = payloads["content-brief.v1.json"]
    research = payloads["evidence-bundle.v1.json"]
    review = payloads["review-packet.v1.json"]
    require(brief.get("schema_version") == "content-brief.v1"
            and brief.get("native_contract") == "question-research-article-brief-candidate.v1"
            and brief.get("variant") == "article", "brief_version_unsupported")
    require(brief.get("status") == "candidate_only" and brief.get("mode") == "draft_only"
            and brief.get("authority") == {"execution_authorized": False, "publish_authorized": False,
                                          "external_write_authorized": False}, "authority_escalation")
    require(all(brief.get(k) == review.get(k) == v for k, v in binding.items()), "closure_binding_drift")
    require(review.get("status") == "pending_human_review" and review.get("evidence_status") == "candidate"
            and all(v is False for v in review["authority"].values()), "review_escalation")
    native = stages["article_brief"]
    require(native.get("schema_version") == "1.0.0", "native_version_unsupported")
    for key in ("title", "audience", "angle", "sections", "contradictions", "unknowns", "search_stop_reason", "authority"):
        require(brief[key] == native[key], "brief_projection_drift")
    require(brief["review_gate"] == native["review_packet"] and brief["review_gate"]["human_confirmation_required"] is True
            and brief["review_gate"]["status"] == "pending_human_review", "review_escalation")
    require(brief["title"] == research["question"] and brief["audience"] == research["audience"], "research_identity_drift")
    require(any(x.get("sha256") == binding["input_sha256"] for x in research["provenance"]["input_files"]),
            "research_input_binding_drift")
    require(research["provenance"]["offline_only"] is True and research["provenance"]["external_api_called"] is False,
            "non_offline_research")
    adapter.validate_instance(research, adapter.load_json(adapter.discover_upstream_schema()), "research-output.v1")
    policy = adapter.validate_unverified_draft_semantics(research)
    claims = {x["claim_id"]: x for x in research["claims"]}
    evidence = {x["evidence_id"]: x for x in research["evidence"]}
    require(bool(brief["sections"]), "brief_without_evidence")
    for section in brief["sections"]:
        claim = claims.get(section["claim_id"])
        require(claim is not None and section["heading"] == claim["text"], "section_claim_drift")
        require(bool(section["evidence_ids"]) and bool(section["source_ids"]), "section_without_evidence")
        for eid in section["evidence_ids"]:
            ev = evidence.get(eid)
            require(ev is not None and ev["claim_id"] == section["claim_id"] and ev["source_id"] in section["source_ids"]
                    and ev["relation"] == "supports" and ev["ai_synthesis"] is False, "section_evidence_mismatch")
    # Reuse the existing candidate builder; do not invent verified facts or an answer.
    policy = copy.deepcopy(policy)
    policy["verified_claims"] = []
    policy["selected_claims"] = [claims[x["claim_id"]] for x in brief["sections"]]
    sections = adapter.build_sections(research, policy)
    body = adapter.render_article_markdown(research, sections, brief["angle"], policy)
    body += "\n## Unresolved contradictions (human review required)\n" + json.dumps(brief["contradictions"], ensure_ascii=False) + "\n"
    cid = "qrp-candidate-" + adapter.stable_suffix(expected_pack_sha256, VERSION, length=24)
    item = adapter.build_content_item(research, policy, sections, cid, "article.md", "", brief["angle"], body)
    item["status"] = "candidate"
    item["channels"]["article"]["status"] = "draft"
    # Source admission/review in a synthetic pack is not real-world verification.
    # The complete original states remain in research_status_snapshot.
    for source in item["provenance"]["sources"]:
        source["evidence_status"] = "unverified"
        source["note"] += "; candidate projection only; original review state preserved in metadata"
    item["visual"]["render_recipe"] = {"renderer": "none", "output_format": "none", "output_refs": []}
    item["gates"]["rights"]["reason"] = "Candidate transformation only; citation, rights and publication review remain pending."
    metadata = item["channels"]["article"]["platform_metadata"]
    metadata["qrp_candidate_binding"] = {**binding, "pack_sha256": expected_pack_sha256,
        "evidence_bundle_payload_sha256": adapter.sha256_value(research), "brief": brief, "review_packet": review}
    adapter.validate_instance(item, adapter.load_json(adapter.DEFAULT_CONTENT_SCHEMA), "content-item.v0.2")
    manifest = {"schema_version": "content-qrp-candidate-conversion.v1", "adapter_version": VERSION,
        **binding, "input_pack_sha256": expected_pack_sha256, "status": "candidate_only", "mode": "draft_only",
        "human_review_required": True, "publication_authorized": False, "render_performed": False,
        "provider_called": False, "content_schema_payload_sha256": adapter.sha256_value(adapter.load_json(adapter.DEFAULT_CONTENT_SCHEMA)),
        "source_receipts": rows, "projection_receipt": projection}
    return item, body, manifest


def write_conversion(pack_path, expected_pack_sha256, output_dir, *, allow_unverified_draft=False):
    item, body, manifest = convert_pack(Path(pack_path), expected_pack_sha256, allow_unverified_draft=allow_unverified_draft)
    texts = {"content-item.json": adapter._json_text(item), "article.md": body}
    manifest["artifacts"] = [{"path": name, "sha256": hashlib.sha256(text.encode()).hexdigest()}
                             for name, text in sorted(texts.items())]
    texts["conversion-manifest.json"] = adapter._json_text(manifest)
    root = Path(output_dir).resolve()
    # Precheck all existing outputs before writing anything. Partial identical output resumes.
    for name, text in texts.items():
        p = root / name
        require(not p.exists() or (p.is_file() and p.read_bytes() == text.encode()), "output_hash_drift")
    root.mkdir(parents=True, exist_ok=True)
    for name, text in texts.items():
        p = root / name
        if not p.exists():
            with p.open("xb") as handle:
                handle.write(text.encode())
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", type=Path, required=True)
    parser.add_argument("--expected-pack-sha256", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--allow-unverified-draft", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = write_conversion(args.pack, args.expected_pack_sha256, args.output_dir,
                                  allow_unverified_draft=args.allow_unverified_draft)
        print(json.dumps(result, ensure_ascii=True))
    except (adapter.AdapterError, KeyError, TypeError, ValueError, OSError) as exc:
        print(json.dumps({"status": "blocked", "code": getattr(exc, "code", "invalid_input"), "detail": str(exc)}))
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
