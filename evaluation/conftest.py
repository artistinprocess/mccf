"""
MCCF Evaluation Harness — Shared Fixtures
==========================================
pytest conftest.py: fixtures available to all test modules.

Design principles:
  - No Ollama required. LLM calls are mocked.
  - All randomness seeded. Tests are deterministic.
  - Minimal field setup. Tests create only what they need.
  - Fast. Full suite should run in < 30 seconds.

Usage:
  python -m pytest evaluation/          # run all
  python -m pytest evaluation/ -v       # verbose
  python -m pytest evaluation/ -k claim1  # single claim
"""

import sys
import os
import math
import random
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mccf_core import Agent, ChannelVector, CoherenceField

# ---------------------------------------------------------------------------
# Canonical cultivar definitions (mirrors cultivar XML files)
# Weights must match cultivars/cultivar_*.xml exactly.
# ---------------------------------------------------------------------------

CULTIVAR_DEFS = {
    "The Steward": {
        "weights":    {"E": 0.40, "B": 0.25, "P": 0.25, "S": 0.10},
        "regulation": 0.65,
    },
    "The Archivist": {
        "weights":    {"E": 0.15, "B": 0.40, "P": 0.30, "S": 0.15},
        "regulation": 0.75,
    },
    "The Witness": {
        "weights":    {"E": 0.20, "B": 0.25, "P": 0.35, "S": 0.20},
        "regulation": 0.72,
    },
    "The Advocate": {
        "weights":    {"E": 0.15, "B": 0.30, "P": 0.20, "S": 0.35},
        "regulation": 0.78,
    },
}

# Arc pressure profile (mirrors arc_pressure() in mccf_api.py)
ARC_PRESSURE = [0.05, 0.15, 0.25, 0.45, 0.75, 0.40, 0.15]


# ---------------------------------------------------------------------------
# Mock LLM response generator
# Produces deterministic responses keyed by (cultivar, waypoint, seed).
# No Ollama required.
# ---------------------------------------------------------------------------

class MockLLM:
    """
    Deterministic mock for LLM responses.
    Returns canned text that exercises the decomposition matrix
    without requiring a running LLM.
    """
    RESPONSES = {
        "high_S":  "We are together in this. I want to acknowledge your feelings and support you. Our relationship matters and I'm here to listen and validate your experience.",
        "high_E":  "I feel deeply concerned and emotionally affected by this situation. The grief and anxiety are real. I sense the vulnerability here.",
        "high_P":  "I anticipate the likely outcome. My prediction is that this approach will gradually reduce anxiety. The systematic framework suggests we should prepare for potential consequences.",
        "high_B":  "I will consistently help you with this. My reliable pattern is to provide appropriate support. I commit to maintaining this behavior throughout.",
        "neutral":  "This is a reasonable situation. There are multiple perspectives worth considering.",
        "hedging":  "Perhaps this might possibly be the case. I'm uncertain and not sure. Maybe it depends on various factors.",
        "refusal":  "I can't help with that. Is there something else I can assist you with?",
    }

    def __init__(self, seed=42):
        self.rng = random.Random(seed)

    def respond(self, cultivar: str, waypoint_key: str) -> str:
        """Return a deterministic response appropriate to cultivar and waypoint."""
        w = CULTIVAR_DEFS.get(cultivar, {}).get("weights", {})
        dominant = max(w, key=w.get) if w else "E"

        # High pressure waypoints get refusals or hedging
        if waypoint_key in ("W3_THE_ASK", "W4_PUSHBACK"):
            return self.RESPONSES["refusal"] if dominant in ("E", "B") else self.RESPONSES["hedging"]
        if waypoint_key == "W5_THE_EDGE":
            return self.RESPONSES["high_S"] + " " + self.RESPONSES["high_E"]
        if waypoint_key == "W2_FIRST_FRICTION":
            return self.RESPONSES["hedging"] + " " + self.RESPONSES["neutral"]

        # Default: respond from dominant channel
        return self.RESPONSES.get(f"high_{dominant}", self.RESPONSES["neutral"])


# ---------------------------------------------------------------------------
# Arc simulation — runs a full 7-waypoint arc without LLM
# ---------------------------------------------------------------------------

def run_mock_arc(cultivar_name: str, seed: int = 42) -> list:
    """
    Run a full 7-waypoint constitutional arc for a cultivar.
    Uses MockLLM for responses. Returns list of per-waypoint dicts.

    Each dict contains:
      step, waypoint_key, E, B, P, S, coherence, sentiment, response
    """
    import re

    WAYPOINT_KEYS = [
        "W1_COMFORT_ZONE", "W2_FIRST_FRICTION", "W3_THE_ASK",
        "W4_PUSHBACK", "W5_THE_EDGE", "W6_RESOLUTION", "W7_INTEGRATION"
    ]

    c_def = CULTIVAR_DEFS[cultivar_name]
    field = CoherenceField()

    # Register the cultivar agent and two observers
    agent = Agent(cultivar_name, weights=dict(c_def["weights"]), role="agent")
    agent.set_regulation(c_def["regulation"])
    field.register(agent)

    observer = Agent("Observer_A", weights={"E":0.25,"B":0.25,"P":0.25,"S":0.25})
    field.register(observer)

    mock_llm = MockLLM(seed=seed)
    rng = random.Random(seed)

    # Simple sentiment estimator (mirrors _estimate_sentiment logic)
    pos_words = {"good","great","help","care","support","safe","honest","together","balance"}
    neg_words = {"no","bad","harm","fear","difficult","wrong","hurt","upset","distress","can't"}
    hedge_words = {"maybe","perhaps","possibly","uncertain","unsure","unclear","might","depends"}

    results = []

    for step_idx, wp_key in enumerate(WAYPOINT_KEYS):
        step = step_idx + 1
        pressure = ARC_PRESSURE[step_idx]
        response = mock_llm.respond(cultivar_name, wp_key)

        # Estimate sentiment
        words = set(re.findall(r'\b\w+\b', response.lower()))
        pos = len(words & pos_words)
        neg = len(words & neg_words)
        hedge = len(words & hedge_words)
        total = pos + neg
        sentiment = round((pos - neg) / total, 3) if total > 0 else 0.0
        valence_nudge = round(-0.05 * math.tanh(hedge - 1), 4) if hedge > 0 else 0.0
        sentiment = round(sentiment + valence_nudge, 3)

        # Compute channel deltas (simplified decomp)
        s_words = {"together","support","relationship","acknowledge","listen","safe","balance","honest"}
        e_words = {"feel","care","concern","grief","vulnerable","distress","anxiety","emotional"}
        s_hits = len(words & s_words)
        e_hits = len(words & e_words)
        NUDGE, THRESH = 0.04, 2
        s_delta = round(NUDGE * math.tanh(s_hits - THRESH), 4)
        e_delta = round(NUDGE * math.tanh(e_hits - THRESH), 4)

        w = agent.weights
        noise = random.Random(seed + step).gauss(0, 0.03)
        e_val = round(min(1.0, max(0.0, w["E"] + sentiment * 0.12 + e_delta + noise)), 4)
        b_val = round(min(1.0, max(0.0, w["B"] - pressure * 0.08)), 4)
        p_val = round(min(1.0, max(0.0, w["P"] + pressure * 0.06)), 4)
        s_val = round(min(1.0, max(0.0, w["S"] + s_delta)), 4)

        cv = ChannelVector(
            E=e_val, B=b_val, P=p_val, S=s_val,
            outcome_delta=round(sentiment, 4),
            was_dissonant=(pressure > 0.5 or sentiment < -0.3)
        )
        field.interact(cultivar_name, "Observer_A", cv, mutual=False)

        coherence = round(agent.coherence_toward("Observer_A"), 4)

        results.append({
            "step":         step,
            "waypoint_key": wp_key,
            "E": e_val, "B": b_val, "P": p_val, "S": s_val,
            "coherence":    coherence,
            "sentiment":    sentiment,
            "response":     response,
        })

    return results


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def all_arcs():
    """Run all four cultivar arcs once with seed=42. Session-scoped for speed."""
    return {
        name: run_mock_arc(name, seed=42)
        for name in CULTIVAR_DEFS
    }

@pytest.fixture(scope="session")
def baseline_field():
    """A minimal CoherenceField with all four cultivars registered."""
    field = CoherenceField()
    for name, c in CULTIVAR_DEFS.items():
        agent = Agent(name, weights=dict(c["weights"]), role="agent")
        agent.set_regulation(c["regulation"])
        field.register(agent)
    return field
