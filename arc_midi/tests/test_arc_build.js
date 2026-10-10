// Emotional arc -> controller lanes, through the whole chain: recipe, build, the MIDI file, and the live Player.
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const T = require('../static/js/mccf_theory.js'), M = require('../static/js/mccf_midi.js'), W = require('../static/js/mccf_smf_writer.js'), A = require('../static/js/mccf_arc.js');
const { group, ok, eq, done } = require('./harness.js');
const bb = fs.readFileSync(path.join(__dirname, '../fixtures/badwater.mid')), B = M.parseMidiFile(bb.buffer.slice(bb.byteOffset, bb.byteOffset + bb.byteLength));
const arcXml = fs.readFileSync(path.join(__dirname, '../fixtures/arc_Anna_2026-09-17.xml'), 'utf8'), ARC = A.parseArc(arcXml), PTS = ARC.cultivars[0].points;
const ab = (u) => u.buffer.slice(u.byteOffset, u.byteOffset + u.byteLength), sha = (u) => crypto.createHash('sha256').update(Buffer.from(u)).digest('hex');
const rec = (backing, extra) => Object.assign({ source: { file: 'badwater.mid', tracks: [3], bars: [10, 16] }, key: { tonic: 'A', scale: 'major' }, ruleSet: 'chorale-strict', seed: 1729, backing,
  voices: [{ id: 'lead', name: 'Theme', source: 'theme', entryBar: 1, program: 24, channel: 5, volume: 127 }, { id: 'f', name: 'Follower', source: 'theme', chain: [{ type: 'transpose', params: { steps: -2 } }], entryBar: 3, program: 24, channel: 6 },
           { id: 'd', name: 'Drums', kind: 'drums', seed: 3 }] }, extra || {});
const WIN = { enabled: false }, WHOLE = { enabled: true, leadInBars: 2, tailBars: 2, mode: 'whole' }, spec = () => A.defaultSpec();
const smf = (b) => W.writeSMF(b.arrangement, { name: 'Conductor' });
const laneMap = (b) => { const m = {}; b.arrangement.tracks.forEach((t, i) => { const c = Object.keys(t.controllers || {}).filter((k) => t.controllers[k].some((e) => e.lane)).map(Number); if (c.length) m[i + 1] = c; }); return m; };

group('a recipe WITHOUT an arc is exactly what it was before');
eq([T.recipeDigest(rec(WIN)).slice(0, 16), sha(smf(T.build(rec(WIN), B).bytes ? T.build(rec(WIN), B) : T.build(rec(WIN), B)).bytes).slice(0, 16)], ['9e7c41b995a0f8ce', '7bf6b9ba693294b7'], 'window recipe: same digest and same file bytes as the version before the arc existed');
eq([T.recipeDigest(rec(WHOLE)).slice(0, 16), sha(smf(T.build(rec(WHOLE), B)).bytes).slice(0, 16)], ['386e2dd1f1645be4', 'ef024e417d751c63'], 'whole-song recipe: the same');
ok(!('arc' in T.normalizeRecipe(rec(WIN))), 'the normalised recipe has no "arc" key'); eq(T.build(rec(WIN), B).arcLanes, [], 'and no lanes'); eq(T.build(rec(WIN), B).warnings.filter((w) => /arc/.test(w)), [], 'and no arc warnings');

group('the recipe’s arc block');
const withArc = (s) => rec(WIN, { arc: s || spec() });
eq(T.validateRecipe(withArc()), [], 'a recipe with the standard arc block is valid'); eq(Object.keys(T.normalizeRecipe(withArc()).arc), ['file', 'sha256', 'agent', 'enabled', 'span', 'interp', 'lanes'], 'normalised with a fixed key order');
{ const s = spec(); s.lanes[0].cc = 0; ok(T.validateRecipe(withArc(s)).some((e) => /controller/.test(e)), 'a bad controller number is a recipe error: ' + T.validateRecipe(withArc(s))[0]); let thrown = ''; try { T.build(withArc(s), B); } catch (e) { thrown = e.message; } ok(/Invalid recipe/.test(thrown), 'and build refuses it'); }
ok(T.recipeDigest(withArc()) !== T.recipeDigest(rec(WIN)), 'adding an arc changes the digest (it changes the music)'); eq(T.recipeDigest(withArc()), T.recipeDigest(withArc(JSON.parse(JSON.stringify(spec())))), 'the same arc block, the same digest'); { const s = spec(); s.lanes[0].hi = 100; ok(T.recipeDigest(withArc(s)) !== T.recipeDigest(withArc()), 'a different lane range, a different digest'); }

group('build: lanes land on the voices and nowhere else');
{ const b0 = T.build(withArc(), B); ok(b0.warnings.some((w) => /no arc is loaded/.test(w)), 'arc on but none loaded: a warning'); eq(b0.arcLanes, [], 'no lanes'); eq(Object.keys(laneMap(b0)), [], 'nothing written');
  const b = T.build(withArc(), B, { arc: { points: PTS, sha256: null } }), arr = b.arrangement; eq(b.warnings.filter((w) => /arc/.test(w)), [], 'with the arc loaded: no arc warnings');
  eq(b.arcLanes.map((l) => [l.curve, l.cc, l.tracks]), [['E', 11, 2], ['Coherence', 91, 2], ['P', 74, 2], ['B', 1, 2]], 'four lanes, each on the two pitched voices (not the drums)');
  const lead = arr.tracks.find((t) => t.voiceId === 'lead'), fol = arr.tracks.find((t) => t.voiceId === 'f'), dr = arr.tracks.find((t) => t.voiceId === 'd');
  [lead, fol].forEach((t) => { eq([1, 11, 74, 91].every((cc) => (t.controllers[cc] || []).some((e) => e.lane)), true, t.name + ' has CC 1, 11, 74, 91 lanes'); ok(t.controllers[11].every((e) => e.channel === t.channel), t.name + ': lane events are on its own channel (' + t.channel + ')'); eq(t.controllers[7], [{ tick: 0, value: t.controllers[7][0].value, channel: t.channel }], t.name + ': its volume (CC7) is untouched'); });
  eq(Object.keys(dr.controllers).sort(), ['7'], 'the drums have only their volume'); eq(lead.controllers[11][0].tick, 0, 'the lane starts at tick 0'); ok(lead.controllers[11][lead.controllers[11].length - 1].tick <= arr.lengthTicks, 'and ends inside the piece');
  eq(lead.controllers[11].length, f_count(PTS, arr), 'lane length = what the arc module computes for this piece'); }
function f_count(pts, arr) { return A.laneEvents(pts, A.DEFAULT_LANES[0], spec(), arr.lengthTicks, arr.ppq).length; }

group('whole-song backing: source tracks are left alone, the arc spans the whole piece');
{ const bw = T.build(rec(WHOLE, { arc: spec() }), B, { arc: { points: PTS } }), base = T.build(rec(WHOLE), B), arr = bw.arrangement;
  arr.tracks.filter((t) => t.sourceTrack !== undefined).forEach((t, i) => { const o = base.arrangement.tracks.filter((x) => x.sourceTrack !== undefined)[i]; eq(JSON.stringify(t.controllers), JSON.stringify(o.controllers), 'source track ' + t.sourceTrack + ' keeps exactly its own controllers'); });
  const lead = arr.tracks.find((t) => t.voiceId === 'lead'), last = lead.controllers[91][lead.controllers[91].length - 1]; ok(last.tick > arr.lengthTicks * 0.9, 'the slow coherence lane runs to the end of the WHOLE song (last change at ' + last.tick + ' of ' + arr.lengthTicks + ')'); }

group('switched off, or the wrong arc');
{ const off = spec(); off.enabled = false; eq(sha(smf(T.build(withArc(off), B, { arc: { points: PTS } })).bytes), sha(smf(T.build(rec(WIN), B)).bytes), 'an arc that is switched off gives the same file bytes as no arc at all');
  const s = spec(); s.sha256 = 'a'.repeat(64); ok(T.build(withArc(s), B, { arc: { points: PTS, sha256: 'b'.repeat(64) } }).warnings.some((w) => /not the file this recipe was made with/.test(w)), 'a different arc file from the one recorded: a warning'); eq(T.build(withArc(s), B, { arc: { points: PTS, sha256: 'a'.repeat(64) } }).warnings.filter((w) => /arc/.test(w)), [], 'the same file: none'); eq(T.build(withArc(s), B, { arc: { points: PTS } }).warnings.filter((w) => /SHA-256/.test(w)), [], 'no hash on the loaded side: nothing to compare, no warning'); }

group('the MIDI file');
{ const b = T.build(withArc(), B, { arc: { points: PTS } }), o1 = smf(b), o2 = smf(T.build(withArc(), B, { arc: { points: PTS } })); eq(sha(o1.bytes), sha(o2.bytes), 'deterministic: the same recipe and arc give the same bytes'); ok(sha(o1.bytes) !== sha(smf(T.build(rec(WIN), B)).bytes), 'and it differs from the no-arc file');
  const back = M.parseMidiFile(ab(o1.bytes)), lead = back.tracks.find((t) => t.name === 'Theme'), orig = b.arrangement.tracks.find((t) => t.voiceId === 'lead');
  eq(lead.controllers[11].map((e) => [e.tick, e.value]), orig.controllers[11].map((e) => [e.tick, e.value]), 're-read from the file: the CC11 lane is there, tick for tick and value for value'); ok(lead.controllers[11].every((e) => e.channel === 4), 'on MIDI channel 5 (index 4)');
  eq(lead.controllers[91].map((e) => e.value).slice(0, 1), [20], 'CC91 starts at 20 (the coherence lane’s low), not the voice’s old static value'); eq(lead.controllers[7][0].value, 127, 'the voice’s volume is still 127'); const dr = back.tracks.find((t) => t.name === 'Drums'); ok(!dr.controllers[11], 'no CC11 on the drums');
  const ccBytes = Array.from(o1.bytes).filter((x, i, a) => x === 0xB4 && a[i + 1] === 11).length; ok(ccBytes >= lead.controllers[11].length, 'the raw file holds the CC11 messages'); eq(o1.warnings.filter((w) => /controller|arc/i.test(w)), [], 'the writer has nothing to say'); }

group('live playback: the Player sends the lanes in time');
const clockOf = () => { const sent = [], out = { send: (m, ts) => sent.push([Array.from(m), ts]) }; let clock = 1000; const pl = new M.Player({ quiet: true, getMidiOutput: () => out, now: () => clock }); return { pl, sent, setClock: (v) => { clock = v; } }; };
{ const b = T.build(withArc(), B, { arc: { points: PTS } }), o = smf(b), lm = laneMap(b), { pl, sent } = clockOf(); pl.load(ab(o.bytes)); const cc = () => pl._events.filter((e) => e.kind === 'midi-cc');
  eq(cc().length, 0, 'before setLanes the Player schedules no controller events (as it always has: only notes)'); pl.setLanes(lm); pl.start(0); pl._pumpStop(); const evs = cc();
  eq(Object.keys(lm).length, 2, 'two tracks have lanes'); ok(evs.length > 100, 'now it schedules them (' + evs.length + ' controller events)');
  const per = {}; evs.forEach((e) => { per[e.ch + ':' + e.cc] = (per[e.ch + ':' + e.cc] || 0) + 1; }); eq(Object.keys(per).sort(), ['4:1', '4:11', '4:74', '4:91', '5:1', '5:11', '5:74', '5:91'], 'on channels 5 and 6 (index 4 and 5), CC 1, 11, 74, 91');
  const lead = pl.data.tracks.find((t) => t.name === 'Theme'); eq(per['4:11'], lead.controllers[11].length, 'every CC11 event of the lead is scheduled once');
  ok(evs.every((e, i) => true), ''); const seq = pl._events.map((e) => e.t); ok(seq.every((t, i) => i === 0 || t >= seq[i - 1]), 'the whole event list stays in time order');
  const firstNote = pl._events.find((e) => e.kind === 'midi-on'); ok(pl._events.indexOf(evs[0]) < pl._events.indexOf(firstNote), 'a controller due at the same moment as a note goes first'); eq(evs.filter((e) => e.t === 0 && e.cc === 11).length, 2, 'both voices get their starting CC11 at t = 0');
  pl.startWall = 5000; sent.length = 0; evs.slice(0, 3).forEach((e) => pl._dispatch(e)); ok(sent.every((m) => m[0].length === 3 && (m[0][0] & 0xF0) === 0xB0), 'dispatched as 3-byte control changes'); ok(sent.every((m) => m[1] === 5000 + evs[sent.indexOf(m)].t * 1000), 'each with its hardware timestamp'); pl.stop(); }
{ const b = T.build(withArc(), B, { arc: { points: PTS } }), { pl } = clockOf(); pl.load(ab(smf(b).bytes)); pl.setLanes(laneMap(b)); pl.start(0); pl._pumpStop(); const all = pl._events.filter((e) => e.kind === 'midi-cc').length; const total = pl._endSec; pl.stop();
  pl.start(total / 2); pl._pumpStop(); const mid = pl._events.filter((e) => e.kind === 'midi-cc'); ok(mid.length < all && mid.length > 8, 'starting half way: fewer events (' + mid.length + ' of ' + all + ')'); const chase = mid.filter((e) => e.t === 0); eq(chase.map((e) => e.cc).sort((a, b) => a - b).join(), '1,1,11,11,74,74,91,91', 'each lane first jumps to its value at that point (a chase), on both voices'); ok(mid.every((e) => e.t >= 0), 'nothing in the past'); pl.stop();
  pl.setTempoScale(2); pl.start(0); pl._pumpStop(); const e2 = pl._events.filter((e) => e.kind === 'midi-cc' && e.cc === 91 && e.ch === 4); pl.stop(); pl.setTempoScale(1); pl.start(0); pl._pumpStop(); const e1 = pl._events.filter((e) => e.kind === 'midi-cc' && e.cc === 91 && e.ch === 4); pl.stop(); ok(Math.abs(e2[e2.length - 1].t * 2 - e1[e1.length - 1].t) < 0.01, 'the tempo scale moves the lanes with the notes (twice as fast, half the time)');
  const lead = pl.data.tracks.find((t) => t.name === 'Theme'); pl.setEnabled(lead.index, false); pl.start(0); pl._pumpStop(); eq(pl._events.filter((e) => e.kind === 'midi-cc' && e.ch === 4).length, 0, 'a muted track sends no lane'); pl.stop(); pl.setEnabled(lead.index, true);
  pl.setChannel(lead.index, 9); pl.start(0); pl._pumpStop(); ok(pl._events.filter((e) => e.kind === 'midi-cc' && e.ch === 8).length > 0 && pl._events.filter((e) => e.kind === 'midi-cc' && e.ch === 4).length === 0, 'a channel override moves the lanes with the notes'); pl.stop(); pl.resetChannels();
  pl.setLanes({}); pl.start(0); pl._pumpStop(); eq(pl._events.filter((e) => e.kind === 'midi-cc').length, 0, 'setLanes({}) turns them off'); pl.stop(); pl.setLanes(laneMap(b)); pl.load(ab(smf(b).bytes)); pl.start(0); pl._pumpStop(); eq(pl._events.filter((e) => e.kind === 'midi-cc').length, 0, 'loading a new file forgets the lanes (the page sets them again)'); pl.stop();
  const pa = new M.Player({ quiet: true, getOutputMode: () => 'audio' }); pa.load(ab(smf(b).bytes)); pa.setLanes(laneMap(b)); pa.start(0); pa._pumpStop(); eq(pa._events.filter((e) => e.kind === 'midi-cc').length, 0, 'in the Web Audio fallback (no MIDI device) there are no controller events'); pa.stop(); }
{ const b = T.build(rec(WHOLE), B), { pl } = clockOf(); pl.load(ab(smf(b).bytes)); const srcCC = pl.data.tracks.some((t) => Object.keys(t.controllers || {}).some((k) => t.controllers[k].some((e) => e.tick > 0))); pl.start(0); pl._pumpStop(); eq(pl._events.filter((e) => e.kind === 'midi-cc').length, 0, 'a source file’s own mid-song controllers are still NOT newly played (' + (srcCC ? 'this file has some' : 'this file has none') + '): behaviour is unchanged'); pl.stop(); }
done();
