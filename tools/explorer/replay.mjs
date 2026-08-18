const authorityEdgeKinds = new Set([
  "delegates",
  "grants_to",
  "parent_delegation",
  "targets",
]);

const recordEarliestTick = (ticks, id, tick) => {
  if (!ticks.has(id) || tick < ticks.get(id)) ticks.set(id, tick);
};

export const indexRevocations = (timeline, edges) => {
  const nodeRevokedAt = new Map();
  const edgeRevokedAt = new Map();
  for (const event of timeline) {
    if (event.kind !== "delegation_revoked") continue;
    for (const nodeId of event.related_node_ids) {
      recordEarliestTick(nodeRevokedAt, nodeId, event.source_event_index);
      for (const edge of edges) {
        if (
          authorityEdgeKinds.has(edge.kind) &&
          (edge.source_node_id === nodeId || edge.target_node_id === nodeId)
        ) {
          recordEarliestTick(edgeRevokedAt, edge.id, event.source_event_index);
        }
      }
    }
  }
  return { nodeRevokedAt, edgeRevokedAt };
};

export const isRevokedAt = (ticks, id, tick) =>
  (ticks.get(id) ?? Number.POSITIVE_INFINITY) <= tick;

export const applyReplayState = ({
  cy,
  edgeRevokedAt,
  firstEdgeEvent,
  firstNodeEvent,
  nodeRevokedAt,
  selectedEvent,
  tick,
}) => {
  cy.elements().removeClass("future event-focus revoked");
  cy.nodes().forEach((node) => {
    const first = firstNodeEvent.get(node.id()) ?? 0;
    node.toggleClass("future", first > tick);
    node.toggleClass("revoked", isRevokedAt(nodeRevokedAt, node.id(), tick));
  });
  cy.edges().forEach((edge) => {
    const first = firstEdgeEvent.get(edge.id()) ?? 0;
    edge.toggleClass("future", first > tick);
    edge.toggleClass("revoked", isRevokedAt(edgeRevokedAt, edge.id(), tick));
  });
  if (selectedEvent) {
    for (const id of selectedEvent.related_node_ids) cy.getElementById(id).addClass("event-focus");
    for (const id of selectedEvent.related_edge_ids) cy.getElementById(id).addClass("event-focus");
  }
};
