/* ==========================================================================
 * mccf_arc.js: emotional arc -> MIDI controller lanes (EBPS linkage 2)
 * --------------------------------------------------------------------------
 * An arc (the "EmotionalArc" XML the MCCF exports, one <Waypoint> per dialogue line with E, B, P, S, Coherence...) becomes
 * MIDI controller lanes: a curve is normalised to ITS OWN range in that arc, mapped to a controller number and an output
 * range, and sampled across the music.
 *
 *   parseArc(text)               -> {id, scene, title, cultivars:[{id, agent, points:[...]}]}   (throws if it is not an arc)
 *   curveStats(points, key)      -> {min, max, mean, sd, distinct, range, first, last, n}
 *   defaultSpec()                -> the recipe's `arc` block with the standard lanes (E->CC11, Coherence->CC91, P->CC74, B->CC1)
 *   normalizeSpec(spec)          -> canonical `arc` block (fixed key order, so recipe digests are stable)
 *   validateSpec(spec)           -> [error strings]
 *   normalized(points, key)      -> [0..1 per waypoint]  (a flat curve is all 0, as in the planning spreadsheet)
 *   laneEvents(points, lane, spec, lengthTicks, ppq) -> [{tick, value}]   (first event at tick 0; only value CHANGES after that)
 *   applyLanes(arrangement, points, spec) -> {lanes:[{curve, cc, events, tracks}], warnings}   (adds events to the voices' tracks)
 *   summary(points, spec, name...) -> the JSON the dashboard shows (stats, lanes, downsampled curves)
 *
 * What is NOT done here (on purpose): S is a stepped curve that suits events (a modal colour change) more than a continuous
 * controller; it can be given a lane like any other, but has none by default.  Drums are not touched by lanes.
 * Browser-free: runs under Node and in the page (window.MccfArc).
 * ========================================================================== */
(function (root) {
'use strict';

var CURVES = ['E', 'B', 'P', 'S', 'Coherence'];
// Controllers a lane may NOT drive: bank select (0, 32), data entry and RPN/NRPN (6, 38, 96-101), and channel-mode messages (120-127).
function ccAllowed(cc) { return cc % 1 === 0 && cc >= 1 && cc <= 119 && [32, 6, 38, 96, 97, 98, 99, 100, 101].indexOf(cc) < 0; }
var SPEC_SPAN = ['whole'];
var INTERP = ['linear', 'step'];

function decode(s) {
  return String(s).replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'").replace(/&#(\d+);/g, function (m, d) { return String.fromCharCode(+d); }).replace(/&amp;/g, '&');
}
function attrs(s) {
  var o = {}, re = /([A-Za-z_][\w:.-]*)\s*=\s*("([^"]*)"|'([^']*)')/g, m;
  while ((m = re.exec(s))) o[m[1]] = decode(m[3] !== undefined ? m[3] : m[4]);
  return o;
}
function num(v) { if (v === undefined || v === null || String(v).trim() === '') return null; var x = Number(v); return isFinite(x) ? x : null; }

function parseArc(text) {
  text = String(text === undefined || text === null ? '' : text);
  if (text.length > 8 * 1024 * 1024) throw new Error('That file is too large to be an arc (limit 8 MB)');
  var head = /<EmotionalArc\b([^>]*)>/.exec(text);
  if (!head) throw new Error('That is not an emotional arc file (no <EmotionalArc> element)');
  var ha = attrs(head[1]), tm = /<title>([\s\S]*?)<\/title>/.exec(text), out = { id: ha.id || '', scene: ha.scene || '', title: tm ? decode(tm[1]).trim() : '', cultivars: [] };
  var cre = /<Cultivar\b([^>]*)>([\s\S]*?)<\/Cultivar>/g, cm;
  while ((cm = cre.exec(text))) {
    var ca = attrs(cm[1]), pts = [], wre = /<Waypoint\b([^>]*?)(\/>|>([\s\S]*?)<\/Waypoint>)/g, wm;
    while ((wm = wre.exec(cm[2]))) {
      var a = attrs(wm[1]), st = wm[3] ? /<Statement\b[^>]*>([\s\S]*?)<\/Statement>/.exec(wm[3]) : null;
      pts.push({ step: num(a.stepno) === null ? pts.length + 1 : num(a.stepno), id: a.id || a.name || '', E: num(a.E), B: num(a.B), P: num(a.P), S: num(a.S),
                 Coherence: num(a.Coherence), mode: a.Mode || '', uncertainty: num(a.Uncertainty), valence: num(a.Valence), reward: num(a.Reward),
                 text: st ? decode(st[1]).trim() : '' });
    }
    out.cultivars.push({ id: ca.id || '', agent: ca.agentname || ca.path_name || '', points: pts });
  }
  if (!out.cultivars.length) throw new Error('That arc has no <Cultivar> with waypoints');
  if (!out.cultivars.some(function (c) { return c.points.length; })) throw new Error('That arc has no waypoints');
  return out;
}

function values(points, key) { return points.map(function (p) { return p[key]; }).filter(function (v) { return v !== null && v !== undefined && isFinite(v); }); }
function curveStats(points, key) {
  var v = values(points, key), n = v.length;
  if (!n) return { min: null, max: null, mean: null, sd: null, distinct: 0, range: null, first: null, last: null, n: 0 };
  var min = Math.min.apply(null, v), max = Math.max.apply(null, v), mean = v.reduce(function (a, b) { return a + b; }, 0) / n;
  var sd = Math.sqrt(v.reduce(function (a, b) { return a + (b - mean) * (b - mean); }, 0) / n), seen = {}; v.forEach(function (x) { seen[x] = 1; });
  return { min: min, max: max, mean: mean, sd: sd, distinct: Object.keys(seen).length, range: max - min, first: v[0], last: v[v.length - 1], n: n };
}
// Each waypoint's value scaled 0..1 within that curve's own range in this arc.  Missing values take the neighbour's (so a gap holds); a flat curve is all 0.
function normalized(points, key) {
  var s = curveStats(points, key), prev = null, out = [];
  points.forEach(function (p) { var v = p[key]; if (v === null || v === undefined || !isFinite(v)) v = prev; prev = v === null ? prev : v; out.push(v); });
  var first = out.filter(function (v) { return v !== null; })[0];
  return out.map(function (v) { if (v === null) v = first; if (v === undefined || s.range === null || s.range === 0) return 0; return (v - s.min) / s.range; });
}

var DEFAULT_LANES = [
  { curve: 'E', cc: 11, lo: 30, hi: 110, on: true },          // expression: the per-line emotional contour
  { curve: 'Coherence', cc: 91, lo: 20, hi: 90, on: true },   // reverb send: the slow arc of the whole piece
  { curve: 'P', cc: 74, lo: 50, hi: 90, on: true },           // brightness: small deviations only
  { curve: 'B', cc: 1, lo: 0, hi: 60, on: true }              // modulation: small movement
];
function defaultSpec() {
  return normalizeSpec({ file: '', sha256: null, agent: '', enabled: true, span: 'whole', interp: 'linear', lanes: DEFAULT_LANES });
}
function clampInt(v, lo, hi, d) { v = Math.round(Number(v)); if (!isFinite(v)) return d; return Math.max(lo, Math.min(hi, v)); }
function normalizeSpec(a) {
  a = a || {};
  return { file: a.file || '', sha256: a.sha256 || null, agent: a.agent || '', enabled: a.enabled === undefined ? true : !!a.enabled,
           span: a.span || 'whole', interp: a.interp || 'linear',
           lanes: (a.lanes || []).map(function (l) {
             return { curve: l.curve, cc: l.cc === undefined ? null : Number(l.cc), lo: l.lo === undefined ? 0 : Number(l.lo), hi: l.hi === undefined ? 127 : Number(l.hi), on: l.on === undefined ? true : !!l.on };
           }) };
}
function validateSpec(spec) {
  var errs = [], a;
  try { a = normalizeSpec(spec); } catch (e) { return [String(e.message || e)]; }
  if (SPEC_SPAN.indexOf(a.span) < 0) errs.push('arc span must be "whole"');
  if (INTERP.indexOf(a.interp) < 0) errs.push('arc interp must be "linear" or "step"');
  if (a.lanes.length > 16) errs.push('an arc can have at most 16 lanes');
  var used = {};
  a.lanes.forEach(function (l, i) {
    var w = 'arc lane ' + (i + 1) + ' (' + l.curve + '): ';
    if (CURVES.indexOf(l.curve) < 0) errs.push(w + 'curve must be one of ' + CURVES.join(', '));
    if (!ccAllowed(l.cc)) errs.push(w + 'controller must be a whole number 1-119, not bank select (0, 32), data entry or RPN/NRPN (6, 38, 96-101)');
    if (!(l.lo % 1 === 0 && l.lo >= 0 && l.lo <= 127 && l.hi % 1 === 0 && l.hi >= 0 && l.hi <= 127)) errs.push(w + 'low and high must be whole numbers 0-127');
    if (l.on) { if (used[l.cc]) errs.push(w + 'controller ' + l.cc + ' is already driven by another lane'); used[l.cc] = true; }
  });
  return errs;
}

// A curve's value (0..1) at position u in [0,1] across the music.  linear: the waypoints are spread evenly from 0 to 1 and joined by straight lines.
// step: each waypoint holds for its own equal share (like a line of dialogue holding until the next one).
function sample(norm, u, interp) {
  var n = norm.length; if (!n) return 0; if (n === 1) return norm[0];
  u = Math.max(0, Math.min(1, u));
  if (interp === 'step') return norm[Math.min(n - 1, Math.floor(u * n))];
  var x = u * (n - 1), i = Math.min(n - 2, Math.floor(x)), f = x - i; return norm[i] + (norm[i + 1] - norm[i]) * f;
}
function laneEvents(points, lane, spec, lengthTicks, ppq) {
  var norm = normalized(points, lane.curve), step = Math.max(1, Math.round(ppq / 2)), ev = [], last = null, lo = lane.lo, hi = lane.hi;
  var L = Math.max(1, Math.round(lengthTicks)), n = norm.length, ticks = {};
  for (var g = 0; g <= L; g += step) ticks[g] = 1;                       // an even grid (eighth notes) ...
  for (var i = 0; i < n; i++) {                                           // ... PLUS each waypoint's own position, so a peak or a low is never stepped over
    var ui = spec.interp === 'step' ? i / n : (n > 1 ? i / (n - 1) : 0);
    ticks[Math.min(L, Math.round(ui * L))] = 1;
  }
  Object.keys(ticks).map(Number).sort(function (x, y) { return x - y; }).forEach(function (t) {
    var v = Math.max(0, Math.min(127, Math.round(lo + sample(norm, t / L, spec.interp) * (hi - lo))));
    if (v !== last) { ev.push({ tick: t, value: v }); last = v; }
  });
  return ev;
}

// Add the lanes to the voices' tracks (tracks that have a voiceId and are not drums).  The lane REPLACES that track's own static value for that controller.
function applyLanes(arr, points, spec, warn) {
  var a = normalizeSpec(spec), out = { lanes: [], warnings: [] };
  if (!a.enabled) return out;
  if (!points || !points.length) { out.warnings.push('the arc is switched on but no arc is loaded: no controller lanes were written'); return out; }
  var errs = validateSpec(a); if (errs.length) { out.warnings.push('arc lanes skipped: ' + errs[0]); return out; }
  var targets = arr.tracks.filter(function (t) { return t.voiceId !== undefined && t.voiceId !== null && t.channel !== 9 && t.drum !== true; });
  var L = arr.lengthTicks || 0;
  if (!(L > 0)) { out.warnings.push('there is no music yet, so no controller lanes were written'); return out; }
  a.lanes.forEach(function (lane) {
    if (!lane.on) return;
    var ev = laneEvents(points, lane, a, L, arr.ppq);
    targets.forEach(function (t) {
      t.controllers = t.controllers || {};
      var keep = (t.controllers[lane.cc] || []).filter(function (e) { return e.tick > 0 && !e.lane; });
      t.controllers[lane.cc] = keep.concat(ev.map(function (e) { return { tick: e.tick, value: e.value, channel: t.channel, lane: true }; }));
    });
    out.lanes.push({ curve: lane.curve, cc: lane.cc, events: ev.length, tracks: targets.length });
  });
  return out;
}

// What the dashboard shows: stats per curve, the lanes with their output range, and every curve downsampled to at most `maxPts` normalised points.
function summary(arc, agentIndex, spec, extra) {
  var cult = arc.cultivars[agentIndex || 0] || arc.cultivars[0], pts = cult.points, a = normalizeSpec(spec), maxPts = 120;
  function down(norm) { if (norm.length <= maxPts) return norm.map(function (v) { return Math.round(v * 1000) / 1000; }); var o = []; for (var i = 0; i < maxPts; i++) o.push(Math.round(norm[Math.round(i * (norm.length - 1) / (maxPts - 1))] * 1000) / 1000); return o; }
  return Object.assign({
    arc: { id: arc.id, scene: arc.scene, title: arc.title, agent: cult.agent, waypoints: pts.length, words: pts.reduce(function (s, p) { return s + (p.text ? p.text.split(/\s+/).filter(Boolean).length : 0); }, 0),
           modes: Array.from(new Set(pts.map(function (p) { return p.mode; }).filter(Boolean))), hasValence: values(pts, 'valence').length > 0, hasUncertainty: values(pts, 'uncertainty').length > 0, hasReward: values(pts, 'reward').length > 0 },
    stats: CURVES.map(function (k) { var s = curveStats(pts, k); s.curve = k; return s; }),
    curves: CURVES.reduce(function (o, k) { o[k] = down(normalized(pts, k)); return o; }, {}),
    spec: { enabled: a.enabled, interp: a.interp, span: a.span, lanes: a.lanes },
  }, extra || {});
}

var api = { CURVES: CURVES, DEFAULT_LANES: DEFAULT_LANES, parseArc: parseArc, curveStats: curveStats, normalized: normalized, defaultSpec: defaultSpec, normalizeSpec: normalizeSpec,
            validateSpec: validateSpec, sample: sample, laneEvents: laneEvents, applyLanes: applyLanes, summary: summary, ccAllowed: ccAllowed };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.MccfArc = api;
})(typeof window !== 'undefined' ? window : this);
