import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";


export const TAG_ROLE_FALLBACK = Object.freeze({
  h1: "primary_headline",
  h2: "scene_title",
  h3: "scene_title",
  h4: "scene_title",
  p: "body",
  li: "multi_column_body",
  blockquote: "body",
  figcaption: "disclosure",
  small: "disclosure",
});


export function loadTypographyGateBinding({ policyPath, expectedSha256, profileId }) {
  const resolvedPolicyPath = path.resolve(policyPath);
  if (!fs.existsSync(resolvedPolicyPath)) {
    throw new Error(`missing typography policy: ${resolvedPolicyPath}`);
  }
  const expected = String(expectedSha256 ?? "").toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(expected)) {
    throw new Error("typography policy SHA-256 must be a lowercase 64-character hexadecimal digest");
  }
  const bytes = fs.readFileSync(resolvedPolicyPath);
  const actual = crypto.createHash("sha256").update(bytes).digest("hex");
  const policy = JSON.parse(bytes.toString("utf8"));
  if (policy.schema !== "lucas.typography_gates.v1") {
    throw new Error(`unsupported typography policy schema: ${policy.schema ?? "missing"}`);
  }
  const profile = policy.profiles?.[profileId];
  if (!profile || typeof profile !== "object") {
    throw new Error(`typography profile ${profileId} is missing from the canonical policy`);
  }
  if (profile.hard_gate !== true || !profile.roles || typeof profile.roles !== "object") {
    throw new Error(`typography profile ${profileId} must declare hard_gate=true and roles`);
  }
  return {
    policy_id: policy.policy_id ?? policy.schema,
    policy_path: resolvedPolicyPath,
    policy_sha256: actual,
    expected_policy_sha256: expected,
    policy_hash_matches: actual === expected,
    profile_id: profileId,
    viewport: profile.viewport ?? null,
    preview: profile.preview ?? null,
    hard_gate: true,
    roles: profile.roles,
    required_roles: Array.isArray(profile.required_roles)
      ? profile.required_roles.filter((role) => typeof role === "string" && role.trim())
      : [],
  };
}


// This function intentionally has no Node imports or closures: Playwright and Puppeteer
// serialize it into the inspected page, keeping the measurement logic identical by route.
export function collectTypographyGateInPage(root, options) {
  const excludedTags = new Set(["script", "style", "noscript", "template", "path", "defs", "symbol", "title"]);
  const isVisible = (node) => {
    const style = getComputedStyle(node);
    const rect = node.getBoundingClientRect();
    return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
  };
  const isExcluded = (node) => excludedTags.has(node.tagName.toLowerCase());
  const nearestRoleBoundary = (start) => {
    let current = start;
    while (current) {
      if (isExcluded(current)) return null;
      const explicitRole = current.getAttribute("data-font-role")?.trim();
      if (explicitRole) return { node: current, role: explicitRole, source: "data-font-role" };
      const fallbackRole = options.tagRoleFallback[current.tagName.toLowerCase()];
      if (fallbackRole) return { node: current, role: fallbackRole, source: "tag-fallback" };
      if (current === root) break;
      current = current.parentElement;
    }
    return { node: start, role: null, source: "unclassified-reading-node" };
  };

  // Inherit the semantic role, not the ancestor's font size: a 10px span
  // inside a 36px paragraph must be measured as 10px.
  const readingNodes = new Map();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let textNode;
  while ((textNode = walker.nextNode())) {
    if (!(textNode.nodeValue ?? "").trim()) continue;
    const parent = textNode.parentElement;
    if (!parent || isExcluded(parent)) continue;
    const boundary = nearestRoleBoundary(parent);
    if (boundary) {
      const entry = readingNodes.get(parent) ?? { node: parent, role: boundary.role, source: boundary.source, text: "" };
      entry.text += textNode.nodeValue;
      readingNodes.set(parent, entry);
    }
  }

  const renderedScale = (node) => {
    // Smallest singular value detects compression in either axis; rotation
    // alone is not shrinkage. SVG screen CTM includes its viewBox scaling.
    let matrix = new DOMMatrix();
    if (node instanceof SVGGraphicsElement && node.getScreenCTM()) {
      const ctm = node.getScreenCTM();
      matrix = new DOMMatrix([ctm.a, ctm.b, ctm.c, ctm.d, ctm.e, ctm.f]);
    } else {
      let current = node;
      while (current) {
        const style = getComputedStyle(current);
        if (style.transform && style.transform !== "none") {
          matrix = new DOMMatrix(style.transform).multiply(matrix);
        }
        if (style.scale && style.scale !== "none") {
          const values = style.scale.split(/\s+/).map((value) => value.endsWith("%") ? Number.parseFloat(value) / 100 : Number(value));
          matrix = new DOMMatrix().scale(values[0], values[1] ?? values[0]).multiply(matrix);
        }
        const zoom = Number.parseFloat(style.zoom);
        if (Number.isFinite(zoom) && zoom > 0) matrix = new DOMMatrix().scale(zoom).multiply(matrix);
        current = current.parentElement;
      }
    }
    if (!matrix.is2D) return null; // perspective needs independent rendered evidence
    const trace = matrix.a ** 2 + matrix.b ** 2 + matrix.c ** 2 + matrix.d ** 2;
    const determinant = (matrix.a * matrix.d - matrix.b * matrix.c) ** 2;
    return Math.sqrt(Math.max(0, (trace - Math.sqrt(Math.max(0, trace ** 2 - 4 * determinant))) / 2));
  };
  const previewScale = options.binding.preview?.width / options.binding.viewport?.width;
  const textNodes = [...readingNodes.values()]
    .filter(({ node }) => isVisible(node))
    .map(({ node, role, source, text }) => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      const fontPx = Number.parseFloat(style.fontSize);
      const scale = renderedScale(node);
      const effectiveFontPx = scale === null ? null : fontPx * scale;
      const minimum = role ? options.roles[role]?.min_font_px : null;
      const clipsX = ["hidden", "clip", "scroll", "auto"].includes(style.overflowX);
      const clipsY = ["hidden", "clip", "scroll", "auto"].includes(style.overflowY);
      const overflow = (clipsX && node.scrollWidth > node.clientWidth + 2)
        || (clipsY && node.scrollHeight > node.clientHeight + 2);
      return {
        role,
        role_source: source,
        tag: node.tagName.toLowerCase(),
        text: text.trim().slice(0, 160),
        font_px: Number.isFinite(fontPx) ? fontPx : null,
        rendered_scale: scale,
        effective_font_px: effectiveFontPx,
        preview_font_px: effectiveFontPx === null || !Number.isFinite(previewScale) ? null : effectiveFontPx * previewScale,
        bbox: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        overflow,
        required_min_font_px: typeof minimum === "number" ? minimum : null,
        text_coverage_ratio: (rect.width * rect.height) / Math.max(1, root.clientWidth * root.clientHeight),
        passes_font_minimum: typeof minimum === "number" && Number.isFinite(effectiveFontPx) && effectiveFontPx + .01 >= minimum,
      };
    });
  const presentRoles = new Set(textNodes.map((node) => node.role));
  const unclassifiedNodes = textNodes.filter((node) => node.role_source === "unclassified-reading-node");
  const unknownRoles = [...new Set(textNodes
    .filter((node) => node.role_source !== "unclassified-reading-node" && node.required_min_font_px === null)
    .map((node) => node.role))];
  const lowFontNodes = textNodes.filter((node) => node.passes_font_minimum === false);
  const overflowNodes = textNodes.filter((node) => node.overflow);
  const missingRequiredRoles = options.requiredRoles.filter((role) => !presentRoles.has(role));
  const fontSizes = textNodes.map((node) => node.effective_font_px).filter(Number.isFinite);
  const failures = [];
  if (!textNodes.length) failures.push("no-visible-text-nodes");
  if (unclassifiedNodes.length) failures.push(`unclassified-reading-node:${unclassifiedNodes.length}`);
  if (unknownRoles.length) failures.push(`unknown-or-unconfigured-roles:${unknownRoles.join(",")}`);
  if (missingRequiredRoles.length) failures.push(`missing-required-roles:${missingRequiredRoles.join(",")}`);
  if (lowFontNodes.length) failures.push(`font-below-role-minimum:${lowFontNodes.length}`);
  if (overflowNodes.length) failures.push(`text-overflow:${overflowNodes.length}`);
  return {
    width: root.clientWidth,
    height: root.clientHeight,
    overflow_px: Math.max(0, root.scrollHeight - root.clientHeight),
    minimum_font_px: fontSizes.length ? Math.min(...fontSizes) : null,
    font_gate: {
      policy_id: options.binding.policy_id,
      profile_id: options.binding.profile_id,
      policy_path: options.binding.policy_path,
      policy_sha256: options.binding.policy_sha256,
      expected_policy_sha256: options.binding.expected_policy_sha256,
      policy_hash_matches: options.binding.policy_hash_matches,
      viewport: options.binding.viewport,
      preview: options.binding.preview,
      hard_gate: options.binding.hard_gate,
      measurement_mode: "text-leaf-computed-font-and-ancestor-transform",
      target_preview_readability: "requires_human_review",
      roles: options.binding.roles,
      text_nodes: textNodes,
      required_roles: options.requiredRoles,
      missing_required_roles: missingRequiredRoles,
      unclassified_reading_node_count: unclassifiedNodes.length,
      unknown_roles: unknownRoles,
      low_font_node_count: lowFontNodes.length,
      overflow_node_count: overflowNodes.length,
      passed: failures.length === 0 && options.binding.policy_hash_matches,
      failures: options.binding.policy_hash_matches ? failures : ["policy-hash-drift", ...failures],
    },
  };
}
