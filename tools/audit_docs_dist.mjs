import { readFile, readdir, stat } from "node:fs/promises";
import { extname, join, relative, sep } from "node:path";

const outputRoot = "dist";
const deploymentBase = "/synthworld";
const forbiddenPaths = new Set([
  "agent-readability.json",
  "llms-full.txt",
  "llms.txt",
]);
const forbiddenOutputPathPatterns = [
  /(?:^|\/)\.well-known\/(?:api-catalog|mcp(?:\.json|\/server-card\.json))(?:\/|$)/,
  /(?:^|\/)(?:api\/ask|ask-ai|mcp|webmcp)(?:\/|$)/,
];
const forbiddenOpaqueExtensions = new Set([".br", ".gz", ".tar", ".tgz", ".zip"]);
const forbiddenSurfacePatterns = [
  ["Ask AI endpoint", /\/(?:api\/ask|ask-ai)(?:["'/?#]|$)/],
  [
    "agent discovery surface",
    /\/(?:agent-readability\.json|llms(?:-full)?\.txt|\.well-known\/(?:api-catalog|mcp(?:\.json|\/server-card\.json)))(?:["'/?#]|$)/,
  ],
  ["WebMCP registration", /(?:navigator|document)\.modelContext|provideContext|registerTool\s*\(/],
];
const forbiddenLeakPatterns = [
  ["absolute home path", /\/home\/[A-Za-z0-9._-]+\//],
  ["GitHub Actions workspace path", /\/github\/workspace(?:\/|$)/],
  ["AWS access key", /AKIA[0-9A-Z]{16}/],
  ["GitHub token", /(?:github_pat_|gh[oprs]_)[A-Za-z0-9_]{20,}/],
  ["Anthropic API key", /sk-ant-[A-Za-z0-9_-]{20,}/],
  ["OpenAI project key", /sk-proj-[A-Za-z0-9_-]{20,}/],
  ["generic secret key", /sk-(?!(?:ant|proj)-)[A-Za-z0-9]{20,}/],
  ["Hugging Face token", /hf_[A-Za-z0-9]{30,}/],
  ["npm token", /npm_[A-Za-z0-9]{30,}/],
  ["Slack token", /xox[baprs]-[A-Za-z0-9-]{20,}/],
  ["private key block", /-----BEGIN (?:EC |OPENSSH |PGP |RSA )?PRIVATE KEY-----/],
  ["AWS session token", /(?:AWS_SESSION_TOKEN|aws_session_token)["'=:\s]+[A-Za-z0-9/+=]{40,}/],
  [
    "answer-key field",
    /(?:(?:"|'|&quot;|&#34;)?(?:expected[_-]?verdict|canonical[_-]?binding|case[_-]?label|ownership[_-]?truth)(?:"|'|&quot;|&#34;)?)\s*[:=]/i,
  ],
  [
    "serialized oracle value",
    /(?:(?:"|'|&quot;|&#34;)?oracle(?:"|'|&quot;|&#34;)?)\s*[:=]\s*(?:\{|\[|"|'|&quot;|&#34;|true|false|null)/i,
  ],
];
const textExtensions = new Set([
  ".css",
  ".html",
  ".js",
  ".json",
  ".map",
  ".md",
  ".mdx",
  ".svg",
  ".txt",
  ".xml",
]);

async function walk(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const paths = [];
  for (const entry of entries.sort((left, right) => left.name.localeCompare(right.name))) {
    const path = join(directory, entry.name);
    if (entry.isDirectory()) {
      paths.push(...(await walk(path)));
    } else if (entry.isFile()) {
      paths.push(path);
    }
  }
  return paths;
}

function displayPath(path) {
  return relative(outputRoot, path).split(sep).join("/");
}

function fail(message) {
  console.error(`docs output audit failed: ${message}`);
  process.exitCode = 1;
}

function auditRootReference(target, renderedPath) {
  const normalizedTarget = target.split(/[?#]/, 1)[0];
  if (
    normalizedTarget !== deploymentBase &&
    !normalizedTarget.startsWith(`${deploymentBase}/`)
  ) {
    fail(
      `root-relative URL ${normalizedTarget} in ${renderedPath} bypasses ${deploymentBase}/`,
    );
  }
}

try {
  await stat(join(outputRoot, "index.html"));
  await stat(join(outputRoot, "blume-search.json"));
  await stat(join(outputRoot, "changelog", "CHANGELOG", "index.html"));
} catch {
  fail("production HTML, changelog route, or the local search index is missing");
}

let outputFiles = [];
try {
  outputFiles = await walk(outputRoot);
} catch {
  fail("dist/ does not exist; run the production build first");
}

for (const path of outputFiles) {
  const renderedPath = displayPath(path);
  const segments = renderedPath.split("/");
  if (
    segments.some((segment) => forbiddenPaths.has(segment)) ||
    forbiddenOutputPathPatterns.some((pattern) => pattern.test(renderedPath)) ||
    renderedPath === ".well-known/mcp.json" ||
    renderedPath === ".well-known/mcp/server-card.json"
  ) {
    fail(`forbidden agent-facing artifact emitted at ${renderedPath}`);
  }
  if (forbiddenOpaqueExtensions.has(extname(path))) {
    fail(`opaque compressed artifact emitted at ${renderedPath}`);
  }

  const text = (await readFile(path)).toString("utf8");
  for (const [label, pattern] of forbiddenLeakPatterns) {
    if (pattern.test(text)) {
      fail(`${label} found in ${renderedPath}`);
    }
  }

  if (!textExtensions.has(extname(path))) {
    continue;
  }

  for (const [label, pattern] of forbiddenSurfacePatterns) {
    if (pattern.test(text)) {
      fail(`${label} found in ${renderedPath}`);
    }
  }

  if (extname(path) === ".html") {
    const rootReference = /(?:action|href|poster|src)=["'](\/(?!\/)[^"']*)["']/g;
    for (const match of text.matchAll(rootReference)) {
      auditRootReference(match[1], renderedPath);
    }
    const sourceSet = /srcset=["']([^"']+)["']/g;
    for (const match of text.matchAll(sourceSet)) {
      for (const candidate of match[1].split(",")) {
        const target = candidate.trim().split(/\s+/, 1)[0];
        if (target.startsWith("/") && !target.startsWith("//")) {
          auditRootReference(target, renderedPath);
        }
      }
    }
  }

  if (extname(path) === ".css") {
    const cssRootReference = /url\(\s*["']?(\/(?!\/)[^"')\s]+)["']?\s*\)/g;
    for (const match of text.matchAll(cssRootReference)) {
      auditRootReference(match[1], renderedPath);
    }
  }

  if (extname(path) === ".js") {
    const scriptRootReference = /["'`](\/(?!\/)[A-Za-z0-9._~-][^"'`\r\n]*)["'`]/g;
    for (const match of text.matchAll(scriptRootReference)) {
      auditRootReference(match[1], renderedPath);
    }
  }
}

if (process.exitCode) {
  process.exit(process.exitCode);
}

console.log(
  `docs output audit passed: ${outputFiles.length} files, local search present, base path ${deploymentBase}/`,
);
