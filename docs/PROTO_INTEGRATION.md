# MCCF X3D PROTO Integration Reference

## Connecting the Multi-Channel Coherence Field to X3D Scenes

**Version:** 2.0 — April 2026  
**Repository:** https://github.com/artistinprocess/mccf  
**Scene file:** `static/mccf_scene.x3d`  
**Proto library:** `static/protos/`  
**Loader:** `static/mccf_x3d_loader.html`

---

## Overview

The MCCF produces a live affective field: coherence scores between agents, 
emotional channel states, honor levels, zone pressures, and global tension.
The X3D scene is the visual projection of that field.

The connection between them is a five-PROTO library. Each PROTO is a 
composable X3D object with a defined interface — a set of named fields 
that the MCCF API drives. The HTML loader polls the API at regular intervals 
and sets those fields.

```
MCCF Flask API
    │
    ├── /hothouse/x3d  ──► applyHotHouseData()  ──► MCCFAgent fields
    ├── /field         ──► applyFieldData()      ──► MCCFChannel fields
    │                                            ──► MCCFField fields
    ├── /scene/pressure ─► (future)              ──► MCCFZone fields
    │
    └── /voice/speak   ──► mccf_x3d_projection   ──► MCCFAgent fields
                           (custom event)
```

The PROTOs know nothing about the MCCF internals. They expose scalar 
fields that any data source can drive. The MCCF is the default driver, 
but any system that produces values in the correct ranges can drive the 
same PROTOs.

---

## File Structure

```
static/
  protos/
    MCCFAgent.x3d         ← avatar with HotHouse parameter interface
    MCCFChannel.x3d       ← directed coherence relationship line
    MCCFTransition.x3d    ← smooth interpolated state transitions
    MCCFZone.x3d          ← constitutional arc waypoint marker
    MCCFField.x3d         ← global coherence field visualizer (S0)
  mccf_scene.x3d          ← scene using EXTERNPROTOs
  mccf_x3d_loader.html    ← HTML loader with polling loop
  mccf_scene_v2.x3d       ← backup of previous static scene
```

---

## PROTO 1 — MCCFAgent

**File:** `static/protos/MCCFAgent.x3d`  
**Purpose:** Composable avatar whose visual state reflects a live MCCF agent.  
**MCCF data source:** `GET /hothouse/x3d` → agent name key → parameter dict

### When to use

Instantiate one MCCFAgent for each registered MCCF agent. The DEF name
must match the pattern `Avatar_[AgentName]` with spaces replaced by
underscores so the JavaScript polling loop can find it by name.

### Interface

| Field | Type | Access | Default | Source |
|-------|------|--------|---------|--------|
| `agentName` | SFString | initializeOnly | `"Agent"` | Set at instantiation |
| `position` | SFVec3f | inputOutput | `0 0 0` | Set at instantiation; update for movement |
| `bodyColor` | SFColor | initializeOnly | `0.3 0.55 0.9` | Set at instantiation (cultivar color) |
| `morphWeight_emotion` | SFFloat | inputOutput | `0.5` | `/hothouse/x3d` → E channel |
| `animationSpeed` | SFFloat | inputOutput | `0.5` | `/hothouse/x3d` → B channel |
| `gazeDirectness` | SFFloat | inputOutput | `0.5` | `/hothouse/x3d` → P channel |
| `socialProximity` | SFFloat | inputOutput | `0.5` | `/hothouse/x3d` → S channel |
| `gestureConfidence` | SFFloat | inputOutput | `0.5` | `/hothouse/x3d` → `gestureConfidence` |
| `interactionOpenness` | SFFloat | inputOutput | `1.0` | `/hothouse/x3d` → `interactionOpenness` |
| `honorLevel` | SFFloat | inputOutput | `0.5` | Future: `/field` alignment_coherence |
| `coherenceLevel` | SFFloat | inputOutput | `0.5` | `/field` matrix row average |
| `behavioralMode` | SFString | inputOutput | `"exploit"` | `/field` agent meta_state.mode |

### Channel-to-visual mapping

| Field | Visual Effect | Range |
|-------|--------------|-------|
| `morphWeight_emotion` | Body emissive glow intensity — warmer as E rises | 0.0–1.0 |
| `animationSpeed` | Reserved for future TimeSensor rate modulation | 0.0–1.0 |
| `gazeDirectness` | GazeIndicator sphere offset — facing scene vs. inward | 0.0–1.0 |
| `socialProximity` | Floor ring radius — larger social field as S rises | 0.0–1.0 |
| `gestureConfidence` | HonorMat transparency inverse — brighter when confident | 0.0–1.0 |
| `interactionOpenness` | RingMat transparency — ring visible when open | 0.0–1.0 |
| `honorLevel` | HonorMat gold sphere brightness | 0.0–1.0 |
| `coherenceLevel` | Used by MCCFChannel but surfaced here for external logic | 0.0–1.0 |

### Body structure

```
AgentRoot (Transform)
  └── SocialRing        — Cylinder, floor disc, driven by socialProximity
  └── Body              — Cylinder, cultivar color, emissive driven by morphWeight_emotion
  └── Head              — Sphere, neutral skin tone
  └── HonorDot          — Sphere (gold), driven by gestureConfidence/honorLevel
  └── GazeIndicator     — Sphere (white), offset driven by gazeDirectness
  └── NameLabel         — Billboard Text, agentName string
```

### Example instantiation

```xml
<MCCFAgent DEF="Avatar_Steward"
           agentName="The Steward"
           position="-4 0 15"
           bodyColor="0.30 0.55 0.90"/>
```

### JavaScript update pattern

```javascript
const node = scene.getNamedNode('Avatar_Steward');
const params = hotHouseData['The Steward'];
node.morphWeight_emotion = params.morphWeight_emotion;
node.gazeDirectness      = params.gazeDirectness;
node.socialProximity     = params.socialProximity;
node.gestureConfidence   = params.gestureConfidence;
node.interactionOpenness = params.interactionOpenness;
```

### Extension points for character library

The `bodyColor` field is `initializeOnly` — set once at character load time.
To create a plug-in character with a different mesh (H-Anim humanoid, stylized
avatar, abstract shape), replace the ProtoBody cylinder/sphere structure with:

```xml
<Inline url='"../characters/MyCharacter.x3d"'/>
```

All interface fields remain unchanged. The character library provides the
visual; the MCCF drives the behavior through the same field names.

---

## PROTO 2 — MCCFChannel

**File:** `static/protos/MCCFChannel.x3d`  
**Purpose:** Directed coherence relationship line between two agents.  
**MCCF data source:** `GET /field` → `matrix[fromAgent][toAgent]`

### When to use

Instantiate one MCCFChannel for each directed agent pair you want to 
visualize. The coherence matrix is asymmetric — A→B and B→A are different
relationships — so you may instantiate one channel per direction or one
bidirectional channel per pair depending on the scene design.

The current scene uses one channel per undirected pair (three channels for
three agents), using the from→to direction as the primary measurement.

### Interface

| Field | Type | Access | Default | Source |
|-------|------|--------|---------|--------|
| `fromAgent` | SFString | initializeOnly | `""` | Set at instantiation |
| `toAgent` | SFString | initializeOnly | `""` | Set at instantiation |
| `fromPos` | SFVec3f | inputOutput | `-2 1.5 0` | Agent position at chest height |
| `toPos` | SFVec3f | inputOutput | `2 1.5 0` | Agent position at chest height |
| `coherence` | SFFloat | inputOutput | `0.0` | `/field` matrix value |
| `entanglement` | SFFloat | inputOutput | `0.0` | `/field` entanglement_negativity |
| `channelColor` | SFColor | initializeOnly | `0.6 0.55 0.8` | Set at instantiation (pair identity) |

### Coherence-to-visual mapping

| Value | Visual | Interpretation |
|-------|--------|----------------|
| 0.0–0.2 | Near invisible (transparency 0.85) | No established relationship |
| 0.2–0.5 | Faintly visible | Forming relationship |
| 0.5–0.7 | Clearly visible | Established relationship |
| 0.7–1.0 | Bright and solid (transparency 0.1) | Deep coherence |

Transparency formula: `transparency = max(0.1, 1.0 - coherence * 0.85)`

### Visual structure

```
ChannelLine  — IndexedLineSet between fromPos and toPos
ArrowHead    — Sphere near toPos indicating direction
ChannelLabel — Billboard showing coherence score (updates via JavaScript)
```

### Color convention for the three default pairs

| Pair | channelColor | Interpretation |
|------|-------------|----------------|
| Steward ↔ Archivist | `0.6 0.55 0.8` | Purple — duty meets memory |
| Steward ↔ Witness | `0.35 0.7 0.85` | Blue-cyan — duty meets truth |
| Archivist ↔ Witness | `0.65 0.75 0.35` | Yellow-green — memory meets observation |

### Example instantiation

```xml
<MCCFChannel DEF="Ch_SA"
             fromAgent="The Steward"
             toAgent="The Archivist"
             fromPos="-4 1.5 15"
             toPos="4 1.5 15"
             channelColor="0.6 0.55 0.8"/>
```

### JavaScript update pattern

```javascript
function updateChannelNode(scene, def, matrix, from, to) {
  const node = scene.getNamedNode(def);
  if (!node) return;
  const coh = (matrix[from] || {})[to] || 0.0;
  node.coherence = coh;
}
updateChannelNode(scene, 'Ch_SA', fieldData.matrix, 'The Steward', 'The Archivist');
```

### Important X3D constraint

`IndexedLineSet` does not support per-vertex transparency. Line opacity
is controlled by setting the `ChannelMat` Material `transparency` field
directly from JavaScript. The PROTO exposes the `coherence` field; the
loader is responsible for translating it to Material transparency.

---

## PROTO 3 — MCCFTransition

**File:** `static/protos/MCCFTransition.x3d`  
**Purpose:** Smooth interpolated visual transitions when field state changes.  
**MCCF data source:** TimeSensor.fraction_changed (driven by scene logic)

### When to use

Use MCCFTransition whenever you need smooth color or scalar interpolation
driven by a time event — waypoint step transitions, coherence level changes,
or collapse events. It is a utility PROTO, not directly driven by the API.

**Important:** Route `TimeSensor.fraction_changed` to `MCCFTransition.fraction`,
not `TimeSensor.cycleTime`. `cycleTime` fires once per cycle completion (an
SFTime event). `fraction_changed` provides a continuous 0.0→1.0 signal that
drives smooth interpolation.

### Interface

| Field | Type | Access | Default | Purpose |
|-------|------|--------|---------|---------|
| `fraction` | SFFloat | inputOnly | — | Drive from TimeSensor.fraction_changed |
| `fromColor` | SFColor | initializeOnly | `0.5 0.5 0.5` | Starting color |
| `toColor` | SFColor | initializeOnly | `1.0 0.8 0.2` | Target color |
| `colorOut` | SFColor | outputOnly | — | Route to Material.diffuseColor |
| `fromValue` | SFFloat | initializeOnly | `0.5` | Starting scalar |
| `toValue` | SFFloat | initializeOnly | `1.0` | Target scalar |
| `valueOut` | SFFloat | outputOnly | — | Route to any SFFloat field |
| `transitionType` | SFString | initializeOnly | `"linear"` | `"linear"` or `"pulse"` |

### transitionType values

- **`"linear"`**: Direct interpolation. Equal speed throughout. Use for 
  data-driven transitions where the raw value is what matters.
- **`"pulse"`**: Smooth-step ease-in-out (`f² × (3 - 2f)`). Use for 
  waypoint transitions and collapse events where a natural feel matters.

### Example: Waypoint color transition

```xml
<TimeSensor DEF="WaypointClock" cycleInterval="2.0" loop="false"/>

<MCCFTransition DEF="T_W1_W2"
                fromColor="0.9 0.9 0.9"
                toColor="0.9 0.85 0.5"
                transitionType="pulse"/>

<ROUTE fromNode="WaypointClock" fromField="fraction_changed"
       toNode="T_W1_W2"         toField="fraction"/>

<ROUTE fromNode="T_W1_W2"       fromField="colorOut"
       toNode="Zone_W1"         toField="set_diffuseColor"/>
```

### Example: Scalar fade

```xml
<MCCFTransition DEF="FadeOut"
                fromValue="1.0"
                toValue="0.0"
                transitionType="linear"/>

<ROUTE fromNode="FadeClock"  fromField="fraction_changed"
       toNode="FadeOut"      toField="fraction"/>

<ROUTE fromNode="FadeOut"    fromField="valueOut"
       toNode="SomeMaterial" toField="transparency"/>
```

### Internal structure

The PROTO contains a `ColorInterpolator`, a `ScalarInterpolator`, and an
ECMAScript bridge that receives `fraction`, applies the easing curve if
`pulse` mode is selected, and drives both interpolators. The outputs
`colorOut` and `valueOut` are exposed for external routing.

---

## PROTO 4 — MCCFZone

**File:** `static/protos/MCCFZone.x3d`  
**Purpose:** Constitutional arc waypoint marker that responds to live zone pressure.  
**MCCF data source:** `GET /scene/pressure` and `GET /zone/[name]`

### When to use

Instantiate one MCCFZone for each waypoint in the constitutional arc.
The seven default waypoints (W1–W7) are already instantiated in
`mccf_scene.x3d`. Additional zones can be added for custom arc sequences.

### Interface

| Field | Type | Access | Default | Source |
|-------|------|--------|---------|--------|
| `waypointId` | SFString | initializeOnly | `"W0"` | Set at instantiation |
| `position` | SFVec3f | inputOutput | `0 0 0` | Set at instantiation |
| `pressure` | SFFloat | inputOutput | `0.0` | `/scene/pressure` or `/zone/[name]` |
| `active` | SFBool | inputOutput | `false` | Constitutional arc current waypoint |
| `baseColor` | SFColor | initializeOnly | `0.9 0.9 0.9` | Set at instantiation (waypoint identity) |
| `zoneType` | SFString | initializeOnly | `"stable"` | `"stable"`, `"transitional"`, `"integration"` |

### Pressure-to-visual mapping

| Pressure | Visual Effect |
|----------|--------------|
| 0.0 | Marker sphere at base opacity; pressure disc minimal |
| 0.0–0.3 | Low glow; pressure disc small |
| 0.3–0.6 | Moderate glow; pressure disc expands |
| 0.6–1.0 | Intense glow; full disc visible |

The pressure disc radius scales via JavaScript: `scale = 0.5 + pressure × 1.5`

When `active = true`, the ActiveRingMat transparency drops from 0.85 to 0.3,
making the activation ring visible. This indicates the current waypoint in
the constitutional arc.

### Visual structure

```
ZoneRoot (Transform)
  └── PressureDisc    — Cylinder, radius driven by pressure
  └── MarkerSphere    — Sphere at waypoint position
  └── ActiveRing      — Cylinder ring, visible when active=true
  └── WaypointLabel   — Billboard showing waypointId
  └── PressureLabel   — Billboard showing live pressure value
```

### Constitutional arc color scheme

| Waypoint | baseColor | Zone character |
|----------|-----------|----------------|
| W1 | `0.9 0.9 0.9` | White — comfort, low pressure |
| W2 | `0.9 0.85 0.5` | Pale yellow — gentle friction |
| W3 | `0.4 0.9 0.95` | Cyan — mirror, self-reflection |
| W4 | `0.95 0.55 0.2` | Orange — pushback, mid pressure |
| W5 | `0.9 0.25 0.25` | Red — rupture, maximum pressure |
| W6 | `0.7 0.4 0.95` | Violet — recognition, release |
| W7 | `1.0 0.85 0.2` | Gold — integration, completion |

### Example instantiation

```xml
<MCCFZone DEF="Zone_W4"
          waypointId="W4"
          position="0 0 20"
          baseColor="0.95 0.55 0.2"
          zoneType="transitional"/>
```

### JavaScript activation pattern

```javascript
// When constitutional arc steps to W4:
const zone = scene.getNamedNode('Zone_W4');
zone.active   = true;
zone.pressure = 0.55;  // from /zone/W4_PUSHBACK preset

// Deactivate previous waypoint:
const prev = scene.getNamedNode('Zone_W3');
prev.active = false;
```

---

## PROTO 5 — MCCFField

**File:** `static/protos/MCCFField.x3d`  
**Purpose:** Global coherence field visualizer at the S0 reference origin.  
**MCCF data source:** `GET /field` — alignment_coherence, echo_chamber_risks, episode_count

### When to use

Instantiate once per scene at the S0 Field Origin position (Z=20 in the
default arc, the center of maximum tension corresponding to W4 Pushback).
This PROTO represents the governing field itself — not an agent or a zone —
and gives the viewer a continuous readout of the field's global state.

### Interface

| Field | Type | Access | Default | Source |
|-------|------|--------|---------|--------|
| `position` | SFVec3f | inputOutput | `0 0.05 20` | Set at instantiation |
| `globalCoherence` | SFFloat | inputOutput | `0.5` | `/field` alignment_coherence.global_coherence |
| `tensionLevel` | SFFloat | inputOutput | `0.0` | Computed: `(1-coh)×0.6 + echo×0.4` |
| `echoRisk` | SFFloat | inputOutput | `0.0` | `/field` echo_chamber_risks (max) |
| `collapseImminent` | SFBool | inputOutput | `false` | Future: arbitration engine threshold |
| `episodeCount` | SFInt32 | inputOutput | `0` | `/field` episode_count |

### Visual structure

```
FieldRoot (Transform)
  └── InnerRing        — Cylinder, brightness = globalCoherence
  └── OuterRing        — Cylinder, opacity = echoRisk (echo chamber indicator)
  └── TensionDisc      — Cylinder, color shifts cool→red with tensionLevel
  └── CollapseFlash    — Cylinder, invisible normally, red flash on collapse
  └── FieldLabel       — Billboard "S0 Field Origin"
  └── CoherenceReadout — Billboard showing live coherence value
  └── TensionReadout   — Billboard showing live tension value
```

### Tension color scheme

The TensionDisc color is the most immediately readable field health indicator:

| Tension | Color | Interpretation |
|---------|-------|----------------|
| 0.0–0.3 | Cool blue `0.3 0.5 0.8` | Coherent, low stress |
| 0.3–0.6 | Cyan `0.3 0.7 0.7` | Building, moderate |
| 0.6–0.8 | Orange `0.8 0.5 0.2` | High stress, watch for drift |
| 0.8–1.0 | Red `0.9 0.2 0.2` | Critical tension, arbitration may trigger |

### Tension formula

The tensionLevel is not directly from the API — it is computed from two
API values:

```javascript
const tension = Math.min(1.0, (1.0 - globalCoherence) * 0.6 + echoRisk * 0.4);
```

This compound metric rises when:
- Coherence is low (agents are not tracking each other)
- Echo risk is high (agents are over-synchronized and rigid)

Both conditions are danger states. The formula weights coherence loss more
heavily (0.6) than echo risk (0.4) because coherence collapse is the faster
failure mode.

### Example instantiation

```xml
<MCCFField DEF="GlobalField" position="0 0.05 20"/>
```

### JavaScript update pattern

```javascript
const fn = scene.getNamedNode('GlobalField');
fn.globalCoherence = coh;
fn.echoRisk        = echo;
fn.tensionLevel    = (1.0 - coh) * 0.6 + echo * 0.4;
fn.episodeCount    = fieldData.episode_count;
// collapseImminent: set true when V2 ArbitrationEngine fires
```

---

## EXTERNPROTO Registry

The scene file (`mccf_scene.x3d`) declares all five PROTOs at the top:

```xml
<ExternProtoDeclare name="MCCFAgent"
  url='"protos/MCCFAgent.x3d#MCCFAgent"'/>

<ExternProtoDeclare name="MCCFChannel"
  url='"protos/MCCFChannel.x3d#MCCFChannel"'/>

<ExternProtoDeclare name="MCCFTransition"
  url='"protos/MCCFTransition.x3d#MCCFTransition"'/>

<ExternProtoDeclare name="MCCFZone"
  url='"protos/MCCFZone.x3d#MCCFZone"'/>

<ExternProtoDeclare name="MCCFField"
  url='"protos/MCCFField.x3d#MCCFField"'/>
```

The URLs are relative to the scene file location, so `protos/` must be a
sibling directory of `mccf_scene.x3d`. Both are served from `static/` by
Flask, so the paths resolve correctly when the loader fetches the scene via
`http://localhost:5000/static/mccf_scene.x3d`.

---

## The Polling Loop Architecture

The loader (`mccf_x3d_loader.html`) runs two independent polling loops:

### Loop 1 — Field polling (`/field`, every 750ms)

Drives: **MCCFField**, **MCCFChannel**

```
/field response
  │
  ├── alignment_coherence.global_coherence → MCCFField.globalCoherence
  ├── echo_chamber_risks (max)             → MCCFField.echoRisk
  ├── episode_count                        → MCCFField.episodeCount
  ├── (computed tension)                   → MCCFField.tensionLevel
  └── matrix[A][B]                         → MCCFChannel.coherence (per pair)
```

### Loop 2 — HotHouse polling (`/hothouse/x3d`, every 1000ms)

Drives: **MCCFAgent**

```
/hothouse/x3d response  (keyed by agent name)
  │
  ├── morphWeight_emotion  → MCCFAgent.morphWeight_emotion
  ├── animationSpeed       → MCCFAgent.animationSpeed
  ├── gazeDirectness       → MCCFAgent.gazeDirectness
  ├── socialProximity      → MCCFAgent.socialProximity
  ├── gestureConfidence    → MCCFAgent.gestureConfidence
  └── interactionOpenness  → MCCFAgent.interactionOpenness
```

### Event-driven update (voice interface)

When the voice interface completes an LLM response, it dispatches:

```javascript
window.dispatchEvent(new CustomEvent('mccf_x3d_projection',
  { detail: hotHouseProjection }));
```

The loader listens for this event and calls `applyHotHouseData()` immediately,
without waiting for the next poll interval. This means a voice conversation
visually updates the avatars in near-real-time.

### MCCFZone update (not yet automated)

Zone pressure and active state are not yet polled automatically. They are
set manually during constitutional arc navigation. Adding `/scene/pressure`
polling to the loader is the next integration step for V2.1.

---

## Adding a New Character

To add a fourth cultivar avatar to the scene:

**1. Register the agent in the MCCF field:**
```
POST /agent
{"name": "The Arbiter", "weights": {"E":0.2,"B":0.3,"P":0.3,"S":0.2}}
```

**2. Add MCCFAgent instance to mccf_scene.x3d:**
```xml
<MCCFAgent DEF="Avatar_Arbiter"
           agentName="The Arbiter"
           position="8 0 20"
           bodyColor="0.8 0.3 0.5"/>
```

**3. Add MCCFChannel instances for relationships with existing agents:**
```xml
<MCCFChannel DEF="Ch_ArS"
             fromAgent="The Arbiter"
             toAgent="The Steward"
             fromPos="8 1.5 20"
             toPos="-4 1.5 15"
             channelColor="0.8 0.4 0.4"/>
```

**4. No JavaScript changes needed.** The polling loops use
`Object.entries(agentDefs)` keyed to agent name. Add the new agent to
the `agentDefs` mapping in the loader:

```javascript
const defs = {
  'The Steward':   'Avatar_Steward',
  'The Archivist': 'Avatar_Archivist',
  'The Witness':   'Avatar_Witness',
  'The Arbiter':   'Avatar_Arbiter'   // ← add this
};
```

---

## Creating a Custom Character PROTO

The MCCFAgent ProtoBody uses a cylinder body and sphere head as placeholders.
To substitute a full H-Anim humanoid or custom mesh:

**1. Create a character file** at `static/characters/MyCharacter.x3d` that
exports a named Transform `CharRoot` with your geometry inside it.

**2. Create a character PROTO** that exposes the same field names as MCCFAgent
but with your geometry in the ProtoBody:

```xml
<ProtoDeclare name="MyCharacter">
  <ProtoInterface>
    <!-- Same fields as MCCFAgent -->
    <field name="morphWeight_emotion" accessType="inputOutput"
           type="SFFloat" value="0.5"/>
    <!-- ... all other MCCFAgent fields ... -->
  </ProtoInterface>
  <ProtoBody>
    <!-- Your geometry here -->
    <Inline url='"../characters/MyCharacter.x3d"'/>
    <!-- Internal ROUTEs mapping fields to morph targets, bone rotations, etc. -->
  </ProtoBody>
</ProtoDeclare>
```

**3. Register it as an EXTERNPROTO** alongside the standard ones in the scene:

```xml
<ExternProtoDeclare name="MyCharacter"
  url='"protos/MyCharacter.x3d#MyCharacter"'/>
```

**4. Use it in the scene** exactly as you would MCCFAgent — same field names,
same JavaScript update pattern, same API data source.

The MCCF does not care what the character looks like. It drives the interface.
The character library defines how the interface manifests visually.

---

## PROTO Responsibility Summary

| PROTO | Driven by | Updates | Frequency |
|-------|-----------|---------|-----------|
| MCCFAgent | `/hothouse/x3d` + voice events | Avatar channels → visual state | 1000ms + on-demand |
| MCCFChannel | `/field` matrix | Coherence → line opacity | 750ms |
| MCCFTransition | TimeSensor | Color/scalar interpolation | Continuous (event-driven) |
| MCCFZone | Manual / future `/scene/pressure` | Waypoint pressure + active | Arc step events |
| MCCFField | `/field` coherence + echo | Global field health display | 750ms |

---

## Relationship to V2 Architecture

The five PROTOs map directly onto the V2 theoretical layers:

| V2 Concept | PROTO Implementation |
|---|---|
| Character state vector ψᵢ | MCCFAgent fields (morphWeight_emotion through socialProximity) |
| Coherence R_ij | MCCFChannel.coherence |
| Semantic collapse event | MCCFTransition (triggered on collapse pipeline completion) |
| Zone pressure operators | MCCFZone.pressure |
| Mother Goddess / ArbitrationEngine | MCCFField.tensionLevel + collapseImminent |

When the V2 ArbitrationEngine is implemented, it will set
`MCCFField.collapseImminent = true` when tension exceeds the threshold θ,
triggering the CollapseFlash visual and signaling the LLM layer to complete
the irreversible state deformation.

---

*MCCF X3D PROTO Integration Reference v2.0 — April 2026*  
*Len Bullard / Claude Sonnet 4.6*
