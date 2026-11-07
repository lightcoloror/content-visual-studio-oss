"""Compile a hash-pinned editorial plan through existing candidate/fact/HTML gates.

No generation, retrieval, publication or semantic truth classifier. Free editorial
language still needs human review; exact quote verification only verifies strings.
Codex / GPT-6 Astra, 2026-09-12. Public candidate adaptation: 2026-11-07.

The two native owners are resolved through their existing public entry points:
`qrp_owner_binding.bind_qrp` for question-research-poc and the registered
`content-creation-system` tool record for the Main consistency gate. No
`sys.path` entry is guessed from a sibling directory, and a missing or mixed
owner blocks instead of being mocked.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import importlib
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from studio_paths import STUDIO_ROOT

VERSION = "2.1.0"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
FACT_CARD_SCHEMA = STUDIO_ROOT / "schemas/content-fact-card.v0.schema.json"
WORKSPACE_ENV = "CONTENT_STUDIO_SYNTHESIS_WORKSPACE"
CONSUMER_INDEX = "consumer-index.json"


class SynthesisError(ValueError):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def require(ok, code):
    if not ok:
        raise SynthesisError(code)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def aggregate(rows, key):
    values = [row.get(key) for row in rows]
    return values[0] if values and all(v == values[0] for v in values) else "mixed"


def _error_code(exc):
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and code else (str(exc).split(":", 1)[0] or "owner_unavailable")


def resolve_workspace_root(explicit=None):
    """Return the explicit common workspace root; never guess an installed root."""
    value = explicit or os.environ.get(WORKSPACE_ENV)
    if value:
        root = Path(value).expanduser().resolve()
        require(root.is_dir(), "workspace_root_missing")
        return root
    # The source checkout is the historical default. An installed package has no
    # writable project root, so it must pass an explicit workspace.
    if STUDIO_ROOT == PROJECT_ROOT:
        return PROJECT_ROOT.resolve()
    raise SynthesisError("workspace_root_required")


def bind_owners(qrp_root=None, tool_registry=None):
    """Bind the existing QRP and Main owners; mixed/missing owners fail closed.

    Returns `(qrp_candidate_adapter, qrp.bounded_deep_loop, main_gate)`. Nothing is
    imported at module import time so `--help` and a clean missing-owner report work
    without QRP, jsonschema or markdown-it-py installed.
    """
    try:
        from qrp_owner_binding import bind_qrp, default_qrp_root
    except ImportError as exc:
        raise SynthesisError("qrp_owner_binding_unavailable") from exc

    root = Path(qrp_root).expanduser() if qrp_root else default_qrp_root()
    root = root.resolve()
    source = root / "src/question_research_poc"
    require(source.is_dir() and (source / "bounded_deep_loop.py").is_file(), "qrp_source_root_required")
    # The explicit owner root is the only path added; no sibling guess is made.
    source_path = str(root / "src")
    if source_path not in sys.path:
        sys.path.insert(0, source_path)
    try:
        bind_qrp(root)
    except (ValueError, OSError) as exc:
        raise SynthesisError(_error_code(exc)) from exc

    try:
        qrp = importlib.import_module("qrp_candidate_adapter")
    except ImportError as exc:
        raise SynthesisError("qrp_candidate_adapter_unavailable") from exc
    try:
        from registered_self_media import load_module
        gate = (load_module("cross_platform_fact_consistency_gate") if tool_registry is None
                else load_module("cross_platform_fact_consistency_gate", tool_registry))
    except ImportError as exc:
        raise SynthesisError("registered_self_media_unavailable") from exc
    except (ValueError, OSError) as exc:
        raise SynthesisError(_error_code(exc)) from exc
    if "question_research_poc.bounded_deep_loop" not in sys.modules:
        raise SynthesisError("qrp_owner_binding_incomplete")
    return qrp, sys.modules["question_research_poc.bounded_deep_loop"], gate


def reviewed_policy(plan, research, upstream, qrp):
    """Optional separately reviewed native evidence; full capture alone grants nothing."""
    row = plan.get("reviewed_research")
    if row is None:
        return None
    native = qrp.bound_object(upstream, row["path"], row["sha256"])
    qrp.adapter.validate_instance(native, read(qrp.adapter.discover_upstream_schema()), "research-output.v1")
    policy = qrp.adapter.validate_research_semantics(native)
    raw_claims = {c["claim_id"]: c for c in research["claims"]}
    raw_sources = {s["source_id"]: s for s in research["sources"]}
    raw_evidence = {e["evidence_id"]: e for e in research["evidence"]}
    for claim in policy["verified_claims"]:
        require(claim["claim_id"] in raw_claims and claim["text"] == raw_claims[claim["claim_id"]]["text"],
                "reviewed_claim_binding_drift")
    for source in policy["used_sources"]:
        raw = raw_sources.get(source["source_id"], {})
        require(raw.get("capture_content_ok") is True, "source_fact_requires_complete_capture")
        require(source["hash"]["value"] == raw.get("content_sha256")
                and source.get("url") == raw.get("canonical_ref"), "reviewed_source_binding_drift")
    for evidence in policy["used_evidence"]:
        raw = raw_evidence.get(evidence["evidence_id"], {})
        require(evidence.get("excerpt") == raw.get("text")
                and all(evidence.get(k) == raw.get(k) for k in ("claim_id", "source_id", "relation")),
                "reviewed_evidence_binding_drift")
    return policy


def validate_plan(plan, research, evidence_policy=None):
    require(plan.get("schema_version") in {"content-original-editorial-plan.v1", "content-original-editorial-plan.v2"},
            "plan_version")
    require(plan.get("status") == "candidate_only" and plan.get("human_approved") is False,
            "authority_escalation")
    claims = {x["claim_id"]: x for x in research["claims"]}
    evidence = {x["evidence_id"]: x for x in research["evidence"]}
    sources = {x["source_id"]: x for x in research["sources"]}
    required = set(plan["claim_ids"])
    require(required and required <= claims.keys(), "unknown_claim")
    seen, found, quote_words = set(), set(), {}
    for u in plan["units"]:
        require(u["id"] not in seen, "duplicate_unit")
        seen.add(u["id"])
        require(not u.get("platform_sample_refs"), "platform_claim_not_fact_authority")
        require(u.get("assertion_kind") != "case", "case_needs_source")
        if u.get("type") == "source_fact":
            reviewed = {c["claim_id"] for c in (evidence_policy or {}).get("verified_claims", [])}
            require(u.get("claim_id") in reviewed, "source_fact_not_admitted")
        require(u["type"] in {"source_fact", "verified_quote", "author_position", "agent_inference"}, "unknown_type")
        text = u["text"]
        eid = u.get("quote_evidence_id")
        # An admitted quote cannot be relabelled as original reasoning.
        looks_like_quote = any(text and text in e["text"] for e in evidence.values())
        require(not (eid or looks_like_quote) or u["type"] == "verified_quote", "quote_type_drift")
        if u["type"] == "verified_quote":
            require(eid in evidence and text in evidence[eid]["text"], "quote_not_in_admitted_excerpt")
            ev = evidence[eid]
            if plan["schema_version"].endswith(".v2") or "quote_source_id" in u:
                require(u.get("quote_source_id") == ev["source_id"], "quote_source_drift")
            require(ev["claim_id"] in required and ev["relation"] == "supports", "quote_claim_mismatch")
            source = sources[ev["source_id"]]
            require(text in source["content"], "quote_not_in_archive")
            require(u.get("claim_id") is None, "quote_claim_type_drift")
            count = len(text.split()) * sum(u["id"] in plan[k] for k in ("article_order", "oral_order"))
            quote_words[ev["source_id"]] = quote_words.get(ev["source_id"], 0) + count
            require(quote_words[ev["source_id"]] <= 25, "quote_length_limit")
        elif u.get("claim_id"):
            cid = u["claim_id"]
            require(cid in required and text == claims[cid]["text"], "canonical_claim_drift")
            require((u["type"], u["assertion_kind"]) in {("agent_inference", "source_interpretation"),
                                                          ("source_fact", "reviewed_source_fact")},
                    "claim_type_drift")
            links = [e for e in evidence.values() if e["claim_id"] == cid and e["relation"] == "supports"]
            require(bool(links) and set(u["evidence_ids"]) == {e["evidence_id"] for e in links}, "evidence_link_drift")
            require(all(sources[e["source_id"]]["source_type"] == "official_documentation" for e in links),
                    "platform_claim_not_fact_authority")
            found.add(cid)
        else:
            require(not re.search(r"\d|百分之[一二三四五六七八九十百]|[一二三四五六七八九十百]+倍", text),
                    "number_needs_source")
            require(u["assertion_kind"] in {"recommendation", "interpretation", "question", "boundary"},
                    "unreviewed_assertion_kind")
            require(set(u.get("derived_from", [])) <= required, "derivation_unknown_claim")
    require(found == required, "claim_set_incomplete")
    for key in ("article_order", "oral_order"):
        order = plan[key]
        require(len(order) == len(set(order)) and set(order) <= seen, "unit_order_invalid")
        used = [u["claim_id"] for u in plan["units"] if u["id"] in order and u.get("claim_id")]
        require(len(used) == len(required) and set(used) == required, "platform_claim_set_drift")
    require(all(x["status"] == "needs_source" for x in plan["withheld"]), "withheld_promotion")


def compile_candidate(plan, research, evidence_policy=None, qrp=None):
    if qrp is None:
        raise SynthesisError("owner_binding_required")
    validate_plan(plan, research, evidence_policy)
    units = {u["id"]: u for u in plan["units"]}
    evidence = {e["evidence_id"]: e for e in research["evidence"]}
    sources = {s["source_id"]: s for s in research["sources"]}
    labels = {"source_fact": "已按证据政策审核的来源事实", "verified_quote": "来源短引",
              "author_position": "拟作者观点，待确认", "agent_inference": "解释与建议"}

    def source_link(sid):
        source = sources[sid]
        ref = source["canonical_ref"]
        require(urlsplit(ref).scheme in {"http", "https"}, "source_reference_invalid")
        label = html.escape(source.get("title") or urlsplit(ref).netloc).replace("[", "&#91;").replace("]", "&#93;")
        return f"[{label}]({ref})"

    def body(order):
        parts = []
        for uid in order:
            u = units[uid]
            if u.get("heading"):
                parts.append("## " + html.escape(u["heading"]))
            text = html.escape(u["text"])
            if u["type"] == "verified_quote":
                ev = evidence[u["quote_evidence_id"]]
                parts.append("> " + text + "\n\n" + f"来源：{source_link(ev['source_id'])}；核对的是摘录文字。")
            elif u.get("claim_id"):
                source_ids = sorted({evidence[eid]["source_id"] for eid in u["evidence_ids"]})
                prefix = labels["source_fact"] + "：" if u["type"] == "source_fact" else "据归档来源整理，待审核："
                parts.append(prefix + text + "\n\n" + " ".join(source_link(sid) for sid in source_ids))
            else:
                parts.append(f"**{labels[u['type']]}：**" + text)
        return "\n\n".join(parts) + "\n"

    title = html.escape(plan["title"])
    article = "# " + title + "\n\n候选稿 · 待编辑审核\n\n" + body(plan["article_order"])
    oral = "# 口播候选：" + title + "\n\n括号外的来源标记供编辑核对，录制前另行确认。\n\n" + body(plan["oral_order"])
    facts = [u for u in plan["units"] if u.get("claim_id")]
    synthetic_only = plan.get("synthetic_only") is True
    topic_id = qrp.adapter.sha256_value({"question": research["question"], "title": plan["title"],
        "sources": [{k: s.get(k) for k in ("source_id", "canonical_ref", "content_sha256")} for s in research["sources"]],
        "facts": facts})[:24]
    fact_card = {"schema_version": "content-fact-card.v0", "fact_card_id": "fact-card-" + topic_id,
        "content_id": "original-" + topic_id, "synthetic_only": synthetic_only, "canonical_status": "draft",
        "revision_id": "fact-rev-" + sha(json_text(facts).encode())[:16],
        "facts": [{"fact_id": u["claim_id"], "text": u["text"], "fact_type": "public-claim", "privacy_class": "public",
                   "evidence_refs": [{"ref_type": "evidence", "ref_id": e} for e in u["evidence_ids"]]} for u in facts],
        "unknowns": plan["unknowns"], "forbidden_claims": [u["text"] for u in plan["withheld"]],
        "gates": {"fact": "needs-review", "privacy": "pass", "medical_insurance": "needs-review",
                  "authorization": "needs-review", "rights": "needs-review"}}
    qrp.adapter.validate_instance(fact_card, read(FACT_CARD_SCHEMA), "content-fact-card.v0")
    trace = {"schema_version": "content-original-trace.v2", "adapter_version": VERSION, "status": "candidate_only",
        "source_fact": [u["claim_id"] for u in facts if u["type"] == "source_fact"],
        "verified_quote_means": "exact string match within admitted archive; capture completeness is separate from fact verification",
        "human_review_required": True, "synthetic_only": synthetic_only,
        "source_snapshot": [{"source_id": s["source_id"],
            "canonical_ref": s["canonical_ref"], "archive_path": s["archive_path"],
            "archive_sha256": s["archive_sha256"], "capture_scope": s.get("capture_scope", "unknown"),
            "capture_status": s.get("capture_status", "unknown"),
            "content_ok": s.get("capture_content_ok", s.get("content_ok"))} for s in sources.values()],
        "units": plan["units"], "article_order": plan["article_order"], "oral_order": plan["oral_order"],
        "withheld": plan["withheld"], "unknowns": plan["unknowns"]}
    return {"article.md": article, "oral-script.md": oral}, fact_card, trace


def validate_rendered(texts, plan, research, evidence_policy=None, qrp=None):
    expected, _, _ = compile_candidate(plan, research, evidence_policy, qrp=qrp)
    require(all(texts.get(name) == text for name, text in expected.items()), "rendered_copy_drift")


def persist(root, texts, stop_after=None):
    root = Path(root).resolve()
    for name, text in texts.items():
        p = (root / name).resolve()
        require(p.is_relative_to(root) and p != root, "output_path_escape")
        require(not p.exists() or p.is_file() and p.read_bytes() == text.encode("utf-8"), "output_hash_drift")
    root.mkdir(parents=True, exist_ok=True)
    count = 0
    for name, text in texts.items():
        p = root / name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("xb") as f:
                f.write(text.encode("utf-8"))
            count += 1
            if count == stop_after:
                return "paused"
    return "complete"


def run(plan_path, expected_plan_sha256, pack_path, expected_pack_sha256, upstream, output,
        stop_after=None, *, text_only=False, workspace_root=None, qrp_root=None, tool_registry=None):
    workspace = resolve_workspace_root(workspace_root)
    plan_path, upstream, output = Path(plan_path).resolve(), Path(upstream).resolve(), Path(output).resolve()
    require(output.is_relative_to(workspace) and output != workspace, "output_path_escape")
    qrp, bound_core, gate = bind_owners(qrp_root=qrp_root, tool_registry=tool_registry)
    require(Path(gate.WORKSPACE_ROOT).resolve() == workspace, "workspace_owner_layout_mismatch")
    require(sha(plan_path.read_bytes()) == expected_plan_sha256, "plan_hash_drift")
    plan = read(plan_path)
    index_path = upstream / CONSUMER_INDEX
    require(sha(index_path.read_bytes()) == plan["consumer_index_sha256"], "consumer_index_drift")
    for row in read(index_path)["artifacts"]:
        p = (upstream / row["path"]).resolve()
        require(p.is_relative_to(upstream) and sha(p.read_bytes()) == row["sha256"], "upstream_hash_drift")
    # The upstream loader binds captures and adds their status before hashing.
    research = bound_core._load_fixture(upstream / "public-input.json")
    require(read(pack_path)["input_sha256"] == qrp.adapter.sha256_value(research), "research_pack_input_mismatch")
    for source in research["sources"]:
        p = (upstream / source["archive_path"]).resolve()
        require(p.is_relative_to(upstream) and sha(p.read_bytes()) == source["archive_sha256"], "archive_hash_drift")
        require(sha(source["content"].encode()) == source["content_sha256"], "archive_content_drift")
    item, _, conversion = qrp.convert_pack(Path(pack_path), expected_pack_sha256, allow_unverified_draft=True)
    evidence_policy = reviewed_policy(plan, research, upstream, qrp)
    texts, card, trace = compile_candidate(plan, research, evidence_policy, qrp=qrp)
    parent_content_id = item["content_id"]
    item["content_id"] = card["content_id"]
    validate_rendered(texts, plan, research, evidence_policy, qrp=qrp)
    item["title"] = item["channels"]["article"]["title"] = plan["title"]
    article = item["channels"]["article"]
    article["summary"] = plan["thesis"]
    article["platform_metadata"]["thesis"] = plan["thesis"]
    article["platform_metadata"]["sections"] = [{"section_id": u["id"], "title": u.get("heading", u["id"]),
        "body": u["text"], "evidence_refs": [{"ref_type": "evidence", "ref_id": e} for e in u.get("evidence_ids", [])]}
        for u in plan["units"] if u["id"] in plan["article_order"]]
    article["platform_metadata"]["original_synthesis"] = {"plan_sha256": expected_plan_sha256,
        "trace_ref": "trace.json", "adapter_version": VERSION, "upstream_content_id": parent_content_id,
        "oral_script_ref": "oral-script.md", "structure_route": "mechanism-explanation",
        "story_design_gate": "not_applicable_non_story_route", "fact_status": "draft_not_human_locked",
        "upstream_snapshot_scope": "all_topic_candidates_not_all_used_in_article"}
    qrp.adapter.validate_instance(item, read(qrp.adapter.DEFAULT_CONTENT_SCHEMA), "content-item.v0.2")
    if not text_only:
        from article_visual_pipeline import render_article_html
        texts["article.html"] = render_article_html(texts["article.md"], plan["title"], "editorial-field-guide")
    visual_plan = {"schema_version": "content-original-visual-plan.v1", "content_id": item["content_id"],
        "title": plan["title"], "claim_ids": plan["claim_ids"], "render_recipe": item["visual"]["render_recipe"],
        "status": "no_image_requested", "render_performed": False}
    texts.update({"content-item.json": json_text(item), "fact-card.json": json_text(card),
                  "trace.json": json_text(trace), "visual-plan.json": json_text(visual_plan)})
    checkpoint = {"schema_version": "content-original-checkpoint.v1", "plan_sha256": expected_plan_sha256,
        "pack_sha256": expected_pack_sha256, "adapter_version": VERSION, "status": "prepared_candidate",
        "artifacts": [{"path": k, "sha256": sha(v.encode())} for k, v in texts.items()]}
    # Pin all inputs and intended outputs before writing candidate payloads.
    state = persist(output, {"checkpoint.json": json_text(checkpoint), **texts}, stop_after=stop_after)
    if state == "paused":
        return {"status": "paused", "checkpoint": str(output / "checkpoint.json")}
    binding = {"fact_card_ref": (output / "fact-card.json").relative_to(workspace).as_posix(),
        "fact_card_sha256": gate.sha256_text_file(output / "fact-card.json"), "revision_id": card["revision_id"]}
    claims = [{"fact_id": f["fact_id"], "normalized_claim": f["text"],
               "normalized_claim_sha256": sha(f["text"].encode()), "required_core": True} for f in card["facts"]]
    gate_input = {"schema_version": "cross-platform-fact-consistency-input.v1", "generated_at": research["observed_at"],
        "content_family_id": item["content_id"], "canonical_fact_binding": binding, "canonical_claims": claims,
        "decision": "passed", "variants": [{"platform": platform,
            "artifact_ref": (output / name).relative_to(workspace).as_posix(),
            "artifact_sha256": gate.sha256_text_file(output / name), "fact_binding": binding,
            "claims": [{"fact_id": c["fact_id"], "state": "present",
                        "normalized_claim_sha256": c["normalized_claim_sha256"], "omission_reason": None}
                       for c in claims]}
            for platform, name in [("article", "article.md"), ("oral", "oral-script.md")]]}
    persist(output, {"cross-platform-input.json": json_text(gate_input)})
    receipt = gate.create_receipt(output / "cross-platform-input.json")
    gate_path = gate.OUTPUT_ROOTS[0] / ("original-synthesis-" + expected_plan_sha256[:16] + "-"
                                        + sha(str(output).encode())[:8] + ".json")
    gate.write_receipt(gate_path, receipt)
    gate.validate_receipt(receipt)
    review = {"schema_version": "content-original-review-packet.v1", "status": "pending_human_review",
        "publication_authorized": False, "native_content_contract_validated": True,
        "fact_card_contract_validated": True, "canonical_status": "draft",
        "consistency_receipt": str(gate_path),
        "consistency_scope": "exact prose rendering plus existing declared claim/hash gate; not NLP truth verification",
        "adapter_version": VERSION, "synthetic_only": plan.get("synthetic_only") is True,
        "source_fact_count": len(trace["source_fact"]),
        "source_host_count": len({urlsplit(s["canonical_ref"]).netloc for s in research["sources"]}),
        "capture_scope": aggregate(trace["source_snapshot"], "capture_scope"),
        "capture_status": aggregate(trace["source_snapshot"], "capture_status"),
        "content_ok": aggregate(trace["source_snapshot"], "content_ok"),
        "arw_status": read(upstream / "arw-quality.json").get("status", "unknown")
        if (upstream / "arw-quality.json").is_file() else "unknown",
        "unknowns": plan["unknowns"], "withheld": plan["withheld"],
        "review_questions": ["确认观点是否代表作者；逐项审核来源解释。", "核对短引与来源适用范围。",
                             "检查未知项是否被无依据地写成结论。"],
        "limitations": ["No human fact lock, publication, browser visual QA, media recording, RCP native import or product trial.",
            "Free editorial text is a hash-pinned candidate, not machine-proven reasoning; case/number labels must be truthful."],
        "rcp_consumer": {"input_ref": str(output / "content-item.json"),
                         "review_ref": str(output / "review-packet.json"), "native_import_executed": False},
        "conversion": conversion}
    persist(output, {"review-packet.json": json_text(review)})
    consumer = {"schema_version": "content-original-consumer-index.v2", "adapter_version": VERSION,
        "content_id": item["content_id"], "closure_run_id": conversion["closure_run_id"],
        "status": "candidate_only", "publication_authorized": False, "text_only": text_only,
        "artifacts": [{"path": name, "sha256": sha((output / name).read_bytes())} for name in
            ["article.md", "oral-script.md", "content-item.json", "fact-card.json", "trace.json",
             "visual-plan.json", "review-packet.json"]],
        "consistency_receipt": str(gate_path),
        "version_policy": "artifact hashes and adapter semantic version; no repository HEAD equality"}
    persist(output, {"consumer-index.json": json_text(consumer)})
    return {"status": "complete_candidate_only", "review_packet": str(output / "review-packet.json"),
            "consistency_receipt": str(gate_path)}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "expected-plan-sha256", "pack", "expected-pack-sha256", "upstream", "output"):
        p.add_argument("--" + name, required=True)
    p.add_argument("--workspace-root", type=Path,
                   help="Explicit common workspace root containing the Main owner and outputs.")
    p.add_argument("--qrp-root", type=Path, help="Explicit public question-research-poc source root.")
    p.add_argument("--tool-registry", type=Path, help="Explicit registered self-media tool registry.")
    p.add_argument("--stop-after", type=int)
    p.add_argument("--text-only", action="store_true",
                   help="Only text/contracts; do not call the HTML adapter or generate images.")
    a = p.parse_args(argv)
    try:
        print(json.dumps(run(a.plan, a.expected_plan_sha256, a.pack, a.expected_pack_sha256, a.upstream,
                             a.output, a.stop_after, text_only=a.text_only, workspace_root=a.workspace_root,
                             qrp_root=a.qrp_root, tool_registry=a.tool_registry)))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "blocked", "code": getattr(exc, "code", "invalid_input"), "detail": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
