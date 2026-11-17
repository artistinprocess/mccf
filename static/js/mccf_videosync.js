// MCCF video sync: the tempo map that turns video time (seconds) into score time (bars and beats) and back.
// Pure functions, no DOM; tested in Node. Used by js/mccf_videotab.js.
//
// A map has a base tempo and meter, an offset, and optional sync points. A sync point says "bar N starts at video second T".
//   - Bar 1 starts at `offset` seconds unless a sync point says otherwise.
//   - Between two sync points the bars are evenly spaced, so the tempo stretches to fit (that is how music is fitted to picture).
//   - Before the first point and after the last, the base tempo applies (scaled by `scale`, the music's tempo scale).
//   - Sync points are NOT rescaled by `scale`: they keep their video times.
(function (root) {
  'use strict';

  function clampNum(v, lo, hi, dflt) { v = +v; if (!isFinite(v)) return dflt; return Math.min(hi, Math.max(lo, v)); }

  // opts: { bpm (20..300, default 90), num (beats per bar, 1..16, default 4), den (2,4,8,16; the beat unit, default 4),
  //         offset (seconds, default 0), scale (0.25..2, default 1), points: [{bar, t}] }
  function create(opts) {
    opts = opts || {};
    var m = {
      bpm: clampNum(opts.bpm, 20, 300, 90),
      num: Math.round(clampNum(opts.num, 1, 16, 4)),
      den: [2, 4, 8, 16].indexOf(+opts.den) >= 0 ? +opts.den : 4,
      offset: clampNum(opts.offset, -3600, 3600, 0),
      scale: clampNum(opts.scale, 0.25, 2, 1),
      points: []
    };
    (opts.points || []).forEach(function (p) { addPoint(m, p.bar, p.t); });
    return m;
  }

  // Seconds in one beat at the base tempo. A beat is a 1/den note; bpm counts quarter notes, so an eighth-note beat is half as long.
  function beatSec(m) { return (60 / (m.bpm * m.scale)) * (4 / m.den); }
  function barSec(m) { return beatSec(m) * m.num; }

  // The sync points, plus the implicit start (bar 1 at the offset) unless a point already defines bar 1.
  function anchors(m) {
    var a = m.points.slice();
    if (!a.length || a[0].bar > 1) a.unshift({ bar: 1, t: m.offset, implicit: true });
    return a;
  }

  // The start time (seconds) of a bar (may be fractional, 1-based).
  function barStart(m, bar) {
    var a = anchors(m), bs = barSec(m), i, last = a[a.length - 1];
    if (bar >= last.bar) return last.t + (bar - last.bar) * bs;
    for (i = 0; i < a.length - 1; i++) {
      if (bar >= a[i].bar && bar < a[i + 1].bar) {
        return a[i].t + (bar - a[i].bar) * (a[i + 1].t - a[i].t) / (a[i + 1].bar - a[i].bar);
      }
    }
    return a[0].t + (bar - a[0].bar) * bs;       // before the first anchor (only if the first point is bar > 1 and bar < 1)
  }

  // Where is video second `t`? -> {bar (integer; 0 or less before bar 1), beat (1-based, fractional), pos (bars, 1 = start of bar 1), bpm (quarter notes per minute), seg}
  function locate(m, t) {
    var a = anchors(m), bs = barSec(m), last = a[a.length - 1], pos, bpmHere = m.bpm * m.scale, seg = 'base', i, span;
    if (t >= last.t) pos = last.bar + (t - last.t) / bs;
    else {
      pos = null;
      for (i = 0; i < a.length - 1; i++) {
        if (t >= a[i].t && t < a[i + 1].t) {
          span = (a[i + 1].t - a[i].t) / (a[i + 1].bar - a[i].bar);                 // seconds per bar in this stretch
          pos = a[i].bar + (t - a[i].t) / span;
          bpmHere = (m.num * (4 / m.den)) * 60 / span;                              // quarter notes per minute
          seg = 'stretched';
          break;
        }
      }
      if (pos === null) pos = a[0].bar + (t - a[0].t) / bs;                         // before the first anchor: base tempo, running up to it
    }
    var bar = Math.floor(pos + 1e-9), beat = (pos - bar) * m.num + 1;
    if (beat >= m.num + 1 - 1e-9) { bar += 1; beat = 1; }
    return { bar: bar, beat: beat, pos: pos, bpm: bpmHere, seg: seg };
  }

  // Add or replace a sync point: bar N (integer >= 1) starts at video second t.
  // Returns {ok:true} or {ok:false, error}. Rejected unless bars and times both increase from point to point,
  // so a new point can never reverse time or move the bars of other stretches.
  function addPoint(m, bar, t) {
    bar = Math.round(+bar); t = +t;
    if (!isFinite(bar) || bar < 1 || !isFinite(t)) return { ok: false, error: 'A sync point needs a bar number of 1 or more and a time.' };
    var pts = m.points.filter(function (p) { return p.bar !== bar; });
    pts.push({ bar: bar, t: t }); pts.sort(function (x, y) { return x.bar - y.bar; });
    for (var i = 1; i < pts.length; i++) {
      if (!(pts[i].t > pts[i - 1].t + 0.01)) return { ok: false, error: 'Bar ' + pts[i].bar + ' must come later in the video than bar ' + pts[i - 1].bar + '.' };
    }
    m.points = pts; return { ok: true };
  }
  function removePoint(m, bar) { m.points = m.points.filter(function (p) { return p.bar !== bar; }); }

  // Bar lines between video seconds 0 and `dur`: [{bar, t}] (bars whose start falls inside the video).
  function barLines(m, dur) {
    var out = [], b, t, guard = 0;
    var first = Math.floor(locate(m, 0).pos); if (first < 1) first = 1;
    for (b = first; guard < 5000; b++, guard++) {
      t = barStart(m, b);
      if (t > dur) break;
      if (t >= 0) out.push({ bar: b, t: t });
    }
    return out;
  }

  // Video second -> MIDI tick (quarter-note ticks from bar 1; ppq per quarter), for placing notes against the picture.
  function toTick(m, t, ppq) {
    var p = locate(m, t).pos - 1;
    return Math.round(p * m.num * (4 / m.den) * ppq);
  }
  function fromTick(m, tick, ppq) {
    var pos = 1 + tick / (m.num * (4 / m.den) * ppq);
    return barStart(m, pos);
  }

  // An empty Standard MIDI File that carries this map: the meter, a tempo for every stretch between sync points, and an
  // end-of-track at the last whole bar of the video. Loaded as a theme, Grid and Notation show the empty bars.
  // Returns {bytes:Uint8Array, bars, ppq, barTicks}.
  function toSMF(m, dur, ppq) {
    ppq = ppq || 480;
    var qPerBar = m.num * (4 / m.den), barTicks = Math.round(qPerBar * ppq);
    var end = locate(m, dur).pos - 1, bars = Math.max(1, Math.ceil(end - 1e-9));
    var ev = [], a = anchors(m), i, us;
    function vlq(n) { var b = [n & 127]; n = Math.floor(n / 128); while (n > 0) { b.unshift((n & 127) | 128); n = Math.floor(n / 128); } return b; }
    function meta(t, d) { return [0xFF, t].concat(vlq(d.length), d); }
    function tempo(sec, q) { us = Math.max(1, Math.min(0xFFFFFF, Math.round(sec / q * 1e6))); return meta(0x51, [us >> 16 & 255, us >> 8 & 255, us & 255]); }
    var name = 'Video bars', nb = []; for (i = 0; i < name.length; i++) nb.push(name.charCodeAt(i));
    ev.push({ tick: 0, d: meta(0x03, nb) });
    ev.push({ tick: 0, d: meta(0x58, [m.num, Math.round(Math.log(m.den) / Math.LN2), 24, 8]) });
    for (i = 0; i < a.length; i++) {
      var tk = Math.round((a[i].bar - 1) * barTicks);
      if (i < a.length - 1) ev.push({ tick: tk, d: tempo((a[i + 1].t - a[i].t) / (a[i + 1].bar - a[i].bar), qPerBar) });
      else ev.push({ tick: tk, d: tempo(barSec(m), qPerBar) });
    }
    var endTick = bars * barTicks, body = [], last = 0;
    ev.sort(function (x, y) { return x.tick - y.tick; });
    ev.forEach(function (e) { body = body.concat(vlq(e.tick - last), e.d); last = e.tick; });
    var endT = Math.max(endTick, last);
    body = body.concat(vlq(endT - last), [0xFF, 0x2F, 0]);
    function u32(n) { return [n >>> 24 & 255, n >>> 16 & 255, n >>> 8 & 255, n & 255]; }
    var out = [0x4D, 0x54, 0x68, 0x64].concat(u32(6), [0, 0, 0, 1, ppq >> 8 & 255, ppq & 255], [0x4D, 0x54, 0x72, 0x6B], u32(body.length), body);
    return { bytes: new Uint8Array(out), bars: bars, ppq: ppq, barTicks: barTicks };
  }

  function toJSON(m) { return { bpm: m.bpm, num: m.num, den: m.den, offset: m.offset, points: m.points.map(function (p) { return { bar: p.bar, t: p.t }; }) }; }
  function fmtPos(p) { return 'bar ' + p.bar + ' beat ' + (Math.round(p.beat * 10) / 10).toFixed(1); }

  var api = { create: create, beatSec: beatSec, barSec: barSec, barStart: barStart, locate: locate, addPoint: addPoint, removePoint: removePoint, barLines: barLines, toTick: toTick, fromTick: fromTick, toSMF: toSMF, toJSON: toJSON, fmtPos: fmtPos };
  if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfVideoSync = api;
})(typeof window !== 'undefined' ? window : this);
