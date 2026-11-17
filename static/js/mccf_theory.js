/* ==========================================================================
 * mccf_theory.js — Theme Workshop engine core (checkpoint 1a)
 * --------------------------------------------------------------------------
 * Pure functions, no DOM, no I/O.  Runs in the browser (window.MccfTheory) and
 * under Node (module.exports) so it can be tested the same way the player was.
 *
 *   scales / pitch space      toDegree, fromDegree, keyInfo
 *   transforms (phase 1a)     transpose, invert, retrograde, retrogradeInversion,
 *                             augment, diminish, sequence, fragment, rotate,
 *                             octaveShift   (+ canon = voice entry, see makeCanon)
 *   voices / arrangement      validateRecipe (DAG check), resolveVoices, assemble
 *   reproducibility           sha256Hex, canonicalJson, recipeDigest, mulberry32
 *   description               fingerprint, describeFingerprint, estimateKey
 *
 * Conventions
 *   - Note shape is the parser's own: {pitch, startTick, durTicks, velocity, channel}
 *   - The theme is extracted into THEME-LOCAL time: tick 0 = start of the chosen
 *     first bar, region = [0, length).  Transforms work in that local time.
 *   - The theme is frozen and never modified.  Voices derive from it (or from other
 *     voices) and lineage is recorded, never overwritten.
 *   - Recipe channels are 1-16 (UI numbering); parser/assembled channels are 0-15.
 *     Recipe `program` is the raw 0-127 number the file carries (parser numbering).
 * ========================================================================== */
(function (root) {
'use strict';

var ENGINE = { name: 'mccf-theory', version: '0.4' };
var HARM = null;
function harmonyEngine() {      // mccf_harmony.js is a separate file: a global in the browser, a require() under Node
  if (HARM) return HARM;
  if (typeof module !== 'undefined' && module.exports) HARM = require('./mccf_harmony.js'); else HARM = root.MccfHarmony;
  if (!HARM) throw new Error('The harmony module (js/mccf_harmony.js) is not loaded');
  return HARM;
}
var RECIPE_VERSION = 1;

// ---------------------------------------------------------------------------
// Scales and pitch space
// ---------------------------------------------------------------------------
var SCALES = {
  'major':          [0, 2, 4, 5, 7, 9, 11],
  'minor':          [0, 2, 3, 5, 7, 8, 10],   // natural minor (the default minor)
  'harmonic-minor': [0, 2, 3, 5, 7, 8, 11],
  'melodic-minor':  [0, 2, 3, 5, 7, 9, 11],
  'dorian':         [0, 2, 3, 5, 7, 9, 10],
  'phrygian':       [0, 1, 3, 5, 7, 8, 10],
  'lydian':         [0, 2, 4, 6, 7, 9, 11],
  'mixolydian':     [0, 2, 4, 5, 7, 9, 10],
  'locrian':        [0, 1, 3, 5, 6, 8, 10],
  'pentatonic':     [0, 2, 4, 7, 9],
  'pentatonic-minor': [0, 3, 5, 7, 10],
  'hexatonic':      [0, 2, 4, 6, 8, 10]       // whole-tone, 6 notes per octave
};
var PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
var PC_NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];

function tonicToPc(t) {
  if (typeof t === 'number') return ((t % 12) + 12) % 12;
  var m = /^([A-Ga-g])([#b]?)$/.exec(String(t).trim());
  if (!m) throw new Error('Unknown tonic: ' + t);
  var pc = PC[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0);
  return ((pc % 12) + 12) % 12;
}

function keyInfo(key) {
  var steps = SCALES[key.scale];
  if (!steps) throw new Error('Unknown scale: ' + key.scale);
  return { tonicPc: tonicToPc(key.tonic), scale: key.scale, steps: steps, N: steps.length };
}
function _fl(a, b) { return Math.floor(a / b); }

// pitch -> {abs, alt}.  abs = octave*N + degree (an integer "scale-step index");
// alt = semitones from that degree (0 for in-scale notes; nearest degree, ties go sharp).
function toDegree(pitch, ki) {
  var rel = pitch - ki.tonicPc, oct = _fl(rel, 12), pc = rel - 12 * oct;
  var best = 0, bestDist = pc - ki.steps[0];
  for (var d = 1; d <= ki.N; d++) {
    var dist = pc - (d === ki.N ? 12 : ki.steps[d]);
    if (Math.abs(dist) < Math.abs(bestDist)) { best = d; bestDist = dist; }
  }
  return { abs: oct * ki.N + best, alt: bestDist };
}
function fromDegree(abs, alt, ki) {
  var oct = _fl(abs, ki.N), deg = abs - oct * ki.N;
  return ki.tonicPc + 12 * oct + ki.steps[deg] + alt;
}

// ---------------------------------------------------------------------------
// Bars
// ---------------------------------------------------------------------------
// timeSigEvents: [{tick,num,den}] (may be empty -> 4/4).  Assumes changes sit on bar lines.
function barTicksFor(ppq, sig) { return Math.round(ppq * 4 * sig.num / sig.den); }
function makeBarMap(ppq, timeSigEvents) {
  var ev = (timeSigEvents && timeSigEvents.length) ? timeSigEvents : [{ tick: 0, num: 4, den: 4 }];
  var segs = [], bar = 1;
  for (var i = 0; i < ev.length; i++) {
    var bt = barTicksFor(ppq, ev[i]);
    if (i > 0) bar = segs[i - 1].bar + Math.round((ev[i].tick - segs[i - 1].tick) / segs[i - 1].barTicks);
    segs.push({ tick: ev[i].tick, bar: bar, barTicks: bt, num: ev[i].num, den: ev[i].den });
  }
  return {
    tickOfBar: function (b) {                    // 1-based bar -> tick
      var s = segs[0];
      for (var i = 0; i < segs.length; i++) if (segs[i].bar <= b) s = segs[i];
      return s.tick + (b - s.bar) * s.barTicks;
    },
    sigAtTick: function (t) {
      var s = segs[0];
      for (var i = 0; i < segs.length; i++) if (segs[i].tick <= t) s = segs[i];
      return { num: s.num, den: s.den, barTicks: s.barTicks };
    }
  };
}

// ---------------------------------------------------------------------------
// Note helpers (all pure: inputs are never mutated)
// ---------------------------------------------------------------------------
// A note may carry a NON-ENUMERABLE degree hint `_d = {abs, alt}` while it travels through a chain, so
// diatonic moves stay exactly reversible even for out-of-scale notes (a note a semitone above a degree can
// coincide with the next degree, which would be ambiguous if re-read from the pitch alone).  The hint is only
// trusted while it still matches the pitch, so any other pitch change silently invalidates it.
function cn(n) {   // clone
  var c = { pitch: n.pitch, startTick: n.startTick, durTicks: n.durTicks, velocity: n.velocity, channel: n.channel };
  if (n._d) Object.defineProperty(c, '_d', { value: n._d, enumerable: false, writable: true, configurable: true });
  return c;
}
function plain(n) { return { pitch: n.pitch, startTick: n.startTick, durTicks: n.durTicks, velocity: n.velocity, channel: n.channel }; }
function degOf(n, ki) {
  if (n._d && fromDegree(n._d.abs, n._d.alt, ki) === n.pitch) return n._d;
  return toDegree(n.pitch, ki);
}
function putDeg(c, abs, alt, ki) {
  c.pitch = fromDegree(abs, alt, ki);
  Object.defineProperty(c, '_d', { value: { abs: abs, alt: alt }, enumerable: false, writable: true, configurable: true });
}
function sortNotes(notes) {   // canonical order: total order, so output never depends on input order
  return notes.slice().sort(function (a, b) {
    return (a.startTick - b.startTick) || (a.pitch - b.pitch) || (a.durTicks - b.durTicks) ||
           (a.velocity - b.velocity) || (a.channel - b.channel);
  });
}
function mapNotes(notes, f) { return notes.map(function (n) { var c = cn(n); f(c, n); return c; }); }
function endOf(notes) { return notes.reduce(function (m, n) { return Math.max(m, n.startTick + n.durTicks); }, 0); }

// ---------------------------------------------------------------------------
// Theme extraction — immutable, theme-local time
// ---------------------------------------------------------------------------
// parsed: parseMidiFile() result.  sel: {tracks:[idx...], bars:[a,b]} (bars inclusive, 1-based).
// Notes are included when they START inside the region; durations are clipped at the region end.
function extractTheme(parsed, sel) {
  var ppq = parsed.ppq, bm = makeBarMap(ppq, parsed.timeSigEvents);
  var a = sel.bars[0], b = sel.bars[1];
  if (!(a >= 1 && b >= a)) throw new Error('Invalid bar range: ' + JSON.stringify(sel.bars));
  var t0 = bm.tickOfBar(a), t1 = bm.tickOfBar(b + 1), notes = [], clipped = 0;
  (sel.tracks || []).forEach(function (ti) {
    var tr = parsed.tracks[ti];
    if (!tr) throw new Error('No such track index: ' + ti);
    tr.notes.forEach(function (n) {
      if (n.startTick >= t0 && n.startTick < t1) {
        var end = Math.min(n.startTick + n.durTicks, t1);
        if (end < n.startTick + n.durTicks) clipped++;
        notes.push({ pitch: n.pitch, startTick: n.startTick - t0, durTicks: end - n.startTick,
                     velocity: n.velocity, channel: n.channel });
      }
    });
  });
  var sig = bm.sigAtTick(t0);
  var tempo = parsed.tempoEvents.filter(function (e) { return e.tick <= t0; });
  var tempoEvents = [{ tick: 0, usPerQuarter: (tempo.length ? tempo[tempo.length - 1] : parsed.tempoEvents[0]).usPerQuarter }];
  parsed.tempoEvents.forEach(function (e) {
    if (e.tick > t0 && e.tick < t1) tempoEvents.push({ tick: e.tick - t0, usPerQuarter: e.usPerQuarter });
  });
  var sorted = sortNotes(notes);
  sorted.forEach(Object.freeze);
  return Object.freeze({
    notes: Object.freeze(sorted), length: t1 - t0, ppq: ppq, barTicks: sig.barTicks,
    timeSig: { num: sig.num, den: sig.den }, tempoEvents: tempoEvents, clipped: clipped,
    sourceTicks: [t0, t1]
  });
}

// ---------------------------------------------------------------------------
// Transforms.  Each is  fn(notes, params, ctx) -> {notes, length}
//   ctx = {ki (keyInfo), ppq, barTicks, length (current region length)}
// ---------------------------------------------------------------------------
function ratio(p) {
  var P = p.p, Q = p.q;
  if (!(P > 0 && Q > 0 && P % 1 === 0 && Q % 1 === 0)) throw new Error('ratio needs positive integers p and q');
  return [P, Q];
}
function fragRange(notes, frag, ctx) {   // -> [t0,t1) tick window plus kept notes, for {bars} or {notes} selectors
  if (!frag) return { t0: 0, t1: ctx.length, notes: notes };
  if (frag.bars) {
    var t0 = (frag.bars[0] - 1) * ctx.barTicks, t1 = Math.min(frag.bars[1] * ctx.barTicks, ctx.length);
    return { t0: t0, t1: t1, notes: notes.filter(function (n) { return n.startTick >= t0 && n.startTick < t1; }) };
  }
  if (frag.notes) {
    var kept = notes.slice(frag.notes[0], frag.notes[1] + 1);
    if (!kept.length) return { t0: 0, t1: 0, notes: [] };
    var base = kept[0].startTick;   // sorted, so the first kept note starts the fragment
    return { t0: base, t1: Math.max(base + 1, endOf(kept)), notes: kept };
  }
  throw new Error('fragment needs {bars:[a,b]} or {notes:[i,j]}');
}
function rebase(sel) {   // kept notes -> local time starting at 0, clipped to the window
  return sel.notes.map(function (n) {
    var c = cn(n); c.startTick = n.startTick - sel.t0;
    c.durTicks = Math.max(1, Math.min(n.startTick + n.durTicks, sel.t1) - n.startTick); return c;
  });
}
function axisPitch(notes, axis, ctx) {
  if (typeof axis === 'number') return axis;
  if (axis && typeof axis === 'object' && typeof axis.pitch === 'number') return axis.pitch;
  if (axis === 'tonic') {   // the tonic nearest the THEME's first note (fixed for the whole voice tree, so inversion stays reversible)
    var k = Math.round((ctx.anchor - ctx.ki.tonicPc) / 12);
    return ctx.ki.tonicPc + 12 * k;
  }
  return notes.length ? notes[0].pitch : 60;   // 'first': first note of the line being transformed
}
function invertNotes(notes, params, ctx) {
  var mode = params.mode || 'diatonic', ki = ctx.ki, ax = axisPitch(notes, params.axis, ctx);
  if (mode === 'chromatic') return mapNotes(notes, function (c, n) { c.pitch = 2 * ax - n.pitch; });
  var a = (params.axis === undefined || params.axis === 'first') && notes.length ? degOf(notes[0], ki) : toDegree(ax, ki);
  return mapNotes(notes, function (c, n) {   // mirror the step index AND the alteration about the axis
    var d = degOf(n, ki);
    putDeg(c, 2 * a.abs - d.abs, 2 * a.alt - d.alt, ki);
  });
}
function retro(notes, L) {   // start' = t0 + t1 - (start+dur), t0 = 0, t1 = L
  return mapNotes(notes, function (c, n) { c.startTick = L - (n.startTick + n.durTicks); });
}
function scaleTime(notes, L, P, Q) {
  return {
    notes: mapNotes(notes, function (c, n) {
      c.startTick = Math.round(n.startTick * P / Q); c.durTicks = Math.max(1, Math.round(n.durTicks * P / Q));
    }),
    length: Math.max(1, Math.round(L * P / Q))
  };
}
function shiftNote(c, n, steps, mode, ki) {   // sets c.pitch (and the degree hint) from n
  if (mode === 'chromatic') { c.pitch = n.pitch + steps; return; }
  var d = degOf(n, ki); putDeg(c, d.abs + steps, d.alt, ki);
}

function parseList(v, what, dflt) {   // "2,3,5" -> [2,3,5]; a number passes through; empty -> [dflt]
  if (typeof v === 'number') return [v];
  var parts = String(v === undefined || v === null ? '' : v).split(',').map(function (x) { return x.trim(); }).filter(function (x) { return x !== ''; });
  if (!parts.length) return [dflt];
  return parts.map(function (x) { var n = Number(x); if (!isFinite(n)) throw new Error('repeat: ' + what + ' must be numbers separated by commas (got "' + x + '")'); return n; });
}
var TRANSFORMS = {
  transpose: { version: 1,
    defaults: { steps: 0, mode: 'diatonic' },
    fn: function (notes, p, ctx) {
      return { notes: mapNotes(notes, function (c, n) { shiftNote(c, n, p.steps, p.mode, ctx.ki); }), length: ctx.length };
    } },
  invert: { version: 1,
    defaults: { axis: 'first', mode: 'diatonic' },
    fn: function (notes, p, ctx) { return { notes: invertNotes(notes, p, ctx), length: ctx.length }; } },
  retrograde: { version: 1,
    defaults: {},
    fn: function (notes, p, ctx) { return { notes: retro(notes, ctx.length), length: ctx.length }; } },
  retrogradeInversion: { version: 1,
    defaults: { axis: 'first', mode: 'diatonic' },
    fn: function (notes, p, ctx) { return { notes: retro(invertNotes(notes, p, ctx), ctx.length), length: ctx.length }; } },
  augment: { version: 1,           // time x p/q   (2:1 doubles)
    defaults: { p: 2, q: 1 },
    fn: function (notes, p, ctx) { var r = ratio(p); return scaleTime(notes, ctx.length, r[0], r[1]); } },
  diminish: { version: 1,          // time x q/p   (2:1 halves; matches the "Diminish 2:1" chip)
    defaults: { p: 2, q: 1 },
    fn: function (notes, p, ctx) { var r = ratio(p); return scaleTime(notes, ctx.length, r[1], r[0]); } },
  sequence: { version: 1,          // `copies` in total, copy i shifted by i*step; optional fragment
    defaults: { copies: 2, step: 1, mode: 'diatonic', fragment: null },
    fn: function (notes, p, ctx) {
      var sel = fragRange(notes, p.fragment, ctx), base = rebase(sel), len = sel.t1 - sel.t0, out = [];
      if (!(p.copies >= 1) || p.copies % 1 !== 0) throw new Error('sequence: copies must be a positive integer');
      for (var i = 0; i < p.copies; i++) {
        for (var j = 0; j < base.length; j++) {
          var c = cn(base[j]); c.startTick += i * len; shiftNote(c, base[j], i * p.step, p.mode, ctx.ki); out.push(c);
        }
      }
      return { notes: out, length: len * p.copies };
    } },
  repeat: { version: 1,            // copies of the line, each its own distance apart, shift and transform (see parseList)
    // copies = total including the original (which is never changed); gaps = beats (quarter notes) from the start of one copy
    // to the start of the next, e.g. "4" or "2,3,5" (the last value repeats); shifts = scale steps (or semitones) for repeat 1, 2, 3...;
    // ops = one code per repeat: - none, i invert, r retrograde, ri retrograde-inversion, a augment 2:1, d diminish 2:1;
    // velocity = change in loudness per copy.  Gap 0 stacks the copies.
    defaults: { copies: 3, gaps: '4', shifts: '0', ops: '', velocity: 0, mode: 'diatonic', fragment: null },
    fn: function (notes, p, ctx) {
      if (!(p.copies >= 1) || p.copies % 1 !== 0) throw new Error('repeat: copies must be a positive integer');
      var gaps = parseList(p.gaps, 'gaps', 4), shifts = parseList(p.shifts, 'shifts', 0), ops = String(p.ops === undefined || p.ops === null ? '' : p.ops).split(',').map(function (x) { return x.trim().toLowerCase(); });
      gaps.forEach(function (g) { if (!(g >= 0)) throw new Error('repeat: gaps are beats and cannot be negative'); });
      var sel = fragRange(notes, p.fragment, ctx), base = rebase(sel), len = sel.t1 - sel.t0, out = [], off = 0, end = len;
      var c2 = { ki: ctx.ki, ppq: ctx.ppq, barTicks: ctx.barTicks, length: len, anchor: ctx.anchor };
      for (var i = 0; i < p.copies; i++) {
        var k = i - 1, code = i === 0 || ops[k] === undefined || ops[k] === '' ? '-' : ops[k], cur = base, clen = len, r;
        if (code === 'i') cur = TRANSFORMS.invert.fn(cur, { axis: 'first', mode: p.mode }, c2).notes;
        else if (code === 'r') cur = TRANSFORMS.retrograde.fn(cur, {}, c2).notes;
        else if (code === 'ri') cur = TRANSFORMS.retrogradeInversion.fn(cur, { axis: 'first', mode: p.mode }, c2).notes;
        else if (code === 'a') { r = TRANSFORMS.augment.fn(cur, { p: 2, q: 1 }, c2); cur = r.notes; clen = r.length; }
        else if (code === 'd') { r = TRANSFORMS.diminish.fn(cur, { p: 2, q: 1 }, c2); cur = r.notes; clen = r.length; }
        else if (code !== '-') throw new Error('repeat: ops code "' + code + '" is not one of - i r ri a d');
        var sh = i === 0 ? 0 : shifts[Math.min(k, shifts.length - 1)];
        for (var j = 0; j < cur.length; j++) {
          var c = cn(cur[j]); c.startTick += off;
          if (sh) shiftNote(c, cur[j], sh, p.mode, ctx.ki);
          if (p.velocity) c.velocity = Math.max(1, Math.min(127, Math.round((cur[j].velocity === undefined ? 90 : cur[j].velocity) + p.velocity * i)));
          out.push(c);
        }
        end = Math.max(end, off + clen);
        off += Math.round(gaps[Math.min(i, gaps.length - 1)] * ctx.ppq);
      }
      return { notes: out, length: end };
    } },
  fragment: { version: 1,          // keep a bar range or note range; result is rebased to 0
    defaults: { bars: null, notes: null },
    fn: function (notes, p, ctx) {
      var sel = fragRange(notes, p.bars ? { bars: p.bars } : { notes: p.notes }, ctx);
      return { notes: rebase(sel), length: sel.t1 - sel.t0 };
    } },
  rotate: { version: 1,            // start from note k, wrap the earlier notes to the end of the region
    defaults: { k: 0 },
    fn: function (notes, p, ctx) {
      if (!notes.length) return { notes: [], length: ctx.length };
      var k = ((p.k % notes.length) + notes.length) % notes.length, ref = notes[k].startTick, L = ctx.length;
      return { notes: mapNotes(notes, function (c, n) { c.startTick = (((n.startTick - ref) % L) + L) % L; }), length: L };
    } },
  octaveShift: { version: 1,       // whole octaves, always +12 semitones per octave
    defaults: { octaves: 1, range: null },
    fn: function (notes, p, ctx) {
      var sel = fragRange(notes, p.range, ctx), set = new Set(sel.notes);
      return { notes: mapNotes(notes, function (c, n) { if (set.has(n)) c.pitch = n.pitch + 12 * p.octaves; }), length: ctx.length };
    } }
};

function normalizeStep(step) {   // fill version + defaults so a saved recipe is explicit
  var t = TRANSFORMS[step.type];
  if (!t) throw new Error('Unknown transform type: ' + step.type);
  var params = {}; Object.keys(t.defaults).forEach(function (k) { params[k] = t.defaults[k]; });
  Object.keys(step.params || {}).forEach(function (k) { params[k] = step.params[k]; });
  return { type: step.type, version: step.version === undefined ? t.version : step.version, params: params };
}

function foldPitches(notes, warnings, where) {   // keep MIDI pitches legal; fold by octave and say so
  var hit = 0;
  var out = notes.map(function (n) {
    if (n.pitch >= 0 && n.pitch <= 127) return n;
    var c = cn(n); while (c.pitch < 0) c.pitch += 12; while (c.pitch > 127) c.pitch -= 12; hit++; return c;
  });
  if (hit) warnings.push(where + ': ' + hit + ' note(s) left the MIDI range and were folded by octave');
  return out;
}

// Apply a chain to notes in theme-local time.  -> {notes, length, warnings}
function applyChain(notes, length, chain, base, where) {
  var cur = sortNotes(notes), len = length, warnings = [];
  (chain || []).forEach(function (raw, i) {
    var step = normalizeStep(raw), t = TRANSFORMS[step.type];
    if (step.version !== t.version) throw new Error(step.type + ' version ' + step.version + ' is not supported (engine has ' + t.version + ')');
    var r = t.fn(cur, step.params, { ki: base.ki, ppq: base.ppq, barTicks: base.barTicks, length: len, anchor: base.anchor });
    cur = sortNotes(foldPitches(r.notes, warnings, (where || 'chain') + '[' + i + '] ' + step.type));
    len = r.length;
  });
  return { notes: cur, length: len, warnings: warnings };
}

// ---------------------------------------------------------------------------
// Recipe
// ---------------------------------------------------------------------------
var RULE_SETS = ['chorale-strict', 'organum-parallel', 'free'];
var DEFAULT_WEIGHTS = {   // reserved for 1c: named harmonic cost terms (see review item 6)
  melodyFit: 1.0, transition: 1.0, cadence: 1.0, voiceLeading: 1.0, stylePenalty: 1.0
};

function normalizeRecipe(r) {
  var out = {
    recipeVersion: r.recipeVersion || RECIPE_VERSION,
    engine: r.engine || { name: ENGINE.name, version: ENGINE.version },
    source: {
      file: r.source && r.source.file, sha256: (r.source && r.source.sha256) || null,
      tracks: ((r.source && r.source.tracks) || []).slice(), bars: ((r.source && r.source.bars) || [1, 1]).slice()
    },
    key: { tonic: r.key.tonic, scale: r.key.scale },
    ruleSet: r.ruleSet || 'chorale-strict',
    seed: r.seed === undefined ? 1 : r.seed,
    harmony: { weights: Object.assign({}, DEFAULT_WEIGHTS, (r.harmony && r.harmony.weights) || {}) },
    // Hear the result over the source file's other tracks (the theme track(s) are replaced by the voices)
    backing: (function () {
      var b = { enabled: !!(r.backing && r.backing.enabled),
                leadInBars: r.backing && r.backing.leadInBars !== undefined ? r.backing.leadInBars : 2,
                tailBars: r.backing && r.backing.tailBars !== undefined ? r.backing.tailBars : 2 };
      if (r.backing && r.backing.mode !== undefined && r.backing.mode !== 'window') b.mode = r.backing.mode;          // 'whole' = the entire source file
      if (r.backing && r.backing.omit && r.backing.omit.length) b.omit = r.backing.omit.slice().sort(function (x, y) { return x - y; });   // source tracks to leave out
      return b;
    })(),
    voices: (r.voices || []).map(function (v, i) {
      var o = {
        id: v.id || ('v' + (i + 1)), name: v.name || ('Voice ' + (i + 1)), source: v.source || 'theme',
        chain: (v.chain || []).map(normalizeStep), entryBar: v.entryBar === undefined ? 1 : v.entryBar,
        program: v.program === undefined ? null : v.program, channel: v.channel === undefined ? i + 1 : v.channel,
        volume: v.volume === undefined ? 100 : v.volume, enabled: v.enabled === undefined ? true : !!v.enabled
      };
      ['pan', 'reverb', 'chorus'].forEach(function (k) { if (v[k] !== undefined) o[k] = v[k]; });
      if (v.kind === 'harmony') {   // a GENERATED chordal harmony: chords (inner voices) + bass, from the voice named in `source`
        o.kind = 'harmony'; o.source = v.source || 'theme'; o.chain = []; o.entryBar = 1;
        o.style = v.style || 'functional'; o.rhythm = v.rhythm || 'bar'; o.vocab = v.vocab || 'triads';
        o.inner = v.inner === undefined ? 2 : v.inner; o.bass = v.bass === undefined ? true : !!v.bass;
        o.inversions = v.inversions || 'smooth'; o.spacing = v.spacing || 'closed';
        o.k = v.k === undefined ? 3 : v.k; o.path = v.path === undefined ? 0 : v.path; o.seed = v.seed === undefined ? null : v.seed;
        o.program = v.program === undefined || v.program === null ? 19 : v.program;                    // 19 = church organ
        o.bassProgram = v.bassProgram === undefined ? 32 : v.bassProgram; o.bassChannel = v.bassChannel === undefined ? (o.channel % 16) + 1 : v.bassChannel; o.bassVolume = v.bassVolume === undefined ? 100 : v.bassVolume;
      }
      if (v.kind === 'notes') {   // a HAND-EDITED voice: its notes ARE the recipe (voice-local ticks; entryBar still places it)
        o.kind = 'notes'; o.source = 'theme'; o.chain = [];
        o.notes = (v.notes || []).map(function (n) { return { p: n.p, s: n.s, d: n.d, v: n.v === undefined ? 90 : n.v }; });
        if (v.frozenFrom) o.frozenFrom = v.frozenFrom;     // provenance only: where these notes came from
      }
      if (v.kind === 'drums') {   // a GENERATED voice: no source or chain, always channel 10, program = GM drum kit
        o.kind = 'drums'; o.source = 'theme'; o.chain = []; o.channel = 10;
        o.program = v.program === undefined || v.program === null ? 32 : v.program;     // 32 = Jazz kit on GM2 synths
        o.style = v.style || 'jazz-swing';
        o.intensity = v.intensity === undefined ? 0.6 : v.intensity;
        o.swing = v.swing === undefined ? 0.667 : v.swing;
        o.fillEvery = v.fillEvery === undefined ? 4 : v.fillEvery;
        o.humanize = v.humanize === undefined ? 0.3 : v.humanize;
        o.ending = v.ending || 'hit';
        o.bars = v.bars === undefined ? 'auto' : v.bars;
        o.seed = v.seed === undefined ? null : v.seed;
      }
      return o;
    })
  };
  return out;
}

// -> array of error strings (empty = valid).  Rejects unknown sources, duplicate ids and cycles.
function validateRecipe(raw) {
  var errs = [], r;
  try { r = normalizeRecipe(raw); } catch (e) { return [String(e.message || e)]; }
  if (!r.source.file) errs.push('source.file is required');
  if (!r.source.tracks.length) errs.push('source.tracks needs at least one track index');
  if (!(r.source.bars[0] >= 1 && r.source.bars[1] >= r.source.bars[0])) errs.push('source.bars must be [first, last] with 1 <= first <= last');
  try { keyInfo(r.key); } catch (e) { errs.push(e.message); }
  if (!(r.backing.leadInBars >= 0 && r.backing.tailBars >= 0)) errs.push('backing leadInBars and tailBars must be >= 0');
  if (r.backing.mode !== undefined && ['window', 'whole'].indexOf(r.backing.mode) < 0) errs.push('backing mode must be "window" or "whole"');
  if (r.backing.omit && !r.backing.omit.every(function (i) { return i >= 0 && i % 1 === 0; })) errs.push('backing omit must be a list of source track numbers');
  if (RULE_SETS.indexOf(r.ruleSet) < 0) errs.push('ruleSet must be one of ' + RULE_SETS.join(', '));
  if (r.engine.name !== ENGINE.name) errs.push('engine.name "' + r.engine.name + '" is not ' + ENGINE.name);
  var ids = {};
  r.voices.forEach(function (v) {
    if (ids[v.id]) errs.push('duplicate voice id: ' + v.id);
    ids[v.id] = v;
    if (v.id === 'theme') errs.push('voice id "theme" is reserved');
    if (!(v.channel >= 1 && v.channel <= 16)) errs.push(v.id + ': channel must be 1-16');
    if (!(v.volume >= 0 && v.volume <= 127)) errs.push(v.id + ': volume must be 0-127');
    if (v.program !== null && !(v.program >= 0 && v.program <= 127)) errs.push(v.id + ': program must be 0-127');
    if (!(v.entryBar >= 1)) errs.push(v.id + ': entryBar must be >= 1');
    if (v.kind === 'harmony') {
      var HH = harmonyEngine();
      if (HH.STYLES.indexOf(v.style) < 0) errs.push(v.id + ': harmony style must be one of ' + HH.STYLES.join(', '));
      if (['beat', 'half', 'bar', 'phrase'].indexOf(v.rhythm) < 0) errs.push(v.id + ': harmonic rhythm must be beat, half, bar or phrase');
      if (['triads', 'sevenths'].indexOf(v.vocab) < 0) errs.push(v.id + ': chord vocabulary must be triads or sevenths');
      if (!(v.inner >= 1 && v.inner <= 4 && v.inner % 1 === 0)) errs.push(v.id + ': inner voices must be 1-4');
      if (['root', 'first', 'smooth'].indexOf(v.inversions) < 0) errs.push(v.id + ': inversions must be root, first or smooth');
      if (['closed', 'open'].indexOf(v.spacing) < 0) errs.push(v.id + ': spacing must be closed or open');
      if (!(v.k >= 1 && v.k <= 8 && v.k % 1 === 0)) errs.push(v.id + ': k (alternative chord paths) must be 1-8');
      if (!(v.path >= 0 && v.path < v.k && v.path % 1 === 0)) errs.push(v.id + ': path must be 0 to k-1');
      if (!(v.seed === null || (v.seed >= 0 && v.seed % 1 === 0))) errs.push(v.id + ': seed must be empty or a whole number >= 0');
      if (!(v.bassChannel >= 1 && v.bassChannel <= 16)) errs.push(v.id + ': bass channel must be 1-16');
      if (!(v.bassProgram >= 0 && v.bassProgram <= 127)) errs.push(v.id + ': bass program must be 0-127');
      if (!(v.bassVolume >= 0 && v.bassVolume <= 127)) errs.push(v.id + ': bass volume must be 0-127');
    }
    if (v.kind === 'notes') {
      if (v.notes.length > 50000) errs.push(v.id + ': too many notes (' + v.notes.length + ')');
      var badNote = 0; v.notes.forEach(function (n) {
        if (!(n.p >= 0 && n.p <= 127 && n.p % 1 === 0 && n.s >= 0 && n.s % 1 === 0 && n.d >= 1 && n.d % 1 === 0 && n.v >= 1 && n.v <= 127 && n.v % 1 === 0)) badNote++;
      });
      if (badNote) errs.push(v.id + ': ' + badNote + ' note(s) have a value out of range (pitch 0-127, whole-number start >= 0, length >= 1, velocity 1-127)');
    }
    if (v.kind === 'drums') {
      if (DRUM_STYLES.indexOf(v.style) < 0) errs.push(v.id + ': drum style must be one of ' + DRUM_STYLES.join(', '));
      if (!(v.intensity >= 0 && v.intensity <= 1)) errs.push(v.id + ': intensity must be 0-1');
      if (!(v.swing >= 0.5 && v.swing <= 0.8)) errs.push(v.id + ': swing must be 0.5-0.8');
      if (!(v.humanize >= 0 && v.humanize <= 1)) errs.push(v.id + ': humanize must be 0-1');
      if (!(v.fillEvery >= 0 && v.fillEvery % 1 === 0)) errs.push(v.id + ': fillEvery must be a whole number of bars (0 = none)');
      if (['hit', 'none'].indexOf(v.ending) < 0) errs.push(v.id + ': ending must be "hit" or "none"');
      if (!(v.bars === 'auto' || (v.bars >= 1 && v.bars % 1 === 0))) errs.push(v.id + ': bars must be "auto" or a whole number >= 1');
      if (!(v.seed === null || (v.seed >= 0 && v.seed % 1 === 0))) errs.push(v.id + ': seed must be empty or a whole number >= 0');
    }
    v.chain.forEach(function (s, i) {
      var t = TRANSFORMS[s.type];
      if (s.version !== t.version) errs.push(v.id + ' chain[' + i + ']: ' + s.type + ' version ' + s.version + ' unsupported (engine has ' + t.version + ')');
    });
  });
  r.voices.forEach(function (v) {
    if (v.source !== 'theme' && !ids[v.source]) errs.push(v.id + ': unknown source "' + v.source + '"');
    else if (v.source !== 'theme' && ids[v.source].kind === 'drums') errs.push(v.id + ': cannot derive from the drums voice "' + v.source + '"');
    else if (v.source !== 'theme' && ids[v.source].kind === 'harmony') errs.push(v.id + ': cannot derive from the harmony voice "' + v.source + '" (it has two parts); freeze it first');
  });
  // cycle check: follow source links; a walk longer than the voice count must loop
  r.voices.forEach(function (v) {
    var seen = {}, cur = v;
    while (cur && cur.source !== 'theme') {
      if (seen[cur.id]) { errs.push('cycle in voice sources involving "' + v.id + '"'); break; }
      seen[cur.id] = true; cur = ids[cur.source];
    }
  });
  return errs;
}

// Voices in dependency order, each with theme-local notes and lineage ["theme", ...ancestors..., self]
function resolveVoices(recipe, theme) {
  var r = normalizeRecipe(recipe), errs = validateRecipe(r);
  if (errs.length) throw new Error('Invalid recipe: ' + errs.join('; '));
  var base = { ki: keyInfo(r.key), ppq: theme.ppq, barTicks: theme.barTicks, anchor: theme.notes.length ? theme.notes[0].pitch : 60 };
  var byId = {}, done = {}, order = [];
  r.voices.forEach(function (v) { byId[v.id] = v; });
  function resolve(v) {
    if (done[v.id]) return done[v.id];
    if (v.kind === 'notes') {
      var hn = sortNotes(v.notes.map(function (n) { return { pitch: n.p, startTick: n.s, durTicks: n.d, velocity: n.v, channel: 0 }; }));
      var hl = hn.length ? Math.ceil(endOf(hn) / theme.barTicks) * theme.barTicks : 0;
      var hv = { id: v.id, name: v.name, notes: hn, length: hl, lineage: [v.id], warnings: [], spec: v };
      done[v.id] = hv; order.push(hv); return hv;
    }
    if (v.kind === 'harmony') {
      var hs = v.source === 'theme' ? { notes: theme.notes, length: theme.length, entryBar: 1 } : (function () { var q = resolve(byId[v.source]); return { notes: q.notes, length: q.length, entryBar: byId[v.source].entryBar }; })();
      var Hn = harmonyEngine(), den = theme.timeSig.den, bt = Math.round(theme.ppq * 4 / den);
      var hr = Hn.harmonize(hs.notes, { key: r.key, ppq: theme.ppq, barTicks: theme.barTicks, beatTicks: bt, rhythm: v.rhythm, vocab: v.vocab, style: v.style, inner: v.inner, bass: v.bass,
        inversions: v.inversions, spacing: v.spacing, ruleSet: r.ruleSet, weights: r.harmony.weights, k: v.k, path: v.path, seed: ((v.seed === null ? r.seed : v.seed) + hashStr(v.id)) >>> 0 });
      var hrec = { id: v.id, name: v.name, notes: [], length: hs.length, lineage: [v.source === 'theme' ? 'theme' : v.source, v.id], warnings: [], spec: v, harmony: true, entryBar: hs.entryBar, parts: hr.parts, analysis: hr };
      if (hr.violations.length) hrec.warnings.push('harmony "' + v.name + '": ' + hr.violations.length + ' rule violation' + (hr.violations.length > 1 ? 's' : '') + ' under ' + r.ruleSet + ' (first: ' + hr.violations[0].message + ', bar ' + hr.violations[0].bar + ')');
      done[v.id] = hrec; order.push(hrec); return hrec;
    }
    if (v.kind === 'drums') {   // generated later, in assemble(), once the length of the music is known
      var dv = { id: v.id, name: v.name, notes: [], length: 0, lineage: [v.id], warnings: [], spec: v, drums: true };
      done[v.id] = dv; order.push(dv); return dv;
    }
    var src = v.source === 'theme'
      ? { notes: theme.notes, length: theme.length, lineage: ['theme'] }
      : resolve(byId[v.source]);
    var res = applyChain(src.notes, src.length, v.chain, base, v.id);
    var out = { id: v.id, name: v.name, notes: res.notes, length: res.length,
                lineage: src.lineage.concat([v.id]), warnings: res.warnings, spec: v };
    done[v.id] = out; order.push(out); return out;
  }
  r.voices.forEach(resolve);
  return order;
}

// Ancestry as a nested tree: [{id, name, chain:[types], children:[...]}], rooted at the theme.
function lineageTree(recipe) {
  var r = normalizeRecipe(recipe);
  function kids(src) {
    return r.voices.filter(function (v) { return v.source === src; }).map(function (v) {
      return { id: v.id, name: v.name, chain: v.chain.map(function (s) { return s.type; }), children: kids(v.id) };
    });
  }
  return { id: 'theme', name: 'Theme', children: kids('theme') };
}

// A window of the SOURCE file's other tracks, rebased so fromBar becomes tick 0.  Used to hear a result against the
// real harmony.  Notes are kept when they START inside the window (durations clipped); each controller's value at
// the window start is carried in at tick 0; per-channel programs are preserved.
function extractWindow(parsed, o) {
  var bm = makeBarMap(parsed.ppq, parsed.timeSigEvents), t0 = bm.tickOfBar(o.fromBar), t1 = bm.tickOfBar(o.toBar + 1);
  var skip = {}; (o.skipTracks || []).forEach(function (i) { skip[i] = true; });
  var repl = {}; (o.replaceTracks || []).forEach(function (i) { repl[i] = true; });   // these play everywhere EXCEPT inside o.replaceRegion {from, to} (source ticks)
  var tracks = [];
  parsed.tracks.forEach(function (tr) {
    if (skip[tr.index] || !tr.noteCount) return;
    var notes = [];
    tr.notes.forEach(function (n) {
      if (repl[tr.index] && o.replaceRegion && n.startTick >= o.replaceRegion.from && n.startTick < o.replaceRegion.to) return;
      if (n.startTick >= t0 && n.startTick < t1) {
        notes.push({ pitch: n.pitch, startTick: n.startTick - t0, durTicks: Math.min(n.startTick + n.durTicks, t1) - n.startTick,
                     velocity: n.velocity, channel: n.channel });
      }
    });
    if (repl[tr.index] && !notes.length) return;   // a replaced theme track with nothing left outside the theme is simply not there (no empty track in the file)
    var ctl = {};
    Object.keys(tr.controllers || {}).forEach(function (cc) {
      var byCh = {};
      tr.controllers[cc].forEach(function (e) {
        var list = byCh[e.channel] || (byCh[e.channel] = { init: null, ev: [] });
        if (e.tick <= t0) list.init = e.value;
        else if (e.tick < t1) list.ev.push({ tick: e.tick - t0, value: e.value, channel: e.channel });
      });
      Object.keys(byCh).map(Number).sort(function (a, b) { return a - b; }).forEach(function (c) {
        var L = byCh[c], out = (ctl[cc] = ctl[cc] || []);
        if (L.init !== null) out.push({ tick: 0, value: L.init, channel: c });
        L.ev.forEach(function (e) { out.push(e); });
      });
    });
    tracks.push({ index: 0, name: tr.name, channel: tr.channel, channelsSeen: tr.channelsSeen.slice(), program: tr.program,
                  programs: Object.assign({}, tr.programs || {}), notes: sortNotes(notes), noteCount: notes.length,
                  controllers: ctl, lengthTicks: endOf(notes), sourceTrack: tr.index });
  });
  var tempo = parsed.tempoEvents.filter(function (e) { return e.tick <= t0; });
  var tempoEvents = [{ tick: 0, usPerQuarter: (tempo.length ? tempo[tempo.length - 1] : parsed.tempoEvents[0]).usPerQuarter }];
  parsed.tempoEvents.forEach(function (e) { if (e.tick > t0 && e.tick < t1) tempoEvents.push({ tick: e.tick - t0, usPerQuarter: e.usPerQuarter }); });
  var sig = bm.sigAtTick(t0);
  var sigs = [{ tick: 0, num: sig.num, den: sig.den, clocks: 24, n32: 8 }];
  (parsed.timeSigEvents || []).forEach(function (e) { if (e.tick > t0 && e.tick < t1) sigs.push({ tick: e.tick - t0, num: e.num, den: e.den, clocks: e.clocks === undefined ? 24 : e.clocks, n32: e.n32 === undefined ? 8 : e.n32 }); });
  return { tracks: tracks, tempoEvents: tempoEvents, timeSigEvents: sigs,
           length: t1 - t0, barTicks: sig.barTicks, fromTick: t0, toTick: t1 };
}
// Put an assembled arrangement over a source window: arrangement tracks first, then the window's tracks.
function mergeBacking(arr, win) {
  var tracks = arr.tracks.concat(win.tracks).map(function (t, i) { var c = Object.assign({}, t); c.index = i; return c; });
  return Object.assign({}, arr, { tracks: tracks, ntrks: tracks.length, tempoEvents: win.tempoEvents,
                                  timeSigEvents: win.timeSigEvents, lengthTicks: Math.max(arr.lengthTicks || 0, win.length) });
}

// Key signature meta for the file: only major/minor map to a signature. Enharmonic spelling defaults to
// the common one (Db, Eb, F#, Ab, Bb). -> {tick:0, sharps, minor} or null.
var MAJOR_SHARPS = [0, -5, 2, -3, 4, -1, 6, 1, -4, 3, -2, 5];   // by tonic pitch class
function keySigEventFor(key) {
  var pc = tonicToPc(key.tonic);
  if (key.scale === 'major') return { tick: 0, sharps: MAJOR_SHARPS[pc], minor: false };
  if (key.scale === 'minor') return { tick: 0, sharps: MAJOR_SHARPS[(pc + 3) % 12], minor: true };
  return null;
}

// ---------------------------------------------------------------------------
// Drums — a generated voice (GM drum map, channel 10).  Deterministic: every random choice is drawn from a
// PRNG seeded by (recipe seed or the voice's own seed) + voice id + bar number, so
//   - the same recipe always gives the same hits,
//   - changing `humanize` changes only how far hits drift from the grid, never WHICH hits there are,
//   - changing `fillEvery` changes only the bars that get fills.
// These patterns are starting points to be judged by ear, not authoritative transcriptions of any drummer.
// ---------------------------------------------------------------------------
var DRUM_STYLES = ['jazz-swing', 'jazz-waltz', 'straight-rock'];
var GMD = { KICK: 36, SNARE: 38, HAT: 42, PEDAL: 44, OPEN: 46, TOM_LF: 41, TOM_HF: 43, TOM_L: 45, TOM_HM: 48, TOM_H: 50, CRASH: 49, RIDE: 51 };
function hashStr(str) { var h = 5381; for (var i = 0; i < str.length; i++) h = ((h * 33) ^ str.charCodeAt(i)) >>> 0; return h; }

// A style is written for one meter; ask for it in another and the nearest sensible one is used, with a note.
function styleForMeter(style, sigKey) {
  var table = { '4/4': { 'jazz-swing': 'jazz-swing', 'jazz-waltz': 'jazz-swing', 'straight-rock': 'straight-rock' },
                '3/4': { 'jazz-swing': 'jazz-waltz', 'jazz-waltz': 'jazz-waltz', 'straight-rock': null } };
  var m = table[sigKey];
  if (!m) return { style: null, warn: 'drums: there is no pattern for ' + sigKey + ' time yet, so the drum voice is silent' };
  if (!m[style]) return { style: null, warn: 'drums: ' + style + ' has no ' + sigKey + ' pattern, so the drum voice is silent' };
  return { style: m[style], warn: m[style] !== style ? 'drums: ' + style + ' in ' + sigKey + ' time uses ' + m[style] : null };
}

var FILLS = {
  swing: { one: [[[0, 38, 78], [1 / 3, 48, 74], [2 / 3, 45, 84]], [[0, 38, 72], [1 / 3, 38, 68], [2 / 3, 43, 86]]],
           two: [[[0, 38, 66], [1 / 3, 38, 64], [2 / 3, 38, 70], [1, 48, 78], [4 / 3, 45, 82], [5 / 3, 43, 90]],
                 [[0, 38, 70], [0.5, 38, 64], [1, 50, 76], [1.5, 48, 80], [5 / 3, 45, 84]]] },
  rock:  { one: [[[0, 38, 86], [0.25, 38, 78], [0.5, 48, 84], [0.75, 45, 92]]],
           two: [[[0, 38, 84], [0.5, 38, 80], [1, 48, 86], [1.25, 48, 80], [1.5, 45, 90], [1.75, 43, 96]]] }
};

// opts: {ppq, barTicks, startTick, bars, style (already meter-resolved), seed, id}
function generateDrums(spec, c) {
  var ppq = c.ppq, bt = c.barTicks, bars = c.bars, I = spec.intensity, sw = spec.swing, hum = spec.humanize;
  var base = (spec.seed === null || spec.seed === undefined) ? c.seed : spec.seed, idh = hashStr(c.id);
  var vscale = 0.55 + 0.75 * I, notes = [], style = c.style, family = style === 'straight-rock' ? 'rock' : 'swing';
  var perBeat = style === 'jazz-waltz' ? 3 : 4;
  function isFillBar(bi) { return spec.fillEvery > 0 && (bi + 1) % spec.fillEvery === 0 && bi < bars - 1; }
  var finalHit = spec.ending === 'hit' && bars >= 1;

  for (var bi = 0; bi < bars; bi++) {
    var rp = mulberry32((base + idh + Math.imul(bi + 1, 2654435761)) >>> 0);
    var rj = mulberry32((base * 31 + idh + Math.imul(bi + 1, 40503) + 0x9E3779B9) >>> 0);
    var ev = [];   // [beat, pitch, velocity, durationInBeats, fixedTiming]
    if (finalHit && bi === bars - 1) {
      ev.push([0, GMD.CRASH, 100, 3, true], [0, GMD.KICK, 96, 0.3, true]);
    } else {
      if (style === 'jazz-swing') {
        [0, 1, 2, 3].forEach(function (b) { ev.push([b, GMD.RIDE, b % 2 === 1 ? 84 : 78, 0.25]); });
        ev.push([1 + sw, GMD.RIDE, 62, 0.25], [3 + sw, GMD.RIDE, 62, 0.25]);
        ev.push([1, GMD.PEDAL, 60, 0.2], [3, GMD.PEDAL, 60, 0.2]);
        [0, 1, 2, 3].forEach(function (b) { ev.push([b, GMD.KICK, 26 + Math.floor(rp() * 10), 0.2]); });
        if (rp() < 0.10 + 0.25 * I) ev.push([[1 + sw, 2 + sw, 3 + sw][Math.floor(rp() * 3)], GMD.KICK, 66 + Math.floor(rp() * 20), 0.2]);
        [0, 1, 2, 3].forEach(function (b) {
          var r = rp(), r2 = rp(), pg = 0.12 + 0.30 * I;
          if (r < pg) ev.push([b + sw, GMD.SNARE, 28 + Math.floor(r2 * 14), 0.15]);
          else if (r < pg + 0.05 * I) ev.push([b + sw, GMD.SNARE, 70 + Math.floor(r2 * 15), 0.15]);
        });
      } else if (style === 'jazz-waltz') {
        [[0, 78], [1, 70], [2, 74]].forEach(function (x) { ev.push([x[0], GMD.RIDE, x[1], 0.25]); });
        ev.push([1 + sw, GMD.RIDE, 62, 0.25]);
        ev.push([1, GMD.PEDAL, 56, 0.2], [2, GMD.PEDAL, 56, 0.2]);
        ev.push([0, GMD.KICK, 28 + Math.floor(rp() * 10), 0.2]);
        if (rp() < 0.08 + 0.2 * I) ev.push([[1 + sw, 2 + sw][Math.floor(rp() * 2)], GMD.KICK, 64 + Math.floor(rp() * 20), 0.2]);
        [1 + sw, 2 + sw].forEach(function (b) {
          var r = rp(), r2 = rp(), pg = 0.12 + 0.30 * I;
          if (r < pg) ev.push([b, GMD.SNARE, 28 + Math.floor(r2 * 14), 0.15]);
          else if (r < pg + 0.05 * I) ev.push([b, GMD.SNARE, 70 + Math.floor(r2 * 15), 0.15]);
        });
      } else {   // straight-rock
        for (var k = 0; k < 8; k++) ev.push([k * 0.5, (k === 7 && rp() < 0.25 * I) ? GMD.OPEN : GMD.HAT, k % 2 === 0 ? 80 : 62, 0.2]);
        ev.push([0, GMD.KICK, 96, 0.25], [2, GMD.KICK, 92, 0.25]);
        if (rp() < 0.30 * I) ev.push([2.5, GMD.KICK, 84, 0.25]);
        if (rp() < 0.15 * I) ev.push([0.5, GMD.KICK, 80, 0.25]);
        ev.push([1, GMD.SNARE, 100, 0.25], [3, GMD.SNARE, 98, 0.25]);
        if (rp() < 0.20 * I) ev.push([3.75, GMD.SNARE, 40, 0.15]);
      }
      if (isFillBar(bi)) {   // replace the end of the bar with a fill
        var two = perBeat === 4 && rp() < 0.5, fs = two ? perBeat - 2 : perBeat - 1;
        if (perBeat === 3) fs = 2;
        var set = FILLS[family][two ? 'two' : 'one'], pat = set[Math.floor(rp() * set.length)];
        ev = ev.filter(function (e) { return e[0] < fs - 1e-9; });
        pat.forEach(function (f) { ev.push([fs + f[0], f[1], f[2], 0.18]); });   // short, so fast fills never overlap themselves
      }
      if (bi > 0 && isFillBar(bi - 1)) {   // land the fill: the crash and a kick replace the downbeat's soft kick
        ev = ev.filter(function (e) { return !(e[0] === 0 && e[1] === GMD.KICK); });
        ev.push([0, GMD.CRASH, 92, 2, true], [0, GMD.KICK, 88, 0.3, true]);
      }
    }
    ev.sort(function (a, b) { return (a[0] - b[0]) || (a[1] - b[1]); });
    ev.forEach(function (e) {
      var jt = rj(), jv = rj();   // always drawn, so humanize only scales the drift
      var t = c.startTick + bi * bt + Math.round(e[0] * ppq) + (e[4] ? 0 : Math.round((jt - 0.5) * 2 * 8 * hum * ppq / 480));
      var v = Math.max(1, Math.min(127, Math.round(e[2] * vscale + (jv - 0.5) * 2 * 10 * hum)));
      notes.push({ pitch: e[1], startTick: Math.max(c.startTick, t), durTicks: Math.max(1, Math.round(e[3] * ppq)), velocity: v, channel: 9 });
    });
  }
  return sortNotes(notes);
}

// Resolve everything a drums voice needs from the theme's meter and the music's length, then generate.
function drumsFor(spec, theme, melodicEnd, recipeSeed) {
  var warnings = [], sigKey = theme.timeSig.num + '/' + theme.timeSig.den, rs = styleForMeter(spec.style, sigKey);
  if (rs.warn) warnings.push(rs.warn);
  if (!rs.style) return { notes: [], warnings: warnings };
  var start = Math.round((spec.entryBar - 1) * theme.barTicks), bars;
  if (spec.bars === 'auto') {
    if (melodicEnd > start) bars = Math.max(1, Math.ceil((melodicEnd - start) / theme.barTicks));
    else { bars = 8; warnings.push('drums: there is no music after bar ' + spec.entryBar + ' to follow, so 8 bars were generated'); }
  } else bars = spec.bars;
  var notes = generateDrums(spec, { ppq: theme.ppq, barTicks: theme.barTicks, startTick: start, bars: bars, style: rs.style, seed: recipeSeed, id: spec.id });
  return { notes: notes, warnings: warnings, bars: bars };
}

// Assemble the parser-shaped object the Player and the SMF writer both consume.
function assemble(recipe, theme, opts) {
  opts = opts || {};
  var shift = Math.round(opts.shiftTicks || 0);   // place the whole arrangement later in time (e.g. at its source position)
  var r = normalizeRecipe(recipe), voices = resolveVoices(r, theme), tracks = [], warnings = [], total = 0;
  var melodicEnd = 0;   // where the pitched music ends (theme-local): the drums run up to here
  voices.forEach(function (v) {
    if (v.drums || !v.spec.enabled) return;
    if (v.harmony) { melodicEnd = Math.max(melodicEnd, Math.round((v.entryBar - 1) * theme.barTicks) + Math.max.apply(null, [0].concat(v.parts.chords.concat(v.parts.bass).map(function (n) { return n.startTick + n.durTicks; })))); return; }
    melodicEnd = Math.max(melodicEnd, Math.round((v.spec.entryBar - 1) * theme.barTicks) + endOf(v.notes));
  });
  if (opts.musicEnd) melodicEnd = Math.max(melodicEnd, opts.musicEnd);   // the source tracks you will hear (backing window), theme-local ticks
  voices.forEach(function (v) {
    var s = v.spec; warnings = warnings.concat(v.warnings);
    if (!s.enabled) return;
    var ch = (s.channel - 1) & 0x0f, off = Math.round((s.entryBar - 1) * theme.barTicks) + shift;
    if (v.harmony) {      // chords (inner voices) on one channel, the bass on another
      var hoff = Math.round((v.entryBar - 1) * theme.barTicks) + shift;
      [['chords', v.parts.chords, s.id, s.name, ch, s.program, s.volume], ['bass', v.parts.bass, s.id + '~bass', s.name + ' bass', (s.bassChannel - 1) & 0x0f, s.bassProgram, s.bassVolume]].forEach(function (pt) {
        if (!pt[1].length) return;
        var hn = pt[1].map(function (n) { var c = plain(n); c.startTick += hoff; c.channel = pt[4]; return c; }), hctl = {}; hctl[7] = [{ tick: 0, value: pt[6], channel: pt[4] }];
        var hl = endOf(hn); total = Math.max(total, hl); var po = {}; po[pt[4]] = pt[5];
        tracks.push({ index: tracks.length, name: pt[3], channel: pt[4], channelsSeen: [pt[4]], program: pt[5], notes: hn, noteCount: hn.length, controllers: hctl, lengthTicks: hl, voiceId: pt[2], role: pt[0], programs: po });
      });
      return;
    }
    var notes;
    if (v.drums) {
      var g = drumsFor(s, theme, melodicEnd, r.seed); warnings = warnings.concat(g.warnings);
      notes = g.notes.map(function (n) { var c = plain(n); c.startTick += shift; c.channel = 9; return c; });
    } else notes = v.notes.map(function (n) { var c = plain(n); c.startTick += off; c.channel = ch; return c; });
    var ctl = {}; ctl[7] = [{ tick: 0, value: s.volume, channel: ch }];
    if (s.pan !== undefined) ctl[10] = [{ tick: 0, value: s.pan, channel: ch }];
    if (s.reverb !== undefined) ctl[91] = [{ tick: 0, value: s.reverb, channel: ch }];
    if (s.chorus !== undefined) ctl[93] = [{ tick: 0, value: s.chorus, channel: ch }];
    var len = endOf(notes); total = Math.max(total, len);
    tracks.push({ index: tracks.length, name: s.name, channel: ch, channelsSeen: [ch], program: s.program,
                  notes: notes, noteCount: notes.length, controllers: ctl, lengthTicks: len, voiceId: s.id,
                  programs: s.program === null ? {} : (function () { var o = {}; o[ch] = s.program; return o; })() });
  });
  return {
    format: 1, ppq: theme.ppq, ntrks: tracks.length, tempoEvents: theme.tempoEvents,
    timeSigEvents: [{ tick: 0, num: theme.timeSig.num, den: theme.timeSig.den, clocks: 24, n32: 8 }],
    keySigEvents: (function () { var k = keySigEventFor(r.key); return k ? [k] : []; })(),
    tracks: tracks, lengthTicks: total, warnings: warnings
  };
}

// ONE entry point for the page and for tests: recipe + parsed source -> everything needed to play/export/describe.
// -> {recipe, theme, arrangement (parser-shaped, ready for writeSMF or the Player), voices:[{id,name,lineage,fingerprint}],
//     warnings:[...]}.  Throws on an invalid recipe.
function build(recipe, parsed) {
  var r = normalizeRecipe(recipe), errs = validateRecipe(r);
  if (errs.length) throw new Error('Invalid recipe: ' + errs.join('; '));
  var theme = extractTheme(parsed, r.source), arr = assemble(r, theme), warnings = arr.warnings.slice(), placedAt = 0;
  if (theme.clipped) warnings.push(theme.clipped + ' theme note(s) run past the end of the region and were cut');
  if (!theme.notes.length) warnings.push('the chosen tracks have no notes in bars ' + r.source.bars[0] + '-' + r.source.bars[1]);
  if (r.backing.enabled) {
    var bm = makeBarMap(parsed.ppq, parsed.timeSigEvents), a = r.source.bars[0];
    var whole = r.backing.mode === 'whole', omit = r.backing.omit || [];
    var from = whole ? 1 : a - Math.max(0, Math.min(r.backing.leadInBars, a - 1));
    var lastLocal = Math.max(1, Math.ceil(arr.lengthTicks / theme.barTicks));
    var to = a + lastLocal - 1 + r.backing.tailBars, win;
    if (whole) {   // the entire source file: the theme track(s) are replaced only INSIDE the theme's bars and keep playing before and after
      var fileBars = Math.max(1, Math.ceil(parsed.tracks.reduce(function (m, t) { return Math.max(m, t.lengthTicks || 0); }, 0) / theme.barTicks));
      to = Math.max(fileBars, a + lastLocal - 1);
      win = extractWindow(parsed, { fromBar: 1, toBar: to, skipTracks: omit, replaceTracks: r.source.tracks.filter(function (i) { return omit.indexOf(i) < 0; }),
                                    replaceRegion: { from: bm.tickOfBar(a), to: bm.tickOfBar(r.source.bars[1] + 1) } });
    } else win = extractWindow(parsed, { fromBar: from, toBar: to, skipTracks: r.source.tracks.concat(omit) });
    var shifted = assemble(r, theme, { shiftTicks: bm.tickOfBar(a) - bm.tickOfBar(from), musicEnd: (to - a + 1) * theme.barTicks });
    var used = {}; win.tracks.forEach(function (t) { if (whole && r.source.tracks.indexOf(t.sourceTrack) >= 0) return; t.channelsSeen.forEach(function (c) { used[c] = true; }); });   // (a replaced theme track keeping its own channel is intended)
    r.voices.forEach(function (v) { if (v.enabled && used[(v.channel - 1) & 15]) warnings.push('voice "' + v.name + '" uses channel ' + v.channel + ', which a source track also uses'); });
    arr = mergeBacking(shifted, win); placedAt = bm.tickOfBar(a) - bm.tickOfBar(from);
  }
  var voices = resolveVoices(r, theme).map(function (v) {
    if (v.harmony) {
      var an = v.analysis; return { id: v.id, name: v.name, lineage: v.lineage, harmony: { windows: an.windows, paths: an.paths, pathIndex: an.pathIndex, cadences: an.cadences, violations: an.violations, cost: an.cost, entryBar: v.entryBar, ruleSet: r.ruleSet, weights: an.weights } };
    }
    if (v.drums) {
      var tk = arr.tracks.filter(function (t) { return t.voiceId === v.id; })[0];
      return { id: v.id, name: v.name, lineage: v.lineage, drums: true, hits: tk ? tk.noteCount : 0,
               endBar: tk ? Math.ceil(tk.lengthTicks / theme.barTicks) : 0 };
    }
    return { id: v.id, name: v.name, lineage: v.lineage, fingerprint: fingerprint(v.notes, v.length, theme.ppq, theme.barTicks) };
  });
  return { recipe: r, theme: theme, arrangement: arr, voices: voices, warnings: warnings, shiftTicks: placedAt };   // shiftTicks: where the theme's bar 1 sits in the arrangement
}

// Turn any pitched voice into a HAND-EDITED voice: its notes, exactly as they sound now, stored in the recipe.  The voice keeps its
// id and entry bar and the notes stay voice-local, so nothing that derives from it changes.  `from` records where the notes came
// from.  -> a new recipe (the argument is not modified).  Throws for drums or an unknown voice.
function freezeVoice(recipe, voiceId, parsed) {
  var r = JSON.parse(JSON.stringify(normalizeRecipe(recipe))), theme = extractTheme(parsed, r.source);
  var idx = -1; r.voices.forEach(function (v, i) { if (v.id === voiceId) idx = i; });
  if (idx < 0) throw new Error('No voice "' + voiceId + '"');
  var v = r.voices[idx];
  if (v.kind === 'notes') return r;                                   // already hand-edited
  if (v.kind === 'harmony') {   // generated harmony -> two hand-edited voices: the chords, and (if there is one) the bass
    var hres = resolveVoices(r, theme).filter(function (x) { return x.id === voiceId; })[0], hv = hres.spec;
    var conv = function (ns) { return ns.map(function (n) { return { p: n.pitch, s: n.startTick, d: n.durTicks, v: n.velocity }; }); };
    var from = { kind: 'harmony', style: hv.style, rhythm: hv.rhythm, vocab: hv.vocab, inner: hv.inner, inversions: hv.inversions, spacing: hv.spacing, path: hv.path, seed: hv.seed, source: hv.source };
    var chordsV = { id: hv.id, name: hv.name, kind: 'notes', source: 'theme', chain: [], entryBar: hres.entryBar, program: hv.program, channel: hv.channel, volume: hv.volume, enabled: hv.enabled,
                    notes: conv(hres.parts.chords), frozenFrom: from }, out = [chordsV];
    if (hres.parts.bass.length) {
      var bid = hv.id + '_bass', used = {}; r.voices.forEach(function (x) { used[x.id] = true; }); for (var q = 2; used[bid]; q++) bid = hv.id + '_bass' + q;
      out.push({ id: bid, name: hv.name + ' bass', kind: 'notes', source: 'theme', chain: [], entryBar: hres.entryBar, program: hv.bassProgram, channel: hv.bassChannel, volume: hv.bassVolume, enabled: hv.enabled, notes: conv(hres.parts.bass), frozenFrom: from });
    }
    r.voices.splice.apply(r.voices, [idx, 1].concat(out));
    return normalizeRecipe(r);
  }
  if (v.kind === 'drums') {   // generated drums -> a hand-edited drum voice holding exactly the hits you hear (channel 10, the same kit)
    var db = build(r, parsed), dt = db.arrangement.tracks.filter(function (t) { return t.voiceId === voiceId; })[0];
    var dOff = Math.round((v.entryBar - 1) * theme.barTicks);
    r.voices[idx] = { id: v.id, name: v.name, kind: 'notes', source: 'theme', chain: [], entryBar: v.entryBar, program: v.program, channel: 10,
                      volume: v.volume, enabled: v.enabled, pan: v.pan, reverb: v.reverb, chorus: v.chorus,
                      notes: dt ? dt.notes.map(function (n) { return { p: n.pitch, s: Math.max(0, n.startTick - (db.shiftTicks || 0) - dOff), d: n.durTicks, v: n.velocity }; }) : [],
                      frozenFrom: { kind: 'drums', style: v.style, intensity: v.intensity, swing: v.swing, fillEvery: v.fillEvery, humanize: v.humanize, ending: v.ending, seed: v.seed } };
    ['pan', 'reverb', 'chorus'].forEach(function (k) { if (r.voices[idx][k] === undefined) delete r.voices[idx][k]; });
    return normalizeRecipe(r);
  }
  var res = resolveVoices(r, theme).filter(function (x) { return x.id === voiceId; })[0];
  r.voices[idx] = { id: v.id, name: v.name, kind: 'notes', source: 'theme', chain: [], entryBar: v.entryBar, program: v.program, channel: v.channel,
                    volume: v.volume, enabled: v.enabled, pan: v.pan, reverb: v.reverb, chorus: v.chorus,
                    notes: res.notes.map(function (n) { return { p: n.pitch, s: n.startTick, d: n.durTicks, v: n.velocity }; }),
                    frozenFrom: { source: v.source, chain: v.chain, entryBar: v.entryBar } };
  ['pan', 'reverb', 'chorus'].forEach(function (k) { if (r.voices[idx][k] === undefined) delete r.voices[idx][k]; });
  return normalizeRecipe(r);
}

// Apply one editing gesture to a hand-edited voice.  Times in `ev` are ARRANGEMENT ticks (what the grid shows); the voice stores
// voice-local ticks, so ctx = {barTicks, shiftTicks} says where the voice sits (shiftTicks = where the theme's bar 1 is).
//   {type:'add', pitch, start, dur, vel}   {type:'move', ids, dTick, dPitch}   {type:'resize', ids, dDur}
//   {type:'velocity', ids, vel | dVel | set:{id:vel}}   {type:'delete', ids}   {type:'paste', notes:[{pitch, start, dur, vel}]}
//   {type:'quantize', ids, grid, strength?, durations?}  {type:'swing', ids, grid, ratio}  {type:'humanize', ids, vel, time, seed}
//   {type:'transform', ids, chain:[{type,params}], place:'after'|'end'|'replace'|'at', at?, join?:{steps}}   (needs ctx.key and ctx.ppq)
//        run a chain of the Workshop's transforms on the selected notes AS A UNIT (retrograde mirrors the phrase onto itself, an inversion
//        turns it about its first note ...) and put the result in the same line as plain notes.  place: right after the selection (default),
//        at the end of the line, in place of the selection, or at arrangement tick `at`.  join: the new phrase is moved by whole SCALE STEPS so its
//        first note lands `steps` steps from the last note before it (0 = the same note, 1 = the next step up, -1 = down), keeping its own accidentals.
// (velocity: `vel` sets them all to one value, `dVel` moves each by the same amount, both clamped to 1-127)
// If a note would land before the voice's own start, the voice is moved EARLIER by whole bars (its entryBar drops, every note keeps
// its sounding position); at bar 1 there is nowhere earlier, so it is clamped.  -> {voice (a new object), select: [ids]}
function editHandNotes(voice, ev, ctx) {
  if (voice.kind !== 'notes') throw new Error('Only hand-edited voices can be edited');
  var v = JSON.parse(JSON.stringify(voice)), notes = v.notes, bt = ctx.barTicks, select = [];
  var entryOff = Math.round((v.entryBar - 1) * bt), toLocal = function (tick) { return Math.round(tick - (ctx.shiftTicks || 0) - entryOff); };
  var valid = function (id) { return id >= 0 && id < notes.length && notes[id]; };
  var ids = (ev.ids || []).filter(valid);
  if (ev.type === 'add') {
    notes.push({ p: Math.max(0, Math.min(127, Math.round(ev.pitch))), s: toLocal(ev.start), d: Math.max(1, Math.round(ev.dur)), v: Math.max(1, Math.min(127, Math.round(ev.vel || 90))) });
    select = [notes.length - 1];
  } else if (ev.type === 'move') {
    ids.forEach(function (i) { notes[i].s += Math.round(ev.dTick || 0); notes[i].p = Math.max(0, Math.min(127, notes[i].p + Math.round(ev.dPitch || 0))); }); select = ids;
  } else if (ev.type === 'resize') {
    ids.forEach(function (i) { notes[i].d = Math.max(1, notes[i].d + Math.round(ev.dDur || 0)); }); select = ids;
  } else if (ev.type === 'velocity') {
    if (ev.set) {   // a velocity for each named note (a drawn ramp)
      Object.keys(ev.set).forEach(function (k) { var i = +k; if (valid(i)) { notes[i].v = Math.max(1, Math.min(127, Math.round(ev.set[k]))); select.push(i); } });
    } else {
      ids.forEach(function (i) { notes[i].v = Math.max(1, Math.min(127, Math.round(ev.dVel !== undefined ? notes[i].v + ev.dVel : ev.vel))); }); select = ids;
    }
  } else if (ev.type === 'quantize') {   // snap starts to a grid of `grid` ticks (measured on the arrangement's bar lines), `strength` 0-1 of the way
    var qg = Math.max(1, Math.round(ev.grid)), qs = ev.strength === undefined ? 1 : Math.max(0, Math.min(1, ev.strength)), qo = entryOff + (ctx.shiftTicks || 0);
    ids.forEach(function (i) {
      var n = notes[i], a0 = n.s + qo, a1 = Math.round(a0 + (Math.round(a0 / qg) * qg - a0) * qs);
      if (ev.durations) { var e0 = a0 + n.d, e1 = Math.round(e0 + (Math.round(e0 / qg) * qg - e0) * qs); n.d = e1 > a1 ? e1 - a1 : Math.max(1, Math.round(qg * qs) || 1); }
      n.s = a1 - qo;
    }); select = ids;
  } else if (ev.type === 'swing') {      // delay the off-beat cells: ratio 0.5 = straight, 0.667 = triplet swing.  Only notes already near an off-beat cell move.
    var sg = Math.max(1, Math.round(ev.grid)), ratio = Math.max(0.5, Math.min(0.8, ev.ratio === undefined ? 0.667 : ev.ratio)), so = entryOff + (ctx.shiftTicks || 0), sd = Math.round((ratio - 0.5) * 2 * sg);
    ids.forEach(function (i) { var a = notes[i].s + so, k = Math.round(a / sg); if (k % 2 !== 0 && Math.abs(a - k * sg) <= sg / 4) notes[i].s += sd; }); select = ids;
  } else if (ev.type === 'transform') {
    if (!ctx.key) throw new Error('A key is needed to transform notes (the recipe\'s key)');
    var tsel = ids.filter(function (id, k, arr) { return arr.indexOf(id) === k; }).sort(function (a, b) { return (notes[a].s - notes[b].s) || (notes[a].p - notes[b].p); });   // the selection is a set: a repeated id is one note
    if (tsel.length) {
      var tt0 = Math.min.apply(null, tsel.map(function (i) { return notes[i].s; })), tt1 = Math.max.apply(null, tsel.map(function (i) { return notes[i].s + notes[i].d; })), span = Math.max(1, tt1 - tt0);
      var seg = tsel.map(function (i) { return { pitch: notes[i].p, startTick: notes[i].s - tt0, durTicks: notes[i].d, velocity: notes[i].v, channel: 0 }; });
      var tki = keyInfo(ctx.key), sortedSeg = sortNotes(seg);
      var res = applyChain(sortedSeg, span, ev.chain || [], { ki: tki, ppq: ctx.ppq || 480, barTicks: bt, anchor: sortedSeg[0].pitch }, 'transform');   // throws on an unknown step
      var place = ev.place || 'after', allEnd = notes.reduce(function (m, n) { return Math.max(m, n.s + n.d); }, 0);
      var at = place === 'replace' ? tt0 : place === 'end' ? allEnd : place === 'at' ? toLocal(ev.at) : tt1;
      var gone = place === 'replace' ? tsel.slice().sort(function (a, b) { return b - a; }) : [];
      var anchor = null;   // the note the new phrase continues from: the top note at the last onset before `at`
      notes.forEach(function (n, i) { if (gone.indexOf(i) >= 0 || n.s >= at) return; if (!anchor || n.s > anchor.s || (n.s === anchor.s && n.p > anchor.p)) anchor = n; });
      var out = res.notes.map(function (n) { return cn(n); });
      if (ev.join && anchor && out.length) {
        var steps = Math.round(ev.join.steps || 0), firstT = out[0].startTick, top = out.filter(function (n) { return n.startTick === firstT; }).reduce(function (m, n) { return n.pitch > m.pitch ? n : m; }, out[0]);
        var delta = degOf(anchor.p === undefined ? top : { pitch: anchor.p }, tki).abs + steps - degOf(top, tki).abs;
        out = out.map(function (n) { var c = cn(n); shiftNote(c, n, delta, 'diatonic', tki); return c; });
      }
      gone.forEach(function (i) { notes.splice(i, 1); });
      select = [];
      out.forEach(function (n) {
        var pitch = n.pitch; while (pitch < 0) pitch += 12; while (pitch > 127) pitch -= 12;
        notes.push({ p: pitch, s: at + n.startTick, d: Math.max(1, n.durTicks), v: Math.max(1, Math.min(127, n.velocity)) }); select.push(notes.length - 1);
      });
    }
  } else if (ev.type === 'humanize') {   // a little random loudness and timing; seeded, and the result is stored as plain notes
    var hr = mulberry32((ev.seed >>> 0) || 1), hv = Math.abs(ev.vel || 0), ht = Math.abs(ev.time || 0);
    ids.forEach(function (i) { var r1 = hr(), r2 = hr(); if (hv) notes[i].v = Math.max(1, Math.min(127, notes[i].v + Math.round((r1 - 0.5) * 2 * hv))); if (ht) notes[i].s += Math.round((r2 - 0.5) * 2 * ht); }); select = ids;
  } else if (ev.type === 'paste') {
    (ev.notes || []).forEach(function (n) {
      notes.push({ p: Math.max(0, Math.min(127, Math.round(n.pitch))), s: toLocal(n.start), d: Math.max(1, Math.round(n.dur)), v: Math.max(1, Math.min(127, Math.round(n.vel || 90))) });
      select.push(notes.length - 1);
    });
  } else if (ev.type === 'delete') {
    ids.slice().sort(function (a, b) { return b - a; }).forEach(function (i, k, arr) { if (k === 0 || arr[k - 1] !== i) notes.splice(i, 1); }); select = [];
  } else throw new Error('Unknown edit: ' + ev.type);
  var minS = notes.reduce(function (m, n) { return Math.min(m, n.s); }, Infinity);
  if (minS < 0) {
    var need = Math.ceil(-minS / bt), avail = Math.max(0, Math.floor(v.entryBar - 1 + 1e-9)), use = Math.min(need, avail);
    if (use > 0) { notes.forEach(function (n) { n.s += use * bt; }); v.entryBar -= use; }
    notes.forEach(function (n) { if (n.s < 0) n.s = 0; });
  }
  return { voice: v, select: select };
}

// Parallel harmony (Kubik's span process): n voices at a fixed distance in SCALE STEPS from the melody, so in a pentatonic scale
// the "thirds" are pentatonic thirds.  They are ordinary derived voices (a diatonic transpose each), so they stay editable.
//   opts: {key, source, distance (2 = thirds, 3 = fourths, 4 = fifths ...), voices, direction 'below'|'above', doubling (add the octave), program, firstChannel, volume, idPrefix, name}
var STEP_NAMES = { 1: '2nd', 2: '3rd', 3: '4th', 4: '5th', 5: '6th', 6: '7th', 7: 'octave' };
function makeParallel(opts) {
  var ki = keyInfo(opts.key), dist = Math.max(1, Math.round(opts.distance || 2)), n = Math.max(1, Math.round(opts.voices || 1)), sign = opts.direction === 'above' ? 1 : -1, out = [], ch = opts.firstChannel || 2, k;
  function add(steps, label) {
    out.push({ id: (opts.idPrefix || 'par') + (out.length + 1), name: label, source: opts.source || 'theme', chain: [{ type: 'transpose', params: { steps: steps, mode: 'diatonic' } }], entryBar: 1,
               program: opts.program === undefined ? null : opts.program, channel: ch++, volume: opts.volume === undefined ? 100 : opts.volume });
  }
  for (k = 1; k <= n; k++) add(sign * dist * k, (opts.name || 'Parallel') + ' ' + (STEP_NAMES[dist * k] || (dist * k + 1) + 'th') + ' ' + (opts.direction === 'above' ? 'above' : 'below'));
  if (opts.doubling) add(sign * ki.N, (opts.name || 'Parallel') + ' octave ' + (opts.direction === 'above' ? 'above' : 'below'));
  return out;
}
// what kind of interval does a distance give, and does the rule set mind?  -> {interval, perfect, note}
function parallelInfo(distance, N, ruleSet, steps) {
  var perfectSteps = { 3: 'fourth', 4: 'fifth' }; perfectSteps[N] = 'octave';
  var d = distance % N === 0 ? N : distance % N, name = perfectSteps[d] || (STEP_NAMES[d] || (d + 1) + 'th'), perfect = !!perfectSteps[d] && N === 7, semis = null;
  if (steps && steps.length === N) {   // name the interval from the scale's REAL semitone distances (a 5-note scale has no diatonic "third")
    var counts = {}, total = 0, i;
    for (i = 0; i < N; i++) {
      var hi = steps[i], j = i - distance, lo = steps[((j % N) + N) % N] + 12 * Math.floor(j / N), iv = hi - lo;
      counts[iv] = (counts[iv] || 0) + 1; total++;
    }
    semis = Object.keys(counts).map(Number).sort(function (a, b) { return a - b; });
    var NAME_OF = { 0: 'unison', 1: 'second', 2: 'second', 3: 'third', 4: 'third', 5: 'fourth', 6: 'tritone', 7: 'fifth', 8: 'sixth', 9: 'sixth', 10: 'seventh', 11: 'seventh', 12: 'octave' };
    var common = semis.reduce(function (best, k) { return counts[k] > (counts[best] || 0) ? k : best; }, semis[0]), pc = 0;
    semis.forEach(function (k) { if (k % 12 === 5 || k % 12 === 7 || k % 12 === 0) pc += counts[k]; });
    name = NAME_OF[common % 13 === common ? common : common % 12] || name; perfect = pc / total >= 0.5;
  }
  var note = perfect ? (ruleSet === 'chorale-strict' ? 'parallel ' + name + 's are forbidden under Chorale-strict' : ruleSet === 'organum-parallel' ? 'parallel ' + name + 's are the point of Organum' : 'parallel ' + name + 's are allowed under Free') : '';
  return { interval: name, perfect: perfect, note: note, semitones: semis };
}

// Canon / imitation preset: `voices` followers, each entering `offsetBars` later than the last,
// each shifted `steps` scale steps from its predecessor's line (running its own chain too).
function makeCanon(opts) {
  var out = [], n = opts.voices || 2, prev = 'theme';
  for (var i = 1; i <= n; i++) {
    var id = (opts.idPrefix || 'canon') + i;
    out.push({ id: id, name: (opts.name || 'Canon') + ' ' + i, source: 'theme',
               chain: [{ type: 'transpose', params: { steps: (opts.steps || 0) * i, mode: opts.mode || 'diatonic' } }]
                        .concat(opts.chain || []),
               entryBar: (opts.firstEntryBar || 1) + (opts.offsetBars || 2) * i,
               program: opts.program === undefined ? null : opts.program, channel: (opts.firstChannel || 2) + i - 1,
               volume: opts.volume === undefined ? 100 : opts.volume });
    prev = id;
  }
  return out;
}

// ---------------------------------------------------------------------------
// Reproducibility helpers
// ---------------------------------------------------------------------------
function sha256Hex(bytes) {   // pure JS, synchronous; bytes = Uint8Array | ArrayBuffer
  var u = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
  var K = new Uint32Array([
    0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
    0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
    0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
    0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]);
  var H = new Uint32Array([0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]);
  var l = u.length, padLen = ((l + 9 + 63) >> 6) << 6, m = new Uint8Array(padLen);
  m.set(u); m[l] = 0x80;
  var bits = l * 8, dv = new DataView(m.buffer);
  dv.setUint32(padLen - 8, Math.floor(bits / 0x100000000)); dv.setUint32(padLen - 4, bits >>> 0);
  var w = new Uint32Array(64);
  function rr(x, n) { return (x >>> n) | (x << (32 - n)); }
  for (var o = 0; o < padLen; o += 64) {
    for (var i = 0; i < 16; i++) w[i] = dv.getUint32(o + i * 4);
    for (i = 16; i < 64; i++) {
      var s0 = rr(w[i-15],7) ^ rr(w[i-15],18) ^ (w[i-15] >>> 3), s1 = rr(w[i-2],17) ^ rr(w[i-2],19) ^ (w[i-2] >>> 10);
      w[i] = (w[i-16] + s0 + w[i-7] + s1) >>> 0;
    }
    var a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
    for (i = 0; i < 64; i++) {
      var S1 = rr(e,6) ^ rr(e,11) ^ rr(e,25), ch = (e & f) ^ (~e & g), t1 = (h + S1 + ch + K[i] + w[i]) >>> 0;
      var S0 = rr(a,2) ^ rr(a,13) ^ rr(a,22), mj = (a & b) ^ (a & c) ^ (b & c), t2 = (S0 + mj) >>> 0;
      h=g; g=f; f=e; e=(d + t1) >>> 0; d=c; c=b; b=a; a=(t1 + t2) >>> 0;
    }
    H[0]+=a; H[1]+=b; H[2]+=c; H[3]+=d; H[4]+=e; H[5]+=f; H[6]+=g; H[7]+=h;
  }
  return Array.prototype.map.call(H, function (x) { return ('00000000' + x.toString(16)).slice(-8); }).join('');
}

function canonicalJson(v) {   // sorted keys, no whitespace: the same recipe always serialises the same way
  if (v === null || typeof v !== 'object') return JSON.stringify(v);
  if (Array.isArray(v)) return '[' + v.map(canonicalJson).join(',') + ']';
  return '{' + Object.keys(v).sort().map(function (k) { return JSON.stringify(k) + ':' + canonicalJson(v[k]); }).join(',') + '}';
}
function utf8Bytes(str) {   // pure UTF-8 encoder: no TextEncoder or Buffer, so the engine runs anywhere
  var out = [];
  for (var i = 0; i < str.length; i++) {
    var c = str.charCodeAt(i);
    if (c >= 0xD800 && c <= 0xDBFF && i + 1 < str.length) {   // surrogate pair -> one code point
      var d = str.charCodeAt(i + 1);
      if (d >= 0xDC00 && d <= 0xDFFF) { c = 0x10000 + ((c - 0xD800) << 10) + (d - 0xDC00); i++; }
    }
    if (c < 0x80) out.push(c);
    else if (c < 0x800) out.push(0xC0 | (c >> 6), 0x80 | (c & 63));
    else if (c < 0x10000) out.push(0xE0 | (c >> 12), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
    else out.push(0xF0 | (c >> 18), 0x80 | ((c >> 12) & 63), 0x80 | ((c >> 6) & 63), 0x80 | (c & 63));
  }
  return new Uint8Array(out);
}
function recipeDigest(recipe) { return sha256Hex(utf8Bytes(canonicalJson(normalizeRecipe(recipe)))); }
function mulberry32(seed) {   // seeded PRNG for later phases (harmony tie-breaks, embellishment)
  var a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0; var t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// ---------------------------------------------------------------------------
// Description: fingerprint + key estimate
// ---------------------------------------------------------------------------
function fingerprint(notes, length, ppq, barTicks) {
  var s = sortNotes(notes), n = s.length;
  var f = { noteCount: n, lengthTicks: length, lengthBars: length / barTicks, lengthBeats: length / ppq };
  if (!n) return f;
  var lo = Infinity, hi = -Infinity, sum = 0, pc = new Array(12).fill(0), onsets = {};
  s.forEach(function (x) {
    lo = Math.min(lo, x.pitch); hi = Math.max(hi, x.pitch); sum += x.pitch; pc[x.pitch % 12] += x.durTicks; onsets[x.startTick] = Math.max(onsets[x.startTick] === undefined ? -1 : onsets[x.startTick], x.pitch);
  });
  var times = Object.keys(onsets).map(Number).sort(function (a, b) { return a - b; });
  var top = times.map(function (t) { return onsets[t]; }), hist = {}, steps = 0;
  for (var i = 1; i < top.length; i++) { var d = Math.abs(top[i] - top[i-1]); hist[d] = (hist[d] || 0) + 1; if (d <= 2) steps++; }
  f.lowest = lo; f.highest = hi; f.rangeSemitones = hi - lo; f.meanPitch = Math.round(sum / n * 100) / 100;
  f.firstPitch = top[0]; f.lastPitch = top[top.length - 1];
  f.onsetCount = times.length; f.notesPerBeat = Math.round(n / f.lengthBeats * 1000) / 1000;
  f.onsetsPerBeat = Math.round(times.length / f.lengthBeats * 1000) / 1000;
  f.intervalHistogram = hist;                                   // |semitones| between successive top notes
  f.stepwiseFraction = top.length > 1 ? Math.round(steps / (top.length - 1) * 1000) / 1000 : 0;
  f.pitchClassWeight = pc.map(function (x) { return Math.round(x / (pc.reduce(function (a, b) { return a + b; }, 0) || 1) * 1000) / 1000; });
  f.tonalCenterPc = pc.indexOf(Math.max.apply(null, pc));
  return f;
}
function describeFingerprint(f) {
  if (!f.noteCount) return 'empty';
  return f.lengthBars.toFixed(2) + ' bars, ' + f.noteCount + ' notes, range ' + f.rangeSemitones + ' st (' + f.lowest + '-' + f.highest +
         '), mean ' + f.meanPitch + ', ' + f.onsetsPerBeat + ' onsets/beat, ' + Math.round(f.stepwiseFraction * 100) + '% stepwise';
}

var KS_MAJ = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88];
var KS_MIN = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17];
function estimateKey(notes) {   // Krumhansl-Schmuckler, duration-weighted -> {tonic, scale, score}
  var pc = new Array(12).fill(0); notes.forEach(function (n) { pc[n.pitch % 12] += n.durTicks; });
  function corr(a, b) {
    var ma = a.reduce(function (x, y) { return x + y; }) / 12, mb = b.reduce(function (x, y) { return x + y; }) / 12, num = 0, da = 0, db = 0;
    for (var i = 0; i < 12; i++) { num += (a[i]-ma)*(b[i]-mb); da += (a[i]-ma)*(a[i]-ma); db += (b[i]-mb)*(b[i]-mb); }
    return da && db ? num / Math.sqrt(da * db) : 0;
  }
  var best = null;
  for (var t = 0; t < 12; t++) {
    var rot = pc.map(function (_, i) { return pc[(i + t) % 12]; });
    [['major', KS_MAJ], ['minor', KS_MIN]].forEach(function (m) {
      var sc = corr(rot, m[1]); if (!best || sc > best.score) best = { tonic: PC_NAMES[t], scale: m[0], score: sc };
    });
  }
  return best;
}

// Build a fresh recipe skeleton from a parsed file (hash supplied by the caller from the file bytes)
function makeRecipe(o) {
  return normalizeRecipe({
    source: { file: o.file, sha256: o.sha256 || null, tracks: o.tracks, bars: o.bars },
    key: o.key, ruleSet: o.ruleSet, seed: o.seed, voices: o.voices
  });
}

var api = {
  ENGINE: ENGINE, RECIPE_VERSION: RECIPE_VERSION, SCALES: SCALES, PC_NAMES: PC_NAMES, RULE_SETS: RULE_SETS,
  DEFAULT_WEIGHTS: DEFAULT_WEIGHTS, TRANSFORMS: TRANSFORMS,
  keyInfo: keyInfo, toDegree: toDegree, fromDegree: fromDegree, tonicToPc: tonicToPc,
  makeBarMap: makeBarMap, barTicksFor: barTicksFor, keySigEventFor: keySigEventFor,
  sortNotes: sortNotes, extractTheme: extractTheme, extractWindow: extractWindow, mergeBacking: mergeBacking, applyChain: applyChain, normalizeStep: normalizeStep,
  normalizeRecipe: normalizeRecipe, validateRecipe: validateRecipe, resolveVoices: resolveVoices,
  lineageTree: lineageTree, assemble: assemble, build: build, freezeVoice: freezeVoice, editHandNotes: editHandNotes, makeParallel: makeParallel, parallelInfo: parallelInfo, generateDrums: generateDrums, drumsFor: drumsFor, styleForMeter: styleForMeter, DRUM_STYLES: DRUM_STYLES, GMD: GMD, makeCanon: makeCanon, makeRecipe: makeRecipe,
  sha256Hex: sha256Hex, utf8Bytes: utf8Bytes, canonicalJson: canonicalJson, recipeDigest: recipeDigest, mulberry32: mulberry32,
  fingerprint: fingerprint, describeFingerprint: describeFingerprint, estimateKey: estimateKey
};
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.MccfTheory = api;

})(typeof window !== 'undefined' ? window : this);
