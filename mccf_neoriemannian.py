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
import time
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


def sample_operation(probs: dict, temperature: float = 1.0, rng=None) -> Optional[str]:
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

    r = (rng.random() if rng is not None else random.random()) * total
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
# Field chord and progression: the agents' triads stacked into one vertical sonority, named as one chord
# ---------------------------------------------------------------------------

CHORD_TEMPLATES = [            # (suffix, intervals) -- suffixes are the ones the Theme Workshop chord box reads (Am7, F#m7b5 ...)
    ('',     (0, 4, 7)),
    ('m',    (0, 3, 7)),
    ('7',    (0, 4, 7, 10)),
    ('maj7', (0, 4, 7, 11)),
    ('m7',   (0, 3, 7, 10)),
    ('dim',  (0, 3, 6)),
    ('m7b5', (0, 3, 6, 10)),
    ('aug',  (0, 4, 8)),
]


def triad_pcs(t: Triad) -> set:
    r = _note_idx(t.root)
    return {r % 12, (r + (4 if t.quality == 'major' else 3)) % 12, (r + 7) % 12}


def field_chord(triads: list) -> dict:
    """Name the chord formed by stacking the given triads: the best-fitting root + quality for the union of their pitch classes.
    Returns {symbol, root, suffix, pcs (the chord's pitch classes), exact (every sounding note is in the chord and the chord has no missing note)}."""
    if not triads:
        return {'symbol': None, 'root': None, 'suffix': None, 'pcs': [], 'exact': False}
    sounding = set()
    for t in triads:
        sounding |= triad_pcs(t)
    roots = {_note_idx(t.root) for t in triads}
    best = None
    for r in range(12):
        for k, (suf, iv) in enumerate(CHORD_TEMPLATES):
            C = {(r + i) % 12 for i in iv}
            matched, missing, extra = len(sounding & C), len(C - sounding), len(sounding - C)
            score = matched * 2.0 - missing * 1.5 - extra * 2.5
            key = (score, 1 if r in roots else 0, -len(iv), -k)
            if best is None or key > best[0]:
                best = (key, r, suf, iv, C, missing, extra)
    _, r, suf, iv, C, missing, extra = best
    root = _note_from_idx(r)
    return {'symbol': root + suf, 'root': root, 'suffix': suf, 'pcs': sorted(C), 'exact': missing == 0 and extra == 0}


def chord_pitches(root: str, suffix: str, octave_shift: int = 0) -> list:
    """MIDI notes of a named chord (root in the octave of middle C)."""
    iv = dict(CHORD_TEMPLATES).get(suffix, (0, 4, 7))
    base = NOTE_MIDI[root] + 12 * octave_shift
    return [base + i for i in iv]


def _vlq(n: int) -> bytes:
    out = [n & 0x7F]
    n >>= 7
    while n:
        out.append(0x80 | (n & 0x7F))
        n >>= 7
    return bytes(reversed(out))


PULSE_PATTERNS = ('sustain', 'quarter', 'eighth', 'offbeat', 'arp')
# sustain: one held block chord per chord change      quarter: the chord struck on every beat
# eighth:  struck every half beat                     offbeat: struck on the off-beats only (a reggae/ska lift)
# arp:     the chord tones rolled up in eighth notes


def pulse_hits(pattern: str, notes: list, beats: float, ppq: int) -> list:
    """[(start_tick, length_ticks, [midi notes])] for one chord lasting `beats` beats."""
    total = max(1, int(round(beats * ppq)))
    if pattern == 'quarter':
        step, offs, ln = ppq, 0, int(ppq * 0.9)
    elif pattern == 'eighth':
        step, offs, ln = ppq // 2, 0, int(ppq * 0.45)
    elif pattern == 'offbeat':
        step, offs, ln = ppq, ppq // 2, int(ppq * 0.45)
    elif pattern == 'arp':
        out, t, k = [], 0, 0
        while t < total:
            out.append((t, min(int(ppq * 0.45), total - t), [notes[k % len(notes)]])); t += ppq // 2; k += 1
        return out
    else:
        return [(0, total, list(notes))]
    out, t = [], offs
    while t < total:
        out.append((t, max(1, min(ln, total - t)), list(notes))); t += step
    return out or [(0, total, list(notes))]


def progression_to_midi(runs: list, bpm: float = 60.0, ppq: int = 480, pulse: str = 'sustain') -> bytes:
    """Standard MIDI File (format 0, one track). Each run of the field progression is a chord lasting its real duration at the given
    tempo (one quarter note per second at 60 bpm), played as a held block or in a pulse pattern (see PULSE_PATTERNS)."""
    bpm = max(20.0, float(bpm)); pulse = pulse if pulse in PULSE_PATTERNS else 'sustain'
    events = []                                  # (tick, order, status bytes); order 0 = off before on at the same tick
    t0 = 0
    for r in runs:
        if not r.get('root'):
            continue
        beats = max(0.25, r['seconds'] * bpm / 60.0)
        notes = chord_pitches(r['root'], r['suffix'])
        for st, ln, ns in pulse_hits(pulse, notes, beats, ppq):
            for n in ns:
                events.append((t0 + st, 1, bytes([0x90, n, 84 if st == 0 else 72])))
                events.append((t0 + st + ln, 0, bytes([0x80, n, 0])))
        t0 += max(1, int(round(beats * ppq)))
    events.sort(key=lambda e: (e[0], e[1]))
    track = bytearray()
    track += _vlq(0) + b'\xFF\x51\x03' + int(60_000_000 / bpm).to_bytes(3, 'big')
    track += _vlq(0) + b'\xFF\x03' + bytes([len(b'MCCF field progression')]) + b'MCCF field progression'
    last = 0
    for tick, _, data in events:
        track += _vlq(tick - last) + data; last = tick
    track += _vlq(max(0, t0 - last)) + b'\xFF\x2F\x00'
    return b'MThd' + (6).to_bytes(4, 'big') + (0).to_bytes(2, 'big') + (1).to_bytes(2, 'big') + ppq.to_bytes(2, 'big') + b'MTrk' + len(track).to_bytes(4, 'big') + bytes(track)


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
        self.bpm = 60.0                       # tempo: with beats_per_chord it sets how often the harmony steps
        self.beats_per_chord = 2.0            # (60 bpm, 2 beats = the old fixed 2 s)
        self.pulse = 'sustain'                # rhythmic pattern of the exported chords and of the pulse a synth can lock to
        self.seed = 0
        self.rng = random.Random(self.seed)   # seeded: the same inputs give the same harmonic path
        self.log: list = []                   # one entry per harmonic step: {step, t, triads, ops, chord}
        self._t0 = None

    @property
    def step_seconds(self) -> float:
        return round(min(30.0, max(0.25, self.beats_per_chord * 60.0 / self.bpm)), 4)

    def configure(self, bpm=None, beats_per_chord=None, pulse=None) -> dict:
        """Set tempo, chord length (in beats) and pulse pattern; values are clamped to sane ranges. Returns the settings."""
        if bpm is not None:
            self.bpm = min(240.0, max(20.0, float(bpm)))
        if beats_per_chord is not None:
            self.beats_per_chord = min(32.0, max(0.5, float(beats_per_chord)))
        if pulse is not None and pulse in PULSE_PATTERNS:
            self.pulse = pulse
        return self.config()

    def config(self) -> dict:
        return {'bpm': self.bpm, 'beats_per_chord': self.beats_per_chord, 'pulse': self.pulse,
                'step_seconds': self.step_seconds, 'beat_seconds': round(60.0 / self.bpm, 4), 'patterns': list(PULSE_PATTERNS)}

    def reset(self, seed: int = 0):
        """Back to the starting triads, an empty log and a re-seeded random stream (call at the start of a scene)."""
        self.seed = int(seed)
        self.rng = random.Random(self.seed)
        self._agents.clear(); self._prev_e.clear()
        self.log = []; self._t0 = None

    def record(self, names: list, ops: dict, now: float = None):
        """Append the stacked state of the named agents after a step."""
        now = time.time() if now is None else now
        if self._t0 is None:
            self._t0 = now
        triads = {n: self._agents[n].current_triad for n in names if n in self._agents}
        fc = field_chord(list(triads.values()))
        self.log.append({'step': len(self.log) + 1, 't': round(now - self._t0, 2),
                         'triads': {n: str(t) for n, t in triads.items()}, 'ops': {n: ops.get(n) for n in triads},
                         'chord': fc['symbol'], 'root': fc['root'], 'suffix': fc['suffix'], 'exact': fc['exact']})
        if len(self.log) > 2000:
            self.log = self.log[-2000:]

    def progression(self) -> list:
        """The field chord over time, repeats merged: [{chord, root, suffix, steps, start, seconds, exact, triads}]."""
        runs = []
        for i, e in enumerate(self.log):
            end = self.log[i + 1]['t'] if i + 1 < len(self.log) else e['t'] + self.step_seconds
            if runs and runs[-1]['chord'] == e['chord']:
                runs[-1]['steps'] += 1; runs[-1]['seconds'] = round(end - runs[-1]['start'], 2)
            else:
                runs.append({'chord': e['chord'], 'root': e['root'], 'suffix': e['suffix'], 'steps': 1, 'start': e['t'],
                             'seconds': round(max(0.0, end - e['t']), 2), 'exact': e['exact'], 'triads': e['triads']})
        return runs

    def lanes(self) -> dict:
        """Each agent's own chord line: {agent: [{triad, steps, start}]} with repeats merged."""
        out = {}
        for e in self.log:
            for n, tr_ in e['triads'].items():
                lane = out.setdefault(n, [])
                if lane and lane[-1]['triad'] == tr_:
                    lane[-1]['steps'] += 1
                else:
                    lane.append({'triad': tr_, 'steps': 1, 'start': e['t']})
        return out

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
        op = sample_operation(probs, temperature, self.rng)

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

    def field_harmony(self, names: list = None) -> dict:
        """
        Aggregate harmonic field state: average Tonnetz distance,
        consonance score (how similar are all agents' triads).
        """
        agents = [a for n, a in self._agents.items() if names is None or n in names]
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

# Minimum seconds between harmonic steps. Polling /neoriemannian/state faster than this
# returns the current state without moving it, so the music does not depend on poll rate.
STEP_INTERVAL_S = 2.0


def make_neoriemannian_api(field, transformer: NeoRiemannianTransformer = None, live=None):
    """
    Create Flask blueprint for Neo-Riemannian endpoints.
    Attach to mccf_api.py with:
        from mccf_neoriemannian import make_neoriemannian_api, NeoRiemannianTransformer
        nr_transformer = NeoRiemannianTransformer()
        nr_bp = make_neoriemannian_api(field, nr_transformer, live=callable)
        app.register_blueprint(nr_bp)

    `live` (optional) is a callable returning {agent: {'observed': {E,B,P,S}, 'drift': 0..1, 'coherence': float|None}} for the characters
    in the scene being played. When it returns anything, those characters (and only those) drive and take part in the harmony,
    from their live EBPS state; otherwise the old behaviour (every registered agent, static weights) is used.
    `nr_bp.advance()` takes one harmonic step if one is due, so the scene's tick can keep the music moving without a browser polling.
    """
    from flask import Blueprint, jsonify, request, Response

    nr_bp = Blueprint('neoriemannian', __name__)
    tr = transformer or NeoRiemannianTransformer()
    last_step = {"t": 0.0}

    def _live():
        try:
            return (live() if live else None) or {}
        except Exception:
            return {}

    def _participants(lv):
        return list(lv.keys()) if lv else list(field.agents.keys())

    def advance(force=False):
        """One harmonic step for every participant, at most once per STEP_INTERVAL_S. Returns the participants."""
        lv = _live()
        names = _participants(lv)
        for name in names:
            tr.ensure_agent(name)
        now = time.time()
        if not (force or now - last_step["t"] >= tr.step_seconds):
            return names
        last_step["t"] = now
        ops = {}
        for name in names:
            agent = field.agents.get(name)
            L = lv.get(name)
            if L:
                e_ch   = L['observed'].get('E', 0.35)
                drift  = min(0.12, float(L.get('drift', 0.0)) * 0.25)        # expressive drift stands in for identity drift
                coh    = L.get('coherence')
            else:
                e_ch   = agent.weights.get('E', 0.35) if agent else 0.35
                drift  = 0.0
                coh    = None
            uncert = agent.meta_state.uncertainty if agent else 0.5
            if L is None and agent is not None:
                d = agent.identity.as_dict()['drift']
                drift = max(abs(v) for v in d.values()) if d else 0.0
            if coh is None and agent is not None:
                scores = [agent.coherence_toward(o) for o in agent._known_agents]
                coh = sum(scores) / len(scores) if scores else 0.5
            ops[name] = tr.step(name, e_ch, uncert, drift, 0.5 if coh is None else coh)
        tr.record(names, ops, now)
        return names

    nr_bp.advance = advance

    @nr_bp.route('/neoriemannian/state', methods=['GET'])
    def nr_state():
        """
        Current harmonic state of the characters in the scene (or of every registered agent when no scene is running).
        Poll from voice HTML or X3D loader to drive Web Audio synthesis.
        ?step=1 forces a step (for tests and manual stepping).
        """
        names = advance(force=request.args.get("step") == "1")
        lv = _live()
        all_states = {n: tr.get_state(n) for n in names}
        harmony    = tr.field_harmony(names)
        for name, state in all_states.items():
            agent = field.agents.get(name)
            L = lv.get(name)
            if agent or L:
                obs = (L or {}).get('observed') or {}
                agent_state = {
                    'arousal': (agent.meta_state.valence * 0.5 + 0.5) if agent else 0.5,
                    'valence': agent.meta_state.valence if agent else 0.0,
                    'E': obs.get('E', agent.weights.get('E', 0.35) if agent else 0.35),
                    'B': obs.get('B', agent.weights.get('B', 0.25) if agent else 0.25),
                }
                coh = (L or {}).get('coherence')
                if coh is None and agent:
                    scores = [agent.coherence_toward(o) for o in agent._known_agents]
                    coh = sum(scores) / len(scores) if scores else 0.5
                ha = tr._agents.get(name)
                if ha:
                    state['audio'] = compute_audio_params(agent_state, ha.current_triad, 0.5 if coh is None else coh)
        return jsonify({"agents": all_states, "harmony": harmony, "live": bool(lv), "steps": len(tr.log),
                        "field_chord": tr.log[-1]["chord"] if tr.log else None, "chords": len(tr.progression()),
                        "pulse": tr.config()})

    @nr_bp.route('/neoriemannian/progression', methods=['GET'])
    def nr_progression():
        """
        The harvested progression: every agent's triads stacked at each step and named as one field chord, repeats merged.
          ?format=json (default) | chart (text, one chord per line) | mid (Standard MIDI File) | symbols (space-separated chord symbols)
          ?lanes=1 adds each agent's own chord line to the JSON.   ?bpm= and ?pulse= override the MIDI tempo and pulse pattern (default: the current settings).
        """
        fmt = request.args.get('format', 'json').lower()
        runs = tr.progression()
        if fmt == 'mid':
            try: bpm = float(request.args.get('bpm', tr.bpm))
            except ValueError: bpm = tr.bpm
            return Response(progression_to_midi(runs, bpm, pulse=request.args.get('pulse', tr.pulse)), mimetype='audio/midi',
                            headers={'Content-Disposition': 'attachment; filename=mccf_field_progression.mid'})
        if fmt == 'symbols':
            return Response(' '.join(r['chord'] for r in runs if r['chord']), mimetype='text/plain')
        if fmt == 'chart':
            lines = ['MCCF field progression  (seed %s, %d steps, %d chords)' % (tr.seed, len(tr.log), len(runs))]
            for r in runs:
                lines.append('%7.1fs  %-8s %s%s' % (r['start'], r['chord'], ' + '.join(r['triads'].values()), '' if r['exact'] else '   (best fit)'))
            return Response('\n'.join(lines) + '\n', mimetype='text/plain')
        out = {'seed': tr.seed, 'steps': len(tr.log), 'step_seconds': tr.step_seconds, 'config': tr.config(), 'progression': runs,
               'symbols': [r['chord'] for r in runs if r['chord']]}
        if request.args.get('lanes') == '1':
            out['lanes'] = tr.lanes()
        return jsonify(out)

    @nr_bp.route('/neoriemannian/config', methods=['GET', 'POST'])
    def nr_config():
        """Tempo and pulse. Body: {bpm, beats_per_chord, pulse}; any subset. The harmony steps every beats_per_chord * 60 / bpm seconds
        (0.25 to 30 s). pulse is one of: sustain, quarter, eighth, offbeat, arp. Settings last until the server restarts."""
        if request.method == 'POST':
            d = request.get_json(silent=True) or {}
            try:
                tr.configure(d.get('bpm'), d.get('beats_per_chord'), d.get('pulse'))
            except (TypeError, ValueError):
                return jsonify({'status': 'error', 'error': 'bpm and beats_per_chord must be numbers'}), 400
        return jsonify({'status': 'ok', **tr.config()})

    @nr_bp.route('/neoriemannian/reset', methods=['POST'])
    def nr_reset():
        """Start the harmony over: starting triads, empty progression, random stream re-seeded. Body: {seed}"""
        data = request.get_json(silent=True) or {}
        tr.reset(int(data.get('seed', 0)))
        last_step["t"] = 0.0
        return jsonify({"status": "ok", "seed": tr.seed})

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
