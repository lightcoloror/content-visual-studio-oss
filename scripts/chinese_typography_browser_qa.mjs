import fs from "node:fs";
import { createRequire } from "node:module";
import path from "node:path";
import process from "node:process";

function argument(name) {
  const index = process.argv.indexOf(name);
  if (index < 0 || !process.argv[index + 1]) throw new Error(`${name} is required`);
  return path.resolve(process.argv[index + 1]);
}

const input = argument("--input");
const output = argument("--output");
const playwrightPackage = argument("--playwright-package");
const packageMetadata = JSON.parse(fs.readFileSync(playwrightPackage, "utf8"));
if (packageMetadata.name !== "playwright") throw new Error(`configured package must be playwright: ${playwrightPackage}`);
const localRequire = createRequire(playwrightPackage);
const { chromium } = localRequire("playwright");
const extension = path.extname(input).toLowerCase();
const source = fs.readFileSync(input, "utf8");
const html = extension === ".svg"
  ? `<!doctype html><html lang="zh-CN"><meta name="viewport" content="width=device-width"><body style="margin:0">${source}</body></html>`
  : source;
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1280, height: 1600 } });
await page.setContent(html, { waitUntil: "load" });
await page.evaluate(() => document.fonts.ready);
const report = await page.evaluate(() => {
  const forbiddenStart = new Set("，。、；：！？）》】〕〉…".split(""));
  const forbiddenEnd = new Set("（《【〔〈".split(""));
  const findings = [];
  const lineMap = new Map();
  const elements = [...document.querySelectorAll("h1,h2,h3,h4,p,li,figcaption,td,th,[data-qa]")]
    .filter((element) => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
    });
  for (const [elementIndex, element] of elements.entries()) {
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const value = node.nodeValue ?? "";
      for (let index = 0; index < value.length; index += 1) {
        if (/\s/u.test(value[index])) continue;
        const range = document.createRange();
        range.setStart(node, index);
        range.setEnd(node, index + 1);
        const rect = range.getBoundingClientRect();
        if (!rect.width && !rect.height) continue;
        const key = `${elementIndex}:${Math.round(rect.top / 2) * 2}`;
        if (!lineMap.has(key)) lineMap.set(key, { text: "", top: rect.top, element: element.tagName.toLowerCase() });
        lineMap.get(key).text += value[index];
      }
    }
  }
  const lines = [...lineMap.values()].sort((left, right) => left.top - right.top);
  lines.forEach((line, index) => {
    if (forbiddenStart.has(line.text[0])) findings.push({ diagnostic_id: "GVL-TYPE-001", line: index + 1, message: `Line starts with ${line.text[0]}` });
    if (forbiddenEnd.has(line.text.at(-1))) findings.push({ diagnostic_id: "GVL-TYPE-002", line: index + 1, message: `Line ends with ${line.text.at(-1)}` });
    if (/^[\u3400-\u9fff\uf900-\ufaff]$/u.test(line.text)) findings.push({ diagnostic_id: "GVL-TYPE-004", line: index + 1, message: "Single-character CJK orphan line" });
  });
  for (const element of elements) {
    const text = element.textContent ?? "";
    for (const match of text.matchAll(/[A-Za-z]{2,}/g)) {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      let remainingStart = match.index;
      let remainingEnd = match.index + match[0].length;
      let offset = 0;
      const tops = new Set();
      let node;
      while ((node = walker.nextNode())) {
        const length = (node.nodeValue ?? "").length;
        const start = Math.max(0, remainingStart - offset);
        const end = Math.min(length, remainingEnd - offset);
        if (start < end) {
          const range = document.createRange();
          range.setStart(node, start);
          range.setEnd(node, end);
          for (const rect of range.getClientRects()) tops.add(Math.round(rect.top / 2) * 2);
        }
        offset += length;
      }
      if (tops.size > 1) findings.push({ diagnostic_id: "GVL-TYPE-003", message: `Western word split across lines: ${match[0]}` });
    }
  }
  const strandedHeadings = elements.filter((element) => /^H[1-4]$/.test(element.tagName) && !element.nextElementSibling);
  for (const heading of strandedHeadings) findings.push({ diagnostic_id: "GVL-TYPE-005", message: `Heading has no following block: ${heading.textContent?.trim()}` });
  const bodyFont = getComputedStyle(document.body).fontFamily;
  if (!bodyFont.trim()) findings.push({ diagnostic_id: "GVL-TYPE-006", message: "No resolved body font family" });
  return { status: findings.length ? "fail" : "pass", locale: document.documentElement.lang || "unknown", writing_mode: getComputedStyle(document.body).writingMode, line_count: lines.length, body_font: bodyFont, findings };
});
await browser.close();
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(JSON.stringify({ status: report.status, output, findings: report.findings.length }));
if (report.status !== "pass") process.exitCode = 2;
