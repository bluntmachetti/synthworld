import assert from "node:assert/strict";
import test from "node:test";

import { applyReplayState, indexRevocations, isRevokedAt } from "./replay.mjs";

const fakeElement = (id) => ({
  addClass(name) {
    this.classes.add(name);
  },
  classes: new Set(),
  id: () => id,
  toggleClass(name, enabled) {
    if (enabled) this.classes.add(name);
    else this.classes.delete(name);
  },
});

const fakeCollection = (items) => ({
  forEach(callback) {
    items.forEach(callback);
  },
  removeClass(names) {
    for (const item of items) {
      for (const name of names.split(" ")) item.classes.delete(name);
    }
  },
});

test("revocation propagates to delegation authority edges at the event tick", () => {
  const delegationId = "delegation-1";
  const timeline = [
    {
      kind: "delegation_revoked",
      related_node_ids: [delegationId],
      source_event_index: 19,
    },
  ];
  const authorityKinds = ["delegates", "grants_to", "parent_delegation", "targets"];
  const edges = authorityKinds.map((kind, index) => ({
    id: `authority-${String(index)}`,
    kind,
    source_node_id: index % 2 === 0 ? delegationId : "other",
    target_node_id: index % 2 === 0 ? "other" : delegationId,
  }));
  edges.push({
    id: "unrelated-ownership",
    kind: "owns",
    source_node_id: delegationId,
    target_node_id: "other",
  });

  const { nodeRevokedAt, edgeRevokedAt } = indexRevocations(timeline, edges);

  assert.equal(isRevokedAt(nodeRevokedAt, delegationId, 18), false);
  assert.equal(isRevokedAt(nodeRevokedAt, delegationId, 19), true);
  for (const edge of edges.slice(0, authorityKinds.length)) {
    assert.equal(isRevokedAt(edgeRevokedAt, edge.id, 18), false);
    assert.equal(isRevokedAt(edgeRevokedAt, edge.id, 19), true);
  }
  assert.equal(edgeRevokedAt.has("unrelated-ownership"), false);
});

test("the first revocation tick wins and unrelated events do not revoke edges", () => {
  const edges = [
    {
      id: "delegates-edge",
      kind: "delegates",
      source_node_id: "principal-1",
      target_node_id: "delegation-1",
    },
  ];
  const timeline = [
    {
      kind: "delegation_granted",
      related_node_ids: ["delegation-1"],
      source_event_index: 1,
    },
    {
      kind: "delegation_revoked",
      related_node_ids: ["delegation-1"],
      source_event_index: 9,
    },
    {
      kind: "delegation_revoked",
      related_node_ids: ["delegation-1"],
      source_event_index: 12,
    },
  ];

  const { nodeRevokedAt, edgeRevokedAt } = indexRevocations(timeline, edges);

  assert.equal(nodeRevokedAt.get("delegation-1"), 9);
  assert.equal(edgeRevokedAt.get("delegates-edge"), 9);
});

test("replay applies revoked state to both delegation nodes and authority edges", () => {
  const node = fakeElement("delegation-1");
  const edge = fakeElement("delegates-edge");
  const all = [node, edge];
  const byId = new Map(all.map((item) => [item.id(), item]));
  const cy = {
    edges: () => fakeCollection([edge]),
    elements: () => fakeCollection(all),
    getElementById: (id) => byId.get(id),
    nodes: () => fakeCollection([node]),
  };
  const common = {
    cy,
    edgeRevokedAt: new Map([[edge.id(), 19]]),
    firstEdgeEvent: new Map([[edge.id(), 1]]),
    firstNodeEvent: new Map([[node.id(), 1]]),
    nodeRevokedAt: new Map([[node.id(), 19]]),
    selectedEvent: null,
  };

  applyReplayState({ ...common, tick: 18 });
  assert.equal(node.classes.has("revoked"), false);
  assert.equal(edge.classes.has("revoked"), false);

  applyReplayState({ ...common, tick: 19 });
  assert.equal(node.classes.has("revoked"), true);
  assert.equal(edge.classes.has("revoked"), true);
});
