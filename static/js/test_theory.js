const fs = require('fs'), path = require('path'), crypto = require('crypto');
const T = require('../static/js/mccf_theory.js'), M = require('../static/js/mccf_midi.js');
const { group, ok, eq, done } = require('./harness.js');

const buf = fs.readFileSync(path.join(__dirname, '../fixtures/badwater.mid'));
const parsed = M.parseMidiFile(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
const KEY = { tonic: 'A', scale: 'major' };
const PPQ = 480;
function fakeParsed(notes, len) { // one-track parsed-shaped fixture, 4/4
  return { ppq: PPQ, tempoEvents: [{ tick: 0, usPerQuarter: 500000 }], timeSigEvents: [],
           tracks: [{ index: 0, notes: notes.map(([p, s, d]) => ({ pitch: p, startTick: s, durTicks: d, velocity: 90, channel: 0 })) }] };
}
const q = 480;
const FIX = {
  'scale run':        fakeParsed([[69,0,q],[71,q,q],[73,2*q,q],[74,3*q,q],[76,4*q,q],[78,5*q,q],[80,6*q,q],[81,7*q,q]]),
  'leap-heavy':       fakeParsed([[57,0,q],[76,q,q/2],[62,1.5*q,q/2],[81,2*q,q],[55,3*q,q],[73,4*q,2*q],[64,6*q,q],[88,7*q,q]]),
  'chromatic passing':fakeParsed([[69,0,q],[70,q,q/2],[71,1.5*q,q/2],[73,2*q,q],[75,3*q,q/2],[76,3.5*q,q/2],[73,4*q,2*q],[68,6*q,2*q]]),
};
const SEL = { tracks: [0], bars: [1, 2] };
const themes = {};
Object.keys(FIX).forEach(k => themes[k] = T.extractTheme(FIX[k], SEL));
themes['badwater t3 b10-16'] = T.extractTheme(parsed, { tracks: [3], bars: [10, 16] });
themes['badwater EP2 b10-12 (poly)'] = T.extractTheme(parsed, { tracks: [2], bars: [10, 12] });

function run(theme, chain, scale = 'major') {
  const base = { ki: T.keyInfo({ tonic: 'A', scale }), ppq: theme.ppq, barTicks: theme.barTicks, anchor: theme.notes[0].pitch };
  return T.applyChain(theme.notes, theme.length, chain, base, 'test');
}
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const ch = (type, params) => ({ type, params });

group('sha256 matches node crypto');
[0, 1, 55, 56, 63, 64, 65, 119, 120, 1000].forEach(n => {
  const b = Buffer.alloc(n, 7); b.forEach((_, i) => b[i] = (i * 31 + 7) & 255);
  ok(T.sha256Hex(new Uint8Array(b)) === crypto.createHash('sha256').update(b).digest('hex'), 'len ' + n);
});
ok(T.sha256Hex(buf) === crypto.createHash('sha256').update(buf).digest('hex'), 'badwater.mid');

group('pitch space');
['major', 'minor', 'harmonic-minor', 'dorian', 'pentatonic', 'pentatonic-minor', 'hexatonic'].forEach(sc => {
  const ki = T.keyInfo({ tonic: 'F#', scale: sc }); let bad = 0, inscaleBad = 0;
  for (let p = 0; p <= 127; p++) {
    const d = T.toDegree(p, ki);
    if (T.fromDegree(d.abs, d.alt, ki) !== p) bad++;
    const pcRel = (((p - ki.tonicPc) % 12) + 12) % 12;
    if (ki.steps.includes(pcRel) && d.alt !== 0) inscaleBad++;
  }
  ok(bad === 0, sc + ' round trip'); ok(inscaleBad === 0, sc + ' in-scale notes have alteration 0');
});
{ const ki = T.keyInfo(KEY);   // A major: C#5 = 73 is degree 2; A5 = 81 is 7 steps above A4
  const a4 = T.toDegree(69, ki), a5 = T.toDegree(81, ki), cs5 = T.toDegree(73, ki);
  ok(a5.abs - a4.abs === 7, 'octave = 7 steps in major'); ok(cs5.abs - a4.abs === 2, 'C#5 is two steps above A4');
  const kp = T.keyInfo({ tonic: 'A', scale: 'pentatonic' });
  ok(T.toDegree(81, kp).abs - T.toDegree(69, kp).abs === 5, 'octave = 5 steps in pentatonic');
  ok(T.fromDegree(T.toDegree(69, kp).abs + 2, 0, kp) === 73, 'pentatonic +2 steps from A4 = C#5');
  ok(T.fromDegree(T.toDegree(69, ki).abs + 2, 0, ki) === 73, 'major +2 steps from A4 = C#5 (a third)');
  const alt = T.toDegree(70, ki); ok(alt.alt !== 0, 'A#4 is outside A major and carries an alteration'); }

group('bar map');
{ const bm = T.makeBarMap(480, []); ok(bm.tickOfBar(1) === 0 && bm.tickOfBar(10) === 9 * 1920, '4/4 default');
  const b34 = T.makeBarMap(480, [{ tick: 0, num: 3, den: 4 }]); ok(b34.tickOfBar(3) === 2880, '3/4');
  const b68 = T.makeBarMap(480, [{ tick: 0, num: 6, den: 8 }]); ok(b68.tickOfBar(2) === 1440, '6/8 = 1440 ticks');
  const mix = T.makeBarMap(480, [{ tick: 0, num: 4, den: 4 }, { tick: 3840, num: 3, den: 4 }]);
  ok(mix.tickOfBar(3) === 3840 && mix.tickOfBar(5) === 3840 + 2 * 1440, 'meter change at bar 3'); }

group('theme extraction');
{ const th = themes['badwater t3 b10-16'];
  eq(th.notes.length, 23, 'badwater track 3 bars 10-16 has 23 notes');
  ok(th.length === 7 * 1920, 'region is 7 bars'); ok(th.notes[0].startTick === 240 && th.notes[0].pitch === 76, 'first note E5 at +240 (rebased)');
  ok(Object.isFrozen(th.notes) && Object.isFrozen(th.notes[0]), 'theme notes frozen');
  ok(th.timeSig.num === 4 && th.timeSig.den === 4, 'time signature read from file');
  eq(th.tempoEvents, [{ tick: 0, usPerQuarter: 472440 }], 'tempo at region start');
  ok(th.notes.every(n => n.startTick >= 0 && n.startTick + n.durTicks <= th.length), 'all notes inside region');
  const est = T.estimateKey(th.notes); ok(est && est.tonic && est.scale, 'key estimate returns a key (' + est.tonic + ' ' + est.scale + '; recipe states A major explicitly)'); }

for (const name of Object.keys(themes)) {
  const th = themes[name], L = th.length;
  group('properties — ' + name);
  const before = JSON.stringify(th.notes);
  // retrograde twice
  ok(same(run(th, [ch('retrograde'), ch('retrograde')]).notes, th.notes), 'retrograde twice = original');
  ok(run(th, [ch('retrograde')]).notes.every(n => n.startTick >= 0 && n.startTick + n.durTicks <= L), 'retrograde stays inside region');
  // diatonic inversion twice, several axes
  const mono = new Set(th.notes.map(n => n.startTick)).size === th.notes.length;
  (mono ? ['first', 'tonic', { pitch: 66 }] : ['tonic', { pitch: 66 }]).forEach(ax =>
    ok(same(run(th, [ch('invert', { axis: ax }), ch('invert', { axis: ax })]).notes, th.notes), 'diatonic inversion twice, axis ' + JSON.stringify(ax)));
  ok(same(run(th, [ch('invert', { mode: 'chromatic', axis: { pitch: 66 } }), ch('invert', { mode: 'chromatic', axis: { pitch: 66 } })]).notes, th.notes), 'chromatic inversion twice (explicit axis)');
  if (mono) ok(same(run(th, [ch('invert', { mode: 'chromatic' }), ch('invert', { mode: 'chromatic' })]).notes, th.notes), 'chromatic inversion twice (axis = first note)');
  // transpose n then -n
  [[3, 'diatonic'], [-5, 'diatonic'], [9, 'diatonic'], [7, 'chromatic'], [-12, 'chromatic']].forEach(([n, mode]) =>
    ok(same(run(th, [ch('transpose', { steps: n, mode }), ch('transpose', { steps: -n, mode })]).notes, th.notes), 'transpose ' + n + ' ' + mode + ' then back'));
  // augment p:q then q:p within one tick
  [[2,1],[3,2],[1,2],[1,3],[5,3],[7,4]].forEach(([p, qq]) => {
    const r = run(th, [ch('augment', { p, q: qq }), ch('augment', { p: qq, q: p })]); let worst = 0;
    r.notes.forEach((n, i) => { const o = th.notes[i]; worst = Math.max(worst, Math.abs(n.startTick - o.startTick), Math.abs(n.durTicks - o.durTicks)); });
    ok(worst <= 1 && r.notes.length === th.notes.length, 'augment ' + p + ':' + qq + ' round trip, worst error ' + worst + ' tick');
  });
  // exact ratios at 480 ppq
  [[2,1],[3,2],[1,2],[1,3]].forEach(([p, qq]) => { const r = run(th, [ch('augment', { p, q: qq })]);
    ok(r.notes.every(n => Number.isInteger(n.startTick) && n.durTicks >= 1), 'augment ' + p + ':' + qq + ' integer ticks, min duration 1'); });
  // inversion preserves interval sizes
  { const ki = T.keyInfo(KEY), s = run(th, []).notes;
    const inv = run(th, [ch('invert', { mode: 'diatonic' })]).notes, invc = run(th, [ch('invert', { mode: 'chromatic' })]).notes;
    // match notes by index (inversion changes pitch only; both lists share the canonical time order of the originals' starts)
    const byStart = a => a.map(n => n.startTick + ':' + n.durTicks);
    const sortIdx = (orig, res) => { const idx = orig.map((n, i) => [n, i]).sort((a, b) => 0); return res; };
    // pair by original index via a keyed rebuild: invert with identity-tagged velocities
    const tagged = s.map((n, i) => Object.assign({}, n, { velocity: i + 1 }));
    const base = { ki, ppq: PPQ, barTicks: th.barTicks };
    const A = T.applyChain(tagged, L, [ch('invert', { mode: 'diatonic' })], base, 't').notes;
    const B = T.applyChain(tagged, L, [ch('invert', { mode: 'chromatic' })], base, 't').notes;
    const ordA = []; A.forEach(n => ordA[n.velocity - 1] = n); const ordB = []; B.forEach(n => ordB[n.velocity - 1] = n);
    let badD = 0, badC = 0;
    for (let i = 0; i < s.length; i++) for (let j = i + 1; j < s.length; j++) {
      const dg = n => n._d || T.toDegree(n.pitch, ki);
      const d0 = dg(s[i]).abs - dg(s[j]).abs;
      const d1 = dg(ordA[i]).abs - dg(ordA[j]).abs;
      if (d1 !== -d0) badD++;
      if ((ordB[i].pitch - ordB[j].pitch) !== -(s[i].pitch - s[j].pitch)) badC++;
    }
    ok(badD === 0, 'diatonic inversion preserves every interval in steps (' + badD + ' violations)');
    ok(badC === 0, 'chromatic inversion preserves every interval in semitones (' + badC + ' violations)'); }
  // retrograde-inversion = inversion then retrograde
  ok(same(run(th, [ch('retrogradeInversion', { axis: 'tonic' })]).notes, run(th, [ch('invert', { axis: 'tonic' }), ch('retrograde')]).notes), 'retrograde-inversion = invert then retrograde');
  // rotation: k then (m-k) restores (distinct onsets only)
  { const onsets = new Set(th.notes.map(n => n.startTick)); const m = th.notes.length;
    if (onsets.size === m && m > 2) { const k = Math.floor(m / 3);
      const s0 = th.notes[0].startTick, expect = th.notes.map(n => Object.assign({}, n, { startTick: n.startTick - s0 }));
      ok(same(run(th, [ch('rotate', { k }), ch('rotate', { k: m - k })]).notes, expect), 'rotate k then m-k restores the theme (starting at its first note, no leading rest)'); }
    ok(run(th, [ch('rotate', { k: 2 })]).notes.length === m, 'rotate keeps note count'); }
  // sequence
  { const r = run(th, [ch('sequence', { copies: 3, step: 2 })]);
    ok(r.notes.length === 3 * th.notes.length && r.length === 3 * L, 'sequence x3: notes and length');
    const second = r.notes.filter(n => n.startTick >= L && n.startTick < 2 * L);
    ok(second.length === th.notes.length, 'second copy has the same note count'); }
  // fragmentation + octave shift
  { const f = run(th, [ch('fragment', { bars: [1, 1] })]);
    ok(f.length === th.barTicks && f.notes.every(n => n.startTick < th.barTicks), 'fragment bar 1');
    const o = run(th, [ch('octaveShift', { octaves: -1 })]);
    ok(o.notes.every((n, i) => n.pitch === th.notes[i].pitch - 12), 'octave shift -1 moves every note a whole octave');
    const oSome = run(th, [ch('octaveShift', { octaves: 1, range: { notes: [0, 0] } })]);
    ok(oSome.notes.filter((n, i) => n.pitch !== th.notes[i].pitch).length === 1, 'octave shift on a note range moves only that range'); }
  // theme never modified
  ok(JSON.stringify(th.notes) === before, 'theme untouched after chains');
  // fingerprint relationships
  { const f0 = T.fingerprint(th.notes, L, PPQ, th.barTicks);
    const fr = run(th, [ch('retrograde')]), f1 = T.fingerprint(fr.notes, fr.length, PPQ, th.barTicks);
    ok(f1.noteCount === f0.noteCount && f1.rangeSemitones === f0.rangeSemitones && f1.meanPitch === f0.meanPitch &&
       f1.lengthTicks === f0.lengthTicks && same(f1.intervalHistogram, f0.intervalHistogram) || f0.onsetCount !== f0.noteCount, 'retrograde fingerprint matches original (count, range, mean, length, interval sizes)');
    const dm = run(th, [ch('diminish', { p: 2, q: 1 })]), f2 = T.fingerprint(dm.notes, dm.length, PPQ, th.barTicks);
    ok(f2.noteCount === f0.noteCount && Math.abs(f2.lengthBars - f0.lengthBars / 2) < 1e-9, 'diminution 2:1 halves the length, keeps the notes');
    ok(Math.abs(f2.notesPerBeat - 2 * f0.notesPerBeat) < 0.01, 'diminution doubles note density'); }
}

group('transform details');
{ const th = themes['scale run'], ki = T.keyInfo(KEY);
  const up2 = run(th, [ch('transpose', { steps: 2 })]).notes.map(n => n.pitch);
  eq(up2, [73,74,76,78,80,81,83,85], 'diatonic +2 on an A major scale run gives a sequence of thirds');
  const cr = run(th, [ch('transpose', { steps: 2, mode: 'chromatic' })]).notes.map(n => n.pitch);
  eq(cr, th.notes.map(n => n.pitch + 2), 'chromatic transposition is exact');
  const inv = run(th, [ch('invert')]).notes.map(n => n.pitch).sort((a, b) => a - b);
  eq(inv[inv.length - 1], 69, 'inversion about the first note (A4) leaves A4 as the top note of a rising run');
  const mix = run(themes['chromatic passing'], [ch('transpose', { steps: 2 })]).notes;
  const d0 = T.toDegree(themes['chromatic passing'].notes[1].pitch, ki), d1 = mix[1]._d;
  ok(d0.alt === d1.alt && d0.alt !== 0, 'passing tone keeps its alteration under diatonic transposition');
  const mm = run(th, [ch('transpose', { steps: 100, mode: 'chromatic' })]); ok(mm.warnings.length === 1 && mm.notes.every(n => n.pitch <= 127), 'out-of-range pitches fold by octave and warn'); }

group('recipe, versions, DAG');
{ const th = themes['badwater t3 b10-16'];
  const base = { source: { file: 'badwater.mid', sha256: T.sha256Hex(buf), tracks: [3], bars: [10, 16] }, key: KEY, seed: 1729 };
  const good = Object.assign({}, base, { voices: [
    { id: 'theme', name: 'x', source: 'theme' }] });
  ok(T.validateRecipe(good).some(e => /reserved/.test(e)), 'voice id "theme" rejected');
  const r = Object.assign({}, base, { voices: [
    { id: 'a', name: 'Theme', source: 'theme', chain: [], entryBar: 1, program: 24, channel: 5 },
    { id: 'b', name: 'Inv', source: 'a', chain: [ch('invert', { axis: 'tonic' })], entryBar: 3, program: 24, channel: 6 },
    { id: 'c', name: 'Dim', source: 'b', chain: [ch('diminish', { p: 2, q: 1 })], entryBar: 5, program: 108, channel: 7 }] });
  eq(T.validateRecipe(r), [], 'valid recipe has no errors');
  const cyc = JSON.parse(JSON.stringify(r)); cyc.voices[0].source = 'c';
  ok(T.validateRecipe(cyc).some(e => /cycle/.test(e)), 'cycle A->C->B->A rejected');
  const self = JSON.parse(JSON.stringify(r)); self.voices[1].source = 'b';
  ok(T.validateRecipe(self).some(e => /cycle/.test(e)), 'self-reference rejected');
  const unk = JSON.parse(JSON.stringify(r)); unk.voices[1].source = 'zzz';
  ok(T.validateRecipe(unk).some(e => /unknown source/.test(e)), 'unknown source rejected');
  const dup = JSON.parse(JSON.stringify(r)); dup.voices[1].id = 'a';
  ok(T.validateRecipe(dup).some(e => /duplicate/.test(e)), 'duplicate id rejected');
  const ver = JSON.parse(JSON.stringify(r)); ver.voices[1].chain[0].version = 2;
  ok(T.validateRecipe(ver).some(e => /version 2 unsupported/.test(e)), 'unsupported transform version rejected');
  ok(T.validateRecipe(Object.assign({}, r, { key: { tonic: 'A', scale: 'nope' } })).length > 0, 'bad scale rejected');
  ok(T.validateRecipe(Object.assign({}, r, { ruleSet: 'jazz' })).length > 0, 'bad rule set rejected');
  const n = T.normalizeRecipe(r); ok(n.voices[1].chain[0].version === 1 && n.engine.version === T.ENGINE.version, 'normalised recipe states transform and engine versions');
  ok(n.harmony.weights.cadence === 1, 'harmony weight slots reserved');

  // lineage + ancestry preserved
  const rv = T.resolveVoices(r, th);
  eq(rv[2].lineage, ['theme', 'a', 'b', 'c'], 'lineage of derived-from-derived voice');
  eq(T.lineageTree(r).children[0].children[0].children[0].id, 'c', 'lineage tree nests a > b > c');
  // derived voice equals running the whole chain on the theme
  const direct = run(th, [ch('invert', { axis: 'tonic' }), ch('diminish', { p: 2, q: 1 })]);
  ok(same(rv[2].notes, direct.notes) && rv[2].length === direct.length, 'voice c = chain b then chain c on the theme');
  ok(JSON.stringify(th.notes) === JSON.stringify(T.extractTheme(parsed, { tracks: [3], bars: [10, 16] }).notes), 'theme still identical after resolving voices');

  // assembly shape
  const arr = T.assemble(r, th);
  eq(arr.tracks.length, 3, 'three tracks'); ok(arr.ppq === 480 && arr.format === 1, 'ppq and format');
  const t1 = arr.tracks[1];
  ok(t1.channel === 5 && t1.notes.every(n => n.channel === 5), 'recipe channel 6 -> parser channel 5');
  ok(t1.notes[0].startTick >= 2 * 1920, 'entryBar 3 offsets the voice by two bars');
  ok(t1.controllers[7][0].value === 100 && t1.program === 24, 'volume CC7 and program carried');
  ['index','name','channel','channelsSeen','program','notes','noteCount','controllers','lengthTicks'].forEach(k => ok(k in t1, 'track has parser field ' + k));
  ok(arr.timeSigEvents[0].num === 4 && arr.tempoEvents[0].usPerQuarter === 472440, 'tempo and meter carried');
  const off = JSON.parse(JSON.stringify(r)); off.voices[2].enabled = false; ok(T.assemble(off, th).tracks.length === 2, 'disabled voice is left out');

  // determinism
  ok(JSON.stringify(T.assemble(r, th)) === JSON.stringify(T.assemble(JSON.parse(JSON.stringify(r)), T.extractTheme(parsed, { tracks: [3], bars: [10, 16] }))), 'assemble is deterministic');
  const shuffled = { voices: r.voices, seed: r.seed, key: r.key, source: { bars: [10, 16], tracks: [3], sha256: r.source.sha256, file: 'badwater.mid' } };
  ok(T.recipeDigest(r) === T.recipeDigest(shuffled), 'recipe digest ignores key order');
  const r2 = JSON.parse(JSON.stringify(r)); r2.seed = 1730; ok(T.recipeDigest(r) !== T.recipeDigest(r2), 'digest changes with the seed');
  const a = T.mulberry32(1729), b = T.mulberry32(1729); ok(a() === b() && a() === b(), 'seeded PRNG repeats');

  // canon preset
  const canon = T.makeCanon({ voices: 2, offsetBars: 2, steps: -4, program: 24, firstChannel: 6 });
  const cr = Object.assign({}, base, { voices: [{ id: 'lead', name: 'Lead', source: 'theme', entryBar: 1, program: 24, channel: 5 }].concat(canon) });
  eq(T.validateRecipe(cr), [], 'canon preset validates'); eq(T.assemble(cr, th).tracks.length, 3, 'three-voice canon assembles');
  const ct = T.assemble(cr, th).tracks; ok(ct[1].notes[0].startTick === ct[0].notes[0].startTick + 2 * 1920 && ct[2].notes[0].startTick === ct[0].notes[0].startTick + 4 * 1920, 'canon entries two bars apart');
  const ki = T.keyInfo(KEY); ok(T.toDegree(ct[1].notes[0].pitch, ki).abs - T.toDegree(ct[0].notes[0].pitch, ki).abs === -4, 'canon follower is 4 scale steps below'); }

done();
