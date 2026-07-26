// Ground Tremor, T=58s — design doc §9's worked example, run end-to-end.
// This is item 3's stated "done when" criterion from the Day 72 build
// schedule: six Actors, one clock trigger, correct fan-out, each Actor's
// own onCollision policy honored.
//
// The six responses named in §9:
//   1. Avatar    — a startle gesture         (interrupt: idle track pre-empted)
//   2. SceneFog  — a flicker spike on visibility, landing on top of the
//                  continuous tension coupling (§4.2's unresolved multi-writer
//                  case — resolved here by item 4a's priority-order policy)
//   3. Door      — the temple door slamming shut (interrupt: idle prop track)
//   4. SFX Actor — a stone-groan sound effect (overlap: doesn't contend with
//                  anything else on its own track)
//   5. Movie Actor — a portal-ripple movie overlay (interrupt: idle track)
//   6. Camera    — a hard cut to a tight orbit (interrupt: Welder default,
//                  same mechanism as any other track — §7)

const assert = require('assert');
const { Dispatcher } = require('./dispatcher');

const d = new Dispatcher();

// ── Actors, minimal field maps (only what this scenario touches) ────────
d.registerActor('Avatar1', { actorType: 'Avatar', fields: [] }, { gesture: { kind: 'gesture' } });
d.registerActor('SceneFog', {
  actorType: 'SceneFog',
  fields: [{ name: 'visibility', reach: 'affect-writable', channel: 'tension', curve: 'inverse', arbitration: 'replace' }],
}, { affect: { kind: 'affect' } });
d.registerActor('TempleDoor', { actorType: 'Door', fields: [] }, { prop: { kind: 'prop' } });
d.registerActor('SFXGroan', { actorType: 'Sound', fields: [] }, { sfx: { kind: 'audio' } });
d.registerActor('PortalRipple', { actorType: 'Movie', fields: [] }, { overlay: { kind: 'movie' } });
d.registerActor('MainCamera', { actorType: 'Camera', fields: [] }, { cuts: { kind: 'camera' } });

// ── pre-existing scene state, so the collisions are real, not vacuous ───
// Avatar has an idle gesture already running.
d.addStep({ id: 'idleSway', actorId: 'Avatar1', trackId: 'gesture', trigger: { type: 'scene-start' }, duration: { certainty: 'estimate' } });
// The continuous tension→visibility coupling has already been writing all scene.
d.addStep({ id: 'tensionCoupling', actorId: 'SceneFog', trackId: 'affect', trigger: { type: 'scene-start' }, duration: { certainty: 'estimate' } });
// Door's prop track is idle (nothing running) — no collision expected there.
// SFX track is idle too.
// Movie overlay track is idle too.
// Camera has an establishing wide shot already bound.
d.addStep({ id: 'wideEstablish', actorId: 'MainCamera', trackId: 'cuts', trigger: { type: 'scene-start' }, duration: { certainty: 'estimate' } });

d.sceneStart();
// Simulate the continuous coupling's first write, same as a real tension
// channel would push each tick before the tremor happens.
d.set('SceneFog', 'visibility', 1400, { priority: 'continuous' });

assert.strictEqual(d.actors.Avatar1.tracks.gesture.activeStepId, 'idleSway');
assert.strictEqual(d.actors.SceneFog.fieldValues.visibility, 1400);
assert.strictEqual(d.actors.MainCamera.tracks.cuts.activeStepId, 'wideEstablish');

// ── the Ground Tremor cue itself, T=58s, six Actors, one clock trigger ──
const CUE = 'GroundTremor';

d.addStep({
  id: 'gt-startle', actorId: 'Avatar1', trackId: 'gesture',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed', seconds: 1.2 },
  onCollision: 'interrupt', cueName: CUE,
});
d.addStep({
  id: 'gt-fogSpike', actorId: 'SceneFog', trackId: 'affect',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed', seconds: 2.0 },
  onCollision: 'interrupt', cueName: CUE,
  fieldWrite: { field: 'visibility', value: 80, priority: 'declared' },
});
d.addStep({
  id: 'gt-doorSlam', actorId: 'TempleDoor', trackId: 'prop',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed', seconds: 0.8 },
  onCollision: 'interrupt', cueName: CUE,
});
d.addStep({
  id: 'gt-stoneGroan', actorId: 'SFXGroan', trackId: 'sfx',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed', seconds: 3.0 },
  onCollision: 'overlap', cueName: CUE,
});
d.addStep({
  id: 'gt-portalRipple', actorId: 'PortalRipple', trackId: 'overlay',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'fixed', seconds: 4.0 },
  onCollision: 'interrupt', cueName: CUE,
});
d.addStep({
  id: 'gt-tightOrbit', actorId: 'MainCamera', trackId: 'cuts',
  trigger: { type: 'declared', time: 58 }, duration: { certainty: 'estimate' },
  onCollision: 'interrupt', cueName: CUE,
});

console.log('Before T=58:');
console.log('  Avatar gesture track:', d.actors.Avatar1.tracks.gesture.activeStepId);
console.log('  Camera cuts track:   ', d.actors.MainCamera.tracks.cuts.activeStepId);
console.log('  Fog visibility:      ', d.actors.SceneFog.fieldValues.visibility);

d.tick(58); // fires the whole cue in one clock tick, via each step's own declared trigger

console.log('\nAt T=58, after the tick:');
console.log('  Avatar gesture track:', d.actors.Avatar1.tracks.gesture.activeStepId);
console.log('  Door prop track:     ', d.actors.TempleDoor.tracks.prop.activeStepId);
console.log('  SFX track:           ', d.actors.SFXGroan.tracks.sfx.activeStepId);
console.log('  Movie overlay track: ', d.actors.PortalRipple.tracks.overlay.activeStepId);
console.log('  Camera cuts track:   ', d.actors.MainCamera.tracks.cuts.activeStepId);
console.log('  Fog visibility:      ', d.actors.SceneFog.fieldValues.visibility);

// ── assertions: each Actor's own collision policy honored ───────────────
let ok = 0, bad = 0;
function check(name, actual, expected) {
  if (JSON.stringify(actual) === JSON.stringify(expected)) { ok++; console.log('  ok -', name); }
  else { bad++; console.log('  FAIL -', name, '| got', JSON.stringify(actual), 'expected', JSON.stringify(expected)); }
}

check('1. Avatar startle displaced the idle sway (interrupt)', d.actors.Avatar1.tracks.gesture.activeStepId, 'gt-startle');
check('1a. idleSway was stopped, not arrived', d.eventLog.some((e) => e.stepId === 'idleSway' && e.verb === 'stop'), true);

check('2. Fog visibility shows the tremor spike value, not the continuous coupling', d.actors.SceneFog.fieldValues.visibility, 80);
check('2a. the fog field lock is held by the declared step while it runs', d.actors.SceneFog.fieldLock.visibility && d.actors.SceneFog.fieldLock.visibility.holderStepId, 'gt-fogSpike');
check('2b. a continuous write attempted mid-tremor is refused (item 4a)', d.set('SceneFog', 'visibility', 1400, { priority: 'continuous' }), false);
check('2c. fog visibility still reads the tremor value after the refused continuous write', d.actors.SceneFog.fieldValues.visibility, 80);

check('3. Door slam started on the previously-idle prop track (interrupt, no real displacement needed)', d.actors.TempleDoor.tracks.prop.activeStepId, 'gt-doorSlam');

check('4. Stone-groan SFX started via overlap', d.eventLog.some((e) => e.stepId === 'gt-stoneGroan' && e.verb === 'start'), true);
check('4a. overlap did not claim the sfx track slot as "the" active step in a way that displaced anything (nothing was running, so it just started normally)', d.actors.SFXGroan.tracks.sfx.activeStepId, 'gt-stoneGroan');

check('5. Portal ripple movie overlay started', d.actors.PortalRipple.tracks.overlay.activeStepId, 'gt-portalRipple');

check('6. Camera cut to tight orbit displaced the wide establish (Welder, generalized)', d.actors.MainCamera.tracks.cuts.activeStepId, 'gt-tightOrbit');
check('6a. wideEstablish was stopped, not arrived — same Welder mechanism as gesture, no camera-specific code', d.eventLog.some((e) => e.stepId === 'wideEstablish' && e.verb === 'stop'), true);

// resolution: let the fixed-duration steps report arrived, confirm the fog
// lock releases and sensed-style cleanup works even inside a cue fan-out.
d.arrived('gt-fogSpike');
check('after gt-fogSpike arrives, the fog lock releases', d.actors.SceneFog.fieldLock.visibility, undefined);
check('continuous writes resume once the lock releases', d.set('SceneFog', 'visibility', 1400, { priority: 'continuous' }), true);

console.log(`\n${ok} checks passed, ${bad} failed`);
if (bad) process.exitCode = 1;
