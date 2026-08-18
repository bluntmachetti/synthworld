import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { build } from "esbuild";
import ELK from "elkjs/lib/elk.bundled.js";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const outputRoot = join(repositoryRoot, "src/synthworld/explorer/assets");
const mode = process.argv[2];
if (!new Set(["--write", "--check"]).has(mode)) {
  throw new Error("usage: node tools/build_explorer_assets.mjs --write|--check");
}

const readPackage = (name) =>
  JSON.parse(readFileSync(join(repositoryRoot, `node_modules/${name}/package.json`), "utf8"));
const cytoscapePackage = readPackage("cytoscape");
const elkPackage = readPackage("elkjs");
const esbuildPackage = readPackage("esbuild");

const projectionCode = [
  "import json, sys",
  "from pathlib import Path",
  "from synthworld.agentic import load_public_agentic_bundle",
  "from synthworld.explorer import canonical_json_bytes, project_asteria_agent_authority_v1",
  "root = Path('src/synthworld/benchmarks/asteria-agentic-v1/public')",
  "manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))",
  "projection = project_asteria_agent_authority_v1(load_public_agentic_bundle(root), public_artifact_set_digest=manifest['artifact_set_digest'])",
  "sys.stdout.buffer.write(canonical_json_bytes(projection))",
].join("; ");
const projectionRun = spawnSync("uv", ["run", "python", "-c", projectionCode], {
  cwd: repositoryRoot,
  encoding: "utf8",
});
if (projectionRun.status !== 0) {
  throw new Error(`could not generate Explorer projection: ${projectionRun.stderr}`);
}
const projectionBytes = Buffer.from(projectionRun.stdout, "utf8");
const projection = JSON.parse(projectionRun.stdout);
const projectionDigest = createHash("sha256").update(projectionBytes).digest("hex");

const nodeById = new Map(
  projection.nodes.map((node) => [
    node.id,
    { id: node.id, width: 180, height: 56, children: [] },
  ]),
);
const roots = [];
for (const node of projection.nodes) {
  const elkNode = nodeById.get(node.id);
  if (node.parent_node_id === null) {
    roots.push(elkNode);
  } else {
    nodeById.get(node.parent_node_id).children.push(elkNode);
  }
}
const pruneEmptyChildren = (node) => {
  if (node.children.length === 0) delete node.children;
  else node.children.forEach(pruneEmptyChildren);
};
roots.forEach(pruneEmptyChildren);

const elk = new ELK();
const laidOut = await elk.layout({
  id: "synthworld-explorer-root",
  children: roots,
  edges: projection.edges
    .filter((edge) => edge.kind !== "contains")
    .map((edge) => ({
      id: edge.id,
      sources: [edge.source_node_id],
      targets: [edge.target_node_id],
    })),
  layoutOptions: {
    "elk.algorithm": "layered",
    "elk.direction": "RIGHT",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.layered.nodePlacement.strategy": "NETWORK_SIMPLEX",
    "elk.layered.spacing.nodeNodeBetweenLayers": "80",
    "elk.padding": "[top=50,left=50,bottom=50,right=50]",
    "elk.spacing.nodeNode": "40",
  },
});

const round = (value) => Number(value.toFixed(3));
const coordinates = [];
const collectCoordinates = (node, parentX = 0, parentY = 0) => {
  const x = parentX + (node.x ?? 0);
  const y = parentY + (node.y ?? 0);
  if (node.id !== "synthworld-explorer-root") {
    const width = node.width ?? 180;
    const height = node.height ?? 56;
    coordinates.push({
      node_id: node.id,
      x: round(x + width / 2),
      y: round(y + height / 2),
      width: round(width),
      height: round(height),
    });
  }
  for (const child of node.children ?? []) collectCoordinates(child, x, y);
};
collectCoordinates(laidOut);
const compareCodePoints = (left, right) => (left < right ? -1 : left > right ? 1 : 0);
coordinates.sort((left, right) => compareCodePoints(left.node_id, right.node_id));

const canonical = (value) => {
  if (Array.isArray(value)) return value.map(canonical);
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value)
        .sort(([left], [right]) => compareCodePoints(left, right))
        .map(([key, child]) => [key, canonical(child)]),
    );
  }
  return value;
};
const canonicalBytes = (value) => Buffer.from(`${JSON.stringify(canonical(value))}\n`, "utf8");
const layoutCandidate = canonicalBytes({
  schema_version: "1.0.0",
  digest_algorithm: "sha256",
  public_projection_digest: projectionDigest,
  options: {
    engine: "elk",
    engine_version: elkPackage.version,
    algorithm: "layered",
    direction: "right",
    node_spacing: 40,
    layer_spacing: 80,
  },
  viewport: { width: 1440, height: 900 },
  coordinate_precision: 3,
  coordinates,
});
const layoutCanonicalizer = spawnSync(
  "uv",
  [
    "run",
    "python",
    "-c",
    [
      "import sys",
      "from synthworld.explorer import ExplorerLayoutManifestV1, canonical_json_bytes",
      "layout = ExplorerLayoutManifestV1.model_validate_json(sys.stdin.buffer.read())",
      "sys.stdout.buffer.write(canonical_json_bytes(layout))",
    ].join("; "),
  ],
  { cwd: repositoryRoot, input: layoutCandidate },
);
if (layoutCanonicalizer.status !== 0) {
  throw new Error(
    `could not canonicalize Explorer layout: ${layoutCanonicalizer.stderr.toString("utf8")}`,
  );
}
const layoutBytes = Buffer.from(layoutCanonicalizer.stdout);

const bundleResult = await build({
  absWorkingDir: repositoryRoot,
  banner: { js: `/*! SynthWorld Explorer; Cytoscape.js ${cytoscapePackage.version} (MIT) */` },
  bundle: true,
  entryPoints: ["tools/explorer/app.js"],
  format: "iife",
  legalComments: "eof",
  minify: true,
  target: ["es2020"],
  write: false,
});
if (bundleResult.outputFiles.length !== 1) throw new Error("Explorer bundle inventory differs");
const bundleBytes = Buffer.from(
  bundleResult.outputFiles[0].text.replace(/[\t ]+$/gm, ""),
  "utf8",
);
const cssBytes = Buffer.from(readFileSync(join(repositoryRoot, "tools/explorer/app.css"), "utf8"));

const notices = [
  "SynthWorld Explorer third-party notices",
  "",
  `Cytoscape.js ${cytoscapePackage.version} — ${cytoscapePackage.license}`,
  "https://js.cytoscape.org/",
  "",
  readFileSync(join(repositoryRoot, "node_modules/cytoscape/LICENSE"), "utf8").trim(),
  "",
  `ELK.js ${elkPackage.version} — ${elkPackage.license}`,
  "https://github.com/kieler/elkjs",
  "",
  readFileSync(join(repositoryRoot, "node_modules/elkjs/LICENSE.md"), "utf8").trim(),
  "",
].join("\n");
const noticeBytes = Buffer.from(notices, "utf8");

const artifacts = new Map([
  ["asteria-agent-authority-v1.layout.json", layoutBytes],
  ["explorer.bundle.js", bundleBytes],
  ["explorer.css", cssBytes],
  ["THIRD_PARTY_NOTICES.txt", noticeBytes],
]);
const manifestBytes = canonicalBytes({
  schema_version: "1.0.0",
  bundler: { name: "esbuild", version: esbuildPackage.version },
  dependencies: [
    { name: "cytoscape", version: cytoscapePackage.version, license: cytoscapePackage.license },
    { name: "elkjs", version: elkPackage.version, license: elkPackage.license },
  ],
  artifacts: Object.fromEntries(
    [...artifacts.entries()].map(([name, bytes]) => [
      name,
      { byte_size: bytes.length, sha256: createHash("sha256").update(bytes).digest("hex") },
    ]),
  ),
});
artifacts.set("manifest.json", manifestBytes);

if (mode === "--write") mkdirSync(outputRoot, { recursive: true });
for (const [name, expected] of artifacts) {
  const target = join(outputRoot, name);
  if (mode === "--write") {
    writeFileSync(target, expected);
    continue;
  }
  let actual;
  try {
    actual = readFileSync(target);
  } catch {
    throw new Error(`missing generated Explorer asset: ${name}`);
  }
  if (!actual.equals(expected)) throw new Error(`generated Explorer asset differs: ${name}`);
}

console.log(`${mode === "--write" ? "wrote" : "verified"} ${artifacts.size} Explorer assets`);
