import { constants } from "node:fs";
import {
  copyFile,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, join, posix } from "node:path";

const sourceRoot = "docs";
const stagingRoot = ".blume-content";
const deploymentBase = "/synthworld";
const githubSource = "https://github.com/bluntmachetti/synthworld";
const rootDocuments = [
  "AGENTIC_BENCHMARK.md",
  "BENCHMARKS.md",
  "DATA_DICTIONARY.md",
  "EVALUATION_KEY_CUSTODY.md",
  "GOLDEN_REVIEW.md",
  "README.md",
  "ROADMAP.md",
  "USER_GUIDE.md",
];
const nestedDocuments = [
  "agent-authority-contract/README.md",
  "authority-governance-contract/README.md",
  "contextual-access-contract/README.md",
  "continuous-assurance-contract/README.md",
  "enterprise-identity-access-contract/README.md",
];
const publicDocumentSources = new Set([
  ...rootDocuments,
  ...nestedDocuments,
  "CHANGELOG.md",
  "huggingface/README.md",
]);
const markdownLink =
  /(?<!!)(\[[^\]\n]*\]\()(<[^>\n]+>|[^)\s\n]+)([^)\n]*\))/gu;

function compareNames(left, right) {
  if (left.name < right.name) return -1;
  if (left.name > right.name) return 1;
  return 0;
}

function destinationForSource(source) {
  if (source === "CHANGELOG.md") return "changelog/CHANGELOG.md";
  if (source.startsWith("docs/")) return source.slice("docs/".length);
  if (publicDocumentSources.has(source)) return source;
  return null;
}

function routeForDestination(destination) {
  let route = destination.replace(/\.(?:md|mdx)$/u, "");
  if (route === "index") route = "";
  if (route.endsWith("/index")) route = route.slice(0, -"/index".length);
  return route ? `${deploymentBase}/${route}` : `${deploymentBase}/`;
}

function githubTarget(source, isDirectory) {
  const view = isDirectory ? "tree" : "blob";
  return `${githubSource}/${view}/main/${source}`;
}

function rewriteTarget(source, rawTarget) {
  const wrapped = rawTarget.startsWith("<") && rawTarget.endsWith(">");
  const target = wrapped ? rawTarget.slice(1, -1) : rawTarget;
  if (
    target === "" ||
    target.startsWith("#") ||
    target.startsWith("//") ||
    /^[a-z][a-z0-9+.-]*:/iu.test(target)
  ) {
    return rawTarget;
  }
  if (target.startsWith(deploymentBase)) return target;
  if (target.startsWith("/")) return `${deploymentBase}${target}`;

  const suffixAt = target.search(/[?#]/u);
  const path = suffixAt === -1 ? target : target.slice(0, suffixAt);
  const suffix = suffixAt === -1 ? "" : target.slice(suffixAt);
  const isDirectory = path.endsWith("/");
  const resolvedSource = posix.normalize(posix.join(posix.dirname(source), path));
  if (resolvedSource === ".." || resolvedSource.startsWith("../")) {
    throw new Error(`documentation link escapes the repository: ${source} -> ${target}`);
  }

  const destination = destinationForSource(resolvedSource);
  if (destination !== null) {
    return `${routeForDestination(destination)}${suffix}`;
  }
  return `${githubTarget(resolvedSource, isDirectory)}${suffix}`;
}

function rewriteMarkdownLinks(content, source) {
  let fence = null;
  return content
    .split(/(?<=\n)/u)
    .map((line) => {
      const marker = /^\s*(`{3,}|~{3,})/u.exec(line)?.[1];
      if (marker) {
        if (fence === null) {
          fence = marker[0];
        } else if (marker[0] === fence) {
          fence = null;
        }
        return line;
      }
      if (fence !== null) return line;
      return line.replace(
        markdownLink,
        (_match, opening, target, closing) =>
          `${opening}${rewriteTarget(source, target)}${closing}`,
      );
    })
    .join("");
}

async function writeDocument(destination, content) {
  const destinationPath = join(stagingRoot, destination);
  await mkdir(dirname(destinationPath), { recursive: true });
  await writeFile(destinationPath, content, { encoding: "utf8", flag: "wx" });
}

async function stageMarkdown(sourcePath, source, destination) {
  const content = await readFile(sourcePath, "utf8");
  await writeDocument(destination, rewriteMarkdownLinks(content, source));
}

async function copyTree(sourcePath, destinationPath, source, destination) {
  await mkdir(destinationPath, { recursive: true });
  const entries = await readdir(sourcePath, { withFileTypes: true });

  for (const entry of entries.sort(compareNames)) {
    const childSourcePath = join(sourcePath, entry.name);
    const childDestinationPath = join(destinationPath, entry.name);
    const childSource = posix.join(source, entry.name);
    const childDestination = posix.join(destination, entry.name);

    if (entry.isDirectory()) {
      await copyTree(
        childSourcePath,
        childDestinationPath,
        childSource,
        childDestination,
      );
    } else if (entry.isFile()) {
      if (/\.(?:md|mdx)$/u.test(entry.name)) {
        await stageMarkdown(childSourcePath, childSource, childDestination);
      } else {
        await copyFile(
          childSourcePath,
          childDestinationPath,
          constants.COPYFILE_EXCL,
        );
      }
    } else {
      throw new Error(`unsupported documentation entry: ${childSource}`);
    }
  }
}

await rm(stagingRoot, { force: true, recursive: true });
await copyTree(sourceRoot, stagingRoot, sourceRoot, "");
for (const document of [...rootDocuments, ...nestedDocuments, "CHANGELOG.md"]) {
  const destination = destinationForSource(document);
  if (destination === null) {
    throw new Error(`missing public documentation destination: ${document}`);
  }
  await stageMarkdown(document, document, destination);
}
await writeDocument(
  "huggingface/README.md",
  `---
title: Hugging Face dataset card
description: Source reference for the historical SynthWorld dataset card.
---

# Hugging Face dataset card

The repository retains a historical dataset card for compatibility and review.
Read the [source dataset card](${githubSource}/blob/main/huggingface/README.md) on GitHub.
`,
);

console.log(`prepared deterministic documentation content in ${stagingRoot}/`);
