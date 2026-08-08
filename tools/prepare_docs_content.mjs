import { constants } from "node:fs";
import { copyFile, mkdir, readdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";

const sourceRoot = "docs";
const stagingRoot = ".blume-content";
const rootDocuments = [
  "AGENTIC_BENCHMARK.md",
  "BENCHMARKS.md",
  "CHANGELOG.md",
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
  "huggingface/README.md",
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

await rm(stagingRoot, { force: true, recursive: true });
await copyTree(sourceRoot, stagingRoot);
for (const document of [...rootDocuments, ...nestedDocuments]) {
  await copyDocument(document);
}
await copyDocument("CHANGELOG.md", "changelog/CHANGELOG.md");

console.log(`prepared deterministic documentation content in ${stagingRoot}/`);
