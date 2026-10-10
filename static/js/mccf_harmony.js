/* ==========================================================================
 * mccf_harmony.js — chordal harmonization for the Theme Workshop (checkpoint 1c)
 * --------------------------------------------------------------------------
 * Pure functions, no DOM.  Given a melody (parser-shaped notes in ticks) and a key it
 *   1. splits the melody into windows by harmonic rhythm (beat / half-bar / bar / phrase),
 *   2. scores every diatonic chord against each window (how many melody notes it contains,
 *      long and strong-beat notes counting more),
 *   3. finds the k lowest-cost chord PATHS (k-best Viterbi): melody fit + a style table of chord-to-chord
 *      transitions + a cadence bonus at phrase ends, every term a named weight so "why that chord?" has an answer,
 *   4. voices each chord for the requested parts under a RULE SET (chorale-strict / organum-parallel / free),
 *      minimising voice movement and avoiding forbidden parallels,
 *   5. returns the notes, the analysis (chord symbols, cadences) and an independent RULE SCAN of the result.
 * Deterministic: the same melody, settings and seed always give the same result.
 * Exposes MccfHarmony (window global, and module.exports under Node).
 * ========================================================================== */
(function (root) {
'use strict';

var MODES = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], 'harmonic-minor': [0, 2, 3, 5, 7, 8, 11], 'melodic-minor': [0, 2, 3, 5, 7, 9, 11],
              dorian: [0, 2, 3, 5, 7, 9, 10], phrygian: [0, 1, 3, 5, 7, 8, 10], lydian: [0, 2, 4, 6, 7, 9, 11], mixolydian: [0, 2, 4, 5, 7, 9, 10], locrian: [0, 1, 3, 5, 6, 8, 10] };
var PARENT = { pentatonic: 'major', 'pentatonic-minor': 'minor', hexatonic: 'major' };   // chords need seven degrees: borrow the parent diatonic scale
var NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'], NAMES_FLAT = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
var PCS = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
var ROMAN = ['I', 'II', 'III', 'IV', 'V', 'VI', 'VII'];
var FUNC = ['T', 'S', 'T', 'S', 'D', 'T', 'D'];     // by scale degree: tonic / subdominant / dominant function
var OFFSET = { major: 0, minor: 3, 'harmonic-minor': 3, 'melodic-minor': 3, dorian: 10, phrygian: 8, lydian: 7, mixolydian: 5, locrian: 1 };
var SHARPS = { 0: 0, 7: 1, 2: 2, 9: 3, 4: 4, 11: 5, 6: 6, 5: -1, 10: -2, 3: -3, 8: -4, 1: -5 };

var RULE_SETS = ['chorale-strict', 'organum-parallel', 'free'];
var STYLES = ['functional', 'plagal'];
var DEFAULT_WEIGHTS = { melodyFit: 1, transition: 1, cadence: 1, voiceLeading: 1, stylePenalty: 1 };
var FIT_SCALE = 4;     // melody fit dominates: a chord that misses the melody must be much better elsewhere to win
// chord-to-chord cost by function class, per style (T tonic, S subdominant, D dominant)
var CLASS_COST = {
  functional: { TT: 0.5, TS: 0.2, TD: 0.45, ST: 0.55, SS: 0.45, SD: 0.0, DT: 0.0, DS: 1.3, DD: 0.6 },
  plagal:     { TT: 0.45, TS: 0.1, TD: 0.8, ST: 0.0, SS: 0.4, SD: 0.4, DT: 0.25, DS: 0.9, DD: 0.7 }
};

function mod12(x) { return ((x % 12) + 12) % 12; }
function tonicToPc(t) {
  if (typeof t === 'number') return mod12(t);
  var m = /^([A-Ga-g])([#b]?)$/.exec(String(t).trim()); if (!m) throw new Error('Unknown tonic: ' + t);
  return mod12(PCS[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0));
}
function flatsKey(key) { var sc = PARENT[key.scale] || key.scale, off = OFFSET[sc] === undefined ? 0 : OFFSET[sc]; return SHARPS[(tonicToPc(key.tonic) + off) % 12] < 0; }
function mulberry32(seed) { var a = seed >>> 0; return function () { a = (a + 0x6D2B79F5) >>> 0; var t = a; t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
function hashStr(s) { var h = 5381; for (var i = 0; i < s.length; i++) h = ((h * 33) ^ s.charCodeAt(i)) >>> 0; return h; }

// ---------------------------------------------------------------------------
// Chord vocabulary
// ---------------------------------------------------------------------------
var QUALITY = { '4,7': 'maj', '3,7': 'min', '3,6': 'dim', '4,8': 'aug', '4,7,11': 'maj7', '4,7,10': 'dom7', '3,7,10': 'min7', '3,6,10': 'hdim7', '3,6,9': 'dim7' };
var SYMBOL = { maj: '', min: 'm', dim: 'dim', dom7: '7', maj7: 'maj7', min7: 'm7', hdim7: 'm7b5', dim7: 'dim7' };

function buildChords(key, vocab) {
  var scale = PARENT[key.scale] || key.scale, steps = MODES[scale] || MODES.major, tpc = tonicToPc(key.tonic), flats = flatsKey(key), names = flats ? NAMES_FLAT : NAMES_SHARP;
  var natMinor = scale === 'minor', sev = vocab === 'sevenths', out = [];
  function make(deg, rootS, third, fifth, seventh, opts) {
    var ints = sev ? [third, fifth, seventh] : [third, fifth], q = QUALITY[ints.join(',')];
    if (!q || q === 'aug') return;                                   // augmented chords are left out of the vocabulary
    var root = mod12(tpc + rootS), tones = [root, mod12(root + third), mod12(root + fifth)]; if (sev) tones.push(mod12(root + seventh));
    var minorish = q === 'min' || q === 'dim' || q === 'min7' || q === 'hdim7' || q === 'dim7';
    var rn = ROMAN[deg]; rn = minorish ? rn.toLowerCase() : rn; if (q === 'dim') rn += '°'; else if (q === 'dim7') rn += '°7'; else if (q === 'hdim7') rn += 'ø7'; else if (q === 'dom7' || q === 'min7') rn += '7'; else if (q === 'maj7') rn += 'M7';
    // the chord's diatonic seventh is a MILD dissonance over a triad (the G over A is the seventh of the dominant), not a wrong note
    var soft = sev ? [] : [mod12(root + ((opts && opts.softIv) || seventh))], nm = (opts && opts.raised) ? NAMES_SHARP : names;
    out.push({ id: (opts && opts.id) || rn, deg: deg, root: root, tones: tones, soft: soft, quality: q, roman: rn, symbol: nm[root] + SYMBOL[q], func: (opts && opts.func) || FUNC[deg], penalty: (opts && opts.penalty) || 0, seventh: sev });
  }
  for (var d = 0; d < 7; d++) {
    var rootS = steps[d], iv = function (k) { return mod12(steps[(d + k) % 7] - rootS); };
    var third = iv(2), fifth = iv(4), seventh = iv(6), pen = 0;
    if (natMinor && d === 4) {                                       // in a minor key the dominant has the raised seventh as its third...
      make(d, rootS, 4, fifth, seventh, { id: sev ? 'V7' : 'V', softIv: 10 });
      make(d, rootS, third, fifth, seventh, { penalty: 0.7, func: 'D' });   // ...and the natural-minor v is kept, but disfavoured
      continue;
    }
    if (d === 2 && scale === 'major') pen = 0.3; if (d === 2 && natMinor) pen = 0.1; if (d === 5) pen = 0.1;
    if (d === 6) pen = 0.8;                                          // the leading-tone / VII chord
    if (natMinor && d === 6) { make(d, rootS, third, fifth, seventh, { penalty: 0.15, func: 'D' }); continue; }   // natural VII (a plain major chord)
    make(d, rootS, third, fifth, seventh, { penalty: pen });
  }
  if (natMinor) make(6, steps[6] + 1, 3, 6, sev ? 10 : 9, { id: sev ? 'vii°7' : 'vii°', penalty: 0.8, func: 'D', raised: true, softIv: 9 });   // the diminished leading-tone chord
  // diminished chords in general are used sparingly
  out.forEach(function (c) { if (c.quality === 'dim' || c.quality === 'hdim7') c.penalty += 0.35; });
  return out;
}

// ---------------------------------------------------------------------------
// Windows by harmonic rhythm, and phrase ends
// ---------------------------------------------------------------------------
function phraseEnds(melody, o) {
  var notes = melody.slice().sort(function (a, b) { return a.startTick - b.startTick; }), ends = [], maxEnd = 0, lastStart = null, bar4 = o.barTicks * 4;
  notes.forEach(function (n) {
    if (lastStart !== null && n.startTick - maxEnd >= o.beatTicks) ends.push(maxEnd);     // a rest of a beat or more ends a phrase
    maxEnd = Math.max(maxEnd, n.startTick + n.durTicks); lastStart = n.startTick;
  });
  if (notes.length) ends.push(maxEnd);
  var out = [];                                                       // no phrase longer than four bars
  var prev = notes.length ? Math.floor(notes[0].startTick / o.barTicks) * o.barTicks : 0;
  ends.forEach(function (e) {
    for (var t = prev + bar4; t < e - o.barTicks / 2; t += bar4) out.push(t);
    out.push(e); prev = e;
  });
  return out;
}
function rangeOf(notes) { if (!notes.length) return 0; var lo = 999, hi = -1; notes.forEach(function (n) { lo = Math.min(lo, n.pitch); hi = Math.max(hi, n.pitch); }); return hi - lo; }
function notesIn(all, t0, t1) { return all.filter(function (n) { return n.startTick < t1 && n.startTick + n.durTicks > t0; }); }
// A window whose melody spans more than an octave and a fifth cannot be voiced under one chord (the inner voices would be
// more than an octave from the melody at some point), so it is split where that helps most.
function splitWide(wins, melody) {
  var out = [], MAXR = 14;
  wins.forEach(function (w) {
    var stack = [w];
    while (stack.length) {
      var x = stack.shift(), rng = rangeOf(x.notes);
      if (rng <= MAXR || x.notes.length < 2) { out.push(x); continue; }
      var times = []; x.notes.forEach(function (n) { if (n.startTick > x.t0 && n.startTick < x.t1 && times.indexOf(n.startTick) < 0) times.push(n.startTick); });
      var best = null; times.sort(function (a, b) { return a - b; }).forEach(function (t) { var sc = Math.max(rangeOf(notesIn(x.notes, x.t0, t)), rangeOf(notesIn(x.notes, t, x.t1))); if (!best || sc < best.sc) best = { t: t, sc: sc }; });
      if (!best || best.sc >= rng) { out.push(x); continue; }
      stack.unshift({ t0: x.t0, t1: best.t, notes: notesIn(x.notes, x.t0, best.t) }, { t0: best.t, t1: x.t1, notes: notesIn(x.notes, best.t, x.t1) });
    }
  });
  return out;
}
function makeWindows(melody, o) {
  if (!melody.length) return [];
  var ends = phraseEnds(melody, o), lo = Infinity, hi = 0; melody.forEach(function (n) { lo = Math.min(lo, n.startTick); hi = Math.max(hi, n.startTick + n.durTicks); });
  var wins = [];
  if (o.rhythm === 'phrase') {
    var prev = Math.floor(lo / o.barTicks) * o.barTicks;
    ends.forEach(function (e) { var t1 = Math.max(prev + o.barTicks, Math.ceil(e / o.barTicks) * o.barTicks); if (t1 > prev) wins.push({ t0: prev, t1: t1 }); prev = t1; });
  } else {
    var span = o.rhythm === 'beat' ? o.beatTicks : o.rhythm === 'half' ? Math.round(o.barTicks / 2) : o.barTicks, a = Math.floor(lo / span) * span, b = Math.ceil(hi / span) * span;
    for (var t = a; t < b; t += span) wins.push({ t0: t, t1: Math.min(b, t + span) });
  }
  wins.forEach(function (w) { w.notes = melody.filter(function (n) { return n.startTick < w.t1 && n.startTick + n.durTicks > w.t0; }).sort(function (a, b) { return a.startTick - b.startTick || b.pitch - a.pitch; }); });
  wins = splitWide(wins, melody);
  wins.forEach(function (w, i) { w.index = i; w.phraseEnd = ends.some(function (e) { return e > w.t0 && e <= w.t1 + 1; }); });
  if (wins.length) wins[wins.length - 1].phraseEnd = true;
  return wins;
}

// ---------------------------------------------------------------------------
// Scoring
// ---------------------------------------------------------------------------
function fitCost(win, chord, scalePcs, o) {   // 0 = every melody note is in the chord; 1 = none is (weighted by length and metric strength)
  var total = 0, miss = 0;
  win.notes.forEach(function (n) {
    var s = Math.max(n.startTick, win.t0), e = Math.min(n.startTick + n.durTicks, win.t1), len = Math.max(0, e - s) / o.beatTicks;
    var pos = (n.startTick % o.barTicks === 0) ? 2.0 : (n.startTick % o.beatTicks === 0) ? 1.2 : 0.7, w = len * pos, pc = mod12(n.pitch);
    total += w;
    if (chord.tones.indexOf(pc) < 0) miss += w * ((chord.soft && chord.soft.indexOf(pc) >= 0) ? (chord.deg === 4 && chord.func === 'D' ? 0 : chord.func === 'D' ? 0.15 : 0.35) : (scalePcs[pc] ? 0.6 : 1.0));   // a note foreign to the key cannot be explained by any chord, so it costs the same everywhere
  });
  return total ? miss / total : 0;
}
function transCost(a, b, win, o, w) { var p = transParts(a, b, win, o, w); return p.trans + p.cad; }
function transParts(a, b, win, o, w) {   // the progression term and the cadence term, separately (so they can be explained)
  var cls = CLASS_COST[o.style] || CLASS_COST.functional, c = cls[a.func + b.func];
  var iv = mod12(b.root - a.root);
  if (iv === 0) c += (a.id === b.id ? 0.6 : 0.3);                                           // repeating a chord, or moving to a chord on the same root
  else if (iv === 5) c -= 0.15;                                                              // root up a fourth (down a fifth): the strong progression
  var cad = 0;
  if (win.phraseEnd) {                                                                        // cadences
    if (b.func === 'S') cad += 2.0;                                                           // a phrase should not end on a subdominant
    if (win.final) {
      if (b.deg === 0 && b.func === 'T') cad -= (a.func === 'D' ? 1.0 : a.func === 'S' ? (o.style === 'plagal' ? 1.0 : 0.7) : 0.2);
    } else if (b.func === 'D') cad -= 0.6;                                                     // half cadence
    else if (b.deg === 0 && a.func === 'D') cad -= 0.4;
  }
  return { trans: w.transition * c, cad: w.cadence * cad };
}

// k-best Viterbi: the k lowest-cost chord sequences
function chordPaths(wins, chords, scalePcs, o, w) {
  var K = Math.max(1, o.k | 0), rnd = mulberry32(o.seed), jit = (o.jitter === undefined ? 0.015 : o.jitter);   // a tie-breaker, not a dice roll: 0.12 let noise overrule a clear i-V reading of Reflections in 26 of 60 seeds
  var fit = wins.map(function (win) {
    return chords.map(function (c) { return w.melodyFit * FIT_SCALE * fitCost(win, c, scalePcs, o) + w.stylePenalty * c.penalty + (rnd() - 0.5) * 2 * jit; });
  });
  var dp = [];
  dp[0] = chords.map(function (c, s) { return [{ cost: fit[0][s] + (c.deg === 0 && c.func === 'T' ? 0 : 0.9 * w.transition), prev: -1, rank: -1 }]; });
  for (var i = 1; i < wins.length; i++) {
    var row = [];
    for (var s = 0; s < chords.length; s++) {
      var cands = [];
      for (var p = 0; p < chords.length; p++) {
        var tc = transCost(chords[p], chords[s], wins[i], o, w);
        if (!wins[i].notes.length && p === s) tc = Math.min(tc, 0);                              // a rest: holding the chord is free
        dp[i - 1][p].forEach(function (e, r) { cands.push({ cost: e.cost + tc + fit[i][s], prev: p, rank: r }); });
      }
      cands.sort(function (a, b) { return a.cost - b.cost; }); row.push(cands.slice(0, K));
    }
    dp.push(row);
  }
  var last = [], n = wins.length - 1;
  dp[n].forEach(function (list, s) { list.forEach(function (e, r) { last.push({ cost: e.cost, s: s, r: r }); }); });
  last.sort(function (a, b) { return a.cost - b.cost; });
  return last.slice(0, K).map(function (L) {
    var path = new Array(wins.length), s = L.s, r = L.r;
    for (var i = n; i >= 0; i--) { path[i] = s; var e = dp[i][s][r]; s = e.prev; r = e.rank; }
    return { chords: path, cost: L.cost };
  });
}

// ---------------------------------------------------------------------------
// Voicing
// ---------------------------------------------------------------------------
var INNER_RANGES = { 1: [[50, 72]], 2: [[55, 74], [48, 67]], 3: [[57, 76], [52, 70], [46, 64]], 4: [[59, 78], [54, 72], [49, 67], [44, 62]] };
var BASS_RANGE = [38, 60];
function sliceMelody(win, t) {       // the melody pitch sounding at tick t (else the first note starting in the window), or null
  var hit = null; win.notes.forEach(function (n) { if (!hit && n.startTick <= t && n.startTick + n.durTicks > t) hit = n; });
  return hit ? hit.pitch : (win.notes.length ? win.notes[0].pitch : null);
}
function isPerfect(a, b) { var d = mod12(a - b); return d === 0 || d === 7; }

function voiceChords(path, wins, chords, key, o, w) {
  var strict = o.ruleSet === 'chorale-strict', relax = strict ? 0 : 6, nIn = o.inner, hasBass = !!o.bass;
  var scale = PARENT[key.scale] || key.scale, steps = MODES[scale] || MODES.major, tpc = tonicToPc(key.tonic), leadPc = mod12(tpc + 11);
  var ranges = (INNER_RANGES[nIn] || INNER_RANGES[2]).map(function (r) { return [r[0] - relax, r[1] + relax]; }), bassR = [BASS_RANGE[0] - relax, BASS_RANGE[1] + relax];
  var nv = nIn + (hasBass ? 1 : 0), M = 110, cands = [];
  wins.forEach(function (win, wi) {
    var chord = chords[path[wi]], mel = win.notes.length ? Math.min.apply(null, win.notes.map(function (n) { return n.pitch; })) : (wi ? cands[wi - 1].mel : 72), list = [];
    var tonesSet = {}; chord.tones.forEach(function (pc) { tonesSet[pc] = true; });
    function pitchesFor(vi) {
      var r = vi < nIn ? ranges[vi] : bassR, out = [], allowed = chord.tones.slice();
      if (vi >= nIn) { allowed = o.inversions === 'root' ? [chord.tones[0]] : [chord.tones[0], chord.tones[1]]; if (o.ruleSet !== 'chorale-strict' && o.inversions !== 'root') allowed.push(chord.tones[2]); }
      for (var p = r[0]; p <= r[1]; p++) if (allowed.indexOf(mod12(p)) >= 0 && p < mel) out.push(p);
      return out;
    }
    function gen(level) {      // level 0: the rules as written; 1: ranges +-6 and no spacing limit; 2: ranges +-14
      var lim = level === 0 ? 0 : (level === 1 ? 6 : 14), out = [];
      function pf(vi) {
        var r = vi < nIn ? ranges[vi] : bassR, allowed = chord.tones.slice(), res = [];
        if (vi >= nIn) { allowed = o.inversions === 'root' ? [chord.tones[0]] : [chord.tones[0], chord.tones[1]]; if (level > 0 || (o.ruleSet !== 'chorale-strict' && o.inversions !== 'root')) allowed.push(chord.tones[2]); }
        for (var p = r[0] - lim; p <= r[1] + lim; p++) if (allowed.indexOf(mod12(p)) >= 0 && p < mel && p >= 0) res.push(p);
        return res;
      }
      var pls = []; for (var q = 0; q < nv; q++) pls.push(pf(q));
      (function rec(vi, cur) {
        if (out.length > 4000) return;
        if (vi === nv) { out.push(cur.slice()); return; }
        var prevP = vi === 0 ? mel : cur[vi - 1];
        pls[vi].forEach(function (p) {
          if (p >= prevP) return;
          var gap = prevP - p;
          if (level === 0 && strict && vi < nIn && gap > 12) return;
          if (level === 0 && !strict && o.ruleSet === 'free' && vi < nIn && gap > 24) return;
          cur.push(p); rec(vi + 1, cur); cur.pop();
        });
      })(0, []);
      return out;
    }
    list = gen(0); if (!list.length) list = gen(1); if (!list.length) list = gen(2);
    if (!list.length) {      // nothing fits (a melody near the bottom of the keyboard): stack chord tones down from just below the melody and let the rule scan report it
      var fb = [], prevP = mel; for (var vq = 0; vq < nv; vq++) { var pp = prevP - 1; while (pp > 0 && chord.tones.indexOf(mod12(pp)) < 0) pp--; fb.push(Math.max(0, pp)); prevP = Math.max(0, pp); }
      list = [fb];
    }
    var scored = list.map(function (v) {
      var cost = 0, pcs = {}, all = (win.notes.length ? [mel] : []).concat(v).map(mod12);
      all.forEach(function (pc) { pcs[pc] = (pcs[pc] || 0) + 1; });
      if (!pcs[chord.tones[0]]) cost += 20; if (!pcs[chord.tones[1]]) cost += 20;                // the root and the third must sound
      if (chord.seventh && !pcs[chord.tones[3]]) cost += 6;
      if (pcs[chord.tones[1]] > 1) cost += 2; if (chord.seventh && pcs[chord.tones[3]] > 1) cost += 4; if (pcs[chord.tones[2]] > 1) cost += 0.5; if (pcs[leadPc] > 1 && tonesSet[leadPc]) cost += 3;
      var gaps = 0; for (var i = 0; i < nIn; i++) { var up = i === 0 ? mel : v[i - 1], g = up - v[i]; gaps += o.spacing === 'open' ? Math.abs(g - 9) * 0.1 : g * 0.08; }
      cost += gaps;
      for (var j = 0; j < nIn; j++) cost += 0.02 * Math.abs(v[j] - (ranges[j][0] + ranges[j][1]) / 2);
      if (hasBass && v[nv - 1] !== undefined && mod12(v[nv - 1]) === chord.tones[1]) cost += 0.35;   // a bass on the third (first inversion) costs a little unless it moves by step
      return { v: v, cost: cost };
    });
    scored.sort(function (a, b) { return a.cost - b.cost; }); cands.push({ list: scored.slice(0, M), mel: mel });
  });
  // DP over windows: least total movement, forbidden parallels, resolutions
  var lt = leadPc, V = w.voiceLeading;
  var mels = wins.map(function (win) { return sliceMelody(win, win.t0); });
  function trans(wi, A, B) {
    var c = 0, ra = [mels[wi - 1]].concat(A.v), rb = [mels[wi]].concat(B.v), chordA = chords[path[wi - 1]], chordB = chords[path[wi]];
    for (var i = 0; i < nv; i++) {
      var d = Math.abs(B.v[i] - A.v[i]), bass = hasBass && i === nv - 1;
      if (bass) { c += V * (d * 0.05 + (d > 9 ? 0.5 : 0)); if (mod12(B.v[i]) === chordB.tones[1] && d <= 2 && d > 0) c -= 0.35; }
      else { c += V * (d * 0.15 + (d > 7 ? 1.0 : 0)); if (d === 0) c -= 0.3 * V; }
    }
    if (strict) {
      for (var a = 0; a < ra.length; a++) for (var b = a + 1; b < ra.length; b++) {
        if (ra[a] === null || ra[b] === null || rb[a] === null || rb[b] === null) continue;
        var ma = rb[a] - ra[a], mb = rb[b] - ra[b];
        if (ma !== 0 && mb !== 0 && ((ma > 0) === (mb > 0)) && isPerfect(ra[a], ra[b]) && isPerfect(rb[a], rb[b]) && mod12(ra[a] - ra[b]) === mod12(rb[a] - rb[b])) c += 60;   // parallel fifths or octaves
      }
      for (var g = 0; g < A.v.length; g++) {                                                       // the generated voices resolve their leading tones (the bass too) and sevenths
        var pa = A.v[g], pb = B.v[g];
        if (mod12(pa) === lt && (chordA.func === 'D') && chordB.deg === 0 && !(pb - pa === 1)) c += 40;
        if (g < nIn && chordA.seventh && mod12(pa) === chordA.tones[3] && chordA.id !== chordB.id && !(pa - pb >= 1 && pa - pb <= 2)) c += 40;
      }
    }
    return c;
  }
  var best = [cands[0].list.map(function (x) { return { cost: x.cost, prev: -1 }; })];
  for (var wi = 1; wi < wins.length; wi++) {
    var row = [];
    cands[wi].list.forEach(function (B) {
      var bc = Infinity, bp = -1;
      cands[wi - 1].list.forEach(function (A, ai) { var c = best[wi - 1][ai].cost + trans(wi, A, B); if (c < bc) { bc = c; bp = ai; } });
      row.push({ cost: bc + B.cost, prev: bp });
    });
    best.push(row);
  }
  var bi = 0; best[wins.length - 1].forEach(function (e, i) { if (e.cost < best[wins.length - 1][bi].cost) bi = i; });
  var chosen = new Array(wins.length), total = best[wins.length - 1][bi].cost;
  for (var k = wins.length - 1; k >= 0; k--) { chosen[k] = cands[k].list[bi].v; bi = best[k][bi].prev; }
  return { voicings: chosen, cost: total, mels: mels };
}

// ---------------------------------------------------------------------------
// Rule scan: an independent check of the RESULT against the rule set
// ---------------------------------------------------------------------------
// slices: [{index, bar, melody (pitch|null), voices:[pitch...] (inner voices then bass), chord (vocabulary entry)}]
function scan(slices, o) {
  var rules = o.ruleSet, strict = rules === 'chorale-strict', out = [], nIn = o.inner, tpc = tonicToPc(o.key.tonic), lt = mod12(tpc + 11);
  var relax = strict ? 0 : 6, ranges = (INNER_RANGES[nIn] || INNER_RANGES[2]).map(function (r) { return [r[0] - relax, r[1] + relax]; }), bassR = [BASS_RANGE[0] - relax, BASS_RANGE[1] + relax];
  var nv = nIn + (o.bass ? 1 : 0), names = [];
  for (var q = 0; q < nIn; q++) names.push('inner ' + (q + 1)); if (o.bass) names.push('bass');
  function add(rule, s, a, b, msg) { out.push({ rule: rule, slice: s.index, bar: s.bar, voices: [a, b], message: msg }); }
  slices.forEach(function (s, i) {
    var row = [s.melodyLow !== undefined ? s.melodyLow : s.melody].concat(s.voices), label = ['melody'].concat(names);
    s.voices.forEach(function (p) { if (s.chord.tones.indexOf(mod12(p)) < 0) add('chord-membership', s, 'voice', null, 'a pitch outside the chord ' + s.chord.symbol); });
    if (rules !== 'organum-parallel') {
      for (var a = 0; a < row.length - 1; a++) {
        if (row[a] === null || row[a + 1] === null) continue;
        if (strict && row[a + 1] > row[a]) add('voice-crossing', s, label[a], label[a + 1], label[a + 1] + ' is above ' + label[a]);   // crossing is only an error under Chorale-strict
        var gap = row[a] - row[a + 1], isBassGap = o.bass && a + 1 === row.length - 1;
        if (strict && !isBassGap && gap > 12) add('spacing', s, label[a], label[a + 1], 'more than an octave between ' + label[a] + ' and ' + label[a + 1]);
        if (rules === 'free' && !isBassGap && gap > 24) add('spacing', s, label[a], label[a + 1], 'more than two octaves between ' + label[a] + ' and ' + label[a + 1]);
      }
    }
    if (strict) {
      s.voices.forEach(function (p, vi) { var r = vi < nIn ? ranges[vi] : bassR; if (p < r[0] || p > r[1]) add('range', s, names[vi], null, names[vi] + ' is outside its range'); });
    }
    if (strict && i > 0) {
      var prev = slices[i - 1], prow = [prev.melody].concat(prev.voices); row = [s.melody].concat(s.voices);   // parallels are judged against the melody as it SOUNDS at the change of chord
      for (var x = 0; x < row.length; x++) for (var y = x + 1; y < row.length; y++) {
        if (row[x] === null || row[y] === null || prow[x] === null || prow[y] === null) continue;
        var mx = row[x] - prow[x], my = row[y] - prow[y];
        if (mx !== 0 && my !== 0 && (mx > 0) === (my > 0) && isPerfect(prow[x], prow[y]) && isPerfect(row[x], row[y]) && mod12(prow[x] - prow[y]) === mod12(row[x] - row[y]))
          add('parallel-' + (mod12(row[x] - row[y]) === 7 ? 'fifths' : 'octaves'), s, label[x], label[y], 'parallel ' + (mod12(row[x] - row[y]) === 7 ? 'fifths' : 'octaves') + ' between ' + label[x] + ' and ' + label[y]);
      }
      s.voices.forEach(function (p, vi) {
        var pp = prev.voices[vi];
        if (mod12(pp) === lt && prev.chord.func === 'D' && s.chord.deg === 0 && p - pp !== 1) add('leading-tone', s, names[vi], null, names[vi] + ' does not resolve the leading tone upward');
        if (vi < nIn && prev.chord.seventh && mod12(pp) === prev.chord.tones[3] && prev.chord.id !== s.chord.id && !(pp - p >= 1 && pp - p <= 2)) add('seventh-resolution', s, names[vi], null, names[vi] + ' does not resolve the chord seventh downward');
      });
    }
  });
  if (strict) slices.forEach(function (s, i) {      // cadence placement: a phrase ends on a tonic (authentic or plagal cadence) or a dominant (half cadence)
    if ((s.phraseEnd || i === slices.length - 1) && s.chord.func === 'S') add('cadence', s, null, null, 'the phrase ends on ' + s.chord.symbol + ', which is neither a tonic nor a dominant');
  });
  return out;
}

// ---------------------------------------------------------------------------
// The whole thing
// ---------------------------------------------------------------------------
// melody: [{pitch,startTick,durTicks,velocity}]  o: {key, ppq, barTicks, beatTicks, rhythm, vocab, style, inner, bass, inversions, spacing, ruleSet, weights, k, path, seed, jitter}
function harmonize(melody, o) {
  o = Object.assign({ rhythm: 'bar', vocab: 'triads', style: 'functional', inner: 2, bass: true, inversions: 'smooth', spacing: 'closed', ruleSet: 'chorale-strict', k: 3, path: 0, seed: 1 }, o);
  var w = Object.assign({}, DEFAULT_WEIGHTS, o.weights || {}), key = o.key, notes = melody.filter(function (n) { return n.durTicks > 0; });
  var wins = makeWindows(notes, o); if (!wins.length) return { windows: [], paths: [], pathIndex: 0, chords: [], parts: { chords: [], bass: [] }, slices: [], violations: [], cadences: [], cost: 0 };
  wins[wins.length - 1].final = true;
  var chords = buildChords(key, o.vocab), scale = PARENT[key.scale] || key.scale, steps = MODES[scale] || MODES.major, tpc = tonicToPc(key.tonic), scalePcs = {};
  steps.forEach(function (s) { scalePcs[mod12(tpc + s)] = true; });
  if (key.scale === 'minor') scalePcs[mod12(tpc + 11)] = true;       // the raised seventh is part of the minor key for this purpose
  var paths = chordPaths(wins, chords, scalePcs, o, w), pi = Math.max(0, Math.min(o.path | 0, paths.length - 1)), path = paths[pi].chords;
  var v = voiceChords(path, wins, chords, key, o, w), nIn = o.inner, hasBass = !!o.bass;
  var chordNotes = [], bassNotes = [], slices = [], barOf = function (t) { return Math.floor(t / o.barTicks) + 1; };
  wins.forEach(function (win, i) {
    var voicing = v.voicings[i], len = Math.max(1, win.t1 - win.t0 - 5);
    voicing.forEach(function (p, vi) { var n = { pitch: p, startTick: win.t0, durTicks: len, velocity: (hasBass && vi === voicing.length - 1) ? 85 : 70, channel: 0 }; if (hasBass && vi === voicing.length - 1) bassNotes.push(n); else chordNotes.push(n); });
    slices.push({ index: i, bar: barOf(win.t0), melody: v.mels[i], melodyLow: win.notes.length ? Math.min.apply(null, win.notes.map(function (n) { return n.pitch; })) : v.mels[i], phraseEnd: !!win.phraseEnd, voices: voicing.slice(), chord: chords[path[i]] });
    win.chord = path[i]; win.symbol = chords[path[i]].symbol; win.roman = chords[path[i]].roman; win.func = chords[path[i]].func;
  });
  var cadences = [];
  wins.forEach(function (win, i) {
    if (!win.phraseEnd) return; var c = chords[path[i]], p = i ? chords[path[i - 1]] : null, type;
    if (c.deg === 0 && c.func === 'T' && p && p.func === 'D') type = 'authentic'; else if (c.deg === 0 && p && p.func === 'S') type = 'plagal'; else if (c.func === 'D') type = 'half';
    else if (p && p.func === 'D' && c.func === 'T') type = 'deceptive'; else type = 'open';
    cadences.push({ bar: barOf(win.t1 - 1), type: type, symbol: c.symbol });
  });
  // WHY each chord: its cost terms next to the two closest rivals, holding the neighbouring chords as chosen.  (Costs exclude the seeded tie-break noise.)
  function describe(r, best) {
    var fitWords = r.fit < 0.05 ? 'every melody note is in the chord' : r.fit < 1 ? 'a little of the melody lies outside the chord' : 'part of the melody lies outside the chord';
    return r.symbol + ' (' + r.roman + '): ' + fitWords + ' [fit ' + r.fit.toFixed(2) + '], progression ' + r.transition.toFixed(2) + ', cadence ' + r.cadence.toFixed(2) + ', style ' + r.style.toFixed(2) + ' = ' + r.total.toFixed(2);
  }
  var why = wins.map(function (win, i) {
    var prev = i ? chords[path[i - 1]] : null, next = i + 1 < wins.length ? chords[path[i + 1]] : null;
    var rows = chords.map(function (c, ci) {
      var fit = w.melodyFit * FIT_SCALE * fitCost(win, c, scalePcs, o), style = w.stylePenalty * c.penalty, tIn = prev ? transParts(prev, c, win, o, w) : { trans: (c.deg === 0 && c.func === 'T') ? 0 : 0.9 * w.transition, cad: 0 }, tOut = next ? transParts(c, next, wins[i + 1], o, w) : { trans: 0, cad: 0 };
      var r = { symbol: c.symbol, roman: c.roman, fit: fit, style: style, transition: tIn.trans + tOut.trans, cadence: tIn.cad + tOut.cad, chosen: ci === path[i] };
      r.total = r.fit + r.style + r.transition + r.cadence; return r;
    });
    var chosen = rows.filter(function (r) { return r.chosen; })[0], rivals = rows.filter(function (r) { return !r.chosen; }).sort(function (a, b) { return a.total - b.total; }).slice(0, 2);
    var margin = rivals.length ? rivals[0].total - chosen.total : 0;
    var text = describe(chosen) + (rivals.length ? '. Runner-up ' + rivals[0].symbol + ' costs ' + (margin >= 0 ? '+' : '') + margin.toFixed(2) + (Math.abs(margin) < 0.05 ? ' (a near tie: the seed broke it)' : '') : '');
    var rnd2 = function (r) { return { symbol: r.symbol, roman: r.roman, fit: +r.fit.toFixed(3), style: +r.style.toFixed(3), transition: +r.transition.toFixed(3), cadence: +r.cadence.toFixed(3), total: +r.total.toFixed(3) }; };
    return { chosen: rnd2(chosen), rivals: rivals.map(rnd2), margin: +margin.toFixed(3), text: text };
  });
  var violations = scan(slices, { ruleSet: o.ruleSet, inner: nIn, bass: hasBass, key: key });
  return { windows: wins.map(function (x) { return { index: x.index, t0: x.t0, t1: x.t1, chord: x.chord, symbol: x.symbol, roman: x.roman, func: x.func, phraseEnd: x.phraseEnd, why: why[x.index] }; }),
           paths: paths.map(function (p) { return { chords: p.chords.slice(), cost: Math.round(p.cost * 1000) / 1000, romans: p.chords.map(function (c) { return chords[c].roman; }) }; }), pathIndex: pi,
           chords: chords.map(function (c) { return { id: c.id, roman: c.roman, symbol: c.symbol, tones: c.tones.slice(), soft: c.soft.slice(), func: c.func, quality: c.quality }; }),
           parts: { chords: chordNotes, bass: bassNotes }, slices: slices, violations: violations, cadences: cadences, cost: Math.round(v.cost * 1000) / 1000, weights: w };
}

var api = { harmonize: harmonize, buildChords: buildChords, makeWindows: makeWindows, phraseEnds: phraseEnds, chordPaths: chordPaths, scan: scan, fitCost: fitCost, tonicToPc: tonicToPc,
            RULE_SETS: RULE_SETS, STYLES: STYLES, DEFAULT_WEIGHTS: DEFAULT_WEIGHTS, MODES: MODES, INNER_RANGES: INNER_RANGES, BASS_RANGE: BASS_RANGE };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfHarmony = api;
})(typeof window !== 'undefined' ? window : this);
