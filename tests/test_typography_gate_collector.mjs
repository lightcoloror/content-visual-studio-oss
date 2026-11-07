#!/usr/bin/env node
/* Targeted synthetic-only unit test: typography_gate_collector.mjs.
 *
 * Node + an explicitly synthetic mock DOM. No browser, Playwright/Puppeteer
 * bridge, service, network or real page rendering. The two bridge modules are
 * not in the public baseline, so their parity is recorded as an honest skip.
 */
import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { fileURLToPath, pathToFileURL } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, "..");
const SCRIPTS = path.join(ROOT, "scripts");
const MODULE_PATH = path.join(SCRIPTS, "typography_gate_collector.mjs");
const WORKSPACE = process.env.CANDIDATE_TEST_WORKSPACE || path.join(ROOT, "..", "synthetic");
fs.mkdirSync(WORKSPACE, { recursive: true });

const collected = await import(pathToFileURL(MODULE_PATH).href);
const { TAG_ROLE_FALLBACK, loadTypographyGateBinding, collectTypographyGateInPage } = collected;

const results = [];
function check(name, fn) {
  try {
    fn();
    results.push({ name, status: "pass" });
  } catch (error) {
    results.push({ name, status: "fail", error: String(error && error.message ? error.message : error) });
  }
}
function skip(name, reason) {
  results.push({ name, status: "skip", reason });
}

const POLICY = {
  schema: "lucas.typography_gates.v1",
  policy_id: "synthetic-typography-policy-for-unit-tests",
  note: "SYNTHETIC TEST-ONLY policy. Not the canonical Owner typography policy.",
  synthetic_only: true,
  profiles: {
    "synthetic-profile-v1": {
      hard_gate: true,
      viewport: { width: 1200, height: 800 },
      preview: { width: 600 },
      required_roles: ["primary_headline", "body"],
      roles: {
        primary_headline: { min_font_px: 24 },
        body: { min_font_px: 12 },
        scene_title: { min_font_px: 18 },
      },
    },
  },
};
const POLICY_PATH = path.join(WORKSPACE, "synthetic-typography-policy.v1.json");
fs.writeFileSync(POLICY_PATH, JSON.stringify(POLICY, null, 2) + "\n", "utf8");
const POLICY_SHA = crypto.createHash("sha256").update(fs.readFileSync(POLICY_PATH)).digest("hex");
const PROFILE_ID = "synthetic-profile-v1";
function loadBinding(expectedSha256 = POLICY_SHA, policyPath = POLICY_PATH, profileId = PROFILE_ID) {
  return loadTypographyGateBinding({ policyPath, expectedSha256, profileId });
}

/* ---- minimal synthetic DOM for the serialized in-page function ---- */
class Matrix {
  constructor(a = 1, b = 0, c = 0, d = 1, e = 0, f = 0) {
    Object.assign(this, { a, b, c, d, e, f });
  }
  get is2D() { return true; }
  scale(sx, sy = sx) { return new Matrix(this.a * sx, this.b * sx, this.c * sy, this.d * sy); }
  multiply(other) {
    return new Matrix(
      this.a * other.a + this.c * other.b,
      this.b * other.a + this.d * other.b,
      this.a * other.c + this.c * other.d,
      this.b * other.c + this.d * other.d,
    );
  }
}
class SvgGraphicsElement {}

function node(tagName, options = {}, parent = null) {
  return {
    tagName: tagName.toUpperCase(),
    parentElement: parent,
    attributes: options.attributes || {},
    style: {
      display: "block", visibility: "visible", fontSize: "14px",
      transform: "none", scale: "none", zoom: "1",
      overflowX: "visible", overflowY: "visible",
      ...(options.style || {}),
    },
    rect: options.rect || { x: 0, y: 0, width: 200, height: 20 },
    clientWidth: options.clientWidth ?? 200,
    clientHeight: options.clientHeight ?? 20,
    scrollWidth: options.scrollWidth ?? 200,
    scrollHeight: options.scrollHeight ?? 20,
    getAttribute(name) {
      return Object.prototype.hasOwnProperty.call(this.attributes, name) ? this.attributes[name] : null;
    },
    getBoundingClientRect() { return this.rect; },
  };
}

function sandboxFor(textNodes) {
  let index = 0;
  const sandbox = {
    DOMMatrix: Matrix,
    SVGGraphicsElement: SvgGraphicsElement,
    NodeFilter: { SHOW_TEXT: 4 },
    getComputedStyle: (element) => element.style,
    document: {
      createTreeWalker: () => ({
        nextNode: () => (index < textNodes.length ? textNodes[index++] : null),
      }),
    },
  };
  return sandbox;
}

const SOURCE = collectTypographyGateInPage.toString();
function runInjected(sandbox, root, binding, extra = {}) {
  const injected = vm.runInNewContext(`(${SOURCE})`, sandbox);
  return injected(root, {
    tagRoleFallback: TAG_ROLE_FALLBACK,
    roles: binding.roles,
    requiredRoles: binding.required_roles,
    binding,
    ...extra,
  });
}
function rootNode(extra = {}) {
  return node("div", {
    rect: { x: 0, y: 0, width: 1200, height: 800 },
    clientWidth: 1200, clientHeight: 800, scrollHeight: 800,
    style: { fontSize: "16px" },
    ...extra,
  });
}

/* ---- binding loader boundaries ---- */
check("TAG_ROLE_FALLBACK mapping is exact and frozen", () => {
  assert.deepEqual(TAG_ROLE_FALLBACK, {
    h1: "primary_headline", h2: "scene_title", h3: "scene_title", h4: "scene_title",
    p: "body", li: "multi_column_body", blockquote: "body",
    figcaption: "disclosure", small: "disclosure",
  });
  assert.equal(Object.isFrozen(TAG_ROLE_FALLBACK), true);
  assert.throws(() => { TAG_ROLE_FALLBACK.h1 = "changed"; });
});

check("module imports only Node stdlib modules", () => {
  const text = fs.readFileSync(MODULE_PATH, "utf8");
  const imports = [...text.matchAll(/^import\s+[^;]+?from\s+"([^"]+)";/gm)].map((m) => m[1]);
  assert.deepEqual(imports.sort(), ["node:crypto", "node:fs", "node:path"]);
});

check("missing policy file is rejected", () => {
  assert.throws(
    () => loadBinding(POLICY_SHA, path.join(WORKSPACE, "absent-policy.json")),
    /missing typography policy/,
  );
});

check("invalid expected SHA-256 is rejected; uppercase is normalized", () => {
  assert.throws(() => loadBinding("NOT-A-DIGEST"), /SHA-256 must be/);
  assert.throws(() => loadBinding("g".repeat(64)), /SHA-256 must be/);
  assert.throws(() => loadBinding("a".repeat(63)), /SHA-256 must be/);
  const normalized = loadBinding(POLICY_SHA.toUpperCase());
  assert.equal(normalized.expected_policy_sha256, POLICY_SHA);
  assert.equal(normalized.policy_hash_matches, true);
});

check("unsupported policy schema is rejected", () => {
  const wrong = { ...POLICY, schema: "other.schema.v9" };
  const p = path.join(WORKSPACE, "wrong-schema.json");
  fs.writeFileSync(p, JSON.stringify(wrong), "utf8");
  assert.throws(
    () => loadBinding(crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"), p),
    /unsupported typography policy schema/,
  );
});

check("missing profile and soft hard_gate are rejected", () => {
  assert.throws(() => loadBinding(POLICY_SHA, POLICY_PATH, "absent-profile"), /missing from the canonical policy/);
  const soft = JSON.parse(JSON.stringify(POLICY));
  soft.profiles[PROFILE_ID].hard_gate = false;
  const p = path.join(WORKSPACE, "soft-gate.json");
  fs.writeFileSync(p, JSON.stringify(soft), "utf8");
  assert.throws(
    () => loadBinding(crypto.createHash("sha256").update(fs.readFileSync(p)).digest("hex"), p),
    /hard_gate=true and roles/,
  );
});

check("valid binding carries hash, roles, viewport and required_roles", () => {
  const binding = loadBinding();
  assert.equal(binding.policy_hash_matches, true);
  assert.equal(binding.policy_sha256, POLICY_SHA);
  assert.equal(binding.expected_policy_sha256, POLICY_SHA);
  assert.equal(binding.hard_gate, true);
  assert.deepEqual(binding.required_roles, ["primary_headline", "body"]);
  assert.equal(binding.roles.primary_headline.min_font_px, 24);
  assert.equal(binding.viewport.width, 1200);
});

check("hash drift is recorded rather than silently accepted", () => {
  const binding = loadBinding("0".repeat(64));
  assert.equal(binding.policy_hash_matches, false);
  assert.equal(binding.policy_sha256, POLICY_SHA);
});

/* ---- serialization contract ---- */
check("in-page function source is closure-free and Node-import free", () => {
  assert.match(SOURCE, /^function collectTypographyGateInPage\(root, options\)/);
  // Only a quoted Node builtin specifier counts as a Node import. The literal
  // "unclassified-reading-node:" is a legitimate failure code, not an import.
  assert.doesNotMatch(SOURCE, /["']node:\w/);
  assert.doesNotMatch(SOURCE, /\bfrom\s+["']node:/);
  assert.doesNotMatch(SOURCE, /\brequire\s*\(\s*["']node:/);
  assert.doesNotMatch(SOURCE, /\brequire\s*\(/);
  assert.doesNotMatch(SOURCE, /\bimport\s*\(/);
  assert.doesNotMatch(SOURCE, /\bprocess\./);
  assert.doesNotMatch(SOURCE, /\bBuffer\b/);
  assert.match(SOURCE, /document\.createTreeWalker/);
});

check("serialized function evaluates in a browser-only sandbox", () => {
  const sandbox = sandboxFor([]);
  assert.equal(typeof vm.runInNewContext(`(${SOURCE})`, sandbox), "function");
  assert.equal("require" in sandbox, false);
});

/* ---- in-page measurement boundaries with synthetic mock DOM ---- */
function validTree() {
  const root = rootNode();
  const h1 = node("h1", { style: { fontSize: "36px" }, rect: { x: 0, y: 0, width: 300, height: 40 },
                         clientWidth: 300, clientHeight: 40, scrollWidth: 300, scrollHeight: 40 }, root);
  const p = node("p", { style: { fontSize: "14px" } }, root);
  const texts = [
    { nodeValue: "Synthetic headline", parentElement: h1 },
    { nodeValue: "Synthetic body", parentElement: p },
  ];
  return { root, texts, sandbox: sandboxFor(texts) };
}

check("normal synthetic tree passes the font gate", () => {
  const binding = loadBinding();
  const { root, sandbox } = validTree();
  const result = runInjected(sandbox, root, binding);
  assert.equal(result.font_gate.passed, true);
  assert.equal(result.font_gate.failures.length, 0);
  assert.equal(result.font_gate.text_nodes.length, 2);
  assert.equal(result.minimum_font_px, 14);
  const roles = Array.from(new Set(Array.from(result.font_gate.text_nodes, (n) => n.role))).sort();
  assert.deepEqual(roles, ["body", "primary_headline"]);
  assert.equal(result.font_gate.policy_hash_matches, true);
  assert.equal(result.font_gate.measurement_mode, "text-leaf-computed-font-and-ancestor-transform");
  assert.equal(result.font_gate.target_preview_readability, "requires_human_review");
});

check("10px span inside 36px paragraph keeps its own font size", () => {
  const binding = loadBinding();
  const root = rootNode();
  const p = node("p", { style: { fontSize: "36px" } }, root);
  const span = node("span", { style: { fontSize: "10px" } }, p);
  const texts = [{ nodeValue: "Small synthetic note", parentElement: span }];
  const result = runInjected(sandboxFor(texts), root, binding);
  const leaf = result.font_gate.text_nodes[0];
  assert.equal(leaf.font_px, 10);
  assert.equal(leaf.role, "body");
  assert.equal(leaf.role_source, "tag-fallback");
  assert.equal(leaf.passes_font_minimum, false);
  assert.equal(result.font_gate.low_font_node_count, 1);
  assert.ok(result.font_gate.failures.includes("font-below-role-minimum:1"));
  assert.equal(result.font_gate.passed, false);
});

check("policy hash drift makes the font gate fail closed", () => {
  const binding = loadBinding("0".repeat(64));
  const { root, sandbox } = validTree();
  const result = runInjected(sandbox, root, binding);
  assert.equal(result.font_gate.passed, false);
  assert.equal(result.font_gate.failures[0], "policy-hash-drift");
  assert.equal(result.font_gate.policy_hash_matches, false);
});

check("no visible text nodes and missing required roles are reported", () => {
  const binding = loadBinding();
  const root = rootNode();
  const result = runInjected(sandboxFor([]), root, binding);
  assert.ok(result.font_gate.failures.includes("no-visible-text-nodes"));
  assert.deepEqual(Array.from(result.font_gate.missing_required_roles), ["primary_headline", "body"]);
  assert.equal(result.font_gate.passed, false);
});

check("unclassified reading node is reported", () => {
  const binding = loadBinding();
  const root = rootNode();
  const texts = [{ nodeValue: "Unclassified synthetic text", parentElement: root }];
  const result = runInjected(sandboxFor(texts), root, binding);
  assert.equal(result.font_gate.unclassified_reading_node_count, 1);
  assert.ok(result.font_gate.failures.includes("unclassified-reading-node:1"));
});

check("explicit unknown data-font-role is reported", () => {
  const binding = loadBinding();
  const root = rootNode();
  const p = node("p", { attributes: { "data-font-role": "mystery_role" } }, root);
  const texts = [{ nodeValue: "Unknown role text", parentElement: p }];
  const result = runInjected(sandboxFor(texts), root, binding);
  assert.deepEqual(Array.from(result.font_gate.unknown_roles), ["mystery_role"]);
  assert.ok(result.font_gate.failures.includes("unknown-or-unconfigured-roles:mystery_role"));
});

check("clipped text overflow is reported", () => {
  const binding = loadBinding();
  const root = rootNode();
  const h1 = node("h1", { style: { fontSize: "36px", overflowX: "hidden" }, scrollWidth: 900, clientWidth: 200 }, root);
  const p = node("p", { style: { fontSize: "14px" } }, root);
  const texts = [
    { nodeValue: "Overlong synthetic headline", parentElement: h1 },
    { nodeValue: "Synthetic body", parentElement: p },
  ];
  const result = runInjected(sandboxFor(texts), root, binding);
  assert.equal(result.font_gate.overflow_node_count, 1);
  assert.ok(result.font_gate.failures.includes("text-overflow:1"));
});

skip("two bridge modules share the same injected collector",
  "article_browser_qa.mjs and social_card_playwright_bridge.mjs are not in public baseline v0.1.1; real browser/bridge parity is unverified");

const passed = results.filter((r) => r.status === "pass").length;
const failed = results.filter((r) => r.status === "fail").length;
const skipped = results.filter((r) => r.status === "skip").length;
console.log(JSON.stringify({ module: "typography_gate_collector.mjs", total: results.length,
  passed, failed, skipped, results }, null, 2));
process.exit(failed ? 1 : 0);
