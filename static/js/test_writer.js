const fs = require('fs'), path = require('path');
const T = require('../static/js/mccf_theory.js'), M = require('../static/js/mccf_midi.js'), W = require('../static/js/mccf_smf_writer.js');
const { group, ok, eq, done } = require('./harness.js');

const GOLDEN = 'e72f349d56f814f5042adff00cdf06d9a6dd18a2bff7905c037b69c1d70f31fe';
const buf = fs.readFileSync(path.join(__dirname, '../fixtures/badwater.mid'));
const ab = u8 => u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength);
const parse = u8 => M.parseMidiFile(ab(u8));
const parsed = parse(buf);
const cmpNotes = (a, b) => JSON.stringify(T.sortNotes(a)) === JSON.stringify(T.sortNotes(b));

group('VLQ');
[[0,[0]],[127,[127]],[128,[0x81,0]],[16383,[0xFF,0x7F]],[16384,[0x81,0x80,0]],[0x0FFFFFFF,[0xFF,0xFF,0xFF,0x7F]]]
  .forEach(([n, b]) => eq(W.vlq(n), b, 'vlq ' + n));

group('round trip — the real badwater.mid, all 9 tracks');
{ const out = W.writeSMF(parsed, { name: 'Conductor' }), back = parse(out.bytes);
  eq(back.format, 1, 'format 1'); eq(back.ppq, 480, 'ppq'); eq(back.tracks.length, parsed.tracks.length + 1, 'conductor + 9 tracks');
  eq(back.tempoEvents, parsed.tempoEvents, 'tempo map'); eq(back.timeSigEvents, parsed.timeSigEvents.map(e => e), 'time signature');
  parsed.tracks.forEach((tr, i) => {
    const b = back.tracks[i + 1];
    ok(cmpNotes(tr.notes, b.notes), 'track ' + i + ' ' + tr.name + ': all ' + tr.noteCount + ' notes identical (pitch, tick, duration, velocity, channel)');
    ok(tr.program === b.program, 'track ' + i + ' program ' + tr.program);
    ok(JSON.stringify(tr.controllers) === JSON.stringify(b.controllers) , 'track ' + i + ' controllers identical (' + Object.keys(tr.controllers).length + ' CC numbers)');
    ok(b.name === tr.name, 'track ' + i + ' name');
  });
  ok(out.warnings.length === 0, 'no warnings on a clean file: ' + out.warnings.join('; ')); }

group('round trip — arrangement: retrograde-inversion + three-voice canon');
const KEY = { tonic: 'A', scale: 'major' };
const sha = T.sha256Hex(buf);
const theme = T.extractTheme(parsed, { tracks: [3], bars: [10, 16] });
const recipe = {
  source: { file: 'badwater.mid', sha256: sha, tracks: [3], bars: [10, 16] }, key: KEY, ruleSet: 'chorale-strict', seed: 1729,
  voices: [
    { id: 'lead', name: 'Theme', source: 'theme', entryBar: 1, program: 24, channel: 5, volume: 110, pan: 40, reverb: 50 },
    { id: 'ri',   name: 'Retrograde-inversion', source: 'theme', entryBar: 1, program: 108, channel: 6, volume: 100,
      chain: [{ type: 'retrogradeInversion', params: { axis: 'tonic' } }] }
  ].concat(T.makeCanon({ voices: 2, offsetBars: 2, steps: -4, program: 24, firstChannel: 7, volume: 90 }))
};
const arr = T.assemble(recipe, theme);
{ const out = W.writeSMF(arr, { name: 'Conductor', comment: 'MCCF ' + T.ENGINE.name + ' ' + T.ENGINE.version + ' recipe ' + T.recipeDigest(recipe) });
  const back = parse(out.bytes);
  eq(back.tracks.length, 1 + arr.tracks.length, 'conductor + 4 voice tracks');
  arr.tracks.forEach((tr, i) => { const b = back.tracks[i + 1];
    ok(cmpNotes(tr.notes, b.notes), tr.name + ': notes round-trip (' + tr.noteCount + ')');
    ok(b.program === tr.program && b.name === tr.name, tr.name + ': program and name');
    ok(b.controllers[7][0].value === tr.controllers[7][0].value && b.controllers[7][0].channel === tr.channel, tr.name + ': volume CC7 on its channel');
    ok(b.channelsSeen.length === 1 && b.channelsSeen[0] === tr.channel, tr.name + ': one channel, ' + (tr.channel + 1)); });
  eq(back.tracks[1].controllers[10][0].value, 40, 'pan CC10'); eq(back.tracks[1].controllers[91][0].value, 50, 'reverb CC91');
  eq(back.keySigEvents, [{ tick: 0, sharps: 3, minor: false }], 'key signature A major = 3 sharps');
  eq(back.timeSigEvents[0].num, 4, 'time signature 4/4'); eq(back.tempoEvents, theme.tempoEvents, 'tempo');
  // the retrograde-inversion voice re-imports exactly as the engine made it
  const riVoice = T.resolveVoices(recipe, theme).find(v => v.id === 'ri');
  ok(cmpNotes(back.tracks[2].notes, riVoice.notes.map(n => Object.assign({}, n, { channel: 5 }))), 'retrograde-inversion re-imports identically');
  // consumer check: the real Player accepts the file and sees what we wrote
  const pl = new M.Player({ quiet: true }); const d = pl.load(ab(out.bytes));
  ok(d.tracks.length === 5, 'Player.load: 5 tracks'); ok(pl.enabled[0] === false && pl.enabled[1] && pl.enabled[4], 'conductor off, voices on');
  eq(pl.instrumentName(d.tracks[1]), 'Acoustic Guitar (nylon)', 'Player instrument name, voice 1'); eq(pl.instrumentName(d.tracks[2]), 'Kalimba', 'Player instrument name, voice 2');
  eq(pl.volume[1], 110, 'Player volume from CC7'); eq(pl.resolvedChannel(d.tracks[1]), 4, 'Player output channel');
  pl.dispose();
  // canon geometry in the written file
  const first = i => back.tracks[i].notes[0].startTick;
  ok(first(4) - first(3) === 2 * 1920, 'canon voice 2 enters two bars after voice 1');
  ok(back.tracks[3].notes.length === 23 && back.tracks[4].notes.length === 23, 'canon voices carry the full theme');
  const emb = Buffer.from(out.bytes).toString('latin1'); ok(emb.includes('recipe ' + T.recipeDigest(recipe)), 'recipe digest is embedded in the file'); }

group('canonical serialization / determinism');
{ const a = W.writeSMF(arr, { name: 'Conductor' }).bytes;
  const rebuilt = T.assemble(JSON.parse(JSON.stringify(recipe)), T.extractTheme(parse(new Uint8Array(buf)), { tracks: [3], bars: [10, 16] }));
  const b = W.writeSMF(rebuilt, { name: 'Conductor' }).bytes;
  ok(Buffer.compare(Buffer.from(a), Buffer.from(b)) === 0, 'same recipe + source -> identical bytes (' + a.length + ' bytes)');
  // input order must not matter
  const shuf = JSON.parse(JSON.stringify(arr)); shuf.tracks.forEach(t => t.notes.reverse());
  ok(Buffer.compare(Buffer.from(a), Buffer.from(W.writeSMF(shuf, { name: 'Conductor' }).bytes)) === 0, 'note input order does not change the bytes');
  const withSeed = JSON.parse(JSON.stringify(recipe)); withSeed.seed = 99;
  ok(Buffer.compare(Buffer.from(a), Buffer.from(W.writeSMF(T.assemble(withSeed, theme), { name: 'Conductor' }).bytes)) === 0, 'seed alone does not change a transform-only file (no random choices in 1a)');
  console.log('  golden sha256 of the canon export:', T.sha256Hex(a));
  ok(T.sha256Hex(a) === GOLDEN, 'bytes match the pinned golden hash (any change to serialization or transforms shows here)'); }

group('overlaps, ordering, clamping');
{ const mk = notes => ({ ppq: 480, tempoEvents: [{ tick: 0, usPerQuarter: 500000 }], timeSigEvents: [], keySigEvents: [],
    tracks: [{ name: 't', channel: 0, program: 0, controllers: {}, notes: notes.map(([p, s, d, ch]) => ({ pitch: p, startTick: s, durTicks: d, velocity: 90, channel: ch || 0 })) }] });
  let r = W.writeSMF(mk([[60, 0, 960], [60, 480, 480]]), {}); let b = parse(r.bytes);
  eq(b.tracks[1].notes.map(n => [n.startTick, n.durTicks]), [[0, 480], [480, 480]], 'overlapping same-pitch note: earlier one trimmed'); ok(r.warnings.length === 1, 'and a warning is returned');
  r = W.writeSMF(mk([[60, 0, 480], [60, 480, 480]]), {}); b = parse(r.bytes);
  eq(b.tracks[1].notes.length, 2, 'back-to-back same pitch stays two notes (off sorts before on)');
  r = W.writeSMF(mk([[60, 0, 480], [60, 0, 240]]), {}); eq(parse(r.bytes).tracks[1].notes.length, 1, 'duplicate onset collapsed to one note');
  r = W.writeSMF(mk([[130, 0, 0], [-5, 10, 480]]), {}); b = parse(r.bytes);
  ok(b.tracks[1].notes.every(n => n.pitch >= 0 && n.pitch <= 127 && n.durTicks >= 1), 'pitch clamped to 0-127, duration at least one tick');
  r = W.writeSMF(mk([[60, 0.4, 479.6]]), {}); eq(parse(r.bytes).tracks[1].notes.map(n => [n.startTick, n.durTicks]), [[0, 480]], 'fractional ticks rounded to integers once, here'); }

done();
