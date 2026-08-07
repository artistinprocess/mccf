const { buildActorRegistry, registerWithDispatcher } = require('./actor-adapter.js');
const { Dispatcher } = require('./dispatcher.js');
const assert = require('assert');

// 1. Basic clean reconciliation
const state1 = {
  placedAgents: { Alice: { position: [1,0,2], color: '#fff', weights:{E:.25,B:.25,P:.25,S:.25}, regulation:0.7, disposition:'', voice:'', hanim_src:'avatars/alice.x3d', hanim_loa:4 } },
  placedCameras: { OverviewCam: { position: [0,1.7,10], hAngle: 0, vAngle: 0, roll: 0 } },
  zones: { garden: { id:'garden', name:'Garden', zone_type:'garden', location:[0,0,0], radius:5 } },
};
const reg1 = buildActorRegistry(state1);
assert.strictEqual(reg1.errors.length, 0, 'expected no errors');
assert.ok(reg1.actors.Alice, 'Alice actor present');
assert.strictEqual(reg1.actors.Alice.actorType, 'Avatar');
assert.deepStrictEqual(Object.keys(reg1.actors.Alice.trackDefs), ['path']);
assert.ok(reg1.actors.OverviewCam, 'OverviewCam actor present');
assert.strictEqual(reg1.actors.OverviewCam.actorType, 'Camera');
assert.deepStrictEqual(Object.keys(reg1.actors.OverviewCam.trackDefs), ['cuts']);
assert.ok(reg1.zones.garden, 'zones passed through, not converted to Actors');
assert.strictEqual(Object.keys(reg1.actors).length, 2, 'zones must not appear in actors');
console.log('Test 1 (clean reconciliation) passed.');

// 2. Cross-namespace collision detection (Avatar and Camera sharing a name)
const state2 = {
  placedAgents: { Alice: state1.placedAgents.Alice },
  placedCameras: { Alice: { position: [0,1.7,0], hAngle:0, vAngle:0, roll:0 } },
  zones: {},
};
const reg2 = buildActorRegistry(state2);
assert.strictEqual(Object.keys(reg2.actors).length, 0, 'must refuse to build actors on collision');
assert.ok(reg2.errors.length === 1 && reg2.errors[0].includes('Alice'), 'must report the collision by name');
console.log('Test 2 (cross-namespace collision) passed.');

// 3. Zone/Actor name collision also caught
const state3 = {
  placedAgents: { Alice: state1.placedAgents.Alice },
  placedCameras: {},
  zones: { Alice: { id:'Alice' } },
};
const reg3 = buildActorRegistry(state3);
assert.strictEqual(reg3.errors.length, 1);
console.log('Test 3 (zone/actor collision) passed.');

// 4. registerWithDispatcher actually wires into a live Dispatcher and steps work
const d = new Dispatcher();
registerWithDispatcher(d, reg1);
assert.ok(d.actors.Alice, 'dispatcher has Alice');
assert.ok(d.actors.OverviewCam, 'dispatcher has OverviewCam');
d.addStep({ id: 'cut1', actorId: 'OverviewCam', trackId: 'cuts', trigger: { type: 'scene-start' }, duration: { certainty: 'fixed' } });
d.sceneStart();
assert.strictEqual(d.actors.OverviewCam.tracks.cuts.activeStepId, 'cut1');
console.log('Test 4 (dispatcher wiring) passed.');

// 5. registerWithDispatcher refuses a registry with errors
let threw = false;
try { registerWithDispatcher(new Dispatcher(), reg2); } catch (e) { threw = true; }
assert.ok(threw, 'registerWithDispatcher must refuse an errored registry');
console.log('Test 5 (refuses errored registry) passed.');

console.log('ALL TESTS PASSED');
