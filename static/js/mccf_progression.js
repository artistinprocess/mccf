// MCCF field progression -> Theme Workshop voices.
// Turns the progression harvested from the harmony engine (GET /neoriemannian/progression?format=json) into notes the Workshop
// can hold as hand-edited voices: a chord voice and a bass voice, in the theme's own ticks. Pure functions, no DOM; tested in Node.
(function (root) {
  'use strict';
  var NOTE_MIDI = { 'C': 60, 'C#': 61, 'D': 62, 'D#': 63, 'E': 64, 'F': 65, 'F#': 66, 'G': 67, 'G#': 68, 'A': 69, 'A#': 70, 'B': 71 };
  var TEMPLATES = { '': [0, 4, 7], 'm': [0, 3, 7], '7': [0, 4, 7, 10], 'maj7': [0, 4, 7, 11], 'm7': [0, 3, 7, 10], 'dim': [0, 3, 6], 'm7b5': [0, 3, 6, 10], 'aug': [0, 4, 8] };
  var PATTERNS = ['sustain', 'quarter', 'eighth', 'offbeat', 'arp'];

  function chordPitches(rootName, suffix) {
    var base = NOTE_MIDI[rootName], iv = TEMPLATES[suffix];
    if (base === undefined || !iv) return null;
    return iv.map(function (i) { return base + i; });
  }

  // [{start, len, notes}] for one chord of `beats` beats; beatTicks = ticks in one beat of the theme.
  function pulseHits(pattern, notes, beats, beatTicks) {
    var total = Math.max(1, Math.round(beats * beatTicks)), out = [], t, k;
    if (pattern === 'quarter') { for (t = 0; t < total; t += beatTicks) out.push({ start: t, len: Math.max(1, Math.min(Math.round(beatTicks * 0.9), total - t)), notes: notes.slice() }); }
    else if (pattern === 'eighth') { var h = Math.max(1, Math.round(beatTicks / 2)); for (t = 0; t < total; t += h) out.push({ start: t, len: Math.max(1, Math.min(Math.round(beatTicks * 0.45), total - t)), notes: notes.slice() }); }
    else if (pattern === 'offbeat') { var o = Math.round(beatTicks / 2); for (t = o; t < total; t += beatTicks) out.push({ start: t, len: Math.max(1, Math.min(Math.round(beatTicks * 0.45), total - t)), notes: notes.slice() }); }
    else if (pattern === 'arp') { var e = Math.max(1, Math.round(beatTicks / 2)); for (t = 0, k = 0; t < total; t += e, k++) out.push({ start: t, len: Math.max(1, Math.min(Math.round(beatTicks * 0.45), total - t)), notes: [notes[k % notes.length]] }); }
    if (!out.length) out.push({ start: 0, len: total, notes: notes.slice() });          // sustain, or anything unrecognised: one held block
    if (pattern === 'sustain' || PATTERNS.indexOf(pattern) < 0) return [{ start: 0, len: total, notes: notes.slice() }];
    return out;
  }

  // progression: the JSON from the server ({progression:[{root,suffix,seconds,chord}], config:{bpm,pulse}}).
  // opts: {beatTicks (required), bpm, pulse, minBeats (default 1), quantum (default 0.5 beat)}
  // Returns {chords:[{p,s,d,v}], bass:[{p,s,d,v}], totalTicks, runs, skipped}.
  function toVoices(progression, opts) {
    var cfg = (progression && progression.config) || {}, runs = (progression && progression.progression) || [];
    var beatTicks = opts.beatTicks, bpm = opts.bpm || cfg.bpm || 60, pulse = opts.pulse || cfg.pulse || 'sustain';
    var minBeats = opts.minBeats === undefined ? 1 : opts.minBeats, quantum = opts.quantum || 0.5;
    var chords = [], bass = [], t0 = 0, used = 0, skipped = 0, prevVo = null, inv = opts.inversion || 'root', spc = opts.spacing || 'close', follow = opts.bassFollows !== false;
    runs.forEach(function (r) {
      var pitches = r.root ? chordPitches(r.root, r.suffix || '') : null;
      if (!pitches) { skipped++; return; }
      var beats = Math.max(minBeats, Math.round((r.seconds * bpm / 60) / quantum) * quantum);
      var vo = voicing(pitches, inv, spc, prevVo); prevVo = vo;
      hitsFor(pulse, vo, beats, beatTicks).forEach(function (h, i) {
        h.notes.forEach(function (p) { chords.push({ p: p, s: t0 + h.start, d: h.len, v: h.start === 0 ? 84 : 72 }); });
      });
      var rootLow = (follow && inv !== 'root') ? placeLow(vo[0]) : NOTE_MIDI[r.root] - 24;   // the root two octaves down (C2..B2); in an inversion, the chord's lowest note
      var bassHits = (pulse === 'quarter' || pulse === 'eighth') ? pulseHits('quarter', [rootLow], beats, beatTicks) : [{ start: 0, len: Math.max(1, Math.round(beats * beatTicks)), notes: [rootLow] }];
      bassHits.forEach(function (h) { bass.push({ p: rootLow, s: t0 + h.start, d: h.len, v: h.start === 0 ? 92 : 80 }); });
      t0 += Math.max(1, Math.round(beats * beatTicks)); used++;
    });
    return { chords: chords, bass: bass, totalTicks: t0, runs: used, skipped: skipped };
  }
  function hitsFor(pattern, notes, beats, beatTicks) { return pulseHits(pattern, notes, beats, beatTicks); }


  // ---------- inversions and open voicings ----------
  var INV_INDEX = { root: 0, first: 1, second: 2, third: 3 };
  function placeLow(p) { return 36 + (((p - 36) % 12) + 12) % 12; }                    // pitch class into C2..B2
  function rotate(ps, k) { var a = ps.slice().sort(function (x, y) { return x - y; }); for (var i = 0; i < k; i++) a.push(a.shift() + 12); return a; }
  function fit(a) { a = a.slice(); while (a[a.length - 1] > 79) a = a.map(function (x) { return x - 12; }); while (a[0] < 48) a = a.map(function (x) { return x + 12; }); return a; }
  function cost(a, b) { var n = Math.min(a.length, b.length), c = 0, i; for (i = 0; i < n; i++) c += Math.abs(a[a.length - 1 - i] - b[b.length - 1 - i]); return c; }
  // ps: root-position pitches (ascending); inversion: root|first|second|third|smooth; spacing: close|open; prev: the previous voicing (for smooth).
  // 'smooth' picks the inversion and octave nearest the previous chord (least movement). 'open' spreads the chord: a triad's middle note goes up
  // an octave (root-fifth-third), a four-note chord drops its second-highest note an octave (drop-2).
  function voicing(ps, inversion, spacing, prev) {
    var n = ps.length, best = null, k, sh, c, cand;
    if (inversion === 'smooth' && prev) {
      for (k = 0; k < n; k++) for (sh = -12; sh <= 12; sh += 12) {
        cand = rotate(ps, k).map(function (x) { return x + sh; });
        if (cand[cand.length - 1] > 79 || cand[0] < 48) continue;
        c = cost(cand, prev.close || prev); if (best === null || c < best.c) best = { c: c, v: cand };
      }
      cand = best ? best.v : fit(rotate(ps, 0));
    } else cand = fit(rotate(ps, Math.min(INV_INDEX[inversion] || 0, n - 1)));
    var close = cand.slice();
    if (spacing === 'open') {
      if (n === 3) cand = [cand[0], cand[2], cand[1] + 12];
      else if (n >= 4) { var d = cand.slice(); d[n - 2] -= 12; cand = d; }
      cand.sort(function (x, y) { return x - y; }); while (cand[0] < 43) cand = cand.map(function (x) { return x + 12; });
    }
    cand.close = close;                                                                  // kept so smooth voice-leading compares like with like
    return cand;
  }

  // ---------- a theme from the progression: chord tones, passing notes, accidentals, up to twelve-tone ----------
  var SCALES = { '': [0, 2, 4, 5, 7, 9, 11], 'maj7': [0, 2, 4, 5, 7, 9, 11], '7': [0, 2, 4, 5, 7, 9, 10], 'm': [0, 2, 3, 5, 7, 9, 10], 'm7': [0, 2, 3, 5, 7, 9, 10], 'dim': [0, 2, 3, 5, 6, 8, 9, 11], 'm7b5': [0, 1, 3, 5, 6, 8, 10], 'aug': [0, 2, 4, 6, 8, 10] };
  function mulberry(seed) { var a = (seed >>> 0) || 1; return function () { a |= 0; a = a + 0x6D2B79F5 | 0; var t = Math.imul(a ^ a >>> 15, 1 | a); t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
  function pcOf(p) { return ((p % 12) + 12) % 12; }
  function nearestPc(pc, ref, lo, hi) { var best = null, bd = 1e9, p; for (p = lo; p <= hi; p++) if (pcOf(p) === pc) { var d = Math.abs(p - ref); if (d < bd) { bd = d; best = p; } } return best === null ? ref : best; }
  // opts: {beatTicks, chromatic 0..1, seed, rhythm 'quarter'|'eighth'|'mixed', lo, hi, bpm, quantum, minBeats}
  // chromatic 0: chord tones on the beat, diatonic passing/neighbour notes from the chord's own scale. Rising: more colour tones, then chromatic passing notes,
  // appoggiaturas and half-step approaches (accidentals). From about 0.7 an increasing share of notes comes from a twelve-tone row; 1.0 is fully serial (all twelve
  // pitch classes before any repeats). Returns {notes:[{p,s,d,v}], stats:{notes,chordTones,diatonic,accidentals,row}, totalTicks, runs}.
  function toTheme(progression, opts) {
    var cfg = (progression && progression.config) || {}, runs = (progression && progression.progression) || [];
    var beatTicks = opts.beatTicks, bpm = opts.bpm || cfg.bpm || 60, c = Math.max(0, Math.min(1, opts.chromatic === undefined ? 0 : opts.chromatic));
    var rnd = mulberry(opts.seed === undefined ? 1 : opts.seed), rhythm = opts.rhythm || 'mixed', lo = opts.lo === undefined ? 60 : opts.lo, hi = opts.hi === undefined ? 84 : opts.hi;
    var minBeats = opts.minBeats === undefined ? 1 : opts.minBeats, quantum = opts.quantum || 0.5, unit = Math.max(1, Math.round(beatTicks / 2)), center = (lo + hi) / 2;
    var ev = [], t0 = 0, used = 0;
    runs.forEach(function (r) {
      var pit = r.root ? chordPitches(r.root, r.suffix || '') : null; if (!pit) return;
      var beats = Math.max(minBeats, Math.round((r.seconds * bpm / 60) / quantum) * quantum), units = Math.max(1, Math.round(beats * 2));
      var ctx = { chord: pit.map(pcOf), scale: SCALES[r.suffix || ''] ? SCALES[r.suffix || ''].map(function (i) { return pcOf(NOTE_MIDI[r.root] + i); }) : pit.map(pcOf) };
      var u = 0;
      while (u < units) {
        var pair = (u % 2 === 0) && (u + 1 < units) && (rhythm === 'eighth' || (rhythm === 'mixed' && rnd() < 0.5));
        ev.push({ t: t0 + u * unit, len: pair ? 1 : (u % 2 === 0 && u + 1 < units ? 2 : 1), strong: true, ctx: ctx, first: u === 0, p: null, kind: '' });
        if (pair) ev.push({ t: t0 + (u + 1) * unit, len: 1, strong: false, ctx: ctx, first: false, p: null, kind: '' });
        u += pair ? 2 : (u % 2 === 0 && u + 1 < units ? 2 : 1);
      }
      t0 += units * unit; used++;
    });
    var stats = { notes: 0, chordTones: 0, diatonic: 0, accidentals: 0, row: 0 };
    if (!ev.length) return { notes: [], stats: stats, totalTicks: 0, runs: 0 };
    var cur = Math.round(center), prev = null;
    // pass 1: the notes on the beat
    ev.forEach(function (e) {
      if (!e.strong) return;
      var ctx = e.ctx, pool, kind = 'chord';
      if (rnd() < c * 0.5) {                                                            // colour tone or accidental on the beat
        if (rnd() < (1 - c) * 0.8 + 0.1) { pool = ctx.scale.filter(function (x) { return ctx.chord.indexOf(x) < 0; }); kind = 'diatonic'; }
        else { pool = []; for (var k = 0; k < 12; k++) if (ctx.scale.indexOf(k) < 0) pool.push(k); kind = 'accidental'; }
        if (!pool.length) { pool = ctx.chord; kind = 'chord'; }
      } else pool = ctx.chord;
      var best = null, bs = 1e9;
      pool.forEach(function (pc) { var p = nearestPc(pc, cur, lo, hi), sc = Math.abs(p - cur) + rnd() * 4 + 0.15 * Math.abs(p - center) + (p === prev ? 3 : 0); if (sc < bs) { bs = sc; best = p; } });
      e.p = best; e.kind = kind; prev = cur; cur = best;
    });
    // pass 2: passing notes, neighbours and approaches between the notes on the beat
    function nextStrong(i) { for (var j = i + 1; j < ev.length; j++) if (ev[j].strong) return ev[j]; return null; }
    function scaleStep(a, dir, ctx) { for (var d = 1; d <= 3; d++) if (ctx.scale.indexOf(pcOf(a + dir * d)) >= 0) return a + dir * d; return a + dir; }
    ev.forEach(function (e, i) {
      if (e.strong) return;
      var a = null, j, nb = nextStrong(i), b = nb ? nb.p : null, ctx = e.ctx, p, kind;
      for (j = i - 1; j >= 0; j--) if (ev[j].strong) { a = ev[j].p; break; }
      if (b === null) b = a;
      var dist = b - a, dir = dist === 0 ? (rnd() < 0.5 ? 1 : -1) : (dist > 0 ? 1 : -1), lastBeforeNext = nb && nb.first;
      if (lastBeforeNext && dist !== 0 && rnd() < 0.2 + c * 0.7) { var ad = Math.abs(b - a) === 1 ? dir : -dir; p = (rnd() < c) ? b + ad : scaleStep(b, ad, nb.ctx); kind = 'approach'; }   // half-step approach to the next chord
      else if (Math.abs(dist) >= 2) { p = (rnd() < c) ? a + dir : scaleStep(a, dir, ctx); if ((p - a) * dir >= Math.abs(dist)) p = (rnd() < c) ? a + dir : scaleStep(a, -dir, ctx); kind = 'pass'; }
      else { p = (rnd() < c) ? a + (rnd() < 0.5 ? 1 : -1) : scaleStep(a, 1, ctx); kind = 'neighbour'; }
      e.p = Math.max(lo - 2, Math.min(hi + 2, p)); e.kind = kind; if (kind === 'approach') e.ctx2 = nb.ctx;
    });
    // pass 3: the twelve-tone row replaces a share of the notes as the dial approaches 1
    var pRow = Math.max(0, Math.min(1, (c - 0.7) / 0.3)), row = [], rp = 0, last = cur;
    function newRow() { var a = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], i, j, t; for (i = 11; i > 0; i--) { j = Math.floor(rnd() * (i + 1)); t = a[i]; a[i] = a[j]; a[j] = t; } return a; }
    var out = [];
    ev.forEach(function (e) {
      if (pRow > 0) { if (!row.length || rp >= row.length) { row = newRow(); rp = 0; } if (rnd() < pRow) { e.p = nearestPc(row[rp++], last, lo, hi); e.kind = 'row'; } }
      last = e.p;
      var pcs = e.ctx, isChord = pcs.chord.indexOf(pcOf(e.p)) >= 0, inScale = pcs.scale.indexOf(pcOf(e.p)) >= 0 || (e.ctx2 && e.ctx2.scale.indexOf(pcOf(e.p)) >= 0);
      if (e.kind === 'row') stats.row++; else if (isChord) stats.chordTones++; else if (inScale) stats.diatonic++; else stats.accidentals++;
      stats.notes++;
      out.push({ p: Math.max(0, Math.min(127, Math.round(e.p))), s: e.t, d: Math.max(1, Math.round(e.len * unit * (e.len >= 2 ? 0.97 : 0.9))), v: e.strong ? (e.first ? 92 : 86) : 70 });
    });
    return { notes: out, stats: stats, totalTicks: t0, runs: used };
  }

  var api = { chordPitches: chordPitches, pulseHits: pulseHits, toVoices: toVoices, toTheme: toTheme, voicing: voicing, PATTERNS: PATTERNS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfProgression = api;
})(typeof window !== 'undefined' ? window : this);
