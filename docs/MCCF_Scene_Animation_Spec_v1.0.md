# MCCF Scene Animation Specification
## Version 1.0 — Day 60

---

## Purpose

This document specifies the architecture for continuous, field-driven scene animation in MCCF. It covers the three-layer model that governs how constitutional agent field states (EBPS values) drive camera, lighting, fog, particles, and avatar animation in real time — and how authored EventCues interact with that continuous layer.

Read this before implementing any Phase 2 camera moves, light animation, fog dynamics, particle systems, or facial/postural animation.

Also read:
- `MCCF_Events_Editor_Architecture.md` — baked vs runtime, vessel principle, SAI rules
- `MCCF_Camera_System_Spec_v1.2.md` — camera system, VP_Free, -Z convention

---

## 1. The Conceptual Model — Rock Concert, Not Film

A film is fully authored. Every cut, every lighting change, every performance beat was decided by a director before the audience arrived. The audience is passive.

A rock concert has structure — setlist, key changes, lighting cues, stage positions — but what happens between the musicians and the audience is emergent. The guitarist feels the room energy and bends the solo. The lighting operator reads the crowd and holds the red longer. The crowd's emotional state feeds back into the band's performance. It is a closed loop with humans in it, and no two nights are the same.

MCCF builds that loop without humans in the performance layer:

- **The constitutional agents are the band** — they have personalities, relationships, field states
- **The EBPS field is the room energy** — it emerges from agent interactions, zone pressures, arc events
- **The couplers are the musicians listening to each other** — field states propagate and influence
- **The semantic zones are the acoustics** — they shape what's possible without dictating outcomes
- **The X3D scene with continuous field-driven camera, lights, fog, and animation is the production rig** — reading the room in real time and expressing what it finds

The goal is a scene that is never static between authored beats. It breathes with the field. When something is happening emotionally, the camera, lights, and avatars reflect it — not because an author scripted that moment, but because the field state is being continuously expressed through the scene graph.

---

## 2. The Three-Layer Model

All scene animation in MCCF operates through three layers, stacked by priority. Higher layers override lower layers for the duration of their activity, then release back to the layer below.

```
┌─────────────────────────────────────────────────────────────┐
│  LAYER 3 — Narrative (highest priority)                     │
│  Arc waypoint EventCues: authored camera cuts, light        │
│  changes, behavior clips. Full author control.              │
│  Fires on WP arrival, manual trigger, or time offset.       │
│  Duration: cue.dur. Releases to Layer 2 on completion.      │
├─────────────────────────────────────────────────────────────┤
│  LAYER 2 — Dramatic (medium priority)                       │
│  Field threshold EventCues: fire when EBPS crosses a        │
│  threshold. "field E>0.6", "field B<0.3", etc.              │
│  Authored in Events Editor. Deterministic triggers,         │
│  but content responds to field state at fire time.          │
│  Duration: cue.dur. Releases to Layer 1 on completion.      │
├─────────────────────────────────────────────────────────────┤
│  LAYER 1 — Continuous (always on, lowest priority)          │
│  EBPS values drive scene parameters as a live shader.       │
│  Camera height, orbit speed, light temperature, fog         │
│  density, particle rate, morph weights — all continuous     │
│  functions of field state. Runs every field tick.           │
│  No authoring required. The emotional ground state.         │
└─────────────────────────────────────────────────────────────┘
```

### Priority and Release

When a Layer 3 cue fires, it takes ownership of its parameters (camera, specific light, etc.) for `cue.dur` seconds. Layer 1 continues running for parameters the Layer 3 cue doesn't own. On release, Layer 1 resumes full ownership smoothly — no snap back.

Layer 2 threshold cues work the same way: they own their parameters for their duration, then release. A Layer 3 narrative cue can interrupt a Layer 2 threshold cue mid-execution.

The Loader tracks ownership per parameter channel. A parameter channel is: `camera`, `light:{node}`, `fog`, `bg`, `behavior:{agent}`, `morph:{agent}:{target}`.

---

## 3. Layer 1 — Continuous Field Shader

### 3.1 The ROUTE/SAI Propagation Principle

X3D's routing system is the signal matrix. Compatible typed outputs connect to compatible typed inputs with no central dispatcher. An `SFFloat` output from a Script node reading E can route directly to:

- `PointLight.intensity`
- `Fog.visibilityRange`
- `TimeSensor.cycleInterval`
- `ParticleSystem.maxParticles`
- `HAnimDisplacer.weight`
- `CAM_Free_Transform.translation` (via interpolator)

The Loader doesn't need to know about fog density or particle rate. It writes E, B, P, S to four Script output fields and the X3D scene graph propagates them to every connected parameter automatically. The Loader seeds the field; the scene expresses it.

This is more like an **analog synthesizer with patch cables** than a digital system with a central mixer. The emergent behavior comes from the patch topology, not from explicit programming of outcomes.

### 3.2 EBPS → Scene Parameter Mappings

These are default mappings. Authors can override individual mappings in the scene XML.

#### Camera (Layer 1 base state)
| Field | Parameter | Mapping | Notes |
|---|---|---|---|
| E (emotional) | Camera height | E=0→1.7m, E=1→4.5m | High E = more elevated, wider perspective |
| B (behavioral) | Orbit speed | B=1→slow/still, B=0→faster drift | Low B = instability, camera searches |
| P (predictive) | Distance | P=1→close, P=0→pull back | Low P = uncertainty, wider frame |
| S (social) | H.Angle drift | S drives slow yaw oscillation | Social field shapes viewing angle |

Layer 1 camera uses VP_Free / CAM_Free_Transform continuously. Layer 3 narrative cuts interrupt and release back.

#### Lighting
| Field | Parameter | Mapping | Notes |
|---|---|---|---|
| E (emotional) | Color temperature | E=0→cool blue (6500K), E=1→warm amber (2700K) | Emotional warmth = warm light |
| B (behavioral) | Flicker amplitude | B=1→stable, B=0→flicker | Behavioral coherence = steady light |
| P (predictive) | Key angle | P=1→frontal, P=0→side/dramatic | Uncertainty = more dramatic lighting |
| S (social) | Fill density | S=1→soft fill, S=0→hard shadows | Social cohesion = filled shadows |
| Valence | Hue rotation | positive→golden, negative→cold blue | Overall scene warmth |

#### Fog
| Field | Parameter | Mapping | Notes |
|---|---|---|---|
| E | Visibility range | E=0→close fog (mystery), E=1→clear | Emotional clarity = visual clarity |
| B | Fog color | B=1→neutral grey, B=0→tinted | Behavioral coherence = neutral atmosphere |
| Tension | Fog density | tension high→denser | Tension builds opacity |

#### Particles
| Field | Parameter | Mapping | Notes |
|---|---|---|---|
| E | Emission rate | E drives particle density | |
| B | Velocity spread | B=1→coherent, B=0→dispersed | Fragmentation = particle dispersion |
| S | Attraction force | S=1→particles cluster, S=0→drift apart | Social field = particle cohesion |
| Tension | Color | tension→red shift | |

#### Avatar Facial / Postural Animation (HAnim)
| Field | Parameter | Mapping | Notes |
|---|---|---|---|
| E | Brow tension, eye openness | E→facial expressivity | High E = more expressive face |
| B | Postural stability | B=1→upright, B=0→shifts, fidgets | Low B = behavioral restlessness |
| P | Head orientation | P=1→engaged/forward, P=0→averted | Uncertainty = averted gaze |
| S | Body orientation toward others | S drives inter-agent facing | Social field = physical engagement |

Facial and postural animation must be **continuous functions**, not threshold events. A face that snaps between states looks mechanical. A face where brow tension, eye openness, and mouth set are smooth functions of EBPS values looks alive. This is what actors do — the field is always on their face, not just when a threshold crosses.

### 3.3 Implementation Pattern — Script Node Bridge

The Layer 1 shader runs through a Script node in the X3D scene that the Loader writes EBPS values to:

```xml
<!-- Field shader bridge — Composer emits this into every scene -->
<Script DEF="FieldShader" directOutput="true">
  <field name="E" type="SFFloat" accessType="inputOutput" value="0.5"/>
  <field name="B" type="SFFloat" accessType="inputOutput" value="0.5"/>
  <field name="P" type="SFFloat" accessType="inputOutput" value="0.5"/>
  <field name="S" type="SFFloat" accessType="inputOutput" value="0.5"/>
  <!-- Computed outputs -->
  <field name="lightTemp"      type="SFFloat" accessType="outputOnly"/>
  <field name="fogRange"       type="SFFloat" accessType="outputOnly"/>
  <field name="camHeight"      type="SFFloat" accessType="outputOnly"/>
  <field name="particleRate"   type="SFFloat" accessType="outputOnly"/>
  <![CDATA[
  ecmascript:
  function E(val) { recompute(); }
  function B(val) { recompute(); }
  function P(val) { recompute(); }
  function S(val) { recompute(); }
  function recompute() {
    lightTemp    = 2700 + (1 - E) * 3800;   // warm→cool
    fogRange     = 20 + E * 280;             // clear at high E
    camHeight    = 1.7 + E * 2.8;            // elevated at high E
    particleRate = Math.round(B * 100);      // coherent at high B
  }
  ]]>
</Script>

<!-- ROUTEs wire outputs to scene parameters -->
<ROUTE fromNode="FieldShader" fromField="fogRange"
       toNode="SceneFog"      toField="visibilityRange"/>
<ROUTE fromNode="FieldShader" fromField="lightTemp"
       toNode="SceneLight"    toField="intensity"/>
```

The Loader writes to `FieldShader.E`, `FieldShader.B`, etc. on every field tick. The Script recomputes and the ROUTEs propagate automatically.

**SAI write pattern (Loader):**
```javascript
function _fireFieldShaderTick(ebps) {
  try {
    var scene = canvas.browser.currentScene;
    var shader = scene.getNamedNode('FieldShader');
    if (!shader) return;
    shader.getField('E').setValue(ebps.E || 0.5);
    shader.getField('B').setValue(ebps.B || 0.5);
    shader.getField('P').setValue(ebps.P || 0.5);
    shader.getField('S').setValue(ebps.S || 0.5);
  } catch(e) {
    console.warn('[FieldShader] tick failed:', e.message);
  }
}
```

This is called from `_fireCouplerTick()` — the existing field tick mechanism — so Layer 1 is always in sync with field state.

---

## 4. Layer 2 — Field Threshold EventCues

### 4.1 Trigger Syntax

Field threshold triggers extend the existing EventCues trigger system:

```xml
<Cue track="camera" trigger="field E>0.6" shot="closeup" subject="Cindy" .../>
<Cue track="light"  trigger="field B<0.3" node="SceneLight" intensity="0.3" .../>
<Cue track="camera" trigger="field tension>0.7" shot="dutch" subject="Cindy" .../>
```

Supported operators: `>`, `<`, `>=`, `<=`. Field names: `E`, `B`, `P`, `S`, `tension`, `valence`, `coherence`.

### 4.2 Threshold Monitoring

The Loader monitors field values on every coupler tick and fires matching threshold cues:

```javascript
// In _fireCouplerTick(), after field update:
_checkFieldThresholdCues(currentEBPS);
```

Threshold cues have a **cooldown** (default 30s) to prevent rapid re-firing when the field oscillates near a threshold. Cooldown is per-cue, configurable via `cooldown=` attribute.

### 4.3 Events Editor UI

Field threshold triggers appear in the trigger dropdown alongside WP arrival triggers:
- `field E>0.6`
- `field B<0.3`
- `field tension>0.7`
- etc.

The inspector shows a threshold slider when a field trigger is selected.

---

## 5. Layer 3 — Narrative EventCues

Already implemented (Days 55–60). Camera cuts, light changes, behavior clips, fog, background — all fire on WP arrival or manual trigger. Full author control.

See `MCCF_Camera_System_Spec_v1.2.md` for camera cue details.

---

## 6. Phase 2 — Scripted Camera Moves

Move shots (`orbit`, `dolly_in`, `dolly_out`, `pan`, `tilt`, `crane_up`, `track`) are Layer 3 narrative cues that drive `CAM_Free_Transform` via TimeSensor interpolators.

### 6.1 Additional Vessel Nodes (Composer emits into every scene)

```xml
<!-- Move shot interpolator vessels -->
<TimeSensor DEF="CAM_Timer" cycleInterval="4" loop="false" enabled="false"/>
<PositionInterpolator    DEF="CAM_PosInterp"  key="0 1" keyValue="0 0 0  0 0 0"/>
<OrientationInterpolator DEF="CAM_OriInterp"  key="0 1" keyValue="0 1 0 0  0 1 0 0"/>
<ROUTE fromNode="CAM_Timer"    fromField="fraction_changed" toNode="CAM_PosInterp"  toField="set_fraction"/>
<ROUTE fromNode="CAM_Timer"    fromField="fraction_changed" toNode="CAM_OriInterp"  toField="set_fraction"/>
<ROUTE fromNode="CAM_PosInterp" fromField="value_changed"  toNode="CAM_Free_Transform" toField="translation"/>
<ROUTE fromNode="CAM_OriInterp" fromField="value_changed"  toNode="CAM_Free_Transform" toField="rotation"/>
```

### 6.2 Loader Implementation Pattern

```javascript
function _executeMoveShot(cue) {
  // Compute start and end positions from cue params
  var subjectPos = _resolveSubjectPos(cue.subject) || [0,0,0];
  var startPos   = _computeCamPosition(subjectPos, cue.distance,    cue.height,    cue.hAngle);
  var endPos     = _computeCamPosition(subjectPos, cue.distanceEnd, cue.heightEnd, cue.hAngleEnd);
  var startOri   = _lookAtOrientation(startPos, subjectPos, cue.vAngle);
  var endOri     = _lookAtOrientation(endPos,   subjectPos, cue.vAngleEnd);

  var scene     = canvas.browser.currentScene;
  var timer     = scene.getNamedNode('CAM_Timer');
  var posInterp = scene.getNamedNode('CAM_PosInterp');
  var oriInterp = scene.getNamedNode('CAM_OriInterp');
  var vpFree    = scene.getNamedNode('VP_Free');

  // Write keyValues
  posInterp.getField('keyValue').setValue(new X3D.MFVec3f(
    new X3D.SFVec3f(startPos[0], startPos[1], startPos[2]),
    new X3D.SFVec3f(endPos[0],   endPos[1],   endPos[2])
  ));
  oriInterp.getField('keyValue').setValue(new X3D.MFRotation(
    new X3D.SFRotation(startOri[0], startOri[1], startOri[2], startOri[3]),
    new X3D.SFRotation(endOri[0],   endOri[1],   endOri[2],   endOri[3])
  ));

  // Set duration and start
  timer.getField('cycleInterval').setValue(cue.flyDuration || 4);
  timer.getField('enabled').setValue(true);
  timer.getField('startTime').setValue(Date.now() / 1000);

  // Bind VP_Free if not already bound
  requestAnimationFrame(function() { vpFree.set_bind = true; });
}
```

### 6.3 Move Shot Types

| Shot | Start | End | Notes |
|---|---|---|---|
| `dolly_in` | `distance` | `distanceEnd` | Push toward subject |
| `dolly_out` | `distance` | `distanceEnd` | Pull back |
| `pan` | `hAngle` | `hAngleEnd` | Rotate in place |
| `tilt` | `vAngle` | `vAngleEnd` | Tilt in place |
| `orbit` | `hAngle` | `hAngleEnd` | Arc around subject at constant distance |
| `crane_up` | `height` | `heightEnd` | Rise and pull back |
| `track` | lateral offset start | lateral offset end | Parallel move |

---

## 7. Lights Specification (outline — full spec in `MCCF_Lights_Spec.md`)

### Layer 3 — Light EventCues (existing)
```xml
<Cue track="light" trigger="w2 arrive" node="SceneLight" intensity="0.9"/>
```
Already implemented. Loader calls `_fireLightEventCue(cue)`.

### Layer 1 — Continuous light animation
- Color temperature from E via FieldShader ROUTE
- Flicker from B via Script-driven animation
- Key angle from P via light position interpolation
- Fill density from S via secondary light intensity

### Color Interpolators
```xml
<ColorInterpolator DEF="LightColorInterp" key="0 0.5 1"
  keyValue="0.4 0.5 1.0  1.0 0.98 0.9  1.0 0.7 0.3"/>
<ROUTE fromNode="FieldShader"     fromField="lightTemp_normalized"
       toNode="LightColorInterp"  toField="set_fraction"/>
<ROUTE fromNode="LightColorInterp" fromField="value_changed"
       toNode="SceneLight"         toField="color"/>
```

---

## 8. Effects Specification (outline — full spec in `MCCF_Effects_Spec.md`)

### Fog
- Layer 3: `<Cue track="fog" trigger="..." visibilityRange="50"/>`
- Layer 1: FieldShader → `SceneFog.visibilityRange` via ROUTE

### Background
- Layer 3: `<Cue track="bg" trigger="..." skyColor="0.1 0.1 0.2"/>`
- Layer 1: E/B drive sky color shift (warm/cool, bright/dark)

### Particles
- Layer 1 only initially — emission rate, velocity, color all field-driven
- Layer 3 particle cues in future (explicit burst events)

---

## 9. Avatar Animation Specification (outline)

### Facial animation — always Layer 1
HAnim morph targets (HAnimDisplacer nodes) driven continuously by EBPS:
- `brow_tension` ← E
- `eye_openness` ← E, P
- `mouth_set`    ← E, S
- `jaw_tension`  ← tension composite

**Must be continuous functions.** Threshold-triggered facial snaps look mechanical. The field is always present on the face.

### Postural animation — Layer 1 base, Layer 3 override
- Body lean, weight shift ← B (low B = restless, shifting)
- Facing direction ← S (social field drives inter-agent orientation)
- Head orientation ← P (low P = averted gaze)

### Behavior clips — Layer 3 only (existing)
```xml
<Cue track="behavior" trigger="w2 arrive" agent="Cindy" clip="Gesture_01"/>
```
Already implemented. Discrete authored events — sit, gesture, turn, etc.

---

## 10. Implementation Sequence

In order — each layer testable independently:

1. **Phase 2 scripted cameras** — `_executeMoveShot()`, interpolator vessels, `orbit` first
2. **FieldShader Script node** — Composer emits it, Loader writes EBPS on every tick, verify ROUTEs propagate
3. **Layer 1 lights** — wire FieldShader → light color/intensity via ColorInterpolator
4. **Layer 1 fog** — wire FieldShader → SceneFog.visibilityRange
5. **Layer 2 threshold triggers** — `field E>0.6` in Events Editor, threshold monitor in Loader
6. **Layer 1 camera** — continuous camera position from field state between narrative cuts
7. **HAnim facial animation** — morph targets driven by FieldShader outputs
8. **Postural animation** — body orientation, lean, gaze direction
9. **Particles** — emission rate, velocity, color from field

At step 9, the scene is breathing with the field. The rock concert is playing.

---

## 11. Open Questions

| Question | Notes |
|---|---|
| Layer 1 camera smoothing | Raw field values will produce jitter — needs low-pass filter or lerp |
| Transition between layers | When Layer 3 releases, Layer 1 should resume smoothly — needs blend |
| Per-agent field vs scene field | Multiple agents have different EBPS — which agent drives Layer 1? Scene average? Dominant agent? |
| FieldShader in X3D vs Loader | Pure X3D Script + ROUTEs is elegant but limits debugging. Loader-driven gives more control. Hybrid recommended. |
| Facial morph availability | Depends on HAnim avatar completeness — confirm morph targets available before speccing |

---

*Day 60. The Swiss clock becomes a rock concert.*
*Layer 1 — continuous. Layer 2 — dramatic. Layer 3 — narrative.*
*The field is always on. The scene always breathes.*
*Compatible type out → compatible type in. That's a lot of options.*
