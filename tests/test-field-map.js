const assert = require('assert');
const { validateFieldMap, serializeFieldMap, parseFieldMap } = require('./field-map');
const { AVATAR, SCENE_FOG, DOOR } = require('./worked-manifests');

let passed = 0, failed = 0;
function test(name, fn) {
  try {
    fn();
    passed++;
    console.log('  ok -', name);
  } catch (e) {
    failed++;
    console.log('  FAIL -', name);
    console.log('       ', e.message);
  }
}

console.log('validateFieldMap — worked manifests all pass:');
test('Avatar validates', () => {
  const { valid, errors } = validateFieldMap(AVATAR);
  assert.strictEqual(valid, true, errors.join('; '));
});
test('SceneFog validates', () => {
  const { valid, errors } = validateFieldMap(SCENE_FOG);
  assert.strictEqual(valid, true, errors.join('; '));
});
test('Door validates', () => {
  const { valid, errors } = validateFieldMap(DOOR);
  assert.strictEqual(valid, true, errors.join('; '));
});

console.log('\nround-trip — serialize(m) -> parse -> deep-equal m:');
[['Avatar', AVATAR], ['SceneFog', SCENE_FOG], ['Door', DOOR]].forEach(([label, manifest]) => {
  test(`${label} round-trips`, () => {
    const xml = serializeFieldMap(manifest);
    const parsed = parseFieldMap(xml);
    assert.deepStrictEqual(parsed, manifest);
  });
});

console.log('\nvalidator rules (§4.1 / format doc rules 1–6):');

test('rule 2 — an empty fields array is a LEGAL manifest (narrative-inert Actor)', () => {
  const m = { actorType: 'ShootingStar', fields: [] };
  const { valid, errors } = validateFieldMap(m);
  assert.strictEqual(valid, true, errors.join('; '));
  // and it must round-trip too — an empty fieldMap node still has to survive serialize/parse
  const parsed = parseFieldMap(serializeFieldMap(m));
  assert.deepStrictEqual(parsed, m);
});

test('rule 1 — a totally missing fieldMap node fails to parse (not legal to export)', () => {
  assert.throws(() => parseFieldMap('<Group/>'), /no fieldMap MetadataSet found/);
});

test('rule 4 — affect-writable field missing channel/curve/arbitration is rejected', () => {
  const m = { actorType: 'X', fields: [{ name: 'f', reach: 'affect-writable' }] };
  const { valid, errors } = validateFieldMap(m);
  assert.strictEqual(valid, false);
  assert.ok(errors.some(e => e.includes('channel')));
  assert.ok(errors.some(e => e.includes('curve')));
  assert.ok(errors.some(e => e.includes('arbitration')));
});

test('rule 4 — track-only field carrying channel/curve/arbitration is rejected', () => {
  const m = { actorType: 'X', fields: [{ name: 'f', reach: 'track-only', channel: 'tension' }] };
  const { valid, errors } = validateFieldMap(m);
  assert.strictEqual(valid, false);
  assert.ok(errors.some(e => e.includes('channel') && e.includes('only legal when')));
});

test('rule 6 — duplicate field names within one Actor type are rejected', () => {
  const m = {
    actorType: 'X',
    fields: [
      { name: 'dup', reach: 'telemetry' },
      { name: 'dup', reach: 'track-only' },
    ],
  };
  const { valid, errors } = validateFieldMap(m);
  assert.strictEqual(valid, false);
  assert.ok(errors.some(e => e.includes('duplicate field name')));
});

test('bad reach value is rejected', () => {
  const m = { actorType: 'X', fields: [{ name: 'f', reach: 'sometimes' }] };
  const { valid } = validateFieldMap(m);
  assert.strictEqual(valid, false);
});

test('serializeFieldMap refuses to serialize an invalid manifest', () => {
  const m = { actorType: 'X', fields: [{ name: 'f', reach: 'nonsense' }] };
  assert.throws(() => serializeFieldMap(m), /refusing to serialize/);
});

test('range is optional and its absence is not an error', () => {
  const m = { actorType: 'X', fields: [{ name: 'f', reach: 'track-only' }] };
  const { valid, errors } = validateFieldMap(m);
  assert.strictEqual(valid, true, errors.join('; '));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed ? 1 : 0);
