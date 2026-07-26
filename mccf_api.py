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
import re
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
            candidates = [
                _scene_filepath(base + '_scene.xml'),
                _scene_filepath(base + '.xml'),
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
    # Sanitise via the shared helper — must stay identical to the sanitization
    # used for the scenes/<scene_name>/ folder (save_scene_xml, arc_export_save)
    # or the Loader's derived scene_name (from this .x3d filename) won't match
    # the arcs folder on disk. See _safe_path_component's docstring.
    safe_name = _safe_path_component(scene_name)
    filename = safe_name + '.x3d'
    filepath = os.path.join(x3d_dir, filename)
    content = request.get_data(as_text=True)
    if not content:
        return jsonify({'status': 'error', 'error': 'no content'}), 400
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'output': f'static/x3d/{filename}', 'filename': filename})


# ---------------------------------------------------------------------------
# HAnim Editor endpoints — extracted to mccf_hanim_api.py (Day 63).
# This was ~3,300 lines (over half the original file) — avatar upload/list/
# preview, HAnim export, joint listing/wiring/normalization, facial morph/AU
# injection, and Mixamo ingestion. Confirmed zero dependency on field/scene/
# drift_manager/playback_manager/chorus_manager or mccf_core imports before
# moving. See register_hanim_api(app) call below, and mccf_hanim_api.py's
# module docstring for the extraction rationale.
# ---------------------------------------------------------------------------

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


def _safe_path_component(s):
    """
    Sanitize a single path SEGMENT (a scene name or take name) for safe use
    inside a nested directory path — NOT the same job as os.path.basename(),
    which only strips a full filename down to its last segment. This is used
    when we're deliberately building a multi-segment path (scenes/<scene>/
    arcs/<take>/<file>) and each segment individually needs to be safe
    without collapsing the whole intended structure down to one component.

    IMPORTANT: this must sanitize identically to upload_x3d_scene()'s
    `re.sub(r'[^A-Za-z0-9_\\-]', '_', scene_name)`, because the X3D Loader
    derives "current scene name" by stripping ".x3d" off whatever filename
    /scene/x3d/list gave it, then sends that as scene_name to /arc/playback.
    If this function sanitized differently (e.g. only stripping slashes and
    leaving spaces/punctuation alone), a scene name like "Giparu Garden"
    would produce scenes/Giparu Garden/arcs/... on save but the Loader would
    query scene_name=Giparu_Garden (from Giparu_Garden.x3d) — a folder that
    doesn't exist, so /arc/playback correctly reports zero files even though
    the arc really was saved. Keeping both sanitizers in lock-step is what
    makes the folder name and the .x3d filename the same string.
    """
    s = (s or '').strip()
    s = re.sub(r'[^A-Za-z0-9_\-]', '_', s)
    return s or 'unnamed'


@app.route('/scene/save/zones', methods=['POST'])
def save_zone_xml():
    """
    LEGACY — superseded by POST /zone/template below (Directory Redesign §5.2).

    Write zone XML from Scene Composer to zones/<filename>.
    Historically called by exportZoneXML() with a scene-prefixed filename
    (e.g. "garden_001_zones.xml"), duplicating data that already lives in the
    scene wrapper's <Zones> block — confirmed nothing reads this file back,
    including the X3D-generation path (see /scene/x3d/upload above, which
    only ever writes content the client already built, never reads zones/).
    Left in place, unchanged, so nothing already relying on it breaks; new
    zone-template work should use /zone/template instead.
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


@app.route('/zone/template', methods=['POST'])
def save_zone_template():
    """
    Save a genuinely reusable zone template to zones/<name>.xml — Directory
    Redesign §5.2: same role as cultivars/<name>.xml (see the cultivar XML
    loader further down this file for the sibling pattern this mirrors).

    Generically named (no scene prefix) — one file per zone TYPE, not per
    placement. A placed zone instance references this by name (template="...")
    from the scene wrapper's own <Zones><Zone> block, which keeps the
    per-placement data (position, radius, and any overridden fields).

    Body: { name: "Giparu", content: "<ZoneTemplate name=\"Giparu\">...</ZoneTemplate>" }
    """
    data = request.get_json() or {}
    name    = data.get('name', '').strip()
    content = data.get('content', '').strip()
    if not name or not content:
        return jsonify({'status': 'error', 'error': 'name and content required'}), 400
    safe_name = _safe_path_component(name)
    zones_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zones')
    os.makedirs(zones_dir, exist_ok=True)
    filepath = os.path.join(zones_dir, safe_name + '.xml')
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'path': f'zones/{safe_name}.xml', 'name': safe_name})


@app.route('/zone/template/list', methods=['GET'])
def list_zone_templates():
    """
    List and parse all zone templates in zones/*.xml into a single dict, the
    same load-everything-up-front shape as the cultivar XML loader below
    (see "Load cultivar XML definitions from cultivars/ directory").

    Skips any leftover *_zones.xml files from the old per-scene writer above
    (save_zone_xml) — those are scene-prefixed and not <ZoneTemplate> XML, so
    they fail the root-tag check and are silently excluded rather than erroring.

    Returns { templates: { "Giparu": { zone_type, descriptor, weights,
                                        ambient_theme, chorus, sound, asset }, ... } }
    """
    import xml.etree.ElementTree as _ET
    zones_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'zones')
    templates = {}
    if not os.path.isdir(zones_dir):
        return jsonify({'templates': templates})

    for fname in sorted(os.listdir(zones_dir)):
        if not fname.endswith('.xml'):
            continue
        fpath = os.path.join(zones_dir, fname)
        try:
            tree = _ET.parse(fpath)
            root = tree.getroot()
            if root.tag != 'ZoneTemplate':
                continue  # not a template file (e.g. legacy *_zones.xml) — skip
            name = root.get('name') or os.path.splitext(fname)[0]

            desc_el = root.find('Descriptor')
            descriptor = (desc_el.text or '').strip() if desc_el is not None else ''

            w_el = root.find('Weights')
            weights = {ch: float(w_el.get(ch, 0.25)) for ch in ('E', 'B', 'P', 'S')} if w_el is not None \
                else {'E': 0.25, 'B': 0.25, 'P': 0.25, 'S': 0.25}

            at_el = root.find('AmbientTheme')
            ambient_theme = {
                'scale': at_el.get('scale', 'major') if at_el is not None else 'major',
                'tempo': at_el.get('tempo', 'medium') if at_el is not None else 'medium'
            }

            zone_type = root.get('zone_type', 'neutral')

            chorus = None
            c_el = root.find('Chorus')
            if c_el is not None:
                persona_el = c_el.find('Persona')
                chorus = {
                    'llm': c_el.get('llm', 'stub'),
                    'tone': c_el.get('tone', 'oracular'),
                    'max_tokens': int(c_el.get('max_tokens', 80)),
                    'display': c_el.get('display', 'overlay'),
                    'persona': (persona_el.text or '').strip() if persona_el is not None else ''
                }

            sound = None
            sd_el = root.find('SoundDesign')
            if sd_el is not None:
                amb_el = sd_el.find('.//Track[@id="ambient"]')
                dw_el  = sd_el.find('.//Track[@id="dwell"]')
                if amb_el is not None:
                    sound = {
                        'url': amb_el.get('url', ''),
                        'gain': float(amb_el.get('gain', 0.8)),
                        'loop': amb_el.get('loop', 'true') != 'false',
                        'filter': amb_el.get('filter') is not None,
                        'filterFreq': int(amb_el.get('filterFreq', 900)),
                        'filterQ': float(amb_el.get('filterQ', 1.0)),
                        'dwellUrl': dw_el.get('url', '') if dw_el is not None else '',
                        'dwellGain': float(dw_el.get('gain', 0.85)) if dw_el is not None else 0.85
                    }

            asset = None
            a_el = root.find('Asset')
            if a_el is not None:
                asset = {
                    'url': a_el.get('url', ''),
                    'offsetX': float(a_el.get('offsetX', 0)),
                    'offsetY': float(a_el.get('offsetY', 0)),
                    'offsetZ': float(a_el.get('offsetZ', 0)),
                    'rotationY': float(a_el.get('rotationY', 0)),
                    'scale': float(a_el.get('scale', 1))
                }

            templates[name] = {
                'zone_type': zone_type,
                'descriptor': descriptor,
                'weights': weights,
                'ambient_theme': ambient_theme,
                'chorus': chorus,
                'sound': sound,
                'asset': asset
            }
        except Exception as e:
            print(f'[zone_template] failed to parse {fname}: {e}')
            continue

    return jsonify({'templates': templates})


@app.route('/scene/save/scene', methods=['POST'])
def save_scene_xml():
    """
    Write scene XML from Scene Composer to scenes/<scene_name>/<filename>.
    Called by exportSceneXML() in mccf_scene_composer.html.
    Body: { filename: "garden_001_scene.xml", content: "<Scene>...</Scene>",
            scene_name: "garden_001" }

    scene_name is now required (Day 67 directory redesign) — the scene folder
    is the container for everything belonging to that scene, including its
    arcs/ subdirectory. Falls back to deriving scene_name from the filename
    (stripping a trailing "_scene.xml") only if the caller doesn't send it,
    for compatibility with any caller not yet updated.
    """
    data = request.get_json() or {}
    filename = data.get('filename', '').strip()
    content  = data.get('content', '').strip()
    scene_name = data.get('scene_name', '').strip()
    if not filename or not content:
        return jsonify({'status': 'error', 'error': 'filename and content required'}), 400
    if not scene_name:
        scene_name = filename[:-len('_scene.xml')] if filename.endswith('_scene.xml') else filename
    scene_name = _safe_path_component(scene_name)
    filename = os.path.basename(filename)
    scenes_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    scene_dir = os.path.join(scenes_root, scene_name)
    os.makedirs(scene_dir, exist_ok=True)
    filepath = os.path.join(scene_dir, filename)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return jsonify({'status': 'ok', 'path': f'scenes/{scene_name}/{filename}'})


def _derive_scene_name(filename):
    """
    Scene name is the filename with its '_scene.xml' suffix stripped — the
    same convention used as the save-time fallback above. Lets every read
    endpoint locate a scene's folder from just the filename it's always been
    passed, without every caller needing to be updated to send scene_name
    explicitly.
    """
    fn = os.path.basename(filename)
    return fn[:-len('_scene.xml')] if fn.endswith('_scene.xml') else fn


def _scene_filepath(filename):
    """Resolve a scene wrapper filename to scenes/<scene_name>/<filename>."""
    filename = os.path.basename(filename)
    scene_name = _safe_path_component(_derive_scene_name(filename))
    scenes_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    return os.path.join(scenes_root, scene_name, filename)


@app.route('/scenes', methods=['GET'])
def list_scenes():
    """
    List scene XML files under scenes/<scene_name>/<scene_name>_scene.xml.
    Returns filename, cultivars found, waypoint count.
    """
    import re as _re
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    if not os.path.isdir(scenes_dir):
        return jsonify({'files': [], 'scenes_dir': scenes_dir})
    files = []
    for scene_name in sorted(os.listdir(scenes_dir)):
        scene_dir = os.path.join(scenes_dir, scene_name)
        if not os.path.isdir(scene_dir):
            continue
        for fname in sorted(os.listdir(scene_dir)):
            if not fname.endswith('.xml'):
                continue
            fpath = os.path.join(scene_dir, fname)
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
    List scene XML files under scenes/<scene_name>/<scene_name>_scene.xml.
    Used by the composer scene dropdown (GET /scene/list/scenes).
    Returns { files: ["garden_001_scene.xml", ...] } sorted newest-first
    by scene folder mtime.
    """
    scenes_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'scenes')
    if not os.path.isdir(scenes_dir):
        return jsonify({'files': [], 'scenes_dir': scenes_dir})
    entries = []
    for scene_name in os.listdir(scenes_dir):
        scene_dir = os.path.join(scenes_dir, scene_name)
        if not os.path.isdir(scene_dir):
            continue
        for fname in os.listdir(scene_dir):
            if fname.endswith('.xml'):
                entries.append((os.path.getmtime(os.path.join(scene_dir, fname)), fname))
    entries.sort(reverse=True)
    files = [fname for _, fname in entries]
    return jsonify({'files': files, 'scenes_dir': scenes_dir})


@app.route('/media/list', methods=['GET'])
def list_media_files():
    """
    List audio files in static/x3d/X3DAssets/media/ directory.
    Used by Scene Composer sound pickers (GET /media/list).
    Returns { files: ["garden_theme.mp3", ...] } sorted alphabetically.

    Day 77: relocated from static/x3d/media/ to static/x3d/X3DAssets/media/
    (the author's own directory reorganization) — matches the exported
    scene's actual relative reference, X3DAssets/media/<subdir>/<file>, since
    the X3D Loader doesn't reference this path itself; it only plays back
    whatever URL Scene Composer already wrote into the exported scene file.

    Optional query params:
      subdir=convolver  — scan static/x3d/X3DAssets/media/convolver/ and
                          prefix filenames with "convolver/" so the composer
                          builds the correct url: X3DAssets/media/convolver/file.wav
      ext=wav           — filter to a single extension (wav only, etc.)
    """
    media_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d', 'X3DAssets', 'media')
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


@app.route('/x3d/assets/list', methods=['GET'])
def list_x3d_assets():
    """
    List available X3D asset files in static/x3d/X3DAssets/.
    Used by Scene Composer's zone editor to populate the "Inline Asset" dropdown,
    so a zone can reference an existing X3D model (e.g. a fountain, statue) via
    <Inline url="X3DAssets/<file>.x3d"/> nested inside the zone's Transform in
    the exported scene — same relative-path convention as protos/ (see
    buildCameraProtoDecls in mccf_scene_composer.html).

    Non-recursive: only top-level .x3d files are listed. The texture/
    subdirectory (referenced internally by asset files via their own relative
    paths) is intentionally not scanned or exposed here — same split as
    convolver/soundeffects staying separate from the flat media/ listing in
    /media/list above.

    Returns { files: ["fountain.x3d", ...] }
    """
    assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'x3d', 'X3DAssets')
    if not os.path.isdir(assets_dir):
        return jsonify({'files': [], 'assets_dir': assets_dir})

    files = sorted([
        f for f in os.listdir(assets_dir)
        if os.path.isfile(os.path.join(assets_dir, f))
        and f.lower().endswith('.x3d')
        and not f.startswith('.')
    ])
    return jsonify({'files': files, 'assets_dir': assets_dir})


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
    filepath = _scene_filepath(filename)
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
        paths:         { name: { name, agent, waypoints:[wpName,...] } },
        dialogueLines: [ { id, actor, type, mode, blocking, trigger, ttsText,
                       tagSource, audioFile, audioSource, text }, ... ]
                       — real <Dialogue><Line> entries if the scene has any,
                       plus every legacy waypoint-nested Question/Response/
                       Statement synthesized with trigger="legacy-waypoint:
                       <name>". See docs/DIALOGUE_SCHEMA.md (Day 72, item 5a).
    }
    """
    import xml.etree.ElementTree as ET
    import re as _re

    data     = request.get_json() or {}
    filename = os.path.basename(data.get('filename', '').strip())
    if not filename:
        return jsonify({'error': 'filename required'}), 400

    filepath = _scene_filepath(filename)
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

    # ── dialogue: new scene-level <Dialogue> container + legacy migration ──
    # Day 72, build schedule item 5a (full decoupling, not the incremental
    # option). See docs/DIALOGUE_SCHEMA.md for the schema and migration
    # rules this implements. A scene with no <Dialogue> element is not an
    # error — it's a scene from before this schema existed; its dialogue
    # lives nested inside <Waypoint> instead (already parsed into each
    # waypoint's qaLines above) and is synthesized here with an explicit
    # trigger="legacy-waypoint:<name>" rather than being silently
    # reinterpreted as a real sensed/zone/declared trigger it never had.
    #
    # trigger is returned as its raw stored string (e.g. "declared:58"), not
    # parsed into a {type, ...} object — that parsing lives client-side in
    # dialogue-xml.js's parseTrigger(), so there's exactly one
    # implementation of it instead of two that could drift apart.
    #
    # Day 73: tagSource/audioSource are returned the same way — raw strings
    # (e.g. "llm-interpreted:Kate"), not parsed objects. Parsing them lives
    # in dialogue-xml.js's parseTagSource()/parseAudioSource(), same reason
    # as trigger. This endpoint previously returned ttsText but silently
    # dropped tagSource/audioFile/audioSource entirely — a real gap (a tag
    # with no recorded provenance, or an audio file with no recorded
    # source, is exactly the ambiguity those fields exist to prevent), now
    # fixed. None if the attribute is absent, for all four.
    dialogue_lines = []

    dialogue_el = root.find('Dialogue')
    if dialogue_el is not None:
        for line_el in dialogue_el.findall('Line'):
            line_id = line_el.get('id', '').strip()
            if not line_id:
                continue
            dialogue_lines.append({
                'id':          line_id,
                'actor':       line_el.get('actor', ''),
                'type':        line_el.get('type', 'Statement'),
                'mode':        line_el.get('mode', 'improv'),
                'blocking':    line_el.get('blocking', 'false').lower() == 'true',
                'trigger':     line_el.get('trigger', '').strip(),
                'ttsText':     line_el.get('ttsText'),     # None if absent — see docs/DIALOGUE_SCHEMA.md
                'tagSource':   line_el.get('tagSource'),   # None if absent — raw string, see above
                'audioFile':   line_el.get('audioFile'),   # None if absent
                'audioSource': line_el.get('audioSource'), # None if absent — raw string, see above
                'text':        (line_el.text or '').strip(),
            })

    for wp_name, wp_data in waypoints.items():
        for idx, qa in enumerate(wp_data['qaLines']):
            dialogue_lines.append({
                'id':          f'{wp_name}_{idx}',
                'actor':       qa['speaker'],
                'type':        qa['type'],
                'mode':        'improv',
                'blocking':    False,
                'trigger':     f'legacy-waypoint:{wp_name}',
                'ttsText':     None,  # legacy-migrated lines never carry these —
                'tagSource':   None,  # see DIALOGUE_SCHEMA.md's migration section:
                'audioFile':   None,  # none of the four Day-73 fields are touched
                'audioSource': None,  # by the legacy-migration path, ever.
                'text':        qa['text'],
            })

    # Notify Chorus manager — parse scene XML for <Chorus> zone extension.
    try:
        cm = app.config.get('_chorus_manager')
        if cm is not None:
            cm.load_config_from_scene_xml(raw)
    except Exception:
        pass

    return jsonify({
        'sceneConfig':    scene_config,
        'zones':          zones_inferred,
        'agents':         agents,
        'placedAgents':   placed_agents,
        'waypoints':      waypoints,
        'paths':          paths,
        'dialogueLines':  dialogue_lines
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
from mccf_hanim_api import register_hanim_api

_attractor_registry = register_attractor_api(app, scene, field)
_scene_registry     = register_scene_api(app)
_cultivar_registry  = register_cultivar_api(app)
register_generate_api(app)
register_hanim_api(app)
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
    # Day 66 fix: summary() alone doesn't carry weights (same convention as
    # /agent/<name>, which adds weights as a sibling key rather than nesting
    # it inside summary()). Without this, every consumer of /field that reads
    # agents[name].weights — Composer's Field State panel, the Loader's
    # applyFieldData()/applyHotHouseData() — got undefined, defaulted to {},
    # and every channel rendered as flat 0.00 regardless of the agent's real
    # constitutional weights.
    for name, agent in field.agents.items():
        agents_summary[name]["weights"] = dict(agent.weights)
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
        # Day 66 fix: this was the only hothouse endpoint the Loader's pollHotHouse()
        # ever called, and it never advanced the simulation — ef.step() was only
        # wired into /hothouse/state, which nothing on the client calls. Every
        # 1000ms poll was re-serving the same frozen snapshot instead of a running
        # field. Stepping here is what makes HotHouse actually live.
        ef.step()
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
    Save arc export as XML.
    Body: { cultivar, timestamp, genre, seed, rows, scene_name, take_name }

    Day 67 directory redesign: an arc belongs to a scene, and multiple
    agents' arcs recorded as part of the same working session belong
    together in one take. Path is now:
        scenes/<scene_name>/arcs/<take_name>/arc_<id>.xml
    take_name is generated client-side once per session and reused across
    every arc saved in that session — see mccf_scene_composer.html's
    _currentTakeId. If the caller doesn't send scene_name or take_name
    (an older client, or a direct API call), falls back to a flat
    scenes/_unscoped_arcs/ location rather than failing, so nothing breaks —
    but this fallback location won't show up scoped to any real scene in
    the playback dropdown, so it's a degraded path, not an equivalent one.
    Returns: { status, filename, path }
    """
    import os
    data      = request.json or {}
    cultivar  = data.get("cultivar", "unknown")
    path_name = data.get("path_name", "").strip()
    timestamp = data.get("timestamp", "")
    scene_name= data.get("scene_name", "").strip()
    take_name = data.get("take_name", "").strip()
    rows      = data.get("rows", [])
    genre     = data.get("genre", "")
    seed      = data.get("seed", None)

    if not rows:
        return jsonify({"status": "error", "message": "no rows"}), 400

    mccf_root = os.path.dirname(os.path.abspath(__file__))
    if scene_name and take_name:
        arcs_dir = os.path.join(
            mccf_root, 'scenes',
            _safe_path_component(scene_name), 'arcs',
            _safe_path_component(take_name)
        )
    else:
        # Degraded fallback — see docstring. Keeps the endpoint working for
        # any caller not yet sending scene_name/take_name, but these land
        # outside every scene's own folder and won't appear scene-scoped.
        arcs_dir = os.path.join(mccf_root, 'scenes', '_unscoped_arcs')
    os.makedirs(arcs_dir, exist_ok=True)

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
        # Use waypoint name as-is — no uppercase mangling.
        # Preserves scene XML name (e.g. "w2") so EventCues trigger matching works.
        wid = row.get("waypoint", "")
        xml += f'    <Waypoint id="{xml_esc(wid)}" stepno="{row.get("step","")}"'
        xml += f' name="{xml_esc(wid)}"'
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
    filepath = os.path.join(arcs_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(xml)

    rel_path = os.path.relpath(filepath, mccf_root)
    return jsonify({"status": "saved", "filename": filename,
                    "path": rel_path, "rows": len(rows)})


# NOTE: GET /arc/playback used to be defined here (Day 67 directory
# redesign). Removed — it was a second, independent implementation of the
# exact same URL that mccf_playback.py's playback_bp already registers
# (see register_playback_api() call above). Two competing route
# registrations for one URL is exactly the "which one wins is whatever
# Flask/Werkzeug decides silently" bug that produced the legacy
# exports_dir/[] response for weeks of live testing — this file's version
# never actually ran once mccf_playback.py was wired in.
# The listing logic now lives in mccf_playback.py's PlaybackManager.list_files()
# / _iter_arc_files(), which was updated to walk the same nested
# scenes/<scene_name>/arcs/<take_name>/ layout that arc_export_save() (below)
# writes to. It has to live there rather than here anyway, since
# /arc/playback/start, /start/all, /step, /stop, and /reset are also only
# defined in mccf_playback.py and need to agree with the listing about
# where arc files actually are.


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


# NOTE: the legacy flat exports/ TSV endpoints (`GET /exports`, `DELETE
# /exports/<filename>`) were removed here as part of the Day 67 directory
# redesign cleanup. Confirmed no caller in either mccf_scene_composer.html
# or mccf_x3d_loader.html referenced them before removal. Arc data now lives
# exclusively under scenes/<scene_name>/arcs/<take_name>/ — see arc_export_save()
# and arc_playback_list() above. If a stray exports/ folder still exists on
# disk from before this cleanup, it is no longer read or written by anything
# in this file and can be deleted manually.


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
        # Parse per-coupler params from JSON attribute if present.
        # ElementTree strips the outer XML quotes, so json.loads works directly.
        import json as _json
        cp_raw = link_el.get('coupler_params', '').strip()
        try:
            coupler_params = _json.loads(cp_raw) if cp_raw else {}
        except (ValueError, TypeError):
            coupler_params = {}
        links.append({
            'from':           src,
            'to':             tgt,
            'strength':       strength,
            'couplers':       couplers,
            'coupler_params': coupler_params,
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
        for candidate in [scene_name + '_scene.xml', scene_name + '.xml']:
            cpath = _scene_filepath(candidate)
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

def _zone_memory_path(scene_name: str) -> str:
    """
    Resolve a scene's zone-memory file to scenes/<scene_name>/zone_memory.json
    (Day 67 directory redesign — this is per-scene instance data, same
    category as the scene wrapper itself, so it lives alongside it rather
    than flat at the scenes/ root under a scene-prefixed filename.)
    """
    scene_dir = _os_zc.path.join(
        _os_zc.path.dirname(_os_zc.path.abspath(__file__)),
        'scenes', _safe_path_component(scene_name)
    )
    return _os_zc.path.join(scene_dir, 'zone_memory.json')

def _get_zone_memory(scene_name: str, zone_id: str) -> list:
    if scene_name not in _zone_memory:
        _zone_memory[scene_name] = {}
    if zone_id not in _zone_memory[scene_name]:
        # Try loading from disk
        mem_path = _zone_memory_path(scene_name)
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
    mem_path = _zone_memory_path(scene_name)
    try:
        _os_zc.makedirs(_os_zc.path.dirname(mem_path), exist_ok=True)
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
    mem_path = _zone_memory_path(scene_name)
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
