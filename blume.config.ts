import { defineConfig } from "blume";

export default defineConfig({
  title: "SynthWorld",
  description:
    "Deterministic synthetic identity data and ground-truth benchmarks.",
  content: {
    sources: [{ type: "filesystem", root: ".blume-content" }],
  },
  github: {
    owner: "bluntmachetti",
    repo: "synthworld",
    branch: "main",
  },
  navigation: {
    sidebar: {
      display: "group",
      items: [
        "/",
        "/getting-started",
        {
          label: "Guides",
          collapsed: true,
          items: [
            "/guides",
            "/guides/identity-worlds",
            "/guides/identity-resolution",
            "/guides/privacy-exposure",
            "/guides/agent-authority",
            "/guides/enterprise-access",
            "/guides/enterprise-identity-planning",
            "/guides/evaluating-a-system",
          ],
        },
        {
          label: "Benchmarks",
          collapsed: true,
          items: [
            "/benchmarks",
            "/benchmarks/catalogue",
            "/AGENTIC_BENCHMARK",
            "/BENCHMARKS",
            "/GOLDEN_REVIEW",
            "/EVALUATION_KEY_CUSTODY",
          ],
        },
        {
          label: "Concepts",
          collapsed: true,
          items: [
            "/concepts",
            "/concepts/benchmark-model",
            "/concepts/public-vs-evaluator",
            "/concepts/determinism-seeds-and-keys",
            "/concepts/explorer-v01",
            "/concepts/conformance-vs-generalisation",
            "/concepts/benchmark-publication",
            "/concepts/safety-boundary",
          ],
        },
        {
          label: "Contracts",
          collapsed: true,
          items: [
            "/agent-authority-contract/README",
            "/authority-governance-contract/README",
            "/contextual-access-contract/README",
            "/continuous-assurance-contract/README",
            "/enterprise-identity-access-contract/README",
            "/decisions/benchmark-publication-governance",
          ],
        },
        {
          label: "Reference",
          collapsed: true,
          items: [
            "/reference",
            "/reference/capabilities",
            "/reference/benchmarks",
            "/reference/cli",
            "/reference/metrics",
            "/reference/schemas",
            "/reference/standards-profiles",
            "/DATA_DICTIONARY",
          ],
        },
        {
          label: "Project",
          collapsed: true,
          items: [
            "/experiments",
            "/roadmap",
            "/ROADMAP",
            "/support",
            "/support/contributing-documentation",
            "/changelog/CHANGELOG",
            "/migration-index",
            "/README",
            "/USER_GUIDE",
            "/huggingface/README",
          ],
        },
      ],
    },
  },
  search: {
    provider: "orama",
    popular: [
      { href: "/getting-started", label: "Getting started", icon: "rocket" },
      { href: "/guides", label: "Guides", icon: "book-open" },
      { href: "/benchmarks", label: "Benchmarks", icon: "gauge" },
      { href: "/reference", label: "Reference", icon: "braces" },
    ],
  },
  theme: {
    accent: { light: "#1976ad", dark: "#46b6f0" },
    action: "#46b6f0",
    background: { light: "#f6f8fb", dark: "#090c13" },
    fonts: {
      body: "ibm-plex-sans",
      display: "ibm-plex-sans",
      mono: "ibm-plex-mono",
    },
    mode: "dark",
    radius: "sm",
  },
  ai: {
    llmsTxt: false,
    ask: {
      enabled: false,
    },
    mcp: {
      enabled: false,
    },
    webmcp: false,
  },
  seo: {
    og: { enabled: false },
    rss: { enabled: false },
    sitemap: true,
    robots: true,
    structuredData: true,
    agentReadability: false,
  },
  deployment: {
    output: "static",
    site: "https://bluntmachetti.github.io",
    base: "/synthworld",
  },
});
