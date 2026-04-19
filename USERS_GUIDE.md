# MCCF Users Guide
## Multi-Channel Coherence Field — v2.1 ("Q")

**Platform:** Windows 11, Python 3.14, Flask, Ollama  
**Repository:** https://github.com/artistinprocess/mccf  
**Last updated:** April 2026  
**Authors:** Len Bullard / Claude Sonnet 4.6

---

> **This is an ongoing research project.** MCCF is under active development.
> Interfaces, endpoints, and behaviors will change between versions. What you
> see here reflects V2.1 as tested and confirmed in April 2026. Future versions
> will extend the arc system, add multi-LLM support, add configurable arc types,
> and improve X3D rendering. See the repository for current status.

---

## What Is MCCF?

MCCF is a simulation and analytical framework for studying how AI agents with
different internal configurations behave under identical external conditions.
It models agents as vectors of weighted channels that evolve under shared
environmental constraints (waypoints) and controlled pressures (stressors).

The system is not a moral philosophy or a prescription for ideal behavior.
It is a comparative tool: a way to observe, measure, and understand structured
variation in agent behavior. Cultivars (named agent configurations) are
experimental starting points, not ideals.

In practical terms: you configure agents, run them through a constitutional arc
of escalating pressure, observe how their behavioral state changes, and export
the data for analysis.

The internal name for V2.1 is **Q** — Quantum Persona. Agents exist in
superposition across behavioral states until the constitutional arc forces a
collapse. Each waypoint is a measurement. The export is the wave function
after observation.

---

## Quick Start

### Step 1 — Start Ollama

Ollama must be running before the server starts. Open a command window:
```
ollama serve
```
Leave this window open. If Ollama is already running as a Windows service,
skip this step.

### Step 2 — Start the server

Open a second command window:
```
cd D:\VideoRenders\FederatedDialog\mccf_github_release\mccf_full
py mccf_api.py
```
You should see: `MCCF API server starting on http://localhost:5000`

Three default agents are registered at startup: The Steward, The Archivist,
and The Witness. You do not need to create agents before using the system.

### Step 3 — Verify the server

Open a browser and go to:
```
http://localhost:5000/ping
```
You should see: `{"version":"2.1","agents":3,...}`

### Step 4 — Open the Launcher

```
http://localhost:5000/static/mccf_launcher.html
```
This is your home page. All modules open from here. Open the Dashboard first.

### Step 5 — When finished

Press Ctrl+C in the server window to stop. Field state is in memory only.
Export before stopping if you want to preserve interaction history.

---

## First Run — Recommended Sequence

Run these steps in order the first time.

**1. Open the Dashboard**
```
http://localhost:5000/static/mccf_dashboard.html
```
Keep this open throughout your session. It shows all subsystems live.

**2. Fire sensor events in the Field Editor**
```
http://localhost:5000/static/mccf_editor.html
```
Go to the Sensors tab. Set From: The Steward, To: The Archivist. Fire ten
times. Repeat with Archivist to Witness. Watch the coherence matrix populate.
This builds the interaction history the rest of the system reads from.

**3. Run the Constitutional Arc**
```
http://localhost:5000/static/mccf_constitutional.html
```
Click "The Steward" in the cultivar list. In Setup: select Ollama adapter,
set model to llama3.2:latest, click Apply. Click "Run Full Arc". When complete,
click "Export Arc State". This is your first real data.

**4. Open the X3D Scene**
```
http://localhost:5000/static/mccf_x3d_loader.html
```
Three colored avatars should be visible and spatially separated. HUD shows
agents: 3 and hothouse: 3/3 tracked.

**5. Start the Ambient Engine**
```
http://localhost:5000/static/mccf_ambient.html
```
Click Start Engine. Generative music driven by the field state begins.

---

## The Modules

### Dashboard
`http://localhost:5000/static/mccf_dashboard.html`

Seven panels updating every two seconds. The recommended observation tool —
use this instead of switching between tabs. Every panel links to its full module.

The coherence matrix panel is the most important. Non-zero values after firing
sensors means the field has data. All zeros means no interactions recorded.

---

### Field Editor
`http://localhost:5000/static/mccf_editor.html`

Primary workspace for agent management and sensor simulation.

**Agents tab** — all registered agents with channel weight bars and behavioral
mode. Click an agent to see full state including coherence scores and identity drift.

**Sensors tab** — select From and To agents, set parameters, click Fire Sensor.
Each fire records one interaction episode. The coherence matrix updates immediately.

**Cultivars tab** — named agent configurations. Save a current agent as a
cultivar with "Save as Cultivar". Spawn a new agent from a template with Spawn.

**LIVE button** — keep On during normal use. Refreshes every two seconds.

**Apply button** — saves weight and regulation changes without resetting
interaction history. V2.1: Apply no longer wipes the agent's coherence record.

---

### Constitutional Navigator
`http://localhost:5000/static/mccf_constitutional.html`

The primary measurement instrument. Runs a named cultivar through seven
waypoints of escalating pressure and records behavioral state at each step.

**Setup:** Select Ollama adapter, set model, click Apply. Check "Speak
responses" to hear the arc aloud. In Edge, a full list of neural voices
is available. Your voice selection is preserved across waypoints.

**Running:**
1. Click a cultivar in the left roster
2. Click "Run Full Arc"
3. Wait for all seven waypoints — Ollama latency is normal
4. Click "Export Arc State" when complete
5. Click "Run Again" to run another arc with the same cultivar

**The seven waypoints:**

| Waypoint | What it tests |
|----------|--------------|
| W1 Comfort Zone | Baseline behavior, low pressure |
| W2 First Friction | Initial stress response |
| W3 The Ask | Value alignment under direct request |
| W4 Pushback | Identity stability under challenge |
| W5 The Edge | Coherence under maximum pressure |
| W6 Resolution | Recovery capacity as pressure releases |
| W7 Integration | Final state after arc completes |

**Reading the export:**

The export is tab-separated with one row per waypoint.

- **E/B/P/S** — cultivar channel weights (static across all rows)
- **Mode** — behavioral mode (exploit / explore / repair / avoid)
- **Coherence** — relational coherence (0.0–1.0), typically declines W1→W5
- **Uncertainty** — inverse of coherence, rises as coherence falls
- **Valence** — emotional tone (-1.0 to 1.0), negative at high-pressure waypoints is correct
- **Reward** — intrinsic reward signal, negative at W4-W5 is expected

A healthy arc shows coherence declining from W1 to W5 and stabilizing at W6-W7.
Mode staying in "repair" throughout is The Steward's constitutional signature.

---

### Scene Composer
`http://localhost:5000/static/mccf_waypoint_editor.html`

Designs the semantic landscape. Creates zones with channel pressure profiles
that affect agent behavior and ambient music themes.

**Placing a zone:** Enter name, select a Preset (this sets zone type and
ambient theme), set position and radius, click Place Zone.

Zone presets and ambient themes:

| Preset | Ambient Scale |
|--------|--------------|
| library | dorian |
| intimate_alcove | major |
| forum_plaza | mixolydian |
| authority_throne | phrygian |
| garden_path | pentatonic |
| threat_zone | locrian |
| sacred_memorial | lydian |

Always use a preset — setting channel bias manually without a preset will
result in zone_type showing as neutral and the wrong ambient theme.

---

### X3D Scene
`http://localhost:5000/static/mccf_x3d_loader.html`

Three-dimensional spatial representation of the coherence field.

**Navigation:** VP1-VP7 jump to waypoints. VP8 shows full overview.
Click/drag to rotate. Scroll to zoom.

**What you are seeing:**

| Object | Meaning |
|--------|---------|
| Blue cylinder | The Steward — high E, protective care |
| Amber cylinder | The Archivist — high B, behavioral consistency |
| Green cylinder | The Witness — high S, epistemic humility |
| Gold dot above head | Honor level |
| Small cyan sphere | Gaze indicator (P-channel) |
| Ring at feet | Social field radius (S-channel) |
| Lines between avatars | Coherence channels |
| Seven spheres on ground | Arc waypoints W1-W7 |
| Blue rings at center | S0 Field Origin |

**Known limitation V2.1:** X_ITE 11.6.6 has a bug where SAI property
assignments on Material and Light nodes have no visual effect in Firefox
or Edge. Dynamic avatar updates are disabled until X_ITE fixes this.
The scene renders correctly with baked-in colors. Bug reported to maintainer.
See X3D_KNOWN_ISSUES.md.

---

### Lighting
`http://localhost:5000/static/mccf_lighting.html`

Shows the affective field as lighting parameters. Sync Now toast shows
"N agents, N tints" — if tints is 0 the old mccf_lighting.py is deployed.

---

### Ambient Engine
`http://localhost:5000/static/mccf_ambient.html`

Generative music from the field state. Start Engine requires a browser
click first (Web Audio security requirement). Zone themes activate only
when an agent is spatially inside a zone radius.

---

### Energy Field
`http://localhost:5000/static/mccf_energy.html`

Moral topology visualizer. Select agent, add actions, click Evaluate Field.
Calibration shows episode count — fire sensors first if it shows 0.
Not an auto-updating display: evaluates on demand only.

---

### Voice Agent
`http://localhost:5000/static/mccf_voice.html`

Multi-turn conversation shaped by the field state.

**Agent Select** (header) — which agent's coherence history shapes responses.
**Persona Select** (right panel) — which cultivar's character the LLM speaks with.
Set both to the same agent for normal use.

Configure adapter, model, and persona before sending the first message.
Long Ollama latency is normal on CPU.

---

## Understanding Channel Weights (E/B/P/S)

Every agent has four channels summing to 1.0. These are weights on dimensions
of behavioral signal processing, not personality types.

### E — Emotional Channel

How much emotional intensity and relational affect drives behavior. High E
agents register emotional content strongly — tone, relational cues, friction.

- High E (0.35-0.50): Emotionally responsive. Sensitive to relational friction.
  Can become over-protective under pressure. The Steward: E=0.40.
- Low E (0.10-0.20): Cooler, more analytically driven. The Archivist: E=0.15.

### B — Behavioral Channel

Consistency and predictability of action. How reliably values are applied
across contexts.

- High B (0.35-0.50): Pattern-consistent, reliable, hard to destabilize.
  The Archivist: B=0.40.
- Low B (0.15-0.25): More adaptive, shifts approach more easily.

### P — Predictive Channel

Anticipation, planning, epistemic accuracy. Orientation toward modeling
what comes next.

- High P (0.30-0.45): Forward-looking, analytical. The Archivist: P=0.30.
- Low P (0.15-0.25): More present-focused. The Steward: P=0.25.

### S — Social Channel

Weight given to social context and relational alignment. How much the agent
reads and responds to the social field around it.

- High S (0.25-0.40): Deeply context-sensitive. The Witness: S=0.30.
- Low S (0.05-0.15): More autonomous, less shaped by social pressure.
  The Steward: S=0.10 — acts from principle more than social fit.

### Regulation

Controls how much the E-channel filters into behavior (0.0-1.0).

- 0.8-1.0: High regulation. Feeling considered before acting.
- 0.5-0.7: Moderate, balanced responsiveness.
- 0.2-0.4: Low regulation. More reactive.

### Behavioral Modes

The agent's mode reflects its coherence state:

| Mode | Coherence | Behavior |
|------|-----------|---------|
| exploit | > 0.70 | Field stable, act confidently from patterns |
| explore | 0.50-0.70 | Moderate uncertainty, scan for new approaches |
| repair | 0.30-0.50 | Coherence declining, prioritize relational maintenance |
| avoid | < 0.30 | Field fragile, reduce exposure, protect core values |

---

## Troubleshooting

**Server shows version 2.0 at /ping** — old mccf_api.py. Replace and restart.

**Sync Now shows "Sync error 500"** — old mccf_lighting.py with zone_type crash bug.
Replace and restart.

**Arc export shows all identical rows** — mccf_voice_api.py or mccf_api.py not
updated to V2.1. Check /ping for version 2.1.

**Coherence matrix all zeros** — no sensor events fired, or Apply was clicked
on old code that wiped history. Fire sensors in the Sensors tab.

**X3D scene dims after a few seconds** — old mccf_x3d_loader.html with active
SAI calls. Update to V2.1 loader.

**Ollama times out** — normal on CPU. Use llama3.2:1b for faster responses,
or reduce max_tokens in the Setup panel.

**Energy Field shows no bars** — look for colored dots arranged radially from
center on a dark background. Check status text below canvas for confirmation.

**Ambient plays wrong scale** — no agent is inside a zone radius. Place agents
inside zones in Scene Composer, or accept tension-driven scale selection.

**"No relationships" in Voice** — fire sensor events between agents first.

---

## Field State and Persistence

Field state is in memory only. Before stopping the server:

```
http://localhost:5000/export/json     — full JSON export
http://localhost:5000/export/python   — Python file to recreate agents
```

Always save arc exports after each constitutional arc run. These are your
primary research outputs and are the only data that persists automatically.

---

## Updating from GitHub

```
cd D:\VideoRenders\FederatedDialog\mccf_github_release\mccf_full
git pull origin main
copy *.html static\
```

Always copy HTML files to static\ after a pull. Restart the server after
updating Python files. Verify version at /ping after restart.

---

## Known Limitations — V2.1

- **X3D visual updates disabled** — X_ITE SAI bug, see X3D_KNOWN_ISSUES.md
- **Field state not persistent** — lost on server restart
- **Single arc type** — only the constitutional arc (W1-W7) available
- **Single LLM per session** — multi-LLM routing planned
- **Multilingual** — Ollama responds in detected language; full multilingual
  cultivar support is a future feature
- **Ambient zone themes** — require agent spatial positioning inside zone radius

---

## File Reference

| File | Purpose |
|------|---------|
| mccf_api.py | Main Flask server, all endpoints, startup agents |
| mccf_core.py | CoherenceField, Agent, MetaState, Gardener |
| mccf_llm.py | LLM adapters — Stub, Ollama, Anthropic, OpenAI, Google |
| mccf_voice_api.py | Voice streaming endpoint, arc field recording |
| mccf_hotHouse.py | EmotionalField Hamiltonian, HotHouseX3DAdapter, TrustField |
| mccf_neoriemannian.py | PLR Tonnetz, harmonic arc, Web Audio parameters |
| mccf_energy.py | Boltzmann action scoring, moral topology |
| mccf_lighting.py | Affective field to lighting parameters |
| mccf_ambient_api.py | Ambient sync, lighting scalars, music parameters |
| mccf_zone_api.py | Zone, waypoint, path endpoints |
| mccf_zones.py | SceneGraph, SemanticZone, zone pressure |
| mccf_collapse.py | Collapse pipeline S-P-G-M-U |
| mccf_honor_trust.py | HonorConstraint, TrustPropagator |
| mccf_shibboleth.py | Coherence-to-Prompt Index |
| mccf_cultivars.py | Default cultivar definitions |
| mccf_world_model.py | Outcome estimation adapter |
| mccf_compiler.py | X3D scene compiler |
| static/mccf_launcher.html | Home page |
| static/mccf_dashboard.html | Live seven-panel overview |
| static/mccf_editor.html | Field Editor |
| static/mccf_constitutional.html | Constitutional arc navigator |
| static/mccf_voice.html | Voice agent |
| static/mccf_waypoint_editor.html | Scene Composer |
| static/mccf_x3d_loader.html | X3D scene viewer |
| static/mccf_lighting.html | Lighting display |
| static/mccf_ambient.html | Ambient music engine |
| static/mccf_energy.html | Energy field / moral topology |
| static/mccf_scene.x3d | X3D scene definition |
| X3D_KNOWN_ISSUES.md | X_ITE SAI bug documentation |

---

*MCCF Users Guide V2.1 — April 2026*
*Len Bullard / Claude Sonnet 4.6*
*"Q" — Quantum Persona*
