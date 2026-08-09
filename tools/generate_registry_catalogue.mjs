import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const root = process.cwd();
const capabilityPath = resolve(root, "docs/_data/capabilities.resolved.json");
const benchmarkPath = resolve(root, "docs/_data/benchmarks.resolved.json");
const outputPath = resolve(root, ".blume-content/benchmarks/catalogue.md");

function object(value, context) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new TypeError(`${context} must be an object`);
  }
  return value;
}

function array(value, context) {
  if (!Array.isArray(value)) {
    throw new TypeError(`${context} must be an array`);
  }
  return value;
}

function string(record, key, context) {
  const value = record[key];
  if (typeof value !== "string" || value.length === 0) {
    throw new TypeError(`${context}.${key} must be a non-empty string`);
  }
  return value;
}

function markdown(value) {
  return value
    .replaceAll("\\", "\\\\")
    .replaceAll("`", "\\`")
    .replaceAll("*", "\\*")
    .replaceAll("_", "\\_")
    .replaceAll("[", "\\[")
    .replaceAll("]", "\\]")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replace(/[\r\n\t]+/g, " ");
}

function ordered(records, context) {
  const ids = new Set();
  return [...records]
    .map((value, index) => object(value, `${context}[${index}]`))
    .sort((left, right) =>
      string(left, "id", context).localeCompare(string(right, "id", context)),
    )
    .map((record) => {
      const id = string(record, "id", context);
      if (ids.has(id)) {
        throw new Error(`${context} contains duplicate id ${id}`);
      }
      ids.add(id);
      return record;
    });
}

function interfaceSummary(capability, name) {
  const interfaces = object(capability.interfaces, "capability.interfaces");
  const entry = object(interfaces[name], `capability.interfaces.${name}`);
  const coverage = string(entry, "coverage", `capability.interfaces.${name}`);
  const count = array(
    entry.surfaces,
    `capability.interfaces.${name}.surfaces`,
  ).length;
  return `${markdown(coverage)} (${count} surfaces)`;
}

function gateSummary(benchmark) {
  const gate = object(benchmark.publication_gate, "benchmark.publication_gate");
  const decision = string(gate, "decision", "benchmark.publication_gate");
  const targets = array(
    gate.approved_targets,
    "benchmark.publication_gate.approved_targets",
  );
  const docsApproved =
    decision === "approved" && targets.some((target) => target === "docs_catalog");
  const counts = new Map();
  for (const [index, value] of array(
    gate.checks,
    "benchmark.publication_gate.checks",
  ).entries()) {
    const check = object(value, `benchmark.publication_gate.checks[${index}]`);
    const status = string(
      check,
      "status",
      `benchmark.publication_gate.checks[${index}]`,
    );
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }
  const checks = [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([status, count]) => `${markdown(status)}: ${count}`)
    .join(", ");
  return {
    catalogueStatus: docsApproved
      ? "Approved for the docs catalogue"
      : "Registry-only; not approved for docs publication",
    checks,
    decision: markdown(decision),
  };
}

async function registry(path, key) {
  const document = object(
    JSON.parse(await readFile(path, "utf8")),
    `${key} registry`,
  );
  string(document, "schema_version", `${key} registry`);
  return ordered(array(document[key], `${key} registry.${key}`), key);
}

const capabilities = await registry(capabilityPath, "capabilities");
const benchmarks = await registry(benchmarkPath, "benchmarks");

const lines = [
  "---",
  "title: Registry catalogue",
  "description: Public capability and benchmark status projected from SynthWorld's resolved governance registries.",
  "---",
  "",
  "# Registry catalogue",
  "",
  "This page is generated during documentation preparation from the resolved",
  "capability and benchmark registries. It is an explicit public projection:",
  "artifact paths, digests, source locations, answer-key labels, and internal",
  "route metadata are not copied into the documentation site.",
  "",
  "A registry entry is not publication authorization. For benchmarks, use the",
  "catalogue status and publication-gate decision shown on each record.",
  "",
  `## Benchmarks (${benchmarks.length})`,
  "",
];

for (const benchmark of benchmarks) {
  const gate = gateSummary(benchmark);
  lines.push(
    `### ${markdown(string(benchmark, "title", "benchmark"))}`,
    "",
    `- ID: \`${markdown(string(benchmark, "id", "benchmark"))}\``,
    `- Version: \`${markdown(string(benchmark, "benchmark_version", "benchmark"))}\``,
    `- Lifecycle: ${markdown(string(benchmark, "lifecycle", "benchmark"))}`,
    `- Kind: ${markdown(string(benchmark, "benchmark_kind", "benchmark"))}`,
    `- Evaluation mode: ${markdown(string(benchmark, "evaluation_mode", "benchmark"))}`,
    `- Introduced in: \`${markdown(string(benchmark, "introduced_in", "benchmark"))}\``,
    `- Catalogue status: ${gate.catalogueStatus}`,
    `- Publication decision: ${gate.decision}`,
    `- Gate checks: ${gate.checks || "none"}`,
    "",
  );
}

lines.push(`## Capabilities (${capabilities.length})`, "");

for (const capability of capabilities) {
  lines.push(
    `### ${markdown(string(capability, "title", "capability"))}`,
    "",
    markdown(string(capability, "summary", "capability")),
    "",
    `- ID: \`${markdown(string(capability, "id", "capability"))}\``,
    `- Maturity: ${markdown(string(capability, "maturity", "capability"))}`,
    `- Since: \`${markdown(string(capability, "since", "capability"))}\``,
    `- Support: ${markdown(string(capability, "support", "capability"))}`,
    `- Python interface: ${interfaceSummary(capability, "python")}`,
    `- CLI interface: ${interfaceSummary(capability, "cli")}`,
    "",
  );
}

await mkdir(dirname(outputPath), { recursive: true });
await writeFile(outputPath, `${lines.join("\n")}\n`, "utf8");
