import { readFile, readdir, writeFile } from "node:fs/promises";
import { extname, join } from "node:path";

const stagingRoot = process.argv[2] ?? ".blume-content";

function compareNames(left, right) {
  if (left.name < right.name) return -1;
  if (left.name > right.name) return 1;
  return 0;
}

function parseFrontmatterTitle(lines, end) {
  for (let index = 1; index < end; index++) {
    const match = /^title:\s*(.*?)\s*$/u.exec(lines[index]);
    if (!match) continue;
    const value = match[1];
    if (value.startsWith('"') && value.endsWith('"')) {
      try {
        return JSON.parse(value);
      } catch {
        return value.slice(1, -1);
      }
    }
    if (value.startsWith("'") && value.endsWith("'")) {
      return value.slice(1, -1).replaceAll("''", "'");
    }
    return value;
  }
  return null;
}

function frontmatter(lines, path) {
  if (lines[0] !== "---") return null;
  const end = lines.indexOf("---", 1);
  if (end === -1) {
    throw new Error(`unterminated frontmatter in staged document: ${path}`);
  }
  return { end, title: parseFrontmatterTitle(lines, end) };
}

function leadingH1(lines, start) {
  let index = start;
  while (index < lines.length && lines[index].trim() === "") index += 1;
  if (index >= lines.length) return null;
  const match = /^#\s+(.+?)(?:\s+#+)?\s*$/u.exec(lines[index]);
  if (!match) return null;
  return { index, title: match[1].trim() };
}

function comparableTitle(value) {
  return value.trim().replace(/\s+/gu, " ");
}

function removeHeading(lines, index) {
  lines.splice(index, 1);
  if (index < lines.length && lines[index].trim() === "") {
    lines.splice(index, 1);
  }
}

function normalizeDocument(content, path) {
  const hadFinalNewline = content.endsWith("\n");
  const lines = content.split("\n");
  const metadata = frontmatter(lines, path);
  const heading = leadingH1(lines, metadata === null ? 0 : metadata.end + 1);
  if (heading === null) return content;

  if (metadata !== null && metadata.title !== null) {
    if (comparableTitle(metadata.title) !== comparableTitle(heading.title)) {
      return content;
    }
    removeHeading(lines, heading.index);
  } else if (metadata !== null) {
    removeHeading(lines, heading.index);
    lines.splice(metadata.end, 0, `title: ${JSON.stringify(heading.title)}`);
  } else {
    removeHeading(lines, heading.index);
    lines.unshift("---", `title: ${JSON.stringify(heading.title)}`, "---", "");
  }

  let normalized = lines.join("\n");
  if (hadFinalNewline && !normalized.endsWith("\n")) normalized += "\n";
  return normalized;
}

async function markdownFiles(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries.sort(compareNames)) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await markdownFiles(path)));
    } else if (entry.isFile() && [".md", ".mdx"].includes(extname(entry.name))) {
      files.push(path);
    } else if (!entry.isFile()) {
      throw new Error(`unsupported staged documentation entry: ${path}`);
    }
  }
  return files;
}

let changed = 0;
for (const path of await markdownFiles(stagingRoot)) {
  const content = await readFile(path, "utf8");
  const normalized = normalizeDocument(content, path);
  if (normalized === content) continue;
  await writeFile(path, normalized, "utf8");
  changed += 1;
}

console.log(`normalized Blume page headings in ${changed} staged document(s)`);
