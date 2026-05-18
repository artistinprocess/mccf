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

    avatar_name = request.headers.get('X-Avatar-Name', '').strip() or 'avatar'
    slug        = _re.sub(r'[^A-Za-z0-9_\-]', '_', avatar_name).lower()
    filename    = f'{slug}_hanim.x3d'
    filepath    = os.path.join(avatar_dir, filename)

    content = request.get_data(as_text=True)
    if not content:
        return jsonify({'status': 'error', 'error': 'no content'}), 400

    # ── XML parse ────────────────────────────────────────────────────────
    # Register namespaces so they round-trip correctly
    ET.register_namespace('', 'https://www.web3d.org/specifications/x3d-4.0.xsd')

    try:
        # ET doesn't handle the <!DOCTYPE ...> declaration — strip it first,
        # preserve the <?xml ...?> processing instruction
        xml_decl   = ''
        doctype    = ''
        body       = content
        lines      = content.splitlines(keepends=True)
        body_lines = []
        for line in lines:
            if line.strip().startswith('<?xml'):
                xml_decl = line
            elif line.strip().startswith('<!DOCTYPE'):
                doctype = line          # save for reference, don't reinsert
            else:
                body_lines.append(line)
        body = ''.join(body_lines)

        root = ET.fromstring(body)
    except ET.ParseError as e:
        return jsonify({'status': 'error', 'error': f'XML parse failed: {e}'}), 400

    # ── DEF names to strip ───────────────────────────────────────────────
    HUD_TIMER_DEFS = {
        'DefaultTimer','PitchTimer','YawTimer','RollTimer',
        'WalkTimer','RunTimer','JumpTimer','KickTimer','StopTimer'
    }
    HUD_DEFS = HUD_TIMER_DEFS | {'HudProx','HudXform'}
    # Touch sensor DEF names — match by suffix pattern
    def is_touch_sensor(el):
        return el.tag.split('}')[-1] == 'TouchSensor'

    def is_hud_node(el):
        tag  = el.tag.split('}')[-1]
        defv = el.get('DEF', '')
        if defv in HUD_DEFS:
            return True
        if tag == 'TouchSensor':
            return True
        if tag == 'TimeSensor' and defv in HUD_TIMER_DEFS:
            return True
        return False

    def is_hud_route(el):
        tag = el.tag.split('}')[-1]
        if tag != 'ROUTE':
            return False
        fn = el.get('fromNode', '')
        tn = el.get('toNode',   '')
        strip_nodes = HUD_DEFS | {
            'Stand_Touch','Pitch_Touch','Yaw_Touch','Roll_Touch',
            'Walk_Touch','Run_Touch','Jump_Touch','Kick_Touch','Stop_Touch'
        }
        return fn in strip_nodes or tn in strip_nodes

    def strip_hud(parent):
        """Recursively remove HUD nodes from parent's children."""
        to_remove = []
        for child in list(parent):
            if is_hud_node(child) or is_hud_route(child):
                to_remove.append(child)
            else:
                strip_hud(child)
        for child in to_remove:
            parent.remove(child)

    strip_hud(root)

    # ── Gather metadata ──────────────────────────────────────────────────
    hanim_el    = root.find('.//{*}HAnimHumanoid')
    loa         = int(hanim_el.get('loa', 4)) if hanim_el is not None else 4
    joint_count = len(root.findall('.//{*}HAnimJoint[@name]'))
    clips = [
        el.get('DEF', '').replace('Timer', '')
        for el in root.findall('.//{*}TimeSensor')
        if el.get('DEF') and el.get('DEF') not in HUD_TIMER_DEFS
    ]

    # ── Serialise ────────────────────────────────────────────────────────
    # Preserve the original <?xml?> declaration; omit DOCTYPE (not needed)
    ET.indent(root, space='  ')
    stripped_content = (xml_decl or '<?xml version="1.0" encoding="UTF-8"?>\n') + \
                       ET.tostring(root, encoding='unicode', xml_declaration=False)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(stripped_content)

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
    """
    src = request.args.get('src', '').strip()
    if not src:
        return "Missing src parameter", 400
    # Serve directly from /static/ — Flask handles this correctly
    x3d_src = f'/static/{src}' if not src.startswith('/') else src
    html = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>H-Anim Preview</title>
  <style>
    * {{ margin:0; padding:0; box-sizing:border-box; }}
    html, body {{ width:100%; height:100%; background:#0a0e18; overflow:hidden; color:#ccc; font-family:monospace; }}
    x3d-canvas {{ width:100%; height:100%; display:block; }}
    #err {{ display:none; padding:12px; font-size:12px; color:#f06060; }}
  </style>
  <script src="https://cdn.jsdelivr.net/npm/x_ite@10.5.2/dist/x_ite.min.js"></script>
</head>
<body>
  <div id="err"></div>
  <x3d-canvas id="canvas" src="{x3d_src}"></x3d-canvas>
  <script>
    var c = document.getElementById('canvas');
    c.addEventListener('load', function() {{
      document.getElementById('err').style.display = 'none';
    }});
    c.addEventListener('error', function(e) {{
      var el = document.getElementById('err');
      el.style.display = 'block';
      el.textContent = 'X_ITE load error: ' + (e.detail || e.message || JSON.stringify(e));
    }});
  </script>
</body>
</html>"""
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
            phi   = self.constitutional_cv[ch]
            eps   = self.expressive_cv[ch]
            new   = eps + deltas[ch]
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
    runtime.set_constitutional(e_val, b_val, p_val, s_val,
                               regulation=agent._affect_regulation)

    meta = agent.meta_state
    coherence_now = round(agent.coherence_toward(others[0]) if others else 0.5, 4)

    if cultivar not in _arc_coherence_history:
        _arc_coherence_history[cultivar] = []
    _arc_coherence_history[cultivar] = [
        r for r in _arc_coherence_history[cultivar] if r['step'] != step
    ]
    _arc_coherence_history[cultivar].append({
        'step': step, 'coherence': coherence_now,
        'E': e_val, 'B': b_val, 'P': p_val, 'S': s_val
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
        strength = float(link.get('strength', 1.0))
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
    })


# ---------------------------------------------------------------------------
# End coupler system
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
    app.run(debug=True, port=5000)
