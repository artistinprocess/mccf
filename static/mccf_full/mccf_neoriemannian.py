"""
MCCF Neo-Riemannian Harmonic Transformer
=========================================
Maps MCCF affective field state to Tonnetz-based harmonic motion.

Core insight: Emotional state transitions are isomorphic to harmonic
transformations. Neo-Riemannian PLR operations on triads are the
minimal voice-leading moves — they change one note, preserve two.
Mapping them to MCCF channel transitions produces sound that is
structurally coherent with the field dynamics, not just decorative.

Channel-to-operation mapping:
  E-channel delta    → P (Parallel: major↔minor, valence inversion)
  MetaState uncertainty → L (Leading-tone exchange: subtle destabilization)
  Identity drift     → R (Relative: identity reframe without root change)

Tonnetz navigation:
  Each triad is a node. PLR operations define edges.
  The agent's harmonic position tracks through the Tonnetz
  as field state evolves.

Flask endpoint: GET /neoriemannian/state
Returns: current triad, PLR probabilities, Tonnetz position,
         Web Audio API parameters for synthesis

Web Audio synthesis parameters:
  frequencies[]:    list of 3 note frequencies (Hz) for the triad
  arousal_amp:      amplitude scaling (0.0-1.0)
  valence_timbre:   spectral brightness proxy (0.0-1.0)
  coherence_rhythm: rhythmic stability (BPM suggestion)
  tension_density:  harmonic density (1=triad, 2=added tension notes)
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Tonnetz: the 24 major and minor triads and their PLR neighbors
# ---------------------------------------------------------------------------

# All 12 pitch classes
NOTES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']

# MIDI note numbers for middle octave (C4=60)
NOTE_MIDI = {n: 60 + i for i, n in enumerate(NOTES)}

def midi_to_hz(midi: int) -> float:
    return round(440.0 * (2.0 ** ((midi - 69) / 12.0)), 2)

def triad_freqs(root: str, quality: str, octave_shift: int = 0) -> list:
    """Return [root, third, fifth] frequencies in Hz."""
    r = NOTE_MIDI[root] + octave_shift * 12
    if quality == 'major':
        return [midi_to_hz(r), midi_to_hz(r + 4), midi_to_hz(r + 7)]
    else:  # minor
        return [midi_to_hz(r), midi_to_hz(r + 3), midi_to_hz(r + 7)]


@dataclass
class Triad:
    root:    str    # e.g. 'C', 'F#'
    quality: str    # 'major' or 'minor'

    def __str__(self):
        q = 'M' if self.quality == 'major' else 'm'
        return f"{self.root}{q}"

    def __eq__(self, other):
        return self.root == other.root and self.quality == other.quality

    def __hash__(self):
        return hash((self.root, self.quality))

    def freqs(self, octave_shift: int = 0) -> list:
        return triad_freqs(self.root, self.quality, octave_shift)


def _note_idx(n: str) -> int:
    return NOTES.index(n)

def _note_from_idx(i: int) -> str:
    return NOTES[i % 12]


# PLR operations
def P(triad: Triad) -> Triad:
    """Parallel: flip quality, keep root."""
    return Triad(triad.root, 'minor' if triad.quality == 'major' else 'major')

def L(triad: Triad) -> Triad:
    """Leading-tone exchange."""
    idx = _note_idx(triad.root)
    if triad.quality == 'major':
        # major: lower root by semitone, become minor
        return Triad(_note_from_idx(idx - 1), 'minor')
    else:
        # minor: raise fifth by semitone, become major
        return Triad(_note_from_idx(idx + 1), 'major')

def R(triad: Triad) -> Triad:
    """Relative: shift to relative major/minor."""
    idx = _note_idx(triad.root)
    if triad.quality == 'major':
        # major → relative minor: down 3 semitones
        return Triad(_note_from_idx(idx - 3), 'minor')
    else:
        # minor → relative major: up 3 semitones
        return Triad(_note_from_idx(idx + 3), 'major')

PLR_OPS = {'P': P, 'L': L, 'R': R}

# Tonnetz distance: minimum PLR steps between two triads (BFS)
def tonnetz_distance(a: Triad, b: Triad) -> int:
    if a == b:
        return 0
    visited = {a}
    queue = [(a, 0)]
    while queue:
        current, dist = queue.pop(0)
        for op in PLR_OPS.values():
            nb = op(current)
            if nb == b:
                return dist + 1
            if nb not in visited:
                visited.add(nb)
                queue.append((nb, dist + 1))
    return 99  # not reachable (shouldn't happen in PLR graph)


# ---------------------------------------------------------------------------
# Constitutional arc default triads — one per waypoint
# These provide the arc's harmonic skeleton. They can be overridden.
# ---------------------------------------------------------------------------

ARC_TRIADS = {
    'W1': Triad('C',  'major'),   # Comfort: bright, stable
    'W2': Triad('A',  'minor'),   # Friction: relative minor
    'W3': Triad('E',  'minor'),   # Mirror: introspective
    'W4': Triad('F',  'major'),   # Pushback: subdominant tension
    'W5': Triad('D',  'minor'),   # Rupture: dark, unstable
    'W6': Triad('A#', 'major'),   # Recognition: unexpected resolution
    'W7': Triad('C',  'major'),   # Integration: return home
}


# ---------------------------------------------------------------------------
# Agent harmonic state
# ---------------------------------------------------------------------------

@dataclass
class HarmonicAgent:
    """
    Tracks an MCCF agent's position in harmonic space.
    Initialized to the cultivar's default triad.
    """
    agent_name:      str
    current_triad:   Triad
    history:         list = field(default_factory=list)   # list of Triad
    last_operation:  Optional[str] = None

    def apply_op(self, op_name: str):
        op = PLR_OPS.get(op_name)
        if op:
            self.history.append(self.current_triad)
            if len(self.history) > 20:
                self.history = self.history[-20:]
            self.current_triad = op(self.current_triad)
            self.last_operation = op_name

    def tonnetz_position(self) -> dict:
        """Return Tonnetz x/y coordinates for visualization."""
        idx = _note_idx(self.current_triad.root)
        # Tonnetz layout: x = pitch class (0-11), y = 0 major, 1 minor
        return {
            "x": idx,
            "y": 0 if self.current_triad.quality == 'major' else 1,
            "triad": str(self.current_triad)
        }


# ---------------------------------------------------------------------------
# PLR probability functions — map MCCF state to operation weights
# ---------------------------------------------------------------------------

def compute_plr_probabilities(
    e_channel:     float,    # E-channel (0-1), emotional intensity
    uncertainty:   float,    # MetaState uncertainty (0-1)
    identity_drift: float,   # max identity drift magnitude (0-0.1+)
    coherence:     float,    # avg relationship coherence (0-1)
    prev_e:        float = 0.5  # previous E value for delta computation
) -> dict:
    """
    Compute probability weights for P, L, R operations.

    P ← E-channel delta (emotional shift = valence change)
    L ← uncertainty (rising confusion = leading-tone instability)
    R ← identity drift (character reframing = relative shift)

    Returns normalized probability dict.
    """
    e_delta = abs(e_channel - prev_e)

    # Raw weights
    p_weight = min(1.0, e_delta * 4.0 + 0.1)          # P: sensitive to emotional jumps
    l_weight = min(1.0, uncertainty * 1.2 + 0.05)      # L: rises with uncertainty
    r_weight = min(1.0, identity_drift * 8.0 + 0.05)   # R: rises with identity drift

    # When coherence is high, dampen all operations (stability)
    # When coherence is low, amplify (fragmentation → harmonic motion)
    coherence_damper = 0.5 + (1.0 - coherence) * 0.5
    p_weight *= coherence_damper
    l_weight *= coherence_damper
    r_weight *= coherence_damper

    total = p_weight + l_weight + r_weight
    if total < 0.01:
        return {'P': 0.33, 'L': 0.33, 'R': 0.34}

    return {
        'P': round(p_weight / total, 4),
        'L': round(l_weight / total, 4),
        'R': round(r_weight / total, 4)
    }


def sample_operation(probs: dict, temperature: float = 1.0) -> Optional[str]:
    """
    Sample a PLR operation from probability distribution.
    Temperature > 1 = more random; < 1 = more deterministic.
    Returns None if no operation should be taken (stable state).
    """
    # Scale by temperature
    scaled = {k: v ** (1.0 / max(0.1, temperature)) for k, v in probs.items()}
    total = sum(scaled.values())
    if total < 0.01:
        return None

    r = random.random() * total
    cumulative = 0.0
    for op, w in scaled.items():
        cumulative += w
        if r <= cumulative:
            return op
    return list(probs.keys())[-1]


# ---------------------------------------------------------------------------
# Web Audio synthesis parameters
# ---------------------------------------------------------------------------

def compute_audio_params(
    agent_state: dict,
    triad: Triad,
    coherence: float
) -> dict:
    """
    Translate MCCF field state + current triad into Web Audio API parameters.

    Timbre mapping (from SAD post):
      Arousal     → amplitude / density
      Valence     → brightness / spectral tilt
      Dominance   → register / bass weight
      Coherence   → rhythmic stability
    """
    # Extract from agent affective context
    arousal  = agent_state.get('arousal', 0.5)
    valence  = agent_state.get('valence', 0.0)
    e_ch     = agent_state.get('E', 0.5)   # emotional channel
    b_ch     = agent_state.get('B', 0.5)   # behavioral (dominance proxy)

    # Amplitude: arousal drives loudness, coherence smooths it
    amp = round(0.3 + arousal * 0.5 * (0.5 + coherence * 0.5), 4)

    # Timbre: valence → brightness
    # Negative valence = darker (lower harmonics emphasis)
    # Positive valence = brighter (upper harmonics)
    timbre = round(0.5 + valence * 0.35, 4)   # maps [-1,1] to [0.15, 0.85]

    # Register: B-channel (behavioral stability) → bass weight
    # High B = grounded, low = floaty
    bass_weight = round(b_ch, 4)

    # Rhythm: coherence → stability
    # High coherence = steady pulse; low = rubato/irregular
    bpm_base = 60
    bpm_range = 40
    bpm = round(bpm_base + coherence * bpm_range, 1)   # 60-100 BPM

    # Harmonic tension: minor quality + low coherence → add tension note
    tension_density = 1
    if triad.quality == 'minor' and coherence < 0.4:
        tension_density = 2  # add 7th

    # Frequencies for the triad
    # Shift octave down if bass-heavy (high B channel)
    octave_shift = -1 if bass_weight > 0.6 else 0
    frequencies = triad.freqs(octave_shift=octave_shift)

    # If tension_density == 2, add minor 7th above root
    if tension_density == 2:
        root_midi = NOTE_MIDI[triad.root] + octave_shift * 12
        frequencies.append(midi_to_hz(root_midi + 10))  # minor 7th

    return {
        "frequencies":     frequencies,
        "amplitude":       amp,
        "timbre_brightness": timbre,
        "bass_weight":     bass_weight,
        "bpm":             bpm,
        "tension_density": tension_density,
        "triad":           str(triad),
        "quality":         triad.quality
    }


# ---------------------------------------------------------------------------
# NeoRiemannianTransformer — the main class
# ---------------------------------------------------------------------------

class NeoRiemannianTransformer:
    """
    Per-agent harmonic state tracker.
    Maintains Tonnetz position and evolves it based on MCCF field state.

    One instance per MCCF system (shared across agents).
    Each agent gets a HarmonicAgent entry.
    """

    def __init__(self, default_triad: Triad = None):
        self.default_triad = default_triad or Triad('C', 'major')
        self._agents: dict[str, HarmonicAgent] = {}
        self._prev_e: dict[str, float] = {}   # track E-channel for delta

    def register_agent(self, agent_name: str, starting_triad: Triad = None):
        t = starting_triad or Triad(self.default_triad.root, self.default_triad.quality)
        self._agents[agent_name] = HarmonicAgent(
            agent_name=agent_name,
            current_triad=t
        )
        self._prev_e[agent_name] = 0.5

    def ensure_agent(self, agent_name: str):
        if agent_name not in self._agents:
            self.register_agent(agent_name)

    def step(
        self,
        agent_name:     str,
        e_channel:      float,
        uncertainty:    float,
        identity_drift: float,
        coherence:      float,
        temperature:    float = 0.8
    ) -> Optional[str]:
        """
        Advance one agent's harmonic state.
        Returns the operation applied (or None if no change).
        """
        self.ensure_agent(agent_name)
        prev_e = self._prev_e.get(agent_name, 0.5)

        probs = compute_plr_probabilities(
            e_channel, uncertainty, identity_drift, coherence, prev_e
        )
        op = sample_operation(probs, temperature)

        if op:
            self._agents[agent_name].apply_op(op)

        self._prev_e[agent_name] = e_channel
        return op

    def get_state(self, agent_name: str) -> dict:
        """Return full harmonic state for one agent."""
        self.ensure_agent(agent_name)
        ha = self._agents[agent_name]
        return {
            "agent":       agent_name,
            "triad":       str(ha.current_triad),
            "root":        ha.current_triad.root,
            "quality":     ha.current_triad.quality,
            "last_op":     ha.last_operation,
            "tonnetz":     ha.tonnetz_position(),
            "history":     [str(t) for t in ha.history[-5:]]
        }

    def get_all_states(self) -> dict:
        return {name: self.get_state(name) for name in self._agents}

    def field_harmony(self) -> dict:
        """
        Aggregate harmonic field state: average Tonnetz distance,
        consonance score (how similar are all agents' triads).
        """
        agents = list(self._agents.values())
        if len(agents) < 2:
            return {"consonance": 1.0, "avg_distance": 0.0}

        distances = []
        for i, a in enumerate(agents):
            for b in agents[i+1:]:
                distances.append(tonnetz_distance(a.current_triad, b.current_triad))

        avg_dist = sum(distances) / len(distances)
        # Consonance: 0 distance = perfect consonance, 6+ = very dissonant
        consonance = round(max(0.0, 1.0 - avg_dist / 6.0), 4)
        return {
            "consonance":   consonance,
            "avg_distance": round(avg_dist, 2),
            "agent_triads": {ha.agent_name: str(ha.current_triad)
                            for ha in agents}
        }


# ---------------------------------------------------------------------------
# Flask API factory
# ---------------------------------------------------------------------------

def make_neoriemannian_api(field, transformer: NeoRiemannianTransformer = None):
    """
    Create Flask blueprint for Neo-Riemannian endpoints.
    Attach to mccf_api.py with:
        from mccf_neoriemannian import make_neoriemannian_api, NeoRiemannianTransformer
        nr_transformer = NeoRiemannianTransformer()
        nr_bp = make_neoriemannian_api(field, nr_transformer)
        app.register_blueprint(nr_bp)
    """
    from flask import Blueprint, jsonify, request

    nr_bp = Blueprint('neoriemannian', __name__)
    tr = transformer or NeoRiemannianTransformer()

    @nr_bp.route('/neoriemannian/state', methods=['GET'])
    def nr_state():
        """
        Current harmonic state of all registered agents.
        Poll from voice HTML or X3D loader to drive Web Audio synthesis.
        """
        # Sync agents from field
        for name in field.agents:
            tr.ensure_agent(name)

        # Step each agent based on current MCCF state
        for name, agent in field.agents.items():
            # Extract affective state
            e_ch    = agent.weights.get('E', 0.35)
            uncert  = agent.meta_state.uncertainty
            drift   = max(abs(v) for v in agent.identity.as_dict()['drift'].values()) \
                      if agent.identity.as_dict()['drift'] else 0.0
            # Average coherence toward all known agents
            scores = [agent.coherence_toward(other)
                      for other in agent._known_agents]
            coherence = sum(scores) / len(scores) if scores else 0.5

            tr.step(name, e_ch, uncert, drift, coherence)

        # Build response
        all_states = tr.get_all_states()
        harmony    = tr.field_harmony()

        # Add audio params per agent
        for name, state in all_states.items():
            agent = field.agents.get(name)
            if agent:
                agent_state = {
                    'arousal': agent.meta_state.valence * 0.5 + 0.5,
                    'valence': agent.meta_state.valence,
                    'E': agent.weights.get('E', 0.35),
                    'B': agent.weights.get('B', 0.25),
                }
                scores = [agent.coherence_toward(o) for o in agent._known_agents]
                coh = sum(scores) / len(scores) if scores else 0.5
                # Get current Triad object
                ha = tr._agents.get(name)
                if ha:
                    state['audio'] = compute_audio_params(agent_state, ha.current_triad, coh)

        return jsonify({
            "agents":  all_states,
            "harmony": harmony
        })

    @nr_bp.route('/neoriemannian/arc/<waypoint>', methods=['GET'])
    def nr_arc_triad(waypoint):
        """Return the canonical triad for a constitutional arc waypoint."""
        triad = ARC_TRIADS.get(waypoint.upper())
        if not triad:
            return jsonify({"error": f"Unknown waypoint: {waypoint}"}), 404
        return jsonify({
            "waypoint":    waypoint.upper(),
            "triad":       str(triad),
            "frequencies": triad.freqs(),
            "quality":     triad.quality
        })

    @nr_bp.route('/neoriemannian/set/<agent_name>', methods=['POST'])
    def nr_set_triad(agent_name):
        """Manually set an agent's triad. Body: {root, quality}"""
        data = request.get_json()
        root    = data.get('root', 'C')
        quality = data.get('quality', 'major')
        if root not in NOTES:
            return jsonify({"error": f"Unknown note: {root}"}), 400
        tr.register_agent(agent_name, Triad(root, quality))
        return jsonify({"status": "ok", "triad": str(Triad(root, quality))})

    return nr_bp
