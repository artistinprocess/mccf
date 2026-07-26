// Day 73 — tests for exportForKate/importFromKate (priority queue item 5).
// Same house style: hand-rolled assertions, zero deps, run with plain `node`.

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
    console.log(`       ${e.stack || e.message}`);
  }
}

function line(overrides) {
  return Object.assign({
    id: 'line_001',
    actor: 'Cindy',
    type: 'Statement',
    mode: 'static',
    blocking: false,
    trigger: { type: 'scene-start' },
    text: 'Hello there.',
  }, overrides);
}

// ── exportForKate ────────────────────────────────────────────────────

test('exportForKate produces the same XML as serializeDialogueBlock', () => {
  const lines = [line(), line({ id: 'line_002', text: 'Second line.' })];
  assert.strictEqual(D.exportForKate(lines), D.serializeDialogueBlock(lines));
});

test('exportForKate output round-trips through parseDialogueBlock', () => {
  const lines = [line()];
  const xml = D.exportForKate(lines);
  const parsed = D.parseDialogueBlock(xml);
  assert.strictEqual(parsed.length, 1);
  assert.strictEqual(parsed[0].id, 'line_001');
});

// ── importFromKate: strict id match ────────────────────────────────────

test('importFromKate: returned line with matching id is treated as an edit', () => {
  const original = [line({ id: 'line_001', text: 'Original text.' })];
  const kateXml = D.exportForKate([line({ id: 'line_001', text: 'Kate edited this.' })]);
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.lines.length, 1);
  assert.strictEqual(result.lines[0].text, 'Kate edited this.');
  assert.deepStrictEqual(result.updatedIds, ['line_001']);
  assert.deepStrictEqual(result.addedIds, []);
});

// ── importFromKate: fallback to exact-text match ───────────────────────

test('importFromKate: id mismatch but exact text match keeps ORIGINAL id', () => {
  const original = [line({ id: 'line_001', text: 'Unchanged text here.' })];
  // Kate returns a different (mangled/regenerated) id but identical text —
  // e.g. she was only asked to add a tag, not edit text. Built as a raw
  // XML string (not via exportForKate) since a bare ttsText-with-no-
  // tagSource-yet is exactly what an LLM reply looks like before our
  // import logic stamps the provenance — exportForKate would (correctly)
  // reject constructing that as an *export*.
  const kateXml = '<Dialogue>\n  <Line id="kate_regenerated_id" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start" ttsText="[thoughtful] Unchanged text here.">Unchanged text here.</Line>\n</Dialogue>';
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.lines.length, 1);
  assert.strictEqual(result.lines[0].id, 'line_001', 'original id must be kept, not the returned one');
  assert.strictEqual(result.lines[0].ttsText, '[thoughtful] Unchanged text here.');
  assert.deepStrictEqual(result.updatedIds, ['line_001']);
  assert.deepStrictEqual(result.addedIds, []);
});

// ── importFromKate: genuinely new lines ────────────────────────────────

test('importFromKate: no id or text match is treated as a new line', () => {
  const original = [line({ id: 'line_001', text: 'Existing line.' })];
  const kateXml = D.exportForKate([
    line({ id: 'line_001', text: 'Existing line.' }), // unchanged, passthrough
    line({ id: 'line_999', text: 'A brand new line Kate wrote.', actor: 'Jack' }),
  ]);
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.lines.length, 2);
  assert.deepStrictEqual(result.updatedIds, ['line_001']);
  assert.deepStrictEqual(result.addedIds, ['line_999']);
  const added = result.lines.find((l) => l.id === 'line_999');
  assert.strictEqual(added.actor, 'Jack');
});

test('importFromKate: id match is authoritative — treated as an edit even if the text is completely different', () => {
  const original = [line({ id: 'line_001', text: 'Existing line.' })];
  // Strict id-first means an id match always wins as an edit, regardless
  // of how different the text is — this is the common case (Kate edits a
  // line's text but keeps sending its original id back).
  const kateXml = '<Dialogue>\n  <Line id="line_001" actor="Jack" type="Statement" mode="static" blocking="false" trigger="scene-start">A totally different edited line.</Line>\n</Dialogue>';
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.lines.length, 1, 'id match means this is an edit, not an addition');
  assert.strictEqual(result.lines[0].id, 'line_001');
  assert.strictEqual(result.lines[0].text, 'A totally different edited line.');
  assert.strictEqual(result.lines[0].actor, 'Jack');
  assert.deepStrictEqual(result.updatedIds, ['line_001']);
  assert.deepStrictEqual(result.addedIds, []);
});

test('importFromKate: multiple new lines get distinct synthesized ids', () => {
  const original = [];
  const kateXml = '<Dialogue>\n' +
    '  <Line id="x" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start">First new line.</Line>\n' +
    '  <Line id="x" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start">Second new line.</Line>\n' +
    '</Dialogue>';
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.addedIds.length, 2);
  assert.notStrictEqual(result.addedIds[0], result.addedIds[1]);
});

// ── tagSource auto-stamping ─────────────────────────────────────────────

test('importFromKate: ttsText with no tagSource gets auto-stamped llm-interpreted:Kate (default name)', () => {
  const original = [line({ id: 'line_001', text: 'Text.' })];
  const kateXml = '<Dialogue>\n  <Line id="line_001" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start" ttsText="[sad] Text.">Text.</Line>\n</Dialogue>';
  const result = D.importFromKate(kateXml, original);
  assert.deepStrictEqual(result.lines[0].tagSource, { type: 'llm-interpreted', name: 'Kate' });
});

test('importFromKate: custom collaboratorName is used in the auto-stamped tagSource', () => {
  const original = [line({ id: 'line_001', text: 'Text.' })];
  const kateXml = '<Dialogue>\n  <Line id="line_001" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start" ttsText="[sad] Text.">Text.</Line>\n</Dialogue>';
  const result = D.importFromKate(kateXml, original, 'Editor-Bot');
  assert.deepStrictEqual(result.lines[0].tagSource, { type: 'llm-interpreted', name: 'Editor-Bot' });
});

test('importFromKate: an explicit tagSource already on the returned line is NOT overwritten', () => {
  const original = [line({ id: 'line_001', text: 'Text.' })];
  const kateXml = D.exportForKate([line({
    id: 'line_001', text: 'Text.', ttsText: '[sad] Text.',
    tagSource: { type: 'authored' },
  })]);
  const result = D.importFromKate(kateXml, original);
  assert.deepStrictEqual(result.lines[0].tagSource, { type: 'authored' });
});

test('importFromKate: a line with no ttsText at all gets no tagSource stamped', () => {
  const original = [line({ id: 'line_001', text: 'Text.' })];
  const kateXml = D.exportForKate([line({ id: 'line_001', text: 'Edited but no tag.' })]);
  const result = D.importFromKate(kateXml, original);
  assert.strictEqual(result.lines[0].ttsText, undefined);
  assert.strictEqual(result.lines[0].tagSource, undefined);
});

// ── bare-fragment tolerance ──────────────────────────────────────────────

test('importFromKate: tolerates a bare <Line> fragment with no <Dialogue> wrapper', () => {
  const original = [line({ id: 'line_001', text: 'Original.' })];
  const bareFragment = '  <Line id="line_001" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start">Edited via bare fragment.</Line>';
  const result = D.importFromKate(bareFragment, original);
  assert.strictEqual(result.valid, true, result.errors.join('; '));
  assert.strictEqual(result.lines[0].text, 'Edited via bare fragment.');
});

// ── validation surfacing ────────────────────────────────────────────────

test('importFromKate: surfaces validation errors instead of throwing on a malformed reply', () => {
  const original = [line({ id: 'line_001', text: 'Original.' })];
  // Kate's reply has a sensed trigger pointing at a line id that doesn't exist
  const badXml = '<Dialogue>\n  <Line id="line_002" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="sensed:nonexistent_id">New text.</Line>\n</Dialogue>';
  const result = D.importFromKate(badXml, original);
  assert.strictEqual(result.valid, false);
  assert.ok(result.errors.some((e) => e.includes('sensed trigger references unknown line id')));
});

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
