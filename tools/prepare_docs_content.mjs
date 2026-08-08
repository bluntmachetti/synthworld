import { constants } from "node:fs";
import {
  copyFile,
  mkdir,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import { dirname, join } from "node:path";

const sourceRoot = "docs";
const stagingRoot = ".blume-content";
const rootDocuments = [
  "AGENTIC_BENCHMARK.md",
  "BENCHMARKS.md",
  "DATA_DICTIONARY.md",
  "EVALUATION_KEY_CUSTODY.md",
  "GOLDEN_REVIEW.md",
];
const nestedDocuments = [
  "agent-authority-contract/README.md",
  "authority-governance-contract/README.md",
  "contextual-access-contract/README.md",
  "continuous-assurance-contract/README.md",
  "enterprise-identity-access-contract/README.md",
];

function compareNames(left, right) {
  if (left.name < right.name) return -1;
  if (left.name > right.name) return 1;
  return 0;
}

async function copyTree(source, destination) {
  await mkdir(destination, { recursive: true });
  const entries = await readdir(source, { withFileTypes: true });

  for (const entry of entries.sort(compareNames)) {
    const sourcePath = join(source, entry.name);
    const destinationPath = join(destination, entry.name);

    if (entry.isDirectory()) {
      await copyTree(sourcePath, destinationPath);
    } else if (entry.isFile()) {
      await copyFile(sourcePath, destinationPath, constants.COPYFILE_EXCL);
    } else {
      throw new Error(`unsupported documentation entry: ${sourcePath}`);
    }
  }
}

async function copyDocument(source, destination = source) {
  const destinationPath = join(stagingRoot, destination);
  await mkdir(dirname(destinationPath), { recursive: true });
  await copyFile(source, destinationPath, constants.COPYFILE_EXCL);
}

async function writeDocument(destination, content) {
  const destinationPath = join(stagingRoot, destination);
  await mkdir(dirname(destinationPath), { recursive: true });
  await writeFile(destinationPath, content, { encoding: "utf8", flag: "wx" });
}

async function adaptDocument(source, replacements) {
  let content = await readFile(source, "utf8");
  for (const [match, replacement] of replacements) {
    content = content.replaceAll(match, replacement);
  }
  await writeDocument(source, content);
}

await rm(stagingRoot, { force: true, recursive: true });
await copyTree(sourceRoot, stagingRoot);
for (const document of [...rootDocuments, ...nestedDocuments]) {
  await copyDocument(document);
}
await adaptDocument("README.md", [
  ["(LICENSE)", "(https://github.com/bluntmachetti/synthworld/blob/main/LICENSE)"],
  ["(Makefile)", "(https://github.com/bluntmachetti/synthworld/blob/main/Makefile)"],
  ["(docs/index.md)", "(index.md)"],
  [
    "(examples/)",
    "(https://github.com/bluntmachetti/synthworld/tree/main/examples)",
  ],
]);
await adaptDocument("ROADMAP.md", [
  ["(docs/roadmap/index.md)", "(roadmap/index.md)"],
]);
await adaptDocument("USER_GUIDE.md", [["(docs/index.md)", "(index.md)"]]);
await writeDocument(
  "CHANGELOG.md",
  `---
title: Changelog shortcut
description: Stable link to the complete SynthWorld release history.
---

# Changelog shortcut

Read the [complete release history](changelog/CHANGELOG.md).
`,
);
const changelog = (await readFile("CHANGELOG.md", "utf8"))
  .replaceAll("(DATA_DICTIONARY.md)", "(../DATA_DICTIONARY.md)")
  .replaceAll("(GOLDEN_REVIEW.md)", "(../GOLDEN_REVIEW.md)");
await writeDocument("changelog/CHANGELOG.md", changelog);
await writeDocument(
  "huggingface/README.md",
  `---
title: Hugging Face dataset card
description: Source reference for the historical SynthWorld dataset card.
---

# Hugging Face dataset card

The repository retains a historical dataset card for compatibility and review.
Read the [source dataset card](https://github.com/bluntmachetti/synthworld/blob/main/huggingface/README.md) on GitHub.
`,
);

console.log(`prepared deterministic documentation content in ${stagingRoot}/`);
