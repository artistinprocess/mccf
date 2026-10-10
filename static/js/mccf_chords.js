/* ==========================================================================
 * mccf_chords.js — the chord dictionary (browser-free, no dependencies)
 * --------------------------------------------------------------------------
 *   QUALITIES         over 40 chord types: triads, sixths, sevenths, extensions, altered dominants
 *   parse(text, key)  "Am7", "F#m7b5", "C7(b9)", "Bb/D", "m7" (quality only), or a roman numeral
 *                     in a key: "V7", "ii65", "vii°7", "bVII", "I64"   ->  {ok, symbol, root, intervals, pcs, bass, inversion, ...}
 *   voice(chord, o)   a chord -> MIDI pitches: inversion, close / open / drop-2 spacing, optional bass note, a register to fit
 *   identify(pitches) the reverse: the chord names that fit a set of notes, best first
 *   list()            the dictionary grouped for a menu
 * Intervals are semitones above the root; 14 = the ninth, 17 = the eleventh, 21 = the thirteenth.
 * Exposes MccfChords (window global, and module.exports under Node).
 * ========================================================================== */
(function (root) {
'use strict';

// key: canonical suffix; aliases: other spellings people type (matched after normalising maj/min/dim/aug/sus/add case)
var Q = [
  // triads
  { key: 'maj',    suffix: '',        aliases: ['', 'M', 'maj', 'major'],                       iv: [0, 4, 7],              family: 'Triads',      name: 'major triad' },
  { key: 'min',    suffix: 'm',       aliases: ['m', 'min', 'minor', '-', 'mi'],                iv: [0, 3, 7],              family: 'Triads',      name: 'minor triad' },
  { key: 'dim',    suffix: 'dim',     aliases: ['dim', '°', 'o'],                               iv: [0, 3, 6],              family: 'Triads',      name: 'diminished triad' },
  { key: 'aug',    suffix: 'aug',     aliases: ['aug', '+'],                                    iv: [0, 4, 8],              family: 'Triads',      name: 'augmented triad' },
  { key: 'sus2',   suffix: 'sus2',    aliases: ['sus2'],                                        iv: [0, 2, 7],              family: 'Triads',      name: 'suspended second' },
  { key: 'sus4',   suffix: 'sus4',    aliases: ['sus4', 'sus'],                                 iv: [0, 5, 7],              family: 'Triads',      name: 'suspended fourth' },
  { key: '5',      suffix: '5',       aliases: ['5'],                                           iv: [0, 7],                 family: 'Triads',      name: 'power chord (root and fifth)' },
  // sixths
  { key: '6',      suffix: '6',       aliases: ['6', 'maj6'],                                   iv: [0, 4, 7, 9],           family: 'Sixths',      name: 'major sixth' },
  { key: 'm6',     suffix: 'm6',      aliases: ['m6', 'min6', '-6'],                            iv: [0, 3, 7, 9],           family: 'Sixths',      name: 'minor sixth' },
  { key: '6/9',    suffix: '6/9',     aliases: ['6/9', '69'],                                   iv: [0, 4, 7, 9, 14],       family: 'Sixths',      name: 'six-nine' },
  { key: 'm6/9',   suffix: 'm6/9',    aliases: ['m6/9', 'm69'],                                 iv: [0, 3, 7, 9, 14],       family: 'Sixths',      name: 'minor six-nine' },
  // sevenths
  { key: '7',      suffix: '7',       aliases: ['7', 'dom7'],                                   iv: [0, 4, 7, 10],          family: 'Sevenths',    name: 'dominant seventh' },
  { key: 'maj7',   suffix: 'maj7',    aliases: ['maj7', 'M7', 'Δ7', 'Δ', 'ma7', '△7', '△'],     iv: [0, 4, 7, 11],          family: 'Sevenths',    name: 'major seventh' },
  { key: 'm7',     suffix: 'm7',      aliases: ['m7', 'min7', '-7', 'mi7'],                     iv: [0, 3, 7, 10],          family: 'Sevenths',    name: 'minor seventh' },
  { key: 'mMaj7',  suffix: 'mMaj7',   aliases: ['mMaj7', 'mM7', 'minmaj7', 'mmaj7', '-Δ', '-Δ7', 'm(maj7)'], iv: [0, 3, 7, 11], family: 'Sevenths',   name: 'minor-major seventh' },
  { key: 'm7b5',   suffix: 'm7b5',    aliases: ['m7b5', 'ø', 'ø7', 'min7b5', 'm7(b5)', '-7b5'], iv: [0, 3, 6, 10],          family: 'Sevenths',    name: 'half-diminished seventh' },
  { key: 'dim7',   suffix: 'dim7',    aliases: ['dim7', '°7', 'o7'],                            iv: [0, 3, 6, 9],           family: 'Sevenths',    name: 'diminished seventh' },
  { key: '7sus4',  suffix: '7sus4',   aliases: ['7sus4', '7sus'],                               iv: [0, 5, 7, 10],          family: 'Sevenths',    name: 'seventh suspended fourth' },
  { key: '7#5',    suffix: '7#5',     aliases: ['7#5', '+7', 'aug7', '7+', '7aug'],             iv: [0, 4, 8, 10],          family: 'Sevenths',    name: 'augmented (dominant) seventh' },
  { key: 'maj7#5', suffix: 'maj7#5',  aliases: ['maj7#5', 'M7#5', 'Δ#5', 'maj7+'],              iv: [0, 4, 8, 11],          family: 'Sevenths',    name: 'major seventh sharp five' },
  { key: '7b5',    suffix: '7b5',     aliases: ['7b5'],                                         iv: [0, 4, 6, 10],          family: 'Sevenths',    name: 'seventh flat five' },
  // ninths, elevenths, thirteenths
  { key: 'add9',   suffix: 'add9',    aliases: ['add9', '2', 'add2'],                           iv: [0, 4, 7, 14],          family: 'Extended',    name: 'major add nine' },
  { key: 'madd9',  suffix: 'madd9',   aliases: ['madd9', 'm(add9)', 'madd2'],                   iv: [0, 3, 7, 14],          family: 'Extended',    name: 'minor add nine' },
  { key: '9',      suffix: '9',       aliases: ['9', 'dom9'],                                   iv: [0, 4, 7, 10, 14],      family: 'Extended',    name: 'dominant ninth' },
  { key: 'maj9',   suffix: 'maj9',    aliases: ['maj9', 'M9', 'Δ9'],                            iv: [0, 4, 7, 11, 14],      family: 'Extended',    name: 'major ninth' },
  { key: 'm9',     suffix: 'm9',      aliases: ['m9', 'min9', '-9'],                            iv: [0, 3, 7, 10, 14],      family: 'Extended',    name: 'minor ninth' },
  { key: '9sus4',  suffix: '9sus4',   aliases: ['9sus4', '9sus'],                               iv: [0, 5, 7, 10, 14],      family: 'Extended',    name: 'ninth suspended fourth' },
  { key: '11',     suffix: '11',      aliases: ['11'],                                          iv: [0, 4, 7, 10, 14, 17],  family: 'Extended',    name: 'dominant eleventh' },
  { key: 'm11',    suffix: 'm11',     aliases: ['m11', 'min11', '-11'],                         iv: [0, 3, 7, 10, 14, 17],  family: 'Extended',    name: 'minor eleventh' },
  { key: '13',     suffix: '13',      aliases: ['13', 'dom13'],                                 iv: [0, 4, 7, 10, 14, 21],  family: 'Extended',    name: 'dominant thirteenth' },
  { key: 'maj13',  suffix: 'maj13',   aliases: ['maj13', 'M13', 'Δ13'],                         iv: [0, 4, 7, 11, 14, 21],  family: 'Extended',    name: 'major thirteenth' },
  { key: 'm13',    suffix: 'm13',     aliases: ['m13', 'min13', '-13'],                         iv: [0, 3, 7, 10, 14, 21],  family: 'Extended',    name: 'minor thirteenth' },
  { key: 'maj7#11', suffix: 'maj7#11', aliases: ['maj7#11', 'M7#11', 'Δ#11', 'lyd'],            iv: [0, 4, 7, 11, 18],      family: 'Extended',    name: 'major seventh sharp eleven (Lydian)' },
  // altered dominants
  { key: '7b9',    suffix: '7b9',     aliases: ['7b9'],                                         iv: [0, 4, 7, 10, 13],      family: 'Altered',     name: 'dominant seventh flat nine' },
  { key: '7#9',    suffix: '7#9',     aliases: ['7#9'],                                         iv: [0, 4, 7, 10, 15],      family: 'Altered',     name: 'dominant seventh sharp nine' },
  { key: '7#11',   suffix: '7#11',    aliases: ['7#11'],                                        iv: [0, 4, 7, 10, 18],      family: 'Altered',     name: 'dominant seventh sharp eleven' },
  { key: '7b13',   suffix: '7b13',    aliases: ['7b13'],                                        iv: [0, 4, 7, 10, 20],      family: 'Altered',     name: 'dominant seventh flat thirteen' },
  { key: '9#11',   suffix: '9#11',    aliases: ['9#11'],                                        iv: [0, 4, 7, 10, 14, 18],  family: 'Altered',     name: 'ninth sharp eleven' },
  { key: '7#5b9',  suffix: '7#5b9',   aliases: ['7#5b9'],                                       iv: [0, 4, 8, 10, 13],      family: 'Altered',     name: 'seventh sharp five flat nine' },
  { key: '7#5#9',  suffix: '7#5#9',   aliases: ['7#5#9'],                                       iv: [0, 4, 8, 10, 15],      family: 'Altered',     name: 'seventh sharp five sharp nine' },
  { key: '7b5b9',  suffix: '7b5b9',   aliases: ['7b5b9'],                                       iv: [0, 4, 6, 10, 13],      family: 'Altered',     name: 'seventh flat five flat nine' },
  { key: '7b5#9',  suffix: '7b5#9',   aliases: ['7b5#9'],                                       iv: [0, 4, 6, 10, 15],      family: 'Altered',     name: 'seventh flat five sharp nine' },
  { key: '7alt',   suffix: '7alt',    aliases: ['7alt', 'alt'],                                 iv: [0, 4, 10, 13, 20],     family: 'Altered',     name: 'altered dominant (flat nine, flat thirteen)' }
];
var BY_KEY = {}, ALIAS = {};
Q.forEach(function (q) { BY_KEY[q.key] = q; q.aliases.forEach(function (a) { ALIAS[a] = q; }); ALIAS[q.suffix] = q; });

var NAMES_SHARP = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
var NAMES_FLAT  = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B'];
var LETTER = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
function mod12(n) { return ((n % 12) + 12) % 12; }
function rootName(pc, flats) { return (flats ? NAMES_FLAT : NAMES_SHARP)[mod12(pc)]; }
function noteToPc(s) { var m = /^([A-Ga-g])([#b]?)$/.exec(s); if (!m) return null; return mod12(LETTER[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0)); }

function normalise(s) {
  return String(s || '').replace(/\s+/g, '').replace(/♯/g, '#').replace(/♭/g, 'b').replace(/\(/g, '').replace(/\)/g, '')
    .replace(/maj/gi, 'maj').replace(/min/gi, 'min').replace(/dim/gi, 'dim').replace(/aug/gi, 'aug').replace(/sus/gi, 'sus').replace(/add/gi, 'add').replace(/alt/gi, 'alt').replace(/lyd/gi, 'lyd');
}
function quality(rest) {
  var q = ALIAS[rest]; if (q) return q;
  if (rest === '') return BY_KEY.maj;
  return null;
}
function build(rootPc, q, bassPc, extra) {
  var iv = q.iv.slice(), pcs = []; iv.forEach(function (i) { var pc = mod12(rootPc + i); if (pcs.indexOf(pc) < 0) pcs.push(pc); });
  var out = { ok: true, root: rootPc, quality: q.key, name: q.name, intervals: iv, pcs: pcs, bass: bassPc === undefined ? null : bassPc, inversion: 0, hasRoot: true };
  for (var k in extra) out[k] = extra[k]; return out;
}
function label(c, flats) { return rootName(c.root, flats) + BY_KEY[c.quality].suffix + (c.bass !== null && c.bass !== c.root ? '/' + rootName(c.bass, flats) : ''); }

// ---- roman numerals: I ii7 V7 vii°7 bVII V65 I64 ... in a key ({tonic, scale}) -----------------------------------
var MODE_STEPS = { major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10], phrygian: [0, 1, 3, 5, 7, 8, 10], lydian: [0, 2, 4, 6, 7, 9, 11],
                   mixolydian: [0, 2, 4, 5, 7, 9, 10], locrian: [0, 1, 3, 5, 6, 8, 10], 'harmonic-minor': [0, 2, 3, 5, 7, 8, 11], 'melodic-minor': [0, 2, 3, 5, 7, 9, 11],
                   pentatonic: [0, 2, 4, 5, 7, 9, 11], 'pentatonic-minor': [0, 2, 3, 5, 7, 8, 10], hexatonic: [0, 2, 4, 5, 7, 9, 11] };
var ROMAN = { I: 0, II: 1, III: 2, IV: 3, V: 4, VI: 5, VII: 6 };
function tonicPc(t) { if (typeof t === 'number') return mod12(t); var m = /^([A-Ga-g])([#b]?)$/.exec(String(t).trim()); if (!m) return null; return mod12(LETTER[m[1].toUpperCase()] + (m[2] === '#' ? 1 : m[2] === 'b' ? -1 : 0)); }
// do the chord names of this key use flats?  (the relative major's signature: F, Bb, Eb, Ab, Db)
var MODE_TO_MAJOR = { major: 0, minor: 3, dorian: 10, phrygian: 8, lydian: 7, mixolydian: 5, locrian: 1, 'harmonic-minor': 3, 'melodic-minor': 3, pentatonic: 0, 'pentatonic-minor': 3, hexatonic: 0 };
function keyPrefersFlats(key) {
  var t = tonicPc(key.tonic); if (t === null) return false;
  var maj = mod12(t + (MODE_TO_MAJOR[key.scale || 'major'] || 0)); return maj === 5 || maj === 10 || maj === 3 || maj === 8 || maj === 1;
}
// the root's name by SCALE DEGREE: the degree's letter plus whatever accidental reaches the pitch (vii° in D minor is C#, not Db)
var LETTERS7 = ['C', 'D', 'E', 'F', 'G', 'A', 'B'];
function spellByDegree(key, deg, rootPc) {
  var t = String(key.tonic).trim(), li = LETTERS7.indexOf(t.charAt(0).toUpperCase()); if (li < 0) return rootName(rootPc, keyPrefersFlats(key));
  var letter = LETTERS7[(li + deg) % 7], diff = mod12(rootPc - LETTER[letter] + 6) - 6;
  return diff === 0 ? letter : diff === 1 ? letter + '#' : diff === -1 ? letter + 'b' : diff === 2 ? letter + '##' : diff === -2 ? letter + 'bb' : rootName(rootPc, keyPrefersFlats(key));
}
function parseRoman(text, key) {
  var m = /^([b#]?)(VII|VI|IV|V|III|II|I|vii|vi|iv|v|iii|ii|i)(.*)$/.exec(text);
  if (!m) return null;
  var tpc = tonicPc(key.tonic); if (tpc === null) return { ok: false, error: 'the key\'s tonic "' + key.tonic + '" is not a note' };
  var scale = key.scale || 'major', steps = MODE_STEPS[scale] || MODE_STEPS.major, upper = m[2] === m[2].toUpperCase(), deg = ROMAN[m[2].toUpperCase()];
  var rootPc = mod12(tpc + steps[deg] + (m[1] === 'b' ? -1 : m[1] === '#' ? 1 : 0));
  var rest = m[3], inv = 0, hasSeventh = false, qual = null;
  // figured bass: 6 = first inversion, 64 = second; 7 = root position seventh, 65 / 43 / 42 (or 2) = its inversions
  var fig = /(65|64|43|42|7|6|2)$/.exec(rest);
  if (fig) { rest = rest.slice(0, rest.length - fig[1].length); var f = fig[1]; if (f === '6') inv = 1; else if (f === '64') inv = 2; else { hasSeventh = true; inv = f === '7' ? 0 : f === '65' ? 1 : f === '43' ? 2 : 3; } }
  var r = normalise(rest);
  var mark = r === '' ? 'plain' : (r === '°' || r === 'o' || r === 'dim') ? 'dim' : (r === 'ø') ? 'hdim' : (r === '+' || r === 'aug') ? 'aug' : (r === 'maj' || r === 'M' || r === 'Δ') ? 'maj' : null;
  if (mark === null) return { ok: false, error: 'cannot read "' + rest + '" after the numeral in "' + text + '"' };
  if (mark === 'plain') qual = hasSeventh ? (upper ? '7' : 'm7') : (upper ? 'maj' : 'min');     // V7 and I7 are dominant sevenths; ii7 is minor seventh (write viiø7 for half-diminished)
  else if (mark === 'dim') qual = hasSeventh ? 'dim7' : 'dim';
  else if (mark === 'hdim') qual = 'm7b5';
  else if (mark === 'aug') qual = hasSeventh ? '7#5' : 'aug';
  else if (mark === 'maj') qual = hasSeventh ? 'maj7' : 'maj';
  // in a minor key the lowercase leading-tone chord (vii°, viiø7) stands on the RAISED seventh
  if (/^(minor|harmonic-minor|melodic-minor)$/.test(scale) && deg === 6 && !upper && !m[1]) rootPc = mod12(tpc + 11);
  var c = build(rootPc, BY_KEY[qual], undefined, { roman: m[1] + m[2] + (mark === 'dim' ? '°' : mark === 'hdim' ? 'ø' : mark === 'aug' ? '+' : '') + (fig ? fig[1] : ''), inversion: inv, hasRoot: true });
  c.fromRoman = true; c.rootName = spellByDegree(key, deg, rootPc); return c;
}

// ---- parse -----------------------------------------------------------------------------------------------------------
function parse(text, key) {
  var raw = String(text === undefined || text === null ? '' : text).trim();
  if (!raw) return { ok: false, error: 'type a chord, for example Am7, F#m7b5, Bb/D, m7, or a numeral such as V7' };
  var s = normalise(raw);
  if (key) { var rm = parseRoman(s.replace(/^b(?=[IiVv])/, 'b'), key); if (rm) { if (rm.ok) rm.symbol = rm.rootName + BY_KEY[rm.quality].suffix; return rm; } }
  var bass = null, sl = /\/([A-Ga-g][#b]?)$/.exec(s);
  if (sl) { bass = noteToPc(sl[1]); s = s.slice(0, s.length - sl[0].length); }
  var rm2 = /^([A-Ga-g])([#b]?)(.*)$/.exec(s), rootPc = null, rest = s, hasRoot = false, rootText = '';
  if (rm2) {
    // "Bb" is B-flat, but "B" followed by a quality that starts with b (b5, b9) is not a root accidental
    var acc = rm2[2], after = rm2[3];
    if (acc === 'b' && /^(5|9|13)/.test(after) && !quality(after) && quality('b' + after)) { acc = ''; after = 'b' + after; }
    rootPc = mod12(LETTER[rm2[1].toUpperCase()] + (acc === '#' ? 1 : acc === 'b' ? -1 : 0)); rest = after; hasRoot = true; rootText = rm2[1].toUpperCase() + acc;
  }
  var q = quality(rest);
  if (!q) {
    var near = Q.filter(function (x) { return x.suffix.indexOf(rest) === 0 && rest.length > 0; }).slice(0, 4).map(function (x) { return x.suffix; });
    return { ok: false, error: 'I do not know the chord quality "' + rest + '"' + (near.length ? ' (did you mean ' + near.join(', ') + '?)' : '') + ' — open the dictionary for the list' };
  }
  var c = build(hasRoot ? rootPc : 0, q, bass === null ? undefined : bass, { hasRoot: hasRoot });
  c.symbol = hasRoot ? rootText + q.suffix + (bass !== null && bass !== rootPc ? '/' + rootName(bass, /b/.test(rootText) || /^(F)$/.test(rootText)) : '') : (q.suffix || 'maj') + (bass !== null ? '/' + rootName(bass, false) : '');
  return c;
}

// ---- voicing -----------------------------------------------------------------------------------------------------------
// chord: a parse() result.  o: {anchor (MIDI pitch the chord should sit near, default 60), rootPc (for quality-only chords),
// inversion (default the chord's own), spacing 'close'|'open'|'drop2', bass (add a bass note an octave-ish below), range [lo, hi]}
function voice(chord, o) {
  o = o || {};
  var anchor = o.anchor === undefined ? 60 : o.anchor, rootPc = chord.hasRoot ? chord.root : (o.rootPc === undefined ? mod12(anchor) : mod12(o.rootPc));
  var r0 = anchor - 6 + mod12(rootPc - (anchor - 6));           // the root nearest the anchor (within a tritone either way)
  var tones = chord.intervals.map(function (i) { return r0 + i; }).sort(function (a, b) { return a - b; });
  var inv = o.inversion === undefined ? (chord.inversion || 0) : o.inversion; inv = Math.max(0, Math.min(tones.length - 1, inv | 0));
  for (var k = 0; k < inv; k++) { tones.push(tones.shift() + 12); tones.sort(function (x, y) { return x - y; }); }   // (re-sort: an extension such as a ninth can sit above the raised root)
  var sp = o.spacing || 'close';
  if (sp === 'open' && tones.length >= 3) tones = tones.map(function (p, i) { return i % 2 === 1 ? p + 12 : p; }).sort(function (a, b) { return a - b; });
  else if (sp === 'drop2' && tones.length >= 4) { tones[tones.length - 2] -= 12; tones.sort(function (a, b) { return a - b; }); }
  var bassPc = chord.bass !== null && chord.bass !== undefined ? chord.bass : (o.bass ? mod12(rootPc) : null);
  if (bassPc !== null) { var low = tones[0], b = low - 1; while (mod12(b) !== bassPc) b--; if (low - b > 12) b += 12; tones.unshift(b); }
  if (o.range) {                                                 // slide by octaves to sit in the register
    var lo = o.range[0], hi = o.range[1], guard = 0;
    while (tones[tones.length - 1] > hi && tones[0] - 12 >= lo && guard++ < 6) tones = tones.map(function (p) { return p - 12; });
    while (tones[0] < lo && tones[tones.length - 1] + 12 <= hi && guard++ < 12) tones = tones.map(function (p) { return p + 12; });
  }
  tones = tones.filter(function (p, i, a) { return a.indexOf(p) === i && p >= 0 && p <= 127; });
  return tones;
}

// ---- identify: which chord names fit these notes? -----------------------------------------------------------------------
function identify(pitches, o) {
  o = o || {};
  var pcs = []; pitches.forEach(function (p) { var pc = mod12(p); if (pcs.indexOf(pc) < 0) pcs.push(pc); });
  if (!pcs.length) return [];
  var lowest = Math.min.apply(null, pitches), bassPc = mod12(lowest), flats = !!o.flats, out = [];
  pcs.forEach(function (r) {
    var have = pcs.map(function (pc) { return mod12(pc - r); }).sort(function (a, b) { return a - b; });
    Q.forEach(function (q) {
      var want = []; q.iv.forEach(function (i) { var c = i % 12; if (want.indexOf(c) < 0) want.push(c); }); want.sort(function (a, b) { return a - b; });
      var missing = want.filter(function (c) { return have.indexOf(c) < 0; }), extra = have.filter(function (c) { return want.indexOf(c) < 0; });
      if (extra.length) return;                                   // a note the chord does not contain
      var droppedFifth = missing.length === 1 && missing[0] === 7 && want.length >= 4;   // a seventh chord with no fifth is still that chord
      if (missing.length && !droppedFifth) return;
      var score = 100 - q.iv.length * 2 - (droppedFifth ? 12 : 0) + (mod12(bassPc - r) === 0 ? 14 : 0) - (q.family === 'Altered' ? 6 : 0) - (q.key === '5' ? 20 : 0) - (q.key === 'sus2' || q.key === 'sus4' ? 8 : 0);
      out.push({ symbol: rootName(r, flats) + q.suffix + (bassPc !== r ? '/' + rootName(bassPc, flats) : ''), root: r, quality: q.key, name: q.name, bass: bassPc, score: score });
    });
  });
  out.sort(function (a, b) { return b.score - a.score || a.symbol.length - b.symbol.length; });
  return out.filter(function (x, i, a) { return a.findIndex(function (y) { return y.symbol === x.symbol; }) === i; });
}

function list() {
  var fam = [], by = {};
  Q.forEach(function (q) { if (!by[q.family]) { by[q.family] = { family: q.family, items: [] }; fam.push(by[q.family]); } by[q.family].items.push({ suffix: q.suffix, key: q.key, name: q.name, intervals: q.iv.slice(), aliases: q.aliases.filter(function (a) { return a !== q.suffix && a !== ''; }) }); });
  return fam;
}

var api = { keyPrefersFlats: keyPrefersFlats, QUALITIES: Q, parse: parse, voice: voice, identify: identify, list: list, rootName: rootName, noteToPc: noteToPc, MODE_STEPS: MODE_STEPS };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfChords = api;
})(typeof window !== 'undefined' ? window : this);
