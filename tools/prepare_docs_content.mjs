import { constants } from "node:fs";
import { copyFile, mkdir, readdir, rm } from "node:fs/promises";
import { join } from "node:path";

const sourceRoot = "docs";
const stagingRoot = ".blume-content";

async function copyTree(source, destination) {
  await mkdir(destination, { recursive: true });
  const entries = await readdir(source, { withFileTypes: true });

  for (const entry of entries.sort((left, right) =>
    left.name.localeCompare(right.name),
  )) {
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

await rm(stagingRoot, { force: true, recursive: true });
await copyTree(sourceRoot, stagingRoot);
await mkdir(join(stagingRoot, "changelog"), { recursive: true });
await copyFile(
  "CHANGELOG.md",
  join(stagingRoot, "changelog", "CHANGELOG.md"),
  constants.COPYFILE_EXCL,
);

console.log(`prepared deterministic documentation content in ${stagingRoot}/`);
