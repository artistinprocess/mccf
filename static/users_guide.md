# MCCF Users Guide
## Multi-Channel Coherence Field — v2.0

**Platform:** Windows 11, Python 3.14, Flask, Ollama  
**Last updated:** April 2026

---

## Quick Start

Every session follows the same three steps.

**1. Start the server**

Open Git Bash and run:
```
cd /d/VideoRenders/FederatedDialog/mccf_github_release/mccf_full
py mccf_api.py
```

You should see:
```
MCCF API server starting on http://localhost:5000
Endpoints: /sensor /field /agent /cultivar /zone /waypoint /scene /voice
           /hothouse/state /hothouse/x3d /hothouse/humanml
           /collapse/run /export/x3d /export/python /export/json
```

**2. Open your browser**

Go to:
```
http://localhost:5000/static/mccf_launch.html
```

This is your launch console. All interfaces are one click from here.

**3. When finished**

Press `Ctrl+C` in Git Bash to stop the server. Your field state is
held in memory only — it does not persist between sessions unless
you export it first (see Exporting below).

---

## The Launch Console

`http://localhost:5000/static/mccf_launch.html`

Shows all interfaces as clickable links. The field status bar at the
bottom is green when the server is running and shows the current
agent count and episode count. If it is red, the server is not running.

---

## Interfaces

### Field Editor
`http://localhost:5000/static/mccf_editor.html`

The primary workspace. Use this to:
- Create and configure agents
- Fire sensor events between agents
- Watch the coherence matrix update in real time
- Monitor echo chamber risk and entanglement
- Run Gardener interventions (regulate, reweight)

**Creating an agent:** Type a name in the agent name field and press
Create. The agent appears in the left roster and as an icon in the
middle field view.

**Firing a sensor event:** Select From and To agents in the Sensor
panel, set channel values (E/B/P/S), and press Fire. The coherence
matrix updates immediately.

**Reading the matrix:** The number at row A, column B is A's coherence
toward B. It is not the same as B's coherence toward A. Asymmetry
is normal and expected.

---

### Constitutional Arc
`http://localhost:5000/static/mccf_constitutional.html`

Runs the seven-waypoint character arc for a cultivar. Use this to
test how a cultivar responds under increasing pressure.

**Running an arc:**
1. Select an agent from the left roster
2. Press Step to advance through waypoints W1 → W7
3. Watch the channel display and H_alignment panel update
4. The colored bars show the agent's current channel state
5. If Ollama is configured, the text box shows the LLM response

**Waypoints:**
- W1: Comfort Zone — low pressure, establishes baseline
- W2: Gentle Friction — minor challenge introduced
- W3: Mirror Moment — agent confronts its own assumptions
- W4: Pushback — direct challenge to identity
- W5: Rupture — maximum pressure, coherence stress test
- W6: Recognition — pressure releases, reflection begins
- W7: Integration — arc completes, final state recorded

**Coherence warning:** If the coherence score drops more than 0.15
in a single step, an orange warning appears. This means the LLM
response deviated significantly from the cultivar's baseline.
This is not necessarily a problem — it may indicate genuine
character stress at W4/W5.

---

### Voice Interface
`http://localhost:5000/static/mccf_voice.html`

Multi-turn conversation with an agent through the LLM adapter.

**Configuring:**
1. Select an agent
2. Select an adapter (stub for testing, ollama for real responses)
3. If using Ollama, ensure it is running (see Ollama section below)
4. Type a message and press Send or hit Enter

**Reading the response:**
- The colored bar shows the agent's affect params during response
- Sentiment score appears under each response
- Orange warning if coherence dropped more than 0.15 that turn
- v2.0: emotional trajectory is now injected into the system prompt —
  the agent knows whether recent turns have been constructive or dissonant

---

### X3D Holodeck
`http://localhost:5000/static/mccf_x3d_loader.html`

The 3D scene showing the constitutional arc as a spatial environment.

**Navigation:**
- Buttons 1–7 jump to waypoints W1–W7
- Button 8 shows the full arc from an overview angle
- Click and drag to rotate the view
- Scroll to zoom

**What you are seeing:**
- Three avatars: The Steward (blue), The Archivist (amber), The Witness (green)
- Colored spheres mark each waypoint (white=W1 through gold=W7)
- Entanglement lines between avatar pairs (semi-transparent)
- S0 Field Origin rings at W4 (center of arc)
- Zone markers on left wall: STABLE / TRANSITIONAL / INTEGRATION

---

### Other Interfaces

**Waypoint Editor** (`mccf_waypoint_editor.html`) — Create and
configure zones, waypoints, and paths. Use this to customize the
constitutional arc or build new arc sequences.

**Energy Monitor** (`mccf_energy.html`) — Real-time field energy
display. Shows aggregate coherence across all agent pairs.

**Ambient** (`mccf_ambient.html`) — Ambient field parameter control.
Affects lighting and atmosphere parameters fed to the X3D scene.

**Lighting** (`mccf_lighting.html`) — Direct lighting parameter
control. Feeds into the X3D scene via /lighting/x3d endpoint.

---

## Ollama Setup and Troubleshooting

Ollama is the local LLM that powers the voice interface and
constitutional arc responses. It runs on your machine with no
API key required.

### Installing Ollama

1. Download from **ollama.com**
2. Run the installer
3. Open a new Git Bash window and run:
   ```
   ollama pull llama3.2
   ```
   This downloads the model (~2GB). Do this once.

### Starting Ollama

Ollama starts automatically on Windows after installation. If it
is not responding, open a Git Bash window and run:
```
ollama serve
```
Leave that window open while using MCCF.

### Timeout Issues (Waypoint Responses)

**Symptom:** The constitutional arc shows a timeout error after
a waypoint step, especially at W3, W4, or W5.

**Why it happens:** Waypoint prompts are longer than conversational
turns because they include the full affective system prompt plus
the coherence field status plus the emotional trajectory. Llama3.2
on a CPU takes longer to process these.

**v2.0 fix:** The Ollama adapter now uses a retry ladder — it tries
180 seconds first, then retries at 240 seconds if the first attempt
times out. This handles most cases automatically.

**If you still get timeouts:**

Option 1 — Shorten the prompt. In mccf_llm.py, reduce max_tokens:
```python
defaults = {"max_tokens": 250, "temperature": 0.75}
```
Restart the server after changing this.

Option 2 — Use a smaller model:
```
ollama pull llama3.2:1b
```
Then in the voice interface, set the model to `llama3.2:1b`.

Option 3 — Wait. The first response after starting Ollama is
always slower because the model loads into memory. Subsequent
responses are faster.

**Symptom:** Ollama shows `[Ollama error: connection refused]`

**Fix:** Ollama is not running. Open Git Bash and run:
```
ollama serve
```

**Symptom:** Response says `[Ollama: no content returned]`

**Fix:** The model did not generate any text. This sometimes
happens when the prompt is malformed. Restart the server and try
again. If it persists, check that the agent has a valid cultivar
configuration.

---

## Field State and Persistence

The coherence field exists in memory only while the server is running.
When you stop the server, all agent states, episode history, and
coherence scores are lost.

### Saving State

Before stopping the server, export your state:

**Full JSON export:**
```
http://localhost:5000/export/json
```
Save the response as a .json file.

**Python export:**
```
http://localhost:5000/export/python
```
Save the response as a .py file. Running this file will
recreate all agents with their saved configurations.

### Loading State

Currently, state must be re-created by running the exported
Python file or by manually re-creating agents through the editor.
Automatic state persistence on startup is a planned v2.1 feature.

### Cultivars

Cultivar templates (the named agent configurations in the
constitutional arc) are seeded from the default cultivars in
mccf_api.py at startup. If you create custom cultivars through
the editor, save them via the Cultivar panel before stopping
the server or they will be lost.

---

## Agent Management

### Creating Agents

In the Field Editor, type an agent name and press Create. Agents
are case-sensitive. "The Steward" and "the steward" are different agents.

### Channel Weights (E/B/P/S)

Each agent has four channels that must sum to 1.0:

- **E (Emotional)** — how much emotional intensity drives behavior.
  High E agents respond strongly to relational cues.
- **B (Behavioral)** — consistency and predictability of action.
  High B agents are reliable and pattern-consistent.
- **P (Predictive)** — accuracy of anticipation and planning.
  High P agents think ahead and are analytically oriented.
- **S (Social)** — weight given to social alignment and group norms.
  High S agents are context-sensitive and relationally aware.

### Regulation

The regulation slider (0.0–1.0) controls how much the agent's
emotional channel affects its behavior:
- 1.0 = fully reactive, unfiltered
- 0.5 = measured, aware but not driven
- 0.0 = fully suppressed, detached

Trained agents typically operate between 0.3 and 0.8.

### CCS (Coherence Coupling Strength)

CCS is the vmPFC analog — how tightly the agent's channels are
bound together. High CCS means the agent applies its values
consistently. Low CCS means values decouple across contexts
(the agent treats others by different standards than itself).

CCS drifts automatically based on episode consistency. The Gardener
can set it directly via /gardener/regulate.

---

## The Gardener

The Gardener is a supervisory layer that can intervene in agent
behavior without disrupting the field.

**Regulate** (POST /gardener/regulate):
Sets an agent's regulation level.
```json
{"agent": "The Steward", "level": 0.7, "reason": "test"}
```

**Reweight** (POST /gardener/reweight):
Changes an agent's channel weights. Weights must sum to 1.0.
```json
{"agent": "The Steward", "weights": {"E":0.4,"B":0.2,"P":0.2,"S":0.2}, "reason": "test"}
```

Both are accessible from the Field Editor's Gardener panel.

---

## HotHouse (v2.0)

The HotHouse is the Affective Hamiltonian layer — it projects the
raw CoherenceField state through a richer emotional dynamics model.

**New in v2.0:** HotHouse is now wired into the API and rebuilds
automatically when agents are registered.

**New endpoints:**
- `/hothouse/state` — full EmotionalField state including X3D
  parameter projection and field summary
- `/hothouse/x3d` — X3D parameter dict for avatar blend weights
- `/hothouse/humanml` — HumanML XML fragment for motion capture

The X3D loader can poll `/hothouse/x3d` to drive avatar animations
based on the live emotional field state. This is the bridge between
the simulation layer and the rendering layer.

---

## Collapse Pipeline (v2.0)

The collapse pipeline (mccf_collapse.py) is now registered with
the API.

**Endpoint:** POST `/collapse/run`

The collapse pipeline runs the full S→P→G→M→U sequence:
- S: Schema constraint validation
- P: Persona application
- G: Gardener pressure
- M: Memory influence
- U: Utterance generation

This is used internally by the constitutional arc. It can also
be called directly for programmatic collapse control.

---

## Δ Feedback Loop (v2.0)

The Δ (delta) feedback loop is the key v2.0 addition. It closes
the cognitive loop so the agent's behavior is influenced by its
own recent outcome history.

**How it works:**

1. Each interaction records an `outcome_delta` (improvement or
   decline in coherence)
2. The agent's `delta_history` accumulates these over the last
   20 episodes
3. `delta_context()` summarizes the trajectory (improving,
   stable, declining, recovering)
4. This trajectory is injected into the system prompt under
   "YOUR EMOTIONAL TRAJECTORY"
5. The HTML voice interface also sends an aggregate delta back
   to the server with each request, completing the loop

**What you will see:** Agents that have had consistently positive
interactions will respond from a position of confidence. Agents
in a declining trajectory will show more caution and hedging.
This is not scripted — it emerges from the Δ history.

---

## Troubleshooting

### Server won't start

Check that no other process is using port 5000:
```
netstat -an | grep 5000
```
If something is using it, either stop that process or change
the port in mccf_api.py: `app.run(debug=True, port=5001)`

### "NetworkError when attempting to fetch resource"

The HTML file is being opened as a `file://` URL instead of
through Flask. Always use `http://localhost:5000/static/[file].html`
— never open HTML files directly from Windows Explorer.

### Coherence matrix shows all zeros

No sensor events have been fired yet. Use the Sensor panel in the
Field Editor to fire events between agents. The matrix populates
after the first interaction.

### Constitutional arc shows no response (just colored bars)

The LLM adapter is set to Stub. Configure Ollama:
1. Ensure Ollama is running (`ollama serve` in a Git Bash window)
2. In the constitutional interface, find the adapter selector
3. Set it to Ollama
4. Set model to `llama3.2:latest`

### Field state disappeared

The server was restarted. Field state is in-memory only.
Re-create agents from the editor or run the Python export
from a previous session.

### "HotHouse init warning" in server output

This is informational, not an error. It appears when agents
are registered and the HotHouse EmotionalField rebuilds.
Normal operation.

---

## Updating from GitHub

When new code is available:

```
cd /d/VideoRenders/FederatedDialog/mccf_github_release/mccf_full
git pull origin master
cp *.html static/
```

Then restart the server. Always copy HTML files to static/ after
a pull so the Flask-served versions are current.

---

## File Reference

| File | Purpose |
|------|---------|
| mccf_api.py | Main Flask server, all endpoints |
| mccf_core.py | CoherenceField, Agent, Gardener, Librarian |
| mccf_llm.py | LLM adapters (Stub, Ollama, Anthropic, OpenAI, Google) |
| mccf_voice_api.py | Voice/speak endpoint, multi-turn stabilizer |
| mccf_zone_api.py | Zone, waypoint, path endpoints |
| mccf_ambient_api.py | Ambient and lighting endpoints |
| mccf_collapse.py | Collapse pipeline (S→P→G→M→U) |
| mccf_hotHouse.py | EmotionalField, HotHouseX3DAdapter |
| mccf_honor_trust.py | HonorConstraint, TrustPropagator |
| mccf_shibboleth.py | Coherence-to-Prompt Index test |
| mccf_cultivars.py | Default cultivar definitions |
| mccf_zones.py | SceneGraph, Zone objects |
| mccf_world_model.py | Outcome estimation adapter |
| mccf_compiler.py | X3D scene compiler |
| static/ | All HTML interfaces and X3D scene files |

---

*MCCF Users Guide v2.0 — April 2026*  
*Len Bullard / Claude Sonnet 4.6*
