/* ==========================================================================
 * mccf_smf_writer.js — canonical Standard MIDI File writer (checkpoint 1a)
 * --------------------------------------------------------------------------
 * Input: a parser-shaped object  {ppq, tempoEvents, timeSigEvents, keySigEvents, tracks[]}
 * (what parseMidiFile() returns, and what MccfTheory.assemble() builds).
 * Output: {bytes: Uint8Array, warnings: [...]}  — a format-1 SMF.
 *
 * CANONICAL SERIALIZATION.  The same input always yields the same bytes:
 *   - fixed header; track 0 = conductor, then one track per input track, in input order
 *   - events at equal ticks always in this order:
 *       meta (name, text, time sig, key sig, tempo)  <  CC0  <  CC32  <  Program Change
 *       <  other CCs (ascending number, then input order)  <  note-offs  <  note-ons
 *     note-offs/ons ordered by pitch, then channel
 *   - no running status, note-offs are 0x80 with velocity 64, VLQs are minimal
 *   - integers only: ticks are rounded once, here, with Math.round; durations >= 1 tick
 *   - same channel+pitch notes that overlap are trimmed to the next note's start (duplicates dropped)
 *   - every track ends with End-of-Track at the same tick (the end of the longest track)
 *   - no timestamps, no generated IDs, no environment-dependent data
 * Browser-free: runs under Node and in the page (window.MccfSmfWriter).
 * ========================================================================== */
(function (root) {
'use strict';

function vlq(n) {
  n = Math.max(0, Math.round(n));
  var out = [n & 0x7f]; n = Math.floor(n / 128);
  while (n > 0) { out.unshift((n & 0x7f) | 0x80); n = Math.floor(n / 128); }
  return out;
}
function u32(n) { return [(n >>> 24) & 255, (n >>> 16) & 255, (n >>> 8) & 255, n & 255]; }
function u16(n) { return [(n >> 8) & 255, n & 255]; }
function ascii(s) { var o = []; for (var i = 0; i < s.length; i++) { var c = s.charCodeAt(i); o.push(c < 256 ? c : 63); } return o; }
function push(dst, src) { for (var i = 0; i < src.length; i++) dst.push(src[i]); }
function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, Math.round(v))); }

// An event is {tick, cls, k1, k2, bytes}; cls orders events within one tick (see header).
var CLS = { META: 0, CC0: 1, CC32: 2, PROG: 3, CC: 4, OFF: 5, ON: 6 };

function metaEv(tick, order, type, payload) {
  return { tick: tick, cls: CLS.META, k1: order, k2: 0, bytes: [0xFF, type].concat(vlq(payload.length), payload) };
}
function sortEvents(evs) {
  return evs.map(function (e, i) { e.i = i; return e; }).sort(function (a, b) {
    return (a.tick - b.tick) || (a.cls - b.cls) || (a.k1 - b.k1) || (a.k2 - b.k2) || (a.i - b.i);
  });
}
function encodeTrack(evs, endTick) {
  var body = [], last = 0;
  sortEvents(evs).forEach(function (e) { push(body, vlq(e.tick - last)); push(body, e.bytes); last = e.tick; });
  push(body, vlq(Math.max(0, endTick - last))); push(body, [0xFF, 0x2F, 0x00]);
  return [0x4D, 0x54, 0x72, 0x6B].concat(u32(body.length), body);
}

// Trim overlapping same-(channel,pitch) notes so the file pairs on/off unambiguously.
function cleanNotes(notes, where, warnings) {
  var groups = {}, out = [], trimmed = 0, dropped = 0;
  notes.forEach(function (n) {
    var c = { pitch: clamp(n.pitch, 0, 127), start: Math.max(0, Math.round(n.startTick)),
              dur: Math.max(1, Math.round(n.durTicks)), vel: clamp(n.velocity === undefined ? 90 : n.velocity, 1, 127),
              ch: clamp(n.channel === undefined ? 0 : n.channel, 0, 15) };
    (groups[c.ch + ':' + c.pitch] || (groups[c.ch + ':' + c.pitch] = [])).push(c);
  });
  Object.keys(groups).sort().forEach(function (k) {
    var g = groups[k].sort(function (a, b) { return (a.start - b.start) || (b.dur - a.dur) || (b.vel - a.vel); });
    for (var i = 0; i < g.length; i++) {
      var cur = g[i], nxt = g[i + 1];
      if (nxt && nxt.start === cur.start) { dropped++; continue; }            // duplicate onset: keep the longer
      if (nxt && nxt.start < cur.start + cur.dur) { cur.dur = nxt.start - cur.start; trimmed++; }
      out.push(cur);
    }
  });
  if (trimmed || dropped) warnings.push(where + ': ' + trimmed + ' overlapping note(s) trimmed, ' + dropped + ' duplicate(s) dropped');
  return out;
}

function writeSMF(arr, opts) {
  opts = opts || {};
  var warnings = [], ppq = arr.ppq, tracksOut = [];
  var cleaned = arr.tracks.map(function (tr) { return cleanNotes(tr.notes, 'track "' + tr.name + '"', warnings); });

  // end of file = end of the longest note, or any later control/meta tick
  var endTick = 0;
  cleaned.forEach(function (ns) { ns.forEach(function (n) { endTick = Math.max(endTick, n.start + n.dur); }); });
  (arr.tempoEvents || []).forEach(function (e) { endTick = Math.max(endTick, Math.round(e.tick)); });
  arr.tracks.forEach(function (tr) {
    Object.keys(tr.controllers || {}).forEach(function (cc) {
      tr.controllers[cc].forEach(function (c) { endTick = Math.max(endTick, Math.round(c.tick)); });
    });
  });
  if (opts.endTick !== undefined) endTick = Math.max(endTick, Math.round(opts.endTick));

  // ---- track 0: conductor ------------------------------------------------
  var cond = [];
  cond.push(metaEv(0, 0, 0x03, ascii(opts.name || 'Conductor')));
  if (opts.comment) cond.push(metaEv(0, 1, 0x01, ascii(opts.comment)));
  (arr.timeSigEvents || []).forEach(function (e) {
    var dd = Math.round(Math.log(e.den) / Math.LN2);
    cond.push(metaEv(Math.round(e.tick), 2, 0x58, [e.num & 255, dd & 255, (e.clocks === undefined ? 24 : e.clocks) & 255, (e.n32 === undefined ? 8 : e.n32) & 255]));
  });
  (arr.keySigEvents || []).forEach(function (e) {
    cond.push(metaEv(Math.round(e.tick), 3, 0x59, [e.sharps & 255, e.minor ? 1 : 0]));
  });
  (arr.tempoEvents || []).forEach(function (e, i) {
    var us = Math.round(e.usPerQuarter);
    cond.push(metaEv(Math.round(e.tick), 4, 0x51, [(us >> 16) & 255, (us >> 8) & 255, us & 255]));
  });
  tracksOut.push(encodeTrack(cond, endTick));

  // ---- one track per input track ----------------------------------------
  arr.tracks.forEach(function (tr, ti) {
    var evs = [], ch = clamp(tr.channel || 0, 0, 15);
    evs.push(metaEv(0, 0, 0x03, ascii(tr.name || ('Track ' + (ti + 1)))));
    // Program Change: one per channel when the track carries a `programs` map (multi-channel tracks),
    // else tr.program on the track's own channel.
    var progs = tr.programs && Object.keys(tr.programs).length ? tr.programs
              : (tr.program !== null && tr.program !== undefined ? (function () { var o = {}; o[ch] = tr.program; return o; })() : {});
    Object.keys(progs).map(Number).sort(function (a, b) { return a - b; }).forEach(function (c) {
      evs.push({ tick: 0, cls: CLS.PROG, k1: c, k2: 0, bytes: [0xC0 | clamp(c, 0, 15), clamp(progs[c], 0, 127)] });
    });
    Object.keys(tr.controllers || {}).map(Number).sort(function (a, b) { return a - b; }).forEach(function (cc) {
      tr.controllers[cc].forEach(function (c, idx) {
        var cls = cc === 0 ? CLS.CC0 : cc === 32 ? CLS.CC32 : CLS.CC;
        evs.push({ tick: Math.max(0, Math.round(c.tick)), cls: cls, k1: cc, k2: idx,
                   bytes: [0xB0 | clamp(c.channel === undefined ? ch : c.channel, 0, 15), cc & 127, clamp(c.value, 0, 127)] });
      });
    });
    cleaned[ti].forEach(function (n) {
      evs.push({ tick: n.start, cls: CLS.ON, k1: n.pitch, k2: n.ch, bytes: [0x90 | n.ch, n.pitch, n.vel] });
      evs.push({ tick: n.start + n.dur, cls: CLS.OFF, k1: n.pitch, k2: n.ch, bytes: [0x80 | n.ch, n.pitch, 64] });
    });
    tracksOut.push(encodeTrack(evs, endTick));
  });

  var head = [0x4D, 0x54, 0x68, 0x64].concat(u32(6), u16(1), u16(tracksOut.length), u16(ppq));
  var all = head; tracksOut.forEach(function (t) { push(all, t); });
  return { bytes: new Uint8Array(all), warnings: warnings };
}

var api = { writeSMF: writeSMF, vlq: vlq };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
else root.MccfSmfWriter = api;
})(typeof window !== 'undefined' ? window : this);
