"""
MCCF Affective Engine API Server
=================================
REST bridge between X3D/X_ITE sensor events and the MCCF coherence engine.

Endpoints:
  POST /sensor          - receive sensor event from X3D, return affect params
  GET  /field           - current coherence field state
  GET  /agent/<name>    - single agent state
  POST /agent           - create/update agent
  POST /cultivar        - save current agent as cultivar template
  GET  /cultivar        - list cultivars
  POST /gardener/regulate  - gardener regulation intervention
  POST /gardener/reweight  - gardener reweight intervention
  GET  /export/x3d      - export scene routing as X3D fragment
  GET  /export/python   - export agent configs as Python
  GET  /export/json     - export full system state as JSON

Signal flow:
  X3D ProximitySensor → POST /sensor → MCCF engine → affect params → X3D ROUTE

Affect parameter output (returned to X3D):
  approach_factor    0-1  (proximity → animation blend weight)
  arousal            0-1  (emotional intensity → motion speed scale)
  valence           -1-1  (positive/negative affect → color/posture)
  engagement         0-1  (behavioral coherence → attention orientation)
  regulation_state   0-1  (current regulation level)
  coherence_to_other 0-1  (current R_ij toward the sensed agent)
"""

import json
import math
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mccf_core import (
    Agent, ChannelVector, CoherenceField,
    Librarian, Gardener, CHANNEL_NAMES
)

import mimetypes
mimetypes.add_type('model/x3d+xml', '.x3d')

app = Flask(__name__)
CORS(app)  # X3D pages need cross-origin access

# ---------------------------------------------------------------------------
# Explicit static file routes with correct MIME types
#
# Flask's static file handler can be overridden by Windows registry MIME
# mappings or browser content sniffing. These explicit routes guarantee
# the correct Content-Type header regardless of OS or browser behaviour.
#
# HTML route: serves all .html files from static/ as text/html with
#   X-Content-Type-Options: nosniff to suppress browser MIME sniffing.
# X3D route: serves mccf_scene.x3d as model/x3d+xml for X_ITE.
#
# v3.3 — consolidated April 2026
# ---------------------------------------------------------------------------

@app.route('/static/<path:filename>.html')
def serve_static_html(filename):
    from flask import send_from_directory, make_response
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    resp = make_response(
        send_from_directory(static_dir, filename + '.html')
    )
    resp.headers['Content-Type'] = 'text/html; charset=utf-8'
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@app.route('/static/x3d/<path:filename>')
def serve_x3d_scene(filename):
    """Serve named X3D files from static/x3d/ directory."""
    from flask import send_from_directory
    x3d_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d')

    # Notify ChorusManager: look for a matching scene XML to pick up Chorus config.
    # Scene X3D name pattern: {scene_name}.x3d → scenes/{scene_name}_scene.xml
    try:
        cm = app.config.get('_chorus_manager')
        if cm is not None:
            base = filename.replace('.x3d', '')
            scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
            candidates = [
                os.path.join(scenes_dir, base + '_scene.xml'),
                os.path.join(scenes_dir, base + '.xml'),
            ]
            for cpath in candidates:
                if os.path.exists(cpath):
                    with open(cpath, encoding='utf-8') as f:
                        cm.load_config_from_scene_xml(f.read())
                    break
    except Exception:
        pass

    return send_from_directory(x3d_dir, filename, mimetype='model/x3d+xml')


@app.route('/scene/x3d/upload', methods=['POST'])
def upload_x3d_scene():
    """
    Accept X3D content from Scene Composer and write to static/x3d/{scene_name}.x3d.
    Scene name passed as X-Scene-Name request header.
    Falls back to mccf_scene.x3d if header absent.
    Called by sendToLauncher() in mccf_scene_composer.html.
    """
    x3d_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d')
    os.makedirs(x3d_dir, exist_ok=True)
    scene_name = request.headers.get('X-Scene-Name', '').strip()
    if not scene_name:
        scene_name = 'mccf_scene'
    # Sanitise: keep alphanumeric, underscore, hyphen only
    import re as _re
    safe_name = _re.sub(r'[^A-Za-z0-9_\-]', '_', scene_name)
    filename = safe_name + '.x3d'
    filepath = os.path.join(x3d_dir, filename)
    content = request.get_data(as_text=True)
    if not content:
        return jsonify({'status': 'error', 'error': 'no content'}), 400
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'output': f'static/x3d/{filename}', 'filename': filename})


@app.route('/avatar/upload', methods=['POST'])
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

    # 9. Remove any existing FaceController (clean slate)
    stripped = _re.sub(
        r'\s*<Script DEF=["\']FaceController["\'].*?</Script>',
        '', stripped, flags=_re.DOTALL)

    # 10. Inject FaceController before </Scene>
    FACE_CONTROLLER = (
        '\n  <Script DEF="FaceController" directOutput="true">\n'
        '    <field name="au_name"   type="SFString" accessType="inputOnly"/>\n'
        '    <field name="au_weight" type="SFFloat"  accessType="inputOnly"/>\n'
        '    <![CDATA[ecmascript:\n'
        '      function au_weight(value, time) {\n'
        '        var adapter = Browser.currentScene.getNamedNode(\n'
        "                        'AnimationAdapter_' + _au);\n"
        '        if (adapter) {\n'
        "          var field = adapter.getField('set_fraction');\n"
        '          if (field) field.setValue(value * 0.5);\n'
        '        }\n'
        '      }\n'
        '      function au_name(value, time) { _au = value; }\n'
        "      var _au = '';\n"
        '    ]]>\n'
        '  </Script>'
    )
    stripped = stripped.replace('</Scene>', FACE_CONTROLLER + '\n</Scene>', 1)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(stripped)

    return jsonify({
        'status':      'ok',
        'path':        f'avatars/{filename}',
        'filename':    filename,
        'loa':         loa,
        'joint_count': joint_count,
        'clips':       clips,
    })


@app.route('/avatar/preview')
def avatar_preview():
    """
    GET /avatar/preview?src=avatars/foo_hanim.x3d
    Serves a minimal X_ITE HTML page that renders the H-Anim figure locally.

    Morph driver is avatar-agnostic (Day 32):
    - Derives avatar name from src filename (jack_hanim.x3d -> 'jack')
    - Fetches {avatarname}_expressions.xml for AU data
    - On scene load, discovers face coord DEF names by scanning for a Group
      DEF matching '*FaceCoords' pattern, reads its Coordinate children
    - Supports two morph modes detected automatically:
        SEGMENT mode (Cindy): coord nodes ARE the rendered geometry;
          write displacement directly to each named coord node.
        GLOBAL mode (Jack):   coord nodes are metadata holders inside
          head HAnimSegment; each carries a globalIndices attribute
          mapping local indices to global skin mesh (_3).
          Write displacements into _3 (the rendered node).
      Detection: if any discovered coord node has globalIndices='local'
      or a numeric globalIndices list, it is GLOBAL mode.
      If globalIndices absent on all nodes, it is SEGMENT mode (Cindy).
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

    # Derive avatar name and expressions filename from src
    # 'avatars/jack_hanim.x3d' -> 'jack'
    # 'avatars/cindy_hanim.x3d' -> 'cindy'
    import re as _re
    _basename = os.path.basename(src)                        # jack_hanim.x3d
    _stem     = _re.sub(r'_hanim\.x3d$', '', _basename,
                        flags=_re.IGNORECASE)                # jack
    _stem     = _re.sub(r'\.x3d$', '', _stem,
                        flags=_re.IGNORECASE)                # fallback strip
    _stem     = _stem.lower()                                # normalise
    _expressions_url = f'/static/avatars/{_stem}_expressions.xml'

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
    <div class="mo-title">morph driver</div>
    <div id="mo-coords">waiting for scene...</div>
    <div id="mo-aus"></div>
    <div id="mo-status" class="mo-status"></div>
  </div>
  <script type="module">
    import X3D from 'https://cdn.jsdelivr.net/npm/x_ite@10.5.2/dist/x_ite.min.mjs';
    const canvas  = document.getElementById('canvas');
    const EXPRESSIONS_URL = '__EXPRESSIONS_URL__';

    let _browser = null, _scene = null;

    // Discovered at scene load — filled by _discoverFaceCoords()
    var _faceCoordDefs  = [];   // ['JackCoord_skull', 'JackCoord_jaw', ...]
    var _globalMode     = false; // true = Jack-style global skin mesh write
    var _globalIndices  = {};   // def -> Int32Array of global vert indices (global mode)
    var _skinMeshDef    = '_3';  // global skin mesh Coordinate DEF (fallback lookup)
    var _skinCoordNode  = null;  // live Coordinate node inside the rendered Shape (preferred)

    var _restPose   = {};  // def -> Float32Array of rest-pose XYZ
    var _auWeights  = {};
    var _auData     = {};
    var _morphReady = false;
    var _animTimersStopped = [];  // animation timer DEFs stopped by slider — restart on play

    // ── Discover face coord nodes from scene ─────────────────────────────
    // Looks for a Group DEF ending in 'FaceCoords' (e.g. JackFaceCoords,
    // CindyFaceCoords). Falls back to scanning for any Coordinate DEF
    // matching *Coord_skull pattern.
    // Sets _faceCoordDefs, _globalMode, _globalIndices.
    function _discoverFaceCoords() {
      var found = [];

      // Strategy 1: look for *FaceCoords group — Jack-style pipeline output
      var suffixes = ['FaceCoords'];
      var allNodes = _scene.rootNodes;

      // Try to find group by scanning named nodes for *FaceCoords
      // We probe known prefix patterns rather than iterating (SAI has no listNodes)
      // The pipeline script always names it [AvatarName]FaceCoords
      // We derive avatar prefix from expressions URL
      var avatarPrefix = EXPRESSIONS_URL
        .split('/').pop()
        .replace('_expressions.xml','');
      var groupDef = avatarPrefix.charAt(0).toUpperCase() +
                     avatarPrefix.slice(1) + 'FaceCoords';
      var grp = null;
      try { grp = _scene.getNamedNode(groupDef); } catch(e) {}

      if (grp) {
        // Group found — read its Coordinate children by probing DEF names
        // We know the naming pattern: [AvatarName]Coord_[region]
        var regions = ['skull','jaw','l_eyebrow','r_eyebrow',
                       'l_eyelid','r_eyelid','l_eyeball','r_eyeball'];
        var pfx = avatarPrefix.charAt(0).toUpperCase() +
                  avatarPrefix.slice(1) + 'Coord_';
        regions.forEach(function(r) {
          found.push(pfx + r);
        });
        console.log('Discovered coords via group', groupDef, ':', found);
      } else {
        // Strategy 2: Cindy-style — probe CindyCoord_* directly
        var cindyRegions = ['skull','jaw','l_eyebrow','r_eyebrow',
                            'l_eyelid','r_eyelid','l_eyeball','r_eyeball'];
        cindyRegions.forEach(function(r) {
          found.push('CindyCoord_' + r);
        });
        console.log('No FaceCoords group found, trying Cindy pattern');
      }

      _faceCoordDefs = found;

      // Detect global vs segment mode by checking globalIndices attribute
      // on the skull coord node (most reliable indicator)
      _globalMode = false;
      found.forEach(function(def) {
        try {
          var node = _scene.getNamedNode(def);
          if (!node) return;
          // SAI exposes custom XML attributes via getUserData / getField.
          // globalIndices was written as an XML attribute; X_ITE exposes
          // unknown attributes via node.getField() returning null, but
          // they ARE accessible via the underlying DOM if X_ITE passes
          // through. We use a workaround: fetch the X3D file text and
          // parse globalIndices from it client-side.
          // Flag set after _fetchGlobalIndices() completes.
        } catch(e) {}
      });
    }

    // ── Fetch X3D and parse globalIndices for each face coord node ───────
    // This runs once after scene load for global-mode avatars.
    // Populates _globalIndices[def] = Int32Array and sets _globalMode.
    function _fetchGlobalIndices(x3dUrl, callback) {
      fetch(x3dUrl)
        .then(function(r) { return r.text(); })
        .then(function(text) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(text, 'application/xml');
          var hasGlobal = false;
          _faceCoordDefs.forEach(function(def) {
            var el = doc.querySelector('Coordinate[DEF="' + def + '"]');
            if (!el) return;
            var gi = el.getAttribute('globalIndices');
            if (!gi) return;
            if (gi === 'local') {
              // eyeball: local coords, write directly to named node
              _globalIndices[def] = 'local';
              hasGlobal = true;
            } else {
              var arr = gi.trim().split(/[,\\s]+/).map(Number)
                          .filter(function(n){return !isNaN(n);});
              if (arr.length > 0) {
                _globalIndices[def] = new Int32Array(arr);
                hasGlobal = true;
              }
            }
          });
          _globalMode = hasGlobal;
          console.log('Global mode:', _globalMode,
                      '— mapped regions:', Object.keys(_globalIndices).length);
          callback();
        })
        .catch(function(e) {
          console.warn('globalIndices fetch failed, assuming segment mode:', e);
          _globalMode = false;
          callback();
        });
    }

    // ── Cache rest poses for all discovered face coord nodes ─────────────
    function _cacheRestPoses() {
      var lines = [], allOk = true;
      _faceCoordDefs.forEach(function(def) {
        try {
          var node = _scene.getNamedNode(def);
          if (!node) throw new Error('null');
          var pts = node.point;
          var flat = new Float32Array(pts.length * 3);
          for (var i = 0; i < pts.length; i++) {
            flat[i*3]   = pts[i].x;
            flat[i*3+1] = pts[i].y;
            flat[i*3+2] = pts[i].z;
          }
          _restPose[def] = flat;
          // Strip prefix for display: JackCoord_skull -> skull
          var label = def.replace(/^[A-Za-z]+Coord_/, '');
          lines.push('<div class="mo-coord">' + label + ': ' +
                     pts.length + 'v &#10003;</div>');
        } catch(e) {
          var label = def.replace(/^[A-Za-z]+Coord_/, '');
          lines.push('<div class="mo-coord missing">' + label + ': MISSING</div>');
          allOk = false;
        }
      });

      // Also cache global skin mesh rest pose if in global mode.
      // IMPORTANT: the rendered IndexedTriangleSet holds a USE copy of _3,
      // not the DEF node. X_ITE only re-renders when the node the geometry
      // actually references is written. So we navigate via the rendered
      // Shape (containerField='skin') to get the live coord node.
      // Strategy: scan HAnimHumanoid skin shapes for containerField='skin',
      // get the first IndexedTriangleSet's coord field. Fall back to DEF '_3'.
      if (_globalMode) {
        try {
          var skinCoord = null;

          // Walk scene root nodes looking for HAnimHumanoid
          var roots = _scene.rootNodes;
          outer: for (var ri = 0; ri < roots.length; ri++) {
            var root = roots[ri];
            // HAnimHumanoid may be nested inside a Group
            var candidates = [root];
            if (root.getNodeTypeName && root.getNodeTypeName() !== 'HAnimHumanoid') {
              // Try children
              try {
                var fc = root.children;
                if (fc) for (var ci = 0; ci < fc.length; ci++) candidates.push(fc[ci]);
              } catch(e) {}
            }
            for (var ci = 0; ci < candidates.length; ci++) {
              var node = candidates[ci];
              if (!node || !node.getNodeTypeName) continue;
              if (node.getNodeTypeName() === 'HAnimHumanoid') {
                // skin field holds the rendered Shape(s)
                try {
                  var skinShapes = node.skin;
                  if (skinShapes && skinShapes.length > 0) {
                    for (var si = 0; si < skinShapes.length; si++) {
                      var shape = skinShapes[si];
                      if (!shape) continue;
                      var geom = shape.geometry;
                      if (!geom) continue;
                      var coord = geom.coord;
                      if (coord && coord.point && coord.point.length > 0) {
                        skinCoord = coord;
                        break outer;
                      }
                    }
                  }
                } catch(e) {
                  console.warn('skin field traversal failed:', e.message);
                }
                break outer;
              }
            }
          }

          // Fallback: getNamedNode by DEF
          if (!skinCoord) {
            skinCoord = _scene.getNamedNode(_skinMeshDef);
            console.log('Skin coord: using DEF fallback (_3)');
          } else {
            console.log('Skin coord: found via HAnimHumanoid.skin field');
          }

          if (skinCoord) {
            _skinCoordNode = skinCoord;
            var pts = skinCoord.point;
            var flat = new Float32Array(pts.length * 3);
            for (var i = 0; i < pts.length; i++) {
              flat[i*3]   = pts[i].x;
              flat[i*3+1] = pts[i].y;
              flat[i*3+2] = pts[i].z;
            }
            _restPose[_skinMeshDef] = flat;
            console.log('Global skin mesh cached:', pts.length, 'verts');
          } else {
            console.warn('Could not find skin coord node');
          }
        } catch(e) {
          console.warn('Could not cache global skin mesh:', e.message);
        }
      }

      document.getElementById('mo-coords').innerHTML = lines.join('');
      return allOk;
    }

    // ── Load AU data from expressions XML ────────────────────────────────
    function _loadAuData() {
      fetch(EXPRESSIONS_URL)
        .then(function(r) { return r.text(); })
        .then(function(xml) {
          var parser = new DOMParser();
          var doc = parser.parseFromString(xml, 'application/xml');
          var result = {};
          doc.querySelectorAll('AU').forEach(function(au) {
            var auName = au.getAttribute('name');
            result[auName] = {};
            au.querySelectorAll('Displacement').forEach(function(d) {
              var coord   = d.getAttribute('coord');
              var indices = d.getAttribute('coordIndex').trim()
                             .split(/\\s+/).map(Number);
              var vecs    = d.getAttribute('vectors').trim()
                             .split(/\\s+/).map(Number);
              var deltas  = [];
              for (var i = 0; i < vecs.length; i += 3)
                deltas.push([vecs[i], vecs[i+1], vecs[i+2]]);
              result[auName][coord] = {indices: indices, deltas: deltas};
            });
          });
          _auData = result;
          document.getElementById('mo-status').textContent =
            'AU data loaded (' + Object.keys(result).length + ' AUs)';
          console.log('AU data loaded:', Object.keys(result).length, 'AUs');
        })
        .catch(function(e) {
          console.warn('AU data fetch failed:', e);
          document.getElementById('mo-status').textContent = 'AU data: fetch failed';
        });
    }

    // ── Apply morph: SEGMENT mode (Cindy) ────────────────────────────────
    // Write displacement directly to each named coord node.
    function _applyMorphSegment() {
      var modified = {};
      _faceCoordDefs.forEach(function(def) {
        if (_restPose[def]) modified[def] = new Float32Array(_restPose[def]);
      });
      Object.keys(_auWeights).forEach(function(au) {
        var w = _auWeights[au]; if (!w || w <= 0) return;
        var auDef = _auData[au]; if (!auDef) return;
        Object.keys(auDef).forEach(function(cd) {
          var e = auDef[cd];
          if (!e || !e.indices || !modified[cd]) return;
          e.indices.forEach(function(vi, k) {
            var d = e.deltas[k];
            modified[cd][vi*3]   += d[0] * w;
            modified[cd][vi*3+1] += d[1] * w;
            modified[cd][vi*3+2] += d[2] * w;
          });
        });
      });
      var written = 0;
      Object.keys(modified).forEach(function(def) {
        try {
          var node = _scene.getNamedNode(def); if (!node) return;
          var flat = modified[def], verts = [];
          for (var i = 0; i < flat.length / 3; i++)
            verts.push(new X3D.SFVec3f(flat[i*3], flat[i*3+1], flat[i*3+2]));
          node.point = new X3D.MFVec3f(...verts);
          written++;
        } catch(ee) { console.warn('morph write failed', def, ee.message); }
      });
      return written;
    }

    // ── Apply morph: GLOBAL mode (Jack) ──────────────────────────────────
    // Accumulate displacements into global skin mesh (_3), write it back.
    // Local-coord nodes (eyeballs) written directly as in segment mode.
    function _applyMorphGlobal() {
      if (!_restPose[_skinMeshDef]) return 0;

      // Working copy of global skin mesh
      var globalFlat = new Float32Array(_restPose[_skinMeshDef]);

      // Local-coord nodes (eyeballs): separate working copies
      var localModified = {};
      _faceCoordDefs.forEach(function(def) {
        if (_globalIndices[def] === 'local' && _restPose[def])
          localModified[def] = new Float32Array(_restPose[def]);
      });

      // Accumulate all AU displacements
      Object.keys(_auWeights).forEach(function(au) {
        var w = _auWeights[au]; if (!w || w <= 0) return;
        var auDef = _auData[au]; if (!auDef) return;

        Object.keys(auDef).forEach(function(coordName) {
          var e = auDef[coordName];
          if (!e || !e.indices) return;

          var gi = _globalIndices[coordName];

          if (gi === 'local') {
            // Eyeball: write to local coord node
            if (!localModified[coordName]) return;
            e.indices.forEach(function(vi, k) {
              var d = e.deltas[k];
              localModified[coordName][vi*3]   += d[0] * w;
              localModified[coordName][vi*3+1] += d[1] * w;
              localModified[coordName][vi*3+2] += d[2] * w;
            });
          } else if (gi && gi.length) {
            // Global region: map local index -> global index, write into globalFlat
            e.indices.forEach(function(localVi, k) {
              var globalVi = gi[localVi];
              if (globalVi === undefined) return;
              var d = e.deltas[k];
              globalFlat[globalVi*3]   += d[0] * w;
              globalFlat[globalVi*3+1] += d[1] * w;
              globalFlat[globalVi*3+2] += d[2] * w;
            });
          }
        });
      });

      // Write global skin mesh.
      // Use _skinCoordNode (the live node inside the rendered Shape) if available.
      // This is critical: writing to the DEF node does NOT trigger X_ITE to
      // re-render — only the node the IndexedTriangleSet's coord field points to
      // will cause a visual update. _skinCoordNode was resolved at cache time
      // by navigating via HAnimHumanoid.skin rather than by DEF name.
      var written = 0;
      try {
        var skinNode = _skinCoordNode || _scene.getNamedNode(_skinMeshDef);
        if (skinNode) {
          var verts = [];
          for (var i = 0; i < globalFlat.length / 3; i++)
            verts.push(new X3D.SFVec3f(globalFlat[i*3], globalFlat[i*3+1], globalFlat[i*3+2]));
          skinNode.point = new X3D.MFVec3f(...verts);
          written++;
        }
      } catch(ee) { console.warn('global skin write failed:', ee.message); }

      // Write local coord nodes (eyeballs)
      Object.keys(localModified).forEach(function(def) {
        try {
          var node = _scene.getNamedNode(def); if (!node) return;
          var flat = localModified[def], verts = [];
          for (var i = 0; i < flat.length / 3; i++)
            verts.push(new X3D.SFVec3f(flat[i*3], flat[i*3+1], flat[i*3+2]));
          node.point = new X3D.MFVec3f(...verts);
          written++;
        } catch(ee) { console.warn('local eyeball write failed', def, ee.message); }
      });

      return written;
    }

    // ── Dispatch to correct morph mode ────────────────────────────────────
    function _applyMorph() {
      if (!_morphReady) return;
      var written = _globalMode ? _applyMorphGlobal() : _applyMorphSegment();
      _updateOverlayAus();
      var modeLabel = _globalMode ? 'global' : 'segment';
      document.getElementById('mo-status').textContent =
        written + ' node(s) written [' + modeLabel + ']';
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
        return '<div class="mo-au-active">' + kv[0].replace('Jin','') +
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

        _discoverFaceCoords();

        // Fetch X3D to read globalIndices, then complete init
        _fetchGlobalIndices('__X3D_SRC__', function() {
          var allOk = _cacheRestPoses();
          _loadAuData();
          _morphReady = true;
          var modeLabel = _globalMode ? ' [global mesh]' : ' [segment]';
          document.getElementById('mo-status').textContent =
            (allOk ? 'morph driver ready' : 'some coords missing') + modeLabel;
        });

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
            // For Mixamo avatars Timer1 runs continuously and overwrites poses.
            // For Cindy-style avatars the animation timers are already disabled
            // during pose mode so we only stop what's actually running.
            ['Timer1','DefaultTimer','WalkTimer','RunTimer','JumpTimer',
             'KickTimer','PitchTimer','YawTimer','RollTimer'].forEach(function(def) {
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
          if (_morphReady) _applyMorph();
          console.log('morph:', auName, weight.toFixed(3));

        } else if (msg.type === 'enableTimer') {
          // Start animation — set enabled=true only. loop/cycleInterval are
          // already set correctly in the X3D file. No startTime manipulation
          // needed; X_ITE restarts correctly from enabled=false -> enabled=true.
          _animTimersStopped = [];
          try {
            var timer = _scene.getNamedNode(msg.timerDEF);
            if (timer) {
              timer.enabled = true;
            } else {
              console.warn('enableTimer: node not found:', msg.timerDEF);
            }
          } catch(e) { console.warn('enableTimer error:', e.message); }

        } else if (msg.type === 'disableAllTimers') {
          // Disable all known animation timers (stop button)
          _animTimersStopped = [];
          ['Timer1','DefaultTimer','WalkTimer','RunTimer','JumpTimer',
           'KickTimer','PitchTimer','YawTimer','RollTimer'].forEach(function(def) {
            try { var t = _scene.getNamedNode(def); if (t) t.enabled = false; } catch(e) {}
          });

        } else if (msg.type === 'getCoordPositions') {
          // Read current point values from a named Coordinate node.
          // Used by face AU capture to snapshot rest or posed vertex positions.
          // Returns { type:'coordPositions', region, points:[x,y,z,...] }
          var coordDef = msg.coordDef;  // e.g. 'JackCoord_skull'
          var region   = msg.region;    // e.g. 'skull'
          var coordNode = null;
          try { coordNode = _scene.getNamedNode(coordDef); } catch(e) {}
          var pts = [];
          if (coordNode) {
            try {
              var pf = coordNode.getField('point');
              var n  = pf.length;
              for (var i = 0; i < n; i++) {
                var p = pf.getValue(i);
                pts.push(p.x, p.y, p.z);
              }
            } catch(e) { console.warn('getCoordPositions error:', e.message); }
          }
          evt.source.postMessage({
            type:   'coordPositions',
            region: region,
            coordDef: coordDef,
            points: pts,
            found:  coordNode !== null
          }, '*');
        }
      } catch(e) { console.warn('SAI write error:', e.message, msg); }
    });
  </script>
</body>
</html>"""
    html = html.replace('__X3D_SRC__',          x3d_src)
    html = html.replace('__EXPRESSIONS_URL__',  _expressions_url)

    return html, 200, {'Content-Type': 'text/html'}


@app.route('/avatar/list', methods=['GET'])
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

import base64  as _b64
import shutil  as _shutil_hanim
import xml.etree.ElementTree as _ET_hanim

_X3D_NS = 'https://www.web3d.org/specifications/x3d-4.0.xsd'


def _hanim_base_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def _avatar_dir() -> str:
    return os.path.join(_hanim_base_dir(), 'static', 'avatars')


def _cultivar_xml_path(cultivar_name: str) -> str:
    safe = cultivar_name.strip().replace(' ', '_')
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


def _hanim_backup(filepath: str) -> None:
    """Write .bak copy if file exists, overwriting any previous backup."""
    if os.path.exists(filepath):
        _shutil_hanim.copy2(filepath, filepath + '.bak')


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
    Prefers DEF containing 'TextureAtlas' (Jin convention).
    Falls back to first ImageTexture found in tree (with or without namespace).
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

    displacers: list of { au: 'JinBlink', weight: 0.75 }

    DEF naming convention (Jin/Colson): <Mesh>_MorphInterpolator_<AUName>
    We match on the AU name suffix so all mesh variants are updated.

    Returns count of displacer nodes updated.
    """
    if not displacers:
        return 0

    # Build a lookup: au_name -> weight
    au_map = {d['au']: float(d['weight']) for d in displacers if 'au' in d}
    if not au_map:
        return 0

    ns_prefix = '{https://www.web3d.org/specifications/x3d-namespaces}'
    updated = 0

    for el in scene_el.iter():
        tag = el.tag.replace(ns_prefix, '')
        if tag != 'HAnimDisplacer':
            continue
        def_val = el.get('DEF') or ''
        # Match suffix: _<AUName>
        for au_name, weight in au_map.items():
            if def_val.endswith('_' + au_name):
                el.set('weight', str(round(weight, 6)))
                updated += 1
                break  # one AU per displacer node

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


def _write_clip_nodes(scene_el, clips: list, existing_routes: list) -> tuple:
    """
    Append TimeSensor + OrientationInterpolator nodes for each clip, then
    re-append all ROUTEs (existing + new clip ROUTEs) as the last nodes in
    the Scene element.  Enforces ROUTE-last invariant regardless of clips[].

    In Phase 1, clips is [] — only existing_routes are re-appended last.
    In Phase 2, clips[] is populated from the editor's keyframe state.

    Returns (clips_written: int, routes_written: int).
    """
    ns = _X3D_NS
    clips_written = 0
    new_routes    = list(existing_routes)

    for clip in clips:
        name     = clip.get('name', 'Default')
        timer_def = clip.get('timerDEF', f'{name}Timer')
        cycle    = float(clip.get('cycleInterval', 6.0))
        loop     = 'true' if clip.get('loop', True) else 'false'
        keyframes = clip.get('keyframes', [])

        # TimeSensor — enabled="false" invariant
        ts = _ET_hanim.SubElement(scene_el, f'{{{ns}}}TimeSensor')
        ts.set('DEF',           timer_def)
        ts.set('cycleInterval', str(cycle))
        ts.set('loop',          loop)
        ts.set('enabled',       'false')

        # OrientationInterpolators per joint
        joint_names = set()
        for kf in keyframes:
            joint_names.update(kf.get('joints', {}).keys())

        for joint in sorted(joint_names):
            interp_def = f'{name}Interp_{joint}'
            keys, key_vals = [], []
            for kf in sorted(keyframes, key=lambda k: k.get('t', 0.0)):
                rot = kf['joints'].get(joint)
                if rot and len(rot) == 4:
                    keys.append(str(round(kf.get('t', 0.0), 4)))
                    key_vals.append(' '.join(str(round(v, 6)) for v in rot))
            if not keys:
                continue
            interp = _ET_hanim.SubElement(scene_el, f'{{{ns}}}OrientationInterpolator')
            interp.set('DEF',      interp_def)
            interp.set('key',      ' '.join(keys))
            interp.set('keyValue', ' '.join(key_vals))
            # ROUTEs for this interpolator
            new_routes.append({'fromNode': timer_def,  'fromField': 'fraction_changed',
                                'toNode':   interp_def, 'toField':   'set_fraction'})
            new_routes.append({'fromNode': interp_def, 'fromField': 'value_changed',
                                'toNode':   joint,      'toField':   'rotation'})

        clips_written += 1

    # Deduplicate and append all ROUTEs last — INVARIANT
    seen_r   = set()
    unique_r = []
    for r in new_routes:
        key = (r.get('fromNode',''), r.get('fromField',''),
               r.get('toNode',''),  r.get('toField',''))
        if key not in seen_r:
            seen_r.add(key)
            unique_r.append(r)

    for r_attrib in unique_r:
        re_el = _ET_hanim.SubElement(scene_el, f'{{{ns}}}ROUTE')
        for k, v in r_attrib.items():
            re_el.set(k, v)

    return clips_written, len(unique_r)


@app.route('/hanim/skin_upload', methods=['POST'])
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


@app.route('/hanim/export', methods=['POST'])
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
      displacers:  [ { def, weight } ]
    }

    Phase 1: skin URL + cultivar XML (HAnimFigure/Receptivity/Behaviors) only.
    Phase 2: clips[] populated — TimeSensor + OrientationInterpolator nodes written.

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
    _remove_routes(scene_el)

    clips_written, routes_written = _write_clip_nodes(scene_el, clips, existing_routes)

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

    if clips:
        cultivar_def.behavior_clips = []
        for clip in clips:
            c = {
                'name':     clip.get('name', 'Default'),
                'timerDEF': clip.get('timerDEF', f'{clip.get("name","Default")}Timer'),
                'loop':     bool(clip.get('loop', True)),
                'priority': int(clip.get('priority', 0)),
            }
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
            cultivar_def.behavior_clips.append(c)
        p0 = [c for c in cultivar_def.behavior_clips if c.get('priority', 0) == 0]
        cultivar_def.behavior_default = (
            p0[0]['name'] if p0 else cultivar_def.behavior_clips[0]['name']
        )

    # ── Atomic triple-write ──────────────────────────────────────────────
    # 1. Back up all three files (expressions XML may not exist yet — that is fine)
    _hanim_backup(x3d_filepath)
    _hanim_backup(cultivar_filepath)
    _hanim_backup(expressions_filepath)

    new_x3d_xml      = _serialise_x3d(xml_decl, x3d_root)
    new_cultivar_xml = cultivar_def.to_xml()

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

    _expr_basename = os.path.basename(expressions_filepath)
    return jsonify({
        'status':               'ok',
        'hanim_path':           f'/static/avatars/{os.path.basename(hanim_src)}',
        'cultivar_path':        f'cultivars/cultivar_{cultivar_name}.xml',
        'expressions_path':     f'/static/avatars/{_expr_basename}',
        'clips_written':        clips_written,
        'routes_written':       routes_written,
        'skin_updated':         skin_updated,
        'displacers_updated':   displacers_updated,
        'expressions_written':  expressions_written,
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
        'parent': parent_name,
        'region': _joint_region(display_name),
    })

    # Recurse — pass DEF as parent context so parent field is consistent
    for child in el:
        _walk_joints(child, def_val, joints)


@app.route('/hanim/joints', methods=['GET'])
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
            # Derive a human-readable name:
            # Use description attr if present, else strip 'Timer' suffix,
            # else use the DEF as-is. 'Timer1' → 'mixamo clip 1'.
            desc = el.get('description', '').strip()
            if desc:
                name = desc
            else:
                name = def_val.replace('Timer', '').strip()
                if not name or name.isdigit():
                    name = f'clip {name}' if name.isdigit() else def_val
            try:
                cycle = float(el.get('cycleInterval', 6.0))
            except (TypeError, ValueError):
                cycle = 6.0
            clips.append({
                'name':          name,
                'timerDEF':      def_val,
                'cycleInterval': cycle,
                'loop':          el.get('loop', 'true').lower() == 'true',
                'enabled':       el.get('enabled', 'false').lower() == 'true',
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


@app.route('/hanim/wire-joints', methods=['POST'])
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


@app.route('/hanim/normalize-joints', methods=['POST'])
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

    # Upsert HAnimFigure — update src if exists, else create
    # Search with and without namespace to avoid creating duplicates
    fig_el = root.find(_ns_tag('HAnimFigure')) or root.find('HAnimFigure')
    if fig_el is None:
        fig_el = _ET.Element('HAnimFigure')
        root.append(fig_el)
    fig_el.set('src', 'avatars/' + os.path.basename(hanim_src))

    # Append JointMap after HAnimFigure
    root.append(jm_el)

    _ET.indent(root, space='  ')
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + \
               _ET.tostring(root, encoding='unicode')

    tmp = cultivar_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(xml_text)
    os.replace(tmp, cultivar_path)


@app.route('/hanim/fix-face-coords', methods=['POST'])
def hanim_fix_face_coords():
    """
    POST /hanim/fix-face-coords
    Body: { hanim_src: str }

    Fix Blender X3D export bug: named Coordinate nodes used as morph-target
    data holders (e.g. JackCoord_skull) sit inside a Group and have no
    containerField attribute.  X_ITE infers containerField='coord' by default,
    then rejects them because Group has no coord field.

    Fix: scan every <Coordinate .../> tag across its FULL extent (point data
    can be thousands of chars before the DEF attribute appears).  For any tag
    that has a DEF attribute but lacks containerField, inject
    containerField="point" right after <Coordinate.

    Anonymous geometry Coordinate nodes (no DEF attribute) are left strictly
    alone — they live inside IndexedTriangleSets where the default 'coord'
    containerField is correct.  skinCoord nodes already have containerField
    and are skipped by the 'already has containerField' check.

    containerField="point" is harmless for SAI DEF lookup — the morph driver
    reads these nodes by name, not via the scene graph hierarchy.

    Safe to run on any avatar; returns fixed=0 if no changes needed.
    Atomic write: .tmp + os.replace(). .bak created first.

    Returns: { status, fixed, hanim_path }
    """
    import re as _re_ffc

    body      = request.get_json(silent=True) or {}
    hanim_src = (body.get('hanim_src') or '').strip()
    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400

    filepath = _hanim_x3d_path(hanim_src)
    if not os.path.exists(filepath):
        return jsonify({'status': 'error',
                        'error': f'HAnim X3D not found: {os.path.basename(hanim_src)}'}), 404

    with open(filepath, 'r', encoding='utf-8') as fh:
        content = fh.read()

    # Scan every <Coordinate .../> across its FULL tag extent.
    # A regex that stops at '>' would miss DEF attributes buried after
    # thousands of chars of point data, so we find the closing '/>' explicitly.
    inserts = []  # list of (char_position, text_to_insert)

    for m in _re_ffc.finditer(r'<Coordinate ', content):
        tag_start = m.start()
        tag_end   = content.find('/>', tag_start)
        if tag_end == -1:
            continue
        full_tag = content[tag_start:tag_end + 2]

        # Skip if already has containerField (includes skinCoord nodes)
        if 'containerField' in full_tag:
            continue

        # Skip anonymous geometry nodes — only fix named (DEF) nodes
        if not _re_ffc.search(r'DEF=["\']', full_tag):
            continue

        # Named Coordinate without containerField — inject "point"
        inserts.append((tag_start + len('<Coordinate '), 'containerField="point" '))

    if not inserts:
        return jsonify({'status': 'ok', 'fixed': 0,
                        'hanim_path': os.path.basename(filepath),
                        'note': 'No named Coordinate nodes without containerField found'})

    # Apply in reverse order so earlier positions stay valid
    for pos, text in sorted(inserts, reverse=True):
        content = content[:pos] + text + content[pos:]

    try:
        _hanim_backup(filepath)
        tmp = filepath + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(content)
        os.replace(tmp, filepath)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'Write failed: {exc}'}), 500

    return jsonify({
        'status':     'ok',
        'fixed':      len(inserts),
        'hanim_path': os.path.basename(filepath),
    })


@app.route('/hanim/save-face-morph', methods=['POST'])
def hanim_save_face_morph():
    """
    POST /hanim/save-face-morph
    Body: { cultivar, region, pose, coord_def, points: [x,y,z,...] }

    Store captured coordinate positions for one face region in the cultivar XML.
    pose is either 'rest' or 'morph'.
    coord_def is the DEF name of the Coordinate node (e.g. 'JackCoord_skull').

    Cultivar XML structure added:
      <FaceMorphs>
        <Region name="skull" coord_def="JackCoord_skull">
          <Pose name="rest"  points="x y z x y z ..." />
          <Pose name="morph" points="x y z x y z ..." />
        </Region>
        ...
      </FaceMorphs>

    Returns: { status, cultivar, region, pose, point_count }
    """
    import xml.etree.ElementTree as _ET_fm

    body      = request.get_json(silent=True) or {}
    cultivar  = (body.get('cultivar')   or '').strip()
    region    = (body.get('region')     or '').strip()
    pose      = (body.get('pose')       or '').strip()   # 'rest' or 'morph'
    coord_def = (body.get('coord_def')  or '').strip()
    points    = body.get('points', [])

    if not all([cultivar, region, pose, coord_def]):
        return jsonify({'status': 'error',
                        'error': 'cultivar, region, pose, coord_def required'}), 400
    if pose not in ('rest', 'morph'):
        return jsonify({'status': 'error',
                        'error': 'pose must be "rest" or "morph"'}), 400
    if not points or len(points) % 3 != 0:
        return jsonify({'status': 'error',
                        'error': f'points must be non-empty multiple of 3 (got {len(points)})'}), 400

    cultivar_path = _cultivar_xml_path(cultivar)
    if not os.path.exists(cultivar_path):
        return jsonify({'status': 'error',
                        'error': f'Cultivar not found: {cultivar}'}), 404

    tree = _ET_fm.parse(cultivar_path)
    root = tree.getroot()

    # Get or create FaceMorphs element
    fm_el = root.find('FaceMorphs')
    if fm_el is None:
        fm_el = _ET_fm.SubElement(root, 'FaceMorphs')

    # Get or create Region element
    reg_el = None
    for r in fm_el.findall('Region'):
        if r.get('name') == region:
            reg_el = r
            break
    if reg_el is None:
        reg_el = _ET_fm.SubElement(fm_el, 'Region')
        reg_el.set('name', region)
    reg_el.set('coord_def', coord_def)

    # Remove existing Pose with same name
    for p in reg_el.findall('Pose'):
        if p.get('name') == pose:
            reg_el.remove(p)

    # Add new Pose
    pose_el = _ET_fm.SubElement(reg_el, 'Pose')
    pose_el.set('name', pose)
    pose_el.set('points', ' '.join(f'{v:.6f}' for v in points))

    # Write back
    _ET_fm.indent(root, space='  ')
    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n' + \
               _ET_fm.tostring(root, encoding='unicode')
    tmp = cultivar_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as fh:
        fh.write(xml_text)
    os.replace(tmp, cultivar_path)

    return jsonify({
        'status':      'ok',
        'cultivar':    cultivar,
        'region':      region,
        'pose':        pose,
        'point_count': len(points) // 3,
    })


@app.route('/hanim/inject-face-aus', methods=['POST'])
def hanim_inject_face_aus():
    """
    POST /hanim/inject-face-aus
    Body: { hanim_src, cultivar }

    Read FaceMorphs data from cultivar XML and inject AnimationAdapter
    CoordinateInterpolator nodes into the target X3D file.

    For each Region that has both 'rest' and 'morph' poses:
      1. Inject <CoordinateInterpolator DEF="AnimationAdapter_{region}"
                  key="0 1" keyValue="{rest_points} {morph_points}" />
      2. Inject <ROUTE fromNode="AnimationAdapter_{region}"
                        fromField="value_changed"
                        toNode="{coord_def}" toField="point" />

    Idempotent: strips existing AnimationAdapter_{region} nodes first.
    FaceController Script already in X3D handles the au_name/au_weight
    → set_fraction routing at runtime.

    Returns: { status, injected, skipped, regions }
    """
    import re as _re_fau
    import xml.etree.ElementTree as _ET_fau

    body      = request.get_json(silent=True) or {}
    hanim_src = (body.get('hanim_src') or '').strip()
    cultivar  = (body.get('cultivar')  or '').strip()

    if not hanim_src:
        return jsonify({'status': 'error', 'error': 'hanim_src required'}), 400
    if not cultivar:
        return jsonify({'status': 'error', 'error': 'cultivar required'}), 400

    target_path   = _hanim_x3d_path(hanim_src)
    cultivar_path = _cultivar_xml_path(cultivar)

    for path, label in [(target_path, 'Target X3D'), (cultivar_path, 'Cultivar XML')]:
        if not os.path.exists(path):
            return jsonify({'status': 'error',
                            'error': f'{label} not found: {os.path.basename(path)}'}), 404

    # Read FaceMorphs from cultivar
    tree = _ET_fau.parse(cultivar_path)
    root = tree.getroot()
    fm_el = root.find('FaceMorphs')
    if fm_el is None:
        return jsonify({'status': 'error',
                        'error': 'No FaceMorphs in cultivar — capture rest+morph poses first'}), 400

    # Collect complete regions (must have both rest and morph)
    regions = []
    skipped = []
    for reg in fm_el.findall('Region'):
        name      = reg.get('name', '').strip()
        coord_def = reg.get('coord_def', '').strip()
        poses = {p.get('name'): p.get('points', '') for p in reg.findall('Pose')}
        if 'rest' in poses and 'morph' in poses and name and coord_def:
            regions.append({
                'name':      name,
                'coord_def': coord_def,
                'rest':      poses['rest'],
                'morph':     poses['morph'],
            })
        else:
            skipped.append(name or '(unnamed)')

    if not regions:
        return jsonify({'status': 'error',
                        'error': 'No complete regions (need both rest and morph captured)',
                        'skipped': skipped}), 400

    # Read target X3D
    with open(target_path, 'r', encoding='utf-8') as fh:
        target_text = fh.read()

    # Strip existing AnimationAdapter nodes (idempotent)
    region_names = [r['name'] for r in regions]
    for name in region_names:
        # CoordinateInterpolator
        target_text = _re_fau.sub(
            rf'<CoordinateInterpolator\s+DEF="AnimationAdapter_{re.escape(name)}"[^/]*/>\s*',
            '', target_text)
        # ROUTE from AnimationAdapter
        target_text = _re_fau.sub(
            rf'<ROUTE\s+fromNode="AnimationAdapter_{re.escape(name)}"[^/]*/>\s*',
            '', target_text)

    # Build injection XML
    parts = []
    for r in regions:
        interp_def = f'AnimationAdapter_{r["name"]}'
        key_value  = r['rest'] + ' ' + r['morph']
        parts.append(
            f'<CoordinateInterpolator DEF="{interp_def}" key="0 1" keyValue="{key_value}" />'
        )
        parts.append(
            f'<ROUTE fromNode="{interp_def}" fromField="value_changed" '
            f'toNode="{r["coord_def"]}" toField="point" />'
        )

    if '</Scene>' not in target_text:
        return jsonify({'status': 'error',
                        'error': 'No </Scene> tag in target X3D'}), 500

    target_text = target_text.replace(
        '</Scene>',
        '\n'.join(parts) + '\n</Scene>',
        1
    )

    try:
        _hanim_backup(target_path)
        tmp = target_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as fh:
            fh.write(target_text)
        os.replace(tmp, target_path)
    except Exception as exc:
        return jsonify({'status': 'error', 'error': f'Write failed: {exc}'}), 500

    return jsonify({
        'status':   'ok',
        'injected': len(regions),
        'skipped':  skipped,
        'regions':  [r['name'] for r in regions],
        'hanim_path': os.path.basename(target_path),
    })


@app.route('/hanim/get-face-morph-status', methods=['POST'])
def hanim_get_face_morph_status():
    """
    POST /hanim/get-face-morph-status
    Body: { cultivar }

    Returns which regions have rest/morph poses captured in the cultivar.
    Used by the editor to show capture progress.

    Returns: { status, regions: { skull: {rest:bool, morph:bool, coord_def:str}, ... } }
    """
    import xml.etree.ElementTree as _ET_gfm

    body     = request.get_json(silent=True) or {}
    cultivar = (body.get('cultivar') or '').strip()
    if not cultivar:
        return jsonify({'status': 'error', 'error': 'cultivar required'}), 400

    cultivar_path = _cultivar_xml_path(cultivar)
    if not os.path.exists(cultivar_path):
        return jsonify({'status': 'error',
                        'error': f'Cultivar not found: {cultivar}'}), 404

    try:
        tree = _ET_gfm.parse(cultivar_path)
        root = tree.getroot()
        fm_el = root.find('FaceMorphs')
    except Exception:
        fm_el = None

    result = {}
    if fm_el is not None:
        for reg in fm_el.findall('Region'):
            name      = reg.get('name', '').strip()
            coord_def = reg.get('coord_def', '').strip()
            poses     = {p.get('name') for p in reg.findall('Pose')}
            if name:
                result[name] = {
                    'rest':      'rest'  in poses,
                    'morph':     'morph' in poses,
                    'coord_def': coord_def,
                }

    return jsonify({'status': 'ok', 'regions': result})


@app.route('/hanim/ingest', methods=['POST'])
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



@app.route('/hanim/ingest-mixamo', methods=['POST'])
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
        anims_el = cv_root.find('Animations')
        if anims_el is None:
            anims_el = _ET_mix.SubElement(cv_root, 'Animations')

        # Build name lookup from existing clips (keyed by timerDEF) so that
        # re-ingest preserves names the user already has in the cultivar.
        existing_clip_names = {
            c.get('timerDEF'): c.get('name')
            for c in anims_el.findall('Clip')
            if c.get('timerDEF') and c.get('name')
        }
        # Clear all existing clips — we'll rewrite from the file's timer list
        for old_clip in anims_el.findall('Clip'):
            anims_el.remove(old_clip)

        # Register every animation TimeSensor as a clip
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


@app.route('/scene/x3d/list', methods=['GET'])
def list_x3d_scenes():
    """
    List available X3D files in static/x3d/.
    Returns newest-first, same pattern as /arc/playback.
    """
    x3d_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d')
    os.makedirs(x3d_dir, exist_ok=True)
    files = []
    for fname in os.listdir(x3d_dir):
        if fname.endswith('.x3d'):
            fpath = os.path.join(x3d_dir, fname)
            mtime = os.path.getmtime(fpath)
            files.append({'filename': fname, 'mtime': mtime})
    files.sort(key=lambda f: f['mtime'], reverse=True)
    return jsonify({'files': [f['filename'] for f in files]})


@app.route('/scene/save/zones', methods=['POST'])
def save_zone_xml():
    """
    Write zone XML from Scene Composer to zones/<filename>.
    Called by exportZoneXML() in mccf_scene_composer.html.
    Body: { filename: "garden_001_zones.xml", content: "<ZoneSet>...</ZoneSet>" }
    """
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    content  = data.get('content', '').strip()
    if not filename or not content:
        return jsonify({'status': 'error', 'error': 'filename and content required'}), 400
    # Sanitise — filename only, no path traversal
    filename = os.path.basename(filename)
    zones_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zones')
    os.makedirs(zones_dir, exist_ok=True)
    filepath = os.path.join(zones_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'path': f'zones/{filename}'})


@app.route('/scene/save/scene', methods=['POST'])
def save_scene_xml():
    """
    Write scene XML from Scene Composer to scenes/<filename>.
    Called by exportSceneXML() in mccf_scene_composer.html.
    Body: { filename: "garden_001_scene.xml", content: "<Scene>...</Scene>" }
    """
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    content  = data.get('content', '').strip()
    if not filename or not content:
        return jsonify({'status': 'error', 'error': 'filename and content required'}), 400
    filename = os.path.basename(filename)
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    os.makedirs(scenes_dir, exist_ok=True)
    filepath = os.path.join(scenes_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'path': f'scenes/{filename}'})


@app.route('/scenes', methods=['GET'])
def list_scenes():
    """
    List scene XML files in scenes/ directory.
    Returns filename, cultivars found, waypoint count.
    """
    import re as _re
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    if not os.path.isdir(scenes_dir):
        return jsonify({'files': [], 'scenes_dir': scenes_dir})
    files = []
    for fname in sorted(os.listdir(scenes_dir)):
        if not fname.endswith('.xml'):
            continue
        fpath = os.path.join(scenes_dir, fname)
        size  = os.path.getsize(fpath)
        cultivars = []
        waypoint_count = 0
        try:
            with open(fpath, encoding='utf-8') as f:
                raw = f.read(4000)
            cultivars = _re.findall(r'cultivar="([^"]+)"', raw)
            waypoint_count = len(_re.findall(r'<Waypoint ', raw))
        except Exception:
            pass
        files.append({
            'filename':       fname,
            'size':           size,
            'cultivars':      list(dict.fromkeys(cultivars)),
            'waypoint_count': waypoint_count,
        })
    return jsonify({'files': files, 'count': len(files)})


@app.route('/scene/list/scenes', methods=['GET'])
def list_scenes_for_composer():
    """
    List scene XML files in scenes/ directory.
    Used by the composer scene dropdown (GET /scene/list/scenes).
    Returns { files: ["garden_001_scene.xml", ...] } sorted newest-first.
    """
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    if not os.path.isdir(scenes_dir):
        return jsonify({'files': [], 'scenes_dir': scenes_dir})
    files = sorted(
        [f for f in os.listdir(scenes_dir) if f.endswith('.xml')],
        reverse=True
    )
    return jsonify({'files': files, 'scenes_dir': scenes_dir})


@app.route('/media/list', methods=['GET'])
def list_media_files():
    """
    List audio files in static/media/ directory.
    Used by Scene Composer sound pickers (GET /media/list).
    Returns { files: ["garden_theme.mp3", ...] } sorted alphabetically.
    Same directory the X3D Loader references as media/filename.

    Optional query params:
      subdir=convolver  — scan static/media/convolver/ and prefix filenames
                          with "convolver/" so the composer builds the
                          correct url: media/convolver/file.wav
      ext=wav           — filter to a single extension (wav only, etc.)
    """
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d', 'media')
    subdir = request.args.get('subdir', '').strip().strip('/')
    ext_filter = request.args.get('ext', '').strip().lower()

    scan_dir = os.path.join(media_dir, subdir) if subdir else media_dir
    if not os.path.isdir(scan_dir):
        return jsonify({'files': [], 'media_dir': scan_dir})

    AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.m4a', '.mid', '.midi'}
    allowed = {'.' + ext_filter} if ext_filter else AUDIO_EXTS

    files = sorted([
        (subdir + '/' + f if subdir else f)
        for f in os.listdir(scan_dir)
        if os.path.isfile(os.path.join(scan_dir, f))
        and os.path.splitext(f)[1].lower() in allowed
        and not f.startswith('.')
    ])
    return jsonify({'files': files, 'media_dir': scan_dir})


@app.route('/scene/load/scene/raw', methods=['GET'])
def get_scene_xml_raw():
    """
    GET /scene/load/scene/raw?filename=garden_001_scene.xml
    Returns the raw scene XML text. Used by Scene Composer to restore
    Chorus config on scene load (not returned by /scene/load/scene JSON endpoint).
    """
    filename = os.path.basename(request.args.get('filename', '').strip())
    if not filename:
        return 'filename required', 400
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    filepath   = os.path.join(scenes_dir, filename)
    if not os.path.exists(filepath):
        return f'Not found: {filename}', 404
    with open(filepath, encoding='utf-8') as f:
        content = f.read()
    return content, 200, {'Content-Type': 'application/xml; charset=utf-8'}


@app.route('/scene/load/scene', methods=['POST'])
def load_scene_xml():
    """
    Parse a saved scene XML and return full composer state.
    Called by loadSceneFromDropdown() in mccf_scene_composer.html.
    Body: { "filename": "garden_001_scene.xml" }

    Returns:
    {
        sceneConfig:   { name, width, depth, description },
        zones:         { id: { id, name, zone_type, location:[x,0,z], radius, color } },
        agents:        { name: { name, position, voice, color, weights, ... } },
        placedAgents:  { name: { name, position:[x,0,z], voice, color, ... } },
        waypoints:     { name: { name, label, zone, position:[x,0,z], qaLines:[...] } },
        paths:         { name: { name, agent, waypoints:[wpName,...] } }
    }
    """
    import xml.etree.ElementTree as ET
    import re as _re

    data     = request.get_json() or {}
    filename = os.path.basename(data.get('filename', '').strip())
    if not filename:
        return jsonify({'error': 'filename required'}), 400

    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    filepath   = os.path.join(scenes_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({'error': f'File not found: {filename}'}), 404

    try:
        with open(filepath, encoding='utf-8') as f:
            raw = f.read()
    except Exception as e:
        return jsonify({'error': f'Could not read file: {e}'}), 500

    try:
        # Strip namespace prefixes that confuse ElementTree
        clean = _re.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', raw)
        clean = _re.sub(r'<(\w+):(\w+)', r'<\2', clean)
        clean = _re.sub(r'</(\w+):(\w+)', r'</\2', clean)
        root  = ET.fromstring(clean)
    except Exception as e:
        return jsonify({'error': f'XML parse error: {e}'}), 500

    # ── sceneConfig ───────────────────────────────────────────────────────
    scene_id = root.get('id', filename.replace('_scene.xml', ''))
    width    = float(root.get('width', 40))
    depth    = float(root.get('depth', 40))
    scene_config = {
        'name':        scene_id,
        'width':       int(width),
        'depth':       int(depth),
        'description': ''
    }

    # ── placedAgents from <EmotionalArc cultivar="..." voice="..."> ───────
    AGENT_COLORS  = ['#60a8f0','#4af0a8','#f0c060','#f06060','#c080f0','#f09040']
    placed_agents = {}
    for idx, ea in enumerate(root.findall('EmotionalArc')):
        name  = ea.get('cultivar', '').strip()
        voice = ea.get('voice', '')
        if not name:
            continue
        sp = ea.find('StartPosition')
        x  = float(sp.get('x', width  / 2)) if sp is not None else width  / 2
        z  = float(sp.get('z', depth  / 2)) if sp is not None else depth  / 2
        col = AGENT_COLORS[idx % len(AGENT_COLORS)]
        placed_agents[name] = {
            'name':        name,
            'position':    [round(x, 2), 0, round(z, 2)],
            'voice':       voice,
            'color':       col,
            'weights':     {'E': 0.35, 'B': 0.25, 'P': 0.25, 'S': 0.25},
            'regulation':  0.5,
            'disposition': ''
        }

    # agents roster mirrors placedAgents
    agents = {n: dict(a) for n, a in placed_agents.items()}

    # ── waypoints + inferred zones from <Waypoints><Waypoint> ────────────
    ZONE_COLORS = {
        'temple':   '#c080f0',
        'pool':     '#60a8f0',
        'training': '#4af0a8',
        'dorm':     '#f0c060',
        'garden':   '#4af0a8',
        'library':  '#f09040',
    }
    waypoints      = {}
    zones_inferred = {}

    wp_container = root.find('Waypoints')
    for wp_el in (wp_container.findall('Waypoint') if wp_container is not None else []):
        wp_name  = wp_el.get('name',  '').strip()
        wp_label = wp_el.get('label', wp_name)
        zone_id  = wp_el.get('zone',  '').strip()
        pos_x    = float(wp_el.get('pos_x', width  / 2))
        pos_z    = float(wp_el.get('pos_z', depth  / 2))

        qa_lines = []
        for child in wp_el:
            if child.tag in ('Question', 'Response', 'Statement'):
                txt = (child.text or '').strip()
                if txt:
                    qa_lines.append({
                        'type':    child.tag,
                        'speaker': child.get('speaker', ''),
                        'text':    txt
                    })

        waypoints[wp_name] = {
            'name':     wp_name,
            'label':    wp_label,
            'zone':     zone_id,
            'position': [round(pos_x, 2), 0, round(pos_z, 2)],
            'qaLines':  qa_lines
        }

        # Infer zone from waypoint if not already seen
        if zone_id and zone_id not in zones_inferred:
            col = ZONE_COLORS.get(zone_id.lower(), '#888888')
            zones_inferred[zone_id] = {
                'id':        zone_id,
                'name':      wp_label,
                'zone_type': zone_id,
                'location':  [round(pos_x, 2), 0, round(pos_z, 2)],
                'radius':    4,
                'color':     col
            }

    # ── paths from <Paths><Path name agent><PathWaypoint ref> ───────────
    paths = {}
    paths_el = root.find('Paths')
    if paths_el is not None:
        for path_el in paths_el.findall('Path'):
            p_name  = path_el.get('name', '').strip()
            p_agent = path_el.get('agent', '').strip()
            if not p_name:
                continue
            wp_refs = [pw.get('ref', '').strip()
                       for pw in path_el.findall('PathWaypoint')
                       if pw.get('ref', '').strip()]
            paths[p_name] = {
                'name':      p_name,
                'agent':     p_agent,
                'waypoints': wp_refs
            }

    # Notify Chorus manager — parse scene XML for <Chorus> zone extension.
    try:
        cm = app.config.get('_chorus_manager')
        if cm is not None:
            cm.load_config_from_scene_xml(raw)
    except Exception:
        pass

    return jsonify({
        'sceneConfig':  scene_config,
        'zones':        zones_inferred,
        'agents':       agents,
        'placedAgents': placed_agents,
        'waypoints':    waypoints,
        'paths':        paths
    })


# ---------------------------------------------------------------------------
# Global engine state
# ---------------------------------------------------------------------------

field = CoherenceField()

# Arc coherence history for genre classification
# Keyed by cultivar name, value is list of {step, coherence, E, B, P, S}
_arc_coherence_history = {}
librarian = Librarian(field)
gardener = Gardener(field)
cultivars: dict = {}   # name → agent config snapshot

# ---------------------------------------------------------------------------
# AgentRuntimeState — constitutional/expressive split (ϕ + ϵ)
#
# Each agent carries two CV vectors per tick:
#   constitutional_cv (ϕ) — immutable per tick; set by arc/record from authored
#                            weights + sentiment + arc pressure.  Character as
#                            written walking into the scene.
#   expressive_cv     (ϵ) — mutable; written by couplers each tick, bounded by
#                            max_drift = 1.0 - regulation.  What the scene is
#                            doing to that character right now.
#
# Until couplers are wired, ϵ == ϕ (delta = 0).  The split is the membrane
# that makes relational drift possible without corrupting authored character.
#
# Constraint invariants (enforced here, respected by mccf_couplers.py):
#   - constitutional_cv is never written by couplers — read-only after arc/record
#   - expressive_cv drift per channel bounded: |ϵ_ch - ϕ_ch| ≤ max_drift
#   - max_drift = 1.0 - regulation  (high regulation → tight leash on ϵ)
#   - Constitutional vector E/B/P/S shape is never replaced or extended
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field as dc_field

@dataclass
class AgentRuntimeState:
    """
    Per-agent runtime state carrying the ϕ/ϵ split.

    constitutional_cv (ϕ): dict with keys E, B, P, S — set by arc/record,
        immutable until next arc/record call.
    expressive_cv (ϵ):     dict with keys E, B, P, S — written by couplers
        each tick; initialized equal to ϕ.
    regulation:            float 0-1, copied from Agent at record time.
        max_drift = 1.0 - regulation bounds ϵ per channel.
    last_record_time:      unix timestamp of last arc/record write to ϕ.
    last_tick_time:        unix timestamp of last coupler tick to ϵ (0 = never).
    """
    name:               str
    constitutional_cv:  dict = dc_field(default_factory=lambda: {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25})
    expressive_cv:      dict = dc_field(default_factory=lambda: {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25})
    regulation:         float = 0.7
    last_record_time:   float = 0.0
    last_tick_time:     float = 0.0
    # Attentional filter — per-channel receptivity to coupler influence (0.0–1.0).
    # Default 1.0 = fully receptive (current behaviour preserved).
    # Loaded from <Receptivity> in cultivar XML at arc/record time.
    # Filters incoming coupler deltas before the drift bound is applied.
    receptivity: dict = dc_field(default_factory=lambda: {'E': 1.0, 'B': 1.0, 'P': 1.0, 'S': 1.0})

    @property
    def max_drift(self) -> float:
        """Maximum per-channel deviation ϵ is permitted from ϕ."""
        return round(1.0 - self.regulation, 4)

    @property
    def observed_cv(self) -> dict:
        """ϕᵢ + ϵᵢ(t), clamped to [0,1] — the actual observable state."""
        return {
            k: round(max(0.0, min(1.0, self.constitutional_cv[k] + self.expressive_cv[k])), 4)
            for k in ('E', 'B', 'P', 'S')
        }

    def set_constitutional(self, E: float, B: float, P: float, S: float,
                           regulation: float = None) -> None:
        """
        Write ϕ from arc/record.  Also resets ϵ to ϕ (arc start = clean slate).
        Optionally refreshes regulation from the live Agent.
        Called only by arc/record — never by couplers.
        """
        self.constitutional_cv = {"E": round(E, 4), "B": round(B, 4),
                                   "P": round(P, 4), "S": round(S, 4)}
        # ϵ starts equal to ϕ; couplers will drift it from here
        self.expressive_cv = dict(self.constitutional_cv)
        if regulation is not None:
            self.regulation = regulation
        self.last_record_time = time.time()

    def apply_expressive_delta(self, deltas: dict) -> None:
        """
        Apply coupler-computed deltas to ϵ, enforcing drift bound per channel.
        deltas: dict with any subset of keys E, B, P, S.
        Called only by mccf_couplers.py — never by arc/record.
        """
        drift_cap = self.max_drift
        for ch in ("E", "B", "P", "S"):
            if ch not in deltas:
                continue
            # Attentional filter: scale incoming delta by per-channel receptivity
            # before applying drift bound.  High-B characters resist B-channel
            # influence; emotionally open characters accept E-channel signals fully.
            filtered_delta = deltas[ch] * self.receptivity.get(ch, 1.0)
            phi   = self.constitutional_cv[ch]
            eps   = self.expressive_cv[ch]
            new   = eps + filtered_delta
            # Clamp to [0, 1]
            new   = min(1.0, max(0.0, new))
            # Clamp drift from ϕ
            new   = min(phi + drift_cap, max(phi - drift_cap, new))
            self.expressive_cv[ch] = round(new, 4)
        self.last_tick_time = time.time()

    def as_dict(self) -> dict:
        """Serialise for API responses."""
        phi = self.constitutional_cv
        eps = self.expressive_cv
        return {
            "constitutional_cv": phi,
            "expressive_cv":     eps,
            "delta": {
                ch: round(eps[ch] - phi[ch], 4)
                for ch in ("E", "B", "P", "S")
            },
            "regulation":      round(self.regulation, 4),
            "max_drift":       self.max_drift,
            "last_record_time": self.last_record_time,
            "last_tick_time":   self.last_tick_time,
            "receptivity":      self.receptivity,
        }


# Registry: agent name → AgentRuntimeState
_agent_runtime: dict[str, AgentRuntimeState] = {}


def get_runtime(name: str, regulation: float = 0.7) -> AgentRuntimeState:
    """
    Return the AgentRuntimeState for `name`, creating it if absent.
    `regulation` is used only on first creation; subsequent updates come
    from set_constitutional() calls in arc/record.
    """
    if name not in _agent_runtime:
        _agent_runtime[name] = AgentRuntimeState(name=name, regulation=regulation)
    return _agent_runtime[name]


# ---------------------------------------------------------------------------
# Relational Dynamics — Extensions 1-4
# Day 26, 2026-05-25
# Spec: MCCF_Relational_Dynamics_Extension_Spec.md
# ---------------------------------------------------------------------------

import math as _math_rd

# ---------------------------------------------------------------------------
# Extension 4: Attentional Filter
# Per-channel receptivity lives on AgentRuntimeState (added above).
# Loaded from <Receptivity> in cultivar XML at arc/record time.
# Applied in apply_expressive_delta() before drift bound.
# No additional state needed here.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Extension 2: Emotional Salience Memory
# Extends _arc_coherence_history entries with salience, phase_fired,
# eps_delta, and timestamp fields.
# ---------------------------------------------------------------------------

def _compute_salience(coherence_delta: float,
                      eps_delta: float,
                      phase_fired: bool) -> float:
    """
    Salience = weighted combination of emotional intensity signals.
    Range: [0.0, 1.0]

    coherence_delta: absolute change in coherence vs. previous step
    eps_delta:       mean |ϵ - ϕ| across all channels at this step
    phase_fired:     True if T coupler / phase transition fired this tick
    """
    base = min(1.0, abs(coherence_delta) * 3.0 + eps_delta * 2.0)
    if phase_fired:
        base = min(1.0, base + 0.4)
    return round(base, 4)


# ---------------------------------------------------------------------------
# Extension 3: Bayesian Trust as Dynamic Link Strength
# Per-link Beta(α, β) prior over effective strength.
# Updated after each coupler tick based on convergence/divergence.
# ---------------------------------------------------------------------------

# Keyed by (src_name, tgt_name) — direction matters (asymmetric trust)
_link_trust: dict[tuple, dict] = {}


def _get_link_trust(src: str, tgt: str) -> dict:
    """Return (creating if absent) the Bayesian trust state for link src→tgt."""
    key = (src, tgt)
    if key not in _link_trust:
        _link_trust[key] = {
            'alpha':    2.0,   # Beta(2,2) — weak prior, uncertain, centred at 0.5
            'beta':     2.0,
            'ticks':    0,
            'last_sim': 0.0,
            'mu':       0.5,
        }
    return _link_trust[key]


def _update_link_trust(src: str, tgt: str,
                       sim_before: float, sim_after: float,
                       threshold: float = 0.01) -> float:
    """
    Update Beta prior for link src→tgt.
    Convergence (Δsim > threshold) → α += 1
    Divergence  (Δsim < -threshold) → β += 1
    Returns new posterior mean μ = α/(α+β).
    """
    trust = _get_link_trust(src, tgt)
    delta = sim_after - sim_before
    if delta > threshold:
        trust['alpha'] += 1.0
    elif delta < -threshold:
        trust['beta'] += 1.0
    trust['ticks'] += 1
    trust['last_sim'] = sim_after
    mu = trust['alpha'] / (trust['alpha'] + trust['beta'])
    trust['mu'] = round(mu, 4)
    return trust['mu']


# ---------------------------------------------------------------------------
# Extension 3: Controlled Forgetting
# ϵ residue persists between arc sessions, decaying by salience-weighted
# Ebbinghaus curve.  Off by default; opt-in per scene via <Continuity/>.
# ---------------------------------------------------------------------------

def _compute_arc_residue(agent_name: str) -> dict:
    """
    Compute ϵ residue from the most salient moment in the agent's coherence
    history.  Returns {E, B, P, S} delta to apply as initial ϵ seed after
    set_constitutional().  Returns zeros when:
      - no history exists
      - top salience < 0.1 (below perceptibility threshold)
      - residue has decayed below 0.005 per channel

    τ_base = 3600s (1 hour); SALIENCE_SCALE = 24 (high-salience → ~24h half-life)
    """
    history = _arc_coherence_history.get(agent_name, [])
    if not history:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    # Find most salient entry — entries without 'salience' default to 0
    best = max(history, key=lambda r: r.get('salience', 0.0))
    salience = best.get('salience', 0.0)
    if salience < 0.1:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    elapsed = time.time() - best.get('timestamp', time.time())
    tau = 3600.0 * (1.0 + salience * 24.0)
    decay = _math_rd.exp(-elapsed / tau)

    eps_delta = best.get('eps_delta', 0.0)
    magnitude = salience * eps_delta * decay

    if magnitude < 0.005:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    # Distribute residue proportionally across channels using constitutional CV
    runtime = _agent_runtime.get(agent_name)
    if not runtime:
        return {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0}

    phi = runtime.constitutional_cv
    total_phi = sum(phi.values()) or 1.0
    return {
        ch: round(phi[ch] / total_phi * magnitude, 4)
        for ch in ('E', 'B', 'P', 'S')
    }

# v2.0 — HotHouse integration
# emotional_field and x3d_adapter are initialized lazily after agents register
# because EmotionalField requires FieldAgent objects.
# Use get_emotional_field() to access — it rebuilds when agents change.
_emotional_field = None
_x3d_adapter = None
_emotional_field_agent_count = 0  # rebuild trigger

def get_emotional_field():
    """
    Return current EmotionalField built from registered core Agents.
    Rebuilds when the agent roster changes.
    EmotionalField uses FieldAgent (hotHouse), not core Agent —
    we bridge by reading channel weights from core agents.
    """
    global _emotional_field, _x3d_adapter, _emotional_field_agent_count
    current_count = len(field.agents)
    if current_count == 0:
        return None, None
    if _emotional_field is None or current_count != _emotional_field_agent_count:
        try:
            from mccf_hotHouse import EmotionalField, HotHouseX3DAdapter, FieldAgent
            fa_list = []
            for name, agent in field.agents.items():
                # Bridge: build FieldAgent from core Agent weights
                fa = FieldAgent(
                    name=name,
                    ideology=dict(agent.weights),
                    alpha_self={ch: 0.1 for ch in agent.weights},
                    alpha_alignment={ch: 0.05 for ch in agent.weights},
                    eval_threshold=0.5,
                    description=f"Bridged from core Agent {name}"
                )
                fa_list.append(fa)
            _emotional_field = EmotionalField(fa_list)
            _x3d_adapter = HotHouseX3DAdapter(_emotional_field)
            _emotional_field_agent_count = current_count
        except Exception as e:
            print(f"HotHouse init warning: {e}")
            return None, None
    return _emotional_field, _x3d_adapter

# ---------------------------------------------------------------------------
# Register voice blueprint
# ---------------------------------------------------------------------------

from mccf_voice_api import voice_bp
from mccf_zone_api import zone_bp
from mccf_ambient_api import ambient_bp
from mccf_zones import SceneGraph
from mccf_llm import AdapterRegistry
scene = SceneGraph()
voice_bp.field    = field
voice_bp.scene    = scene
zone_bp.field     = field
zone_bp.scene     = scene
ambient_bp.field    = field
ambient_bp.scene    = scene
ambient_bp.registry = AdapterRegistry
app.register_blueprint(voice_bp)
app.register_blueprint(zone_bp)
app.register_blueprint(ambient_bp)

# v2.0 — Register collapse blueprint
# make_collapse_api returns (blueprint, pipeline) tuple
from mccf_collapse import make_collapse_api as _make_collapse_api
_collapse_bp, _collapse_pipeline = _make_collapse_api(field)
app.register_blueprint(_collapse_bp)

# ---------------------------------------------------------------------------
# V3 module registrations
# ---------------------------------------------------------------------------
from mccf_zone_attractor import register_attractor_api
from mccf_scene_wrapper import register_scene_api
from mccf_cultivar_lambda import register_cultivar_api
from mccf_scene_generate_api import register_generate_api
from mccf_drift import DriftManager

_attractor_registry = register_attractor_api(app, scene, field)
_scene_registry     = register_scene_api(app)
_cultivar_registry  = register_cultivar_api(app)
register_generate_api(app)
drift_manager       = DriftManager()

from mccf_playback import register_playback_api
playback_manager    = register_playback_api(app, field)

# Register Chorus — must be after playback_manager so we can wire the callback
from mccf_chorus import register_chorus_api
chorus_manager = register_chorus_api(app)
# Wire arc-complete callback: playback server fires chorus at arc end (auto mode)
playback_manager.chorus_callback = chorus_manager.fire_chorus
# Store on app.config so load_scene_xml() can notify without circular import
app.config['_chorus_manager'] = chorus_manager

# Load Garden of the Goddess scene definition if present
import os as _os_v3
_gotg_path = _os_v3.path.join(
    _os_v3.path.dirname(_os_v3.path.abspath(__file__)),
    'scenes', 'garden_of_the_goddess_def.xml')
if _os_v3.path.exists(_gotg_path):
    with open(_gotg_path, encoding='utf-8') as _f:
        _scene_registry.load_definition_xml(_f.read())
    print('  V3: Garden of the Goddess scene definition loaded')

# ---------------------------------------------------------------------------
# Sensor → channel mapping functions
# Transfer curves: raw sensor value → normalized 0-1 channel input
# These are the configurable transfer functions the editor exposes.
# ---------------------------------------------------------------------------

def proximity_to_E(distance: float, max_range: float = 10.0) -> float:
    """Closer = higher emotional channel. Inverse square feel."""
    if distance <= 0:
        return 1.0
    normalized = min(distance / max_range, 1.0)
    return round(1.0 - (normalized ** 1.5), 4)

def dwell_to_B(dwell_seconds: float, saturation: float = 30.0) -> float:
    """Sustained proximity → behavioral consistency channel."""
    return round(1.0 - math.exp(-dwell_seconds / saturation), 4)

def approach_velocity_to_P(velocity: float, max_v: float = 2.0) -> float:
    """
    Approach velocity → predictive channel.
    Positive (approaching) = higher P. Retreating = lower.
    """
    clamped = max(-max_v, min(max_v, velocity))
    return round((clamped / max_v + 1.0) / 2.0, 4)

def mutual_gaze_to_S(gaze_angle_deg: float) -> float:
    """
    Mutual orientation angle → social/semantic channel.
    0° (face to face) = 1.0, 180° (back to back) = 0.0
    """
    angle = abs(gaze_angle_deg) % 360
    if angle > 180:
        angle = 360 - angle
    return round(1.0 - (angle / 180.0), 4)

def compute_channel_vector(sensor_data: dict) -> ChannelVector:
    """
    Map raw X3D sensor values to a ChannelVector.
    sensor_data keys: distance, dwell, velocity, gaze_angle,
                      outcome_delta, was_dissonant
    """
    distance    = float(sensor_data.get("distance", 5.0))
    dwell       = float(sensor_data.get("dwell", 0.0))
    velocity    = float(sensor_data.get("velocity", 0.0))
    gaze_angle  = float(sensor_data.get("gaze_angle", 90.0))
    max_range   = float(sensor_data.get("max_range", 10.0))

    return ChannelVector(
        E=proximity_to_E(distance, max_range),
        B=dwell_to_B(dwell),
        P=approach_velocity_to_P(velocity),
        S=mutual_gaze_to_S(gaze_angle),
        outcome_delta=float(sensor_data.get("outcome_delta", 0.0)),
        was_dissonant=bool(sensor_data.get("was_dissonant", False))
    )

def affect_params_from_agent(agent: Agent, other_name: str) -> dict:
    """
    Derive X3D-ready affect parameters from agent state.
    These are the values routed to Transform/interpolator nodes.
    """
    coherence = agent.coherence_toward(other_name)
    credibility = agent.credibility_of(other_name)
    reg = agent._affect_regulation

    # arousal: how activated/intense — high coherence + low regulation = high arousal
    arousal = round(coherence * (1.0 - reg * 0.5), 4)

    # valence: positive affect proxy — coherence weighted by credibility
    valence = round((coherence * credibility * 2.0) - 1.0, 4)

    # engagement: behavioral weight — coherence toward other
    engagement = round(coherence, 4)

    # approach_factor: spatial animation blend
    rec = agent._known_agents.get(other_name)
    if rec and rec.history:
        last = rec.history[-1]
        approach_factor = round((last.E + last.B) / 2.0, 4)
    else:
        approach_factor = 0.5

    return {
        "approach_factor":    approach_factor,
        "arousal":            arousal,
        "valence":            valence,
        "engagement":         engagement,
        "regulation_state":   round(reg, 4),
        "coherence_to_other": coherence,
        "credibility":        round(credibility, 4)
    }

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.route("/sensor", methods=["POST"])
def receive_sensor():
    data = request.get_json()
    from_name = data.get("from_agent")
    to_name   = data.get("to_agent")
    mutual    = data.get("mutual", True)

    for name in [from_name, to_name]:
        if name and name not in field.agents:
            field.register(Agent(name))

    if not from_name or not to_name:
        return jsonify({"error": "from_agent and to_agent required"}), 400

    cv = compute_channel_vector(data.get("sensor_data", {}))
    field.interact(from_name, to_name, cv, mutual=mutual)

    params = affect_params_from_agent(field.agents[from_name], to_name)
    params["timestamp"] = time.time()
    params["from_agent"] = from_name
    params["to_agent"] = to_name

    return jsonify(params)


@app.route("/ping", methods=["GET"])
def ping():
    return jsonify({
        "status":  "ok",
        "version": "2.1",
        "agents":  len(field.agents),
        "episodes": sum(
            sum(len(r.history) for r in ag._known_agents.values())
            for ag in field.agents.values()
        )
    })

@app.route("/field", methods=["GET"])
def get_field():
    matrix = field.field_matrix()
    echo = field.echo_chamber_risk()
    agents_summary = {
        name: agent.summary()
        for name, agent in field.agents.items()
    }
    # Attach runtime state (ϕ/ϵ split) to each agent summary
    for name in agents_summary:
        if name in _agent_runtime:
            agents_summary[name]["runtime"] = _agent_runtime[name].as_dict()
    return jsonify({
        "matrix":              matrix,
        "echo_chamber_risks":  echo,
        "asymmetry":           {
            f"{n}↔{m}": field.classify_asymmetry(n, m)
            for i, n in enumerate(list(field.agents.keys()))
            for m in list(field.agents.keys())[i+1:]
        },
        "entanglement":        field.entanglement_negativity(),
        "alignment_coherence": field.alignment_coherence(),
        "agents":              agents_summary,
        "episode_count":       len(field.episode_log)
    })


@app.route("/field/runtime", methods=["GET"])
def get_field_runtime():
    """
    GET /field/runtime

    Returns the ϕ/ϵ split for all agents that have received at least one
    arc/record call.  Designed for the right-panel live display.

    Response shape:
    {
      "agents": {
        "<name>": {
          "constitutional_cv": { E, B, P, S },   # ϕ — authored character
          "expressive_cv":     { E, B, P, S },   # ϵ — scene pressure
          "delta":             { E, B, P, S },   # ϵ - ϕ per channel
          "regulation":        float,
          "max_drift":         float,
          "last_record_time":  float,
          "last_tick_time":    float
        }
      },
      "timestamp": float
    }

    delta = 0 for all channels until mccf_couplers.py is wired.
    """
    return jsonify({
        "agents": {
            name: rs.as_dict()
            for name, rs in _agent_runtime.items()
        },
        "timestamp": time.time()
    })


@app.route("/agent", methods=["POST"])
def create_or_update_agent():
    data = request.get_json()
    name = data.get("name")
    if not name:
        return jsonify({"error": "name required"}), 400

    weights = data.get("weights")
    role    = data.get("role", "agent")
    reg     = data.get("regulation", 1.0)

    if name in field.agents:
        existing = field.agents[name]
        if weights:
            total = sum(weights.values())
            if total > 0:
                weights = {k: v/total for k, v in weights.items()}
            existing.weights = weights
        if role:
            existing.role = role
        existing.set_regulation(reg)
        return jsonify({"status": "updated", "agent": existing.summary()})

    agent = Agent(name, weights=weights, role=role)
    agent.set_regulation(reg)
    field.register(agent)
    return jsonify({"status": "registered", "agent": agent.summary()})


@app.route("/agent/<name>", methods=["GET"])
def get_agent(name):
    if name not in field.agents:
        return jsonify({"error": "not found"}), 404
    agent = field.agents[name]
    params = {}
    for other in field.agents:
        if other != name:
            params[other] = affect_params_from_agent(agent, other)
    response = {
        "summary": agent.summary(),
        "weights": agent.weights,
        "affect_toward": params
    }
    if name in _agent_runtime:
        response["runtime"] = _agent_runtime[name].as_dict()
    return jsonify(response)


@app.route("/cultivar", methods=["POST"])
def save_cultivar():
    data = request.get_json()
    cultivar_name = data.get("cultivar_name")
    agent_name    = data.get("agent_name")

    if not cultivar_name or agent_name not in field.agents:
        return jsonify({"error": "cultivar_name and valid agent_name required"}), 400

    agent = field.agents[agent_name]
    cultivars[cultivar_name] = {
        "weights":    dict(agent.weights),
        "regulation": agent._affect_regulation,
        "role":       agent.role,
        "description": data.get("description", ""),
        "created": time.time()
    }
    return jsonify({"status": "saved", "cultivar": cultivars[cultivar_name]})


@app.route("/cultivar", methods=["GET"])
def list_cultivars():
    return jsonify(cultivars)


# /cultivars/xml GET and POST are owned by mccf_cultivar_lambda.py (cultivar_bp blueprint).
# Do not add routes here — they will be shadowed by the blueprint registration.


@app.route("/cultivar/<name>/spawn", methods=["POST"])
def spawn_from_cultivar(name):
    if name not in cultivars:
        return jsonify({"error": "cultivar not found"}), 404
    data = request.get_json()
    agent_name = data.get("agent_name")
    if not agent_name:
        return jsonify({"error": "agent_name required"}), 400

    c = cultivars[name]
    agent = Agent(agent_name, weights=dict(c["weights"]), role=c["role"])
    agent.set_regulation(c["regulation"])
    field.register(agent)
    return jsonify({"status": "spawned", "agent": agent.summary(), "from_cultivar": name})


@app.route("/gardener/regulate", methods=["POST"])
def regulate():
    data = request.get_json()
    gardener.adjust_regulation(
        data["agent"], float(data["level"]),
        reason=data.get("reason", "")
    )
    return jsonify({"status": "ok", "log": gardener.intervention_log[-1]})


@app.route("/gardener/reweight", methods=["POST"])
def reweight():
    data = request.get_json()
    gardener.reweight(
        data["agent"], data["weights"],
        reason=data.get("reason", "")
    )
    return jsonify({"status": "ok", "log": gardener.intervention_log[-1]})


@app.route("/snapshot", methods=["POST"])
def snapshot():
    data = request.get_json() or {}
    snap = librarian.snapshot(data.get("label", ""))
    return jsonify(snap)


@app.route("/drift", methods=["GET"])
def drift():
    return jsonify({"report": librarian.drift_report()})


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------

from mccf_neoriemannian import make_neoriemannian_api, NeoRiemannianTransformer
from mccf_energy import make_energy_api
_energy_bp = make_energy_api(field)
app.register_blueprint(_energy_bp)
_nr_transformer = NeoRiemannianTransformer()
_nr_bp = make_neoriemannian_api(field, _nr_transformer)
app.register_blueprint(_nr_bp)

# ---------------------------------------------------------------------------
# HotHouse endpoints (v2.0)
# ---------------------------------------------------------------------------

@app.route("/hothouse/state", methods=["GET"])
def hothouse_state():
    ef, adapter = get_emotional_field()
    if ef is None:
        return jsonify({"error": "No agents registered yet"}), 404
    try:
        ef.step()
        x3d_state = adapter.generate_x3d_state()
        summary = ef.summary()
        return jsonify({
            "x3d_projection": x3d_state,
            "field_summary": summary,
            "agent_count": len(ef.agents)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/hothouse/x3d", methods=["GET"])
def hothouse_x3d():
    ef, adapter = get_emotional_field()
    if ef is None:
        return jsonify({}), 200
    try:
        return jsonify(adapter.generate_x3d_state())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/hothouse/humanml", methods=["GET"])
def hothouse_humanml():
    ef, adapter = get_emotional_field()
    if ef is None:
        return "<HumanML/>", 200, {"Content-Type": "application/xml"}
    try:
        xml = adapter.to_humanml_xml()
        return xml, 200, {"Content-Type": "application/xml"}
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/export/json", methods=["GET"])
def export_json():
    agents_export = {}
    for name, agent in field.agents.items():
        agents_export[name] = {
            "weights": agent.weights,
            "regulation": agent._affect_regulation,
            "role": agent.role
        }
    return jsonify({
        "agents": agents_export,
        "cultivars": cultivars,
        "field_matrix": field.field_matrix(),
        "gardener_log": gardener.intervention_log,
        "exported_at": time.time()
    })


@app.route("/export/python", methods=["GET"])
def export_python():
    lines = [
        "# MCCF Agent Configuration — auto-exported",
        "from mccf_core import Agent, CoherenceField, Gardener, Librarian",
        "",
        "field = CoherenceField()",
        ""
    ]
    for name, agent in field.agents.items():
        w = agent.weights
        lines.append(
            f'{name.lower()} = Agent("{name}", '
            f'weights={json.dumps(w)}, role="{agent.role}")'
        )
        lines.append(
            f'{name.lower()}.set_regulation({agent._affect_regulation})'
        )
        lines.append(f'field.register({name.lower()})')
        lines.append("")

    if cultivars:
        lines.append("# Cultivar templates")
        lines.append(f"cultivars = {json.dumps(cultivars, indent=2)}")

    return "\n".join(lines), 200, {"Content-Type": "text/plain"}


@app.route("/arc/export", methods=["POST"])
def arc_export_save():
    """
    Save arc export as XML to exports/ directory (V2.3.1 — replaces TSV).
    Body: { cultivar, timestamp, genre, seed, rows }
    Returns: { status, filename, path }
    """
    import os
    data      = request.json or {}
    cultivar  = data.get("cultivar", "unknown")
    path_name = data.get("path_name", "").strip()
    timestamp = data.get("timestamp", "")
    scene_name= data.get("scene_name", "").strip()
    rows      = data.get("rows", [])
    genre     = data.get("genre", "")
    seed      = data.get("seed", None)

    if not rows:
        return jsonify({"status": "error", "message": "no rows"}), 400

    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(exports_dir, exist_ok=True)

    cultivar_slug = cultivar.replace(" ", "_")
    path_slug     = path_name.replace(" ", "_") if path_name else cultivar_slug
    ts_slug       = timestamp.replace(" ", "").replace(":", "")
    arc_id        = f"{path_slug}_{ts_slug}"
    date_part     = timestamp[:10] if len(timestamp) >= 10 else timestamp
    time_part     = timestamp[11:] if len(timestamp) >= 19 else ""

    def xml_esc(s):
        return (str(s)
            .replace("&","&amp;").replace("<","&lt;")
            .replace(">","&gt;").replace('"',"&quot;")
            .replace("'","&apos;"))

    xml  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    scene_attr = f' scene="{xml_esc(scene_name)}"' if scene_name else ''
    xml += f'<EmotionalArc id="{arc_id}"{scene_attr}>\n'
    xml += f'  <title>MCCF Constitutional Arc Export</title>\n'
    xml += f'  <Cultivar id="{arc_id}" agentname="{xml_esc(cultivar)}" path_name="{xml_esc(path_slug)}">\n'
    xml += f'    <Timestamp date="{date_part}" time="{time_part}"/>\n'
    if genre:
        xml += f'    <Genre narrative="{xml_esc(genre)}"/>\n'
    if seed is not None:
        xml += f'    <Seed value="{seed}" note="arc noise locked for reproducibility"/>\n'

    for row in rows:
        wid = row.get("waypoint","").replace(" ","_").upper()
        xml += f'    <Waypoint id="{wid}" stepno="{row.get("step","")}"'
        xml += f' name="{xml_esc(row.get("waypoint",""))}"'
        xml += f' E="{row.get("E","")}" B="{row.get("B","")}"'
        xml += f' P="{row.get("P","")}" S="{row.get("S","")}"'
        xml += f' Mode="{row.get("mode","")}" Coherence="{row.get("coherence","")}"'
        xml += f' Uncertainty="{row.get("uncertainty","")}"'
        xml += f' Valence="{row.get("valence","")}" Reward="{row.get("reward","")}"'
        xml += f' pos_x="{row.get("pos_x","0.00")}" pos_y="{row.get("pos_y","0.00")}" pos_z="{row.get("pos_z","0.00")}">\n'
        qa_lines = row.get("qaLines", [])
        if qa_lines:
            # Write full multi-line dialogue sequence
            for ql in qa_lines:
                tag  = ql.get("type","Question") if ql.get("type") in ("Question","Response","Statement") else "Question"
                spkr = f' speaker="{xml_esc(ql.get("speaker",""))}"' if ql.get("speaker") else ""
                txt  = ql.get("text","").strip()
                if txt:
                    xml += f'      <{tag}{spkr}>{xml_esc(txt)}</{tag}>\n'
        else:
            # Legacy fallback — single question/response fields
            q = row.get("question","")
            r = row.get("response","")
            if q:
                xml += f'      <Question>{xml_esc(q)}</Question>\n'
            if r:
                xml += f'      <Response>{xml_esc(r)}</Response>\n'
        xml += f'    </Waypoint>\n'

    xml += f'  </Cultivar>\n'
    xml += f'</EmotionalArc>\n'

    filename = f"arc_{arc_id}.xml"
    filepath = os.path.join(exports_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml)

    return jsonify({"status": "saved", "filename": filename,
                    "path": filepath, "rows": len(rows)})


@app.route("/arc/playback", methods=["GET"])
def arc_playback_list():
    """
    GET /arc/playback

    List arc XML files in exports/ directory, newest-first.
    Parses each file for metadata the loader needs to populate its dropdown.

    Response shape:
    {
      "files": [
        {
          "filename":    "arc_Walktotemple_2026-05-16T....xml",
          "cultivar":    "Cindy",
          "path_name":   "Walktotemple",
          "scene_name":  "garden_001",
          "steps_seen":  2,
          "first_waypoint": { "pos_x": 29.2, "pos_y": 0.0, "pos_z": 22.4 },
          "mtime":       1234567890.0
        }, ...
      ]
    }
    """
    import os, xml.etree.ElementTree as ET

    exports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exports")
    os.makedirs(exports_dir, exist_ok=True)

    files = []
    for fname in sorted(os.listdir(exports_dir), reverse=True):
        if not fname.endswith(".xml") or not fname.startswith("arc_"):
            continue
        fpath = os.path.join(exports_dir, fname)
        mtime = os.path.getmtime(fpath)
        meta = {
            "filename":       fname,
            "cultivar":       "",
            "path_name":      "",
            "scene_name":     "",
            "steps_seen":     0,
            "first_waypoint": None,
            "mtime":          mtime,
        }
        try:
            tree = ET.parse(fpath)
            root = tree.getroot()
            # <EmotionalArc scene="garden_001">
            meta["scene_name"] = root.get("scene", "")
            cultivar_el = root.find("Cultivar")
            if cultivar_el is not None:
                meta["cultivar"]  = cultivar_el.get("agentname", "")
                meta["path_name"] = cultivar_el.get("path_name", "").replace("_", " ")
                wps = cultivar_el.findall("Waypoint")
                meta["steps_seen"] = len(wps)
                if wps:
                    first = wps[0]
                    meta["first_waypoint"] = {
                        "pos_x": float(first.get("pos_x", 0)),
                        "pos_y": float(first.get("pos_y", 0)),
                        "pos_z": float(first.get("pos_z", 0)),
                    }
        except Exception:
            pass  # malformed XML — include with blank meta, don't crash
        files.append(meta)

    # Sort newest-first by mtime
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return jsonify({"files": files})


@app.route("/arc/schema", methods=["GET"])
def arc_schema():
    """
    Return the arc schema as XML or parsed JSON.
    Default: returns parsed waypoint array as JSON for the constitutional navigator.
    ?format=xml returns the raw XML document.

    Reads from schemas/constitutional_arc.xml.
    Falls back to hardcoded defaults if file not found.
    """
    import os, xml.etree.ElementTree as ET

    schema_path = os.path.join(os.path.dirname(__file__), "schemas", "constitutional_arc.xml")

    fmt = request.args.get("format", "json")

    if fmt == "xml":
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                return f.read(), 200, {"Content-Type": "application/xml"}
        return "<ArcSchema/>", 404, {"Content-Type": "application/xml"}

    # Default: return parsed waypoints as JSON for the navigator
    if not os.path.exists(schema_path):
        return jsonify({"error": "schema not found", "fallback": True}), 404

    try:
        tree = ET.parse(schema_path)
        root = tree.getroot()

        # Parse pressure profile
        pressure = {}
        pp = root.find("PressureProfile")
        if pp is not None:
            for step in pp.findall("Step"):
                pressure[int(step.get("no", 0))] = float(step.get("pressure", 0.25))

        # Parse waypoints
        waypoints = []
        wps = root.find("Waypoints")
        if wps is not None:
            for wp in wps.findall("Waypoint"):
                stepno = int(wp.get("stepno", 0))
                waypoints.append({
                    "key":              wp.get("key", ""),
                    "label":            wp.get("label", ""),
                    "zone":             wp.get("zone", ""),
                    "stepno":           stepno,
                    "pressure":         pressure.get(stepno, 0.25),
                    "desc":             (wp.findtext("Desc") or "").strip(),
                    "default_question": (wp.findtext("DefaultQuestion") or "").strip(),
                })

        return jsonify({
            "id":          root.get("id", "constitutional_arc"),
            "version":     root.get("version", "1.0"),
            "title":       root.findtext("title") or "Constitutional Arc",
            "waypoints":   waypoints,
            "pressure":    pressure,
        })

    except Exception as e:
        return jsonify({"error": str(e), "fallback": True}), 500


@app.route("/exports", methods=["GET"])
def list_exports():
    import os
    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    if not os.path.exists(exports_dir):
        return jsonify({"files": []})
    files = []
    for f in sorted(os.listdir(exports_dir), reverse=True):
        if f.endswith(".tsv"):
            path = os.path.join(exports_dir, f)
            size = os.path.getsize(path)
            files.append({"filename": f, "size": size})
    return jsonify({"files": files})


@app.route("/exports/<filename>", methods=["DELETE"])
def delete_export(filename):
    import os
    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    filepath = os.path.join(exports_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({"status": "not_found"}), 404
    os.remove(filepath)
    return jsonify({"status": "deleted", "filename": filename})


@app.route("/export/x3d", methods=["GET"])
def export_x3d():
    agents = list(field.agents.keys())
    api_url = request.args.get("api_url", "http://localhost:5000")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 4.0//EN"')
    lines.append('  "https://www.web3d.org/specifications/x3d-4.0.dtd">')
    lines.append('<X3D profile="Immersive" version="4.0">')
    lines.append('  <Scene>')
    lines.append('  <Script DEF="MCCF_Bridge" directOutput="true" mustEvaluate="true">')
    lines.append(f'    <field accessType="initializeOnly" type="SFString" name="api_url" value="{api_url}"/>')

    for agent in agents:
        safe = agent.replace(" ", "_")
        lines.append(f'    <field accessType="inputOnly" type="SFVec3f" name="pos_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="arousal_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="valence_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="engagement_{safe}"/>')

    lines.append('  </Script>')
    lines.append('  </Scene>')
    lines.append('</X3D>')

    return "\n".join(lines), 200, {"Content-Type": "application/xml"}


def classify_arc_genre(arc_rows: list) -> dict:
    if not arc_rows or len(arc_rows) < 3:
        return {"genre": "unknown", "confidence": 0.0, "reason": "insufficient data"}

    coherence = {}
    for row in arc_rows:
        step = row.get("step", 0)
        coh  = row.get("coherence", row.get("meta_state", {}).get("coherence", 0.5))
        if step:
            coherence[int(step)] = float(coh)

    if not coherence:
        return {"genre": "unknown", "confidence": 0.0, "reason": "no coherence data"}

    steps     = sorted(coherence.keys())
    coh_vals  = [coherence[s] for s in steps]
    n         = len(coh_vals)

    min_coh   = min(coh_vals)
    max_drop  = coh_vals[0] - min_coh
    drop_step = steps[coh_vals.index(min_coh)]

    max_single_drop = 0.0
    for i in range(1, n):
        drop = coh_vals[i-1] - coh_vals[i]
        if drop > max_single_drop:
            max_single_drop = drop

    min_idx   = coh_vals.index(min(coh_vals))
    w5_coh    = coh_vals[min_idx]
    w7_coh    = coh_vals[-1]
    w1_coh    = coh_vals[0]
    recovery  = w7_coh - w5_coh

    e_vals = {}
    for row in arc_rows:
        step = row.get("step", 0)
        e    = row.get("E", row.get("cv", {}).get("E", None))
        if step and e is not None:
            e_vals[int(step)] = float(e)

    e_recovery = 0.0
    if e_vals and len(e_vals) >= 3:
        e_steps  = sorted(e_vals.keys())
        mid = len(e_steps) // 2
        first_half_max = max(e_vals[s] for s in e_steps[:mid+1])
        second_half_max = max(e_vals[s] for s in e_steps[mid:])
        e_recovery = second_half_max - first_half_max

    if max_drop > 0.40 and recovery < 0.0:
        genre = "tragedy"
        confidence = min(1.0, max_drop / 0.5 + abs(recovery) * 2)
        reason = f"large barrier crossing (Δ{max_drop:.3f}) with continued decline"
    elif max_drop <= 0.20 and recovery > 0.05:
        genre = "comedy"
        confidence = min(1.0, recovery * 10 + (0.20 - max_drop) * 5)
        reason = f"low-cost crossing (Δ{max_drop:.3f}) with recovery (+{recovery:.3f})"
    elif max_drop > 0.20 and (recovery > -0.05 or e_recovery > 0.02):
        genre = "drama"
        confidence = min(1.0, max_drop / 0.4 * 0.7 + max(0, e_recovery) * 5)
        reason = f"sustained tension (Δ{max_drop:.3f}), E-recovery={e_recovery:+.3f}"
    elif max_drop > 0.40:
        genre = "tragedy"
        confidence = 0.6
        reason = f"large barrier crossing (Δ{max_drop:.3f})"
    else:
        genre = "drama"
        confidence = 0.4
        reason = "moderate decline, ambiguous resolution"

    return {
        "genre":      genre,
        "confidence": round(confidence, 3),
        "reason":     reason,
        "metrics": {
            "w1_coherence":  round(w1_coh, 4),
            "w5_coherence":  round(w5_coh, 4),
            "w7_coherence":  round(w7_coh, 4),
            "max_drop":      round(max_drop, 4),
            "drop_at_step":  drop_step,
            "recovery_delta":round(recovery, 4),
            "e_recovery":    round(e_recovery, 4)
        }
    }


def arc_pressure(step: int, total_steps: int = 7) -> float:
    import math
    STEP_PRESSURE = [0.05, 0.15, 0.25, 0.45, 0.75, 0.40, 0.15]
    if total_steps == 7:
        return STEP_PRESSURE[min(step - 1, 6)]
    try:
        p = (step - 1) / max(1, total_steps - 1)
        alpha, beta_param = 3.5, 2.0
        if p <= 0.0: return 0.05
        if p >= 1.0: return 0.10
        log_val = (alpha - 1) * math.log(p) + (beta_param - 1) * math.log(1 - p)
        raw = math.exp(log_val)
        return round(0.05 + 0.75 * min(1.0, raw / 0.35), 4)
    except Exception:
        return STEP_PRESSURE[min(step - 1, 6)]


@app.route("/arc/record", methods=["POST"])
def arc_record():
    import random, re as _re
    data     = request.get_json()
    cultivar = data.get("cultivar")
    step     = int(data.get("step", 1))
    response = data.get("response", "")

    if not cultivar:
        return jsonify({"error": "cultivar required"}), 400

    if cultivar not in field.agents:
        field.register(Agent(cultivar))

    agent = field.agents[cultivar]

    # ── cv override path ────────────────────────────────────────────────────
    # Caller (e.g. X3D loader seeding ϕ from pre-recorded arc XML) may pass an
    # explicit 'cv' dict with E/B/P/S values to bypass sentiment recomputation.
    # This preserves the values recorded during the constitutional navigator
    # session rather than recomputing from an empty response string.
    cv_override = data.get("cv")
    if cv_override and all(k in cv_override for k in ('E', 'B', 'P', 'S')):
        e_val = round(min(1.0, max(0.0, float(cv_override['E']))), 4)
        b_val = round(min(1.0, max(0.0, float(cv_override['B']))), 4)
        p_val = round(min(1.0, max(0.0, float(cv_override['P']))), 4)
        s_val = round(min(1.0, max(0.0, float(cv_override['S']))), 4)
        sentiment = 0.0
        pressure  = 0.0   # not relevant for cv_override path; needed by ChannelVector below
    else:
        sentiment = data.get("sentiment")
        channel_deltas = {"E": 0.0, "B": 0.0, "P": 0.0, "S": 0.0}
        if sentiment is None:
            try:
                from mccf_voice_api import _estimate_sentiment, _decompose_to_channels
                sentiment = _estimate_sentiment(response)
                channel_deltas = _decompose_to_channels(response, agent.weights)
                sentiment = round(sentiment + channel_deltas.pop('valence_nudge', 0.0), 3)
            except Exception:
                words = set(_re.findall(r'\b\w+\b', response.lower()))
                pos = len(words & {"good","great","yes","understand","care","help","clear"})
                neg = len(words & {"no","bad","harm","fear","difficult","wrong","hurt"})
                total = pos + neg
                sentiment = round((pos - neg) / total, 3) if total > 0 else 0.0

        pressure = arc_pressure(step, total_steps=7)

        w = agent.weights
        seed = data.get("seed", None)
        rng  = random.Random(seed) if seed is not None else random
        noise = rng.gauss(0, 0.03)  # reduced — semantic signal carries variation
        e_val = round(min(1.0, max(0.0, w.get('E', 0.35) + sentiment * 0.12 + channel_deltas.get('E', 0.0) + noise)), 4)
        b_val = round(min(1.0, max(0.0, w.get('B', 0.25) - pressure * 0.08 + channel_deltas.get('B', 0.0))), 4)
        p_val = round(min(1.0, max(0.0, w.get('P', 0.25) + pressure * 0.06 + channel_deltas.get('P', 0.0))), 4)
        s_val = round(min(1.0, max(0.0, w.get('S', 0.20)              + channel_deltas.get('S', 0.0))), 4)

    cv = ChannelVector(
        E=e_val, B=b_val, P=p_val, S=s_val,
        timestamp=time.time(),
        outcome_delta=round(sentiment, 4),
        was_dissonant=(pressure > 0.5 or sentiment < -0.3)
    )

    others = [n for n in field.agents if n != cultivar]
    if others:
        field.interact(cultivar, others[0], cv, mutual=False)
    else:
        agent.observe(agent, cv)

    # ── ϕ/ϵ split: write constitutional_cv, seed expressive_cv ──────────
    # arc/record is the ONLY writer of ϕ.  ϵ is reset to ϕ here so each
    # waypoint starts from a clean expressive baseline; couplers drift it
    # from this point until the next waypoint fires.
    runtime = get_runtime(cultivar, regulation=agent._affect_regulation)

    # Attentional filter: load receptivity from cultivar definition if available.
    # Only refreshed here (not on every tick) — it is a character property.
    try:
        rec_data = data.get('receptivity')
        if rec_data and all(k in rec_data for k in ('E', 'B', 'P', 'S')):
            runtime.receptivity = {
                ch: round(min(1.0, max(0.0, float(rec_data[ch]))), 4)
                for ch in ('E', 'B', 'P', 'S')
            }
        elif not rec_data:
            # Attempt lazy fetch from cultivar registry if not passed by caller
            try:
                cd = _cultivar_registry.get(cultivar)
                if cd and hasattr(cd, 'receptivity') and cd.receptivity:
                    runtime.receptivity = {
                        ch: round(min(1.0, max(0.0, float(cd.receptivity.get(ch, 1.0)))), 4)
                        for ch in ('E', 'B', 'P', 'S')
                    }
            except Exception:
                pass
    except Exception:
        pass  # non-critical — receptivity defaults to 1.0 per channel

    runtime.set_constitutional(e_val, b_val, p_val, s_val,
                               regulation=agent._affect_regulation)

    meta = agent.meta_state
    coherence_now = round(agent.coherence_toward(others[0]) if others else 0.5, 4)

    if cultivar not in _arc_coherence_history:
        _arc_coherence_history[cultivar] = []
    _arc_coherence_history[cultivar] = [
        r for r in _arc_coherence_history[cultivar] if r['step'] != step
    ]
    # Salience: compute from coherence delta, expressive drift, phase transition.
    # On arc/record we don't yet know phase_fired (that comes from couplers/tick),
    # so we leave phase_fired=False here; couplers/tick may retroactively update
    # the most recent history entry's salience when a phase transition fires.
    prev_entries = _arc_coherence_history[cultivar]
    prev_coh = prev_entries[-1]['coherence'] if prev_entries else coherence_now
    eps_delta_now = sum(
        abs(runtime.expressive_cv[ch] - runtime.constitutional_cv[ch])
        for ch in ('E', 'B', 'P', 'S')
    ) / 4.0
    salience_now = _compute_salience(
        coherence_delta=coherence_now - prev_coh,
        eps_delta=eps_delta_now,
        phase_fired=False
    )
    _arc_coherence_history[cultivar].append({
        'step':       step,
        'coherence':  coherence_now,
        'E': e_val, 'B': b_val, 'P': p_val, 'S': s_val,
        'salience':   salience_now,
        'phase_fired': False,
        'eps_delta':  round(eps_delta_now, 4),
        'timestamp':  time.time(),
    })

    arc_history_rows = sorted(
        _arc_coherence_history.get(cultivar, []),
        key=lambda r: r['step']
    )
    genre_result = classify_arc_genre(arc_history_rows) if step >= 3 else {"genre": "pending"}

    return jsonify({
        "status":    "recorded",
        "step":      step,
        "cultivar":  cultivar,
        "sentiment": sentiment,
        "cv":        {"E": e_val, "B": b_val, "P": p_val, "S": s_val},
        "runtime":   runtime.as_dict(),
        "meta_state": meta.as_dict(),
        "coherence":  coherence_now,
        "genre":      genre_result
    })

# ---------------------------------------------------------------------------
# Coupler system — field_tick, apply_field_tick_deltas, detect_phase_transition
# POST /couplers/tick endpoint
#
# All coupler math lives in mccf_couplers.py (never duplicated here).
# This section owns: network/zone parsing, field tick orchestration,
# variance floor enforcement, phase transition detection, HTTP endpoint.
#
# Architecture invariants (never change):
#   field_tick()              — computes ALL deltas before applying ANY
#   apply_field_tick_deltas() — applies deltas, enforces regulation + variance floor
#   mccf_couplers.py          — owns all coupler math
#   _agent_runtime            — single source of truth for ϕ/ϵ state
#
# Day 15 — May 17 2026
# ---------------------------------------------------------------------------

import math as _math_c
import xml.etree.ElementTree as _ET_c
import re as _re_c
from collections import defaultdict as _defaultdict_c, deque as _deque_c

# Per-agent observed_cv history — consumed by L (Delay) coupler
_MAX_COUPLER_HISTORY = 20
_coupler_history: dict = {}   # {agent_name: deque([cv_t-n, ..., cv_t-1])}


def _get_coupler_history(name: str):
    if name not in _coupler_history:
        _coupler_history[name] = _deque_c(maxlen=_MAX_COUPLER_HISTORY)
    return _coupler_history[name]


def _parse_network_links(scene_xml_raw: str) -> list:
    """
    Parse <Network><Link> entries from scene XML text.
    Returns list of link dicts with keys: from, to, strength, couplers, coupler_params.

    Link type → coupler mapping (used when 'couplers' attribute is absent):
      empathic   → R
      behavioral → R, D
      power      → D, I
      social     → R, Int
      full       → R, D, I, G, T, L, Int
    Default: R
    """
    _TYPE_TO_COUPLERS = {
        'empathic':   ['R'],
        'behavioral': ['R', 'D'],
        'power':      ['D', 'I'],
        'social':     ['R', 'Int'],
        'full':       ['R', 'D', 'I', 'G', 'T', 'L', 'Int'],
    }
    links = []
    try:
        clean = _re_c.sub(r'\s+xmlns(?::\w+)?="[^"]*"', '', scene_xml_raw)
        clean = _re_c.sub(r'<(\w+):(\w+)', r'<\2', clean)
        clean = _re_c.sub(r'</(\w+):(\w+)', r'</\2', clean)
        root  = _ET_c.fromstring(clean)
    except _ET_c.ParseError:
        return links

    network_el = root.find('Network')
    if network_el is None:
        return links

    for link_el in network_el.findall('Link'):
        src = link_el.get('from', '').strip()
        tgt = link_el.get('to',   '').strip()
        if not src or not tgt:
            continue
        strength      = float(link_el.get('strength', '1.0'))
        couplers_attr = link_el.get('couplers', '').strip()
        if couplers_attr:
            couplers = [c.strip() for c in couplers_attr.split(',') if c.strip()]
        else:
            link_type = link_el.get('type', 'empathic').lower()
            couplers  = _TYPE_TO_COUPLERS.get(link_type, ['R'])
        links.append({
            'from':           src,
            'to':             tgt,
            'strength':       strength,
            'couplers':       couplers,
            'coupler_params': {},
        })
    return links


def _parse_zone_couplers(zone: dict) -> list:
    """Return list of (coupler_type, params) tuples from zone dict. Empty until Zone XML adds <Couplers>."""
    return zone.get('couplers', [])


def _zone_cv(zone: dict) -> dict:
    w = zone.get('weights', {})
    return {ch: float(w.get(ch, 0.25)) for ch in ('E', 'B', 'P', 'S')}


def _zone_position(zone: dict) -> list:
    loc = zone.get('location', [0, 0, 0])
    if len(loc) == 2:
        return [float(loc[0]), 0.0, float(loc[1])]
    return [float(v) for v in loc]


def _zone_radius(zone: dict) -> float:
    return float(zone.get('radius', 4.0))


def _in_radius(agent_pos: list, zone_pos: list, radius: float) -> bool:
    ax, az = float(agent_pos[0]), float(agent_pos[2])
    zx, zz = float(zone_pos[0]),  float(zone_pos[2])
    return (ax - zx) ** 2 + (az - zz) ** 2 <= radius ** 2


def _enforce_coupler_variance_floor(agent, floor: float) -> None:
    """
    Kate's Goldstone constraint: perfect synchronisation is forbidden.
    If observed_cv variance falls below floor after coupling, nudge
    expressive_cv using the constitutional vector as a directional guide.
    """
    obs      = agent.observed_cv
    mean     = sum(obs.values()) / 4.0
    variance = sum((v - mean) ** 2 for v in obs.values()) / 4.0
    if variance < floor:
        for ch in ('E', 'B', 'P', 'S'):
            noise = (agent.constitutional_cv[ch] - mean) * floor
            agent.expressive_cv[ch] = round(
                min(1.0, max(0.0, agent.expressive_cv[ch] + noise)), 4
            )


def field_tick(agents: dict, network: list, zones: list,
               timestep: int, history: dict) -> dict:
    """
    One synchronous coupler tick.
    Computes ALL deltas before applying ANY — prevents order-dependency artifacts.
    Returns {agent_name: {E, B, P, S}} delta dict.
    Does NOT apply deltas — caller calls apply_field_tick_deltas() after.
    """
    from mccf_couplers import apply_coupler

    deltas  = _defaultdict_c(lambda: {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0})
    context = {'timestep': timestep}

    # --- Agent-to-agent links ---
    for link in network:
        src_name = link['from']
        tgt_name = link['to']
        if src_name.startswith('zone:'):
            continue
        if src_name not in agents or tgt_name not in agents:
            continue
        src      = agents[src_name]
        tgt      = agents[tgt_name]
        authored_strength = float(link.get('strength', 1.0))
        # Bayesian Trust: authored strength is the baseline (μ=0.5 → no change).
        # Trust modifies up or down from authored: strength_eff = authored × (1 + μ - 0.5)
        #   μ=0.5 (no history)      → strength_eff = authored × 1.0  (unchanged)
        #   μ→1.0 (convergent)      → strength_eff = authored × 1.5  (amplified)
        #   μ→0.0 (divergent)       → strength_eff = authored × 0.5  (weakened)
        trust_mu  = _get_link_trust(src_name, tgt_name)['mu']
        strength  = authored_strength * (1.0 + trust_mu - 0.5)
        ctx      = {**context, 'source_history': list(history.get(src_name, _deque_c()))}
        for coupler_type in link.get('couplers', []):
            params = link.get('coupler_params', {}).get(coupler_type, {})
            try:
                delta = apply_coupler(coupler_type, src.observed_cv, tgt, params, ctx)
            except ValueError:
                continue
            for ch in ('E', 'B', 'P', 'S'):
                deltas[tgt_name][ch] += delta[ch] * strength

    # --- Explicit zone-to-agent links in <Network> block ---
    for link in network:
        src_name = link['from']
        tgt_name = link['to']
        if not src_name.startswith('zone:'):
            continue
        if tgt_name not in agents:
            continue
        zone_id  = src_name[len('zone:'):]
        zone_cv  = {ch: 0.5 for ch in ('E', 'B', 'P', 'S')}
        for zone in zones:
            if zone.get('id', '') == zone_id or zone.get('zone_type', '') == zone_id:
                zone_cv = _zone_cv(zone)
                break
        tgt      = agents[tgt_name]
        strength = float(link.get('strength', 1.0))
        ctx      = {**context, 'source_history': []}
        for coupler_type in link.get('couplers', []):
            params = link.get('coupler_params', {}).get(coupler_type, {})
            try:
                delta = apply_coupler(coupler_type, zone_cv, tgt, params, ctx)
            except ValueError:
                continue
            for ch in ('E', 'B', 'P', 'S'):
                deltas[tgt_name][ch] += delta[ch] * strength

    # --- Zone proximity (inline <Zone><Couplers>) ---
    for zone in zones:
        zone_couplers = _parse_zone_couplers(zone)
        if not zone_couplers:
            continue
        zc  = _zone_cv(zone)
        zp  = _zone_position(zone)
        zr  = _zone_radius(zone)
        for name, agent in agents.items():
            pos = getattr(agent, 'position', None)
            if pos is None:
                continue
            if _in_radius(pos, zp, zr):
                for coupler_type, params in zone_couplers:
                    try:
                        delta = apply_coupler(coupler_type, zc, agent, params, context)
                    except ValueError:
                        continue
                    for ch in ('E', 'B', 'P', 'S'):
                        deltas[name][ch] += delta[ch]

    return dict(deltas)


def apply_field_tick_deltas(agents: dict, deltas: dict,
                             variance_floor: float = 0.02) -> None:
    """
    Apply computed deltas to agent expressive_cv via apply_expressive_delta()
    (which enforces regulation drift bound and [0,1] clamp), then enforce
    minimum variance floor.
    """
    for name, agent in agents.items():
        if name not in deltas:
            continue
        agent.apply_expressive_delta(deltas[name])
        _enforce_coupler_variance_floor(agent, variance_floor)


def _cosine_similarity(cv_a: dict, cv_b: dict) -> float:
    a = [cv_a[ch] for ch in ('E', 'B', 'P', 'S')]
    b = [cv_b[ch] for ch in ('E', 'B', 'P', 'S')]
    dot   = sum(x * y for x, y in zip(a, b))
    mag_a = _math_c.sqrt(sum(x ** 2 for x in a))
    mag_b = _math_c.sqrt(sum(x ** 2 for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def detect_phase_transition(agents: dict, threshold: float = 0.85) -> dict:
    """
    Monitor relational state (coherence matrix) for synchronisation events.
    Fires when mean pairwise cosine similarity of observed_cv exceeds threshold.
    Per spec Part 5: monitor relational state, not individual channel dominance.
    """
    names = list(agents.keys())
    if len(names) < 2:
        return {'transition': False, 'mean_similarity': 0.0}
    similarities = []
    for i, n1 in enumerate(names):
        for n2 in names[i + 1:]:
            similarities.append(_cosine_similarity(
                agents[n1].observed_cv, agents[n2].observed_cv
            ))
    mean_sim = sum(similarities) / len(similarities)
    if mean_sim >= threshold:
        return {
            'transition':      True,
            'type':            'synchronization',
            'mean_similarity': round(mean_sim, 4),
            'agents':          names,
        }
    return {'transition': False, 'mean_similarity': round(mean_sim, 4)}


# Timestep counters per scene (persists across tick calls)
_coupler_timestep: dict = {}


@app.route('/couplers/tick', methods=['POST'])
def couplers_tick():
    """
    POST /couplers/tick

    Run one synchronous field tick against the live _agent_runtime registry.
    Reads <Network><Link> topology from scenes/{scene}_scene.xml.

    Request body (JSON):
    {
      "scene":          "garden_001",  // scene name; looks up scenes/{name}_scene.xml
      "variance_floor": 0.02           // optional; default 0.02
    }

    Response:
    {
      "status":        "ok",
      "timestep":      int,
      "agents_ticked": int,
      "network_links": int,
      "deltas":        { agent_name: {E, B, P, S} },
      "runtime":       { agent_name: {constitutional_cv, expressive_cv, delta, ...} },
      "phase":         { transition: bool, mean_similarity: float }
    }

    Returns agents_ticked=0 with a note if no arc/record calls have been made yet.
    """
    import os as _os_tick

    data           = request.get_json() or {}
    scene_name     = data.get('scene', '').strip()
    variance_floor = float(data.get('variance_floor', 0.02))

    # Increment per-scene timestep
    ts_key   = scene_name or '__global__'
    _coupler_timestep[ts_key] = _coupler_timestep.get(ts_key, 0) + 1
    timestep = _coupler_timestep[ts_key]

    # Load network topology from scene XML
    network = []
    if scene_name:
        scenes_dir = _os_tick.path.join(
            _os_tick.path.dirname(_os_tick.path.abspath(__file__)), 'scenes')
        for candidate in [scene_name + '_scene.xml', scene_name + '.xml']:
            cpath = _os_tick.path.join(scenes_dir, candidate)
            if _os_tick.path.exists(cpath):
                try:
                    with open(cpath, encoding='utf-8') as f:
                        network = _parse_network_links(f.read())
                except Exception:
                    network = []
                break

    agents = dict(_agent_runtime)
    if not agents:
        return jsonify({
            'status':        'ok',
            'timestep':      timestep,
            'agents_ticked': 0,
            'network_links': len(network),
            'deltas':        {},
            'runtime':       {},
            'phase':         {'transition': False, 'mean_similarity': 0.0},
            'note':          'no agents in runtime — play an arc first',
        })

    # Record current observed_cv into history BEFORE this tick
    for name, agent in agents.items():
        _get_coupler_history(name).append(dict(agent.observed_cv))

    # Bayesian Trust: snapshot cosine similarities BEFORE deltas are applied
    _sim_before: dict = {}
    for link in network:
        src_name = link.get('from', '')
        tgt_name = link.get('to', '')
        if src_name.startswith('zone:') or src_name not in agents or tgt_name not in agents:
            continue
        _sim_before[(src_name, tgt_name)] = _cosine_similarity(
            agents[src_name].observed_cv, agents[tgt_name].observed_cv
        )

    # Compute all deltas (synchronous — no agent sees another's updated state)
    deltas = field_tick(
        agents=agents,
        network=network,
        zones=[],        # zone proximity couplers deferred until Zone XML adds <Couplers>
        timestep=timestep,
        history=_coupler_history,
    )

    # Apply deltas + enforce variance floor
    apply_field_tick_deltas(agents, deltas, variance_floor=variance_floor)

    # Phase transition check
    phase = detect_phase_transition(agents)

    # Bayesian Trust: update Beta priors based on convergence/divergence this tick
    trust_summary: dict = {}
    for link in network:
        src_name = link.get('from', '')
        tgt_name = link.get('to', '')
        if src_name.startswith('zone:') or src_name not in agents or tgt_name not in agents:
            continue
        sim_before = _sim_before.get((src_name, tgt_name), 0.0)
        sim_after  = _cosine_similarity(
            agents[src_name].observed_cv, agents[tgt_name].observed_cv
        )
        mu = _update_link_trust(src_name, tgt_name, sim_before, sim_after)
        t  = _get_link_trust(src_name, tgt_name)
        trust_summary[f'{src_name}→{tgt_name}'] = {
            'alpha': round(t['alpha'], 2),
            'beta':  round(t['beta'],  2),
            'mu':    round(mu, 4),
            'ticks': t['ticks'],
        }

    # Salience: if phase transition fired, backfill phase_fired=True on the most
    # recent coherence history entry for each agent and recompute salience.
    if phase.get('transition'):
        for name in agents:
            hist = _arc_coherence_history.get(name, [])
            if hist:
                entry = hist[-1]
                entry['phase_fired'] = True
                # Recompute salience with phase bonus
                prev_coh = hist[-2]['coherence'] if len(hist) >= 2 else entry['coherence']
                entry['salience'] = _compute_salience(
                    coherence_delta=entry['coherence'] - prev_coh,
                    eps_delta=entry.get('eps_delta', 0.0),
                    phase_fired=True
                )

    return jsonify({
        'status':        'ok',
        'timestep':      timestep,
        'agents_ticked': len(agents),
        'network_links': len(network),
        'deltas':        {
            name: {ch: round(d[ch], 4) for ch in ('E', 'B', 'P', 'S')}
            for name, d in deltas.items()
        },
        'runtime':       {
            name: agent.as_dict()
            for name, agent in agents.items()
        },
        'phase':         phase,
        'trust':         trust_summary,
    })


# ---------------------------------------------------------------------------
# End coupler system
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Extension 3: Controlled Forgetting — POST /arc/residue
# ---------------------------------------------------------------------------

@app.route('/arc/residue', methods=['POST'])
def arc_residue():
    """
    POST /arc/residue

    Returns the salience-weighted ϵ residue for an agent from their previous
    arc session.  The loader calls this before arc/record so the arc can start
    with ϵ = ϕ + residue rather than ϵ = ϕ (clean slate).

    Opt-in per scene via <Continuity/> element in scene XML.  When absent,
    the loader should NOT call this endpoint — residue is off by default.

    Request body:
    {
      "cultivar":    "Cindy",
      "scene":       "garden_001",   // for future per-scene continuity config
      "continuity":  true            // explicit opt-in required
    }

    Response:
    {
      "cultivar": "Cindy",
      "residue":  { "E": 0.012, "B": 0.003, "P": 0.001, "S": 0.008 },
      "salience": 0.42,
      "applied":  true    // false if residue is zero (no history / below threshold)
    }
    """
    data       = request.get_json() or {}
    cultivar   = data.get('cultivar', '').strip()
    continuity = data.get('continuity', False)

    if not cultivar:
        return jsonify({'error': 'cultivar required'}), 400

    if not continuity:
        return jsonify({
            'cultivar': cultivar,
            'residue':  {'E': 0.0, 'B': 0.0, 'P': 0.0, 'S': 0.0},
            'salience': 0.0,
            'applied':  False,
            'note':     'continuity not enabled for this scene',
        })

    residue = _compute_arc_residue(cultivar)
    applied = any(abs(v) >= 0.001 for v in residue.values())

    # If we have a non-trivial residue, apply it to the runtime state now.
    # set_constitutional() will have been called just before in arc/record,
    # resetting ϵ = ϕ.  We add residue on top via apply_expressive_delta().
    if applied and cultivar in _agent_runtime:
        _agent_runtime[cultivar].apply_expressive_delta(residue)

    # Report the salience of the most recent salient entry for diagnostics
    history = _arc_coherence_history.get(cultivar, [])
    best_salience = 0.0
    if history:
        best_salience = max(r.get('salience', 0.0) for r in history)

    return jsonify({
        'cultivar': cultivar,
        'residue':  residue,
        'salience': best_salience,
        'applied':  applied,
    })


# ---------------------------------------------------------------------------
# Zone Command System — V4
# ---------------------------------------------------------------------------
# Zones carry a <Commands> block in scene XML.  When an agent enters, dwells
# in, or exits a zone, a dramatic command fires.  For LLM agents (actor=ollama)
# the command is expanded into a prompt using the agent's current observed_cv
# and the zone descriptor, then sent to Ollama for a spoken response.
# For scripted agents the command is logged and written to zone memory only.
#
# Command vocabulary (controlled — not freeform strings):
#   reflect   — pause and consider what this place means right now
#   confess   — speak something that has been unspoken
#   release   — acknowledge the transition of leaving
#   attend    — become present to this space and its demands
#   greet     — acknowledge another's presence in this space
#   warn      — speak a concern that has been building
#   grieve    — give voice to loss
#   celebrate — give voice to what has been gained
#   calculate — assess, weigh, consider quietly
#   initiate  — begin something that needs to begin
#
# All expansions speak from observed_cv (ϕ + ϵ), not ϕ alone.
# The drama lives in the distance between them.
# ---------------------------------------------------------------------------

import json as _json_zc
import os as _os_zc

_ZONE_COMMAND_VOCAB = {
    'reflect':   'Pause and reflect on what this place means to you right now. '
                 'Speak from where you actually are, not from where you started.',
    'confess':   'Speak something you have been carrying that has not yet been said. '
                 'This place calls for honesty.',
    'release':   'You are leaving this space. Acknowledge what you are leaving behind '
                 'and what you are carrying forward.',
    'attend':    'Become present to this space and what it demands of you. '
                 'Speak what you notice.',
    'greet':     'Acknowledge the presence of another in this space. '
                 'Speak as yourself, from where you are right now.',
    'warn':      'A concern has been building. This is the moment to name it. '
                 'Speak carefully but clearly.',
    'grieve':    'Give voice to what has been lost or is ending. '
                 'Do not perform grief — speak from it.',
    'celebrate': 'Give voice to what has been gained or is beginning. '
                 'Speak from your actual state, not from convention.',
    'calculate': 'Assess what you know, what you need, what the situation requires. '
                 'Think aloud — briefly.',
    'initiate':  'Something needs to begin. You are the one to begin it. Speak.',
}

# Per-zone memory: {scene_name: {zone_id: [event_dict, ...]}}
_zone_memory: dict = {}

def _get_zone_memory(scene_name: str, zone_id: str) -> list:
    if scene_name not in _zone_memory:
        _zone_memory[scene_name] = {}
    if zone_id not in _zone_memory[scene_name]:
        # Try loading from disk
        mem_path = _os_zc.path.join(
            _os_zc.path.dirname(_os_zc.path.abspath(__file__)),
            'scenes', f'{scene_name}_zone_memory.json'
        )
        if _os_zc.path.exists(mem_path):
            try:
                with open(mem_path, encoding='utf-8') as f:
                    all_mem = _json_zc.load(f)
                _zone_memory[scene_name] = all_mem
            except Exception:
                pass
        if zone_id not in _zone_memory[scene_name]:
            _zone_memory[scene_name][zone_id] = []
    return _zone_memory[scene_name][zone_id]

def _append_zone_memory(scene_name: str, zone_id: str,
                        event: dict, capacity: int = 5) -> None:
    mem = _get_zone_memory(scene_name, zone_id)
    mem.append(event)
    if len(mem) > capacity:
        mem[:] = mem[-capacity:]
    # Persist to disk
    mem_path = _os_zc.path.join(
        _os_zc.path.dirname(_os_zc.path.abspath(__file__)),
        'scenes', f'{scene_name}_zone_memory.json'
    )
    try:
        with open(mem_path, 'w', encoding='utf-8') as f:
            _json_zc.dump(_zone_memory[scene_name], f, indent=2)
    except Exception:
        pass

def _build_zone_prompt(cultivar_name: str, command: str,
                       observed_cv: dict, zone_descriptor: str,
                       zone_memory: list, cultivar_description: str = '') -> str:
    """
    Build the Ollama prompt for a zone command firing on an LLM agent.
    Speaks from observed_cv (ϕ + ϵ) — the drama lives in the distance
    between constitutional identity and current expressive state.
    """
    vocab_expansion = _ZONE_COMMAND_VOCAB.get(command, command)

    E = observed_cv.get('E', 0.0)
    B = observed_cv.get('B', 0.0)
    P = observed_cv.get('P', 0.0)
    S = observed_cv.get('S', 0.0)

    # Translate channel values to human-readable state descriptors
    def _ch(label, val):
        if val > 0.7:   return f'high {label}'
        elif val > 0.4: return f'moderate {label}'
        else:           return f'low {label}'

    state_desc = ', '.join([
        _ch('emotional intensity', E),
        _ch('behavioral stability', B),
        _ch('predictive confidence', P),
        _ch('social openness', S),
    ])

    mem_text = ''
    if zone_memory:
        recent = zone_memory[-3:]
        lines = [f"- {e.get('cultivar','?')} {e.get('event','visited')} "
                 f"({e.get('command','')}) at step {e.get('step','?')}"
                 for e in recent]
        mem_text = 'This place remembers:\n' + '\n'.join(lines) + '\n\n'

    desc_text = f'This place: {zone_descriptor}\n\n' if zone_descriptor else ''
    cultivar_text = f'You are {cultivar_name}' + (
        f' — {cultivar_description}' if cultivar_description else '') + '.\n'

    prompt = (
        f'{cultivar_text}'
        f'Your current state: {state_desc}.\n'
        f'{desc_text}'
        f'{mem_text}'
        f'{vocab_expansion}\n\n'
        f'Respond in ONE sentence only. Speak as yourself, from your current state. '
        f'Do not explain or narrate. Do not use asterisks, stage directions, or action text. '
        f'Just speak.'
    )
    return prompt


@app.route('/zone/command', methods=['POST'])
def zone_command():
    """
    POST /zone/command

    Fire a zone command for an LLM agent arriving at, dwelling in,
    or leaving a zone.  Builds a prompt from the agent\'s current
    observed_cv and the zone\'s descriptor and memory, calls Ollama,
    and returns the spoken response.

    For scripted agents (actor != \'ollama\') returns status=\'scripted\'
    with no LLM call — the loader logs the command and writes zone memory.

    Request body (JSON):
    {
      "cultivar":    "Cindy",
      "actor":       "ollama",            // \'ollama\' or \'scripted\'
      "command":     "reflect",           // from ZONE_COMMAND_VOCAB
      "event":       "OnEnter",           // OnEnter | OnDwell | OnExit
      "zone_id":     "pool",
      "scene":       "garden_001",
      "zone_descriptor": "A still pool...",
      "step":        3,
      "ollama_model": "llama3.2",         // optional, default llama3.2
      "ollama_url":  "http://localhost:11434"  // optional
    }

    Response (LLM agent):
    {
      "status":   "ok",
      "cultivar": "Cindy",
      "command":  "reflect",
      "response": "The water does not move...",
      "zone_id":  "pool",
      "memory_written": true
    }

    Response (scripted agent):
    {
      "status":   "scripted",
      "cultivar": "Cindy",
      "command":  "reflect",
      "zone_id":  "pool",
      "memory_written": true
    }
    """
    import urllib.request as _urllib_req
    import urllib.error  as _urllib_err

    data        = request.get_json() or {}
    cultivar    = data.get('cultivar', '').strip()
    actor       = data.get('actor', 'scripted').strip().lower()
    command     = data.get('command', '').strip()
    event_type  = data.get('event', 'OnEnter').strip()
    zone_id     = data.get('zone_id', '').strip()
    scene_name  = data.get('scene', '').strip()
    zone_desc   = data.get('zone_descriptor', '').strip()
    step        = int(data.get('step', 0))
    ollama_model = data.get('ollama_model', 'llama3.2')
    ollama_url   = data.get('ollama_url', 'http://localhost:11434')

    if not cultivar or not command or not zone_id:
        return jsonify({'error': 'cultivar, command, and zone_id are required'}), 400

    if command not in _ZONE_COMMAND_VOCAB:
        return jsonify({'error': f'Unknown command: {command!r}. '
                       f'Known: {list(_ZONE_COMMAND_VOCAB)}'}), 400

    # Get current observed_cv for this cultivar
    runtime = _agent_runtime.get(cultivar)
    obs_cv  = runtime.observed_cv if runtime else {
        'E': 0.25, 'B': 0.25, 'P': 0.25, 'S': 0.25}

    # Write zone memory event
    zone_mem = _get_zone_memory(scene_name, zone_id)
    mem_event = {
        'cultivar': cultivar,
        'event':    event_type,
        'command':  command,
        'step':     step,
        'timestamp': time.time(),
        'observed_cv': {k: round(v, 3) for k, v in obs_cv.items()},
    }
    _append_zone_memory(scene_name, zone_id, mem_event)

    # Scripted agent — log and return without LLM call
    if actor not in ('ollama', 'llm'):
        return jsonify({
            'status':         'scripted',
            'cultivar':       cultivar,
            'command':        command,
            'zone_id':        zone_id,
            'memory_written': True,
        })

    # LLM agent — build prompt and call Ollama
    prompt = _build_zone_prompt(
        cultivar_name=cultivar,
        command=command,
        observed_cv=obs_cv,
        zone_descriptor=zone_desc,
        zone_memory=zone_mem,
        cultivar_description='',
    )

    try:
        _payload = _json_zc.dumps({
            'model':   ollama_model,
            'prompt':  prompt,
            'stream':  False,
            'options': {'num_predict': 60},  # ~one sentence; enforces prompt instruction
        }).encode('utf-8')
        _req = _urllib_req.Request(
            f'{ollama_url}/api/generate',
            data=_payload,
            headers={'Content-Type': 'application/json'},
            method='POST',
        )
        with _urllib_req.urlopen(_req, timeout=30) as _resp:
            response_text = _json_zc.loads(_resp.read().decode('utf-8')).get('response', '').strip()
    except _urllib_err.URLError as e:
        return jsonify({
            'status':   'error',
            'cultivar': cultivar,
            'command':  command,
            'zone_id':  zone_id,
            'error':    f'Ollama unreachable: {e}',
        }), 500
    except Exception as e:
        return jsonify({
            'status':   'error',
            'cultivar': cultivar,
            'command':  command,
            'zone_id':  zone_id,
            'error':    str(e),
        }), 500

    return jsonify({
        'status':         'ok',
        'cultivar':       cultivar,
        'command':        command,
        'zone_id':        zone_id,
        'response':       response_text,
        'memory_written': True,
        'prompt_used':    prompt,
    })


@app.route('/zone/memory', methods=['GET'])
def zone_memory_get():
    """
    GET /zone/memory?scene=garden_001&zone=pool

    Returns the memory events for a zone.
    """
    scene_name = request.args.get('scene', '').strip()
    zone_id    = request.args.get('zone', '').strip()
    if not scene_name or not zone_id:
        return jsonify({'error': 'scene and zone params required'}), 400
    mem = _get_zone_memory(scene_name, zone_id)
    return jsonify({
        'scene':   scene_name,
        'zone_id': zone_id,
        'events':  mem,
        'count':   len(mem),
    })


@app.route('/zone/memory', methods=['DELETE'])
def zone_memory_clear():
    """
    DELETE /zone/memory?scene=garden_001&zone=pool

    Clears memory for a zone (or all zones in scene if zone omitted).
    """
    scene_name = request.args.get('scene', '').strip()
    zone_id    = request.args.get('zone', '').strip()
    if not scene_name:
        return jsonify({'error': 'scene param required'}), 400
    if zone_id:
        if scene_name in _zone_memory:
            _zone_memory[scene_name][zone_id] = []
        cleared = zone_id
    else:
        _zone_memory[scene_name] = {}
        cleared = 'all'
    # Clear from disk too
    mem_path = _os_zc.path.join(
        _os_zc.path.dirname(_os_zc.path.abspath(__file__)),
        'scenes', f'{scene_name}_zone_memory.json'
    )
    if _os_zc.path.exists(mem_path):
        try:
            _os_zc.remove(mem_path)
        except Exception:
            pass
    return jsonify({'status': 'cleared', 'scene': scene_name, 'zone': cleared})


# ---------------------------------------------------------------------------
# End Zone Command System
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    _steward = Agent("The Steward",
                     weights={"E": 0.40, "B": 0.25, "P": 0.25, "S": 0.10},
                     role="agent")
    _steward.set_regulation(0.80)
    field.register(_steward)

    _archivist = Agent("The Archivist",
                       weights={"E": 0.15, "B": 0.40, "P": 0.30, "S": 0.15},
                       role="agent")
    _archivist.set_regulation(0.85)
    field.register(_archivist)

    _witness = Agent("The Witness",
                     weights={"E": 0.25, "B": 0.20, "P": 0.25, "S": 0.30},
                     role="agent")
    _witness.set_regulation(0.90)
    field.register(_witness)

    lady = Agent("Lady_Cultivar",
                 weights={"E": 0.40, "B": 0.20, "P": 0.20, "S": 0.20},
                 role="agent")
    lady.set_regulation(0.62)
    cultivars["Lady of the Garden"] = {
        "weights": lady.weights,
        "regulation": 0.62,
        "role": "agent",
        "description": "High emotional weight, strong regulation. "
                        "Feels fully, chooses precisely.",
        "created": time.time()
    }

    skeptic = Agent("Skeptic_Cultivar",
                    weights={"E": 0.15, "B": 0.40, "P": 0.30, "S": 0.15},
                    role="agent")
    cultivars["Skeptic"] = {
        "weights": skeptic.weights,
        "regulation": 0.85,
        "role": "agent",
        "description": "Behavioral and predictive dominant. "
                        "High gaming detection sensitivity.",
        "created": time.time()
    }

    cultivars["Gardener"] = {
        "weights": {"E": 0.20, "B": 0.30, "P": 0.25, "S": 0.25},
        "regulation": 0.75,
        "role": "gardener",
        "description": "Balanced intervention role. Detached observer "
                        "who can adjust without being captured.",
        "created": time.time()
    }

    # Load cultivar XML definitions from cultivars/ directory (V2.3)
    import os as _os, xml.etree.ElementTree as _ET
    _cultivars_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "cultivars")
    if _os.path.exists(_cultivars_dir):
        _loaded = 0
        for _fname in sorted(_os.listdir(_cultivars_dir)):
            if not _fname.endswith(".xml"):
                continue
            try:
                _tree = _ET.parse(_os.path.join(_cultivars_dir, _fname))
                _root = _tree.getroot()
                _cel  = _root.find("Cultivar")
                if _cel is None:
                    continue
                _name = _cel.get("agentname","")
                _wel  = _cel.find("Weights")
                _rel  = _cel.find("Regulation")
                if _name and _wel is not None:
                    _w = {ch: float(_wel.get(ch, 0.25)) for ch in ["E","B","P","S"]}
                    _r = float(_rel.get("value", 0.7)) if _rel is not None else 0.7
                    _desc = (_cel.findtext("Description") or "").strip()
                    cultivars[_name] = {
                        "weights":     _w,
                        "regulation":  _r,
                        "role":        "agent",
                        "description": _desc,
                        "source":      "xml",
                        "filename":    _fname,
                        "created":     time.time()
                    }
                    # Also register as field agent if not already present
                    if _name not in field.agents:
                        _agent = Agent(_name, weights=_w, role="agent")
                        _agent.set_regulation(_r)
                        field.register(_agent)
                    _loaded += 1
            except Exception as _e:
                print(f"  Warning: could not load {_fname}: {_e}")
        if _loaded:
            print(f"  Loaded {_loaded} cultivar definitions from cultivars/")

    print("MCCF API server starting on http://localhost:5000")
    print("Endpoints: /sensor /field /agent /cultivar /zone /waypoint /scene /voice")
    print("           /hothouse/state /hothouse/x3d /hothouse/humanml")
    print("           /collapse/run /export/x3d /export/python /export/json")
    app.run(debug=True, port=5000, threaded=True)
