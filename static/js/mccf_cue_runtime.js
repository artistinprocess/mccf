/* ==========================================================================
 * mccf_cue_runtime.js — GENERATED FILE.  Do not edit by hand.
 * --------------------------------------------------------------------------
 * Built by tools/extract_cue_runtime.js from the Loader (mccf_x3d_loader.html),
 *   Loader sha256: 9d121cf5d1999bee99e30c5210768edc07e74e4698471f6a11ea63e6be7f2277
 *   Loader size  : 405309 bytes
 * The functions between the "extracted" markers are copied VERBATIM from the Loader, so a cue
 * behaves here exactly as it does there.  The wrapper after them (a scheduler, Stop, a few hooks) is
 * the only code written for the editor; it lives in tools/extract_cue_runtime.js.
 * To pick up a change in the Loader:   node tools/extract_cue_runtime.js mccf_x3d_loader.html static/js/mccf_cue_runtime.js
 *
 * Runs the cue tracks: camera, fog, bg, effect, animation, movie, turn, path, audio, midi, gesture, face, behavior.
 * Left to the Loader: light.
 * Needs on the page: js/mccf_midi.js (MccfMidi) for MIDI cues.  Exposes MccfCueRuntime.
 * ========================================================================== */
(function (root) {

// ---- provided by the wrapper, not copied: the Loader binds this to its own page element ----
var canvas = null;

// ---- extracted from the Loader (77 items, verbatim) ----
var API = 'http://localhost:5000';

var _facialDisplacerCache = {};

var _facialDisplacerWarned = {};

function _getFacialDisplacers(suffix) {
  if (_facialDisplacerCache[suffix] !== undefined) return _facialDisplacerCache[suffix];
  var scene = canvas.browser.currentScene;
  if (!scene) return null;
  var want = {
    AU1_l:  'AU1_InnerBrowRaiser_l_displacer_'      + suffix,
    AU1_r:  'AU1_InnerBrowRaiser_r_displacer_'      + suffix,
    AU2_l:  'AU2_OuterBrowRaiser_l_displacer_'      + suffix,
    AU2_r:  'AU2_OuterBrowRaiser_r_displacer_'      + suffix,
    AU4_l:  'AU4_BrowLowerer_l_displacer_'          + suffix,
    AU4_r:  'AU4_BrowLowerer_r_displacer_'          + suffix,
    AU5_l:  'AU5_UpperLidRaiser_l_displacer_'       + suffix,
    AU5_r:  'AU5_UpperLidRaiser_r_displacer_'       + suffix,
    AU6:    'AU6_CheekRaiser_displacer_'            + suffix,
    AU12:   'AU12_LipCornerPuller_displacer_'       + suffix,
    AU26:   'AU26_JawDrop_LipCorrective_displacer_' + suffix
  };
  var found = {};
  var anyFound = false;
  var missing = [];
  Object.keys(want).forEach(function(key) {
    var node = null;
    try { node = scene.getImportedNode(want[key]); } catch (e) { node = null; }
    if (node) { found[key] = node; anyFound = true; } else { missing.push(want[key]); }
  });
  if (!anyFound) {
    // No displacers at all for this suffix — likely an avatar that
    // doesn't have the facial-displacer set built yet (e.g. Cindy,
    // before her AUs exist). Cache null so this isn't re-attempted
    // every poll tick, and warn once rather than staying silent.
    if (!_facialDisplacerWarned[suffix]) {
      console.warn('[facial] no AU displacers found for', suffix, '— facial EBPS driver will do nothing for this agent');
      _facialDisplacerWarned[suffix] = true;
    }
    _facialDisplacerCache[suffix] = null;
    return null;
  }
  if (missing.length && !_facialDisplacerWarned[suffix]) {
    console.warn('[facial] ' + missing.length + '/11 AU displacers not found for', suffix, '— missing:', missing);
    _facialDisplacerWarned[suffix] = true;
  }
  _facialDisplacerCache[suffix] = found;
  return found;
}

function applyBehaviorClip(agentSafeName, clip) {
  var timerMap = _behaviorTimerMap[agentSafeName];
  if (!timerMap) {
    console.warn('applyBehaviorClip: no timerMap for', agentSafeName,
                 '— behavior timers never resolved (check pbActivateX3DTimers logs for this agent; likely the exported scene is missing <IMPORT ... AS="' +
                 (clip && clip.timerDEF) + '_' + agentSafeName + '"/> or it hasn\'t resolved yet).');
    return false;
  }

  // Disable all other behavior timers
  // MECHANISM (confirmed Day 25): enabled=true/false is the correct SAI path.
  // startTime/stopTime do NOT work in X_ITE for behavior switching.
  Object.keys(timerMap).forEach(function(base) {
    if (base !== clip.timerDEF) {
      try { timerMap[base].enabled = false; } catch(e) {}
    }
  });

  // Enable the selected clip
  var targetNode = timerMap[clip.timerDEF];
  if (!targetNode) {
    console.warn('applyBehaviorClip: timer not found:', clip.timerDEF, agentSafeName,
                 '— timerMap has:', Object.keys(timerMap).join(', ') || '(empty)');
    return false;
  }

  try {
    // One-shot (non-looping) timers keep a stale startTime stamped into the avatar
    // file, so setting enabled alone never replays them (confirmed live: Bow only
    // played once given a fresh start on the browser's own epoch clock). Give them
    // one, same order as the console test that worked. Looping timers are untouched.
    var _oneShot = (targetNode.loop === false);
    var _now = (canvas.browser.currentTime > 0) ? canvas.browser.currentTime : Date.now() / 1000;
    if (_oneShot) targetNode.stopTime = _now - 0.01;
    targetNode.enabled = true;
    if (_oneShot) targetNode.startTime = _now + 0.05;
  } catch(e) {
    console.warn('applyBehaviorClip: SAI write failed for', agentSafeName, clip.timerDEF, e);
    return false;
  }

  var previous = _agentCurrentClip[agentSafeName] || '(none)';
  _agentCurrentClip[agentSafeName] = clip.name;

  if (clip.loop) {
    _agentLastLoopClip[agentSafeName] = clip.name;
    console.log('behavior:', agentSafeName, previous, '→', clip.name);
  } else {
    // Oneshot: fire once, then return to last looping clip
    console.log('behavior:', agentSafeName, previous, '→', clip.name, '(oneshot)');
    var returnTo  = _agentLastLoopClip[agentSafeName] || 'Default';
    var duration  = 5500;   // conservative fallback — JumpTimer/KickTimer cycleInterval ~5.5s
    try {
      var ci = targetNode.cycleInterval;
      if (ci && ci > 0) duration = Math.round(ci * 1000);
    } catch(e) {}
    var _gen = _pbCbGeneration;
    setTimeout(function() {
      // Self-expire if a reset has run since this oneshot fired
      if (_pbCbGeneration !== _gen) return;
      if (_agentCurrentClip[agentSafeName] !== clip.name) return;
      var config = _agentBehaviorClips[agentSafeName];
      if (!config) return;
      var returnClip = (config.clips || []).find(function(c) { return c.name === returnTo; });
      if (returnClip) applyBehaviorClip(agentSafeName, returnClip);
    }, duration + 150);
  }
  return true;
}

function _switchBehaviorTimer(agentSafeName, targetDEF, tNow) {
  var timerMap = _behaviorTimerMap[agentSafeName];
  if (!timerMap) {
    console.log('_switchBehaviorTimer: no timerMap for', agentSafeName, '— skipping');
    return;
  }

  console.log('_switchBehaviorTimer:', agentSafeName, '→', targetDEF);

  // Disable all timers except the target — each in its own try/catch
  BEHAVIOR_TIMER_BASES.forEach(function(base) {
    if (base === targetDEF) return;
    try {
      var n = timerMap[base];
      if (n) n.enabled = false;
    } catch(e) {
      console.warn('_switchBehaviorTimer: enabled=false failed for', base, e.message);
    }
  });

  // Enable the target
  var target = timerMap[targetDEF];
  if (!target) {
    console.warn('_switchBehaviorTimer: timer not found:', targetDEF, agentSafeName);
    return;
  }
  try {
    target.enabled = true;
  } catch(e) {
    console.warn('_switchBehaviorTimer: enabled=true failed:', agentSafeName, targetDEF, e.message);
    return;
  }

  var prev = _agentCurrentClip[agentSafeName] || '(none)';
  _agentCurrentClip[agentSafeName]  = targetDEF.replace('Timer','');
  _agentLastLoopClip[agentSafeName] = targetDEF.replace('Timer','');
  if (targetDEF === 'WalkTimer') _agentWalkStartTime[agentSafeName] = Date.now();
  console.log('_switchBehaviorTimer: done —', agentSafeName, prev, '→', targetDEF);
}

var _pbCbGeneration = 0;

var _behaviorTimerMap    = {};

var _agentBehaviorClips  = {};

var _agentCurrentClip    = {};

var _agentLastLoopClip   = {};

var _agentWalkStartTime  = {};

var _agentWaypointCache  = {};

var _agentCurrentStep    = {};

var _eventCues           = [];

var _audioSources        = {};

var _midiSources         = {};

var _midiRecs            = {};

var _activeCueAudio      = [];

var _cameraCueFireSeq    = 0;

var BEHAVIOR_TIMER_BASES = [
  'DefaultTimer','PitchTimer','YawTimer','RollTimer',
  'WalkTimer','RunTimer','JumpTimer','KickTimer'
];

var _x3dTimerActive = {};

function _parseEventCues(doc) {
  // Read <EventCues><Cue .../></EventCues> from scene XML doc.
  // Called from _parseSceneZoneData after _buildPivotCacheFromSceneXml.
  //
  // Day 85: rewritten alongside the Composer export-side fix. This used
  // to parse the OLD, trigger-based schema (t/dur/trigger/agent/shot/
  // subject/...) — the rich Camera Cue Spec v1.0 fields plus a
  // waypoint-arrival trigger vocabulary. The current Events Editor
  // (mccf_timeline_prototype.html, Day 81+) authors a much simpler flat
  // schema instead — track/target/label/t0/duration, fired by absolute
  // scene-clock time, not by a named trigger. Confirmed by reading that
  // tool's own CUES shape directly, not guessed. Old-schema attributes
  // (shot=, subject=, trigger=, agent=, node=, etc.) are no longer
  // written by anything and are not parsed here — this project has never
  // actually shipped a scene with real EventCues content until this fix,
  // so there is no legacy real-world XML to stay compatible with.
  // Audio sources placed in the Composer (<AudioSources><AudioSource name= url= loop= gain= x= y= z=>).
  // Read straight from the scene XML rather than through the X3D BasicAudioSource
  // PROTO: that proto's ExternProto file was failing to load (404), and the
  // XML carries everything an 'audio' cue needs.
  _audioSources = {};
  doc.querySelectorAll('AudioSources > AudioSource').forEach(function(el) {
    var nm = el.getAttribute('name');
    if (!nm) return;
    var g = parseFloat(el.getAttribute('gain'));
    _audioSources[nm] = {
      name: nm,
      url:  el.getAttribute('url') || '',
      loop: el.getAttribute('loop') === 'true',
      gain: isNaN(g) ? 1 : g,
      x: parseFloat(el.getAttribute('x')) || 0,
      y: parseFloat(el.getAttribute('y')) || 0,
      z: parseFloat(el.getAttribute('z')) || 0
    };
  });
  // MIDI sources: <MidiSources><MidiSource name url device tempo loop><Track index enabled channel volume/></MidiSource>
  _midiSources = {};
  doc.querySelectorAll('MidiSources > MidiSource').forEach(function(el) {
    var nm = el.getAttribute('name');
    if (!nm) return;
    var tempo = parseFloat(el.getAttribute('tempo'));
    var tracks = [];
    el.querySelectorAll('Track').forEach(function(t) {
      var idx = parseInt(t.getAttribute('index'), 10);
      if (isNaN(idx)) return;
      var o = { index: idx };
      if (t.hasAttribute('enabled')) o.enabled = t.getAttribute('enabled') !== 'false';
      if (t.hasAttribute('channel')) o.channel = parseInt(t.getAttribute('channel'), 10);
      if (t.hasAttribute('volume'))  o.volume  = parseInt(t.getAttribute('volume'), 10);
      tracks.push(o);
    });
    _midiSources[nm] = { name: nm, url: el.getAttribute('url') || '', device: el.getAttribute('device') || '',
                         tempo: (isNaN(tempo) || tempo <= 0) ? 1 : tempo, loop: el.getAttribute('loop') === 'true', tracks: tracks };
  });
  _midiPrepareAll();
  var cues = [];
  doc.querySelectorAll('EventCues > Cue').forEach(function(el) {
    function ga(attr) { return el.getAttribute(attr); }
    function gf(attr, def) { var v = parseFloat(ga(attr)); return isNaN(v) ? (def !== undefined ? def : null) : v; }
    var cue = {
      track:    ga('track')  || 'camera',
      target:   ga('target') || '',
      label:    ga('label')  || '',
      t0:       gf('t0', 0),
      duration: gf('dur', 2),
      // Day 85: real bug caught before it bit — several existing camera
      // shot executors (_executeAgentOrbit, _executeAgentTrack,
      // _executeMoveShot) read cue.dur directly, a holdover from the old
      // schema's field name. This parser only set cue.duration, so every
      // move/orbit/track shot would have silently fallen back to a
      // hardcoded 4s default regardless of what was actually authored —
      // no error, just a wrong number. Both names now carry the same
      // value so every existing consumer keeps working, whichever name
      // it happens to read.
      dur:      gf('dur', 2),
      clip:     ga('clip')   || null,     // gesture cues only
      pathId:      ga('pathId') || null,     // path cues only
      walkGesture: ga('walkGesture') || null, // path cues only, optional
      pathStart: (ga('pathStartX') !== null) ? [gf('pathStartX',0), gf('pathStartY',0), gf('pathStartZ',0)] : null,
      pathStartOrient: (ga('pathStartAngle') !== null) ? [gf('pathStartAX',0), gf('pathStartAY',1), gf('pathStartAZ',0), gf('pathStartAngle',0)] : null,
      // Day 88: real, new track types. triggerRef is the exact node name
      // to look up via getImportedNode() — computed by Composer, not
      // recomputed here, so this parser doesn't need to know the naming
      // formula at all, just read what's given.
      internalDef: ga('internalDef') || null,
      triggerRef:  ga('triggerRef')  || null,
      // Day 90: effect cues only. Left as strings (not gf()-parsed floats) --
      // a color field's value is "R G B" (three space-separated numbers),
      // not a single float, so this has to stay generic text either way.
      from:        ga('from') || null,
      to:          ga('to')   || null,
      visible:     ga('visible') === 'false' ? false : true,  // movie cues only; defaults true (matches the form's own default)
      // Day 95: facial cues (track="face"). expression = name in the avatar's expressions file;
      // weights = its AU weights embedded by the Composer at export ("AU12_LipCornerPuller=0.85;...").
      expression:  ga('expression') || null,
      weights:     ga('weights')    || null,
      fadeIn:      gf('fadeIn', 0.5),
      fadeOut:     gf('fadeOut', 0.5),
      intensity:   gf('intensity', 1),
    };
    if (cue.track === 'camera') {
      // Day 85: full camera field parse, matching exactly what the
      // Composer writer now emits and what _fireCameraEventCue and its
      // downstream executors (_executeStaticCameraShot, _executeMoveShot,
      // _executeAgentOrbit, _executeAgentTrack) actually read. Previously
      // NONE of these were parsed at all — even with the writer and the
      // Timeline authoring UI both fixed, every camera cue would have
      // arrived here with just track/target/label/t0/dur and nothing a
      // real shot needs.
      if (ga('shot'))       cue.shot       = ga('shot');
      if (ga('subject'))    cue.subject    = ga('subject');
      if (ga('camera'))     cue.camera     = ga('camera');
      if (ga('viewpoint'))  cue.viewpoint  = ga('viewpoint');
      cue.jump       = ga('jump') === 'false' ? false : true;
      cue.transition = ga('transition') || 'cut';
      if (ga('flyDuration') !== null) cue.flyDuration = gf('flyDuration');
      if (ga('distance')    !== null) cue.distance    = gf('distance');
      if (ga('height')      !== null) cue.height      = gf('height');
      if (ga('hAngle')      !== null) cue.hAngle      = gf('hAngle');
      if (ga('vAngle')      !== null) cue.vAngle      = gf('vAngle');
      if (ga('distanceEnd') !== null) cue.distanceEnd = gf('distanceEnd');
      if (ga('heightEnd')   !== null) cue.heightEnd   = gf('heightEnd');
      if (ga('hAngleEnd')   !== null) cue.hAngleEnd   = gf('hAngleEnd');
      if (ga('vAngleEnd')   !== null) cue.vAngleEnd   = gf('vAngleEnd');
      if (ga('arcDepth')        !== null) cue.arcDepth        = gf('arcDepth');
      if (ga('trackOffset')     !== null) cue.trackOffset     = gf('trackOffset');
      if (ga('trackOffsetEnd')  !== null) cue.trackOffsetEnd  = gf('trackOffsetEnd');
      if (ga('trackDepth')      !== null) cue.trackDepth      = gf('trackDepth');
      cue.loop = ga('loop') === 'true';
    }
    cues.push(cue);
  });
  _eventCues = cues;
  console.log('[EventCues] loaded:', _eventCues.length, _eventCues.map(function(c){ return c.track + '@' + c.t0 + 's:' + (c.target||c.shot||c.viewpoint||'?'); }).join(', '));
}

var _faceCueActive = {};

var _faceCueLoop   = {};

var _faceCueWarned = {};

function _faceParseWeights(str) {
  var out = {};
  String(str || '').split(';').forEach(function(pair) {
    var i = pair.indexOf('=');
    if (i < 1) return;
    var au = pair.slice(0, i).trim(), v = parseFloat(pair.slice(i + 1));
    if (au && !isNaN(v)) out[au] = v;
  });
  return out;
}

function _faceKeysForAU(au) {
  var m = /^AU(\d+)/.exec(au || '');
  if (!m) return [];
  var n = parseInt(m[1], 10);
  if (n === 6 || n === 12 || n === 26) return ['AU' + n];
  if (n === 1 || n === 2 || n === 4 || n === 5) {
    if (/_l$/i.test(au)) return ['AU' + n + '_l'];
    if (/_r$/i.test(au)) return ['AU' + n + '_r'];
    return ['AU' + n + '_l', 'AU' + n + '_r'];
  }
  return [];
}

function _faceEase(k) { return k * k * (3 - 2 * k); }

function _fireFaceEventCue(cue, opts) {
  opts = opts || {};
  var gen = (opts.gen !== undefined) ? opts.gen : _pbCbGeneration;
  if (gen !== _pbCbGeneration) return;                       // superseded by a newer Play/Reset
  var safeName = String(cue.target || '').replace(/[^A-Za-z0-9_]/g, '_');
  var weights  = _faceParseWeights(cue.weights);
  if (!Object.keys(weights).length) {
    console.warn('[EventCues] face: cue "' + (cue.expression || cue.label || '?') + '" for ' + cue.target +
      ' carries no AU weights -- re-export the scene from the Composer (it embeds them from ' +
      'the avatar\'s expressions file).');
    return;
  }
  var displacers = _getFacialDisplacers(safeName);
  if (!displacers) {
    console.warn('[EventCues] face: no AU displacers for ' + cue.target + ' -- cue "' + (cue.expression || cue.label) + '" skipped.');
    return;
  }

  // Target value per displacer node, scaled by the cue's intensity.
  var intensity = (cue.intensity === undefined || isNaN(cue.intensity)) ? 1 : cue.intensity;
  var target = {};
  Object.keys(weights).forEach(function(au) {
    var keys = _faceKeysForAU(au);
    if (!keys.length && !_faceCueWarned[safeName + '|' + au]) {
      _faceCueWarned[safeName + '|' + au] = true;
      console.warn('[EventCues] face: ' + au + ' has no displacer on ' + cue.target + ' -- skipped.');
    }
    keys.forEach(function(k) {
      if (displacers[k]) target[k] = Math.min(1, Math.max(0, weights[au] * intensity));
    });
  });
  var keys = Object.keys(target);
  if (!keys.length) {
    console.warn('[EventCues] face: none of "' + (cue.expression || cue.label) + '"\'s AUs map to a displacer on ' + cue.target + '.');
    return;
  }

  // A newer face cue takes over from a running one, starting from wherever the face is now.
  if (_faceCueLoop[safeName]) _faceCueLoop[safeName].stop(false);
  var start = {};
  keys.forEach(function(k) { start[k] = (typeof displacers[k].weight === 'number') ? displacers[k].weight : 0; });

  var totalMs = Math.max(0.05, cue.dur || 2) * 1000;
  var inMs    = Math.max(0, Math.min(totalMs, (cue.fadeIn  === undefined ? 0.5 : cue.fadeIn)  * 1000));
  var outMs   = Math.max(0, Math.min(totalMs - inMs, (cue.fadeOut === undefined ? 0.5 : cue.fadeOut) * 1000));
  var holdEnd = totalMs - outMs;
  var t0      = (window.performance && performance.now) ? performance.now() : Date.now();
  var last    = {};
  var stopped = false;

  _faceCueActive[safeName] = true;
  function write(k, v) {
    if (last[k] !== undefined && Math.abs(last[k] - v) < 0.002) return;   // skip no-op writes
    last[k] = v;
    try { displacers[k].weight = v; } catch (e) {}
  }
  function finish(toNeutral) {
    if (stopped) return;
    stopped = true;
    if (toNeutral) keys.forEach(function(k) { try { displacers[k].weight = 0; } catch (e) {} });
    _faceCueActive[safeName] = false;
    delete _faceCueLoop[safeName];
  }
  _faceCueLoop[safeName] = { stop: finish };

  function step() {
    if (stopped) return;
    if (gen !== _pbCbGeneration) { finish(true); return; }        // Reset/Play -> back to neutral
    var now = (window.performance && performance.now) ? performance.now() : Date.now();
    var e = now - t0;
    if (e >= totalMs) { keys.forEach(function(k) { write(k, 0); }); finish(false); return; }
    keys.forEach(function(k) {
      var v;
      if (e < inMs)            v = start[k] + (target[k] - start[k]) * _faceEase(inMs > 0 ? e / inMs : 1);
      else if (e < holdEnd)    v = target[k];
      else                     v = target[k] * (1 - _faceEase(outMs > 0 ? (e - holdEnd) / outMs : 1));
      write(k, v);
    });
    (window.requestAnimationFrame || function(f) { return setTimeout(f, 33); })(step);
  }
  console.log('[EventCues] face:', cue.target, '->', (cue.expression || cue.label), '| AUs', keys.join(','),
              '| in', (inMs / 1000).toFixed(2) + 's hold', ((holdEnd - inMs) / 1000).toFixed(2) + 's out', (outMs / 1000).toFixed(2) + 's',
              '| intensity', intensity);
  step();
}

function _stopAudioCueRecord(rec) {
  if (rec.timer) { clearTimeout(rec.timer); rec.timer = null; }
  try { rec.audio.pause(); } catch (e) {}
  _activeCueAudio = _activeCueAudio.filter(function(r) { return r !== rec; });
}

function _stopAudioCues(name) {
  _activeCueAudio.slice().forEach(function(rec) {
    if (!name || rec.name === name) _stopAudioCueRecord(rec);
  });
}

function _fireAudioEventCue(cue) {
  if (cue.label === 'stop') { _stopAudioCues(cue.target); return; }
  var src = _audioSources[cue.target];
  if (!cue.target || !src) {
    console.warn('[EventCues] audio: no audio source named "' + (cue.target || '') + '" — known sources:',
                 Object.keys(_audioSources).join(', ') || '(none)');
    return;
  }
  if (!src.url) { console.warn('[EventCues] audio: source "' + src.name + '" has no file'); return; }
  var url = /^(https?:)?\//.test(src.url) ? src.url : '/static/x3d/' + src.url;
  var a = new Audio(url);
  a.volume = Math.max(0, Math.min(1, src.gain));
  a.loop = !!src.loop;
  var rec = { audio: a, timer: null, name: src.name };
  a.addEventListener('ended', function() { _stopAudioCueRecord(rec); });
  a.addEventListener('error', function() {
    console.warn('[EventCues] audio: could not load', url, '— is the file in static/x3d/' + src.url + ' ?');
    _stopAudioCueRecord(rec);
  });
  _activeCueAudio.push(rec);
  var pr = a.play();
  if (pr && pr.catch) pr.catch(function(e) {
    console.warn('[EventCues] audio: play() rejected for', src.name, '-', e && e.name,
                 e && e.name === 'NotAllowedError' ? '(browser wants a click in this window first)' : '');
    _stopAudioCueRecord(rec);
  });
  if (a.loop) rec.timer = setTimeout(function() { _stopAudioCueRecord(rec); }, Math.max(0.1, cue.duration || 4) * 1000);
  console.log('[EventCues] audio:', src.name, '->', url, '| gain', a.volume, a.loop ? '| loop for ' + (cue.duration || 4) + 's' : '| one-shot');
}

var _midiAccessPromise = null;

var _midiFallbackCtx = null;

var _midiStopGen = 0;

function _midiGetAccess() {
  if (!_midiAccessPromise) {
    _midiAccessPromise = navigator.requestMIDIAccess
      ? navigator.requestMIDIAccess()
      : Promise.reject(new Error('Web MIDI is not available in this browser'));
  }
  return _midiAccessPromise;
}

function _midiFallbackAudio() {
  if (!_midiFallbackCtx) {
    try { _midiFallbackCtx = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {}
  }
  if (_midiFallbackCtx && _midiFallbackCtx.state === 'suspended') { try { _midiFallbackCtx.resume(); } catch (e) {} }
  return _midiFallbackCtx;
}

function _midiPrepare(src) {
  var rec = { src: src, output: null, mode: 'audio', player: null, ready: null };
  rec.player = new MccfMidi.Player({
    getMidiOutput:   function() { return rec.output; },
    getOutputMode:   function() { return rec.mode; },
    getAudioContext: _midiFallbackAudio,
    onEnd: function() { console.log('[EventCues] midi: "' + src.name + '" finished'); }
  });
  rec.player.loop = src.loop;
  rec.player.tempoScale = src.tempo;
  var url = /^(https?:)?\//.test(src.url) ? src.url : '/static/x3d/' + src.url;
  var fileP = fetch(url).then(function(r) {
    if (!r.ok) throw new Error('HTTP ' + r.status + ' for ' + url);
    return r.arrayBuffer();
  });
  var devP = !src.device ? Promise.resolve() : _midiGetAccess().then(function(access) {
    var outs = []; access.outputs.forEach(function(o) { outs.push(o); });
    var h = src.device.toLowerCase();
    var found = outs.filter(function(o) { return (o.name || '').toLowerCase().indexOf(h) >= 0; })[0];
    if (found) { rec.output = found; rec.mode = 'midi'; }
    else console.warn('[EventCues] midi: no output matching "' + src.device + '" — using browser synth. Available:',
                      outs.map(function(o) { return o.name; }).join(' | ') || '(none)');
  }).catch(function(e) { console.warn('[EventCues] midi: Web MIDI unavailable (' + e.message + ') — using browser synth'); });
  rec.ready = Promise.all([fileP, devP]).then(function(res) {
    rec.player.load(res[0]);
    rec.player.applyTrackSettings(src.tracks);
    console.log('[EventCues] midi: "' + src.name + '" ready —', rec.player.data.tracks.length, 'tracks, output:',
                rec.mode === 'midi' ? rec.output.name : 'browser synth');
    return rec;
  }).catch(function(e) {
    console.warn('[EventCues] midi: could not prepare "' + src.name + '":', e && e.message);
    return null;
  });
  return rec;
}

function _midiPrepareAll() {
  Object.keys(_midiRecs).forEach(function(k) { try { _midiRecs[k].player.dispose(); } catch (e) {} });
  _midiRecs = {};
  if (typeof MccfMidi === 'undefined') return;
  Object.keys(_midiSources).forEach(function(k) { _midiRecs[k] = _midiPrepare(_midiSources[k]); });
}

function _stopMidiCues() {
  _midiStopGen++;   // cancels any cue still waiting for its file to load
  Object.keys(_midiRecs).forEach(function(k) {
    var r = _midiRecs[k];
    r.player.stop();
    if (r.mode === 'midi') r.player.panic();
  });
}

function _fireMidiEventCue(cue) {
  var rec = _midiRecs[cue.target];
  if (!cue.target || !rec) {
    console.warn('[EventCues] midi: no MIDI source named "' + (cue.target || '') + '" — known sources:',
                 Object.keys(_midiRecs).join(', ') || '(none)');
    return;
  }
  if (cue.label === 'stop') { rec.player.stop(); if (rec.mode === 'midi') rec.player.panic(); return; }
  var gen = _midiStopGen;
  rec.ready.then(function(r) {
    if (!r || gen !== _midiStopGen) return;   // failed to load, or Stop/Reset happened meanwhile
    r.player.start(0);
    console.log('[EventCues] midi: playing "' + r.src.name + '"');
  });
}

var _STATIC_SHOTS = {
  wide:true, medium:true, closeup:true, extreme_closeup:true,
  overhead:true, worms_eye:true, dutch:true,
  over_shoulder:true, profile:true, two_shot:true
};

var _MOVE_SHOTS = {
  dolly_in:true, dolly_out:true, pan:true, tilt:true,
  orbit:true, crane_up:true, track:true
};

var _LINEAR_MOVE_SHOTS = { dolly_in:true, dolly_out:true, pan:true, tilt:true, crane_up:true };

function _fireCameraEventCue(cue) {
  // Day 85: stamp this fire with the current sequence number BEFORE
  // dispatching to any shot executor below — see _cameraCueFireSeq's own
  // declaration comment for why. Every executor's trySet() checks
  // cue._fireSeq against the live counter right before actually writing/
  // binding, so a slow retry from an OLDER cue can no longer clobber a
  // newer cue that already succeeded.
  _cameraCueFireSeq++;
  cue._fireSeq = _cameraCueFireSeq;

  var shot = (cue.shot || '').toLowerCase();

  // ── BAKED PATH: agent-attached viewpoints ─────────────────
  // VP_{subject}_{Eye|Side} lives inside the agent Transform in X3D.
  // Loader just binds it — no position computation, no VP_Free.
  if (shot === 'agent_eye' || shot === 'agent_side') {
    var suffix = (shot === 'agent_eye') ? 'Eye' : 'Side';
    var subjectSafe = (cue.subject || '').replace(/[^A-Za-z0-9_]/g, '_');
    // Day 83: fly is NOT yet supported for avatar-attached viewpoints — the
    // target pose is local to the avatar's own (possibly moving) Transform,
    // and _flyCameraTo needs a flat world-space destination. Logged, not
    // silently dropped — falls back to the existing jump toggle (cut-only).
    if (cue.transition === 'fly') {
      console.warn('[EventCues] camera: fly requested for ' + shot + ' «' + (cue.subject||'?') +
        '» — not yet supported for avatar-attached viewpoints, falling back to cut');
    }
    _bindNamedViewpoint('VP_' + subjectSafe + '_' + suffix, cue.transition !== 'fly', cue._fireSeq);
    return;
  }

  // ── BAKED PATH: agent-orbit ────────────────────────────────
  // Day 64: a CAM_OrbitProto_{subject} ProtoInstance (AgentOrbitCamera, see
  // mccf_camera_protos.x3d) lives inside the agent's own Transform — parented, so the
  // avatar's world motion is free (no tracking math). Orbit math here is RELATIVE
  // OFFSET ONLY: radius/height/angle around the avatar's local origin. The avatar's
  // Transform translation is never read or written by this path — that's the whole
  // point of parenting.
  if (shot === 'agent_orbit') {
    _executeAgentOrbit(cue);
    return;
  }

  // ── BAKED PATH: agent-track ────────────────────────────────
  // Day 64: a CAM_TrackProto_{subject} ProtoInstance (AgentTrackCamera, see
  // mccf_camera_protos.x3d) lives inside the agent's own Transform — parented, same
  // principle as agent-orbit. Checked as its own explicit branch, not merged into
  // agent_orbit's — the keyframe math is different (linear lateral lerp vs circular
  // sweep) even though the parenting architecture and proto plumbing are identical.
  if (shot === 'agent_track') {
    _executeAgentTrack(cue);
    return;
  }

  // ── BAKED PATH: placed free camera ────────────────────────
  // Day 64: a CAM_Free_{name} FreeCamera ProtoInstance, placed via Composer's grid-based
  // camera placement UI. Static — no TimeSensor, no interpolation. Deliberately a
  // separate code path from cue.viewpoint below: that path calls _bindNamedViewpoint
  // directly on a plain top-level authored Viewpoint, but a FreeCamera's inner Viewpoint
  // is DEF'd "VP" *inside* its ProtoBody — unreachable via getNamedNode from outside,
  // same SAI-into-proto constraint as agent_orbit/agent_track. Binding it means setting
  // the ProtoInstance's own exposed set_bind field, not looking up an internal name that
  // doesn't exist from the outside.
  if (shot === 'free_camera' && cue.camera) {
    var freeCamSafe = cue.camera.replace(/[^A-Za-z0-9_]/g, '_');
    // Day 83: fly is NOT yet supported for placed FreeCamera destinations —
    // its world orientation is composed from three nested rotations (yaw/
    // pitch/roll, see mccf_camera_protos.x3d's FreeCamera ProtoBody), and
    // combining those into one axis-angle by hand is exactly the custom
    // rotation math this project's house style avoids. Logged, not silently
    // dropped — falls back to the existing instant bind.
    if (cue.transition === 'fly') {
      console.warn('[EventCues] camera: fly requested for free_camera «' + cue.camera +
        '» — not yet supported for placed FreeCamera destinations, falling back to cut');
    }
    _bindFreeCamera(freeCamSafe, cue._fireSeq);
    return;
  }

  // ── BAKED PATH: explicitly authored named viewpoint ───────
  // Author placed a named VP in the scene and referenced it by name in the cue
  // (VP_Overview, VP_Origin, a zone VP, or any other author-DEF'd top-level
  // Viewpoint). This is the only other case where _bindNamedViewpoint is called.
  if (cue.viewpoint) {
    // Day 83: fly support. Only safe here because these are plain top-level
    // <Viewpoint> nodes (see mccf_scene_composer.html's own export of
    // VP_Overview/VP_Origin/zone VPs) — position/orientation are already a
    // flat world-space value with no proto-wrapping or parenting to unwind,
    // unlike FreeCamera/agent-attached targets (see those two branches
    // above). Read directly via SAI field access, same pattern already used
    // throughout this file for reading authored node values.
    if (cue.transition === 'fly') {
      var _flyAttempts = 0;
      (function tryFlyToNamedVP() {
        _flyAttempts++;
        try {
          var scene = canvas.browser.currentScene;
          var targetVp = null;
          try { targetVp = scene.getImportedNode(cue.viewpoint); } catch(ie) {}
          if (!targetVp) { try { targetVp = scene.getNamedNode(cue.viewpoint); } catch(ne) {} }
          if (targetVp) {
            var toPosStr = targetVp.getField('position').toString();
            var toRotStr = targetVp.getField('orientation').toString();
            var toPos = String(toPosStr).trim().split(/\s+/).map(Number);
            var toRot = String(toRotStr).trim().split(/\s+/).map(Number);
            if (toPos.length === 3 && !toPos.some(isNaN) && toRot.length === 4 && !toRot.some(isNaN)) {
              console.log('[EventCues] camera: fly to baked VP «' + cue.viewpoint + '»');
              _flyCameraTo(toPos, toRot, cue.flyDuration || 2, cue.viewpoint);
              return;
            }
            console.warn('[EventCues] camera: fly «' + cue.viewpoint + '» — could not parse position/orientation, falling back to cut');
          } else if (_flyAttempts < 10) {
            setTimeout(tryFlyToNamedVP, 200);
            return;
          } else {
            console.warn('[EventCues] camera: fly target «' + cue.viewpoint + '» not found after retries, falling back to cut');
          }
        } catch(e) { console.warn('[EventCues] camera: fly «' + cue.viewpoint + '» exception:', e.message); }
        // Any failure above falls through to the ordinary cut bind, rather than doing nothing.
        _bindNamedViewpoint(cue.viewpoint, cue.jump !== false, cue._fireSeq);
      })();
      return;
    }
    console.log('[EventCues] camera: baked VP «' + cue.viewpoint + '»');
    _bindNamedViewpoint(cue.viewpoint, cue.jump !== false, cue._fireSeq);
    return;
  }

  // ── RUNTIME PATH: static computed shot via VP_Free ────────
  // Author chose a shot type from the static list. Loader computes position
  // from cue params and drives VP_Free. VP_Free is never named by the author.
  if (_STATIC_SHOTS[shot]) {
    _executeStaticCameraShot(cue);
    return;
  }

  // ── RUNTIME PATH: move shot via VP_Free (Phase 2) ─────────
  if (_MOVE_SHOTS[shot]) {
    _executeMoveShot(cue);
    return;
  }

  // ── No valid path — skip with diagnostic ─────────────────
  // Reaches here only if cue has no viewpoint= and an unrecognised or absent shot=.
  // VP_Free is never bound as a fallback.
  console.warn('[EventCues] camera: cue «' + (cue.label||'?') + '» — shot «' + shot +
    '» not recognised and no viewpoint= set. Cue skipped. ' +
    'Check Events Editor export or scene XML.');
}

function _bindNamedViewpoint(vpName, wantJump, expectedSeq) {
  var attempts = 0;
  function tryBind() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var vpNode = null;
      try { vpNode = scene.getImportedNode(vpName); } catch(ie) {}
      if (!vpNode) { try { vpNode = scene.getNamedNode(vpName); } catch(ne) {} }
      if (vpNode) {
        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration
        // comment. If a newer camera cue has fired since this retry loop
        // started, this bind is stale: skip it rather than clobber
        // whatever the newer cue already set.
        if (expectedSeq !== undefined && expectedSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale bind of', vpName, 'skipped — a newer camera cue has fired since');
          return;
        }
        try {
          var jumpField = vpNode.getField('jump');
          if (jumpField) jumpField.setValue(wantJump !== false);
          else vpNode.jump = (wantJump !== false);
        } catch(je) { try { vpNode.jump = (wantJump !== false); } catch(je2) {} }
        vpNode.set_bind = true;
        console.log('[EventCues] camera: set_bind', vpName, 'jump=' + (wantJump !== false),
          attempts > 1 ? '(attempt ' + attempts + ')' : '');
        return;
      }
    } catch(e) {}
    if (attempts < 10) {
      setTimeout(tryBind, 200);
    } else {
      console.warn('[EventCues] camera: viewpoint not found after retries:', vpName);
    }
  }
  tryBind();
}

function _computeCamPosition(subjectPos, distance, height, hAngleDeg) {
  var hRad = (hAngleDeg || 0) * Math.PI / 180;
  return [
    subjectPos[0] + distance * Math.sin(hRad),
    subjectPos[1] + height,
    subjectPos[2] + distance * Math.cos(hRad)
  ];
}

var LOOK_AT_HEIGHT = 1.7;

function _lookAtOrientation(camPos, targetPos, vAngleDeg) {
  var dx = targetPos[0] - camPos[0];
  var dy = (targetPos[1] + LOOK_AT_HEIGHT) - camPos[1];
  var dz = targetPos[2] - camPos[2];
  // X3D cameras look down -Z by default. To face the target we need the -Z axis
  // to point toward (dx, dy, dz), so we negate the vector for atan2.
  // Yaw (rotation around Y): atan2(-dx, -dz) points -Z toward target in XZ plane.
  var yaw = Math.atan2(-dx, -dz);
  // Pitch — tilt up/down to target plus authored vAngle offset.
  // Positive pitch = look up, negative = look down.
  var horizDist = Math.sqrt(dx * dx + dz * dz);
  var pitch = Math.atan2(dy, horizDist) + ((vAngleDeg || 0) * Math.PI / 180);
  // Full quaternion compose: q_yaw (Y axis) * q_pitch (X axis)
  var cosY = Math.cos(yaw / 2),   sinY = Math.sin(yaw / 2);
  var cosP = Math.cos(pitch / 2), sinP = Math.sin(pitch / 2);
  // Quaternion multiply: q_yaw * q_pitch
  var qw = cosY * cosP;
  var qx = cosY * sinP;
  var qy = sinY * cosP;
  var qz = -sinY * sinP;
  // Convert quaternion to axis-angle
  var angle = 2 * Math.acos(Math.min(1, Math.max(-1, qw)));
  var s = Math.sqrt(1 - qw * qw);
  var ax, ay, az;
  if (s < 0.001) {
    ax = 0; ay = 1; az = 0;  // degenerate — default Y axis
  } else {
    ax = qx / s; ay = qy / s; az = qz / s;
  }
  return [ax, ay, az, angle];
}

function _resolveSubjectPos(subjectName) {
  if (!subjectName) return null;
  var safeName = subjectName.replace(/[^A-Za-z0-9_]/g, '_');

  // ── Path 0: live X3D transform ────────────────────────────────────────
  // Real bug fix: every path below (1-5) is backend waypoint/arc-step
  // bookkeeping — none of them ever read the avatar's actual live
  // Transform. That was fine while every agent moved exclusively via the
  // waypoint/arc stepping system (each step genuinely fires a fresh
  // "WP arrival" that keeps _agentCurrentStep current), but a
  // RecordedPath-driven walk (the "path" EventCue) never fires those
  // arrivals at all -- confirmed live: _agentCurrentStep['Anna'] gets set
  // once, at the one-time initial "Begin arrive", and then never updates
  // again for the rest of the run, however far the RecordedPath actually
  // walks them. Every later camera cue computed its subject position from
  // that single frozen starting coordinate -- explaining exactly why the
  // camera kept framing near the start of the walk (in this scene's case,
  // near the Island/lake) regardless of where Anna herself had actually
  // arrived, while Anna's own position (driven independently by the
  // RecordedPath's own interpolators via ROUTE) was always correct. The
  // live Transform is authoritative for ANY locomotion mechanism, so it's
  // tried first now; the existing paths remain as fallbacks for whatever
  // this read can't handle (asset targets with no Avatar_ node, a subject
  // not yet placed in the scene, etc).
  try {
    var _liveNode = canvas.browser.currentScene.getNamedNode('Avatar_' + safeName);
    if (_liveNode) {
      var _liveT = _liveNode.translation;
      if (_liveT && typeof _liveT.x === 'number' && typeof _liveT.y === 'number' && typeof _liveT.z === 'number') {
        var lpos = [_liveT.x, _liveT.y, _liveT.z];
        console.log('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 0 (live transform)', lpos);
        return lpos;
      }
    }
  } catch (eLive) { /* fall through to the bookkeeping-based paths below */ }

  // ── Path 1: runtime arrived position via _agentCurrentStep ──────────────
  // Preferred path: use the step number that was recorded when this cultivar
  // most recently arrived at a waypoint during live playback.
  var arrivedStep = _agentCurrentStep[safeName];
  if (arrivedStep !== undefined) {
    var runtimeCache = _agentWaypointCache[safeName];
    var runtimeEntry = runtimeCache && runtimeCache[arrivedStep];
    if (runtimeEntry) {
      var rpos = [parseFloat(runtimeEntry.pos_x) || 0, 0, parseFloat(runtimeEntry.pos_z) || 0];
      console.log('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 1 (runtime step ' + arrivedStep + ')', rpos);
      return rpos;
    }
    console.warn('[EventCues] _resolveSubjectPos «' + subjectName + '» — _agentCurrentStep=' + arrivedStep +
      ' but no cache entry found (cache keys: ' + (runtimeCache ? Object.keys(runtimeCache) : 'null') + ')');
  }

  // ── Path 2: waypointPosMap keyed by subject name ─────────────────────────
  // Only applies when subjectName happens to match a WP name (rare — zone centroids etc.)
  var wpEntry = _waypointPosMap[subjectName] || _waypointPosMap[subjectName.toUpperCase()];
  if (wpEntry) {
    var wpos = [parseFloat(wpEntry.pos_x) || 0, 0, parseFloat(wpEntry.pos_z) || 0];
    console.log('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 2 (_waypointPosMap match)', wpos);
    return wpos;
  }

  // ── Path 3: pre-loaded pivot cache fallback (all steps present) ──────────
  // WARNING: this cache contains ALL waypoints from scene XML at load time,
  // so "most recent step" is the highest-numbered WP, not the arrived one.
  // Only use as fallback when no runtime arrival has been recorded.
  var cache = _agentWaypointCache[safeName];
  if (cache) {
    var steps = Object.keys(cache).filter(function(k){ return !isNaN(k); }).map(Number).sort(function(a,b){return b-a;});
    if (steps.length > 0) {
      var entry = cache[steps[0]];
      var cpos = [parseFloat(entry.pos_x) || 0, 0, parseFloat(entry.pos_z) || 0];
      console.warn('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 3 (pre-loaded cache step ' + steps[0] +
        ' — no runtime arrival recorded yet). pos=', cpos,
        '  All steps:', steps.join(','));
      return cpos;
    }
  }

  // ── Path 4: EmotionalArc start position ──────────────────────────────────
  if (_cultivarStartPos[subjectName]) {
    var sp = _cultivarStartPos[subjectName];
    console.log('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 4 (start position)', sp);
    return sp;
  }

  // ── Path 5: scene centroid fallback ──────────────────────────────────────
  console.warn('[EventCues] _resolveSubjectPos «' + subjectName + '» → PATH 5: position not found — using origin.');
  return [0, 0, 0];
}

function _bindFreeCamera(nameSafe, expectedSeq) {
  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var node = canvas.browser.currentScene.getNamedNode('CAM_Free_' + nameSafe);
      if (node) {
        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration comment.
        if (expectedSeq !== undefined && expectedSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale free-camera bind of', nameSafe, 'skipped — a newer camera cue has fired since');
          return;
        }
        node.set_bind = true;
        console.log('[EventCues] camera: free camera «' + nameSafe + '» bound');
        return;
      }
      console.warn('[EventCues] camera: free camera CAM_Free_' + nameSafe + ' not found — re-export scene from Composer');
    } catch (e) {
      console.warn('[EventCues] camera: free camera bind exception:', e.message);
    }
    if (attempts < 10) setTimeout(trySet, 200);
    else console.warn('[EventCues] camera: free camera CAM_Free_' + nameSafe + ' not found after retries');
  }
  trySet();
}

function _flyCameraTo(toPos, toRot, duration, label) {
  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var camXform   = scene.getNamedNode('CAM_Free_Transform');
      var vpFree     = scene.getNamedNode('VP_Free');
      var camTimer   = scene.getNamedNode('CAM_FlyTimer');
      var easeInterp = scene.getNamedNode('CAM_FlyEase');
      var posInterp  = scene.getNamedNode('CAM_FlyPosInterp');
      var oriInterp  = scene.getNamedNode('CAM_FlyOriInterp');
      var proxSensor = scene.getNamedNode('MCCF_PathRecorderProx');

      if (camXform && vpFree && camTimer && easeInterp && posInterp && oriInterp) {
        // FROM pose — live read via the ProximitySensor, same mechanism and
        // same field-parse convention as the Events Editor's path recorder
        // (_pathRecTick, mccf_events_editor_prototype_2.html). Falls back to
        // an instant snap+bind (old cut behavior) if the sensor is missing or
        // the camera is currently outside its sensed region — interpolating
        // from a bad/stale FROM pose would be worse than not interpolating.
        var fromPos = null, fromRot = null;
        if (proxSensor) {
          try {
            var activeStr = proxSensor.getField('isActive').toString();
            if (activeStr === 'TRUE' || activeStr === 'true') {
              var pParts = String(proxSensor.getField('position_changed').toString()).trim().split(/\s+/).map(Number);
              var rParts = String(proxSensor.getField('orientation_changed').toString()).trim().split(/\s+/).map(Number);
              if (pParts.length === 3 && !pParts.some(isNaN)) fromPos = pParts;
              if (rParts.length === 4 && !rParts.some(isNaN)) fromRot = rParts;
            }
          } catch (pe) { console.warn('[EventCues] camera: fly — ProximitySensor read failed:', pe.message); }
        }
        if (!fromPos || !fromRot) {
          console.warn('[EventCues] camera: fly «' + (label||'?') + '» — could not read a live FROM pose ' +
            '(sensor missing or camera outside sensed region) — falling back to instant cut');
          camXform.translation = new X3D.SFVec3f(toPos[0], toPos[1], toPos[2]);
          camXform.rotation    = new X3D.SFRotation(toRot[0], toRot[1], toRot[2], toRot[3]);
          requestAnimationFrame(function() { vpFree.set_bind = true; });
          return;
        }

        // Two-keyframe animation: 0 = current live pose, 1 = destination.
        // Same indexed MF array assignment pattern as _executeMoveShot (confirmed
        // against X_ITE's own README — bulk MFVec3f/MFRotation constructors don't
        // exist in X_ITE's SAI).
        posInterp.key.length = 0; posInterp.keyValue.length = 0;
        oriInterp.key.length = 0; oriInterp.keyValue.length = 0;
        posInterp.key[0] = 0; posInterp.keyValue[0] = new X3D.SFVec3f(fromPos[0], fromPos[1], fromPos[2]);
        posInterp.key[1] = 1; posInterp.keyValue[1] = new X3D.SFVec3f(toPos[0], toPos[1], toPos[2]);
        oriInterp.key[0] = 0; oriInterp.keyValue[0] = new X3D.SFRotation(fromRot[0], fromRot[1], fromRot[2], fromRot[3]);
        oriInterp.key[1] = 1; oriInterp.keyValue[1] = new X3D.SFRotation(toRot[0], toRot[1], toRot[2], toRot[3]);

        // Belt-and-suspenders — same as _executeMoveShot: rely on the static XML
        // ROUTEs from the Composer export, but confirm the chain at runtime too.
        // Topology here has one extra hop vs the move-shot vessel: CAM_FlyTimer
        // feeds CAM_FlyEase (the ease curve), and CAM_FlyEase's eased output —
        // not CAM_FlyTimer's raw linear fraction — feeds the two interpolators.
        try {
          canvas.browser.addRoute(camTimer,  'fraction_changed', easeInterp, 'set_fraction');
          canvas.browser.addRoute(easeInterp,'value_changed',    posInterp,  'set_fraction');
          canvas.browser.addRoute(easeInterp,'value_changed',    oriInterp,  'set_fraction');
          canvas.browser.addRoute(posInterp, 'value_changed',    camXform,   'set_translation');
          canvas.browser.addRoute(oriInterp, 'value_changed',    camXform,   'set_rotation');
        } catch(e) { console.warn('[EventCues] camera: fly addRoute via SAI failed:', e.message); }

        camTimer.cycleInterval = duration;
        camTimer.loop = false;

        // Snap to the FROM pose first — matches the live pose exactly, so this
        // is visually a no-op — then bind VP_Free, same sequencing as
        // _executeMoveShot's "snap to start, then bind, then start timer".
        camXform.translation = new X3D.SFVec3f(fromPos[0], fromPos[1], fromPos[2]);
        camXform.rotation    = new X3D.SFRotation(fromRot[0], fromRot[1], fromRot[2], fromRot[3]);

        requestAnimationFrame(function() {
          vpFree.set_bind = true;
          requestAnimationFrame(function() {
            // canvas.browser.currentTime returns 0 in some X_ITE builds — same
            // fallback every other startTime write in this file already uses.
            var _flyStartTime = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
              ? canvas.browser.currentTime : (performance.now() / 1000);
            camTimer.startTime = _flyStartTime;
            camTimer.enabled   = true;
            console.log('[EventCues] camera: fly «' + (label||'?') + '» started, dur=' + duration +
              ' from=[' + fromPos.map(function(v){return v.toFixed(2);}).join(',') + ']' +
              ' to=[' + toPos.map(function(v){return v.toFixed(2);}).join(',') + ']');
          });
        });
        return;
      }
      var missing = [];
      if (!camXform)   missing.push('CAM_Free_Transform');
      if (!vpFree)     missing.push('VP_Free');
      if (!camTimer)   missing.push('CAM_FlyTimer');
      if (!easeInterp) missing.push('CAM_FlyEase');
      if (!posInterp)  missing.push('CAM_FlyPosInterp');
      if (!oriInterp)  missing.push('CAM_FlyOriInterp');
      console.warn('[EventCues] camera: fly — missing vessel nodes:', missing.join(', '), '— re-export scene from Composer');
    } catch(e) { console.warn('[EventCues] camera: fly trySet exception:', e.message); }
    if (attempts < 10) setTimeout(trySet, 200);
    else console.warn('[EventCues] camera: fly — vessel nodes not found after retries');
  }
  trySet();
}

function _executeStaticCameraShot(cue) {
  var subjectPos = _resolveSubjectPos(cue.subject) || [0, 0, 0];
  var distance  = (cue.distance  !== null && cue.distance  !== undefined) ? cue.distance  : 8;
  var height    = (cue.height    !== null && cue.height    !== undefined) ? cue.height    : 3;
  var hAngle    = (cue.hAngle    !== null && cue.hAngle    !== undefined) ? cue.hAngle    : 0;
  var vAngle    = (cue.vAngle    !== null && cue.vAngle    !== undefined) ? cue.vAngle    : 0;

  var camPos = _computeCamPosition(subjectPos, distance, height, hAngle);
  var orient = _lookAtOrientation(camPos, subjectPos, vAngle);

  // Day 83: real fly support. Destination is already a flat world position +
  // single combined orientation (computed above via _lookAtOrientation) —
  // exactly the shape _flyCameraTo needs, no extra work required for this
  // shot type. cut (the default) keeps the original direct-write+bind path
  // below, unchanged.
  if (cue.transition === 'fly') {
    _flyCameraTo(camPos, orient, cue.flyDuration || 2, cue.shot || cue.label);
    return;
  }

  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var camXform = scene.getNamedNode('CAM_Free_Transform');
      var vpFree   = scene.getNamedNode('VP_Free');
      console.log('[EventCues] camera trySet attempt', attempts,
        'camXform=', camXform ? 'FOUND' : 'NULL',
        'vpFree=', vpFree ? 'FOUND' : 'NULL');
      if (camXform && vpFree) {
        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration
        // comment. Checked here, right before the actual write/bind,
        // rather than at the top of trySet(), so the retry loop itself
        // still runs to completion either way — only the final action is
        // guarded.
        if (cue._fireSeq !== undefined && cue._fireSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale static-shot bind skipped — a newer camera cue has fired since');
          return;
        }
        // Write both translation and rotation to CAM_Free_Transform.
        // VP_Free sits at local origin with identity pose — the Transform carries everything.
        // Day 77: was .getField('translation'/'rotation').setValue(...) wrapped in a
        // try/catch that fell back to direct assignment only if an exception was
        // thrown. That doesn't actually guard against the documented failure mode
        // (Camera Spec v1.3 §4) — getField().setValue() can silently fail to
        // register a value with no exception at all, so the fallback would never
        // trigger on the specific case it needed to. Direct assignment first, no
        // fallback needed — matches the pattern already proven everywhere else in
        // this file.
        camXform.translation = new X3D.SFVec3f(camPos[0], camPos[1], camPos[2]);
        camXform.rotation    = new X3D.SFRotation(orient[0], orient[1], orient[2], orient[3]);
        console.log('[EventCues] camera: CAM_Free_Transform written OK — binding VP_Free');
        var _camLog = 'subj=' + (cue.subject || 'origin')
          + ' pos=[' + camPos.map(function(v){return v.toFixed(2);}).join(',') + ']'
          + ' orient=[' + orient.map(function(v){return v.toFixed(3);}).join(',') + ']'
          + (attempts > 1 ? ' (attempt ' + attempts + ')' : '');
        console.log('[EventCues] camera: VP_Free static shot "' + (cue.shot || cue.label) + '"', _camLog);
        // Bind VP_Free after one rAF so X_ITE processes the Transform write first.
        requestAnimationFrame(function() {
          console.log('[EventCues] camera: set_bind firing now');
          vpFree.set_bind = true;
        });
        return;
      }
      if (!camXform) console.warn('[EventCues] camera: CAM_Free_Transform not found — re-export scene from Composer');
      if (!vpFree)   console.warn('[EventCues] camera: VP_Free not found — re-export scene from Composer');
    } catch(e) { console.warn('[EventCues] camera trySet exception:', e.message); }
    if (attempts < 10) {
      setTimeout(trySet, 200);
    } else {
      console.warn('[EventCues] camera: VP_Free/CAM_Free_Transform not found after retries');
    }
  }
  trySet();
}

function _executeAgentOrbit(cue) {
  var subjectSafe = (cue.subject || '').replace(/[^A-Za-z0-9_]/g, '_');
  if (!subjectSafe) {
    console.warn('[EventCues] camera: agent_orbit — cue has no subject, skipped');
    return;
  }

  var radius   = (cue.distance !== null && cue.distance !== undefined) ? parseFloat(cue.distance) : 5;
  var height   = (cue.height   !== null && cue.height   !== undefined) ? parseFloat(cue.height)   : 1.7;
  var hAngle   = (cue.hAngle   !== null && cue.hAngle   !== undefined) ? parseFloat(cue.hAngle)   : 0;
  var vAngle   = (cue.vAngle   !== null && cue.vAngle   !== undefined) ? parseFloat(cue.vAngle)   : -8;
  var duration = (cue.dur      !== null && cue.dur      !== undefined) ? parseFloat(cue.dur)      : 4;
  var doLoop   = (cue.loop === true || cue.loop === 'true');

  var STEPS = 36;
  var keys = [];
  var posKeys = [];
  var oriKeys = [];
  var subjectPos = [0, 0, 0]; // local origin — avatar Transform IS the world position

  for (var i = 0; i <= STEPS; i++) {
    var frac = i / STEPS;
    var theta = (hAngle + frac * 360) * Math.PI / 180;
    var cx = radius * Math.sin(theta);
    var cy = height;
    var cz = radius * Math.cos(theta);
    var orient = _lookAtOrientation([cx, cy, cz], subjectPos, vAngle);
    keys.push(frac);
    posKeys.push(cx, cy, cz);
    oriKeys.push(orient[0], orient[1], orient[2], orient[3]);
  }

  // Day 64: the four internal vessel nodes (Transform/Viewpoint/TimeSensor/2x Interpolator)
  // and their four ROUTEs are gone from view — they now live inside AgentOrbitCamera's
  // ProtoBody (mccf_camera_protos.x3d), wired with static IS connections and static
  // ROUTEs baked in at proto-declare time. This function talks to exactly one node —
  // the ProtoInstance itself, DEF'd CAM_OrbitProto_{subject} by the Composer — through
  // its exposed interface. No addRoute calls needed anymore: routing is structural, not
  // runtime-assembled, so there's nothing left for this function to wire.
  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var orbitProto = null;
      // Day 77: CAM_OrbitProto_{subject} now lives inside the avatar's own Inline
      // scope (Character-Creator-authored rig), same reasoning and same fallback
      // order as _bindNamedViewpoint's update above.
      try { orbitProto = scene.getImportedNode('CAM_OrbitProto_' + subjectSafe); } catch(ie) {}
      if (!orbitProto) { try { orbitProto = scene.getNamedNode('CAM_OrbitProto_' + subjectSafe); } catch(ne) {} }

      if (orbitProto) {
        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration comment.
        if (cue._fireSeq !== undefined && cue._fireSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale agent_orbit bind skipped — a newer camera cue has fired since');
          return;
        }

        var keyField      = orbitProto.getField('key');
        var keyValueField = orbitProto.getField('keyValue');
        var oriValueField = orbitProto.getField('oriKeyValue');
        keyField.length      = 0;
        keyValueField.length = 0;
        oriValueField.length = 0;
        for (var ki = 0; ki <= STEPS; ki++) {
          keyField[ki]      = keys[ki];
          keyValueField[ki] = new X3D.SFVec3f(posKeys[ki*3], posKeys[ki*3+1], posKeys[ki*3+2]);
          oriValueField[ki] = new X3D.SFRotation(oriKeys[ki*4], oriKeys[ki*4+1], oriKeys[ki*4+2], oriKeys[ki*4+3]);
        }

        orbitProto.cycleInterval = duration;
        orbitProto.loop          = doLoop;

        // Day 77: was .getField('initialTranslation').setValue(...) — the exact SAI
        // pattern Camera Spec v1.3 §4 already proved unreliable, and the same fix
        // applied everywhere else this session. Every OTHER field in this function
        // already used direct assignment (cycleInterval, loop, the keyValue/
        // oriKeyValue array writes above) — only these two were left on the old
        // pattern, likely explaining "camera moves slightly but never reaches its
        // first position": set_bind would still correctly switch which viewpoint is
        // bound, but the starting pose could silently fail to register, leaving the
        // camera at a stale position until the keyframe animation gradually moved it.
        orbitProto.initialTranslation = new X3D.SFVec3f(posKeys[0], posKeys[1], posKeys[2]);
        orbitProto.initialRotation    = new X3D.SFRotation(oriKeys[0], oriKeys[1], oriKeys[2], oriKeys[3]);

        requestAnimationFrame(function() {
          orbitProto.set_bind = true;
          requestAnimationFrame(function() {
            var _t0 = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
              ? canvas.browser.currentTime : (performance.now() / 1000);
            orbitProto.startTime = _t0;
            orbitProto.enabled   = true;
            console.log('[EventCues] camera: agent_orbit started — subject=' + subjectSafe
              + ' radius=' + radius + ' height=' + height + ' hAngle=' + hAngle
              + ' dur=' + duration + ' loop=' + doLoop);
          });
        });
        return;
      }

      console.warn('[EventCues] camera: agent_orbit — missing proto instance CAM_OrbitProto_'
        + subjectSafe + ' — re-export scene from Composer');

    } catch(e) { console.warn('[EventCues] camera: agent_orbit trySet exception:', e.message); }
    if (attempts < 10) setTimeout(trySet, 200);
    else console.warn('[EventCues] camera: agent_orbit — proto instance not found after retries');
  }
  trySet();
}

function _executeAgentTrack(cue) {
  var subjectSafe = (cue.subject || '').replace(/[^A-Za-z0-9_]/g, '_');
  if (!subjectSafe) {
    console.warn('[EventCues] camera: agent_track — cue has no subject, skipped');
    return;
  }

  var off0    = (cue.trackOffset    !== null && cue.trackOffset    !== undefined) ? parseFloat(cue.trackOffset)    : -3;
  var off1    = (cue.trackOffsetEnd !== null && cue.trackOffsetEnd !== undefined) ? parseFloat(cue.trackOffsetEnd) : 3;
  var height  = (cue.height         !== null && cue.height         !== undefined) ? parseFloat(cue.height)         : 1.7;
  var depth   = (cue.trackDepth     !== null && cue.trackDepth     !== undefined) ? parseFloat(cue.trackDepth)     : 4;
  var vAngle  = (cue.vAngle         !== null && cue.vAngle         !== undefined) ? parseFloat(cue.vAngle)         : -8;
  var duration= (cue.dur            !== null && cue.dur            !== undefined) ? parseFloat(cue.dur)            : 4;
  // loop is orbit/agent_orbit-only per spec §3 — agent_track always plays once.
  var doLoop  = false;

  var STEPS = 36;
  var keys = [];
  var posKeys = [];
  var oriKeys = [];
  var localOrigin = [0, 0, 0]; // local origin — avatar Transform IS the world position

  for (var i = 0; i <= STEPS; i++) {
    var frac = i / STEPS;
    var cx = off0 + (off1 - off0) * frac;
    var cy = height;
    var cz = depth;
    var orient = _lookAtOrientation([cx, cy, cz], localOrigin, vAngle);
    keys.push(frac);
    posKeys.push(cx, cy, cz);
    oriKeys.push(orient[0], orient[1], orient[2], orient[3]);
  }

  // Day 64: converted to the same AgentTrackCamera proto pattern as agent_orbit — one
  // ProtoInstance (CAM_TrackProto_{subject}) replaces the five internal vessel DEFs this
  // function used to reach individually. No addRoute calls needed: routing is static
  // inside the ProtoBody now, not runtime-assembled.
  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var trackProto = null;
      // Day 77: CAM_TrackProto_{subject} now lives inside the avatar's own Inline
      // scope — same fix as _executeAgentOrbit above.
      try { trackProto = scene.getImportedNode('CAM_TrackProto_' + subjectSafe); } catch(ie) {}
      if (!trackProto) { try { trackProto = scene.getNamedNode('CAM_TrackProto_' + subjectSafe); } catch(ne) {} }

      if (trackProto) {

        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration comment.
        if (cue._fireSeq !== undefined && cue._fireSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale agent_track bind skipped — a newer camera cue has fired since');
          return;
        }

        var keyField      = trackProto.getField('key');
        var keyValueField = trackProto.getField('keyValue');
        var oriValueField = trackProto.getField('oriKeyValue');
        keyField.length      = 0;
        keyValueField.length = 0;
        oriValueField.length = 0;
        for (var ki = 0; ki <= STEPS; ki++) {
          keyField[ki]      = keys[ki];
          keyValueField[ki] = new X3D.SFVec3f(posKeys[ki*3], posKeys[ki*3+1], posKeys[ki*3+2]);
          oriValueField[ki] = new X3D.SFRotation(oriKeys[ki*4], oriKeys[ki*4+1], oriKeys[ki*4+2], oriKeys[ki*4+3]);
        }

        trackProto.cycleInterval = duration;
        trackProto.loop          = doLoop;

        // Day 77: same fix as agent_orbit's equivalent lines above — was
        // .getField('initialTranslation').setValue(...), the unreliable pattern.
        trackProto.initialTranslation = new X3D.SFVec3f(posKeys[0], posKeys[1], posKeys[2]);
        trackProto.initialRotation    = new X3D.SFRotation(oriKeys[0], oriKeys[1], oriKeys[2], oriKeys[3]);

        requestAnimationFrame(function() {
          trackProto.set_bind = true;
          requestAnimationFrame(function() {
            var _t0 = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
              ? canvas.browser.currentTime : (performance.now() / 1000);
            trackProto.startTime = _t0;
            trackProto.enabled   = true;
            console.log('[EventCues] camera: agent_track started — subject=' + subjectSafe
              + ' offset=' + off0 + '→' + off1 + ' depth=' + depth + ' height=' + height
              + ' dur=' + duration);
          });
        });
        return;
      }

      console.warn('[EventCues] camera: agent_track — missing proto instance CAM_TrackProto_'
        + subjectSafe + ' — re-export scene from Composer');

    } catch(e) { console.warn('[EventCues] camera: agent_track trySet exception:', e.message); }
    if (attempts < 10) setTimeout(trySet, 200);
    else console.warn('[EventCues] camera: agent_track — proto instance not found after retries');
  }
  trySet();
}

function _computeOrbitMoveKeyframes(subjectPos, cue, steps) {
  var radius = (cue.distance !== null && cue.distance !== undefined) ? parseFloat(cue.distance) : 5;
  var height = (cue.height   !== null && cue.height   !== undefined) ? parseFloat(cue.height)   : 1.7;
  var hAngle = (cue.hAngle   !== null && cue.hAngle   !== undefined) ? parseFloat(cue.hAngle)   : 0;
  var vAngle = (cue.vAngle   !== null && cue.vAngle   !== undefined) ? parseFloat(cue.vAngle)   : -8;

  var keys = [], posKeys = [], oriKeys = [];
  for (var i = 0; i <= steps; i++) {
    var frac = i / steps;
    var theta = (hAngle + frac * 360) * Math.PI / 180;
    var cx = subjectPos[0] + radius * Math.sin(theta);
    var cy = subjectPos[1] + height;
    var cz = subjectPos[2] + radius * Math.cos(theta);
    var orient = _lookAtOrientation([cx, cy, cz], subjectPos, vAngle);
    keys.push(frac);
    posKeys.push(cx, cy, cz);
    oriKeys.push(orient[0], orient[1], orient[2], orient[3]);
  }
  return { keys: keys, posKeys: posKeys, oriKeys: oriKeys };
}

function _computeParametricMoveKeyframes(subjectPos, cue, steps) {
  var dist0 = (cue.distance    !== null && cue.distance    !== undefined) ? parseFloat(cue.distance)    : 5;
  var dist1 = (cue.distanceEnd !== null && cue.distanceEnd !== undefined) ? parseFloat(cue.distanceEnd) : dist0;
  var ht0   = (cue.height      !== null && cue.height      !== undefined) ? parseFloat(cue.height)      : 1.7;
  var ht1   = (cue.heightEnd   !== null && cue.heightEnd   !== undefined) ? parseFloat(cue.heightEnd)   : ht0;
  var hA0   = (cue.hAngle      !== null && cue.hAngle      !== undefined) ? parseFloat(cue.hAngle)      : 0;
  var hA1   = (cue.hAngleEnd   !== null && cue.hAngleEnd   !== undefined) ? parseFloat(cue.hAngleEnd)   : hA0;
  var vA0   = (cue.vAngle      !== null && cue.vAngle      !== undefined) ? parseFloat(cue.vAngle)      : -8;
  var vA1   = (cue.vAngleEnd   !== null && cue.vAngleEnd   !== undefined) ? parseFloat(cue.vAngleEnd)   : vA0;
  var arcDepth = (cue.arcDepth !== null && cue.arcDepth !== undefined) ? parseFloat(cue.arcDepth) : 0;

  var keys = [], posKeys = [], oriKeys = [];
  for (var i = 0; i <= steps; i++) {
    var frac = i / steps;
    var dist = dist0 + (dist1 - dist0) * frac;
    var ht   = ht0   + (ht1   - ht0)   * frac + arcDepth * Math.sin(Math.PI * frac);
    var hA   = hA0   + (hA1   - hA0)   * frac;
    var vA   = vA0   + (vA1   - vA0)   * frac;

    var camPos = _computeCamPosition(subjectPos, dist, ht, hA);
    var orient = _lookAtOrientation(camPos, subjectPos, vA);

    keys.push(frac);
    posKeys.push(camPos[0], camPos[1], camPos[2]);
    oriKeys.push(orient[0], orient[1], orient[2], orient[3]);
  }
  return { keys: keys, posKeys: posKeys, oriKeys: oriKeys };
}

function _executeMoveShot(cue) {
  var shot = cue.shot;
  var isOrbit  = (shot === 'orbit');
  var isLinear = !!_LINEAR_MOVE_SHOTS[shot];

  if (!isOrbit && !isLinear) {
    console.warn('[EventCues] camera: move shot «' + shot + '» not yet implemented');
    return;
  }

  var subjectPos = _resolveSubjectPos(cue.subject) || [0, 0, 0];
  var duration = (cue.dur !== null && cue.dur !== undefined) ? parseFloat(cue.dur) : 4;
  // loop is orbit-only per spec §3 — every other move shot plays once and holds last frame.
  var doLoop   = isOrbit && (cue.loop === true || cue.loop === 'true');

  // 36 steps = one keyframe every ~3% of the move. Matches the orbit convention
  // (one every 10° there) and is smooth enough for arcs (pan/tilt) as well as
  // straight lines (dolly).
  var STEPS = 36;
  var kf = isOrbit
    ? _computeOrbitMoveKeyframes(subjectPos, cue, STEPS)
    : _computeParametricMoveKeyframes(subjectPos, cue, STEPS);
  var keys = kf.keys, posKeys = kf.posKeys, oriKeys = kf.oriKeys;

  var attempts = 0;
  function trySet() {
    attempts++;
    try {
      var scene = canvas.browser.currentScene;
      var camXform  = scene.getNamedNode('CAM_Free_Transform');
      var vpFree    = scene.getNamedNode('VP_Free');
      var camTimer  = scene.getNamedNode('CAM_Timer');
      var posInterp = scene.getNamedNode('CAM_PosInterp');
      var oriInterp = scene.getNamedNode('CAM_OriInterp');

      if (camXform && vpFree && camTimer && posInterp && oriInterp) {

        // Day 85: stale-retry guard — see _cameraCueFireSeq's declaration comment.
        if (cue._fireSeq !== undefined && cue._fireSeq !== _cameraCueFireSeq) {
          console.log('[EventCues] camera: stale move-shot bind skipped — a newer camera cue has fired since');
          return;
        }

        // Write keyframes to interpolators using indexed MF array assignment.
        // Confirmed pattern from official X_ITE README (createNode/keyframe example):
        //   interpolator.key[i] = ...;  interpolator.keyValue[i] = new X3D.SFVec3f(...);
        // NOT a bulk MFFloat/MFVec3f constructor call — that API does not exist in X_ITE.
        // Truncate any stale authored placeholder values before repopulating.
        posInterp.key.length      = 0;
        posInterp.keyValue.length = 0;
        oriInterp.key.length      = 0;
        oriInterp.keyValue.length = 0;
        for (var ki = 0; ki <= STEPS; ki++) {
          posInterp.key[ki]      = keys[ki];
          posInterp.keyValue[ki] = new X3D.SFVec3f(posKeys[ki*3], posKeys[ki*3+1], posKeys[ki*3+2]);
          oriInterp.key[ki]      = keys[ki];
          oriInterp.keyValue[ki] = new X3D.SFRotation(oriKeys[ki*4], oriKeys[ki*4+1], oriKeys[ki*4+2], oriKeys[ki*4+3]);
        }

        // DIAGNOSTIC — confirm the interpolator nodes actually hold the keyframes we just wrote.
        console.log('[EventCues] camera: ' + shot + ' keyframe check — posInterp.key.length=' + posInterp.key.length
          + ' posInterp.keyValue.length=' + posInterp.keyValue.length
          + ' oriInterp.key.length=' + oriInterp.key.length
          + ' oriInterp.keyValue.length=' + oriInterp.keyValue.length);
        console.log('[EventCues] camera: ' + shot + ' keyframe[0]=', posInterp.keyValue[0] && posInterp.keyValue[0].toString());
        console.log('[EventCues] camera: ' + shot + ' keyframe[last]=', posInterp.keyValue[STEPS] && posInterp.keyValue[STEPS].toString());

        // Belt-and-suspenders — add the ROUTEs via SAI as well as relying on the static XML
        // ROUTEs from the Composer export. Browser.addRoute is idempotent-safe to call even
        // if the route already exists from the X3D file; confirms the chain at runtime.
        try {
          canvas.browser.addRoute(camTimer,  'fraction_changed', posInterp, 'set_fraction');
          canvas.browser.addRoute(camTimer,  'fraction_changed', oriInterp, 'set_fraction');
          canvas.browser.addRoute(posInterp, 'value_changed',    camXform,  'set_translation');
          canvas.browser.addRoute(oriInterp, 'value_changed',    camXform,  'set_rotation');
          console.log('[EventCues] camera: ' + shot + ' ROUTEs added via SAI (belt-and-suspenders)');
        } catch(e) { console.warn('[EventCues] camera: addRoute via SAI failed:', e.message); }

        // Configure timer — direct property assignment throughout (confirmed working pattern).
        camTimer.cycleInterval = duration;
        camTimer.loop          = doLoop;

        // Snap camera to move start position then bind VP_Free (TELEPORT, instantaneous).
        // This is intentional — the authored start values are where the shot begins.
        // Day 77: was .getField('translation'/'rotation').setValue(...) — the exact
        // unreliable pattern the comment above this block already claimed had been
        // replaced everywhere in this function. These two lines were simply missed.
        camXform.translation = new X3D.SFVec3f(posKeys[0], posKeys[1], posKeys[2]);
        camXform.rotation    = new X3D.SFRotation(oriKeys[0], oriKeys[1], oriKeys[2], oriKeys[3]);

        requestAnimationFrame(function() {
          vpFree.set_bind = true;
          // Start timer one rAF after bind so VP_Free is active before interpolators fire.
          // Use direct property assignment — confirmed working pattern from walk/avatar code.
          // startTime set before enabled=true, matching dwell/segment timer pattern (line ~1592).
          requestAnimationFrame(function() {
            // canvas.browser.currentTime returns 0 in some X_ITE builds (confirmed
            // elsewhere in this file, e.g. line ~1708) — fall back to performance.now()/1000
            // exactly as every other startTime write in this codebase already does.
            var _moveStartTime = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
              ? canvas.browser.currentTime : (performance.now() / 1000);
            camTimer.startTime = _moveStartTime;
            camTimer.enabled   = true;
            console.log('[EventCues] camera: ' + shot + ' started — subject=' + (cue.subject||'?')
              + ' dur=' + duration + ' loop=' + doLoop);
          });
        });
        return;
      }

      var missing = [];
      if (!camXform)  missing.push('CAM_Free_Transform');
      if (!vpFree)    missing.push('VP_Free');
      if (!camTimer)  missing.push('CAM_Timer');
      if (!posInterp) missing.push('CAM_PosInterp');
      if (!oriInterp) missing.push('CAM_OriInterp');
      console.warn('[EventCues] camera: ' + shot + ' — missing vessel nodes:', missing.join(', '),
        '— re-export scene from Composer');

    } catch(e) { console.warn('[EventCues] camera: ' + shot + ' trySet exception:', e.message); }
    if (attempts < 10) setTimeout(trySet, 200);
    else console.warn('[EventCues] camera: ' + shot + ' — vessel nodes not found after retries');
  }
  trySet();
}

function _fireFogEventCue(cue) {
  // Convention: DEF="SceneFog" on the Fog node.
  // cue.label may encode visibilityRange as a number string for now.
  try {
    var scene = canvas.browser.currentScene;
    var fogNode = scene.getNamedNode('SceneFog');
    if (fogNode) {
      var range = parseFloat(cue.label);
      if (!isNaN(range)) fogNode.visibilityRange = range;
      console.log('[EventCues] fog: visibilityRange →', isNaN(range) ? '(no change)' : range);
    } else {
      console.warn('[EventCues] fog: SceneFog node not found');
    }
  } catch(e) { console.warn('[EventCues] fog failed:', e); }
}

function _fireBgEventCue(cue) {
  // Convention: DEF="SceneBG" on the Background node.
  // TODO: parse skyColor from cue.label when format is defined.
  try {
    var scene = canvas.browser.currentScene;
    var bgNode = scene.getNamedNode('SceneBG');
    if (bgNode) {
      console.log('[EventCues] bg: SceneBG found — skyColor encoding TBD, label:', cue.label);
    } else {
      console.warn('[EventCues] bg: SceneBG node not found');
    }
  } catch(e) { console.warn('[EventCues] bg failed:', e); }
}

function _fireBehaviorEventCue(cue) {
  // Day 85: real bug fix, confirmed by grep — this called a function named
  // switchBehaviorTimer (no leading underscore), which does not exist
  // anywhere in this file. Every call threw a ReferenceError, silently
  // swallowed by the catch below, so this path has never actually worked.
  // Even fixed to the real function name, it would have been the wrong
  // one: _switchBehaviorTimer is the low-level walk/idle-only switcher,
  // keyed by a raw TimeSensor DEF name ('WalkTimer'/'DefaultTimer'), which
  // is what THIS legacy 'behavior' track was actually authored against.
  // The 'gesture' track below (current schema) is the one that needs
  // applyBehaviorClip's richer, named-clip handling instead — see that
  // function's own comment for why the two aren't interchangeable.
  // No current authoring UI produces 'behavior' track cues (the Day-81
  // Events Editor's TRACKS list is camera/light/gesture/path) — kept
  // working rather than deleted per this project's "flag, don't rip out
  // blind" rule, in case an older exported scene XML still has one.
  if (!cue.agent || !cue.clip) return;
  try {
    var safeName = cue.agent.replace(/[^A-Za-z0-9_]/g, '_');
    _switchBehaviorTimer(safeName, cue.clip);
    console.log('[EventCues] behavior:', cue.agent, 'timer →', cue.clip);
  } catch(e) { console.warn('[EventCues] behavior failed:', cue.agent, cue.clip, e); }
}

function _resolveEventCueTriggerNode(triggerRef, attempt, onFound, onGiveUp) {
  attempt = attempt || 1;
  var node;
  try {
    var scene = canvas.browser.currentScene;
    try { node = scene.getImportedNode(triggerRef); } catch(ie) {}
    if (!node) { try { node = scene.getNamedNode(triggerRef); } catch(ne) {} }
  } catch(e) {}
  if (node) { onFound(node, attempt); return; }
  if (attempt < 10) {
    setTimeout(function() { _resolveEventCueTriggerNode(triggerRef, attempt + 1, onFound, onGiveUp); }, 200);
  } else if (onGiveUp) {
    onGiveUp();
  }
}

function _fireMovieVisibilityEventCue(cue) {
  if (!cue.triggerRef || !cue.internalDef) {
    console.warn('[EventCues] movie: cue missing internalDef (no Shape name authored) — nothing to fire:', cue);
    return;
  }
  _resolveEventCueTriggerNode(cue.triggerRef, 1,
    function(node, attempt) {
      try {
        node.visible = cue.visible;
        console.log('[EventCues] movie: ' + cue.internalDef + ' visible=' + cue.visible,
                    attempt > 1 ? '(attempt ' + attempt + ')' : '');
      } catch(e) {
        console.warn('[EventCues] movie: found ' + cue.triggerRef + ' but it has no visible field (not a Shape?):', e.message);
      }
    },
    function() {
      console.warn('[EventCues] movie: ' + cue.triggerRef + ' not found after retries — check the asset has a real <EXPORT localDEF="' + cue.internalDef + '" AS="' + cue.internalDef + '"/> statement in its own file');
    }
  );
}

function _fireTurnEventCue(cue) {
  if (!cue.triggerRef || !cue.target) {
    console.warn('[EventCues] turn: cue missing triggerRef or target — nothing to fire:', cue);
    return;
  }
  _resolveEventCueTriggerNode(cue.triggerRef, 1,
    function(turnTimer, attempt) {
      try {
        var scene = canvas.browser.currentScene;
        var safeTarget = cue.target.replace(/[^A-Za-z0-9_]/g, '_');
        var targetNode = null;
        try { targetNode = scene.getNamedNode('Avatar_' + safeTarget); } catch(e1) {}
        if (!targetNode) { try { targetNode = scene.getNamedNode('PlacedAsset_' + safeTarget); } catch(e2) {} }
        if (!targetNode) {
          console.warn('[EventCues] turn: target "' + cue.target + '" not found as Avatar_' + safeTarget +
            ' or PlacedAsset_' + safeTarget + ' — nothing to rotate');
          return;
        }
        var interpName = 'TurnInterp_' + cue.triggerRef.replace(/^TurnTimer_/, '');
        var turnInterp = null;
        try { turnInterp = scene.getNamedNode(interpName); } catch(eI) {}
        if (!turnInterp) {
          console.warn('[EventCues] turn: ' + interpName + ' not found — scene needs a fresh Export X3D to pick up the turn cue nodes');
          return;
        }
        // Read the target's current Y-axis angle defensively — same
        // reasoning as the path ease-in's rotation read: real, genuine
        // uncertainty about SFRotation's exact read-back shape in this
        // codebase, confirmed only for writes, not reads. A turn only
        // means anything as a pure Y-axis rotation; if the current
        // rotation's axis isn't recognizably (0,1,0) (or the identity/
        // zero-angle axis X3D uses for "no rotation yet"), starting angle
        // defaults to 0 rather than guessing at unsupported axis math —
        // with a warning, so this is visible rather than silently wrong.
        var curAngle = 0;
        try {
          var curRot = targetNode.rotation;
          if (curRot && typeof curRot.angle === 'number') {
            var ax = curRot.x, ay = curRot.y, az = curRot.z;
            var isYAxis = (Math.abs(ax) < 1e-4 && Math.abs(az) < 1e-4 &&
                           (Math.abs(ay - 1) < 1e-4 || Math.abs(ay) < 1e-4));
            if (isYAxis) {
              curAngle = (Math.abs(ay) < 1e-4) ? 0 : curRot.angle;
            } else {
              console.warn('[EventCues] turn: ' + cue.target + '\'s current rotation axis isn\'t (0,1,0) — (' +
                ax + ',' + ay + ',' + az + '). Starting the turn from angle 0 rather than guessing; the turn ' +
                'itself will still apply correctly, just not layered on top of whatever non-Y rotation is ' +
                'already there.');
            }
          }
        } catch (eR) { /* default curAngle=0 already set */ }

        // Sign convention confirmed by direct author testing: positive
        // degrees = turn right, negative degrees = turn left. (X3D's own
        // right-hand-rule convention around +Y, viewed from above, would
        // suggest the opposite for a "forward = -Z" rig — negated here to
        // match the confirmed, tested result rather than that untested
        // assumption.) invert remains available in case a different
        // avatar's rig convention ever needs the opposite of this.
        var deltaRad = -(cue.degrees || 0) * Math.PI / 180;
        if (cue.invert) deltaRad = -deltaRad;
        var endAngle = curAngle + deltaRad;

        turnInterp.key.length = 0; turnInterp.keyValue.length = 0;
        turnInterp.key[0] = 0; turnInterp.keyValue[0] = new X3D.SFRotation(0, 1, 0, curAngle);
        turnInterp.key[1] = 1; turnInterp.keyValue[1] = new X3D.SFRotation(0, 1, 0, endAngle);

        var tNow = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
          ? canvas.browser.currentTime : (performance.now() / 1000);
        turnTimer.stopTime  = tNow - 0.01;
        turnTimer.startTime = tNow + 0.05;
        // Day 94: paired with Composer now exporting TurnTimer_EC_* as
        // enabled="false" (was missing entirely — defaulted to
        // enabled=true, which let an orphaned turn cue fire itself with
        // no trigger). Every other dynamically-fired timer in this file
        // already re-enables itself here the same way; this one just
        // never had to before, since it didn't start disabled.
        turnTimer.enabled   = true;
        console.log('[EventCues] turn: ' + cue.target + ' — ' + (cue.degrees||0) + '\u00b0 over ' +
          (cue.duration||2) + 's' + (cue.invert ? ' (inverted)' : '') + ', from ' +
          (curAngle*180/Math.PI).toFixed(1) + '\u00b0 to ' + (endAngle*180/Math.PI).toFixed(1) + '\u00b0',
          attempt > 1 ? '(attempt ' + attempt + ')' : '');
      } catch (e) {
        console.warn('[EventCues] turn: failed to fire (' + e.message + ')');
      }
    },
    function() {
      console.warn('[EventCues] turn: ' + cue.triggerRef + ' not found after retries — scene needs a fresh Export X3D to pick up the turn cue nodes');
    }
  );
}

function _fireEffectEventCue(cue) {
  if (!cue.triggerRef) {
    console.warn('[EventCues] effect: cue has no triggerRef — was this exported by the current Composer? Re-export and try again:', cue);
    return;
  }
  _resolveEventCueTriggerNode(cue.triggerRef, 1,
    function(node, attempt) {
      try {
        var tNow = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
          ? canvas.browser.currentTime : (performance.now() / 1000);
        node.stopTime  = tNow - 0.01;
        node.startTime = tNow + 0.05;
        node.enabled   = true; // Day 94 precedent (path/turn timers): must be set explicitly, a TimeSensor with only startTime written can stay disabled
        console.log('[EventCues] effect: ' + cue.target + ' (' + (cue.from||'?') + ' → ' + (cue.to||'?') + ') started at t=' + tNow.toFixed(2),
                    attempt > 1 ? '(attempt ' + attempt + ')' : '');
      } catch(e) {
        console.warn('[EventCues] effect: found ' + cue.triggerRef + ' but it has no startTime field (not a TimeSensor?):', e.message);
      }
    },
    function() {
      console.warn('[EventCues] effect: ' + cue.triggerRef + ' not found after retries — check "' + cue.target + '" is still a registered Effect Target in Composer\'s Assets tab, and re-export.');
    }
  );
}

function _fireAnimationEventCue(cue) {
  if (!cue.triggerRef || !cue.internalDef) {
    console.warn('[EventCues] animation: cue missing internalDef (no TimeSensor name authored) — nothing to fire:', cue);
    return;
  }
  _resolveEventCueTriggerNode(cue.triggerRef, 1,
    function(node, attempt) {
      try {
        var tNow = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
          ? canvas.browser.currentTime : (performance.now() / 1000);
        node.stopTime  = tNow - 0.01;
        node.startTime = tNow + 0.05;
        console.log('[EventCues] animation: ' + cue.internalDef + ' started at t=' + tNow.toFixed(2),
                    attempt > 1 ? '(attempt ' + attempt + ')' : '');
      } catch(e) {
        console.warn('[EventCues] animation: found ' + cue.triggerRef + ' but it has no startTime field (not a TimeSensor?):', e.message);
      }
    },
    function() {
      console.warn('[EventCues] animation: ' + cue.triggerRef + ' not found after retries — check the asset has a real <EXPORT localDEF="' + cue.internalDef + '" AS="' + cue.internalDef + '"/> statement in its own file');
    }
  );
}

function _firePathEventCue(cue) {
  if (!cue.target || !cue.pathId || !cue.triggerRef) {
    console.warn('[EventCues] path: cue missing target/pathId — nothing to fire:', cue);
    return;
  }
  if (cue.walkGesture) {
    // Reuses the exact same, already-proven gesture-firing logic — a
    // synthetic cue object is all _fireGestureEventCue actually needs.
    _fireGestureEventCue({ target: cue.target, clip: cue.walkGesture });
  }
  _resolveEventCueTriggerNode(cue.triggerRef, 1,
    function(mainTimer) {
      var scene = canvas.browser.currentScene;
      var safeTarget = cue.target.replace(/[^A-Za-z0-9_]/g, '_');
      var targetNode = null;
      try { targetNode = scene.getNamedNode('Avatar_' + safeTarget); } catch(e) {}
      if (!targetNode) { try { targetNode = scene.getNamedNode('PlacedAsset_' + safeTarget); } catch(e2) {} }
      // Real bug fix: pbPushPosition (and several sibling functions —
      // the broadcast-position write, pbJump, TTS-delay timing) already
      // have a guard for exactly this class of conflict —
      // `if (_x3dTimerActive[nodeName]) return;` — "if an X3D TimeSensor
      // is driving this avatar, don't also write its position from JS."
      // That guard has only ever been set by the OLD arc/waypoint
      // Timer_{agent}_N system (pbActivateX3DTimers). A RecordedPath-driven
      // agent never sets it, so every one of those guards silently never
      // fires for an agent like this — confirmed live: pbPushPosition
      // pushed Avatar_Anna straight to a waypoint file's "Begin"/"Sit"
      // coordinates (both landing at/near the Island/lake zone) while the
      // path's own continuous position control was simultaneously active,
      // fighting over her Transform. Setting the SAME existing flag here
      // makes all of those already-correct guards recognize a
      // RecordedPath-driven agent too, rather than adding a new,
      // narrower, one-off check just for this function. Cleared
      // automatically wherever _x3dTimerActive already gets wholesale
      // reset (pbReset, pbPlayAll's generation bump, pbStopX3DTimers) —
      // no separate cleanup needed.
      if (targetNode) {
        _x3dTimerActive['Avatar_' + safeTarget] = true;
        // Closes a real timing gap in the fix above: the flag only stops
        // FUTURE pbPushPosition calls from starting a write. A waypoint
        // "arrive" trigger firing before this cue's t0 (very common — the
        // very first waypoint arrival typically fires near t=0, while a
        // path cue often has its own t0 a second or so later) can already
        // have a JS lerp (setInterval-driven, running for pace seconds —
        // default 3s) actively in flight by the time this line runs. The
        // flag alone doesn't stop an already-running interval; it has to
        // be cancelled directly. Same cancellation pbPushPosition already
        // does to itself when starting a new lerp — reused here so a path
        // cue reliably wins over a lerp that's already mid-flight instead
        // of the two fighting over the same Transform for the next couple
        // of seconds.
        if (_lerpActive[safeTarget]) {
          clearInterval(_lerpActive[safeTarget].timer);
          delete _lerpActive[safeTarget];
        }
      }
      var tNow = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
        ? canvas.browser.currentTime : (performance.now() / 1000);
      function startMainDirectly(why) {
        mainTimer.stopTime  = tNow - 0.01;
        mainTimer.startTime = tNow + 0.05;
        // Day 94: paired with Composer now exporting PathTimer_EC_* as
        // enabled="false" — see the ease-in block below for the fuller
        // explanation; this is the direct-start fallback's own copy of
        // the same fix, needed here too since these code paths return
        // before ever reaching the ease-in block.
        mainTimer.enabled   = true;
        console.log('[EventCues] path: ' + cue.target + ' — main path timer started directly (' + why + ')');
      }
      if (!targetNode || !cue.pathStart) {
        startMainDirectly(!targetNode ? 'target node not found' : 'no pathStart recorded');
        return;
      }
      var cur;
      try { cur = targetNode.translation; } catch(e3) { cur = null; }
      // Defensive: if the read-back shape isn't what's expected (real,
      // remaining uncertainty about SFVec3f's exact property names on a
      // read, vs. the constructor pattern confirmed for writes), fail
      // safely to the instant-start fallback rather than risk computing
      // NaN distances and silently building a broken ease-in.
      if (cur && (typeof cur.x !== 'number' || typeof cur.y !== 'number' || typeof cur.z !== 'number')) {
        console.warn('[EventCues] path: read back translation in an unexpected shape', cur, '— treating as unreadable');
        cur = null;
      }
      var dx = cur ? (cue.pathStart[0]-cur.x) : 999, dy = cur ? (cue.pathStart[1]-cur.y) : 0, dz = cur ? (cue.pathStart[2]-cur.z) : 999;
      var dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
      if (!cur || dist < 0.3) {
        startMainDirectly(cur ? ('already at path start, dist=' + dist.toFixed(2)) : 'could not read current position');
        return;
      }
      // Ease-in: fixed, reasonable duration rather than distance-scaled —
      // simple, predictable, easy to reason about while this is new.
      var easeDur = 1.5;
      var cueSafe = cue.triggerRef.replace(/[^A-Za-z0-9_]/g, '_');
      // Day 88: real, new capability — rotation ease, sharing the exact
      // same EaseTimer as position (one clock, paired interpolators,
      // same architecture as the main path playback itself). Read
      // defensively, same reasoning as the translation read above —
      // genuine, real uncertainty about SFRotation's exact read-back
      // shape, not yet proven in this codebase the way writes are
      // (confirmed via X_ITE's own examples). If anything about this
      // looks wrong, orientation easing is just skipped — the target
      // still gets the correct facing the instant the main path timer's
      // own OrientationInterpolator takes over, it just won't have eased
      // into it smoothly. Position easing is unaffected either way.
      var curRot = null;
      if (cue.pathStartOrient) {
        try { curRot = targetNode.rotation; } catch(eR) { curRot = null; }
        if (curRot && (typeof curRot.x !== 'number' || typeof curRot.y !== 'number' || typeof curRot.z !== 'number' || typeof curRot.angle !== 'number')) {
          console.warn('[EventCues] path: read back rotation in an unexpected shape', curRot, '— skipping rotation ease, position ease unaffected');
          curRot = null;
        }
      }
      // Real fix, two bugs deep: this used to dynamically build a fresh
      // TimeSensor/Interpolator via scene.createX3DFromString() on every
      // single fire. That was broken on two separate counts, confirmed
      // live: (1) createX3DFromString belongs to Browser, not X3DScene —
      // "scene.createX3DFromString is not a function" fired on literally
      // every attempt, so ease-in has never actually run; every path cue
      // has always silently fallen back to an instant jump. (2) an earlier
      // same-day fix to reuse nodes across Plays used bulk array assignment
      // on the interpolator's keyValue field (`interp.keyValue = [...]`) —
      // also unsupported by X_ITE's SAI, which only accepts indexed
      // assignment (confirmed against X_ITE's own README, see
      // _flyCameraTo's identical situation and fix above). Properly fixed
      // by following this project's own already-proven pattern for exactly
      // this problem: Composer now bakes reusable PathEaseTimer/
      // PathEaseInterp/PathEaseOrient nodes (and their routes) into the
      // compiled scene once per path cue, at export time, next to that
      // cue's main path nodes — same relationship CAM_FlyTimer/
      // CAM_FlyPosInterp/CAM_FlyOriInterp have to _flyCameraTo. Nothing
      // is created at runtime here anymore; this just fetches the
      // pre-baked nodes and mutates their fields with the confirmed
      // indexed-assignment pattern, exactly like _flyCameraTo does.
      var easeTimer, easeInterp, easeOrient = null;
      try {
        easeTimer  = scene.getNamedNode('PathEaseTimer_' + cueSafe);
        easeInterp = scene.getNamedNode('PathEaseInterp_' + cueSafe);
        if (curRot) { try { easeOrient = scene.getNamedNode('PathEaseOrient_' + cueSafe); } catch(eo) { easeOrient = null; } }
      } catch(eLookup) {
        console.warn('[EventCues] path: PathEaseTimer_' + cueSafe + '/PathEaseInterp_' + cueSafe +
          ' not found (' + eLookup.message + ') — scene needs a fresh Export X3D to pick up the ease-in nodes. Falling back to instant jump + direct start.');
        startMainDirectly('ease-in nodes not found in scene');
        return;
      }
      if (!easeTimer || !easeInterp) {
        console.warn('[EventCues] path: PathEaseTimer_' + cueSafe + '/PathEaseInterp_' + cueSafe +
          ' not found — scene needs a fresh Export X3D to pick up the ease-in nodes. Falling back to instant jump + direct start.');
        startMainDirectly('ease-in nodes not found in scene');
        return;
      }
      try {
        easeInterp.key.length = 0; easeInterp.keyValue.length = 0;
        easeInterp.key[0] = 0; easeInterp.keyValue[0] = new X3D.SFVec3f(cur.x, cur.y, cur.z);
        easeInterp.key[1] = 1; easeInterp.keyValue[1] = new X3D.SFVec3f(cue.pathStart[0], cue.pathStart[1], cue.pathStart[2]);
        if (curRot && easeOrient) {
          easeOrient.key.length = 0; easeOrient.keyValue.length = 0;
          easeOrient.key[0] = 0; easeOrient.keyValue[0] = new X3D.SFRotation(curRot.x, curRot.y, curRot.z, curRot.angle);
          easeOrient.key[1] = 1; easeOrient.keyValue[1] = new X3D.SFRotation(
            cue.pathStartOrient[0], cue.pathStartOrient[1], cue.pathStartOrient[2], cue.pathStartOrient[3]);
        }
        // Restart the one-shot timer: stop just before now, start just after —
        // same pattern startMainDirectly uses on mainTimer above. The route
        // from this timer's cycleTime into mainTimer.set_startTime is baked
        // statically into the scene now, so it keeps working across every
        // repeated start/stop cycle without needing to be re-added here.
        easeTimer.stopTime  = tNow - 0.01;
        easeTimer.startTime = tNow + 0.05;
        // Day 94: paired with Composer now exporting both PathEaseTimer_EC_*
        // and PathTimer_EC_* as enabled="false" (previously missing —
        // defaulted to enabled=true, letting an orphaned path cue fire
        // itself with no trigger at all, snapping its target to its
        // placeholder 0,0,0 keyValue the instant the scene clock started).
        // mainTimer is enabled here too, ahead of its own startTime — it's
        // armed via the baked cycleTime→set_startTime ROUTE below rather
        // than a direct assignment in this branch, but enabled still has
        // to be set explicitly first or that routed startTime has nothing
        // to activate when it lands.
        easeTimer.enabled   = true;
        mainTimer.enabled   = true;
        console.log('[EventCues] path: ' + cue.target + ' — easing in over ' + easeDur + 's (dist=' + dist.toFixed(2) + 'm'+(curRot&&easeOrient?', with rotation':'')+'), then main path timer starts');
      } catch(e4) {
        console.warn('[EventCues] path: ease-in field mutation failed (' + e4.message + ') — falling back to instant jump + direct start');
        startMainDirectly('ease-in mutation failed');
      }
    },
    function() {
      console.warn('[EventCues] path: ' + cue.triggerRef + ' (main path timer) not found after retries — check the recorded path has real keys and the target (' + cue.target + ') is actually placed');
    }
  );
}

var GESTURE_CUE_MAX_ATTEMPTS = 20;

var GESTURE_CUE_RETRY_MS = 250;

function _fireGestureEventCue(cue, _retry) {
  if (!cue.target || !cue.clip) {
    console.warn('[EventCues] gesture: cue missing target or clip — nothing to fire:', cue);
    return;
  }
  var safeName = cue.target.replace(/[^A-Za-z0-9_]/g, '_');
  var gen = (_retry && _retry.gen !== undefined) ? _retry.gen : _pbCbGeneration;
  var attempts = _retry ? _retry.attempts : 0;

  // Self-expire if a newer Play/Reset has superseded this cue.
  if (gen !== _pbCbGeneration) return;

  var config = _agentBehaviorClips[safeName];
  var clipsReady = !!(config && config.clips && config.clips.length);
  var timerMapReady = !!_behaviorTimerMap[safeName];

  if (!clipsReady || !timerMapReady) {
    if (attempts < GESTURE_CUE_MAX_ATTEMPTS) {
      if (attempts === 0) {
        console.log('[EventCues] gesture: ' + cue.target + ' not ready yet for "' + cue.clip + '" (' +
          (!clipsReady ? 'behavior_clips not loaded' : 'timer map not resolved') +
          ') — retrying (up to ' + GESTURE_CUE_MAX_ATTEMPTS + '×' + GESTURE_CUE_RETRY_MS + 'ms) instead of dropping the cue');
      }
      setTimeout(function() { _fireGestureEventCue(cue, { attempts: attempts + 1, gen: gen }); }, GESTURE_CUE_RETRY_MS);
    } else {
      console.warn('[EventCues] gesture: gave up on "' + cue.clip + '" for ' + cue.target + ' after ' +
        GESTURE_CUE_MAX_ATTEMPTS + ' retries (' +
        (!clipsReady ? 'behavior_clips never loaded' : 'timer map never resolved') +
        ') — check pbActivateX3DTimers logs for this agent.');
    }
    return;
  }

  var clipObj = config.clips.find(function(c) { return c.name === cue.clip; });
  if (!clipObj) {
    console.warn('[EventCues] gesture: clip "' + cue.clip + '" not found in', cue.target + "'s behavior_clips — available:", config.clips.map(function(c){ return c.name; }).join(', '));
    return;
  }
  var ok = applyBehaviorClip(safeName, clipObj);
  if (ok) {
    console.log('[EventCues] gesture:', cue.target, '→', cue.clip, attempts ? ('(resolved after ' + attempts + ' retries)') : '');
  } else {
    console.warn('[EventCues] gesture: FAILED to apply', cue.clip, 'on', cue.target,
                 '— clip was found in behavior_clips but applyBehaviorClip could not enable the timer (see warning above).');
  }
}

var _lerpActive = {};

function _ensureBehaviorClipsLoaded(cultivarName) {
  var safeName = cultivarName.replace(/[^A-Za-z0-9_]/g, '_');
  if (_agentBehaviorClips[safeName]) return; // already loaded or in flight-guarded by caller
  fetch(API + '/cultivars/' + encodeURIComponent(cultivarName))
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data) return;
      if (data.behavior_clips && data.behavior_clips.length) {
        _agentBehaviorClips[safeName] = {
          clips:   data.behavior_clips,
          default: data.behavior_default || 'Default'
        };
        console.log('_ensureBehaviorClipsLoaded: behavior clips loaded for', cultivarName,
                    '—', data.behavior_clips.length, 'clips');
      } else {
        _agentBehaviorClips[safeName] = {
          clips:   [{ name:'Default', timerDEF:'DefaultTimer', loop:true, priority:0 }],
          default: 'Default'
        };
        console.log('_ensureBehaviorClipsLoaded: no behavior clips for', cultivarName, '— DefaultTimer fallback');
      }
    })
    .catch(function() {
      _agentBehaviorClips[safeName] = {
        clips:   [{ name:'Default', timerDEF:'DefaultTimer', loop:true, priority:0 }],
        default: 'Default'
      };
    });
}

var _waypointPosMap  = {};

var _spZones        = [];

function spStartSceneTracks() {
  var musicTrack = window._spSceneMusicTrack;
  var bedTrack   = window._spSceneBedTrack;
  console.log('[sound] spStartSceneTracks: music=', !!musicTrack, 'bed=', !!bedTrack);
  try {
    var scene = canvas.browser.currentScene;
    if (!scene) return;
    var tNow = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
      ? canvas.browser.currentTime : (performance.now() / 1000);

    // Gate open — tell all SoundFader Scripts that playback is now live.
    // This prevents ProximitySensor events before Play from triggering audio.
    _spPlaybackLive = true;
    (_spZones || []).forEach(function(z) {
      try {
        var sf = scene.getNamedNode('SoundFader_' + z.key);
        if (sf) { try { sf.getField('playing').setValue(true); console.log('[sound] gate open:', 'SoundFader_' + z.key); } catch(e2) { console.warn('[sound] gate open failed:', z.key, e2); } }
      } catch(e) {}
    });

    // Start Music clip via SAI — clears any prior stopTime guard first
    try {
      var mClip = scene.getNamedNode('Clip_Music');
      if (mClip) {
        mClip.enabled   = true;          // lift the enabled=false load-time block (see _quiesceSceneAudio)
        mClip.stopTime  = tNow - 0.01;   // clear guard (startTime=-1 stopTime=-2 set by composer)
        mClip.startTime = tNow + 0.05;
        console.log('[sound] Clip_Music started via SAI at t=', tNow.toFixed(2),
                    'loop=', mClip.loop);
      } else {
        console.log('[sound] Clip_Music not found in scene');
      }
    } catch(e) { console.warn('[sound] Clip_Music start error:', e); }

    // Start Bed clip via SAI — enable first (X_ITE ignores startTime guard on loop=true
    // clips at AudioDestination init time; enabled=false in X3D is the reliable block).
    try {
      var bClip = scene.getNamedNode('Clip_Bed');
      if (bClip) {
        bClip.enabled   = true;           // lift the enabled=false load-time block
        bClip.stopTime  = tNow - 0.01;   // clear startTime=-1 stopTime=-2 guard
        bClip.startTime = tNow + 0.05;
        console.log('[sound] Clip_Bed started via SAI at t=', tNow.toFixed(2),
                    'loop=', bClip.loop);
      } else {
        console.log('[sound] Clip_Bed not found in scene');
      }
    } catch(e) { console.warn('[sound] Clip_Bed start error:', e); }

    // Day 87: real fix — this was a single one-shot lookup, no retry at
    // all, unlike the proven-working avatar-timer imports elsewhere in
    // this file (which retry several times, 200ms apart, exactly because
    // an Inline'd file isn't guaranteed to have finished loading and
    // resolving its IMPORT the instant Play is clicked). Confirmed via
    // Sunrize: the file parses cleanly and the MovieTexture itself loads
    // fine — "TheSceneMovie not found" is much more likely this Inline
    // (a 33MB video) still loading at the exact moment Play fires than
    // any remaining syntax problem. Retrying up to 10x/200ms gives it
    // real time to finish without silently failing if it's just slow.
    (function tryStartMovie(attempt) {
      attempt = attempt || 1;
      var movieNode;
      // Day 87: real fix — every other IMPORT resolution in this file
      // (camera viewpoints, orbit/track protos, behavior clips) uses
      // getImportedNode(), never plain getNamedNode(), for a name
      // introduced via IMPORT. This was the one place that only ever
      // tried getNamedNode(), which explains "not found after retries"
      // even with a correct <IMPORT>/<EXPORT> pair and no timing issue
      // at all — retrying the wrong lookup just retries the wrong thing.
      try { movieNode = scene.getImportedNode('TheSceneMovie'); } catch(ie) {}
      if (!movieNode) { try { movieNode = scene.getNamedNode('TheSceneMovie'); } catch(ne) {} }
      if (movieNode) {
        var tNow2 = (canvas.browser.currentTime && canvas.browser.currentTime > 0)
          ? canvas.browser.currentTime : (performance.now() / 1000);
        movieNode.stopTime  = tNow2 - 0.01;
        movieNode.startTime = tNow2 + 0.05;
        console.log('[movie] TheSceneMovie started via SAI at t=', tNow2.toFixed(2),
                    attempt > 1 ? '(attempt ' + attempt + ')' : '');
        return;
      }
      if (attempt < 10) {
        setTimeout(function() { tryStartMovie(attempt + 1); }, 200);
      } else {
        console.log('[movie] TheSceneMovie not found after retries — no asset in this scene is marked "drives movie playback", or its Inline never finished loading');
      }
    })();

  } catch(e) { console.warn('spStartSceneTracks error:', e); }
}

var _spPlaybackLive = false;
// ---- end of extracted code ----

// ================= wrapper (written for the editor) =================
var _cultivarStartPos = {};   // an implicit global in the Loader; declared here so no fallback path can throw
var RUNNABLE = {"camera":1,"fog":1,"bg":1,"effect":1,"animation":1,"movie":1,"turn":1,"path":1,"audio":1,"midi":1,"gesture":1,"face":1,"behavior":1};
var NOT_PREVIEWED = {"light":"lights: the Loader's own cue parser does not read a light cue's target yet, and its light executor says so"};
var _runTimers = [], _runStart = null, _running = false, _hasRun = false, _endAt = 0, _hooks = {}, _timerNames = [], _fired = 0, _failed = [];
var _faceRest = {}, _faceRestLoops = {};   // agent -> {AU: resting weight}, captured before the agent's first face cue; agent -> the ease-back in progress
var _muted = true, _soundNames = [], _gainWas = {}, _silenced = 0;   // the editor preview starts SILENT: the author switches sound on

function _dispatch(cue) {
  switch (cue.track) {
    case 'camera':    _fireCameraEventCue(cue); break;
    case 'fog':       _fireFogEventCue(cue); break;
    case 'bg':        _fireBgEventCue(cue); break;
    case 'effect':    _fireEffectEventCue(cue); break;
    case 'animation': _fireAnimationEventCue(cue); break;
    case 'movie':     _fireMovieVisibilityEventCue(cue); break;
    case 'turn':      _fireTurnEventCue(cue); break;
    case 'path':      _firePathEventCue(cue); break;
    case 'gesture':   _fireGestureEventCue(cue); break;
    case 'face':      _faceCueWithRest(cue); break;
    case 'behavior':  _fireBehaviorEventCue(cue); break;
    case 'audio':     if (_muted) { _silenced++; break; } _fireAudioEventCue(cue); break;      // silent preview: the cue counts as fired, nothing plays
    case 'midi':      if (_muted) { _silenced++; break; } _fireMidiEventCue(cue); break;
    default: console.warn('[CueRuntime] no preview for track "' + cue.track + '"');
  }
}
// A new canvas is a new scene: every table that holds ITS nodes is dropped (stale node references would silently do nothing), and anything
// still pending from the old scene is superseded.  The clip lists fetched from the server describe the agent, not the scene, so they stay.
function setCanvas(el) {
  _stopFaceLoops(true); _applyFaceRest(); _pbCbGeneration++;        // (a face still posed on the old scene goes back to its resting expression)
  canvas = el || null; _gainWas = {}; _behaviorTimerMap = {}; _agentCurrentClip = {}; _agentLastLoopClip = {};
  _facialDisplacerCache = {}; _faceCueActive = {}; _faceCueLoop = {}; _faceCueWarned = {}; _facialDisplacerWarned = {}; _faceRest = {}; _faceRestLoops = {};
}
function setApiBase(base) { API = base === undefined || base === null ? API : String(base); }   // '' = the page's own server
// ---- the resting expression ----
// The Loader's face cue fades its AUs back to ZERO when it ends; in the Loader the agent's own affect-driven face (the hot-house EBPS driver) then takes over again on its next tick,
// so her resting expression returns.  The editor has no such driver, so without this a cue would leave her face at zero (Anna's resting smile, AU12 = 0.44, was lost).
// Stand-in: the resting weights the scene itself carries are captured the first time an agent's face is used (before any cue has moved it) and the face is eased back to them
// when a cue is over.  (The Loader's real resting face follows live affect and can differ from this fixed pose.)
function _captureFaceRest(safe) {
  if (_faceRest[safe]) return;
  var d = _getFacialDisplacers(safe); if (!d) return;
  var r = {}; Object.keys(d).forEach(function (k) { var w = d[k].weight; r[k] = (typeof w === 'number') ? w : 0; }); _faceRest[safe] = r;
}
function _applyFaceRest() {          // instantly: every agent whose face is not owned by a cue goes to its resting expression
  Object.keys(_faceRest).forEach(function (safe) {
    var d = _facialDisplacerCache[safe]; if (!d || _faceCueActive[safe]) return;
    Object.keys(_faceRest[safe]).forEach(function (k) { if (d[k]) { try { d[k].weight = _faceRest[safe][k]; } catch (e) {} } });
  });
}
function _easeFaceToRest(safe) {     // 0.3 s ease from wherever the face is (the cue's fade-out ends at zero) back to its resting expression
  var d = _facialDisplacerCache[safe], rest = _faceRest[safe]; if (!d || !rest) return;
  var keys = Object.keys(rest).filter(function (k) { return d[k]; }), from = {}, gen = _pbCbGeneration, ms = 300;
  keys.forEach(function (k) { from[k] = (typeof d[k].weight === 'number') ? d[k].weight : 0; });
  var t0 = (window.performance && performance.now) ? performance.now() : Date.now(), loop = { cancel: function () { loop.done = true; } };
  _faceRestLoops[safe] = loop;
  (function step() {
    if (loop.done || gen !== _pbCbGeneration || _faceCueActive[safe]) { loop.done = true; if (_faceRestLoops[safe] === loop) delete _faceRestLoops[safe]; return; }   // a Stop, a newer run or a newer cue: leave the face alone
    var e = ((window.performance && performance.now) ? performance.now() : Date.now()) - t0, f = e >= ms ? 1 : _faceEase(e / ms);
    keys.forEach(function (k) { try { d[k].weight = from[k] + (rest[k] - from[k]) * f; } catch (x) {} });
    if (e < ms) (window.requestAnimationFrame || function (fn) { return setTimeout(fn, 33); })(step); else if (_faceRestLoops[safe] === loop) delete _faceRestLoops[safe];
  })();
}
function _faceCueWithRest(cue) {
  var safe = String(cue.target || '').replace(/[^A-Za-z0-9_]/g, '_'), gen = _pbCbGeneration, tries = 0;
  try { _captureFaceRest(safe); } catch (e) {}
  if (_faceRestLoops[safe]) { _faceRestLoops[safe].cancel(); delete _faceRestLoops[safe]; }
  _fireFaceEventCue(cue);
  // when the Loader's loop for this cue is over, ease back to rest, unless a newer cue now owns the face (it will do the same when it ends)
  _runTimers.push(setTimeout(function check() {
    if (gen !== _pbCbGeneration || !_running) return;
    if (_faceCueActive[safe]) { if (++tries < 60) _runTimers.push(setTimeout(check, 50)); return; }
    _easeFaceToRest(safe);
  }, Math.max(0.05, cue.dur || 2) * 1000 + 60));
}
function _stopFaceLoops(toNeutral) { Object.keys(_faceCueLoop).forEach(function (k) { try { _faceCueLoop[k].stop(!!toNeutral); } catch (e) {} }); }

// ---- the agents the timeline touches: their clip lists and behavior timers, which the Loader builds when it starts Play ----
// The clip list comes from the Loader's own _ensureBehaviorClipsLoaded (GET /cultivars/<agent>).  The timer table is MIRRORED, not copied, from
// "tryMapTimers" inside the Loader's pbActivateX3DTimers: that function is the Loader's whole playback engine (72 functions, 3,400 lines), so only this
// loop is reproduced: look up each behavior timer the agent's avatar file exports as the imported node <Base>_<Agent> (retrying while its Inline loads,
// 20 x 250 ms as the Loader does), then switch the idle DefaultTimer on and note it as the current and last-looping clip.
function _mapBehaviorTimers(sName, gen) {
  var attempts = 0, MAX_ATTEMPTS = 20, RETRY_MS = 250, map = {};
  function tryMap() {
    if (_pbCbGeneration !== gen) return;                       // a newer run, a Stop, or a new scene: abandon
    attempts++;
    try {
      var sc = _scene(); if (!sc) { if (attempts < MAX_ATTEMPTS) setTimeout(tryMap, RETRY_MS); return; }
      var inl = null; try { inl = sc.getNamedNode('HAnim_' + sName); } catch (e2) {}
      if (!inl) { console.log('[CueRuntime] no HAnim_' + sName + ' in the scene: a static avatar, nothing to animate'); return; }
      var bases = BEHAVIOR_TIMER_BASES.slice(), cfg = _agentBehaviorClips[sName];
      if (cfg && cfg.clips) cfg.clips.forEach(function (clip) { var td = clip.timerDEF || (clip.name + 'Timer'); if (bases.indexOf(td) === -1) bases.push(td); });
      bases.forEach(function (base) { if (map[base]) return; try { var n = sc.getImportedNode(base + '_' + sName); if (n) map[base] = n; } catch (e3) {} });
      var found = Object.keys(map), missing = bases.filter(function (b) { return !map[b]; });
      if (found.length > 0 && (missing.length === 0 || attempts >= MAX_ATTEMPTS)) {
        _behaviorTimerMap[sName] = map;
        if (missing.length) console.warn('[CueRuntime] behavior timers PARTIALLY mapped for ' + sName + ' (gave up retrying); missing: ' + missing.join(', '));
        var def = map['DefaultTimer'];
        if (def) { try { def.enabled = true; _agentCurrentClip[sName] = 'Default'; _agentLastLoopClip[sName] = 'Default'; } catch (e4) {} }
      } else if (attempts < MAX_ATTEMPTS) { setTimeout(tryMap, RETRY_MS); }
      else { console.warn('[CueRuntime] no behavior timers found for ' + sName + ' after ' + MAX_ATTEMPTS + ' attempts: its gesture cues will not play'); }
    } catch (e) { if (attempts < MAX_ATTEMPTS) setTimeout(tryMap, RETRY_MS); }
  }
  tryMap();
}
function agentsInCues() {
  var seen = {}, out = [];
  _eventCues.forEach(function (c) { if (c.target && /^(gesture|behavior|face|path|turn)$/.test(c.track) && !seen[c.target]) { seen[c.target] = true; out.push(c.target); } });
  return out;
}
function _prepareAgents() {
  var gen = _pbCbGeneration;
  agentsInCues().forEach(function (name) {
    var safe = String(name).replace(/[^A-Za-z0-9_]/g, '_');
    try { _ensureBehaviorClipsLoaded(name); } catch (e) {}
    _mapBehaviorTimers(safe, gen);
  });
}
function _scene() { try { return canvas && canvas.browser ? canvas.browser.currentScene : null; } catch (e) { return null; } }

// The names of every time-dependent node the scene file declares: TimeSensors (motion), AudioClips and MovieTextures (sound).
// Read from the file itself, because the SAI cannot be relied on to enumerate nodes (the Loader's own Stop says so).
// Stop switches them all off, so motion freezes where it is and nothing keeps sounding.
function timerNamesFromX3D(text) {
  var names = [], seen = {}, re = /<(?:TimeSensor|AudioClip|MovieTexture)\b[^>]*?\bDEF\s*=\s*(?:"([^"]+)"|'([^']+)')/g, m;
  while ((m = re.exec(String(text || '')))) { var n = m[1] || m[2]; if (n && !seen[n]) { seen[n] = true; names.push(n); } }
  return names;
}
function setTimerNames(list) { _timerNames = (list || []).slice(); }
// The sound sources the scene file declares (AudioClip, MovieTexture).  Both have a 'gain' field (X_ITE: "the amount of linear
// amplification to apply to the output of the node"); the movie the Loader starts on Play is imported, so it is named separately.
function soundNamesFromX3D(text) {
  var names = [], seen = {}, re = /<(?:AudioClip|MovieTexture)\b[^>]*?\bDEF\s*=\s*(?:"([^"]+)"|'([^']+)')/g, m;
  while ((m = re.exec(String(text || '')))) { var n = m[1] || m[2]; if (n && !seen[n]) { seen[n] = true; names.push(n); } }
  return names;
}
function setSoundNames(list) { _soundNames = (list || []).slice(); }
// Nodes the Loader's own Play starts (the scene's movie, imported, and its Music and Bed clips).  Stop and the sound switch always cover them;
// a scene without one simply has nothing to do.
var ALWAYS_STOP = ['TheSceneMovie', 'Clip_Music', 'Clip_Bed'];
// A node can come from the scene itself or arrive through an IMPORT (an Inline'd asset: the movie, avatar timers); the Loader looks in both places.
// Only time-dependent nodes (TimeSensor, AudioClip, MovieTexture) have enabled / stopTime.  A movie cue's target is an imported Shape (MovieShape): X_ITE
// rejects those fields on a Shape and logs an error each time, so Stop must leave such a node alone.
function _isTimeDependent(node) {
  try { if (typeof node.getTypeName === 'function') return /^(TimeSensor|AudioClip|MovieTexture)$/.test(String(node.getTypeName())); } catch (e) {}
  return true;       // a node with no type name (a test stand-in): assume it is one
}
function _findNode(sc, name) {
  try { var n = sc.getNamedNode(name); if (n) return n; } catch (e) {}
  try { var i = sc.getImportedNode(name); if (i) return i; } catch (e2) {}
  return null;
}
// Fallback when the scene file could not be read: the timers the cues themselves name.
function _timersFromCues() {
  var names = [], add = function (n) { if (n && names.indexOf(n) < 0) names.push(n); };
  _eventCues.forEach(function (c) {
    add(c.triggerRef); var m = /^PathTimer_(.+)$/.exec(c.triggerRef || ''); if (m) add('PathEaseTimer_' + m[1]);
    if (c.track === 'camera') { add('CAM_Timer'); add('CAM_FlyTimer'); }
  });
  return names;
}

// Silence (or restore) every sound source in the scene by its gain, remembering each one's original gain so unmuting puts it back exactly.
function applyGain() {
  var sc = _scene(), n = 0; if (!sc) return 0;
  var names = []; _soundNames.concat(ALWAYS_STOP).forEach(function (x) { if (x && names.indexOf(x) < 0) names.push(x); });
  names.forEach(function (name) {
    var node = _findNode(sc, name); if (!node) return;
    try {
      if (_gainWas[name] === undefined) { var g = node.gain; if (typeof g !== 'number') return; _gainWas[name] = g; }
      node.gain = _muted ? 0 : _gainWas[name]; n++;
    } catch (e) {}
  });
  return n;
}
// setMuted(true): audio and MIDI cues stop playing (anything sounding is stopped now) and movie/clip gains go to 0.  setMuted(false): back again.
function setMuted(m) {
  _muted = !!m;
  if (_muted) { try { _stopAudioCues(); } catch (e) {} try { _stopMidiCues(); } catch (e) {} }
  applyGain();
  return _muted;
}
// Has the imported movie (a large Inline) finished loading yet?  The Loader's own Play retries for exactly this reason.
function movieFound() { var sc = _scene(); return !!(sc && _findNode(sc, 'TheSceneMovie')); }
function describe() {
  var by = {}, skipped = {}, runnable = 0, end = 0;
  _eventCues.forEach(function (c) {
    by[c.track] = (by[c.track] || 0) + 1; end = Math.max(end, (parseFloat(c.t0) || 0) + (parseFloat(c.duration) || 0));
    if (RUNNABLE[c.track]) runnable++; else skipped[c.track] = (skipped[c.track] || 0) + 1;
  });
  var notes = Object.keys(skipped).map(function (t) { return skipped[t] + ' ' + t + ' cue' + (skipped[t] > 1 ? 's' : '') + ' (' + (NOT_PREVIEWED[t] || 'not previewed here') + ') play in the Loader'; });
  return { total: _eventCues.length, runnable: runnable, byTrack: by, skipped: skipped, notes: notes, endAt: end,
           audioSources: Object.keys(_audioSources), midiSources: Object.keys(_midiSources) };
}
function load(xmlText) {
  var doc = new DOMParser().parseFromString(String(xmlText || ''), 'text/xml');
  if (doc.querySelector('parsererror')) throw new Error('the scene XML could not be parsed');
  _parseEventCues(doc);                       // also prepares the scene's MIDI sources
  return describe();
}
function start(hooks) {
  // Starting a run only cancels what is pending.  It must NOT freeze the scene (stop() without noFreeze disables every timer, clip and
  // movie): an Animation cue sets only a node's start time and never enables it, so a node disabled here would never play.
  // (stop() also supersedes anything pending from an earlier run: gesture retries, face loops, timer lookups)
  stop({ keepRan: true, noFreeze: true }); _hooks = hooks || {}; _running = true; _hasRun = true; _fired = 0; _failed = []; _silenced = 0; _runStart = performance.now(); _endAt = 0;
  _applyFaceRest(); _prepareAgents();
  var scheduled = 0, skippedN = 0;
  _eventCues.forEach(function (cue) {
    var t = Math.max(0, parseFloat(cue.t0) || 0); _endAt = Math.max(_endAt, t + (parseFloat(cue.duration) || 0));
    if (!RUNNABLE[cue.track]) { skippedN++; return; }
    scheduled++;
    _runTimers.push(setTimeout(function () {
      try { _dispatch(cue); _fired++; try { applyGain(); } catch (eg) {} if (_hooks.onFire) _hooks.onFire(cue); }   // (re-apply the sound switch: an Inline'd movie may only just have loaded)
      catch (e) { _failed.push({ cue: cue, error: e }); console.warn('[CueRuntime] cue failed:', cue.track, cue.label || cue.target || '', e && e.message); if (_hooks.onError) _hooks.onError(cue, e); }
    }, t * 1000));
  });
  // What the Loader's Play does before any cue: start the scene's Music and Bed clips and the movie.  (Without this the movie only plays
  // if a cue happens to aim at it, and the Loader's Play never relies on that.)  The sound switch is applied right away and again every
  // 100 ms for the first 6 s, so a movie whose big Inline finishes loading late is silenced (or not) before it is heard.
  try { spStartSceneTracks(); } catch (e) { console.warn('[CueRuntime] scene tracks:', e && e.message); }
  try { applyGain(); } catch (e) {}
  for (var g = 1; g <= 60; g++) _runTimers.push(setTimeout(function () { try { applyGain(); } catch (e) {} }, g * 100));
  if (_hooks.onEnd) _runTimers.push(setTimeout(function () { _hooks.onEnd(); }, (_endAt + 0.25) * 1000));
  return { scheduled: scheduled, skipped: skippedN, endAt: _endAt };
}
// Stop: cancel what has not fired yet, silence audio and MIDI, and freeze every timer in the scene where it is.
function stop(opts) {
  _runTimers.forEach(function (t) { clearTimeout(t); }); _runTimers = [];
  var was = _running; _running = false; _runStart = null;
  _stopFaceLoops(!(opts && opts.noFreeze) ? false : true);   // Stop: a face mid-expression stays where it is; a restart or reload: back to neutral
  _pbCbGeneration++;                                        // supersede every pending gesture retry, one-shot return, timer-map lookup and ease-back
  _faceRestLoops = {}; if (opts && opts.noFreeze) _applyFaceRest();      // a restart or reload puts the face back to its resting expression (Stop leaves it posed)
  try { _stopAudioCues(); } catch (e) {}
  try { _stopMidiCues(); } catch (e) {}
  Object.keys(_lerpActive).forEach(function (k) { try { clearInterval(_lerpActive[k].timer); } catch (e) {} });
  _lerpActive = {}; _x3dTimerActive = {};
  var sc = _scene(), frozen = 0;
  if (sc && !(opts && opts.noFreeze)) {
    var names = [], seen = {}; _timerNames.concat(_timersFromCues(), ALWAYS_STOP).forEach(function (n) { if (n && !seen[n]) { seen[n] = true; names.push(n); } });
    var now = 0; try { now = canvas.browser.currentTime > 0 ? canvas.browser.currentTime : performance.now() / 1000; } catch (e) { now = performance.now() / 1000; }
    names.forEach(function (n) {
      var node = _findNode(sc, n); if (!node || !_isTimeDependent(node)) return;
      try { node.enabled = false; } catch (e) {}      // a TimeSensor or AudioClip: off
      try { node.stopTime = now; } catch (e) {}       // a MovieTexture (no enabled field) or a running clip: stopped now
      frozen++;
    });
    Object.keys(_behaviorTimerMap).forEach(function (agent) {      // the agent's body-animation timers (idle, walk, gesture clips)
      var m = _behaviorTimerMap[agent]; Object.keys(m).forEach(function (base) { try { m[base].enabled = false; } catch (e) {} try { m[base].stopTime = now; } catch (e2) {} frozen++; });
    });
  }
  return { wasRunning: was, frozen: frozen };
}
function elapsed() { return _running && _runStart !== null ? (performance.now() - _runStart) / 1000 : null; }
function reset() { stop({ noFreeze: true }); _hasRun = false; _fired = 0; _failed = []; }
function dispose() {   // release the MIDI players (do NOT call _midiPrepareAll here: that would fetch the files again)
  stop({ noFreeze: true });
  Object.keys(_midiRecs).forEach(function (k) { try { _midiRecs[k].player.dispose(); } catch (e) {} }); _midiRecs = {};
}

var api = { setApiBase: setApiBase, agents: agentsInCues, movieFound: movieFound, setMuted: setMuted, isMuted: function () { return _muted; }, applyGain: applyGain, soundNamesFromX3D: soundNamesFromX3D, setSoundNames: setSoundNames, silenced: function () { return _silenced; }, setCanvas: setCanvas, load: load, start: start, stop: stop, reset: reset, dispose: dispose, elapsed: elapsed,
            isRunning: function () { return _running; }, hasRun: function () { return _hasRun; }, cues: function () { return _eventCues.slice(); },
            describe: describe, fired: function () { return _fired; }, failures: function () { return _failed.slice(); }, endAt: function () { return _endAt; },
            timerNamesFromX3D: timerNamesFromX3D, setTimerNames: setTimerNames, runnableTracks: function () { return Object.keys(RUNNABLE); },
            _internals: { faceRest: function () { return _faceRest; }, faceActive: function () { return _faceCueActive; }, faceCache: function () { return _facialDisplacerCache; }, behaviorTimerMap: function () { return _behaviorTimerMap; }, clips: function () { return _agentBehaviorClips; }, currentClip: function () { return _agentCurrentClip; }, dispatch: _dispatch, eventCues: function () { return _eventCues; }, audioSources: function () { return _audioSources; }, midiRecs: function () { return _midiRecs; } } };
if (typeof module !== 'undefined' && module.exports) module.exports = api; else root.MccfCueRuntime = api;
})(typeof window !== 'undefined' ? window : this);
