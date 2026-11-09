// First-party glue shared by the existing local-only QA wrappers. No browser starts here.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

export function loadBrowserPackage(manifest, names) {
  const resolved = fs.realpathSync(path.resolve(manifest));
  const metadata = JSON.parse(fs.readFileSync(resolved, "utf8"));
  if (!names.includes(metadata.name)) throw new Error(`configured package must be ${names.join(" or ")}`);
  const require = createRequire(resolved);
  const loaded = require(path.dirname(resolved));
  return loaded.default ?? loaded;
}

export function integerArgument(value, label) {
  if (!/^\d+$/.test(String(value))) throw new Error(`${label} must be a non-negative integer`);
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) throw new Error(`${label} must be a safe integer`);
  return parsed;
}

export function assetRoot(input, explicitRoot) {
  const file = fs.realpathSync(path.resolve(input));
  if (!fs.statSync(file).isFile()) throw new Error("input must be a local file");
  const root = fs.realpathSync(path.resolve(explicitRoot ?? path.dirname(file)));
  if (!fs.statSync(root).isDirectory() || !within(file, root)) throw new Error("input is outside asset root");
  return root;
}

function within(file, root) {
  const relative = path.relative(root, file);
  return relative === "" || (!path.isAbsolute(relative) && relative !== ".." && !relative.startsWith(`..${path.sep}`));
}

export function allowedAssetUrl(value, root) {
  try {
    const url = new URL(value);
    if (["data:", "blob:", "about:"].includes(url.protocol)) return true;
    if (url.protocol !== "file:") return false;
    return within(fs.realpathSync(fileURLToPath(url)), fs.realpathSync(root));
  } catch { return false; }
}

export function protectOutput(output, inputs) {
  const resolved = path.resolve(output);
  const stat = fs.existsSync(resolved) ? fs.statSync(resolved, { bigint: true }) : null;
  if (stat && !stat.isFile()) throw new Error("output must be a file");
  for (const input of inputs) {
    const file = fs.realpathSync(path.resolve(input));
    const source = fs.statSync(file, { bigint: true });
    if (resolved === file || (stat && stat.dev === source.dev && stat.ino === source.ino)) {
      throw new Error("output would overwrite an input or runtime file");
    }
  }
}

function blockedLabel(value) {
  try {
    const url = new URL(value);
    return url.protocol === "file:" ? "file:outside-asset-root" : `${url.protocol}//${url.host}`;
  } catch { return "invalid-url"; }
}

export async function puppeteerOfflinePage(page, root) {
  const blocked = [];
  // These adapters inspect already-rendered static HTML/SVG, not application scripts.
  await page.setJavaScriptEnabled(false);
  await page.setOfflineMode(true);
  await page.setRequestInterception(true);
  page.on("request", async request => {
    if (allowedAssetUrl(request.url(), root)) await request.continue();
    else { blocked.push(blockedLabel(request.url())); await request.abort(); }
  });
  return blocked;
}

export async function playwrightOfflineContext(browser, root, blocked, options) {
  const context = await browser.newContext({ ...options, javaScriptEnabled: false,
    serviceWorkers: "block", acceptDownloads: false, offline: true });
  await context.route("**/*", async route => {
    if (allowedAssetUrl(route.request().url(), root)) await route.continue();
    else { blocked.push(blockedLabel(route.request().url())); await route.abort(); }
  });
  return context;
}
