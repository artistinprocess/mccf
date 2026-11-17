/* MCCF V5 Ambient: serial / twelve-tone support.
 *
 * Self-contained.  Does not change mccf_theory.js.  Provides:
 *   - tone rows: parse, generate (seeded; optional all-interval and no-triad rules), take from a theme
 *   - the four row forms (P, I, R, RI) at any transposition, the 12x12 matrix, interval series
 *   - a serial line generator (row forms -> notes, with rhythm, register and dynamics options)
 *   - a serial rule scan (is each 12-note statement a legal row form; repeated notes; triad outlines; octave leaps)
 *   - a 'chromatic' scale (no tonic) added to MccfTheory.SCALES so a recipe can have no tonal centre
 *
 * Form labels are RELATIVE to the row as written: P0 is the row, P5 is the row up five semitones,
 * I0 is the inversion starting on the row's first note, I5 starts five semitones above it.
 * R and RI are the retrogrades of P and I at the same transposition.
 *
 * Everything that looks random is drawn from a seeded generator, so the same settings give the same notes.
 */
(function (root) {
  'use strict';

  var NAMES = ['C', 'C#', 'D', 'Eb', 'E', 'F', 'F#', 'G', 'Ab', 'A', 'Bb', 'B'];
  var PCS = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
  function mod12(x) { return ((x % 12) + 12) % 12; }

  // ---------- seeded generator (mulberry32) ----------
  function rng(seed) {
    var a = (seed >>> 0) || 1;
    return function () {
      a = (a + 0x6D2B79F5) >>> 0;
      var t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function shuffled(arr, rnd) {
    var a = arr.slice();
    for (var i = a.length - 1; i > 0; i--) { var j = Math.floor(rnd() * (i + 1)); var t = a[i]; a[i] = a[j]; a[j] = t; }
    return a;
  }

  // ---------- rows ----------
  // Two published rows are included as starting points (pitch-class facts, not score text).
  var PRESETS = [
    { id: 'chromatic', name: 'Chromatic scale (0 1 2 … 11)', row: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11] },
    { id: 'op25', name: 'Schoenberg, Suite Op. 25 (E F G Db Gb Eb Ab D B C A Bb)', row: [4, 5, 7, 1, 6, 3, 8, 2, 11, 0, 9, 10] },
    { id: 'berg', name: 'Berg, Violin Concerto (G Bb D F# A C E G# B C# Eb F)', row: [7, 10, 2, 6, 9, 0, 4, 8, 11, 1, 3, 5] }
  ];

  function isRow(row) {
    if (!row || row.length !== 12) return false;
    var seen = {}; for (var i = 0; i < 12; i++) { var p = row[i]; if (p !== (p | 0) || p < 0 || p > 11 || seen[p]) return false; seen[p] = true; }
    return true;
  }
  // "0 1 2 …", "C Db E …", "T E" (ten, eleven) -> {row} or {error}
  function parseRow(text) {
    var toks = String(text || '').split(/[\s,;]+/).filter(Boolean), out = [];
    for (var i = 0; i < toks.length; i++) {
      var t = toks[i], v;
      if (/^\d+$/.test(t)) v = parseInt(t, 10);
      else if (/^[tT]$/.test(t)) v = 10;
      else if (/^[eE]$/.test(t) && toks.length && /\d/.test(text)) v = 11;     // 'E' is the number 11 only in a numeric row
      else {
        var m = /^([A-Ga-g])([#b]?)$/.exec(t);
        if (!m) return { error: 'cannot read "' + t + '" (use 0-11 or note names such as C, Db, F#)' };
        v = PCS[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0);
      }
      if (v < 0 || v > 11) { if (v === 12) v = 0; else return { error: '"' + t + '" is outside 0-11' }; }
      out.push(mod12(v));
    }
    if (out.length !== 12) return { error: 'a row has 12 notes; this has ' + out.length };
    var seen = {}, dup = [];
    out.forEach(function (p) { if (seen[p]) dup.push(NAMES[p]); seen[p] = true; });
    if (dup.length) { var miss = []; for (var p = 0; p < 12; p++) if (!seen[p]) miss.push(NAMES[p]); return { error: 'repeated: ' + dup.join(', ') + '; missing: ' + miss.join(', ') }; }
    return { row: out };
  }
  function rowText(row) { return row.map(function (p) { return NAMES[p]; }).join(' '); }

  function intervals(row) { var o = []; for (var i = 1; i < 12; i++) o.push(mod12(row[i] - row[i - 1])); return o; }
  function isAllInterval(row) {
    var seen = {}; var iv = intervals(row);
    for (var i = 0; i < iv.length; i++) { if (seen[iv[i]]) return false; seen[iv[i]] = true; }
    return true;                                   // 11 distinct values of 1..11
  }
  function hasTriad(a, b, c) {
    var s = [mod12(a), mod12(b), mod12(c)];
    for (var r = 0; r < 3; r++) {
      var x = s[r], y = mod12(s[(r + 1) % 3] - x), z = mod12(s[(r + 2) % 3] - x);
      if ((y === 4 && z === 7) || (y === 7 && z === 4) || (y === 3 && z === 7) || (y === 7 && z === 3)) return true;
    }
    return false;
  }
  function triadsIn(row) { var n = 0; for (var i = 2; i < row.length; i++) if (hasTriad(row[i - 2], row[i - 1], row[i])) n++; return n; }

  // Seeded row generator.  allInterval: all 11 intervals different.  noTriads: no three neighbours spelling a major or minor triad.
  function generateRow(o) {
    o = o || {};
    var rnd = rng(o.seed === undefined ? 1 : o.seed), nodes = 0, LIMIT = 300000, best = null;
    var row = [], used = {}, ivUsed = {};
    function dfs() {
      if (nodes++ > LIMIT) return false;
      if (row.length === 12) return true;
      var cand = shuffled([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], rnd);
      for (var k = 0; k < cand.length; k++) {
        var p = cand[k]; if (used[p]) continue;
        var iv = row.length ? mod12(p - row[row.length - 1]) : -1;
        if (o.allInterval && row.length && ivUsed[iv]) continue;
        if (o.noTriads && row.length >= 2 && hasTriad(row[row.length - 2], row[row.length - 1], p)) continue;
        row.push(p); used[p] = true; if (iv >= 0) ivUsed[iv] = true;
        if (dfs()) return true;
        row.pop(); used[p] = false; if (iv >= 0) ivUsed[iv] = false;
      }
      return false;
    }
    if (dfs()) return { row: row.slice(), note: (o.allInterval ? 'all-interval' : 'random') + (o.noTriads ? ', no triads' : '') };
    return { row: shuffled([0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11], rnd), note: 'no row met the rules in the search limit; this is a plain random row' };
  }

  // The first twelve different pitch classes of a theme, in order of first appearance.
  // If the theme has fewer than twelve, the missing ones are added in seeded random order.
  function rowFromTheme(notes, seed) {
    var seen = {}, row = [];
    (notes || []).slice().sort(function (a, b) { return (a.startTick - b.startTick) || (a.pitch - b.pitch); }).forEach(function (n) {
      var p = mod12(n.pitch); if (!seen[p]) { seen[p] = true; row.push(p); }
    });
    var own = row.length, rest = [];
    for (var p = 0; p < 12; p++) if (!seen[p]) rest.push(p);
    shuffled(rest, rng(seed === undefined ? 1 : seed)).forEach(function (p) { row.push(p); });
    return { row: row, own: own, note: own >= 12 ? 'all twelve from the theme' : own + ' from the theme, ' + (12 - own) + ' added' };
  }

  // ---------- forms and matrix ----------
  // type: 'P' | 'I' | 'R' | 'RI'; n = semitones above the row as written
  function form(row, type, n) {
    var t = mod12(n || 0), base = row[0], out = [];
    for (var i = 0; i < 12; i++) {
      var inv = (type === 'I' || type === 'RI');
      out.push(mod12((inv ? base - (row[i] - base) : row[i]) + t));
    }
    if (type === 'R' || type === 'RI') out.reverse();
    return out;
  }
  function parseForms(text) {          // "P0 I3 R0 RI7" -> [{type,n}] or {error}
    var toks = String(text || '').split(/[\s,;]+/).filter(Boolean), out = [];
    for (var i = 0; i < toks.length; i++) {
      var m = /^(RI|P|I|R)(\d{1,2})$/i.exec(toks[i]);
      if (!m || +m[2] > 11) return { error: 'cannot read "' + toks[i] + '" (use P0, I3, R0, RI7 … the number is 0-11)' };
      out.push({ type: m[1].toUpperCase(), n: +m[2] });
    }
    if (!out.length) return { error: 'name at least one form, such as P0' };
    return { forms: out };
  }
  function formLabel(f) { return f.type + f.n; }
  // matrix[k][j]: row k is P at transposition (I0[k]-row[0]); column j is I at transposition (row[j]-row[0])
  function matrix(row) {
    var I0 = form(row, 'I', 0), m = [];
    for (var k = 0; k < 12; k++) {
      var t = mod12(I0[k] - row[0]), line = form(row, 'P', t);
      m.push({ label: 'P' + t, notes: line });
    }
    var cols = []; for (var j = 0; j < 12; j++) cols.push('I' + mod12(row[j] - row[0]));
    return { rows: m, cols: cols };
  }
  // which labelled form (if any) a 12-note sequence is
  function identify(row, seq) {
    var types = ['P', 'I', 'R', 'RI'];
    for (var t = 0; t < 4; t++) for (var n = 0; n < 12; n++) {
      var f = form(row, types[t], n), ok = true;
      for (var i = 0; i < 12; i++) if (f[i] !== seq[i]) { ok = false; break; }
      if (ok) return types[t] + n;
    }
    return null;
  }

  // ---------- line generator ----------
  // o: row, forms [{type,n}], count (how many statements; the forms cycle), ppq, barTicks,
  //    unit ('quarter','eighth','sixteenth','half','beat' = ppq), rhythm {mode: even|cell|theme|random, cell:[…], theme:[ticks…], seed},
  //    register {low, high, placement: closest|wide|fixed, maxLeap, start}, velocity {base, accent},
  //    restAfter (units of silence after each statement), seed
  var UNITS = { half: 2, quarter: 1, eighth: 0.5, sixteenth: 0.25, triplet: 1 / 3 };
  function parseCell(text) {
    var toks = String(text || '').split(/[\s,;]+/).filter(Boolean), out = [];
    for (var i = 0; i < toks.length; i++) { var v = parseFloat(toks[i]); if (!isFinite(v) || v === 0 || Math.abs(v) > 32) return { error: 'cannot read "' + toks[i] + '" (use numbers of units; a minus sign makes a rest)' }; out.push(v); }
    if (!out.length) return { error: 'write at least one length, such as 1 1 2' };
    return { cell: out };
  }
  function makeLine(o) {
    var rnd = rng(o.seed === undefined ? 1 : o.seed), rr = rng((o.seed === undefined ? 1 : o.seed) + 7919);
    var ppq = o.ppq || 480, unit = Math.max(1, Math.round(ppq * (UNITS[o.unit] || 1)));
    var reg = Object.assign({ low: 48, high: 84, placement: 'closest', maxLeap: 14, start: 60 }, o.register || {});
    var vel = Object.assign({ base: 70, accent: 12 }, o.velocity || {});
    var rhy = Object.assign({ mode: 'even', cell: [1], theme: [] }, o.rhythm || {});
    var forms = o.forms && o.forms.length ? o.forms : [{ type: 'P', n: 0 }];
    var count = Math.max(1, Math.min(48, o.count || forms.length));
    var notes = [], tick = 0, prev = null, idx = 0, statements = [];
    function nextDur() {                                   // -> units*ticks, negative = rest
      var d;
      if (rhy.mode === 'cell') { d = rhy.cell[idx % rhy.cell.length] * unit; }
      else if (rhy.mode === 'theme' && rhy.theme.length) { d = rhy.theme[idx % rhy.theme.length]; }
      else if (rhy.mode === 'random') { var pool = rhy.cell && rhy.cell.length > 1 ? rhy.cell : [1, 1, 2, 3, 0.5]; d = pool[Math.floor(rr() * pool.length)] * unit; }
      else d = unit;
      return Math.round(d);
    }
    function place(pc) {
      var cands = []; for (var p = pc; p <= 127; p += 12) if (p >= reg.low && p <= reg.high) cands.push(p);
      if (!cands.length) { var q = reg.low + mod12(pc - reg.low); cands = [Math.min(127, q)]; }
      if (reg.placement === 'fixed') { return cands[0]; }
      var ref = prev === null ? reg.start : prev;
      if (reg.placement === 'wide' && prev !== null) {
        var ok = cands.filter(function (c) { return Math.abs(c - prev) >= 7 && Math.abs(c - prev) <= reg.maxLeap + 12; });
        var pool = ok.length ? ok : cands;
        return pool[Math.floor(rnd() * pool.length)];
      }
      var best = cands[0];
      cands.forEach(function (c) { if (Math.abs(c - ref) < Math.abs(best - ref)) best = c; });
      return best;
    }
    for (var s = 0; s < count; s++) {
      var f = forms[s % forms.length], seq = form(o.row, f.type, f.n), first = idx;
      for (var i = 0; i < 12; i++) {
        var d = nextDur(); idx++;
        if (d < 0) { tick += -d; i--; if (idx - first > 400) break; continue; }       // a rest does not use a pitch
        var p = place(seq[i]); prev = p;
        notes.push({ p: p, s: tick, d: Math.max(1, Math.round(d * 0.95)), v: Math.max(1, Math.min(127, vel.base + (i === 0 ? vel.accent : 0))) });
        tick += d;
      }
      if (o.restAfter > 0) tick += Math.round(o.restAfter * unit);
      statements.push({ form: formLabel(f), pcs: seq.slice(), firstNote: notes.length - 12, endTick: tick });
    }
    return { notes: notes, statements: statements, endTick: tick };
  }

  // ---------- serial rule scan ----------
  // notes: [{p,s,d,v}] in voice-local ticks.  o: row (or null: any 12-note set is accepted), barOffset (entry bar - 1), barTicks,
  //   allowRepeat (an immediate repeat of the same note does not count), flagTriads, flagOctaves, flagRepeatEarly
  function scan(notes, o) {
    o = o || {};
    var bt = o.barTicks || 1920, off = o.barOffset || 0;
    var seq = (notes || []).slice().sort(function (a, b) { return (a.s - b.s) || (a.p - b.p); });
    var viol = [], stmts = [], line = [], windows = [], cur = [], simult = 0;
    function bar(n) { return Math.floor(n.s / bt) + 1 + off; }
    for (var i = 0; i < seq.length; i++) {
      if (i && seq[i].s === seq[i - 1].s) simult++;
      // an immediate repeat inside a statement does not count as a new note; a note that starts the next statement always does
      if (o.allowRepeat && cur.length > 0 && cur.length < 12 && cur[cur.length - 1].p === seq[i].p) continue;
      line.push(seq[i]); cur.push(seq[i]);
      if (cur.length === 12) { windows.push(cur); cur = []; }
    }
    if (cur.length) windows.push(cur);
    if (simult) viol.push({ bar: bar(seq[0]), msg: simult + ' note(s) start together with another; this scan reads one line, so check chords by ear or scan each voice alone' });
    function closeWindow(w, partial) {
      var pcs = w.map(function (n) { return mod12(n.p); }), seen = {}, dups = [];
      pcs.forEach(function (p, k) { if (seen[p] !== undefined) dups.push({ p: p, at: k }); else seen[p] = k; });
      var st = { index: stmts.length + 1, bar: bar(w[0]), form: null, ok: true, partial: !!partial };
      if (dups.length) {
        st.ok = false;
        var miss = []; for (var p = 0; p < 12; p++) if (seen[p] === undefined) miss.push(NAMES[p]);
        viol.push({ bar: bar(w[dups[0].at]), msg: 'statement ' + st.index + (partial ? ' (unfinished)' : '') + ': ' + NAMES[dups[0].p] + ' comes again before all twelve notes have sounded' + (partial ? '' : '; missing ' + miss.join(', ')) });
      } else if (!partial && o.row) {
        st.form = identify(o.row, pcs);
        if (!st.form) { st.ok = false; viol.push({ bar: bar(w[0]), msg: 'statement ' + st.index + ' is a complete twelve-note set but not a form of the row (P, I, R or RI)' }); }
      } else if (!partial) st.form = 'set';
      if (partial && !dups.length) st.form = 'unfinished, ' + w.length + ' of 12';
      stmts.push(st);
    }
    windows.forEach(function (w) { closeWindow(w, w.length < 12); });
    if (o.flagTriads) for (var k = 2; k < line.length; k++) if (hasTriad(line[k - 2].p, line[k - 1].p, line[k].p))
      viol.push({ bar: bar(line[k]), msg: 'three neighbouring notes outline a major or minor triad (' + [line[k - 2], line[k - 1], line[k]].map(function (n) { return NAMES[mod12(n.p)]; }).join(' ') + '), which sounds tonal' });
    if (o.flagOctaves) for (var m = 1; m < line.length; m++) { var dv = Math.abs(line[m].p - line[m - 1].p); if (dv && dv % 12 === 0) viol.push({ bar: bar(line[m]), msg: 'octave leap between neighbouring notes (' + NAMES[mod12(line[m].p)] + ')' }); }
    viol.sort(function (a, b) { return a.bar - b.bar; });
    return { statements: stmts, violations: viol, noteCount: line.length };
  }

  // ---------- chromatic scale (no tonal centre) ----------
  function install(T) {
    if (T && T.SCALES && !T.SCALES.chromatic) T.SCALES.chromatic = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
  }

  var API = {
    NAMES: NAMES, PRESETS: PRESETS, UNITS: UNITS, rng: rng,
    isRow: isRow, parseRow: parseRow, rowText: rowText, intervals: intervals, isAllInterval: isAllInterval, triadsIn: triadsIn,
    generateRow: generateRow, rowFromTheme: rowFromTheme,
    form: form, parseForms: parseForms, formLabel: formLabel, matrix: matrix, identify: identify,
    parseCell: parseCell, makeLine: makeLine, scan: scan, install: install
  };
  if (typeof module !== 'undefined' && module.exports) module.exports = API;
  else { root.MccfSerial = API; if (root.MccfTheory) install(root.MccfTheory); }
})(typeof window !== 'undefined' ? window : this);
