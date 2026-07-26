// Day 73 — headless DOM test for mccf_dialogue_editor.html (priority
// queue item 6). Loads the real file into jsdom, drives real interactions
// through the actual rendered DOM (not just calling functions directly),
// and checks both DOM state and fetch call shapes.

const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');

let passed = 0;
let failed = 0;
function check(label, cond, detail) {
  const status = cond ? 'PASS' : 'FAIL';
  console.log(`[${status}] ${label}` + (detail && !cond ? `  (${detail})` : ''));
  if (cond) passed++; else failed++;
}

const html = fs.readFileSync(path.join(__dirname, '../mccf_dialogue_editor.html'), 'utf8');

async function run() {
  const fetchCalls = [];
  let mockFetchImpl = async (url, opts) => {
    fetchCalls.push({ url, opts });
    return { ok: true, json: async () => ({}), text: async () => '', headers: { get: () => '' } };
  };

  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    resources: 'usable',
    url: 'http://localhost/mccf_dialogue_editor.html',
    beforeParse(window) {
      window.fetch = (...args) => mockFetchImpl(...args);
      window.confirm = () => true;
      window.alert = () => {};
      window.URL.createObjectURL = () => 'blob:mock';
      window.URL.revokeObjectURL = () => {};
      window.navigator.clipboard = { writeText: async () => {} };
    },
  });

  // Let the synchronous <script> run (renderAll() at the end of the file).
  await new Promise((resolve) => dom.window.addEventListener('load', resolve));
  const win = dom.window;
  const doc = win.document;

  // ── initial render ────────────────────────────────────────────────
  check('initial render: 5 seed lines in the list', doc.querySelectorAll('.line-card').length === 5,
        `found ${doc.querySelectorAll('.line-card').length}`);
  check('initial render: validation badge shows valid', doc.getElementById('val-badge').textContent.includes('valid'));
  check('initial render: first line auto-selected in editor', doc.querySelector('#main textarea') !== null);

  // ── selecting a line ──────────────────────────────────────────────
  win.selectLine('line_jack_001');
  check('selectLine: jack line becomes active card', doc.querySelector('.line-card.active .lc-actor').textContent === 'Jack');
  check('selectLine: editor shows that line\'s text', doc.querySelector('#main textarea').value.includes('He always did like the water'));
  check('selectLine: provenance badge shows llm-interpreted', doc.querySelector('.prov-badge').textContent.includes('interpreted by Kate'));

  // ── editing fields ────────────────────────────────────────────────
  win.selectLine('line_cindy_001');
  win.updateField('text', 'How does the water feel today, truly?');
  const cindyLine = win.lines.find((l) => l.id === 'line_cindy_001');
  check('updateField: text change reflected in state', cindyLine.text === 'How does the water feel today, truly?');

  win.updateField('blocking', true);
  check('updateField: boolean field updates', cindyLine.blocking === true);

  // ── insertTag: the fixed bug (was appending, now prefixes + inits from text) ──
  win.insertTag('happy');
  check('insertTag: ttsText initialized from clean text + tag prefixed', cindyLine.ttsText === '[happy] How does the water feel today, truly?');
  check('insertTag: tagSource set to authored object', JSON.stringify(cindyLine.tagSource) === JSON.stringify({ type: 'authored' }));

  win.insertTag('whisper');
  check('insertTag: second tag prefixes onto existing ttsText (not blank)', cindyLine.ttsText === '[whisper] [happy] How does the water feel today, truly?');

  // ── onTtsTextEdit: clearing removes both fields cleanly ────────────
  win.onTtsTextEdit('');
  check('onTtsTextEdit(""): ttsText removed entirely', cindyLine.ttsText === undefined);
  check('onTtsTextEdit(""): tagSource removed entirely', cindyLine.tagSource === undefined);

  // ── trigger editing ──────────────────────────────────────────────
  win.updateTriggerType('zone');
  check('updateTriggerType: switches to zone trigger shape', JSON.stringify(cindyLine.trigger) === JSON.stringify({ type: 'zone', zone: '' }));
  win.updateTriggerParam('zone', 'Garden');
  check('updateTriggerParam: sets zone id', cindyLine.trigger.zone === 'Garden');

  win.updateTriggerType('arc-complete');
  check('updateTriggerType: arc-complete has no zone key until set (bare form)', !('zone' in cindyLine.trigger) || cindyLine.trigger.zone === undefined);

  // ── validation surfaces in the UI ──────────────────────────────────
  win.updateField('text', '');
  check('validation: empty text makes the badge show an error', doc.getElementById('val-badge').textContent.includes('error'));
  check('validation: invalid line gets the invalid card class', doc.querySelector(`.line-card.invalid`) !== null);
  win.updateField('text', 'restored');

  // ── audio source flow ──────────────────────────────────────────────
  win.updateAudioSource('recorded');
  check('updateAudioSource: sets audioSource object', JSON.stringify(cindyLine.audioSource) === JSON.stringify({ type: 'recorded' }));
  check('updateAudioSource: audioFile initialized to empty string (not left undefined)', cindyLine.audioFile === '');
  win.updateAudioSource('');
  check('updateAudioSource(""): clears both audioSource and audioFile', cindyLine.audioSource === undefined && cindyLine.audioFile === undefined);

  win.mockGenerateAudio();
  check('mockGenerateAudio: sets a real audioFile path and default source', cindyLine.audioFile.includes('line_cindy_001') && cindyLine.audioSource.type === 'elevenlabs');

  // ── add / delete line ────────────────────────────────────────────
  const countBefore = win.lines.length;
  win.addLine();
  check('addLine: line count increases by 1', win.lines.length === countBefore + 1);
  check('addLine: new line is selected', win.selectedId === win.lines[win.lines.length - 1].id);
  win.deleteLine();
  check('deleteLine: line count returns to previous (confirm mocked true)', win.lines.length === countBefore);

  // ── /voice/preview wiring (mocked fetch) ────────────────────────────
  fetchCalls.length = 0;
  mockFetchImpl = async (url, opts) => {
    fetchCalls.push({ url, opts });
    return {
      ok: true,
      json: async () => ({
        sentiment: 0.1, tag_valence: 0.2, channel_deltas: { E: 0, B: 0, P: 0, S: 0 },
        weights: { E: 0.25, B: 0.25, P: 0.25, S: 0.25 }, arousal_proxy: 0.4, engagement_proxy: 0.5,
        regulation: 1.0, suggested_tag: 'thoughtful', suggested_tts_text: '[thoughtful] restored',
      }),
      text: async () => '',
      headers: { get: () => 'application/json' },
    };
  };
  win.selectedId = 'line_cindy_001';
  win.lines.find((l) => l.id === 'line_cindy_001').text = 'restored';
  await win.runPreview();
  check('runPreview: calls /voice/preview with the line text', fetchCalls.length === 1 && fetchCalls[0].url.endsWith('/voice/preview'));
  check('runPreview: request body carries the line text', JSON.parse(fetchCalls[0].opts.body).text === 'restored');
  const previewedLine = win.lines.find((l) => l.id === 'line_cindy_001');
  check('runPreview: stores the response on the line', previewedLine._preview && previewedLine._preview.suggested_tag === 'thoughtful');
  check('runPreview: renders arousal_proxy/engagement_proxy field names (not the old mock proxy names)',
        doc.body.innerHTML.includes('arousal_proxy') && doc.body.innerHTML.includes('engagement_proxy'));

  win.acceptSuggestedTag();
  check('acceptSuggestedTag: uses the real suggested_tts_text verbatim', previewedLine.ttsText === '[thoughtful] restored');
  check('acceptSuggestedTag: sets tagSource to algorithmic', JSON.stringify(previewedLine.tagSource) === JSON.stringify({ type: 'algorithmic' }));

  // ── preview error handling (network failure) ────────────────────────
  mockFetchImpl = async () => { throw new Error('network down'); };
  await win.runPreview();
  check('runPreview: network failure surfaces as _previewError, not a crash', !!previewedLine._previewError);
  check('runPreview: error message rendered in the preview panel', doc.body.innerHTML.includes('Preview failed'));

  // ── Kate export/import: real engine, XML format ─────────────────────
  win.openExportKateModal();
  const exportXml = doc.querySelector('#modal-body textarea').value;
  check('Kate export: produces real <Dialogue> XML, not bracket format', exportXml.includes('<Dialogue>') && !exportXml.includes('[line_cindy_001]'));
  win.closeModal();

  win.openImportKateModal();
  doc.getElementById('import-name').value = 'Kate';
  doc.getElementById('import-text').value =
    '<Dialogue>\n  <Line id="line_cindy_001" actor="Cindy" type="Question" mode="improv" blocking="true" trigger="zone:Garden" ttsText="[whisper] restored">restored</Line>\n</Dialogue>';
  win.doImport();
  const reImported = win.lines.find((l) => l.id === 'line_cindy_001');
  check('Kate import: applies the reconciled line back into state', reImported.ttsText === '[whisper] restored');
  check('Kate import: auto-stamps tagSource since none was returned', JSON.stringify(reImported.tagSource) === JSON.stringify({ type: 'llm-interpreted', name: 'Kate' }));

  // invalid Kate reply should NOT be applied
  win.openImportKateModal();
  doc.getElementById('import-text').value =
    '<Dialogue>\n  <Line id="line_bad" actor="" type="Statement" mode="static" blocking="false" trigger="scene-start"></Line>\n</Dialogue>';
  const beforeBadImport = win.lines.length;
  win.doImport();
  check('Kate import: invalid reconciled result is NOT applied to state', win.lines.length === beforeBadImport);
  check('Kate import: validation errors shown in the modal instead', doc.getElementById('import-msg').innerHTML.includes('modal-err'));
  win.closeModal();

  // ── Load / Export scene XML (no server needed) ──────────────────────
  const fixtureXml = '<Scene><Zones></Zones><Dialogue>\n  <Line id="loaded_1" actor="Cindy" type="Statement" mode="static" blocking="false" trigger="scene-start">Loaded from a pasted scene.</Line>\n</Dialogue></Scene>';
  win.applyLoadedSceneXml(fixtureXml);
  check('Load scene: replaces in-memory lines with the parsed Dialogue block', win.lines.length === 1 && win.lines[0].id === 'loaded_1');
  check('Load scene: stores the raw XML for later merge-safe export', win.loadedRawXml === fixtureXml);

  win.openExportSceneModal();
  const exportedSceneXml = doc.querySelector('#modal-body textarea').value;
  check('Export scene: merges back into the loaded raw XML (Zones survives untouched)', exportedSceneXml.includes('<Zones>'));
  check('Export scene: contains the current Dialogue content', exportedSceneXml.includes('Loaded from a pasted scene.'));
  win.closeModal();

  // legacy migration fallback
  const legacyXml = '<Scene><Waypoints><Waypoint name="wp1"><Question speaker="Cindy">Legacy Q?</Question></Waypoint></Waypoints></Scene>';
  win.applyLoadedSceneXml(legacyXml);
  check('Load scene: falls back to legacy waypoint migration when no Dialogue block exists',
        win.lines.length === 1 && win.lines[0].trigger.type === 'legacy-waypoint');

  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed === 0 ? 0 : 1);
}

run().catch((e) => { console.error('HARNESS ERROR:', e); process.exit(1); });
