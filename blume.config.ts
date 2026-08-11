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
    tabs: [
      { label: "Home", path: "/", href: "/" },
      { label: "Getting Started", path: "/getting-started" },
      { label: "Guides", path: "/guides" },
      { label: "Benchmarks", path: "/benchmarks" },
      { label: "Experiments", path: "/experiments" },
      { label: "Roadmap", path: "/roadmap" },
      { label: "Support", path: "/support" },
      { label: "Reference", path: "/reference" },
    ],
    featured: [
      {
        label: "Changelog",
        href: "/changelog/CHANGELOG",
        icon: "history",
      },
    ],
    sidebar: {
      display: "group",
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
    accent: "teal",
    mode: "system",
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
