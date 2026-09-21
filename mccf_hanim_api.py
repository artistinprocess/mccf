"""
mccf_hanim_api.py — HAnim Editor endpoints.

Extracted from mccf_api.py (Day 63) — this was the single largest
concentration of one domain living directly in the main API file
(~3,300 lines, over half the original file), and the one that never
got the same Blueprint-module treatment already applied to voice,
zone, ambient, drift, chorus, playback, energy, and neoriemannian.

Scope: avatar upload/listing/preview, HAnim skeleton export, joint
listing/wiring/normalization, facial morph/action-unit injection, and
Mixamo ingestion. Every route in this file is self-contained — traced
directly against the source (Day 63) and confirmed to have zero
dependency on the live app-level `field`/`scene`/`drift_manager`/
`playback_manager`/`chorus_manager` singletons defined in mccf_api.py,
and zero dependency on the `mccf_core` imports (Agent, ChannelVector,
CoherenceField, Librarian, Gardener, CHANNEL_NAMES) used elsewhere in
that file. It only needs `os`, Flask's `request`/`jsonify`, and its
own already-local imports (base64, shutil, xml.etree.ElementTree,
re — most of those imported function-locally in the original and left
that way here, unchanged).

Registration, matching the existing V3 module pattern
(register_attractor_api, register_scene_api, register_cultivar_api,
register_generate_api, register_playback_api, register_chorus_api):

    from mccf_hanim_api import register_hanim_api
    register_hanim_api(app)
"""

import os
import re as _re
import time as _time_hanim
import math as _math
from flask import Blueprint, request, jsonify
import base64  as _b64
import shutil  as _shutil_hanim
import xml.etree.ElementTree as _ET_hanim

hanim_bp = Blueprint('hanim', __name__)


@hanim_bp.route('/avatar/upload', methods=['POST'])
def upload_avatar():
    """
    POST /avatar/upload
    Accepts an H-Anim X3D file, strips scene-control nodes (HUD Transform,
    ProximitySensor HudProx, TouchSensors, named animation TimeSensors,
    and their ROUTEs), saves to static/avatars/{slug}_hanim.x3d.

    Uses proper XML parse → node removal → reserialise to avoid the
    malformed-output problems of line-based heuristics.

    Returns: { status, path, loa, clips, joint_count }
    """
    import re as _re
    import xml.etree.ElementTree as ET

    avatar_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'avatars')
    os.makedirs(avatar_dir, exist_ok=True)

    raw_name = request.headers.get('X-Avatar-Name', '').strip() or 'avatar'
    slug     = _re.sub(r'[^A-Za-z0-9_.\-]', '_', raw_name)
    filename = f'{slug}.x3d'
    filepath    = os.path.join(avatar_dir, filename)

    content = request.get_data(as_text=True)
    if not content:
        return jsonify({'status': 'error', 'error': 'no content'}), 400

    # ── Regex-based stripping ───────────────────────────────────────────
    # ET.fromstring/tostring destroys large attribute data (coordIndex,
    # displacements on HAnimDisplacer) and CDATA sections. Use regex instead
    # to preserve all attribute data exactly as authored.

    import re as _re

    # ── Gather metadata via ET (read-only, no reserialise) ───────────────
    import xml.etree.ElementTree as _ET
    try:
        _body_lines = []
        for _line in content.splitlines(keepends=True):
            if not _line.strip().startswith('<?xml') and \
               not _line.strip().startswith('<!DOCTYPE'):
                _body_lines.append(_line)
        _root = _ET.fromstring(''.join(_body_lines))
    except _ET.ParseError as e:
        return jsonify({'status': 'error', 'error': f'XML parse failed: {e}'}), 400

    hanim_el    = _root.find('.//{*}HAnimHumanoid')
    loa         = int(hanim_el.get('loa', 4)) if hanim_el is not None else 4
    joint_count = len(_root.findall('.//{*}HAnimJoint[@name]'))
    BEHAVIOR_TIMER_DEFS = {
        'DefaultTimer','PitchTimer','YawTimer','RollTimer',
        'WalkTimer','RunTimer','JumpTimer','KickTimer'
    }
    clips = [
        el.get('DEF', '').replace('Timer', '')
        for el in _root.findall('.//{*}TimeSensor')
        if el.get('DEF') and el.get('DEF') in BEHAVIOR_TIMER_DEFS
    ]

    # ── Regex strip on raw content ───────────────────────────────────────
    stripped = content

    # 1. Remove DOCTYPE
    stripped = _re.sub(r'<!DOCTYPE[^>]*>\s*', '', stripped)

    # 2. Remove HUD structure nodes (multi-line)
    #    HudXform: the Transform wrapping the entire HUD
    #    HudProx: ProximitySensor
    stripped = _re.sub(
        r'<Transform\s[^>]*DEF=["\']HudXform["\'][^>]*>.*?</Transform>\s*',
        '', stripped, flags=_re.DOTALL)
    stripped = _re.sub(
        r'<ProximitySensor\s[^>]*DEF=["\']HudProx["\'][^>]*/>\s*',
        '', stripped)
    stripped = _re.sub(
        r'<ProximitySensor\s[^>]*DEF=["\']HudProx["\'][^>]*>.*?</ProximitySensor>\s*',
        '', stripped, flags=_re.DOTALL)

    # 3. Remove StopTimer TimeSensor
    stripped = _re.sub(
        r'<TimeSensor\s[^>]*DEF=["\']StopTimer["\'][^>]*/>\s*',
        '', stripped)

    # 4. Remove TouchSensors
    stripped = _re.sub(
        r'<TouchSensor\s[^>]*/>\s*', '', stripped)
    stripped = _re.sub(
        r'<TouchSensor\s[^>]*>.*?</TouchSensor>\s*', '', stripped, flags=_re.DOTALL)

    # 5. Remove ProtoDeclare/ProtoInstance (HUD menu system)
    stripped = _re.sub(
        r'<ProtoDeclare\s[^>]*>.*?</ProtoDeclare>\s*',
        '', stripped, flags=_re.DOTALL)
    stripped = _re.sub(
        r'<ProtoInstance\s[^>]*>.*?</ProtoInstance>\s*',
        '', stripped, flags=_re.DOTALL)
    stripped = _re.sub(
        r'<ProtoInstance\s[^>]*/>\s*', '', stripped)

    # 6. Remove ROUTEs referencing HUD/Touch nodes
    HUD_ROUTE_NODES = {
        'HudProx','HudXform','StopTimer',
        'Stand_Touch','Pitch_Touch','Yaw_Touch','Roll_Touch',
        'Walk_Touch','Run_Touch','Jump_Touch','Kick_Touch','Stop_Touch'
    }
    def strip_hud_routes(text):
        def should_strip(m):
            attrs = m.group(0)
            fn = _re.search(r'fromNode=["\']([^"\']+)["\']', attrs)
            tn = _re.search(r'toNode=["\']([^"\']+)["\']', attrs)
            fn = fn.group(1) if fn else ''
            tn = tn.group(1) if tn else ''
            return fn in HUD_ROUTE_NODES or tn in HUD_ROUTE_NODES
        result = []
        for line in text.split('\n'):
            if '<ROUTE ' in line and should_strip(_re.search(r'<ROUTE[^>]*/>', line) or
                                                  type('M', (), {'group': lambda s,n: ''})()) :
                m = _re.search(r'<ROUTE[^>]*/>', line)
                if m and should_strip(m):
                    continue
            result.append(line)
        return '\n'.join(result)
    stripped = strip_hud_routes(stripped)

    # 7. Disable behavior TimeSensors (set enabled="false")
    for _tdef in BEHAVIOR_TIMER_DEFS:
        stripped = _re.sub(
            r'(<TimeSensor\s[^>]*DEF=["\']' + _tdef + r'["\'][^>]*)\benabled=["\'][^"\']*["\']',
            r'\1enabled="false"', stripped)
        # If no enabled attr, add it
        def _add_enabled(m, tdef=_tdef):
            tag = m.group(0)
            if 'enabled=' not in tag:
                tag = tag.replace('/>', ' enabled="false"/>')
            return tag
        stripped = _re.sub(
            r'<TimeSensor\s[^>]*DEF=["\']' + _tdef + r'["\'][^>]*/>',
            _add_enabled, stripped)

    # 8. Ensure Scripting component declared
    if '<component name="Scripting"' not in stripped:
        stripped = stripped.replace(
            '<component name="HAnim"',
            '<component name="Scripting" level="1" />\n    <component name="HAnim"', 1)

    # 9. Remove any leftover FaceController (migration cleanup for avatars
    #    uploaded under the earlier AnimationAdapter-based pipeline — that
    #    Script and the CoordinateInterpolator/set_fraction indirection it
    #    drove are superseded now that HAnimDisplacer.weight is confirmed
    #    to be settable directly, per spec, on a single skinned mesh. See
    #    SEED_facial_displacer_breakthrough.md. No replacement is injected:
    #    EBPS connectors and the editor's AU sliders both drive
    #    HAnimDisplacer nodes directly by name (convention:
    #    '<AUName>_displacer', or '<AUName>_l_displacer'/'_r_displacer' for
    #    laterally-split AUs) — there is no longer a central controller
    #    node for a fresh upload to carry.
    stripped = _re.sub(
        r'\s*<Script DEF=["\']FaceController["\'].*?</Script>',
        '', stripped, flags=_re.DOTALL)

    # Day 89: real, confirmed vulnerability found while investigating a
    # report of Anna.x3d ending up completely empty (0 bytes) after some
    # action in the H-Anim Editor. This was the only write anywhere in
    # this file that went straight to the real target path — every other
    # save operation here writes to a tmp file first, then renames
    # atomically, specifically so a mid-write failure can never leave the
    # real file truncated (open(path, 'w') empties it immediately, before
    # anything new is written). Matching that same safe pattern now.
    tmp_path = filepath + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(stripped)
    os.replace(tmp_path, filepath)

    return jsonify({
        'status':      'ok',
        'path':        f'avatars/{filename}',
        'filename':    filename,
        'loa':         loa,
        'joint_count': joint_count,
        'clips':       clips,
    })


@hanim_bp.route('/avatar/preview')
def avatar_preview():
    """
    GET /avatar/preview?src=avatars/foo_hanim.x3d
    Serves a minimal X_ITE HTML page that renders the H-Anim figure locally.

    Morph driver is avatar-agnostic and spec-compliant: it drives
    HAnimDisplacer.weight directly, by DEF name, and does no per-avatar
    discovery, probing, or displacement math of its own — that's the
    renderer's job once a node is a real HAnimDisplacer.

    Naming convention: 'setDisplacerWeight' messages carry an AU name
    (e.g. 'AU4_BrowLowerer'); the driver tries '<AUName>_displacer' and
    the laterally-split '<AUName>_l_displacer' / '<AUName>_r_displacer'
    variants via getNamedNode, and writes .weight on whichever exist.
    Avatars that don't have a given AU's displacer simply don't match
    anything — no error, no special-casing per avatar.

    Superseded (Sept 2026): the old avatar-specific *Coord_<region> /
    AnimationAdapter_<region> CoordinateInterpolator pipeline (per-region
    Coordinate nodes hand-written back with computed deltas, one JS mode
    for "segment" avatars and another for "global mesh" avatars). See
    SEED_facial_displacer_breakthrough.md for why that was unnecessary.
    """
    src = request.args.get('src', '').strip()
    if not src:
        return "Missing src parameter", 400
    # Normalise src to avatars/ subdir if caller passed a bare filename.
    # Accepts: 'cindy_hanim.x3d'         -> '/static/avatars/cindy_hanim.x3d'
    #          'avatars/cindy_hanim.x3d' -> '/static/avatars/cindy_hanim.x3d'
    #          '/static/avatars/...'     -> unchanged
    if src.startswith('/'):
        x3d_src = src
    elif src.startswith('avatars/') or src.startswith('static/'):
        x3d_src = f'/static/{src}'
    else:
        x3d_src = f'/static/avatars/{src}'

    html = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>H-Anim Preview</title>
  <style>
    * { margin:0; padding:0; box-sizing:border-box; }
    html, body { width:100%; height:100%; background:#0a0e18; overflow:hidden; color:#ccc; font-family:monospace; }
    x3d-canvas { width:100%; height:100%; display:block; }
    #err { display:none; padding:12px; font-size:12px; color:#f06060; }
    #morph-overlay {
      position:fixed; bottom:10px; right:10px; width:260px;
      background:rgba(10,12,22,0.92); border:1px solid #2a2a44;
      border-radius:4px; padding:10px 12px; font-size:12px;
      line-height:1.6; pointer-events:none; z-index:999; color:#8899bb;
    }
    #morph-overlay .mo-title {
      font-size:10px; letter-spacing:0.12em; text-transform:uppercase;
      color:#556; margin-bottom:5px; border-bottom:1px solid #1e1e30; padding-bottom:3px;
    }
    #morph-overlay .mo-coord        { color:#4a7; margin-bottom:2px; font-size:11px; }
    #morph-overlay .mo-coord.missing { color:#f64; }
    #morph-overlay .mo-au-active    { color:#8af; font-size:12px; }
    #morph-overlay .mo-au-zero      { color:#334; }
    #morph-overlay .mo-status       { color:#fa4; margin-top:4px; font-size:11px; }
  </style>
</head>
<body>
  <div id="err"></div>
  <x3d-canvas id="canvas" src="__X3D_SRC__"></x3d-canvas>
  <div id="morph-overlay">
    <div class="mo-title">displacer driver</div>
    <div id="mo-coords">waiting for scene...</div>
    <div id="mo-aus"></div>
    <div id="mo-status" class="mo-status"></div>
  </div>
  <script type="module">
    import X3D from 'https://cdn.jsdelivr.net/npm/x_ite@16.1.3/dist/x_ite.min.mjs';
    // Bumped from 11.6.0 → 16.1.3 to match mccf_x3d_loader.html's pin
    // (same verified-latest version, not the unconfirmed "16.3" from the
    // cycleComplete seed note). Kept in sync so this preview and the main
    // Loader show the same X_ITE build/loading screen rather than
    // silently drifting apart. This page is a simpler, read-only preview
    // (no timer-switching, no behavior-clip logic), so the four
    // documented 11.6-specific SAI quirks matter less here than in the
    // full loader — but worth a quick visual check after this change,
    // same discipline as any other version bump in this project.
    const canvas  = document.getElementById('canvas');

    let _browser = null, _scene = null;
    var _animTimersStopped = [];  // animation timer DEFs stopped by joint-drag — restart on play
    var _enabledTimers     = [];  // timer DEFs currently turned on via enableTimer — avatar-agnostic Stop

    // ── Displacer weight driver ───────────────────────────────────────────
    // Spec-compliant and avatar-agnostic: HAnimDisplacer carries its own
    // 'weight' SFFloat field, driven directly by DEF name. No discovery,
    // no rest-pose caching, no manual displacement math — the renderer
    // (X_ITE) applies the displacement itself once weight is set, exactly
    // as it would for any other native X3D node. See
    // SEED_facial_displacer_breakthrough.md for how this was confirmed.
    //
    // Naming convention: '<AUName>_displacer' for a single displacer, or
    // '<AUName>_l_displacer' / '<AUName>_r_displacer' for AUs split across
    // two HAnimJoints (most facial AUs are bilateral). All three name
    // variants are tried for every incoming AU; whichever exist on this
    // particular avatar get written, the rest are silently skipped. This
    // is what makes the driver avatar-agnostic: it carries no per-avatar
    // prefix, mesh name, or region list of any kind.
    var _auWeights = {};

    function _displacerCandidates(auName) {
      return [auName + '_displacer', auName + '_l_displacer', auName + '_r_displacer'];
    }

    function _setDisplacerWeight(auName, weight) {
      var written = 0;
      _displacerCandidates(auName).forEach(function(def) {
        try {
          var node = _scene.getNamedNode(def);
          if (!node) return;
          var wf = node.getField('weight');
          if (wf) { wf.setValue(weight); written++; }
        } catch(e) { /* node doesn't exist on this avatar — skip */ }
      });
      return written;
    }

    function _updateOverlayAus() {
      var el = document.getElementById('mo-aus');
      var active = Object.entries(_auWeights)
        .filter(function(kv) { return kv[1] > 0.01; })
        .sort(function(a, b) { return b[1] - a[1]; });
      if (!active.length) {
        el.innerHTML = '<div class="mo-au-zero">— no active AUs —</div>';
        return;
      }
      el.innerHTML = active.map(function(kv) {
        var b = Math.round(kv[1] * 10);
        return '<div class="mo-au-active">' + kv[0] +
               ' ' + '█'.repeat(b) + '░'.repeat(10-b) +
               ' ' + kv[1].toFixed(2) + '</div>';
      }).join('');
    }

    // ── Scene load ────────────────────────────────────────────────────────
    canvas.addEventListener('load', function() {
      document.getElementById('err').style.display = 'none';
      try {
        _browser = X3D.getBrowser(canvas);
        _scene   = _browser.currentScene;
        console.log('SAI ready — scene nodes:', _scene.rootNodes.length);
        document.getElementById('mo-coords').textContent = 'displacer driver ready';
      } catch(e) {
        console.warn('SAI init failed:', e.message);
        document.getElementById('mo-status').textContent = 'SAI init failed: ' + e.message;
      }
    });

    canvas.addEventListener('error', function(e) {
      var el = document.getElementById('err');
      el.style.display = 'block';
      el.textContent = 'X_ITE load error: ' + (e.detail || e.message || JSON.stringify(e));
    });

    // ── postMessage interface (unchanged) ─────────────────────────────────
    window.addEventListener('message', function(evt) {
      if (!_browser || !_scene) return;
      var msg = evt.data; if (!msg || !msg.type) return;
      try {
        if (msg.type === 'setJointRotation') {
          var r = msg.rotation || [0,0,1,0];
          var sfr = new X3D.SFRotation(r[0], r[1], r[2], r[3]);

          // Sanitise joint DEF for WireInterp lookup — DEF names cannot contain
          // colons (Mixamo: 'mixamorig:Hips' -> 'mixamorig_Hips') or hyphens.
          var safeDef = msg.joint.replace(/:/g, '_').replace(/-/g, '_');

          // Strategy 1: drive through WireInterp_<jointDEF> if it exists.
          var interpDef = 'WireInterp_' + safeDef;
          var interp = null;
          try { interp = _scene.getNamedNode(interpDef); } catch(e) {}
          if (interp) {
            // Stop animation timers only if needed — they fight WireInterp writes.
            // Uses _enabledTimers (whatever enableTimer actually turned on)
            // rather than a hardcoded name list — same fix, same reasoning
            // as disableAllTimers below; this was an independent copy of
            // the identical bug, not touched by that earlier fix.
            _enabledTimers.forEach(function(def) {
              try {
                var t = _scene.getNamedNode(def);
                if (t && t.enabled) {
                  t.enabled = false;
                  if (_animTimersStopped.indexOf(def) === -1) _animTimersStopped.push(def);
                }
              } catch(e) {}
            });
            var kv = new X3D.MFRotation(sfr, sfr);
            interp.keyValue = kv;
            var timerDef = 'WireTimer_' + safeDef;
            var wireTimer = null;
            try { wireTimer = _scene.getNamedNode(timerDef); } catch(e) {}
            if (wireTimer) {
              wireTimer.enabled = false;
              try {
                var fracField = interp.getField('set_fraction');
                if (fracField) fracField.setValue(0);
              } catch(e) {}
            }
          } else {
            // Strategy 2: direct rotation write
            var node = _scene.getNamedNode(msg.joint);
            if (!node) { console.warn('SAI: joint not found:', msg.joint); return; }
            node.rotation = sfr;
          }

        } else if (msg.type === 'getJointRotation') {
          // Round-trip: read live rotation from scene, post back to editor.
          var jointNode = null;
          try { jointNode = _scene.getNamedNode(msg.joint); } catch(e) {}
          var rot = [0, 0, 1, 0];
          if (jointNode) {
            try {
              var r = jointNode.rotation;
              rot = [r.x, r.y, r.z, r.angle];
            } catch(e) {}
          }
          evt.source.postMessage({
            type:     'jointRotation',
            joint:    msg.joint,
            rotation: rot
          }, '*');

        } else if (msg.type === 'setDisplacerWeight') {
          var auName = msg.au;
          var weight = typeof msg.weight === 'number' ? msg.weight : 0;
          _auWeights[auName] = weight;
          var written = _setDisplacerWeight(auName, weight);
          _updateOverlayAus();
          document.getElementById('mo-status').textContent =
            written + ' displacer(s) updated';
          console.log('displacer:', auName, weight.toFixed(3), '->', written, 'node(s)');

        } else if (msg.type === 'enableTimer') {
          // Start animation — set enabled=true only. loop/cycleInterval are
          // already set correctly in the X3D file. No startTime manipulation
          // needed; X_ITE restarts correctly from enabled=false -> enabled=true.
          _animTimersStopped = [];
          try {
            var timer = _scene.getNamedNode(msg.timerDEF);
            if (timer) {
              timer.enabled = true;
              // Track it so disableAllTimers can turn off exactly what's
              // running, regardless of what this avatar calls its timers —
              // no hardcoded name list needed for any naming convention.
              if (_enabledTimers.indexOf(msg.timerDEF) === -1) {
                _enabledTimers.push(msg.timerDEF);
              }
            } else {
              console.warn('enableTimer: node not found:', msg.timerDEF);
            }
          } catch(e) { console.warn('enableTimer error:', e.message); }

        } else if (msg.type === 'disableAllTimers') {
          // Disable whatever enableTimer actually turned on. Avatar-agnostic
          // by construction: no assumption about timer DEF naming (Tripo's
          // Timer1..Timer14, or DefaultTimer/WalkTimer/etc. on other rigs) —
          // we only ever disable timers this driver itself enabled.
          _animTimersStopped = [];
          _enabledTimers.forEach(function(def) {
            try { var t = _scene.getNamedNode(def); if (t) t.enabled = false; } catch(e) {}
          });
          _enabledTimers = [];

        }
        // 'getCoordPositions' removed: it existed only to snapshot rest/posed
        // vertex positions for the old capture-rest/capture-morph pipeline.
        // Real per-vertex AU deltas now come straight from Blender's shape
        // keys via glTF export (see anna_au_deltas.json) — nothing in this
        // preview needs to read coordinates back out of the live scene.
      } catch(e) { console.warn('SAI write error:', e.message, msg); }
    });
  </script>
</body>
</html>"""
    html = html.replace('__X3D_SRC__', x3d_src)

    return html, 200, {'Content-Type': 'text/html'}


@hanim_bp.route('/avatar/list', methods=['GET'])
def list_avatars():
    """List stripped H-Anim files in static/avatars/."""
    avatar_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'avatars')
    if not os.path.isdir(avatar_dir):
        return jsonify({'avatars': []})
    files = sorted(
        [f for f in os.listdir(avatar_dir) if f.endswith('.x3d')],
        key=lambda f: os.path.getmtime(os.path.join(avatar_dir, f)),
        reverse=True
    )
    return jsonify({'avatars': files})


# ---------------------------------------------------------------------------
# HAnim Editor Export Endpoints
# Day 27 — 2026-05-26
# Spec: MCCF_HAnim_Editor_Spec.md
#
# POST /hanim/skin_upload  — decode base64 data URL → save PNG to static/avatars/
# POST /hanim/export       — atomic dual-write: HAnim X3D + cultivar XML
#
# Phase 1 scope (what runs today):
#   skin_upload : decode → write → return relative URL
#   export      : update ImageTexture url (skin swap)
#                 update <HAnimFigure src>, <Receptivity>, <Behaviors> in cultivar XML
#                 scaffold TimeSensor/OrientationInterpolator/ROUTE for clips[] array
#                 (clips[] is empty in Phase 1; full in Phase 2)
#
# Architecture invariants enforced here (never relax):
#   - All exported TimeSensors: enabled="false"   (loader activates via SAI)
#   - TimeSensor DEF naming: {ClipName}Timer
#   - ROUTEs always last in Scene element
#   - Both files backed up (.bak) before any write
#   - os.replace() rename — neither file updated unless both writes succeed
# ---------------------------------------------------------------------------


_X3D_NS = 'https://www.web3d.org/specifications/x3d-4.0.xsd'


def _hanim_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _avatar_dir() -> str:
    return os.path.join(_hanim_base_dir(), 'static', 'avatars')


def _cultivar_xml_path(cultivar_name: str) -> str:
    # Day 94: MUST match CultivarRegistry._save_to_disk's own slug exactly
    # (mccf_cultivar_lambda.py) — that lowercases; this used not to. Two
    # different casings meant hanim_export() was writing a cultivar's
    # clip data to a SEPARATE file (e.g. cultivar_Anna.xml) from the one
    # CultivarRegistry actually serves reads from (cultivar_anna.xml) —
    # both get loaded into the in-memory registry at startup since
    # _load_from_disk() scans every .xml file and keys by the <Cultivar
    # DEFinition name="..."> attribute, not the filename, so neither file
    # errors or goes missing; the lowercase one just sorts after the
    # capitalized one alphabetically and silently wins, discarding
    # whatever hanim_export had just written. Confirmed against Anna:
    # her avatar X3D resolved and wrote correctly after the Day 94 clip
    # fix, but GET /cultivars/Anna kept serving pre-fix data regardless
    # of a full server restart — restarting reloads both files and
    # reproduces the exact same shadowing, so it looked like the fix
    # hadn't taken even though the file on disk it actually targets was
    # already right.
    safe = cultivar_name.strip().lower().replace(' ', '_')
    return os.path.join(_hanim_base_dir(), 'cultivars', f'cultivar_{safe}.xml')


def _hanim_x3d_path(hanim_src: str) -> str:
    """Resolve hanim_src basename to absolute path under static/avatars/."""
    return os.path.join(_avatar_dir(), os.path.basename(hanim_src))


def _expressions_xml_path(hanim_src: str) -> str:
    """
    Derive the expressions XML path from a hanim_src filename.
    'jack_hanim.x3d' -> static/avatars/jack_expressions.xml
    'cindy_hanim.x3d' -> static/avatars/cindy_expressions.xml
    """
    import re as _re
    basename = os.path.basename(hanim_src)
    stem = _re.sub(r'_hanim\.x3d$', '', basename, flags=_re.IGNORECASE)
    stem = _re.sub(r'\.x3d$', '', stem, flags=_re.IGNORECASE)
    stem = stem.lower()
    return os.path.join(_avatar_dir(), f'{stem}_expressions.xml')


_BACKUP_KEEP = 5   # timestamped generations kept per file (Anna.x3d is ~24 MB each)


def _hanim_backup(filepath: str) -> None:
    """
    Snapshot a file before it is modified.

    Writes <file>.bak (latest — the atomic-rename rollback path in hanim_export reads
    this) AND a timestamped copy under a sibling backups/ folder, pruned to the newest
    _BACKUP_KEEP. The single .bak alone was overwritten on every export, so two exports in
    a row destroyed the only good copy; the timestamped history survives that.
    Best-effort for the history: a failure there never blocks the export.
    """
    if not os.path.exists(filepath):
        return
    _shutil_hanim.copy2(filepath, filepath + '.bak')
    try:
        base = os.path.basename(filepath)
        bdir = os.path.join(os.path.dirname(filepath), 'backups')
        os.makedirs(bdir, exist_ok=True)
        stamp = _time_hanim.strftime('%Y%m%d-%H%M%S')
        dst, n = os.path.join(bdir, f'{base}.{stamp}.bak'), 1
        while os.path.exists(dst):
            n += 1
            dst = os.path.join(bdir, f'{base}.{stamp}-{n}.bak')
        _shutil_hanim.copy2(filepath, dst)
        mine = sorted((f for f in os.listdir(bdir) if f.startswith(base + '.') and f.endswith('.bak')),
                      key=lambda f: os.path.getmtime(os.path.join(bdir, f)))
        for old in mine[:-_BACKUP_KEEP]:
            os.remove(os.path.join(bdir, old))
    except OSError:
        pass


def _parse_x3d_file(filepath: str):
    """
    Parse an X3D file.  Strips the XML declaration and DOCTYPE so ElementTree
    can handle it.  Returns (xml_decl_line: str, root_element).
    """
    with open(filepath, 'r', encoding='utf-8') as fh:
        raw = fh.read()
    xml_decl = ''
    body_lines = []
    for line in raw.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith('<?xml'):
            xml_decl = line
        elif stripped.startswith('<!DOCTYPE'):
            pass   # drop DOCTYPE — not needed for round-trip
        else:
            body_lines.append(line)
    root = _ET_hanim.fromstring(''.join(body_lines))
    return xml_decl, root


def _serialise_x3d(xml_decl: str, root) -> str:
    """Serialise an ElementTree root back to X3D text."""
    _ET_hanim.register_namespace('', _X3D_NS)
    body = _ET_hanim.tostring(root, encoding='unicode', xml_declaration=False)
    return (xml_decl or '<?xml version="1.0" encoding="UTF-8"?>\n') + body


def _update_image_texture_url(root, new_url: str) -> bool:
    """
    Find the atlas ImageTexture node and update its url attribute.
    Prefers a DEF containing 'TextureAtlas' (a naming convention, not a
    requirement — any avatar's atlas texture can use it).
    Falls back to first ImageTexture found in tree (with or without namespace),
    so this works even on avatars that don't follow the convention at all.
    Returns True if a node was updated.
    """
    ns = _X3D_NS
    target = None
    for el in root.iter(f'{{{ns}}}ImageTexture'):
        if 'TextureAtlas' in el.get('DEF', '') or 'textureatlas' in el.get('DEF', '').lower():
            target = el
            break
    if target is None:
        for el in root.iter(f'{{{ns}}}ImageTexture'):
            target = el
            break
    if target is None:
        for el in root.iter('ImageTexture'):  # no-namespace fallback
            target = el
            break
    if target is None:
        return False
    target.set('url', f'"{new_url}"')
    return True


def _collect_routes(root) -> list:
    """Return all ROUTE element attribute dicts from the tree."""
    ns = _X3D_NS
    seen  = set()
    routes = []
    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        for el in root.iter(tag):
            key = (el.get('fromNode',''), el.get('fromField',''),
                   el.get('toNode',''),   el.get('toField',''))
            if key not in seen:
                seen.add(key)
                routes.append(dict(el.attrib))
    return routes


def _remove_routes(parent) -> None:
    """Recursively remove all ROUTE elements from the tree in-place."""
    ns = _X3D_NS
    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        to_remove = [c for c in parent if c.tag == tag]
        for c in to_remove:
            parent.remove(c)
    for child in parent:
        _remove_routes(child)


def _find_scene_el(root):
    """Return the <Scene> element regardless of namespace presence."""
    ns = _X3D_NS
    scene = root.find(f'{{{ns}}}Scene')
    if scene is None:
        scene = root.find('Scene')
    return scene


def _update_displacer_weights(scene_el, displacers: list) -> int:
    """
    Write AU weight values back into HAnimDisplacer nodes in the X3D tree.

    displacers: list of { au: 'AU4_BrowLowerer', weight: 0.75 }

    Avatar-agnostic naming convention (matches the live preview driver in
    avatar_preview() exactly, so an X3D exported here previews correctly):
    for AU name '<AUName>', the displacer DEF is one of
      '<AUName>_displacer'    — unilateral AU, one displacer
      '<AUName>_l_displacer'  — bilateral AU, left-side displacer
      '<AUName>_r_displacer'  — bilateral AU, right-side displacer
    All three candidates are checked for every AU; a bilateral AU with both
    l_/r_ displacers present gets both updated from the same weight value.
    No mesh name, joint name, or avatar name appears anywhere in the match —
    an avatar that has none of these three nodes for a given AU is simply
    skipped, which is what lets the same expressions/AU data drive any
    avatar that happens to implement that AU.

    Returns count of displacer nodes updated.
    """
    if not displacers:
        return 0

    # Build a lookup: au_name -> weight
    au_map = {d['au']: float(d['weight']) for d in displacers if 'au' in d}
    if not au_map:
        return 0

    # Every candidate DEF name we might need to match, mapped back to weight.
    def_to_weight = {}
    for au_name, weight in au_map.items():
        for suffix in ('_displacer', '_l_displacer', '_r_displacer'):
            def_to_weight[au_name + suffix] = weight

    ns_prefix = '{https://www.web3d.org/specifications/x3d-namespaces}'
    updated = 0

    for el in scene_el.iter():
        tag = el.tag.replace(ns_prefix, '')
        if tag != 'HAnimDisplacer':
            continue
        def_val = el.get('DEF') or ''
        if def_val in def_to_weight:
            el.set('weight', str(round(def_to_weight[def_val], 6)))
            updated += 1

    return updated


def _write_expressions_xml(expressions_path: str, expressions: list) -> int:
    """
    Upsert <Expression> blocks into an MCCFExpressions XML file.

    expressions: list of { name: str, au_weights: { AUName: float, ... } }
      au_weights must be the FULL vector — all AUs present, zeroes included.
      Preserves complete state for downstream consumers and future lerp work.

    Strategy:
      - Parse existing file if present (preserves <Weight> displacement vectors
        on existing <Expression> blocks not covered by this export).
      - For each incoming expression, replace or insert the <Expression> block
        entirely — all <Weight> children rewritten from au_weights.
      - Existing <ExpressionState> element preserved unchanged.
      - Writes atomically via .tmp + os.replace().

    Returns count of expressions written.
    """
    import xml.etree.ElementTree as _ET

    if not expressions:
        return 0

    # ── Parse or create root ─────────────────────────────────────────────
    root = None
    if os.path.exists(expressions_path):
        try:
            tree = _ET.parse(expressions_path)
            root = tree.getroot()
        except _ET.ParseError:
            root = None  # corrupt file — rebuild from scratch

    if root is None:
        root = _ET.Element('MCCFExpressions')

    # ── Index existing Expression elements by name ───────────────────────
    existing = {}
    for el in list(root.findall('Expression')):
        name = el.get('name', '')
        if name:
            existing[name] = el

    # ── Upsert each incoming expression ─────────────────────────────────
    written = 0
    for expr in expressions:
        name = (expr.get('name') or '').strip()
        au_weights = expr.get('au_weights') or {}
        if not name or not au_weights:
            continue

        # Build fresh Expression element
        expr_el = _ET.Element('Expression')
        expr_el.set('name', name)

        # Write all AUs — full vector, zeroes preserved
        for au_name, value in sorted(au_weights.items()):
            w_el = _ET.SubElement(expr_el, 'Weight')
            w_el.set('au',    au_name)
            w_el.set('value', str(round(float(value), 6)))

        if name in existing:
            # Replace in-place — find position and swap
            idx = list(root).index(existing[name])
            root.remove(existing[name])
            root.insert(idx, expr_el)
        else:
            # Append before ExpressionState if present, else at end
            state_el = root.find('ExpressionState')
            if state_el is not None:
                idx = list(root).index(state_el)
                root.insert(idx, expr_el)
            else:
                root.append(expr_el)

        existing[name] = expr_el
        written += 1

    if written == 0:
        return 0

    # ── Serialise with readable indentation ─────────────────────────────
    _ET.indent(root, space='  ')
    xml_text = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                + _ET.tostring(root, encoding='unicode'))

    # ── Atomic write ─────────────────────────────────────────────────────
    tmp_path = expressions_path + '.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as fh:
        fh.write(xml_text)
    os.replace(tmp_path, expressions_path)

    return written


def _look_at_orientation(cam_pos, target_pos, v_angle_deg):
    """
    Python port of mccf_x3d_loader.html's _lookAtOrientation — including the Day 63
    LOOK_AT_HEIGHT correction (aim at eye height, not the ground point) that the events
    editor's own _prevLookAtOrientation never received. Ported from the Loader, the
    corrected/authoritative source, not the stale copy — see Day 77 Camera Model
    Revision doc for how that staleness was found (in mccf_scene_composer.html's
    camera-seeding feature) and fixed there too.

    Returns [ax, ay, az, angle] — X3D SFRotation axis-angle.
    """
    LOOK_AT_HEIGHT = 1.7
    dx = target_pos[0] - cam_pos[0]
    dy = (target_pos[1] + LOOK_AT_HEIGHT) - cam_pos[1]
    dz = target_pos[2] - cam_pos[2]
    yaw = _math.atan2(-dx, -dz)
    horiz_dist = _math.sqrt(dx * dx + dz * dz)
    pitch = _math.atan2(dy, horiz_dist) + (v_angle_deg * _math.pi / 180)
    cos_y, sin_y = _math.cos(yaw / 2), _math.sin(yaw / 2)
    cos_p, sin_p = _math.cos(pitch / 2), _math.sin(pitch / 2)
    qw = cos_y * cos_p
    qx = cos_y * sin_p
    qy = sin_y * cos_p
    qz = -sin_y * sin_p
    angle = 2 * _math.acos(min(1, max(-1, qw)))
    s = _math.sqrt(1 - qw * qw)
    if s < 0.001:
        ax, ay, az = 0, 1, 0
    else:
        ax, ay, az = qx / s, qy / s, qz / s
    return [ax, ay, az, angle]


def _compute_orbit_camera_keyframes(radius, height, start_angle_deg, v_angle_deg, steps=36):
    """
    Python port of mccf_x3d_loader.html's _executeAgentOrbit keyframe loop. Target is
    always local origin [0,0,0] — the avatar's own Transform IS the world position,
    same reasoning as the Loader's runtime version (this is now authored once at
    Character-Creator time instead of computed at cue-fire time, but the geometry is
    identical). Returns (keys, pos_key_values, ori_key_values) — flat lists, X3D
    MFFloat/MFVec3f/MFRotation shapes, ready to join into attribute strings.
    """
    keys, pos_vals, ori_vals = [], [], []
    subject_pos = [0, 0, 0]
    for i in range(steps + 1):
        frac = i / steps
        theta = (start_angle_deg + frac * 360) * _math.pi / 180
        cx = radius * _math.sin(theta)
        cy = height
        cz = radius * _math.cos(theta)
        orient = _look_at_orientation([cx, cy, cz], subject_pos, v_angle_deg)
        keys.append(frac)
        pos_vals.append((cx, cy, cz))
        ori_vals.append(tuple(orient))
    return keys, pos_vals, ori_vals


def _compute_track_camera_keyframes(off0, off1, height, depth, v_angle_deg, steps=36):
    """
    Python port of mccf_x3d_loader.html's _executeAgentTrack keyframe loop. Same local-
    origin-target reasoning as orbit above.
    """
    keys, pos_vals, ori_vals = [], [], []
    local_origin = [0, 0, 0]
    for i in range(steps + 1):
        frac = i / steps
        cx = off0 + (off1 - off0) * frac
        cy = height
        cz = depth
        orient = _look_at_orientation([cx, cy, cz], local_origin, v_angle_deg)
        keys.append(frac)
        pos_vals.append((cx, cy, cz))
        ori_vals.append(tuple(orient))
    return keys, pos_vals, ori_vals


# DEF names used INSIDE the avatar file (bare, one per avatar — not per-scene-instance).
# Matches the identity-EXPORT convention _write_clip_nodes already established:
# "localDEF and AS are the same bare name. The agent-suffix... is applied by the Scene
# Composer's IMPORT AS= attribute, not here." Composer's IMPORT AS= targets deliberately
# match what the Loader already looks up today (VP_{subject}_Eye, CAM_OrbitProto_{subject},
# CAM_TrackProto_{subject}) — see the Day 77 Camera Model Revision doc — so only the
# Loader's *lookup mechanism* needs to change (getNamedNode -> getImportedNode), not any
# caller-side string construction.
_CAM_RIG_DEFS = {'agent_eye': 'CAM_Eye', 'agent_side': 'CAM_Side',
                 'agent_orbit': 'CAM_Orbit', 'agent_track': 'CAM_Track'}

# Relative path from static/avatars/ to static/x3d/protos/ — confirmed against
# mccf_api.py's own comment on X3DAssets ("same relative-path convention as protos/,
# see buildCameraProtoDecls") and Composer's avatar Inline path (../avatars/... from
# static/x3d/), not guessed.
_CAM_PROTO_REL_URL = '../x3d/protos/mccf_camera_protos.x3d'


def _ensure_camera_proto_declares(scene_el):
    """
    Add ExternProtoDeclare for AgentOrbitCamera/AgentTrackCamera to the avatar file's
    own Scene if not already present — proto instantiation requires a matching
    ProtoDeclare/ExternProtoDeclare in the SAME execution context, not inherited from
    whatever inlines this file. Interface mirrors mccf_camera_protos.x3d's real
    ProtoDeclare exactly (position/rotation via initialTranslation/initialRotation,
    not a single combined field — same reasoning as that file's own comment: ordinary
    parent/child Transform nesting composes yaw/pitch/roll, not custom JS axis-angle
    math). Idempotent — checks by name before inserting, inserted at the front of
    Scene so it precedes any ProtoInstance that references it.
    """
    ns = _X3D_NS
    existing_names = set()
    for el in scene_el.findall(f'{{{ns}}}ExternProtoDeclare'):
        if el.get('name'):
            existing_names.add(el.get('name'))

    def _make_declare(name, extra_fields):
        if name in existing_names:
            return None
        el = _ET_hanim.Element(f'{{{ns}}}ExternProtoDeclare')
        el.set('name', name)
        el.set('url', f'"{_CAM_PROTO_REL_URL}#{name}"')
        fields = [
            ('inputOutput', 'SFVec3f', 'initialTranslation'),
            ('inputOutput', 'SFRotation', 'initialRotation'),
            ('inputOutput', 'MFFloat', 'key'),
            ('inputOutput', 'MFVec3f', 'keyValue'),
            ('inputOutput', 'MFRotation', 'oriKeyValue'),
            ('inputOutput', 'SFTime', 'cycleInterval'),
            ('inputOutput', 'SFBool', 'loop'),
            ('inputOutput', 'SFBool', 'enabled'),
            ('inputOutput', 'SFTime', 'startTime'),
            ('inputOutput', 'SFString', 'description'),
            ('inputOnly', 'SFBool', 'set_bind'),
        ]
        for access, ftype, fname in fields:
            f_el = _ET_hanim.SubElement(el, f'{{{ns}}}field')
            f_el.set('accessType', access)
            f_el.set('type', ftype)
            f_el.set('name', fname)
        return el

    for name in ('AgentOrbitCamera', 'AgentTrackCamera'):
        el = _make_declare(name, None)
        if el is not None:
            scene_el.insert(0, el)


def _remove_elements_by_def(root, def_names) -> None:
    """Recursively remove elements whose DEF is in def_names, in-place. Mirrors
    _remove_routes' recursion pattern — needed so re-exporting from Character Creator
    replaces a previous rig instead of accumulating duplicate-DEF nodes (unlike
    _write_clip_nodes, which is append-only; camera rig nodes are fixed-identity, one
    per avatar, so idempotent replacement is the correct behavior here, not append)."""
    to_remove = [c for c in root if c.get('DEF') in def_names]
    for c in to_remove:
        root.remove(c)
    for child in root:
        _remove_elements_by_def(child, def_names)


def _remove_elements_by_localdef(root, tag, def_names) -> None:
    """Same as above but for EXPORT elements, keyed by localDEF not DEF."""
    to_remove = [c for c in root if c.tag == tag and c.get('localDEF') in def_names]
    for c in to_remove:
        root.remove(c)
    for child in root:
        _remove_elements_by_localdef(child, tag, def_names)


def _write_camera_rig_nodes(scene_el, camera_rig: dict) -> list:
    """
    Write CAM_Eye/CAM_Side/CAM_Orbit/CAM_Track nodes (whichever camera_rig marks
    enabled) into the avatar file's own Scene, each with a matching identity EXPORT
    statement so Composer's IMPORT ... AS= mechanism can pull them into a scene at
    the correct per-instance name. Removes any previously-written rig nodes first —
    idempotent replacement, not accumulation (see _remove_elements_by_def).

    Returns the list of rig types actually written (for the manifest and the
    hanim_export response).
    """
    ns = _X3D_NS
    all_defs = set(_CAM_RIG_DEFS.values())
    _remove_elements_by_def(scene_el, all_defs)
    _remove_elements_by_localdef(scene_el, f'{{{ns}}}EXPORT', all_defs)

    written = []
    needs_protos = False

    def _add_export(def_name):
        ex = _ET_hanim.SubElement(scene_el, f'{{{ns}}}EXPORT')
        ex.set('localDEF', def_name)
        ex.set('AS', def_name)

    eye_cfg = camera_rig.get('agent_eye') or {}
    if eye_cfg.get('enabled'):
        vp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}Viewpoint')
        vp.set('DEF', _CAM_RIG_DEFS['agent_eye'])
        vp.set('position', '0 1.7 0.2')
        vp.set('orientation', '0 1 0 3.14159')
        vp.set('jump', 'true')
        vp.set('description', 'Eye')
        _add_export(_CAM_RIG_DEFS['agent_eye'])
        written.append('agent_eye')

    side_cfg = camera_rig.get('agent_side') or {}
    if side_cfg.get('enabled'):
        vp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}Viewpoint')
        vp.set('DEF', _CAM_RIG_DEFS['agent_side'])
        vp.set('position', '2.5 1.5 0')
        vp.set('orientation', '0 1 0 1.5708')
        vp.set('jump', 'true')
        vp.set('description', 'Side')
        _add_export(_CAM_RIG_DEFS['agent_side'])
        written.append('agent_side')

    orbit_cfg = camera_rig.get('agent_orbit') or {}
    if orbit_cfg.get('enabled'):
        radius = float(orbit_cfg.get('radius', 8.6))
        height = float(orbit_cfg.get('height', 3.2))
        start_angle = float(orbit_cfg.get('startAngle', 0))
        v_angle = float(orbit_cfg.get('vAngle', -8))
        cycle = float(orbit_cfg.get('cycleInterval', 4))
        loop = bool(orbit_cfg.get('loop', True))
        keys, pos_vals, ori_vals = _compute_orbit_camera_keyframes(radius, height, start_angle, v_angle)
        el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}AgentOrbitCamera')
        el.set('DEF', _CAM_RIG_DEFS['agent_orbit'])
        el.set('description', 'Orbit')
        el.set('cycleInterval', str(cycle))
        el.set('loop', 'true' if loop else 'false')
        el.set('initialTranslation', '%.6g %.6g %.6g' % pos_vals[0])
        el.set('initialRotation', '%.6g %.6g %.6g %.6g' % ori_vals[0])
        el.set('key', ' '.join('%.6g' % k for k in keys))
        el.set('keyValue', ' '.join('%.6g %.6g %.6g' % p for p in pos_vals))
        el.set('oriKeyValue', ' '.join('%.6g %.6g %.6g %.6g' % o for o in ori_vals))
        _add_export(_CAM_RIG_DEFS['agent_orbit'])
        written.append('agent_orbit')
        needs_protos = True

    track_cfg = camera_rig.get('agent_track') or {}
    if track_cfg.get('enabled'):
        off0 = float(track_cfg.get('trackOffset', -3))
        off1 = float(track_cfg.get('trackOffsetEnd', 3))
        height = float(track_cfg.get('height', 1.7))
        depth = float(track_cfg.get('trackDepth', 4))
        v_angle = float(track_cfg.get('vAngle', -8))
        cycle = float(track_cfg.get('cycleInterval', 4))
        keys, pos_vals, ori_vals = _compute_track_camera_keyframes(off0, off1, height, depth, v_angle)
        el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}AgentTrackCamera')
        el.set('DEF', _CAM_RIG_DEFS['agent_track'])
        el.set('description', 'Track')
        el.set('cycleInterval', str(cycle))
        el.set('loop', 'false')  # agent_track always plays once — Camera Spec §3, not author-configurable
        el.set('initialTranslation', '%.6g %.6g %.6g' % pos_vals[0])
        el.set('initialRotation', '%.6g %.6g %.6g %.6g' % ori_vals[0])
        el.set('key', ' '.join('%.6g' % k for k in keys))
        el.set('keyValue', ' '.join('%.6g %.6g %.6g' % p for p in pos_vals))
        el.set('oriKeyValue', ' '.join('%.6g %.6g %.6g %.6g' % o for o in ori_vals))
        _add_export(_CAM_RIG_DEFS['agent_track'])
        written.append('agent_track')
        needs_protos = True

    if needs_protos:
        _ensure_camera_proto_declares(scene_el)

    return written


def _camera_rig_manifest_path(hanim_src: str) -> str:
    """static/avatars/cindy_hanim.x3d -> static/avatars/cindy_hanim.manifest.xml —
    same sidecar-file, same-basename-plus-suffix convention as
    _expressions_xml_path (cindy_hanim.x3d -> cindy_expressions.xml), per the Avatar
    Camera Rig Manifest doc §4 decision (XML sidecar, not embedded in the .x3d)."""
    base = os.path.basename(hanim_src)
    stem = base[:-4] if base.lower().endswith('.x3d') else base
    return os.path.join(_avatar_dir(), f'{stem}.manifest.xml')


def _write_camera_rig_manifest(hanim_src: str, camera_rig: dict, written_rig_types: list) -> None:
    """
    Write the sidecar XML manifest per Avatar Camera Rig Manifest doc §4:
    '<MetadataSet name="cameraRig"> listing the Viewpoints actually parented in that
    file'. Reuses field-map.js's own <MetadataSet>/<MetadataString> house style,
    per that doc's explicit convention — hand-rolled here since this is the Python
    side, not a shared module with the JS convention, but the output shape matches.

    Carries the full authored parameter values as attributes, not just boolean
    presence — needed so Character Creator can reconstruct its form state when an
    author reopens an avatar that already has a rig, rather than only being able to
    tell Composer "orbit exists" with no way to re-populate radius/height/etc. The
    doc's own wording ("listing the Viewpoints actually parented") doesn't forbid
    this; Composer's read side only needs the name attribute, everything else is
    additional and backward-compatible with a reader that ignores extra attributes.

    Note: behavior-clip listing (the manifest's other stated purpose, per §4 —
    "plus whichever behavior clips are present") is NOT added here. Clips are
    already written by _write_clip_nodes earlier in hanim_export() from a different
    payload key (clips, not cameraRig) — merging that into this manifest write is a
    reasonable follow-up but out of scope for the camera rig work this serves; not
    doing it silently.
    """
    path = _camera_rig_manifest_path(hanim_src)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<MetadataSet name="cameraRig">']
    for rig_type in written_rig_types:
        cfg = camera_rig.get(rig_type) or {}
        attrs = [f'name="{rig_type}"', 'value="1"']
        for key, val in cfg.items():
            if key == 'enabled':
                continue
            if isinstance(val, bool):
                attrs.append(f'{key}="{"true" if val else "false"}"')
            else:
                attrs.append(f'{key}="{val}"')
        lines.append(f'  <MetadataString {" ".join(attrs)}/>')
    lines.append('</MetadataSet>')
    content = '\n'.join(lines) + '\n'
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(content)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Clip export — timer index + safe writer  (Day 95 rewrite; closes S1/S2/S4)
#
# The contract this block enforces, in one place:
#   1. A TimeSensor that has ROUTEs out of fraction_changed is REAL. Export
#      never strips, rewrites, renames or re-parents it. (Old code deleted
#      Anna's routed Timer6 this way and left 51 dangling ROUTEs.)
#   2. A clip is AUTHORED only if some keyframe actually holds joints. The
#      editor seeds every clip with two empty default keyframes, so "has a
#      keyframes list" says nothing (old `if not keyframes` was never true).
#   3. A clip's own timerDEF is honoured as-is when it resolves (by DEF or by
#      EXPORT alias, e.g. BowTimer -> Timer8) to a real timer. It is never
#      swapped for a description-matched neighbour — that is what pointed the
#      cultivar at Timer8/Timer13 while the scene imports BowTimer.
#   4. Only nodes this writer created (and that no author-supplied ROUTE
#      touches beyond its own interpolators) are ever removed on re-export.
# ---------------------------------------------------------------------------

def _tag_local(el) -> str:
    """Element tag without its namespace; '' for comments/PIs."""
    t = el.tag
    return t.rsplit('}', 1)[-1] if isinstance(t, str) else ''


def _safe_def(name: str) -> str:
    """Valid X3D DEF for names WE create (timers, interpolators): [A-Za-z0-9_] only."""
    return _re.sub(r'[^A-Za-z0-9_]', '_', name or '')


def _build_timer_index(scene_el, existing_routes: list):
    """
    Facts about every clip-candidate TimeSensor (WireTimer_* pose plumbing is excluded).

    Returns (timers, alias):
      timers: { DEF: {def, el, routes, exports, description, loop} } in document order,
              routes = number of fraction_changed ROUTEs leaving it (0 = hollow)
      alias:  { EXPORT AS name: DEF }  so a clip can reference a timer by the name the
              scene IMPORTs (BowTimer) as well as by its DEF (Timer8).
    """
    routed = {}
    for r in existing_routes:
        if r.get('fromField') == 'fraction_changed':
            routed[r.get('fromNode')] = routed.get(r.get('fromNode'), 0) + 1
    exports = {}
    for el in scene_el.iter():
        if _tag_local(el) == 'EXPORT' and el.get('localDEF'):
            exports.setdefault(el.get('localDEF'), []).append(el.get('AS') or el.get('localDEF'))
    timers = {}
    for el in scene_el.iter():
        if _tag_local(el) != 'TimeSensor':
            continue
        d = el.get('DEF', '')
        if not d or d.startswith('WireTimer_') or d in timers:
            continue
        timers[d] = {'def': d, 'el': el, 'routes': routed.get(d, 0),
                     'exports': exports.get(d, []),
                     'description': el.get('description', ''), 'loop': el.get('loop')}
    alias = {}
    for d, info in timers.items():
        for a in info['exports']:
            alias.setdefault(a, d)
    return timers, alias


def _resolve_timer_ref(ref: str, timers: dict, alias: dict):
    """Timer info for a clip's timerDEF, whether it is a DEF or an EXPORT alias."""
    if ref in timers:
        return timers[ref]
    return timers.get(alias.get(ref, ''))


def _reachable_name(info: dict) -> str:
    """The name a scene can IMPORT this timer under: its own DEF if exported under
    that name, else its first EXPORT alias, else the DEF (exists but unreachable)."""
    if info['def'] in info['exports']:
        return info['def']
    return info['exports'][0] if info['exports'] else info['def']


def _find_real_clips_by_label(timers: dict) -> dict:
    """
    Fallback only — used when a clip's own timerDEF resolves to nothing real.
    { humanized label: [timer info, ...] } for ROUTED timers, most reachable first
    (a timer with an EXPORT can be IMPORTed by a scene; one without cannot).
    """
    by_label = {}
    for d, info in timers.items():
        if info['routes'] <= 0:
            continue
        label = _humanize_gesture_label(info['description'], d)
        by_label.setdefault(label, []).append(info)
    for lst in by_label.values():
        lst.sort(key=lambda i: 0 if i['exports'] else 1)   # stable: keeps document order
    return by_label


def _clip_is_authored(clip: dict) -> bool:
    """True only if some keyframe really holds joint rotations."""
    for kf in clip.get('keyframes') or []:
        if isinstance(kf, dict) and kf.get('joints'):
            return True
    return False


def _joint_lookup(scene_el):
    """(by_def, by_name): HAnimJoint DEF set, and name -> DEF. The editor keys keyframes
    by the joint's `name`, but a ROUTE must target its DEF — in Anna 38 of 96 joints
    differ (DEF 'L-Thigh', name 'L_Thigh'), so name-targeted ROUTEs dangled."""
    by_def, by_name = set(), {}
    for el in scene_el.iter():
        if _tag_local(el) != 'HAnimJoint' or el.get('USE'):
            continue
        d = el.get('DEF')
        if d:
            by_def.add(d)
            if el.get('name'):
                by_name.setdefault(el.get('name'), d)
    return by_def, by_name


def _authored_interp_prefixes(timer_def: str, clip_name: str) -> tuple:
    """DEF prefixes this writer has used for a clip's interpolators: current
    '<timer>_Interp_' and the legacy '<clipname>Interp_'."""
    pfx = [f'{timer_def}_Interp_']
    if clip_name:
        pfx.append(f'{clip_name}Interp_')
    return tuple(pfx)


def _is_own_authored(timer_def: str, clip_name: str, routes: list) -> bool:
    """True if every fraction_changed ROUTE out of this timer feeds an interpolator
    carrying this writer's own naming — i.e. it is our previous output, safe to replace.
    A timer wired to anything else (Blender/Mixamo/Sunrize animation) is never ours."""
    pfx = _authored_interp_prefixes(timer_def, clip_name)
    outs = [r for r in routes if r.get('fromNode') == timer_def
            and r.get('fromField') == 'fraction_changed']
    return all(r.get('toNode', '').startswith(pfx) for r in outs)


def _remove_authored_clip(scene_el, timer_def: str, clip_name: str) -> set:
    """
    Remove a previous version of a clip THIS WRITER authored: the TimeSensor, its EXPORT
    and its own-named OrientationInterpolators. Callers must have checked
    _is_own_authored first. Every removal is on the direct-child list it lives in
    (nested nodes are handled too). Returns the set of removed DEFs so the caller can
    drop the ROUTEs that touched them (no dangling endpoints).
    """
    pfx = _authored_interp_prefixes(timer_def, clip_name)
    removed = set()
    for parent in list(scene_el.iter()):
        for child in list(parent):
            t = _tag_local(child)
            if t == 'TimeSensor' and child.get('DEF') == timer_def:
                removed.add(timer_def); parent.remove(child)
            elif t == 'EXPORT' and child.get('localDEF') == timer_def:
                parent.remove(child)
            elif t == 'OrientationInterpolator' and child.get('DEF', '').startswith(pfx):
                removed.add(child.get('DEF')); parent.remove(child)
    return removed


def _write_clip_nodes(scene_el, clips: list, existing_routes: list) -> tuple:
    """
    Resolve every clip in the export payload against the file, write nodes only for
    genuinely authored clips, and re-append all ROUTEs last (ROUTE-last invariant).

    Per clip, in order:
      1. clip.timerDEF resolves (DEF or EXPORT alias) to a timer that has ROUTEs
         -> REAL. Nothing in the file is touched, resolved name = the timerDEF as sent.
         Exceptions: (a) clip.loop_edited -> ONLY that timer's loop attribute is set;
         (b) the clip also carries authored keyframes AND the timer is this writer's own
         earlier output -> falls through to a clean rewrite (step 3).
         Authored keyframes on someone else's routed timer are ignored, with a warning.
      2. Not authored (no keyframe holds joints) and no real timer of that ref ->
         label fallback (description match, only timers that have an EXPORT); else skipped.
         Never writes and never strips anything.
      3. Authored -> (re)write TimeSensor(enabled=false)+EXPORT+OrientationInterpolators
         with sanitised DEFs, joints mapped name->DEF; refuse (warning) rather than
         overwrite anything that isn't our own earlier output.

    Returns (clips_written, routes_written, resolved_defs, report) where report =
    {'warnings': [str], 'loop_updated': [str], 'skipped': [str]}. resolved_defs maps clip
    name -> the timerDEF the cultivar should store.
    """
    ns = _X3D_NS
    clips_written = 0
    new_routes    = list(existing_routes)
    resolved_defs = {}
    report        = {'warnings': [], 'loop_updated': [], 'skipped': []}

    timers, alias   = _build_timer_index(scene_el, existing_routes)
    by_label        = _find_real_clips_by_label(timers)
    joint_defs, joint_names = _joint_lookup(scene_el)
    used_defs = {el.get('DEF') for el in scene_el.iter() if el.get('DEF')}

    for clip in clips:
        name     = clip.get('name') or 'Default'
        ref      = (clip.get('timerDEF') or '').strip()
        authored = _clip_is_authored(clip)
        info     = _resolve_timer_ref(ref, timers, alias) if ref else None
        real     = info is not None and info['routes'] > 0

        # ── 1. The clip's own timer is real and wired ───────────────────
        if real:
            own = _is_own_authored(info['def'], name, existing_routes)
            if not (authored and own):
                if authored:
                    report['warnings'].append(
                        f"clip '{name}': keyframes ignored — timer '{ref}' already animates "
                        f"{info['routes']} joints and was not authored by this editor; "
                        f"add a NEW clip to author a new animation")
                if clip.get('loop_edited'):
                    want = 'true' if clip.get('loop', True) else 'false'
                    if (info['el'].get('loop') or 'false') != want:
                        info['el'].set('loop', want)
                        report['loop_updated'].append(f"{info['def']} loop={want}")
                resolved_defs[name] = ref
                clips_written += 1
                continue
            # else: our own earlier authored output being re-authored — rewrite below,
            # under the timer's real DEF even if the clip referenced it by EXPORT alias
            ref = info['def']

        # ── 2. Nothing authored: resolve by label, never write/strip ───
        if not authored:
            # Only a timer a scene can IMPORT (has an EXPORT) is a usable target; resolving to
            # an unexported one (Anna's Timer13) would point the cultivar somewhere unreachable.
            cands = [i for i in (by_label.get(name) or []) if i['exports']]
            if cands:
                resolved_defs[name] = _reachable_name(cands[0])
                clips_written += 1
            else:
                report['skipped'].append(f"clip '{name}' (timerDEF '{ref}'): no real animation, "
                                         f"no authored keyframes — nothing written")
            continue

        # ── 3. Genuinely authored clip: (re)write it ────────────────────
        timer_def = _safe_def(ref or (name + 'Timer'))
        if timer_def != ref and ref:
            report['warnings'].append(f"clip '{name}': timerDEF '{ref}' is not a valid DEF; "
                                      f"written as '{timer_def}'")
        clash = timers.get(timer_def)
        if clash is not None and clash['routes'] > 0 and not _is_own_authored(timer_def, name, existing_routes):
            report['warnings'].append(f"clip '{name}': '{timer_def}' is a routed timer this editor "
                                      f"did not author — clip not written")
            continue

        joint_kfs = {}   # joint DEF -> [(t, rot)]
        for kf in sorted(clip.get('keyframes') or [], key=lambda k: k.get('t', 0.0)):
            for jkey, rot in (kf.get('joints') or {}).items():
                jdef = jkey if jkey in joint_defs else joint_names.get(jkey)
                if jdef is None:
                    report['warnings'].append(f"clip '{name}': joint '{jkey}' not in this file — skipped")
                    continue
                if rot and len(rot) == 4:
                    joint_kfs.setdefault(jdef, []).append((kf.get('t', 0.0), rot))
        if not joint_kfs:
            report['skipped'].append(f"clip '{name}': no keyframe joints match this file — nothing written")
            continue

        removed = _remove_authored_clip(scene_el, timer_def, name)
        if removed:
            used_defs -= removed
            new_routes = [r for r in new_routes
                          if r.get('fromNode') not in removed and r.get('toNode') not in removed]

        cycle = float(clip.get('cycleInterval', 6.0))
        loop  = 'true' if clip.get('loop', True) else 'false'

        ts = _ET_hanim.SubElement(scene_el, f'{{{ns}}}TimeSensor')
        ts.set('DEF',           timer_def)
        ts.set('cycleInterval', str(cycle))
        ts.set('loop',          loop)
        ts.set('enabled',       'false')          # invariant: never starts on its own
        used_defs.add(timer_def)

        # Identity EXPORT so the loader can reach it via getImportedNode once the
        # scene's <IMPORT> registers it (agent suffix is added by Composer's AS=).
        ex = _ET_hanim.SubElement(scene_el, f'{{{ns}}}EXPORT')
        ex.set('localDEF', timer_def)
        ex.set('AS',       timer_def)

        for jdef in sorted(joint_kfs):
            base = f'{timer_def}_Interp_{_safe_def(jdef)}'
            interp_def, n = base, 2
            while interp_def in used_defs:
                interp_def, n = f'{base}_{n}', n + 1
            used_defs.add(interp_def)
            pts = joint_kfs[jdef]
            interp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}OrientationInterpolator')
            interp.set('DEF',      interp_def)
            interp.set('key',      ' '.join(str(round(t, 4)) for t, _ in pts))
            interp.set('keyValue', ' '.join(' '.join(str(round(v, 6)) for v in rot) for _, rot in pts))
            new_routes.append({'fromNode': timer_def,  'fromField': 'fraction_changed',
                               'toNode':   interp_def, 'toField':   'set_fraction'})
            new_routes.append({'fromNode': interp_def, 'fromField': 'value_changed',
                               'toNode':   jdef,       'toField':   'set_rotation'})

        resolved_defs[name] = timer_def
        clips_written += 1

    # Deduplicate and append all ROUTEs last — INVARIANT
    seen_r, unique_r = set(), []
    for r in new_routes:
        key = (r.get('fromNode', ''), r.get('fromField', ''), r.get('toNode', ''), r.get('toField', ''))
        if key not in seen_r:
            seen_r.add(key)
            unique_r.append(r)
    for r_attrib in unique_r:
        re_el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}ROUTE')
        for k, v in r_attrib.items():
            re_el.set(k, v)

    return clips_written, len(unique_r), resolved_defs, report


def _x3d_integrity(root) -> dict:
    """
    Structural problems in an X3D tree, as {category: sorted [names]} — used to compare a
    file BEFORE and AFTER an export mutates it. Categories: dangling_route (ROUTE endpoint
    not defined), export_undefined (EXPORT localDEF not defined), export_duplicate_as,
    def_duplicate, def_whitespace (invalid X3D name).
    """
    defs, imported = {}, set()
    routes, exports = [], []
    for el in root.iter():
        t = _tag_local(el)
        d = el.get('DEF')
        if d:
            defs[d] = defs.get(d, 0) + 1
        if t == 'ROUTE':
            routes.append(el)
        elif t == 'EXPORT':
            exports.append(el)
        elif t == 'IMPORT':
            imported.add(el.get('AS') or el.get('importedDEF') or '')
    known = set(defs) | imported
    endpoints = set()
    for r in routes:
        endpoints.add(r.get('fromNode', '')); endpoints.add(r.get('toNode', ''))
    as_count = {}
    for e in exports:
        n = e.get('AS') or e.get('localDEF') or ''
        as_count[n] = as_count.get(n, 0) + 1
    return {
        'dangling_route':      sorted(n for n in endpoints if n not in known),
        'export_undefined':    sorted({e.get('localDEF', '') for e in exports if e.get('localDEF') not in defs}),
        'export_duplicate_as': sorted(n for n, c in as_count.items() if c > 1),
        'def_duplicate':       sorted(n for n, c in defs.items() if c > 1),
        'def_whitespace':      sorted(n for n in defs if _re.search(r'\s', n)),
    }


def _integrity_regressions(before: dict, after: dict) -> list:
    """Problems present AFTER but not BEFORE, as human-readable strings. Problems the file
    already had (e.g. Anna's five whitespace-DEF stubs) do not block an export."""
    out = []
    for cat, names in after.items():
        new = sorted(set(names) - set(before.get(cat, [])))
        if new:
            out.append(f"{cat}: {', '.join(new[:8])}" + (f" (+{len(new) - 8} more)" if len(new) > 8 else ''))
    return out



@hanim_bp.route('/hanim/skin_upload', methods=['POST'])
def hanim_skin_upload():
    """
    POST /hanim/skin_upload
    Body: { cultivar: str, data_url: str }

    Decodes a base64 data URL (image/png or image/jpeg) and saves it to
    static/avatars/<cultivar_slug>_skin.png.

    Returns: { status, path }
      path is the relative URL the X_ITE viewer can load,
      e.g. '/static/avatars/cindy_skin.png'
    """
    import re as _re
    data      = request.get_json(silent=True) or {}
    cultivar  = (data.get('cultivar') or '').strip()
    data_url  = (data.get('data_url') or '').strip()

    if not data_url:
        return jsonify({'status': 'error', 'error': 'data_url required'}), 400

    match = _re.match(r'^data:(image/(?:png|jpeg|jpg));base64,(.+)$',
                      data_url, _re.DOTALL)
    if not match:
        return jsonify({'status': 'error',
                        'error': 'data_url must be base64-encoded image/png or image/jpeg'}), 400
    try:
        img_bytes = _b64.b64decode(match.group(2))
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'base64 decode failed: {exc}'}), 400

    os.makedirs(_avatar_dir(), exist_ok=True)
    slug     = _re.sub(r'[^A-Za-z0-9_\-]', '_', cultivar).lower() if cultivar else 'avatar'
    filename = f'{slug}_skin.png'
    filepath = os.path.join(_avatar_dir(), filename)
    try:
        with open(filepath, 'wb') as fh:
            fh.write(img_bytes)
    except OSError as exc:
        return jsonify({'status': 'error', 'error': f'write failed: {exc}'}), 500

    return jsonify({'status': 'ok', 'path': f'/static/avatars/{filename}'})


@hanim_bp.route('/hanim/export', methods=['POST'])
def hanim_export():
    """
    POST /hanim/export
    Body (JSON):
    {
      cultivar:    str,           # e.g. "Cindy"
      hanim_src:   str,           # e.g. "cindy_hanim.x3d"
      skin_url:    str | null,    # relative path or data URL
      receptivity: { E, B, P, S },
      expressions: [ { name, au_weights } ],
      clips:       [ { name, timerDEF, cycleInterval, loop, priority,
                        keyframes: [{t, joints:{jointName:[ax,ay,az,angle]}}],
                        cv_conditions } ],
      displacers:  [ { au, weight } ]   # au: AU name; see _update_displacer_weights
    }

    Phase 1: skin URL + cultivar XML (HAnimFigure/Receptivity/Behaviors) only.
    Phase 2: clips[] populated — TimeSensor + OrientationInterpolator nodes written.

    Day 95 contract (see _write_clip_nodes):
      * A clip is written only if some keyframe holds joints; a routed TimeSensor is never
        stripped/rewritten; clip.timerDEF (DEF or EXPORT alias) is honoured as sent.
      * clip.loop_edited=true (set by the editor only when the author changed Loop) is the
        ONLY thing that lets export touch the loop attribute of an existing real timer.
      * cameraRig absent/null = leave the avatar's CAM_* rig nodes untouched; an explicit
        object (even all-disabled) replaces them.
      * The result is integrity-checked against the file as it arrived; an export that would
        add a dangling ROUTE / undefined EXPORT / duplicate or whitespace DEF is refused with
        HTTP 409 and NOTHING is written.
      * removed_clips: [name] / renamed_clips: [{from, to}] delete or rename cultivar entries
        (the avatar's timer nodes are left in place -- a deleted gesture becomes an orphan timer).
      * The running server's in-memory cultivar registry is refreshed after the write, so the
        Composer / Events editor see new clips WITHOUT a Flask restart.
      * Refuses (HTTP 409, nothing written) if the cultivar record would not be valid XML.
      * Response adds: warnings, loop_updated, skipped, preexisting_problems, clips_removed,
        registry_refreshed.

    Atomic triple-write via .tmp + os.replace().  All three files backed up first.
    No file is modified if any write fails.

    Returns:
    {
      status, hanim_path, cultivar_path, expressions_path,
      clips_written, routes_written, skin_updated, expressions_written
    }
    """
    import re as _re
    from mccf_cultivar_lambda import CultivarDefinition

    body          = request.get_json(silent=True) or {}
    cultivar_name = (body.get('cultivar') or '').strip()
    hanim_src     = (body.get('hanim_src') or '').strip()
    skin_url      = (body.get('skin_url') or '').strip()
    receptivity   = body.get('receptivity') or {'E': 1.0, 'B': 1.0, 'P': 1.0, 'S': 1.0}
    clips         = body.get('clips') or []
    expressions   = body.get('expressions') or []
    # au_weights in each expression must be the full vector (all AUs, zeroes included)
    # displacers: AU weight values written back into HAnimDisplacer nodes in X3D

    if not cultivar_name:
        return jsonify({'status': 'error', 'error': 'cultivar name required'}), 400
    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400

    x3d_filepath         = _hanim_x3d_path(hanim_src)
    cultivar_filepath    = _cultivar_xml_path(cultivar_name)
    expressions_filepath = _expressions_xml_path(hanim_src)

    if not os.path.exists(x3d_filepath):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404
    if not os.path.exists(cultivar_filepath):
        return jsonify({'status': 'error',
                        'error': f'Cultivar XML not found for: {cultivar_name}'}), 404
    # expressions XML need not pre-exist — _write_expressions_xml() creates it if absent

    # ── Handle data URL skin — decode and save before any file writes ────
    final_skin_url = skin_url if skin_url and not skin_url.startswith('data:') else None
    if skin_url and skin_url.startswith('data:'):
        match = _re.match(r'^data:(image/(?:png|jpeg|jpg));base64,(.+)$',
                          skin_url, _re.DOTALL)
        if not match:
            return jsonify({'status': 'error',
                            'error': 'skin_url data URL must be image/png or image/jpeg'}), 400
        try:
            img_bytes = _b64.b64decode(match.group(2))
        except Exception as exc:
            return jsonify({'status': 'error',
                            'error': f'skin data URL decode failed: {exc}'}), 400
        os.makedirs(_avatar_dir(), exist_ok=True)
        slug      = _re.sub(r'[^A-Za-z0-9_\-]', '_', cultivar_name).lower()
        skin_file = f'{slug}_skin.png'
        skin_path = os.path.join(_avatar_dir(), skin_file)
        try:
            with open(skin_path, 'wb') as fh:
                fh.write(img_bytes)
        except OSError as exc:
            return jsonify({'status': 'error',
                            'error': f'skin image write failed: {exc}'}), 500
        final_skin_url = f'/static/avatars/{skin_file}'

    # ── Parse X3D ────────────────────────────────────────────────────────
    try:
        xml_decl, x3d_root = _parse_x3d_file(x3d_filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D parse failed: {exc}'}), 500

    # ── Update ImageTexture url ──────────────────────────────────────────
    skin_updated = False
    if final_skin_url:
        skin_updated = _update_image_texture_url(x3d_root, final_skin_url)

    # ── Collect existing ROUTEs, strip from tree, re-append last ─────────
    existing_routes = _collect_routes(x3d_root)
    scene_el = _find_scene_el(x3d_root)
    if scene_el is None:
        return jsonify({'status': 'error',
                        'error': 'No <Scene> element found in X3D file'}), 500
    # Snapshot the file's structural problems BEFORE anything mutates it, so the gate
    # below refuses only problems this export would introduce (Anna already carries five
    # whitespace-DEF stubs; those must not block every future export).
    integrity_before = _x3d_integrity(x3d_root)
    _remove_routes(scene_el)

    clips_written, routes_written, resolved_timer_defs, clip_report = \
        _write_clip_nodes(scene_el, clips, existing_routes)

    # ── Write camera rig nodes (Day 77) ────────────────────────────────────
    # camera_rig: { agent_eye: {enabled}, agent_side: {enabled},
    #               agent_orbit: {enabled, radius, height, startAngle, vAngle,
    #                             cycleInterval, loop},
    #               agent_track: {enabled, trackOffset, trackOffsetEnd, height,
    #                             trackDepth, vAngle, cycleInterval} }
    # Written into the avatar's OWN Scene (this file), not the calling scene —
    # per the Avatar Camera Rig Manifest doc's decision that rigs are authored once
    # per avatar file, not injected generically at Composer export time.
    # cameraRig ABSENT/null = "editor did not load the rig state" -> leave the rig nodes
    # exactly as they are. Only an explicit object (even all-disabled) replaces the rig.
    # (An empty {} used to wipe CAM_Eye/Side/Orbit/Track and their EXPORTs.)
    camera_rig = body.get('cameraRig')
    camera_rig_written = [] if camera_rig is None else _write_camera_rig_nodes(scene_el, camera_rig)

    # ── Write AU displacer weights ────────────────────────────────────────
    displacers      = body.get('displacers') or []
    displacers_updated = _update_displacer_weights(scene_el, displacers)

    # ── Parse cultivar XML via CultivarDefinition ─────────────────────────
    try:
        with open(cultivar_filepath, 'r', encoding='utf-8') as fh:
            cultivar_def = CultivarDefinition.from_xml(fh.read())
    except Exception as exc:
        return jsonify({'status': 'error',
                        'error': f'Cultivar XML parse failed: {exc}'}), 500

    # ── Update cultivar fields ───────────────────────────────────────────
    cultivar_def.hanim_src = os.path.basename(hanim_src)

    cultivar_def.receptivity = {
        ch: round(min(1.0, max(0.0, float(receptivity.get(ch, 1.0)))), 4)
        for ch in ('E', 'B', 'P', 'S')
    }

    # Day 95: clips the author DELETED or RENAMED in the editor. Export used to merge only
    # what it was sent and preserve every existing cultivar entry, so a deleted clip could
    # never leave the cultivar and a rename left the old name behind as a duplicate (a
    # renamed Bow became a second entry, 'BowHead', still firing the Bow timer).
    existing_by_name = {c.get('name'): c for c in cultivar_def.behavior_clips}
    clips_removed = []
    _payload_names = {c.get('name', 'Default') for c in clips}
    for _n in (body.get('removed_clips') or []):
        if _n in existing_by_name and _n not in _payload_names:
            del existing_by_name[_n]
            clips_removed.append(_n)

    if clips:
        # Day 83: real bug fix, confirmed by direct user test (playback panel
        # showed several real, working clips; cultivar still only had Default
        # after Export). This used to wholesale-replace cultivar_def.
        # behavior_clips with ONLY whatever was in THIS export's clips[] —
        # which is _heClips, the hand-authored pose-editing scratchpad on the
        # client (see mccf_character_creator.html's heExport()). _heClips
        # self-seeds with a single "Default" entry whenever the author hasn't
        # hand-built a custom animation, so every Export — even one that only
        # changes skin/receptivity/expressions — silently discarded every
        # OTHER real clip the avatar actually has (the standard base timers,
        # any Mixamo-ingested clips), regardless of what GET /hanim/joints
        # reports as genuinely present in the X3D file.
        #
        # Fixed to merge by name instead of replacing: existing entries not
        # present in this export's clips[] are preserved untouched; entries
        # that ARE present get added or updated.
        #
        # Day 94: the gap this comment used to warn about (_write_clip_nodes
        # having no existing-DEF check, so feeding it already-real clips
        # would create duplicate TimeSensor DEFs) is now closed in that
        # function itself. As part of that fix it also resolves, per clip,
        # the timerDEF that's ACTUALLY real and ROUTE-wired — which is not
        # always what the client sent (Character Creator can only know
        # whatever timerDEF was last saved here, so a bad value keeps
        # re-confirming itself across saves unless something checks against
        # the real file). Using resolved_timer_defs here instead of trusting
        # clip.get('timerDEF') directly is what breaks that loop.
        for clip in clips:
            name = clip.get('name', 'Default')
            resolved_def = resolved_timer_defs.get(name)
            if resolved_def is None:
                # This clip had no real animation and no authored keyframes
                # — _write_clip_nodes wrote nothing for it. Don't add a
                # cultivar entry pointing at a timerDEF that doesn't exist.
                continue
            # Start from the existing entry so keys this merge doesn't own (e.g. cycleInterval)
            # survive instead of being dropped by the wholesale replace.
            c = dict(existing_by_name.get(name) or {})
            c.update({
                'name':     name,
                'timerDEF': resolved_def,
                'loop':     bool(clip.get('loop', True)),
                'priority': int(clip.get('priority', 0)),
            })
            cv = clip.get('cv_conditions') or {}
            for ch in ('E', 'B', 'P', 'S'):
                for bound in ('min', 'max'):
                    key = f'{ch}_{bound}'
                    val = cv.get(key)
                    if val is not None:
                        try:
                            c[key] = round(float(val), 4)
                        except (TypeError, ValueError):
                            pass
            existing_by_name[name] = c

    # A rename is complete only once the NEW name is in the merged set (a clip the merge
    # skipped must not take its old entry with it).
    for _r in (body.get('renamed_clips') or []):
        _a, _b = _r.get('from'), _r.get('to')
        if _a and _b and _a != _b and _a in existing_by_name and _b in existing_by_name:
            del existing_by_name[_a]
            clips_removed.append(_a)

    if clips or clips_removed:
        cultivar_def.behavior_clips = list(existing_by_name.values())
        p0 = [c for c in cultivar_def.behavior_clips if c.get('priority', 0) == 0]
        cultivar_def.behavior_default = (
            p0[0]['name'] if p0 else
            (cultivar_def.behavior_clips[0]['name'] if cultivar_def.behavior_clips else 'Default')
        )

    # ── Integrity gate ───────────────────────────────────────────────────
    # Refuse (writing NOTHING) if this export would leave the avatar with a structural
    # problem it did not have on the way in: a ROUTE to a node that no longer exists, an
    # EXPORT of an undefined DEF, a duplicate DEF/EXPORT name, or a whitespace DEF.
    integrity_after = _x3d_integrity(x3d_root)
    regressions = _integrity_regressions(integrity_before, integrity_after)
    if regressions:
        return jsonify({
            'status':      'error',
            'error':       'export refused — it would corrupt the avatar file (nothing was written): '
                           + '; '.join(regressions),
            'regressions': regressions,
        }), 409

    # -- Cultivar validity gate -------------------------------------------
    # CultivarDefinition.to_xml() writes clip names into attributes WITHOUT escaping, so a
    # gesture called  Tom & Jerry  (or containing < > or a double quote) would produce an
    # unparseable cultivar file and the character would fail to load at the next startup.
    # Serialise once, prove it parses, and refuse (writing nothing) if it does not.
    new_cultivar_xml = cultivar_def.to_xml()
    try:
        _ET_hanim.fromstring(new_cultivar_xml.split('?>', 1)[1] if new_cultivar_xml.lstrip().startswith('<?xml') else new_cultivar_xml)
    except _ET_hanim.ParseError as exc:
        return jsonify({
            'status': 'error',
            'error':  'export refused -- the cultivar record would be invalid XML (nothing was written). '
                      'A clip name containing & < > or a double quote is the usual cause: ' + str(exc),
        }), 409

    # ── Atomic triple-write ──────────────────────────────────────────────
    # 1. Back up all three files (expressions XML may not exist yet — that is fine)
    _hanim_backup(x3d_filepath)
    _hanim_backup(cultivar_filepath)
    _hanim_backup(expressions_filepath)

    new_x3d_xml      = _serialise_x3d(xml_decl, x3d_root)

    tmp_x3d      = x3d_filepath      + '.tmp'
    tmp_cultivar = cultivar_filepath + '.tmp'
    # expressions written atomically inside _write_expressions_xml() itself;
    # call it now so any error aborts before we touch the other two files.
    expressions_written = 0
    if expressions:
        try:
            expressions_written = _write_expressions_xml(expressions_filepath, expressions)
        except OSError as exc:
            return jsonify({'status': 'error',
                            'error': f'expressions XML write failed: {exc}'}), 500

    # 2. Write X3D and cultivar temp files
    try:
        with open(tmp_x3d, 'w', encoding='utf-8') as fh:
            fh.write(new_x3d_xml)
        with open(tmp_cultivar, 'w', encoding='utf-8') as fh:
            fh.write(new_cultivar_xml)
    except OSError as exc:
        for p in (tmp_x3d, tmp_cultivar):
            try:
                os.remove(p)
            except OSError:
                pass
        return jsonify({'status': 'error', 'error': f'temp write failed: {exc}'}), 500

    # 3. Rename into place — both or neither
    try:
        os.replace(tmp_x3d,      x3d_filepath)
        os.replace(tmp_cultivar, cultivar_filepath)
    except OSError as exc:
        # Attempt restore from .bak
        for src, dst in [(x3d_filepath + '.bak',      x3d_filepath),
                         (cultivar_filepath + '.bak', cultivar_filepath)]:
            if os.path.exists(src):
                try:
                    _shutil_hanim.copy2(src, dst)
                except OSError:
                    pass
        return jsonify({'status': 'error',
                        'error': f'atomic rename failed (backups preserved): {exc}'}), 500

    # Day 95: the running server serves cultivars from an IN-MEMORY registry that is loaded
    # from disk once, at startup. Writing the file alone left the Composer/Events editor
    # (GET /cultivars/xml) on the old clip list until Flask was restarted. Refresh the
    # registry entry with the definition we just wrote (memory only; the file is already
    # written atomically above). Best effort: a failure here never fails the export.
    registry_refreshed = False
    try:
        from mccf_cultivar_lambda import cultivar_bp as _cbp
        _live = getattr(_cbp, 'registry', None)
        if _live is not None:
            _live._cultivars[cultivar_def.name] = cultivar_def
            registry_refreshed = True
    except Exception:
        registry_refreshed = False

    _expr_basename = os.path.basename(expressions_filepath)

    # Manifest write happens AFTER the atomic X3D rename succeeds — a manifest
    # describing a rig that didn't actually get saved (because the atomic write
    # failed and rolled back above) would be worse than no manifest at all, since
    # Composer would then believe rig content exists that isn't really there.
    # Not itself part of the atomic triple-write (manifest is discovery metadata,
    # not scene-critical content — an out-of-date-by-a-few-seconds manifest on a
    # write failure that's already been reported as an error is an acceptable gap,
    # a phantom rig claim is not) but still best-effort try/except so a manifest
    # write failure doesn't turn a successful export into a 500.
    try:
        if camera_rig is not None:
            _write_camera_rig_manifest(hanim_src, camera_rig, camera_rig_written)
    except OSError as exc:
        return jsonify({
            'status': 'ok',
            'hanim_path': f'/static/avatars/{os.path.basename(hanim_src)}',
            'cultivar_path': f'cultivars/cultivar_{cultivar_name}.xml',
            'expressions_path': f'/static/avatars/{_expr_basename}',
            'clips_written': clips_written,
            'routes_written': routes_written,
            'skin_updated': skin_updated,
            'expressions_written': expressions_written,
            'camera_rig_written': camera_rig_written,
            'camera_rig_manifest_warning': f'manifest write failed: {exc}',
            'warnings': clip_report['warnings'], 'loop_updated': clip_report['loop_updated'],
            'skipped': clip_report['skipped'],
            'clips_removed': clips_removed, 'registry_refreshed': registry_refreshed,
        })

    return jsonify({
        'status':               'ok',
        'hanim_path':           f'/static/avatars/{os.path.basename(hanim_src)}',
        'cultivar_path':        f'cultivars/cultivar_{cultivar_name}.xml',
        'expressions_path':     f'/static/avatars/{_expr_basename}',
        'clips_written':        clips_written,
        'routes_written':       routes_written,
        'skin_updated':         skin_updated,
        'camera_rig_written':   camera_rig_written,
        'displacers_updated':   displacers_updated,
        'expressions_written':  expressions_written,
        # Day 95: what the export did NOT do, and what it noticed
        'warnings':             clip_report['warnings'],
        'loop_updated':         clip_report['loop_updated'],
        'skipped':              clip_report['skipped'],
        'preexisting_problems': {k: len(v) for k, v in integrity_before.items() if v},
        'clips_removed':        clips_removed,        # cultivar entries deleted/renamed away
        'registry_refreshed':   registry_refreshed,   # running server's cultivar list updated (no restart)
    })


# ---------------------------------------------------------------------------
# GET /hanim/joints
# Day 27 — 2026-05-26
#
# Parse the HAnimJoint hierarchy from a stored HAnim X3D file and return
# a flat array of joint descriptors for the Pose/Gesture tab tree panel.
#
# Each entry: { name, def, center, parent, region }
#   name   — H-Anim 2.0 standard joint name (e.g. "l_hip")
#   def    — DEF attribute as written in the X3D file (e.g. "hanim_l_hip")
#   center — [x, y, z] float list from the center attribute (rest position)
#   parent — parent joint name, or null for humanoid_root
#   region — one of: spine | left_arm | right_arm | left_leg | right_leg | other
#
# Body region assignment uses H-Anim 2.0 standard joint name prefixes and
# the spine list from the spec (Section 4.2).
# ---------------------------------------------------------------------------

# H-Anim 2.0 spine joint names (humanoid_root through skull), hierarchy order.
_SPINE_JOINTS = {
    'humanoid_root', 'sacroiliac',
    'vl5','vl4','vl3','vl2','vl1',
    'vt12','vt11','vt10','vt9','vt8','vt7','vt6','vt5','vt4','vt3','vt2','vt1',
    'vc7','vc6','vc5','vc4','vc3','vc2','vc1',
    'skullbase','skull',
}


def _joint_region(name: str) -> str:
    """
    Classify a joint name into a body region string.
    Accepts HAnim 2.0 names (l_shoulder), Blender dot (shoulder.L),
    Blender underscore (shoulder_L), and gltf_hyphen (shoulder-L).
    Falls back to 'other' for IK/helper bones with no HAnim equivalent.
    """
    _ARM_KW = ('shoulder','elbow','radiocarpal','ulnocarpal',
               'midcarpal','carpometacarpal','metacarpophalangeal',
               'interphalangeal','carpal','wrist')
    _LEG_KW = ('hip','knee','talocrural','talocalcaneonavicular',
               'cuneonavicular','calcaneocuboid','transversetarsal',
               'tarsometatarsal','metatarsophalangeal','tarsal',
               'ankle','subtalar')

    # Try HAnim 2.0 classification first
    if name in _SPINE_JOINTS:
        return 'spine'
    if name.startswith('l_'):
        low = name[2:]
        if any(k in low for k in _LEG_KW): return 'left_leg'
        if any(k in low for k in _ARM_KW): return 'left_arm'
        return 'left_arm'
    if name.startswith('r_'):
        low = name[2:]
        if any(k in low for k in _LEG_KW): return 'right_leg'
        if any(k in low for k in _ARM_KW): return 'right_arm'
        return 'right_arm'

    # Not HAnim — try translating via _BLENDER_TO_HANIM
    import re as _re_region
    # Normalise to Blender dot lowercase for lookup
    nk = name.lower()
    # gltf_hyphen: shoulder-L -> shoulder.l
    nk = _re_region.sub(r'-([lr])$', lambda m: '.' + m.group(1), nk)
    nk = _re_region.sub(r'-(\d{2,3})', r'.\1', nk)
    nk = nk.replace('-', '_')
    # blender_under: shoulder_L -> shoulder.l
    nk = _re_region.sub(r'_([lr])$', lambda m: '.' + m.group(1), nk)

    hanim = _BLENDER_TO_HANIM.get(nk)
    if hanim:
        return _joint_region(hanim)  # recurse with canonical name

    # Mixamo names: mixamorig:RightArm etc.
    if name.lower().startswith('mixamorig:'):
        low = name[10:].lower()   # strip prefix
        _MIXAMO_SPINE_KW = ('hips','spine','neck','head')
        _MIXAMO_LEFT_ARM = ('leftshoulder','leftarm','leftforearm','lefthand',
                            'lefthandthumb','lefthandindex','lefthandmiddle',
                            'lefthandring','lefthandpinky')
        _MIXAMO_RIGHT_ARM = ('rightshoulder','rightarm','rightforearm','righthand',
                             'righthandthumb','righthandindex','righthandmiddle',
                             'righthandring','righthandpinky')
        _MIXAMO_LEFT_LEG = ('leftupleg','leftleg','leftfoot','lefttoebase')
        _MIXAMO_RIGHT_LEG = ('rightupleg','rightleg','rightfoot','righttoebase')
        if any(low.startswith(k) for k in _MIXAMO_SPINE_KW):   return 'spine'
        if any(low.startswith(k) for k in _MIXAMO_LEFT_ARM):   return 'left_arm'
        if any(low.startswith(k) for k in _MIXAMO_RIGHT_ARM):  return 'right_arm'
        if any(low.startswith(k) for k in _MIXAMO_LEFT_LEG):   return 'left_leg'
        if any(low.startswith(k) for k in _MIXAMO_RIGHT_LEG):  return 'right_leg'
        return 'other'

    # Spine keywords that appear in Blender names
    _SPINE_KW = ('hips','spine','chest','upper_chest','neck','head',
                 'breast','pelvis','torso')
    low = name.lower()
    if any(k in low for k in _SPINE_KW):
        return 'spine'

    return 'other'


def _parse_center(center_str: str) -> list:
    """Parse an X3D SFVec3f center attribute string to [x, y, z] floats."""
    try:
        parts = center_str.strip().split()
        if len(parts) == 3:
            return [round(float(p), 6) for p in parts]
    except (ValueError, AttributeError):
        pass
    return [0.0, 0.0, 0.0]


def _parse_rotation(rot_str: str) -> list:
    """Parse an X3D SFRotation string to [ax, ay, az, angle_radians]; identity if absent/invalid."""
    try:
        parts = (rot_str or '').strip().split()
        if len(parts) == 4:
            return [round(float(p), 6) for p in parts]
    except (ValueError, AttributeError):
        pass
    return [0.0, 0.0, 1.0, 0.0]


def _walk_joints(el, parent_name, joints: list) -> None:
    """
    Recursively walk the X3D element tree collecting HAnimJoint nodes
    in depth-first order.

    el          — current XML element (any tag)
    parent_name — DEF value of the enclosing HAnimJoint, or None
    joints      — accumulator list (mutated in place)

    Returns one dict per joint:
      name   — from the name= attribute (semantic, e.g. 'shoulder.L')
               falls back to DEF with hanim_/HAnimJoint_/Joint_ prefix stripped
      def    — exact DEF= attribute value (e.g. 'shoulder-L')
               this is what WireInterp_ names are built from and what
               _heJointMap keys on — must be preserved exactly
      region — derived from name (Blender dot names classify correctly)
    """
    tag = el.tag.split('}')[-1]

    if tag != 'HAnimJoint':
        for child in el:
            _walk_joints(child, parent_name, joints)
        return

    # Skip USE references
    if el.get('USE'):
        return

    def_val  = el.get('DEF', '')
    name_val = el.get('name', '')

    # name: prefer name= attr; fall back to DEF with common prefixes stripped
    if name_val:
        display_name = name_val
    else:
        display_name = def_val
        for prefix in ('hanim_', 'HAnimJoint_', 'Joint_'):
            if def_val.lower().startswith(prefix.lower()):
                display_name = def_val[len(prefix):]
                break

    joints.append({
        'name':   display_name,          # human-readable / name= attr
        'def':    def_val,               # exact DEF value — joint map key
        'center': _parse_center(el.get('center', '0 0 0')),
        # Day 95: the joint's REST rotation as authored in the file. Blender/Tripo rigs bake
        # bone orientation into it (Anna: 30 of 48 joints are non-zero, e.g. thighs 173 deg),
        # so the editor cannot assume "rest == [0,0,1,0]" the way an H-Anim-native rig allows.
        'rest':   _parse_rotation(el.get('rotation', '')),
        'parent': parent_name,
        'region': _joint_region(display_name),
    })

    # Recurse — pass DEF as parent context so parent field is consistent
    for child in el:
        _walk_joints(child, def_val, joints)


@hanim_bp.route('/hanim/joints', methods=['GET'])
def hanim_joints():
    """
    GET /hanim/joints?src=<hanim_src>

    Parse the HAnimJoint hierarchy from static/avatars/<hanim_src> and
    return a flat ordered array of joint descriptors for the pose tab
    tree panel.

    Query param:
      src — HAnim X3D filename (basename only, e.g. 'cindy_hanim.x3d')

    Response:
    {
      "joints": [
        {
          "name":   "humanoid_root",
          "def":    "hanim_humanoid_root",
          "center": [0.0, 0.9149, 0.0],
          "parent": null,
          "region": "spine"
        },
        ...
      ],
      "count": 146,
      "src":   "cindy_hanim.x3d"
    }

    Joints are returned depth-first (same order as in the X3D file).
    The tree panel reconstructs the hierarchy from the parent field.

    404 — file not found
    400 — src param missing
    500 — X3D parse error
    """
    src = request.args.get('src', '').strip()
    if not src:
        return jsonify({'error': 'src param required'}), 400

    filepath = _hanim_x3d_path(src)
    if not os.path.exists(filepath):
        return jsonify({'error': f'HAnim X3D not found: {os.path.basename(src)}'}), 404

    try:
        _, root = _parse_x3d_file(filepath)
    except Exception as exc:
        return jsonify({'error': f'X3D parse failed: {exc}'}), 500

    joints = []

    # Preferred entry point: HAnimHumanoid → skeleton subtree
    ns = _X3D_NS
    humanoid = root.find(f'.//{{{ns}}}HAnimHumanoid')
    if humanoid is None:
        humanoid = root.find('.//HAnimHumanoid')

    if humanoid is not None:
        # X3D 4.0: skeleton may be a named container child element
        skeleton_el = humanoid.find(f'{{{ns}}}skeleton')
        if skeleton_el is None:
            skeleton_el = humanoid.find('skeleton')
        start = skeleton_el if skeleton_el is not None else humanoid
        for child in start:
            _walk_joints(child, None, joints)
    else:
        # Fallback: walk entire document tree
        _walk_joints(root, None, joints)

    # ── Scan for TimeSensor nodes — playable clips ──────────────────────────
    # Skip WireTimer_ nodes — those are pose infrastructure, not animation clips
    #
    # Day 95 (S3): every entry now says whether it is REAL. `routes` = number of
    # fraction_changed ROUTEs leaving the timer; `hollow` = routes == 0 (a stub that
    # animates nothing — duplicates and leftovers of old exports; Anna has ~82 of them).
    # `exported_as` = the names a scene can IMPORT it under. The full list is still returned
    # (the wiring/ingest detection below relies on it); the editor filters on `hollow`.
    _routes_all = _collect_routes(root)
    _routed = {}
    for _r in _routes_all:
        if _r.get('fromField') == 'fraction_changed':
            _routed[_r.get('fromNode')] = _routed.get(_r.get('fromNode'), 0) + 1
    _exported = {}
    for _el in root.iter():
        if _tag_local(_el) == 'EXPORT' and _el.get('localDEF'):
            _exported.setdefault(_el.get('localDEF'), []).append(_el.get('AS') or _el.get('localDEF'))
    clips = []
    seen_defs = set()
    for tag in (f'{{{ns}}}TimeSensor', 'TimeSensor'):
        for el in root.iter(tag):
            def_val = el.get('DEF', '')
            if not def_val or def_val in seen_defs:
                continue
            if def_val.startswith('WireTimer_'):
                continue
            seen_defs.add(def_val)
            # Derive a human-readable name via the SAME normalization
            # _write_clip_nodes/hanim_ingest_mixamo already use
            # (_humanize_gesture_label), not a second, looser one —
            # this used to just use the raw description as-is
            # ('Armature|preset:biped:look around'), which meant a
            # clip discovered here and a clip already saved into a
            # cultivar's behavior_clips (always humanized, e.g.
            # 'Look Around') never matched as the same clip. That
            # mismatch is exactly what let _write_clip_nodes' new
            # real-animation match silently miss a clip whenever
            # Character Creator seeded _heClips straight from this
            # route instead of from a previously-saved cultivar.
            desc = el.get('description', '').strip()
            name = _humanize_gesture_label(desc, def_val)
            if not desc:
                # No description at all — _humanize_gesture_label
                # already falls back to def_val here; keep the old
                # 'clip N' cosmetic for a bare numeric suffix
                # ('Timer1' -> '1' -> 'clip 1') rather than showing
                # the raw DEF, same behavior as before this change.
                bare = def_val.replace('Timer', '').strip()
                if bare.isdigit():
                    name = f'clip {bare}'
            try:
                cycle = float(el.get('cycleInterval', 6.0))
            except (TypeError, ValueError):
                cycle = 6.0
            clips.append({
                'name':          name,
                'timerDEF':      def_val,
                'cycleInterval': cycle,
                # X3D's default for TimeSensor.loop is FALSE. This used to default to
                # 'true', so every timer with no loop attribute (Anna's Bow, Idle, Wait)
                # was reported — and shown in the editor — as looping when it isn't.
                'loop':          el.get('loop', 'false').lower() == 'true',
                'enabled':       el.get('enabled', 'false').lower() == 'true',
                'routes':        _routed.get(def_val, 0),
                'hollow':        _routed.get(def_val, 0) == 0,
                'exported_as':   _exported.get(def_val, []),
            })

    # ── Load joint map from cultivar if one is linked ────────────────────
    # Scan cultivars/ for a cultivar whose HAnimFigure src matches this avatar.
    # If found, return the JointMap so the editor can resolve group presets
    # without knowing the avatar's native joint naming convention.
    joint_map = {}
    cultivars_dir = os.path.join(_hanim_base_dir(), 'cultivars')
    avatar_basename = os.path.basename(src).lower()
    if os.path.isdir(cultivars_dir):
        for fname in os.listdir(cultivars_dir):
            if not fname.endswith('.xml'):
                continue
            cpath = os.path.join(cultivars_dir, fname)
            jm = _read_cultivar_joint_map(cpath)
            if jm:
                # Verify this cultivar's HAnimFigure points to our avatar
                try:
                    import xml.etree.ElementTree as _ET_jm
                    _root_jm = _ET_jm.parse(cpath).getroot()
                    fig = _root_jm.find('HAnimFigure')
                    if fig is not None and \
                       fig.get('src', '').lower() == avatar_basename:
                        joint_map = jm
                        break
                except Exception:
                    pass

    # ── Apply joint_map to get HAnim display names and correct regions ─────
    # For Mixamo avatars, DEF is 'mixamorig:RightArm' but joint_map maps it
    # to 'r_shoulder'. Apply that so the tree shows HAnim names and the
    # region filter buttons (L ARM, R LEG etc) work correctly.
    if joint_map:
        for j in joints:
            hanim_name = joint_map.get(j['def'])
            if hanim_name:
                j['name']   = hanim_name
                j['region'] = _joint_region(hanim_name)

    return jsonify({
        'joints':    joints,
        'count':     len(joints),
        'clips':     clips,
        'src':       os.path.basename(src),
        'joint_map': joint_map,
    })


@hanim_bp.route('/hanim/wire-joints', methods=['POST'])
def hanim_wire_joints():
    """
    POST /hanim/wire-joints
    Body: { hanim_src: str }

    For avatars that have HAnimJoint nodes but no animation infrastructure
    (no OrientationInterpolators, TimeSensors, or ROUTEs), this endpoint
    generates stub nodes for every joint so the SAI setJointRotation
    messages from the HAnim Editor have something to drive.

    Each joint gets:
      - OrientationInterpolator DEF="WireInterp_<jointDEF>"
          key="0 1"  keyValue="0 0 1 0  0 0 1 0"   (identity at both ends)
      - TimeSensor DEF="WireTimer_<jointDEF>"
          cycleInterval="1"  loop="true"  enabled="false"
      - ROUTE TimeSensor.fraction_changed → Interp.set_fraction
      - ROUTE Interp.value_changed        → Joint.rotation

    Joints that already have a wired interpolator (detected by scanning
    existing ROUTEs toNode → jointDEF, toField=rotation) are skipped —
    this is safe to call on a partially-wired file.

    Atomic write: .tmp file + os.replace().  .bak created first.

    Returns: { status, joints_wired, joints_skipped, hanim_path }
    """
    body      = request.get_json(silent=True) or {}
    hanim_src = (body.get('hanim_src') or '').strip()
    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400

    filepath = _hanim_x3d_path(hanim_src)
    if not os.path.exists(filepath):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404

    try:
        xml_decl, root = _parse_x3d_file(filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D parse failed: {exc}'}), 500

    ns = _X3D_NS

    # Collect all joint DEFs from the tree
    joint_defs = []
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if el.get('USE'):
                continue
            def_val = el.get('DEF', '').strip()
            if def_val:
                joint_defs.append(def_val)

    if not joint_defs:
        return jsonify({'status': 'error',
                        'error': 'No HAnimJoint DEF nodes found in file'}), 400

    # Find existing ROUTEs that already drive joint rotation — skip those joints
    already_wired = set()
    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        for el in root.iter(tag):
            if el.get('toField', '') == 'rotation':
                already_wired.add(el.get('toNode', ''))

    scene_el = _find_scene_el(root)
    if scene_el is None:
        return jsonify({'status': 'error',
                        'error': 'No <Scene> element in X3D file'}), 500

    # Strip existing ROUTEs (will be re-appended last per invariant)
    existing_routes = _collect_routes(root)
    _remove_routes(scene_el)

    # Build a lookup: def → rotation attribute string from the joint element
    joint_rot_map = {}
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if el.get('USE'):
                continue
            def_val = el.get('DEF', '').strip()
            rot     = el.get('rotation', '').strip()
            if def_val and rot:
                joint_rot_map[def_val] = rot

    new_routes = list(existing_routes)
    joints_wired   = 0
    joints_skipped = 0

    for jdef in joint_defs:
        if jdef in already_wired:
            joints_skipped += 1
            continue

        timer_def  = f'WireTimer_{jdef}'
        interp_def = f'WireInterp_{jdef}'

        # TimeSensor stub — enabled=false, never fires on load
        ts = _ET_hanim.SubElement(scene_el, f'{{{ns}}}TimeSensor')
        ts.set('DEF',           timer_def)
        ts.set('cycleInterval', '1')
        ts.set('loop',          'true')
        ts.set('enabled',       'false')

        # OrientationInterpolator — keyValue = joint's rest rotation at both ends.
        # Using rest rotation (not identity) means the stub is a no-op at fraction=0
        # and preserves the skeleton's rest pose on scene load.
        rest_rot = joint_rot_map.get(jdef, '0 0 1 0')
        parts = rest_rot.split()
        if len(parts) == 4:
            kv = ' '.join(parts) + '  ' + ' '.join(parts)
        else:
            kv = '0 0 1 0  0 0 1 0'

        interp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}OrientationInterpolator')
        interp.set('DEF',      interp_def)
        interp.set('key',      '0 1')
        interp.set('keyValue', kv)

        # ROUTEs
        new_routes.append({'fromNode': timer_def,  'fromField': 'fraction_changed',
                            'toNode':   interp_def, 'toField':   'set_fraction'})
        new_routes.append({'fromNode': interp_def, 'fromField': 'value_changed',
                            'toNode':   jdef,       'toField':   'rotation'})
        joints_wired += 1

    # Re-append all ROUTEs last — invariant
    for r_attrib in new_routes:
        re_el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}ROUTE')
        for k, v in r_attrib.items():
            re_el.set(k, v)

    # Atomic write
    try:
        _hanim_backup(filepath)
        out_text = _serialise_x3d(xml_decl, root)
        tmp_path = filepath + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(out_text)
        os.replace(tmp_path, filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'Write failed: {exc}'}), 500

    return jsonify({
        'status':        'ok',
        'joints_wired':  joints_wired,
        'joints_skipped': joints_skipped,
        'hanim_path':    os.path.basename(filepath),
    })


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# POST /hanim/normalize-joints
# Rewrite HAnimJoint DEF and name attributes to HAnim 2.0 standard names.
# Run once on any Blender-exported avatar before using it in MCCF.
# ---------------------------------------------------------------------------

# Blender armature bone name → HAnim 2.0 joint name
# Keys: Blender DEF or name values (lowercased for lookup)
# Values: authoritative HAnim 2.0 name (ISO/IEC 19774 / X3D spec)
_BLENDER_TO_HANIM = {
    # ── Spine / torso ────────────────────────────────────────────────────
    'hips':         'humanoid_root',
    'spine':        'vl5',
    'chest':        'vt12',
    'upper_chest':  'vt6',
    'neck':         'vc4',
    'head':         'skullbase',

    # ── Left leg ─────────────────────────────────────────────────────────
    'thigh.l':      'l_hip',      'thigh_l':      'l_hip',
    'shin.l':       'l_knee',     'shin_l':       'l_knee',
    'foot.l':       'l_talocrural', 'foot_l':     'l_talocrural',
    'toe.l':        'l_metatarsophalangeal_2', 'toe_l': 'l_metatarsophalangeal_2',

    # ── Right leg ────────────────────────────────────────────────────────
    'thigh.r':      'r_hip',      'thigh_r':      'r_hip',
    'shin.r':       'r_knee',     'shin_r':       'r_knee',
    'foot.r':       'r_talocrural', 'foot_r':     'r_talocrural',
    'toe.r':        'r_metatarsophalangeal_2', 'toe_r': 'r_metatarsophalangeal_2',

    # ── Left arm ─────────────────────────────────────────────────────────
    'shoulder.l':   'l_sternoclavicular', 'shoulder_l':  'l_sternoclavicular',
    'upper_arm.l':  'l_shoulder',         'upper_arm_l': 'l_shoulder',
    'forearm.l':    'l_elbow',            'forearm_l':   'l_elbow',
    'hand.l':       'l_radiocarpal',      'hand_l':      'l_radiocarpal',

    # ── Right arm ────────────────────────────────────────────────────────
    'shoulder.r':   'r_sternoclavicular', 'shoulder_r':  'r_sternoclavicular',
    'upper_arm.r':  'r_shoulder',         'upper_arm_r': 'r_shoulder',
    'forearm.r':    'r_elbow',            'forearm_r':   'r_elbow',
    'hand.r':       'r_radiocarpal',      'hand_r':      'r_radiocarpal',

    # ── Left hand ────────────────────────────────────────────────────────
    'palm.01.l':    'l_carpometacarpal_1',
    'palm.02.l':    'l_midcarpal_2',
    'palm.03.l':    'l_midcarpal_3',
    'palm.04.l':    'l_midcarpal_4_5',
    'thumb.01.l':   'l_carpometacarpal_1',
    'thumb.02.l':   'l_metacarpophalangeal_1',
    'thumb.03.l':   'l_carpal_interphalangeal_1',
    'f_index.01.l': 'l_metacarpophalangeal_2',
    'f_index.02.l': 'l_carpal_proximal_interphalangeal_2',
    'f_index.03.l': 'l_carpal_distal_interphalangeal_2',
    'f_middle.01.l':'l_metacarpophalangeal_3',
    'f_middle.02.l':'l_carpal_proximal_interphalangeal_3',
    'f_middle.03.l':'l_carpal_distal_interphalangeal_3',
    'f_ring.01.l':  'l_metacarpophalangeal_4',
    'f_ring.02.l':  'l_carpal_proximal_interphalangeal_4',
    'f_ring.03.l':  'l_carpal_distal_interphalangeal_4',
    'f_pinky.01.l': 'l_metacarpophalangeal_5',
    'f_pinky.02.l': 'l_carpal_proximal_interphalangeal_5',
    'f_pinky.03.l': 'l_carpal_distal_interphalangeal_5',

    # ── Right hand ───────────────────────────────────────────────────────
    'palm.01.r':    'r_carpometacarpal_1',
    'palm.02.r':    'r_midcarpal_2',
    'palm.03.r':    'r_midcarpal_3',
    'palm.04.r':    'r_midcarpal_4_5',
    'thumb.01.r':   'r_carpometacarpal_1',
    'thumb.02.r':   'r_metacarpophalangeal_1',
    'thumb.03.r':   'r_carpal_interphalangeal_1',
    'f_index.01.r': 'r_metacarpophalangeal_2',
    'f_index.02.r': 'r_carpal_proximal_interphalangeal_2',
    'f_index.03.r': 'r_carpal_distal_interphalangeal_2',
    'f_middle.01.r':'r_metacarpophalangeal_3',
    'f_middle.02.r':'r_carpal_proximal_interphalangeal_3',
    'f_middle.03.r':'r_carpal_distal_interphalangeal_3',
    'f_ring.01.r':  'r_metacarpophalangeal_4',
    'f_ring.02.r':  'r_carpal_proximal_interphalangeal_4',
    'f_ring.03.r':  'r_carpal_distal_interphalangeal_4',
    'f_pinky.01.r': 'r_metacarpophalangeal_5',
    'f_pinky.02.r': 'r_carpal_proximal_interphalangeal_5',
    'f_pinky.03.r': 'r_carpal_distal_interphalangeal_5',
}


@hanim_bp.route('/hanim/normalize-joints', methods=['POST'])
def hanim_normalize_joints():
    """
    POST /hanim/normalize-joints
    Body: { hanim_src: str }

    Rewrite HAnimJoint DEF and name attributes from Blender/pipeline
    naming to authoritative HAnim 2.0 standard names (ISO/IEC 19774).

    Also rewrites ROUTE fromNode/toNode references that target renamed
    joints so existing animation infrastructure stays valid.

    Joints not in the mapping table are left unchanged and reported in
    'unmapped' — typically IK/helper bones with no HAnim equivalent.

    Atomic write: .tmp + os.replace(). .bak created first.

    Returns:
    {
      status, hanim_path,
      renamed:        [ {old_def, new_def} ],
      unmapped:       [ def_value ],
      routes_updated: int
    }
    """
    import re as _re_norm

    body      = request.get_json(silent=True) or {}
    hanim_src = (body.get('hanim_src') or '').strip()
    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400

    filepath = _hanim_x3d_path(hanim_src)
    if not os.path.exists(filepath):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404

    try:
        xml_decl, root = _parse_x3d_file(filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D parse failed: {exc}'}), 500

    ns = _X3D_NS

    # Build rename map: old_def → new_hanim_name
    rename_map = {}
    unmapped   = []

    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if el.get('USE'):
                continue
            old_def  = el.get('DEF',  '').strip()
            old_name = el.get('name', '').strip()
            if not old_def:
                continue

            # Try name attr first (more semantic), then DEF attr
            lookup = (old_name or old_def).lower()
            new_name = _BLENDER_TO_HANIM.get(lookup) or _BLENDER_TO_HANIM.get(old_def.lower())

            if new_name is None:
                # Already a valid HAnim 2.0 name (lowercase + underscores + digits)?
                if _re_norm.match(r'^[a-z][a-z0-9_]*$', old_def):
                    continue   # looks like HAnim already — leave it
                unmapped.append(old_def)
                continue

            if new_name == old_def and new_name == old_name:
                continue   # already correct

            rename_map[old_def] = new_name

    # Apply renames to HAnimJoint DEF/name and USE references
    renamed = []
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            use_val = el.get('USE', '')
            if use_val:
                if use_val in rename_map:
                    el.set('USE', rename_map[use_val])
                continue
            old_def = el.get('DEF', '').strip()
            if old_def in rename_map:
                new_name = rename_map[old_def]
                el.set('DEF',  new_name)
                el.set('name', new_name)
                renamed.append({'old_def': old_def, 'new_def': new_name})

    # Update ROUTE fromNode/toNode references for renamed joints
    routes_updated = 0
    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        for el in root.iter(tag):
            for attr in ('fromNode', 'toNode'):
                val = el.get(attr, '')
                if val in rename_map:
                    el.set(attr, rename_map[val])
                    routes_updated += 1

    # Strip any stale WireTimer_* / WireInterp_* nodes and their ROUTEs.
    # These were generated by a previous wire-joints run and reference the
    # old (pre-normalize) joint names — they must be removed so wire-joints
    # can re-run cleanly with the correct HAnim 2.0 names.
    scene_el = _find_scene_el(root)
    wire_stripped = 0
    if scene_el is not None:
        to_remove = []
        for child in list(scene_el):
            tag = child.tag.split('}')[-1]
            def_val = child.get('DEF', '')
            if tag in ('TimeSensor', 'OrientationInterpolator') and \
               (def_val.startswith('WireTimer_') or def_val.startswith('WireInterp_')):
                to_remove.append(child)
            elif tag == 'ROUTE':
                fn = child.get('fromNode', '')
                tn = child.get('toNode', '')
                if fn.startswith('WireTimer_') or fn.startswith('WireInterp_') or \
                   tn.startswith('WireTimer_') or tn.startswith('WireInterp_'):
                    to_remove.append(child)
        for el in to_remove:
            scene_el.remove(el)
        wire_stripped = len(to_remove)

    nothing_changed = (not renamed and wire_stripped == 0)
    if nothing_changed:
        return jsonify({
            'status':         'ok',
            'hanim_path':     os.path.basename(filepath),
            'renamed':        [],
            'unmapped':       unmapped,
            'routes_updated': 0,
            'wire_stripped':  0,
            'note':           'No changes needed — file may already be normalized',
        })

    # Atomic write
    try:
        _hanim_backup(filepath)
        out_text = _serialise_x3d(xml_decl, root)
        tmp_path = filepath + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(out_text)
        os.replace(tmp_path, filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'Write failed: {exc}'}), 500

    return jsonify({
        'status':          'ok',
        'hanim_path':      os.path.basename(filepath),
        'renamed':         renamed,
        'unmapped':        unmapped,
        'routes_updated':  routes_updated,
        'wire_stripped':   wire_stripped,
    })


# ---------------------------------------------------------------------------
# POST /hanim/ingest
# Day 35 — 2026-06-02
#
# Avatar pipeline ingest: detect joint naming convention, build a joint→HAnim
# 2.0 translation map, write it into the cultivar XML as <JointMap>, then wire
# all joints (TimeSensor + OrientationInterpolator + ROUTEs with rest-rotation
# keyValues).
#
# The X3D file is NEVER renamed.  The JointMap is a translation layer stored
# in the cultivar, not surgery on the geometry file.  Skin weights remain valid
# because the joint DEF names never change.
#
# Naming conventions detected:
#   blender_dot   — Blender default: "thigh.L", "upper_arm.R", "f_index.01.L"
#   blender_under — Blender with underscores: "thigh_L", "upper_arm_R"
#   mixamo        — Mixamo: "mixamorig:LeftUpLeg", "mixamorig:RightArm"
#   hanim         — Already HAnim 2.0: "l_hip", "r_shoulder"
#   unknown       — None of the above
#
# Returns:
# {
#   status, hanim_path, cultivar_path,
#   convention,           # detected naming convention string
#   joints_mapped,        # count with a known HAnim 2.0 equivalent
#   joints_unmapped,      # count with no known equivalent (IK/helper bones)
#   joints_wired,         # new wire stubs added
#   joints_skipped,       # joints already wired (skipped)
#   joint_map             # { def: hanim_name, ... }  (full map written to cultivar)
# }
# ---------------------------------------------------------------------------

def _detect_naming_convention(joint_defs: list) -> str:
    """
    Heuristic: inspect a sample of joint DEF values and return the most likely
    naming convention.
    """
    dot_count   = sum(1 for d in joint_defs if '.' in d)
    colon_count = sum(1 for d in joint_defs if ':' in d)
    # gltf_hyphen: X_ITE saves glTF joints with hyphens and skeletalConfiguration='GLTF'
    # Pattern: ends with -L or -R, or has -NN- numeric segments
    import re as _re_detect
    hyphen_count = sum(1 for d in joint_defs
                       if _re_detect.search(r'-[LR]$|-\d{2}', d))
    hanim_count = sum(1 for d in joint_defs
                      if d.lower() in _HANIM_KNOWN_NAMES or
                         any(d.lower().startswith(p) for p in ('l_','r_','humanoid_','skullbase')))
    n = max(len(joint_defs), 1)
    if colon_count / n > 0.3:
        return 'mixamo'
    if hyphen_count / n > 0.2:
        return 'gltf_hyphen'
    if dot_count / n > 0.2:
        return 'blender_dot'
    if hanim_count / n > 0.5:
        return 'hanim'
    # Check for underscore-suffix pattern: "thigh_L", "upper_arm_R"
    under_suffix = sum(1 for d in joint_defs if d.endswith('_L') or d.endswith('_R'))
    if under_suffix / n > 0.2:
        return 'blender_under'
    return 'unknown'


# Known HAnim 2.0 names used by the convention detector
_HANIM_KNOWN_NAMES = set(_SPINE_JOINTS) | {
    'l_hip','r_hip','l_knee','r_knee','l_talocrural','r_talocrural',
    'l_shoulder','r_shoulder','l_elbow','r_elbow','l_radiocarpal','r_radiocarpal',
    'l_sternoclavicular','r_sternoclavicular',
}


def _build_joint_map(joint_defs: list, convention: str) -> dict:
    """
    Build a mapping { def_value: hanim_2_0_name } for all joints that have a
    known HAnim equivalent.  Uses _BLENDER_TO_HANIM for Blender conventions and
    a Mixamo table for Mixamo rigs.  Joints with no mapping are omitted.
    """
    _MIXAMO_TO_HANIM = {
        'mixamorig:hips':               'humanoid_root',
        'mixamorig:spine':              'vl5',
        'mixamorig:spine1':             'vt12',
        'mixamorig:spine2':             'vt6',
        'mixamorig:neck':               'vc4',
        'mixamorig:head':               'skullbase',
        'mixamorig:leftupleg':          'l_hip',
        'mixamorig:leftleg':            'l_knee',
        'mixamorig:leftfoot':           'l_talocrural',
        'mixamorig:lefttoebase':        'l_metatarsophalangeal_2',
        'mixamorig:rightupleg':         'r_hip',
        'mixamorig:rightleg':           'r_knee',
        'mixamorig:rightfoot':          'r_talocrural',
        'mixamorig:righttoebase':       'r_metatarsophalangeal_2',
        'mixamorig:leftshoulder':       'l_sternoclavicular',
        'mixamorig:leftarm':            'l_shoulder',
        'mixamorig:leftforearm':        'l_elbow',
        'mixamorig:lefthand':           'l_radiocarpal',
        'mixamorig:rightshoulder':      'r_sternoclavicular',
        'mixamorig:rightarm':           'r_shoulder',
        'mixamorig:rightforearm':       'r_elbow',
        'mixamorig:righthand':          'r_radiocarpal',
        'mixamorig:lefthandthumb1':     'l_carpometacarpal_1',
        'mixamorig:lefthandthumb2':     'l_metacarpophalangeal_1',
        'mixamorig:lefthandthumb3':     'l_carpal_interphalangeal_1',
        'mixamorig:lefthandindex1':     'l_metacarpophalangeal_2',
        'mixamorig:lefthandindex2':     'l_carpal_proximal_interphalangeal_2',
        'mixamorig:lefthandindex3':     'l_carpal_distal_interphalangeal_2',
        'mixamorig:lefthandmiddle1':    'l_metacarpophalangeal_3',
        'mixamorig:lefthandmiddle2':    'l_carpal_proximal_interphalangeal_3',
        'mixamorig:lefthandmiddle3':    'l_carpal_distal_interphalangeal_3',
        'mixamorig:lefthandring1':      'l_metacarpophalangeal_4',
        'mixamorig:lefthandring2':      'l_carpal_proximal_interphalangeal_4',
        'mixamorig:lefthandring3':      'l_carpal_distal_interphalangeal_4',
        'mixamorig:lefthandpinky1':     'l_metacarpophalangeal_5',
        'mixamorig:lefthandpinky2':     'l_carpal_proximal_interphalangeal_5',
        'mixamorig:lefthandpinky3':     'l_carpal_distal_interphalangeal_5',
        'mixamorig:righthandthumb1':    'r_carpometacarpal_1',
        'mixamorig:righthandthumb2':    'r_metacarpophalangeal_1',
        'mixamorig:righthandthumb3':    'r_carpal_interphalangeal_1',
        'mixamorig:righthandindex1':    'r_metacarpophalangeal_2',
        'mixamorig:righthandindex2':    'r_carpal_proximal_interphalangeal_2',
        'mixamorig:righthandindex3':    'r_carpal_distal_interphalangeal_2',
        'mixamorig:righthandmiddle1':   'r_metacarpophalangeal_3',
        'mixamorig:righthandmiddle2':   'r_carpal_proximal_interphalangeal_3',
        'mixamorig:righthandmiddle3':   'r_carpal_distal_interphalangeal_3',
        'mixamorig:righthandring1':     'r_metacarpophalangeal_4',
        'mixamorig:righthandring2':     'r_carpal_proximal_interphalangeal_4',
        'mixamorig:righthandring3':     'r_carpal_distal_interphalangeal_4',
        'mixamorig:righthandpinky1':    'r_metacarpophalangeal_5',
        'mixamorig:righthandpinky2':    'r_carpal_proximal_interphalangeal_5',
        'mixamorig:righthandpinky3':    'r_carpal_distal_interphalangeal_5',
    }

    result = {}
    for def_val in joint_defs:
        key = def_val.lower()
        if convention == 'mixamo':
            hanim_name = _MIXAMO_TO_HANIM.get(key)
        elif convention == 'gltf_hyphen':
            # X_ITE glTF→X3D save uses hyphens: 'upper-arm-L', 'f-index-01-L'
            # Normalize to Blender dot notation for lookup: 'upper_arm.l', 'f_index.01.l'
            import re as _re_gh
            nk = key
            nk = _re_gh.sub(r'-([lr])$', lambda m: '.' + m.group(1), nk)  # -L/-R suffix
            nk = _re_gh.sub(r'-(\d{2,3})', r'.\1', nk)  # -01 -02 -> .01 .02
            nk = nk.replace('-', '_')                    # remaining hyphens -> underscores
            hanim_name = _BLENDER_TO_HANIM.get(nk)
        elif convention in ('blender_dot', 'blender_under', 'unknown'):
            hanim_name = _BLENDER_TO_HANIM.get(key)
        elif convention == 'hanim':
            # Already HAnim — map def to itself (strip hanim_ prefix if present)
            if key.startswith('hanim_'):
                hanim_name = key[6:]
            elif key in _HANIM_KNOWN_NAMES or key in _SPINE_JOINTS:
                hanim_name = key
            else:
                hanim_name = None
        else:
            hanim_name = _BLENDER_TO_HANIM.get(key)

        if hanim_name:
            result[def_val] = hanim_name

    return result


def _read_cultivar_joint_map(cultivar_path: str) -> dict:
    """
    Read <JointMap> from a cultivar XML file and return { def: hanim_name }.
    Returns empty dict if file missing, JointMap absent, or any parse error.
    """
    if not os.path.exists(cultivar_path):
        return {}
    try:
        import xml.etree.ElementTree as _ET
        tree = _ET.parse(cultivar_path)
        root = tree.getroot()
        jm_el = root.find('JointMap')
        if jm_el is None:
            return {}
        result = {}
        for j in jm_el.findall('Joint'):
            def_val  = j.get('def', '').strip()
            hanim    = j.get('hanim', '').strip()
            if def_val and hanim:
                result[def_val] = hanim
        return result
    except Exception:
        return {}


def _write_cultivar_joint_map(cultivar_path: str, joint_map: dict,
                               hanim_src: str, convention: str) -> None:
    """
    Upsert <JointMap convention="..."> and <HAnimFigure src="..."> into a
    cultivar XML file.  Atomic write via .tmp + os.replace().

    Preserves all other elements in the file.  If JointMap already exists
    it is replaced entirely.  HAnimFigure src attribute is updated.
    """
    import xml.etree.ElementTree as _ET

    _CULTIVAR_NS = 'http://mccf.artistinprocess.com/cultivar/v3'
    _ET.register_namespace('', _CULTIVAR_NS)  # suppress ns0: prefixes on serialize

    tree = _ET.parse(cultivar_path)
    root = tree.getroot()

    # Detect namespace prefix for find() — works with or without xmlns
    _ns_tag = lambda tag: (
        f'{{{_CULTIVAR_NS}}}{tag}'
        if root.tag.startswith('{') else tag
    )

    # Remove stale JointMap if present (with or without namespace)
    for _jm_tag in (_ns_tag('JointMap'), 'JointMap'):
        old_jm = root.find(_jm_tag)
        if old_jm is not None:
            root.remove(old_jm)
            break

    # Build new JointMap element
    jm_el = _ET.Element('JointMap')
    jm_el.set('convention', convention)
    for def_val, hanim_name in sorted(joint_map.items()):
        j = _ET.SubElement(jm_el, 'Joint')
        j.set('def',   def_val)
        j.set('hanim', hanim_name)

    # Upsert HAnimFigure — replace ALL existing HAnimFigure elements with a
    # single fresh one.
    #
    # Previously: `root.find(_ns_tag('HAnimFigure')) or root.find('HAnimFigure')`.
    # ElementTree Elements are falsy whenever they have zero children,
    # regardless of whether find() matched — and a leaf, attribute-only
    # element like <HAnimFigure src="..."/> always has zero children. So
    # that `or` always fell through to the second find() (which then failed
    # for the same namespace-unaware reason as bug #3's <Animations> lookup),
    # leaving fig_el always None. Every call therefore appended a fresh
    # <HAnimFigure> without ever removing the old one(s) -- confirmed via a
    # real duplicate-laden cultivar file: 5 -> 6 -> 7 accumulating across
    # three consecutive ingest runs. Fixed by unconditionally removing every
    # existing HAnimFigure (namespaced or not) before appending exactly one
    # -- idempotent, and self-heals any duplicates already on disk, same
    # dedup-on-write approach already used for <Animations>/<Behaviors>.
    for _fig_tag in (_ns_tag('HAnimFigure'), 'HAnimFigure'):
        for old_fig in list(root.findall(_fig_tag)):
            root.remove(old_fig)
    fig_el = _ET.Element('HAnimFigure')
    fig_el.set('src', 'avatars/' + os.path.basename(hanim_src))
    root.append(fig_el)

    # Append JointMap after HAnimFigure
    root.append(jm_el)

    _ET.indent(root, space='  ')
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + \
               _ET.tostring(root, encoding='unicode')

    tmp = cultivar_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(xml_text)
    os.replace(tmp, cultivar_path)


# The old avatar-specific facial-morph pipeline (fix-face-coords,
# save-face-morph, inject-face-aus, get-face-morph-status) lived here.
# It hand-wrote per-region Coordinate nodes and CoordinateInterpolator
# ("AnimationAdapter_<region>") ROUTEs to fake displacement, because at
# the time nobody had confirmed HAnimDisplacer.weight could be driven
# directly and sparsely against HAnimHumanoid.skinCoord. That's now
# confirmed (see SEED_facial_displacer_breakthrough.md) and real AU
# vertex deltas are extracted straight from Blender's shape keys via
# glTF export, so this endpoint group is removed rather than kept as
# dead weight. _update_displacer_weights() above and the live preview
# driver in avatar_preview() are the spec-compliant replacement.


# ---------------------------------------------------------------------------
# /hanim/build-displacers — the general-purpose version of the one-off
# script that built Anna's first 9 real HAnimDisplacer nodes. That build
# required a conversation because the joint mapping (which AU attaches to
# which joint, split by side or single) was worked out by hand, against
# Anna's specific rig, in-session. The mapping logic itself was never
# avatar-specific reasoning, though — it's a small set of naming rules
# ("brow AUs want an eyebrow joint if one exists", "otherwise fall back to
# Head") that apply to any avatar's real joint list. This endpoint makes
# that rule set a permanent, reusable part of the pipeline, so building or
# rebuilding an avatar's displacers after a Blender pass doesn't require a
# session with Claude every time — same self-service spirit as the
# Dialogue Editor's "Generate improv lines" / "Run Arc" split.
# ---------------------------------------------------------------------------

# (au_name_substring, joint_hint) — first match wins, checked top to bottom.
# joint_hint of 'eyebrow'/'eyelid'/'eyeball' means "split by side if both
# l_<hint>_joint and r_<hint>_joint exist on this avatar; otherwise fall
# through to the Head default below." joint_hint of a literal joint name
# (e.g. 'temporomandibular') means "single displacer on that joint if it
# exists; otherwise fall through."
_AU_JOINT_RULES = [
    ('InnerBrowRaiser',   'eyebrow'),
    ('OuterBrowRaiser',   'eyebrow'),
    ('BrowLowerer',       'eyebrow'),
    ('UpperLidRaiser',    'eyelid'),
    ('LidTightener',      'eyelid'),
    ('LidDroop',          'eyelid'),
    ('Squint',            'eyelid'),
    ('Slit',              'eyelid'),
    ('Blink',             'eyelid'),
    ('Wink',              'eyelid'),
    ('EyesClosed',        'eyelid'),
    ('JawDrop',           'temporomandibular'),
    ('MouthStretch',      'temporomandibular'),
]
_AU_JOINT_FALLBACK = 'Head'


def _hanim_discover_joints(content: str) -> dict:
    """
    Scan an X3D file's text for every real HAnimJoint's name and X
    translation. Returns {joint_name: x_translation_or_None}. Used to (a)
    know which joints this specific avatar actually has, and (b) derive
    the left/right sign convention from the avatar's own rig rather than
    assuming it matches any other avatar's (confirmed for Anna: l_ joints
    sit at negative X, r_ joints at positive X — but that's a fact about
    her rig, not a rule to hardcode for everyone).
    """
    joints = {}
    import re as _re2
    # Two-step, not one combined regex: a single regex with an optional
    # group preceded by a lazy quantifier will happily skip the optional
    # group even when it's present later in the string (confirmed by
    # testing against a real joint tag — this is exactly that trap, not
    # hypothetical). Capture each full opening tag first, then search
    # for translation within that known-bounded substring.
    for m in _re2.finditer(r'<HAnimJoint\b[^>]*?/?>', content, _re2.DOTALL):
        tag = m.group(0)
        name_m = _re2.search(r'name="([^"]+)"', tag)
        if not name_m:
            continue
        name = name_m.group(1)
        trans_m = _re2.search(r'translation="([^"]*)"', tag)
        x = None
        if trans_m:
            parts = trans_m.group(1).split()
            if parts:
                try: x = float(parts[0])
                except ValueError: x = None
        joints[name] = x
    return joints


def _hanim_resolve_au_joint(au_name: str, available_joints: dict) -> dict:
    """
    Decide where a given AU's displacer(s) should attach on THIS avatar's
    actual rig. Returns one of:
      {'mode': 'split', 'l_joint': ..., 'r_joint': ...}
      {'mode': 'single', 'joint': ...}
      {'mode': 'unavailable'}  — no suitable joint exists at all, not even
                                  the Head fallback (shouldn't normally
                                  happen, but not assumed impossible)
    """
    hint = None
    for substr, h in _AU_JOINT_RULES:
        if substr in au_name:
            hint = h
            break

    if hint in ('eyebrow', 'eyelid', 'eyeball'):
        l_name, r_name = f'l_{hint}_joint', f'r_{hint}_joint'
        if l_name in available_joints and r_name in available_joints:
            return {'mode': 'split', 'l_joint': l_name, 'r_joint': r_name}
        # fall through to Head if this avatar doesn't have the pair
    elif hint and hint in available_joints:
        return {'mode': 'single', 'joint': hint}
        # (temporomandibular case — falls through to Head if absent)

    if _AU_JOINT_FALLBACK in available_joints:
        return {'mode': 'single', 'joint': _AU_JOINT_FALLBACK}
    return {'mode': 'unavailable'}


def _hanim_build_displacer_xml(def_name: str, indices: list, deltas_by_idx: dict) -> str:
    coord_index = ' '.join(str(i) for i in indices)
    disp_parts = []
    for i in indices:
        dx, dy, dz = deltas_by_idx[i]
        disp_parts.append(f'{dx!r} {dy!r} {dz!r}')
    displacements = ' '.join(disp_parts)
    return (f'<HAnimDisplacer DEF="{def_name}" name="{def_name}" '
            f'coordIndex="{coord_index}" displacements="{displacements}" weight="0" />')


def _hanim_remove_existing_displacer(content: str, def_name: str) -> str:
    """Idempotency: strip any prior displacer with this exact DEF before
    inserting a fresh one, so rebuilding an AU (e.g. after a Blender
    smoothing pass) never leaves a stale duplicate behind."""
    import re as _re2
    pattern = r'\s*<HAnimDisplacer DEF="' + _re2.escape(def_name) + r'"[^>]*?/>'
    return _re2.sub(pattern, '', content, count=1, flags=_re2.DOTALL)


def _hanim_insert_into_joint(content: str, joint_name: str, children_xml: str) -> str:
    """Insert children_xml as the first child of the named HAnimJoint,
    whether it's currently self-closing or already has children. Raises
    ValueError if the joint isn't found (caller decides how to report it,
    rather than this failing silently)."""
    import re as _re2
    m = _re2.search(r'<HAnimJoint[^>]*name="' + _re2.escape(joint_name) + r'"[^>]*?(/?)>',
                     content, _re2.DOTALL)
    if not m:
        raise ValueError(f'joint not found: {joint_name}')
    matched_text = m.group(0)
    self_closing = m.group(1) == '/'
    indent = '\n      '
    if self_closing:
        new_text = matched_text[:-2] + '>' + indent + children_xml + '\n    </HAnimJoint>'
    else:
        new_text = matched_text + indent + children_xml
    if content.count(matched_text) != 1:
        raise ValueError(f'joint tag for {joint_name!r} is not uniquely matchable — refusing to guess')
    return content.replace(matched_text, new_text, 1)


@hanim_bp.route('/hanim/build-displacers', methods=['POST'])
def hanim_build_displacers():
    """
    POST /hanim/build-displacers

    General-purpose version of the script that built Anna's first 9 real
    displacers — same convention (<AUName>_displacer /
    <AUName>_l_displacer / <AUName>_r_displacer), same joint-mapping
    rules, but auto-detecting which joints THIS avatar actually has
    rather than assuming any specific rig. Idempotent: rebuilding an AU
    that already exists replaces it cleanly rather than duplicating it,
    so this is also the right call after a Blender smoothing pass on an
    existing AU, not just for building new ones.

    Request body:
    {
      "hanim_src":   "Anna_displacer_test2.x3d",   // resolved under static/avatars/
      "au_deltas":   { "AU12_LipCornerPuller": {"1570": [dx,dy,dz], ...}, ... },
      "base_mesh":   [[x,y,z], ...]                 // rest-pose points, same
                                                      // vertex numbering as
                                                      // au_deltas' keys
    }

    Only the AUs present in "au_deltas" are touched — an existing avatar
    with 9 displacers, given just an updated AU12 entry, gets exactly
    AU12 rebuilt and everything else left alone.

    Response:
    {
      "status": "ok",
      "built": [ {"au": "AU12_LipCornerPuller", "mode": "single",
                  "joint": "Head", "vertex_count": 443}, ... ],
      "skipped": [ {"au": "...", "reason": "no suitable joint found"} ]
    }
    """
    data = request.get_json() or {}
    hanim_src = data.get('hanim_src', '')
    au_deltas = data.get('au_deltas') or {}
    base_mesh = data.get('base_mesh') or []

    if not hanim_src:
        return jsonify({'error': 'hanim_src required'}), 400
    if not au_deltas:
        return jsonify({'error': 'au_deltas required (at least one AU)'}), 400
    if not base_mesh:
        return jsonify({'error': 'base_mesh required — needed for left/right splitting'}), 400

    filepath = _hanim_x3d_path(hanim_src)
    if not os.path.exists(filepath):
        return jsonify({'error': f'avatar file not found: {hanim_src}'}), 404

    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    available_joints = _hanim_discover_joints(content)
    built, skipped = [], []

    for au_name, verts in au_deltas.items():
        placement = _hanim_resolve_au_joint(au_name, available_joints)
        deltas_by_idx = {int(k): v for k, v in verts.items()}

        if placement['mode'] == 'unavailable':
            skipped.append({'au': au_name, 'reason': 'no suitable joint found on this avatar, not even Head'})
            continue

        try:
            if placement['mode'] == 'split':
                # Derive which side of x=0 is actually "left" from this
                # avatar's own l_<hint>_joint translation, rather than
                # assuming negative-x=left holds for every rig. True for
                # Anna (confirmed: l_eyebrow_joint sits at x=-0.017) but
                # that's a fact about her rig, not a rule to hardcode.
                l_joint_x = available_joints.get(placement['l_joint'])
                left_is_negative = (l_joint_x is None) or (l_joint_x < 0)
                left_idx, right_idx = [], []
                for k in verts:
                    idx = int(k)
                    x = base_mesh[idx][0] if idx < len(base_mesh) else 0.0
                    is_left = (x < 0) if left_is_negative else (x >= 0)
                    (left_idx if is_left else right_idx).append(idx)

                l_def = f'{au_name}_l_displacer'
                r_def = f'{au_name}_r_displacer'
                content = _hanim_remove_existing_displacer(content, l_def)
                content = _hanim_remove_existing_displacer(content, r_def)
                content = _hanim_insert_into_joint(
                    content, placement['l_joint'],
                    _hanim_build_displacer_xml(l_def, left_idx, deltas_by_idx))
                content = _hanim_insert_into_joint(
                    content, placement['r_joint'],
                    _hanim_build_displacer_xml(r_def, right_idx, deltas_by_idx))
                built.append({'au': au_name, 'mode': 'split',
                              'l_joint': placement['l_joint'], 'r_joint': placement['r_joint'],
                              'l_vertex_count': len(left_idx), 'r_vertex_count': len(right_idx)})
            else:
                def_name = f'{au_name}_displacer'
                idx_list = [int(k) for k in verts]
                content = _hanim_remove_existing_displacer(content, def_name)
                content = _hanim_insert_into_joint(
                    content, placement['joint'],
                    _hanim_build_displacer_xml(def_name, idx_list, deltas_by_idx))
                built.append({'au': au_name, 'mode': 'single',
                              'joint': placement['joint'], 'vertex_count': len(idx_list)})
        except ValueError as e:
            skipped.append({'au': au_name, 'reason': str(e)})

    if built:
        _hanim_backup(filepath)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return jsonify({'status': 'ok', 'built': built, 'skipped': skipped})


@hanim_bp.route('/hanim/ingest', methods=['POST'])
def hanim_ingest():
    """
    POST /hanim/ingest
    Body: { hanim_src: str, cultivar: str }

    Avatar pipeline ingest — single button replaces the old normalize→wire
    two-step.  The X3D is never renamed; the joint map is stored in the
    cultivar.

    Steps:
      1. Parse joint DEFs from X3D
      2. Detect naming convention
      3. Build joint_map { def: hanim_2_0_name }
      4. Write JointMap + HAnimFigure into cultivar XML (atomic)
      5. Wire all un-wired joints with rest-rotation keyValues (atomic)

    Returns: { status, convention, joints_mapped, joints_unmapped,
               joints_wired, joints_skipped, joint_map, hanim_path,
               cultivar_path }
    """
    body      = request.get_json(silent=True) or {}
    hanim_src = (body.get('hanim_src') or '').strip()
    cultivar  = (body.get('cultivar')  or '').strip()

    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400
    if not cultivar:
        return jsonify({'status': 'error', 'error': 'cultivar required'}), 400

    x3d_path      = _hanim_x3d_path(hanim_src)
    cultivar_path = _cultivar_xml_path(cultivar)

    if not os.path.exists(x3d_path):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404
    if not os.path.exists(cultivar_path):
        return jsonify({'status': 'error',
                        'error': f'Cultivar XML not found for: {cultivar}'}), 404

    # ── 1. Parse joint DEFs ──────────────────────────────────────────────
    try:
        xml_decl, root = _parse_x3d_file(x3d_path)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D parse failed: {exc}'}), 500

    ns = _X3D_NS
    joint_defs = []
    joint_rot_map = {}
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if el.get('USE'):
                continue
            def_val = el.get('DEF', '').strip()
            if def_val:
                joint_defs.append(def_val)
                rot = el.get('rotation', '').strip()
                if rot:
                    joint_rot_map[def_val] = rot

    if not joint_defs:
        return jsonify({'status': 'error',
                        'error': 'No HAnimJoint DEF nodes found in file'}), 400

    # ── 2. Detect convention ─────────────────────────────────────────────
    convention = _detect_naming_convention(joint_defs)

    # ── 3. Build joint map ───────────────────────────────────────────────
    joint_map = _build_joint_map(joint_defs, convention)

    joints_mapped   = len(joint_map)
    joints_unmapped = len(joint_defs) - joints_mapped

    # ── 4. Write JointMap into cultivar XML ──────────────────────────────
    try:
        _hanim_backup(cultivar_path)
        _write_cultivar_joint_map(cultivar_path, joint_map, hanim_src, convention)
    except Exception as exc:
        return jsonify({'status': 'error',
                        'error': f'Cultivar write failed: {exc}'}), 500

    # ── 5. Wire joints (rest-rotation keyValues) ─────────────────────────
    # Find joints that already have a rotation ROUTE so we skip them
    already_wired = set()
    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        for el in root.iter(tag):
            if el.get('toField', '') == 'rotation':
                already_wired.add(el.get('toNode', ''))

    scene_el = _find_scene_el(root)
    if scene_el is None:
        return jsonify({'status': 'error',
                        'error': 'No <Scene> element in X3D file'}), 500

    existing_routes = _collect_routes(root)
    _remove_routes(scene_el)

    new_routes     = list(existing_routes)
    joints_wired   = 0
    joints_skipped = 0

    for jdef in joint_defs:
        if jdef in already_wired:
            joints_skipped += 1
            continue

        timer_def  = f'WireTimer_{jdef}'
        interp_def = f'WireInterp_{jdef}'

        ts = _ET_hanim.SubElement(scene_el, f'{{{ns}}}TimeSensor')
        ts.set('DEF',           timer_def)
        ts.set('cycleInterval', '1')
        ts.set('loop',          'true')
        ts.set('enabled',       'false')

        rest_rot = joint_rot_map.get(jdef, '0 0 1 0')
        parts = rest_rot.split()
        kv = (' '.join(parts) + '  ' + ' '.join(parts)) if len(parts) == 4 \
             else '0 0 1 0  0 0 1 0'

        interp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}OrientationInterpolator')
        interp.set('DEF',      interp_def)
        interp.set('key',      '0 1')
        interp.set('keyValue', kv)

        new_routes.append({'fromNode': timer_def,  'fromField': 'fraction_changed',
                            'toNode':   interp_def, 'toField':   'set_fraction'})
        new_routes.append({'fromNode': interp_def, 'fromField': 'value_changed',
                            'toNode':   jdef,       'toField':   'rotation'})
        joints_wired += 1

    # Re-append all ROUTEs last — invariant
    for r_attrib in new_routes:
        re_el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}ROUTE')
        for k, v in r_attrib.items():
            re_el.set(k, v)

    # Atomic X3D write
    try:
        _hanim_backup(x3d_path)
        out_text = _serialise_x3d(xml_decl, root)
        tmp_path = x3d_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(out_text)
        os.replace(tmp_path, x3d_path)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D write failed: {exc}'}), 500

    return jsonify({
        'status':          'ok',
        'convention':      convention,
        'joints_mapped':   joints_mapped,
        'joints_unmapped': joints_unmapped,
        'joints_wired':    joints_wired,
        'joints_skipped':  joints_skipped,
        'joint_map':       joint_map,
        'hanim_path':      os.path.basename(x3d_path),
        'cultivar_path':   os.path.basename(cultivar_path),
    })



def _humanize_gesture_label(description: str, fallback: str) -> str:
    """
    Derive an author-friendly gesture name from a TimeSensor's description
    attribute. Handles both naming variants seen on Anna's file:
      'Armature|preset:biped:look around' -> 'Look Around'
      'preset:biped:look around'          -> 'Look Around'
    Falls back to the bare timerDEF (never invents a label from nothing --
    an empty or unrecognized description just means 'Timer3' etc., same
    as GET /hanim/joints already does today).
    """
    desc = (description or '').strip()
    if not desc:
        return fallback
    tail  = desc.split('|')[-1]          # drop an 'Armature|' prefix if present
    label = tail.split(':')[-1].strip()  # last segment of preset:biped:<name>
    if not label:
        return fallback
    return label.replace('_', ' ').replace('-', ' ').title()


def _build_def_index(root):
    """Map every DEF name in the tree to its element, for fingerprint lookups."""
    idx = {}
    for el in root.iter():
        d = el.get('DEF')
        if d and d not in idx:
            idx[d] = el
    return idx


def _gesture_fingerprint(timer_def, existing_routes, def_index):
    """
    Build a comparable signature for what a TimeSensor actually animates:
    the sorted (target joint, key, keyValue) for every interpolator it
    drives, read off the real ROUTE graph rather than assumed from DEF
    naming. Two TimeSensors with an identical fingerprint are driving
    identical animation data -- a genuine duplicate, not just a name
    collision. Confirmed against Anna's Timer1/Timer8 pair (same 42
    joints, same keyValue arrays) before relying on this.
    """
    interp_defs = [r['toNode'] for r in existing_routes
                   if r.get('fromNode') == timer_def
                   and r.get('fromField') == 'fraction_changed']
    sig = []
    for interp_def in interp_defs:
        target_routes = [r for r in existing_routes
                          if r.get('fromNode') == interp_def
                          and r.get('fromField') == 'value_changed']
        target = target_routes[0]['toNode'] if target_routes else ''
        el = def_index.get(interp_def)
        sig.append((target,
                    el.get('key', '')      if el is not None else '',
                    el.get('keyValue', '') if el is not None else ''))
    sig.sort(key=lambda t: t[0])
    return tuple(sig)


@hanim_bp.route('/hanim/ingest-mixamo', methods=['POST'])
def hanim_ingest_mixamo():
    """
    POST /hanim/ingest-mixamo
    Body: { hanim_src: str, cultivar: str, animation_name: str (optional) }

    Mixamo-specific ingest that:
      1. Runs the standard ingest pipeline (joint_map, WireInterps)
      2. Preserves the existing TimeSensor + all Interpolator/ROUTE animation
         data that X_ITE wrote during GLTF->X3D conversion — these are the
         Mixamo animation keyframes and must not be replaced with WireInterps.
      3. Renames the TimeSensor and adds animation_name metadata to cultivar
         so the editor can show/control the clip.
      4. Stores animation clip info { name, cycleInterval, bone_count } in
         cultivar XML under <Animations><Clip>.

    Key difference from /hanim/ingest:
      Standard ingest replaces all existing ROUTEs with WireInterps.
      This endpoint KEEPS the Mixamo animation ROUTEs and adds WireInterps
      only for joints that have NO existing animation ROUTE — effectively
      allowing both the Mixamo animation and manual pose overrides to coexist.

    Returns: { status, convention, joints_mapped, joints_unmapped,
               joints_wired, animation_preserved, clip_name,
               cycle_interval, hanim_path, cultivar_path }
    """
    import xml.etree.ElementTree as _ET_mix
    body          = request.get_json(silent=True) or {}
    hanim_src     = (body.get('hanim_src')       or '').strip()
    cultivar      = (body.get('cultivar')        or '').strip()
    animation_name = (body.get('animation_name') or 'mixamo_anim').strip()

    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400
    if not cultivar:
        return jsonify({'status': 'error', 'error': 'cultivar required'}), 400

    x3d_path      = _hanim_x3d_path(hanim_src)
    cultivar_path = _cultivar_xml_path(cultivar)

    if not os.path.exists(x3d_path):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404
    if not os.path.exists(cultivar_path):
        return jsonify({'status': 'error',
                        'error': f'Cultivar XML not found for: {cultivar}'}), 404

    # ── Parse X3D ──────────────────────────────────────────────────────────
    try:
        xml_decl, root = _parse_x3d_file(x3d_path)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D parse failed: {exc}'}), 500

    ns = _X3D_NS

    # ── Ensure Scripting component declared (needed for FaceController) ───
    head_el = root.find('head')
    if head_el is None:
        head_el = root.find(f'{{{ns}}}head')
    if head_el is not None:
        existing_comps = {el.get('name', '') for el in head_el
                         if el.tag in ('component', f'{{{ns}}}component')}
        if 'Scripting' not in existing_comps:
            comp = _ET_mix.SubElement(head_el, 'component')
            comp.set('name', 'Scripting')
            comp.set('level', '1')

    # ── Collect joint DEFs ─────────────────────────────────────────────────
    joint_defs    = []
    joint_rot_map = {}
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if el.get('USE'):
                continue
            def_val = el.get('DEF', '').strip()
            if def_val:
                joint_defs.append(def_val)
                rot = el.get('rotation', '').strip()
                if rot:
                    joint_rot_map[def_val] = rot

    if not joint_defs:
        return jsonify({'status': 'error',
                        'error': 'No HAnimJoint DEF nodes found'}), 400

    # ── Detect convention and build joint map ──────────────────────────────
    convention = _detect_naming_convention(joint_defs)
    joint_map  = _build_joint_map(joint_defs, convention)

    # ── Snapshot existing animation data before any modification ──────────
    # Collect: TimeSensor details, all interpolators, all existing ROUTEs
    anim_timer_el    = None
    cycle_interval   = None
    anim_route_nodes = set()   # toNode values that already have animation ROUTEs
    existing_routes  = []

    # Collect ALL animation TimeSensors (not WireTimers) — multi-clip files
    # have one TimeSensor per clip (Timer1, Timer2, ... TimerN).
    all_anim_timers = []
    for tag in (f'{{{ns}}}TimeSensor', 'TimeSensor'):
        for el in root.iter(tag):
            if not el.get('DEF', '').startswith('WireTimer'):
                all_anim_timers.append(el)
    if all_anim_timers:
        anim_timer_el  = all_anim_timers[0]
        cycle_interval = anim_timer_el.get('cycleInterval')

    for tag in (f'{{{ns}}}ROUTE', 'ROUTE'):
        for el in root.iter(tag):
            attribs = {k: v for k, v in el.attrib.items()}
            to_node  = el.get('toNode', '')
            to_field = el.get('toField', '')
            # Drop scale and translation interpolator ROUTEs entirely.
            # X_ITE exports scale tracks as PositionInterpolator nodes with DEF
            # names starting with "ScaleInterpolator" — causes bone elongation.
            # Translation tracks are also dropped: bone positions are defined by
            # the rest `translation` attribute on each HAnimJoint; animated
            # set_translation from multiple simultaneous clips fighting over the
            # same bone causes severe distortion. Rotation-only animation is
            # correct for character rigs.
            if to_field in ('set_scale', 'scale', 'set_translation', 'translation') or \
               to_node.startswith('ScaleInterpolator') or \
               to_node.startswith('TranslationInterpolator'):
                continue
            existing_routes.append(attribs)
            # Track which joints already have animation ROUTEs targeting them
            if to_field in ('set_rotation', 'rotation', 'set_translation',
                            'translation'):
                anim_route_nodes.add(to_node)

    animation_preserved = anim_timer_el is not None
    bone_count = len(anim_route_nodes)

    # Keep the TimeSensor DEF exactly as-is — renaming requires patching every
    # ROUTE that references it, which is fragile across nested groups.
    # The timer DEF is stored in the cultivar clip record so the playback
    # panel can find it by its original name.

    # ── Move ALL TimeSensors to Scene root so SAI getNamedNode() finds them ─
    # X_ITE's getNamedNode only searches the flat Scene namespace, not nested
    # groups. Multi-clip Mixamo files have one TimeSensor per animation, all
    # inside nested Groups. Move every non-WireTimer TimeSensor to Scene root.
    scene_el_early = _find_scene_el(root)
    if scene_el_early is not None:
        # Find insert position: just before the first ROUTE
        insert_pos = len(list(scene_el_early))
        for i, sc in enumerate(list(scene_el_early)):
            stag = sc.tag.split('}')[-1] if '}' in sc.tag else sc.tag
            if stag == 'ROUTE':
                insert_pos = i
                break

        # Collect all TimeSensors not already at Scene root and not WireTimers
        scene_direct = set(id(c) for c in scene_el_early)
        timers_to_move = []
        for el in root.iter():
            for child in list(el):
                ctag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if ctag != 'TimeSensor':
                    continue
                def_val = child.get('DEF', '')
                if def_val.startswith('WireTimer_'):
                    continue
                if id(child) in scene_direct:
                    continue  # already at root
                timers_to_move.append((el, child))

        for parent_el, timer_el in timers_to_move:
            parent_el.remove(timer_el)
            timer_el.set('loop',    'true')
            timer_el.set('enabled', 'false')
            scene_el_early.insert(insert_pos, timer_el)
            insert_pos += 1  # maintain order

    # ── Remove EXPORT nodes — they re-export nested DEFs into scene namespace
    # and can override the moved TimeSensors with the original nested versions.
    if scene_el_early is not None:
        for tag in ('EXPORT', f'{{{ns}}}EXPORT'):
            to_remove = [c for c in scene_el_early if c.tag == tag]
            for c in to_remove:
                scene_el_early.remove(c)

    # ── Strip scale attribute from all HAnimJoint nodes ─────────────────
    # Mixamo exports near-identity scale values (e.g. 0.9999999) on joints.
    # X_ITE compounds these down the joint chain — 4 finger joints each with
    # 0.9999999 scale produce visible elongation. Strip all joint scale attrs.
    for tag in (f'{{{ns}}}HAnimJoint', 'HAnimJoint'):
        for el in root.iter(tag):
            if 'scale' in el.attrib:
                del el.attrib['scale']

    # ── Remove ScaleInterpolator and TranslationInterpolator nodes ────────
    # X_ITE exports scale tracks as PositionInterpolator nodes with DEF names
    # starting with "ScaleInterpolator", and translation tracks as
    # PositionInterpolator nodes with DEF names starting with
    # "TranslationInterpolator". Both are dropped:
    # - Scale compounds through joint chains causing elongation artifacts.
    # - Translation from multiple simultaneous clips conflicts on the same
    #   bones; rest pose translation on HAnimJoint defines bone length.
    # Their ROUTEs were already excluded from existing_routes above.
    for el in root.iter():
        to_remove = [
            child for child in list(el)
            if child.get('DEF', '').startswith('ScaleInterpolator')
            or child.get('DEF', '').startswith('TranslationInterpolator')
        ]
        for child in to_remove:
            el.remove(child)

    safe_anim_name = animation_name.replace(' ', '_').replace('-', '_')
    timer_new_def  = anim_timer_el.get('DEF', 'Timer1') if anim_timer_el is not None else f'{safe_anim_name}_Timer'

    # ── Write joint map to cultivar ────────────────────────────────────────
    try:
        _hanim_backup(cultivar_path)
        _write_cultivar_joint_map(cultivar_path, joint_map, hanim_src, convention)
    except Exception as exc:
        return jsonify({'status': 'error',
                        'error': f'Cultivar write failed: {exc}'}), 500

    # ── Write animation clip metadata to cultivar ──────────────────────────
    try:
        cv_tree = _ET_mix.parse(cultivar_path)
        cv_root = cv_tree.getroot()

        # NOTE: cultivar XML declares a default xmlns on the root, which
        # every descendant inherits once parsed -- a bare .find('Animations')
        # never matches {ns}Animations and silently creates a duplicate
        # un-namespaced element on every re-ingest. Use a namespace wildcard,
        # and actively remove ALL matches (not just the first) to mop up
        # duplicates that already accumulated in live cultivar files before
        # this was caught.
        existing_anims_els = cv_root.findall('{*}Animations')
        existing_clip_names = {}
        for el in existing_anims_els:
            for c in el.findall('{*}Clip'):
                if c.get('timerDEF') and c.get('name'):
                    existing_clip_names[c.get('timerDEF')] = c.get('name')
        for el in existing_anims_els:
            cv_root.remove(el)
        anims_el = _ET_mix.SubElement(cv_root, 'Animations')

        # Register every animation TimeSensor as a clip. <Animations> stays a
        # complete inventory of every TimeSensor physically in the file,
        # duplicates included -- this is ingest's own record of what exists,
        # not what's authorable.
        for timer_el in all_anim_timers:
            t_def  = timer_el.get('DEF', 'Timer1')
            t_ci   = timer_el.get('cycleInterval', '0')
            # Use existing cultivar name if present, else fall back to timer DEF
            t_name = existing_clip_names.get(t_def, t_def)
            c_el = _ET_mix.SubElement(anims_el, 'Clip')
            c_el.set('name',          t_name)
            c_el.set('timerDEF',      t_def)
            c_el.set('cycleInterval', t_ci)
            c_el.set('bone_count',    str(bone_count))

        # ── Also populate <Behaviors> -- the table Composer/Events Editor
        # actually read (see cultivar_lambda.py; CultivarDefinition has no
        # concept of <Animations>, only <Behaviors>). Unlike <Animations>,
        # this is meant to be the *authorable* clip list, so true duplicate
        # tracks are collapsed to one entry each -- confirmed real duplicate
        # (not just a name collision) via _gesture_fingerprint, which
        # compares actual ROUTE-graph targets and keyframe data rather than
        # trusting that a matching label means matching animation. Not
        # hardcoded to any specific Timer range -- future avatars may not
        # split their duplicate tracks evenly.
        # NOTE: same wildcard-vs-bare namespace bug as Animations above --
        # if MORE than one <Behaviors> exists (e.g. a stale one left over
        # from before this fix), merge names from all of them, then
        # collapse to a single element.
        existing_beh_blocks = cv_root.findall('{*}Behaviors')
        existing_beh_names = {}
        for el in existing_beh_blocks:
            for c in el.findall('{*}Clip'):
                if c.get('timerDEF') and c.get('name'):
                    existing_beh_names[c.get('timerDEF')] = c.get('name')
        for el in existing_beh_blocks:
            cv_root.remove(el)
        beh_el = _ET_mix.SubElement(cv_root, 'Behaviors')

        def_index   = _build_def_index(root)
        seen_labels = {}   # fresh_label -> fingerprint of the entry already kept
        seen_bases  = set()   # fresh (pre-disambiguation) labels already claimed
        primary_timer_defs = []   # first timerDEF per FRESH label -- these get
                                   # EXPORTed below so the Loader (IMPORT/
                                   # getImportedNode) can reach them. Based on
                                   # the description-derived label, not the
                                   # preserved cultivar name, so a prior
                                   # disambiguated name (e.g. 'Fold Arms 2'
                                   # already stored for Timer9) can't be
                                   # mistaken for a brand-new base label on a
                                   # later re-ingest.
        first_name  = None
        for timer_el in all_anim_timers:
            t_def = timer_el.get('DEF', 'Timer1')
            t_ci  = timer_el.get('cycleInterval', '0')
            desc  = timer_el.get('description', '')
            fresh_label = _humanize_gesture_label(desc, t_def)
            fp = _gesture_fingerprint(t_def, existing_routes, def_index)

            if fresh_label not in seen_bases:
                seen_bases.add(fresh_label)
                primary_timer_defs.append(t_def)

            dedup_key = fresh_label
            if dedup_key in seen_labels:
                if fp == seen_labels[dedup_key]:
                    # Same joints, same keyframes -- true duplicate track.
                    # Skip for authoring; still recorded in <Animations>.
                    continue
                # Same cleaned label, different data -- a real naming
                # collision, not a duplicate. Disambiguate rather than
                # silently drop someone's actual gesture.
                base, n = dedup_key, 2
                while f'{base} {n}' in seen_labels:
                    n += 1
                dedup_key = f'{base} {n}'
            seen_labels[dedup_key] = fp

            # Respect a human rename already stored for THIS timerDEF;
            # otherwise use the freshly-derived (possibly disambiguated) key.
            display_name = existing_beh_names.get(t_def) or dedup_key
            if first_name is None:
                first_name = display_name

            b_el = _ET_mix.SubElement(beh_el, 'Clip')
            b_el.set('name',          display_name)
            b_el.set('timerDEF',      t_def)
            b_el.set('cycleInterval', t_ci)
            b_el.set('loop',          'true')
            b_el.set('priority',      '0')

        if first_name and not beh_el.get('default'):
            beh_el.set('default', first_name)

        cv_tree.write(cultivar_path, encoding='unicode', xml_declaration=False)
    except Exception as exc:
        return jsonify({'status': 'error',
                        'error': f'Cultivar animation write failed: {exc}'}), 500

    # ── Add WireInterps for ALL joints so pose sliders work ───────────────
    # Use bare tag names (no namespace prefix) to match the Mixamo file format.
    # WireInterps start disabled so animation plays freely; sliders enable them.
    scene_el = _find_scene_el(root)
    if scene_el is None:
        return jsonify({'status': 'error',
                        'error': 'No <Scene> element in X3D file'}), 500

    _remove_routes(scene_el)

    new_routes   = list(existing_routes)   # keep all original animation routes
    joints_wired = 0

    for jdef in joint_defs:
        # DEF names must be valid XML NCNames — colons are illegal (reserved for
        # namespace prefixes). Mixamo DEFs like 'mixamorig:Hips' must be sanitised.
        safe_def   = jdef.replace(':', '_').replace('-', '_')
        timer_def  = f'WireTimer_{safe_def}'
        interp_def = f'WireInterp_{safe_def}'

        ts = _ET_mix.SubElement(scene_el, 'TimeSensor')
        ts.set('DEF',           timer_def)
        ts.set('cycleInterval', '1')
        ts.set('loop',          'true')
        ts.set('enabled',       'false')

        rest_rot = joint_rot_map.get(jdef, '0 0 1 0')
        parts    = rest_rot.split()
        kv = (' '.join(parts) + '  ' + ' '.join(parts)) if len(parts) == 4 \
             else '0 0 1 0  0 0 1 0'

        interp = _ET_mix.SubElement(scene_el, 'OrientationInterpolator')
        interp.set('DEF',      interp_def)
        interp.set('key',      '0 1')
        interp.set('keyValue', kv)

        new_routes.append({'fromNode': timer_def,  'fromField': 'fraction_changed',
                           'toNode':   interp_def, 'toField':   'set_fraction'})
        new_routes.append({'fromNode': interp_def, 'fromField': 'value_changed',
                           'toNode':   jdef,       'toField':   'rotation'})
        joints_wired += 1

    # Re-append all ROUTEs — bare tag name matches no-namespace source file
    for r_attrib in new_routes:
        re_el = _ET_mix.SubElement(scene_el, 'ROUTE')
        for k, v in r_attrib.items():
            re_el.set(k, v)

    # ── Inject standard camera viewpoints ─────────────────────────────────
    # Remove any existing SceneViewpoints group first (idempotent re-ingest)
    for child in list(scene_el):
        ctag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
        if ctag == 'Group' and child.get('DEF') == 'SceneViewpoints':
            scene_el.remove(child)

    n = cultivar  # avatar name for viewpoint descriptions
    vp_group = _ET_mix.SubElement(scene_el, 'Group')
    vp_group.set('DEF', 'SceneViewpoints')

    _VIEWPOINTS = [
        {'description': f'{n}',                 'position': '0 1 3',      'centerOfRotation': '0 1 0'},
        {'description': f'{n} Front',            'position': '0 0.4 4',    'centerOfRotation': '0 0.9149 0.0016'},
        {'description': f'{n} Front Close',      'position': '0 0.8 2',    'centerOfRotation': '0 0.9149 0.0016'},
        {'description': f'{n} Front Closer',     'position': '0 1.2 1',    'centerOfRotation': '0 0.9149 0.0016'},
        {'description': f'{n} Front Face',       'position': '0 1.63 1',   'centerOfRotation': '0 1.5 0.0016'},
        {'description': f'{n} Right Side',       'position': '2.6 0.8 0',  'centerOfRotation': '0 0.9149 0.0016',
         'orientation': '0 1 0 1.5708'},
        {'description': f'{n} Right Side Close', 'position': '1 0.8 0.5',  'centerOfRotation': '0 0.9149 0.0016',
         'orientation': '0 1 0 1.2'},
        {'description': f'{n} Left Side Close',  'position': '-1 0.8 0.5', 'centerOfRotation': '0 0.9149 0.0016',
         'orientation': '0 1 0 -1.2'},
        {'description': f'{n} Left Side',        'position': '-2.6 0.8 0', 'centerOfRotation': '0 0.9149 0.0016',
         'orientation': '0 1 0 -1.5708'},
        {'description': f'{n} Top',              'position': '0 3.5 0',    'centerOfRotation': '0 0.9149 0.0016',
         'orientation': '1 0 0 -1.5708'},
    ]
    for vp in _VIEWPOINTS:
        vp_el = _ET_mix.SubElement(vp_group, 'Viewpoint')
        for k, v in vp.items():
            vp_el.set(k, v)

    # ── EXPORT the primary gesture timers ──────────────────────────────────
    # TimeSensor promotion (above) fixes getNamedNode() for the Character
    # Creator, but the Loader reaches Anna's timers via IMPORT/
    # getImportedNode, which requires the target file to EXPORT the node --
    # promotion alone doesn't help the Loader. "Primary" here is the same
    # first-occurrence-per-base-label set used to build <Behaviors> above
    # (primary_timer_defs), so this list tracks that table automatically --
    # not hardcoded to a Timer range, and it won't export the unconfirmed
    # '2' duplicate tracks. Identity export (localDEF == AS), matching the
    # "don't rename, just alias" convention already established for this
    # file. Idempotent: removes any EXPORTs for this avatar's primary set
    # left over from a prior ingest run before re-adding, so re-ingesting
    # doesn't accumulate duplicates the way the cultivar writer once did.
    for tag in ('EXPORT', f'{{{_X3D_NS}}}EXPORT'):
        for ex in list(scene_el.findall(tag)):
            if ex.get('localDEF') in primary_timer_defs:
                scene_el.remove(ex)
    for t_def in primary_timer_defs:
        ex = _ET_mix.SubElement(scene_el, 'EXPORT')
        ex.set('localDEF', t_def)
        ex.set('AS',       t_def)

    # ── Atomic X3D write ───────────────────────────────────────────────────
    try:
        _hanim_backup(x3d_path)
        out_text = _serialise_x3d(xml_decl, root)
        tmp_path = x3d_path + '.tmp'
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            fh.write(out_text)
        os.replace(tmp_path, x3d_path)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'X3D write failed: {exc}'}), 500

    return jsonify({
        'status':               'ok',
        'convention':           convention,
        'joints_mapped':        len(joint_map),
        'joints_unmapped':      len(joint_defs) - len(joint_map),
        'joints_wired':         joints_wired,
        'animation_preserved':  animation_preserved,
        'clip_name':            animation_name,
        'timer_def':            timer_new_def,
        'cycle_interval':       cycle_interval,
        'animated_bones':       bone_count,
        'hanim_path':           os.path.basename(x3d_path),
        'cultivar_path':        os.path.basename(cultivar_path),
    })


# End HAnim Editor Export Endpoints


# ---------------------------------------------------------------------------
# Registration — matches the register_X_api(app) pattern used by
# mccf_scene_wrapper, mccf_cultivar_lambda, mccf_scene_generate_api.
# ---------------------------------------------------------------------------

def register_hanim_api(app):
    app.register_blueprint(hanim_bp)
    return hanim_bp
