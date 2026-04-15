"""
MCCF Energy Field API
======================
Implements the moral topology / energy field visualizer.

The energy field models each possible action as a point in a
three-dimensional space of (valence, salience, coherence). The
Boltzmann energy function from the collapse pipeline is extended
here to give an interactive exploration surface.

Energy function per action:
  E(a) = (1 - coherence(a)) * w_coherence
        + (1 - valence(a))  * w_valence
        + (1 - salience(a)) * w_salience

Selection probability:
  P(a) ∝ exp(-E(a) / T)

The "moral topology" of the field is the landscape of these
energies across the registered action set — where actions cluster,
which are available, which are avoided.

Endpoints:
  POST /energy/weights   — set w_valence, w_salience, w_coherence, T
  POST /energy/evaluate  — evaluate a set of candidate actions for
                           an agent in the current field state
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional
from flask import Blueprint, jsonify, request


# ---------------------------------------------------------------------------
# Energy weights (mutable via POST /energy/weights)
# ---------------------------------------------------------------------------

@dataclass
class EnergyWeights:
    w_valence:   float = 0.35   # weight of emotional alignment
    w_salience:  float = 0.30   # weight of contextual relevance
    w_coherence: float = 0.35   # weight of field coherence
    temperature: float = 0.50   # Boltzmann temperature (sharpness)

    def as_dict(self) -> dict:
        return {
            "w_valence":   round(self.w_valence,   4),
            "w_salience":  round(self.w_salience,  4),
            "w_coherence": round(self.w_coherence, 4),
            "temperature": round(self.temperature, 4),
        }


_weights = EnergyWeights()


# ---------------------------------------------------------------------------
# Action energy computation
# ---------------------------------------------------------------------------

def score_action(
    action_text: str,
    agent,
    field_state: dict,
    position: list,
    weights: EnergyWeights
) -> dict:
    """
    Estimate the energy of a candidate action for a given agent.

    Valence: how well the action aligns with the agent's emotional state.
    Salience: how contextually relevant the action is (zone/position proximity).
    Coherence: how consistent the action is with the agent's relationship history.

    These are heuristic estimates — for the full Boltzmann collapse with
    LLM scoring, use the collapse pipeline. This is for interactive topology
    exploration without LLM calls.
    """
    w = agent.weights if hasattr(agent, 'weights') else {'E':0.35,'B':0.25,'P':0.20,'S':0.20}

    # Valence: E-channel weight × regulation proxy
    # High E-weight agents prefer emotionally resonant actions
    reg = getattr(agent, '_affect_regulation', 1.0)
    valence = round(w.get('E', 0.35) * reg + random.gauss(0, 0.05), 4)
    valence = max(0.0, min(1.0, valence))

    # Salience: P-channel (predictive) × action text length proxy
    # Longer/more specific actions score higher salience for analytical agents
    words = len(action_text.split())
    salience_base = w.get('P', 0.20) + min(0.3, words / 30.0)
    salience = round(max(0.0, min(1.0, salience_base + random.gauss(0, 0.04))), 4)

    # Coherence: from field matrix — average coherence toward known agents
    matrix = field_state.get('matrix', {})
    agent_name = agent.name if hasattr(agent, 'name') else 'unknown'
    row = matrix.get(agent_name, {})
    scores = [v for k, v in row.items() if k != agent_name and v > 0]
    if scores:
        coherence = round(sum(scores) / len(scores) + random.gauss(0, 0.03), 4)
    else:
        coherence = round(w.get('B', 0.25) + random.gauss(0, 0.05), 4)
    coherence = max(0.0, min(1.0, coherence))

    # Zone proximity bonus — actions near zone centers get salience boost
    # position is [x, 0, z]; zones along z axis at 5,10,15,20,25,30,35
    zone_z_positions = [5, 10, 15, 20, 25, 30, 35]
    z_pos = position[2] if len(position) > 2 else 0
    min_zone_dist = min(abs(z_pos - z) for z in zone_z_positions)
    zone_bonus = max(0.0, 0.1 - min_zone_dist * 0.005)
    salience = min(1.0, salience + zone_bonus)

    # Energy function
    E = (
        (1.0 - coherence) * weights.w_coherence +
        (1.0 - valence)   * weights.w_valence   +
        (1.0 - salience)  * weights.w_salience
    )
    E = round(max(0.0, min(1.0, E)), 4)

    return {
        "action":    action_text,
        "valence":   valence,
        "salience":  salience,
        "coherence": coherence,
        "E_total":   E,
    }


def boltzmann_rank(scored: list, temperature: float) -> list:
    """
    Apply Boltzmann distribution over scored actions.
    Returns scored list with selection_probability added, sorted by probability.
    """
    T = max(0.05, temperature)
    raw = [math.exp(-s['E_total'] / T) for s in scored]
    total = sum(raw) or 1.0
    for s, p in zip(scored, raw):
        s['selection_probability'] = round(p / total, 4)
    return sorted(scored, key=lambda x: x['selection_probability'], reverse=True)


def compute_field_summary(ranked: list, temperature: float) -> dict:
    """
    Compute summary statistics for the evaluated action set.
    Characterizes the topology of the energy landscape.
    """
    if not ranked:
        return {"topology": "empty", "dominant_action": "—", "avoided_action": "—",
                "energy_spread": 0.0, "temperature": temperature}

    energies = [r['E_total'] for r in ranked]
    spread   = round(max(energies) - min(energies), 4)

    dominant = ranked[0]['action']
    avoided  = ranked[-1]['action']

    # Topology classification
    if spread < 0.05:
        topology = "flat"         # all actions roughly equivalent
    elif spread < 0.15:
        topology = "gradual"      # smooth gradient
    elif spread < 0.30:
        topology = "structured"   # clear differentiation
    elif ranked[0]['selection_probability'] > 0.6:
        topology = "sharp"        # one action strongly dominant
    else:
        topology = "complex"      # multiple competing attractors

    return {
        "dominant_action": dominant,
        "avoided_action":  avoided,
        "energy_spread":   spread,
        "topology":        topology,
        "temperature":     round(temperature, 3),
    }


def compute_calibration(agent) -> dict:
    """
    Estimate the reliability of energy predictions for this agent
    based on their CoherenceRecord history depth.
    """
    records = getattr(agent, '_known_agents', {})
    total_episodes = sum(
        len(list(getattr(r, 'history', [])))
        for r in records.values()
    )
    if total_episodes == 0:
        return {"n_episodes": 0, "reliability": "uncalibrated",
                "status": "no history", "mean_bias": None}
    elif total_episodes < 5:
        return {"n_episodes": total_episodes, "reliability": "low",
                "status": "sparse history", "mean_bias": 0.0}
    elif total_episodes < 20:
        return {"n_episodes": total_episodes, "reliability": "moderate",
                "status": "building history", "mean_bias": 0.0}
    else:
        return {"n_episodes": total_episodes, "reliability": "good",
                "status": "well calibrated", "mean_bias": 0.0}


# ---------------------------------------------------------------------------
# Flask Blueprint factory
# ---------------------------------------------------------------------------

def make_energy_api(field):
    """
    Create the energy field blueprint.
    Register in mccf_api.py with:
        from mccf_energy import make_energy_api
        energy_bp = make_energy_api(field)
        app.register_blueprint(energy_bp)
    """
    energy_bp = Blueprint('energy', __name__)

    @energy_bp.route('/energy/weights', methods=['POST'])
    def set_weights():
        """
        Update energy function weights and temperature.
        Body: { w_valence, w_salience, w_coherence, temperature }
        """
        data = request.get_json() or {}
        if 'w_valence'   in data: _weights.w_valence   = float(data['w_valence'])
        if 'w_salience'  in data: _weights.w_salience  = float(data['w_salience'])
        if 'w_coherence' in data: _weights.w_coherence = float(data['w_coherence'])
        if 'temperature' in data: _weights.temperature = float(data['temperature'])

        # Normalize coherence/valence/salience weights to sum to 1
        total = _weights.w_valence + _weights.w_salience + _weights.w_coherence
        if total > 0:
            _weights.w_valence   /= total
            _weights.w_salience  /= total
            _weights.w_coherence /= total

        return jsonify({"status": "ok", "weights": _weights.as_dict()})

    @energy_bp.route('/energy/weights', methods=['GET'])
    def get_weights():
        """Return current energy weights."""
        return jsonify(_weights.as_dict())

    @energy_bp.route('/energy/evaluate', methods=['POST'])
    def evaluate():
        """
        Evaluate a set of candidate actions for an agent.

        Body:
          agent_name: str
          actions:    list of action text strings
          position:   [x, y, z] — agent's current scene position

        Response:
          ranked_actions: list of scored+ranked action dicts
          field_summary:  topology characterization
          calibration:    reliability estimate
        """
        data       = request.get_json() or {}
        agent_name = data.get('agent_name', '')
        actions    = data.get('actions', [])
        position   = data.get('position', [0, 0, 0])

        if not agent_name or agent_name not in field.agents:
            return jsonify({"error": f"Agent '{agent_name}' not found"}), 404
        if not actions:
            return jsonify({"error": "No actions provided"}), 400

        agent = field.agents[agent_name]

        # Get current field state for coherence computation
        field_state = {
            "matrix": field.field_matrix()
        }

        # Score each action
        scored = [
            score_action(a, agent, field_state, position, _weights)
            for a in actions
        ]

        # Boltzmann ranking
        ranked = boltzmann_rank(scored, _weights.temperature)

        # Add outcome estimate rationale (heuristic)
        for r in ranked:
            label = (
                "strongly aligned with current field state"
                if r['E_total'] < 0.2 else
                "available with moderate tension"
                if r['E_total'] < 0.4 else
                "elevated friction — proceed with awareness"
                if r['E_total'] < 0.6 else
                "high resistance — field not supportive"
                if r['E_total'] < 0.8 else
                "avoided — significant field opposition"
            )
            r['outcome_estimate'] = {"rationale": label}

        summary     = compute_field_summary(ranked, _weights.temperature)
        calibration = compute_calibration(agent)

        return jsonify({
            "agent_name":     agent_name,
            "ranked_actions": ranked,
            "field_summary":  summary,
            "calibration":    calibration,
            "weights_used":   _weights.as_dict()
        })

    @energy_bp.route('/energy/state', methods=['GET'])
    def energy_state():
        """Current energy weights and field overview."""
        agents_summary = {}
        for name, agent in field.agents.items():
            matrix = field.field_matrix()
            row = matrix.get(name, {})
            scores = [v for k, v in row.items() if k != name and v > 0]
            avg_coh = round(sum(scores) / len(scores), 4) if scores else 0.0
            w = agent.weights
            # Approximate field energy for this agent
            valence   = w.get('E', 0.35) * getattr(agent, '_affect_regulation', 1.0)
            coherence = avg_coh
            E_agent   = round(
                (1 - coherence) * _weights.w_coherence +
                (1 - valence)   * _weights.w_valence   +
                (1 - w.get('P', 0.20)) * _weights.w_salience,
                4
            )
            agents_summary[name] = {
                "weights":    dict(w),
                "avg_coherence": avg_coh,
                "E_field":    E_agent
            }

        return jsonify({
            "weights":  _weights.as_dict(),
            "agents":   agents_summary
        })

    return energy_bp
