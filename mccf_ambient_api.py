"""
MCCF Ambient Sync API
======================
Single endpoint that closes all perceptual loops simultaneously:

  POST /ambient/sync
    → updates MCCF field from voice/sensor data
    → computes music parameters
    → computes lighting state
    → returns all three in one response

  GET  /lighting/state    — current computed lighting
  GET  /lighting/scalars  — flat scalar dict for X3D routing
  GET  /lighting/x3d      — X3D fragment for current lighting
  GET  /ambient/state     — combined music + lighting + field state

This is the unified output bus. One coherence state.
Three simultaneous perceptual channels: sound, light, voice.
"""

import json
import os
import re
import tempfile
import time
from flask import Blueprint, request, jsonify, current_app

ambient_bp = Blueprint('ambient', __name__)

# Injected after registration:
#   ambient_bp.field   = CoherenceField
#   ambient_bp.scene   = SceneGraph
#   ambient_bp.registry = AdapterRegistry

_last_lighting = None
_last_music    = None


def _get_field():  return ambient_bp.field
def _get_scene():
    return ambient_bp.scene if hasattr(ambient_bp, 'scene') else None


# ---------------------------------------------------------------------------
# Ambient sync — the unified output bus
# ---------------------------------------------------------------------------

@ambient_bp.route('/ambient/sync', methods=['POST'])
def ambient_sync():
    """
    Master sync endpoint. Called by:
    - Voice agent on each utterance
    - X3D scene on sensor events
    - Ambient engine on its poll timer

    Body (all optional — uses last known state for missing fields):
    {
        "from_agent":    "Alice",
        "to_agent":      "AI",
        "position":      [x, y, z],
        "sensor_data":   { distance, dwell, velocity, gaze_angle },
        "audio_features": { pitch_variance, energy, ... },
        "record_episode": false,
        "outcome_delta":  0.0,
        "valence":        0.0
    }

    Returns:
    {
        "field":    { matrix, agents, echo_risks },
        "lighting": { LightState scalar dict },
        "music":    { music parameters },
        "voice":    { TTS voice params },
        "timestamp": float
    }
    """
    from mccf_lighting import compute_lighting, lighting_scalars
    from mccf_llm import affect_to_voice_params, prosody_to_channel_vector

    data       = request.get_json() or {}
    from_name  = data.get("from_agent")
    to_name    = data.get("to_agent")
    position   = data.get("position", [0, 0, 0])

    field = _get_field()
    scene = _get_scene()

    # Update field from sensor data if provided
    if from_name and to_name and from_name in field.agents and to_name in field.agents:
        sensor_data = data.get("sensor_data")
        audio_feats = data.get("audio_features")

        if sensor_data:
            from mccf_api import compute_channel_vector
            cv = compute_channel_vector(sensor_data)
            if scene:
                cv = scene.apply_zone_pressure(cv, tuple(position))
            field.interact(from_name, to_name, cv)

        if audio_feats:
            cv_audio = prosody_to_channel_vector(audio_feats)
            field.interact(from_name, to_name, cv_audio, mutual=False)

    # Record episode to zone if requested
    if data.get("record_episode") and scene and from_name:
        from mccf_zones import ResonanceEpisode
        ep = ResonanceEpisode(
            timestamp=time.time(),
            agents_present=[from_name, to_name] if to_name else [from_name],
            outcome_delta=float(data.get("outcome_delta", 0.0)),
            emotional_intensity=0.5,
            valence=float(data.get("valence", 0.0)),
            label=data.get("episode_label", "sync")
        )
        scene.record_episode_at(tuple(position), ep)

    # Build affective context
    # If no agent specified, use first registered agent
    if not from_name and field.agents:
        from_name = next(iter(field.agents))

    # If no position given, use zone centroid or scene midpoint
    if not position or position == [0, 0, 0]:
        scene_local = _get_scene()
        if scene_local and scene_local.zones:
            locs = [list(z.location) for z in scene_local.zones.values()]
            position = [
                sum(l[0] for l in locs) / len(locs),
                0,
                sum(l[2] for l in locs) / len(locs)
            ]
        else:
            position = [0, 0, 15]  # scene midpoint default

    affective_context = _build_affective_context(from_name or "", position)

    # Compute lighting
    field_dict = {
        "agents": {
            n: {
                "weights": a.weights,
                "role": a.role,
                "regulation": a._affect_regulation
            }
            for n, a in field.agents.items()
        },
        "matrix": field.field_matrix(),
        "echo_chamber_risks": field.echo_chamber_risk()
    }
    scene_dict = scene.scene_summary() if scene else {"zones": []}

    light_state = compute_lighting(affective_context, field_dict, scene_dict)
    scalars     = lighting_scalars(light_state)
    global _last_lighting
    _last_lighting = scalars

    # Compute music parameters
    music = _compute_music_params(affective_context, scene_dict)
    global _last_music
    _last_music = music

    # Compute voice params
    voice_params = affect_to_voice_params(affective_context)

    return jsonify({
        "field":     field_dict,
        "_debug_agent_count": len(field_dict.get("agents", {})),
        "_debug_tint_count":  len(scalars.get("agent_tints", {})),
        "lighting":  scalars,
        "music":     music,
        "voice":     voice_params,
        "affect":    affective_context,
        "timestamp": time.time()
    })


def _build_affective_context(agent_name: str, position: list) -> dict:
    """Build unified affective context from field + scene."""
    field = _get_field()
    scene = _get_scene()

    agent  = field.agents.get(agent_name)
    matrix = field.field_matrix()
    row    = matrix.get(agent_name, {})

    coherence_scores = {k: v for k, v in row.items() if k != agent_name}
    avg_coh = sum(coherence_scores.values()) / max(1, len(coherence_scores))

    pos = tuple(position)
    zone_pressure = scene.zone_pressure_at(pos) if scene else {}
    active_zones  = [
        {"name": z.name, "type": z.zone_type, "color": z.color}
        for z in scene.active_zones_at(pos)
    ] if scene else []

    reg = agent._affect_regulation if agent else 1.0

    # Arousal: E channel pressure + inverse regulation
    E_pressure = zone_pressure.get("E", 0.0)
    arousal    = max(0, min(1, 0.5 + E_pressure + (1 - reg) * 0.2))

    # Valence: coherence + social zone pressure
    S_pressure = zone_pressure.get("S", 0.0)
    valence    = round((avg_coh - 0.5) * 1.5 + S_pressure * 0.3, 3)

    # Engagement: B channel + average coherence
    B_pressure = zone_pressure.get("B", 0.0)
    engagement = max(0, min(1, avg_coh * 0.6 + B_pressure * 0.3 + 0.3))

    return {
        "agent_name":         agent_name,
        "coherence_scores":   coherence_scores,
        "avg_coherence":      round(avg_coh, 4),
        "active_zones":       active_zones,
        "zone_pressure":      zone_pressure,
        "arousal":            round(arousal, 4),
        "valence":            round(valence, 4),
        "engagement":         round(engagement, 4),
        "regulation_state":   round(reg, 4),
        "coherence_to_other": round(avg_coh, 4),
        "position":           list(position),
        "timestamp":          time.time()
    }


def _compute_music_params(affective_context: dict, scene_dict: dict) -> dict:
    """
    Derive music parameters from affective context.
    Mirrors the logic in mccf_ambient.html fieldToMusic().
    """
    E   = affective_context.get("arousal", 0.5)
    val = affective_context.get("valence", 0.0)
    reg = affective_context.get("regulation_state", 0.7)
    coh = affective_context.get("avg_coherence", 0.5)
    zp  = affective_context.get("zone_pressure", {})
    zones = affective_context.get("active_zones", [])

    tension  = E * 0.6 + (1 - coh) * 0.4
    B        = zp.get("B", 0.0)
    P        = zp.get("P", 0.0)
    S        = zp.get("S", 0.0)

    tempo    = int(50 + E * 70 * (1 - reg * 0.25))

    zone_type = "neutral"
    if zones:
        z0 = zones[0]
        zone_type = z0.get("type", "neutral") if isinstance(z0, dict) else "neutral"

    ZONE_SCALES = {
        "library": "dorian", "intimate": "major",
        "forum": "mixolydian", "authority": "phrygian",
        "garden": "pentatonic", "threat": "locrian",
        "sacred": "lydian", "neutral": "pentatonic"
    }

    if tension > 0.7:    mode = "locrian"
    elif tension > 0.5:  mode = "phrygian"
    else:                mode = ZONE_SCALES.get(zone_type, "pentatonic")

    return {
        "tension":            round(tension, 3),
        "rhythm_stability":   round(0.5 + B * 0.5, 3),
        "melodic_resolution": round(0.5 + P * 0.5, 3),
        "texture_density":    round(0.3 + S * 0.5 + coh * 0.2, 3),
        "tempo":              tempo,
        "mode":               mode,
        "zone_type":          zone_type,
        "arousal":            round(E, 3),
        "valence":            round(val, 3),
        "avg_coherence":      round(coh, 3)
    }


# ---------------------------------------------------------------------------
# Lighting endpoints
# ---------------------------------------------------------------------------

@ambient_bp.route('/lighting/state', methods=['GET'])
def lighting_state():
    if not _last_lighting:
        return jsonify({"error": "no lighting state yet — call /ambient/sync first"}), 404
    return jsonify(_last_lighting)


@ambient_bp.route('/lighting/scalars', methods=['GET'])
def lighting_scalars_endpoint():
    """
    Flat scalar dict ready for direct routing to X3D light nodes.
    v2.0: Also returns flattened r/g/b components for direct SFColor
    assignment from JavaScript (key_r, key_g, key_b, etc.)
    """
    if not _last_lighting:
        return jsonify({"error": "no data"}), 404
    out = dict(_last_lighting)
    # Flatten color arrays to named components for SAI assignment
    for light in ('key', 'fill', 'ambient', 'rim'):
        col = out.get(f'{light}_color', [1.0, 1.0, 1.0])
        if isinstance(col, (list, tuple)) and len(col) == 3:
            out[f'{light}_r'] = round(float(col[0]), 4)
            out[f'{light}_g'] = round(float(col[1]), 4)
            out[f'{light}_b'] = round(float(col[2]), 4)
    return jsonify(out)


@ambient_bp.route('/lighting/x3d', methods=['GET'])
def lighting_x3d():
    """X3D fragment for current lighting state."""
    if not _last_lighting:
        return "<!-- No lighting state yet -->", 200, {"Content-Type": "application/xml"}

    from mccf_lighting import LightState
    # Reconstruct LightState from scalars
    ls = LightState(
        key_color       = tuple(_last_lighting.get("key_color", [1,1,1])),
        key_intensity   = _last_lighting.get("key_intensity", 0.8),
        key_direction   = tuple(_last_lighting.get("key_direction", [-0.5,-1,-0.5])),
        fill_color      = tuple(_last_lighting.get("fill_color", [0.8,0.85,1])),
        fill_intensity  = _last_lighting.get("fill_intensity", 0.4),
        ambient_color   = tuple(_last_lighting.get("ambient_color", [0.2,0.2,0.25])),
        ambient_intensity = _last_lighting.get("ambient_intensity", 0.3),
        rim_color       = tuple(_last_lighting.get("rim_color", [0.6,0.7,1])),
        rim_intensity   = _last_lighting.get("rim_intensity", 0.2),
        agent_tints     = _last_lighting.get("agent_tints", {}),
        flicker_offset  = _last_lighting.get("flicker_amplitude", 0.0),
        kelvin          = _last_lighting.get("kelvin_normalized", 0.5) * 7000 + 2000,
        contrast        = _last_lighting.get("contrast", 0.5),
        zone_type       = _last_lighting.get("zone_type", "neutral")
    )
    return ls.to_x3d_fragment(), 200, {"Content-Type": "application/xml"}


@ambient_bp.route('/ambient/state', methods=['GET'])
def ambient_state():
    """Combined music + lighting + field state."""
    field = _get_field()
    return jsonify({
        "field": {
            "matrix":      field.field_matrix(),
            "echo_risks":  field.echo_chamber_risk(),
            "agent_count": len(field.agents)
        },
        "lighting": _last_lighting or {},
        "music":    _last_music    or {},
        "timestamp": time.time()
    })


# ---------------------------------------------------------------------------
# Theme Workshop: save a MIDI file (and its recipe) into the scene media folder
# ---------------------------------------------------------------------------
# The Workshop page can download a file, or - when this server is reachable - save it straight into
#   <static folder>/x3d/X3DAssets/media/music/   (recipes: .../music/recipes/)
# where the Scene Composer's MIDI tab and the Loader find it.  Deliberately narrow, because it writes to disk:
#   - plain names only (letters, digits, . _ -), ending in .mid / .recipe.json: no paths, no spaces
#   - the bytes must really be a Standard MIDI File (header check), and at most MAX_MIDI_BYTES
#   - an existing file is NEVER replaced unless the request says overwrite=1 (the page asks the user first)
#   - the write is atomic (temp file, then rename), so a failed save cannot leave half a file
#   - only requests from this machine are accepted, unless MCCF_ALLOW_REMOTE_SAVE=1 is set in the environment
MIDI_SUBPATH = ("x3d", "X3DAssets", "media", "music")
MAX_MIDI_BYTES = 5 * 1024 * 1024
MAX_RECIPE_BYTES = 1024 * 1024
_SAFE_MID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,78}\.mid$")
_SAFE_RECIPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,90}\.recipe\.json$")


def _err(message, status, **extra):
    out = {"ok": False, "error": message}
    out.update(extra)
    return jsonify(out), status


def _save_guard():
    """None if the request may write files, else an error response."""
    if os.environ.get("MCCF_ALLOW_REMOTE_SAVE") != "1" and request.remote_addr not in ("127.0.0.1", "::1"):
        return _err("saving is only allowed from this machine (set MCCF_ALLOW_REMOTE_SAVE=1 to allow others)", 403)
    if not current_app.static_folder:
        return _err("this server has no static folder to save into", 500)
    return None


def _media_dir(*extra):
    return os.path.join(os.path.realpath(os.path.join(current_app.static_folder, *MIDI_SUBPATH)), *extra)


def _write_atomic(directory, name, data, overwrite):
    """Write data to directory/name.  -> 'created' | 'overwritten' | 'exists' (nothing written)."""
    os.makedirs(directory, exist_ok=True)
    real_dir = os.path.realpath(directory)
    target = os.path.realpath(os.path.join(real_dir, name))
    if os.path.dirname(target) != real_dir:
        raise ValueError("bad file name")
    existed = os.path.exists(target)
    if existed and not overwrite:
        return "exists"
    fd, tmp = tempfile.mkstemp(dir=real_dir, prefix=".tmp_", suffix=".part")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return "overwritten" if existed else "created"


def _looks_like_midi(data):
    # "MThd", header length 6, format 0-2, at least one track, a division
    return len(data) >= 14 and data[:4] == b"MThd" and data[4:8] == b"\x00\x00\x00\x06" and data[9] <= 2 and (data[10] << 8 | data[11]) >= 1


@ambient_bp.route("/ambient/save_midi", methods=["POST"])
def save_midi():
    """POST raw .mid bytes.  Query: name=<file>.mid  overwrite=1 (optional)."""
    denied = _save_guard()
    if denied:
        return denied
    name = request.args.get("name") or ""
    if not _SAFE_MID.match(name):
        return _err("the file name must be letters, digits, '.', '_' or '-', start with a letter or digit, and end in .mid", 400)
    if request.content_length is not None and request.content_length > MAX_MIDI_BYTES:
        return _err("that file is too large (limit %d bytes)" % MAX_MIDI_BYTES, 413)
    data = request.get_data(cache=False)
    if len(data) > MAX_MIDI_BYTES:
        return _err("that file is too large (limit %d bytes)" % MAX_MIDI_BYTES, 413)
    if not _looks_like_midi(data):
        return _err("that is not a Standard MIDI File", 400)
    try:
        result = _write_atomic(_media_dir(), name, data, request.args.get("overwrite") == "1")
    except (OSError, ValueError) as e:
        return _err("could not save: %s" % e, 500)
    if result == "exists":
        return _err("%s already exists" % name, 409, name=name, exists=True)
    return jsonify({"ok": True, "name": name, "url": "X3DAssets/media/music/" + name, "bytes": len(data),
                    "overwritten": result == "overwritten"}), (200 if result == "overwritten" else 201)


@ambient_bp.route("/ambient/save_recipe", methods=["POST"])
def save_recipe():
    """POST a recipe as JSON.  Query: name=<file>.recipe.json  overwrite=1 (optional)."""
    denied = _save_guard()
    if denied:
        return denied
    name = request.args.get("name") or ""
    if not _SAFE_RECIPE.match(name):
        return _err("the recipe name must be letters, digits, '.', '_' or '-', and end in .recipe.json", 400)
    data = request.get_data(cache=False)
    if len(data) > MAX_RECIPE_BYTES:
        return _err("that recipe is too large (limit %d bytes)" % MAX_RECIPE_BYTES, 413)
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _err("that is not valid JSON", 400)
    if not isinstance(doc, dict) or not isinstance(doc.get("voices"), list) or not isinstance(doc.get("source"), dict):
        return _err("that does not look like a Theme Workshop recipe", 400)
    try:
        result = _write_atomic(_media_dir("recipes"), name, data, request.args.get("overwrite") == "1")
    except (OSError, ValueError) as e:
        return _err("could not save: %s" % e, 500)
    if result == "exists":
        return _err("%s already exists" % name, 409, name=name, exists=True)
    return jsonify({"ok": True, "name": name, "url": "X3DAssets/media/music/recipes/" + name, "bytes": len(data),
                    "overwritten": result == "overwritten"}), (200 if result == "overwritten" else 201)


@ambient_bp.route("/ambient/media_midi", methods=["GET"])
def media_midi():
    """The .mid files already in the scene media folder (so the page can warn before overwriting)."""
    folder = _media_dir() if current_app.static_folder else None
    files = []
    if folder and os.path.isdir(folder):
        for entry in sorted(os.listdir(folder)):
            full = os.path.join(folder, entry)
            if entry.lower().endswith(".mid") and os.path.isfile(full):
                st = os.stat(full)
                files.append({"name": entry, "bytes": st.st_size, "modified": int(st.st_mtime)})
    return jsonify({"ok": True, "files": files})


# ---- folder pickers: list and read the files of one content type, so an author never has to remember where they live ----------------------------
# Folders (all under the server's static folder unless noted):
#   midi     static/x3d/X3DAssets/media/music/            *.mid
#   recipe   static/x3d/X3DAssets/media/music/recipes/    *.json
#   mapping  static/x3d/X3DAssets/media/music/mappings/   *.json   (MIDI mapping files)
#   score    static/x3d/X3DAssets/media/music/scores/     *.json   (score snapshots)
#   arc      scenes/<scene>/arcs/<take>/arc_*.xml and scenes/_unscoped_arcs/*.xml   (beside this file, not under static)
_SAFE_PART = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._ -]{0,100}$")
_SAFE_JSON = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,90}\.json$")
_FILE_TYPES = {
    "midi":    {"sub": (), "ext": (".mid", ".midi")},
    "recipe":  {"sub": ("recipes",), "ext": (".json",)},
    "mapping": {"sub": ("mappings",), "ext": (".json",)},
    "score":   {"sub": ("scores",), "ext": (".json",)},
}


def _arc_root():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "scenes")


def _list_arcs():
    root = _arc_root()
    out = []
    if not os.path.isdir(root):
        return out
    for scene in sorted(os.listdir(root)):
        sdir = os.path.join(root, scene)
        if not os.path.isdir(sdir):
            continue
        if scene == "_unscoped_arcs":
            groups = [("", sdir)]
        else:
            adir = os.path.join(sdir, "arcs")
            groups = [(t, os.path.join(adir, t)) for t in sorted(os.listdir(adir))] if os.path.isdir(adir) else []
        for take, tdir in groups:
            if not os.path.isdir(tdir):
                continue
            for f in os.listdir(tdir):
                full = os.path.join(tdir, f)
                if f.lower().endswith(".xml") and os.path.isfile(full):
                    st = os.stat(full)
                    rel = "/".join(p for p in (scene, "arcs" if take else "", take, f) if p) if scene != "_unscoped_arcs" else "_unscoped_arcs/" + f
                    out.append({"name": rel, "label": f, "group": (scene + (" / " + take if take else "")) if scene != "_unscoped_arcs" else "unscoped arcs",
                                "bytes": st.st_size, "modified": int(st.st_mtime)})
    out.sort(key=lambda e: -e["modified"])
    return out


@ambient_bp.route("/ambient/files", methods=["GET"])
def ambient_files():
    """GET ?type=midi|recipe|mapping|score|arc -> {files:[{name,label,group,bytes,modified}], folder}."""
    t = request.args.get("type", "")
    if t == "arc":
        return jsonify({"ok": True, "type": t, "folder": "scenes/<scene>/arcs/<take>", "files": _list_arcs()})
    spec = _FILE_TYPES.get(t)
    if not spec or not current_app.static_folder:
        return _err("unknown file type", 400)
    folder = _media_dir(*spec["sub"])
    files = []
    if os.path.isdir(folder):
        for entry in os.listdir(folder):
            full = os.path.join(folder, entry)
            if os.path.isfile(full) and entry.lower().endswith(spec["ext"]) and not entry.startswith("."):
                st = os.stat(full)
                files.append({"name": entry, "label": entry, "group": "", "bytes": st.st_size, "modified": int(st.st_mtime)})
    files.sort(key=lambda e: -e["modified"])
    return jsonify({"ok": True, "type": t, "folder": "x3d/X3DAssets/media/music" + ("/" + "/".join(spec["sub"]) if spec["sub"] else ""), "files": files})


@ambient_bp.route("/ambient/file", methods=["GET"])
def ambient_file():
    """GET ?type=...&name=... -> the file's bytes. Names are checked part by part; nothing outside the type's folder is served."""
    t, name = request.args.get("type", ""), request.args.get("name", "")
    if t == "arc":
        root, ext = _arc_root(), (".xml",)
        parts = name.split("/")
        if not 1 <= len(parts) <= 4 or not all(_SAFE_PART.match(p) and p not in (".", "..") for p in parts):
            return _err("bad file name", 400)
    else:
        spec = _FILE_TYPES.get(t)
        if not spec or not current_app.static_folder:
            return _err("unknown file type", 400)
        root, ext = _media_dir(*spec["sub"]), spec["ext"]
        parts = [name]
        if not _SAFE_PART.match(name) or "/" in name or "\\" in name:
            return _err("bad file name", 400)
    if not name.lower().endswith(ext):
        return _err("wrong kind of file", 400)
    real_root = os.path.realpath(root)
    target = os.path.realpath(os.path.join(real_root, *parts))
    if not target.startswith(real_root + os.sep) or not os.path.isfile(target):
        return _err("no such file", 404)
    with open(target, "rb") as fh:
        data = fh.read(8 * 1024 * 1024 + 1)
    if len(data) > 8 * 1024 * 1024:
        return _err("that file is too large to open here", 413)
    mime = "application/json" if target.endswith(".json") else ("text/xml" if target.endswith(".xml") else "application/octet-stream")
    return current_app.response_class(data, mimetype=mime)


@ambient_bp.route("/ambient/save_file", methods=["POST"])
def save_file():
    """POST JSON. Query: type=mapping|score  name=<file>.json  overwrite=1 (optional). Same rules as save_recipe."""
    denied = _save_guard()
    if denied:
        return denied
    t, name = request.args.get("type", ""), request.args.get("name") or ""
    if t not in ("mapping", "score"):
        return _err("type must be mapping or score", 400)
    if not _SAFE_JSON.match(name):
        return _err("the name must be letters, digits, '.', '_' or '-', and end in .json", 400)
    data = request.get_data(cache=False)
    if len(data) > MAX_RECIPE_BYTES:
        return _err("that file is too large (limit %d bytes)" % MAX_RECIPE_BYTES, 413)
    try:
        doc = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _err("that is not valid JSON", 400)
    if not isinstance(doc, dict):
        return _err("that does not look like a %s file" % t, 400)
    try:
        result = _write_atomic(_media_dir(*_FILE_TYPES[t]["sub"]), name, data, request.args.get("overwrite") == "1")
    except (OSError, ValueError) as e:
        return _err("could not save: %s" % e, 500)
    if result == "exists":
        return _err("%s already exists" % name, 409, name=name, exists=True)
    return jsonify({"ok": True, "name": name, "bytes": len(data), "overwritten": result == "overwritten"}), (200 if result == "overwritten" else 201)


# ---- emotional arc -> MIDI state (what the Ambient page is using; read by the dashboard) -------------------------------------------------------
_ARC_STATE = {"state": None, "updated": None}
_ARC_CURVES = ("E", "B", "P", "S", "Coherence")
_MAX_ARC_BYTES = 256 * 1024


def _num(v, lo=None, hi=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        return None
    if lo is not None and v < lo:
        return None
    if hi is not None and v > hi:
        return None
    return v


def _txt(v, n=200):
    return v[:n] if isinstance(v, str) else ""


def clean_arc_state(body):
    """Rebuild a posted arc summary from known fields only. Returns (state, None) or (None, reason)."""
    if not isinstance(body, dict):
        return None, "the body must be a JSON object"
    arc = body.get("arc")
    if not isinstance(arc, dict):
        return None, "missing 'arc'"
    stats_in, curves_in, spec_in = body.get("stats"), body.get("curves"), body.get("spec")
    if not isinstance(stats_in, list) or len(stats_in) > 8:
        return None, "'stats' must be a list of at most 8"
    if not isinstance(curves_in, dict) or len(curves_in) > 8:
        return None, "'curves' must be an object of at most 8 curves"
    if not isinstance(spec_in, dict) or not isinstance(spec_in.get("lanes"), list) or len(spec_in["lanes"]) > 16:
        return None, "'spec.lanes' must be a list of at most 16"
    stats = []
    for s in stats_in:
        if not isinstance(s, dict) or s.get("curve") not in _ARC_CURVES:
            return None, "a stat has an unknown curve"
        stats.append({"curve": s["curve"], **{k: _num(s.get(k)) for k in ("min", "max", "mean", "sd", "range", "first", "last")},
                      "distinct": _num(s.get("distinct"), 0, 100000), "n": _num(s.get("n"), 0, 100000)})
    curves = {}
    for k, v in curves_in.items():
        if k not in _ARC_CURVES or not isinstance(v, list) or len(v) > 200:
            return None, "curve %r is not an allowed name with at most 200 values" % (k,)
        pts = [_num(x, 0, 1) for x in v]
        if any(p is None for p in pts):
            return None, "curve %r has a value outside 0..1" % (k,)
        curves[k] = pts
    lanes = []
    for l in spec_in["lanes"]:
        if not isinstance(l, dict) or l.get("curve") not in _ARC_CURVES:
            return None, "a lane has an unknown curve"
        cc, lo, hi = _num(l.get("cc"), 0, 127), _num(l.get("lo"), 0, 127), _num(l.get("hi"), 0, 127)
        if cc is None or lo is None or hi is None:
            return None, "a lane needs cc, lo and hi between 0 and 127"
        lanes.append({"curve": l["curve"], "cc": int(cc), "lo": int(lo), "hi": int(hi), "on": bool(l.get("on", True))})
    built = []
    for l in body.get("lanes") or []:
        if isinstance(l, dict) and l.get("curve") in _ARC_CURVES and _num(l.get("cc"), 0, 127) is not None:
            built.append({"curve": l["curve"], "cc": int(l["cc"]), "events": int(_num(l.get("events"), 0, 10 ** 7) or 0), "tracks": int(_num(l.get("tracks"), 0, 1000) or 0)})
    state = {
        "arc": {"id": _txt(arc.get("id")), "scene": _txt(arc.get("scene")), "title": _txt(arc.get("title")), "agent": _txt(arc.get("agent")),
                "waypoints": int(_num(arc.get("waypoints"), 0, 100000) or 0), "words": int(_num(arc.get("words"), 0, 10 ** 7) or 0),
                "modes": [_txt(m, 40) for m in (arc.get("modes") or [])[:20] if isinstance(m, str)],
                "hasValence": bool(arc.get("hasValence")), "hasUncertainty": bool(arc.get("hasUncertainty")), "hasReward": bool(arc.get("hasReward"))},
        "stats": stats, "curves": curves,
        "spec": {"enabled": bool(spec_in.get("enabled", True)), "interp": "step" if spec_in.get("interp") == "step" else "linear", "span": "whole", "lanes": lanes},
        "lanes": built, "file": _txt(body.get("file"), 120), "sha256": _txt(body.get("sha256"), 64), "source": _txt(body.get("source"), 120), "recipe": _txt(body.get("recipe"), 16),
        "warnings": [_txt(w, 300) for w in (body.get("warnings") or [])[:10] if isinstance(w, str)],
    }
    return state, None


@ambient_bp.route("/ambient/arc/state", methods=["GET", "POST"])
def arc_state():
    """POST (this machine only): the Ambient page's current arc mapping, or {"clear": true}. GET: what was last posted."""
    if request.method == "GET":
        s = _ARC_STATE["state"]
        return jsonify({"ok": True, "loaded": s is not None, "updated": _ARC_STATE["updated"], "state": s})
    if os.environ.get("MCCF_ALLOW_REMOTE_SAVE") != "1" and request.remote_addr not in ("127.0.0.1", "::1"):
        return _err("only this machine may set the arc state (set MCCF_ALLOW_REMOTE_SAVE=1 to allow others)", 403)
    if (request.content_length or 0) > _MAX_ARC_BYTES:
        return _err("too large (limit %d bytes)" % _MAX_ARC_BYTES, 413)
    raw = request.get_data(cache=False)
    if len(raw) > _MAX_ARC_BYTES:
        return _err("too large (limit %d bytes)" % _MAX_ARC_BYTES, 413)
    try:
        body = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return _err("the body is not JSON", 400)
    if isinstance(body, dict) and body.get("clear") is True:
        _ARC_STATE["state"], _ARC_STATE["updated"] = None, None
        return jsonify({"ok": True, "loaded": False})
    state, why = clean_arc_state(body)
    if why:
        return _err(why, 400)
    _ARC_STATE["state"], _ARC_STATE["updated"] = state, time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())
    return jsonify({"ok": True, "loaded": True, "updated": _ARC_STATE["updated"]})
