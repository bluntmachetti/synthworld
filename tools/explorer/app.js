import cytoscape from "cytoscape";

import { applyReplayState, indexRevocations } from "./replay.mjs";

const parseData = (id) => JSON.parse(document.getElementById(id).textContent);
const projection = parseData("synthworld-projection");
const layout = parseData("synthworld-layout");
const overlayNode = document.getElementById("synthworld-evaluator-overlay");
const overlay = overlayNode ? JSON.parse(overlayNode.textContent) : null;
const coordinateByNode = new Map(
  layout.coordinates.map((coordinate) => [coordinate.node_id, coordinate]),
);
const annotationsByTarget = new Map();

for (const annotation of overlay?.annotations ?? []) {
  const annotations = annotationsByTarget.get(annotation.target_id) ?? [];
  annotations.push(annotation);
  annotationsByTarget.set(annotation.target_id, annotations);
}

const propertyObject = (properties) =>
  Object.fromEntries(properties.map((property) => [property.key, property.value]));

const elements = [
  ...projection.nodes.map((node) => ({
    group: "nodes",
    data: {
      id: node.id,
      sourceId: node.source_id,
      kind: node.kind,
      label: node.label,
      parent: node.parent_node_id,
      properties: propertyObject(node.properties),
    },
    position: {
      x: coordinateByNode.get(node.id).x,
      y: coordinateByNode.get(node.id).y,
    },
  })),
  ...projection.edges.map((edge) => ({
    group: "edges",
    data: {
      id: edge.id,
      source: edge.source_node_id,
      target: edge.target_node_id,
      kind: edge.kind,
      label: edge.label,
      properties: propertyObject(edge.properties),
    },
  })),
];

const nodeColors = {
  organisation: "#12323a",
  department: "#1b5960",
  principal: "#147d7e",
  logical_agent: "#2e9d8f",
  runtime: "#76b7a8",
  credential: "#d19a24",
  delegation: "#d4a72c",
  proposed_delegation: "#ef8d32",
  resource: "#526b78",
  action_attempt: "#e2583e",
};

const cy = cytoscape({
  container: document.getElementById("synthworld-graph"),
  elements,
  layout: { name: "preset", fit: true, padding: 36 },
  minZoom: 0.08,
  maxZoom: 3,
  wheelSensitivity: 0.16,
  style: [
    {
      selector: "node",
      style: {
        "background-color": (element) => nodeColors[element.data("kind")] ?? "#526b78",
        "border-color": "#102a31",
        "border-width": 1.5,
        color: "#102a31",
        "font-family": "ui-monospace, SFMono-Regular, Menlo, monospace",
        "font-size": 9,
        height: 38,
        label: "data(label)",
        "min-zoomed-font-size": 7,
        padding: 12,
        shape: "round-rectangle",
        "text-background-color": "#fffdf6",
        "text-background-opacity": 0.92,
        "text-background-padding": 3,
        "text-max-width": 150,
        "text-wrap": "ellipsis",
        width: 150,
      },
    },
    {
      selector: ":parent",
      style: {
        "background-opacity": 0.06,
        "border-style": "dashed",
        "font-size": 10,
        "font-weight": 700,
        padding: 24,
        "text-valign": "top",
      },
    },
    {
      selector: "edge",
      style: {
        "curve-style": "bezier",
        "line-color": "#91a29f",
        opacity: 0.42,
        "target-arrow-color": "#91a29f",
        "target-arrow-shape": "triangle",
        width: 1,
      },
    },
    {
      selector: 'edge[kind = "delegates"], edge[kind = "grants_to"], edge[kind = "parent_delegation"]',
      style: { "line-color": "#c88c18", "target-arrow-color": "#c88c18", width: 2 },
    },
    {
      selector: 'edge[kind = "attempts"], edge[kind = "presents"]',
      style: { "line-color": "#e2583e", "target-arrow-color": "#e2583e", width: 2 },
    },
    {
      selector: ".future",
      style: { display: "none" },
    },
    {
      selector: ".revoked",
      style: {
        "background-color": "#a4aaa8",
        "line-color": "#a4aaa8",
        opacity: 0.28,
        "target-arrow-color": "#a4aaa8",
      },
    },
    {
      selector: ".event-focus",
      style: { "border-color": "#ff4f36", "border-width": 4, opacity: 1, "z-index": 100 },
    },
    {
      selector: ":selected",
      style: { "border-color": "#ff4f36", "border-width": 4, opacity: 1 },
    },
  ],
});

const firstNodeEvent = new Map();
const firstEdgeEvent = new Map();
for (const event of projection.timeline) {
  for (const id of event.related_node_ids) {
    if (!firstNodeEvent.has(id)) firstNodeEvent.set(id, event.source_event_index);
  }
  for (const id of event.related_edge_ids) {
    if (!firstEdgeEvent.has(id)) firstEdgeEvent.set(id, event.source_event_index);
  }
}

const inspectorTitle = document.getElementById("synthworld-inspector-title");
const inspectorKind = document.getElementById("synthworld-inspector-kind");
const inspectorProperties = document.getElementById("synthworld-inspector-properties");
const inspectorTruth = document.getElementById("synthworld-inspector-truth");

const appendDefinition = (container, key, value) => {
  const term = document.createElement("dt");
  term.textContent = key;
  const description = document.createElement("dd");
  description.textContent = Array.isArray(value) ? value.join(", ") : String(value);
  container.append(term, description);
};

const inspect = (element) => {
  const data = element.data();
  inspectorTitle.textContent = data.label ?? data.id;
  inspectorKind.textContent = String(data.kind ?? element.group()).replaceAll("_", " ");
  inspectorProperties.replaceChildren();
  appendDefinition(inspectorProperties, "id", data.id);
  if (data.sourceId) appendDefinition(inspectorProperties, "source id", data.sourceId);
  for (const [key, value] of Object.entries(data.properties ?? {})) {
    appendDefinition(inspectorProperties, key.replaceAll("_", " "), value);
  }
  inspectorTruth.replaceChildren();
  for (const annotation of annotationsByTarget.get(data.id) ?? []) {
    const article = document.createElement("article");
    const heading = document.createElement("h4");
    heading.textContent = annotation.label;
    const value = document.createElement("p");
    value.textContent = annotation.value;
    article.append(heading, value);
    const details = document.createElement("dl");
    for (const property of annotation.properties) {
      appendDefinition(details, property.key.replaceAll("_", " "), property.value);
    }
    article.append(details);
    inspectorTruth.append(article);
  }
};

cy.on("tap", "node, edge", (event) => inspect(event.target));

const slider = document.getElementById("synthworld-timeline-slider");
const timelineLabel = document.getElementById("synthworld-timeline-label");
const eventButtons = document.getElementById("synthworld-event-buttons");
const { nodeRevokedAt, edgeRevokedAt } = indexRevocations(
  projection.timeline,
  projection.edges,
);

const setTick = (tick) => {
  const selectedEvent = projection.timeline.find((event) => event.source_event_index === tick);
  cy.batch(() => {
    applyReplayState({
      cy,
      edgeRevokedAt,
      firstEdgeEvent,
      firstNodeEvent,
      nodeRevokedAt,
      selectedEvent,
      tick,
    });
  });
  timelineLabel.textContent = selectedEvent
    ? `tick ${String(tick).padStart(2, "0")} / ${selectedEvent.kind.replaceAll("_", " ")}`
    : "tick 00 / initial world";
  for (const button of eventButtons.children) {
    button.toggleAttribute("aria-current", Number(button.dataset.tick) === tick);
  }
};

for (const event of projection.timeline) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.tick = String(event.source_event_index);
  button.textContent = `${String(event.source_event_index).padStart(2, "0")} ${event.kind.replaceAll("_", " ")}`;
  button.addEventListener("click", () => {
    slider.value = String(event.source_event_index);
    setTick(event.source_event_index);
  });
  eventButtons.append(button);
}

slider.max = String(projection.timeline.length);
slider.addEventListener("input", () => setTick(Number(slider.value)));
document.getElementById("synthworld-fit").addEventListener("click", () => cy.fit(undefined, 36));
document.getElementById("synthworld-reset").addEventListener("click", () => {
  slider.value = String(projection.timeline.length);
  setTick(projection.timeline.length);
  cy.fit(undefined, 36);
});

setTick(projection.timeline.length);
if (cy.nodes().length > 0) inspect(cy.nodes()[0]);
