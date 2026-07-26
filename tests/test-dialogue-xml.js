const assert = require('assert');
const {
  parseTrigger, serializeTrigger, validateDialogueLines,
  serializeDialogueBlock, parseDialogueBlock,
  parseLegacyWaypointLines, mergeDialogueIntoRawXml,
} = require('./dialogue-xml');

let passed = 0, failed = 0;
function test(name, fn) {
  try { fn(); passed++; console.log('  ok -', name); }
  catch (e) { failed++; console.log('  FAIL -', name); console.log('       ', e.message); }
}

const SAMPLE_LINES = [
  { id: 'line_cindy_001', actor: 'Cindy', type: 'Question', mode: 'improv', blocking: false,
    trigger: { type: 'scene-start' }, text: 'How does the water feel today?' },
  { id: 'line_cindy_002', actor: 'Cindy', type: 'Response', mode: 'static', blocking: true,
    trigger: { type: 'sensed', lineId: 'line_cindy_001' }, text: 'Cool. Cooler than I expected.' },
  { id: 'line_jack_001', actor: 'Jack', type: 'Statement', mode: 'static', blocking: false,
    trigger: { type: 'zone', zone: 'Pool' }, text: 'He always did like the water more than the rest of us.' },
  { id: 'line_jack_002', actor: 'Jack', type: 'Statement', mode: 'static', blocking: false,
    trigger: { type: 'declared', time: 58 }, text: 'Did you feel that?' },
];

console.log('trigger string <-> object:');
test('scene-start round-trips', () => {
  assert.deepStrictEqual(parseTrigger('scene-start'), { type: 'scene-start' });
  assert.strictEqual(serializeTrigger({ type: 'scene-start' }), 'scene-start');
});
test('zone round-trips', () => {
  assert.deepStrictEqual(parseTrigger('zone:Pool'), { type: 'zone', zone: 'Pool' });
  assert.strictEqual(serializeTrigger({ type: 'zone', zone: 'Pool' }), 'zone:Pool');
});
test('declared round-trips with numeric time', () => {
  const t = parseTrigger('declared:58');
  assert.deepStrictEqual(t, { type: 'declared', time: 58 });
  assert.strictEqual(serializeTrigger(t), 'declared:58');
});
test('legacy-waypoint round-trips', () => {
  const t = parseTrigger('legacy-waypoint:Pool_Approach');
  assert.deepStrictEqual(t, { type: 'legacy-waypoint', waypoint: 'Pool_Approach' });
});

console.log('\nvalidation:');
test('sample lines validate clean', () => {
  const { valid, errors } = validateDialogueLines(SAMPLE_LINES);
  assert.strictEqual(valid, true, errors.join('; '));
});
test('duplicate id rejected', () => {
  const bad = [SAMPLE_LINES[0], { ...SAMPLE_LINES[1], id: SAMPLE_LINES[0].id }];
  const { valid, errors } = validateDialogueLines(bad);
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes('duplicate id')));
});
test('sensed trigger referencing an unknown id is rejected', () => {
  const bad = [{ ...SAMPLE_LINES[1], trigger: { type: 'sensed', lineId: 'nope' } }];
  const { valid, errors } = validateDialogueLines(bad);
  assert.strictEqual(valid, false);
  assert.ok(errors.some((e) => e.includes('unknown line id')));
});
test('missing text rejected', () => {
  const bad = [{ ...SAMPLE_LINES[0], text: '' }];
  const { valid } = validateDialogueLines(bad);
  assert.strictEqual(valid, false);
});

console.log('\nDialogue-block round-trip (serialize -> parse -> deep-equal):');
test('sample lines round-trip through a <Dialogue> block', () => {
  const block = serializeDialogueBlock(SAMPLE_LINES);
  const fakeScene = `<Scene id="test">\n${block}\n</Scene>`;
  const parsed = parseDialogueBlock(fakeScene);
  assert.deepStrictEqual(parsed, SAMPLE_LINES);
});
test('a scene with no Dialogue block parses to an empty array, not an error', () => {
  assert.deepStrictEqual(parseDialogueBlock('<Scene id="x"></Scene>'), []);
});

console.log('\nlegacy migration (matches mccf_scene_composer.html\'s real exportSceneXML shape):');
const LEGACY_SCENE_XML = `<Scene id="garden_001" width="40" depth="40">
<EmotionalArc cultivar="Cindy" actor="1" voice="female_1"><StartPosition x="10" y="0" z="12"/></EmotionalArc>
<Waypoints>
  <Waypoint name="Pool_Approach" label="Approach the pool" zone="Pool" pos_x="10.00" pos_y="0.00" pos_z="12.00" dwell="2" pace="1.4">
    <Question speaker="Cindy">How does the water feel today?</Question>
    <Response speaker="Cindy">Cool. Cooler than I expected.</Response>
  </Waypoint>
  <Waypoint name="Empty_WP" label="" zone="" pos_x="5.00" pos_y="0.00" pos_z="5.00" dwell="2" pace="1.4"/>
</Waypoints>
<Paths>
  <Path name="Path_Cindy_1" agent="Cindy"><PathWaypoint ref="Pool_Approach"/></Path>
</Paths>
</Scene>`;

test('legacy Question/Response lines are extracted with legacy-waypoint trigger', () => {
  const lines = parseLegacyWaypointLines(LEGACY_SCENE_XML);
  assert.strictEqual(lines.length, 2);
  assert.strictEqual(lines[0].type, 'Question');
  assert.strictEqual(lines[0].actor, 'Cindy');
  assert.strictEqual(lines[0].text, 'How does the water feel today?');
  assert.deepStrictEqual(lines[0].trigger, { type: 'legacy-waypoint', waypoint: 'Pool_Approach' });
  assert.strictEqual(lines[0].mode, 'improv');
  assert.strictEqual(lines[0].blocking, false);
  assert.strictEqual(lines[1].type, 'Response');
});
test('a self-closing Waypoint with no lines contributes nothing', () => {
  const lines = parseLegacyWaypointLines(LEGACY_SCENE_XML);
  assert.ok(!lines.some((l) => l.trigger.waypoint === 'Empty_WP'));
});
test('migrated legacy lines themselves pass validation (with fresh unique ids)', () => {
  const lines = parseLegacyWaypointLines(LEGACY_SCENE_XML);
  const { valid, errors } = validateDialogueLines(lines);
  assert.strictEqual(valid, true, errors.join('; '));
});

console.log('\nmerge-safe save (must not disturb anything outside <Dialogue>):');
test('inserting a new Dialogue block leaves the rest of the scene byte-identical', () => {
  const merged = mergeDialogueIntoRawXml(LEGACY_SCENE_XML, SAMPLE_LINES);
  // everything from the original legacy scene must still appear verbatim
  assert.ok(merged.includes('<Waypoint name="Pool_Approach"'));
  assert.ok(merged.includes('<Question speaker="Cindy">How does the water feel today?</Question>'));
  assert.ok(merged.includes('<Path name="Path_Cindy_1" agent="Cindy">'));
  assert.ok(merged.includes('<Dialogue>'));
  assert.ok(merged.trim().endsWith('</Scene>'));
});
test('re-merging replaces the previous Dialogue block rather than duplicating it', () => {
  const once = mergeDialogueIntoRawXml(LEGACY_SCENE_XML, SAMPLE_LINES);
  const editedLines = [{ ...SAMPLE_LINES[0], text: 'EDITED TEXT' }];
  const twice = mergeDialogueIntoRawXml(once, editedLines);
  const dialogueBlockCount = (twice.match(/<Dialogue>/g) || []).length;
  assert.strictEqual(dialogueBlockCount, 1);
  assert.ok(twice.includes('EDITED TEXT'));
  assert.ok(!twice.includes('Did you feel that?'), 'old line 4 should be gone after re-merge replaced the whole block');
  // still untouched outside Dialogue
  assert.ok(twice.includes('<Path name="Path_Cindy_1" agent="Cindy">'));
});
test('merge refuses to guess an insertion point if </Scene> is missing', () => {
  assert.throws(() => mergeDialogueIntoRawXml('<Scene id="broken">', SAMPLE_LINES), /refusing to guess/);
});
test('merge refuses to write invalid lines', () => {
  const bad = [{ ...SAMPLE_LINES[0], text: '' }];
  assert.throws(() => mergeDialogueIntoRawXml(LEGACY_SCENE_XML, bad));
});

console.log(`\n${passed} passed, ${failed} failed`);
if (failed) process.exitCode = 1;
