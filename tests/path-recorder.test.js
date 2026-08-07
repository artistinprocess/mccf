const { rdpIndices, buildRecordedPath, validateRecordedPath, serializeRecordedPath, parseRecordedPath } = require('./path-recorder.js');
const assert = require('assert');

// 1. RDP on a straight line should collapse to just the two endpoints
const straight = [[0,0,0],[1,0,0],[2,0,0],[3,0,0],[4,0,0],[5,0,0]];
assert.deepStrictEqual(rdpIndices(straight, 0.01), [0,5], 'straight line should decimate to endpoints only');
console.log('Test 1 (straight line decimates to 2 points) passed.');

// 2. RDP on an L-shaped path should keep the corner
const corner = [[0,0,0],[1,0,0],[2,0,0],[2,1,0],[2,2,0],[2,3,0]];
const idx = rdpIndices(corner, 0.05);
assert.ok(idx.includes(2), 'corner point (index 2) must survive decimation: got ' + JSON.stringify(idx));
assert.strictEqual(idx[0], 0); assert.strictEqual(idx[idx.length-1], 5);
console.log('Test 2 (corner survives) passed.');

// 3. High tolerance collapses even a curve to endpoints
const curve = [[0,0,0],[1,0.5,0],[2,0.8,0],[3,0.5,0],[4,0,0]];
assert.deepStrictEqual(rdpIndices(curve, 100), [0,4], 'huge tolerance should collapse everything');
console.log('Test 3 (huge tolerance collapses to endpoints) passed.');

// 4. buildRecordedPath end to end, with orientation carried (not decimated independently)
const raw = [];
for (let i = 0; i <= 20; i++) {
  raw.push({ t: i * 0.1, position: [i * 0.5, 0, 0], orientation: [0, 1, 0, i * 0.05] });
}
// bend it partway through
for (let i = 21; i <= 40; i++) {
  raw.push({ t: i * 0.1, position: [10, 0, (i - 20) * 0.5], orientation: [0, 1, 0, i * 0.05] });
}
const built = buildRecordedPath(raw, { id: 'flight_1', tolerance: 0.05 });
assert.ok(built.stats.decimatedKeyCount < built.stats.rawSampleCount, 'decimation must actually reduce sample count');
assert.ok(built.stats.decimatedKeyCount >= 3, 'the bend must survive as its own key');
assert.strictEqual(built.keys[0].orientation.length, 4);
console.log('Test 4 (buildRecordedPath end to end) passed:', built.stats);

// 5. Validation catches non-monotonic t
const bad = { id: 'x', keys: [{t:1,position:[0,0,0],orientation:[0,1,0,0]},{t:0.5,position:[1,0,0],orientation:[0,1,0,0]}] };
const v = validateRecordedPath(bad);
assert.strictEqual(v.valid, false);
assert.ok(v.errors.some(e => e.includes('strictly greater')));
console.log('Test 5 (non-monotonic t rejected) passed.');

// 6. Round-trip through XML
built.id = 'flight_1';
const xml = serializeRecordedPath(built);
const parsed = parseRecordedPath(xml);
assert.strictEqual(parsed.id, 'flight_1');
assert.strictEqual(parsed.keys.length, built.keys.length);
assert.ok(Math.abs(parsed.keys[1].position[0] - built.keys[1].position[0]) < 1e-3);
console.log('Test 6 (XML round-trip) passed.');

console.log('ALL TESTS PASSED');
