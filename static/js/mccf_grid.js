/* ==========================================================================
 * mccf_grid.js — piano-roll (grid) view for the Theme Workshop (checkpoint 1b-i)
 * --------------------------------------------------------------------------
 * Draws parser-shaped data ({ppq, tempoEvents, timeSigEvents, tracks[]}) on a canvas.
 *   - time runs across in bars and beats (the file's first time signature; 4/4 if none)
 *   - pitch runs up, auto-fitted to the notes present; zoom and scroll on both axes
 *   - notes are rectangles coloured by track (same colours as the mixer), velocity = opacity
 *   - a selectable snap grid is drawn as faint lines
 *   - a "ghost" of the original theme can be drawn behind the selected voice
 *   - drums appear as marks on their own lane
 *   - a playback cursor follows the Player's clock
 *
 * The picture is computed by layout(), a pure function of the view state and the data, so it is
 * testable in Node without a browser.  draw() only paints what layout() returns.
 * Exposes MccfGrid (window global, and module.exports under Node).
 * ========================================================================== */
(function (root) {
'use strict';

var NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];
var BLACK = { 1: 1, 3: 1, 6: 1, 8: 1, 10: 1 };
// drum lane rows, top to bottom (General MIDI drum map)
var DRUM_ROWS = [['cymbals', [49, 51, 52, 53, 55, 57, 59]], ['hats', [42, 44, 46]], ['toms', [41, 43, 45, 47, 48, 50]],
                 ['snare', [37, 38, 39, 40]], ['kick', [35, 36]], ['other', null]];
var SNAPS = { '1/2': 2, '1/4': 1, '1/8': 1 / 2, '1/16': 1 / 4, '1/32': 1 / 8, '1/8T': 1 / 3, '1/16T': 1 / 6, 'off': 0 };   // fraction of a quarter note

// General MIDI percussion names for the rows of a drum voice being edited
var DRUM_NAMES = { 35: 'Kick 2', 36: 'Kick', 37: 'Side stick', 38: 'Snare', 39: 'Clap', 40: 'Snare 2', 41: 'Floor tom L', 42: 'Closed hat', 43: 'Floor tom H', 44: 'Pedal hat',
                   45: 'Low tom', 46: 'Open hat', 47: 'Mid tom L', 48: 'Mid tom H', 49: 'Crash', 50: 'High tom', 51: 'Ride', 52: 'China', 53: 'Ride bell', 54: 'Tambourine',
                   55: 'Splash', 56: 'Cowbell', 57: 'Crash 2', 58: 'Vibraslap', 59: 'Ride 2' };
function noteName(p) { return NAMES[((p % 12) + 12) % 12] + (Math.floor(p / 12) - 1); }
function drumRow(pitch) {
  for (var i = 0; i < DRUM_ROWS.length - 1; i++) if (DRUM_ROWS[i][1].indexOf(pitch) >= 0) return i;
  return DRUM_ROWS.length - 1;
}
function isDrumTrack(tr) { return !!(tr.channelsSeen && tr.channelsSeen.indexOf(9) >= 0); }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }

// tick <-> seconds, from the tempo map (the same algorithm the Player uses)
function tempoSegments(ppq, te) {
  var segs = [], sec = 0;
  for (var i = 0; i < te.length; i++) {
    var next = i + 1 < te.length ? te[i + 1].tick : Infinity;
    segs.push({ tick: te[i].tick, sec: sec, secPerTick: te[i].usPerQuarter / ppq / 1e6, next: next });
    if (next !== Infinity) sec += (next - te[i].tick) * te[i].usPerQuarter / ppq / 1e6;
  }
  return segs;
}
function makeSecToTick(ppq, te) {
  var segs = tempoSegments(ppq, te && te.length ? te : [{ tick: 0, usPerQuarter: 500000 }]);
  return function (s) {
    if (s <= 0) return 0;
    var seg = segs[0];
    for (var i = 0; i < segs.length; i++) if (segs[i].sec <= s) seg = segs[i];
    return seg.tick + (s - seg.sec) / seg.secPerTick;
  };
}
function meterOf(data) {
  var s = (data.timeSigEvents && data.timeSigEvents[0]) || { num: 4, den: 4 };
  return { num: s.num, den: s.den, barTicks: Math.round(data.ppq * 4 * s.num / s.den), beatTicks: Math.round(data.ppq * 4 / s.den) };
}

function GridView(canvas, opts) {
  this.canvas = canvas; this.o = opts || {};
  this.snap = '1/16'; this.showGhost = true; this.follow = true; this.selected = null;
  this.view = { tick0: 0, ppb: 60, pitchHi: 84, ppSemi: 12, w: 800, h: 360, gutter: 58, ruler: 22, drumH: 56, velH: 64 };
  this.editOn = false; this.tool = 'draw'; this.newVel = 90; this.clip = null; this._ptr = null; this.sel = {}; this.drag = null; this.autoFit = true; this.dirty = true; this.running = false; this._raf = null; this._info = null; this._infoData = null; this._cursorTick = null;
}
var G = GridView.prototype;

// ---- what is in the data --------------------------------------------------
G.data = function () { return this.o.getData ? this.o.getData() : null; };
G.info = function () {
  var d = this.data(); if (!d) return null;
  var key = d.tracks.length + ':' + d.tracks.reduce(function (s, t) { return s + t.noteCount; }, 0);
  if (this._infoData === d && this._infoKey === key) return this._info;
  var lo = Infinity, hi = -Infinity, total = 0, drums = false;
  d.tracks.forEach(function (t) {
    if (!t.noteCount) return;
    total = Math.max(total, t.lengthTicks || 0);
    if (isDrumTrack(t)) { drums = true; return; }
    t.notes.forEach(function (n) { if (n.pitch < lo) lo = n.pitch; if (n.pitch > hi) hi = n.pitch; });
  });
  if (lo === Infinity) { lo = 48; hi = 84; }
  this._info = { ppq: d.ppq, meter: meterOf(d), total: total, lo: lo, hi: hi, drums: drums };
  this._infoData = d; this._infoKey = key; return this._info;
};
// the velocity lane exists while a hand-edited voice is being edited
G.laneOn = function () {
  if (!this.editOn || this.selected === null) return false;
  if (this.o.canEdit) return !!this.o.canEdit(this.selected);
  return !!(this.o.getEdit && this.o.getEdit(this.selected));
};
G.areaBottom = function () { var v = this.view, i = this.info(); return v.h - (i && i.drums ? v.drumH + 4 : 0) - (this.laneOn() ? v.velH + 4 : 0); };

// ---- view control -----------------------------------------------------------
G.resize = function (w, h) { this.view.w = Math.max(200, w); this.view.h = Math.max(120, h); this.dirty = true; };
G.fit = function () {   // whole piece across, all melodic notes up and down
  var i = this.info(), v = this.view; if (!i) return;
  v.ppb = clamp((v.w - v.gutter - 14) / Math.max(1, i.total / i.ppq), 0.5, 600); v.tick0 = 0;
  this.fitPitch(); this.autoFit = true; this.dirty = true;   // stays true until you zoom or scroll by hand: then the view is yours
};
G.fitDrumRows = function () {   // rows 35-59 (the General MIDI drum kit) fill the note area
  var v = this.view, avail = this.areaBottom() - v.ruler, rows = 59 - 35 + 3;
  v.ppSemi = clamp(Math.floor(avail / rows), 6, 26); v.pitchHi = 60 + Math.max(0, (avail / v.ppSemi - rows) / 2); this.dirty = true;
};
G.fitPitch = function () {
  var i = this.info(), v = this.view; if (!i) return;
  var E0 = this.editTarget(); if (E0 && E0.drums) return this.fitDrumRows();
  var rows = i.hi - i.lo + 5, avail = this.areaBottom() - v.ruler;
  v.ppSemi = clamp(Math.floor(avail / rows), 2, 26);
  v.pitchHi = i.hi + 2 + Math.max(0, (avail / v.ppSemi - rows) / 2); this.dirty = true;
};
G.setZoom = function (ppb) { var v = this.view; this._zoomX(ppb / v.ppb, v.gutter); };
G._zoomX = function (f, px) {
  var v = this.view, i = this.info(); if (!i) return;
  var t = this.tickAtX(px); v.ppb = clamp(v.ppb * f, 0.5, 600); v.tick0 = t - (px - v.gutter) * i.ppq / v.ppb; this.autoFit = false; this.dirty = true;
};
G.zoomY = function (f) {
  var v = this.view, mid = v.pitchHi - (this.areaBottom() - v.ruler) / v.ppSemi / 2;
  v.ppSemi = clamp(v.ppSemi * f, 2, 40); v.pitchHi = mid + (this.areaBottom() - v.ruler) / v.ppSemi / 2; this.dirty = true;
};
G.scrollBy = function (dx, dy) {
  var v = this.view, i = this.info(); if (!i) return;
  if (dx) { v.tick0 = clamp(v.tick0 + dx * i.ppq / v.ppb, -i.ppq * 4, i.total + i.ppq * 4); this.autoFit = false; }
  v.pitchHi = clamp(v.pitchHi + dy / v.ppSemi, 20, 140); this.dirty = true;
};
G.scrollToTick = function (t) { this.view.tick0 = t; this.autoFit = false; this.dirty = true; };

// ---- coordinates --------------------------------------------------------------
G.X = function (tick) { var v = this.view, i = this.info(); return v.gutter + (tick - v.tick0) * v.ppb / i.ppq; };
G.tickAtX = function (x) { var v = this.view, i = this.info(); return v.tick0 + (x - v.gutter) * i.ppq / v.ppb; };
G.Y = function (pitch) { var v = this.view; return v.ruler + (v.pitchHi - pitch) * v.ppSemi; };
// row p occupies y in [Y(p), Y(p)+ppSemi): its top edge is continuous value p and the row runs DOWN from it, so ceil
G.pitchAtY = function (y) { var v = this.view; return Math.ceil(v.pitchHi - (y - v.ruler) / v.ppSemi); };

// ---- the picture ---------------------------------------------------------------
G.layout = function () {
  var d = this.data(), i = this.info(), v = this.view, self = this;
  if (!d || !i) return null;
  var chordsIn = this.o.getChords ? this.o.getChords() : null, rh = (chordsIn && chordsIn.length) ? 40 : 22;     // a chord strip makes the ruler taller
  if (v.ruler !== rh) { v.ruler = rh; if (this.autoFit) this.fitPitch(); }
  var E = this.editTarget(), dEdit = !!(E && E.drums), gw = dEdit ? 84 : 58;     // editing a drum voice: wider gutter for the drum names
  if (v.gutter !== gw) v.gutter = gw;
  var fitKey = dEdit ? E.trackIndex + ':' + (E.voiceId || '') : null;
  if (fitKey !== this._drumFit) { this._drumFit = fitKey; if (dEdit) this.fitDrumRows(); }   // show the drum sounds as soon as a drum voice is picked
  var aB = this.areaBottom(), lane = this.laneOn(), out = { w: v.w, h: v.h, gutter: v.gutter, ruler: v.ruler, areaBottom: aB, drumTop: aB + 4 + (lane ? v.velH + 4 : 0), drumH: v.drumH, velTop: aB + 4, velH: v.velH, vel: null, marquee: null,
    hasDrums: i.drums, drumEdit: dEdit, chords: null, notes: [], ghost: [], drums: [], bars: [], beats: [], snapLines: [], keys: [], cursor: null, tracks: [] };
  var pr = i.ppq, tick1 = this.tickAtX(v.w), tick0 = this.tickAtX(v.gutter);

  // pitch rows (piano keys)
  var pLo = Math.floor(this.pitchAtY(aB)), pHi = Math.ceil(this.pitchAtY(v.ruler));
  for (var p = Math.max(0, pLo); p <= Math.min(127, pHi); p++) {
    var y = this.Y(p);
    out.keys.push({ pitch: p, y: y, h: v.ppSemi, black: !!BLACK[p % 12], label: dEdit ? (DRUM_NAMES[p] || '') : ((p % 12 === 0 || v.ppSemi >= 14) ? noteName(p) : ''), drum: dEdit ? !!DRUM_NAMES[p] : false });
  }
  // bars, beats, snap lines
  var m = i.meter, pxBar = m.barTicks * v.ppb / pr, pxBeat = m.beatTicks * v.ppb / pr;
  var every = pxBar >= 36 ? 1 : pxBar >= 18 ? 2 : pxBar >= 9 ? 4 : pxBar >= 4.5 ? 8 : pxBar >= 2.2 ? 16 : 32;
  var b0 = Math.max(0, Math.floor(tick0 / m.barTicks)), b1 = Math.ceil(tick1 / m.barTicks);
  for (var b = b0; b <= b1; b++) out.bars.push({ x: this.X(b * m.barTicks), n: b + 1, label: (b % every === 0) ? String(b + 1) : '' });
  if (pxBeat >= 12) for (var t = Math.max(0, Math.floor(tick0 / m.beatTicks)) * m.beatTicks; t <= tick1; t += m.beatTicks) if (t % m.barTicks) out.beats.push(this.X(t));
  var sf = SNAPS[this.snap] || 0, st = sf * pr;
  if (st > 0 && st * v.ppb / pr >= 6) for (var s = Math.max(0, Math.floor(tick0 / st)) * st; s <= tick1; s += st) {
    if (Math.abs(s % m.beatTicks) > 0.5 && Math.abs(s % m.beatTicks - m.beatTicks) > 0.5) out.snapLines.push(this.X(s));
  }

  // notes, per track
  var drumRowH = v.drumH / DRUM_ROWS.length;
  d.tracks.forEach(function (tr) {
    if (!tr.noteCount) return;
    var drum = isDrumTrack(tr), on = self.o.isEnabled ? !!self.o.isEnabled(tr.index) : true;
    out.tracks.push({ index: tr.index, name: tr.name, drum: drum, enabled: on, noteCount: tr.noteCount });
    var col = self.o.color ? self.o.color(tr.index) : '#a060f0';
    tr.notes.forEach(function (n) {
      var x = self.X(n.startTick), w = Math.max(2, n.durTicks * v.ppb / pr);
      if (x + w < v.gutter || x > v.w) return;
      var alpha = (0.25 + 0.75 * clamp(n.velocity, 0, 127) / 127) * (on ? 1 : 0.18);
      if (drum && !(dEdit && tr.index === E.trackIndex)) {
        var r = drumRow(n.pitch);
        out.drums.push({ x: x, y: out.drumTop + r * drumRowH, w: Math.min(w, 6), h: Math.max(2, drumRowH - 1), track: tr.index, alpha: alpha, color: col, pitch: n.pitch, row: r });
      } else {
        var y = self.Y(n.pitch);
        if (y + v.ppSemi < v.ruler || y > aB) return;
        out.notes.push({ x: x, y: y, w: w, h: Math.max(2, v.ppSemi - 1), track: tr.index, alpha: alpha, color: col, pitch: n.pitch, tick: n.startTick, dur: n.durTicks });
      }
    });
  });

  // ghost: the original theme, behind the selected voice
  var g = (this.showGhost && this.selected !== null && this.o.getGhost) ? this.o.getGhost(this.selected) : null;
  if (g) {
    out.ghostLabel = g.label || 'original';
    g.notes.forEach(function (n) {
      var x = self.X(n.startTick), w = Math.max(2, n.durTicks * v.ppb / pr), y = self.Y(n.pitch);
      if (x + w < v.gutter || x > v.w || y + v.ppSemi < v.ruler || y > aB) return;
      out.ghost.push({ x: x, y: y, w: w, h: Math.max(2, v.ppSemi - 1), pitch: n.pitch, tick: n.startTick, dur: n.durTicks });
    });
  }

  // editing overlay: the selected notes of the voice being edited, and the notes as they will be if the drag is dropped now
  out.editTrack = null; out.editSel = []; out.preview = [];
  if (E) {
    out.editTrack = E.trackIndex;
    var rectOf = function (n, start, dur, pitch) { return { x: self.X(start), y: self.Y(pitch), w: Math.max(2, dur * v.ppb / pr), h: Math.max(2, v.ppSemi - 1), id: n && n.id, pitch: pitch }; };
    E.notes.forEach(function (n) { if (self.sel[n.id]) out.editSel.push(rectOf(n, n.start, n.dur, n.pitch)); });
    var dg = this.drag;
    if (dg && dg.kind === 'move' && (dg.dTick || dg.dPitch)) dg.orig.forEach(function (n) { out.preview.push(rectOf(n, n.start + dg.dTick, n.dur, n.pitch + dg.dPitch)); });
    else if (dg && dg.kind === 'resize' && dg.dDur) dg.orig.forEach(function (n) { out.preview.push(rectOf(n, n.start, Math.max(1, n.dur + dg.dDur), n.pitch)); });
    else if (dg && dg.kind === 'draw') out.preview.push(rectOf(null, dg.start, dg.dur, dg.pitch));
  }

  if (E && lane) {   // velocity lane: one bar per note of the voice being edited (a drag in progress is shown live)
    var dv = (this.drag && this.drag.kind === 'vel') ? this.drag.dVel : 0, dids = (this.drag && this.drag.kind === 'vel') ? this.drag.ids : [];
    var rset = (this.drag && this.drag.kind === 'ramp' && this.drag.moved) ? this._rampSet(this.drag) : null;
    out.vel = { top: out.velTop, h: v.velH, bars: [] };
    E.notes.forEach(function (n) {
      var x = self.X(n.start); if (x < v.gutter - 4 || x > v.w + 4) return;
      var val = rset && rset[n.id] !== undefined ? rset[n.id] : (dids.indexOf(n.id) >= 0 ? clamp(n.vel + dv, 1, 127) : n.vel);
      out.vel.bars.push({ id: n.id, x: x, vel: val, y: self.velY(val), bottom: out.velTop + v.velH - 4, sel: !!self.sel[n.id], pitch: n.pitch });
    });
  }
  if (out.vel && this.drag && this.drag.kind === 'ramp' && this.drag.moved) out.ramp = { x0: this.drag.sx, y0: this.drag.sy, x1: this.drag.x, y1: this.drag.y };
  if (this.tool === 'chord' && E && this._ptr && !this.drag) {   // a preview of the chord a click would stamp
    var pc = this._chordAt(this._ptr.x, this._ptr.y);
    if (pc && !pc.error) out.chordPreview = { symbol: pc.symbol, notes: pc.pitches.map(function (p) { return { x: self.X(pc.start), y: self.Y(p), w: Math.max(3, pc.dur * v.ppb / i.ppq), h: Math.max(2, v.ppSemi - 1), pitch: p }; }) };
    else if (pc && pc.error) out.previewError = pc.error;
  }
  if (this.drag && this.drag.kind === 'marquee' && this.drag.moved) { var mq = this.drag; out.marquee = { x: Math.min(mq.sx, mq.x), y: Math.min(mq.sy, mq.y), w: Math.abs(mq.x - mq.sx), h: Math.abs(mq.y - mq.sy) }; }

  if (chordsIn && chordsIn.length) {   // chord strip: one cell per harmonic window; the one under the cursor is marked
    out.chords = chordsIn.map(function (c) { var x0 = self.X(c.start), x1 = self.X(c.end); return { x0: x0, x1: x1, symbol: c.symbol, roman: c.roman, func: c.func, now: self._cursorTick !== null && self._cursorTick !== undefined && self._cursorTick >= c.start && self._cursorTick < c.end }; })
      .filter(function (c) { return c.x1 >= v.gutter && c.x0 <= v.w; });
  }
  // playback cursor, and the keys it is sounding (pitch -> track colour)
  var ct = this._cursorTick; out.active = {};
  if (ct !== null && ct !== undefined) {
    out.cursor = { x: this.X(ct), tick: ct };
    d.tracks.forEach(function (tr) {
      if (!tr.noteCount || (isDrumTrack(tr) && !(dEdit && tr.index === E.trackIndex)) || (self.o.isEnabled && !self.o.isEnabled(tr.index))) return;
      for (var q = 0; q < tr.notes.length; q++) {
        var n = tr.notes[q]; if (n.startTick > ct) break;                       // notes are sorted by start
        if (n.startTick + n.durTicks > ct) out.active[n.pitch] = self.o.color ? self.o.color(tr.index) : '#a060f0';
      }
    });
  }
  return out;
};

// ---- painting ---------------------------------------------------------------------
G.draw = function () {
  var ctx = this.canvas.getContext && this.canvas.getContext('2d'); this.dirty = false;
  var L = this.layout(), v = this.view, self2 = this; if (!ctx) return L;
  ctx.setTransform && ctx.setTransform(this.dpr || 1, 0, 0, this.dpr || 1, 0, 0);
  ctx.fillStyle = '#060810'; ctx.fillRect(0, 0, v.w, v.h);
  if (!L) {
    ctx.fillStyle = '#aab0be'; ctx.font = '13px monospace'; ctx.fillText('Load a MIDI file to see its notes here.', v.gutter + 16, 60); return null;
  }
  // piano-key rows
  ctx.save(); ctx.beginPath(); ctx.rect(v.gutter, v.ruler, v.w - v.gutter, L.areaBottom - v.ruler); ctx.clip();
  L.keys.forEach(function (k) { ctx.fillStyle = L.drumEdit ? (k.drum ? '#10162a' : '#070a12') : (k.black ? '#0a0d16' : '#0d1120'); ctx.fillRect(v.gutter, k.y, v.w - v.gutter, k.h);
    if (k.pitch % 12 === 0) { ctx.fillStyle = 'rgba(160,96,240,0.10)'; ctx.fillRect(v.gutter, k.y + k.h - 1, v.w - v.gutter, 1); } });
  // grid lines: snap (faintest), beats, bars
  ctx.fillStyle = 'rgba(170,176,190,0.07)'; L.snapLines.forEach(function (x) { ctx.fillRect(Math.round(x), v.ruler, 1, L.areaBottom - v.ruler); });
  ctx.fillStyle = 'rgba(170,176,190,0.14)'; L.beats.forEach(function (x) { ctx.fillRect(Math.round(x), v.ruler, 1, L.areaBottom - v.ruler); });
  ctx.fillStyle = 'rgba(160,96,240,0.35)'; L.bars.forEach(function (b) { ctx.fillRect(Math.round(b.x), v.ruler, 1, L.areaBottom - v.ruler); });
  // ghost (outline only, behind everything else)
  if (L.ghost.length) {
    ctx.fillStyle = 'rgba(214,222,240,0.07)'; L.ghost.forEach(function (g) { ctx.fillRect(g.x, g.y, g.w, g.h); });
    ctx.strokeStyle = 'rgba(214,222,240,0.85)'; ctx.lineWidth = 1; ctx.setLineDash && ctx.setLineDash([3, 2]);
    L.ghost.forEach(function (g) { ctx.strokeRect(g.x + 0.5, g.y + 0.5, Math.max(1, g.w - 1), Math.max(1, g.h - 1)); }); ctx.setLineDash && ctx.setLineDash([]);
  }
  // notes
  var sel = this.selected;   // the selected voice is outlined in amber (the ghost is white and dashed)
  L.notes.forEach(function (n) { ctx.globalAlpha = n.alpha; ctx.fillStyle = n.color; ctx.fillRect(n.x, n.y, n.w, n.h);
    if (n.track === sel) { ctx.globalAlpha = 0.95; ctx.strokeStyle = '#f0c060'; ctx.lineWidth = 1; ctx.strokeRect(n.x + 0.5, n.y + 0.5, Math.max(1, n.w - 1), Math.max(1, n.h - 1)); } });
  if (L.editTrack !== null) {   // selection (white) and the drag preview (the voice's colour with an amber outline)
    var ecol = this.o.color ? this.o.color(L.editTrack) : '#a060f0';
    L.preview.forEach(function (r) { ctx.globalAlpha = 0.6; ctx.fillStyle = ecol; ctx.fillRect(r.x, r.y, r.w, r.h); ctx.globalAlpha = 1; ctx.strokeStyle = '#f0c060'; ctx.lineWidth = 2; ctx.strokeRect(r.x + 1, r.y + 1, Math.max(1, r.w - 2), Math.max(1, r.h - 2)); });
    ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; L.editSel.forEach(function (r) { ctx.strokeRect(r.x + 1, r.y + 1, Math.max(1, r.w - 2), Math.max(1, r.h - 2)); });
  }
  ctx.globalAlpha = 1; ctx.restore();
  if (L.vel) {   // velocity lane
    var lt = L.vel.top, lb = lt + L.vel.h;
    ctx.fillStyle = '#0a0d16'; ctx.fillRect(v.gutter, lt, v.w - v.gutter, L.vel.h);
    ctx.save(); ctx.beginPath(); ctx.rect(v.gutter, lt, v.w - v.gutter, L.vel.h); ctx.clip();
    ctx.fillStyle = 'rgba(170,176,190,0.10)'; [32, 64, 96, 127].forEach(function (g) { ctx.fillRect(v.gutter, Math.round(self2.velY(g)), v.w - v.gutter, 1); });
    ctx.fillStyle = 'rgba(160,96,240,0.30)'; L.bars.forEach(function (b) { ctx.fillRect(Math.round(b.x), lt, 1, L.vel.h); });
    var vcol = this.o.color ? this.o.color(L.editTrack) : '#a060f0';
    L.vel.bars.forEach(function (b) {
      ctx.globalAlpha = b.sel ? 1 : 0.8; ctx.fillStyle = vcol; ctx.fillRect(Math.round(b.x) - 1, b.y, 3, b.bottom - b.y);
      ctx.fillStyle = b.sel ? '#ffffff' : vcol; ctx.fillRect(Math.round(b.x) - 3, b.y - 2, 7, 5);
    });
    if (L.ramp) { ctx.strokeStyle = '#f0c060'; ctx.lineWidth = 2; ctx.beginPath(); ctx.moveTo(L.ramp.x0, L.ramp.y0); ctx.lineTo(L.ramp.x1, L.ramp.y1); ctx.stroke(); ctx.fillStyle = '#f0c060'; ctx.fillRect(L.ramp.x0 - 3, L.ramp.y0 - 3, 6, 6); ctx.fillRect(L.ramp.x1 - 3, L.ramp.y1 - 3, 6, 6); }
    ctx.globalAlpha = 1; ctx.restore();
    ctx.fillStyle = '#0a0d16'; ctx.fillRect(0, lt, v.gutter, L.vel.h); ctx.fillStyle = '#6b7080'; ctx.font = '10px monospace'; ctx.fillText('127', 6, Math.round(this.velY(127)) + 4); ctx.fillText('64', 6, Math.round(this.velY(64)) + 4); ctx.fillStyle = '#aab0be'; ctx.fillText('Vel', 6, lt + L.vel.h - 5);
  }
  if (L.chordPreview && L.chordPreview.notes.length) {   // the chord tool: what a click here would stamp
    ctx.fillStyle = 'rgba(240,192,96,0.28)'; ctx.strokeStyle = '#f0c060'; ctx.lineWidth = 1; ctx.setLineDash && ctx.setLineDash([3, 2]);
    L.chordPreview.notes.forEach(function (n) { ctx.fillRect(n.x, n.y, n.w, n.h); ctx.strokeRect(n.x + 0.5, n.y + 0.5, Math.max(1, n.w - 1), Math.max(1, n.h - 1)); }); ctx.setLineDash && ctx.setLineDash([]);
    if (L.chordPreview.symbol) { ctx.fillStyle = '#f0c060'; ctx.font = 'bold 11px monospace'; ctx.fillText(L.chordPreview.symbol, L.chordPreview.notes[0].x + 2, Math.min.apply(null, L.chordPreview.notes.map(function (n) { return n.y; })) - 4); }
  }
  if (L.marquee) { ctx.fillStyle = 'rgba(240,192,96,0.12)'; ctx.fillRect(L.marquee.x, L.marquee.y, L.marquee.w, L.marquee.h); ctx.strokeStyle = '#f0c060'; ctx.lineWidth = 1; ctx.strokeRect(L.marquee.x + 0.5, L.marquee.y + 0.5, L.marquee.w, L.marquee.h); }
  // drum lane
  if (L.hasDrums) {
    ctx.fillStyle = '#0a0d16'; ctx.fillRect(v.gutter, L.drumTop, v.w - v.gutter, v.drumH);
    ctx.save(); ctx.beginPath(); ctx.rect(v.gutter, L.drumTop, v.w - v.gutter, v.drumH); ctx.clip();
    ctx.fillStyle = 'rgba(160,96,240,0.35)'; L.bars.forEach(function (b) { ctx.fillRect(Math.round(b.x), L.drumTop, 1, v.drumH); });
    L.drums.forEach(function (n) { ctx.globalAlpha = n.alpha; ctx.fillStyle = n.color; ctx.fillRect(n.x, n.y, n.w, n.h); });
    ctx.globalAlpha = 1; ctx.restore();
    ctx.fillStyle = '#aab0be'; ctx.font = '10px monospace'; ctx.fillText('Perc', 6, L.drumTop + 14);
  }
  if (L.ghostLabel && L.ghost.length) { ctx.fillStyle = 'rgba(214,222,240,0.85)'; ctx.font = '11px monospace'; ctx.fillText('┄ dashed = ' + L.ghostLabel, v.gutter + 8, L.areaBottom - 8); }
  // gutter: a piano keyboard whose keys line up with the rows of the grid.  White keys run the full width, black keys are
  // the short dark bars at the back; a key lights up in its track's colour while the cursor is sounding that pitch.
  ctx.save(); ctx.beginPath(); ctx.rect(0, v.ruler, v.gutter, L.areaBottom - v.ruler); ctx.clip();
  ctx.fillStyle = '#0a0d16'; ctx.fillRect(0, v.ruler, v.gutter, L.areaBottom - v.ruler);
  var blackW = Math.round(v.gutter * 0.6), keyW = v.gutter - 2;
  if (L.drumEdit) {   // a drum voice: no keyboard, the drum sounds themselves are the rows
    L.keys.forEach(function (k) {
      var lit = L.active[k.pitch];
      ctx.fillStyle = lit ? lit : (k.drum ? '#1a2036' : '#0a0d16'); ctx.fillRect(0, k.y, keyW, k.h - (k.drum ? 1 : 0));
      if (k.label) { ctx.fillStyle = lit ? '#060810' : '#c8cfe0'; ctx.font = '10px monospace'; ctx.fillText(k.label, 5, k.y + Math.min(k.h - 2, 10)); }
    });
  } else L.keys.forEach(function (k) {
    ctx.fillStyle = '#e8e5da'; ctx.fillRect(0, k.y, keyW, k.h);                                    // the white key (also behind each black key)
    ctx.fillStyle = 'rgba(0,0,0,0.28)';                                                               // the gap between neighbouring white keys
    if (k.black) ctx.fillRect(blackW, k.y + Math.floor(k.h / 2), keyW - blackW, 1);                   // behind a black key: through the middle of its row
    else if (k.pitch % 12 === 4 || k.pitch % 12 === 11) ctx.fillRect(0, k.y + k.h - 1, keyW, 1);      // E|F and B|C have no black key between them
    var lit = L.active[k.pitch];
    if (lit) { ctx.globalAlpha = 0.9; ctx.fillStyle = lit; ctx.fillRect(k.black ? 0 : 0, k.y, k.black ? blackW : keyW, k.h); ctx.globalAlpha = 1; }
    else if (k.black) { ctx.fillStyle = '#1b1f2b'; ctx.fillRect(0, k.y, blackW, Math.max(1, k.h - 1)); }
    if (!k.black && k.label) { ctx.fillStyle = lit ? '#060810' : (k.pitch % 12 === 0 ? '#2a2f3d' : '#6b7080'); ctx.font = (k.pitch % 12 === 0 ? 'bold ' : '') + '10px monospace'; ctx.fillText(k.label, blackW + 2, k.y + Math.min(k.h - 1, 10)); }
  });
  ctx.fillStyle = '#1a2035'; ctx.fillRect(keyW, v.ruler, 2, L.areaBottom - v.ruler); ctx.restore();
  // ruler
  ctx.fillStyle = '#0a0d16'; ctx.fillRect(0, 0, v.w, v.ruler);
  if (L.chords) {
    ctx.save(); ctx.beginPath(); ctx.rect(v.gutter, 22, v.w - v.gutter, 18); ctx.clip();
    L.chords.forEach(function (c, i) {
      ctx.fillStyle = c.now ? 'rgba(160,96,240,0.45)' : (i % 2 ? '#0f1422' : '#131a2c'); ctx.fillRect(Math.max(v.gutter, c.x0), 22, Math.max(1, c.x1 - Math.max(v.gutter, c.x0)), 18);
      ctx.fillStyle = 'rgba(160,96,240,0.35)'; ctx.fillRect(Math.round(c.x0), 22, 1, 18);
      var w = c.x1 - c.x0; ctx.fillStyle = c.now ? '#ffffff' : '#c8cfe0'; ctx.font = 'bold 11px monospace'; if (w > 22) ctx.fillText(c.symbol, Math.max(v.gutter, c.x0) + 4, 35);
      if (w > 74) { ctx.fillStyle = c.now ? '#e8d8ff' : '#6b7080'; ctx.font = '10px monospace'; ctx.fillText(c.roman, Math.max(v.gutter, c.x0) + 8 + c.symbol.length * 7, 35); }
    });
    ctx.restore(); ctx.fillStyle = '#aab0be'; ctx.font = '9px monospace'; ctx.fillText('CHORDS', 6, 35);
  }
  ctx.fillStyle = '#aab0be'; ctx.font = '11px monospace';
  L.bars.forEach(function (b) { if (b.label && b.x >= v.gutter - 2) ctx.fillText(b.label, b.x + 3, 15); });
  ctx.fillStyle = 'rgba(160,96,240,0.35)'; L.bars.forEach(function (b) { if (b.x >= v.gutter) ctx.fillRect(Math.round(b.x), 16, 1, 6); });
  // cursor
  if (L.cursor && L.cursor.x >= v.gutter && L.cursor.x <= v.w) {
    ctx.fillStyle = '#4af0a8'; ctx.fillRect(Math.round(L.cursor.x), 0, 2, v.h);
  }
  return L;
};

// ---- interaction helpers -------------------------------------------------------------
G.hitTest = function (x, y) {   // -> track index of the note under the point (topmost), or null
  var L = this.layout(); if (!L) return null;
  for (var k = L.notes.length - 1; k >= 0; k--) { var n = L.notes[k]; if (x >= n.x && x <= n.x + n.w && y >= n.y && y <= n.y + n.h) return n.track; }
  for (var j = L.drums.length - 1; j >= 0; j--) { var q = L.drums[j]; if (x >= q.x - 2 && x <= q.x + q.w + 2 && y >= q.y && y <= q.y + q.h) return q.track; }
  return null;
};
// the explanation of the chord under the pointer in the chord strip (why that chord?), or null
G.chordWhy = function (x, y) {
  var ch = this.o.getChords ? this.o.getChords() : null, v = this.view; if (!ch || !ch.length || y < 22 || y >= v.ruler || x < v.gutter) return null;
  var t = this.tickAtX(x); for (var k = 0; k < ch.length; k++) if (t >= ch[k].start && t < ch[k].end) return ch[k].why || (ch[k].symbol + ' (' + ch[k].roman + ')');
  return null;
};
G.readout = function (x, y) {
  var i = this.info(); if (!i) return '';
  var t = Math.max(0, this.tickAtX(x)), m = i.meter, bar = Math.floor(t / m.barTicks) + 1, beat = (t % m.barTicks) / m.beatTicks + 1;
  var txt = 'bar ' + bar + ' · beat ' + beat.toFixed(2);
  if (y >= this.view.ruler && y <= this.areaBottom()) { var p = this.pitchAtY(y); if (p >= 0 && p <= 127) txt += ' · ' + noteName(p) + ' (' + p + ')'; }
  return txt;
};
G.select = function (index) { if (index !== this.selected) this.sel = {}; this.selected = index; this.dirty = true; if (this.o.onSelect) this.o.onSelect(index); };

// ---- editing (the pointer model: pure, so every gesture is testable without a browser) ---------------------------------
// The grid never edits anything itself: it works out what you meant and reports it through o.onEdit({type, track, ...}); the owner
// changes the recipe and the grid redraws from the result.  o.getEdit() describes the voice being edited, or null when the
// selected track is not hand-editable:  {trackIndex, notes:[{id, pitch, start, dur, vel}], minStart}.
G.setEditMode = function (on) { this.editOn = !!on; this.drag = null; this.dirty = true; if (this.o.onEditChange) this.o.onEditChange(); };
G.editTarget = function () {
  if (!this.editOn || !this.o.getEdit || this.selected === null) return null;
  var E = this.o.getEdit(this.selected); if (!E || E.trackIndex !== this.selected) return null;
  var keep = {}, any = false; E.notes.forEach(function (n) { if (this.sel[n.id]) { keep[n.id] = true; any = true; } }, this);
  if (any || Object.keys(this.sel).length) this.sel = keep;                     // drop selections that no longer exist (after undo, delete)
  return E;
};
G.snapTicks = function () { var i = this.info(); return Math.max(1, Math.round((SNAPS[this.snap] || 1 / 16) * i.ppq)); };
G.selectedIds = function () { return Object.keys(this.sel).map(Number).sort(function (a, b) { return a - b; }); };
G.setSelection = function (ids) { this.sel = {}; (ids || []).forEach(function (i) { this.sel[i] = true; }, this); this.dirty = true; if (this.o.onEditChange) this.o.onEditChange(); };
G._emit = function (ev) {
  ev.track = this.selected; var r = this.o.onEdit ? this.o.onEdit(ev) : null;
  if (r && r.select) this.setSelection(r.select); else if (ev.type === 'delete') this.setSelection([]);
  this.dirty = true;
};
G._audition = function (pitch, vel) { if (this.o.onAudition && pitch >= 0 && pitch <= 127) this.o.onAudition(pitch, this.selected === null ? this._firstTrack() : this.selected, vel || this.newVel); };
G._firstTrack = function () { var d = this.data(), t = d && d.tracks.filter(function (x) { return x.noteCount && !isDrumTrack(x); })[0]; return t ? t.index : 0; };
G.defaultDur = function () { return this.snapTicks(); };   // a click draws one grid cell: a 16th at 1/16 snap, an eighth at 1/8; drag for longer
G.snapPx = function () { var i = this.info(); return i ? this.snapTicks() * this.view.ppb / i.ppq : 0; };   // how wide one grid cell is on screen
G.velY = function (vel) { var v = this.view, top = this.areaBottom() + 4; return top + v.velH - 4 - (clamp(vel, 1, 127) / 127) * (v.velH - 8); };
G.velBarAt = function (x, y) {      // the velocity bar nearest the pointer (within 6 px sideways), or null
  var E = this.editTarget(); if (!E || !this.laneOn()) return null; var v = this.view, best = null, bd = 1e9, self = this;
  E.notes.forEach(function (n) { var dx = Math.abs(self.X(n.start) - x); if (dx > 6) return; var d = dx * 4 + Math.abs(self.velY(n.vel) - y); if (d < bd) { bd = d; best = n; } });
  return best;
};
G.velAtY = function (y) { var v = this.view, top = this.areaBottom() + 4; return clamp(Math.round((top + v.velH - 4 - y) / (v.velH - 8) * 127), 1, 127); };
// a line drawn across the lane -> a velocity for every note under it (only the selected ones, if any are selected)
G._rampSet = function (d) {
  var E = this.editTarget(); if (!E) return {};
  var xl = Math.min(d.sx, d.x), xr = Math.max(d.sx, d.x), a = d.sx <= d.x ? { x: d.sx, v: this.velAtY(d.sy) } : { x: d.x, v: this.velAtY(d.y) }, b = d.sx <= d.x ? { x: d.x, v: this.velAtY(d.y) } : { x: d.sx, v: this.velAtY(d.sy) };
  var any = Object.keys(this.sel).length > 0, out = {}, self = this;
  E.notes.forEach(function (n) {
    var nx = self.X(n.start); if (nx < xl - 3 || nx > xr + 3) return; if (any && !self.sel[n.id]) return;
    var f = xr === xl ? 0 : clamp((nx - xl) / (xr - xl), 0, 1); out[n.id] = clamp(Math.round(a.v + (b.v - a.v) * f), 1, 127);
  });
  return out;
};
G.inLane = function (x, y) { var v = this.view, top = this.areaBottom() + 4; return this.laneOn() && x >= v.gutter && y >= top && y < top + v.velH; };
G.hitEditNote = function (x, y) {     // -> {note, zone: 'body'|'right'} for the topmost note of the voice being edited
  var E = this.editTarget(); if (!E) return null; var v = this.view, i = this.info();
  for (var k = E.notes.length - 1; k >= 0; k--) {
    var n = E.notes[k], nx = this.X(n.start), nw = Math.max(2, n.dur * v.ppb / i.ppq), ny = this.Y(n.pitch);
    if (x >= nx && x <= nx + nw && y >= ny && y <= ny + v.ppSemi) { var edge = Math.min(7, Math.max(3, nw / 3)); return { note: n, zone: (x >= nx + nw - edge) ? 'right' : 'body' }; }
  }
  return null;
};
G.cursorFor = function (x, y) {
  var d = this.drag, v = this.view;
  if (d) return d.kind === 'resize' ? 'ew-resize' : (d.kind === 'draw' || d.kind === 'marquee') ? 'crosshair' : (d.kind === 'vel' || d.kind === 'ramp') ? 'ns-resize' : d.kind === 'key' ? 'pointer' : 'grabbing';
  if (this.inLane(x, y)) return this.velBarAt(x, y) ? 'ns-resize' : 'default';
  if (x < v.gutter) return (y >= v.ruler && y < this.areaBottom()) ? 'pointer' : 'default';
  if (this.editTarget() && y >= v.ruler && y < this.areaBottom()) { if (this.tool === 'chord') return 'copy'; var h = this.hitEditNote(x, y); return h ? (h.zone === 'right' ? 'ew-resize' : 'grab') : (this.tool === 'select' ? 'default' : 'crosshair'); }
  return 'grab';
};
G.setTool = function (t) { this.tool = (t === 'select' || t === 'chord') ? t : 'draw'; this.dirty = true; if (this.o.onEditChange) this.o.onEditChange(); };
// ---- the chord tool: the page supplies o.chordNotes(spec, anchorPitch) -> {pitches, symbol} | {error}; a click stamps the chord as plain notes ----
G.setChord = function (spec) { this.chordSpec = Object.assign({ symbol: '', inversion: 0, spacing: 'close', bass: false, length: 'beat' }, spec || {}); this.dirty = true; };
G.chordLength = function () {
  var i = this.info(), m = i ? i.meter : { beatTicks: 480, barTicks: 1920 }, L = (this.chordSpec || {}).length;
  return typeof L === 'number' ? Math.max(1, L) : L === 'cell' ? this.snapTicks() : L === 'half' ? Math.round(m.barTicks / 2) : L === 'bar' ? m.barTicks : m.beatTicks;
};
G._chordAt = function (x, y) {   // what a click here would stamp: {pitches, start, dur, symbol} or {error}
  var E = this.editTarget(), v = this.view; if (!E || !this.o.chordNotes || !this.chordSpec) return null;
  if (x < v.gutter || y < v.ruler || y >= this.areaBottom()) return null;
  var st = this.snapTicks(), anchor = clamp(this.pitchAtY(y), 0, 127), r = this.o.chordNotes(this.chordSpec, anchor);
  if (!r || r.error || !r.pitches || !r.pitches.length) return { error: r && r.error ? r.error : 'no chord' };
  return { pitches: r.pitches, symbol: r.symbol || '', start: Math.max(E.minStart, Math.floor(this.tickAtX(x) / st) * st), dur: this.chordLength() };
};
G.stampChord = function (x, y) {
  var c = this._chordAt(x, y); if (!c) return false;
  if (c.error) { if (this.o.onChordError) this.o.onChordError(c.error); return false; }
  var vel = this.newVel; this._emit({ type: 'paste', notes: c.pitches.map(function (p) { return { pitch: p, start: c.start, dur: c.dur, vel: vel }; }) });
  if (this.o.onAuditionChord) this.o.onAuditionChord(c.pitches, vel, this.editTarget() ? this.editTarget().trackIndex : this.selected);
  return true;
};
// ---- transform the selection (the chain, where to put the result and how to join it are the page's settings) ----
G.selectionPitches = function () { var E = this.editTarget(); return E ? E.notes.filter(function (n) { return this.sel[n.id]; }, this).map(function (n) { return n.pitch; }) : []; };
G.transformSelection = function (spec) {
  var E = this.editTarget(); if (!E) return 0; var ids = this.selectedIds(); if (!ids.length) return 0;
  var ev = { type: 'transform', ids: ids, chain: spec.chain || [], place: spec.place || 'after', join: spec.join || null }, v = this.view, p = this._ptr, st = this.snapTicks();
  if (ev.place === 'at') ev.at = (p && p.x >= v.gutter && p.y >= v.ruler && p.y < this.areaBottom()) ? Math.floor(this.tickAtX(p.x) / st) * st : Math.ceil(v.tick0 / st) * st;
  this._emit(ev); return ids.length;
};
G.hover = function (x, y) { this._ptr = (x === null || x === undefined) ? null : { x: x, y: y }; };
G.selectionVelocity = function () {      // {min, max, mean, count} of the selected notes' velocities, or null
  var E = this.editTarget(); if (!E) return null; var vs = E.notes.filter(function (n) { return this.sel[n.id]; }, this).map(function (n) { return n.vel; });
  if (!vs.length) return null; return { min: Math.min.apply(null, vs), max: Math.max.apply(null, vs), mean: Math.round(vs.reduce(function (a, b) { return a + b; }, 0) / vs.length), count: vs.length };
};
// the velocity control: with notes selected it sets THEIR velocity; with none it sets what new notes get
G.setVelocity = function (vel) {
  vel = clamp(Math.round(vel), 1, 127); var ids = this.selectedIds(), E = this.editTarget();
  if (E && ids.length) { this._emit({ type: 'velocity', ids: ids, vel: vel }); var n = E.notes.filter(function (q) { return q.id === ids[0]; })[0]; if (n) this._audition(n.pitch, vel); }
  else { this.newVel = vel; if (this.o.onEditChange) this.o.onEditChange(); }
};
G.nudgeVelocity = function (d) { var ids = this.selectedIds(); if (!ids.length) return false; this._emit({ type: 'velocity', ids: ids, dVel: d }); var E = this.editTarget(), n = E && E.notes.filter(function (q) { return q.id === ids[0]; })[0]; if (n) this._audition(n.pitch, clamp(n.vel + d, 1, 127)); return true; };

// ---- clipboard: notes are kept relative to the earliest, so they can be pasted anywhere, into any hand-edited voice ----
G.copy = function () {
  var E = this.editTarget(); if (!E) return 0; var sel = E.notes.filter(function (n) { return this.sel[n.id]; }, this); if (!sel.length) return 0;
  var t0 = Math.min.apply(null, sel.map(function (n) { return n.start; }));
  this.clip = sel.map(function (n) { return { pitch: n.pitch, dt: n.start - t0, dur: n.dur, vel: n.vel }; }); return sel.length;
};
G.cut = function () { var n = this.copy(); if (n) this._emit({ type: 'delete', ids: this.selectedIds() }); return n; };
// paste where the pointer is (snapped to the grid), else at the left edge of the view; the pasted notes become the selection
G.paste = function () {
  var E = this.editTarget(); if (!E || !this.clip || !this.clip.length) return false;
  var v = this.view, st = this.snapTicks(), aB = this.areaBottom(), p = this._ptr, t;
  if (p && p.x >= v.gutter && p.y >= v.ruler && p.y < aB) t = Math.floor(this.tickAtX(p.x) / st) * st; else t = Math.ceil(v.tick0 / st) * st;
  t = Math.max(E.minStart, t);
  this._emit({ type: 'paste', notes: this.clip.map(function (n) { return { pitch: n.pitch, start: t + n.dt, dur: n.dur, vel: n.vel }; }) }); return true;
};
// copy the selection and put it right after itself (repeat to tile a phrase)
G.duplicate = function () {
  var E = this.editTarget(); if (!E) return false; var sel = E.notes.filter(function (n) { return this.sel[n.id]; }, this); if (!sel.length) return false;
  var st = this.snapTicks(), t0 = Math.min.apply(null, sel.map(function (n) { return n.start; })), t1 = Math.max.apply(null, sel.map(function (n) { return n.start + n.dur; }));
  var shift = Math.max(st, Math.ceil((t1 - t0) / st) * st);
  this._emit({ type: 'paste', notes: sel.map(function (n) { return { pitch: n.pitch, start: n.start + shift, dur: n.dur, vel: n.vel }; }) }); return true;
};
// ---- groove tools: act on the selected notes, or on every note of the voice when none are selected.  Return how many notes. ----
G._groove = function () { var E = this.editTarget(); if (!E) return null; var ids = this.selectedIds(), all = !ids.length; if (all) ids = E.notes.map(function (n) { return n.id; }); return ids.length ? { ids: ids, all: all } : null; };
G.quantize = function (strength, durations) { var g = this._groove(); if (!g) return 0; this._emit({ type: 'quantize', ids: g.ids, grid: this.snapTicks(), strength: strength === undefined ? 1 : strength, durations: !!durations }); this.lastGroove = g; return g.ids.length; };
G.swing = function (ratio) { var g = this._groove(); if (!g) return 0; this._emit({ type: 'swing', ids: g.ids, grid: this.snapTicks(), ratio: ratio }); this.lastGroove = g; return g.ids.length; };
G.humanize = function (vel, time) { var g = this._groove(); if (!g) return 0; this._emit({ type: 'humanize', ids: g.ids, vel: vel, time: time, seed: this.seedFn ? this.seedFn() : Math.floor(Math.random() * 2147483647) }); this.lastGroove = g; return g.ids.length; };
G.pointerDown = function (x, y, m) {
  m = m || {}; var v = this.view, aB = this.areaBottom(); this.drag = null;
  if (x < v.gutter) { if (y >= v.ruler && y < aB) { this._audition(this.pitchAtY(y)); this.drag = { kind: 'key' }; } return; }   // click a piano key: hear it
  if (this.inLane(x, y) && m.alt && this.editTarget()) {          // Alt+drag in the velocity lane: draw a ramp (crescendo / decrescendo)
    this.drag = { kind: 'ramp', sx: x, sy: y, x: x, y: y, moved: false }; this.dirty = true; return;
  }
  if (this.inLane(x, y) && !m.alt && m.button !== 1) {          // the velocity lane: drag a bar up or down
    var bar = this.velBarAt(x, y);
    if (bar) {
      if (m.shift) { if (this.sel[bar.id]) delete this.sel[bar.id]; else this.sel[bar.id] = true; this.dirty = true; this.drag = { kind: 'click' }; if (this.o.onEditChange) this.o.onEditChange(); return; }
      if (!this.sel[bar.id]) this.sel = (function (o) { o[bar.id] = true; return o; })({});
      var E0 = this.editTarget(), ids0 = this.selectedIds(), orig0 = {}; E0.notes.forEach(function (n) { if (this.sel[n.id]) orig0[n.id] = n.vel; }, this);
      this.drag = { kind: 'vel', sx: x, sy: y, ids: ids0, orig: orig0, primary: bar, dVel: 0, moved: false, lastAud: bar.vel };
      this._audition(bar.pitch, bar.vel); this.dirty = true; if (this.o.onEditChange) this.o.onEditChange();
    } else this.drag = { kind: 'click' };
    return;
  }
  var inNotes = y >= v.ruler && y < aB, E = (inNotes && !m.alt && m.button !== 1) ? this.editTarget() : null;
  if (E && this.tool === 'chord') { this.stampChord(x, y); this.drag = { kind: 'click' }; return; }
  if (E) {
    var hit = this.hitEditNote(x, y);
    if (hit) {
      var id = hit.note.id;
      if (m.shift) { if (this.sel[id]) delete this.sel[id]; else this.sel[id] = true; this.dirty = true; this.drag = { kind: 'click' }; if (this.o.onEditChange) this.o.onEditChange(); return; }
      if (!this.sel[id]) this.sel = (function (o) { o[id] = true; return o; })({});
      var ids = this.selectedIds(), orig = E.notes.filter(function (n) { return this.sel[n.id]; }, this).map(function (n) { return { id: n.id, pitch: n.pitch, start: n.start, dur: n.dur }; });
      this.drag = { kind: hit.zone === 'right' ? 'resize' : 'move', sx: x, sy: y, ids: ids, orig: orig, primary: hit.note, dTick: 0, dPitch: 0, dDur: 0, moved: false, lastPitch: hit.note.pitch, E: E };
      this._audition(hit.note.pitch); this.dirty = true; if (this.o.onEditChange) this.o.onEditChange(); return;
    }
    var other = this.hitTest(x, y);
    if (other !== null && other !== E.trackIndex) { this.drag = { kind: 'selectTrack', track: other, sx: x, sy: y, moved: false }; return; }   // another voice: a click selects it
    if (this.tool === 'select' || m.ctrl || m.meta) {            // empty space with the select tool (or Ctrl held): a box
      var base = m.shift ? Object.assign({}, this.sel) : {};
      this.drag = { kind: 'marquee', sx: x, sy: y, x: x, y: y, moved: false, additive: !!m.shift, base: base, E: E }; if (!m.shift) this.sel = {}; this.dirty = true; return;
    }
    var st = this.snapTicks(), p = clamp(this.pitchAtY(y), 0, 127);
    this.sel = {}; this.drag = { kind: 'draw', sx: x, sy: y, start: Math.max(E.minStart, Math.floor(this.tickAtX(x) / st) * st), pitch: p, dur: this.defaultDur(), moved: false, E: E };
    this._audition(p, this.newVel); this.dirty = true; if (this.o.onEditChange) this.o.onEditChange(); return;
  }
  this.drag = { kind: 'pan', sx: x, sy: y, lastX: x, lastY: y, moved: false };
};
G.pointerMove = function (x, y) {
  var d = this.drag; if (!d || d.kind === 'key' || d.kind === 'click') return;
  if (Math.abs(x - d.sx) + Math.abs(y - d.sy) > 3) d.moved = true;
  if (d.kind === 'ramp') { d.x = x; d.y = clamp(y, this.areaBottom() + 4, this.areaBottom() + 4 + this.view.velH); d.moved = true; this.dirty = true; return; }
  if (d.kind === 'vel') {
    var H = this.view.velH - 8; d.dVel = Math.round((d.sy - y) / H * 127); d.moved = d.moved || d.dVel !== 0;
    var pv = clamp(d.primary.vel + d.dVel, 1, 127); if (Math.abs(pv - d.lastAud) >= 12) { d.lastAud = pv; this._audition(d.primary.pitch, pv); }
    this.dirty = true; return;
  }
  if (d.kind === 'marquee') {
    d.x = x; d.y = y; var rx0 = Math.min(d.sx, x), rx1 = Math.max(d.sx, x), ry0 = Math.min(d.sy, y), ry1 = Math.max(d.sy, y), vv = this.view, ppq0 = this.info().ppq, hit = Object.assign({}, d.base);
    d.E.notes.forEach(function (n) { var nx = this.X(n.start), nw = Math.max(2, n.dur * vv.ppb / ppq0), ny = this.Y(n.pitch); if (nx <= rx1 && nx + nw >= rx0 && ny <= ry1 && ny + vv.ppSemi >= ry0) hit[n.id] = true; }, this);
    this.sel = hit; this.dirty = true; return;
  }
  if (d.kind === 'pan') { if (d.moved) { this.scrollBy(-(x - d.lastX), -(y - d.lastY)); d.lastX = x; d.lastY = y; if (this.o.onView) this.o.onView(); } return; }
  var st = this.snapTicks(), ppq = this.info().ppq;
  if (d.kind === 'move') {
    var minStart = Math.min.apply(null, d.orig.map(function (n) { return n.start; })), lo = Math.min.apply(null, d.orig.map(function (n) { return n.pitch; })), hi = Math.max.apply(null, d.orig.map(function (n) { return n.pitch; }));
    var dT = Math.round((this.tickAtX(x) - this.tickAtX(d.sx)) / st) * st, dP = this.pitchAtY(y) - this.pitchAtY(d.sy);
    dT = Math.max(dT, d.E.minStart - minStart); dP = clamp(dP, -lo, 127 - hi);
    d.dTick = dT; if (dP !== d.dPitch) { d.dPitch = dP; this._audition(d.primary.pitch + dP); } d.dPitch = dP;
  } else if (d.kind === 'resize') {
    var minDur = Math.min.apply(null, d.orig.map(function (n) { return n.dur; }));
    d.dDur = Math.max(Math.round((this.tickAtX(x) - this.tickAtX(d.sx)) / st) * st, st - minDur);
  } else if (d.kind === 'draw') {
    if (d.moved) d.dur = Math.max(st, Math.round(this.tickAtX(x) / st) * st - d.start);
  }
  this.dirty = true;
};
G.pointerUp = function (x, y) {
  var d = this.drag; this.drag = null; if (!d) return; this.dirty = true;
  if (d.kind === 'selectTrack') { if (!d.moved) this.select(d.track); return; }
  if (d.kind === 'pan') { if (!d.moved) { var h = this.hitTest(x, y); if (h !== null) this.select(h); } return; }
  if (d.kind === 'ramp') { var set = d.moved ? this._rampSet(d) : {}; if (Object.keys(set).length) this._emit({ type: 'velocity', set: set }); return; }
  if (d.kind === 'vel') { if (d.dVel) this._emit({ type: 'velocity', ids: d.ids, dVel: d.dVel }); else if (this.o.onEditChange) this.o.onEditChange(); return; }
  if (d.kind === 'marquee') { if (!d.moved && !d.additive) this.sel = {}; if (this.o.onEditChange) this.o.onEditChange(); return; }
  if (d.kind === 'move') { if (d.dTick || d.dPitch) this._emit({ type: 'move', ids: d.ids, dTick: d.dTick, dPitch: d.dPitch }); }
  else if (d.kind === 'resize') { if (d.dDur) this._emit({ type: 'resize', ids: d.ids, dDur: d.dDur }); }
  else if (d.kind === 'draw') { this._emit({ type: 'add', pitch: d.pitch, start: d.start, dur: d.dur, vel: this.newVel }); }
};
G.cancelDrag = function () { if (this.drag) { this.drag = null; this.dirty = true; return true; } return false; };
// keys while the grid is being edited -> true if the key was used
G.keyDown = function (key, m) {
  m = m || {}; var E = this.editTarget(); if (!E) return false;
  if (key === 'Escape') { if (!this.cancelDrag()) this.setSelection([]); return true; }
  var mod = m.ctrl || m.meta, kl = (key || '').toLowerCase();
  if (mod && kl === 'c') return this.copy() > 0;
  if (mod && kl === 'x') return this.cut() > 0;
  if (mod && kl === 'v') return this.paste();
  if (mod && kl === 'd') return this.duplicate();
  if (!mod && !m.alt && (key === 'd' || key === 'D')) { this.setTool('draw'); return true; }
  if (!mod && !m.alt && (key === 's' || key === 'S')) { this.setTool('select'); return true; }
  if (!mod && !m.alt && (key === 'c' || key === 'C')) { this.setTool('chord'); return true; }
  if (!mod && (key === '+' || key === '=')) return this.nudgeVelocity(5);
  if (!mod && (key === '-' || key === '_')) return this.nudgeVelocity(-5);
  if ((m.ctrl || m.meta) && (key === 'a' || key === 'A')) { this.setSelection(E.notes.map(function (n) { return n.id; })); return true; }
  var ids = this.selectedIds(); if (!ids.length) return false;
  if (key === 'Delete' || key === 'Backspace') { this._emit({ type: 'delete', ids: ids }); return true; }
  var st = this.snapTicks(), dT = 0, dP = 0;
  if (key === 'ArrowLeft') dT = -st; else if (key === 'ArrowRight') dT = st; else if (key === 'ArrowUp') dP = m.shift ? 12 : 1; else if (key === 'ArrowDown') dP = m.shift ? -12 : -1; else return false;
  var sel = E.notes.filter(function (n) { return this.sel[n.id]; }, this), lo = Math.min.apply(null, sel.map(function (n) { return n.pitch; })), hi = Math.max.apply(null, sel.map(function (n) { return n.pitch; }));
  dT = Math.max(dT, E.minStart - Math.min.apply(null, sel.map(function (n) { return n.start; }))); dP = clamp(dP, -lo, 127 - hi);
  if (!dT && !dP) return true;
  this._emit({ type: 'move', ids: ids, dTick: dT, dPitch: dP }); if (dP) this._audition(sel[0].pitch + dP); return true;
};

// the cursor: Player seconds -> ticks.  `sec` null = not playing.
G.setClock = function (songSeconds) {
  var d = this.data();
  if (songSeconds === null || songSeconds === undefined || !d) { if (this._cursorTick !== null) { this._cursorTick = null; this.dirty = true; } return; }
  var tick = makeSecToTick(d.ppq, d.tempoEvents)(songSeconds);
  this._cursorTick = tick; this.dirty = true;
  if (this.follow) {   // page-flip: keep the cursor in view
    var x = this.X(tick), v = this.view;
    if (x > v.w - 50 || x < v.gutter + 4) v.tick0 = tick - (v.w - v.gutter) * 0.15 * this.info().ppq / v.ppb;
  }
};

// ---- animation loop + mouse (browser only) ---------------------------------------------------
G.frame = function () {
  if (!this.running) return;
  var sec = this.o.getClock ? this.o.getClock() : null; this.setClock(sec);
  if (this.dirty || sec !== null) this.draw();
  var self = this; this._raf = (typeof requestAnimationFrame === 'function') ? requestAnimationFrame(function () { self.frame(); }) : null;
};
G.start = function () { if (this.running) return; this.running = true; this.dirty = true; this.frame(); };
G.stop = function () { this.running = false; if (this._raf && typeof cancelAnimationFrame === 'function') cancelAnimationFrame(this._raf); this._raf = null; };
G.attach = function () {
  var self = this, c = this.canvas;
  function pos(e) { var r = c.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
  function mods(e) { return { shift: e.shiftKey, alt: e.altKey, ctrl: e.ctrlKey, meta: e.metaKey, button: e.button }; }
  c.addEventListener('wheel', function (e) {
    e.preventDefault(); var p = pos(e);
    if (e.ctrlKey && e.shiftKey) self.zoomY(e.deltaY < 0 ? 1.15 : 1 / 1.15);
    else if (e.ctrlKey) self._zoomX(e.deltaY < 0 ? 1.15 : 1 / 1.15, p.x);
    else if (e.shiftKey) self.scrollBy(0, e.deltaY);
    else self.scrollBy(e.deltaX || e.deltaY, e.deltaX ? e.deltaY : 0);
    if (self.o.onView) self.o.onView();
  }, { passive: false });
  c.addEventListener('mousedown', function (e) { var p = pos(e); self.pointerDown(p.x, p.y, mods(e)); });
  window.addEventListener('mousemove', function (e) { if (self.drag) { var p = pos(e); self.pointerMove(p.x, p.y); c.style.cursor = self.cursorFor(p.x, p.y); } });
  window.addEventListener('mouseup', function (e) { if (self.drag) { var p = pos(e); self.pointerUp(p.x, p.y); c.style.cursor = self.cursorFor(p.x, p.y); } });
  c.addEventListener('mousemove', function (e) { var p = pos(e); self.hover(p.x, p.y); if (!self.drag) c.style.cursor = self.cursorFor(p.x, p.y); if (self.o.onHover) self.o.onHover(self.readout(p.x, p.y)); if (self.o.onChordHover) self.o.onChordHover(self.chordWhy(p.x, p.y)); });
  c.addEventListener('mouseleave', function () { self.hover(null); if (self.o.onChordHover) self.o.onChordHover(null); });
};

var api = { DRUM_NAMES: DRUM_NAMES, GridView: GridView, makeSecToTick: makeSecToTick, meterOf: meterOf, noteName: noteName, drumRow: drumRow, isDrumTrack: isDrumTrack, SNAPS: SNAPS, DRUM_ROWS: DRUM_ROWS };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfGrid = api;
})(typeof window !== 'undefined' ? window : this);
