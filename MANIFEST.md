# MCCF — Full Package Manifest
## Updated Day 60 — June 27, 2026

---

## Core Engine
- `mccf_core.py`             — Agent, CoherenceField, Librarian, Gardener
- `mccf_zones.py`            — SemanticZone, Waypoint, AgentPath, SceneGraph
- `mccf_llm.py`              — LLM adapter layer (Anthropic, OpenAI, Ollama, Google, Stub)
- `mccf_cultivars.py`        — Cultivar definitions and constitutional types
- `mccf_cultivar_lambda.py`  — Lambda expressions for cultivar behavioral dynamics
- `mccf_world_model.py`      — WorldModelAdapter, EnergyField, risk disclosure
- `mccf_energy.py`           — Moral topology and energy field computation
- `mccf_drift.py`            — Field drift and attractor dynamics
- `mccf_collapse.py`         — Collapse detection and recovery
- `mccf_compiler.py`         — Scene and arc compilation
- `mccf_honor_trust.py`      — Honor/trust relationship layer
- `mccf_neoriemannian.py`    — Neo-Riemannian harmonic field model
- `mccf_couplers.py`         — Field coupling between agents
- `mccf_hotHouse.py`         — Hothouse dynamics (accelerated field evolution)
- `mccf_zone_attractor.py`   — Zone attractor fields
- `mccf_shibboleth.py`       — Shibboleth / recognition layer
- `mccf_chorus.py`           — Chorus voice synthesis and field response

## API Server
- `mccf_api.py`              — Flask REST server: playback, scene, arc, field, export
- `mccf_zone_api.py`         — Zone/waypoint/path/scene blueprint
- `mccf_voice_api.py`        — Voice agent SSE streaming blueprint
- `mccf_ambient_api.py`      — /ambient/sync unified output bus (music + lighting + field)
- `mccf_scene_generate_api.py` — Scene generation API
- `mccf_scene_wrapper.py`    — Scene XML wrapper and utilities
- `mccf_playback.py`         — Arc playback engine: step, session, waypoint resolution
- `mccf_x3d_generator.py`    — Procedural X3D scene generation
- `mccf_zone_api.py`         — Zone management blueprint
- `mccf_cultivar_lambda.py`  — Cultivar lambda behavioral layer

## Browser Interfaces (`static/`)
### Scene Authoring
- `mccf_scene_composer.html`         — V4: Scene authoring — zones, waypoints, paths, agents, events, export
- `mccf_events_editor_prototype_2.html` — Camera, light, fog, behavior event cue editor with timeline
- `mccf_waypoint_editor.html`        — Legacy waypoint/zone editor
- `mccf_character_creator.html`      — Character/cultivar authoring
- `mccf_constitutional.html`         — Constitutional navigator

### Playback and Monitoring
- `mccf_x3d_loader.html`             — X3D/X_ITE live scene player: arc playback, EventCues, camera system
- `mccf_dashboard.html`              — Field state dashboard
- `mccf_editor.html`                 — Agent + coherence field editor
- `mccf_launcher.html`               — Scene/arc launcher

### Specialist Tools
- `mccf_voice.html`                  — Voice agent with Web Speech API
- `mccf_ambient.html`                — Generative ambient music engine
- `mccf_lighting.html`               — Real-time lighting visualizer
- `mccf_sound_panel.html`            — Zone audio panel
- `mccf_energy.html`                 — Moral topology visualizer
- `mccf_x3d_demo.html`               — X3D/X_ITE demo scene

## X3D Assets (`static/x3d/`)
- Scene X3D files exported from Scene Composer
- `MCCFAgent.x3d`, `MCCFZone.x3d`, `MCCFField.x3d`, etc. — reusable X3D prototypes

## Scene Data (`scenes/`)
- `{scene_name}_scene.xml`           — Scene XML: zones, waypoints, paths, agents, EventCues

## HAnim (`HAnim/`)
- HAnim 2.0 avatar definitions and behavior specifications

## Schemas (`schemas/`)
- JSON schemas for API validation

## Specifications (`docs/`)
- `MCCF_Camera_System_Spec_v1.2.md`        — Camera EventCues: shot types, VP_Free pattern, -Z convention
- `MCCF_Events_Editor_Architecture.md`      — Baked vs runtime events, vessel principle, SAI rules, coordinate system
- `MCCF_V5_Semantic_Field_Spec.md`          — Semantic field specification
- `MCCF_HAnim_Behavior_Activation_Spec.md`  — HAnim behavior activation
- `MCCF_HAnim_Editor_Spec.md`               — HAnim editor specification
- `MCCF_Coupler_Implementation_Spec.md`     — Field coupler implementation
- `MCCF_Relational_Dynamics_Extension_Spec.md` — Relational dynamics
- `X3D_KNOWN_ISSUES.md`                     — X_ITE/X3D known issues and workarounds
- `CONFIGURATION_REFERENCE.md`              — Configuration reference
- `SYSTEMS_MANUAL.md`                       — Full systems manual
- `USERS_GUIDE.md`                          — User guide
- `PHILOSOPHY.md`                           — Project philosophy
- `FOUNDATIONS.md`, `THEORETICAL_FOUNDATIONS.md`, `MATHEMATICAL_THEORY.md` — Theory
- `DOMAINS.md`                              — Domain model
- `CONTRIBUTING.md`, `CONTRIBUTORS.md`      — Contribution guide

## Session Seeds (`Seeds/`)
- Day-by-day session handoff documents
- Each seed carries: GitHub baseline commit, confirmed working state, remaining tasks, key architecture facts
- **Required reading at the start of each session**

## Tests
- `test_drift.py`, `test_playback.py`, `test_scene_generate_api.py`
- `test_scene_wrapper.py`, `test_x3d_generator.py`, `test_zone_attractor.py`

## Run
```bash
pip install -r requirements.txt
python mccf_api.py
# Open mccf_x3d_loader.html or mccf_scene_composer.html at http://localhost:5000/static/
```

---

## Architecture Overview

### Signal Flow
```
Constitutional Navigator → EmotionalArc XML
    ↓
Arc Playback (mccf_playback.py + mccf_api.py)
    ↓ WP arrival events
X3D Loader (mccf_x3d_loader.html)
    ├── EventCues → Camera cuts (VP_Free via CAM_Free_Transform SAI)
    ├── EventCues → Light intensity
    ├── EventCues → Behavior clips (HAnim TimeSensor)
    └── EventCues → Fog / Background
    ↓
CoherenceField (EBPS values from arc waypoints)
    ↓
/ambient/sync ← field state
    ├── music params  → mccf_ambient.html
    ├── lighting      → mccf_lighting.html
    └── voice params  → mccf_voice.html
    ↓
Chorus → synthesized field response text
```

### Camera System (Day 58–60)
Two fundamentally different camera types — never mixed:
- **Baked:** agent_eye/agent_side bind named VP inside agent Transform. Named `viewpoint=` binds any authored VP.
- **Runtime:** shot types (wide, medium, closeup, etc.) drive VP_Free via CAM_Free_Transform SAI writes.
- VP_Free is an implementation vessel — never in author vocabulary, never in cue data.
- X3D cameras face **-Z**. Look-at yaw: `atan2(-dx, -dz)`. SAI writes to Viewpoint position/orientation are ignored by X_ITE — write to the parent Transform instead.

### EventCues Pipeline (Day 55–60)
- EventCues live in `scenes/{name}_scene.xml`, NOT in the X3D file
- Loader reads EventCues at scene load via `/scene/load/scene/raw`
- Triggers: `"w2 arrive"` (scene XML name) or `"Waypt2 arrive"` (server ID) — both checked
- Delay scheduling via `_pendingCueTimers`
- Camera, light, fog, background, behavior tracks all dispatched from `fireEventCuesForTrigger()`

---

## Federated Design
This codebase was developed across multiple LLM collaboration sessions:
- **ChatGPT:** initial prototype scaffold and formal spec
- **Gemini:** breadth passes and alternative framings
- **Claude:** architectural continuity, zone/semantic pressure layer, LLM adapter interface,
  voice+prosody pipeline, ambient music engine, X3D scene composer, EventCues camera system,
  baked/runtime architecture, HAnim behavior layer

Each pass contributes what its architecture favors.
The GitHub is the shared phenotype.
Contributions welcome — prove ideas with code.

---

## Risk Disclosure
- World model outputs: LLM opinions, not ground truth
- Tail risk: systematically underestimated by LLMs
- Field weights: hand-set governance assertions, not learned
- Calibration: empirical feedback loop present but early
- Governance: Gardener role is a sketch, not a system
- Camera system: runtime computed, not terrain-aware (Saturn III)
- Status: research prototype — use at your own risk
