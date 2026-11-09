#!/usr/bin/env node

import { loadBrowserPackage, assetRoot, protectOutput, puppeteerOfflinePage } from "./browser_qa_runtime.mjs";
import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { collectTypographyGateInPage, loadTypographyGateBinding, TAG_ROLE_FALLBACK } from "./typography_gate_collector.mjs";


function parseArgs(argv) {
  const args = {};
  for (let index = 0; index < argv.length; index += 2) {
    const name = argv[index];
    const value = argv[index + 1];
    if (!name?.startsWith("--") || value === undefined) {
      throw new Error(`invalid argument sequence near ${name ?? "<end>"}`);
    }
    args[name.slice(2)] = value;
  }
  for (const name of ["html", "desktop", "mobile", "report", "chromium", "puppeteer-package", "typography-policy", "typography-policy-sha256", "desktop-typography-profile", "mobile-typography-profile"]) {
    if (!args[name]) throw new Error(`missing --${name}`);
  }
  return args;
}


function loadPuppeteer(packageJsonPath) {
  return loadBrowserPackage(packageJsonPath, ["puppeteer", "puppeteer-core"]);
}

async function inspectViewport(browser, htmlPath, screenshotPath, viewport, typographyBinding, allowNoFigures = false, localRoot) {
  const page = await browser.newPage();
  try {
    const blocked = await puppeteerOfflinePage(page, localRoot);
    await page.setViewport(viewport);
    await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "networkidle0" });
    await page.evaluate(async () => {
      window.scrollTo(0, document.documentElement.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 150));
      window.scrollTo(0, 0);
    });
    await page.waitForFunction(
      () => [...document.images].every((image) => image.complete && image.naturalWidth > 0),
      { timeout: 10_000 },
    );

    const inspection = await page.evaluate(() => {
      const parseBox = (value) => {
        if (!value) return null;
        const numbers = value.split(",").map(Number);
        if (numbers.length !== 4 || numbers.some((number) => !Number.isFinite(number))) return null;
        return { x: numbers[0], y: numbers[1], width: numbers[2], height: numbers[3] };
      };
      const within = (inner, outer, tolerance = 0.025) => (
        inner.x >= outer.x - tolerance
        && inner.y >= outer.y - tolerance
        && inner.x + inner.width <= outer.x + outer.width + tolerance
        && inner.y + inner.height <= outer.y + outer.height + tolerance
      );
      const visibleCrop = (image, style) => {
        const width = image.clientWidth;
        const height = image.clientHeight;
        const naturalWidth = image.naturalWidth;
        const naturalHeight = image.naturalHeight;
        if (!width || !height || !naturalWidth || !naturalHeight || style.objectFit !== "cover") {
          return { x: 0, y: 0, width: 1, height: 1 };
        }
        const scale = Math.max(width / naturalWidth, height / naturalHeight);
        const renderedWidth = naturalWidth * scale;
        const renderedHeight = naturalHeight * scale;
        const focusX = Number.parseFloat(style.getPropertyValue("--visual-focus-x")) / 100;
        const focusY = Number.parseFloat(style.getPropertyValue("--visual-focus-y")) / 100;
        const x = ((renderedWidth - width) * (Number.isFinite(focusX) ? focusX : 0.5)) / scale;
        const y = ((renderedHeight - height) * (Number.isFinite(focusY) ? focusY : 0.5)) / scale;
        return {
          x: x / naturalWidth,
          y: y / naturalHeight,
          width: width / scale / naturalWidth,
          height: height / scale / naturalHeight,
        };
      };

      const article = document.querySelector("article");
      const articleWidth = article?.getBoundingClientRect().width ?? 0;
      const figures = [...document.querySelectorAll("figure.article-visual")].map((figure) => {
        const image = figure.querySelector("img");
        const style = getComputedStyle(image);
        const crop = visibleCrop(image, style);
        const safeCrop = parseBox(figure.dataset.safeCrop);
        const subject = parseBox(figure.dataset.subjectBounds);
        const rect = figure.getBoundingClientRect();
        const isPhoto = (figure.dataset.mediaRoute ?? "").endsWith("-photo");
        const isSideLayout = figure.classList.contains("article-visual--text-left")
          || figure.classList.contains("article-visual--text-right");
        return {
          slot_id: figure.dataset.visualSlotId,
          loaded: image.complete && image.naturalWidth > 0,
          alt_complete: Boolean(image.getAttribute("alt")?.trim()),
          rights_complete: Boolean(figure.dataset.sourceId && figure.dataset.license),
          safe_crop_contains_visible: safeCrop ? within(crop, safeCrop) : false,
          subject_visible: subject ? within(subject, crop) : false,
          crop,
          safe_crop: safeCrop,
          subject_bounds: subject,
          figure_width: rect.width,
          article_width: articleWidth,
          mobile_photo_full_width: !isPhoto || window.innerWidth > 640 || rect.width >= articleWidth * 0.95,
          desktop_side_layout_compact: !isPhoto || window.innerWidth <= 640 || !isSideLayout || rect.width <= articleWidth * 0.6,
        };
      });
      return {
        viewport_width: window.innerWidth,
        viewport_height: window.innerHeight,
        scroll_width: document.documentElement.scrollWidth,
        article_width: articleWidth,
        figure_count: figures.length,
        figures,
      };
    });
    const typographyRoot = await page.$("article") ?? await page.$("body");
    if (!typographyRoot) throw new Error("article typography gate could not find article or body root");
    const typographyMetrics = await typographyRoot.evaluate(collectTypographyGateInPage, {
      tagRoleFallback: TAG_ROLE_FALLBACK,
      roles: typographyBinding.roles,
      requiredRoles: typographyBinding.required_roles,
      binding: typographyBinding,
    });
    if (blocked.length) throw new Error(`nonlocal requests disabled: ${blocked.join(", ")}`);
    inspection.typography_gate = typographyMetrics.font_gate;
    inspection.no_horizontal_overflow = inspection.scroll_width <= inspection.viewport_width;
    inspection.passed = inspection.no_horizontal_overflow
      && inspection.typography_gate.passed
      && (allowNoFigures || inspection.figure_count > 0)
      && inspection.figures.every((figure) => (
        figure.loaded
        && figure.alt_complete
        && figure.rights_complete
        && figure.safe_crop_contains_visible
        && figure.subject_visible
        && figure.mobile_photo_full_width
        && figure.desktop_side_layout_compact
      ));
    await page.screenshot({ path: screenshotPath, fullPage: true, type: "png" });
    return inspection;
  } finally {
    await page.close();
  }
}


async function main() {
  const args = parseArgs(process.argv.slice(2));
  const localRoot = assetRoot(args.html, args["asset-root"]);
  for (const name of ["desktop", "mobile", "report"]) protectOutput(args[name], [args.html, args["typography-policy"], args["puppeteer-package"], args.chromium]);
  const allowNoFigures = args["allow-no-figures"] === "true";
  const desktopTypographyBinding = loadTypographyGateBinding({
    policyPath: args["typography-policy"],
    expectedSha256: args["typography-policy-sha256"],
    profileId: args["desktop-typography-profile"],
  });
  const mobileTypographyBinding = loadTypographyGateBinding({
    policyPath: args["typography-policy"],
    expectedSha256: args["typography-policy-sha256"],
    profileId: args["mobile-typography-profile"],
  });
  if (!desktopTypographyBinding.policy_hash_matches || !mobileTypographyBinding.policy_hash_matches) {
    throw new Error("typography policy hash mismatch");
  }
  const puppeteer = loadPuppeteer(args["puppeteer-package"]);
  const browser = await puppeteer.launch({
    executablePath: path.resolve(args.chromium),
    headless: true,
    pipe: true,
    timeout: 15000,
  });
  let report;
  try {
    report = {
      schema_version: "article-browser-qa.v1",
      html: path.resolve(args.html),
      desktop: await inspectViewport(
        browser,
        path.resolve(args.html),
        path.resolve(args.desktop),
        { width: 1200, height: 900, deviceScaleFactor: 1 },
        desktopTypographyBinding,
        allowNoFigures, localRoot,
      ),
      mobile: await inspectViewport(
        browser,
        path.resolve(args.html),
        path.resolve(args.mobile),
        { width: 390, height: 844, deviceScaleFactor: 1, isMobile: true },
        mobileTypographyBinding,
        allowNoFigures, localRoot,
      ),
    };
  } finally {
    await browser.close();
  }
  report.passed = report.desktop.passed && report.mobile.passed;
  report.allow_no_figures = allowNoFigures;
  fs.mkdirSync(path.dirname(path.resolve(args.report)), { recursive: true });
  fs.writeFileSync(path.resolve(args.report), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  process.stdout.write(`${JSON.stringify(report)}\n`);
  if (!report.passed) process.exitCode = 2;
}


if (process.argv.includes("--help")) {
  console.log("Local article QA: --html --desktop --mobile --report --chromium --puppeteer-package --typography-policy --typography-policy-sha256 --desktop-typography-profile --mobile-typography-profile; optional --asset-root and --allow-no-figures true. Browser sandbox retained; no runtime installation.");
} else main().catch((error) => {
  process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`);
  process.exitCode = 2;
});
