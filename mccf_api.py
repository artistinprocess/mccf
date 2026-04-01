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

app = Flask(__name__)
CORS(app)  # X3D pages need cross-origin access

# ---------------------------------------------------------------------------
# Global engine state
# ---------------------------------------------------------------------------

field = CoherenceField()
librarian = Librarian(field)
gardener = Gardener(field)
cultivars: dict = {}   # name → agent config snapshot

# ---------------------------------------------------------------------------
# Register voice blueprint
# ---------------------------------------------------------------------------

from mccf_voice_api import voice_bp
from mccf_zone_api import zone_bp
from mccf_zones import SceneGraph
scene = SceneGraph()
voice_bp.field = field
voice_bp.scene = scene
zone_bp.field  = field
zone_bp.scene  = scene
app.register_blueprint(voice_bp)
app.register_blueprint(zone_bp)

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


if __name__ == "__main__":
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
    print("Endpoints: /sensor /field /agent /cultivar /zone /waypoint /scene /voice /export/x3d")
    app.run(debug=True, port=5000)
