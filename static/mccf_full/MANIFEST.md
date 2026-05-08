# MCCF — Full Package Manifest

## Core Engine
- `mccf_core.py`        — Agent, CoherenceField, Librarian, Gardener
- `mccf_zones.py`       — SemanticZone, Waypoint, AgentPath, SceneGraph
- `mccf_llm.py`         — LLM adapter layer (Anthropic, OpenAI, Ollama, Google, Stub)

## API Server
- `mccf_api.py`         — Flask REST server, sensor endpoint, exports
- `mccf_zone_api.py`    — Zone/waypoint/path/scene blueprint
- `mccf_voice_api.py`   — Voice agent SSE streaming blueprint

## Browser Interfaces
- `mccf_editor.html`         — Agent + coherence field editor
- `mccf_waypoint_editor.html`— Scene composer: zones, waypoints, paths, arc analysis
- `mccf_x3d_demo.html`       — X3D/X_ITE live scene with avatar affect routing
- `mccf_voice.html`          — Voice agent with Web Speech API
- `mccf_ambient.html`        — Generative ambient music engine

## Demo
- `examples/three_agent_demo.py` — Standalone Python simulation

## Run
```bash
pip install flask flask-cors
python mccf_api.py
# open any .html file in browser, set API to http://localhost:5000
```

## Federated Design
This codebase was bred across three LLM passes:
- ChatGPT: initial prototype scaffold and formal spec
- Gemini: breadth passes and alternative framings  
- Claude: architectural continuity from the long design conversation,
          zone/semantic pressure layer, LLM adapter interface,
          voice+prosody pipeline, ambient music engine

Each pass contributes what its architecture favors.
The GitHub is the shared phenotype.
Contributions welcome — prove ideas with code.

## Perceptual Output Bus (added pass 3)
- `mccf_lighting.py`     — Kelvin/color/contrast computation from affective field
- `mccf_ambient_api.py`  — /ambient/sync unified output bus (music + lighting + field)
- `mccf_lighting.html`   — Real-time lighting visualizer with stage preview

## Signal Flow
```
CoherenceField
    ↓
/ambient/sync  ←── sensor events, voice prosody, zone episodes
    ├── music params  → mccf_ambient.html (Web Audio API)
    ├── lighting state → mccf_lighting.html + X3D ROUTE targets
    ├── voice params   → mccf_voice.html (Web Speech API rate/pitch)
    └── field update   → mccf_editor.html matrix display
```

## Affective → Lighting Mapping
- E (emotional)  → color temperature shift (warm ↔ cool)
- B (behavioral) → light stability / flicker amplitude
- P (predictive) → directionality / key angle
- S (social)     → fill density / shadow softness
- valence        → hue rotation (golden ↔ cold blue)
- regulation     → contrast ratio (soft ↔ hard shadows)
- zone_type      → lighting preset character

## World Model + Energy Field (Layer 2)
- `mccf_world_model.py`  — WorldModelAdapter, EnergyField, risk disclosure
- `mccf_energy.html`     — Moral topology visualizer

### Layer 2 Signal Chain
```
Agent proposes actions (text)
    ↓
WorldModelAdapter queries LLM → OutcomeEstimate {expected_value, uncertainty, tail_risk}
    ↓
EnergyField.evaluate() → E(s,a) = wv·Ev + wu·Eu + wk·Ek
    ↓
rank_actions() → Boltzmann P(a|s) ∝ exp(-E/T)
    ↓
visual_signal() → X3D color/scale/pulse parameters
    ↓
ResonanceEpisode feedback → calibration_bias correction
```

### Risk Disclosure (embedded in code)
- World model outputs: LLM opinions, not ground truth
- Tail risk: systematically underestimated
- Weights: hand-set governance assertions
- Calibration: empirical feedback loop present but early
- Governance: Gardener role is a sketch, not a system
- Status: research prototype, use at your own risk
