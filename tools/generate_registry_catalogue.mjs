import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const root = process.cwd();
const capabilityPath = resolve(root, "docs/_data/capabilities.resolved.json");
const benchmarkPath = resolve(root, "docs/_data/benchmarks.resolved.json");
const outputPath = resolve(root, ".blume-content/benchmarks/catalogue.md");
const supportedSchemaVersion = "1.0.0";
const requiredGateChecks = new Set([
  "adversarial_review",
  "baseline",
  "boundary_validation",
  "catalogue_hf_metadata",
  "checksums",
  "clean_install_reproduction",
  "deterministic_ci_recreation",
  "evaluator_truth",
  "independent_versions",
  "limitations",
  "metric_denominators",
  "public_input",
  "safety_review",
  "scorer_version",
  "submission_contract",
]);

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
    .replace(/\b([A-Za-z][A-Za-z0-9+.-]*):\/\//g, "$1&#58;//")
    .replace(/\bmailto:/gi, "mailto&#58;")
    .replace(/\bwww\./gi, "www&#46;")
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

function compare(left, right) {
  if (left < right) return -1;
  if (left > right) return 1;
  return 0;
}

function ordered(records, context) {
  const ids = new Set();
  return [...records]
    .map((value, index) => object(value, `${context}[${index}]`))
    .sort((left, right) =>
      compare(string(left, "id", context), string(right, "id", context)),
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
  if (benchmark.publication_gate === null) {
    if (benchmark.publication_gate_id !== null) {
      throw new Error(
        `benchmark ${benchmark.id} has a gate id without a publication gate`,
      );
    }
    return {
      catalogueStatus: "Registry-only; no publication gate assigned",
      checks: "not evaluated",
      decision: "not assigned",
    };
  }
  const gate = object(benchmark.publication_gate, "benchmark.publication_gate");
  const benchmarkId = string(benchmark, "id", "benchmark");
  const benchmarkVersion = string(benchmark, "benchmark_version", "benchmark");
  const gateId = string(gate, "id", "benchmark.publication_gate");
  const publicationGateId = string(benchmark, "publication_gate_id", "benchmark");
  if (
    string(gate, "benchmark_id", "benchmark.publication_gate") !== benchmarkId ||
    string(gate, "benchmark_version", "benchmark.publication_gate") !==
      benchmarkVersion ||
    gateId !== publicationGateId
  ) {
    throw new Error(`benchmark ${benchmarkId} has a mismatched publication gate`);
  }
  const decision = string(gate, "decision", "benchmark.publication_gate");
  const targets = array(
    gate.approved_targets,
    "benchmark.publication_gate.approved_targets",
  ).map((target, index) => {
    if (typeof target !== "string" || target.length === 0) {
      throw new TypeError(
        `benchmark.publication_gate.approved_targets[${index}] must be a non-empty string`,
      );
    }
    return target;
  });
  const counts = new Map();
  const checkNames = new Set();
  const checksList = array(
    gate.checks,
    "benchmark.publication_gate.checks",
  );
  let checksSuccessful = checksList.length > 0;
  for (const [index, value] of checksList.entries()) {
    const check = object(value, `benchmark.publication_gate.checks[${index}]`);
    const name = string(
      check,
      "name",
      `benchmark.publication_gate.checks[${index}]`,
    );
    const status = string(
      check,
      "status",
      `benchmark.publication_gate.checks[${index}]`,
    );
    if (!requiredGateChecks.has(name) || checkNames.has(name)) {
      throw new Error(
        `benchmark ${benchmarkId} has an unknown or duplicate gate check ${name}`,
      );
    }
    if (!["pass", "not_applicable", "pending", "fail"].includes(status)) {
      throw new Error(
        `benchmark ${benchmarkId} has unsupported gate status ${status}`,
      );
    }
    checkNames.add(name);
    checksSuccessful &&= status === "pass" || status === "not_applicable";
    counts.set(status, (counts.get(status) ?? 0) + 1);
  }
  if (
    checkNames.size !== requiredGateChecks.size ||
    [...requiredGateChecks].some((name) => !checkNames.has(name))
  ) {
    throw new Error(`benchmark ${benchmarkId} has an incomplete publication gate`);
  }
  const docsTargetApproved = targets.includes("docs_catalog");
  if (decision === "approved" && docsTargetApproved && !checksSuccessful) {
    throw new Error(
      `benchmark ${benchmarkId} approves docs with unsuccessful gate checks`,
    );
  }
  const docsApproved =
    decision === "approved" && docsTargetApproved && checksSuccessful;
  const checks = [...counts.entries()]
    .sort(([left], [right]) => compare(left, right))
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
  const schemaVersion = string(document, "schema_version", `${key} registry`);
  if (schemaVersion !== supportedSchemaVersion) {
    throw new Error(
      `${key} registry schema ${schemaVersion} is not supported; expected ${supportedSchemaVersion}`,
    );
  }
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
