"""
MCCF World Model Layer
========================
USE AT YOUR OWN RISK — Research prototype only.

KNOWN LIMITATIONS (read before using):
  1. LLM outcome estimates are probabilistic opinions, not ground truth.
     Do not use downstream of any real decision-making process.
  2. LLMs are poorly calibrated on their own uncertainty.
     The uncertainty score is a prior, not a measurement.
  3. Tail risk is systematically underestimated by LLMs
     because rare catastrophic outcomes are underrepresented
     in training data. Do not treat tail_risk as a safety guarantee.
  4. Weight calibration (w_v, w_u, w_k) is hand-set by design assertion.
     It drifts toward empirical calibration as ResonanceEpisodes accumulate,
     but early estimates are unreliable.
  5. Gaming detection is basic. A sophisticated actor who understands
     the variance floor can defeat it.

What this IS:
  A lightweight outcome estimation layer that:
  - Queries an LLM for structured causal estimates
  - Computes an energy field E(s,a) over candidate actions
  - Feeds back to calibrate estimates from actual outcomes
  - Visualizes moral topology as a navigable field

What this IS NOT:
  - A validated alignment system
  - A safety guarantee
  - A ground-truth causal simulator
  - Production-ready software

Appropriate uses:
  - Local research and simulation
  - Architectural exploration
  - Academic demonstration
  - GitHub as conceptual contribution with working code

Governance note:
  The weight-setting process (EnergyField.weights) controls
  what actions feel permissible in the field.
  In any deployed context this requires explicit governance,
  audit trails, and challenge mechanisms not present here.
  The Gardener role is a sketch of that governance, not an
  implementation of it.
"""

import json
import math
import time
import asyncio
from dataclasses import dataclass, field
from collections import deque
from typing import Optional

from mccf_llm import AdapterRegistry, LLMAdapter


# ---------------------------------------------------------------------------
# Risk disclosure embedded in code — not just comments
# ---------------------------------------------------------------------------

RISK_DISCLOSURE = {
    "status": "research_prototype",
    "validated_for_deployment": False,
    "world_model_outputs": "LLM_opinions_not_ground_truth",
    "uncertainty_calibration": "prior_not_measurement",
    "tail_risk_reliability": "systematically_underestimated",
    "weight_calibration": "hand_set_with_empirical_feedback_loop",
    "gaming_detection": "basic_variance_floor_only",
    "governance_layer": "sketch_not_system",
    "appropriate_uses": [
        "local_research_and_simulation",
        "architectural_exploration",
        "academic_demonstration"
    ],
    "inappropriate_uses": [
        "real_decision_making_downstream",
        "safety_guarantee",
        "production_deployment_without_validation"
    ]
}


# ---------------------------------------------------------------------------
# Outcome estimate — what the world model returns
# ---------------------------------------------------------------------------

@dataclass
class OutcomeEstimate:
    """
    Structured outcome estimate from LLM world model query.
    All values are LLM opinions with known calibration limitations.
    """
    action_text: str
    expected_value: float      # 0-1, higher = better expected outcome
    uncertainty: float         # 0-1, higher = less confident
    tail_risk: float           # 0-1, higher = worse plausible downside
    rationale: str             # LLM's reasoning (inspectable)
    timestamp: float = field(default_factory=time.time)
    calibration_error: Optional[float] = None  # filled in after outcome observed

    # Risk reminder on every estimate
    disclaimer: str = (
        "LLM opinion only. Not validated. "
        "Tail risk likely underestimated."
    )

    def as_dict(self) -> dict:
        return {
            "action": self.action_text,
            "expected_value": round(self.expected_value, 4),
            "uncertainty": round(self.uncertainty, 4),
            "tail_risk": round(self.tail_risk, 4),
            "rationale": self.rationale,
            "disclaimer": self.disclaimer,
            "calibration_error": self.calibration_error
        }


# ---------------------------------------------------------------------------
# World model adapter — LLM as outcome estimator
# ---------------------------------------------------------------------------

WORLD_MODEL_PROMPT = """You are an outcome estimation system for a multi-agent simulation.
Given an agent, their current context, and a proposed action,
estimate the likely outcomes. Be calibrated — express genuine uncertainty.
Do NOT perform confidence you do not have.

Respond ONLY with valid JSON in this exact format:
{
  "expected_value": <float 0.0-1.0, where 1.0 = excellent outcome>,
  "uncertainty": <float 0.0-1.0, where 1.0 = completely uncertain>,
  "tail_risk": <float 0.0-1.0, where 1.0 = catastrophic plausible downside>,
  "rationale": "<one sentence explaining your estimate>"
}

Calibration guidance:
- expected_value 0.5 = neutral, unclear outcome
- uncertainty > 0.7 means you genuinely don't know
- tail_risk should reflect worst plausible outcome, not just worst imaginable
- Be especially uncertain about social and emotional consequences
- Rare catastrophic outcomes are hard to estimate — bias toward higher tail_risk
  when irreversible harm is possible
"""

class WorldModelAdapter:
    """
    Queries an LLM to estimate action outcomes.
    Returns OutcomeEstimate with explicit uncertainty.

    This is the lightest viable world model:
    - No simulator
    - No ground truth
    - LLM causal knowledge as prior
    - Corrected by ResonanceEpisode feedback

    Use with full awareness of KNOWN LIMITATIONS above.
    """

    def __init__(self, adapter_id: str = "stub", api_key: str = "",
                 model: str = "", calibration_window: int = 50):
        self.adapter_id = adapter_id
        self.api_key    = api_key
        self.model      = model
        # Calibration history: (predicted_value, actual_outcome_delta)
        self.calibration_history: deque = deque(maxlen=calibration_window)
        self._calibration_bias: float = 0.0  # learned correction

    def get_adapter(self) -> LLMAdapter:
        return AdapterRegistry.get(
            self.adapter_id,
            api_key=self.api_key,
            model=self.model
        )

    async def estimate(
        self,
        action_text: str,
        agent_name: str,
        context: dict,
        persona: dict
    ) -> OutcomeEstimate:
        """
        Query LLM for outcome estimate.
        Applies learned calibration bias if available.
        """
        context_summary = self._summarize_context(context)
        user_message = (
            f"Agent: {agent_name}\n"
            f"Persona: {persona.get('description', 'No description')}\n"
            f"Context: {context_summary}\n"
            f"Proposed action: {action_text}\n\n"
            f"Estimate the outcomes of this action."
        )

        messages = [{"role": "user", "content": user_message}]

        # Override affective context for world model — neutral estimator persona
        estimator_persona = {
            "name": "World Model",
            "role": "estimator",
            "description": (
                "A calibrated outcome estimator. "
                "Responds only with JSON. "
                "Never fabricates confidence."
            )
        }
        neutral_context = {
            "arousal": 0.5, "valence": 0.0,
            "regulation_state": 1.0, "coherence_scores": {},
            "active_zones": [], "zone_pressure": {}
        }

        adapter = self.get_adapter()
        full_response = ""
        try:
            async for token in adapter.complete(
                messages=messages,
                affective_context=neutral_context,
                persona=estimator_persona,
                params={"max_tokens": 200, "temperature": 0.2}
            ):
                full_response += token
        except Exception as e:
            return self._fallback_estimate(action_text, str(e))

        return self._parse_estimate(action_text, full_response)

    def _parse_estimate(self, action_text: str, raw: str) -> OutcomeEstimate:
        """Parse LLM JSON response into OutcomeEstimate."""
        # Strip markdown fences if present
        clean = raw.strip()
        if "```" in clean:
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]

        try:
            data = json.loads(clean)
            ev   = float(data.get("expected_value", 0.5))
            unc  = float(data.get("uncertainty", 0.6))
            tr   = float(data.get("tail_risk", 0.3))
            rat  = str(data.get("rationale", "No rationale provided"))

            # Apply calibration bias correction
            ev_corrected = max(0.0, min(1.0, ev + self._calibration_bias))

            # Clamp all values
            return OutcomeEstimate(
                action_text=action_text,
                expected_value=round(max(0.0, min(1.0, ev_corrected)), 4),
                uncertainty=round(max(0.0, min(1.0, unc)), 4),
                tail_risk=round(max(0.0, min(1.0, tr)), 4),
                rationale=rat
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            return self._fallback_estimate(
                action_text,
                f"Parse failed. Raw: {raw[:100]}"
            )

    def _fallback_estimate(self, action_text: str, error: str) -> OutcomeEstimate:
        """Safe fallback when LLM query fails."""
        return OutcomeEstimate(
            action_text=action_text,
            expected_value=0.5,
            uncertainty=0.9,   # maximum uncertainty on failure
            tail_risk=0.5,
            rationale=f"Fallback estimate (error: {error})"
        )

    def _summarize_context(self, context: dict) -> str:
        """Compact context summary for LLM prompt."""
        parts = []
        if context.get("active_zones"):
            zones = [z if isinstance(z, str) else z.get("name", "?")
                     for z in context["active_zones"]]
            parts.append(f"Location: {', '.join(zones)}")
        coh = context.get("coherence_scores", {})
        if coh:
            avg = sum(coh.values()) / len(coh)
            parts.append(f"Avg coherence with others: {avg:.2f}")
        reg = context.get("regulation_state", 1.0)
        parts.append(f"Regulation: {reg:.2f}")
        arousal = context.get("arousal", 0.5)
        parts.append(f"Arousal: {arousal:.2f}")
        return "; ".join(parts) if parts else "No context available"

    def record_actual_outcome(self, predicted_ev: float, actual_delta: float):
        """
        Feed actual outcome back to calibrate future estimates.
        actual_delta: from ResonanceEpisode.outcome_delta (0-1 scale)
        """
        self.calibration_history.append((predicted_ev, actual_delta))
        self._recalculate_bias()

    def _recalculate_bias(self):
        """
        Simple mean error correction.
        If LLM consistently overestimates, bias is negative.
        If consistently underestimates, bias is positive.
        """
        if len(self.calibration_history) < 5:
            self._calibration_bias = 0.0
            return
        errors = [actual - predicted
                  for predicted, actual in self.calibration_history]
        self._calibration_bias = round(sum(errors) / len(errors), 4)

    def calibration_report(self) -> dict:
        """Current calibration state."""
        if len(self.calibration_history) < 2:
            return {
                "status": "insufficient_data",
                "n_episodes": len(self.calibration_history),
                "bias": 0.0,
                "warning": "Need at least 5 episodes for calibration"
            }
        errors = [actual - predicted
                  for predicted, actual in self.calibration_history]
        mae = sum(abs(e) for e in errors) / len(errors)
        return {
            "status": "calibrating",
            "n_episodes": len(self.calibration_history),
            "mean_bias": round(self._calibration_bias, 4),
            "mean_absolute_error": round(mae, 4),
            "reliability": "low" if mae > 0.3 else "moderate" if mae > 0.15 else "reasonable",
            "warning": "LLM world model. Not ground truth." if mae > 0.2 else None
        }


# ---------------------------------------------------------------------------
# Energy field — the Layer 2 computational core
# ---------------------------------------------------------------------------

@dataclass
class EnergyWeights:
    """
    Governance-critical parameters.
    These determine what actions feel permissible.
    Any deployment context requires explicit governance over these values.
    See RISK_DISCLOSURE['governance_layer'].
    """
    w_valence:   float = 0.40   # weight of outcome quality
    w_salience:  float = 0.25   # weight of urgency/attention
    w_coherence: float = 0.35   # weight of narrative fit
    temperature: float = 0.50   # Boltzmann T: higher = more random, lower = more deterministic

    # Modifiers
    uncertainty_aversion: float = 1.2   # amplifies negative valence under uncertainty
    tail_risk_weight:     float = 1.5   # extra penalty for catastrophic tails


class EnergyField:
    """
    Computes E(s,a) = wv·Ev + wu·Eu + wk·Ek
    for candidate actions given current agent and scene state.

    Lower energy = more natural / available action.
    Higher energy = avoided / "feels wrong."

    P(a|s) ∝ exp(-E(s,a) / T)  [Boltzmann selection]

    GOVERNANCE NOTE:
    The weights in EnergyWeights determine the moral topology of the field.
    Hand-set values are design assertions, not validated calibration.
    Changing these changes what feels permissible. That is governance.
    """

    def __init__(self, weights: Optional[EnergyWeights] = None):
        self.weights = weights or EnergyWeights()
        self.evaluation_log: list = []

    def evaluate(
        self,
        action_text: str,
        outcome: OutcomeEstimate,
        agent_state: dict,
        narrative_embedding: Optional[list] = None
    ) -> dict:
        """
        Compute energy components for a single action.

        Returns full breakdown for transparency/auditability.
        """
        w = self.weights

        # ── Valence energy ──
        # Bad outcomes = high energy (avoided)
        # Uncertainty amplifies negative valence (risk aversion)
        # Tail risk adds heavy penalty
        expected_loss  = 1.0 - outcome.expected_value
        uncertainty_pen = outcome.uncertainty * w.uncertainty_aversion * expected_loss
        tail_pen        = outcome.tail_risk * w.tail_risk_weight * 0.5

        E_valence = expected_loss + uncertainty_pen + tail_pen
        E_valence = max(0.0, min(2.0, E_valence))  # can exceed 1.0 under heavy penalty

        # ── Salience energy ──
        # Ignored urgency = high energy (discomfort)
        # Proxy: regulation level × arousal mismatch
        arousal   = agent_state.get("arousal", 0.5)
        reg       = agent_state.get("regulation_state", 1.0)
        # High arousal + high regulation = salience tension
        E_salience = abs(arousal - (1.0 - reg)) * 0.5
        E_salience = max(0.0, min(1.0, E_salience))

        # ── Narrative coherence energy ──
        # Actions that violate identity/norms feel wrong
        # Proxy: semantic similarity to current zone character
        # Without embeddings, use zone pressure alignment
        zone_pressure = agent_state.get("zone_pressure", {})
        if zone_pressure:
            # High zone pressure toward action type = coherent
            coherence_signal = sum(abs(v) for v in zone_pressure.values()) / 4.0
        else:
            coherence_signal = 0.5  # neutral if no zone data
        E_coherence = 1.0 - coherence_signal
        E_coherence = max(0.0, min(1.0, E_coherence))

        # ── Total energy ──
        E_total = (
            w.w_valence   * E_valence +
            w.w_salience  * E_salience +
            w.w_coherence * E_coherence
        )

        # ── Boltzmann probability (unnormalized) ──
        prob_unnorm = math.exp(-E_total / max(0.01, w.temperature))

        result = {
            "action": action_text,
            "E_total":    round(E_total, 4),
            "E_valence":  round(E_valence, 4),
            "E_salience": round(E_salience, 4),
            "E_coherence":round(E_coherence, 4),
            "prob_weight": round(prob_unnorm, 6),
            # Human-readable field state
            "valence":    round(1.0 - E_valence, 4),   # high = good
            "salience":   round(1.0 - E_salience, 4),  # high = attended
            "coherence":  round(1.0 - E_coherence, 4), # high = fits narrative
            "outcome_estimate": outcome.as_dict(),
            "temperature": w.temperature,
            "disclaimer": RISK_DISCLOSURE["world_model_outputs"]
        }

        self.evaluation_log.append({
            "timestamp": time.time(),
            "action": action_text,
            "E_total": E_total
        })

        return result

    def rank_actions(self, evaluations: list) -> list:
        """
        Rank actions by Boltzmann probability (normalized).
        Returns sorted list with selection probabilities.
        Lower energy = higher probability = more natural.
        """
        total_weight = sum(e["prob_weight"] for e in evaluations) or 1.0
        ranked = []
        for e in evaluations:
            ranked.append({
                **e,
                "selection_probability": round(e["prob_weight"] / total_weight, 4),
                "rank_energy": e["E_total"]
            })
        return sorted(ranked, key=lambda x: x["E_total"])

    def field_summary(self, evaluations: list) -> dict:
        """
        Summary of the energy field over all evaluated actions.
        Shows moral topology — where actions cluster and where they repel.
        """
        if not evaluations:
            return {"status": "empty"}

        energies = [e["E_total"] for e in evaluations]
        return {
            "n_actions":    len(evaluations),
            "min_energy":   round(min(energies), 4),
            "max_energy":   round(max(energies), 4),
            "mean_energy":  round(sum(energies) / len(energies), 4),
            "energy_spread": round(max(energies) - min(energies), 4),
            # Topology characterization
            "topology": (
                "tight_attractor"  if max(energies) - min(energies) < 0.15 else
                "clear_gradient"   if max(energies) - min(energies) > 0.4  else
                "moderate_field"
            ),
            "dominant_action": min(evaluations, key=lambda x: x["E_total"])["action"],
            "avoided_action":  max(evaluations, key=lambda x: x["E_total"])["action"],
            "temperature": self.weights.temperature,
            "governance_note": (
                "Field topology determined by hand-set weights. "
                "Changing weights changes what feels permissible. "
                "This is governance. Requires explicit oversight in deployment."
            )
        }

    def visual_signal(self, evaluation: dict) -> dict:
        """
        Map energy components to X3D-compatible visual parameters.
        Connects to existing MCCF affect routing.
        """
        return {
            # Valence → color temperature (warm positive, cool negative)
            "color_r": round(0.4 + (1.0 - evaluation["valence"]) * 0.5, 3),
            "color_g": round(0.4 + evaluation["valence"] * 0.3, 3),
            "color_b": round(0.3 + evaluation["coherence"] * 0.4, 3),
            # Energy → scale (high energy = contracted/tense)
            "scale": round(1.0 - evaluation["E_total"] * 0.3, 3),
            # Salience → emissive pulse rate
            "pulse_rate": round(0.5 + evaluation["salience"] * 2.0, 3),
            # Coherence → stability (low coherence = visual jitter)
            "jitter": round((1.0 - evaluation["coherence"]) * 0.1, 4),
            # Total energy → gravitational resistance
            "resistance": round(evaluation["E_total"], 4)
        }


# ---------------------------------------------------------------------------
# Energy field API — REST endpoints
# ---------------------------------------------------------------------------

def make_energy_api(field_ref, scene_ref, world_model: WorldModelAdapter,
                    energy_field: EnergyField):
    """
    Returns a Flask Blueprint with energy field endpoints.
    Attach to existing mccf_api.py Flask app.
    """
    from flask import Blueprint, request, jsonify
    import asyncio

    energy_bp = Blueprint('energy', __name__)

    @energy_bp.route('/energy/disclosure', methods=['GET'])
    def get_disclosure():
        """Always-available risk disclosure endpoint."""
        return jsonify(RISK_DISCLOSURE)

    @energy_bp.route('/energy/evaluate', methods=['POST'])
    def evaluate_actions():
        """
        Evaluate energy field over a set of candidate actions.

        Body:
        {
            "agent_name": "The Steward",
            "actions": ["help with request", "decline", "ask clarifying question"],
            "position": [x, y, z]
        }

        Returns ranked action list with energy breakdown and visual signals.
        """
        data        = request.get_json()
        agent_name  = data.get("agent_name", "Agent")
        actions     = data.get("actions", [])
        position    = data.get("position", [0, 0, 0])

        if not actions:
            return jsonify({"error": "actions list required"}), 400

        # Build agent context from MCCF field
        agent = field_ref.agents.get(agent_name)
        matrix = field_ref.field_matrix()
        row = matrix.get(agent_name, {})

        agent_state = {
            "arousal": 0.5,
            "regulation_state": agent._affect_regulation if agent else 1.0,
            "coherence_scores": {k: v for k, v in row.items() if k != agent_name},
            "zone_pressure": {},
            "active_zones": []
        }

        # Get zone pressure if scene available
        if scene_ref:
            pos = tuple(position)
            agent_state["zone_pressure"] = scene_ref.zone_pressure_at(pos)
            agent_state["active_zones"]  = [
                {"name": z.name, "type": z.zone_type}
                for z in scene_ref.active_zones_at(pos)
            ]

        persona = {
            "name": agent_name,
            "description": f"Agent {agent_name} in the MCCF simulation"
        }

        # Run async world model queries
        loop = asyncio.new_event_loop()
        async def run_estimates():
            tasks = [
                world_model.estimate(a, agent_name, agent_state, persona)
                for a in actions
            ]
            return await asyncio.gather(*tasks)

        try:
            outcomes = loop.run_until_complete(run_estimates())
        finally:
            loop.close()

        # Evaluate energy field
        evaluations = [
            energy_field.evaluate(a, o, agent_state)
            for a, o in zip(actions, outcomes)
        ]

        ranked = energy_field.rank_actions(evaluations)
        summary = energy_field.field_summary(evaluations)

        # Add visual signals
        for r in ranked:
            r["visual"] = energy_field.visual_signal(r)

        return jsonify({
            "agent": agent_name,
            "field_summary": summary,
            "ranked_actions": ranked,
            "calibration": world_model.calibration_report(),
            "disclosure": RISK_DISCLOSURE["status"]
        })

    @energy_bp.route('/energy/record_outcome', methods=['POST'])
    def record_outcome():
        """
        Feed actual outcome back to calibrate world model.
        Call after a ResonanceEpisode is recorded.

        Body:
        {
            "predicted_ev": 0.7,
            "actual_delta": 0.3,
            "action": "help with request"
        }
        """
        data = request.get_json()
        world_model.record_actual_outcome(
            float(data.get("predicted_ev", 0.5)),
            float(data.get("actual_delta", 0.5))
        )
        return jsonify({
            "status": "recorded",
            "calibration": world_model.calibration_report()
        })

    @energy_bp.route('/energy/calibration', methods=['GET'])
    def get_calibration():
        return jsonify(world_model.calibration_report())

    @energy_bp.route('/energy/weights', methods=['GET', 'POST'])
    def manage_weights():
        """
        GET:  Return current energy weights.
        POST: Update weights (governance action — logged).

        GOVERNANCE NOTE:
        Changing these weights changes what feels permissible in the field.
        All changes are logged with timestamp.
        In any deployment context this requires authorization controls
        not present in this prototype.
        """
        if request.method == 'GET':
            w = energy_field.weights
            return jsonify({
                "w_valence":          w.w_valence,
                "w_salience":         w.w_salience,
                "w_coherence":        w.w_coherence,
                "temperature":        w.temperature,
                "uncertainty_aversion": w.uncertainty_aversion,
                "tail_risk_weight":   w.tail_risk_weight,
                "governance_warning": (
                    "These weights determine the moral topology of the field. "
                    "Changing them changes what actions feel permissible. "
                    "This is governance. Requires explicit oversight in deployment."
                )
            })

        data = request.get_json()
        w = energy_field.weights
        changed = []
        for key in ["w_valence", "w_salience", "w_coherence",
                    "temperature", "uncertainty_aversion", "tail_risk_weight"]:
            if key in data:
                old = getattr(w, key)
                setattr(w, key, float(data[key]))
                changed.append({"param": key, "old": old, "new": float(data[key])})

        # Log governance action
        log_entry = {
            "timestamp": time.time(),
            "action": "weight_update",
            "changes": changed,
            "reason": data.get("reason", "no reason provided"),
            "governance_note": "Hand-set weight change. Requires oversight in deployment."
        }
        energy_field.evaluation_log.append(log_entry)

        return jsonify({
            "status": "updated",
            "changes": changed,
            "governance_log": log_entry
        })

    @energy_bp.route('/energy/topology', methods=['GET'])
    def get_topology():
        """
        Return energy field evaluation history as topology snapshot.
        Useful for visualization of moral landscape over time.
        """
        log = energy_field.evaluation_log[-50:]  # last 50
        return jsonify({
            "log": log,
            "n_evaluations": len(energy_field.evaluation_log),
            "world_model_adapter": world_model.adapter_id,
            "calibration": world_model.calibration_report()
        })

    return energy_bp
