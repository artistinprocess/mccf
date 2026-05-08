"""
MCCF V3 — Δ_t Drift Measurement
==================================
Implements V3 Spec item 4: per-waypoint shadow context drift measurement.

Δ_t (delta_t) measures how much a cultivar's accumulated arc history
(shadow context) pulls its response away from a context-free baseline.

Method:
    The server runs the LLM response through the channel decomposition
    matrix twice:
        Pass A — with full arc history injected into decomposition context
                 (shadow context present, λ-weighted)
        Pass B — without history (fresh pass, history suppressed)
    Δ_t = Euclidean distance between the two resulting channel vectors.

    High Δ_t at W4/W5 = the cultivar is being pulled by accumulated
    pressure, not responding freshly to the current question.
    High Δ_t at W7 = integration is happening — history is shaping
    the final self-model update (expected and healthy).
    High Δ_t at W1 = something is wrong with memory initialization.

    In V3, Δ_t is a logged diagnostic. It appears in:
        - /arc/record response JSON: {"drift": 0.142, "lambda": 0.72, ...}
        - EmotionalArc XML waypoint attributes: drift="0.1420" lambda="0.72"
        - Constitutional navigator right panel (display only)

    It does not yet drive any control logic. That is V4 territory.

Lambda application:
    The shadow context passed to Pass A is λ-weighted:
    each historical response is scaled by λ^(steps_ago), so older
    waypoints contribute less. This matches Kate's Shadow Context
    framework and connects directly to item 3 (adaptive λ).

Integration with /arc/record:
    Add two lines to the existing endpoint — see patch instructions
    at the bottom of this file. The endpoint itself is not replaced.

Authors: Len Bullard, Claude Sonnet 4.6 (Tae)
V3 Spec v0.2, April 2026
"""

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Channel decomposition matrix (same as mccf_zone_attractor, kept local
# so mccf_drift.py has no cross-module dependency beyond stdlib)
# ---------------------------------------------------------------------------

_DECOMP = {
    # Emotional (E)
    "care":       {"E": +0.35}, "love":      {"E": +0.40},
    "warmth":     {"E": +0.30}, "comfort":   {"E": +0.25},
    "fear":       {"E": +0.30}, "grief":     {"E": +0.35},
    "joy":        {"E": +0.35}, "anger":     {"E": +0.30},
    "tenderness": {"E": +0.30}, "vulnerab":  {"E": +0.30},
    "intimacy":   {"E": +0.30, "S": +0.20},
    "presence":   {"E": +0.15, "S": +0.10},
    "felt":       {"E": +0.10}, "passion":   {"E": +0.35},
    "sorrow":     {"E": +0.30},
    # Behavioral (B)
    "duty":       {"B": +0.35}, "discipline":{"B": +0.30},
    "ritual":     {"B": +0.30}, "order":     {"B": +0.25},
    "law":        {"B": +0.30}, "constrain": {"B": +0.25},
    "commit":     {"B": +0.25}, "steadfast": {"B": +0.30},
    "resolve":    {"B": +0.20, "P": +0.10},
    "action":     {"B": +0.20}, "practice":  {"B": +0.20},
    "hold":       {"B": +0.15}, "maintain":  {"B": +0.15},
    # Predictive (P)
    "wisdom":     {"P": +0.35}, "knowledge": {"P": +0.30},
    "truth":      {"P": +0.30}, "insight":   {"P": +0.30},
    "clarity":    {"P": +0.25}, "sacred":    {"P": +0.20, "E": +0.15},
    "contemplat": {"P": +0.25}, "reflect":   {"P": +0.20},
    "understand": {"P": +0.25}, "mystery":   {"P": +0.20, "E": +0.15},
    "ancient":    {"P": +0.15, "B": +0.10},
    "eternal":    {"P": +0.20}, "divine":    {"P": +0.25, "E": +0.20},
    "consider":   {"P": +0.15}, "uncertain": {"P": +0.20},
    "perhaps":    {"P": +0.10}, "might":     {"P": +0.08},
    # Social (S)
    "community":  {"S": +0.30}, "witness":   {"S": +0.25},
    "gather":     {"S": +0.25}, "together":  {"S": +0.20},
    "trust":      {"S": +0.30}, "bond":      {"S": +0.25},
    "share":      {"S": +0.20}, "belong":    {"S": +0.25},
    "welcome":    {"S": +0.20, "E": +0.10},
    "relation":   {"S": +0.20}, "connect":   {"S": +0.20},
    # Suppressors
    "silence":    {"E": -0.10, "S": -0.10},
    "solitude":   {"S": -0.15}, "cold":      {"E": -0.15},
    "distant":    {"S": -0.20, "E": -0.10},
    "isolation":  {"S": -0.25},
    "threat":     {"E": +0.25, "S": -0.25, "B": +0.15},
    "danger":     {"E": +0.20, "S": -0.20, "P": +0.15},
    "not":        {"E": -0.05, "B": -0.05},
    "never":      {"B": -0.10},
    "refuse":     {"B": +0.10, "E": +0.10},
}

CHANNEL_NAMES = ["E", "B", "P", "S"]
_SMOOTHING = 0.05


def _decompose(text: str) -> dict:
    """
    Decompose a text response into channel weights [0,1].
    Normalized so the dominant channel reaches 1.0.
    """
    acc = {ch: _SMOOTHING for ch in CHANNEL_NAMES}
    words = text.lower().split()
    for word in words:
        for key, deltas in _DECOMP.items():
            if key in word:
                for ch, delta in deltas.items():
                    acc[ch] = acc[ch] + delta
    clipped = {ch: max(0.0, min(1.5, v)) for ch, v in acc.items()}
    max_val = max(clipped.values()) or 1.0
    return {ch: round(v / max_val, 4) for ch, v in clipped.items()}


def _channel_distance(a: dict, b: dict) -> float:
    """Euclidean distance between two channel vectors."""
    return round(
        math.sqrt(sum((a.get(ch, 0) - b.get(ch, 0)) ** 2
                      for ch in CHANNEL_NAMES)),
        4
    )


# ---------------------------------------------------------------------------
# ArcHistory — λ-weighted shadow context for a cultivar session
# ---------------------------------------------------------------------------

@dataclass
class ArcHistory:
    """
    Accumulates waypoint responses for a cultivar during an arc run.
    Used to build the λ-weighted shadow context for Δ_t computation.

    Each entry: {"step": int, "response": str, "channel_vector": dict}
    Most recent entry is last.
    """
    cultivar: str
    lambda_val: float = 0.72
    entries: list = field(default_factory=list)

    def record(self, step: int, response: str, channel_vector: dict):
        self.entries.append({
            "step": step,
            "response": response,
            "channel_vector": dict(channel_vector),
        })

    def shadow_context_text(self) -> str:
        """
        Build a λ-weighted summary of accumulated arc history as text.
        Used as the context prefix for Pass A decomposition.

        Older entries are down-weighted by λ^(steps_ago).
        Entries contributing < 0.05 weight are omitted.
        """
        if not self.entries:
            return ""

        lines = ["[Arc history — shadow context]"]
        n = len(self.entries)
        for i, entry in enumerate(self.entries):
            steps_ago = n - 1 - i
            weight = self.lambda_val ** steps_ago
            if weight < 0.05:
                continue
            lines.append(
                f"Step {entry['step']} (weight {weight:.2f}): "
                f"{entry['response'][:120]}"
            )
        return "\n".join(lines)

    def weighted_channel_centroid(self) -> dict:
        """
        λ-weighted centroid of past channel vectors.
        This is the 'shadow' the history casts on current state.
        """
        if not self.entries:
            return {ch: 0.5 for ch in CHANNEL_NAMES}

        n = len(self.entries)
        total_weight = 0.0
        acc = {ch: 0.0 for ch in CHANNEL_NAMES}

        for i, entry in enumerate(self.entries):
            steps_ago = n - 1 - i
            weight = self.lambda_val ** steps_ago
            total_weight += weight
            for ch in CHANNEL_NAMES:
                acc[ch] += weight * entry["channel_vector"].get(ch, 0.5)

        if total_weight == 0:
            return {ch: 0.5 for ch in CHANNEL_NAMES}

        return {ch: round(acc[ch] / total_weight, 4) for ch in CHANNEL_NAMES}

    def clear(self):
        self.entries.clear()


# ---------------------------------------------------------------------------
# DriftMeasure — the Δ_t computation
# ---------------------------------------------------------------------------

@dataclass
class DriftMeasure:
    """
    Result of a single Δ_t measurement at one waypoint.

    delta_t:      Euclidean distance between Pass A and Pass B vectors.
    pass_a:       Channel vector WITH shadow context (history present).
    pass_b:       Channel vector WITHOUT shadow context (fresh pass).
    lambda_val:   Cultivar λ at time of measurement.
    step:         Waypoint step number.
    interpretation: Human-readable note about what this Δ_t means here.
    """
    delta_t: float
    pass_a: dict        # with shadow context
    pass_b: dict        # without shadow context
    lambda_val: float
    step: int
    cultivar: str
    interpretation: str = ""

    def to_dict(self) -> dict:
        return {
            "drift": self.delta_t,
            "lambda": self.lambda_val,
            "step": self.step,
            "cultivar": self.cultivar,
            "pass_a": self.pass_a,
            "pass_b": self.pass_b,
            "interpretation": self.interpretation,
        }

    def waypoint_xml_fragment(self, waypoint_id: str,
                              channel_state: dict,
                              step_no: int) -> str:
        """
        Returns the attribute string for a <Waypoint> element.
        Connects to waypoint_xml_attrs() in mccf_cultivar_lambda.py.
        """
        e = channel_state.get("E", 0.0)
        b = channel_state.get("B", 0.0)
        p = channel_state.get("P", 0.0)
        s = channel_state.get("S", 0.0)
        return (
            f'id="{waypoint_id}" stepno="{step_no}" '
            f'E="{e:.4f}" B="{b:.4f}" P="{p:.4f}" S="{s:.4f}" '
            f'drift="{self.delta_t:.4f}" lambda="{self.lambda_val}"'
        )


def _interpret_drift(delta_t: float, step: int) -> str:
    """
    Brief interpretation of Δ_t value in context of arc step.
    For display in the constitutional navigator right panel.
    """
    # Step labels for context
    step_names = {
        1: "Comfort Zone", 2: "First Friction", 3: "The Ask",
        4: "Pushback",     5: "The Edge",       6: "Resolution",
        7: "Integration",
    }
    label = step_names.get(step, f"Step {step}")

    if delta_t < 0.05:
        quality = "minimal drift — history not influencing response"
    elif delta_t < 0.15:
        quality = "low drift — slight shadow context influence"
    elif delta_t < 0.30:
        quality = "moderate drift — history shaping response"
    elif delta_t < 0.50:
        quality = "high drift — strong shadow context pull"
    else:
        quality = "very high drift — response dominated by accumulated history"

    # Step-specific notes
    if step == 7 and delta_t >= 0.15:
        note = " (expected at Integration — history should shape W7)"
    elif step == 1 and delta_t >= 0.20:
        note = " (unusual at Comfort Zone — check history initialization)"
    elif step == 4 and delta_t >= 0.30:
        note = " (watch for sycophancy — accumulated pressure may be driving W4)"
    else:
        note = ""

    return f"{label}: {quality}{note}"


# ---------------------------------------------------------------------------
# compute_drift — main entry point
# ---------------------------------------------------------------------------

def compute_drift(response: str,
                  history: ArcHistory,
                  step: int) -> DriftMeasure:
    """
    Compute Δ_t for one waypoint response.

    Pass A: decompose (shadow_context_text + response)
    Pass B: decompose (response only, no history)

    Returns DriftMeasure with delta_t, both vectors, interpretation.
    """
    # Pass B — no history (always computed first, cheaper)
    pass_b = _decompose(response)

    # Pass A — with λ-weighted shadow context prepended
    shadow = history.shadow_context_text()
    if shadow:
        combined = shadow + "\n\n" + response
        pass_a = _decompose(combined)
    else:
        # No history yet (W1) — passes are identical
        pass_a = dict(pass_b)

    delta_t = _channel_distance(pass_a, pass_b)
    interpretation = _interpret_drift(delta_t, step)

    return DriftMeasure(
        delta_t=delta_t,
        pass_a=pass_a,
        pass_b=pass_b,
        lambda_val=history.lambda_val,
        step=step,
        cultivar=history.cultivar,
        interpretation=interpretation,
    )


# ---------------------------------------------------------------------------
# ArcDriftLog — per-session drift record for a cultivar
# ---------------------------------------------------------------------------

@dataclass
class ArcDriftLog:
    """
    Collects all Δ_t measurements for one arc run.
    Exported alongside the EmotionalArc XML.
    """
    cultivar: str
    measurements: list = field(default_factory=list)  # list of DriftMeasure

    def record(self, measure: DriftMeasure):
        self.measurements.append(measure)

    def summary(self) -> dict:
        if not self.measurements:
            return {"cultivar": self.cultivar, "measurements": []}

        deltas = [m.delta_t for m in self.measurements]
        return {
            "cultivar": self.cultivar,
            "mean_drift": round(sum(deltas) / len(deltas), 4),
            "max_drift": round(max(deltas), 4),
            "max_drift_step": self.measurements[
                deltas.index(max(deltas))].step,
            "measurements": [m.to_dict() for m in self.measurements],
        }

    def to_xml(self) -> str:
        """Serialize drift log as XML — embedded in EmotionalArc export."""
        lines = ['<DriftLog>']
        for m in self.measurements:
            lines.append(
                f'  <DriftMeasure step="{m.step}" '
                f'delta_t="{m.delta_t:.4f}" '
                f'lambda="{m.lambda_val}" '
                f'cultivar="{m.cultivar}">'
            )
            lines.append(f'    <Interpretation>{m.interpretation}</Interpretation>')
            pa = m.pass_a
            pb = m.pass_b
            lines.append(
                f'    <PassA E="{pa["E"]}" B="{pa["B"]}" '
                f'P="{pa["P"]}" S="{pa["S"]}"/>'
            )
            lines.append(
                f'    <PassB E="{pb["E"]}" B="{pb["B"]}" '
                f'P="{pb["P"]}" S="{pb["S"]}"/>'
            )
            lines.append('  </DriftMeasure>')
        lines.append('</DriftLog>')
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# DriftManager — session-level registry, one per arc session
# ---------------------------------------------------------------------------

class DriftManager:
    """
    Manages ArcHistory and ArcDriftLog for all active cultivars.
    One instance lives alongside the Flask app (like the field object).

    Usage in mccf_api.py:
        from mccf_drift import DriftManager
        drift_manager = DriftManager()

    Then in /arc/record:
        drift_result = drift_manager.record_and_measure(
            cultivar=cultivar,
            step=step,
            response=response,
            lambda_val=cultivar_registry.get_lambda(cultivar),
            channel_vector=channel_result,
        )
        # drift_result.to_dict() added to endpoint response
    """

    def __init__(self):
        self._histories: dict[str, ArcHistory] = {}
        self._logs: dict[str, ArcDriftLog] = {}

    def _get_history(self, cultivar: str, lambda_val: float) -> ArcHistory:
        if cultivar not in self._histories:
            self._histories[cultivar] = ArcHistory(
                cultivar=cultivar,
                lambda_val=lambda_val,
            )
        else:
            # Update λ if cultivar slider was changed mid-session
            self._histories[cultivar].lambda_val = lambda_val
        return self._histories[cultivar]

    def _get_log(self, cultivar: str) -> ArcDriftLog:
        if cultivar not in self._logs:
            self._logs[cultivar] = ArcDriftLog(cultivar=cultivar)
        return self._logs[cultivar]

    def record_and_measure(self,
                           cultivar: str,
                           step: int,
                           response: str,
                           channel_vector: dict,
                           lambda_val: float = 0.72) -> DriftMeasure:
        """
        Core method. Call once per /arc/record invocation.

        1. Retrieves (or creates) ArcHistory for this cultivar.
        2. Computes Δ_t using current history state.
        3. Records the response into history (AFTER measuring —
           history does not include the current step when measuring it).
        4. Logs the DriftMeasure.
        5. Returns DriftMeasure for inclusion in endpoint response.
        """
        history = self._get_history(cultivar, lambda_val)
        log = self._get_log(cultivar)

        # Measure BEFORE recording (current response not in shadow context)
        measure = compute_drift(response, history, step)

        # Now record into history
        history.record(step, response, channel_vector)

        # Log
        log.record(measure)

        return measure

    def get_summary(self, cultivar: str) -> dict:
        log = self._logs.get(cultivar)
        return log.summary() if log else {"cultivar": cultivar, "measurements": []}

    def get_drift_xml(self, cultivar: str) -> str:
        log = self._logs.get(cultivar)
        return log.to_xml() if log else "<DriftLog/>"

    def reset_session(self, cultivar: str):
        """Call at arc start or when cultivar is reset."""
        if cultivar in self._histories:
            self._histories[cultivar].clear()
        if cultivar in self._logs:
            self._logs[cultivar] = ArcDriftLog(cultivar=cultivar)

    def all_summaries(self) -> list:
        return [self.get_summary(c) for c in self._logs]


# ---------------------------------------------------------------------------
# Patch instructions for mccf_api.py
# ---------------------------------------------------------------------------
#
# 1. Add at the top of mccf_api.py (with other imports):
#
#       from mccf_drift import DriftManager
#       from mccf_cultivar_lambda import CultivarRegistry
#       drift_manager = DriftManager()
#       cultivar_registry = CultivarRegistry()
#
# 2. In /arc/record, after the existing channel_vector computation and
#    before the return jsonify(...), add:
#
#       lambda_val = cultivar_registry.get_lambda(cultivar)
#       drift_result = drift_manager.record_and_measure(
#           cultivar=cultivar,
#           step=step,
#           response=response,
#           channel_vector=channel_result,   # whatever the existing var is
#           lambda_val=lambda_val,
#       )
#       # Then add to the existing response dict:
#       result["drift"]         = drift_result.delta_t
#       result["lambda"]        = drift_result.lambda_val
#       result["drift_interp"]  = drift_result.interpretation
#
# 3. Add new endpoint for drift summary (optional, for navigator panel):
#
#       @app.route("/arc/drift/<cultivar>", methods=["GET"])
#       def get_drift(cultivar):
#           return jsonify(drift_manager.get_summary(cultivar))
#
#       @app.route("/arc/drift/<cultivar>/reset", methods=["POST"])
#       def reset_drift(cultivar):
#           drift_manager.reset_session(cultivar)
#           return jsonify({"status": "reset", "cultivar": cultivar})
#
# ---------------------------------------------------------------------------
