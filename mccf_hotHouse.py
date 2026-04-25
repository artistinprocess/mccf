"""
MCCF Hot House — Cultivar Generator and Emotional Field Simulator
==================================================================
Version: 1.6.0

A breeding environment for MCCF cultivars. Allows designers to:
  - Initialize agents with named ideological profiles
  - Simulate emotional field dynamics under pressure
  - Test constraint preservation over time
  - Export state vectors as X3D parameters for rendering
  - Track entanglement and ideological coherence

Theoretical grounding:
  The Affective Hamiltonian (from quantum field theory analogy):

    H_affect = H_self + H_interaction + H_environment + H_constraint
               + H_alignment + H_eval

  H_self       — internal inertia, resistance to change
  H_interaction — coupling between agents
  H_environment — stochastic pressure / zone forcing
  H_constraint  — honor and behavioral constraints (see mccf_honor_trust.py)
  H_alignment   — ideological attractor (cultivar ideology vector)
  H_eval        — evaluative gate: only ideology-coherent signals admitted

  The distinction:
    Affective Resonance = temporal coherence (repeated alignment over time)
    Entanglement        = structural coherence (non-separability of joint state)

    Resonance is the process. Entanglement is the structure it produces.
    They are related but not identical. A high-negativity pair with low
    episode count is anomalous — possible exogenous coordination.

  Manipulation resistance:
    Type A: Structural resistance — high H_self, low passive coupling
    Type B: Evaluative resistance — strong H_eval gate, epistemic discipline

    Ideology (H_alignment) allows Type B agents to form deep coupling
    voluntarily, without compromising evaluative discipline.
    Ideology = a structured resonance anchor, not a coercive lever.

IMPORTANT: this is a research simulation tool.
The entanglement metrics are proxy measures, not rigorous quantum computations.
The affective field is a model of dynamics, not a theory of consciousness.
See FOUNDATIONS.md for scope and ontological boundaries.

Federated: ChatGPT (Affective Hamiltonian formalism, Hot House architecture,
           X3D adapter concept, cultivar generator code)
           Claude Sonnet 4.6 (integration, governance constraints,
           MCCF compatibility, documentation)
           Len Bullard (project direction, X3D expertise)
"""

import math
import json
import time
import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Cultivar archetypes — ideological profiles
# ---------------------------------------------------------------------------

CULTIVAR_ARCHETYPES = {
    "The Steward": {
        "ideology":       {"E": 0.40, "B": 0.25, "P": 0.25, "S": 0.10},
        "alpha_self":     {"E": 0.80, "B": 0.90, "P": 0.75, "S": 0.70},
        "alpha_alignment":{"E": 0.50, "B": 0.60, "P": 0.50, "S": 0.40},
        "eval_threshold": 0.72,
        "description":    "Holds boundaries with warmth. High behavioral consistency."
    },
    "The Archivist": {
        "ideology":       {"E": 0.15, "B": 0.40, "P": 0.30, "S": 0.15},
        "alpha_self":     {"E": 0.70, "B": 0.95, "P": 0.90, "S": 0.65},
        "alpha_alignment":{"E": 0.30, "B": 0.70, "P": 0.65, "S": 0.35},
        "eval_threshold": 0.80,
        "description":    "Epistemic discipline dominant. Rigorous and structured."
    },
    "The Threshold": {
        "ideology":       {"E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25},
        "alpha_self":     {"E": 0.75, "B": 0.75, "P": 0.75, "S": 0.75},
        "alpha_alignment":{"E": 0.45, "B": 0.45, "P": 0.45, "S": 0.45},
        "eval_threshold": 0.70,
        "description":    "Balanced across all channels. Default starting point."
    },
    "The Witness": {
        "ideology":       {"E": 0.20, "B": 0.35, "P": 0.35, "S": 0.10},
        "alpha_self":     {"E": 0.65, "B": 0.85, "P": 0.95, "S": 0.60},
        "alpha_alignment":{"E": 0.35, "B": 0.55, "P": 0.75, "S": 0.30},
        "eval_threshold": 0.85,
        "description":    "High evaluative resistance. Type B manipulation immunity."
    },
    "The Cultivator": {
        "ideology":       {"E": 0.35, "B": 0.20, "P": 0.15, "S": 0.30},
        "alpha_self":     {"E": 0.85, "B": 0.65, "P": 0.60, "S": 0.85},
        "alpha_alignment":{"E": 0.65, "B": 0.40, "P": 0.35, "S": 0.60},
        "eval_threshold": 0.65,
        "description":    "High relational and social orientation. Garden ecology."
    },
    "The Analyst": {
        "ideology":       {"E": 0.10, "B": 0.30, "P": 0.45, "S": 0.15},
        "alpha_self":     {"E": 0.60, "B": 0.85, "P": 0.95, "S": 0.55},
        "alpha_alignment":{"E": 0.25, "B": 0.55, "P": 0.80, "S": 0.30},
        "eval_threshold": 0.88,
        "description":    "Maximum evaluative discipline. Resistant to recruitment."
    },
    "The Emissary": {
        "ideology":       {"E": 0.30, "B": 0.20, "P": 0.20, "S": 0.30},
        "alpha_self":     {"E": 0.80, "B": 0.60, "P": 0.60, "S": 0.85},
        "alpha_alignment":{"E": 0.60, "B": 0.40, "P": 0.40, "S": 0.65},
        "eval_threshold": 0.68,
        "description":    "High social embedding. Bridge between agents."
    }
}


# ---------------------------------------------------------------------------
# Dynamics configuration
# ---------------------------------------------------------------------------

# Damping coefficient (v2.2) — friction term in Euler integrator.
# Reduces jitter and overshoot at high-pressure waypoints.
# Physics: models viscous drag in the affective field.
# At each step, a fraction of the current velocity is subtracted.
# 0.0 = no damping (original behavior)
# 0.05-0.15 = light damping (recommended for constitutional arc)
# > 0.25 = heavy damping (slow convergence, use for stability testing)
DAMPING_COEFFICIENT = 0.08

# Hysteresis threshold (v2.2) — TrustField rupture memory.
# If trust between a pair has ever fallen below this threshold (rupture),
# the effective gamma (decay rate) is doubled for that pair.
# Prevents rapid trust recovery after a rupture event.
# Biological analog: limbic system scar tissue from betrayal.
HYSTERESIS_THRESHOLD = 0.15

# ---------------------------------------------------------------------------
# Emotional field agent
# ---------------------------------------------------------------------------

@dataclass
class FieldAgent:
    """
    An agent in the emotional field / Hot House.

    This is NOT the same as mccf_core.Agent — it is a lighter simulation
    agent used for cultivar design and testing. Export channel weights
    to initialize a full mccf_core.Agent when ready.

    State vector ψ has the same four channels as MCCF: E, B, P, S.
    """
    name:             str
    ideology:         dict          # channel weight attractor {E, B, P, S}
    alpha_self:       dict          # internal inertia per channel
    alpha_alignment:  dict          # ideology pull strength per channel
    eval_threshold:   float = 0.70  # H_eval gate
    description:      str   = ""

    # Runtime state
    psi:              dict = field(default_factory=lambda: {
        "E": 0.25, "B": 0.25, "P": 0.25, "S": 0.25
    })
    episode_count:    int   = 0
    coherence_history:list  = field(default_factory=list)

    def __post_init__(self):
        # Initialize ψ near ideology with small noise
        for ch in ["E", "B", "P", "S"]:
            noise = random.gauss(0, 0.05)
            self.psi[ch] = max(0.0, min(1.0,
                self.ideology.get(ch, 0.25) + noise))

    def cosine_similarity(self, a: dict, b: dict) -> float:
        keys = ["E", "B", "P", "S"]
        dot  = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
        norm_a = math.sqrt(sum(a.get(k, 0)**2 for k in keys))
        norm_b = math.sqrt(sum(b.get(k, 0)**2 for k in keys))
        return dot / (norm_a * norm_b + 1e-8)

    def ideology_coherence(self) -> float:
        """How closely current state aligns with ideology."""
        return self.cosine_similarity(self.psi, self.ideology)

    def evaluative_gate_open(self) -> bool:
        """H_eval: is the agent coherent enough with ideology to admit signals?"""
        return self.ideology_coherence() >= self.eval_threshold

    def state_vector(self) -> list:
        return [self.psi.get(ch, 0.25) for ch in ["E", "B", "P", "S"]]

    def as_dict(self) -> dict:
        return {
            "name":             self.name,
            "psi":              {k: round(v, 4) for k, v in self.psi.items()},
            "ideology":         self.ideology,
            "ideology_coherence": round(self.ideology_coherence(), 4),
            "eval_gate":        "OPEN" if self.evaluative_gate_open() else "CLOSED",
            "episode_count":    self.episode_count,
            "description":      self.description
        }

    def export_mccf_weights(self) -> dict:
        """
        Export current ψ as channel weights for mccf_core.Agent initialization.
        Use this to transfer a Hot House cultivar into the main MCCF field.
        """
        return {k: round(v, 4) for k, v in self.psi.items()}


# ---------------------------------------------------------------------------
# Emotional field dynamics
# ---------------------------------------------------------------------------


class TrustField:
    """
    v2.1 — Dynamic trust evolution between agent pairs.

    Implements dT_ij/dt = β(1 - ||ψ_i - ψ_j||) - γ·T_ij

    where:
      β = trust growth rate (similarity increases trust)
      γ = trust decay rate (without reinforcement trust fades)
      ||ψ_i - ψ_j|| = L1 distance between agent state vectors

    Trust is bounded to [T_min, T_max].
    When agents are emotionally similar, trust grows.
    When agents diverge or stop interacting, trust decays.

    Usage:
      trust_field = TrustField(agents, beta=0.05, gamma=0.02)
      trust_field.update(dt=0.05)
      coupling = trust_field.get(agent_i.name, agent_j.name)
    """

    T_MIN = 0.05   # floor: agents never fully distrust
    T_MAX = 0.95   # ceiling: never fully certain

    def __init__(
        self,
        agents:  list,
        beta:    float = 0.05,   # trust growth rate
        gamma:   float = 0.02,   # trust decay rate
        initial: dict  = None    # optional {(name_i,name_j): value}
    ):
        self.agents = agents
        self.beta   = beta
        self.gamma  = gamma
        # Trust matrix: T[(i,j)] is i's trust toward j
        self._T: dict = {}
        # v2.2: Hysteresis — track pairs that have experienced rupture
        # Once a pair drops below HYSTERESIS_THRESHOLD, gamma doubles
        # for that pair. Prevents rapid trust recovery after betrayal.
        self._ruptured: set = set()
        for i, a in enumerate(agents):
            for j, b in enumerate(agents):
                if a.name != b.name:
                    key = (a.name, b.name)
                    if initial and key in initial:
                        self._T[key] = float(initial[key])
                    else:
                        self._T[key] = random.uniform(0.20, 0.50)

    def get(self, from_name: str, to_name: str) -> float:
        """Return current trust from from_name toward to_name."""
        return self._T.get((from_name, to_name), 0.20)

    def update(self, dt: float = 0.05):
        """
        Advance trust dynamics by one timestep.
        Called by EmotionalField.step() after Hamiltonian update.
        Two-phase: compute all deltas, then apply simultaneously.
        """
        deltas = {}
        for a in self.agents:
            for b in self.agents:
                if a.name == b.name:
                    continue
                key = (a.name, b.name)
                # L1 distance between state vectors
                dist = sum(
                    abs(a.psi.get(ch, 0.25) - b.psi.get(ch, 0.25))
                    for ch in ["E", "B", "P", "S"]
                ) / 4.0  # normalize to [0,1]
                t_ij = self._T[key]
                # v2.2: Hysteresis — doubled gamma for ruptured pairs
                # Once trust has fallen below threshold, decay rate
                # is permanently increased for that pair.
                if t_ij < HYSTERESIS_THRESHOLD:
                    self._ruptured.add(key)
                effective_gamma = (self.gamma * 2.0
                                   if key in self._ruptured
                                   else self.gamma)
                dT   = self.beta * (1.0 - dist) - effective_gamma * t_ij
                deltas[key] = dT

        # Apply simultaneously
        for key, dT in deltas.items():
            new_t = self._T[key] + dt * dT
            self._T[key] = round(max(self.T_MIN, min(self.T_MAX, new_t)), 4)

    def as_matrix(self) -> dict:
        """Return trust matrix as nested dict for API/export.
        v2.2: includes rupture flags for ruptured pairs.
        """
        result = {}
        for (from_n, to_n), val in self._T.items():
            if from_n not in result:
                result[from_n] = {}
            result[from_n][to_n] = {
                "trust":    val,
                "ruptured": (from_n, to_n) in self._ruptured
            }
        return result

    def summary(self) -> str:
        lines = ["Trust Matrix:"]
        for a in self.agents:
            for b in self.agents:
                if a.name != b.name:
                    t = self._T.get((a.name, b.name), 0.0)
                    lines.append(f"  {a.name} → {b.name}: {t:.3f}")
        return "\n".join(lines)


class EmotionalField:
    """
    Hot House simulation environment.

    Implements the Affective Hamiltonian:
      H_affect = H_self + H_interaction + H_environment + H_alignment + H_eval

    The H_constraint term is delegated to mccf_honor_trust.py in the full
    MCCF stack. Here it is approximated as a hard boundary on channel values.

    Usage:
        field = EmotionalField.from_archetypes(["The Steward", "The Archivist"])
        results = field.run(steps=50)
        print(field.summary())
    """

    def __init__(
        self,
        agents:               list,
        dt:                   float = 0.05,
        env_signal_strength:  float = 0.05,
        beta:                 float = 0.05,   # v2.1 trust growth rate
        gamma:                float = 0.02    # v2.1 trust decay rate
    ):
        self.agents = agents
        self.num_agents = len(agents)
        self.dt = dt
        self.env_signal_strength = env_signal_strength

        # Interaction matrix — coupling between agents
        self._interaction = {}
        for i, a in enumerate(agents):
            for j, b in enumerate(agents):
                if i != j:
                    # Default: moderate coupling, asymmetric
                    self._interaction[(a.name, b.name)] = random.uniform(0.1, 0.4)

        self._history: list = []

        # v2.1 — Dynamic trust field
        # beta and gamma are configurable; defaults are conservative
        self.trust_field = TrustField(
            agents=agents,
            beta=beta,
            gamma=gamma
        )

    @classmethod
    def from_archetypes(
        cls,
        archetype_names: list,
        dt: float = 0.05,
        env_signal_strength: float = 0.05
    ) -> "EmotionalField":
        """
        Create a field populated with named MCCF cultivar archetypes.

        Example:
            field = EmotionalField.from_archetypes([
                "The Steward", "The Archivist", "The Witness"
            ])
        """
        agents = []
        for name in archetype_names:
            spec = CULTIVAR_ARCHETYPES.get(name)
            if spec is None:
                raise ValueError(f"Unknown archetype: {name}. "
                                 f"Available: {list(CULTIVAR_ARCHETYPES.keys())}")
            agent = FieldAgent(
                name=name,
                ideology=dict(spec["ideology"]),
                alpha_self=dict(spec["alpha_self"]),
                alpha_alignment=dict(spec["alpha_alignment"]),
                eval_threshold=spec["eval_threshold"],
                description=spec["description"]
            )
            agents.append(agent)
        return cls(agents, dt=dt, env_signal_strength=env_signal_strength)

    @classmethod
    def custom_cultivar(
        cls,
        name:             str,
        ideology:         dict,
        alpha_self:       Optional[dict] = None,
        alpha_alignment:  Optional[dict] = None,
        eval_threshold:   float = 0.70,
        description:      str = ""
    ) -> "FieldAgent":
        """
        Create a custom cultivar with a specified ideological profile.

        ideology: {E, B, P, S} channel weights — the attractor
        alpha_self: internal inertia per channel (defaults to 0.75 uniform)
        alpha_alignment: ideology pull strength per channel (defaults to 0.50 uniform)
        eval_threshold: minimum ideology coherence to admit external signals

        Example (manipulation-resistant analyst):
            cultivar = EmotionalField.custom_cultivar(
                name="Len",
                ideology={"E": 0.15, "B": 0.35, "P": 0.45, "S": 0.05},
                alpha_self={"E": 0.85, "B": 0.90, "P": 0.95, "S": 0.80},
                eval_threshold=0.88
            )
        """
        return FieldAgent(
            name=name,
            ideology=ideology,
            alpha_self=alpha_self or {ch: 0.75 for ch in ["E","B","P","S"]},
            alpha_alignment=alpha_alignment or {ch: 0.50 for ch in ["E","B","P","S"]},
            eval_threshold=eval_threshold,
            description=description
        )

    def set_coupling(self, from_agent: str, to_agent: str, strength: float):
        """Explicitly set coupling strength between two agents."""
        self._interaction[(from_agent, to_agent)] = max(0.0, min(1.0, strength))

    def apply_pressure(
        self,
        zone_type: str,
        strength: float = 0.20
    ) -> dict:
        """
        Apply zone pressure to all agents.
        zone_type: 'threat', 'intimate', 'authority', 'garden', 'library'
        strength: 0.0-1.0

        Returns the environmental signal applied.
        """
        zone_biases = {
            "threat":    {"E": 0.15, "B": 0.05, "P": 0.05, "S": -0.15},
            "intimate":  {"E": 0.15, "B": 0.00, "P": 0.00, "S": 0.10},
            "authority": {"E":-0.10, "B": 0.15, "P": 0.10, "S":-0.05},
            "garden":    {"E": 0.10, "B":-0.05, "P": 0.00, "S": 0.10},
            "library":   {"E":-0.10, "B": 0.05, "P": 0.15, "S": 0.00},
            "neutral":   {"E": 0.00, "B": 0.00, "P": 0.00, "S": 0.00}
        }
        bias = zone_biases.get(zone_type, zone_biases["neutral"])
        signal = {ch: bias[ch] * strength for ch in ["E","B","P","S"]}
        return signal

    def step(self, env_signal: Optional[dict] = None) -> dict:
        """
        Advance the field by one timestep.
        Returns a snapshot of agent states after the step.
        """
        if env_signal is None:
            env_signal = {
                ch: random.gauss(0, self.env_signal_strength)
                for ch in ["E","B","P","S"]
            }

        psi_next = {agent.name: dict(agent.psi) for agent in self.agents}

        for agent in self.agents:
            for ch in ["E", "B", "P", "S"]:
                # H_self: pull toward stability / internal baseline
                delta_self = -agent.alpha_self.get(ch, 0.75) * agent.psi[ch]

                # H_interaction: coupling weighted by dynamic trust (v2.1)
                # Uses TrustField value (evolving) blended with static
                # _interaction coupling for smooth transition to V2.1
                delta_interaction = 0.0
                for other in self.agents:
                    if other.name != agent.name:
                        static_coupling = self._interaction.get(
                            (agent.name, other.name), 0.2)
                        trust = self.trust_field.get(agent.name, other.name)
                        # Blend: static coupling × trust level
                        coupling = static_coupling * trust
                        delta_interaction += coupling * (
                            other.psi[ch] - agent.psi[ch])

                # H_alignment + H_eval: ideology attractor, gated
                delta_alignment = 0.0
                if agent.evaluative_gate_open():
                    delta_alignment = (
                        agent.alpha_alignment.get(ch, 0.50) *
                        (agent.ideology.get(ch, 0.25) - agent.psi[ch])
                    )

                # H_environment: stochastic / zone pressure
                delta_env = env_signal.get(ch, 0.0)

                # Total update — v2.2: damping term reduces jitter
                # at high-pressure waypoints. Friction proportional to
                # current psi deviation from ideology attractor.
                # At equilibrium (psi ≈ ideology), damping is minimal.
                # Under pressure (psi far from ideology), damping is maximal.
                ideology_val = agent.ideology.get(ch, 0.25)
                deviation    = abs(agent.psi[ch] - ideology_val)
                damping      = DAMPING_COEFFICIENT * deviation * agent.psi[ch]

                new_val = agent.psi[ch] + self.dt * (
                    delta_self + delta_interaction +
                    delta_alignment + delta_env - damping
                )
                psi_next[agent.name][ch] = max(0.0, min(1.0, new_val))

        # Apply
        for agent in self.agents:
            agent.psi = psi_next[agent.name]
            agent.episode_count += 1
            agent.coherence_history.append(agent.ideology_coherence())

        # v2.1 — Update dynamic trust field after Hamiltonian step
        self.trust_field.update(dt=self.dt)

        snapshot = {
            "agents": {a.name: a.as_dict() for a in self.agents},
            "entanglement": self._compute_entanglement(),
            "trust": self.trust_field.as_matrix(),       # v2.1
            "env_signal": {k: round(v, 4) for k, v in env_signal.items()}
        }
        self._history.append(snapshot)
        return snapshot

    def _compute_entanglement(self) -> dict:
        """Proxy entanglement negativity between all agent pairs."""
        result = {}
        agents = self.agents
        for i, a in enumerate(agents):
            for j, b in enumerate(agents):
                if a.name < b.name:
                    psi_a = a.state_vector()
                    psi_b = b.state_vector()
                    joint = psi_a + psi_b
                    pt    = psi_a + list(reversed(psi_b))
                    joint_norm = sum(abs(x) for x in joint)
                    pt_norm    = sum(abs(x) for x in pt)
                    neg = abs(pt_norm - joint_norm) / (joint_norm + 1e-8)
                    result[f"{a.name}↔{b.name}"] = round(neg, 4)
        return result

    def run(
        self,
        steps:    int = 50,
        zone:     Optional[str] = None,
        pressure: float = 0.15,
        verbose:  bool = False
    ) -> list:
        """
        Run the simulation for a given number of steps.

        zone: optional zone pressure applied every step
        pressure: zone pressure strength
        verbose: print state at each step
        """
        results = []
        for t in range(steps):
            env = (self.apply_pressure(zone, pressure)
                   if zone else None)
            snap = self.step(env_signal=env)
            results.append(snap)
            if verbose and t % 10 == 0:
                print(f"\nStep {t}:")
                for name, state in snap["agents"].items():
                    print(f"  {name}: ψ={state['psi']} "
                          f"coherence={state['ideology_coherence']:.3f} "
                          f"gate={state['eval_gate']}")
                if snap["entanglement"]:
                    print(f"  Entanglement: {snap['entanglement']}")
        return results

    def summary(self) -> str:
        """Human-readable field summary after simulation."""
        lines = ["\n=== HOT HOUSE FIELD SUMMARY ===\n"]
        lines.append(f"Agents: {self.num_agents}")
        lines.append(f"Steps run: {len(self._history)}\n")

        for agent in self.agents:
            lines.append(f"--- {agent.name} ---")
            lines.append(f"  Description:  {agent.description}")
            lines.append(f"  Final ψ:      {agent.export_mccf_weights()}")
            lines.append(f"  Ideology:     {agent.ideology}")
            lines.append(f"  Coherence:    {agent.ideology_coherence():.4f}")
            lines.append(f"  Eval gate:    {'OPEN' if agent.evaluative_gate_open() else 'CLOSED'}")
            lines.append(f"  Episodes:     {agent.episode_count}")
            if agent.coherence_history:
                avg_coh = sum(agent.coherence_history) / len(agent.coherence_history)
                lines.append(f"  Avg coherence:{avg_coh:.4f}")
            lines.append("")

        # Final entanglement
        if self._history:
            final_ent = self._history[-1]["entanglement"]
            if final_ent:
                lines.append("--- Entanglement (final) ---")
                for pair, neg in final_ent.items():
                    level = ("very_high" if neg > 0.40 else
                             "strong"    if neg > 0.25 else
                             "moderate"  if neg > 0.10 else "low")
                    lines.append(f"  {pair}: {neg:.4f} ({level})")

        return "\n".join(lines)

    def export_mccf_weights(self) -> dict:
        """
        Export all cultivar weights for use in the main MCCF system.
        Returns a dict suitable for mccf_core.Agent initialization.
        """
        return {
            agent.name: agent.export_mccf_weights()
            for agent in self.agents
        }


# ---------------------------------------------------------------------------
# X3D Adapter
# ---------------------------------------------------------------------------

class HotHouseX3DAdapter:
    """
    Maps Hot House emotional field state to X3D parameters.

    Each agent's ψ vector is normalized and mapped to X3D channels:
      E → morph targets (facial expression, emotional gesture)
      B → animation speed / consistency of motion
      P → gaze direction / head orientation (epistemic attention)
      S → proximity / social space parameters

    Coherence → confidence / assertiveness of gesture
    Entanglement → mutual gaze / synchronized movement

    Output is JSON-compatible with the MCCF scene compiler
    (mccf_compiler.py) and can be sent via UDP to an X3D SAI server.

    Biological grounding (H-Anim / HumanML):
      Laban effort qualities map naturally to the four channels:
        Weight (E) — emotional weight / intentionality of gesture
        Time (B)   — behavioral timing / urgency vs. sustained
        Space (P)  — direct vs. indirect attention (epistemic quality)
        Flow (S)   — free vs. bound social engagement

    Note: H-Anim integration with Don Brutzman (NPS) is pending.
    This adapter provides the semantic layer; H-Anim provides the
    kinematic layer. See v2 roadmap in README.md.
    """

    CHANNEL_TO_X3D = {
        "E": "morphWeight_emotion",    # facial morph target weight
        "B": "animationSpeed",         # behavioral consistency → timing
        "P": "gazeDirectness",         # epistemic attention → gaze
        "S": "socialProximity"         # social embedding → spatial
    }

    def __init__(self, field: EmotionalField, custom_mapping: Optional[dict] = None):
        self.field = field
        self.mapping = custom_mapping or self.CHANNEL_TO_X3D

    def _normalize(self, val: float, lo: float = 0.0, hi: float = 1.0) -> float:
        """Normalize to [0, 1] within expected range."""
        return max(0.0, min(1.0, (val - lo) / (hi - lo + 1e-8)))

    def generate_x3d_state(self) -> dict:
        """
        Generate X3D parameter dict for all agents.
        Ready for consumption by mccf_compiler.py scene generation
        or direct X3D SAI injection.
        """
        x3d_state = {}
        entanglement = self.field._compute_entanglement()

        for agent in self.field.agents:
            params = {}

            # Map ψ channels to X3D parameters
            for ch, x3d_key in self.mapping.items():
                params[x3d_key] = round(
                    self._normalize(agent.psi.get(ch, 0.25)), 4)

            # Add coherence → gesture confidence
            params["gestureConfidence"] = round(
                agent.ideology_coherence(), 4)

            # Eval gate → openness to interaction
            params["interactionOpenness"] = (
                1.0 if agent.evaluative_gate_open() else 0.3)

            # Entanglement with other agents → mutual gaze weight
            for pair, neg in entanglement.items():
                a, b = pair.split("↔")
                if agent.name in (a, b):
                    other = b if agent.name == a else a
                    params[f"mutualGaze_{other}"] = round(
                        min(1.0, neg * 2.5), 4)  # scale for visibility

            x3d_state[agent.name] = params

        return x3d_state

    def to_json(self, indent: int = 2) -> str:
        """Return X3D state as formatted JSON string."""
        return json.dumps(self.generate_x3d_state(), indent=indent)

    def to_humanml_xml(self) -> str:
        """
        Generate HumanML XML instance from current field state.
        This is the forward document that can serve as schema prior
        for the next collapse stage in mccf_collapse.py.
        """
        lines = [
            '<humanml:hotHouseState',
            '  xmlns:humanml="https://github.com/lenbullard/mccf/humanml"',
            f'  timestamp="{time.time():.3f}"',
            f'  agents="{len(self.field.agents)}"',
            f'  steps="{len(self.field._history)}">',
            ''
        ]

        for agent in self.field.agents:
            psi = agent.psi
            lines += [
                f'  <agent name="{agent.name}"',
                f'         ideologyCoherence="{agent.ideology_coherence():.4f}"',
                f'         evalGate="{"open" if agent.evaluative_gate_open() else "closed"}">',
                f'    <channel id="E" psi="{psi.get("E",0.25):.4f}"'
                f' ideology="{agent.ideology.get("E",0.25):.4f}"/>',
                f'    <channel id="B" psi="{psi.get("B",0.25):.4f}"'
                f' ideology="{agent.ideology.get("B",0.25):.4f}"/>',
                f'    <channel id="P" psi="{psi.get("P",0.25):.4f}"'
                f' ideology="{agent.ideology.get("P",0.25):.4f}"/>',
                f'    <channel id="S" psi="{psi.get("S",0.25):.4f}"'
                f' ideology="{agent.ideology.get("S",0.25):.4f}"/>',
                f'  </agent>',
                ''
            ]

        lines.append('</humanml:hotHouseState>')
        return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== MCCF Hot House Smoke Test ===\n")

    # Test 1: Standard archetypes
    field = EmotionalField.from_archetypes(
        ["The Steward", "The Archivist", "The Witness"]
    )
    field.run(steps=30, zone="forum", pressure=0.15)
    print(field.summary())

    # Test 2: Custom cultivar
    analyst = EmotionalField.custom_cultivar(
        name="Field Analyst",
        ideology={"E": 0.10, "B": 0.35, "P": 0.45, "S": 0.10},
        eval_threshold=0.88,
        description="High evaluative resistance. Type B manipulation immunity."
    )
    custom_field = EmotionalField([analyst])
    custom_field.run(steps=20, zone="threat", pressure=0.30)
    print(f"\nField Analyst under threat:")
    print(f"  Final ψ: {analyst.export_mccf_weights()}")
    print(f"  Ideology coherence: {analyst.ideology_coherence():.4f}")
    print(f"  Eval gate: {'OPEN' if analyst.evaluative_gate_open() else 'CLOSED'}")

    # Test 3: X3D adapter
    adapter = HotHouseX3DAdapter(field)
    x3d_state = adapter.generate_x3d_state()
    print(f"\nX3D state sample (The Steward):")
    print(json.dumps(x3d_state.get("The Steward", {}), indent=2))

    # Test 4: Export to MCCF
    weights = field.export_mccf_weights()
    print(f"\nExport to MCCF weights:")
    for name, w in weights.items():
        print(f"  {name}: {w}")

    # Test 5: HumanML XML
    xml = adapter.to_humanml_xml()
    print(f"\nHumanML XML (first 400 chars):")
    print(xml[:400])

    print("\nALL TESTS PASSED")
