# MCCF Session Handoff — Day 24
*Generated end-of-session Day 23 — 2026-05-22*

---

## Project: The New York Rocket
**MCCF** — Multi-agent X3D real-time theater engine animating a novel-in-progress.

**Pipeline:** Novel → MCCF scene → animated theater → XML-to-prompt → video generation → ElevenLabs voices → film.

**Story:** Enheduana's daughter Enredhuanna founded Hypoborea, a secret society operating for 6,000 years. Principal agent Anna (the Librarian) delivers the opening monologue ending in *"They are our incense." / "Blessed be."* — at which point the Greek Chorus fires.

**Repo:** https://github.com/artistinprocess/mccf — branch **`master`** (not main)

**Author does not edit code. Claude delivers complete files only. Always ask before using GitHub.**

---

## Architecture Invariants — NEVER VIOLATE

```
waypointOrder (SFInt32, initializeOnly) — REQUIRED on every Path
  Same number = simultaneous movement; ascending = sequential
  Missing or invalid = HARD STOP
  Validator: _validateAndBuildOrderGroups()

constitutional_cv (phi)  — written ONLY by arc/record
expressive_cv (eps)      — written ONLY by couplers
mccf_couplers.py         — owns all coupler math
observed_cv              — phi + eps clamped [0,1]

SAI avatar position:     avatarNode.translation = new X3D.SFVec3f(x, y, z)
/voice/speak             — SSE stream, NOT JSON
Files:                   HTML → static/, Python → repo root
ROUTEs MUST be last in X3D scene
All Timers/Dwells:       enabled="false" in X3D file
isActive=FALSE           — arrival signal, NOT cycleTime
startFromLoader (SFTime) — fired by pbReleaseDwell after WP1 dwell
advanceSeg (SFInt32)     — fired by _pbAdvanceSeg after each dwell expires
_pbArcComplete           — dict {safeName: bool}, NOT a global bool
_pbLastArcFiles          — retained for legacy/debug only; NOT used for Chorus
Chorus fires at scene end (allDone=true) via pbUpdateDisplayFinal
  transcript assembled live from _chorusTranscript during playback
  cv from _chorusFinalCV (last waypoint of last agent)
  POST /chorus/fire {transcript, cv, scene_name} — NO file lookup
  arc files live in exports/ — bare filename, no path prefix
API var:                 var API = 'http://localhost:5000'  (in both HTML files)
Loader URL:              API + '/static/mccf_x3d_loader.html'

HAnim behavior timers:   enabled="false" in stripped avatar file
                         MCCF activates via SAI startTime/stopTime writes
                         Timer DEF names: DefaultTimer, PitchTimer, YawTimer,
                         RollTimer, WalkTimer, RunTimer, JumpTimer, KickTimer
```

---

## Current Scene: garden_001

### Agents

| Agent | Status | waypointOrder | Waypoints | Segments | Notes |
|---|---|---|---|---|---|
| Cindy | Active, path recorded | 1 | 3 | 2 | HAnim — cindy_hanim.x3d (LOA4, 8 timers, disabled) |
| The Gardener | Active, path recorded | 2 | 2 | 1 | Placeholder avatar |
| The Steward | Placed, no path | — | — | — | Stationary cultivar, does NOT block allDone |
| **Anna** | **NOT YET AUTHORED** | TBD | TBD | TBD | Principal agent — pending HAnim behavior resolution |

### Scene State — confirmed working Day 23
- Full scene plays: Cindy (order 1) completes, The Gardener (order 2) fires, allDone triggers Chorus
- Chorus: working — transcript-direct to Ollama, overlay displays, auto-dismiss 18s
- Emotion display: working — ϕ/ϵ bars update per agent per waypoint
- Reset+Replay: working
- Behavior clip system: **BLOCKED** — see Day 23 blocker below
- `cultivar_cindy.xml`: restored with full character data + `<Behaviors>` table (6 clips)

---

## Day 23 Work Completed

### Task 1 — `mccf_cultivar_lambda.py` ✅
Added `behavior_clips` and `behavior_default` fields to `CultivarDefinition`.
`<Behaviors>` XML element fully parsed and serialized.
`GET /cultivars/<name>` now returns behavior data.
All five round-trip tests pass.

### Task 2 — `mccf_x3d_loader.html` — timer suffix + retry loop ✅
`_behaviorTimerMap`, `_agentBehaviorClips`, `_agentCurrentClip`, `_agentLastLoopClip` state variables added.
`BEHAVIOR_TIMER_BASES` list defined.
Retry loop (10 attempts × 500ms) for timer map population at `pbActivateX3DTimers`.

### Task 3 — `mccf_x3d_loader.html` — `selectBehaviorClip()` + `applyBehaviorClip()` ✅
Full behavior selection logic with hysteresis (±0.03).
Oneshot clip support with generation-guarded return timer.
Integrated into `applyHotHouseData()` — reads `observed_cv` or falls back to hotHouse channel values.

### Task 4 — `mccf_x3d_loader.html` — behavior clips loaded at `_seedArcRecord` ✅
Fetches `GET /cultivars/<name>` at first waypoint per cultivar.
Stores in `_agentBehaviorClips[safeName]`.
DefaultTimer fallback when no clips authored.

### Task 5 — `mccf_x3d_loader.html` — reset cleanup ✅
`_agentCurrentClip` and `_agentLastLoopClip` cleared on reset.
`_behaviorTimerMap` and `_agentBehaviorClips` preserved across reset.

### Task 6 — `cultivar_cindy.xml` authored ✅
Full character data restored (alias Salida, Microsoft Zira voice, cindy_hanim.x3d, weights).
`<Behaviors>` table: Default, Attentive, Casual, Walk, Run, Jump.

### `mccf_api.py` — avatar stripper fixes ✅
`BEHAVIOR_TIMER_DEFS` separated from `HUD_ONLY_TIMER_DEFS` — behavior timers now SURVIVE stripping.
`enabled="false"` forced on all behavior TimeSensors at strip time.
`EXPORT` statements added to stripped avatar file for each surviving timer.
`strip_hud()` now correctly removes only TouchSensors and StopTimer.

### `mccf_scene_composer.html` — IMPORT statements ✅
Eight `<IMPORT>` statements written after each `<Inline DEF="HAnim_*">` tag at scene export.
AS names follow `TimerBase_AgentSafeName` convention.

---

## Day 23 Blocker — X_ITE IMPORT/EXPORT Not Implemented

**Status: AWAITING W3C HAnim WG RESPONSE**

**Finding:** X_ITE 11.6.6 does not implement the X3D 4.0 IMPORT/EXPORT mechanism.

**Evidence:**
- `cindy_hanim.x3d` has correct `<EXPORT localDEF="DefaultTimer" AS="DefaultTimer"/>` statements ✅
- `garden_001.x3d` has correct `<IMPORT inlineDEF="HAnim_Cindy" exportedDEF="DefaultTimer" AS="DefaultTimer_Cindy"/>` statements ✅
- `canvas.browser.currentScene.getNamedNode('DefaultTimer_Cindy')` → "Named node not found" ❌
- `canvas.browser.currentScene.namedNodes` returns 43 nodes, none are behavior timers ❌
- `Inline.getExportedNode` → undefined ❌
- `Inline.internalScene` → undefined ❌

**Additional finding:** `namedNodes` returns numeric indices rather than a name-keyed structure — non-standard SAI behavior per spec.

**Two bug reports prepared for X3D public list / Holger Seelig:**
1. `IMPORT` statements do not register nodes accessible via `getNamedNode` or `namedNodes`
2. `namedNodes` returns numeric array rather than name-keyed entries (non-standard SAI)

**Messages sent to:** W3C HAnim WG (Don Brutzman), X3D public list pending WG response.

**Options when response arrives:**

*Option A — WG provides correct X_ITE API path (preferred)*
Update loader to use the correct call. No architecture change.

*Option B — X_ITE confirmed bug, fix pending*
Implement Option C as temporary workaround, revert when X_ITE is patched.

*Option C — Inline HAnim XML directly at scene export*
Scene Composer fetches avatar file content at export time and writes raw XML
into the scene instead of `<Inline>` reference. All timer DEF names become
first-class parent scene nodes. Scene files get larger (~6000 lines per LOA4 agent)
but behavior system works immediately. Easiest path.

*Option D — Move timer activation into X3D Script node*
Add behavior state polling to the `Arrival_` Script which has full
`Browser.currentScene` access from inside X3D. Loader posts desired behavior
to server; Script polls and fires timers. More extensible long-term.
More complex to implement.

**DO NOT implement Option C or D until WG response received.**

---

## Files Deployed — Day 23

All files confirmed deployed and tested:

| File | Location | Status |
|---|---|---|
| `mccf_cultivar_lambda.py` | repo root | ✅ deployed, tested |
| `mccf_x3d_loader.html` | static/ | ✅ deployed |
| `mccf_scene_composer.html` | static/ | ✅ deployed |
| `mccf_api.py` | repo root | ✅ deployed |
| `cultivar_cindy.xml` | cultivars/ | ✅ deployed |
| `cindy_hanim.x3d` | static/avatars/ | ✅ deployed (EXPORT statements present) |

---

## Playback Flow (current, confirmed working)

```
User clicks "Play All"
  → POST /arc/playback/start/all
  → pbActivateX3DTimers — wires Arrival_ callbacks, attempts behavior timer map
    → tryMapTimers() retry loop (10 × 500ms) — currently exhausts without finding timers
  → Groups fired in waypointOrder sequence
  → _seedArcRecord — fetches behavior_clips from /cultivars/<name>
  → Each group: pbUpdateDisplay → TTS → pbReleaseDwell → startFromLoader → Timer_1
  → isActive=FALSE arrivals → advanceSeg → next timer
  → allDone=true → pbUpdateDisplayFinal
    → POST /chorus/fire {transcript, cv, scene_name}
    → Ollama responds async
    → chorus-overlay displays, auto-dismiss 18s

User clicks "Reset + Replay"
  → pbReset() — _pbCbGeneration++ (invalidates stale callbacks)
  → _agentCurrentClip = {}, _agentLastLoopClip = {} (behavior state cleared)
  → Kill_ nodes snap avatars to StartPosition
  → POST /arc/playback/reset
  → pbPlayAll() fires
```

---

## Day 24 Priorities (in order)

### 1. Resolve X_ITE IMPORT/EXPORT blocker
Wait for WG response. When received, implement the appropriate option above.
Do not author Anna or rename the scene until behavior activation is confirmed working
on Cindy — she is the test case for the entire behavior system.

### 2. Confirm behavior transitions in console
Once blocker resolved, Play All and verify console shows:
```
pbActivateX3DTimers: behavior timers mapped for Cindy (attempt N) — DefaultTimer...
behavior: Cindy (none) → Default
behavior: Cindy Default → Attentive
behavior: Cindy Attentive → Walk
```

### 3. Author Anna's path (after behavior confirmed on Cindy)
- Place Anna on the map in Scene Composer
- waypointOrder: likely 1 (simultaneous with Cindy) or 0 (precedes everyone)
- Final waypoint dwell long enough for full monologue before allDone
- Arc voice data: *"They are our incense."* then *"Blessed be."*
- Anna's `<Behaviors>` table: Default and Address (PitchTimer) only,
  Walk gated at B > 0.80 (Librarian — stationary during monologue)

### 4. Scene rename: garden_001 → hypoborea_001 (after Anna authored and tested)
Affects: .x3d filename, _scene.xml, _zones.xml, arc filenames, scene name field.

### 5. The Steward
Stationary cultivar. Path authoring deferred until scripted.
Confirmed safe — does not affect allDone count.

---

## HAnim Design Decisions — Confirmed Day 23

- **LOA 2 static avatars** (Jin, Chul, Hyun, Sun): deferred. Suitable for crowd
  dummies only. No gesture or gait capability. Stored in hanim/ subdirectory.
- **LOA 4 (JinLOA4Animated.x3d)**: the standard for all MCCF agents.
- **Facial animation**: uses HAnimDisplacer nodes, not joint rotation.
  Awaiting W3C HAnim WG example files for standards-compliant implementation.
  Deferred to future sprint. Not on critical path for opening scene.
- **HAnim editor module**: deferred. Will be added to Character Creator when
  facial animation sprint begins. Estimated one weekend.
- **Same mesh, multiple cultivars**: confirmed valid. Emotional field is
  per-cultivar; mesh is shared. `<Behaviors>` thresholds differentiate characters.
- **Viewpoint sequencer**: planned future feature. HAnim viewpoints survive
  stripping and are accessible in scene. Will bind to waypointOrder events.

---

## Spec Documents — In Effect

- `MCCF_HAnim_Behavior_Activation_Spec.md` (Day 23) — behavior clip system design
- `MCCF_Relational_Dynamics_Extension_Spec.md` — trust, salience, attentional filter
  (deferred — not started Day 23, blocked on behavior activation)

---

## Known Non-Issues — Do Not Fix

- `VP_Overview not found` on load — cosmetic, X_ITE
- `ambient/sync 500` — ModuleNotFoundError: No module named 'mccf_lighting'
- `lighting/scalars 404`
- AudioContext gesture warning from X_ITE
- MS audio 48khz reset
- Jin.png local file path error — cosmetic, image asset not on server

---

## Future: MCCF as Programmed Instruction Platform
(unchanged from Day 22 handoff — deferred until theater pipeline stable)

---

*End of Day 23 handoff. Paste this file at the start of the Day 24 conversation.*
