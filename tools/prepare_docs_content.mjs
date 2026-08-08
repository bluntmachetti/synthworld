import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
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

function routePathForDestination(destination) {
  let route = destination.replace(/\.(?:md|mdx)$/u, "");
  if (route === "index") route = "";
  if (route.endsWith("/index")) route = route.slice(0, -"/index".length);
  return route;
}

function githubTarget(source, isDirectory) {
  const view = isDirectory ? "tree" : "blob";
  return `${githubSource}/${view}/main/${source}`;
}

function relativeRoute(source, target, suffix) {
  const sourceDestination = destinationForSource(source);
  if (sourceDestination === null) {
    throw new Error(`missing source route for staged document: ${source}`);
  }
  const sourceRoute = routePathForDestination(sourceDestination);
  const relative = posix.relative(sourceRoute, target);
  if (relative === "") return suffix || ".";
  return `${relative}${suffix}`;
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
  const suffixAt = target.search(/[?#]/u);
  const path = suffixAt === -1 ? target : target.slice(0, suffixAt);
  const suffix = suffixAt === -1 ? "" : target.slice(suffixAt);
  if (path === deploymentBase || path.startsWith(`${deploymentBase}/`)) {
    const route = path.slice(deploymentBase.length).replace(/^\//u, "");
    return relativeRoute(source, route, suffix);
  }
  if (path.startsWith("/")) {
    return relativeRoute(source, path.replace(/^\//u, ""), suffix);
  }
  const isDirectory = path.endsWith("/");
  const resolvedSource = posix.normalize(posix.join(posix.dirname(source), path));
  if (resolvedSource === ".." || resolvedSource.startsWith("../")) {
    throw new Error(`documentation link escapes the repository: ${source} -> ${target}`);
  }

  const destination = destinationForSource(resolvedSource);
  if (destination !== null) {
    return relativeRoute(
      source,
      routePathForDestination(destination),
      suffix,
    );
  }
  return `${githubTarget(resolvedSource, isDirectory)}${suffix}`;
}

function isEscaped(content, index) {
  let backslashes = 0;
  for (let cursor = index - 1; cursor >= 0 && content[cursor] === "\\"; cursor--) {
    backslashes += 1;
  }
  return backslashes % 2 === 1;
}

function runLength(content, index, character) {
  let length = 0;
  while (content[index + length] === character) length += 1;
  return length;
}

function labelStart(line, closing) {
  let depth = 1;
  for (let cursor = closing - 1; cursor >= 0; cursor--) {
    if (isEscaped(line, cursor)) continue;
    if (line[cursor] === "]") depth += 1;
    if (line[cursor] === "[") {
      depth -= 1;
      if (depth === 0) return cursor;
    }
  }
  return -1;
}

function destinationEnd(line, start) {
  if (line[start] === "<") {
    for (let cursor = start + 1; cursor < line.length; cursor++) {
      if (line[cursor] === ">" && !isEscaped(line, cursor)) return cursor + 1;
    }
    return -1;
  }

  let depth = 0;
  for (let cursor = start; cursor < line.length; cursor++) {
    if (isEscaped(line, cursor)) continue;
    if (line[cursor] === "(") {
      depth += 1;
    } else if (line[cursor] === ")") {
      if (depth === 0) return cursor;
      depth -= 1;
    } else if (/\s/u.test(line[cursor]) && depth === 0) {
      return cursor;
    }
  }
  return -1;
}

function rewriteMarkdownLine(line, source, state) {
  const replacements = [];
  for (let cursor = 0; cursor < line.length; cursor++) {
    if (state.comment) {
      const end = line.indexOf("-->", cursor);
      if (end === -1) return line;
      state.comment = false;
      cursor = end + "-->".length - 1;
      continue;
    }
    if (line.startsWith("<!--", cursor)) {
      state.comment = true;
      cursor += "<!--".length - 1;
      continue;
    }
    if (line[cursor] === "`") {
      const length = runLength(line, cursor, "`");
      if (state.inlineCode === 0) {
        state.inlineCode = length;
      } else if (length === state.inlineCode) {
        state.inlineCode = 0;
      }
      cursor += length - 1;
      continue;
    }
    if (
      state.inlineCode !== 0 ||
      line[cursor] !== "]" ||
      line[cursor + 1] !== "(" ||
      isEscaped(line, cursor)
    ) {
      continue;
    }

    const opening = labelStart(line, cursor);
    if (opening === -1 || line[opening - 1] === "!") continue;
    const start = cursor + 2;
    const end = destinationEnd(line, start);
    if (end === -1 || end === start) continue;
    replacements.push({
      end,
      replacement: rewriteTarget(source, line.slice(start, end)),
      start,
    });
    cursor = end - 1;
  }

  let rewritten = line;
  for (const replacement of replacements.reverse()) {
    rewritten =
      rewritten.slice(0, replacement.start) +
      replacement.replacement +
      rewritten.slice(replacement.end);
  }
  return rewritten;
}

function rewriteMarkdownLinks(content, source) {
  const state = { comment: false, fence: null, inlineCode: 0 };
  return content
    .split(/(?<=\n)/u)
    .map((line) => {
      const marker = /^ {0,3}(`{3,}|~{3,})(.*)$/u.exec(line);
      if (state.fence !== null) {
        if (
          marker &&
          marker[1][0] === state.fence.character &&
          marker[1].length >= state.fence.length &&
          marker[2].trim() === ""
        ) {
          state.fence = null;
        }
        return line;
      }
      if (marker) {
        state.fence = { character: marker[1][0], length: marker[1].length };
        state.inlineCode = 0;
        return line;
      }
      return rewriteMarkdownLine(line, source, state);
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
    } else if (entry.isFile() && /\.(?:md|mdx)$/u.test(entry.name)) {
      await stageMarkdown(childSourcePath, childSource, childDestination);
    } else if (entry.isFile()) {
      continue;
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
