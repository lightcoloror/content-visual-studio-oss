"""Synthetic contract tests for global_visual_validation.py and visual_asset_routing.py.

The fixture writes invented contracts, invented schemas, invented brand records
and invented artifact bytes under a TemporaryDirectory. Nothing reads a real
studio package, private brand asset, network endpoint or subprocess.

The two JSON Schema files embedded here are explicitly labelled SYNTHETIC TEST
ONLY: they carry the public contract's field shapes needed by the validator,
but they are not canonical-contract proof. The host verifies the real packaged
nine contracts separately.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.request
from unittest import mock

_OMITTED = object()

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_SYNTHETIC_STUDIO_TMP: tempfile.TemporaryDirectory | None = None


def _ensure_studio_paths() -> None:
    global _SYNTHETIC_STUDIO_TMP
    try:
        import studio_paths  # noqa: F401

        return
    except ImportError:
        pass
    if "studio_paths" in sys.modules:
        return
    _SYNTHETIC_STUDIO_TMP = tempfile.TemporaryDirectory(prefix="synthetic-studio-paths-")
    module = types.ModuleType("studio_paths")
    module.__file__ = str(_SCRIPTS / "studio_paths.py")
    module.HERE = _SCRIPTS
    module.SOURCE_ROOT = _SCRIPTS.parent
    module.STUDIO_ROOT = Path(_SYNTHETIC_STUDIO_TMP.name)
    module.HUMAN_VOICE_ROOT = module.STUDIO_ROOT / "skills" / "human-voice-editor"
    module.research_schema_path = lambda: module.STUDIO_ROOT / "schemas" / "research-output.schema.json"
    sys.modules["studio_paths"] = module


_ensure_studio_paths()

import check_shared_visual_lock as lock_module  # noqa: E402
import global_visual_validation as gvv  # noqa: E402
import visual_asset_routing as routing  # noqa: E402

SOURCE_ROOT_ENV = gvv.SOURCE_ROOT_ENV
AUTHORITY_REF = "contracts/authority-registry.v1.json"

GLOBAL_CONTEXT_SCHEMA_NAME = "schemas/global-visual-context.v1.schema.json"
DATA_VISUAL_SCHEMA_NAME = "schemas/data-visual-spec.v1.schema.json"
CONFORMANCE_SCHEMA_NAME = "schemas/visual-conformance-receipt.v1.schema.json"
GUIDELINES_NAME = "contracts/guidelines.v1.json"
TYPOGRAPHY_NAME = "contracts/chinese-typography.v1.json"
ICONS_NAME = "contracts/icon-registry.v1.json"
IMAGERY_NAME = "contracts/imagery-grammar.v1.json"
MOTION_NAME = "contracts/motion-grammar.v1.json"
MATRIX_NAME = "contracts/cross-medium-conformance.v1.json"

SYNTHETIC_LABEL = (
    "SYNTHETIC TEST ONLY: minimal shape of the supplied generic contract; "
    "not canonical contract proof."
)

# ---------------------------------------------------------------------------
# Synthetic-but-shape-faithful schemas (clearly labelled)
# ---------------------------------------------------------------------------

GLOBAL_CONTEXT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.invalid/synthetic-test-only/global-visual-context.v1.schema.json",
    "$comment": SYNTHETIC_LABEL,
    "title": "Global visual context (synthetic test shape)",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "ruleset",
        "locale",
        "writing_mode",
        "conformance_profile",
        "authority_scope",
        "enforcement",
    ],
    "properties": {
        "schema_version": {"const": "global-visual-context.v1"},
        "ruleset": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ref", "version", "sha256"],
            "properties": {
                "ref": {"type": "string", "minLength": 1},
                "version": {"type": "string", "pattern": "^[0-9]+\\.[0-9]+\\.[0-9]+$"},
                "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        "locale": {"enum": ["zh-Hans", "zh-Hant"]},
        "writing_mode": {"const": "horizontal-tb"},
        "conformance_profile": {
            "enum": ["article.v1", "social-card.v1", "infographic.v1", "pptx.v1", "web.v1"]
        },
        "authority_scope": {"enum": ["global-only", "brand-bound"]},
        "brand_authority": {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "profile_id",
                "profile_version",
                "repository_ref",
                "authority_version",
                "profile_ref",
                "tokens_ref",
                "projection_sha256",
                "qa_receipt_ref",
                "qa_receipt_sha256",
            ],
            "properties": {
                "profile_id": {"type": "string", "minLength": 1},
                "profile_version": {"type": "string", "minLength": 1},
                "repository_ref": {"type": "string", "minLength": 1},
                "authority_version": {"type": "string", "minLength": 1},
                "profile_ref": {"type": "string", "minLength": 1},
                "tokens_ref": {"type": "string", "minLength": 1},
                "projection_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                "qa_receipt_ref": {"type": "string", "minLength": 1},
                "qa_receipt_sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        "enforcement": {
            "type": "object",
            "additionalProperties": False,
            "required": ["p0", "p1", "p2"],
            "properties": {
                "p0": {"const": "blocking"},
                "p1": {"enum": ["report-only", "blocking"]},
                "p2": {"const": "explicit-only"},
            },
        },
        "motion": {
            "type": "object",
            "additionalProperties": False,
            "required": ["mode"],
            "properties": {
                "mode": {"enum": ["none", "explicit"]},
                "purpose": {"type": "string", "minLength": 1, "maxLength": 160},
                "static_fallback_ref": {"type": "string", "minLength": 1},
            },
        },
        "exceptions": {
            "type": "array",
            "uniqueItems": True,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rule_id", "reason", "reviewer", "expires_at"],
                "properties": {
                    "rule_id": {"type": "string", "minLength": 1},
                    "reason": {"type": "string", "minLength": 8},
                    "reviewer": {"type": "string", "minLength": 1},
                    "expires_at": {"type": "string", "format": "date-time"},
                },
            },
        },
    },
    "allOf": [
        {
            "if": {
                "properties": {"authority_scope": {"const": "brand-bound"}},
                "required": ["authority_scope"],
            },
            "then": {"required": ["brand_authority"]},
        },
        {
            "if": {
                "properties": {"motion": {"properties": {"mode": {"const": "explicit"}}, "required": ["mode"]}},
                "required": ["motion"],
            },
            "then": {
                "properties": {"conformance_profile": {"const": "web.v1"}},
                "required": ["motion"],
            },
        },
    ],
}

CONFORMANCE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.invalid/synthetic-test-only/visual-conformance-receipt.v1.schema.json",
    "$comment": SYNTHETIC_LABEL,
    "title": "Visual conformance receipt (synthetic test shape)",
    "type": "object",
    "additionalProperties": False,
    "required": [
        "schema_version",
        "receipt_id",
        "artifact_id",
        "content_id",
        "created_at",
        "ruleset",
        "output",
        "authority_receipts",
        "media_qa",
        "findings",
        "result",
        "policy",
    ],
    "properties": {
        "schema_version": {"const": "visual-conformance-receipt.v1"},
        "receipt_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9._-]{2,127}$"},
        "artifact_id": {"type": "string", "minLength": 3},
        "content_id": {"type": "string", "minLength": 6},
        "created_at": {"type": "string", "format": "date-time"},
        "ruleset": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ref", "version", "sha256"],
            "properties": {
                "ref": {"type": "string"},
                "version": {"type": "string"},
                "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        "output": {
            "type": "object",
            "additionalProperties": False,
            "required": ["ref", "sha256"],
            "properties": {
                "ref": {"type": "string"},
                "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        "authority_receipts": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "ref", "schema_version", "sha256"],
                "properties": {
                    "kind": {"enum": ["global-rules", "brand-authority", "media-qa", "motion-review"]},
                    "ref": {"type": "string"},
                    "schema_version": {"type": "string"},
                    "sha256": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                },
            },
        },
        "media_qa": {
            "type": "object",
            "additionalProperties": False,
            "required": ["profile_id", "hard_checks", "result"],
            "properties": {
                "profile_id": {"type": "string", "minLength": 1},
                "hard_checks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["name", "status"],
                        "properties": {
                            "name": {"type": "string", "minLength": 1},
                            "status": {"enum": ["pass", "fail"]},
                            "details": {"type": "string"},
                        },
                    },
                },
                "result": {"enum": ["pass", "fail"]},
            },
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["diagnostic_id", "rule_id", "priority", "enforcement", "status", "message"],
                "properties": {
                    "diagnostic_id": {"type": "string"},
                    "rule_id": {"type": "string"},
                    "priority": {"enum": ["P0", "P1", "P2"]},
                    "enforcement": {"enum": ["blocking", "report-only", "human-check", "not-applicable"]},
                    "status": {"enum": ["pass", "fail", "needs-review", "not-applicable"]},
                    "message": {"type": "string"},
                    "evidence_ref": {"type": "string"},
                },
            },
        },
        "exceptions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["rule_id", "reason", "reviewer", "expires_at"],
                "properties": {
                    "rule_id": {"type": "string"},
                    "reason": {"type": "string", "minLength": 8},
                    "reviewer": {"type": "string", "minLength": 1},
                    "expires_at": {"type": "string", "format": "date-time"},
                },
            },
        },
        "result": {"enum": ["pass", "fail", "review-required"]},
        "policy": {
            "type": "object",
            "additionalProperties": False,
            "required": ["manual_only", "candidate_only", "p1_mode", "p2_mode"],
            "properties": {
                "manual_only": {"type": "boolean"},
                "candidate_only": {"type": "boolean"},
                "p1_mode": {"enum": ["report-only", "blocking"]},
                "p2_mode": {"const": "explicit-only"},
            },
        },
    },
}

DATA_VISUAL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.invalid/synthetic-test-only/data-visual-spec.v1.schema.json",
    "$comment": SYNTHETIC_LABEL
    + " The validator does not load this file; the full packaged contract is host-verified.",
    "title": "Normalized data visual specification (synthetic test shape)",
    "type": "object",
    "required": ["schema_version", "artifact_id", "manual_only"],
    "properties": {
        "schema_version": {"const": "data-visual-spec.v1"},
        "artifact_id": {"type": "string"},
        "manual_only": {"const": True},
    },
}

# ---------------------------------------------------------------------------
# Supplied generic contracts (same shapes as the packaged public contracts)
# ---------------------------------------------------------------------------

GUIDELINES = {
    "schema_version": "global-visual-guidelines.v1",
    "version": "1.0.0",
    "updated_at": "2026-08-24T08:30:00+08:00",
    "updated_by": "Codex (GPT-5.6 Sol)",
    "guidelines": [
        {"guideline_id": "brand-authority-conformance", "diagnostic_id": "GVL-AUTH-001", "version": "1.0.0", "priority": "P0", "purpose": "Keep brand facts and generated projections bound to one declared authority.", "status": "active", "source_refs": ["contracts/global-visual-style-reference-candidates.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["all"], "exclusions": [], "related": ["qa-receipt-bridge"], "test_hooks": ["authority-drift", "projection-hash", "reverse-write-forbidden"]},
        {"guideline_id": "chinese-typography", "diagnostic_id": "GVL-TYPE-001", "version": "1.0.0", "priority": "P0", "purpose": "Make horizontal Chinese composition locale-aware and testable in rendered output.", "status": "active", "source_refs": ["contracts/chinese-typography.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["article", "social-card", "infographic", "pptx", "web"], "exclusions": ["vertical-writing"], "related": [], "test_hooks": ["line-boundary", "cjk-orphan", "font-resolution", "heading-keep"]},
        {"guideline_id": "data-visual-language", "diagnostic_id": "GVL-DATA-001", "version": "1.0.0", "priority": "P0", "purpose": "Bind charts to comparison questions, precision, uncertainty, sources and responsive fallbacks.", "status": "active", "source_refs": ["schemas/data-visual-spec.v1.schema.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["article", "infographic", "pptx", "web"], "exclusions": [], "related": [], "test_hooks": ["data-contract", "table-alternative", "responsive-fallback"]},
        {"guideline_id": "iconography-grammar", "diagnostic_id": "GVL-ICON-001", "version": "1.0.0", "priority": "P1", "purpose": "Use only registered semantic icons with labels, accessibility names and reviewed metaphors.", "status": "report-only", "source_refs": ["contracts/icon-registry.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["article", "social-card", "infographic", "pptx", "web"], "exclusions": [], "related": [], "test_hooks": ["icon-registry", "forbidden-metaphor", "icon-label"]},
        {"guideline_id": "imagery-and-illustration-grammar", "diagnostic_id": "GVL-IMAGE-001", "version": "1.0.0", "priority": "P1", "purpose": "Separate evidence, documentary, explanatory and decorative imagery while preserving rights and crop intent.", "status": "report-only", "source_refs": ["contracts/imagery-grammar.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["article", "social-card", "infographic", "pptx", "web"], "exclusions": [], "related": [], "test_hooks": ["imagery-role", "overlay-safety", "ai-opt-in"]},
        {"guideline_id": "guideline-lifecycle-and-provenance", "diagnostic_id": "GVL-GOV-001", "version": "1.0.0", "priority": "P1", "purpose": "Keep every rule queryable, scoped, attributable, versioned and deprecatable.", "status": "report-only", "source_refs": ["schemas/guideline.v1.schema.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["all"], "exclusions": [], "related": [], "test_hooks": ["guideline-schema", "stable-diagnostic-id"]},
        {"guideline_id": "cross-medium-conformance-matrix", "diagnostic_id": "GVL-MEDIA-001", "version": "1.0.0", "priority": "P1", "purpose": "Apply only relevant rules to each medium and make every fallback explicit.", "status": "report-only", "source_refs": ["contracts/cross-medium-conformance.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["all"], "exclusions": [], "related": [], "test_hooks": ["profile-coverage", "fallback-required"]},
        {"guideline_id": "qa-receipt-bridge", "diagnostic_id": "GVL-QA-001", "version": "1.0.0", "priority": "P1", "purpose": "Bind trusted authority and media QA receipts without re-running equivalent checks.", "status": "report-only", "source_refs": ["schemas/visual-conformance-receipt.v1.schema.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["all"], "exclusions": [], "related": ["brand-authority-conformance"], "test_hooks": ["receipt-hash", "receipt-version", "stale-receipt"]},
        {"guideline_id": "motion-grammar", "diagnostic_id": "GVL-MOTION-001", "version": "1.0.0", "priority": "P2", "purpose": "Permit meaningful motion only for explicit Web items with reduced and static fallbacks.", "status": "draft", "source_refs": ["contracts/motion-grammar.v1.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["web"], "exclusions": ["article", "social-card", "infographic", "pptx"], "related": [], "test_hooks": ["motion-explicit", "reduced-motion", "static-fallback"]},
        {"guideline_id": "specimen-and-calibration-gallery", "diagnostic_id": "GVL-SPEC-001", "version": "1.0.0", "priority": "P2", "purpose": "Calibrate guidelines with synthetic approved and rejected rendered pairs.", "status": "draft", "source_refs": ["schemas/specimen.v1.schema.json"], "checked_at": "2026-08-24T08:30:00+08:00", "applies_to": ["all"], "exclusions": ["storybook-before-threshold"], "related": [], "test_hooks": ["specimen-schema", "approved-and-antipattern-pair"]},
    ],
}

TYPOGRAPHY = {
    "schema_version": "chinese-typography.v1",
    "version": "1.0.0",
    "source_refs": ["https://github.com/w3c/clreq/tree/96c4986a9e1d74a815e0c045995b1853f018f7ec"],
    "policy": {
        "writing_modes": ["horizontal-tb"],
        "locales": ["zh-Hans", "zh-Hant"],
        "rendered_output_is_authority": True,
        "raster_requires_structural_source": True,
        "automatic_copy_rewrite": False,
    },
    "rules": {
        "line_start_forbidden": "，。、；：！？）》】〕〉…",
        "line_end_forbidden": "（《【〔〈",
        "western_word_break": "keep-whole-when-fit",
        "mixed_script_spacing": "renderer-managed",
        "orphan_control": {"minimum_cjk_characters_on_final_line": 2},
        "heading_keep_with_next": True,
        "font_fallback_must_resolve": True,
    },
    "diagnostics": {
        "line_start": "GVL-TYPE-001",
        "line_end": "GVL-TYPE-002",
        "western_word_break": "GVL-TYPE-003",
        "orphan": "GVL-TYPE-004",
        "heading_keep": "GVL-TYPE-005",
        "font_missing": "GVL-TYPE-006",
        "raster_source_missing": "GVL-TYPE-007",
    },
}

ICON_REGISTRY = {
    "schema_version": "icon-registry.v1",
    "version": "1.0.0",
    "source": {
        "project": "lucide",
        "repository": "https://github.com/lucide-icons/lucide",
        "commit": "33a44aa8b0b43d9b0ed14eb08860a1b5550a1573",
        "license": "ISC-with-listed-Feather-icons-MIT",
        "canvas": 24,
        "stroke_width": 2,
        "linecap": "round",
        "linejoin": "round",
    },
    "policy": {
        "registered_only": True,
        "visible_label_required": True,
        "accessible_name_required": True,
        "color_only_meaning_forbidden": True,
        "full_library_vendoring": False,
    },
    "icons": [
        {"semantic_id": "dressing-wet", "lucide_name": "droplets", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "dressing-leak", "lucide_name": "waves", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "dressing-loose", "lucide_name": "unlink", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "dressing-saturated", "lucide_name": "circle-gauge", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "systemic-fever", "lucide_name": "thermometer", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "wound-red-hot", "lucide_name": "flame", "status": "active-with-label", "contexts": ["medical-observation"]},
        {"semantic_id": "wound-discharge-odor", "lucide_name": "triangle-alert", "status": "active-with-label", "contexts": ["medical-observation"]},
        {"semantic_id": "wound-bleeding", "lucide_name": "scan-search", "status": "active-with-label", "contexts": ["medical-observation"]},
        {"semantic_id": "observe-without-opening", "lucide_name": "eye", "status": "active", "contexts": ["medical-observation"]},
        {"semantic_id": "contact-caregiver", "lucide_name": "phone-call", "status": "active", "contexts": ["action"]},
        {"semantic_id": "scheduled-check", "lucide_name": "clock-3", "status": "active", "contexts": ["time"]},
        {"semantic_id": "stable-keep-closed", "lucide_name": "shield-check", "status": "forbidden-brand-metaphor", "contexts": [], "reason": "The personal brand authority forbids shield metaphors."},
        {"semantic_id": "generic-risk-shield", "lucide_name": "shield-alert", "status": "forbidden-brand-metaphor", "contexts": [], "reason": "Shield imagery can imply guaranteed protection."},
    ],
    "diagnostics": {
        "unregistered": "GVL-ICON-001",
        "forbidden": "GVL-ICON-002",
        "missing_visible_label": "GVL-ICON-003",
        "missing_accessible_name": "GVL-ICON-004",
        "color_only": "GVL-ICON-005",
    },
}

IMAGERY = {
    "schema_version": "imagery-grammar.v1",
    "version": "1.0.0",
    "roles": ["evidence-photo", "documentary-photo", "explanatory-illustration", "diagram", "decoration"],
    "treatments": ["natural", "documentary", "annotated", "muted-support", "none"],
    "text_overlay_policies": ["none", "safe-area-only", "explicit-approved"],
    "evidence_statuses": ["verified", "user-confirmed", "illustrative-only", "needs-review", "unknown"],
    "policy": {
        "real_photo_default_text_overlay": "none",
        "evidence_photo_cannot_be_stock": True,
        "rights_and_privacy_required": True,
        "focal_cover_requires_focal_point": True,
        "overlay_requires_safe_crop": True,
        "generated_image_requires_explicit_user_request": True,
    },
    "diagnostics": {
        "role_missing": "GVL-IMAGE-001",
        "evidence_mismatch": "GVL-IMAGE-002",
        "overlay_without_safe_crop": "GVL-IMAGE-003",
        "rights_or_privacy": "GVL-IMAGE-004",
        "ai_authorization": "GVL-IMAGE-005",
    },
}

MOTION = {
    "schema_version": "motion-grammar.v1",
    "version": "1.0.0",
    "policy": {
        "eligible_media_adapters": ["web"],
        "activation": "explicit-item-only",
        "automatic_routing": False,
        "allowed_properties": ["transform", "opacity"],
        "purpose_required": True,
        "reduced_motion_required": True,
        "static_fallback_required": True,
        "manual_review_required": True,
    },
    "roles": ["direction", "state", "interaction", "wayfinding"],
    "diagnostics": {
        "implicit_motion": "GVL-MOTION-001",
        "unsupported_media": "GVL-MOTION-002",
        "layout_property": "GVL-MOTION-003",
        "reduced_motion_missing": "GVL-MOTION-004",
        "static_fallback_missing": "GVL-MOTION-005",
    },
}

MATRIX = {
    "schema_version": "cross-medium-conformance.v1",
    "version": "1.0.0",
    "rollout": {
        "p0": "blocking-after-fixture-acceptance",
        "p1": "report-only",
        "p2": "explicit-only",
        "p1_promotion": {
            "minimum_specimens_per_applicable_medium": 3,
            "consecutive_stable_runs": 2,
            "maximum_noncritical_false_positive_rate": 0.05,
            "critical_false_positives_allowed": 0,
            "manual_owner_approval_required": True,
        },
    },
    "profiles": {
        "article.v1": {"media_adapter": "article", "rules": ["brand-authority-conformance", "chinese-typography", "imagery-and-illustration-grammar", "iconography-grammar", "qa-receipt-bridge"], "static_fallback": "html-or-markdown"},
        "social-card.v1": {"media_adapter": "social-card", "rules": ["brand-authority-conformance", "chinese-typography", "imagery-and-illustration-grammar", "iconography-grammar", "qa-receipt-bridge"], "static_fallback": "png-with-structural-source"},
        "infographic.v1": {"media_adapter": "infographic", "rules": ["brand-authority-conformance", "chinese-typography", "data-visual-language", "imagery-and-illustration-grammar", "iconography-grammar", "qa-receipt-bridge"], "static_fallback": "svg-or-png-with-structural-source"},
        "pptx.v1": {"media_adapter": "pptx", "rules": ["brand-authority-conformance", "chinese-typography", "data-visual-language", "imagery-and-illustration-grammar", "iconography-grammar", "qa-receipt-bridge"], "static_fallback": "pptx-plus-rendered-preview"},
        "web.v1": {"media_adapter": "web", "rules": ["brand-authority-conformance", "chinese-typography", "data-visual-language", "imagery-and-illustration-grammar", "iconography-grammar", "qa-receipt-bridge", "motion-grammar"], "static_fallback": "static-html-or-image"},
    },
    "enforcement": {
        "brand-authority-conformance": {"priority": "P0", "default": "blocking"},
        "chinese-typography": {"priority": "P0", "default": "blocking"},
        "data-visual-language": {"priority": "P0", "default": "blocking"},
        "iconography-grammar": {"priority": "P1", "default": "report-only"},
        "imagery-and-illustration-grammar": {"priority": "P1", "default": "report-only"},
        "guideline-lifecycle-and-provenance": {"priority": "P1", "default": "report-only"},
        "cross-medium-conformance-matrix": {"priority": "P1", "default": "report-only"},
        "qa-receipt-bridge": {"priority": "P1", "default": "report-only"},
        "motion-grammar": {"priority": "P2", "default": "human-check"},
        "specimen-and-calibration-gallery": {"priority": "P2", "default": "not-applicable"},
    },
}

RUNTIME = {
    "schema_version": "global-visual-runtime.v1",
    "shared_root": None,
    "playwright_package": {
        "env": "PLAYWRIGHT_PACKAGE_JSON",
        "fallback_ref": None,
        "expected_name": "playwright",
        "expected_version": "1.61.1",
    },
    "shared_package": "@lightcolor/shared-visual-design-system",
    "shared_package_version": "1.1.0",
    "ruleset_ref": "contracts/guidelines.v1.json",
    "ruleset_version": "1.0.0",
    "authority_registry_ref": AUTHORITY_REF,
    "shared_lock_ref": "vendor/shared-visual-design-system/shared-visual-design-system.lock.json",
    "p0_activation": "active",
    "p1_mode": "report-only",
    "p2_mode": "explicit-only",
    "new_artifact_opt_in": "renderer_options.global_visual_v1=true",
    "automatic_publication": False,
    "automatic_ai_image_generation": False,
    "boundary": "generic structural contract/projection only; no authority, renderer, generation or publishing permission",
}

EMPTY_AUTHORITY = {
    "schema_version": "visual-authority-registry.v1",
    "synthetic_example_only": True,
    "brand_authorities": {},
}

BRAND_LOCAL_ROOT = "brands/synthetic-brand"
BRAND_REGISTRY = {
    "schema_version": "visual-authority-registry.v1",
    "synthetic_test_only": True,
    "brand_authorities": {
        "synthetic-brand.v1": {
            "repository": "synthetic://operator-provided/synthetic-brand",
            "profile_version": "2.0.0",
            "local_root": BRAND_LOCAL_ROOT,
            "tokens_ref": "brand-tokens.json",
            "profile_ref": "brand-profile.json",
            "qa_receipt_ref": "qa-receipt.json",
        }
    },
}
BRAND_PROFILE = {
    "schema_version": "brand-profile.v1",
    "profile_id": "synthetic-brand.v1",
    "meta": {"source_updated_at": "2026-01-01T00:00:00Z"},
}
BRAND_TOKENS = {
    "schema_version": "brand-tokens.v1",
    "synthetic_test_only": True,
    "tokens": {"color.ink": "#101010", "color.paper": "#fafafa"},
}
BRAND_RECEIPT = {
    "schema_version": "authority-receipt.v1",
    "profile_version": "2.0.0",
    "created_at": "2026-02-01T00:00:00Z",
    "qa": {"status": "pass"},
}
BRAND_FILES = {
    BRAND_LOCAL_ROOT + "/brand-profile.json": BRAND_PROFILE,
    BRAND_LOCAL_ROOT + "/brand-tokens.json": BRAND_TOKENS,
    BRAND_LOCAL_ROOT + "/qa-receipt.json": BRAND_RECEIPT,
}

CONTRACTS = {
    GLOBAL_CONTEXT_SCHEMA_NAME: GLOBAL_CONTEXT_SCHEMA,
    DATA_VISUAL_SCHEMA_NAME: DATA_VISUAL_SCHEMA,
    CONFORMANCE_SCHEMA_NAME: CONFORMANCE_SCHEMA,
    GUIDELINES_NAME: GUIDELINES,
    TYPOGRAPHY_NAME: TYPOGRAPHY,
    ICONS_NAME: ICON_REGISTRY,
    IMAGERY_NAME: IMAGERY,
    MOTION_NAME: MOTION,
    MATRIX_NAME: MATRIX,
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json_bytes(document) -> bytes:
    return json.dumps(document, indent=2, ensure_ascii=False).encode("utf-8")


def article_artifact(**overrides):
    artifact = {
        "artifact_id": "artifact-001",
        "media_adapter": "article",
        "output_family": "article",
        "layout_intent": "article",
    }
    artifact.update(overrides)
    return artifact


def infographic_artifact(**overrides):
    artifact = {
        "artifact_id": "artifact-chart-001",
        "media_adapter": "infographic",
        "output_family": "infographic",
        "layout_intent": "data-chart",
    }
    artifact.update(overrides)
    return artifact


def web_artifact(**overrides):
    artifact = {
        "artifact_id": "artifact-web-001",
        "media_adapter": "web",
        "output_family": "web",
        "layout_intent": "web",
    }
    artifact.update(overrides)
    return artifact


def exception_entry(rule_id: str, expires_at: str) -> dict:
    return {
        "rule_id": rule_id,
        "reason": "synthetic exception reason",
        "reviewer": "synthetic-reviewer",
        "expires_at": expires_at,
    }


class VisualFixture:
    """Synthetic packaged source/projection/config layout."""

    def __init__(self, base: Path, *, brand: bool = False) -> None:
        self.base = base
        self.source = base / "source"
        self.projection = base / "projection"
        self.config_dir = base / "config"
        self.runtime_path = self.config_dir / "global-visual-runtime.v1.json"
        self.lock_path = self.projection / lock_module.LOCK_FILENAME
        self.source.mkdir(parents=True, exist_ok=True)
        self.projection.mkdir(parents=True, exist_ok=True)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        for ref, document in CONTRACTS.items():
            data = _json_bytes(document)
            self.write(self.source / ref, data)
            self.write(self.projection / ref, data)
        self.brand_paths = {}
        if brand:
            self.write(self.source / AUTHORITY_REF, _json_bytes(BRAND_REGISTRY))
            for ref, document in BRAND_FILES.items():
                self.write(self.source / ref, _json_bytes(document))
            self.brand_paths = {
                "registry": self.source / AUTHORITY_REF,
                "profile": self.source / (BRAND_LOCAL_ROOT + "/brand-profile.json"),
                "tokens": self.source / (BRAND_LOCAL_ROOT + "/brand-tokens.json"),
                "receipt": self.source / (BRAND_LOCAL_ROOT + "/qa-receipt.json"),
            }
        else:
            self.write(self.source / AUTHORITY_REF, _json_bytes(EMPTY_AUTHORITY))
        self.write(self.runtime_path, _json_bytes(RUNTIME))
        lock = {
            "schema_version": "shared-visual-design-system-lock.v1",
            "package": "@lightcolor/shared-visual-design-system",
            "consumer": "content-visual-studio",
            "package_version": "1.1.0",
            "files": {},
        }
        for ref in CONTRACTS:
            lock["files"][ref] = {
                "sha256": _sha((self.source / ref).read_bytes()),
                "projected_ref": ref,
            }
        self.write(self.lock_path, _json_bytes(lock))

    @staticmethod
    def write(path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def write_json(self, path: Path, document) -> None:
        self.write(path, _json_bytes(document))

    def write_lock(self, lock: dict) -> None:
        self.write_json(self.lock_path, lock)

    def add_locked_member(self, ref: str, data: bytes) -> None:
        """Add an extra lock-declared member (projection + lock entry) to the fixture."""

        self.write(self.source / ref, data)
        self.write(self.projection / ref, data)
        lock = json.loads(self.lock_path.read_text(encoding="utf-8"))
        lock["files"][ref] = {"sha256": _sha(data), "projected_ref": ref}
        self.write_lock(lock)

    def lock_files(self) -> dict:
        return json.loads(self.lock_path.read_text(encoding="utf-8"))["files"]

    def kwargs(self) -> dict:
        return {
            "shared_root": self.source,
            "runtime_path": self.runtime_path,
            "schema_root": self.projection,
        }

    def item(self, **overrides) -> dict:
        item = {
            "content_id": "content-demo-001",
            "topic": "synthetic insurance wording example",
            "visual": {
                "design_system": {},
                "semantic_visual_map": [],
                "assets": [],
            },
        }
        item.update(overrides)
        return item

    def brand_item(self, **overrides) -> dict:
        item = self.item(**overrides)
        item["visual"]["visual_profile"] = "synthetic-brand.v1"
        item["visual"]["visual_profile_version"] = "2.0.0"
        return item

    def output(self, name: str = "artifact-001.png", data: bytes = b"\x89PNG\r\n\x1a\nsynthetic-bytes") -> Path:
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def context(self, item=None, artifact=None):
        return gvv.build_runtime_context(
            item if item is not None else self.item(),
            artifact if artifact is not None else article_artifact(),
            **self.kwargs(),
        )

    def receipt(
        self,
        *,
        item=_OMITTED,
        artifact=_OMITTED,
        typography=_OMITTED,
        data_status=_OMITTED,
        media_qa=_OMITTED,
        output_path=_OMITTED,
    ) -> dict:
        return gvv.build_conformance_receipt(
            self.item() if item is _OMITTED else item,
            article_artifact() if artifact is _OMITTED else artifact,
            self.output() if output_path is _OMITTED else output_path,
            {"status": "pass", "ref": "synthetic/typography-evidence.txt"}
            if typography is _OMITTED
            else typography,
            {"normalized_spec_valid": True} if data_status is _OMITTED else data_status,
            {"profile_id": "article.v1", "hard_checks": [], "result": "pass"}
            if media_qa is _OMITTED
            else media_qa,
            **self.kwargs(),
        )

    def validate_item(self, item, artifact) -> list:
        return gvv.validate_global_visual_item(item, artifact, **self.kwargs())


class GlobalVisualContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="global-visual-test-")
        self.base = Path(self._tmp.name)
        self._fixture_counter = 0

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def fixture(self, *, brand: bool = False) -> VisualFixture:
        self._fixture_counter += 1
        return VisualFixture(self.base / f"case-{self._fixture_counter}", brand=brand)

    @staticmethod
    def _enabled_item(fixture: VisualFixture) -> tuple[dict, dict]:
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = fixture.context()
        artifact = article_artifact()
        artifact["renderer_options"] = {"global_visual_v1": True}
        return item, artifact

    # -- positive global-only flow -----------------------------------------

    def test_global_only_context_and_receipt(self) -> None:
        fixture = self.fixture()
        output = fixture.output()
        receipt = fixture.receipt(output_path=output)

        context = fixture.context()
        self.assertEqual(context["authority_scope"], "global-only")
        self.assertNotIn("brand_authority", context)
        self.assertEqual(context["conformance_profile"], "article.v1")
        self.assertEqual(context["ruleset"]["ref"], GUIDELINES_NAME)
        self.assertEqual(context["ruleset"]["version"], "1.0.0")
        self.assertEqual(
            context["ruleset"]["sha256"],
            _sha((fixture.source / GUIDELINES_NAME).read_bytes()),
        )
        self.assertEqual(context["enforcement"], {"p0": "blocking", "p1": "report-only", "p2": "explicit-only"})

        self.assertEqual(receipt["schema_version"], "visual-conformance-receipt.v1")
        self.assertEqual(receipt["receipt_id"], "content-demo-001.artifact-001.visual-conformance")
        self.assertEqual(receipt["result"], "pass")
        self.assertEqual(receipt["output"]["ref"], str(output))
        self.assertEqual(receipt["output"]["sha256"], _sha(output.read_bytes()))
        self.assertEqual(
            receipt["policy"],
            {
                "manual_only": True,
                "candidate_only": False,
                "p1_mode": "report-only",
                "p2_mode": "explicit-only",
            },
        )
        self.assertEqual(receipt["authority_receipts"][0]["kind"], "global-rules")
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "pass")
        self.assertEqual(statuses["GVL-TYPE-001"], "pass")
        self.assertEqual(statuses["GVL-DATA-001"], "not-applicable")
        self.assertEqual(statuses["GVL-MOTION-001"], "not-applicable")

    def test_disabled_item_returns_empty_without_dependencies(self) -> None:
        fixture = self.fixture()
        item = fixture.item()
        artifact = article_artifact()
        with mock.patch.dict(os.environ, {SOURCE_ROOT_ENV: ""}):
            result = gvv.validate_global_visual_item(
                item,
                artifact,
                shared_root=fixture.base / "missing-source",
                runtime_path=fixture.base / "missing-runtime.json",
                schema_root=fixture.base / "missing-schema",
            )
        self.assertEqual(result, [])

    def test_enabled_item_requires_explicit_root(self) -> None:
        fixture = self.fixture()
        item, artifact = self._enabled_item(fixture)
        with mock.patch.dict(os.environ, {SOURCE_ROOT_ENV: ""}):
            errors = gvv.validate_global_visual_item(
                item,
                artifact,
                runtime_path=fixture.runtime_path,
                schema_root=fixture.projection,
            )
        self.assertTrue(errors)
        self.assertIn("shared visual source root", errors[0][1])

    def test_declared_context_cannot_bypass_lock(self) -> None:
        fixture = self.fixture()
        item, artifact = self._enabled_item(fixture)
        broken_lock = {
            "schema_version": "shared-visual-design-system-lock.v1",
            "package": "@lightcolor/shared-visual-design-system",
            "consumer": "content-visual-studio",
            "package_version": "1.1.0",
            "files": {},
        }
        fixture.write_lock(broken_lock)
        with self.assertRaises(ValueError) as caught:
            fixture.context(item=item, artifact=artifact)
        self.assertIn("lock", str(caught.exception).lower())
        errors = fixture.validate_item(item, artifact)
        self.assertTrue(errors)
        self.assertIn("lock", errors[0][1].lower())

    def test_validate_item_reports_ruleset_error(self) -> None:
        fixture = self.fixture()
        broken = fixture.context()
        broken["ruleset"]["sha256"] = "0" * 64
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = broken
        artifact = article_artifact()
        artifact["renderer_options"] = {"global_visual_v1": True}
        errors = fixture.validate_item(item, artifact)
        self.assertTrue(errors)
        self.assertTrue(any("ruleset.sha256" in message for _, message in errors))

    # -- ruleset / profile negatives ---------------------------------------

    def _context_errors(self, fixture: VisualFixture, context: dict) -> list[str]:
        return gvv.validate_runtime_context(context, None, **fixture.kwargs())

    def test_ruleset_hash_mismatch_fails(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        context["ruleset"]["sha256"] = "0" * 64
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("ruleset.sha256: ruleset hash mismatch" in error for error in errors), errors)

    def test_ruleset_version_mismatch_fails(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        context["ruleset"]["version"] = "9.9.9"
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("ruleset.version: ruleset version mismatch" in error for error in errors), errors)

    def test_ruleset_version_mismatch_from_runtime_config_fails(self) -> None:
        fixture = self.fixture()
        runtime = copy.deepcopy(RUNTIME)
        runtime["ruleset_version"] = "9.9.9"
        fixture.write_json(fixture.runtime_path, runtime)
        context = fixture.context()
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("ruleset.version" in error for error in errors), errors)

    def test_ruleset_reference_escape_fails(self) -> None:
        fixture = self.fixture()
        for bad_ref in ("../outside.json", str(fixture.base / "outside.json"), "https://example.invalid/ruleset.json"):
            with self.subTest(ref=bad_ref):
                context = fixture.context()
                context["ruleset"]["ref"] = bad_ref
                errors = self._context_errors(fixture, context)
                self.assertTrue(any("could not verify ruleset" in error for error in errors), errors)

    def test_malformed_ruleset_fails(self) -> None:
        fixture = self.fixture()
        broken = b"{not json"
        # A malformed document must be a lock-declared member for the parse
        # failure to be the reason for refusal (not merely an unlocked file).
        fixture.add_locked_member("contracts/broken.json", broken)
        context = fixture.context()
        context["ruleset"] = {
            "ref": "contracts/broken.json",
            "version": "1.0.0",
            "sha256": _sha(broken),
        }
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("could not verify ruleset" in error for error in errors), errors)
        self.assertTrue(any("not valid JSON" in error for error in errors), errors)

    def test_unlocked_declared_ruleset_is_refused(self) -> None:
        fixture = self.fixture()
        alternate = b'{"version": "1.0.0", "guidelines": []}'
        # The extra file exists in the source root but was never added to the lock.
        fixture.write(fixture.source / "contracts" / "alternate-unlocked.json", alternate)
        self.assertNotIn("contracts/alternate-unlocked.json", fixture.lock_files())

        context = fixture.context()
        context["ruleset"] = {
            "ref": "contracts/alternate-unlocked.json",
            "version": "1.0.0",
            "sha256": _sha(alternate),
        }
        # The caller-supplied hash exactly matches the consumed bytes; the old
        # caller-hash-only check accepted this unlocked file.
        self.assertEqual(context["ruleset"]["sha256"], _sha(alternate))
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("could not verify ruleset" in error for error in errors), errors)
        self.assertTrue(any("not declared" in error for error in errors), errors)

        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = context
        with self.assertRaises(ValueError):
            fixture.receipt(item=item)

    def test_read_swap_after_stale_lock_check_is_refused(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        old_guidelines = (fixture.source / GUIDELINES_NAME).read_bytes()
        swapped = b'{"version": "1.0.0", "guidelines": []}'
        # Change the consumed source after the context/lock were observed.
        fixture.write(fixture.source / GUIDELINES_NAME, swapped)
        context["ruleset"]["sha256"] = _sha(swapped)
        self.assertEqual(
            fixture.lock_files()[GUIDELINES_NAME]["sha256"], _sha(old_guidelines)
        )
        self.assertNotEqual(context["ruleset"]["sha256"], _sha(old_guidelines))

        errors = self._context_errors(fixture, context)
        self.assertTrue(any("could not verify ruleset" in error for error in errors), errors)
        self.assertTrue(any("hash mismatch" in error for error in errors), errors)

        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = context
        # Simulate a lock check that saw the old, still-pinned bytes. The
        # consumption path must still refuse the changed bytes.
        with mock.patch.object(gvv, "validate_lock", return_value=[]):
            with self.assertRaises(ValueError):
                fixture.receipt(item=item)

    def test_custom_additional_locked_member_is_allowed(self) -> None:
        fixture = self.fixture()
        custom = b'{"version": "3.2.1", "guidelines": []}'
        fixture.add_locked_member("contracts/custom-ruleset.json", custom)
        self.assertEqual(
            lock_module.validate_lock(
                fixture.source,
                lock_path=fixture.lock_path,
                projection_root=fixture.projection,
            ),
            [],
        )
        context = fixture.context()
        context["ruleset"] = {
            "ref": "contracts/custom-ruleset.json",
            "version": "3.2.1",
            "sha256": _sha(custom),
        }
        self.assertEqual(self._context_errors(fixture, context), [])

        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = context
        self.assertEqual(fixture.receipt(item=item)["result"], "pass")

    def test_media_profile_mapping_fails_closed(self) -> None:
        fixture = self.fixture()
        with self.assertRaises(ValueError):
            gvv.build_runtime_context(
                fixture.item(), article_artifact(media_adapter="hologram"), **fixture.kwargs()
            )
        context = fixture.context()
        context["conformance_profile"] = "web.v1"
        errors = gvv.validate_runtime_context(context, article_artifact(), **fixture.kwargs())
        self.assertTrue(any("conformance_profile" in error for error in errors), errors)

    # -- exceptions ---------------------------------------------------------

    def test_exceptions_known_future_pass(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        context["exceptions"] = [exception_entry("chinese-typography", "2999-01-01T00:00:00Z")]
        errors = self._context_errors(fixture, context)
        self.assertFalse(any("exceptions." in error for error in errors), errors)

    def test_exceptions_unknown_rule_fails(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        context["exceptions"] = [exception_entry("made-up-rule", "2999-01-01T00:00:00Z")]
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("unknown rule" in error for error in errors), errors)

    def test_exceptions_expired_fails(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        context["exceptions"] = [exception_entry("chinese-typography", "2000-01-01T00:00:00Z")]
        errors = self._context_errors(fixture, context)
        self.assertTrue(any("exception is expired" in error for error in errors), errors)

    def test_exceptions_naive_and_invalid_dates_fail_without_success(self) -> None:
        fixture = self.fixture()
        for bad_expiry in ("2999-01-01T00:00:00", "not-a-date"):
            with self.subTest(expires_at=bad_expiry):
                context = fixture.context()
                context["exceptions"] = [exception_entry("chinese-typography", bad_expiry)]
                errors = self._context_errors(fixture, context)
                self.assertTrue(any("invalid date-time" in error for error in errors), errors)

    def test_invalid_context_enums_fail_closed(self) -> None:
        fixture = self.fixture()
        cases = []
        context = fixture.context()
        context["authority_scope"] = "unknown-scope"
        cases.append(context)
        context = fixture.context()
        context["motion"] = {"mode": "sometimes"}
        cases.append(context)
        for index, context in enumerate(cases):
            with self.subTest(case=index):
                errors = self._context_errors(fixture, context)
                self.assertTrue(errors)

    # -- brand-bound context ------------------------------------------------

    def test_brand_bound_context_and_receipt(self) -> None:
        fixture = self.fixture(brand=True)
        item = fixture.brand_item()
        context = fixture.context(item=item, artifact=article_artifact())
        self.assertEqual(context["authority_scope"], "brand-bound")
        authority = context["brand_authority"]
        self.assertEqual(authority["profile_id"], "synthetic-brand.v1")
        self.assertEqual(authority["profile_version"], "2.0.0")
        self.assertEqual(authority["authority_version"], "2.0.0")
        self.assertEqual(
            authority["projection_sha256"],
            _sha(fixture.brand_paths["tokens"].read_bytes()),
        )
        self.assertEqual(
            authority["qa_receipt_sha256"],
            _sha(fixture.brand_paths["receipt"].read_bytes()),
        )
        receipt = fixture.receipt(item=item)
        self.assertEqual(receipt["result"], "pass")
        kinds = [entry["kind"] for entry in receipt["authority_receipts"]]
        self.assertEqual(kinds, ["global-rules", "brand-authority"])

    def test_brand_non_passing_receipt_fails(self) -> None:
        fixture = self.fixture(brand=True)
        receipt_document = copy.deepcopy(BRAND_RECEIPT)
        receipt_document["qa"] = {"status": "fail"}
        fixture.write_json(fixture.brand_paths["receipt"], receipt_document)
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")
        self.assertEqual(receipt["result"], "fail")

    def test_brand_token_hash_drift_fails(self) -> None:
        fixture = self.fixture(brand=True)
        context = fixture.context(item=fixture.brand_item())
        fixture.write(fixture.brand_paths["tokens"], b'{"schema_version": "brand-tokens.v1", "drift": true}')
        item = fixture.brand_item()
        item["visual"]["design_system"]["global_visual"] = context
        receipt = fixture.receipt(item=item)
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")
        self.assertEqual(receipt["result"], "fail")

    def test_brand_source_date_stale_receipt_fails(self) -> None:
        fixture = self.fixture(brand=True)
        profile = copy.deepcopy(BRAND_PROFILE)
        profile["meta"] = {"source_updated_at": "2026-03-01T00:00:00Z"}
        fixture.write_json(fixture.brand_paths["profile"], profile)
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")

    def test_brand_naive_receipt_date_fails(self) -> None:
        fixture = self.fixture(brand=True)
        receipt_document = copy.deepcopy(BRAND_RECEIPT)
        receipt_document["created_at"] = "2026-02-01T00:00:00"
        fixture.write_json(fixture.brand_paths["receipt"], receipt_document)
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")

    def test_brand_expired_receipt_fails(self) -> None:
        fixture = self.fixture(brand=True)
        receipt_document = copy.deepcopy(BRAND_RECEIPT)
        receipt_document["qa"] = {"status": "pass", "expires_at": "2000-01-01T00:00:00Z"}
        fixture.write_json(fixture.brand_paths["receipt"], receipt_document)
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")

    def test_brand_profile_version_mismatch_fails(self) -> None:
        fixture = self.fixture(brand=True)
        receipt_document = copy.deepcopy(BRAND_RECEIPT)
        receipt_document["profile_version"] = "1.0.0"
        fixture.write_json(fixture.brand_paths["receipt"], receipt_document)
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")

    def test_brand_missing_receipt_fails_closed(self) -> None:
        fixture = self.fixture(brand=True)
        fixture.brand_paths["receipt"].unlink()
        with self.assertRaises(ValueError):
            fixture.context(item=fixture.brand_item())

    def test_brand_invalid_receipt_json_fails_closed(self) -> None:
        fixture = self.fixture(brand=True)
        fixture.write(fixture.brand_paths["receipt"], b"{not json")
        receipt = fixture.receipt(item=fixture.brand_item())
        statuses = {finding["diagnostic_id"]: finding["status"] for finding in receipt["findings"]}
        self.assertEqual(statuses["GVL-AUTH-001"], "fail")

    def test_brand_record_requires_explicit_tokens_ref(self) -> None:
        fixture = self.fixture(brand=True)
        registry = copy.deepcopy(BRAND_REGISTRY)
        del registry["brand_authorities"]["synthetic-brand.v1"]["tokens_ref"]
        fixture.write_json(fixture.brand_paths["registry"], registry)
        with self.assertRaises(ValueError):
            fixture.context(item=fixture.brand_item())

    def test_brand_record_cannot_escape_shared_root(self) -> None:
        fixture = self.fixture(brand=True)
        registry = copy.deepcopy(BRAND_REGISTRY)
        registry["brand_authorities"]["synthetic-brand.v1"]["local_root"] = "../outside-brand"
        fixture.write_json(fixture.brand_paths["registry"], registry)
        with self.assertRaises(ValueError):
            fixture.context(item=fixture.brand_item())

    def test_no_implicit_brand_authority(self) -> None:
        fixture = self.fixture()
        item = fixture.item()
        item["visual"]["visual_profile"] = "synthetic-brand.v1"
        item["topic"] = "insurance guidance for a named account"
        context = fixture.context(item=item)
        self.assertEqual(context["authority_scope"], "global-only")
        self.assertNotIn("brand_authority", context)

    # -- typography / data / icons / imagery / motion -----------------------

    def _finding(self, receipt: dict, diagnostic_id: str) -> dict:
        matches = [finding for finding in receipt["findings"] if finding["diagnostic_id"] == diagnostic_id]
        self.assertEqual(len(matches), 1, receipt["findings"])
        return matches[0]

    def _first_by_rule(self, receipt: dict, rule_id: str) -> dict:
        matches = [finding for finding in receipt["findings"] if finding["rule_id"] == rule_id]
        self.assertEqual(len(matches), 1, receipt["findings"])
        return matches[0]

    def test_typography_outcomes(self) -> None:
        fixture = self.fixture()
        cases = [
            ({"status": "pass", "ref": "synthetic/type.txt"}, "pass", "pass"),
            ({"status": "fail", "message": "synthetic typography failure"}, "fail", "fail"),
            ({"status": "needs-review"}, "needs-review", "review-required"),
            ({"status": "verified"}, "fail", "fail"),
            ({"status": "pass"}, "needs-review", "review-required"),
        ]
        for typography, expected_status, expected_result in cases:
            with self.subTest(typography=typography):
                receipt = fixture.receipt(typography=typography)
                finding = self._finding(receipt, "GVL-TYPE-001")
                self.assertEqual(finding["status"], expected_status)
                self.assertEqual(receipt["result"], expected_result)

    def test_data_visual_outcomes(self) -> None:
        fixture = self.fixture()
        not_applicable = fixture.receipt()
        self.assertEqual(self._finding(not_applicable, "GVL-DATA-001")["status"], "not-applicable")

        valid = fixture.receipt(
            artifact=infographic_artifact(),
            data_status={"normalized_spec_valid": True, "message": "synthetic valid chart"},
        )
        self.assertEqual(self._finding(valid, "GVL-DATA-001")["status"], "pass")
        self.assertEqual(valid["result"], "pass")

        invalid = fixture.receipt(
            artifact=infographic_artifact(),
            data_status={"normalized_spec_valid": False, "message": "synthetic invalid chart"},
        )
        self.assertEqual(self._finding(invalid, "GVL-DATA-001")["status"], "fail")
        self.assertEqual(invalid["result"], "fail")

    def test_icon_outcomes_remain_report_only(self) -> None:
        fixture = self.fixture()
        cases = [
            ({"semantic_id": "dressing-wet", "copy_anchor": "敷料潮湿", "meaning": "敷料潮湿图标"}, "pass"),
            ({"semantic_id": "not-registered", "copy_anchor": "x", "meaning": "y"}, "fail"),
            ({"semantic_id": "stable-keep-closed", "copy_anchor": "x", "meaning": "y"}, "fail"),
            ({"semantic_id": "dressing-wet", "meaning": "y"}, "fail"),
            ({"semantic_id": "dressing-wet", "copy_anchor": "x"}, "fail"),
        ]
        for binding, expected_status in cases:
            with self.subTest(binding=binding):
                item = fixture.item()
                item["visual"]["semantic_visual_map"] = [{"bindings": [binding]}]
                receipt = fixture.receipt(item=item)
                finding = self._first_by_rule(receipt, "iconography-grammar")
                self.assertTrue(finding["diagnostic_id"].startswith("GVL-ICON"))
                self.assertEqual(finding["status"], expected_status)
                self.assertEqual(finding["enforcement"], "report-only")
                self.assertEqual(receipt["result"], "pass")

    def test_icon_diagnostic_ids(self) -> None:
        fixture = self.fixture()
        cases = [
            ({"semantic_id": "not-registered", "copy_anchor": "x", "meaning": "y"}, "GVL-ICON-001"),
            ({"semantic_id": "stable-keep-closed", "copy_anchor": "x", "meaning": "y"}, "GVL-ICON-002"),
            ({"semantic_id": "dressing-wet", "meaning": "y"}, "GVL-ICON-003"),
            ({"semantic_id": "dressing-wet", "copy_anchor": "x"}, "GVL-ICON-004"),
        ]
        for binding, diagnostic_id in cases:
            with self.subTest(binding=binding):
                item = fixture.item()
                item["visual"]["semantic_visual_map"] = [{"bindings": [binding]}]
                receipt = fixture.receipt(item=item)
                self.assertEqual(self._finding(receipt, diagnostic_id)["status"], "fail")

    def _imagery_asset(self, **overrides) -> dict:
        asset = {
            "asset_id": "asset-synthetic-001",
            "ref": "synthetic/photo.txt",
            "visual_role": "documentary-photo",
            "asset_type": "photo",
            "rights_status": "verified",
            "privacy_status": "not-applicable",
            "evidence_status": "verified",
            "treatment": "documentary",
            "text_overlay_policy": "none",
        }
        asset.update(overrides)
        return asset

    def test_imagery_outcomes(self) -> None:
        fixture = self.fixture()
        cases = [
            (self._imagery_asset(), "pass", "pass"),
            (self._imagery_asset(visual_role="evidence-photo", asset_type="stock-photo"), "fail", "pass"),
            (self._imagery_asset(rights_status=None), "fail", "pass"),
            (self._imagery_asset(privacy_status=None), "fail", "pass"),
            (self._imagery_asset(privacy_status="needs-review"), "fail", "pass"),
            (
                self._imagery_asset(text_overlay_policy="safe-area-only", safe_crop=None),
                "fail",
                "pass",
            ),
            (self._imagery_asset(fit_strategy="focal-cover", focal_point=None), "fail", "pass"),
            (
                self._imagery_asset(
                    visual_role="explanatory-illustration",
                    asset_type="generated-image",
                    treatment="annotated",
                ),
                "fail",
                "pass",
            ),
            (
                self._imagery_asset(visual_role="evidence-photo", evidence_status="unknown"),
                "fail",
                "pass",
            ),
            (
                self._imagery_asset(evidence_status="unknown"),
                "needs-review",
                "review-required",
            ),
        ]
        for asset, expected_status, expected_result in cases:
            with self.subTest(asset=asset):
                item = fixture.item()
                item["visual"]["assets"] = [asset]
                receipt = fixture.receipt(item=item)
                finding = self._first_by_rule(receipt, "imagery-and-illustration-grammar")
                self.assertTrue(finding["diagnostic_id"].startswith("GVL-IMAGE"))
                self.assertEqual(finding["status"], expected_status)
                self.assertEqual(finding["enforcement"], "report-only")
                self.assertEqual(receipt["result"], expected_result)

    def test_imagery_diagnostic_ids(self) -> None:
        fixture = self.fixture()
        cases = [
            (
                self._imagery_asset(visual_role="evidence-photo", asset_type="stock-photo"),
                "GVL-IMAGE-002",
            ),
            (
                self._imagery_asset(text_overlay_policy="safe-area-only", safe_crop=None),
                "GVL-IMAGE-003",
            ),
            (self._imagery_asset(rights_status=None), "GVL-IMAGE-004"),
            (
                self._imagery_asset(
                    visual_role="explanatory-illustration",
                    asset_type="generated-image",
                    treatment="annotated",
                ),
                "GVL-IMAGE-005",
            ),
        ]
        for asset, diagnostic_id in cases:
            with self.subTest(diagnostic_id=diagnostic_id):
                item = fixture.item()
                item["visual"]["assets"] = [asset]
                receipt = fixture.receipt(item=item)
                self.assertEqual(self._finding(receipt, diagnostic_id)["status"], "fail")

    def test_generated_image_opt_in_is_record_consistency(self) -> None:
        fixture = self.fixture()
        item = fixture.item()
        item["visual"]["assets"] = [
            self._imagery_asset(
                visual_role="explanatory-illustration",
                asset_type="generated-image",
                treatment="annotated",
            )
        ]
        record = {
            "policy": routing.AI_IMAGE_POLICY,
            "explicit_user_request": True,
            "request_text": "请模型生成图片",
            "matched_trigger": "模型生成图片",
        }
        self.assertFalse(routing.is_ai_image_generation_authorized(item["visual"].get("ai_image_generation")))
        self.assertTrue(routing.is_ai_image_generation_authorized(record))
        item["visual"]["ai_image_generation"] = record
        receipt = fixture.receipt(item=item)
        self.assertEqual(self._finding(receipt, "GVL-IMAGE-001")["status"], "pass")
        self.assertEqual(receipt["result"], "pass")

    def test_motion_outcomes(self) -> None:
        fixture = self.fixture()
        static_receipt = fixture.receipt()
        self.assertEqual(self._finding(static_receipt, "GVL-MOTION-001")["status"], "not-applicable")

        web_context = fixture.context(artifact=web_artifact())
        web_context["motion"] = {
            "mode": "explicit",
            "purpose": "synthetic state change",
            "static_fallback_ref": "synthetic/static.html",
        }
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = web_context
        explicit = fixture.receipt(item=item, artifact=web_artifact())
        self.assertEqual(self._finding(explicit, "GVL-MOTION-001")["status"], "needs-review")
        self.assertEqual(explicit["result"], "review-required")

        missing_fallback = copy.deepcopy(web_context)
        missing_fallback["motion"] = {"mode": "explicit", "purpose": "synthetic state change"}
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = missing_fallback
        invalid = fixture.receipt(item=item, artifact=web_artifact())
        self.assertEqual(self._finding(invalid, "GVL-MOTION-001")["status"], "fail")
        self.assertEqual(invalid["result"], "review-required")

    def test_motion_requires_explicit_web_context(self) -> None:
        fixture = self.fixture()
        article_context = fixture.context()
        article_context["motion"] = {
            "mode": "explicit",
            "purpose": "synthetic state change",
            "static_fallback_ref": "synthetic/static.html",
        }
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = article_context
        with self.assertRaises(ValueError):
            fixture.receipt(item=item, artifact=article_artifact())

        invalid_context = fixture.context()
        invalid_context["motion"] = {"mode": "sometimes"}
        item = fixture.item()
        item["visual"]["design_system"]["global_visual"] = invalid_context
        with self.assertRaises(ValueError):
            fixture.receipt(item=item, artifact=article_artifact())

    # -- media QA evidence qualification ------------------------------------

    def test_media_qa_pass_and_fail(self) -> None:
        fixture = self.fixture()
        failing = fixture.receipt(
            media_qa={"profile_id": "article.v1", "hard_checks": [{"name": "synthetic", "status": "fail"}], "result": "fail"}
        )
        self.assertEqual(failing["result"], "fail")

    def test_media_qa_missing_or_nonpassing_never_passes(self) -> None:
        fixture = self.fixture()
        cases = [
            {"profile_id": "article.v1", "hard_checks": [], "result": "needs-review"},
            {"profile_id": "article.v1", "hard_checks": [], "result": "unknown"},
            {"profile_id": "article.v1", "hard_checks": []},
            {"profile_id": "article.v1", "hard_checks": [], "result": None},
            {},
            None,  # explicit None must reach the implementation, not the default pass fixture
        ]
        for media_qa in cases:
            with self.subTest(media_qa=media_qa):
                with self.assertRaises(ValueError):
                    fixture.receipt(media_qa=media_qa)

    # -- Playwright and no-side-effect boundaries --------------------------

    def test_playwright_default_refusal(self) -> None:
        fixture = self.fixture()
        with mock.patch.dict(os.environ, {"PLAYWRIGHT_PACKAGE_JSON": ""}):
            with self.assertRaises(ValueError):
                gvv.resolve_playwright_package(runtime_path=fixture.runtime_path)

    def test_playwright_env_and_explicit_path(self) -> None:
        fixture = self.fixture()
        package = fixture.base / "node_modules" / "playwright" / "package.json"
        fixture.write_json(package, {"name": "playwright", "version": "1.61.1"})
        imported_before = "playwright" in sys.modules
        with mock.patch.dict(os.environ, {"PLAYWRIGHT_PACKAGE_JSON": str(package)}):
            self.assertEqual(
                gvv.resolve_playwright_package(runtime_path=fixture.runtime_path),
                package.resolve(),
            )
        self.assertEqual(
            gvv.resolve_playwright_package(
                runtime_path=fixture.runtime_path, package_json=package
            ),
            package.resolve(),
        )
        self.assertEqual("playwright" in sys.modules, imported_before)

    def test_playwright_rejects_wrong_identity(self) -> None:
        fixture = self.fixture()
        for document in (
            {"name": "puppeteer", "version": "1.61.1"},
            {"name": "playwright", "version": "0.0.1"},
            {"name": "playwright"},
        ):
            with self.subTest(document=document):
                package = fixture.base / "synthetic-package.json"
                fixture.write_json(package, document)
                with mock.patch.dict(os.environ, {"PLAYWRIGHT_PACKAGE_JSON": ""}):
                    with self.assertRaises(ValueError):
                        gvv.resolve_playwright_package(
                            runtime_path=fixture.runtime_path, package_json=package
                        )

    def test_validation_makes_no_network_or_subprocess_call(self) -> None:
        fixture = self.fixture()
        item, artifact = self._enabled_item(fixture)
        with mock.patch.object(socket, "socket") as socket_mock, mock.patch.object(
            subprocess, "Popen"
        ) as popen_mock, mock.patch.object(subprocess, "run") as run_mock:
            receipt = fixture.receipt()
            self.assertEqual(receipt["result"], "pass")
            self.assertEqual(fixture.validate_item(item, artifact), [])
        socket_mock.assert_not_called()
        popen_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_unprovided_external_schema_ref_does_not_fetch(self) -> None:
        fixture = self.fixture()
        bad_schema_root = fixture.base / "bad-schema"
        # Keep the valid lock/projection so only the external $ref is unusual.
        shutil.copytree(fixture.projection, bad_schema_root)
        bad_schema = copy.deepcopy(GLOBAL_CONTEXT_SCHEMA)
        bad_schema["properties"]["remote_probe"] = {
            "$ref": "https://example.invalid/unprovided-remote.json"
        }
        fixture.write_json(
            bad_schema_root / "schemas" / "global-visual-context.v1.schema.json", bad_schema
        )
        context = fixture.context()
        context["remote_probe"] = 1
        kwargs = fixture.kwargs()
        kwargs["schema_root"] = bad_schema_root
        with mock.patch.object(socket, "socket") as socket_mock, mock.patch.object(
            socket, "getaddrinfo"
        ) as dns_mock, mock.patch.object(urllib.request, "urlopen") as urlopen_mock:
            errors = gvv.validate_runtime_context(context, None, **kwargs)
        self.assertTrue(
            any("schema validation could not complete" in error for error in errors), errors
        )
        socket_mock.assert_not_called()
        dns_mock.assert_not_called()
        urlopen_mock.assert_not_called()

    def test_missing_registry_capability_refuses_without_fallback(self) -> None:
        fixture = self.fixture()
        with mock.patch.object(gvv, "_EMPTY_REGISTRY", None), mock.patch.object(
            gvv, "Draft202012Validator"
        ) as constructor, mock.patch.object(
            urllib.request, "urlopen"
        ) as urlopen_mock, mock.patch.object(
            socket, "getaddrinfo"
        ) as dns_mock:
            errors = gvv._schema_instance_errors(
                GLOBAL_CONTEXT_SCHEMA, {}, "synthetic context"
            )
        constructor.assert_not_called()
        urlopen_mock.assert_not_called()
        dns_mock.assert_not_called()
        self.assertTrue(any("refusing" in error for error in errors), errors)

        context = fixture.context()
        with mock.patch.object(gvv, "_EMPTY_REGISTRY", None):
            errors = gvv.validate_runtime_context(context, None, **fixture.kwargs())
        self.assertTrue(
            any("schema validation could not complete" in error for error in errors), errors
        )
        self.assertTrue(any("refusing" in error for error in errors), errors)

    def test_unsupported_registry_constructor_refuses_without_fallback(self) -> None:
        calls: list[dict] = []

        def fake_validator(schema, *args, **kwargs):
            calls.append(dict(kwargs))
            if "registry" not in kwargs:
                raise AssertionError("fallback validator without a registry was constructed")
            raise TypeError("registry keyword is unsupported by this fake")

        with mock.patch.object(gvv, "Draft202012Validator", fake_validator):
            with mock.patch.object(
                urllib.request, "urlopen"
            ) as urlopen_mock, mock.patch.object(
                socket, "getaddrinfo"
            ) as dns_mock:
                errors = gvv._schema_instance_errors(
                    GLOBAL_CONTEXT_SCHEMA, {}, "synthetic context"
                )
        self.assertEqual(len(calls), 1)
        self.assertIn("registry", calls[0])
        self.assertTrue(
            any("does not support" in error and "refusing" in error for error in errors),
            errors,
        )
        urlopen_mock.assert_not_called()
        dns_mock.assert_not_called()

    def test_internal_defs_validate_with_empty_registry(self) -> None:
        schema = {
            "$defs": {"label": {"type": "string"}},
            "type": "object",
            "properties": {"label": {"$ref": "#/$defs/label"}},
        }
        self.assertEqual(
            gvv._schema_instance_errors(schema, {"label": "ok"}, "synthetic context"), []
        )
        self.assertTrue(
            gvv._schema_instance_errors(schema, {"label": 1}, "synthetic context")
        )

    # -- captured bytes and artifact checks --------------------------------

    def test_ruleset_bytes_are_read_once_per_validation(self) -> None:
        fixture = self.fixture()
        context = fixture.context()
        real_read = gvv._read_bytes
        calls: list[Path] = []

        def recording(path):
            calls.append(Path(path))
            return real_read(path)

        # Ruleset consumption now happens through the lock module's pinned-byte
        # loader, so record reads in both modules.
        with mock.patch.object(gvv, "_read_bytes", side_effect=recording), mock.patch.object(
            lock_module, "_read_bytes", side_effect=recording
        ):
            errors = gvv.validate_runtime_context(context, None, **fixture.kwargs())
        self.assertEqual(errors, [])
        ruleset_path = (fixture.source / GUIDELINES_NAME).resolve()
        self.assertEqual(sum(1 for path in calls if path == ruleset_path), 1)

    def test_output_bytes_are_read_once(self) -> None:
        fixture = self.fixture()
        output = fixture.output()
        real_read = gvv._read_bytes
        calls: list[Path] = []

        def recording(path):
            calls.append(Path(path))
            return real_read(path)

        with mock.patch.object(gvv, "_read_bytes", side_effect=recording):
            receipt = fixture.receipt(output_path=output)
        self.assertEqual(receipt["output"]["sha256"], _sha(output.read_bytes()))
        self.assertEqual(sum(1 for path in calls if path == output), 1)

    def test_missing_or_empty_output_fails_closed(self) -> None:
        fixture = self.fixture()
        with self.assertRaises(ValueError):
            fixture.receipt(output_path=fixture.base / "missing-output.png")
        empty = fixture.output(name="empty-output.png", data=b"")
        with self.assertRaises(ValueError):
            fixture.receipt(output_path=empty)

    # -- helper boundary ----------------------------------------------------

    def test_visual_asset_routing_record_consistency_is_not_consent(self) -> None:
        gate = {
            "policy": routing.AI_IMAGE_POLICY,
            "explicit_user_request": True,
            "request_text": "AI 生图",
            "matched_trigger": "AI 生图",
        }
        self.assertTrue(routing.is_ai_image_generation_authorized(gate))
        forged = dict(gate, matched_trigger="模型生成图片")
        self.assertFalse(routing.is_ai_image_generation_authorized(forged))
        self.assertFalse(
            routing.is_ai_image_generation_authorized(
                {"explicit_user_request": True, "request_text": "no trigger phrase"}
            )
        )
        self.assertFalse(routing.resolve_ai_image_generation("please draw a picture")["allowed"])
        self.assertTrue(
            routing.validate_ai_image_generation_opt_in(
                {"visual": {"render_recipe": {"renderer": "imagegen"}}}
            )
        )
        self.assertEqual(routing.validate_ai_image_generation_opt_in({"visual": {"assets": []}}), [])


if __name__ == "__main__":
    unittest.main()
