#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { loadBrowserPackage, assetRoot, protectOutput, playwrightOfflineContext, integerArgument } from "./browser_qa_runtime.mjs";
import { pathToFileURL } from "node:url";
import { collectTypographyGateInPage, loadTypographyGateBinding, TAG_ROLE_FALLBACK } from "./typography_gate_collector.mjs";

if (process.argv.includes("--help")) { console.log("Local social card PNG: --html --output --selector --card-index --chromium --playwright-package --typography-policy --typography-profile --typography-policy-sha256; optional --expected-count --asset-root. Explicit browser/runtime required; sandbox retained."); process.exit(0); }

const values = new Map();
for (let index = 2; index < process.argv.length; index += 2) {
  const key = process.argv[index];
  const value = process.argv[index + 1];
  if (!key?.startsWith("--") || value === undefined) {
    throw new Error("arguments must be --name value pairs");
  }
  values.set(key.slice(2), value);
}

for (const key of ["html", "output", "selector", "card-index", "chromium", "playwright-package", "typography-policy", "typography-profile", "typography-policy-sha256"]) {
  if (!values.has(key)) throw new Error(`missing --${key}`);
}

const htmlPath = path.resolve(values.get("html"));
const outputPath = path.resolve(values.get("output"));
const chromiumPath = path.resolve(values.get("chromium"));
const playwrightPackagePath = path.resolve(values.get("playwright-package"));
const typographyPolicyPath = path.resolve(values.get("typography-policy"));
const typographyProfile = values.get("typography-profile");
const expectedTypographyPolicySha256 = values.get("typography-policy-sha256").toLowerCase();
const selector = values.get("selector");
const cardIndex = integerArgument(values.get("card-index"), "card-index");
const expectedCount = values.has("expected-count")
  ? integerArgument(values.get("expected-count"), "expected-count")
  : null;
if (!fs.existsSync(htmlPath)) throw new Error(`missing HTML input: ${htmlPath}`);
if (!fs.existsSync(chromiumPath)) throw new Error(`missing Chromium executable: ${chromiumPath}`);
if (!fs.existsSync(playwrightPackagePath)) {
  throw new Error(`missing Playwright package manifest: ${playwrightPackagePath}`);
}
if (!fs.existsSync(typographyPolicyPath)) {
  throw new Error(`missing typography policy: ${typographyPolicyPath}`);
}
if (!/^[0-9a-f]{64}$/.test(expectedTypographyPolicySha256)) {
  throw new Error("typography policy SHA-256 must be a lowercase 64-character hexadecimal digest");
}
const playwrightPackage = JSON.parse(fs.readFileSync(playwrightPackagePath, "utf8"));
if (playwrightPackage.name !== "playwright") {
  throw new Error(`configured package must be playwright: ${playwrightPackagePath}`);
}
if (!Number.isInteger(cardIndex) || cardIndex < 0) throw new Error("card index must be non-negative");

const typographyBinding = loadTypographyGateBinding({
  policyPath: typographyPolicyPath,
  expectedSha256: expectedTypographyPolicySha256,
  profileId: typographyProfile,
});
if (!typographyBinding.policy_hash_matches) throw new Error("typography policy hash mismatch");

const { chromium } = loadBrowserPackage(playwrightPackagePath, ["playwright"]);
const localRoot = assetRoot(htmlPath, values.get("asset-root"));
protectOutput(outputPath, [htmlPath, typographyPolicyPath, playwrightPackagePath, chromiumPath]);
const blockedRemoteRequests = [];
const browser = await chromium.launch({
  headless: true,
  executablePath: chromiumPath,
  chromiumSandbox: true,
  timeout: 15000,
});

try {
  const context = await playwrightOfflineContext(browser, localRoot, blockedRemoteRequests, {
    viewport: { width: 1400, height: 1700 }, deviceScaleFactor: 1,
  });
  const page = await context.newPage();
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts?.ready);
  const cards = page.locator(selector);
  const cardCount = await cards.count();
  if (cardCount < 1) throw new Error(`selector ${selector} matched no cards`);
  if (expectedCount !== null && cardCount !== expectedCount) {
    throw new Error(`expected ${expectedCount} cards, found ${cardCount}`);
  }
  if (cardIndex >= cardCount) throw new Error(`card index ${cardIndex} exceeds deck size ${cardCount}`);
  if (blockedRemoteRequests.length) {
    throw new Error(`remote requests are disabled: ${blockedRemoteRequests.join(", ")}`);
  }

  const card = cards.nth(cardIndex);
  const metrics = await card.evaluate(collectTypographyGateInPage, {
    tagRoleFallback: TAG_ROLE_FALLBACK,
    roles: typographyBinding.roles,
    requiredRoles: typographyBinding.required_roles,
    binding: typographyBinding,
  });
  if (metrics.overflow_px > 4) {
    metrics.font_gate.passed = false;
    metrics.font_gate.failures.push(`card-overflow:${metrics.overflow_px}px`);
  }
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  await card.screenshot({ path: outputPath, type: "png" });
  process.stdout.write(JSON.stringify({
    ...metrics,
    card_count: cardCount,
    card_index: cardIndex,
    blocked_remote_requests: blockedRemoteRequests,
  }));
} finally {
  await browser.close();
}
