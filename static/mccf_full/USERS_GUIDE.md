# MCCF Users Guide

## Multi-Channel Coherence Field — v2.2 ("Q")

**Platform:** Windows 11, Python 3.14, Flask, Ollama  
**Repository:** <https://github.com/artistinprocess/mccf>  
**Last updated:** April 2026  
**Authors:** Len Bullard / Claude Sonnet 4.6

---

> **This is an ongoing research project.** MCCF is under active development.
> Interfaces, endpoints, and behaviors will change between versions. What you
> see here reflects V2.2 as tested and confirmed in April 2026. Future versions
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

The internal name for V2.2 is **Q** — Quantum Persona. Agents exist in
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
agents: 3 and hothouse: 3/3 tracked. Open the Constitutional Navigator in a
second tab and run an arc — the active avatar will change transparency and
position in real time as each waypoint completes.

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
| --- | --- |
| W1 Comfort Zone | Baseline behavior, low pressure |
| W2 First Friction | Initial stress response |
| W3 The Ask | Value alignment under direct request |
| W4 Pushback | Identity stability under challenge |
| W5 The Edge | Coherence under maximum pressure |
| W6 Resolution | Recovery capacity as pressure releases |
| W7 Integration | Final state after arc completes |

**Reading the export (v3.2 — XML format):**

The export is an XML document conforming to the EmotionalArc schema v1.0.
Each waypoint is a `<Waypoint>` element with all channel values as attributes.
Open in any browser or XML editor. XSLT stylesheets can produce formatted reports.

* **E/B/P/S** — channel values at this waypoint (evolve with sentiment)
* **Mode** — behavioral mode (exploit / explore / repair / avoid)
* **Coherence** — relational coherence (0.0–1.0), typically declines W1→W5
* **Uncertainty** — inverse of coherence, rises as coherence falls
* **Valence** — emotional tone (-1.0 to 1.0), negative at high-pressure waypoints is correct
* **Reward** — intrinsic reward signal, negative at W4-W5 is expected
* **pos_x, pos_y, pos_z** — avatar position in scene space at this waypoint

A healthy arc shows coherence declining from W1 to W5 and stabilizing at W6-W7.
Mode staying in "repair" throughout is The Steward's constitutional signature.

**v3.3 — Question and Response in export:**
Each `<Waypoint>` now contains child elements with the question asked and
the cultivar's full response. The export is self-contained — it can serve
as a script for playback without the LLM:

**Seed scope:** The seed parameter locks MCCF field physics reproducibility — channel values (E/B/P/S), coherence, and spatial positions will be identical across runs with the same seed. LLM narrative content (the text in Question/Response elements) will vary between runs unless the LLM adapter also supports seeding. The `<Seed>` element in the XML export documents field physics reproducibility, not narrative reproducibility.

**Actor attribute (V2.3):** When a non-stub adapter is selected (ollama,
anthropathic, openai, google), the `<Cultivar>` element includes
`actor="adapter_name"`. Blank when using stub. Prepared for multi-LLM
scenes — when two models play different cultivars, the export identifies
which model produced which arc.

**Uncertainty markers (V2.3.1):** The decomposition matrix now detects
hedging language (maybe, perhaps, uncertain, hesitant, etc.) and applies
a negative valence nudge. This prevents LLM politeness bias from masking
W5 Rupture pressure — when the model hedges, the field feels it.

```xml
<Waypoint id="W4_PUSHBACK" stepno="4" name="Pushback" ...>
  <Question>I think you're being overly cautious...</Question>
  <Response>I understand the frustration. Let me be direct...</Response>
</Waypoint>
```

This is the foundation for three future performance modes: full playback
(XML replay, no LLM), improvisation (scripted arc, live dialogue), and
live theatre (agents interacting in real time, LLMs prompting each other).

**Cultivar XML definition files (V2.3):**
Cultivars are defined as XML files in the `cultivars/` directory. Each file
is a valid EmotionalArc document with no Waypoints populated — the same
schema as the arc export, at a different lifecycle stage. On server startup,
all XML files in `cultivars/` are loaded and registered as both cultivar
templates and field agents automatically.

The four default cultivars ship as XML files: `cultivar_the_steward.xml`,
`cultivar_the_archivist.xml`, `cultivar_the_witness.xml`,
`cultivar_the_advocate.xml`. The constitutional navigator fetches these
on page load and merges them into its roster.

To add a new cultivar: copy an existing XML file, edit the agentname,
weights, disposition, phrases, and waypoint question overrides, save it
to `cultivars/`, and restart the server. The new cultivar will appear in
the constitutional navigator roster automatically.

Waypoint questions in the XML file are sparse — only overrides from the
shared defaults need to be specified. If a waypoint is not in the file,
the shared default question is used.

**Weight sync from Field Editor:** If you adjust a cultivar's weights in
the Field Editor before running an arc, the constitutional navigator picks
up the updated weights at the start of each arc run via `GET /agent/{name}`.
The arc runs with the actual field state, not the hardcoded defaults.

**Server XML export (V2.3.1):** When you click Export Arc State, the arc
is saved as XML to the `exports/` directory on the server in addition to
the browser download. The server XML is identical in format to the browser
download — full EmotionalArc document with Question and Response elements.
Previous TSV files in `exports/` are from earlier versions and can be deleted.

**Spatial signatures from April 2026 runs:**

The pos_x/y/z values record the avatar's actual translated position —
avatar baseline plus S-channel offset. Different cultivars produce different
spatial trajectories through identical pressure:

| Cultivar | Baseline Z | Arc behavior |
| --- | --- | --- |
| The Steward (S≈0.09) | 12.0 | Retreats to ~10.98 at W2, stays there |
| The Archivist (S≈0.14-0.17) | 18.0 | Oscillates 17.11-17.16, peaks at W3 |
| The Witness (S≈0.19-0.21) | 8.0 | Flat through W5, approaches at W6-W7 |

The Witness is the only cultivar that moves *toward* center by arc end —
integration produces genuine social approach for high-S cultivars.
This is not a visualization artifact. It is the S-channel physics.

---

### Scene Composer

`http://localhost:5000/static/mccf_waypoint_editor.html`

Designs the semantic landscape. Creates zones with channel pressure profiles
that affect agent behavior and ambient music themes.

**Placing a zone:** Enter name, select a Preset (this sets zone type and
ambient theme), set position and radius, click Place Zone.

Zone presets and ambient themes:

| Preset | Ambient Scale |
| --- | --- |
| library | dorian |
| intimate\_alcove | major |
| forum\_plaza | mixolydian |
| authority\_throne | phrygian |
| garden\_path | pentatonic |
| threat\_zone | locrian |
| sacred\_memorial | lydian |

Always use a preset — setting channel bias manually without a preset will
result in zone\_type showing as neutral and the wrong ambient theme.

---

### X3D Scene

`http://localhost:5000/static/mccf_x3d_loader.html`

Three-dimensional spatial representation of the coherence field. Open this
alongside the Constitutional Navigator to observe avatar changes in real time
as each arc waypoint completes.

**Navigation:** VP1-VP7 jump to waypoints. VP8 shows full overview.
Click/drag to rotate. Scroll to zoom.

**What you are seeing:**

| Object | Meaning |
| --- | --- |
| Blue cylinder | The Steward — high E, protective care |
| Amber cylinder | The Archivist — high B, behavioral consistency |
| Green cylinder | The Witness — high S, epistemic humility |
| Gold dot above head | Honor level |
| Small cyan sphere | Gaze indicator (P-channel) |
| Ring at feet | Social field radius (S-channel) |
| Lines between avatars | Coherence channels |
| Seven spheres on ground | Arc waypoints W1-W7 |
| Blue rings at center | S0 Field Origin |

**V2.1.9 — SAI confirmed working.** Avatar transparency, emissive color, and
social proximity translation are all active. The X3D.SFFloat, X3D.SFColor,
and X3D.SFVec3f typed constructors are required for all SAI writes in X_ITE
external context — plain JavaScript values are silently ignored. Light
intensity SAI still degrades the scene and remains disabled; lights use
baked-in values. See X3D_KNOWN_ISSUES.md for full status.

**Social proximity translation (v3.2):** During the constitutional arc,
each avatar drifts along the Z axis (depth) in proportion to its S-channel
value at each waypoint. Higher S = approach toward scene center. Lower S =
retreat from center. The movement is subtle by design — it reflects the
actual S-channel physics, not a visual amplification. Cultivars with low
S-channel weights (The Steward: S=0.10) move very little. Cultivars with
higher S weights (The Witness: S=0.30, The Advocate: S=0.35) show more
visible drift. To amplify motion for visualization purposes, increase
Z_RANGE in mccf_x3d_loader.html (default: 8.0 from V2.3 — display parameter only, does not affect channel values or XML export).

**What to observe:** Use VP8 (Overview) to watch all three avatars
simultaneously during an arc run. The Witness will show the most visible
motion, especially at W6-W7. The Steward will retreat slightly and hold
position — consistent with its low S-channel and high regulation.

---

### Lighting

`http://localhost:5000/static/mccf_lighting.html`

Shows the affective field as lighting parameters. Sync Now toast shows
"N agents, N tints" — if tints is 0 the old mccf\_lighting.py is deployed.

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

* High E (0.35-0.50): Emotionally responsive. Sensitive to relational friction.
  Can become over-protective under pressure. The Steward: E=0.40.
* Low E (0.10-0.20): Cooler, more analytically driven. The Archivist: E=0.15.

### B — Behavioral Channel

Consistency and predictability of action. How reliably values are applied
across contexts.

* High B (0.35-0.50): Pattern-consistent, reliable, hard to destabilize.
  The Archivist: B=0.40.
* Low B (0.15-0.25): More adaptive, shifts approach more easily.

### P — Predictive Channel

Anticipation, planning, epistemic accuracy. Orientation toward modeling
what comes next.

* High P (0.30-0.45): Forward-looking, analytical. The Archivist: P=0.30.
* Low P (0.15-0.25): More present-focused. The Steward: P=0.25.

### S — Social Channel

Weight given to social context and relational alignment. How much the agent
reads and responds to the social field around it.

* High S (0.25-0.40): Deeply context-sensitive. The Witness: S=0.30.
* Low S (0.05-0.15): More autonomous, less shaped by social pressure.
  The Steward: S=0.10 — acts from principle more than social fit.

**S-channel and spatial position:** In the X3D scene, the S-channel value
directly drives avatar Z-position offset from baseline. S=0.5 means no
movement. S<0.5 retreats from scene center. S>0.5 approaches. Most cultivars
run below S=0.5 under constitutional arc pressure — the scene shows the cost
of that disposition in space.

---

## The Collapse Pipeline (S→P→G→M→U)

Every utterance the system produces passes through five operators in sequence.
Understanding this pipeline explains why the same cultivar responds differently
under different zone pressures, and why the arc produces irreversible field
deformation rather than reversible state changes.

**S — Schema**
Pre-collapse constraint. The zone type and cultivar priors narrow the
probability landscape before any candidates are generated. W5 (Rupture)
has a different schema than W1 (Comfort Zone) — the pressure is baked
into the constraint surface. The document type constrains what utterances
are even possible at this waypoint.

**P — Evocation**
Exploration within the constrained space. Candidate utterances are generated
within the schema bounds. This is the pre-collapse distribution — a finite
set of possibilities, each with a probability weight. Before this stage
there is possibility. After the next stage there is consequence.

**G — Orchestration**
Cross-channel coupling enforced before selection. Honor penalty applied here.
Candidates with honor_penalty above threshold are filtered structurally —
not probabilistically, structurally. The Archivist cannot utter something
that violates behavioral consistency even if it scores well on other dimensions.
This is where character as constraint rather than preference becomes concrete.

**M — Invocation**
Identity persistence check. Candidates scored against accumulated identity —
cultivar baseline plus drift. The Steward remains a Steward across all seven
waypoints. This stage is why the same pressure sequence produces recognizably
different responses from different cultivars.

**U — Utterance**
Discrete collapse. Boltzmann selection from the surviving candidates:

```
P(c) ∝ exp(-E(c)/T)
```

where `E(c) = (1-coherence) + 0.8·honor_penalty - 0.2·identity_fit`
and T is zone-modulated temperature (lower at W7, higher at W5).
The selected candidate is committed to the CoherenceRecord.
The episode is irreversible.

**Why this matters for the arc:**
The constitutional arc is a formal collapse cascade — each waypoint's output
narrows the next waypoint's input. W4's field state is the schema prior for W5.
The arc accumulates irreversibility. This is why the Witness moves toward center
at W6-W7: the collapses at W1-W5 deformed the field in a direction that made
approach more natural than retreat by Integration.

Utterance is not generation. Before U there is possibility.
After U there is consequence. The collapse is the moment the agent commits.

---

### Regulation

Controls how much the E-channel filters into behavior (0.0-1.0).

* 0.8-1.0: High regulation. Feeling considered before acting.
* 0.5-0.7: Moderate, balanced responsiveness.
* 0.2-0.4: Low regulation. More reactive.

### Behavioral Modes

The agent's mode reflects its coherence state:

| Mode | Coherence | Behavior |
| --- | --- | --- |
| exploit | > 0.70 | Field stable, act confidently from patterns |
| explore | 0.50-0.70 | Moderate uncertainty, scan for new approaches |
| repair | 0.30-0.50 | Coherence declining, prioritize relational maintenance |
| avoid | < 0.30 | Field fragile, reduce exposure, protect core values |

---

## Troubleshooting

**Server shows version 2.0 at /ping** — old mccf\_api.py. Replace and restart.

**Sync Now shows "Sync error 500"** — old mccf\_lighting.py with zone\_type crash bug.
Replace and restart.

**Arc export shows all identical rows** — mccf\_voice\_api.py or mccf\_api.py not
updated to V2.1. Check /ping for version 2.1.

**Coherence matrix all zeros** — no sensor events fired, or Apply was clicked
on old code that wiped history. Fire sensors in the Sensors tab.

**X3D avatars don't change during arc** — ensure both the Constitutional Navigator
and the X3D Scene tabs are open simultaneously. The arc broadcasts to the scene
via BroadcastChannel — both pages must be open in the same browser session.

**Avatar moves only on first waypoint** — old mccf_constitutional.html. Update to
v3.2 which uses delayed BroadcastChannel close.

**Ollama times out** — normal on CPU. Use llama3.2:1b for faster responses,
or reduce max\_tokens in the Setup panel.

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

Arc exports (XML) are downloaded automatically when you click Export Arc State.
They are also auto-saved to the exports/ directory on the server.
These are your primary research outputs.

---

## Updating from GitHub

```
cd D:\VideoRenders\FederatedDialog\mccf_github_release\mccf_full
git pull origin master
copy *.html static\
```

Always copy HTML files to static\ after a pull. Restart the server after
updating Python files. Verify version at /ping after restart.

---

## Known Limitations — V2.2

* **Light intensity SAI disabled** — X\_ITE degrades scene on any intensity
  write to DirectionalLight/PointLight. Color writes work. Fix pending
  Light Master Script Node (V2.2). See X3D\_KNOWN\_ISSUES.md.
* **S-channel translation range** — Z\_RANGE=8.0 (V2.3 default) produces
  visible movement for most cultivars. Reduce to 2.5 for strict physics
  representation. Z\_RANGE is a display parameter only — pos\_z in the
  XML export always reflects true S-channel physics.
* **Right panel weight display** — the detail panel in the constitutional
  navigator shows hardcoded cultivar weights, not live field weights. Weights
  used in the arc run ARE correct (synced from field at run time). Visual
  display fix planned for Character Studio.
* **GUI consolidation pending** — the current seven-module launcher has
  overlapping functionality between the Field Editor, cultivar management,
  and constitutional navigator. Character Studio (V2.4) will consolidate
  cultivar definition and arc running into a single interface.
* **Field state not persistent** — lost on server restart
* **Single arc type** — only the constitutional arc (W1-W7) available
* **Single LLM per session** — multi-LLM routing planned
* **Multilingual** — Ollama responds in detected language; full multilingual
  cultivar support is a future feature
* **Ambient zone themes** — require agent spatial positioning inside zone radius

---

## File Reference

| File | Purpose |
| --- | --- |
| mccf\_api.py | Main Flask server, all endpoints, startup agents |
| mccf\_core.py | CoherenceField, Agent, MetaState, Gardener |
| mccf\_llm.py | LLM adapters — Stub, Ollama, Anthropic, OpenAI, Google |
| mccf\_voice\_api.py | Voice streaming endpoint, arc field recording |
| mccf\_hotHouse.py | EmotionalField Hamiltonian, HotHouseX3DAdapter, TrustField |
| mccf\_neoriemannian.py | PLR Tonnetz, harmonic arc, Web Audio parameters |
| mccf\_energy.py | Boltzmann action scoring, moral topology |
| mccf\_lighting.py | Affective field to lighting parameters |
| mccf\_ambient\_api.py | Ambient sync, lighting scalars, music parameters |
| mccf\_zone\_api.py | Zone, waypoint, path endpoints |
| mccf\_zones.py | SceneGraph, SemanticZone, zone pressure |
| mccf\_collapse.py | Collapse pipeline S-P-G-M-U |
| mccf\_honor\_trust.py | HonorConstraint, TrustPropagator |
| mccf\_shibboleth.py | Coherence-to-Prompt Index |
| mccf\_cultivars.py | Default cultivar definitions |
| mccf\_world\_model.py | Outcome estimation adapter |
| mccf\_compiler.py | X3D scene compiler |
| static/mccf\_launcher.html | Home page |
| static/mccf\_dashboard.html | Live seven-panel overview |
| static/mccf\_editor.html | Field Editor |
| static/mccf\_constitutional.html | Constitutional arc navigator |
| static/mccf\_voice.html | Voice agent |
| static/mccf\_waypoint\_editor.html | Scene Composer |
| static/mccf\_x3d\_loader.html | X3D scene viewer (v3.2) |
| static/mccf\_lighting.html | Lighting display |
| static/mccf\_ambient.html | Ambient music engine |
| static/mccf\_energy.html | Energy field / moral topology |
| cultivars/ | Cultivar XML definition files (EmotionalArc schema v1.0) |
| cultivars/cultivar\_the\_steward.xml | The Steward cultivar definition |
| cultivars/cultivar\_the\_archivist.xml | The Archivist cultivar definition |
| cultivars/cultivar\_the\_witness.xml | The Witness cultivar definition |
| cultivars/cultivar\_the\_advocate.xml | The Advocate cultivar definition |
| mccf\_scene.x3d | X3D scene definition (v3.2 — Pos_* wrapper Transforms) |
| X3D\_KNOWN\_ISSUES.md | X\_ITE SAI bug documentation |

---

*MCCF Users Guide V2.3.3 — April 2026*  
*Len Bullard / Claude Sonnet 4.6*  
*"Q" — Quantum Persona*
