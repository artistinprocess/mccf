const assert = require('assert');
const { Dispatcher, DispatchError } = require('./dispatcher');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log('  ok -', name); }
  catch (e) { failed++; console.log('  FAIL -', name); console.log('       ', e.message); }
}

const emptyFieldMap = { actorType: 'Test', fields: [] };

console.log('identity discipline (same rule as build-item 1, applied to Actors/steps):');
test('duplicate actor id is rejected', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, {});
  assert.throws(() => d.registerActor('A', emptyFieldMap, {}), DispatchError);
});
test('duplicate step id is rejected (step ids are scene-wide unique)', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { t: { kind: 'gesture' } });
  d.addStep({ id: 's1', actorId: 'A', trackId: 't', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
  assert.throws(() => d.addStep({ id: 's1', actorId: 'A', trackId: 't', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } }), DispatchError);
});
test('addStep rejects unknown actor', () => {
  const d = new Dispatcher();
  assert.throws(() => d.addStep({ id: 's1', actorId: 'nope', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } }), DispatchError);
});

console.log('\nscene-start:');
test('scene-start steps fire on sceneStart()', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { walk: { kind: 'path' } });
  d.addStep({ id: 'seg1', actorId: 'A', trackId: 'walk', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
  d.sceneStart();
  assert.strictEqual(d.actors.A.tracks.walk.activeStepId, 'seg1');
});

console.log('\nsensed chaining (§5.3 — push, not pull):');
test('arrived on step1 starts a sensed step chained off it', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { walk: { kind: 'path' } });
  d.addStep({ id: 'seg1', actorId: 'A', trackId: 'walk', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
  d.addStep({ id: 'seg2', actorId: 'A', trackId: 'walk', trigger: { type: 'sensed', stepId: 'seg1' }, duration: { certainty: 'fixed' } });
  d.sceneStart();
  assert.strictEqual(d.actors.A.tracks.walk.activeStepId, 'seg1');
  d.arrived('seg1');
  assert.strictEqual(d.actors.A.tracks.walk.activeStepId, 'seg2');
});

console.log('\nWelder displacement (§5.1, generalizes to any track kind incl. camera §7):');
test('starting a new step on an active track displaces (stops) the old one, not arrives it', () => {
  const d = new Dispatcher();
  d.registerActor('Cam', emptyFieldMap, { cuts: { kind: 'camera' } });
  d.addStep({ id: 'cut1', actorId: 'Cam', trackId: 'cuts', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
  d.addStep({ id: 'cut2', actorId: 'Cam', trackId: 'cuts', trigger: { type: 'zone', zone: 'Z1' }, duration: { certainty: 'fixed' } });
  d.sceneStart();
  d.fireZone('Cam', 'Z1');
  assert.strictEqual(d.actors.Cam.tracks.cuts.activeStepId, 'cut2');
  const cut1Events = d.eventLog.filter((e) => e.stepId === 'cut1');
  assert.ok(cut1Events.some((e) => e.verb === 'stop'), 'cut1 should have been stop()ped, not arrived()');
  assert.ok(!cut1Events.some((e) => e.verb === 'arrived'), 'displaced step must not report arrived — it did not finish on its own');
});

console.log('\ndeclared triggers and the master clock (§3.1, §5.3):');
test('declared step fires once clock reaches its time, not before', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { g: { kind: 'gesture' } });
  d.addStep({ id: 'startle', actorId: 'A', trackId: 'g', trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed' } });
  d.tick(10);
  assert.strictEqual(d.actors.A.tracks.g.activeStepId, null);
  d.tick(58);
  assert.strictEqual(d.actors.A.tracks.g.activeStepId, 'startle');
});
test('declared step does not re-fire on a later tick', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { g: { kind: 'gesture' } });
  d.addStep({ id: 'startle', actorId: 'A', trackId: 'g', trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed' } });
  d.tick(58);
  d.arrived('startle');
  d.tick(60);
  assert.strictEqual(d.actors.A.tracks.g.activeStepId, null, 'must not restart on the next tick');
});

console.log('\ndeclared-vs-running collision policies (§5.4):');
test('interrupt: declared step cuts off a running one immediately', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { d1: { kind: 'dialogue' } });
  d.addStep({ id: 'line1', actorId: 'A', trackId: 'd1', trigger: { type: 'scene-start' }, duration: { certainty: 'estimate' } });
  d.addStep({ id: 'explosion', actorId: 'A', trackId: 'd1', trigger: { type: 'declared', time: 5 }, duration: { certainty: 'fixed' }, onCollision: 'interrupt' });
  d.sceneStart();
  d.tick(5);
  assert.strictEqual(d.actors.A.tracks.d1.activeStepId, 'explosion');
});
test('wait: declared step holds until the running one arrives, then fires', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { music: { kind: 'audio' } });
  d.addStep({ id: 'dialogue1', actorId: 'A', trackId: 'music', trigger: { type: 'scene-start' }, duration: { certainty: 'estimate' } });
  d.addStep({ id: 'scoredCue', actorId: 'A', trackId: 'music', trigger: { type: 'declared', time: 5 }, duration: { certainty: 'fixed' }, onCollision: 'wait' });
  d.sceneStart();
  d.tick(5);
  assert.strictEqual(d.actors.A.tracks.music.activeStepId, 'dialogue1', 'must not preempt while waiting');
  d.arrived('dialogue1');
  assert.strictEqual(d.actors.A.tracks.music.activeStepId, 'scoredCue', 'should fire once the wait releases');
});
test('overlap: declared step runs alongside without displacing the track', () => {
  const d = new Dispatcher();
  d.registerActor('A', emptyFieldMap, { bed: { kind: 'audio' } });
  d.addStep({ id: 'ambientBed', actorId: 'A', trackId: 'bed', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
  d.addStep({ id: 'sfx', actorId: 'A', trackId: 'bed', trigger: { type: 'declared', time: 5 }, duration: { certainty: 'fixed' }, onCollision: 'overlap' });
  d.sceneStart();
  d.tick(5);
  assert.strictEqual(d.actors.A.tracks.bed.activeStepId, 'ambientBed', 'overlap must not steal the track slot');
  const sfxEvents = d.eventLog.filter((e) => e.stepId === 'sfx');
  assert.ok(sfxEvents.some((e) => e.verb === 'start'), 'sfx should still have started, just without displacement');
});

console.log('\nfield arbitration (§5.2):');
const avatarFieldMap = {
  actorType: 'Avatar',
  fields: [
    { name: 'idleGestureBias', reach: 'affect-writable', channel: 'arousal', curve: 'direct', arbitration: 'track-wins' },
    { name: 'walkPace', reach: 'affect-writable', channel: 'arousal', curve: 'direct', arbitration: 'blend' },
    { name: 'poemLine', reach: 'track-only' },
  ],
};
test('track-only field refuses set() outright', () => {
  const d = new Dispatcher();
  d.registerActor('A', avatarFieldMap, {});
  assert.strictEqual(d.set('A', 'poemLine', 'hi'), false);
});
test('unknown field refuses set()', () => {
  const d = new Dispatcher();
  d.registerActor('A', avatarFieldMap, {});
  assert.strictEqual(d.set('A', 'nope', 1), false);
});
test('track-wins: affect set() is refused while the track is active', () => {
  const d = new Dispatcher();
  d.registerActor('A', avatarFieldMap, {});
  assert.strictEqual(d.set('A', 'idleGestureBias', 0.8, { trackActive: true }), false);
  assert.strictEqual(d.set('A', 'idleGestureBias', 0.8, { trackActive: false }), true);
});
test('blend: walkPace applies the named multiplier blend function (item 4b)', () => {
  const d = new Dispatcher();
  d.registerActor('A', avatarFieldMap, {});
  d.set('A', 'walkPace', 1.2, { recordedValue: 1.4 }); // 1.4 recorded × 1.2 arousal multiplier
  assert.strictEqual(d.actors.A.fieldValues.walkPace, 1.4 * 1.2);
});

console.log('\naffect-vs-affect priority order (item 4a decision):');
const fogFieldMap = { actorType: 'SceneFog', fields: [{ name: 'visibility', reach: 'affect-writable', channel: 'tension', curve: 'inverse', arbitration: 'replace' }] };
test('a continuous write applies normally with no declared lock held', () => {
  const d = new Dispatcher();
  d.registerActor('Fog', fogFieldMap, {});
  assert.strictEqual(d.set('Fog', 'visibility', 500, { priority: 'continuous' }), true);
  assert.strictEqual(d.actors.Fog.fieldValues.visibility, 500);
});
test('a declared write locks the field; a subsequent continuous write is refused', () => {
  const d = new Dispatcher();
  d.registerActor('Fog', fogFieldMap, {});
  d.set('Fog', 'visibility', 500, { priority: 'continuous' });
  d.set('Fog', 'visibility', 80, { priority: 'declared', holderStepId: 'tremorSpike' });
  assert.strictEqual(d.actors.Fog.fieldValues.visibility, 80);
  const refused = d.set('Fog', 'visibility', 600, { priority: 'continuous' });
  assert.strictEqual(refused, false);
  assert.strictEqual(d.actors.Fog.fieldValues.visibility, 80, 'declared value must survive the refused continuous write');
});
test('releasing the declared step (via arrived) lets continuous writes through again', () => {
  const d = new Dispatcher();
  d.registerActor('Fog', fogFieldMap, { affect: { kind: 'affect' } });
  d.addStep({ id: 'tremorSpike', actorId: 'Fog', trackId: 'affect', trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed' } });
  d.set('Fog', 'visibility', 500, { priority: 'continuous' });
  d.set('Fog', 'visibility', 80, { priority: 'declared', holderStepId: 'tremorSpike' });
  d.arrived('tremorSpike');
  const allowed = d.set('Fog', 'visibility', 600, { priority: 'continuous' });
  assert.strictEqual(allowed, true);
  assert.strictEqual(d.actors.Fog.fieldValues.visibility, 600);
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exitCode = 1;
