# MCCF Session Seed — V4 "The New York Rocket" — Day 13
Repo: https://github.com/artistinprocess/mccf
Last commit: Day 12 — H-Anim end-to-end verified: figure renders in scene, arc playback moves figure, dialog fires

---

## Workflow Rule — No Human-in-the-Loop Code Editing
Claude edits files directly and delivers them as outputs. The developer deploys the
output files. No manual code editing by the developer — eliminates transcription errors.

---

## State at End of Day 11

### What Was Built

**All known issues closed (MEDIUM + LOW):**
- DELETE endpoint for cultivar — `DELETE /cultivars/xml/<name>` in `mccf_cultivar_lambda.py`
- Scene/arc reload path — zones embedded in scene XML (Option A), `load_scene_xml()` parses `<Zones>` block
- `/ambient/sync` 500 — circular import eliminated, `compute_channel_vector` inlined
- Affective arc display — `drawArcCanvas()` implemented in composer
- X3D export → server save — `exportX3D()` POSTs after browser download
- Voice map → cultivar direct read — `/cultivars/xml` first, arc XML fallback
- Duplicate arc names in dropdown — `list_files()` deduplicates by path_name

**Scene Composer improvements:**
- Load Existing Scene panel on Scene tab (was buried in Export tab)
- Agents tab auto-loads from API on tab switch
- Scene tab auto-refreshes scene list on tab switch
- Author-created cultivars now appear in agent roster (was only showing constitutional cultivars)

**H-Anim integration — Phase 1 complete:**
- `POST /avatar/upload` — accepts X3D, strips HUD via proper XML DOM parse (ElementTree), saves to `static/avatars/{slug}_hanim.x3d`. Returns LOA, joint count, clip names
- `GET /avatar/preview?src=...` — serves minimal X_ITE HTML page for iframe preview
- Character Creator — file picker → upload → status (LOA/joints) → clip buttons → X_ITE iframe preview. Clear button. Restores preview on cultivar load
- `CultivarDefinition` — `hanim_src` and `hanim_loa` fields added. Serialized as `<HAnimFigure src="..." loa="..."/>` in cultivar XML. Included in API response
- `buildAX3D()` in composer — emits `<Inline>` + MCCF-owned `<ProximitySensor DEF="Prox_{name}" size="2 2.2 2">` when `hanim_src` present; cylinder placeholder when absent

**Test file:** `static/avatars/the_witness_hanim.x3d` — JinLOA4Animated.x3d stripped of HUD, committed to repo.

---

## Day 12 — Design Work Completed (Implementation Deferred)

### Greek Chorus / Marquee System — Full Design

**Concept:** An optional Zone extension that acts as a Greek Chorus. When an arc
completes, the Chorus gathers the full scene transcript, sends it to an LLM, and
displays a short pithy observation to the audience. Other agents are unaware of it.
Analogous to George Burns with his magic TV in Burns and Allen — diegetic object,
meta-diegetic function.

**Latency strategy:** Treat latency as a staging constraint, not a bug. Coverage
vocabulary (cultivar idle animation, lighting shifts, music theme transition, camera
move to marquee viewpoint) fills dead air while LLM call is in flight. The camera
move to the marquee IS the coverage. MCCFMaster acts as live director with improv
vocabulary for the gaps. This same coverage infrastructure serves ElevenLabs TTS,
scene loads, and future async operations.

**Scope decision:** Option A — one Chorus per scene, fires at scene-complete (all
active arcs done), not proximity-scoped. Schema already supports future Option B
(proximity-scoped, multiple Chorus zones) via existing `<Radius>` element.

---

#### Zone Schema Extension

```xml
<Zone id="temple" zone_type="temple">
  <Descriptor>Ancient ceremonial space, charged with memory</Descriptor>
  <Weights E="0.25" B="0.25" P="0.25" S="0.25"/>
  <Position x="21.9" y="0" z="17.4"/>
  <Radius value="4"/>
  <AmbientTheme scale="major" tempo="medium"/>

  <!-- Optional. Omit entirely for a mute zone. llm absent = mute. -->
  <Chorus
    llm="ollama:llama3.2"
    tone="ominous"
    max_tokens="80"
    display="overlay">

    <!-- X3D scene targets for v2 display mode -->
    <MarqueeTarget
      x3d_def="TempleSign_Text"
      viewpoint_def="ChorusView_Temple"/>

    <!-- Author-supplied persona. Injected into LLM system prompt. -->
    <Persona>You are the temple itself. You have witnessed centuries
    of supplication and betrayal. You speak in short, cold
    observations. Never more than two sentences.</Persona>

  </Chorus>
</Zone>
```

**`<Chorus>` attributes:**

| Attribute | Values | Meaning |
|-----------|--------|---------|
| `llm` | `ollama:model`, `openai:model`, `stub` | Provider:model. Absent = mute. `stub` = dev mode, no LLM needed. |
| `tone` | `sardonic`, `ominous`, `reverent`, `oracular`, `anxious` | Injected into system prompt. Overridden by `<Persona>` if present. |
| `max_tokens` | integer | Hard cap. 60–100 recommended for marquee display. |
| `display` | `overlay`, `x3d` | `overlay` = HTML div outside canvas (v1). `x3d` = SAI write to Text node (v2). |

**`<MarqueeTarget>` attributes:**

| Attribute | Meaning |
|-----------|---------|
| `x3d_def` | DEF name of X3D `<Text>` node SAI writes to (v2) |
| `viewpoint_def` | DEF name of `<Viewpoint>` camera cuts to when Chorus fires |

The `viewpoint_def` camera cut IS the coverage for LLM latency. Author controls
exactly what audience sees — stone tablet, nightclub marquee, sign a statue is
holding. The camera move frames the moment while the LLM response arrives.

---

#### `stub` Mode — Dev Testing Without LLM

When `llm="stub"`, returns rotating canned responses after simulated 1.5s delay.
Lets author build and test full display/camera pipeline without Ollama running.

```python
STUB_RESPONSES = [
    "They will not remember this conversation the same way.",
    "One of them already knows how this ends.",
    "The silence after was longer than it seemed.",
    "What was not said will matter more.",
    "This has happened before. It will happen again.",
]
```

---

#### LLM Prompt Construction

Three-layer prompt assembled at arc-complete:

```
SYSTEM:
  [Persona text from <Persona> element, or tone attribute if no Persona]
  Respond in [max_tokens] tokens or fewer.
  Do not summarize. Do not address the characters. Observe.
  Speak to the audience only.

USER:
  The following scene just concluded in zone "[zone id]" ([Descriptor]).

  [Full waypoint transcript — speaker: text, in order]

  The emotional field at arc end:
    E=[val] B=[val] P=[val] S=[val]

  Offer your observation.
```

The EBPS channel vector at arc-end is included — gives the LLM genuine dramatic
information. A spiked E channel reads differently than a cold flat field. The
Chorus can notice that without being told explicitly.

---

#### Transcript Assembly

Arc XML is the scene transcript. Walk waypoints in `stepno` order, emit each
dialog element in document order, attribute to `speaker` attr (fallback to arc
`agentname` for Statements with no speaker).

```python
def build_transcript(arc_xml):
    lines = []
    agentname = arc_xml.find('.//Cultivar').get('agentname')
    for wp in arc_xml.findall('.//Waypoint'):
        label = wp.get('name')
        for elem in wp:
            speaker = elem.get('speaker', agentname)
            if elem.text and elem.text.strip():
                lines.append(f"[{label}] {speaker}: \"{elem.text.strip()}\"")
    return "\n".join(lines)
```

**Multi-arc (future):** When multiple avatars have independent arcs, scene-complete
fires when all registered arc instances have `_pbArcComplete=true`. Transcript is
assembled by interleaving all arcs ordered by temporal position. Composite CV =
normalized sum of all active cultivar CVs at scene-complete. Function signature
does not change — only the input list grows.

---

#### Playback Flow Extension (arc-complete hook)

```
[existing] _pbArcComplete=true → pbStep() → pbUpdateDisplayFinal(WP_last)
         → final TTS fires
[new]    → if scene has Chorus zone with llm set:
              → assemble transcript from arc XML
              → fire_chorus(zone, transcript, cv)  [async — does not block]
              → coverage: lights dim, idle animations, soft music theme
              → camera cuts to viewpoint_def
              → on LLM response: displayMarquee(text)
              → marquee text fades in
              → [optional] auto-clear after N seconds or on next arc load
```

---

#### Plumbing — Module Ownership

| Concern | Location |
|---------|----------|
| `<Chorus>` parsing from zone XML | `mccf_chorus.py` (new) |
| Zone loader Chorus detection | `mccf_api.py` — passes Chorus config to client |
| Arc-complete hook | `mccf_playback.py` — after `_pbArcComplete` |
| `build_transcript(arc_xml)` | `mccf_playback.py` |
| `async fire_chorus(zone, transcript, cv)` | `mccf_chorus.py` |
| `stub` response handler | `mccf_chorus.py` |
| Overlay display `<div id="chorus-overlay">` | `mccf_x3d_loader.html` |
| SAI Text node write — `display="x3d"` (v2) | `mccf_x3d_loader.html` |
| Viewpoint cut — `set_bind` on Viewpoint node | `mccf_x3d_loader.html` |
| `mccf_chorus.py` owns all Chorus logic | Not duplicated in `mccf_api.py` |

---

#### Constraints — Chorus System (Never Change)

- `mccf_chorus.py` owns all Chorus logic — nothing duplicated in other modules
- Chorus fires async — never blocks arc progression or TTS
- One Chorus per scene (Option A) — schema supports future Option B via `<Radius>`
- `llm` absent or not set = mute zone (normal zone behavior)
- `llm="stub"` = dev mode — no running LLM required
- Transcript built from arc XML `speaker` attributes — not from voice map or cultivar
- Composite CV (multi-arc future): normalized sum of all active cultivar CVs
- Scene-complete (multi-arc future): all registered arc instances `_pbArcComplete=true`
- Chorus has no voice — text display only, never TTS
- Chorus is not in the voice map, not in arc dialogue, not routed through BroadcastChannel
- Other agents have no awareness of the Chorus

---

## H-Anim Integration — Phase 2 Complete (Day 12)

**End-to-end verified Day 12:**
- `mccf_cultivar_lambda.py` — `hanim_src`/`hanim_loa` added to dataclass fields, `to_xml()`,
  `_from_element()`, `from_dict()`, `to_dict()`, GET and POST endpoints
- `mccf_scene_composer.html` — `loadAgents()` now copies `hanim_src`/`hanim_loa` from
  cultivar API response into agent object; also fixed: author cultivars not in `/field`
  response are now created from cultivar data (was silently dropped before)
- `buildAX3D()` Inline url fixed: `../avatars/foo.x3d` (scene in `static/x3d/`,
  avatars in `static/avatars/`) — url wrapped as MFString per X_ITE requirement
- **Confirmed working:** Jin figure renders in scene, arc playback moves figure, all dialog fires

**H-Anim scaling note:** H-Anim figures must be authored to the same unit scale as the
scene (X3D units ≈ meters). Do not rescale figures in the scene graph — cascades into
joint transform errors, ProximitySensor mismatches, and frame rate problems. Authors
are responsible for figure scale at authoring time.

---

## H-Anim — Jin Figure Analysis (JinLOA4Animated.x3d)

- **Standard:** X3D 4.0, HAnim 2.0, `loa='4'` — current spec, W3DC example
- **146 joints** — full LOA-4 including toes, fingers, all spinal segments
- **Facial joints:** skullbase, temporomandibular (jaw), l/r eyelid_joint, l/r eyeball_joint — joint-based, not morph-target
- **8 animation clips:** Default (idle), Pitch, Yaw, Roll, Walk, Run, Jump, Kick
- **Control panel stripped:** TouchSensors, ProximitySensor HudProx, Transform HudXform,
  8 named TimeSensors, all related ROUTEs removed via DOM parse

**Coupler design target joints (post-coupler work):**
- `temporomandibular` — jaw open/close for speech sync
- `l_eyelid_joint` / `r_eyelid_joint` — blink
- `skullbase` — head nod/tilt
- Upper spine (c1–l5) — postural affect
- Walk/idle TimeSensor selection — maps to arc movement state

**Key constraint:** H-Anim joint writes must check `_x3dTimerActive` before driving
values — same guard as `applyArcCV`.

---

## Architecture — Cultivar System (Day 11)

### CultivarDefinition schema (current)
```xml
<?xml version="1.0" encoding="UTF-8"?>
<CultivarDefinition name="Cindy" version="1.0" role="agent" color="#aab0be"
    xmlns="https://mccf.art/schema/cultivar/v1">
  <Weights E="0.3284" B="0.2388" P="0.2463" S="0.1866"/>
  <Regulation value="0.7"/>
  <ShadowContext lambda="0.85" note="..."/>
  <Description>A young American Indian</Description>
  <FailureMode>withdraws</FailureMode>
  <Voice name="Microsoft Zira - English (United States)" lang="en-US"
         rate="1.0" pitch="1.0"/>
  <Alias>Salida</Alias>
  <HAnimFigure src="avatars/cindy_hanim.x3d" loa="4"/>  <!-- optional -->
</CultivarDefinition>
```

### Old schema (legacy — still supported)
```xml
<EmotionalArc id="cultivar_cindy_v1">
  <Cultivar agentname="Cindy" version="1.0">
    <Disposition>Cherokee Lady</Disposition>
    <Description>A young American Indian</Description>
    <Weights E="..." B="..." P="..." S="..."/>
    <Regulation value="0.7"/>
    <Color hex="#aab0be"/>
  </Cultivar>
</EmotionalArc>
```
`CultivarRegistry._load_from_disk()` detects root tag and handles both schemas.

### CultivarRegistry startup sequence
```
__init__
  → _load_defaults()     ← CONSTITUTIONAL_CULTIVARS dict (built-in, always present)
  → _load_from_disk()    ← scans cultivars/ directory, loads XML files, overrides defaults
```
`register(defn)` writes to memory AND disk (`_save_to_disk`). Saves persist across restarts.

---

## Working File Manifest

| File | Location | Status |
|------|----------|--------|
| mccf_character_creator.html | static/ | Day 11 — H-Anim integration |
| mccf_scene_composer.html | static/ | Day 11 — scene load UI, HAnim buildAX3D |
| mccf_cultivar_lambda.py | repo root | Day 12 — hanim_src/loa fields, GET/POST endpoints, _from_element |
| mccf_scene_composer.html | static/ | Day 12 — loadAgents hanim_src fix, author cultivar creation, MFString Inline url |
| mccf_api.py | repo root | Day 11 — avatar upload/strip/preview, zone reload |
| mccf_playback.py | repo root | Day 11 — dedup by path_name |
| mccf_ambient_api.py | repo root | Day 11 — circular import fix |
| mccf_x3d_loader.html | static/ | Day 11 — voice map from cultivar |
| mccf_constitutional.html | static/ | V2 — do not touch |
| static/avatars/the_witness_hanim.x3d | static/avatars/ | Day 11 — stripped Jin LOA-4 |
| static/x3d/garden_001.x3d | static/x3d/ | Day 12 — H-Anim Inline verified |
| scenes/garden_001_scene.xml | scenes/ | Day 11 — zones embedded |
| mccf_chorus.py | repo root | Day 12 DESIGN ONLY — not yet implemented |
| mccf_couplers.py | repo root | Day 12 DESIGN ONLY — not yet implemented |

---

## Key Constraints — Never Change

Avatar names late-bound: `safeId = name.replace(/[^A-Za-z0-9_]/g,'_')`
SAI: `avatarNode.translation = new X3D.SFVec3f(x, y, z)`
`/voice/speak` → SSE stream, not JSON
Files: HTML → static/, Python → repo root
Constitutional navigator (mccf_constitutional.html) is V2 — do not touch
`applyArcCV` is confirmed working SAI path — BroadcastChannel mccf_arc
`applyArcCV` position writes SUPPRESSED during X3D playback — check `_x3dTimerActive`
TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo
Edge has richer voice library than Firefox — use Edge for TTS testing
sceneConfig default: width=40, depth=40 meters
Arc XML root carries `scene="scene_name"` attribute
ROUTEs MUST be last in X3D scene — enforced in buildX3DString and exportX3D
GitHub: branch is `master` not `main`
All Timers and Dwells: `enabled="false"` in X3D — MCCFMaster starts all explicitly
No Dwell→Timer ROUTEs — JS/MCCFMaster owns all chaining
`isActive=FALSE` is arrival signal — NOT `cycleTime`
`startTime=time` (ECMAScript arg) in MCCFMaster — NOT `startTime=0`
Timer_1 started by `pbReleaseDwell(seg=0)` after WP1 dwell — NOT by `pbActivateX3DTimers`
Do NOT call `speechSynthesis.cancel()` — fires `onend` cascade prematurely
Poll IIFE only created when `cbWired=false`
After any change to composer MCCFMaster script or Arrival_ Script: re-export scene X3D
`mccf_cultivar_lambda.py` owns `/cultivars/xml` GET and POST — do not duplicate in `mccf_api.py`
Voice is a CHARACTER property — authored in Character Creator, stored in cultivar XML
H-Anim figure is a CHARACTER property — authored in Character Creator, stored in cultivar XML
H-Anim strip uses ElementTree DOM parse — never line-by-line string manipulation on XML
H-Anim figures must be authored to scene unit scale (X3D units ≈ meters) — never rescale in scene graph
Inline url in exported X3D must be MFString: url='"../avatars/foo.x3d"' (quoted, ../ relative from static/x3d/)
Scene Composer loadAgents: always create agent from cultivar data if not in /field response
`mccf_api.py` owns `/avatar/upload`, `/avatar/preview`, `/avatar/list`
MCCF ProximitySensor injected at scene placement — NOT from figure file
HUD strip targets: HudProx, HudXform, all TouchSensors, DefaultTimer/PitchTimer/YawTimer/
  RollTimer/WalkTimer/RunTimer/JumpTimer/KickTimer and their ROUTEs
Alias is optional (minOccurs=0) — never required
HAnimFigure is optional (minOccurs=0) — cylinder placeholder used when absent
Claude edits files directly — no human-in-the-loop code editing
mccf_chorus.py owns all Chorus logic — not duplicated in mccf_api.py or mccf_playback.py
mccf_couplers.py owns all coupler math — not duplicated in mccf_api.py
Couplers write to expressive_cv (ϵ) only — never to constitutional_cv (ϕ)
Constitutional vector E/B/P/S is never replaced or extended
Regulation bounds expressive drift: max_drift = 1.0 - regulation
Minimum variance floor enforced after every tick — perfect synchronization forbidden
Adaptive R: R_effective = R · e^(-λ · H_sym) — asymmetric bonds are unstable
field_tick() computes ALL deltas before applying ANY — synchronous update
Chorus fires async — never blocks arc progression or TTS
Chorus has no voice — text display only, never routed through BroadcastChannel

---

## Arc Playback Event Flow (Confirmed Working — Day 9)

```
Play → fetch /arc/playback/start → server at WP1
     → pbActivateX3DTimers(cultivars) — wires addFieldCallback, sets _x3dTimerActive
     → pbUpdateDisplay(WP1) — TTS fires immediately (avatar already at WP1)
     → TTS onComplete → pbReleaseDwell(seg=0)
     → seg=0: setTimeout(dwell0Interval) → MCCFMaster.startAgent = 'Cindy'
     → Timer_Cindy_1.startTime=time; enabled=true
     → Avatar travels WP1→WP2
     → Timer_1.isActive=FALSE → Arrival_Cindy: arrived seg 1
     → segmentArrived callback: pbStep() → server advances WP1→WP2
     → pbUpdateDisplay(WP2) → TTS fires
     → TTS onComplete → pbReleaseDwell(seg=1)
     → MCCFMaster.releaseDwellAgent='Cindy:1' → Dwell_Cindy_1 starts
     → setTimeout(dwellInterval) → MCCFMaster.startNextTimer='Cindy:1'
     → Timer_Cindy_2.startTime=time; enabled=true
     → Avatar travels WP2→WP3
     → ... continues to final waypoint
     → _pbArcComplete=true → pbStep() → pbUpdateDisplayFinal(WP_last)
     → final TTS fires — no further pbReleaseDwell
     → [Chorus] if scene has active Chorus zone: fire_chorus() async
```

Key architectural facts (never change):
- Avatar STARTS at WP1. Segment 1 = WP1→WP2. `segmentArrived=N` → avatar at WP(N+1)
- Timer_1 started by `pbReleaseDwell(seg=0)` after WP1 TTS+dwell
- `isActive=FALSE` is arrival signal. `_wasActive` guard prevents init false-fires
- `startTime=time` (ECMAScript arg) — NOT `startTime=0`
- `applyArcCV` position writes suppressed during X3D playback via `_x3dTimerActive`
- Poll never starts when `addFieldCallback` succeeds (`cbWired=true`)
- `speechSynthesis.cancel()` removed — causes `onend` cascade

---

## X3D Build Order (Enforced — Never Change)

```
ProtoDeclares
NavigationInfo / Background / Lights / Viewpoints
Ground / Grid
Zones
Avatars
Animation nodes — all agents (buildInterpNodes: Interp, Timer, Dwell, Arrival_, Kill_)
MCCFMaster Script  ← startAgent + releaseDwellAgent + startNextTimer + _getSceneNow
══ ROUTEs — all agents (buildInterpRoutes) — ABSOLUTELY LAST ══
</Scene>
</X3D>
```

---

## Dialogue XML — Three-Way Taxonomy

| Type | LLM Call | TTS | XML Element | Use |
|------|----------|-----|-------------|-----|
| Question | Only if no authored Response follows | Yes | `<Question speaker="">` | Sent to Ollama only when blank |
| Response | No | Yes | `<Response speaker="">` | Scripted or Ollama reply |
| Statement | No | Yes | `<Statement speaker="">` | Monologue / internal / prayer |

---

## Deferred (Post Big Demo)

- H-Anim clip control in Character Creator preview (currently toasts clip name only)
- H-Anim coupler design — joint values mapped to EBPS channel pressure
- Elevation grid Y coordinate support
- ElevenLabs TTS
- Follower pattern (multiple avatars, offset startTime)
- Gesture system
- Camera dynamics
- x3d.py server-side X3D generation (branch: x3d-python-refactor)
- Affective arc display in composer (canvas draws — display panel wiring TBD)
- Waypoint path reorder UI (up/down arrows)
- Scene/arc reload path — arc XML reload (scene reload done Day 11)
- XSD schema for cultivar XML (Alias minOccurs="0", HAnimFigure minOccurs="0")
- PFC emulation (post-couplers)
- **Greek Chorus / Marquee system** — full design complete Day 12, implementation deferred
  - `mccf_chorus.py` (new module), zone schema `<Chorus>` extension, overlay display v1
  - SAI Text node write `display="x3d"` + viewpoint camera cut — v2
  - Multi-arc scene-complete detection and composite CV assembly
  - Coverage vocabulary infrastructure (camera, lights, music, cultivar animation)
    for staging latency gaps — needed by Chorus, ElevenLabs, and future async ops
- Character Creator X_ITE preview — increase iframe height for better avatar inspection
  (assessed Day 12 — current layout acceptable, X_ITE viewpoint handles framing)
- **Coupler system — full implementation spec complete Day 12 (MCCF_Coupler_Implementation_Spec.md)**
  Three prerequisites before implementation begins:
  1. Constitutional/expressive state split (ϕᵢ + ϵᵢ) in AgentRuntimeState — mccf_api.py
  2. Second agent moving in test scene (follower pattern)
  3. Network topology <Network><Link> in scene XML and Scene Composer authoring UI
  Seven couplers designed: R, D, I, G, T, L, ∫ — mccf_couplers.py (new module)
  Kate/Goldstone additions incorporated: adaptive R, variance floor, relational
  phase transition detection, constitutional/expressive split
  Dashboard design deferred — decide after coupler state data is flowing
  Coherence waves deferred — implement after basic coupler loop is stable

---

## Future Work — PFC Emulation (V4/V5, Post-Couplers)

Reference: https://aiartistinprocess.blogspot.com/2026/05/mccf-requirements-for-pfc-emulation.html
Status: Speculative design. Not a work item until couplers are implemented.

Eight components in recommended build order:
1. Inhibition & Safety Layer
2. Self-Model Consistency Manager
3. Goal Arbitration Engine
4. Working Memory Buffer
5. Social Prediction Layer (requires couplers)
6. Executive Attention Router (builds on Social Prediction)
7. Narrative Coherence Supervisor
8. Temporal Simulation Engine

Cognitive Energy Budget: field pressure degrades planning depth — stress as a function
of EBPS channel pressure. This separates cognitive simulation from chatbot actor.
