import { readFile, readdir } from "node:fs/promises";
import { extname, join, relative, sep } from "node:path";

const outputRoot = process.argv[2] ?? "dist";

function compareNames(left, right) {
  if (left.name < right.name) return -1;
  if (left.name > right.name) return 1;
  return 0;
}

async function htmlFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries.sort(compareNames)) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await htmlFiles(path)));
    } else if (entry.isFile() && extname(entry.name).toLowerCase() === ".html") {
      files.push(path);
    }
  }
  return files;
}

function displayPath(path) {
  return relative(outputRoot, path).split(sep).join("/");
}

let audited = 0;
for (const path of await htmlFiles(outputRoot)) {
  const content = await readFile(path, "utf8");
  const headings = content.match(/<h1(?:\s[^>]*)?>[\s\S]*?<\/h1>/giu) ?? [];
  if (headings.length > 1) {
    console.error(
      `docs heading audit failed: ${headings.length} H1 elements found in ${displayPath(path)}`,
    );
    process.exitCode = 1;
  }
  audited += 1;
}

if (process.exitCode) process.exit(process.exitCode);
console.log(`docs heading audit passed: ${audited} HTML page(s), at most one H1 each`);
