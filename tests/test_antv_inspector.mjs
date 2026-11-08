#!/usr/bin/env node
// Directed regression tests for scripts/inspect_antv_input.mjs.
//
// IMPORTANT: every @antv/infographic package written below is a SYNTHETIC
// first-party fixture. It proves the adapter's argument validation, module
// resolution, input reading and output/error plumbing only. It is NOT a
// native-parser acceptance test; the host verifies the real optional parser
// separately. No browser, renderer, network fetch or package installation is
// used anywhere in this file.
//
// Runner: node --test test_antv_inspector.mjs
// The inspector is resolved from CONTENT_STUDIO_TEST_ROOT + /scripts when the
// host provides that variable, otherwise from the test file's parent repo.

import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = process.env.CONTENT_STUDIO_TEST_ROOT
  ? path.resolve(process.env.CONTENT_STUDIO_TEST_ROOT)
  : path.resolve(TEST_DIR, "..");
const INSPECTOR = path.join(REPO_ROOT, "scripts", "inspect_antv_input.mjs");

const DEFAULT_RESULT = {
  options: {
    template: "sequence-steps-simple",
    data: { title: "Synthetic", items: [{ label: "a" }] },
  },
  errors: [],
  warnings: [],
};

function makeTempDir(prefix) {
  return fs.mkdtempSync(path.join(os.tmpdir(), prefix));
}

function writeTextFile(filePath, contents) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.writeFileSync(filePath, contents, "utf8");
}

function writeJsonFile(filePath, value) {
  writeTextFile(filePath, JSON.stringify(value));
}

// Render a tiny first-party ESM module that satisfies the adapter's parser
// import contract (default-free ``parseSyntax`` named export).
function parserModuleSource(result) {
  return `export function parseSyntax() {\n  return ${JSON.stringify(result)};\n}\n`;
}

function writeSyntheticPackage(containerRoot, options = {}) {
  const {
    name = "@antv/infographic",
    parserSource = parserModuleSource(DEFAULT_RESULT),
    withParser = true,
  } = options;
  const packageRoot = path.join(
    containerRoot,
    "node_modules",
    "@antv",
    "infographic",
  );
  writeJsonFile(path.join(packageRoot, "package.json"), {
    name,
    version: "0.0.0-synthetic",
    type: "module",
  });
  if (withParser) {
    writeTextFile(
      path.join(packageRoot, "esm", "syntax", "index.js"),
      parserSource,
    );
  }
  return packageRoot;
}

function runInspector(args, options = {}) {
  return spawnSync(process.execPath, [INSPECTOR, ...args], {
    encoding: "utf8",
    timeout: 30000,
    cwd: options.cwd,
  });
}

// Strip host-specific absolute paths so no assertion depends on the machine
// layout; assertions below additionally look only at stable message fragments.
function normalized(text) {
  let output = String(text ?? "");
  const roots = [REPO_ROOT, os.tmpdir(), fs.realpathSync(os.tmpdir())];
  for (const root of roots) {
    for (const variant of new Set([root, root.split(path.sep).join("/")])) {
      if (variant) {
        output = output.split(variant).join("<ROOT>");
      }
    }
  }
  return output.split("\\").join("/");
}

function assertRejected(result, pattern) {
  assert.equal(result.signal, null, `terminated by signal ${result.signal}`);
  assert.equal(
    result.status,
    2,
    `expected exit 2, got ${result.status}; stderr=${normalized(result.stderr)}`,
  );
  assert.equal(
    result.stdout,
    "",
    `expected no stdout, got ${normalized(result.stdout)}`,
  );
  if (pattern) {
    assert.match(result.stderr, pattern);
  }
}

test("prints help and exits 0 without any installed parser", (t) => {
  const scratch = makeTempDir("studio-antv-help-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));

  const result = runInspector(["--help"], { cwd: scratch });
  assert.equal(result.status, 0);
  assert.equal(result.signal, null);
  assert.match(result.stdout, /inspect_antv_input\.mjs/);
  assert.match(result.stdout, /No install, browser or rendering\./);
  assert.equal(result.stderr, "");
});

test("rejects a missing runtime root and/or missing input", (t) => {
  const scratch = makeTempDir("studio-antv-missing-runtime-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");

  const cases = [[], ["--input", input]];
  for (const args of cases) {
    assertRejected(
      runInspector(args),
      /explicit input and exactly one runtime root required/,
    );
  }
});

test("rejects both runtime roots being supplied at once", (t) => {
  const scratch = makeTempDir("studio-antv-two-roots-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container);

  assertRejected(
    runInspector([
      "--module-root",
      container,
      "--package-root",
      packageRoot,
      "--input",
      input,
    ]),
    /exactly one runtime root required/,
  );
});

test("rejects duplicate, unknown and valueless options", (t) => {
  const scratch = makeTempDir("studio-antv-bad-args-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container);

  const cases = [
    ["--input", input, "--input", input, "--package-root", packageRoot],
    ["--bogus", "value", "--input", input, "--package-root", packageRoot],
    ["--input", "--package-root", packageRoot],
    ["--input"],
    ["--package-root"],
  ];
  for (const args of cases) {
    assertRejected(
      runInspector(args),
      /arguments must be unique --name value pairs/,
    );
  }
});

test("rejects a package whose identity is not @antv/infographic", (t) => {
  const scratch = makeTempDir("studio-antv-identity-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container, { name: "@antv/other" });

  assertRejected(
    runInspector(["--package-root", packageRoot, "--input", input]),
    /configured package must be @antv\/infographic/,
  );
});

test("rejects an absent package or package root", (t) => {
  const scratch = makeTempDir("studio-antv-absent-package-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");

  assertRejected(
    runInspector([
      "--package-root",
      path.join(scratch, "missing-package"),
      "--input",
      input,
    ]),
    /ENOENT/,
  );

  const emptyContainer = path.join(scratch, "empty-container");
  fs.mkdirSync(emptyContainer, { recursive: true });
  assertRejected(
    runInspector(["--module-root", emptyContainer, "--input", input]),
    /ENOENT/,
  );
});

test("rejects a package without the syntax parser module", (t) => {
  const scratch = makeTempDir("studio-antv-absent-parser-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container, { withParser: false });

  assertRejected(
    runInspector(["--package-root", packageRoot, "--input", input]),
    /Cannot find module|ERR_MODULE_NOT_FOUND/,
  );
});

test("rejects an absent input file", (t) => {
  const scratch = makeTempDir("studio-antv-absent-input-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container);

  assertRejected(
    runInspector([
      "--package-root",
      packageRoot,
      "--input",
      path.join(scratch, "missing.ifgc"),
    ]),
    /ENOENT/,
  );
});

test("maps synthetic parser output to exactly template, data, errors and warnings", (t) => {
  const scratch = makeTempDir("studio-antv-mapping-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container);

  const expected = {
    template: "sequence-steps-simple",
    data: { title: "Synthetic", items: [{ label: "a" }] },
    errors: [],
    warnings: [],
  };

  const viaModuleRoot = runInspector([
    "--module-root",
    container,
    "--input",
    input,
  ]);
  assert.equal(viaModuleRoot.signal, null);
  assert.equal(viaModuleRoot.status, 0, normalized(viaModuleRoot.stderr));
  assert.equal(viaModuleRoot.stderr, "");
  assert.deepEqual(JSON.parse(viaModuleRoot.stdout), expected);

  const viaPackageRoot = runInspector([
    "--package-root",
    packageRoot,
    "--input",
    input,
  ]);
  assert.equal(viaPackageRoot.status, 0, normalized(viaPackageRoot.stderr));
  assert.equal(viaPackageRoot.stderr, "");
  assert.deepEqual(JSON.parse(viaPackageRoot.stdout), expected);
});

test("preserves parser-reported syntax errors and warnings", (t) => {
  const scratch = makeTempDir("studio-antv-parser-errors-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const result = {
    options: {
      template: "list-grid-simple",
      data: { title: "Synthetic", items: [] },
    },
    errors: ["synthetic syntax error at token 3"],
    warnings: ["synthetic advisory"],
  };
  const packageRoot = writeSyntheticPackage(container, {
    parserSource: parserModuleSource(result),
  });

  const run = runInspector(["--package-root", packageRoot, "--input", input]);
  assert.equal(run.status, 0, normalized(run.stderr));
  assert.equal(run.stderr, "");
  // A legitimate parse error stays data, not a silent success.
  assert.deepEqual(JSON.parse(run.stdout), {
    template: "list-grid-simple",
    data: { title: "Synthetic", items: [] },
    errors: ["synthetic syntax error at token 3"],
    warnings: ["synthetic advisory"],
  });
});

test("maps absent parser fields to null and empty containers", (t) => {
  const scratch = makeTempDir("studio-antv-defaults-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container, {
    parserSource: parserModuleSource({}),
  });

  const run = runInspector(["--package-root", packageRoot, "--input", input]);
  assert.equal(run.status, 0, normalized(run.stderr));
  assert.deepEqual(JSON.parse(run.stdout), {
    template: null,
    data: {},
    errors: [],
    warnings: [],
  });
});

test("passes the local input text to the parser", (t) => {
  const scratch = makeTempDir("studio-antv-input-text-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const source = "synthetic-infographic-source-line\n";
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, source);
  const container = path.join(scratch, "container");
  const parserSource =
    "export function parseSyntax(source) {\n" +
    '  return { options: { template: "list-grid-simple", ' +
    "data: { title: String(source) } }, errors: [], warnings: [] };\n" +
    "}\n";
  const packageRoot = writeSyntheticPackage(container, { parserSource });

  const run = runInspector(["--package-root", packageRoot, "--input", input]);
  assert.equal(run.status, 0, normalized(run.stderr));
  assert.deepEqual(JSON.parse(run.stdout).data, { title: source });
});

test("reports fatal parser exceptions on stderr and exits 2", (t) => {
  const scratch = makeTempDir("studio-antv-parser-throws-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const parserSource =
    "export function parseSyntax() {\n" +
    '  throw new Error("synthetic parser exploded");\n' +
    "}\n";
  const packageRoot = writeSyntheticPackage(container, { parserSource });

  const run = runInspector(["--package-root", packageRoot, "--input", input]);
  assertRejected(run, /synthetic parser exploded/);
});

test("fails closed when the parser returns no object", (t) => {
  const scratch = makeTempDir("studio-antv-parser-null-");
  t.after(() => fs.rmSync(scratch, { recursive: true, force: true }));
  const input = path.join(scratch, "input.ifgc");
  writeTextFile(input, "synthetic-infographic-source\n");
  const container = path.join(scratch, "container");
  const packageRoot = writeSyntheticPackage(container, {
    parserSource: "export function parseSyntax() {\n  return null;\n}\n",
  });

  assertRejected(runInspector(["--package-root", packageRoot, "--input", input]));
});
