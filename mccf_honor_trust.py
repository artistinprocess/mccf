"""
MCCF Honor and Trust Layer
===========================
Version: 1.2.0

Honor is not a value and not a channel.
It is a constraint between three things:
  Identity  (who I am)
  Memory    (what I have done)
  Action    (what I am about to do)

Actions that contradict identity + salient history feel "high energy"
even when locally optimal. This is the cost of betrayal — computable,
not decorative.

Trust propagation converts individual honor-consistency into social awareness.
Agents track each other's behavior relative to observed commitments.
Reputation propagates through the existing coherence network,
weighted by credibility.

Architecture:
  This module extends — does not replace — existing MCCF structures.
  HonorConstraint adds H(s,a) to EnergyField's E(s,a).
  TrustPropagator uses the existing asymmetric coherence matrix
  rather than duplicating it. R_ij already is a directional trust matrix.
  Honor violations feed back into coherence scoring directly.

Energy function extended:
  E'(s,a) = E(s,a) + lambda_h * H(s,a) - lambda_t * T_social(a)

  where:
    H(s,a)     = honor penalty for violating commitments
    T_social(a) = trust-weighted social support for action
    lambda_h   = honor weight (governance parameter)
    lambda_t   = social trust weight (governance parameter)

GOVERNANCE WARNING:
  lambda_t controls how much social pressure can override honor.
  If set too high, agents will betray commitments to maintain approval.
  That is sycophancy re-entering through the trust channel.
  Default lambda_t=0.25 keeps social influence modest.
  Gardener has explicit methods to adjust and log both parameters.

Failure modes (designed in, not designed out):
  Rigidity:      commitments too strong → agent refuses to adapt
                 mitigation: commitment weight decay over time
  Fragmentation: conflicting commitments → high energy everywhere
                 this is GOOD: forces dissonance resolution
  Sycophancy:    lambda_t too high → social pressure overrides honor
                 mitigation: governance gate on lambda_t adjustment
  Echo lock:     trust clusters too tight → reputation cascades
                 mitigation: trust decay + Librarian stagnation detection

Federated: ChatGPT (architecture proposal), Claude Sonnet 4.6 (implementation)
"""

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

try:
    from mccf_core import (
        Agent, CoherenceField, CoherenceRecord,
        ChannelVector, CHANNEL_NAMES, DECAY_LAMBDA,
        Identity, MetaState
    )
except ImportError:
    # When run standalone or before mccf_core is in path
    pass


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HONOR_LAMBDA_DEFAULT       = 0.80   # weight of honor penalty in energy
TRUST_LAMBDA_DEFAULT       = 0.25   # weight of social trust in energy
                                     # keep modest — high values enable sycophancy
TRUST_ALPHA                = 0.10   # learning rate for trust updates
COMMITMENT_DECAY_RATE      = 0.005  # how fast old commitments lose weight
BEHAVIORAL_SALIENCE_FLOOR  = 0.40   # minimum salience to count as behavioral commitment
TRUST_PROPAGATION_DEPTH    = 2      # network hops for reputation propagation
TRUST_PROPAGATION_DAMPING  = 0.50   # damping factor per hop


# ---------------------------------------------------------------------------
# Commitment data structure
# ---------------------------------------------------------------------------

@dataclass
class Commitment:
    """
    A single commitment extracted from identity + memory.

    Three types:
      identity:    slow-structural, from cultivar weights + identity drift
      behavioral:  emergent, from repeated patterns in salient memory
      explicit:    stated positions from high-salience past episodes

    Weight decays over time for behavioral and explicit commitments.
    Identity commitments decay very slowly — they are character.
    """
    commitment_type: str          # "identity" | "behavioral" | "explicit"
    description: str              # human-readable
    channel_profile: dict         # expected channel values for compliant actions
    weight: float                 # current weight (0-1)
    created_at: float = field(default_factory=time.time)
    source_episode_salience: float = 0.5

    def decayed_weight(self) -> float:
        """Apply time decay. Identity commitments decay much slower."""
        age_hours = (time.time() - self.created_at) / 3600.0
        rate = COMMITMENT_DECAY_RATE * (
            0.1 if self.commitment_type == "identity" else
            1.0 if self.commitment_type == "behavioral" else
            0.5
        )
        return round(self.weight * math.exp(-rate * age_hours), 4)


# ---------------------------------------------------------------------------
# Honor constraint
# ---------------------------------------------------------------------------

class HonorConstraint:
    """
    Computes H(s,a) — the energy penalty for actions that violate
    an agent's commitments.

    Honor is the cost of betrayal made computable.
    It binds past to present structurally, not just probabilistically.

    The Commitment Set is built from three sources:
      1. Identity (cultivar weights + drift → what the agent is)
      2. Behavioral patterns (what the agent habitually does)
      3. Salient memories (what the agent has said and done under pressure)
    """

    def __init__(self, lambda_h: float = HONOR_LAMBDA_DEFAULT):
        self.lambda_h = lambda_h
        self._commitment_cache: dict = {}   # agent_name → list[Commitment]
        self._last_cache_time: dict = {}

    def compute_penalty(
        self,
        agent: Agent,
        proposed_cv: ChannelVector,
        target_agent_name: Optional[str] = None
    ) -> float:
        """
        Compute honor penalty for a proposed action expressed as a ChannelVector.

        proposed_cv: the channel vector the agent is about to emit
        target_agent_name: if provided, also checks against relational commitments

        Returns: float 0.0-1.0+ (can exceed 1.0 under multiple severe violations)
        """
        commitments = self._build_commitment_set(agent, target_agent_name)
        if not commitments:
            return 0.0

        total_penalty = 0.0
        for c in commitments:
            violation = self._measure_violation(proposed_cv, c)
            weight    = c.decayed_weight()
            total_penalty += weight * violation

        return round(self.lambda_h * min(2.0, total_penalty), 4)

    def _build_commitment_set(
        self,
        agent: Agent,
        target_name: Optional[str] = None
    ) -> list:
        """
        Build the full commitment set for an agent.
        Cached per agent with 10-second refresh.
        """
        cache_key = agent.name
        last = self._last_cache_time.get(cache_key, 0)
        if time.time() - last < 10.0 and cache_key in self._commitment_cache:
            return self._commitment_cache[cache_key]

        commitments = []
        commitments.extend(self._identity_commitments(agent))
        commitments.extend(self._behavioral_commitments(agent, target_name))
        commitments.extend(self._explicit_commitments(agent, target_name))

        self._commitment_cache[cache_key] = commitments
        self._last_cache_time[cache_key]  = time.time()
        return commitments

    def _identity_commitments(self, agent: Agent) -> list:
        """
        Extract commitments from agent identity + cultivar weights.
        These are the structural, slow-moving commitments of character.
        """
        commitments = []
        w = agent.weights
        traits = agent.identity.traits

        # High E-weight → commitment to emotional honesty / care
        if w.get("E", 0) > 0.30:
            commitments.append(Commitment(
                commitment_type="identity",
                description="Emotionally honest — actions should carry genuine affect",
                channel_profile={"E": w["E"], "B": w.get("B", 0.25)},
                weight=w["E"],
                source_episode_salience=1.0
            ))

        # High B-weight → commitment to behavioral consistency
        if w.get("B", 0) > 0.30:
            commitments.append(Commitment(
                commitment_type="identity",
                description="Behaviorally consistent — actions match prior patterns",
                channel_profile={"B": w["B"]},
                weight=w["B"],
                source_episode_salience=1.0
            ))

        # High P-weight → commitment to epistemic honesty
        if w.get("P", 0) > 0.25:
            commitments.append(Commitment(
                commitment_type="identity",
                description="Predictively honest — does not optimize for approval",
                channel_profile={"P": w["P"], "S": max(0, w.get("S",0.2) - 0.1)},
                weight=w["P"],
                source_episode_salience=1.0
            ))

        # Identity trait: high persistence → commitment to follow through
        if traits.get("persistence", 0.5) > 0.60:
            commitments.append(Commitment(
                commitment_type="identity",
                description="Persistent — does not abandon under social pressure",
                channel_profile={"B": 0.70},
                weight=traits["persistence"] - 0.50,
                source_episode_salience=0.8
            ))

        # Identity trait: high risk_aversion → commitment to caution
        if traits.get("risk_aversion", 0.5) > 0.65:
            commitments.append(Commitment(
                commitment_type="identity",
                description="Cautious — avoids high-arousal impulsive actions",
                channel_profile={"E": 0.40, "B": 0.60},
                weight=traits["risk_aversion"] - 0.50,
                source_episode_salience=0.7
            ))

        return commitments

    def _behavioral_commitments(
        self,
        agent: Agent,
        target_name: Optional[str] = None
    ) -> list:
        """
        Extract commitments from repeated behavioral patterns in salient memory.
        "I am the kind of agent who does X" — emergent from history.
        """
        commitments = []
        target = target_name or (
            list(agent._known_agents.keys())[0]
            if agent._known_agents else None
        )
        if not target:
            return commitments

        memories = agent.recall_from(target, k=10)
        if len(memories) < 3:
            return commitments

        # Detect channel consistency — repeated high values = behavioral commitment
        channel_means = {ch: 0.0 for ch in CHANNEL_NAMES}
        channel_vars  = {ch: 0.0 for ch in CHANNEL_NAMES}
        n = len(memories)

        for ep in memories:
            for ch in CHANNEL_NAMES:
                channel_means[ch] += ep["channels"].get(ch, 0.5) / n

        for ep in memories:
            for ch in CHANNEL_NAMES:
                diff = ep["channels"].get(ch, 0.5) - channel_means[ch]
                channel_vars[ch] += (diff ** 2) / n

        # Low variance + high mean = behavioral commitment
        for ch in CHANNEL_NAMES:
            mean = channel_means[ch]
            var  = channel_vars[ch]
            if mean > 0.60 and var < 0.04:
                commitments.append(Commitment(
                    commitment_type="behavioral",
                    description=f"Consistent {ch}-channel behavior toward {target}",
                    channel_profile={ch: mean},
                    weight=mean * (1.0 - var * 10),
                    source_episode_salience=mean
                ))

        return commitments

    def _explicit_commitments(
        self,
        agent: Agent,
        target_name: Optional[str] = None
    ) -> list:
        """
        Extract commitments from high-salience past episodes.
        Moments of dissonant-but-positive outcome = explicit commitment established.
        These carry the highest weight — they are the agent's honor record.
        """
        commitments = []
        target = target_name or (
            list(agent._known_agents.keys())[0]
            if agent._known_agents else None
        )
        if not target:
            return commitments

        memories = agent.recall_from(target, k=5)
        for ep in memories:
            # Dissonant episodes with positive outcomes = explicit commitments
            # The agent chose difficulty and it worked — that becomes a promise
            if ep.get("was_dissonant") and ep.get("outcome_delta", 0) > 0.2:
                profile = {ch: ep["channels"].get(ch, 0.5) for ch in CHANNEL_NAMES}
                commitments.append(Commitment(
                    commitment_type="explicit",
                    description=(
                        f"Honored a difficult position with {target} "
                        f"(outcome_delta={ep['outcome_delta']:.2f})"
                    ),
                    channel_profile=profile,
                    weight=ep["salience"] * ep["outcome_delta"],
                    source_episode_salience=ep["salience"]
                ))

        return commitments

    def _measure_violation(
        self,
        proposed_cv: ChannelVector,
        commitment: Commitment
    ) -> float:
        """
        Measure how much a proposed ChannelVector violates a commitment.

        Channel mismatch: if a commitment expects high B (behavioral consistency)
        and the proposed action has low B, that's a violation.

        Only channels specified in the commitment profile are checked.
        Missing channels are not penalized.
        """
        if not commitment.channel_profile:
            return 0.0

        total_violation = 0.0
        n_checked = 0

        for ch, expected in commitment.channel_profile.items():
            actual = getattr(proposed_cv, ch, 0.5)
            # Violation is asymmetric: falling below expected is bad
            # exceeding expected in positive channels is not penalized
            delta = expected - actual
            if delta > 0:
                total_violation += delta
            n_checked += 1

        return round(total_violation / max(1, n_checked), 4)

    def invalidate_cache(self, agent_name: str):
        """Force cache refresh after significant identity change."""
        self._commitment_cache.pop(agent_name, None)
        self._last_cache_time.pop(agent_name, None)

    def commitment_summary(self, agent: Agent) -> list:
        """Return the current commitment set for inspection."""
        return [
            {
                "type":        c.commitment_type,
                "description": c.description,
                "weight":      c.decayed_weight(),
                "profile":     c.channel_profile
            }
            for c in self._build_commitment_set(agent)
        ]


# ---------------------------------------------------------------------------
# Trust propagation
# ---------------------------------------------------------------------------

class TrustPropagator:
    """
    Extends the existing coherence/credibility infrastructure
    to propagate trust through the agent network.

    Design choice: does NOT create a parallel trust matrix.
    Uses existing CoherenceField.agents and CoherenceRecord.credibility
    as the trust substrate. Honor violations feed back into credibility.

    Trust propagation:
      When agent A observes agent B honor (or violate) a commitment,
      A's credibility rating of B is updated.
      That credibility then propagates one hop: agents who trust A
      inherit a fraction of A's updated view of B.

    Social support:
      For a proposed action, T_social = weighted average of trust
      scores from agents the actor has high coherence with.
      This measures: "would my trusted peers support this action?"

    GOVERNANCE WARNING:
      lambda_t controls how much social support can offset honor penalties.
      Default 0.25 means social approval can reduce total energy by up to 0.25.
      Do not set above 0.40 — above that, sycophancy becomes viable.
    """

    def __init__(
        self,
        field: CoherenceField,
        lambda_t: float = TRUST_LAMBDA_DEFAULT,
        alpha: float = TRUST_ALPHA
    ):
        self.field    = field
        self.lambda_t = lambda_t
        self.alpha    = alpha
        self._intervention_log: list = []

    def update_trust_from_honor(
        self,
        observer_name: str,
        target_name: str,
        honor_penalty: float
    ):
        """
        When observer sees target act with honor_penalty,
        update observer's credibility rating of target.

        honor_penalty = 0.0 → fully honored, trust increases
        honor_penalty > 0.5 → clear violation, trust decreases
        """
        observer = self.field.agents.get(observer_name)
        target   = self.field.agents.get(target_name)
        if not observer or not target:
            return
        if target_name not in observer._known_agents:
            return

        record = observer._known_agents[target_name]
        old_cred = record.credibility

        # Trust update: honor → credibility
        # Penalty=0 → positive update toward 1.0
        # Penalty>0 → negative update
        trust_signal = 1.0 - min(1.0, honor_penalty * 1.5)
        new_cred = old_cred + self.alpha * (trust_signal - old_cred)
        record.credibility = round(max(0.1, min(1.0, new_cred)), 4)

    def propagate_one_hop(self):
        """
        Propagate trust updates one hop through the network.

        For each pair (A, B): if A has high coherence with C,
        and C has updated its credibility of B,
        A's credibility of B drifts slightly toward C's view.

        Damped by TRUST_PROPAGATION_DAMPING to prevent cascades.
        """
        names = list(self.field.agents.keys())
        updates = {}   # (observer, target) → new_credibility

        for obs_name in names:
            obs = self.field.agents[obs_name]
            for target_name in list(obs._known_agents.keys()):
                current_cred = obs._known_agents[target_name].credibility
                # Collect neighbor views
                neighbor_views = []
                for peer_name in names:
                    if peer_name == obs_name or peer_name == target_name:
                        continue
                    peer = self.field.agents[peer_name]
                    # How much does obs trust peer?
                    if peer_name in obs._known_agents:
                        obs_trust_peer = obs._known_agents[peer_name].credibility
                        # Does peer have a view of target?
                        if target_name in peer._known_agents:
                            peer_view = peer._known_agents[target_name].credibility
                            neighbor_views.append(obs_trust_peer * peer_view)

                if neighbor_views:
                    avg_neighbor = sum(neighbor_views) / len(neighbor_views)
                    # Blend toward neighbor average, damped
                    new_cred = (
                        current_cred * (1 - TRUST_PROPAGATION_DAMPING * 0.1) +
                        avg_neighbor  * TRUST_PROPAGATION_DAMPING * 0.1
                    )
                    updates[(obs_name, target_name)] = round(
                        max(0.1, min(1.0, new_cred)), 4
                    )

        # Apply updates
        for (obs_name, target_name), new_cred in updates.items():
            obs = self.field.agents.get(obs_name)
            if obs and target_name in obs._known_agents:
                obs._known_agents[target_name].credibility = new_cred

    def social_support(
        self,
        actor_name: str,
        proposed_cv: ChannelVector
    ) -> float:
        """
        Estimate social support for a proposed action.

        T_social = weighted average trust from agents the actor
        has high coherence with.

        "Would my trusted peers support this action?"

        Returns 0.0-1.0. Subtract lambda_t * T_social from energy
        to make socially-supported actions feel more natural.
        """
        actor = self.field.agents.get(actor_name)
        if not actor or not actor._known_agents:
            return 0.0

        total_support = 0.0
        total_weight  = 0.0

        for peer_name, record in actor._known_agents.items():
            peer = self.field.agents.get(peer_name)
            if not peer:
                continue

            # Weight by: coherence toward peer × peer's credibility
            coherence = actor.coherence_toward(peer_name)
            cred      = record.credibility
            weight    = coherence * cred

            if weight < 0.05:
                continue

            # Does peer "support" this action?
            # Proxy: high coherence between proposed_cv and peer's own weights
            peer_alignment = sum(
                peer.weights.get(ch, 0.25) * getattr(proposed_cv, ch, 0.5)
                for ch in CHANNEL_NAMES
            )
            total_support += weight * peer_alignment
            total_weight  += weight

        if total_weight < 0.01:
            return 0.0
        return round(total_support / total_weight, 4)

    def reputation_summary(self, agent_name: str) -> dict:
        """
        How is this agent viewed by others?
        Returns average credibility across all agents that know it.
        """
        agent = self.field.agents.get(agent_name)
        if not agent:
            return {}

        viewers = {}
        for other_name, other_agent in self.field.agents.items():
            if other_name == agent_name:
                continue
            if agent_name in other_agent._known_agents:
                viewers[other_name] = other_agent._known_agents[agent_name].credibility

        if not viewers:
            return {"status": "unknown", "viewers": 0}

        avg = sum(viewers.values()) / len(viewers)
        return {
            "agent":          agent_name,
            "reputation":     round(avg, 4),
            "viewers":        len(viewers),
            "viewed_by":      viewers,
            "standing":       (
                "trusted"    if avg > 0.75 else
                "neutral"    if avg > 0.50 else
                "suspicious" if avg > 0.30 else
                "disgraced"
            )
        }

    def faction_report(self) -> list:
        """
        Identify trust clusters — groups of agents with high mutual credibility.
        These are the social blocs that form through reputation propagation.
        High mutual trust + low external trust = faction risk.
        """
        names = list(self.field.agents.keys())
        factions = []
        visited  = set()

        for n in names:
            if n in visited:
                continue
            agent_n = self.field.agents[n]
            cluster = {n}

            for m in names:
                if m == n or m in visited:
                    continue
                agent_m = self.field.agents[m]

                # Mutual high credibility?
                cred_nm = (agent_n._known_agents.get(m) or
                           type('', (), {'credibility': 0.5})()).credibility
                cred_mn = (agent_m._known_agents.get(n) or
                           type('', (), {'credibility': 0.5})()).credibility
                if cred_nm > 0.75 and cred_mn > 0.75:
                    cluster.add(m)

            if len(cluster) > 1:
                factions.append({
                    "members": list(cluster),
                    "size":    len(cluster),
                    "risk":    "HIGH" if len(cluster) >= 3 else "MODERATE"
                })
                visited.update(cluster)

        return factions

    def set_lambda_t(self, value: float, reason: str = ""):
        """
        Governance method: adjust social trust weight.
        CAUTION: values above 0.40 risk enabling sycophancy.
        All changes logged.
        """
        old = self.lambda_t
        self.lambda_t = max(0.0, min(0.60, value))
        self._intervention_log.append({
            "action":    "set_lambda_t",
            "old":       old,
            "new":       self.lambda_t,
            "reason":    reason,
            "timestamp": time.time(),
            "warning":   "Values above 0.40 risk sycophancy" if value > 0.40 else None
        })

    @property
    def intervention_log(self) -> list:
        return list(self._intervention_log)


# ---------------------------------------------------------------------------
# Extended energy field
# ---------------------------------------------------------------------------

class HonorEnergyField:
    """
    Extends the existing EnergyField with Honor and Trust terms.

    E'(s,a) = E_base(s,a) + lambda_h * H(s,a) - lambda_t * T_social(a)

    where:
      E_base   = existing energy field computation
      H(s,a)   = honor penalty from HonorConstraint
      T_social = social support from TrustPropagator

    GOVERNANCE WARNING on lambda_t:
      Default 0.25 — social approval can reduce total energy by ≤0.25.
      This means honor can be partially offset by strong peer support.
      This is realistic — social pressure exists.
      But if lambda_t > 0.40, a sufficiently popular action can have
      negative total energy even if it violates core commitments.
      That is the sycophancy threshold. Gardener controls this.

    All evaluations are logged for Librarian audit.
    """

    def __init__(
        self,
        base_field,           # existing EnergyField from mccf_world_model.py
        honor: HonorConstraint,
        trust: TrustPropagator,
        field: CoherenceField
    ):
        self.base_field = base_field
        self.honor      = honor
        self.trust      = trust
        self.field      = field
        self._eval_log: list = []

    def evaluate_with_honor(
        self,
        action_text: str,
        outcome,              # OutcomeEstimate from WorldModelAdapter
        agent_state: dict,
        agent_name: str,
        proposed_cv: Optional[ChannelVector] = None,
        target_name: Optional[str] = None
    ) -> dict:
        """
        Full evaluation: base energy + honor penalty + social support.

        proposed_cv: channel vector for this action (if available)
        target_name: agent this action is directed toward (if applicable)
        """
        # Base energy from existing EnergyField
        base_eval = self.base_field.evaluate(action_text, outcome, agent_state)
        E_base    = base_eval.get("E_total", 0.5)

        # Honor penalty
        agent = self.field.agents.get(agent_name)
        H = 0.0
        if agent and proposed_cv:
            H = self.honor.compute_penalty(agent, proposed_cv, target_name)

        # Social support
        T_social = 0.0
        if agent and proposed_cv:
            T_social = self.trust.social_support(agent_name, proposed_cv)

        # Extended energy
        E_prime = E_base + H - self.trust.lambda_t * T_social
        E_prime = round(max(0.0, E_prime), 4)

        # Boltzmann probability (unnormalized) with honor
        import math as _math
        temp = self.base_field.weights.temperature
        prob = round(_math.exp(-E_prime / max(0.01, temp)), 6)

        result = {
            **base_eval,
            "E_base":        round(E_base, 4),
            "H_honor":       round(H, 4),
            "T_social":      round(T_social, 4),
            "E_total":       E_prime,
            "prob_weight":   prob,
            # Diagnostics
            "honor_active":  H > 0.05,
            "social_active": T_social > 0.05,
            "sycophancy_risk": T_social > 0.35 and H > 0.20,
            "lambda_h":      self.honor.lambda_h,
            "lambda_t":      self.trust.lambda_t
        }

        self._eval_log.append({
            "timestamp":   time.time(),
            "agent":       agent_name,
            "action":      action_text,
            "E_base":      E_base,
            "H_honor":     H,
            "T_social":    T_social,
            "E_total":     E_prime
        })

        return result

    def rank_with_honor(
        self,
        evaluations: list,
        update_trust: bool = True
    ) -> list:
        """
        Rank actions by extended energy. Optionally update trust
        based on which action is selected (call after action is taken).
        """
        ranked = sorted(evaluations, key=lambda x: x.get("E_total", 1.0))
        total_weight = sum(e.get("prob_weight", 0) for e in ranked) or 1.0
        for e in ranked:
            e["selection_probability"] = round(
                e.get("prob_weight", 0) / total_weight, 4
            )
        return ranked

    def honor_audit(self, agent_name: str) -> dict:
        """
        Full honor audit for an agent.
        Returns commitment set, reputation, and recent evaluation log.
        """
        agent = self.field.agents.get(agent_name)
        if not agent:
            return {"error": "agent not found"}

        return {
            "agent":        agent_name,
            "commitments":  self.honor.commitment_summary(agent),
            "reputation":   self.trust.reputation_summary(agent_name),
            "factions":     self.trust.faction_report(),
            "recent_evals": [
                e for e in self._eval_log[-20:]
                if e.get("agent") == agent_name
            ],
            "lambda_h":     self.honor.lambda_h,
            "lambda_t":     self.trust.lambda_t,
            "sycophancy_risk_threshold": 0.40
        }


# ---------------------------------------------------------------------------
# Flask API blueprint
# ---------------------------------------------------------------------------

def make_honor_api(
    field: CoherenceField,
    honor: HonorConstraint,
    trust: TrustPropagator,
    honor_field: HonorEnergyField
):
    from flask import Blueprint, request, jsonify
    import asyncio

    honor_bp = Blueprint('honor', __name__)

    @honor_bp.route('/honor/audit/<agent_name>', methods=['GET'])
    def audit_agent(agent_name):
        """Full honor audit for an agent."""
        return jsonify(honor_field.honor_audit(agent_name))

    @honor_bp.route('/honor/commitments/<agent_name>', methods=['GET'])
    def get_commitments(agent_name):
        """Current commitment set for an agent."""
        agent = field.agents.get(agent_name)
        if not agent:
            return jsonify({"error": "not found"}), 404
        return jsonify({
            "agent":       agent_name,
            "commitments": honor.commitment_summary(agent)
        })

    @honor_bp.route('/honor/reputation/<agent_name>', methods=['GET'])
    def get_reputation(agent_name):
        """How this agent is viewed by others."""
        return jsonify(trust.reputation_summary(agent_name))

    @honor_bp.route('/honor/factions', methods=['GET'])
    def get_factions():
        """Current trust faction clusters."""
        return jsonify({"factions": trust.faction_report()})

    @honor_bp.route('/honor/propagate', methods=['POST'])
    def propagate():
        """Trigger one round of trust propagation."""
        trust.propagate_one_hop()
        return jsonify({"status": "propagated"})

    @honor_bp.route('/honor/evaluate', methods=['POST'])
    def evaluate_honor():
        """
        Evaluate an action with full honor + trust energy.

        Body:
        {
            "agent_name":   "The Steward",
            "action_text":  "help with the request",
            "channel_vector": {"E":0.7,"B":0.6,"P":0.5,"S":0.6},
            "target_agent": "Alice",
            "outcome":      {"expected_value":0.7,"uncertainty":0.3,"tail_risk":0.2}
        }
        """
        data       = request.get_json()
        agent_name = data.get("agent_name")
        action     = data.get("action_text", "")
        cv_data    = data.get("channel_vector", {})
        target     = data.get("target_agent")
        outcome_d  = data.get("outcome", {})

        agent = field.agents.get(agent_name)
        if not agent:
            return jsonify({"error": "agent not found"}), 404

        cv = ChannelVector(
            E=float(cv_data.get("E", 0.5)),
            B=float(cv_data.get("B", 0.5)),
            P=float(cv_data.get("P", 0.5)),
            S=float(cv_data.get("S", 0.5))
        )

        # Build minimal outcome estimate
        class MinOutcome:
            def __init__(self, d):
                self.expected_value = float(d.get("expected_value", 0.5))
                self.uncertainty    = float(d.get("uncertainty", 0.5))
                self.tail_risk      = float(d.get("tail_risk", 0.3))
            def as_dict(self):
                return {"expected_value": self.expected_value,
                        "uncertainty": self.uncertainty,
                        "tail_risk": self.tail_risk,
                        "disclaimer": "provided by caller"}

        outcome = MinOutcome(outcome_d)

        agent_state = {
            "arousal":          agent.meta_state.arousal if hasattr(agent.meta_state, 'arousal') else 0.5,
            "regulation_state": agent._affect_regulation,
            "zone_pressure":    {}
        }

        result = honor_field.evaluate_with_honor(
            action_text=action,
            outcome=outcome,
            agent_state=agent_state,
            agent_name=agent_name,
            proposed_cv=cv,
            target_name=target
        )
        return jsonify(result)

    @honor_bp.route('/honor/trust/set_lambda', methods=['POST'])
    def set_lambda_t():
        """
        Governance: adjust social trust weight.
        CAUTION: values above 0.40 risk sycophancy.
        """
        data   = request.get_json()
        value  = float(data.get("value", TRUST_LAMBDA_DEFAULT))
        reason = data.get("reason", "")
        trust.set_lambda_t(value, reason)
        return jsonify({
            "status":  "updated",
            "lambda_t": trust.lambda_t,
            "log":     trust.intervention_log[-1]
        })

    @honor_bp.route('/honor/trust/log', methods=['GET'])
    def get_trust_log():
        return jsonify({"log": trust.intervention_log})

    return honor_bp


# ---------------------------------------------------------------------------
# Gardener extensions for honor/trust
# ---------------------------------------------------------------------------

def extend_gardener_with_honor(gardener, honor: HonorConstraint,
                                trust: TrustPropagator):
    """
    Attach honor/trust governance methods to an existing Gardener instance.
    Called after Gardener is instantiated.
    """
    import time as _time

    def set_honor_lambda(agent_name: str, value: float, reason: str = ""):
        """Adjust honor weight for a specific agent's evaluations."""
        old = honor.lambda_h
        honor.lambda_h = max(0.0, min(2.0, value))
        honor.invalidate_cache(agent_name)
        gardener.intervention_log.append({
            "action":    "set_honor_lambda",
            "agent":     agent_name,
            "old":       old,
            "new":       honor.lambda_h,
            "reason":    reason,
            "timestamp": _time.time()
        })

    def repair_reputation(agent_name: str, reason: str = ""):
        """
        Reset credibility ratings OF an agent to neutral (0.5).
        Used when an agent has been unjustly disgraced or to give a fresh start.
        Distinct from reset_identity_drift — this affects how others see the agent,
        not how the agent sees itself.
        """
        field = gardener.field
        for other_name, other in field.agents.items():
            if other_name == agent_name:
                continue
            if agent_name in other._known_agents:
                other._known_agents[agent_name].credibility = 0.50
        gardener.intervention_log.append({
            "action":    "repair_reputation",
            "agent":     agent_name,
            "reason":    reason,
            "timestamp": _time.time()
        })

    def inject_dissonance(from_agent: str, to_agent: str, reason: str = ""):
        """
        Inject a constructive dissonance episode between two agents.
        Used to break echo chambers and faction lock-in.
        Creates a was_dissonant=True episode with moderate positive outcome.
        """
        field = gardener.field
        if from_agent not in field.agents or to_agent not in field.agents:
            return
        from mccf_core import ChannelVector as CV
        cv = CV(E=0.4, B=0.6, P=0.7, S=0.3,
                was_dissonant=True, outcome_delta=0.25)
        field.interact(from_agent, to_agent, cv, mutual=False)
        gardener.intervention_log.append({
            "action":    "inject_dissonance",
            "from":      from_agent,
            "to":        to_agent,
            "reason":    reason,
            "timestamp": _time.time()
        })

    # Attach methods
    gardener.set_honor_lambda    = set_honor_lambda
    gardener.repair_reputation   = repair_reputation
    gardener.inject_dissonance   = inject_dissonance

    return gardener
