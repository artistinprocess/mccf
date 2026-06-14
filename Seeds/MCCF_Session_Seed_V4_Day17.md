# MCCF Session Seed — V4 "The New York Rocket" — Day 17
Repo: https://github.com/artistinprocess/mccf
Last commit: Day 16 — zone command system working; Ollama speaking from observed_cv

---

## Workflow Rule — No Human-in-the-Loop Code Editing
Claude edits files directly and delivers them as outputs. The developer deploys the
output files. No manual code editing by the developer — eliminates transcription errors.

---

## Day 15 — Completed

### What Was Built

**mccf_couplers.py (new module):**
- All seven couplers implemented per spec: R (Resonance), D (Damping), I (Inversion),
  G (Gated), T (Threshold), L (Delay), ∫/Int (Integration)
- COUPLER_REGISTRY + apply_coupler() public entry point
- Helper functions: _parse_filter, _asymmetry, _eval_condition
- Fixed double-paren typo in coupler_integration from spec

**mccf_api.py additions:**
- `observed_cv` property added to AgentRuntimeState — ϕ + ϵ clamped to [0,1]
  (was missing; coupler code uses it everywhere — caused 500 on couplers/tick)
- `cv_override` path in arc/record — caller passes explicit E/B/P/S dict to bypass
  sentiment recomputation; used by X3D loader to seed ϕ from arc XML values
- `pressure = 0.0` in cv_override branch — was unbound, crashed ChannelVector
- Dead code fixed: POST /agent route decorator was missing, handler body was stranded
  after return in get_field_runtime() since an earlier refactor
- field_tick(), apply_field_tick_deltas(), _enforce_coupler_variance_floor()
- detect_phase_transition(), _cosine_similarity()
- _parse_network_links(), zone helpers
- _coupler_history deque registry for L (Delay) coupler
- POST /couplers/tick endpoint

**mccf_scene_composer.html:**
- _sceneArcAdvance() now calls arc/record at EVERY waypoint, not just LLM waypoints
- Scripted/statement-only waypoints use authored text for sentiment estimation
- Constitutional Navigator is now obsolete — composer is sole arc/record caller

**mccf_x3d_loader.html:**
- _seedArcRecord(state) — calls POST /arc/record on each waypoint arrival to seed ϕ
  from arc XML CV values; falls back to cultivar weights for pre-fix arcs
- _fireCouplerTick() — calls POST /couplers/tick after each waypoint arrival
- pbPlay() now calls _seedArcRecord + _fireCouplerTick for WP1 on play start
- pbStep() seeds then ticks in sequence
- pbUpdateDisplayFinal() ticks on final waypoint
- ϕ/ϵ panel display: bars 8px (was 4px), font 11px (was 9px), bold non-zero delta

### Verified Working
- Both Cindy and Steward appear in ϕ/ϵ panel after playing arcs
- Small but detectable ϵ variation confirmed — R coupler producing drift
- links=2 confirmed (Cindy ↔ Steward empathic bidirectional, strength 0.60)
- agents_ticked=2 confirmed after fix

### Bugs Fixed During Day 15
- observed_cv missing from AgentRuntimeState → AttributeError in couplers/tick
- pressure unbound in cv_override path → UnboundLocalError in arc/record
- _seedArcRecord silently skipping arcs without E/B/P/S on waypoints (pre-fix arcs)
- pbPlay() not seeding WP1 (only pbStep was seeding, which fires on seg 1 arrival)

---

## Day 16 — Completed

### What Was Built

**Zone Command System (new):**
- `garden_001_scene.xml` — zones upgraded to prototype:
  - pool: zone_type=sacred_memorial, Commands (OnEnter:reflect/*, OnDwell:confess/Cindy,
    OnExit:release/*), Memory capacity=5, Descriptor text
  - temple: zone_type=authority_throne, Commands (OnEnter:attend/*, OnEnter:greet/Cindy,
    OnDwell:warn/The Steward), Memory capacity=5, Descriptor text
  - Zone weights updated to reflect zone character (pool E↑, temple B↑)
- `mccf_api.py` additions:
  - `_ZONE_COMMAND_VOCAB` — 10 named dramatic commands with prompt expansions
  - `_zone_memory` dict + `_get_zone_memory()` + `_append_zone_memory()` — persists
    to `scenes/{scene}_zone_memory.json` on every event; loaded on first access
  - `_build_zone_prompt()` — builds Ollama prompt from observed_cv (ϕ+ϵ, not ϕ alone),
    zone descriptor, zone memory, cultivar name, and command expansion
  - `POST /zone/command` — dispatches to Ollama for LLM agents, logs for scripted agents
  - `GET /zone/memory` — inspect zone memory
  - `DELETE /zone/memory` — clear zone memory for testing
  - urllib used for Ollama calls (requests module not installed)
- `mccf_x3d_loader.html` additions:
  - `_zoneCommands`, `_zoneDescriptors`, `_cultivarActors`, `_waypointZoneMap` caches
  - `_parseSceneZoneData()` — fetches `GET /scene/load/scene/raw` to read Commands
    and EmotionalArc actor attributes from scene XML (not the X3D file)
  - `_matchZoneCommand()` — specific cultivar match takes priority over wildcard `*`
  - `_fireZoneCommand()` — dispatches POST /zone/command; speaks LLM response via TTS
    using cultivar voice; scripted agents logged only
  - Zone guard in `pbPlay()` — re-triggers parse if _zoneCommands still empty
  - pbStep() tracks zone transitions — fires OnExit for old zone, OnEnter for new
  - pbPlay() fires OnEnter for WP1 starting zone
  - pbStop() resets `_agentZone` tracking

### Verified Working
- Zone commands parsed: ['pool', 'temple'], Actors: {Cindy: 'ollama', Steward: 'ollama'}
- WaypointZones: {wppool: 'pool', wptemple: 'temple'}
- OnEnter pool reflect → Ollama responded: "This pool feels like a refuge for me now..."
- OnExit pool release → Ollama responded: "I'm leaving the stillness of the pool..."
- OnEnter temple greet → Ollama responded (with stage direction artifact — see below)
- Zone command responses arrive async ~1-2s after scripted TTS starts (fire-and-forget)

### Bugs Fixed During Day 16
- `requests` module not installed — replaced with `urllib.request` throughout
- `_parseSceneZoneData()` was reading `_loadedSceneDefXml` (reconstructed fragment,
  no Zone elements) — fixed to fetch `GET /scene/load/scene/raw` directly
- Zone data not loaded before Play pressed — added readiness guard in `pbPlay()`
- `current_waypoint` from playback response uses uppercase label as `id` (e.g. 'POOL')
  not waypoint name ('wppool') — fixed with candidate array lookup in zone derivation

### Known Tuning Items (not bugs — authorial choices)
- **Response length**: Ollama running long (3-5 sentences). Prompt says "one to three"
  but not enforced. Add `max_tokens: 60` to Ollama request and tighten to "one sentence."
- **Stage direction artifact**: LLM adding `*I take a deep breath*` action text.
  Add "Do not use asterisks or stage directions" to prompt. Strip asterisk spans from
  TTS text before speaking.
- **Timing**: Zone command responses arrive after scripted TTS starts (Ollama latency
  ~1-2s). For WP1 reflect, dramatic intent may prefer zone speech BEFORE scripted line.
  Option: await zone command response before starting TTS at WP1. Adds latency.
  Current fire-and-forget behavior is acceptable for now.
- **New scenes**: Scene Composer zone editor UI needs Commands/Memory authoring tab.
  Currently hand-edited in XML. Defer to composer update session.

---

## Day 17 — Next: Concurrent Arc Firing

### Context
The two arcs (Cindy and Steward) currently play sequentially — one completes before
the other starts. The X3D scene already has interpolators and timers for both agents.
Concurrent firing means both arcs play simultaneously.

### What Needs to Be Built

**Step 1 — Server: multi-arc session support**
Current: PlaybackSession handles one arc at a time. Playing a second arc replaces
the first session.
Needed: either simultaneous sessions keyed by cultivar name, or a single session
that manages multiple arcs and advances each independently.
The simplest approach: a dict of active sessions, keyed by cultivar name.
POST /arc/playback/start returns a session_id. All other playback endpoints
accept an optional session_id parameter.

**Step 2 — X3D: start all timers at once**
MCCFMaster already handles startAgent per cultivar. Concurrent firing means
calling startAgent for all cultivars in sequence (or near-simultaneously) after
all WP1 TTS completes.
The segmentArrived callbacks are already per-agent — they don't interfere.
Each agent's dwell/timer chain is independent.

**Step 3 — Loader: play multiple arcs**
pbPlay() currently handles one arc file. Need a way to select and play multiple
arcs simultaneously. Options:
  A) "Play All" button that plays all arcs in the current scene simultaneously
  B) Multi-select in the arc dropdown
  C) Scene-driven: load scene → automatically play all arcs associated with that scene
Option C is architecturally cleanest and aligns with the workflow goal.

**Step 4 — Coupler tick with both agents active simultaneously**
Currently _fireCouplerTick fires on each segmentArrived. With concurrent arcs,
ticks fire from both agents' arrival events — this is correct behavior.
The field_tick() synchronous update rule already handles this: all deltas computed
before any are applied, so concurrent arrivals don't cause order-dependency artifacts.

### Architecture Invariants (Never Change — Carry Forward)
```
constitutional_cv (ϕ) — written ONLY by arc/record via set_constitutional()
expressive_cv (ϵ)     — written ONLY by couplers via apply_expressive_delta()
max_drift             = 1.0 - regulation (per agent)
mccf_couplers.py      — owns all coupler math, never duplicated in mccf_api.py
field_tick()          — compute ALL deltas, then apply ALL (synchronous)
Variance floor        — enforced after every tick, perfect sync forbidden
Network topology      — read from scene XML <Network><Link> block
observed_cv           — ϕ + ϵ clamped to [0,1], read by couplers
```

---

## State at End of Day 16

### Files Changed (Day 16)
- `mccf_api.py` — zone command system: _ZONE_COMMAND_VOCAB, _zone_memory, 
                   _build_zone_prompt, POST /zone/command, GET/DELETE /zone/memory
- `mccf_x3d_loader.html` — _parseSceneZoneData, _fireZoneCommand, _matchZoneCommand,
                             zone tracking in pbPlay/pbStep/pbStop, zone readiness guard
- `scenes/garden_001_scene.xml` — Commands and Memory blocks on both zones,
                                   updated zone_types and weights, Descriptor text

### Test Scene State
- Scene: garden_001
- Agents: Cindy (pool start), The Steward (temple start)
- Network: Cindy ↔ The Steward, empathic, strength 0.60, bidirectional
- Arcs: both agents have arc XML in exports/; played sequentially
- ϕ/ϵ panel: both agents visible, ϵ drift confirmed
- Zone commands: firing on OnEnter/OnExit for both zones, Ollama responding
- Zone memory: persisting to scenes/garden_001_zone_memory.json

---

## Relational Dynamics Extension — Design Complete

Full spec in `MCCF_Relational_Dynamics_Extension_Spec.md` (upload at session start).
Four extensions in implementation order:

1. **Attentional Filter** — per-cultivar receptivity vector in cultivar XML;
   modulates incoming coupler deltas per channel before drift bound.
   One session. Lowest risk.
2. **Emotional Salience Memory** — salience weight per coherence history entry;
   T coupler phase events and high ϵ drift mark significant moments.
   One session.
3. **Bayesian Trust** — Beta distribution prior per network link; updates from
   resonance/divergence each tick; effective strength = authored × posterior mean.
   One to two sessions. Requires salience.
4. **Controlled Forgetting** — ϵ residue persists between arc sessions, decays
   by Ebbinghaus curve weighted by salience. High-regulation characters recover
   faster. Requires salience and trust.
   One session.

Total: three to four sessions. All four preserve existing architecture invariants.
Connection to Kate's "coherent incompleteness" discussion documented in spec.

---

## Deferred (Post Big Demo — updated)

- Constitutional Navigator — OBSOLETE (composer is now sole arc/record caller)
- Concurrent arc firing — **Day 17 priority**
- Zone command tuning (length, stage directions, timing) — **Day 17 minor**
- Scene Composer zone editor UI — Commands/Memory authoring tab
- Ease-in/ease-out — key/keyValue shape change on PositionInterpolator nodes
- Follower pattern — startTime offset on second agent's Timer relative to first
- H-Anim clip control in Character Creator preview
- H-Anim coupler design — joint values mapped to EBPS channel pressure
- Elevation grid Y coordinate support
- ElevenLabs TTS
- Gesture system / Camera dynamics
- Affective arc display in composer
- Waypoint path reorder UI
- Greek Chorus v2 — SAI Text node write
- Greek Chorus multi-arc — scene-complete detection across all active arcs
- Coherence waves (spec Part 6) — deferred until basic coupler loop stable
- PFC emulation (V4/V5, post-couplers)
- Dashboard Option B/C — dedicated coupler monitor / in-scene visualization

---

## Persistent Technical Rules (full carry-forward)

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
Inline url in exported X3D must be MFString: url='"../avatars/foo.x3d"'
Scene Composer loadAgents: always create agent from cultivar data if not in /field response
`mccf_api.py` owns `/avatar/upload`, `/avatar/preview`, `/avatar/list`
MCCF ProximitySensor injected at scene placement — NOT from figure file
Claude edits files directly — no human-in-the-loop code editing
mccf_chorus.py owns all Chorus logic — not duplicated in mccf_api.py
mccf_couplers.py owns all coupler math — not duplicated in mccf_api.py
Couplers write to expressive_cv (ϵ) only — never to constitutional_cv (ϕ)
Constitutional vector E/B/P/S is never replaced or extended
Regulation bounds expressive drift: max_drift = 1.0 - regulation
Minimum variance floor enforced after every tick — perfect synchronization forbidden
Adaptive R: R_effective = R · e^(-λ · H_sym) — asymmetric bonds are unstable
field_tick() computes ALL deltas before applying ANY — synchronous update
observed_cv = ϕ + ϵ clamped [0,1] — what couplers read as source state
arc/record cv_override path — pass explicit {E,B,P,S} dict to bypass sentiment
Chorus fires async — never blocks arc progression or TTS
Scene XML is self-contained: <Zones> block embedded, ChorusManager reads from it
Zone commands fire async (fire-and-forget) — never block arc playback or TTS
Zone command vocab is controlled (10 named commands) — never freeform strings
_build_zone_prompt speaks from observed_cv (ϕ+ϵ) not ϕ alone — drama lives in the distance
Zone memory persists to scenes/{scene}_zone_memory.json — survives server restart
_parseSceneZoneData() fetches /scene/load/scene/raw — NOT _loadedSceneDefXml (wrong cache)
Ollama called via urllib.request — requests module not installed in this environment
current_waypoint.id from playback response is uppercase label (e.g. 'POOL') not wp name
Zone derivation uses candidate array: [wp.id, wp.key, wp.name, wp.label, ...] against _waypointZoneMap
