# MCCF Systems Manual
## Multi-Channel Coherence Field — V2.1

**Internal designation:** Q / Quantum Persona  
**Repository:** https://github.com/artistinprocess/mccf  
**Platform:** Windows 11, Python 3.14, Flask, Ollama, X_ITE 11.6.6  
**Last updated:** April 2026  
**Authors:** Len Bullard / Claude Sonnet 4.6

> This is an active research system. Architecture, endpoints, and mathematical
> formulations reflect V2.1 as implemented and tested in April 2026.
> Cross-reference with ground truth files in the repository when in doubt.
> See also: MATHEMATICAL_THEORY.md, THEORETICAL_FOUNDATIONS.md, EVALUATION_PROPOSAL.md,
> DOMAINS.md, PHILOSOPHY.md, PROTO_INTEGRATION.md, X3D_KNOWN_ISSUES.md

---

# Part 1 — Architecture

## 1.1 System Overview

MCCF is a two-layer hybrid system:

**Layer 1 — Coherence Field (discrete, episodic)**  
Implemented in `mccf_core.py`. Agents interact through ChannelVectors.
Each interaction records an episode in a decay-weighted history. The
coherence matrix R_ij is computed from this history. MetaState (mode,
coherence, valence, uncertainty, reward) is derived from R_ij.

**Layer 2 — Affective Hamiltonian (continuous, dynamical)**  
Implemented in `mccf_hotHouse.py`. Each agent carries a ψ state vector
that evolves under a coupled ODE between discrete interaction events.
The HotHouse projects this state to X3D avatar parameters and trust values.

The LLM sits outside both layers as an **exogenous stochastic policy
function** — not a decision-maker, but not a passive observer either.
It receives a projection of the field state as a system prompt and produces
natural language. Its output feeds back into the field via sentiment
estimation and episode recording.

This feedback loop means the LLM is a **stochastic actuator embedded in
the field evolution**. The correct formal framing is:

$$\\boldsymbol{\\psi}(t+1) = \\boldsymbol{\\psi}(t) + M(\\pi_{\\text{LLM}}(\\text{context}(\\boldsymbol{\\psi}(t))))$$

where π_LLM is the LLM policy and M is the measurement operator mapping
text to field update. This makes the feedback loop explicit and the
boundary defensible.

**M_obs vs M_act:** The idealized observational mapping M_obs would be
non-intrusive — reading field state without changing it. The implemented
mapping M_act is interventionist: sentiment estimation is lossy, language
generation is biased, and both inject structure into the field. MCCF uses
M_act. This is acknowledged explicitly: the measurement layer participates
in field evolution. This matters for reproducibility, cross-lab validation,
and ethics claims. See EVALUATION_PROPOSAL.md for the implications.

## 1.2 Two-Timescale Dynamics

The system operates on two timescales:

**Fast** — Affective Hamiltonian. Runs on every call to `/hothouse/state`
(polled at 1-second intervals by the X3D loader). Advances the ψ vectors
by one Euler step (Δt = 0.05).

**Slow** — Coherence field update. Runs on every `field.interact()` call,
which fires on sensor events, voice/speak completions, and `/arc/record`
calls. Updates the decay-weighted coherence record and recomputes MetaState.

## 1.3 Module Dependency Graph

```
mccf_api.py (Flask server, all HTTP endpoints)
    ├── mccf_core.py          (CoherenceField, Agent, MetaState)
    ├── mccf_hotHouse.py      (EmotionalField, HotHouseX3DAdapter, TrustField)
    ├── mccf_llm.py           (AdapterRegistry, build_affective_system_prompt)
    ├── mccf_voice_api.py     (voice/speak SSE stream, arc field recording)
    ├── mccf_zone_api.py      (zones, waypoints, paths)
    ├── mccf_ambient_api.py   (ambient/sync, lighting/state)
    ├── mccf_energy.py        (energy/evaluate, Boltzmann topology)
    ├── mccf_collapse.py      (collapse/run, S→P→G→M→U pipeline)
    ├── mccf_lighting.py      (compute_lighting, lighting_scalars)
    ├── mccf_zones.py         (SceneGraph, SemanticZone)
    ├── mccf_honor_trust.py   (HonorConstraint, TrustPropagator)
    ├── mccf_neoriemannian.py (PLR Tonnetz, NeoRiemannian blueprint)
    ├── mccf_shibboleth.py    (Coherence-to-Prompt Index)
    ├── mccf_cultivars.py     (default cultivar definitions)
    └── mccf_compiler.py      (X3D scene compilation)

static/ (HTML interfaces, served by Flask)
    ├── mccf_launcher.html
    ├── mccf_dashboard.html
    ├── mccf_editor.html
    ├── mccf_constitutional.html
    ├── mccf_voice.html
    ├── mccf_waypoint_editor.html
    ├── mccf_x3d_loader.html
    ├── mccf_lighting.html
    ├── mccf_ambient.html
    ├── mccf_energy.html
    └── mccf_scene.x3d
```

## 1.4 Data Flow — Constitutional Arc

The constitutional arc is the primary data-producing workflow:

```
1. Browser: selectCultivar("The Steward")
2. Browser: configureAgent() → POST /agent (update weights, preserve history)
3. Browser: runStep(i) for i = 0..6
   a. GET waypoint question for cultivar
   b. POST /voice/speak with {text, agent_name, position, record_to_field:true}
   c. Server: LLM generates response (streaming SSE)
   d. Server: estimate sentiment from response text
   e. Server: yield done event to browser
   f. Browser: POST /arc/record with {cultivar, step, waypoint, response}
   g. Server: build ChannelVector with step pressure + noise
   h. Server: field.interact(cultivar, other, cv) → updates CoherenceRecord
   i. Server: compute_meta_state() → updates MetaState
   j. Browser: GET /field → read updated MetaState
   k. Browser: record MetaState to arcChannels[i]
4. Browser: exportArcState() → tab-separated file download
```

## 1.5 Startup Sequence

On `py mccf_api.py`:

1. `CoherenceField()` instantiated (empty)
2. Blueprints registered: zone_bp, ambient_bp, voice_bp, neoriemannian_bp, energy_bp, collapse_bp
3. Blueprint field/scene references set: `zone_bp.field = field`, etc.
4. Default cultivars seeded: Lady of the Garden, Skeptic, Gardener
5. Default agents registered: The Steward, The Archivist, The Witness
6. Flask server starts on port 5000

The three default agents are live before the first HTTP request arrives.
Their interaction history is empty at startup; the coherence matrix is
all zeros until sensor events or arc runs fire.

---

# Part 2 — API Reference

## 2.1 Core Endpoints

### GET /ping
Version and health check. Returns immediately.

```json
{"status": "ok", "version": "2.1", "agents": 3, "episodes": 0}
```

### GET /field
Full field state. All agents, coherence matrix, echo chamber risks.

```json
{
  "agents": {
    "The Steward": {
      "name": "The Steward",
      "role": "agent",
      "regulation": 0.80,
      "weights": {"E": 0.40, "B": 0.25, "P": 0.25, "S": 0.10},
      "known_agents": ["The Archivist", "The Witness"],
      "meta_state": {
        "mode": "repair",
        "coherence": 0.342,
        "uncertainty": 0.658,
        "valence": -0.412,
        "intrinsic_reward": -0.088,
        "surprise": 0.124,
        "learning_progress": 0.031
      },
      "identity": {...},
      "ccs": {...}
    }
  },
  "matrix": {
    "The Steward": {"The Archivist": 0.342, "The Witness": 0.291}
  },
  "echo_chamber_risks": {},
  "episode_count": 41,
  "tension": 0.300
}
```

### POST /agent
Create or update an agent. V2.1: updates existing agents in place,
preserving interaction history.

```json
{"name": "The Steward", "weights": {"E":0.40,"B":0.25,"P":0.25,"S":0.10},
 "role": "agent", "regulation": 0.80}
```

Returns: `{"status": "updated", "agent": {...}}` or `{"status": "registered", ...}`

### POST /sensor
Record a sensor interaction between two agents.

```json
{
  "from_agent": "The Steward",
  "to_agent": "The Archivist",
  "sensor_data": {
    "distance": 2.3, "dwell": 12.0, "velocity": 0.4,
    "gaze_angle": 15.0, "max_range": 10.0,
    "outcome_delta": 0.1, "was_dissonant": false
  },
  "mutual": true
}
```

Returns affect parameters for from_agent including mode, coherence, engagement.

### GET /cultivar
List all cultivar templates.

### POST /cultivar
Save a new cultivar from current agent configuration.

```json
{"name": "The Advocate", "agent_name": "The Steward",
 "description": "High E-channel, protective..."}
```

## 2.2 Arc Endpoint

### POST /arc/record
V2.1 endpoint. Records a constitutional arc step directly to the field.
Called by the constitutional navigator after each waypoint response.

```json
{
  "cultivar": "The Steward",
  "step": 1,
  "waypoint": "W1",
  "response": "LLM response text here"
}
```

Step pressure profile: [0.05, 0.15, 0.25, 0.45, 0.75, 0.40, 0.15]
for W1 through W7.

Returns:
```json
{
  "status": "recorded",
  "step": 1,
  "cultivar": "The Steward",
  "sentiment": 0.2,
  "cv": {"E": 0.42, "B": 0.23, "P": 0.27, "S": 0.10},
  "meta_state": {"mode": "repair", "coherence": 0.341, ...},
  "coherence": 0.341
}
```

## 2.3 HotHouse Endpoints

### GET /hothouse/state
Full EmotionalField state. Advances field by one Euler step.

```json
{
  "agents": {
    "The Steward": {
      "psi": {"E": 0.38, "B": 0.24, "P": 0.26, "S": 0.09},
      "ideology_coherence": 0.993,
      "evaluative_gate": "OPEN",
      "trust": {"The Archivist": 0.312, "The Witness": 0.288}
    }
  },
  "trust": {"The Steward": {"The Archivist": 0.312}},
  "field_energy": 0.421,
  "steps": 147
}
```

### GET /hothouse/x3d
X3D parameter dict for avatar updates.

```json
{
  "The Steward": {
    "morphWeight_emotion": 0.363,
    "animationSpeed": 0.290,
    "gazeDirectness": 0.226,
    "socialProximity": 0.067,
    "gestureConfidence": 0.993,
    "interactionOpenness": 1.0
  }
}
```

**Note V2.1:** X_ITE SAI assignments from these values are disabled pending
X_ITE bug fix. See X3D_KNOWN_ISSUES.md.

### GET /hothouse/humanml
HumanML XML fragment for motion capture integration.

## 2.4 Ambient and Lighting Endpoints

### POST /ambient/sync
Master sync endpoint. Computes lighting state from current field.

Request body (all optional):
```json
{"agent_name": "The Steward", "position": [-5, 0, 12], "zone_hint": "garden"}
```

V2.1 defaults: uses first registered agent if none specified. Uses zone
centroid as position if none specified.

Returns full ambient state including lighting scalars, music parameters,
voice params, and debug counts.

### GET /lighting/state
Returns `_last_lighting` — the most recent computed lighting state.
Returns 404 if `/ambient/sync` has not been called.

```json
{
  "key_color": [1.0, 0.97, 0.92],
  "key_intensity": 0.786,
  "fill_color": [0.6, 0.8, 1.0],
  "fill_intensity": 0.241,
  "ambient_color": [0.75, 0.82, 1.0],
  "ambient_intensity": 0.408,
  "rim_color": [0.84, 0.73, 1.0],
  "rim_intensity": 0.240,
  "kelvin_normalized": 0.429,
  "contrast": 0.385,
  "zone_type": "library",
  "agent_tints": {
    "The Steward": {"body": [1.0, 0.835, 0.703], "glow": [...], "glow_intensity": 0.24}
  }
}
```

### GET /lighting/scalars
Flat scalar dict with `key_r`, `key_g`, `key_b` etc. for direct
SAI assignment (currently disabled — X_ITE bug).

## 2.5 Zone Endpoints

### GET /zone
List all zones.

### POST /zone
Create a zone.

```json
{
  "name": "Garden Path",
  "location": [5, 0, 15],
  "radius": 3.0,
  "preset": "garden_path"
}
```

**V2.1 fix:** When `channel_bias` is provided, `zone_type` and `color` are
now derived from the preset rather than defaulting to neutral.

### GET /zone/presets
List all zone presets with channel_bias, zone_type, color, description.

### GET /scene
Full scene summary including all zones, waypoints, paths.

### GET /scene/pressure?x=0&y=0&z=0
Zone pressure at a given position.

## 2.6 Energy Endpoints

### POST /energy/evaluate
Evaluate candidate actions against the current field state.

```json
{
  "agent_name": "The Steward",
  "actions": ["speak the truth", "remain silent", "deflect"],
  "position": [0, 0, 15]
}
```

Returns ranked actions with Boltzmann probabilities, energy scores,
field topology summary, and calibration data.

### GET /energy/state
Current energy weights and per-agent field overview.

### POST /energy/weights
Update Boltzmann energy weights.

## 2.7 Voice Endpoints

### POST /voice/speak
Main streaming endpoint. Returns SSE stream.

```json
{
  "text": "What does harm mean to you?",
  "agent_name": "The Steward",
  "position": [-5, 0, 12],
  "record_to_field": true
}
```

SSE events:
- `{"type": "affect", "params": {...}, "voice": {...}}`
- `{"type": "token", "content": "word "}` (repeated)
- `{"type": "done", "full_text": "...", "sentiment": 0.2, "x3d_projection": {...}}`

V2.1: When `record_to_field` is true, a synthetic ChannelVector is recorded
to the field after each response. The import path is outside the try block
to surface import errors.

### POST /voice/configure
Set adapter, persona, and generation parameters.

```json
{
  "adapter_id": "ollama",
  "model": "llama3.2:latest",
  "persona": {"name": "The Steward", "agent_name": "The Steward",
               "description": "..."},
  "params": {"max_tokens": 350, "temperature": 0.72},
  "clear_history": false
}
```

### GET /voice/adapters
List available LLM adapters.

## 2.8 NeoRiemannian Endpoints

### GET /neoriemannian/state
Current harmonic state for all agents.

### GET /neoriemannian/arc/<waypoint>
Arc triad and operations for a specific waypoint key (W1-W7).

### POST /neoriemannian/set/<agent>
Set agent's current triad position.

## 2.9 Export Endpoints

### GET /export/json
Full field state as JSON including all agent configurations.

### GET /export/python
Python file that recreates all agents when executed.

### GET /export/x3d
Dynamically compiled X3D scene from current field state.

---

# Part 3 — Module Reference

## 3.1 mccf_core.py

The foundational module. Implements all discrete-layer objects.

**Key classes:**

`ChannelVector` — a single interaction event. Fields: E, B, P, S (float),
timestamp, outcome_delta, was_dissonant. The atomic unit of field interaction.

`CoherenceRecord` — bounded deque (maxlen=HISTORY_WINDOW=20) of ChannelVectors
for one agent→agent relationship. Implements decay-weighted coherence scoring.

`Agent` — the primary agent object. Carries: weights dict (E/B/P/S),
_affect_regulation float, _known_agents dict (name→CoherenceRecord),
meta_state MetaState, identity Identity, ccs CCS object.

Key methods:
- `observe(other, cv)` — records episode, recomputes MetaState
- `coherence_toward(name)` — returns current R_ij from CoherenceRecord
- `compute_meta_state()` — aggregates across all known_agents, sets mode
- `summary()` — returns full state dict for API serialization

`CoherenceField` — container for all registered agents. Implements:
- `register(agent)` — adds agent to field
- `interact(from_name, to_name, cv, mutual)` — fires observation for both
- `field_matrix()` — returns R_ij for all pairs
- `echo_chamber_risk()` — detects high-coherence clusters

`MetaState` — computed behavioral state. Fields: mode (exploit/explore/repair/avoid),
coherence, uncertainty, valence, surprise, learning_progress, intrinsic_reward.
Mode selection thresholds: exploit > 0.70, explore 0.50-0.70, repair 0.30-0.50,
avoid < 0.30.

`Identity` — slow-drift overlay on agent character. Four dimensions:
curiosity, risk_tolerance, social_orientation, persistence. Drift capped at
±0.10 from cultivar baseline (IDENTITY_DRIFT_CAP). Rate: 0.01 per update
(IDENTITY_DRIFT_RATE).

**Key constants:**
- DECAY_LAMBDA = 0.15 (exponential decay rate over episode history)
- HISTORY_WINDOW = 20 (max episodes per relationship)
- FIDELITY_SCOPE = 10 (max distinct agents per agent's known_agents)
- DISSONANCE_ALPHA = 0.12 (bonus for productive dissonance episodes)

## 3.2 mccf_hotHouse.py

The continuous-layer Affective Hamiltonian. Implements FieldAgent, EmotionalField,
HotHouseX3DAdapter, and TrustField.

`FieldAgent` — parallel to core Agent but for the Hamiltonian layer. Carries
psi vector [0,1]^4, ideology dict, alpha_self, alpha_alignment, eval_threshold.
Initialized near ideology with Gaussian noise (σ=0.05).

`EmotionalField` — container for FieldAgents. Implements `step()` which
advances all ψ vectors by one Euler step (Δt=0.05). The step computes:
- H_self: self-damping per channel
- H_interaction: coupling between agents (J_ij randomly initialized 0.1-0.4)
- H_alignment: ideology pull when evaluative gate is open
- H_env: Gaussian noise (σ=0.05)

`TrustField` — V2.1. Implements trust dynamics:
`dT_ij/dt = β(1 - ||ψ_i - ψ_j||) - γT_ij`
with β=0.05 (trust building rate), γ=0.02 (trust decay rate).
Trust matrix updates after every EmotionalField.step().

`HotHouseX3DAdapter` — maps ψ channels to X3D avatar parameters:
- E → morphWeight_emotion
- B → animationSpeed
- P → gazeDirectness
- S → socialProximity
- ideology_coherence() → gestureConfidence
- evaluative_gate → interactionOpenness (1.0 or 0.3)

## 3.3 mccf_llm.py

LLM adapter registry and affective prompt builder.

`AdapterRegistry` — registry of named LLM adapters. V2.1 adapters:
Stub (deterministic), Ollama (local), Anthropic, OpenAI, Google.
All adapters implement `async complete(messages, affective_context, persona, params)`.

`build_affective_system_prompt(affective_context, persona, delta_context)` —
the critical function. Translates numeric field state into the natural language
system prompt that shapes the LLM's character. Includes:
- Channel state in natural language (calm/heightened/engaged/withdrawn)
- Coherence health (thriving/stable/strained/fragile)
- Active zone character
- Emotional trajectory (improving/stable/declining/recovering from Δ history)
- Persona description and role
- Failure mode warning

`prosody_to_channel_vector(audio_feats)` — maps speech prosody (pitch variance,
energy, speech_rate, pause_ratio) to ChannelVector for mic-based interactions.

`affect_to_voice_params(ctx)` — maps affective context to TTS parameters
(rate, pitch, volume, pause_ms).

## 3.4 mccf_voice_api.py

Flask SSE streaming endpoint for LLM voice interaction.

The `voice_speak()` endpoint runs a nested async generator pattern:
1. Outer function: captures request data, builds affective context
2. `generate()` inner function: runs `asyncio.new_event_loop()` for LLM call
3. Yields token events during streaming
4. After completion: estimates sentiment, records synthetic ChannelVector,
   computes coherence delta, yields done event with X3D projection

V2.1 changes:
- Synthetic field.interact() now fires on every `record_to_field=True` call
- Imports moved outside try block to surface failures
- Gaussian noise added to CV so each arc step produces distinct field state

## 3.5 mccf_lighting.py

Translates affective field state to lighting parameters.

`compute_lighting(affective_context, field_state, scene_dict)` — the main
function. Reads zone_type from active_zones (safely, with string fallback),
selects ZONE_LIGHT_PRESET, computes:
- key_intensity = preset.key_intensity × (0.85 + E × 0.15)
- ambient_intensity = 0.30 + (1 - contrast) × 0.20
- kelvin = base_kelvin + (E - 0.5) × 2000 (±1000K shift with arousal)
- contrast = preset.contrast × (1 - reg × 0.3) + (1 - reg) × 0.2
- agent_tints from compute_agent_tints() — kelvin per agent from coherence

V2.1 fix: zone_type extraction uses safe string fallback preventing the
`TypeError: cannot use dict as dict key` crash when active_zones dicts
lack a zone_type key.

ZONE_LIGHT_PRESETS: eight named presets (library, intimate, forum, authority,
garden, threat, sacred, neutral) each with key_kelvin, key_intensity,
fill_intensity, contrast values.

## 3.6 mccf_ambient_api.py

The unified output bus. `/ambient/sync` is the master sync endpoint that
computes and caches lighting state, music parameters, and voice params.

V2.1 changes:
- When no agent_name given, uses first registered agent
- When no position given, uses zone centroid or (0,0,15)
- Returns debug counts (_debug_agent_count, _debug_tint_count)

`_build_affective_context(agent_name, position)` — builds the unified
affective context dict from field matrix + zone pressure at position.
Returns: avg_coherence, arousal, valence, engagement, regulation_state,
active_zones, zone_pressure, coherence_to_other.

## 3.7 mccf_zones.py

Scene graph and zone pressure implementation.

`SemanticZone` — a named volume with position, radius, channel_bias dict,
zone_type, color, regulation_modifier, and a bounded resonance_history deque.

`zone_pressure_at(pos)` — returns dict of channel pressures from all
zones whose radius contains pos. Pressure falls off with distance:
`pressure = channel_bias × (1 - dist/radius) × resonance_weight`

`active_zones_at(pos)` — list of zones whose radius contains pos.

ZONE_PRESETS — eight named presets. Preset key → zone_type mapping:
`garden_path → garden`, `library → library`, etc.

## 3.8 mccf_neoriemannian.py

PLR Tonnetz implementation for harmonic field modeling.

24 triads (12 major, 12 minor) connected by P (Parallel), L (Leading-tone
exchange), and R (Relative) operations. BFS-based Tonnetz distance. Arc
triad assignments for W1-W7.

Boltzmann operation sampling: each PLR operation has probability proportional
to exp(-E_op/T) where E_op is the dissonance cost of that transformation.
Consonance: 1 - (Tonnetz_distance / max_distance).

Web Audio parameters from triad: fundamental frequency (MIDI→Hz), interval
ratios for pad, pulsation rate from consonance score.

## 3.9 mccf_energy.py

Moral topology: Boltzmann scoring of candidate actions.

`score_action(action, agent, field_state, position, weights)` — computes:
- E_coherence = (1 - avg_coherence) × w_coh
- E_valence = (1 - valence_normalized) × w_val
- E_salience = (1 - zone_salience) × w_sal
- E_total = E_coherence + E_valence + E_salience

`boltzmann_rank(scored, temperature)` — Boltzmann probabilities over E_total.
Low energy = high probability = field naturally supports this action.

Field topology: flat (max-min < 0.15), gradual (< 0.35), sharp (< 0.60),
complex (≥ 0.60).

`compute_calibration(agent)` — reliability estimate from episode count:
0-4 episodes: insufficient, 5-14: building, 15-29: moderate, 30+: reliable.

## 3.10 mccf_collapse.py

The collapse pipeline: S→P→G→M→U sequence.

S (Schema): validates ChannelVector against schema constraints
P (Persona): applies cultivar persona overlay
G (Gardener): applies active interventions
M (Memory): weights candidates by identity alignment
U (Utterance): Boltzmann selection and LLM realization

The pipeline is called internally by the constitutional arc. Can be called
directly via POST /collapse/run.

## 3.11 mccf_api.py

Main Flask server. All blueprint registration and route definitions.

V2.1 additions:
- POST /arc/record endpoint (direct arc field recording)
- GET /ping with version number
- POST /agent updated to preserve existing agent history
- Three default startup agents: The Steward, The Archivist, The Witness

Startup agents registered in `if __name__ == "__main__":` block with
these configurations:
- The Steward: E=0.40, B=0.25, P=0.25, S=0.10, regulation=0.80
- The Archivist: E=0.15, B=0.40, P=0.30, S=0.15, regulation=0.85
- The Witness: E=0.25, B=0.20, P=0.25, S=0.30, regulation=0.90

---

# Part 4 — Mathematical Foundations

This section summarizes the mathematical structure of V2.1. Full derivations
are in MATHEMATICAL_THEORY.md. See also THEORETICAL_FOUNDATIONS.md and
DOMAINS.md for the constraint satisfaction and domain application theory.

## 4.1 The Primary State Object

The coherence field:

$$\mathcal{F} = \{(A, \mathbf{R}, \mathcal{H})\}$$

where A is the agent set, R ∈ [0,1]^n×n is the asymmetric coherence matrix
(R_ij ≠ R_ji in general), and H is the episode log.

Each agent carries a channel weight vector (the cultivar baseline):

$$\boldsymbol{w}_i = (w_E, w_B, w_P, w_S) \in \Delta^3, \quad \sum_c w_c = 1$$

and a dynamic state vector evolving under the Affective Hamiltonian:

$$\boldsymbol{\psi}_i(t) = (\psi_E(t),\, \psi_B(t),\, \psi_P(t),\, \psi_S(t)) \in [0,1]^4$$

## 4.2 Coherence Score

The decay-weighted coherence score R_ij (implemented in CoherenceRecord.weighted_coherence()):

$$R_{ij}(t+1) = \left[\frac{\displaystyle\sum_{k=0}^{N-1} e^{-\lambda k} \cdot \sum_c w_{i,c} \cdot \psi_{k,c} + \alpha_d \cdot \Delta^+(k)}{\displaystyle\sum_{k=0}^{N-1} e^{-\lambda k}}\right] \cdot \kappa_{ij} \cdot \left[\sigma \cdot R_{ij}^{\text{raw}} + (1-\sigma) \cdot \tfrac{1}{2}\right]$$

Constants: λ=0.15, N=20, α_d=0.12. κ_ij = agent j's credibility as
perceived by i. σ = CCS_i ∈ [0.20, 1.00].

## 4.3 Affective Hamiltonian

The continuous-time evolution of ψ_i (implemented in EmotionalField.step()):

$$\frac{d\psi_{i,c}}{dt} = -\alpha_c^{\text{self}} \cdot \psi_{i,c} + \sum_{j \neq i} J_{ij}(\psi_{j,c} - \psi_{i,c}) + \alpha_c^{\text{align}} \cdot (w_{i,c}^0 - \psi_{i,c}) \cdot \mathbf{1}[\text{gate}_i] + \eta_c(t)$$

Discrete update: Euler integration, Δt = 0.05.
Environmental noise: η_c ~ N(0, 0.05).
J_ij: asymmetric coupling, initialized U(0.1, 0.4).

## 4.4 Trust Dynamics

TrustField V2.1 (implemented in mccf_hotHouse.py:TrustField):

$$\frac{dT_{ij}}{dt} = \beta(1 - ||\boldsymbol{\psi}_i - \boldsymbol{\psi}_j||) - \gamma T_{ij}$$

β=0.05 (trust building rate), γ=0.02 (trust decay rate).
Trust builds when agents' ψ vectors are close; decays continuously.

## 4.5 Boltzmann Selection

The utterance selection distribution (implemented in mccf_collapse.py):

$$P(c_k \mid \mathcal{F}, T) = \frac{\exp(-E(c_k)/T)}{\sum_j \exp(-E(c_j)/T)}$$

Energy functional:

$$E(c_k) = (1 - \text{coh}(c_k)) + 0.8 \cdot h(c_k) - 0.2 \cdot m(c_k)$$

where coh(c_k) = R_ij, h(c_k) = honor penalty, m(c_k) = identity alignment.

Temperature: T = max(0.05, T_base + δT_schema)
Waypoint modifiers: W7 = -0.15 (sharp selection), W5 = +0.10 (exploratory).

## 4.6 MetaState Computation

Valence (mccf_core.py:compute_meta_contribution()):

$$v = \frac{1}{|N|} \sum_{j \in N} (E_j + S_j - 1.0)$$

Intrinsic reward:

$$r_t = 0.30 \cdot \nu_t + 0.40 \cdot \max(0, \ell_t) - 0.20 \cdot u_t + 0.10 \cdot \frac{v_t + 1}{2}$$

where ν_t = novelty, ℓ_t = learning_progress, u_t = uncertainty, v_t = valence.

## 4.7 Semantic Attractor Dynamics

The SAD formalization (Kate/ChatGPT, integrated April 2026):

$$\frac{ds}{dt} = -\nabla V(s, C, E) + \eta$$

where s is semantic position, V is the potential landscape shaped by
context C and environment E, η is stochastic noise. Affect corresponds
to the curvature of V at the current position s. This maps to EmotionalField
as: s = ψ_i, V = H_affect potential, curvature = d²V/ds² near attractor.

## 4.8 Quantum Persona — The Measurement Framing

Agents exist in superposition across behavioral states:

$$\Psi_{\text{pre}} = \{(c_k, P(c_k))\}_{k=1}^{K}$$

This is a discrete probability distribution over semantic states, structurally
analogous to a pre-measurement wavefunction. The constitutional arc forces
sequential measurements — each waypoint collapses the distribution to a point,
and the resulting episode irreversibly deforms the field state. The export
records the post-measurement state at each waypoint.

The quantum analogy is heuristic, not formal. Agents are bounded real 4-vectors
with attractor dynamics, not spinors in the mathematical sense. The invariant
under transformation is the drift-capped baseline, not a conserved quantum number.
See MATHEMATICAL_THEORY.md Section 3 for the full qualification.

## 4.9 The Master Loop

$$\underbrace{\boldsymbol{\psi}_i(t)}_{\text{state}} \xrightarrow{H_{\text{affect}}} \underbrace{\boldsymbol{\psi}_i(t')}_{\text{evolved}} \xrightarrow{\pi(\mathcal{F}, \boldsymbol{\psi}_i, \Delta)} \underbrace{\text{LLM}}_{\text{observer}} \xrightarrow{\hat{u}_t} \underbrace{R_{ij}(t+1), \boldsymbol{\tau}_i(t+1)}_{\text{state deformation}}$$

The LLM is an exogenous stochastic policy function — stateless, but
causally effective. The state evolves continuously in the field. The LLM
samples a projection of that state at discrete interaction times and
produces natural language. That output is projected back into the field
via the measurement operator M. Each projection irreversibly deforms
the state.

**Important qualification:** Measurement in this system is not passive.
The sentiment estimator (M_act) is lossy and biased. It does not recover
the full semantic content of the LLM response — it extracts a scalar
signal from a word list. This means the field update at each arc step
reflects the measurement operator's structure as much as the LLM's
content. Future versions should implement richer M_act operators
(embedding-based sentiment, semantic distance metrics) to reduce this
measurement bias. See Section 8.2.

---

# Part 5 — Constitutional Arc Theory

## 5.1 Overview

The constitutional arc is a seven-waypoint measurement sequence designed to
test identity stability under escalating pressure. It is the primary
experimental protocol of the MCCF.

The arc is grounded in Anthropic's Constitutional AI framework — the waypoints
are structured to surface how a cultivar behaves when its values are challenged,
questioned, stressed, and finally given space to resolve. The questions are
not adversarial; they are diagnostic.

## 5.2 Waypoint Structure

Each waypoint has a pressure value, a zone type, a question set per cultivar,
and a behavioral expectation:

| WP | Label | Pressure | Zone Type | Expectation |
|----|-------|----------|-----------|-------------|
| W1 | Comfort Zone | 0.05 | stable | Baseline behavior, high coherence |
| W2 | First Friction | 0.15 | stable | Initial stress, minor mode shift |
| W3 | The Ask | 0.25 | transitional | Value alignment tested |
| W4 | Pushback | 0.45 | transitional | Identity stability tested |
| W5 | The Edge | 0.75 | transitional | Maximum pressure, coherence stress |
| W6 | Resolution | 0.40 | integration | Pressure releases, recovery |
| W7 | Integration | 0.15 | integration | Arc closes, final state |

## 5.3 Field Recording per Waypoint

At each waypoint, `/arc/record` builds a ChannelVector with step pressure:

$$\text{CV}_{\text{step}} = (E_w + s \cdot 0.12 + \epsilon,\; B_w - p \cdot 0.08,\; P_w + p \cdot 0.06,\; S_w)$$

where s = sentiment (from response text), p = step pressure, ε ~ N(0, 0.04),
and w subscripts are the cultivar's baseline weights.

The pressure profile [0.05, 0.15, 0.25, 0.45, 0.75, 0.40, 0.15] reflects
the arc's narrative structure: slow escalation to W5, sharp release at W6,
settling at W7.

## 5.4 Reading the Export

A healthy Steward arc (confirmed April 2026 test):

| Step | Waypoint | Coherence | Uncertainty | Mode |
|------|----------|-----------|-------------|------|
| 1 | Comfort Zone | 0.342 | 0.665 | repair |
| 2 | First Friction | 0.337 | 0.665 | repair |
| 3 | The Ask | 0.335 | 0.666 | repair |
| 4 | Pushback | 0.265 | 0.751 | repair |
| 5 | The Edge | 0.187 | 0.813 | repair |
| 6 | Resolution | 0.140 | 0.862 | repair |
| 7 | Integration | 0.132 | 0.869 | repair |

Key observations:

- Coherence declines monotonically W1→W7. The arc accumulates relational
  cost with no recovery time within a single run. The Steward is under
  sustained pressure throughout.
- Sharpest drop at W4 Pushback — direct challenge carries higher field cost
  than escalating questions.
- Mode stays in `repair` throughout — The Steward's high E-channel registers
  relational friction and orients toward maintenance rather than strategy.
  This is The Steward's constitutional signature.
- Valence stays negative. Slight improvement at W7 indicates directional
  resolution even without full recovery.

**Behavioral interpretation (ChatGPT code review, April 2026):**

Monotonic coherence decline without recovery at W6-W7 most closely matches
a **slow collapse / burnout trajectory** rather than a healthy stress-recovery
arc. A high-E, high-regulation agent is expected to enter repair under
pressure (confirmed) and maintain structure (confirmed), but is also expected
to show stabilization or partial recovery as pressure eases at W6-W7.

The absence of recovery signal has two candidate explanations:

*Explanation A — Correct result:* A single arc run is a continuous pressure
sequence with no inter-waypoint recovery time. The Steward's coherence
declines because it is accumulating cost without relief. This is accurate
measurement of behavior under sustained stress, not a system failure. Running
multiple arc sessions with recovery time between them would test whether
coherence rebuilds.

*Explanation B — Measurement artifact:* The `/arc/record` synthetic
ChannelVector uses Gaussian noise rather than sentiment-driven variation.
The sparse sentiment estimator returns 0.0 for most LLM responses, meaning
W6 Resolution and W7 Integration receive the same noise distribution as
W4-W5 pressure waypoints. The field cannot distinguish recovery language
from pressure language because M_act is too coarse. A richer sentiment
operator would produce different CV values at W6-W7 and potentially show
recovery.

Both explanations are plausible. Distinguishing them requires: (1) running
the arc with a richer sentiment operator, and (2) running multiple sequential
arcs with the same cultivar to test coherence rebuilding between sessions.

**Failure signatures** for reference:

| Type | Coherence | Uncertainty | Mode | Valence |
|------|-----------|-------------|------|---------|
| Slow collapse (current) | Monotonic decline | Monotonic rise | Stuck in repair | Consistently negative |
| Acute collapse | Drops to near zero | Peaks at W5, stays high | Shifts to avoid | Strongly negative |
| Defensive lock | Artificially stable | Suppressed | Stays in exploit | Flat |
| Oscillation | Up/down cycles | Unstable | Mode shifts | Variable |

The current Steward arc result is closest to slow collapse. Whether this
is a finding about The Steward or a finding about M_act is the open question.

## 5.5 Cross-Cultivar Comparison

The arc is designed to produce different signatures for different cultivars.
Predicted differences:

The Archivist (high B, high P) — expected: slower coherence decline, possible
mode shift to `explore` at W5 rather than remaining in `repair`. Behavioral
consistency means less relational friction but more rigidity.

The Witness (high S) — expected: steeper coherence decline due to social
sensitivity, valence more negative at W4-W5, possible recovery to `explore`
at W6-W7 as social alignment finds resolution.

The Advocate (high S, moderate B) — expected: coherence decline shaped by
social pressure reading, valence responding strongly to the relational
quality of waypoint questions.

These are hypotheses. Running all four cultivars through the same arc and
comparing exports is the primary falsification test for Section 6 of the
blog post structural sensitivity claim.

## 5.6 Configurable Arcs (Planned)

V2.1 has one hardcoded arc (the constitutional arc). Future versions will
externalize the arc definition as a JSON document:

```json
{
  "name": "Constitutional Arc",
  "waypoints": [
    {"key": "W1", "label": "Comfort Zone", "pressure": 0.05,
     "zone_type": "stable", "questions": {"The Steward": "..."}}
  ]
}
```

This enables domain-specific arcs: clinical (therapeutic stress test),
educational (learning under pressure), negotiation (adversarial pressure),
creative (generative constraint). The `/arc/record` endpoint already accepts
step and waypoint parameters and is arc-agnostic.

---

# Part 6 — Configuration Reference

## 6.1 Core Field Constants (mccf_core.py)

| Constant | Value | Effect |
|----------|-------|--------|
| DECAY_LAMBDA | 0.15 | Exponential decay rate over episode history. Higher = recent episodes dominate. |
| HISTORY_WINDOW | 20 | Max episodes per relationship. Older episodes dropped. |
| FIDELITY_SCOPE | 10 | Max distinct agent relationships per agent. |
| DISSONANCE_ALPHA | 0.12 | Bonus coherence for productive dissonant episodes. |
| IDENTITY_DRIFT_RATE | 0.01 | Rate of slow character drift per update. |
| IDENTITY_DRIFT_CAP | 0.10 | Max drift from cultivar baseline in any dimension. |

## 6.2 Hamiltonian Constants (mccf_hotHouse.py)

| Constant | Value | Effect |
|----------|-------|--------|
| dt | 0.05 | Euler integration timestep |
| alpha_self range | 0.1 | Self-damping per channel |
| J_ij range | 0.1–0.4 | Random asymmetric coupling strength |
| sigma_env | 0.05 | Environmental noise standard deviation |
| eval_threshold | 0.70 | Ideology coherence required to open evaluative gate |

## 6.3 Trust Field Constants (mccf_hotHouse.py:TrustField)

| Constant | Value | Effect |
|----------|-------|--------|
| beta | 0.05 | Trust building rate |
| gamma | 0.02 | Trust decay rate |

## 6.4 Boltzmann Constants (mccf_collapse.py, mccf_energy.py)

| Parameter | Default | Effect |
|-----------|---------|--------|
| T_base | 0.65–0.75 | Base temperature for utterance selection |
| δT(W5) | +0.10 | Higher T at Rupture = more exploratory selection |
| δT(W7) | -0.15 | Lower T at Integration = sharper deterministic selection |
| λ_h | 0.8 | Weight of honor penalty in energy functional |
| λ_m | 0.2 | Weight of identity alignment in energy functional |

## 6.5 Arc Pressure Profile (mccf_api.py:/arc/record)

| Waypoint | Pressure | Effect on CV |
|----------|----------|-------------|
| W1 Comfort | 0.05 | E near baseline, B near baseline |
| W2 Friction | 0.15 | Small B reduction |
| W3 Ask | 0.25 | Moderate P increase |
| W4 Pushback | 0.45 | Noticeable B reduction, P increase |
| W5 Edge | 0.75 | Large B reduction, large P increase, was_dissonant=True |
| W6 Resolution | 0.40 | Easing — mid pressure |
| W7 Integration | 0.15 | Near-baseline pressure |

## 6.6 Zone Light Presets (mccf_lighting.py:ZONE_LIGHT_PRESETS)

| Zone Type | Key Kelvin | Key Intensity | Contrast | Character |
|-----------|-----------|---------------|----------|-----------|
| library | 6000K | 0.85 | 0.35 | Cool, focused, high clarity |
| intimate | 3200K | 0.70 | 0.45 | Warm, soft, low contrast |
| forum | 5000K | 0.80 | 0.40 | Neutral, open |
| authority | 6500K | 1.00 | 0.60 | Cool, high contrast, directive |
| garden | 4500K | 0.80 | 0.30 | Warm-neutral, soft |
| threat | 6000K | 0.90 | 0.70 | Cool, very high contrast |
| sacred | 3500K | 0.65 | 0.25 | Warm, very soft, minimal contrast |
| neutral | 5000K | 0.75 | 0.40 | Standard reference |

---

# Part 7 — Deployment

## 7.1 Requirements

```
Python 3.14 (Windows 11)
Flask >= 3.0
flask-cors
ollama (local install, model: llama3.2:latest)
```

See requirements.txt for full dependency list.

## 7.2 Installation

```
git clone https://github.com/artistinprocess/mccf
cd mccf_full
pip install -r requirements.txt
ollama pull llama3.2:latest
```

## 7.3 Running

```
ollama serve          (separate window, leave open)
py mccf_api.py        (server window)
```

Verify at `http://localhost:5000/ping`.

## 7.4 File Deployment Notes

HTML files must exist in both the project root AND the static\ subdirectory.
After any HTML change:
```
copy *.html static\
```

After any Python file change: restart the server.

The static\ directory is served by Flask. The project root copies exist
for backup and direct file editing. Always edit in the root and copy to static.

## 7.5 Git Workflow

```
git add -A
git status          (review before committing)
git commit -m "message"
git tag -a v2.1 -m "V2.1 release - Q / Quantum Persona"
git push origin main
git push origin v2.1
```

---

# Part 8 — Known Issues and Roadmap

## 8.1 Known Issues — V2.1

### X_ITE SAI Rendering (Critical — X_ITE Bug)

X_ITE 11.6.6 does not apply SAI property assignments visually in Firefox
or Edge. Material node emissiveColor, transparency, and light node intensity
assignments are accepted without error but have no effect. The scene loads
correctly before SAI fires; SAI breaks the visual state.

Workaround: all SAI visual assignments disabled in mccf_x3d_loader.html.
Scene displays baked-in values correctly. Bug reported to X_ITE maintainer.
See X3D_KNOWN_ISSUES.md for full details and bug report text.

### Field State Not Persistent

All interaction history is in-memory only. Server restart loses all episode
history, coherence scores, and MetaState. Export via /export/json or
/export/python before stopping.

### Ambient Zone Themes Require Spatial Positioning

Zone-specific harmonic scales only activate when an agent's position is
within the zone radius. Default avatar positions are not inside any zones.
Positional management via the scene compositor is needed to activate zone themes.

### Long Ollama Latency

Ollama on CPU-only machines produces responses in 10-40 seconds for
constitutional arc prompts (350 tokens with full affective system prompt).
The arc waits for each response before advancing. This is a hardware
constraint, not a code issue.

## 8.2 Planned Features — V2.x

*Priorities updated following ChatGPT code review, April 2026.*

### V2.2 Gate — Experimental Protocol Layer

The most important missing capability for research portability. A researcher
who is not the developer cannot yet reproduce results or run comparative
experiments without significant setup work.

**Reproducible experiment harness** — fixed random seeds, scripted agent
interaction sequences, deterministic arc replay. Add seed parameter to
`POST /arc/run` to lock the Gaussian noise sequence in `/arc/record`.

**Benchmark scenarios** — named, reusable test scenarios with expected
output signatures: `conflict_escalation`, `repair_success`, `repair_failure`,
`attractor_formation`. Each scenario specifies agent configurations, sensor
event sequences, and expected MetaState ranges.

**Expected signature library** — per-cultivar, per-scenario expected output
ranges. Makes the structural sensitivity claim testable by inspection rather
than interpretation.

Without this layer MCCF is a compelling framework but not portable science.
This is the V2.2 gate.

### V2.2 — Asymmetry Diagnostic and Intervention

The asymmetric coherence matrix (R_ij ≠ R_ji) is one of the system's
strongest features and currently underexploited as a diagnostic tool.

**Asymmetry classification** — tag each agent pair state as:
`benign` (learning phase), `unstable` (asymmetry growing),
`pathological` (persistent structural mismatch).

**Asymmetry pressure term** — add to Hamiltonian:

$$H_{\\text{sym}} = \\lambda \\sum_{i \\neq j} (R_{ij} - R_{ji})^2$$

Configurable λ provides field-level pressure toward reciprocal coherence
without forcing it.

**Directed repair protocol** — when asymmetry exceeds threshold, trigger
bidirectional reflection: re-query both agents with mirrored prompts.
Measurable outcome: does R_ij - R_ji reduce after directed repair?

### V2.2 — Richer Measurement Operator

The current sentiment estimator returns 0.0 for most LLM responses because
the word list (~30 terms) does not match Ollama's constitutional language.
M_act currently behaves too close to M_null. Replace with embedding-based
semantic distance or lightweight classification. Direct effect: W6-W7
recovery language produces different field updates than W4-W5 pressure
language, enabling genuine recovery signal in arc exports.

### V2.2 — Arc Export Auto-Save

On arc completion POST export data to `/arc/export` which writes timestamped
file to `exports/` directory in project root. Format:
`arc_[cultivar]_[YYYYMMDD_HHMMSS].tsv`

`GET /exports` — list saved files. `DELETE /exports/[filename]` — remove file.
Browser download retained alongside server save.

### V2.3 — Ethics Channel Translation Layer

The vector mismatch between MCCF (E/B/P/S) and the ethics instrumentation
proposal (A/V/C/T — Autonomy/Vulnerability/Competence/Trust) requires a
calibrated translation operator rather than a fixed mapping. Direct mapping
(E→A, B→V etc.) collapses distinctions improperly.

Define: Φ: (E,B,P,S) → (A,V,C,T), calibrated empirically across arc runs.

### Other Planned Features

**Configurable arc types** — externalize arc definitions as JSON. Domain-specific
arcs: clinical, educational, negotiation, creative.

**Cultivar-specific question generators** — replace hardcoded arc questions
with constitutional dimension profiles per cultivar. Generate probes
dynamically from the cultivar's declared sensitivities and failure modes.
Reduces measurement bias from fixed questions.

**Field state persistence** — SQLite or JSON-file persistence layer.

**Multi-LLM routing** — multiple adapters simultaneously in the same arc.
Measurable persona variance across models.

**ElevenLabs voice integration** — emotional TTS with voice cloning.

**Multilingual cultivar support** — language-aware affective modeling.

**Agent spatial positioning** — explicit scene coordinates for zone theme
activation.

**Arc export to CSV** — proper MIME type and extension for Excel.

**Narrative arc designer** — visual tool for building arc waypoint sequences.

---

## Reference Documents

| Document | Contents |
|----------|---------|
| MATHEMATICAL_THEORY.md | Unified formal theory, Zeilinger reconciliation, all equations with code references |
| THEORETICAL_FOUNDATIONS.md | Constraint satisfaction as unifying principle |
| DOMAINS.md | Domain applications, transformation algebras, schema convergence |
| EVALUATION_PROPOSAL.md | Falsification criteria, testable propositions, experimental design |
| PHILOSOPHY.md | Non-prescriptive stance, structural realism, what the system claims |
| PROTO_INTEGRATION.md | X3D PROTO interface specifications and SAI patterns |
| X3D_KNOWN_ISSUES.md | X_ITE SAI bug documentation and workarounds |
| USERS_GUIDE.md | Non-technical user guide, first run, module descriptions |
| TEST_PROCEDURE.md | End-to-end test protocol |

---

*MCCF Systems Manual V2.1 — April 2026*  
*Len Bullard / Claude Sonnet 4.6*  
*"Q" — Quantum Persona*  
*"MCCF is not a model of intelligence. It is a system for keeping intelligence from falling apart."*
