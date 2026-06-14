# MCCF Behavior System Specification
**Version:** 0.1 — Day 25, 2026-05-24
**Rule:** Author does not edit code. Claude delivers complete files only.
**Repo:** https://github.com/artistinprocess/mccf — branch `master`

---

## 1. Design Goals

1. HAnim avatar behaviors (Walk, Run, Jump, Kick, Pitch, Yaw, Roll, Default/idle) fire from pre-built X3D TimeSensors already present in the avatar file — no new animation code needed.
2. Behaviors are triggered by three distinct event sources: arc playback (transit/dwell), zone proximity, and inter-agent proximity.
3. The emotional state of each agent (EBPS vector) is maintained at runtime by the Director and influences which behavior fires.
4. EBPS→behavior mapping starts authored (static lookup table per cultivar) then becomes dynamic as accumulated resonance modifies weights across scenes.
5. Inter-scene history is persisted so relationships between agents evolve over time.

---

## 2. Architecture: Composer vs Director

### 2.1 MCCF Composer (authoring time)
Produces static artifacts consumed by the Director at runtime.

| Composer output | Contains |
|---|---|
| Scene XML (`*_scene.xml`) | Zones, waypoints, paths, network links, agent cultivar refs |
| X3D scene file (`*.x3d`) | ProximitySensors (zone + avatar), Inline+IMPORT for HAnim, movement Timers/Interpolators, all ROUTEs |
| Cultivar XML (`cultivar_*.xml`) | Agent identity, voice, HAnimFigure src, initial EBPS vector, behavior→EBPS map |
| Arc XML (`exports/*.xml`) | Recorded waypoint sequence with waypointOrder groups |

### 2.2 MCCF Director (runtime)
Python/Flask server process. Reads composer artifacts at scene load. Owns all runtime state.

**Director responsibilities:**
- Load scene XML → parse Network links, zone EBPS biases, path waypointOrder groups
- Load cultivar XML → initialize per-agent EBPS vector and behavior map
- Load arc XML → build ordered action group sequence
- Drive arc playback: fire movement timers per waypointOrder group via SAI (through loader)
- Fire behavior timers at transit start (Walk on) and dwell start (Walk off, dwell behavior on)
- Receive proximity events from loader (zone enter/exit, agent enter/exit)
- Apply zone EBPS pressure on zone entry
- Apply network coupler math on inter-agent proximity
- Map current EBPS vector → behavior timer name → fire via loader
- Accumulate resonance history → update behavior map weights over time
- Persist inter-scene history to JSON store

---

## 3. HAnim Behavior Timer Contract

### 3.1 Timer names (fixed, defined in HAnim file)
```
DefaultTimer   — idle stand / breathe
PitchTimer     — head pitch
YawTimer       — head yaw
RollTimer      — head roll
WalkTimer      — walk cycle
RunTimer       — run cycle
JumpTimer      — jump
KickTimer      — kick
```

### 3.2 Activation mechanism
```javascript
// X3D SAI — to start a behavior:
timerNode.enabled = true;

// To stop a behavior:
timerNode.enabled = false;
```

**Rule:** exactly one behavior timer is `enabled=true` at any moment per agent.
All others are `enabled=false`. Mutual exclusion enforced by Director.

All timers ship with `enabled="false"` in the HAnim X3D file.
`DefaultTimer` is started by the loader on scene load (initial idle state).

**Confirmed Day 25:** `enabled=true/false` is the ONLY working SAI mechanism in X_ITE.
`startTime`, `stopTime` do NOT work for behavior switching. Do not use them.
`setValue('enabled', new X3D.SFBool(true))` also fails — direct property assignment only.

### 3.3 IMPORT naming convention (in scene X3D)
```xml
<IMPORT inlineDEF="HAnim_Cindy" exportedDEF="WalkTimer" AS="WalkTimer_Cindy"/>
```
Pattern: `TimerBase_AgentSafeName`

### 3.4 Access from loader JS
```javascript
// Via getImportedNode — retry loop until Inline resolves
const node = scene.getImportedNode('WalkTimer_Cindy');
node.setValue('enabled', new X3D.SFBool(true));
```

---

## 4. Event Sources and Behavior Triggers

### 4.1 Arc Playback (transit / dwell)

**Implementation (confirmed Day 25):** walk/idle switching is driven by field callbacks
on the path `Timer_N` nodes, wired in `_wirePathTimerBehavior()` after the behavior
timer map resolves:

```javascript
// Transit begins — isActive fires TRUE when Timer_N starts
Timer_N.isActive = true  →  WalkTimer.enabled = true, all others false

// Transit ends — fraction_changed reaches 1.0 at cycle completion
Timer_N.fraction_changed >= 0.99  →  DefaultTimer.enabled = true, all others false
```

**Never use TTS completion or dwell timing to drive behavior switches.**
Locomotion is X3D-native. Dialogue is MCCF-native. They are independent.

**Pivot implementation (confirmed Day 25):**
- `_buildPivotCacheFromSceneXml(doc)` runs inside `_parseSceneZoneData` at scene load
- Parses `<Path><PathWaypoint ref="wpName"/>` sequence + `<Waypoint pos_x pos_z>` positions
- Builds `_agentWaypointCache[safeName] = {1:{pos_x,pos_z}, 2:..., ...}` (1-based by path order)
- At `isActive=true`: `_pivotAgentToSegment(safeName, seg)` computes `atan2(dx, dz)` heading
- Writes `avatarNode.rotation = new X3D.SFRotation(0, 1, 0, heading)` to `Avatar_` Transform
- 50ms gap between pivot and WalkTimer enable gives X3D one render frame to apply rotation
- **TODO (next):** duplicate first keyValue in PositionInterpolator in scene composer so avatar
  holds position briefly — removes need for 50ms setTimeout entirely


**waypointOrder** groups simultaneous events. Numeric. Same number fires together; higher number waits for lower to complete.

**Transit start** (movement Timer_N fires):
- Stop current behavior
- Start `WalkTimer`

**Dwell start** (Dwell_N fires, TTS begins):
- Stop `WalkTimer`
- Start behavior specified by waypoint's `dwell_behavior` field (default: `DefaultTimer`)
- Apply zone EBPS pressure if waypoint is inside a zone

**Waypoint data fields** (current + additions needed):
```
name           — string, unique
label          — string, narrative label
position       — [x, y, z]
dwell_time     — float seconds
dwell_behavior — string: "Default"|"Walk"|"Run"|"Jump"|"Kick"|"Pitch"|"Yaw"|"Roll"  ← ADD
zone_pressure  — string, zone name (already present)
```

### 4.2 Zone Proximity (ProximitySensor in X3D)

Each zone has a `ProximitySensor DEF="Prox_ZoneName"` baked by the composer.

**enterTime** → loader reports `zone_enter` event to Director with `{agent, zone}`
**exitTime** → loader reports `zone_exit` event to Director with `{agent, zone}`

Director response to `zone_enter`:
1. Look up zone's EBPS bias (E, B, P, S sliders — already stored on zone)
2. Apply bias to agent's current vector: `agent.EBPS += zone.bias × zone.influence_weight`
3. Map new EBPS → behavior timer → fire

### 4.3 Inter-Agent Proximity (avatar ProximitySensor)

Each agent gets a `ProximitySensor DEF="AgentProx_AgentSafeName"` inside their scene Transform, radius ~2.5 units (social interaction distance). Added by composer at scene build time.

**enterTime** → loader reports `agent_prox_enter` event: `{agent, other_agent}`
**exitTime** → loader reports `agent_prox_exit` event: `{agent, other_agent}`

Director response to `agent_prox_enter`:
1. Look up Network link: `from=agent, to=other_agent`
2. If link exists: `other.EBPS += agent.EBPS × link.strength` (per link.type channel weighting)
3. Map both agents' new EBPS → behavior timers → fire
4. Log interaction to resonance history

---

## 5. EBPS Vector and Behavior Mapping

### 5.1 EBPS Vector
Four channels, range −1.0 to +1.0:
```
E — Empathic / relational
B — Behavioral / somatic
P — Projective / spatial
S — Symbolic / archetypal
```

Each agent has a live vector maintained by Director. Initialized from cultivar XML.

### 5.2 Behavior→EBPS Map (authored in cultivar, then dynamic)

Initial static map (per cultivar XML, `<BehaviorMap>` element — TO BE ADDED):
```xml
<BehaviorMap>
  <Entry behavior="Default" E="0.0"  B="0.0"  P="0.0"  S="0.0"/>
  <Entry behavior="Walk"    E="0.1"  B="0.5"  P="0.3"  S="0.0"/>
  <Entry behavior="Run"     E="0.0"  B="0.9"  P="0.5"  S="0.0"/>
  <Entry behavior="Jump"    E="0.2"  B="0.8"  P="0.6"  S="0.1"/>
  <Entry behavior="Kick"    E="-0.2" B="0.9"  P="0.2"  S="-0.1"/>
  <Entry behavior="Pitch"   E="0.3"  B="0.1"  P="0.1"  S="0.4"/>
  <Entry behavior="Yaw"     E="0.2"  B="0.1"  P="0.3"  S="0.3"/>
  <Entry behavior="Roll"    E="0.1"  B="0.2"  P="0.2"  S="0.5"/>
</BehaviorMap>
```

**Mapping algorithm** (Director): given current EBPS vector, find behavior whose map entry minimizes Euclidean distance. That behavior fires.

### 5.3 Dynamic weight accumulation

After each inter-agent interaction the Director adjusts the behavior map weights:
```
resonance_delta = interaction_outcome × link.strength × decay_factor
behavior_map[behavior].weights += resonance_delta
```

`interaction_outcome` is initially 1.0 (all interactions positive). Future: dialogue sentiment analysis feeds this value.

`decay_factor` applies across scenes: weights decay toward initial values at a configured rate unless reinforced.

---

## 6. Inter-Scene Persistence

Director maintains a JSON history store at `data/resonance_history.json`:
```json
{
  "agents": {
    "Cindy": {
      "ebps": [0.1, 0.3, 0.0, 0.2],
      "behavior_map_deltas": { "Walk": [0.0, 0.05, 0.02, 0.0], ... },
      "interaction_log": [
        { "scene": "garden_001", "partner": "The Gardener", "strength": 0.70, "outcome": 1.0, "timestamp": "..." }
      ]
    }
  }
}
```

Loaded by Director at scene start. Updated at scene end or on significant interaction events.

---

## 7. Task List (ordered)

### Phase 1 — Prove behavior firing works ✅ COMPLETE (Day 25)
- [x] **1.1** `getImportedNode` resolves after Inline load — confirmed
- [x] **1.2** `WalkTimer_Cindy.enabled=true` → walk loops — confirmed
- [x] **1.3** `WalkTimer_Cindy.enabled=false`, `DefaultTimer_Cindy.enabled=true` → idle — confirmed
- [x] **1.4** Arc playback wired via `_wirePathTimerBehavior()`: `Timer_N.isActive=true` → Walk, `Timer_N.fraction_changed>=0.99` → Default — confirmed working cleanly
- [x] **1.5** Avatar pivots to face direction of travel at each segment start — confirmed working

### Phase 2 — Waypoint behavior authoring
- [ ] **2.1** Add `dwell_behavior` field to waypoint data model (server + waypoint editor UI)
- [ ] **2.2** Scene composer reads `dwell_behavior` from waypoint and passes to loader
- [ ] **2.3** Loader fires correct behavior timer at dwell start

### Phase 3 — Zone proximity behaviors
- [ ] **3.1** Loader reports `zone_enter` / `zone_exit` events to Director via POST
- [ ] **3.2** Director applies zone EBPS bias, maps to behavior, fires timer
- [ ] **3.3** Test: Cindy enters CindyAtTemple zone → behavior shifts

### Phase 4 — Inter-agent proximity
- [ ] **4.1** Composer adds `AgentProx_AgentSafeName` ProximitySensor to scene X3D at build time
- [ ] **4.2** Loader reports `agent_prox_enter` / `agent_prox_exit` to Director
- [ ] **4.3** Director applies network coupler math, fires behavior on both agents
- [ ] **4.4** Add Anna as second agent (prerequisite: Phase 1 confirmed working for Cindy)

### Phase 5 — EBPS map authoring
- [ ] **5.1** Add `<BehaviorMap>` to cultivar XML schema
- [ ] **5.2** Character creator UI: behavior map editor (table of EBPS values per behavior)
- [ ] **5.3** Director loads behavior map from cultivar at scene start

### Phase 6 — Dynamic resonance
- [ ] **6.1** Director accumulates resonance history per interaction
- [ ] **6.2** Behavior map weights update after interactions
- [ ] **6.3** Persist to `data/resonance_history.json`, load at scene start
- [ ] **6.4** Decay function across scenes

---

## 8. Known Non-Issues (do not fix)

- `ambient/sync 500` — mccf_lighting module missing, not in scope
- `lighting/scalars 404` — same
- AudioContext gesture warning — browser policy, harmless
- `HAnimHumanoid.segments deprecated` — X3D 4.x cosmetic, X_ITE honors it
- Tracking Prevention blocked jsdelivr — Edge/Firefox cookie policy, harmless

---

## 9. Architecture Invariants (never change without updating this doc)

- `waypointOrder` (SFInt32, initializeOnly) — REQUIRED on every Path node
- ROUTEs MUST be last in X3D scene file
- All behavior Timers: `enabled="false"` in HAnim X3D file
- `DefaultTimer` started by loader on scene load
- `var API = 'http://localhost:5000'` in both HTML files
- Behavior timer DEF in HAnim: `DefaultTimer`, `PitchTimer`, `YawTimer`, `RollTimer`, `WalkTimer`, `RunTimer`, `JumpTimer`, `KickTimer`
- IMPORT AS in scene: `TimerBase_AgentSafeName`
- HAnim Inline DEF: `HAnim_AgentSafeName`
- HAnim files: `static/avatars/` — EXPORT statements required for all 8 timer bases
- Cultivar files: `cultivars/cultivar_*.xml`
- Arc files: `exports/` — bare filename, no path prefix
- Resonance history: `data/resonance_history.json`
