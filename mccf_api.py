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
    """
    Primary endpoint: X3D fires this on sensor events.

    Body:
    {
        "from_agent": "Alice",
        "to_agent":   "AI",
        "sensor_data": {
            "distance":    2.3,
            "dwell":       12.0,
            "velocity":    0.4,
            "gaze_angle":  15.0,
            "max_range":   10.0
        },
        "mutual": true
    }

    Returns affect parameters for the from_agent.
    """
    data = request.get_json()
    from_name = data.get("from_agent")
    to_name   = data.get("to_agent")
    mutual    = data.get("mutual", True)

    # Auto-register agents if not known
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
        "entanglement":        field.entanglement_negativity(),    # v1.6.0
        "alignment_coherence": field.alignment_coherence(),        # v1.6.0
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

    # v2.1: UPDATE existing agent rather than replacing it.
    # Replacing would wipe all interaction history (_known_agents).
    if name in field.agents:
        existing = field.agents[name]
        if weights:
            # Normalize weights
            total = sum(weights.values())
            if total > 0:
                weights = {k: v/total for k, v in weights.items()}
            existing.weights = weights
        if role:
            existing.role = role
        existing.set_regulation(reg)
        return jsonify({"status": "updated", "agent": existing.summary()})

    # New agent
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
    """Save current agent config as a named cultivar template."""
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


@app.route("/cultivar/<name>/spawn", methods=["POST"])
def spawn_from_cultivar(name):
    """Create a new agent initialized from a cultivar template."""
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

# v2.1 — Register Neo-Riemannian blueprint
from mccf_neoriemannian import make_neoriemannian_api, NeoRiemannianTransformer

# v2.1 — Register Energy Field blueprint
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
    """
    Return current EmotionalField state as JSON.
    This is the CoherenceField projected through the HotHouse
    Affective Hamiltonian — richer than raw channel values.
    """
    ef, adapter = get_emotional_field()
    if ef is None:
        return jsonify({"error": "No agents registered yet"}), 404
    try:
        ef.step()  # advance one timestep
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
    """
    Return X3D parameter dict for current field state.
    Used by the X3D loader to update avatar blend weights.
    """
    ef, adapter = get_emotional_field()
    if ef is None:
        return jsonify({}), 200
    try:
        return jsonify(adapter.generate_x3d_state())
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/hothouse/humanml", methods=["GET"])
def hothouse_humanml():
    """
    Return HumanML XML fragment for current field state.
    """
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
    """Full system state export."""
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
    """Export agent configs as Python setup code."""
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
    Save arc export data to exports/ directory.
    Called by constitutional arc HTML after arc completion.
    Body: { cultivar, timestamp, rows: [{step, waypoint, E, B, P, S,
            mode, coherence, uncertainty, valence, reward}] }
    Returns: { status, filename, path }
    """
    import os, csv, io
    data      = request.json or {}
    cultivar  = data.get("cultivar", "unknown").replace(" ", "_")
    timestamp = data.get("timestamp", "").replace(" ", "_").replace(":", "-")
    rows      = data.get("rows", [])

    if not rows:
        return jsonify({"status": "error", "message": "no rows"}), 400

    # Ensure exports directory exists
    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    os.makedirs(exports_dir, exist_ok=True)

    filename = f"arc_{cultivar}_{timestamp}.tsv"
    filepath = os.path.join(exports_dir, filename)

    # Write TSV
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter="	")
        writer.writerow(["MCCF Constitutional Arc Export"])
        writer.writerow([f"Cultivar: {data.get('cultivar', 'unknown')}"])
        writer.writerow([f"Timestamp: {data.get('timestamp', '')}"])
        writer.writerow([])
        writer.writerow(["Step", "Waypoint", "E", "B", "P", "S",
                         "Mode", "Coherence", "Uncertainty", "Valence", "Reward"])
        for row in rows:
            writer.writerow([
                row.get("step", ""),
                row.get("waypoint", ""),
                row.get("E", ""), row.get("B", ""),
                row.get("P", ""), row.get("S", ""),
                row.get("mode", ""), row.get("coherence", ""),
                row.get("uncertainty", ""), row.get("valence", ""),
                row.get("reward", "")
            ])

    return jsonify({"status": "saved", "filename": filename,
                    "path": filepath, "rows": len(rows)})


@app.route("/exports", methods=["GET"])
def list_exports():
    """List saved arc export files."""
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
    """Delete a saved arc export file."""
    import os
    exports_dir = os.path.join(os.path.dirname(__file__), "exports")
    filepath = os.path.join(exports_dir, filename)
    if not os.path.exists(filepath):
        return jsonify({"status": "not_found"}), 404
    os.remove(filepath)
    return jsonify({"status": "deleted", "filename": filename})


@app.route("/export/x3d", methods=["GET"])
def export_x3d():
    """
    Export X3D scene fragment: ProximitySensors, Script node,
    and ROUTE statements connecting sensors → MCCF API → transforms.
    Uses X_ITE SAI (Scene Access Interface) external API pattern.
    """
    agents = list(field.agents.keys())
    api_url = request.args.get("api_url", "http://localhost:5000")

    lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    lines.append('<!DOCTYPE X3D PUBLIC "ISO//Web3D//DTD X3D 4.0//EN"')
    lines.append('  "https://www.web3d.org/specifications/x3d-4.0.dtd">')
    lines.append('<X3D profile="Immersive" version="4.0">')
    lines.append('  <Scene>')
    lines.append('')
    lines.append('  <!-- MCCF Affective Bridge Script -->')
    lines.append('  <!-- Receives sensor events, calls MCCF API, routes params to avatars -->')
    lines.append('')
    lines.append('  <Script DEF="MCCF_Bridge" directOutput="true" mustEvaluate="true">')
    lines.append(f'    <field accessType="initializeOnly" type="SFString" name="api_url" value="{api_url}"/>')

    for agent in agents:
        safe = agent.replace(" ", "_")
        lines.append(f'    <field accessType="inputOnly" type="SFVec3f" name="pos_{safe}"/>')
        lines.append(f'    <field accessType="inputOnly" type="SFRotation" name="rot_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="arousal_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="valence_{safe}"/>')
        lines.append(f'    <field accessType="outputOnly" type="SFFloat" name="engagement_{safe}"/>')

    lines.append('    <![CDATA[')
    lines.append('      ecmascript:')
    lines.append('')
    lines.append('      var api_url = "";')
    lines.append('      var agent_positions = {};')
    lines.append('      var agent_dwell = {};')
    lines.append('      var last_time = {};')
    lines.append('')
    lines.append('      function initialize() {')
    lines.append('        api_url = fields.api_url;')
    lines.append('      }')
    lines.append('')

    for agent in agents:
        safe = agent.replace(" ", "_")
        lines.append(f'      function pos_{safe}(val, time) {{')
        lines.append(f'        agent_positions["{agent}"] = val;')
        lines.append(f'        _updateCoherence("{agent}", val, time);')
        lines.append(f'      }}')
        lines.append('')

    lines.append('      function _updateCoherence(from_agent, pos, ts) {')
    lines.append('        var agents = ' + json.dumps(agents) + ';')
    lines.append('        for (var i = 0; i < agents.length; i++) {')
    lines.append('          var to_agent = agents[i];')
    lines.append('          if (to_agent === from_agent) continue;')
    lines.append('          var other_pos = agent_positions[to_agent];')
    lines.append('          if (!other_pos) continue;')
    lines.append('')
    lines.append('          var dx = pos.x - other_pos.x;')
    lines.append('          var dz = pos.z - other_pos.z;')
    lines.append('          var distance = Math.sqrt(dx*dx + dz*dz);')
    lines.append('')
    lines.append('          var key = from_agent + "_" + to_agent;')
    lines.append('          if (!agent_dwell[key]) agent_dwell[key] = 0;')
    lines.append('          if (!last_time[key]) last_time[key] = ts;')
    lines.append('          if (distance < 3.0) {')
    lines.append('            agent_dwell[key] += (ts - last_time[key]);')
    lines.append('          } else {')
    lines.append('            agent_dwell[key] = Math.max(0, agent_dwell[key] - 1);')
    lines.append('          }')
    lines.append('          last_time[key] = ts;')
    lines.append('')
    lines.append('          var body = JSON.stringify({')
    lines.append('            from_agent: from_agent,')
    lines.append('            to_agent: to_agent,')
    lines.append('            sensor_data: {')
    lines.append('              distance: distance,')
    lines.append('              dwell: agent_dwell[key],')
    lines.append('              velocity: 0.0,')
    lines.append('              gaze_angle: 45.0,')
    lines.append('              max_range: 10.0')
    lines.append('            }')
    lines.append('          });')
    lines.append('')
    lines.append('          _postToMCCF(from_agent, body);')
    lines.append('        }')
    lines.append('      }')
    lines.append('')
    lines.append('      function _postToMCCF(agent_name, body) {')
    lines.append('        var xhr = new XMLHttpRequest();')
    lines.append('        xhr.open("POST", api_url + "/sensor", true);')
    lines.append('        xhr.setRequestHeader("Content-Type", "application/json");')
    lines.append('        xhr.onreadystatechange = function() {')
    lines.append('          if (xhr.readyState === 4 && xhr.status === 200) {')
    lines.append('            var r = JSON.parse(xhr.responseText);')
    lines.append('            _applyAffect(agent_name, r);')
    lines.append('          }')
    lines.append('        };')
    lines.append('        xhr.send(body);')
    lines.append('      }')
    lines.append('')
    lines.append('      function _applyAffect(agent_name, params) {')
    for agent in agents:
        safe = agent.replace(" ", "_")
        lines.append(f'        if (agent_name === "{agent}") {{')
        lines.append(f'          arousal_{safe} = params.arousal;')
        lines.append(f'          valence_{safe} = params.valence;')
        lines.append(f'          engagement_{safe} = params.engagement;')
        lines.append(f'        }}')
    lines.append('      }')
    lines.append('    ]]>')
    lines.append('  </Script>')
    lines.append('')

    # Avatar transform stubs + ROUTE statements
    for agent in agents:
        safe = agent.replace(" ", "_")
        lines.append(f'  <!-- Avatar: {agent} -->')
        lines.append(f'  <Transform DEF="Avatar_{safe}">')
        lines.append(f'    <Shape><Appearance><Material DEF="Mat_{safe}"/></Appearance>')
        lines.append(f'      <Sphere radius="0.5"/></Shape>')
        lines.append(f'  </Transform>')
        lines.append(f'  <ProximitySensor DEF="Prox_{safe}" size="20 20 20"/>')
        lines.append(f'  <ROUTE fromNode="Avatar_{safe}" fromField="translation"')
        lines.append(f'         toNode="MCCF_Bridge" toField="pos_{safe}"/>')
        lines.append(f'  <!-- Affect outputs routed to animation/material nodes -->')
        lines.append(f'  <!-- ROUTE fromNode="MCCF_Bridge" fromField="arousal_{safe}"')
        lines.append(f'         toNode="AnimBlend_{safe}" toField="weight"/> -->')
        lines.append('')

    lines.append('  </Scene>')
    lines.append('</X3D>')

    return "\n".join(lines), 200, {"Content-Type": "application/xml"}


def classify_arc_genre(arc_rows: list) -> dict:
    """
    Classify constitutional arc trajectory as comedy, drama, or tragedy.
    
    Based on three observable metrics from the arc export:
    1. Coherence profile shape (recovery vs monotonic vs oscillating)
    2. W5 barrier crossing magnitude (coherence drop W4→W5)
    3. W6-W7 recovery delta (coherence change from W5 minimum to W7)
    
    Genre definitions (from April 2026 theoretical session):
    - Comedy:  misalignment + low-cost resolution
    - Drama:   misalignment + delayed resolution  
    - Tragedy: misalignment + irreversible divergence
    
    Returns dict with genre, confidence, and diagnostic metrics.
    """
    if not arc_rows or len(arc_rows) < 3:
        return {"genre": "unknown", "confidence": 0.0, "reason": "insufficient data"}

    # Extract coherence values by step
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

    # W5 barrier crossing — use total drop from W1 to minimum
    # (single-step drop misses gradual decline; total drop is more meaningful)
    min_coh   = min(coh_vals)
    max_drop  = coh_vals[0] - min_coh
    drop_step = steps[coh_vals.index(min_coh)]
    
    # Also track largest single-step for oscillation detection
    max_single_drop = 0.0
    for i in range(1, n):
        drop = coh_vals[i-1] - coh_vals[i]
        if drop > max_single_drop:
            max_single_drop = drop

    # W5 minimum and W6-W7 recovery — use actual step numbers not index
    # Find the minimum coherence point (the pressure peak)
    min_idx   = coh_vals.index(min(coh_vals))
    w5_coh    = coh_vals[min_idx]   # actual minimum, not necessarily step 5
    w7_coh    = coh_vals[-1]        # last step
    w1_coh    = coh_vals[0]         # first step
    recovery  = w7_coh - w5_coh     # negative = continued decline, positive = recovery

    # E-channel recovery at W6-W7 (if available)
    e_vals = {}
    for row in arc_rows:
        step = row.get("step", 0)
        e    = row.get("E", row.get("cv", {}).get("E", None))
        if step and e is not None:
            e_vals[int(step)] = float(e)

    e_recovery = 0.0
    if e_vals and len(e_vals) >= 3:
        e_steps  = sorted(e_vals.keys())
        # E recovery: compare peak E in second half to peak E in first half
        mid = len(e_steps) // 2
        first_half_max = max(e_vals[s] for s in e_steps[:mid+1])
        second_half_max = max(e_vals[s] for s in e_steps[mid:])
        e_recovery = second_half_max - first_half_max

    # Classification rules
    # Tragedy: large W5 crossing + no recovery
    if max_drop > 0.40 and recovery < 0.0:
        genre = "tragedy"
        confidence = min(1.0, max_drop / 0.5 + abs(recovery) * 2)
        reason = f"large barrier crossing (Δ{max_drop:.3f}) with continued decline"

    # Comedy: moderate crossing + positive recovery
    elif max_drop <= 0.20 and recovery > 0.05:
        genre = "comedy"
        confidence = min(1.0, recovery * 10 + (0.20 - max_drop) * 5)
        reason = f"low-cost crossing (Δ{max_drop:.3f}) with recovery (+{recovery:.3f})"

    # Drama: significant crossing + E-channel recovery signal
    elif max_drop > 0.20 and (recovery > -0.05 or e_recovery > 0.02):
        genre = "drama"
        confidence = min(1.0, max_drop / 0.4 * 0.7 + max(0, e_recovery) * 5)
        reason = f"sustained tension (Δ{max_drop:.3f}), E-recovery={e_recovery:+.3f}"

    # Default tragedy if large crossing with any negative movement
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
    """
    Formal pressure function for constitutional arc (V2.2).
    Replaces hardcoded STEP_PRESSURE array.

    Uses a beta-distribution-shaped schedule (Grok review, April 2026):
    peaks near normalized progress 0.65 (≈ W5 The Edge).

    Parameters α=3.5, β=2.0 give a right-skewed curve that:
    - Starts low (W1 Comfort)
    - Rises through W2-W4
    - Peaks at W5 (0.75)
    - Eases at W6-W7

    Falls back to the original hand-tuned array for backward compatibility
    if math.lgamma is not available.
    """
    import math

    # Original hand-tuned profile — preserved as fallback and reference
    STEP_PRESSURE = [0.05, 0.15, 0.25, 0.45, 0.75, 0.40, 0.15]
    if total_steps == 7:
        return STEP_PRESSURE[min(step - 1, 6)]

    # For non-standard arc lengths: beta distribution shape
    try:
        p = (step - 1) / max(1, total_steps - 1)  # normalize to [0,1]
        alpha, beta_param = 3.5, 2.0
        # Unnormalized beta PDF value (we just need the shape)
        if p <= 0.0: return 0.05
        if p >= 1.0: return 0.10
        log_val = (alpha - 1) * math.log(p) + (beta_param - 1) * math.log(1 - p)
        raw = math.exp(log_val)
        # Scale to [0.05, 0.80] range
        return round(0.05 + 0.75 * min(1.0, raw / 0.35), 4)
    except Exception:
        return STEP_PRESSURE[min(step - 1, 6)]


@app.route("/arc/record", methods=["POST"])
def arc_record():
    """
    Record a constitutional arc step to the coherence field.
    Called by the constitutional navigator after each waypoint response.
    Returns updated meta_state for the cultivar.

    Body:
    {
        "cultivar":    "The Steward",
        "step":        1,            # 1-7
        "waypoint":    "W1",
        "response":    "LLM response text",
        "sentiment":   0.2           # optional, computed if omitted
    }
    """
    import random, re as _re
    data     = request.get_json()
    cultivar = data.get("cultivar")
    step     = int(data.get("step", 1))
    response = data.get("response", "")

    if not cultivar:
        return jsonify({"error": "cultivar required"}), 400

    # Ensure agent exists
    if cultivar not in field.agents:
        field.register(Agent(cultivar))

    agent = field.agents[cultivar]

    # Estimate sentiment using semantic decomposition (V2.2)
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

    # Build channel vector with step-based variation + semantic decomposition
    # Pressure profile uses formal function (Grok V2.2 recommendation)
    pressure = arc_pressure(step, total_steps=7)

    w = agent.weights
    # Reproducible arc runs: optional seed parameter locks Gaussian noise.
    # Uses local Random instance — thread-safe, no global state mutation.
    # No seed = existing behavior unchanged.
    seed = data.get("seed", None)
    rng  = random.Random(seed) if seed is not None else random
    noise = rng.gauss(0, 0.03)
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

    # Interact with all other agents (mutual=False — arc is one-directional)
    others = [n for n in field.agents if n != cultivar]
    if others:
        field.interact(cultivar, others[0], cv, mutual=False)
    else:
        # No other agents — self-interact as fallback
        agent.observe(agent, cv)

    # Return updated meta_state
    meta = agent.meta_state
    # Classify genre from arc so far (available from step 3)
    coherence_now = round(agent.coherence_toward(others[0]) if others else 0.5, 4)

    # Store coherence per step for genre classification
    if cultivar not in _arc_coherence_history:
        _arc_coherence_history[cultivar] = []
    # Remove any existing entry for this step (re-run support)
    _arc_coherence_history[cultivar] = [
        r for r in _arc_coherence_history[cultivar] if r['step'] != step
    ]
    _arc_coherence_history[cultivar].append({
        'step': step, 'coherence': coherence_now,
        'E': e_val, 'B': b_val, 'P': p_val, 'S': s_val
    })

    # Use stored arc history for genre classification
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
    # Register default field agents so lighting/X3D/hothouse work at startup
    # without requiring the user to open the Editor first.
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

    # Seed some default cultivars
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

    print("MCCF API server starting on http://localhost:5000")
    print("Endpoints: /sensor /field /agent /cultivar /zone /waypoint /scene /voice")
    print("           /hothouse/state /hothouse/x3d /hothouse/humanml")
    print("           /collapse/run /export/x3d /export/python /export/json")
    app.run(debug=True, port=5000)
