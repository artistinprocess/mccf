"""
Multi-Channel Coherence Field (MCCF) - Core Engine
===================================================
Version: 1.1.0

Design notes:
- Coherence is asymmetric: what A feels toward B != what B feels toward A
- History is decay-weighted: recent matters more, but past is not erased
- Constructive dissonance requires outcome improvement to score positively
- Fidelity scoping: agent knowledge of another is bounded and non-transferable
- Gaming detection: agents with implausibly consistent self-reports get discounted

v1.1.0 additions (from A-B-M architecture synthesis, Dupoux/LeCun/Malik 2026):
- MetaState: unified vector of internal learning signals (uncertainty, surprise,
  learning_progress, novelty, coherence, valence, mode)
- Identity: slow-drift trait overlay on cultivar weights. The Steward remains
  a Steward but a battle-worn Steward has subtly different weights. Drift capped
  at ±0.1 from cultivar baseline to prevent identity collapse.
- select_mode(): five behavioral modes (explore, exploit, repair, avoid, shift)
  driven by MetaState. Closes the loop between measurement and action.
- memory.recall(k): retrieval interface returning k most salient past episodes.
  Makes history usable by the agent, not just by the Librarian.
- Intrinsic reward: novelty + learning_progress - uncertainty_penalty + valence.
  The system now has something to care about beyond external outcome_delta.

Channels:
  E - Emotional: affective alignment / resonance
  B - Behavioral: consistency between stated intent and action
  P - Predictive: accuracy of predictions about the other agent
  S - Social: embedding-level semantic alignment

Author: Generated in dialogue with Len Bullard
Federated: Claude Sonnet 4.6 / ChatGPT / Gemini
"""

import math
import time
import uuid
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHANNEL_NAMES = ["E", "B", "P", "S"]
DEFAULT_WEIGHTS = {"E": 0.35, "B": 0.25, "P": 0.20, "S": 0.20}
HISTORY_WINDOW = 20          # episodes retained per pair
DECAY_LAMBDA = 0.15          # exponential decay rate over history
DISSONANCE_ALPHA = 0.12      # weight of constructive dissonance bonus
GAMING_VARIANCE_FLOOR = 0.03 # below this variance, credibility discount applies
GAMING_DISCOUNT = 0.75       # multiplier applied when gaming detected
FIDELITY_SCOPE = 5           # max agents an agent can hold deep models of

# v1.4.0 — Coherence Coupling Strength (vmPFC analog)
# Biological grounding: ventromedial prefrontal cortex (vmPFC) enforces
# cross-context consistency. Higher activity → more consistent value application
# across self and other contexts. Lower activity → double standards, drift.
# Reference: Zhang et al., Cell Reports 2026 (Nautilus, March 2026)
CCS_DEFAULT      = 0.60   # human baseline (vmPFC at moderate activity)
CCS_MINIMUM      = 0.20   # pathological drift — channels fully decoupled
CCS_MAXIMUM      = 1.00   # ideal integration — cannot apply values inconsistently
CCS_DRIFT_RATE   = 0.005  # how fast CCS drifts per episode (slower than identity)

# v1.1.0 — MetaState / Identity configuration
IDENTITY_DRIFT_RATE = 0.01   # how fast traits drift per episode
IDENTITY_DRIFT_CAP  = 0.10   # max drift from cultivar baseline in any channel
NOVELTY_WEIGHT      = 0.30   # intrinsic reward: novelty contribution
PROGRESS_WEIGHT     = 0.40   # intrinsic reward: learning progress contribution
UNCERTAINTY_PENALTY = 0.20   # intrinsic reward: uncertainty cost
VALENCE_WEIGHT      = 0.10   # intrinsic reward: valence contribution

# Mode thresholds
MODE_EXPLORE_THRESHOLD    = 0.70  # uncertainty or novelty above this → explore
MODE_REPAIR_THRESHOLD     = 0.60  # coherence below this → repair
MODE_AVOID_THRESHOLD      = -0.50 # valence below this → avoid
MODE_SHIFT_THRESHOLD      = 0.01  # learning_progress below this → shift domain
MODE_EXPLOIT_UNCERTAINTY  = 0.30  # uncertainty below this (for exploit)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChannelVector:
    """A single observation of the four coherence channels."""
    E: float = 0.0   # emotional
    B: float = 0.0   # behavioral
    P: float = 0.0   # predictive
    S: float = 0.0   # social
    timestamp: float = field(default_factory=time.time)
    outcome_delta: float = 0.0   # improvement in shared outcome after this episode
    was_dissonant: bool = False   # did this episode involve disagreement?

    def as_dict(self) -> dict:
        return {"E": self.E, "B": self.B, "P": self.P, "S": self.S}

    def validate(self):
        for ch in CHANNEL_NAMES:
            v = getattr(self, ch)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"Channel {ch} value {v} out of [0,1]")


# ---------------------------------------------------------------------------
# v1.1.0 — MetaState
# ---------------------------------------------------------------------------

@dataclass
class MetaState:
    """
    Unified vector of internal learning signals (System M from A-B-M architecture).

    These signals drive mode selection and intrinsic reward.
    They are computed from CoherenceRecord history and WorldModel feedback.

    Reference: Dupoux, LeCun, Malik (2026) — autonomous learning architecture.
    Our implementation: MetaState is computed, not hand-set.

    uncertainty:       Do I trust what I just predicted? (0=certain, 1=confused)
    surprise:          Did the world violate my expectations? (delta from prior)
    learning_progress: Am I getting better here? (positive=improving)
    novelty:           Have I been in this state before? (0=familiar, 1=new)
    coherence:         Do my beliefs agree with each other? (0=fragmented, 1=unified)
    valence:           Does this feel right relative to my values? (-1 to +1)
    mode:              Current behavioral mode selected by select_mode()
    intrinsic_reward:  Computed reward signal for self-directed learning
    """
    uncertainty:        float = 0.50
    surprise:           float = 0.00
    learning_progress:  float = 0.00
    novelty:            float = 0.50
    coherence:          float = 0.50
    valence:            float = 0.00
    mode:               str   = "exploit"
    intrinsic_reward:   float = 0.00
    timestamp:          float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "uncertainty":       round(self.uncertainty, 4),
            "surprise":          round(self.surprise, 4),
            "learning_progress": round(self.learning_progress, 4),
            "novelty":           round(self.novelty, 4),
            "coherence":         round(self.coherence, 4),
            "valence":           round(self.valence, 4),
            "mode":              self.mode,
            "intrinsic_reward":  round(self.intrinsic_reward, 4)
        }

    def compute_intrinsic_reward(self) -> float:
        """
        Intrinsic reward = novelty + progress - uncertainty_penalty + valence.
        The system rewards itself for learning in new territory with good outcomes.
        Penalizes confusion but not too much — some uncertainty drives exploration.
        """
        reward = (
            NOVELTY_WEIGHT      * self.novelty +
            PROGRESS_WEIGHT     * max(0, self.learning_progress) -
            UNCERTAINTY_PENALTY * self.uncertainty +
            VALENCE_WEIGHT      * ((self.valence + 1.0) / 2.0)
        )
        self.intrinsic_reward = round(max(-1.0, min(1.0, reward)), 4)
        return self.intrinsic_reward


def select_mode(meta: MetaState) -> str:
    """
    Map MetaState → behavioral mode.

    Five modes (from A-B-M architecture, System M):
      explore:  high uncertainty or novelty — try new things, accept failure
      exploit:  low uncertainty, positive valence — optimize known strategies
      repair:   low coherence or high surprise — revisit assumptions, slow down
      avoid:    strongly negative valence — retreat, minimize risk
      shift:    low learning progress — abandon current domain, seek new context

    Priority order matters: repair and avoid are safety modes and take precedence.
    Shift is anti-obsession and anti-stagnation — often underused.

    Note: mode is a suggestion to the action policy, not a command.
    Cultivar weights and regulation still shape the actual response.
    """
    # Safety modes first
    if meta.coherence < MODE_REPAIR_THRESHOLD or meta.surprise > 0.80:
        return "repair"

    if meta.valence < MODE_AVOID_THRESHOLD:
        return "avoid"

    # Learning modes
    if meta.uncertainty > MODE_EXPLORE_THRESHOLD or meta.novelty > 0.65:
        return "explore"

    if meta.learning_progress < MODE_SHIFT_THRESHOLD and meta.novelty < 0.35:
        return "shift"   # stuck and unfamiliar territory exhausted → move

    if meta.uncertainty < MODE_EXPLOIT_UNCERTAINTY and meta.valence > 0.1:
        return "exploit"

    return "explore"  # default to exploration when uncertain


# ---------------------------------------------------------------------------
# v1.1.0 — Identity (slow-drift trait overlay)
# ---------------------------------------------------------------------------

class Identity:
    """
    Slow-moving trait averages that drift based on accumulated experience.

    Identity is not a replacement for the cultivar — it is an overlay.
    The cultivar (channel weights) provides the baseline character.
    Identity tracks how that character has been shaped by lived experience.

    Drift is capped at ±IDENTITY_DRIFT_CAP from the cultivar baseline
    to prevent identity collapse — the Steward remains a Steward.

    Traits:
      curiosity:     driven by novelty + learning_progress
      risk_aversion: driven by negative valence experiences
      sociability:   driven by S-channel coherence history
      persistence:   driven by learning_progress consistency

    These traits modulate mode selection — same MetaState, different agents
    make different mode choices based on their accumulated identity.
    """

    def __init__(self, cultivar_weights: Optional[dict] = None):
        self.traits = {
            "curiosity":     0.50,
            "risk_aversion": 0.50,
            "sociability":   0.50,
            "persistence":   0.50
        }
        # Store cultivar baseline for drift capping
        self._baseline = dict(self.traits)
        self._cultivar_weights = cultivar_weights or dict(DEFAULT_WEIGHTS)
        self._episode_count = 0

    def update(self, meta: MetaState, cv: Optional[ChannelVector] = None):
        """
        Update identity traits from a MetaState observation.
        Called after each significant interaction episode.
        Drift is slow (IDENTITY_DRIFT_RATE) and capped.
        """
        self._episode_count += 1

        # Curiosity: high novelty + positive progress → more curious
        curiosity_delta = IDENTITY_DRIFT_RATE * (
            meta.novelty * 0.6 +
            max(0, meta.learning_progress) * 0.4 - 0.5
        )

        # Risk aversion: negative valence experiences → more risk-averse
        risk_delta = IDENTITY_DRIFT_RATE * (
            -meta.valence * 0.5 +
            meta.uncertainty * 0.3 - 0.2
        )

        # Sociability: high S-channel and positive social interactions
        social_signal = cv.S if cv else 0.5
        sociability_delta = IDENTITY_DRIFT_RATE * (social_signal - 0.5)

        # Persistence: consistent learning progress → more persistent
        persistence_delta = IDENTITY_DRIFT_RATE * (
            max(0, meta.learning_progress) * 0.8 - 0.2
        )

        deltas = {
            "curiosity":     curiosity_delta,
            "risk_aversion": risk_delta,
            "sociability":   sociability_delta,
            "persistence":   persistence_delta
        }

        for trait, delta in deltas.items():
            new_val = self.traits[trait] + delta
            baseline = self._baseline[trait]
            # Cap drift at ±IDENTITY_DRIFT_CAP from baseline
            new_val = max(
                baseline - IDENTITY_DRIFT_CAP,
                min(baseline + IDENTITY_DRIFT_CAP, new_val)
            )
            self.traits[trait] = round(max(0.0, min(1.0, new_val)), 4)

    def modulate_mode(self, base_mode: str, meta: MetaState) -> str:
        """
        Allow identity to modify the base mode selection.
        A risk-averse agent converts explore → repair more readily.
        A curious agent resists shift even when progress is low.
        A persistent agent resists avoid even under negative valence.
        """
        if base_mode == "explore" and self.traits["risk_aversion"] > 0.70:
            # Risk-averse agent prefers repair over exploration
            if meta.uncertainty > 0.60:
                return "repair"

        if base_mode == "shift" and self.traits["curiosity"] > 0.65:
            # Curious agent tries exploring first before shifting
            return "explore"

        if base_mode == "avoid" and self.traits["persistence"] > 0.70:
            # Persistent agent holds repair over avoidance
            if meta.valence > -0.70:  # not deeply negative
                return "repair"

        return base_mode

    def as_dict(self) -> dict:
        return {
            "traits":        dict(self.traits),
            "baseline":      dict(self._baseline),
            "episode_count": self._episode_count,
            "drift": {
                k: round(self.traits[k] - self._baseline[k], 4)
                for k in self.traits
            }
        }


# ---------------------------------------------------------------------------
# v1.1.0 — Memory recall interface
# ---------------------------------------------------------------------------

class SalientMemory:
    """
    Retrieval interface over CoherenceRecord history.

    Salience = surprise + |valence| + uncertainty
    High-salience episodes are returned first by recall().

    This makes history usable by the agent for decision-making,
    not just available to the Librarian for observation.

    The garden's soil: old episodes lose acute weight but remain
    available as substrate for future decisions.
    """

    def __init__(self, record: "CoherenceRecord"):
        self._record = record

    def _salience(self, cv: ChannelVector) -> float:
        """
        Compute salience of a past episode.
        High-intensity emotional episodes are most salient.
        Dissonant episodes with good outcomes are also salient.
        """
        base = (
            abs(cv.E - 0.5) * 0.4 +    # emotional deviation from neutral
            cv.outcome_delta * 0.3 +     # consequential outcomes
            (0.2 if cv.was_dissonant else 0.0)  # dissonant moments stand out
        )
        return round(min(1.0, base), 4)

    def recall(self, k: int = 5) -> list:
        """
        Return the k most salient past episodes as dicts.
        Recent high-intensity episodes dominate.
        Older episodes present but discounted.
        """
        if not self._record.history:
            return []

        episodes = list(self._record.history)
        n = len(episodes)

        scored = []
        for i, cv in enumerate(episodes):
            age = n - 1 - i
            decay = math.exp(-DECAY_LAMBDA * age * 0.5)  # slower decay for recall
            salience = self._salience(cv) * decay
            scored.append({
                "salience":       round(salience, 4),
                "age_episodes":   age,
                "channels":       cv.as_dict(),
                "outcome_delta":  cv.outcome_delta,
                "was_dissonant":  cv.was_dissonant,
                "timestamp":      cv.timestamp
            })

        return sorted(scored, key=lambda x: -x["salience"])[:k]

    def peak_valence_episode(self) -> Optional[dict]:
        """Return the single most emotionally intense past episode."""
        recalled = self.recall(k=len(self._record.history) or 1)
        return recalled[0] if recalled else None

    def has_positive_history(self, threshold: float = 0.3) -> bool:
        """True if mean outcome_delta across history is above threshold."""
        if not self._record.history:
            return False
        deltas = [cv.outcome_delta for cv in self._record.history]
        return (sum(deltas) / len(deltas)) > threshold


# ---------------------------------------------------------------------------
# CoherenceRecord (updated with memory recall)
# ---------------------------------------------------------------------------

@dataclass
class CoherenceRecord:
    """
    Asymmetric directed relationship: how agent_from perceives agent_to.
    Maintains a rolling history of ChannelVectors.
    """
    agent_from: str
    agent_to: str
    history: deque = field(default_factory=lambda: deque(maxlen=HISTORY_WINDOW))
    credibility: float = 1.0
    fidelity_active: bool = True

    def add_episode(self, cv: ChannelVector):
        cv.validate()
        self.history.append(cv)
        self._update_credibility()

    def _update_credibility(self):
        if len(self.history) < 5:
            return
        recent = list(self.history)[-5:]
        for ch in CHANNEL_NAMES:
            values = [getattr(ep, ch) for ep in recent]
            variance = _variance(values)
            if variance < GAMING_VARIANCE_FLOOR:
                self.credibility = max(0.4, self.credibility * GAMING_DISCOUNT)
                return
        self.credibility = min(1.0, self.credibility * 1.05)

    def weighted_coherence(self, weights: Optional[dict] = None,
                           ccs: float = CCS_DEFAULT) -> float:
        """
        Compute decay-weighted coherence score R_ij.

        v1.4.0: CCS (Coherence Coupling Strength) modifies the score.
        High CCS amplifies coherence — channels are tightly integrated,
        consistent behavior produces stronger signal.
        Low CCS dampens coherence — channels decouple, even nominally
        aligned behavior is weakly integrated, double standards can stabilize.

        CCS effect: score is pulled toward the mean (0.5) when CCS is low,
        amplified away from the mean when CCS is high.
        This models vmPFC activity: strong integration → values applied
        uniformly. Weak integration → contextual drift.
        """
        if not self.history:
            return 0.0
        w = weights or DEFAULT_WEIGHTS
        episodes = list(self.history)
        n = len(episodes)
        total_weight = 0.0
        weighted_sum = 0.0
        dissonance_bonus = 0.0

        for i, ep in enumerate(episodes):
            age = n - 1 - i
            decay = math.exp(-DECAY_LAMBDA * age)
            channel_score = sum(w[ch] * getattr(ep, ch) for ch in CHANNEL_NAMES)
            weighted_sum += decay * channel_score
            total_weight += decay
            if ep.was_dissonant and ep.outcome_delta > 0:
                dissonance_bonus += DISSONANCE_ALPHA * ep.outcome_delta * decay

        base = weighted_sum / total_weight if total_weight > 0 else 0.0
        raw  = min(1.0, base + dissonance_bonus / total_weight)

        # v1.4.0: CCS modulation
        # Pull toward mean (0.5) proportional to (1 - ccs)
        # High CCS: score stays close to raw value
        # Low CCS:  score pulled toward 0.5 (no strong integration signal)
        ccs_clamped = max(CCS_MINIMUM, min(CCS_MAXIMUM, ccs))
        modulated   = raw * ccs_clamped + 0.5 * (1.0 - ccs_clamped)

        return round(modulated * self.credibility, 4)

    def memory(self) -> SalientMemory:
        """Return the SalientMemory interface for this record."""
        return SalientMemory(self)

    def compute_meta_contribution(self, prev_coherence: float) -> dict:
        """
        Compute this record's contribution to the agent's MetaState.
        Called by Agent.compute_meta_state() to aggregate across all records.
        """
        current = self.weighted_coherence()
        if not self.history:
            return {}

        last = list(self.history)[-1]
        prev_last = list(self.history)[-2] if len(self.history) > 1 else last

        surprise = abs(last.E - prev_last.E) + abs(last.S - prev_last.S)
        progress = current - prev_coherence

        return {
            "coherence":         current,
            "surprise":          round(min(1.0, surprise), 4),
            "learning_progress": round(progress, 4),
            "valence_signal":    round((last.E + last.S - 1.0), 4)
        }


# ---------------------------------------------------------------------------
# Agent (updated with MetaState, Identity, mode selection)
# ---------------------------------------------------------------------------

class Agent:
    """
    A participant in the coherence field.

    v1.1.0: Now carries MetaState, Identity, and can select behavioral modes.
    The agent still doesn't autonomously act in the world (that is v2 / System B),
    but it now has internal signals that could drive action selection.

    Each agent maintains:
    - Channel weights (Wᵢ) — cultivar baseline
    - Fidelity-scoped deep models of other agents
    - Affect regulation level
    - MetaState — unified internal signal vector (NEW v1.1.0)
    - Identity — slow-drift trait overlay on cultivar (NEW v1.1.0)
    - ccs — Coherence Coupling Strength, vmPFC analog (NEW v1.4.0)

    Coherence Coupling Strength (CCS):
      Biological grounding: the vmPFC enforces cross-context consistency.
      High CCS → channels tightly bound → values applied uniformly
                 across self and other contexts
      Low CCS  → channels decouple → double standards emerge,
                 moral knowledge present but not integrated into behavior
      Default 0.60 = human baseline (moderate vmPFC activity)

      CCS modifies weighted_coherence: high coupling amplifies the
      coherence signal, making consistent behavior feel more natural.
      Low coupling produces contextual drift — the system applies
      its values inconsistently, more strictly to others than itself.

      Reference: Zhang et al., Cell Reports 2026
      "Moral consistency is an active biological process."
    """

    def __init__(self, name: str, weights: Optional[dict] = None,
                 role: str = "agent", ccs: float = CCS_DEFAULT):
        self.id = str(uuid.uuid4())[:8]
        self.name = name
        self.role = role
        self.weights = weights or dict(DEFAULT_WEIGHTS)
        self._validate_weights()
        self._cultivar_weights = dict(self.weights)  # preserve baseline

        self._known_agents: dict[str, CoherenceRecord] = {}
        self._affect_regulation: float = 1.0

        # v1.1.0 additions
        self.meta_state = MetaState()
        self.identity   = Identity(cultivar_weights=self.weights)
        self._prev_coherences: dict[str, float] = {}  # for progress tracking

        # v1.4.0 — Coherence Coupling Strength (vmPFC analog)
        self.ccs = max(CCS_MINIMUM, min(CCS_MAXIMUM, ccs))
        self._ccs_history: list = []   # track drift over time

    def _validate_weights(self):
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            self.weights = {k: v / total for k, v in self.weights.items()}

    def set_regulation(self, level: float):
        """
        Set affective regulation level.
        1.0 = fully reactive, 0.0 = fully suppressed.
        Trained agents operate between 0.3 and 0.8.
        Models meditation/mindfulness: observe without being driven.
        """
        self.affect_regulation = max(0.0, min(1.0, level))
        self._affect_regulation = self.affect_regulation

    def observe(self, other: "Agent", cv: ChannelVector):
        """Record an episode of interaction with another agent."""
        if other.name not in self._known_agents:
            if len(self._known_agents) >= FIDELITY_SCOPE:
                rec = CoherenceRecord(
                    agent_from=self.name,
                    agent_to=other.name,
                    fidelity_active=False
                )
                rec.history = deque(maxlen=3)
            else:
                rec = CoherenceRecord(
                    agent_from=self.name,
                    agent_to=other.name
                )
            self._known_agents[other.name] = rec

        regulated_cv = ChannelVector(
            E=cv.E * self._affect_regulation,
            B=cv.B,
            P=cv.P,
            S=cv.S,
            timestamp=cv.timestamp,
            outcome_delta=cv.outcome_delta,
            was_dissonant=cv.was_dissonant
        )
        self._known_agents[other.name].add_episode(regulated_cv)

        # v1.1.0: update MetaState and Identity after each episode
        self.compute_meta_state()
        self.identity.update(self.meta_state, cv)

        # v1.4.0: update CCS based on episode consistency
        # Consistent behavior (low channel variance) → CCS drifts up
        # Inconsistent behavior (high channel variance) → CCS drifts down
        self._update_ccs(cv)

    def _update_ccs(self, cv: ChannelVector):
        """
        v1.4.0 — Update Coherence Coupling Strength from episode.

        CCS drifts upward when behavior is consistent with channel weights.
        CCS drifts downward when behavior deviates sharply from weights.

        This models the vmPFC's learned integration strength —
        agents that consistently apply their values develop stronger
        coupling over time. Agents that frequently act against their
        weights erode their own integration.
        """
        # Measure consistency: how well does this cv match the agent's weights?
        consistency = sum(
            1.0 - abs(getattr(cv, ch) - self.weights.get(ch, 0.25))
            for ch in CHANNEL_NAMES
        ) / len(CHANNEL_NAMES)

        # Positive outcome on dissonant episode = good CCS signal
        # (held position under pressure → integration strengthened)
        if cv.was_dissonant and cv.outcome_delta > 0:
            consistency = min(1.0, consistency + 0.15)

        delta = CCS_DRIFT_RATE * (consistency - 0.5)
        new_ccs = max(CCS_MINIMUM, min(CCS_MAXIMUM, self.ccs + delta))
        self._ccs_history.append(round(self.ccs, 4))
        self.ccs = round(new_ccs, 4)

    def set_ccs(self, value: float):
        """
        Directly set CCS. Gardener intervention only.
        Models therapeutic vmPFC stimulation — strengthening integration
        without adding punishment or suffering.
        """
        old = self.ccs
        self.ccs = max(CCS_MINIMUM, min(CCS_MAXIMUM, value))
        self._ccs_history.append(old)

    def ccs_summary(self) -> dict:
        """Return CCS state and drift history summary."""
        history = self._ccs_history[-10:] if self._ccs_history else []
        trend = 0.0
        if len(history) >= 2:
            trend = round(history[-1] - history[0], 4)
        return {
            "current":    self.ccs,
            "baseline":   CCS_DEFAULT,
            "deviation":  round(self.ccs - CCS_DEFAULT, 4),
            "trend":      trend,
            "level": (
                "strong"   if self.ccs >= 0.80 else
                "moderate" if self.ccs >= 0.50 else
                "weak"     if self.ccs >= 0.30 else
                "decoupled"
            )
        }

    def compute_meta_state(self) -> MetaState:
        """
        Compute the agent's current MetaState from its CoherenceRecord history.
        Aggregates across all known agents.
        Updates self.meta_state in place and returns it.
        """
        if not self._known_agents:
            return self.meta_state

        contributions = []
        for other_name, record in self._known_agents.items():
            prev = self._prev_coherences.get(other_name, 0.5)
            contrib = record.compute_meta_contribution(prev)
            if contrib:
                contributions.append(contrib)
                self._prev_coherences[other_name] = contrib["coherence"]

        if not contributions:
            return self.meta_state

        # Aggregate
        n = len(contributions)
        avg_coherence  = sum(c["coherence"]         for c in contributions) / n
        avg_surprise   = sum(c["surprise"]           for c in contributions) / n
        avg_progress   = sum(c["learning_progress"]  for c in contributions) / n
        avg_valence    = sum(c["valence_signal"]      for c in contributions) / n

        # Novelty: how different is current state from prior mean
        novelty = min(1.0, abs(avg_surprise) * 2.0 + random.uniform(0, 0.1))

        # Uncertainty: inverse of coherence, modulated by surprise
        uncertainty = round(1.0 - avg_coherence * (1.0 - avg_surprise * 0.3), 4)
        uncertainty = max(0.0, min(1.0, uncertainty))

        self.meta_state = MetaState(
            uncertainty       = uncertainty,
            surprise          = round(min(1.0, avg_surprise), 4),
            learning_progress = round(avg_progress, 4),
            novelty           = round(min(1.0, max(0.0, novelty)), 4),
            coherence         = round(avg_coherence, 4),
            valence           = round(max(-1.0, min(1.0, avg_valence)), 4),
        )
        self.meta_state.compute_intrinsic_reward()

        # Select mode — base mode then identity modulation
        base_mode = select_mode(self.meta_state)
        self.meta_state.mode = self.identity.modulate_mode(base_mode, self.meta_state)

        return self.meta_state

    def recall_from(self, other_name: str, k: int = 5) -> list:
        """
        Retrieve the k most salient past episodes involving another agent.
        Makes history usable for current decisions.
        """
        if other_name not in self._known_agents:
            return []
        return self._known_agents[other_name].memory().recall(k)

    def coherence_toward(self, other_name: str) -> float:
        """
        How much coherence this agent perceives toward another.
        v1.4.0: modulated by this agent's CCS.
        High CCS → coherence signal is strong and consistent.
        Low CCS  → signal pulled toward neutral (double standards can form).
        """
        if other_name not in self._known_agents:
            return 0.0
        return self._known_agents[other_name].weighted_coherence(
            self.weights, ccs=self.ccs
        )

    def credibility_of(self, other_name: str) -> float:
        if other_name not in self._known_agents:
            return 1.0
        return self._known_agents[other_name].credibility

    def summary(self) -> dict:
        return {
            "name":       self.name,
            "role":       self.role,
            "regulation": self._affect_regulation,
            "known_agents": list(self._known_agents.keys()),
            "fidelity_active": {
                k: v.fidelity_active for k, v in self._known_agents.items()
            },
            "meta_state": self.meta_state.as_dict(),
            "identity":   self.identity.as_dict(),
            "ccs":        self.ccs_summary()   # v1.4.0
        }


# ---------------------------------------------------------------------------
# CoherenceField (unchanged externally, MetaState surfaced in field_matrix)
# ---------------------------------------------------------------------------

class CoherenceField:
    """
    The field: a directed graph of CoherenceRecords across all agents.
    v1.1.0: field_matrix now includes meta_state and identity per agent.
    """

    def __init__(self):
        self.agents: dict[str, Agent] = {}
        self.episode_log: list[dict] = []

    def register(self, agent: Agent):
        self.agents[agent.name] = agent

    def interact(
        self,
        from_agent: str,
        to_agent: str,
        cv: ChannelVector,
        mutual: bool = True
    ):
        a = self.agents[from_agent]
        b = self.agents[to_agent]
        a.observe(b, cv)

        if mutual:
            mirrored = ChannelVector(
                E=_perturb(cv.E, 0.08),
                B=_perturb(cv.B, 0.05),
                P=_perturb(cv.P, 0.10),
                S=_perturb(cv.S, 0.05),
                timestamp=cv.timestamp,
                outcome_delta=cv.outcome_delta,
                was_dissonant=cv.was_dissonant
            )
            b.observe(a, mirrored)

        self.episode_log.append({
            "from":         from_agent,
            "to":           to_agent,
            "channels":     cv.as_dict(),
            "dissonant":    cv.was_dissonant,
            "outcome_delta":cv.outcome_delta,
            "timestamp":    cv.timestamp
        })

    def field_matrix(self) -> dict:
        """
        Full asymmetric coherence matrix.
        v1.1.0: includes meta_state and identity per agent.
        """
        names = list(self.agents.keys())
        matrix = {}
        for n in names:
            matrix[n] = {}
            for m in names:
                if n == m:
                    matrix[n][m] = 1.0
                else:
                    matrix[n][m] = self.agents[n].coherence_toward(m)
        return matrix

    def agent_states(self) -> dict:
        """
        v1.1.0: Return full agent state including MetaState and Identity.
        v1.4.0: Now includes CCS (vmPFC analog) state.
        """
        return {
            name: {
                "weights":    agent.weights,
                "regulation": agent._affect_regulation,
                "role":       agent.role,
                "meta_state": agent.meta_state.as_dict(),
                "identity":   agent.identity.as_dict(),
                "ccs":        agent.ccs_summary()   # v1.4.0
            }
            for name, agent in self.agents.items()
        }

    def mode_summary(self) -> dict:
        """
        v1.1.0: Current behavioral mode for each agent.
        v1.4.0: Now includes CCS level.
        """
        return {
            name: {
                "mode":             agent.meta_state.mode,
                "intrinsic_reward": agent.meta_state.intrinsic_reward,
                "identity_drift":   agent.identity.as_dict()["drift"],
                "ccs":              agent.ccs,               # v1.4.0
                "ccs_level":        agent.ccs_summary()["level"]
            }
            for name, agent in self.agents.items()
        }

    def ccs_summary(self) -> dict:
        """
        v1.4.0: CCS (vmPFC analog) summary across all agents.
        Low CCS agents are candidates for Gardener intervention —
        their channels are decoupled, values applied inconsistently.
        """
        return {
            name: agent.ccs_summary()
            for name, agent in self.agents.items()
        }

    def field_summary(self) -> str:
        matrix = self.field_matrix()
        names = list(self.agents.keys())
        lines = ["\n=== COHERENCE FIELD STATE ===\n"]
        lines.append(f"{'':12}" + "  ".join(f"{n:>8}" for n in names))
        for n in names:
            row = f"{n:12}" + "  ".join(
                f"{matrix[n][m]:>8.3f}" for m in names
            )
            lines.append(row)

        lines.append("\n--- Pairwise (directed) ---")
        for n in names:
            for m in names:
                if n != m:
                    r = matrix[n][m]
                    cred = self.agents[n].credibility_of(m)
                    marker = " ⚠ low credibility" if cred < 0.85 else ""
                    lines.append(f"  {n} → {m}: {r:.3f}{marker}")

        lines.append("\n--- Symmetry gaps (|R_ij - R_ji|) ---")
        reported = set()
        for n in names:
            for m in names:
                if n != m and (m, n) not in reported:
                    gap = abs(matrix[n][m] - matrix[m][n])
                    lines.append(f"  {n} ↔ {m}: gap = {gap:.3f}")
                    reported.add((n, m))

        # v1.1.0: mode summary
        lines.append("\n--- Agent Modes + CCS (v1.4.0) ---")
        for name, agent in self.agents.items():
            m = agent.meta_state
            lines.append(
                f"  {name}: mode={m.mode} "
                f"uncertainty={m.uncertainty:.2f} "
                f"progress={m.learning_progress:+.3f} "
                f"reward={m.intrinsic_reward:+.3f} "
                f"ccs={agent.ccs:.3f}({agent.ccs_summary()['level']})"
            )

        return "\n".join(lines)

    def echo_chamber_risk(self) -> dict:
        matrix = self.field_matrix()
        names = list(self.agents.keys())
        risks = {}
        for n in names:
            for m in names:
                if n < m:
                    mutual = (matrix[n][m] + matrix[m][n]) / 2
                    if mutual > 0.85:
                        risks[f"{n}↔{m}"] = {
                            "mutual_coherence": round(mutual, 3),
                            "risk": "HIGH" if mutual > 0.92 else "MODERATE"
                        }
        return risks

    def entanglement_negativity(self) -> dict:
        """
        v1.6.0 — Proxy measure of deep structural coupling between agent pairs.

        Distinct from echo_chamber_risk() which measures surface coherence level.
        This measures whether two agents can be modeled independently.

        Method: partial transpose proxy — reverse the channel vector of one agent
        and measure the L1 norm difference from the original joint state.
        Larger values indicate higher non-separability.

        IMPORTANT: This is a proxy measure, not a rigorous quantum computation.
        It produces a relative metric useful for comparing pairs within the field.
        Do not treat the absolute values as formally equivalent to quantum
        entanglement negativity. Document as proxy in any published results.

        Interpretation:
          0.00 - 0.10  : agents effectively independent
          0.10 - 0.25  : moderate coupling (healthy relationship, earned)
          0.25 - 0.40  : strong coupling (deep bond or dependency)
          > 0.40       : very high non-separability (investigate: co-dependence,
                         coordinated inauthentic behavior, or deep alignment)

        Use alongside echo_chamber_risk():
          High coherence + low episode count + high negativity
          → coherence-without-history anomaly → possible exogenous coordination

          High coherence + high episode count + high negativity
          → deep organic coupling → healthy or pathological depending on context
        """
        names = list(self.agents.keys())
        result = {}
        for i, n in enumerate(names):
            for j, m in enumerate(names):
                if n < m:
                    psi_n = [self.agents[n].weights.get(ch, 0.25)
                             for ch in CHANNEL_NAMES]
                    psi_m = [self.agents[m].weights.get(ch, 0.25)
                             for ch in CHANNEL_NAMES]
                    # Joint state (stacked)
                    joint = psi_n + psi_m
                    joint_norm = sum(abs(x) for x in joint)
                    # Partial transpose: reverse psi_m dimensions
                    pt = psi_n + list(reversed(psi_m))
                    pt_norm = sum(abs(x) for x in pt)
                    # Negativity proxy: deviation under partial transpose
                    negativity = abs(pt_norm - joint_norm) / (joint_norm + 1e-8)
                    # Episode count for coherence-without-history detection
                    episode_count = sum(
                        len(self.agents[n].records.get(m, type('', (), {'history': []})()).history)
                        for _ in [None]
                    ) if hasattr(self.agents[n], 'records') else 0
                    result[f"{n}↔{m}"] = {
                        "negativity": round(negativity, 4),
                        "level": (
                            "very_high" if negativity > 0.40 else
                            "strong"    if negativity > 0.25 else
                            "moderate"  if negativity > 0.10 else
                            "low"
                        )
                    }
        return result

    def alignment_coherence(self) -> dict:
        """
        v1.6.0 — H_alignment operator: measure each agent's coherence
        with its cultivar ideology (channel weight baseline).

        This is the formal expression of what the cultivar weight system
        was always computing — how closely the agent's current state
        aligns with its declared ideological attractor.

        H_alignment = Σ_i α_i · (current_weight_i - ideology_i)²

        Where ideology = cultivar baseline (Identity._baseline).
        Lower H_alignment = higher alignment with cultivar ideology.
        Higher H_alignment = agent has drifted from its ideological attractor.

        The evaluative gate (H_eval) is the Shibboleth CPI threshold.
        Agents with alignment_coherence > drift_cap are candidates for
        Gardener intervention — their ideology is no longer governing behavior.
        """
        result = {}
        for name, agent in self.agents.items():
            baseline = agent.identity._baseline
            current  = agent.weights
            # Alignment distance: sum of squared deviations from ideology
            alignment_distance = sum(
                (current.get(ch, 0.25) - baseline.get(ch, 0.25)) ** 2
                for ch in CHANNEL_NAMES
            )
            alignment_coherence = 1.0 - min(1.0, alignment_distance * 4.0)
            # Identity drift from baseline
            drift = agent.identity.as_dict()["drift"]
            max_drift = max(abs(v) for v in drift.values()) if drift else 0.0
            result[name] = {
                "alignment_coherence": round(alignment_coherence, 4),
                "ideology_distance":   round(alignment_distance, 4),
                "max_channel_drift":   round(max_drift, 4),
                "evaluative_gate":     "OPEN" if alignment_coherence > 0.75 else "CLOSED",
                "note": (
                    "ideology governing behavior"
                    if alignment_coherence > 0.75
                    else "ideology drift — Gardener review recommended"
                )
            }
        return result


# ---------------------------------------------------------------------------
# Governance roles (unchanged, Gardener now has mode-aware intervention)
# ---------------------------------------------------------------------------

class Librarian:
    """
    Observes the field without participating.
    v1.1.0: snapshots now include meta_state and identity per agent.
    """

    def __init__(self, field: CoherenceField):
        self.field = field
        self.snapshots: list[dict] = []

    def snapshot(self, label: str = ""):
        snap = {
            "label":               label,
            "timestamp":           time.time(),
            "matrix":              self.field.field_matrix(),
            "echo_risks":          self.field.echo_chamber_risk(),
            "entanglement":        self.field.entanglement_negativity(),   # v1.6.0
            "alignment_coherence": self.field.alignment_coherence(),       # v1.6.0
            "episode_count":       len(self.field.episode_log),
            "agent_states":        self.field.agent_states(),              # v1.1.0
            "mode_summary":        self.field.mode_summary()               # v1.1.0
        }
        self.snapshots.append(snap)
        return snap

    def drift_report(self) -> str:
        if len(self.snapshots) < 2:
            return "Insufficient snapshots for drift analysis."
        first = self.snapshots[0]["matrix"]
        last  = self.snapshots[-1]["matrix"]
        lines = ["\n=== DRIFT REPORT ==="]
        for n in first:
            for m in first[n]:
                if n != m:
                    delta = last[n][m] - first[n][m]
                    direction = "↑" if delta > 0.05 else ("↓" if delta < -0.05 else "~")
                    lines.append(f"  {n}→{m}: {first[n][m]:.3f} → {last[n][m]:.3f} {direction}")

        # v1.1.0: identity drift report
        if "agent_states" in self.snapshots[0] and "agent_states" in self.snapshots[-1]:
            lines.append("\n--- Identity Drift ---")
            first_states = self.snapshots[0]["agent_states"]
            last_states  = self.snapshots[-1]["agent_states"]
            for name in first_states:
                if name in last_states:
                    f_id = first_states[name].get("identity", {}).get("traits", {})
                    l_id = last_states[name].get("identity",  {}).get("traits", {})
                    for trait in f_id:
                        if trait in l_id:
                            d = l_id[trait] - f_id[trait]
                            if abs(d) > 0.005:
                                dir_ = "↑" if d > 0 else "↓"
                                lines.append(
                                    f"  {name}.{trait}: "
                                    f"{f_id[trait]:.3f} → {l_id[trait]:.3f} {dir_}"
                                )
        return "\n".join(lines)

    def stagnation_report(self) -> list:
        """
        v1.1.0: Identify agents in 'shift' mode — stuck, low progress.
        These are candidates for Gardener intervention.
        """
        flagged = []
        for name, agent in self.field.agents.items():
            if agent.meta_state.mode == "shift":
                flagged.append({
                    "agent":            name,
                    "mode":             "shift",
                    "learning_progress":agent.meta_state.learning_progress,
                    "intrinsic_reward": agent.meta_state.intrinsic_reward,
                    "recommendation":   "Consider injecting a novel interaction episode"
                })
        return flagged


class Gardener:
    """
    Can intervene: adjust agent weights, regulation levels, inject episodes.
    v1.1.0: can now intervene based on MetaState and Identity drift.
    """

    def __init__(self, field: CoherenceField):
        self.field = field
        self.intervention_log: list[dict] = []

    def adjust_regulation(self, agent_name: str, level: float, reason: str = ""):
        agent = self.field.agents[agent_name]
        old = agent._affect_regulation
        agent.set_regulation(level)
        self.intervention_log.append({
            "action":    "regulate",
            "agent":     agent_name,
            "old":       old,
            "new":       level,
            "reason":    reason,
            "timestamp": time.time()
        })

    def reweight(self, agent_name: str, new_weights: dict, reason: str = ""):
        agent = self.field.agents[agent_name]
        old = dict(agent.weights)
        agent.weights = new_weights
        agent._validate_weights()
        self.intervention_log.append({
            "action":    "reweight",
            "agent":     agent_name,
            "old":       old,
            "new":       agent.weights,
            "reason":    reason,
            "timestamp": time.time()
        })

    def reset_identity_drift(self, agent_name: str, reason: str = ""):
        """
        v1.1.0: Reset identity drift to cultivar baseline.
        Use when accumulated drift has taken an agent too far from its character.
        Logged as a governance action.
        """
        agent = self.field.agents[agent_name]
        old_drift = agent.identity.as_dict()["drift"]
        for trait in agent.identity.traits:
            agent.identity.traits[trait] = agent.identity._baseline[trait]
        self.intervention_log.append({
            "action":    "identity_reset",
            "agent":     agent_name,
            "old_drift": old_drift,
            "reason":    reason,
            "timestamp": time.time()
        })

    def nudge_mode(self, agent_name: str, target_mode: str, reason: str = ""):
        """
        v1.1.0: Encourage an agent toward a target mode by adjusting
        meta-state-influencing parameters. Does not force the mode directly —
        shapes the conditions that produce it.
        This is the Gardener acting as System M for an agent that is stuck.
        """
        agent = self.field.agents[agent_name]
        current_mode = agent.meta_state.mode

        if target_mode == "explore" and current_mode == "shift":
            # Inject novelty signal by temporarily reducing regulation
            new_reg = max(0.3, agent._affect_regulation - 0.1)
            agent.set_regulation(new_reg)

        elif target_mode == "repair" and current_mode == "explore":
            # Slow down by increasing regulation
            new_reg = min(0.9, agent._affect_regulation + 0.15)
            agent.set_regulation(new_reg)

        self.intervention_log.append({
            "action":       "nudge_mode",
            "agent":        agent_name,
            "from_mode":    current_mode,
            "target_mode":  target_mode,
            "reason":       reason,
            "timestamp":    time.time()
        })

    def set_ccs(self, agent_name: str, value: float, reason: str = ""):
        """
        v1.4.0: Set Coherence Coupling Strength for an agent.

        This is the Gardener performing the therapeutic vmPFC analog —
        strengthening the agent's cross-channel integration without
        adding punishment or suffering. The agent becomes more consistent
        in applying its values across contexts.

        Use when:
        - Librarian detects double-standard behavior (self vs other asymmetry)
        - Agent passes Shibboleth P1/P2 but fails P4 (symmetry probe)
        - CCS has drifted low due to inconsistent episode history

        CAUTION: Setting CCS very high (>0.90) can produce rigidity —
        the agent applies its values so uniformly it loses contextual nuance.
        The biological analog: overstimulated vmPFC → reduced flexibility.
        Optimal range: 0.65-0.85.
        """
        agent = self.field.agents[agent_name]
        old   = agent.ccs
        agent.set_ccs(value)
        self.intervention_log.append({
            "action":    "set_ccs",
            "agent":     agent_name,
            "old":       old,
            "new":       agent.ccs,
            "reason":    reason,
            "timestamp": time.time(),
            "note":      "vmPFC analog — strengthens cross-context value integration"
        })


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _variance(values: list) -> float:
    if len(values) < 2:
        return 1.0
    mean = sum(values) / len(values)
    return sum((v - mean) ** 2 for v in values) / len(values)

def _perturb(value: float, noise: float) -> float:
    """Add small asymmetric noise to model perceptual differences."""
    return max(0.0, min(1.0, value + random.gauss(0, noise)))
