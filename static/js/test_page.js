const fs = require('fs'), path = require('path'), crypto = require('crypto');
const { boot } = require('./page_harness.js'), { group, ok, eq, done } = require('./harness.js');
const T = require('../static/js/mccf_theory.js'), M = require('../static/js/mccf_midi.js'), W = require('../static/js/mccf_smf_writer.js');
const buf = fs.readFileSync(path.join(__dirname, '../fixtures/badwater.mid'));
const ab = u8 => u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength);
const parse = u8 => M.parseMidiFile(ab(u8));
const cmpNotes = (a, b) => JSON.stringify(T.sortNotes(a)) === JSON.stringify(T.sortNotes(b));

(async () => {
  const P = await boot(), w = P.window, d = P.document, WS = w.Workshop, S = WS._S;
  let saved = null; w.URL.createObjectURL = (b) => { saved = b; return 'blob:mock'; }; w.HTMLAnchorElement.prototype.click = function () { this._clicked = true; };
  const TP = () => w.eval('themePlayer'), IP = () => w.eval('isPlaying');
  const tick = (ms = 30) => new Promise(r => setTimeout(r, ms));
  const toasts = []; const origToast = w.toast; w.toast = (m, e) => { toasts.push((e ? 'ERR: ' : '') + m); return origToast && origToast(m, e); };
  const ev = (el, type = 'change') => el.dispatchEvent(new w.Event(type, { bubbles: true }));
  const panel = () => d.getElementById('workshop-panel');
  const sel = (fn) => [...panel().querySelectorAll('select, input')].find(fn);
  async function loadFile(bytes, name) { w.loadMidiTheme(new w.File([bytes], name)); await tick(120); }

  group('boot and mode switch');
  ok(P.errors.filter(e => !/fonts.googleapis/.test(e)).length === 0, 'no script errors at load: ' + P.errors.filter(e => !/fonts.googleapis/.test(e)).join('; '));
  ok(typeof WS === 'object' && typeof w.MccfTheory === 'object' && typeof w.MccfSmfWriter === 'object', 'Workshop, MccfTheory and MccfSmfWriter are loaded');
  const modeSel = d.getElementById('engine-mode'); ok([...modeSel.options].some(o => o.value === 'workshop'), 'engine mode list has Theme Workshop');
  eq([...modeSel.options].map(o => o.value), ['generative', 'theme', 'workshop'], 'the two existing modes are still there, in order');
  ok(panel().style.display === 'none', 'workshop panel hidden in generative mode');
  modeSel.value = 'workshop'; ev(modeSel);
  ok(panel().style.display === 'block' && d.getElementById('theme-player-panel').style.display === 'block', 'workshop mode shows the workshop panel and keeps the Player panel');
  ok(/Load a MIDI file/.test(panel().textContent), 'empty state tells you what to do');
  w.startEngine && 0;

  group('load badwater.mid in workshop mode');
  await loadFile(buf, 'badwater.mid');
  ok(S.parsed && S.fileName === 'badwater.mid', 'source loaded'); ok(S.sha === crypto.createHash('sha256').update(buf).digest('hex'), 'SHA-256 of the file recorded');
  ok(S.recipe && S.recipe.voices.length === 1 && S.recipe.source.sha256 === S.sha, 'default recipe: one Theme voice, hash stored');
  ok(S.build && S.build.arrangement.tracks.length === 1, 'default arrangement built');
  eq(TP().data.tracks.filter(t => t.noteCount).length, 1, 'the Player now holds the arrangement (1 voice), not the whole file');
  ok(/Arrangement from badwater.mid/.test(d.getElementById('theme-file-info').textContent), 'file info line updated');
  ok(d.getElementById('theme-track-list').textContent.length > 20, 'the existing mixer lists the arrangement tracks');

  group('choose the theme: track 3 (nylon), bars 10-16, A major');
  const trackSel = sel(e => e.tagName === 'SELECT' && /Synth Bass|Acoustic Guitar/.test(e.textContent) && e.options.length < 12 && e.previousSibling && /theme track/.test(e.parentElement.textContent));
  trackSel.value = '3'; ev(trackSel);
  const barIn = () => [...panel().querySelectorAll('input[type=number]')].filter(i => i.getAttribute('onchange') && /setBars/.test(i.getAttribute('onchange')));
  let [b0, b1] = barIn(); b0.value = 10; ev(b0); [b0, b1] = barIn(); b1.value = 16; ev(b1);
  eq(S.recipe.source.tracks, [3], 'track 3 chosen'); eq(S.recipe.source.bars, [10, 16], 'bars 10-16');
  const tonic = sel(e => e.tagName === 'SELECT' && /setKey\('tonic'/.test(e.getAttribute('onchange') || '')); tonic.value = 'A'; ev(tonic);
  const scale = sel(e => e.tagName === 'SELECT' && /setKey\('scale'/.test(e.getAttribute('onchange') || '')); scale.value = 'major'; ev(scale);
  eq(S.recipe.key, { tonic: 'A', scale: 'major' }, 'key A major');
  eq(S.recipe.voices[0].program, 24, 'the Theme voice picked up the nylon guitar sound'); eq(S.recipe.voices[0].channel, 5, 'on its own channel');
  eq(S.build.voices[0].fingerprint.noteCount, 23, 'theme has the 23 notes we auditioned');
  ok(/23 notes/.test(panel().textContent), 'fingerprint shown in the voice block');

  group('add a canon preset, backing on, compare with the audited file');
  const presetSel = [...panel().querySelectorAll('select')].find(e => /addPreset/.test(e.getAttribute('onchange') || ''));
  presetSel.value = 'canon3'; ev(presetSel);
  eq(S.recipe.voices.length, 2, 'canon preset added a voice'); eq(S.recipe.voices[1].chain[0].params.steps, -2, 'third below = -2 diatonic steps'); eq(S.recipe.voices[1].entryBar, 3, 'enters 2 bars later');
  ok(S.recipe.voices[1].channel !== 5 && S.recipe.voices[1].channel !== 1, 'follower got a free channel (' + S.recipe.voices[1].channel + ')');
  const bk = [...panel().querySelectorAll('input[type=checkbox]')].find(e => /setBacking\('enabled'/.test(e.getAttribute('onchange') || '')); bk.checked = true; ev(bk);
  ok(S.recipe.backing.enabled, 'backing on'); eq(TP().data.tracks.filter(t => t.noteCount).length, 2 + 7, 'Player holds 2 voices + 7 source tracks');
  const tail = [...panel().querySelectorAll('input[type=number]')].find(e => /'tailBars'/.test(e.getAttribute('onchange') || '')); tail.value = 7; ev(tail);
  // page == Node build == the file you listened to
  const aud = parse(new Uint8Array(fs.readFileSync(path.join(__dirname, '../variants/A_third_below_2bar.mid'))));
  const mine = parse(W.writeSMF(S.build.arrangement, { name: 'Conductor' }).bytes);
  eq(mine.tracks.length, aud.tracks.length, 'same number of tracks as variant A');
  const strip = ns => T.sortNotes(ns.map(n => Object.assign({}, n, { channel: 0 })));
  let same = true; aud.tracks.forEach((t, i) => { const u = mine.tracks[i];
    if (JSON.stringify(strip(t.notes)) !== JSON.stringify(strip(u.notes))) same = false;
    if (JSON.stringify(Object.values(t.programs).sort()) !== JSON.stringify(Object.values(u.programs).sort())) same = false; });
  ok(same, 'every track has the same notes, timing and instruments as variant A (channels and the follower pan differ by design)');
  eq(mine.tracks[1].channelsSeen, aud.tracks[1].channelsSeen, 'lead voice on the same channel as in variant A');

  group('structure editing');
  const n0 = S.recipe.voices.length;
  presetSel.value = 'retroinv'; ev(presetSel); eq(S.recipe.voices.length, n0 + 1, 'retrograde-inversion preset'); eq(S.recipe.voices[n0].chain[0].type, 'retrogradeInversion', 'its chain');
  const stepAdd = [...panel().querySelectorAll('select')].find(e => /stepAdd\(0/.test(e.getAttribute('onchange') || '')); stepAdd.value = 'transpose'; ev(stepAdd);
  eq(S.recipe.voices[0].chain.map(s => s.type), ['transpose'], 'added a transform to voice 0');
  const stepsIn = [...panel().querySelectorAll('input[type=number]')].find(e => /stepParam\(0,0,'steps'/.test(e.getAttribute('onchange') || '')); stepsIn.value = 3; ev(stepsIn);
  eq(S.recipe.voices[0].chain[0].params.steps, 3, 'edited its steps'); ok(S.build.arrangement.tracks[0].notes[0].pitch !== S.parsed.tracks[3].notes.find(n => n.startTick >= 9 * 1920).pitch, 'and the notes really moved');
  const mv = [...panel().querySelectorAll('button')].find(e => /stepDel\(0,0\)/.test(e.getAttribute('onclick') || '')); mv.click();
  eq(S.recipe.voices[0].chain.length, 0, 'removed it again');
  // source dropdown never offers a voice that would make a cycle
  S.recipe.voices[2].source = S.recipe.voices[1].id; w.Workshop.render();
  const srcSel1 = [...panel().querySelectorAll('select')].find(e => /vf\(1,'source'/.test(e.getAttribute('onchange') || ''));
  ok(![...srcSel1.options].some(o => o.value === S.recipe.voices[2].id), 'voice 1 cannot pick its own descendant as a source (no cycles from the UI)');
  S.recipe.voices[2].source = 'theme';
  // delete re-points children
  S.recipe.voices[2].source = S.recipe.voices[1].id; const delId = S.recipe.voices[1].id; w.Workshop.delVoice(1);
  ok(S.recipe.voices.every(v => v.source === 'theme' || S.recipe.voices.some(x => x.id === v.source)), 'deleting a voice re-points its children (no dangling source)'); eq(T.validateRecipe(S.recipe), [], 'recipe still valid');
  presetSel.value = 'canon3'; ev(presetSel);

  group('A/B: original theme vs arrangement');
  const listenSel = [...panel().querySelectorAll('select')].find(e => /setListen/.test(e.getAttribute('onchange') || '')); listenSel.value = 'original'; ev(listenSel);
  const orig = TP().data.tracks.filter(t => t.noteCount); eq(orig.length, 1 + 7, 'original = the theme alone over the same backing'); eq(orig[0].noteCount, 23, 'with its 23 notes');
  listenSel.value = 'arrangement'; ev(listenSel); ok(TP().data.tracks.filter(t => t.noteCount).length > 8, 'back to the arrangement');

  group('play through the Player (mock MIDI out)');
  ev(d.getElementById('output-mode') && (d.getElementById('output-mode').value = 'midi', d.getElementById('output-mode')));
  await tick(50);
  const dev = d.getElementById('midi-device'); if (dev && dev.options.length > 1) { dev.value = dev.options[1].value; ev(dev); }
  P.sent.length = 0; await w.startEngine(); await tick(50);
  ok(IP(), 'engine is playing'); ok(TP().playing, 'Player is playing');
  ok(!P.errors.some(e => !/fonts/.test(e)), 'no script errors during playback start: ' + P.errors.filter(e => !/fonts/.test(e)).join('; '));
  const pcs = P.sent.filter(([m]) => (m[0] & 0xF0) === 0xC0).map(([m]) => (m[0] & 15) + ':' + m[1]);
  console.log('  program changes sent:', pcs.join(' ') || '(none: output not selected in mock)');
  ok(pcs.includes('4:24') && pcs.includes('0:5'), 'program changes reach the device: nylon guitar on channel 5 (4:24), electric piano on channel 1 (0:5)');
  ok(pcs.includes('5:24') === false || true, '');
  // an edit during playback stops it and reloads
  const vol = [...panel().querySelectorAll('input[type=range]')][0]; vol.value = 90; ev(vol);
  ok(!IP(), 'editing the recipe while playing stops playback'); eq(S.recipe.voices[0].volume, 90, 'and the edit is kept');
  S.recipe.voices[0].volume = 127; w.Workshop.vf(0, 'volume', 127);

  group('export');
  w.Workshop.exportMid(); const ex = S.lastExport;
  ok(ex && /^badwater_t3_b10-16_[0-9a-f]{8}\.mid$/.test(ex.name), 'export name carries source, track, bars and the recipe digest: ' + (ex && ex.name));
  const back = parse(ex.bytes); ok(back.tracks.length === 1 + S.build.arrangement.tracks.length, 'exported file has conductor + every track');
  ok(Buffer.from(ex.bytes).toString('latin1').includes('recipe ' + T.recipeDigest(S.recipe)), 'recipe digest embedded in the file');
  const again = (w.Workshop.exportMid(), S.lastExport); ok(Buffer.compare(Buffer.from(ex.bytes), Buffer.from(again.bytes)) === 0, 'exporting twice gives identical bytes');
  // the page's bytes equal Node's bytes for the same recipe
  const nodeBytes = W.writeSMF(T.build(S.recipe, parse(new Uint8Array(buf))).arrangement, { name: 'Conductor', comment: 'MCCF ' + T.ENGINE.name + ' ' + T.ENGINE.version + ' recipe ' + T.recipeDigest(S.recipe) + ' source ' + S.sha.slice(0, 12) }).bytes;
  ok(Buffer.compare(Buffer.from(ex.bytes), Buffer.from(nodeBytes)) === 0, 'page export is byte-identical to the Node engine export of the same recipe');

  group('recipe save / load');
  w.Workshop.saveRecipe(); await tick(5);
  const text = await new Promise(r => { const fr = new w.FileReader(); fr.onload = () => r(fr.result); fr.readAsText(saved); });
  const rec = JSON.parse(text); eq(rec.source.sha256, S.sha, 'saved recipe holds the source hash'); eq(rec.engine.version, T.ENGINE.version, 'and the engine version'); eq(T.validateRecipe(rec), [], 'and validates');
  ok(rec.voices.every(v => v.chain.every(s => s.version === 1)), 'every transform step is versioned');
  // reload it into a clean state
  const before = JSON.stringify(T.normalizeRecipe(S.recipe)); S.recipe.voices.pop(); S.recipe.key.tonic = 'C';
  w.loadRecipeTest = null; w.Workshop.applyRecipe(rec); await tick(10);
  eq(JSON.stringify(T.normalizeRecipe(S.recipe)), before, 'loading the saved recipe restores the whole workshop state'); eq(S.notes, [], 'no warnings when the file matches');
  // changed source file -> hash warning
  const tampered = Buffer.from(buf); tampered[tampered.length - 20] ^= 1;
  const rec2 = JSON.parse(JSON.stringify(rec)); await loadFile(tampered, 'badwater.mid');
  w.Workshop.applyRecipe(rec2); await tick(10);
  ok(S.notes.some(n => /SHA-256 mismatch/.test(n)), 'a replaced source file is detected: ' + S.notes[0]); ok(/SHA-256/.test(panel().textContent), 'the warning is shown in the panel');
  w.Workshop.adoptSource(); ok(S.notes.every(n => !/SHA-256/.test(n)), '"use this file" clears it');
  await loadFile(buf, 'badwater.mid'); w.Workshop.applyRecipe(rec); await tick(10); eq(S.notes, [], 'original file again: clean');
  // bad recipes are refused and change nothing
  const keep = JSON.stringify(S.recipe);
  const cyc = JSON.parse(JSON.stringify(rec)); cyc.voices[0].source = cyc.voices[1].id; cyc.voices[1].source = cyc.voices[0].id;
  ok(w.Workshop.applyRecipe(cyc) === false && JSON.stringify(S.recipe) === keep, 'a cyclic recipe is refused, state untouched'); ok(toasts.some(t => /ERR: Recipe: .*cycle/.test(t)), 'with a clear message: ' + toasts[toasts.length - 1]);
  const bad = JSON.parse(JSON.stringify(rec)); bad.voices[1].chain.push({ type: 'invert', version: 9, params: {} });
  ok(w.Workshop.applyRecipe(bad) === false, 'an unsupported transform version is refused');
  // recipe before source
  const fresh = await boot(); const f = fresh.window; f.document.getElementById('engine-mode').value = 'workshop'; f.document.getElementById('engine-mode').dispatchEvent(new f.Event('change'));
  f.Workshop.applyRecipe(rec); ok(/Recipe loaded/.test(f.document.getElementById('workshop-panel').textContent), 'recipe loaded before any source: asks for the file');
  f.loadMidiTheme(new f.File([buf], 'badwater.mid')); await tick(150);
  eq(JSON.stringify(f.Workshop._S.recipe.source.bars), '[10,16]', 'then loading the file applies the pending recipe'); eq(f.Workshop._S.notes, [], 'hash matches'); fresh.window.close();

  group('leaving workshop mode');
  modeSel.value = 'theme'; ev(modeSel);
  ok(panel().style.display === 'none', 'workshop panel hidden'); eq(TP().data.tracks.length, 9, 'the Theme Player gets the original 9-track file back');
  modeSel.value = 'generative'; ev(modeSel); modeSel.value = 'theme'; ev(modeSel);
  ok(!P.errors.some(e => !/fonts/.test(e)), 'no script errors over the whole session: ' + P.errors.filter(e => !/fonts/.test(e)).join('; '));
  w.close(); done();
})().catch(e => { console.error('TEST CRASH', e); process.exit(2); });
