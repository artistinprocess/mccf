/* ==========================================================================
 * mccf_midi.js — shared MIDI file parsing + playback for MCCF pages
 * --------------------------------------------------------------------------
 * Used by mccf_ambient.html (theme player), mccf_x3d_loader.html (MIDI cues on
 * the scene clock) and, later, the Events Editor (track list / mixer pane).
 * Exposes one global:  window.MccfMidi  (also module.exports under Node).
 *
 *   MccfMidi.parseMidiFile(arrayBuffer)  -> {format, ppq, ntrks, tempoEvents, tracks[]}
 *   MccfMidi.Player                      -> multi-track player (see class below)
 *   MccfMidi.GM_PROGRAMS / GM_DRUM_KITS / PC_NAMES / trackColor / fmtClock / clamp127
 *
 * The parser and player were developed and tested inside mccf_ambient.html
 * (24 parser tests, live Roland/MOTU rig) and moved here unchanged in
 * behaviour; the only change is that playback state now lives on a Player
 * instance instead of page globals, so more than one page can use it.
 * ========================================================================== */
(function (root) {
'use strict';

// ---------------------------------------------------------------------------
// Standard MIDI File parser — format 0/1, PPQN division. Control Change events
// are captured per track as a generic map: track.controllers[ccNumber] =
// [{tick, value, channel}, ...].
// ---------------------------------------------------------------------------
function _readVLQ(bytes, pos) {
  let value = 0, b;
  do {
    b = bytes[pos.i++];
    value = (value << 7) | (b & 0x7f);
  } while (b & 0x80);
  return value;
}

function parseMidiFile(arrayBuffer) {
  const bytes = new Uint8Array(arrayBuffer);
  const pos = { i: 0 };
  function readStr(n) { let s=''; for (let k=0;k<n;k++) s += String.fromCharCode(bytes[pos.i++]); return s; }
  function readU32() { const v=(bytes[pos.i]<<24)|(bytes[pos.i+1]<<16)|(bytes[pos.i+2]<<8)|bytes[pos.i+3]; pos.i+=4; return v>>>0; }
  function readU16() { const v=(bytes[pos.i]<<8)|bytes[pos.i+1]; pos.i+=2; return v; }

  if (readStr(4) !== 'MThd') throw new Error('Not a Standard MIDI File (missing MThd header)');
  const headerLen = readU32();
  const format    = readU16();
  const ntrks     = readU16();
  const division  = readU16();
  pos.i += Math.max(0, headerLen - 6); // tolerate a non-standard header length
  if (division & 0x8000) {
    throw new Error('SMPTE time division not supported — only PPQN (ticks-per-quarter-note) files can be imported');
  }
  const ppq = division;

  const tracks = [];
  const tempoEvents = []; // {tick, usPerQuarter}, collected across ALL tracks
  const timeSigEvents = []; // {tick, num, den, clocks, n32}, collected across ALL tracks
  const keySigEvents  = []; // {tick, sharps (-7..+7), minor}, collected across ALL tracks

  for (let t = 0; t < ntrks; t++) {
    if (readStr(4) !== 'MTrk') throw new Error('Malformed file — expected MTrk chunk for track ' + t);
    const trackLen = readU32();
    const trackEnd = pos.i + trackLen;

    let tick = 0, runningStatus = null;
    let name = null, program = null;
    const programs = {};   // channel -> first Program Change seen on that channel (0-based channel)
    const channelsSeen = new Set();
    const openNotes = {}; // "channel:pitch" -> {startTick, velocity}
    const notes = [];
    const controllers = {}; // ccNumber -> [{tick, value, channel}], in file order

    while (pos.i < trackEnd) {
      tick += _readVLQ(bytes, pos);
      let statusByte = bytes[pos.i];
      if (statusByte < 0x80) {
        // Running status — reuse the last channel-message status byte,
        // this byte is actually the first data byte (matches test fixture).
        statusByte = runningStatus;
      } else {
        pos.i++;
        if (statusByte < 0xF0) runningStatus = statusByte; // only channel messages set running status
      }

      if (statusByte === 0xFF) {
        const metaType = bytes[pos.i++];
        const len = _readVLQ(bytes, pos);
        const payload = bytes.slice(pos.i, pos.i + len);
        pos.i += len;
        if (metaType === 0x03 && name === null) {
          name = Array.from(payload).map(c => String.fromCharCode(c)).join('');
        } else if (metaType === 0x51 && len === 3) {
          tempoEvents.push({ tick, usPerQuarter: (payload[0]<<16)|(payload[1]<<8)|payload[2] });
        } else if (metaType === 0x58 && len >= 2) {
          timeSigEvents.push({ tick, num: payload[0], den: Math.pow(2, payload[1]),
                               clocks: payload[2], n32: payload[3] });
        } else if (metaType === 0x59 && len === 2) {
          keySigEvents.push({ tick, sharps: (payload[0] << 24) >> 24, minor: payload[1] === 1 });
        }
        // other meta types (lyrics, markers, etc.) intentionally not extracted
      } else if (statusByte === 0xF0 || statusByte === 0xF7) {
        const len = _readVLQ(bytes, pos);
        pos.i += len; // sysex — skip, not relevant to note import
      } else {
        const kind = statusByte & 0xF0, ch = statusByte & 0x0F;
        channelsSeen.add(ch);
        if (kind === 0x90 || kind === 0x80) {
          const pitch = bytes[pos.i++], vel = bytes[pos.i++];
          const key = ch + ':' + pitch;
          if (kind === 0x90 && vel > 0) {
            openNotes[key] = { startTick: tick, velocity: vel };
          } else {
            // note-off, OR note-on with velocity 0 (standard "running status
            // note-off" convention some exporters use instead of real 0x80)
            const open = openNotes[key];
            if (open) {
              notes.push({ pitch, startTick: open.startTick, durTicks: Math.max(1, tick - open.startTick),
                           velocity: open.velocity, channel: ch });
              delete openNotes[key];
            }
          }
        } else if (kind === 0xC0) {
          const prog = bytes[pos.i++];
          if (program === null) program = prog;
          if (programs[ch] === undefined) programs[ch] = prog;
        } else if (kind === 0xB0) {
          // Control Change — captured as a generic per-track CC map (CC7 volume,
          // CC10 pan, CC11 expression, sustain, ...), not a hardcoded subset.
          const ccNum = bytes[pos.i++], ccVal = bytes[pos.i++];
          (controllers[ccNum] || (controllers[ccNum] = [])).push({ tick, value: ccVal, channel: ch });
        } else if (kind === 0xA0 || kind === 0xE0) {
          pos.i += 2; // aftertouch / pitch bend — 2 data bytes, still skipped
        } else if (kind === 0xD0) {
          pos.i += 1; // channel pressure — 1 data byte
        }
      }
    }
    pos.i = trackEnd; // tolerate any trailing bytes this loop didn't consume

    // Any note-on left open at end of track (malformed/truncated file) —
    // close it at the track's own end rather than dropping it silently.
    Object.keys(openNotes).forEach(key => {
      const [chStr, pitchStr] = key.split(':');
      const open = openNotes[key];
      notes.push({ pitch: parseInt(pitchStr,10), startTick: open.startTick,
                   durTicks: Math.max(1, tick - open.startTick), velocity: open.velocity,
                   channel: parseInt(chStr,10) });
    });

    notes.sort((a,b) => a.startTick - b.startTick);
    tracks.push({
      index: t, name: name || ('Track ' + (t+1)), channel: channelsSeen.size ? [...channelsSeen][0] : 0,
      channelsSeen: [...channelsSeen], program, programs, notes, noteCount: notes.length, controllers,
      // A noteless track named 'Video bars' (made by the Video tab) takes its length from its end-of-track, so Grid and Notation show the empty bars.
      lengthTicks: Math.max(notes.reduce((m,n) => Math.max(m, n.startTick + n.durTicks), 0), (!notes.length && /^Video bars/.test(name || '')) ? tick : 0)
    });
  }

  tempoEvents.sort((a,b) => a.tick - b.tick);
  if (!tempoEvents.length) tempoEvents.push({ tick: 0, usPerQuarter: 500000 }); // default 120bpm, per spec

  timeSigEvents.sort((a,b) => a.tick - b.tick);
  keySigEvents.sort((a,b) => a.tick - b.tick);
  // timeSigEvents / keySigEvents may be empty; consumers assume 4/4 and no key.
  return { format, ppq, ntrks, tempoEvents, timeSigEvents, keySigEvents, tracks };
}

// Build a tick -> seconds converter from the tempo map, standard SMF
// algorithm: walk tempo segments in order, accumulating real time.
function makeTickToSeconds(ppq, tempoEvents) {
  const segments = tempoEvents.map((te, i) => ({
    tick: te.tick, usPerQuarter: te.usPerQuarter,
    nextTick: (i+1 < tempoEvents.length) ? tempoEvents[i+1].tick : Infinity
  }));
  return function tickToSeconds(targetTick) {
    let seconds = 0;
    for (const seg of segments) {
      if (targetTick <= seg.tick) break;
      const segEndTick = Math.min(targetTick, seg.nextTick);
      const ticksInSeg = segEndTick - seg.tick;
      seconds += (ticksInSeg * seg.usPerQuarter / ppq) / 1e6;
      if (targetTick <= seg.nextTick) break;
    }
    return seconds;
  };
}

// ---------------------------------------------------------------------------
// Small shared helpers / tables
// ---------------------------------------------------------------------------
function clamp127(v) { return Math.max(0, Math.min(127, Math.round(v))); }
function trackColor(index) { return 'hsl(' + ((index * 67 + 190) % 360) + ',75%,62%)'; }
function fmtClock(sec) {
  var m = Math.floor(sec / 60), s = sec - m * 60;
  return String(m).padStart(2, '0') + ':' + (s < 10 ? '0' : '') + s.toFixed(1);
}
var PC_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'];

// General MIDI Level 1 instrument names, indexed by the 0-based program number
// stored in the file (prog 24 = "Acoustic Guitar (nylon)").
var GM_PROGRAMS = [
'Acoustic Grand Piano','Bright Acoustic Piano','Electric Grand Piano','Honky-tonk Piano','Electric Piano 1','Electric Piano 2','Harpsichord','Clavinet',
'Celesta','Glockenspiel','Music Box','Vibraphone','Marimba','Xylophone','Tubular Bells','Dulcimer',
'Drawbar Organ','Percussive Organ','Rock Organ','Church Organ','Reed Organ','Accordion','Harmonica','Tango Accordion',
'Acoustic Guitar (nylon)','Acoustic Guitar (steel)','Electric Guitar (jazz)','Electric Guitar (clean)','Electric Guitar (muted)','Overdriven Guitar','Distortion Guitar','Guitar Harmonics',
'Acoustic Bass','Electric Bass (finger)','Electric Bass (pick)','Fretless Bass','Slap Bass 1','Slap Bass 2','Synth Bass 1','Synth Bass 2',
'Violin','Viola','Cello','Contrabass','Tremolo Strings','Pizzicato Strings','Orchestral Harp','Timpani',
'String Ensemble 1','String Ensemble 2','Synth Strings 1','Synth Strings 2','Choir Aahs','Voice Oohs','Synth Voice','Orchestra Hit',
'Trumpet','Trombone','Tuba','Muted Trumpet','French Horn','Brass Section','Synth Brass 1','Synth Brass 2',
'Soprano Sax','Alto Sax','Tenor Sax','Baritone Sax','Oboe','English Horn','Bassoon','Clarinet',
'Piccolo','Flute','Recorder','Pan Flute','Blown Bottle','Shakuhachi','Whistle','Ocarina',
'Lead 1 (square)','Lead 2 (sawtooth)','Lead 3 (calliope)','Lead 4 (chiff)','Lead 5 (charang)','Lead 6 (voice)','Lead 7 (fifths)','Lead 8 (bass + lead)',
'Pad 1 (new age)','Pad 2 (warm)','Pad 3 (polysynth)','Pad 4 (choir)','Pad 5 (bowed)','Pad 6 (metallic)','Pad 7 (halo)','Pad 8 (sweep)',
'FX 1 (rain)','FX 2 (soundtrack)','FX 3 (crystal)','FX 4 (atmosphere)','FX 5 (brightness)','FX 6 (goblins)','FX 7 (echoes)','FX 8 (sci-fi)',
'Sitar','Banjo','Shamisen','Koto','Kalimba','Bagpipe','Fiddle','Shanai',
'Tinkle Bell','Agogo','Steel Drums','Woodblock','Taiko Drum','Melodic Tom','Synth Drum','Reverse Cymbal',
'Guitar Fret Noise','Breath Noise','Seashore','Bird Tweet','Telephone Ring','Helicopter','Applause','Gunshot'
];
// On channel 10 the program number selects a drum KIT, not an instrument
// (Roland GS / GM2 kit numbers).
var GM_DRUM_KITS = { 0:'Standard Kit', 8:'Room Kit', 16:'Power Kit', 24:'Electronic Kit', 25:'TR-808 Kit',
                     32:'Jazz Kit', 40:'Brush Kit', 48:'Orchestra Kit', 56:'SFX Kit' };

// ---------------------------------------------------------------------------
// Player — plays a parsed file's tracks to a Web MIDI output (or, as a crude
// fallback, to Web Audio oscillators). Host pages supply the outputs by
// callback so this file never touches page globals or the DOM:
//
//   new MccfMidi.Player({
//     getMidiOutput:      () => MIDIOutput | null,
//     getOutputMode:      () => 'midi' | 'audio',
//     getAudioContext:    () => AudioContext | null,      // 'audio' mode only
//     getAudioDestination:() => AudioNode | null,         // 'audio' mode only
//     onEnd:              () => {}                        // finished, not looping
//   })
//
// Scheduling: background tabs throttle main-thread timers to ~1 Hz, which
// makes hardware sputter when a window loses focus. So a Web Worker supplies
// the clock (not throttled with the tab) and notes are handed to Web MIDI a
// short lookahead early WITH a hardware timestamp.
// ---------------------------------------------------------------------------
var _allPlayers = [];

function Player(opts) {
  opts = opts || {};
  this.getMidiOutput       = opts.getMidiOutput       || function () { return null; };
  this.getOutputMode       = opts.getOutputMode       || function () { return 'midi'; };
  this.getAudioContext     = opts.getAudioContext     || function () { return null; };
  this.getAudioDestination = opts.getAudioDestination|| function () { return null; };
  this.onEnd = opts.onEnd || null;
  this.now = opts.now || function () { return performance.now(); };
  // Lookahead = how far ahead of "now" notes are handed to Web MIDI (with a hardware
  // timestamp). It ADAPTS: normally minLookahead, but when the page's main thread
  // stalls (heavy X3D scenes, movie decode) it grows to cover the stalls, so a busy
  // page delays nothing. The cost of a big lookahead is only how far ahead things
  // are queued; stop() cancels the queued remainder (see _release).
  this.minLookahead = 0.15;
  this.maxLookahead = 1.5;
  this.lookahead = 0.15;
  this.quiet = !!opts.quiet;      // suppress console diagnostics
  this.stats = { maxGapMs: 0, lateNotes: 0 };
  this._gaps = []; this._lastPumpMs = 0; this._lateLogged = 0; this._lateLogAt = 0;

  this.data = null;               // parseMidiFile() result
  this.enabled = {};              // track index -> bool
  this.channelOverride = {};      // track index -> output channel 1..16 (absent = file's own)
  this.volume = {};               // track index -> 0..127 (seeded from the file's first CC7)
  this.tempoScale = 1;
  this.playScale = 1;             // scale in effect when playback was last scheduled
  this.loop = true;
  this.polyOn = true;             // CC127 before playback (mitigation for mono patches)
  this.sendSetup = true;          // file's Bank/Program/Pan/Reverb/Chorus before playback
  this.playing = false;
  this.paused = false; this._pausedAt = 0;
  this.startWall = 0;             // now() at (virtual) playback position 0
  this.viz = [];                  // {pitch,vel,track,drum,startMs,endMs} for visualizations

  this._events = []; this._idx = 0; this._endSec = 0;
  this._recent = [];              // tokens for every note handed to the device recently: {channel,pitch,ts,offTs}
  this._voices = [];              // Web Audio voices (audio mode)
  this._gains = {};               // per-track GainNodes (audio mode)
  this._worker = null; this._workerUrl = null; this._timer = null;
  this._keyCache = null;
  this._pumpBound = this._pump.bind(this);
  _allPlayers.push(this);
}

var P = Player.prototype;

P.dispose = function () {
  this.stop();
  var i = _allPlayers.indexOf(this); if (i >= 0) _allPlayers.splice(i, 1);
};

P.load = function (arrayBuffer) {
  var d = parseMidiFile(arrayBuffer);
  this.stop();
  this.data = d;
  this.enabled = {}; this.channelOverride = {}; this.volume = {}; this._gains = {};
  var self = this;
  d.tracks.forEach(function (tr) {
    self.enabled[tr.index] = tr.noteCount > 0;   // empty tracks (e.g. Conductor) start off
    self.volume[tr.index] = self.fileVolume(tr);
  });
  this._keyCache = null;
  return d;
};

// Apply saved per-track settings, e.g. from scene XML:
//   [{index, enabled, channel (1-16), volume (0-127)}, ...]  — every field optional
P.applyTrackSettings = function (list) {
  var self = this;
  (list || []).forEach(function (t) {
    if (t.enabled !== undefined) self.enabled[t.index] = !!t.enabled;
    if (t.channel >= 1 && t.channel <= 16) self.channelOverride[t.index] = t.channel;
    if (t.volume >= 0 && t.volume <= 127) self.volume[t.index] = t.volume;
  });
  this._keyCache = null;
};

// Volume the file itself authored for a track: its earliest CC7, else 100.
P.fileVolume = function (tr) {
  var list = tr.controllers && tr.controllers[7];
  if (!list || !list.length) return 100;
  return list.reduce(function (a, b) { return b.tick < a.tick ? b : a; }).value;
};

// Output channel (0-15) a track's notes go out on: override, else the file's.
P.resolvedChannel = function (tr) {
  var o = this.channelOverride[tr.index];
  return ((o !== undefined ? o : (tr.channel + 1)) - 1) & 0x0f;
};

P.instrumentName = function (tr) {
  if (this.resolvedChannel(tr) === 9) {   // drums follow the OUTPUT channel
    return tr.program === null ? 'Drums' : (GM_DRUM_KITS[tr.program] || ('Drum Kit ' + tr.program));
  }
  return tr.program === null ? '(no program in file)' : (GM_PROGRAMS[tr.program] || ('Program ' + tr.program));
};

// ---- live controls (each re-schedules from the current position if playing)
P.setEnabled = function (i, on) { this.enabled[i] = !!on; this._keyCache = null; this.reschedule(); };
P.setChannel = function (i, ch) {
  ch = parseInt(ch, 10);
  if (!(ch >= 1 && ch <= 16)) return;
  this.channelOverride[i] = ch; this._keyCache = null;
  this.reschedule(); // stop() releases notes on the channel they STARTED on
};
P.resetChannels = function () { this.channelOverride = {}; this._keyCache = null; this.reschedule(); };
P.setTempoScale = function (v) { this.tempoScale = parseFloat(v) || 1; }; // applies at next (re)schedule
P.setVolume = function (i, v) {
  v = clamp127(parseInt(v, 10) || 0);
  this.volume[i] = v;
  if (!this.playing || !this.data) return;
  var tr = this.data.tracks.filter(function (t) { return t.index === i; })[0];
  if (!tr) return;
  if (this.getOutputMode() === 'midi') this._send([0xB0 | this.resolvedChannel(tr), 7, v]);
  else if (this._gains[i]) {
    var ctx = this.getAudioContext();
    try { this._gains[i].gain.setTargetAtTime(v / 100, ctx.currentTime, 0.02); } catch (e) {}
  }
};

// ---- position / info
P.elapsed = function () { return this.playing ? Math.max(0, (this.now() - this.startWall) / 1000) : (this.paused ? this._pausedAt : 0); };
P.totalSeconds = function () {
  if (!this.data) return 0;
  var t2s = makeTickToSeconds(this.data.ppq, this.data.tempoEvents), self = this, maxTick = 0;
  this.data.tracks.forEach(function (tr) { if (self.enabled[tr.index]) maxTick = Math.max(maxTick, tr.lengthTicks); });
  return t2s(maxTick) / this.tempoScale;
};
P.currentBpm = function () {
  var te = this.data.tempoEvents, t2s = makeTickToSeconds(this.data.ppq, te);
  var musical = this.playing ? this.elapsed() * this.playScale : 0, cur = te[0];
  for (var k = 0; k < te.length; k++) { if (t2s(te[k].tick) <= musical) cur = te[k]; else break; }
  return (60e6 / cur.usPerQuarter) * this.tempoScale;
};

// Krumhansl-Schmuckler key estimate over duration-weighted pitch classes of
// the enabled, non-drum tracks. -> {pc, mode:'major'|'minor', r} | null
P.estimateKey = function () {
  if (this._keyCache) return this._keyCache;
  if (!this.data) return null;
  var self = this, hist = []; for (var i = 0; i < 12; i++) hist.push(0);
  this.data.tracks.forEach(function (tr) {
    if (!self.enabled[tr.index] || self.resolvedChannel(tr) === 9) return;
    tr.notes.forEach(function (n) { hist[n.pitch % 12] += n.durTicks; });
  });
  if (!hist.reduce(function (a, b) { return a + b; }, 0)) return null;
  var MAJ = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88];
  var MIN = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17];
  function corr(a, b) {
    var ma = a.reduce(function (x, y) { return x + y; }, 0) / 12, mb = b.reduce(function (x, y) { return x + y; }, 0) / 12;
    var num = 0, da = 0, db = 0;
    for (var j = 0; j < 12; j++) { num += (a[j]-ma)*(b[j]-mb); da += (a[j]-ma)*(a[j]-ma); db += (b[j]-mb)*(b[j]-mb); }
    return (da && db) ? num / Math.sqrt(da * db) : -1;
  }
  var best = { r: -2 };
  for (var k = 0; k < 12; k++) {
    var rot = hist.map(function (_, j) { return hist[(j + k) % 12]; });
    var rM = corr(rot, MAJ), rm = corr(rot, MIN);
    if (rM > best.r) best = { r: rM, pc: k, mode: 'major' };
    if (rm > best.r) best = { r: rm, pc: k, mode: 'minor' };
  }
  this._keyCache = best;
  return best;
};

// What is sounding right now (for meters/visualizations).
P.sounding = function () {
  var now = this.now(), pcVel = [], pcTrack = [], voices = 0;
  for (var i = 0; i < 12; i++) { pcVel.push(0); pcTrack.push(-1); }
  if (this.playing) this.viz.forEach(function (n) {
    if (n.drum || now < n.startMs || (n.endMs !== null && now >= n.endMs)) return;
    voices++;
    var pc = n.pitch % 12;
    if (n.vel > pcVel[pc]) { pcVel[pc] = n.vel; pcTrack[pc] = n.track; }
  });
  return { voices: voices, pcVel: pcVel, pcTrack: pcTrack };
};

// ---- MIDI plumbing
P._send = function (msg, tsMs) {
  var out = this.getMidiOutput();
  if (!out) return false;
  try { if (tsMs === undefined) out.send(msg); else out.send(msg, tsMs); return true; } catch (e) { return false; }
};

// Panic: All Sound Off + All Notes Off + Reset Controllers, all 16 channels.
P.panic = function () {
  for (var ch = 0; ch < 16; ch++) {
    this._send([0xB0 | ch, 120, 0]); this._send([0xB0 | ch, 123, 0]); this._send([0xB0 | ch, 121, 0]);
  }
};

// Sent once per channel in use, before any note: Poly On, then the file's own
// Bank Select / Program Change / Pan / Reverb / Chorus, then the volume.
// Without Program Change the synth stays on its power-on patches (piano, and
// the drum kit on ch10).
P._sendChannelSetup = function () {
  if (this.getOutputMode() !== 'midi' || !this.getMidiOutput()) return false;
  var self = this, any = false, polySent = {};
  function first(tr, cc) {
    var list = tr.controllers && tr.controllers[cc];
    return (list && list.length) ? list.reduce(function (a, b) { return b.tick < a.tick ? b : a; }).value : null;
  }
  this.data.tracks.forEach(function (tr) {
    if (!self.enabled[tr.index] || !tr.noteCount) return;
    var ch = self.resolvedChannel(tr);
    function send(m) { if (self._send(m)) any = true; }
    if (self.polyOn && !polySent[ch]) { send([0xB0 | ch, 127, 0]); polySent[ch] = true; }
    if (self.sendSetup) {
      var msb = first(tr, 0), lsb = first(tr, 32);
      if (msb !== null) send([0xB0 | ch, 0, clamp127(msb)]);
      if (lsb !== null) send([0xB0 | ch, 32, clamp127(lsb)]);
      if (tr.program !== null) send([0xC0 | ch, clamp127(tr.program)]);
      [10, 11, 91, 93].forEach(function (cc) { var v = first(tr, cc); if (v !== null) send([0xB0 | ch, cc, clamp127(v)]); });
    }
    send([0xB0 | ch, 7, clamp127(self.volume[tr.index] !== undefined ? self.volume[tr.index] : 100)]);
  });
  return any;
};

// ---- Web Audio fallback (crude triangle-wave voices)
// Sound ONE note right now, on a track's own channel and patch (clicking a piano key; placing or moving a note on the
// grid).  Safe while playing or stopped; the note-off is scheduled so nothing can hang.  -> true if it was sent.
P.audition = function (pitch, velocity, trackIndex, ms) {
  ms = ms || 350; velocity = Math.max(1, clamp127(velocity || 90)); pitch = clamp127(pitch);
  var tr = this.data && this.data.tracks[trackIndex], self = this;
  if (this.getOutputMode() === 'midi' && this.getMidiOutput()) {
    var ch = tr ? this.resolvedChannel(tr) : 0;
    if (tr && tr.program !== null && tr.program !== undefined) this._send([0xC0 | ch, clamp127(tr.program)]);
    this._send([0xB0 | ch, 7, clamp127(this.volume[trackIndex] !== undefined ? this.volume[trackIndex] : 100)]);
    if (!this._send([0x90 | ch, pitch, velocity])) return false;
    setTimeout(function () { self._send([0x80 | ch, pitch, 0]); }, ms);
    return true;
  }
  if (!this.getAudioContext()) return false;
  this._playAudioNote(pitch, 0, ms / 1000, velocity / 127, this._trackGain(trackIndex));
  return true;
};
P._trackGain = function (index) {
  var ctx = this.getAudioContext();
  if (!ctx) return null;
  if (!this._gains[index]) {
    try {
      var g = ctx.createGain();
      g.gain.value = (this.volume[index] !== undefined ? this.volume[index] : 100) / 100;
      var dest = this.getAudioDestination() || ctx.destination;
      g.connect(dest);
      this._gains[index] = g;
    } catch (e) { return null; }
  }
  return this._gains[index];
};
P._playAudioNote = function (pitch, delaySec, durSec, vel01, destNode) {
  var ctx = this.getAudioContext();
  if (!ctx) return;
  var t = ctx.currentTime + Math.max(0, delaySec);
  var osc = ctx.createOscillator(); osc.type = 'triangle';
  osc.frequency.value = 440 * Math.pow(2, (pitch - 69) / 12);
  var g = ctx.createGain();
  g.gain.setValueAtTime(0, t);
  g.gain.linearRampToValueAtTime(0.18 * vel01, t + Math.min(0.03, durSec * 0.2));
  g.gain.linearRampToValueAtTime(0, t + durSec);
  osc.connect(g); g.connect(destNode || this.getAudioDestination() || ctx.destination);
  osc.start(t); osc.stop(t + durSec + 0.02);
  this._voices.push({ osc: osc, g: g });
};

// ---- scheduler
P._pumpStart = function () {
  this._pumpStop();
  this._lastPumpMs = 0;
  try {
    this._workerUrl = URL.createObjectURL(new Blob(['setInterval(function(){postMessage(0)},15)'], { type: 'text/javascript' }));
    this._worker = new Worker(this._workerUrl);
    this._worker.onmessage = this._pumpBound;
  } catch (e) {
    this._worker = null;
    this._timer = setInterval(this._pumpBound, 20); // fallback: main-thread timer (throttled when unfocused)
  }
};
P._pumpStop = function () {
  if (this._worker) { try { this._worker.terminate(); } catch (e) {} this._worker = null; }
  if (this._workerUrl) { try { URL.revokeObjectURL(this._workerUrl); } catch (e) {} this._workerUrl = null; }
  if (this._timer) { clearInterval(this._timer); this._timer = null; }
};

P._pushViz = function (rec) {
  this.viz.push(rec);
  if (this.viz.length > 800) this.viz.splice(0, 300); // hidden tab: nobody is pruning
};

P._dispatch = function (ev) {
  var tsMs = this.startWall + ev.t * 1000; // absolute now() time this event is due
  if (ev.kind === 'midi-on') {
    if (!this.getMidiOutput()) return;
    if (tsMs < this.now() - 5) this.stats.lateNotes++;   // due in the past = main thread was busy
    this._send([0x90 | ev.ch, ev.pitch, ev.vel], tsMs);
    ev.token.ts = tsMs;
    this._recent.push(ev.token);
    var rec = { pitch: ev.pitch, vel: ev.vel / 127, track: ev.track, drum: ev.drum, startMs: tsMs, endMs: null };
    ev.token.viz = rec; this._pushViz(rec);
  } else if (ev.kind === 'midi-off') {
    this._send([0x80 | ev.ch, ev.pitch, 0], tsMs);
    ev.token.offTs = tsMs;
    if (ev.token.viz) ev.token.viz.endMs = tsMs;
  } else if (ev.kind === 'audio') {
    if (!this.getAudioContext()) return;
    this._pushViz({ pitch: ev.pitch, vel: ev.vel01, track: ev.track, drum: ev.drum, startMs: tsMs, endMs: tsMs + ev.dur * 1000 });
    this._playAudioNote(ev.pitch, Math.max(0, (tsMs - this.now()) / 1000), ev.dur, ev.vel01, this._trackGain(ev.track));
  }
};

P._pump = function () {
  if (!this.playing) return;
  var nowMs = this.now();
  if (this._lastPumpMs) {
    var gap = nowMs - this._lastPumpMs;
    this._gaps.push([nowMs, gap]);
    if (gap > this.stats.maxGapMs) this.stats.maxGapMs = gap;
  }
  this._lastPumpMs = nowMs;
  var cutoff = nowMs - 6000, drop = 0, worst = 0;
  while (drop < this._gaps.length && this._gaps[drop][0] < cutoff) drop++;
  if (drop) this._gaps.splice(0, drop);
  for (var gi = 0; gi < this._gaps.length; gi++) if (this._gaps[gi][1] > worst) worst = this._gaps[gi][1];
  var la = Math.min(this.maxLookahead, Math.max(this.minLookahead, (worst * 1.5 + 50) / 1000));
  if (!this.quiet && la > this.lookahead + 0.2) {
    console.log('[MccfMidi] main thread stalled ~' + Math.round(worst) + 'ms — lookahead raised to ' + la.toFixed(2) + 's');
  }
  this.lookahead = la;
  this._recent = this._recent.filter(function (n) { return !(n.offTs && n.offTs < nowMs - 200); });

  var el = this.elapsed(), horizon = el + this.lookahead;
  while (this._idx < this._events.length && this._events[this._idx].t <= horizon) {
    this._dispatch(this._events[this._idx++]);
  }
  if (!this.quiet && this.stats.lateNotes > this._lateLogged && nowMs - this._lateLogAt > 2000) {
    console.log('[MccfMidi] ' + (this.stats.lateNotes - this._lateLogged) + ' note(s) reached the synth late (page busy); worst pump gap ' +
                Math.round(this.stats.maxGapMs) + 'ms');
    this._lateLogged = this.stats.lateNotes; this._lateLogAt = nowMs;
  }
  if (this._idx >= this._events.length && el >= this._endSec + 0.1) {
    if (this.loop && this._endSec > 0) { this.start(0); }
    else { this._release(); this.playing = false; if (this.onEnd) this.onEnd(); }
  }
};

// offsetSec = position (scaled, real seconds) to begin from; 0 = the top.
P.start = function (offsetSec) {
  offsetSec = offsetSec || 0;
  if (!this.data) return false;
  this._release();
  this.playing = true;
  var t2s = makeTickToSeconds(this.data.ppq, this.data.tempoEvents), self = this;
  this.playScale = this.tempoScale;
  this.startWall = this.now() - offsetSec * 1000;
  var mode = this.getOutputMode();

  // Give the synth a moment to act on Program Change before the first note.
  if (this._sendChannelSetup()) this.startWall += 150;

  var events = [], maxEnd = 0;
  this.data.tracks.forEach(function (tr) {
    if (!self.enabled[tr.index]) return;
    var ch = self.resolvedChannel(tr); // resolved ONCE, so note-off always matches note-on
    tr.notes.forEach(function (note) {
      var startAbs = t2s(note.startTick) / self.tempoScale;
      var endAbs   = t2s(note.startTick + note.durTicks) / self.tempoScale;
      maxEnd = Math.max(maxEnd, endAbs);
      if (endAbs <= offsetSec) return;
      var t0 = Math.max(0, startAbs - offsetSec);
      var t1 = Math.max(t0 + 0.02, endAbs - offsetSec);
      var pitch = clamp127(note.pitch);
      if (mode === 'midi') {
        var token = { channel: ch, pitch: pitch, ts: 0 };
        var vel = Math.max(1, clamp127(note.velocity));
        events.push({ t: t0, kind: 'midi-on',  ch: ch, pitch: pitch, vel: vel, token: token, track: tr.index, drum: ch === 9, order: 1 });
        events.push({ t: t1, kind: 'midi-off', ch: ch, pitch: pitch, token: token, order: 0 });
      } else {
        events.push({ t: t0, kind: 'audio', pitch: pitch, dur: Math.max(0.02, t1 - t0), vel01: note.velocity / 127, track: tr.index, drum: ch === 9, order: 1 });
      }
    });
  });
  events.sort(function (a, b) { return (a.t - b.t) || (a.order - b.order); }); // note-off before note-on at equal time
  this._events = events; this._idx = 0;
  this._endSec = Math.max(0, maxEnd - offsetSec);
  this._pumpStart();
  return true;
};

// Re-schedule from the CURRENT position (not the top): used when a track is
// toggled / remapped mid-song.
P.reschedule = function () {
  if (!this.playing) return;
  var musicalSec = this.elapsed() * this.playScale;
  this.start(musicalSec / this.tempoScale);
};

// Silence everything and forget the schedule, without changing `playing`.
P._release = function () {
  this._pumpStop();
  this._events = []; this._idx = 0;
  this.viz = [];
  var ctx = this.getAudioContext();
  this._voices.forEach(function (v) {
    try { v.g.gain.cancelScheduledValues(ctx.currentTime); v.g.gain.setValueAtTime(0, ctx.currentTime); v.osc.stop(ctx.currentTime + 0.02); } catch (e) {}
  });
  this._voices = [];
  // Everything already handed to the device may still be queued in the future
  // (lookahead can be >1 s on a busy page), so cancel it explicitly. Each note goes
  // to the channel it was STARTED on:
  //   - already sounding (ts <= now): send its note-off now
  //   - not yet sounding (ts > now): can't be un-sent, so also send its note-off
  //     1 ms after its start -> a click at worst, instead of a ghost phrase.
  var used = {}, now = this.now(), self = this;
  this._recent.forEach(function (n) {
    used[n.channel] = true;
    self._send([0x80 | (n.channel & 0x0f), n.pitch, 0]);
    if (n.ts && n.ts > now) self._send([0x80 | (n.channel & 0x0f), n.pitch, 0], n.ts + 1);
  });
  Object.keys(used).forEach(function (ch) { self._send([0xB0 | (ch & 0x0f), 123, 0]); });
  this._recent = [];
};

P.stop = function () { this._release(); this.playing = false; this.paused = false; this._pausedAt = 0; };

// Pause: silence the notes and remember the position; resume() carries on from there. elapsed() holds still while paused.
P.pause = function () {
  if (!this.playing) return false;
  this._pausedAt = this.elapsed();
  this._release(); this.playing = false; this.paused = true;
  return true;
};
P.resume = function () {
  if (!this.paused) return false;
  var at = this._pausedAt; this.paused = false;
  return this.start(at);
};

// Closing a page mid-song used to leave the synth holding notes (Web MIDI has
// no auto-release), so every live player panics when its page goes away.
if (typeof window !== 'undefined' && window.addEventListener) {
  var _panicAll = function () { _allPlayers.forEach(function (p) { try { p.panic(); } catch (e) {} }); };
  window.addEventListener('pagehide', _panicAll);
  window.addEventListener('beforeunload', _panicAll);
}

var api = {
  parseMidiFile: parseMidiFile, makeTickToSeconds: makeTickToSeconds, Player: Player,
  GM_PROGRAMS: GM_PROGRAMS, GM_DRUM_KITS: GM_DRUM_KITS, PC_NAMES: PC_NAMES,
  clamp127: clamp127, trackColor: trackColor, fmtClock: fmtClock
};
if (typeof module !== 'undefined' && module.exports) module.exports = api;
root.MccfMidi = api;
})(typeof window !== 'undefined' ? window : globalThis);
