/* ==========================================================================
 * mccf_notation.js — read-only staff notation for the Theme Workshop (checkpoint 1b-ii)
 * --------------------------------------------------------------------------
 * Two layers:
 *   1. CONVERSION (pure, no DOM, no VexFlow): parser-shaped data -> a score model
 *        - bars from the file's time signature (4/4 if none)
 *        - note spelling chosen from the KEY (MIDI does not distinguish C# from Db)
 *        - accidentals tracked per bar, naturals where needed
 *        - durations split into legal note values, with ties across beats and barlines
 *        - overlapping notes separated into voices on the same staff
 *        - clef chosen by range; drums on a percussion staff
 *   2. DRAWING: draw(VexFlow, element, score, opts) — stacked staves, a window of bars at a time,
 *      and cursorAt(layout, tick) so a playback cursor can follow the clock.
 * Notation is an ANALYSIS AID.  Unquantized (live-played) notes are snapped to a 16th grid and the
 * count of notes moved is reported; swing/triplet feel is detected and reported, not notated.
 * Exposes MccfNotation (window global, and module.exports under Node).
 * ========================================================================== */
(function (root) {
'use strict';

var LETTERS = ['c', 'd', 'e', 'f', 'g', 'a', 'b'];
var LETTER_PC = { c: 0, d: 2, e: 4, f: 5, g: 7, a: 9, b: 11 };
var SHARP_ORDER = ['f', 'c', 'g', 'd', 'a', 'e', 'b'], FLAT_ORDER = ['b', 'e', 'a', 'd', 'g', 'c', 'f'];
var SHARPS_BY_MAJOR_PC = { 0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5 };
var MAJOR_SHARP = ['C', 'G', 'D', 'A', 'E', 'B', 'F#', 'C#'], MAJOR_FLAT = ['C', 'F', 'Bb', 'Eb', 'Ab', 'Db', 'Gb', 'Cb'];
// the relative major of each mode, as semitones above its tonic (a mode shares its relative major's key signature)
var MODE_OFFSET = { major: 0, minor: 3, 'harmonic-minor': 3, 'melodic-minor': 3, dorian: 10, phrygian: 8, lydian: 7, mixolydian: 5,
                    locrian: 1, pentatonic: 0, 'pentatonic-minor': 3, hexatonic: 0 };
var MINORISH = { minor: 1, 'harmonic-minor': 1, 'melodic-minor': 1, 'pentatonic-minor': 1, dorian: 1, phrygian: 1, locrian: 1 };
var PCNAMES = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };

function tonicToPc(t) {
  if (typeof t === 'number') return ((t % 12) + 12) % 12;
  var m = /^([A-Ga-g])([#b]?)$/.exec(String(t).trim()); if (!m) throw new Error('Unknown tonic: ' + t);
  return (((PCNAMES[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0)) % 12) + 12) % 12;
}

// ---------------------------------------------------------------------------
// Key signature and spelling
// ---------------------------------------------------------------------------
function keyInfo(key) {
  var tpc = tonicToPc(key.tonic), scale = key.scale || 'major';
  var off = MODE_OFFSET[scale] === undefined ? 0 : MODE_OFFSET[scale];
  var sharps = SHARPS_BY_MAJOR_PC[(tpc + off) % 12], sigAlt = {}, i;
  if (sharps > 0) for (i = 0; i < sharps; i++) sigAlt[SHARP_ORDER[i]] = 1;
  else for (i = 0; i < -sharps; i++) sigAlt[FLAT_ORDER[i]] = -1;
  var ki = { tonicPc: tpc, scale: scale, sharps: sharps, sigAlt: sigAlt,
             vexKey: sharps >= 0 ? MAJOR_SHARP[sharps] : MAJOR_FLAT[-sharps], minorish: !!MINORISH[scale] };
  // the letter the tonic is written with, so the leading tone can be spelled as a raised seventh
  var tl = null;
  LETTERS.forEach(function (l) { if (((LETTER_PC[l] + (sigAlt[l] || 0)) + 12) % 12 === tpc) tl = l; });
  if (!tl) LETTERS.forEach(function (l) { if (LETTER_PC[l] === tpc) tl = l; });
  if (!tl) LETTERS.forEach(function (l) { if (LETTER_PC[l] === (tpc + (sharps >= 0 ? 11 : 1)) % 12) tl = l; });
  ki.leadLetter = LETTERS[(LETTERS.indexOf(tl || 'c') + 6) % 7];
  return ki;
}

// pitch -> {letter, alt (-1,0,+1), oct, key ('c#/5')}
function spellPitch(p, ki) {
  var pc = ((p % 12) + 12) % 12, letter = null, alt = 0, i;
  for (i = 0; i < 7 && letter === null; i++) {                       // 1. a note of the key signature's own scale
    var l = LETTERS[i], a = ki.sigAlt[l] || 0;
    if (((LETTER_PC[l] + a) + 12) % 12 === pc) { letter = l; alt = a; }
  }
  if (letter === null && pc === (ki.tonicPc + 11) % 12) {            // 2. the leading tone: a raised seventh (C# in D minor)
    var la = ((pc - LETTER_PC[ki.leadLetter] + 18) % 12) - 6;
    if (Math.abs(la) <= 1) { letter = ki.leadLetter; alt = la; }
  }
  if (letter === null) {
    for (i = 0; i < 7 && letter === null; i++) if (LETTER_PC[LETTERS[i]] === pc) { letter = LETTERS[i]; alt = 0; }   // 3. a natural
  }
  if (letter === null) {                                             // 4. a black key: sharps in sharp keys, flats in flat keys
    if (ki.sharps >= 0) { letter = LETTERS[LETTERS.map(function (x) { return LETTER_PC[x]; }).indexOf(pc - 1)]; alt = 1; }
    else { letter = LETTERS[LETTERS.map(function (x) { return LETTER_PC[x]; }).indexOf(pc + 1)]; alt = -1; }
  }
  var oct = Math.floor((p - alt) / 12) - 1;
  return { letter: letter, alt: alt, oct: oct, key: letter + (alt === 1 ? '#' : alt === -1 ? 'b' : '') + '/' + oct };
}

// ---------------------------------------------------------------------------
// Durations.  Unit = a sixteenth note (ppq/4 ticks).
// ---------------------------------------------------------------------------
var VALUES = [[16, 'w', 0], [12, 'h', 1], [8, 'h', 0], [6, 'q', 1], [4, 'q', 0], [3, '8', 1], [2, '8', 0], [1, '16', 0]];
function allowedAt(c, pos, L) {
  if (c === 16) return pos === 0 && L >= 16;
  if (c === 12 || c === 8) return pos % 4 === 0;
  if (c === 6 || c === 3) return pos % 2 === 0;
  return true;
}
// split `len` units starting at `pos` (inside a bar of L units) into legal note values: [{s, units, dur, dots}]
function splitUnits(pos, len, L) {
  var out = [];
  while (len > 0) {
    var take = null;
    for (var i = 0; i < VALUES.length && !take; i++) if (VALUES[i][0] <= len && allowedAt(VALUES[i][0], pos, L)) take = VALUES[i];
    out.push({ s: pos, units: take[0], dur: take[1], dots: take[2] }); pos += take[0]; len -= take[0];
  }
  return out;
}

// ---------------------------------------------------------------------------
// Clef
// ---------------------------------------------------------------------------
function chooseClef(notes) {
  if (!notes.length) return 'treble';
  var ps = notes.map(function (n) { return n.pitch; }).sort(function (a, b) { return a - b; });
  return ps[Math.floor(ps.length / 2)] >= 58 ? 'treble' : 'bass';
}

// ---------------------------------------------------------------------------
// Drums: General MIDI pitch -> staff position and notehead ('x2' = x notehead), and which voice (hands up, feet down)
// ---------------------------------------------------------------------------
var DRUM_KEYS = { 35: 'f/4', 36: 'f/4', 37: 'c/5/x2', 38: 'c/5', 39: 'c/5/x2', 40: 'c/5', 41: 'g/4', 42: 'g/5/x2', 43: 'g/4', 44: 'd/4/x2',
                  45: 'a/4', 46: 'g/5/x2', 47: 'd/5', 48: 'd/5', 49: 'a/5/x2', 50: 'e/5', 51: 'f/5/x2', 52: 'a/5/x2', 53: 'f/5/x2', 55: 'a/5/x2', 57: 'a/5/x2', 59: 'f/5/x2' };
function drumKey(p) { return DRUM_KEYS[p] || 'g/5/x2'; }
function isFoot(p) { return p === 35 || p === 36 || p === 44; }

// ---------------------------------------------------------------------------
// One staff, one bar at a time
// ---------------------------------------------------------------------------
// qnotes: [{pitch, qs, qe, tieNext?...}] quantized to units; opts {L (units per bar), bar, drums, ki, u, ppq}
function buildMeasure(qnotes, bar, o) {
  var L = o.L, uStart = (bar - 1) * L, segs = [], i;
  qnotes.forEach(function (n) {
    if (n.qs < uStart + L && n.qe > uStart) {
      segs.push({ pitch: n.pitch, s: Math.max(n.qs, uStart) - uStart, e: Math.min(n.qe, uStart + L) - uStart, tieNext: n.qe > uStart + L, tiePrev: n.qs < uStart });
    }
  });
  // chords: the same start and end.  Drums are different: a hit's real length means nothing, so hits sharing a
  // start (in the same voice) form a chord that lasts until the next hit in that voice, at most one beat.
  var chordMap = {}, chords = [];
  segs.forEach(function (g) {
    var foot = !!(o.drums && isFoot(g.pitch)), k = o.drums ? (foot ? 'F' : 'H') + g.s : g.s + ':' + g.e, c = chordMap[k];
    if (!c) { c = chordMap[k] = { s: g.s, e: g.e, notes: [], foot: foot }; chords.push(c); }
    c.notes.push(g);
  });
  if (o.drums) ['F', 'H'].forEach(function (vk) {
    var mine = chords.filter(function (c) { return (vk === 'F') === c.foot; }).sort(function (a, b) { return a.s - b.s; });
    mine.forEach(function (c, i) {
      c.e = Math.max(c.s + 1, Math.min(i + 1 < mine.length ? mine[i + 1].s : L, c.s + 4, L));
      c.notes.forEach(function (n) { n.tieNext = false; n.tiePrev = false; });
    });
  });
  chords.forEach(function (c) { c.notes.sort(function (a, b) { return a.pitch - b.pitch; }); c.top = c.notes[c.notes.length - 1].pitch; });
  // voices
  var voices = [], dropped = 0;
  chords.sort(function (a, b) { return (a.s - b.s) || (b.top - a.top); });
  if (o.drums) {
    voices = [{ chords: [], last: 0 }, { chords: [], last: 0 }];
    chords.forEach(function (c) { var v = voices[c.foot ? 1 : 0]; if (c.s < v.last) { dropped += c.notes.length; return; } v.chords.push(c); v.last = c.e; });
    voices = voices.filter(function (v) { return v.chords.length; });
  } else {
    chords.forEach(function (c) {
      var v = null; for (i = 0; i < voices.length && !v; i++) if (voices[i].last <= c.s) v = voices[i];
      if (!v) { if (voices.length < 4) { v = { chords: [], last: 0 }; voices.push(v); } else { dropped += c.notes.length; return; } }
      v.chords.push(c); v.last = c.e;
    });
  }
  // events per voice: notes (split into legal values, tied) and rests in the gaps
  var out = [];
  function rests(from, to, list) {
    if (to <= from) return;
    if (from === 0 && to === L && L === 16) { list.push({ rest: true, dur: 'w', dots: 0, s: 0, units: 16, whole: true }); return; }
    splitUnits(from, to - from, L).forEach(function (p) { list.push({ rest: true, dur: p.dur, dots: p.dots, s: p.s, units: p.units }); });
  }
  voices.forEach(function (v) {
    var ev = [], cur = 0;
    v.chords.forEach(function (c) {
      rests(cur, c.s, ev);
      var pieces = splitUnits(c.s, c.e - c.s, L);
      pieces.forEach(function (p, pi) {
        var last = pi === pieces.length - 1;
        ev.push({ rest: false, dur: p.dur, dots: p.dots, s: p.s, units: p.units, pitches: c.notes.map(function (n) { return n.pitch; }),
                  tieNext: c.notes.map(function (n) { return last ? n.tieNext : true; }), tiePrev: c.notes.map(function (n) { return pi === 0 ? n.tiePrev : true; }) });
      });
      cur = c.e;
    });
    rests(cur, L, ev); out.push({ events: ev });
  });
  if (!out.length) { var e0 = []; rests(0, L, e0); out.push({ events: e0 }); }
  // spelling and accidentals, in time order across the voices of this staff
  var state = {}, order = [];
  out.forEach(function (v, vi) { v.events.forEach(function (e) { if (!e.rest) order.push([e.s, vi, e]); }); });
  order.sort(function (a, b) { return (a[0] - b[0]) || (a[1] - b[1]); });
  order.forEach(function (x) {
    var e = x[2]; e.keys = []; e.acc = [];
    e.pitches.forEach(function (p, k) {
      if (o.drums) { e.keys.push(drumKey(p)); e.acc.push(null); return; }
      var sp = spellPitch(p, o.ki), id = sp.letter + sp.oct, shown = state[id] !== undefined ? state[id] : (o.ki.sigAlt[sp.letter] || 0);
      e.keys.push(sp.key);
      if (e.tiePrev[k]) { e.acc.push(null); return; }                     // a tied continuation needs no accidental
      if (sp.alt !== shown) { e.acc.push(sp.alt === 1 ? '#' : sp.alt === -1 ? 'b' : 'n'); state[id] = sp.alt; } else e.acc.push(null);
    });
  });
  out.forEach(function (v) { v.events.forEach(function (e) { e.tick = ((bar - 1) * L + e.s) * o.u; }); });
  return { bar: bar, units: L, voices: out, dropped: dropped, empty: !segs.length };
}

// notes -> units, with a count of how many had to move
// opts.straighten: write a swing feel as straight eighths (an off-beat about 2/3 of the way through a beat moves to 1/2)
function quantize(notes, u, opts) {
  var ppq = u * 4, straighten = !!(opts && opts.straighten), moved = 0, trip = 0;
  function remap(t) { if (!straighten) return t; var b = Math.floor(t / ppq), f = (t - b * ppq) / ppq; return (f >= 0.55 && f < 0.8) ? (b + 0.5) * ppq : t; }
  var q = notes.map(function (n) {
    var st = remap(n.startTick), en = remap(n.startTick + n.durTicks);
    var qs = Math.round(st / u), qe = Math.max(qs + 1, Math.round(en / u));
    var raw = Math.abs(n.startTick - Math.round(n.startTick / u) * u);          // triplet feel is judged on the RAW onsets
    if (raw > u * 0.25) { var t3 = ppq / 3, dt = Math.abs(n.startTick / t3 - Math.round(n.startTick / t3)) * t3; if (dt < u * 0.12) trip++; }
    if (Math.abs(st - qs * u) > u * 0.25) moved++;
    else if (Math.abs(en - qe * u) > u * 0.5) moved++;
    return { pitch: n.pitch, qs: qs, qe: qe };
  });
  return { notes: q, moved: moved, tripletish: trip };
}

// ---------------------------------------------------------------------------
// The whole score for a window of bars
// ---------------------------------------------------------------------------
function meterOf(data) {
  var s = (data.timeSigEvents && data.timeSigEvents[0]) || { num: 4, den: 4 };
  return { num: s.num, den: s.den, barTicks: Math.round(data.ppq * 4 * s.num / s.den) };
}
function totalBarsOf(data) {
  var m = meterOf(data); return Math.max(1, Math.ceil(data.tracks.reduce(function (x, t) { return Math.max(x, t.lengthTicks || 0); }, 0) / m.barTicks));
}
function isDrumTrack(t) { return !!(t.channelsSeen && t.channelsSeen.indexOf(9) >= 0); }

// opts: {fromBar, bars, key {tonic, scale}, tracks: [index...] (default: every track with notes)}
function buildScore(data, opts) {
  var m = meterOf(data), u = data.ppq / 4, L = Math.round(m.barTicks / u), total = totalBarsOf(data);
  var from = Math.max(1, Math.min(opts.fromBar || 1, total)), to = Math.min(total, from + Math.max(1, opts.bars || 4) - 1);
  var ki = keyInfo(opts.key || { tonic: 'C', scale: 'major' });
  var t0 = (from - 1) * m.barTicks, t1 = to * m.barTicks, staves = [], moved = 0, trip = 0, drop = 0, notes = 0, swung = 0;
  var want = opts.tracks || data.tracks.filter(function (t) { return t.noteCount; }).map(function (t) { return t.index; });
  want.forEach(function (ti) {
    var tr = data.tracks[ti]; if (!tr) return;
    if (!tr.noteCount && !(opts.tracks && !data.tracks.some(function (t) { return t.noteCount; }))) return;   // a score with no notes at all (video bars): the staff asked for is drawn empty
    var inWin = tr.notes.filter(function (n) { return n.startTick < t1 && n.startTick + n.durTicks > t0; });
    var drums = isDrumTrack(tr), q = quantize(inWin, u), ms = [], feel = q.tripletish >= 2 && q.tripletish / inWin.length > 0.12;   // a few swung notes in a sparse part still count
    if (feel && opts.straightenSwing !== false) q = Object.assign(quantize(inWin, u, { straighten: true }), { tripletish: q.tripletish });
    if (feel) swung++;
    for (var b = from; b <= to; b++) ms.push(buildMeasure(q.notes, b, { L: L, drums: drums, ki: ki, u: u, ppq: data.ppq }));
    moved += q.moved; trip += q.tripletish; notes += inWin.length; ms.forEach(function (x) { drop += x.dropped; });
    staves.push({ track: ti, name: tr.name, kind: drums ? 'drums' : 'pitched', clef: drums ? 'percussion' : chooseClef(tr.notes), measures: ms,
                  hasNotes: ms.some(function (x) { return !x.empty; }) });
  });
  return { fromBar: from, toBar: to, totalBars: total, meter: m, unitsPerBar: L, key: ki, staves: staves,
           stats: { notes: notes, moved: moved, dropped: drop, tripletFeel: swung > 0, swungStaves: swung, straightened: swung > 0 && opts.straightenSwing !== false } };
}

// ---------------------------------------------------------------------------
// Drawing (VexFlow 4.x).  VF = Vex.Flow.  Returns a layout for the cursor.
// ---------------------------------------------------------------------------
function draw(VF, el, score, opts) {
  opts = opts || {};
  var W = opts.width || 900, per = Math.max(1, Math.min(opts.perSystem || 4, score.toBar - score.fromBar + 1));
  var LEFT = 8, LABEL_W = 74, RIGHT = 12, STAFF_H = opts.staffHeight || 118, TOP = 34, GAP = 26;
  var staves = score.staves, nBars = score.toBar - score.fromBar + 1, nSys = Math.ceil(nBars / per);
  var sysH = staves.length * STAFF_H + GAP, H = TOP + nSys * sysH + 16;
  el.innerHTML = '';
  var renderer = new VF.Renderer(el, VF.Renderer.Backends.SVG); renderer.resize(W, H);
  var ctx = renderer.getContext(); ctx.setFont('Arial', 11, '');
  var layout = { width: W, height: H, systems: [], perSystem: per };
  var sig = Math.abs(score.key.sharps), clefW = 40, keyW = 11 * sig + (sig ? 8 : 0), timeW = 30;
  var num = score.meter.num, den = score.meter.den, ties = [];

  for (var s = 0; s < nSys; s++) {
    var barsHere = []; for (var b = s * per; b < Math.min(nBars, (s + 1) * per); b++) barsHere.push(score.fromBar + b);
    var y0 = TOP + s * sysH, firstExtra = clefW + keyW + (s === 0 ? timeW : 0);
    var avail = W - LEFT - LABEL_W - RIGHT, mw = (avail - firstExtra) / per;   // equal measure widths; the first carries the clef and key
    var sys = { index: s, y0: y0 - 14, y1: y0 + staves.length * STAFF_H - 18, bars: [] }; layout.systems.push(sys);
    var open = {};   // pitch key -> {note, idx}: ties begun in this system
    var x = LEFT + LABEL_W, prevStaves = null;
    barsHere.forEach(function (bar, j) {
      var w = mw + (j === 0 ? firstExtra : 0), col = [];
      // a stave per track for this column
      staves.forEach(function (st, k) {
        var stave = new VF.Stave(x, y0 + k * STAFF_H, w);
        if (j === 0) { stave.addClef(st.clef); if (st.kind === 'pitched') stave.addKeySignature(score.key.vexKey); if (s === 0) stave.addTimeSignature(num + '/' + den); }
        if (k === 0 && j === 0) stave.setMeasure(bar);
        if (bar === score.totalBars) stave.setEndBarType(VF.Barline.type.END);
        col.push(stave);
      });
      var startX = 0; col.forEach(function (sv) { startX = Math.max(startX, sv.getNoteStartX()); }); col.forEach(function (sv) { sv.setNoteStartX(startX); sv.setContext(ctx).draw(); });
      // notes: every voice of every staff, formatted together so equal ticks line up across the staves
      var allVoices = [], beams = [], perStaff = [], anchors = [], staffAnchors = staves.map(function () { return []; });
      staves.forEach(function (st, k) {
        var m = st.measures[bar - score.fromBar], multi = m.voices.length > 1, vlist = [];
        m.voices.forEach(function (v, vi) {
          var tick = [], notes = v.events.map(function (e) {
            var rest = e.rest, keys = rest ? [(st.clef === 'bass' ? 'd/3' : 'b/4')] : e.keys;
            var n = new VF.StaveNote({ keys: keys, duration: e.dur + (rest ? 'r' : ''), clef: st.clef === 'percussion' ? 'percussion' : st.clef,
                                       auto_stem: !multi || rest ? true : false, stem_direction: multi ? (vi === 0 ? 1 : -1) : undefined });
            if (e.whole) n.setCenterAlignment && n.setCenterAlignment(false);
            if (e.dots) VF.Dot.buildAndAttach([n], { all: true });
            if (!rest) e.acc.forEach(function (a, i) { if (a) n.addModifier(new VF.Accidental(a), i); });
            n._ev = e; return n;
          });
          var voice = new VF.Voice({ num_beats: num, beat_value: den }).setMode(VF.Voice.Mode.SOFT); voice.addTickables(notes);
          allVoices.push(voice); vlist.push({ voice: voice, notes: notes });
          try { VF.Beam.generateBeams(notes, { maintain_stem_directions: multi }).forEach(function (bm) { beams.push(bm); }); } catch (err) { /* beaming is cosmetic */ }
        });
        perStaff.push({ stave: col[k], vlist: vlist, st: st });
      });
      if (allVoices.length) {
        var f = new VF.Formatter(); perStaff.forEach(function (ps) { if (ps.vlist.length) f.joinVoices(ps.vlist.map(function (v) { return v.voice; })); });
        f.format(allVoices, Math.max(40, w - (startX - x) - 14));
      }
      perStaff.forEach(function (ps, k) {
        ps.vlist.forEach(function (v) { v.voice.draw(ctx, ps.stave); });
        // ties: a note with tieNext waits for the next note of the same pitch with tiePrev
        ps.vlist.forEach(function (v) { v.notes.forEach(function (n) {
          var e = n._ev; if (e.rest) return;
          e.keys.forEach(function (key, i) {
            var id = k + '|' + key;
            if (e.tiePrev[i]) { var o = open[id]; ties.push(new VF.StaveTie({ first_note: o ? o.note : null, last_note: n, first_indices: [o ? o.idx : i], last_indices: [i] })); delete open[id]; }
            if (e.tieNext[i]) open[id] = { note: n, idx: i };
          });
          staffAnchors[k].push({ tick: e.tick, x: n.getAbsoluteX() });
          if (k === 0) anchors.push({ tick: e.tick, x: n.getAbsoluteX() });
        }); });
      });
      beams.forEach(function (bm) { bm.setContext(ctx).draw(); });
      if (j === 0 && staves.length > 1) {
        new VF.StaveConnector(col[0], col[col.length - 1]).setType(VF.StaveConnector.type.SINGLE_LEFT).setContext(ctx).draw();
      }
      var t0 = (bar - 1) * score.meter.barTicks, t1 = bar * score.meter.barTicks;
      anchors.push({ tick: t0, x: startX }, { tick: t1, x: x + w });
      anchors.sort(function (a, b) { return (a.tick - b.tick) || (a.x - b.x); });
      var dedup = []; anchors.forEach(function (a) { if (!dedup.length || dedup[dedup.length - 1].tick !== a.tick) dedup.push(a); });
      sys.bars.push({ bar: bar, tick0: t0, tick1: t1, x0: x, x1: x + w, anchors: dedup, staffAnchors: staffAnchors });
      x += w;
    });
    Object.keys(open).forEach(function (id) { ties.push(new VF.StaveTie({ first_note: open[id].note, last_note: null, first_indices: [open[id].idx], last_indices: [open[id].idx] })); });
    ties.forEach(function (t) { try { t.setContext(ctx).draw(); } catch (err) { /* a tie to a note outside the window */ } }); ties = [];
    staves.forEach(function (st, k) { ctx.fillText(st.name.length > 11 ? st.name.slice(0, 10) + '…' : st.name, LEFT, y0 + k * STAFF_H + 52); });
  }
  return layout;
}

// where the cursor goes for a given tick: {x, y0, y1, system} or null when the tick is outside the drawn window
function cursorAt(layout, tick) {
  for (var s = 0; s < layout.systems.length; s++) {
    var sys = layout.systems[s];
    for (var b = 0; b < sys.bars.length; b++) {
      var bar = sys.bars[b];
      if (tick >= bar.tick0 && tick < bar.tick1) {
        var a = bar.anchors, i = 0; while (i + 1 < a.length && a[i + 1].tick <= tick) i++;
        var p = a[i], q = a[i + 1] || { tick: bar.tick1, x: bar.x1 }, f = q.tick === p.tick ? 0 : (tick - p.tick) / (q.tick - p.tick);
        return { x: p.x + (q.x - p.x) * f, y0: sys.y0, y1: sys.y1, system: s, bar: bar.bar };
      }
    }
  }
  return null;
}

var api = { keyInfo: keyInfo, spellPitch: spellPitch, splitUnits: splitUnits, chooseClef: chooseClef, quantize: quantize, buildMeasure: buildMeasure,
            buildScore: buildScore, meterOf: meterOf, totalBarsOf: totalBarsOf, draw: draw, cursorAt: cursorAt, drumKey: drumKey, isDrumTrack: isDrumTrack,
            VALUES: VALUES };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfNotation = api;
})(typeof window !== 'undefined' ? window : this);
