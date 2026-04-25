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
# Explicit X3D MIME type route
# Flask's static file handler ignores mimetypes.add_type() — this route
# intercepts mccf_scene.x3d and serves it with the correct MIME type so
# X_ITE receives model/x3d+xml instead of application/octet-stream.
# v3.2 — added April 2026
# ---------------------------------------------------------------------------
@app.route('/static/mccf_scene.x3d')
def serve_x3d_scene():
    from flask import send_from_directory
    static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
    return send_from_directory(static_dir, 'mccf_scene.x3d',
                               mimetype='model/x3d+xml')

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
    return jsonify({
        "matrix":              matrix,
        "echo_chamber_risks":  echo,
        "entanglement":        field.entanglement_negativity(),
        "alignment_coherence": field.alignment_coherence(),
        "agents":              agents_summary,
        "episode_count":       len(field.episode_log)
    })


@app.route("/agent", methods=["POST"])
def create_agent():
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
    return jsonify({
        "summary": agent.summary(),
        "weights": agent.weights,
        "affect_toward": params
    })


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


@app.route("/cultivars/xml", methods=["GET"])
def list_cultivars_xml():
    """
    List cultivar XML definition files from cultivars/ directory.
    Returns filenames and parsed metadata (agentname, weights, disposition).
    """
    import os
    cultivars_dir = os.path.join(os.path.dirname(__file__), "cultivars")
    if not os.path.exists(cultivars_dir):
        return jsonify({"cultivars": [], "note": "cultivars/ directory not found"})

    import xml.etree.ElementTree as ET
    results = []
    for fname in sorted(os.listdir(cultivars_dir)):
        if not fname.endswith(".xml"):
            continue
        fpath = os.path.join(cultivars_dir, fname)
        try:
            tree = ET.parse(fpath)
            root = tree.getroot()
            cultivar_el = root.find("Cultivar")
            if cultivar_el is None:
                continue
            weights_el  = cultivar_el.find("Weights")
            reg_el      = cultivar_el.find("Regulation")
            color_el    = cultivar_el.find("Color")
            weights = {}
            if weights_el is not None:
                for ch in ["E","B","P","S"]:
                    v = weights_el.get(ch)
                    if v is not None:
                        weights[ch] = float(v)
            results.append({
                "filename":    fname,
                "id":          cultivar_el.get("id",""),
                "agentname":   cultivar_el.get("agentname",""),
                "version":     cultivar_el.get("version","1.0"),
                "disposition": (cultivar_el.findtext("Disposition") or "").strip(),
                "description": (cultivar_el.findtext("Description") or "").strip(),
                "weights":     weights,
                "regulation":  float(reg_el.get("value", 0.7)) if reg_el is not None else 0.7,
                "color":       color_el.get("hex","") if color_el is not None else "",
            })
        except Exception as e:
            results.append({"filename": fname, "error": str(e)})

    return jsonify({"cultivars": results, "count": len(results)})


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
    timestamp = data.get("timestamp", "")
    rows      = data.get("rows", [])
    genre     = data.get("genre", "")
    seed      = data.get("seed", None)

    if not rows:
        return jsonify({"status": "error", "message": "no rows"}), 400

    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(exports_dir, exist_ok=True)

    cultivar_slug = cultivar.replace(" ", "_")
    ts_slug       = timestamp.replace(" ", "").replace(":", "")
    arc_id        = f"{cultivar_slug}_{ts_slug}"
    date_part     = timestamp[:10] if len(timestamp) >= 10 else timestamp
    time_part     = timestamp[11:] if len(timestamp) >= 19 else ""

    def xml_esc(s):
        return (str(s)
            .replace("&","&amp;").replace("<","&lt;")
            .replace(">","&gt;").replace('"',"&quot;")
            .replace("'","&apos;"))

    xml  = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml += f'<EmotionalArc id="{arc_id}">\n'
    xml += f'  <title>MCCF Constitutional Arc Export</title>\n'
    xml += f'  <Cultivar id="{arc_id}" agentname="{xml_esc(cultivar)}">\n'
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
        "meta_state": meta.as_dict(),
        "coherence":  coherence_now,
        "genre":      genre_result
    })

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
