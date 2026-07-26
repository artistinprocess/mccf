// Day 73 — tests for the ttsText/tagSource/audioFile/audioSource schema
// additions (priority queue item 2). Same house style as the rest of the
// test suite: hand-rolled assertions, zero deps, run with plain `node`.

const assert = require('assert');
const D = require('../static_dialogue-xml.js');

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
    console.log(`       ${e.message}`);
  }
}

// ── tagSource parse/serialize ──────────────────────────────────────────

test('parseTagSource: algorithmic', () => {
  assert.deepStrictEqual(D.parseTagSource('algorithmic'), { type: 'algorithmic' });
});

test('parseTagSource: authored', () => {
  assert.deepStrictEqual(D.parseTagSource('authored'), { type: 'authored' });
});

test('parseTagSource: llm-interpreted:Kate', () => {
  assert.deepStrictEqual(D.parseTagSource('llm-interpreted:Kate'), { type: 'llm-interpreted', name: 'Kate' });
});

test('parseTagSource: invalid string flagged, not thrown', () => {
  const r = D.parseTagSource('bogus');
  assert.strictEqual(r.type, '__invalid__');
});

test('serializeTagSource round-trips all three forms', () => {
  const forms = ['algorithmic', 'authored', 'llm-interpreted:Kate'];
  for (const f of forms) {
    assert.strictEqual(D.serializeTagSource(D.parseTagSource(f)), f);
  }
});

test('serializeTagSource throws on unknown type', () => {
  assert.throws(() => D.serializeTagSource({ type: 'nonsense' }));
});

// ── audioSource parse/serialize ────────────────────────────────────────

test('parseAudioSource: elevenlabs', () => {
  assert.deepStrictEqual(D.parseAudioSource('elevenlabs'), { type: 'elevenlabs' });
});

test('parseAudioSource: recorded', () => {
  assert.deepStrictEqual(D.parseAudioSource('recorded'), { type: 'recorded' });
});

test('parseAudioSource: other-engine:Azure', () => {
  assert.deepStrictEqual(D.parseAudioSource('other-engine:Azure'), { type: 'other-engine', name: 'Azure' });
});

test('serializeAudioSource round-trips all three forms', () => {
  const forms = ['elevenlabs', 'recorded', 'other-engine:Azure'];
  for (const f of forms) {
    assert.strictEqual(D.serializeAudioSource(D.parseAudioSource(f)), f);
  }
});

// ── validation: co-requirement rules ───────────────────────────────────

function baseLine(overrides) {
  return Object.assign({
    id: 'line_001',
    actor: 'Cindy',
    type: 'Statement',
    mode: 'static',
    blocking: false,
    trigger: { type: 'scene-start' },
    text: 'Hello.',
  }, overrides);
}

test('validate: line with no ttsText/audioFile at all is valid (backward compat)', () => {
  const r = D.validateDialogueLines([baseLine()]);
  assert.strictEqual(r.valid, true, r.errors.join('; '));
});

test('validate: ttsText present without tagSource is invalid', () => {
  const r = D.validateDialogueLines([baseLine({ ttsText: '[happy] Hello.' })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('tagSource missing')));
});

test('validate: tagSource present without ttsText is invalid', () => {
  const r = D.validateDialogueLines([baseLine({ tagSource: { type: 'authored' } })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('ttsText missing')));
});

test('validate: ttsText + tagSource together is valid', () => {
  const r = D.validateDialogueLines([baseLine({
    ttsText: '[happy] Hello.',
    tagSource: { type: 'authored' },
  })]);
  assert.strictEqual(r.valid, true, r.errors.join('; '));
});

test('validate: ttsText + invalid tagSource.type is invalid', () => {
  const r = D.validateDialogueLines([baseLine({
    ttsText: '[happy] Hello.',
    tagSource: { type: 'nonsense' },
  })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('tagSource must be one of')));
});

test('validate: audioFile present without audioSource is invalid', () => {
  const r = D.validateDialogueLines([baseLine({ audioFile: 'audio/x.mp3' })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('audioSource missing')));
});

test('validate: audioSource present without audioFile is invalid', () => {
  const r = D.validateDialogueLines([baseLine({ audioSource: { type: 'recorded' } })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('audioFile missing')));
});

test('validate: audioFile + audioSource together is valid', () => {
  const r = D.validateDialogueLines([baseLine({
    audioFile: 'audio/x.mp3',
    audioSource: { type: 'recorded' },
  })]);
  assert.strictEqual(r.valid, true, r.errors.join('; '));
});

test('validate: all four fields together, independent of each other, is valid', () => {
  const r = D.validateDialogueLines([baseLine({
    ttsText: '[sad] Hello.',
    tagSource: { type: 'llm-interpreted', name: 'Kate' },
    audioFile: 'audio/x.mp3',
    audioSource: { type: 'elevenlabs' },
  })]);
  assert.strictEqual(r.valid, true, r.errors.join('; '));
});

test('validate: ttsText present but not a string is invalid', () => {
  const r = D.validateDialogueLines([baseLine({
    ttsText: 12345,
    tagSource: { type: 'authored' },
  })]);
  assert.strictEqual(r.valid, false);
  assert.ok(r.errors.some((e) => e.includes('ttsText must be a string')));
});

// ── serialize / parse round-trip through full <Dialogue> block ────────

test('round-trip: line with no new fields unaffected (byte-shape check)', () => {
  const lines = [baseLine()];
  const xml = D.serializeDialogueBlock(lines);
  assert.ok(!xml.includes('ttsText'), 'ttsText attribute should not appear when unset');
  assert.ok(!xml.includes('audioFile'), 'audioFile attribute should not appear when unset');
  const full = `<Scene>${xml}</Scene>`;
  const parsed = D.parseDialogueBlock(full);
  assert.strictEqual(parsed.length, 1);
  assert.strictEqual(parsed[0].ttsText, undefined);
  assert.strictEqual(parsed[0].tagSource, undefined);
  assert.strictEqual(parsed[0].audioFile, undefined);
  assert.strictEqual(parsed[0].audioSource, undefined);
});

test('round-trip: line with ttsText/tagSource survives serialize->parse', () => {
  const lines = [baseLine({
    id: 'line_002',
    ttsText: '[whisper] Careful now.',
    tagSource: { type: 'algorithmic' },
  })];
  const xml = D.serializeDialogueBlock(lines);
  const full = `<Scene>${xml}</Scene>`;
  const parsed = D.parseDialogueBlock(full);
  assert.strictEqual(parsed[0].ttsText, '[whisper] Careful now.');
  assert.deepStrictEqual(parsed[0].tagSource, { type: 'algorithmic' });
});

test('round-trip: line with audioFile/audioSource survives serialize->parse', () => {
  const lines = [baseLine({
    id: 'line_003',
    audioFile: 'audio/jack_pool_001.mp3',
    audioSource: { type: 'recorded' },
  })];
  const xml = D.serializeDialogueBlock(lines);
  const full = `<Scene>${xml}</Scene>`;
  const parsed = D.parseDialogueBlock(full);
  assert.strictEqual(parsed[0].audioFile, 'audio/jack_pool_001.mp3');
  assert.deepStrictEqual(parsed[0].audioSource, { type: 'recorded' });
});

test('round-trip: all four fields together survive serialize->parse', () => {
  const lines = [baseLine({
    id: 'line_004',
    ttsText: '[sad] He always did like the water more than the rest of us.',
    tagSource: { type: 'authored' },
    audioFile: 'audio/jack_pool_001.mp3',
    audioSource: { type: 'other-engine', name: 'Azure' },
  })];
  const xml = D.serializeDialogueBlock(lines);
  const full = `<Scene>${xml}</Scene>`;
  const parsed = D.parseDialogueBlock(full);
  assert.strictEqual(parsed[0].ttsText, '[sad] He always did like the water more than the rest of us.');
  assert.deepStrictEqual(parsed[0].tagSource, { type: 'authored' });
  assert.strictEqual(parsed[0].audioFile, 'audio/jack_pool_001.mp3');
  assert.deepStrictEqual(parsed[0].audioSource, { type: 'other-engine', name: 'Azure' });
});

test('round-trip: ttsText with special characters escapes/unescapes correctly', () => {
  const lines = [baseLine({
    id: 'line_005',
    ttsText: '[happy] "Well," she said, "that\'s that & done."',
    tagSource: { type: 'authored' },
  })];
  const xml = D.serializeDialogueBlock(lines);
  const full = `<Scene>${xml}</Scene>`;
  const parsed = D.parseDialogueBlock(full);
  assert.strictEqual(parsed[0].ttsText, '[happy] "Well," she said, "that\'s that & done."');
});

// ── legacy migration: new fields never appear on synthesized lines ────

test('legacy migration: synthesized lines have no ttsText/audioFile fields', () => {
  const sceneXml = `
    <Scene>
      <Waypoints>
        <Waypoint name="wp1">
          <Question speaker="Cindy">How does the water feel?</Question>
        </Waypoint>
      </Waypoints>
    </Scene>
  `;
  const lines = D.parseLegacyWaypointLines(sceneXml);
  assert.strictEqual(lines.length, 1);
  assert.strictEqual(lines[0].ttsText, undefined);
  assert.strictEqual(lines[0].tagSource, undefined);
  assert.strictEqual(lines[0].audioFile, undefined);
  assert.strictEqual(lines[0].audioSource, undefined);
  // and legacy lines still validate fine as-is (no co-requirement triggered)
  const r = D.validateDialogueLines(lines);
  assert.strictEqual(r.valid, true, r.errors.join('; '));
});

// ── existing behavior (Day 72) untouched — quick spot-checks ──────────

test('regression: mergeDialogueIntoRawXml still works with mixed old/new lines', () => {
  const sceneXml = '<Scene><Waypoints></Waypoints></Scene>';
  const lines = [
    baseLine({ id: 'a' }),
    baseLine({
      id: 'b',
      ttsText: '[thoughtful] hm.',
      tagSource: { type: 'algorithmic' },
    }),
  ];
  const merged = D.mergeDialogueIntoRawXml(sceneXml, lines);
  assert.ok(merged.includes('<Dialogue>'));
  assert.ok(merged.includes('id="a"'));
  assert.ok(merged.includes('ttsText="[thoughtful] hm."'));
  const reparsed = D.parseDialogueBlock(merged);
  assert.strictEqual(reparsed.length, 2);
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
