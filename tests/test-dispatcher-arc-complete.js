// Day 73 — tests for the arc-complete trigger addition to dispatcher.js
// (priority queue item 3). Same house style as the rest of the suite:
// hand-rolled assertions, zero deps, run with plain `node`.

const assert = require('assert');
const { Dispatcher, DispatchError } = require('../static_dispatcher.js');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    passed++;
    console.log(`[PASS] ${name}`);
  } catch (e) {
    failed++;
    console.log(`[FAIL] ${name}`);
    console.log(`       ${e.stack || e.message}`);
  }
}

const emptyFieldMap = { fields: [] };

function freshDispatcher() {
  const d = new Dispatcher();
  d.registerActor('Cindy', emptyFieldMap, { gesture: { kind: 'gesture' } });
  return d;
}

// ── firing semantics: bare vs zone-scoped ──────────────────────────────

test('bare arc-complete fires when fireArcComplete() called with no zoneId', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' },
    duration: { certainty: 'estimate' },
  });
  d.fireArcComplete();
  const started = d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1');
  assert.strictEqual(started.length, 1);
});

test('bare arc-complete fires for ANY zoneId (unconditional)', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' },
    duration: { certainty: 'estimate' },
  });
  d.fireArcComplete('PoolZone');
  const started = d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1');
  assert.strictEqual(started.length, 1);
});

test('zone-scoped arc-complete:PoolZone fires only for matching zoneId', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete', zone: 'PoolZone' },
    duration: { certainty: 'estimate' },
  });
  d.fireArcComplete('GardenZone');
  assert.strictEqual(d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1').length, 0, 'should not fire for wrong zone');
  d.fireArcComplete();
  assert.strictEqual(d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1').length, 0, 'should not fire for bare/undefined zoneId');
  d.fireArcComplete('PoolZone');
  assert.strictEqual(d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1').length, 1, 'should fire for matching zone');
});

test('fireArcComplete can fire the same step more than once (no one-shot bookkeeping, unlike declared)', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' },
    duration: { certainty: 'estimate' },
  });
  d.fireArcComplete();
  d.arrived('s1'); // clears track so second fire isn't itself a same-step collision no-op
  d.fireArcComplete();
  const started = d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 's1');
  assert.strictEqual(started.length, 2);
});

// ── collision-policy handling (shared with declared) ───────────────────

test('arc-complete default (interrupt) displaces an active step on the same track', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'running', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'scene-start' },
    duration: { certainty: 'estimate' },
  });
  d.addStep({
    id: 'arc_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' },
    duration: { certainty: 'estimate' },
  });
  d.sceneStart(); // 'running' now active on gesture track
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'running');
  d.fireArcComplete();
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'arc_line', 'interrupt should displace via Welder');
  const stopped = d.eventLog.filter((e) => e.verb === 'stop' && e.stepId === 'running');
  assert.strictEqual(stopped.length, 1, 'displaced step should have been stopped');
});

test('arc-complete with onCollision=overlap does not displace the track', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'running', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'scene-start' },
    duration: { certainty: 'estimate' },
  });
  d.addStep({
    id: 'arc_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' }, onCollision: 'overlap',
    duration: { certainty: 'estimate' },
  });
  d.sceneStart();
  d.fireArcComplete();
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'running', 'overlap should NOT displace the running step');
  const overlapEntries = d.eventLog.filter((e) => e.stepId === 'arc_line' && e.detail === 'overlap — no track displacement');
  assert.strictEqual(overlapEntries.length, 1);
});

test('arc-complete with onCollision=wait queues behind the active step, fires on arrived()', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'running', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'scene-start' },
    duration: { certainty: 'estimate' },
  });
  d.addStep({
    id: 'arc_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' }, onCollision: 'wait',
    duration: { certainty: 'estimate' },
  });
  d.sceneStart();
  d.fireArcComplete();
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'running', 'wait should not start immediately');
  d.arrived('running'); // running finishes on its own, drains wait queue
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'arc_line', 'queued arc-complete step should start once queue drains');
});

// ── addStep validation ──────────────────────────────────────────────────

test('addStep accepts bare arc-complete trigger', () => {
  const d = freshDispatcher();
  assert.doesNotThrow(() => d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete' },
    duration: { certainty: 'estimate' },
  }));
});

test('addStep accepts zone-scoped arc-complete trigger', () => {
  const d = freshDispatcher();
  assert.doesNotThrow(() => d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete', zone: 'PoolZone' },
    duration: { certainty: 'estimate' },
  }));
});

test('addStep rejects arc-complete trigger with a non-string zone', () => {
  const d = freshDispatcher();
  assert.throws(() => d.addStep({
    id: 's1', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'arc-complete', zone: 42 },
    duration: { certainty: 'estimate' },
  }), DispatchError);
});

// ── regression: declared/fireCue firing unaffected by the extraction ──

test('regression: declared trigger via tick() still fires and still displaces (interrupt)', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'running', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'scene-start' },
    duration: { certainty: 'estimate' },
  });
  d.addStep({
    id: 'declared_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'declared', time: 5 },
    duration: { certainty: 'estimate' },
  });
  d.sceneStart();
  d.tick(5);
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'declared_line');
});

test('regression: fireCue() still fires a group of declared steps with wait policy honored', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'running', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'scene-start' },
    duration: { certainty: 'estimate' },
  });
  d.addStep({
    id: 'cue_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'declared', time: 10 }, onCollision: 'wait', cueName: 'beat1',
    duration: { certainty: 'estimate' },
  });
  d.sceneStart();
  d.fireCue('beat1');
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'running', 'wait should not preempt');
  d.arrived('running');
  assert.strictEqual(d.actors.Cindy.tracks.gesture.activeStepId, 'cue_line');
});

test('regression: declared trigger via tick() only fires once (one-shot bookkeeping intact)', () => {
  const d = freshDispatcher();
  d.addStep({
    id: 'declared_line', actorId: 'Cindy', trackId: 'gesture',
    trigger: { type: 'declared', time: 5 },
    duration: { certainty: 'estimate' },
  });
  d.tick(5);
  d.tick(6); // should not re-fire
  const started = d.eventLog.filter((e) => e.verb === 'start' && e.stepId === 'declared_line');
  assert.strictEqual(started.length, 1);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
