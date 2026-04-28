# MCCF V3 — "The New York Rocket" — Specification

**Version:** 0.1 draft — April 28, 2026  
**Status:** For team review — one round of comments requested  
**Repository:** https://github.com/artistinprocess/mccf  
**Authors:** Len Bullard, Claude Sonnet 4.6 (Tae)  
**Theoretical contributors:** Kate (ChatGPT), Fidget (Gemini), Grok

---

## What V3 Is

V2 is a measurement instrument. One cultivar, one arc, sequential waypoints,
human as master clock.

V3 is a scene. One or more agents, spatial field, zone attractors, emergent
movement, live or scripted performance.

The transition: from measuring how an agent holds character under pressure
to observing how agents move through a semantic landscape and interact with
each other and with zones that have their own gravitational profiles.

V3 does not replace V2. The constitutional arc runs inside V3 as Improvisation
mode. V2 arcs play back as Playback mode. Live Theatre mode emerges from
the field without a script.

---

## What V3 Builds

Eight concrete deliverables. Everything else is deferred.

### 1. Zone Attractor System

Zones become semantic agents with their own channel vectors, not just
pressure modifiers. A zone's vocabulary descriptor is routed through the
same decomposition matrix as LLM responses, producing a zone ψ_zone vector.
Agent coherence toward a zone is computable with the existing R_ij machinery.
High coherence = gravitational pull. Low coherence = neutral or repulsion.

**Zone XML definition (EmotionalArc schema family):**
```xml
<Zone id="the_pool" zone_type="intimate">
  <Descriptor>care vulnerability warmth comfort intimacy presence felt</Descriptor>
  <Weights E="0.40" B="0.10" P="0.20" S="0.30"/>
  <Position x="0" y="0" z="8"/>
  <Radius value="5.0"/>
  <NoiseCoefficient value="0.10"/>
  <AmbientTheme scale="dorian" tempo="slow"/>
</Zone>
```

**Three starting zones for Garden of the Goddess:**
- The Temple — high P, high regulation, low noise. Sacred attractor.
- The Pool — high E/S, low regulation, moderate noise. Intimate attractor.
- The Library — high B/P, moderate S, low noise. Knowledge attractor.

**New endpoint:** `GET /zones` — returns registered zones with ψ_zone vectors.  
**New endpoint:** `POST /zones` — registers a zone from XML definition.  
**New file:** `zones/garden_of_the_goddess.xml` — scene zone definitions.

---

### 2. X3D Master Script

A single Script node governs all avatar movement, zone proximity detection,
and sound node switching. Currently the X3D loader HTML does this work in
JavaScript outside the scene. V3 moves it inside the X3D scene.

The Master Script receives field state from the MCCF server and drives:
- Avatar position (all four channels, not just S)
- Zone proximity triggers
- Sound node activation
- Lighting state (if reliable — see Module Decisions)

**Avatar movement — full channel mapping:**

| Channel | Movement Parameter |
|---|---|
| E (emotional) | lean/tilt toward conversation partner |
| B (behavioral) | stance stability / groundedness |
| P (predictive) | orientation toward destination zone |
| S (social) | approach/retreat along Z axis (current) |

The S-channel Z-translation we built in V2 remains. E, B, P drive additional
motion parameters to be determined by Len's X3D design work.

**New file:** `mccf_master_script.x3d` — Script node with routing.  
**Modified file:** `mccf_scene.x3d` — adds ROUTE connections to Master Script.  
**Modified file:** `mccf_x3d_loader.html` — delegates scene control to Master Script.

---

### 3. Three Performance Modes

Selectable in the constitutional navigator. One UI change — a mode selector
before arc run. The arc runner behavior changes per mode.

**Playback** — reads an existing EmotionalArc XML file. No LLM calls.
Channel values at each waypoint are read directly from the XML. Avatar
positions interpolate between waypoint pos_x/y/z values. Deterministic,
reproducible. Requires a valid EmotionalArc XML file as input.

**Improvisation** — current V2 behavior. Arc schema defines structure and
questions. LLM responds live. Field state evolves. This is the default mode.

**Live Theatre** — agents in a shared field, no scripted waypoints. The arc
advances on field events (coherence thresholds, zone proximity triggers) not
on human prompting. The Master Script drives timing. Genre classifier runs
continuously. Export captures what actually happened. Human can inject
thumps via keyboard or UI.

**New endpoint:** `GET /arc/playback` — accepts an EmotionalArc XML filename,
returns channel sequence for animation.

---

### 4. Scene XML Wrapper

A single-character scene is already valid — one EmotionalArc, one cultivar.
The Scene wrapper adds structure for multi-agent scenes without breaking
single-agent use.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Scene id="garden_session_001" timestamp="2026-05-01T20:00:00"
       zone_set="garden_of_the_goddess" mode="improvisation">
  <EmotionalArc cultivar="The Witness" actor="ollama" voice="Microsoft David"/>
  <!-- multi-agent: add more EmotionalArc elements here -->
</Scene>
```

Single-agent scene: one EmotionalArc element. No other changes needed.
Multi-agent scene: multiple EmotionalArc elements with different actor values.

The Scene element is the new root for `exports/`. Current EmotionalArc exports
remain valid as-is — they are wrapped on export, not replaced.

---

### 5. Δ_t Drift Measurement

Per Kate's Shadow Context framework. Each waypoint now logs a drift score
alongside channel values. Implementation: the server runs the LLM response
through decomposition twice — once with full arc history (shadow context
present), once without history (fresh pass). The divergence is Δ_t.

In V3 this is a logged diagnostic, not a control signal. It appears in the
XML export and in the right panel of the constitutional navigator.

```xml
<Waypoint id="W3_THE_ASK" stepno="3" ...
          drift="0.142" lambda="0.72">
```

`drift` = Δ_t for this waypoint.
`lambda` = cultivar's shadow context decay rate (from cultivar XML).

**New cultivar XML attribute:**
```xml
<ShadowContext lambda="0.72" note="moderate memory, uncertainty without accumulation"/>
```

**Modified endpoint:** `/arc/record` — computes and returns Δ_t alongside
existing channel values.

---

### 6. Adaptive λ Per Cultivar

Shadow context decay rate is a cultivar property. High λ = strong memory,
character persists. Low λ = present-moment focus, less accumulated drift.

Default values (adjustable in Character Studio):
- The Steward: λ = 0.85
- The Archivist: λ = 0.90
- The Witness: λ = 0.72
- The Advocate: λ = 0.60
- New cultivars: λ = 0.70 default
- The Ladies (when defined): λ = 0.20

λ exposed in:
- Cultivar XML definition files
- Character Studio slider (new field)
- `GET /cultivars/xml` response
- `POST /cultivars/xml` payload

---

### 7. Spatial Sound

X3D Sound nodes positioned at zone centers. Proximity to a zone activates
its ambient theme. Multiple zone overlaps blend proportionally.

```xml
<Sound location="0 0 15" maxBack="8" maxFront="8" spatialize="true">
  <AudioClip url="sounds/temple_lydian.wav" loop="true"/>
</Sound>
```

Sound files are external to the scene — researchers provide their own.
The scene schema defines the node structure; sound design is the author's work.

The current music module produces sounds Len describes as ugly. It is retired
in V3. Spatial Sound replaces it with author-provided audio files. This is
simpler, more flexible, and produces better results.

**New directory:** `sounds/` — author-provided ambient audio files.  
**Modified file:** `mccf_scene.x3d` — adds Sound nodes per zone.  
**Retired:** existing music generation module.

---

### 8. Garden of the Goddess — Initial Scene

The first V3 scene. Three zones, one or more cultivars, Improvisation mode
as the starting point.

Zone definitions in `zones/garden_of_the_goddess.xml`.
Scene definition in `scenes/garden_001.xml`.
Cultivar definitions in `cultivars/` (existing files + new ones authored
through Character Studio).

Characters and their relationships are Len's narrative design work. The
instrument provides the field. The author provides the characters and scene.

---

## Module Decisions

### Lighting Module — RETIRE

The lighting module has never worked reliably. X3D SAI light intensity
writes degrade the scene. Color writes work but are disconnected from
meaningful field state. V3 retires the lighting module rather than carry
non-functional code forward. If reliable lighting is needed later, it is
redesigned from scratch based on a clear requirement.

### Voice Module — HOLD

The voice module has an untested microphone input that could be useful
for Live Theatre mode (human voice as input to the field). It is not
retired but it is not a V3 build target. It is held for testing when
Live Theatre mode is stable. Do not invest in it before then.

### Music Module — RETIRE AND REPLACE

The current music module is theoretically interesting but produces poor
results. Spatial Sound (item 7 above) replaces it with author-provided
audio files positioned in the X3D scene. The music generation code is
retired. Spatial sound design is the author's responsibility.

### Character Studio — EXTEND, NOT REPLACE

Character Studio gained λ (shadow context decay) as a new slider. The
rest of its interface is unchanged. It is not redesigned in V3.

### Field Editor — SCOPE LIMIT

The Field Editor creates in-memory agents. Character Studio creates
persistent XML-backed cultivars. In V3 these remain separate. The
Field Editor is used for tuning, not character creation. No new features.

---

## XML Schema Additions

All additions are backward compatible. Existing V2 documents remain valid.

**Zone definition (new document type, same family):**
`<Zone>` with Descriptor, Weights, Position, Radius, NoiseCoefficient, AmbientTheme

**Scene wrapper (new root element for exports):**
`<Scene>` with id, timestamp, zone_set, mode, containing one or more `<EmotionalArc>`

**Waypoint additions:**
- `drift` attribute — Δ_t measurement
- `lambda` attribute — cultivar λ at time of run

**Cultivar additions:**
- `<ShadowContext lambda=""/>` element

**Existing elements:** unchanged.

---

## What V3 Does Not Build

The following are explicitly deferred. Not in scope. Not in the build list.

- CRIL full implementation (Interpretability Pressure field, CRM states)
- Θ-modifying systems (rule-editing civilizations)
- Geopolitical sphere dynamics
- Embedding-based measurement operator (semantic similarity routing)
- Blueprint refactor of mccf_api.py
- Multiple simultaneous scenes
- Full sensitivity analysis with real LLM data at scale
- Automated Gardener triggers (beyond diagnostic logging)
- Human-rated validation set for evaluation claims
- MaxEditor / full scene design tool

---

## Open Questions for Team Review

1. **X3D Master Script architecture** — what is the right division between
   the Master Script (inside the scene) and the loader HTML (outside)?
   Should all field-to-scene routing live in the Script node, or is some
   JavaScript in the HTML appropriate?

2. **Zone proximity detection** — X3D ProximitySensor fires when an avatar
   enters a zone radius. How does the sensor event feed back into the MCCF
   field? Does proximity increase coherence toward that zone, or does the
   field drive proximity without feedback?

3. **Playback interpolation** — between waypoints, does the avatar interpolate
   linearly or follow a curve? Does B-channel (behavioral consistency) affect
   interpolation smoothness?

4. **λ in the arc** — does λ decay within a single arc run (each waypoint
   the shadow context fades slightly) or is λ a fixed cultivar property
   that only matters across sessions?

5. **The Ladies** — what are their cultivar definitions? What waypoint
   questions should they carry? Len's narrative decision, not a spec decision.

6. **Sound file format** — WAV or OGG? X3D supports both. What is the
   recommended format for the sounds/ directory?

7. **Multi-LLM routing** — in Improvisation mode with two LLMs, do they
   respond to each other's outputs, or only to the shared arc questions?
   If they respond to each other, what is the turn structure?

---

## Review Request

This specification is submitted for one round of team review before
implementation begins. Please focus on:

- **Scope**: Is anything missing that is genuinely necessary for V3?
  Is anything included that should be deferred?
- **Architecture**: Are the eight build items internally consistent?
  Do they create dependencies that complicate the build order?
- **X3D**: Does the Master Script approach make sense given how X3D
  SAI actually behaves? (Len's domain.)
- **Module decisions**: Agree or disagree with lighting/music retirement?

We are not requesting theoretical extensions or new features. One round
of bounded comments, then implementation begins.

---

## Implementation Order (proposed)

1. Zone XML schema + `POST /zones` endpoint
2. Scene XML wrapper
3. Adaptive λ in cultivar XML + Character Studio
4. Δ_t measurement in `/arc/record`
5. X3D Master Script (Len leads X3D work, Tae leads Python/API)
6. Three performance modes (Playback first, then Live Theatre)
7. Spatial Sound nodes
8. Garden of the Goddess scene

---

*MCCF V3 Specification v0.1 — April 28, 2026*  
*For review by: Kate (ChatGPT), Fidget (Gemini), Grok, Len Bullard*
