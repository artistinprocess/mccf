# MCCF Session Seed — V4 "The New York Rocket" — Day 15
Repo: https://github.com/artistinprocess/mccf
Last commit: `10fd371` — Day 14 fix: arc/playback endpoint, Network tab, modes array

---

## Workflow Rule — No Human-in-the-Loop Code Editing
Claude edits files directly and delivers them as outputs. The developer deploys the
output files. No manual code editing by the developer — eliminates transcription errors.

---

## Day 14 — Completed

### What Was Built

**Prerequisite #1 — Constitutional/expressive state split (ϕ/ϵ) in mccf_api.py:**
- `AgentRuntimeState` dataclass added (line ~651): carries `constitutional_cv` (ϕ),
  `expressive_cv` (ϵ), `regulation`, `last_record_time`, `last_tick_time`
- `_agent_runtime: dict[str, AgentRuntimeState]` registry + `get_runtime()` lazy helper
- `set_constitutional()` — arc/record only writer of ϕ; seeds ϵ = ϕ on each call
- `apply_expressive_delta()` — couplers only writer of ϵ; enforces drift bound per channel
- `max_drift = 1.0 - regulation` — The Steward 0.20, Cindy 0.00 (regulation=1.0 — needs fix)
- `arc/record` now writes ϕ and returns `"runtime"` key in response
- `GET /field` and `GET /agent/<name>` augmented with `"runtime"` key
- `GET /field/runtime` — new dedicated endpoint for right-panel display

**Prerequisite #2 — Second agent moving in test scene:**
- `garden_001.x3d` — Steward animation nodes added: `Interp_The_Steward_1`,
  `Timer_The_Steward_1` (1.58s), `Dwell_The_Steward_1` (2.0s), `Arrival_The_Steward`,
  `Kill_The_Steward`, three ROUTEs
- `garden_001_scene.xml` — `<Path name="StewardToTemple">` and `<Path name="pathToPool">`
  added. Three paths total. Cindy and Steward pass each other when both arcs play.
- Arc playback confirmed: each arc plays separately (concurrent firing is deferred)

**Prerequisite #3 — Network topology in scene XML and Scene Composer:**
- `garden_001_scene.xml` now contains:
  ```xml
  <Network>
    <Link from="Cindy" to="The Steward" strength="0.60" type="empathic"/>
    <Link from="The Steward" to="Cindy" strength="0.60" type="empathic"/>
  </Network>
  ```
- Scene Composer — `Network` tab added (between Paths and Export):
  - From/To agent dropdowns (populated from placedAgents)
  - Type select: empathic / behavioral / power / social / full
  - Strength slider 0–1
  - Add Link / Add Bidirectional buttons
  - Live link list with delete
- `exportSceneXML()` writes `<Network>` block after `</Paths>`
- `_restoreChorusFromXml()` extended to also parse `<Network>` on scene load
- `_applyLoadedScene()` restores `networks[]` if server returns it
- Links stat added to Scene Stats panel

**ϕ/ϵ display in X3D loader right panel (`mccf_x3d_loader.html`):**
- `▶ ϕ/ϵ state` toggle at bottom of `#field-overlay` (collapsed by default)
- Polls `GET /field/runtime` every 750ms when expanded
- Per-agent rows: dual bar (ϕ blue, ϵ green overlay), numeric ϵ, delta per channel,
  regulation / drift cap / last tick time
- Delta all zeros until couplers run — confirmed working in Day 14 test

**Arc playback fix:**
- `GET /arc/playback` was missing — only referenced in a comment
- Added: scans `exports/`, parses each arc XML for cultivar/path_name/scene_name/
  waypoint count/first_waypoint, returns newest-first
- X3D loader arc dropdown now populates correctly on Refresh

**Known issue to fix before couplers:**
- Cindy's `regulation = 1.0`, `max_drift = 0.00` — her ϵ will be pinned to ϕ
- Check `<Regulation>` element in Cindy's cultivar XML — likely missing or set to 1.0
- Fix in Character Creator or directly in cultivar XML before Day 15 coupler work

---

## Day 15 — Next: mccf_couplers.py

### What Needs to Be Built

All three coupler prerequisites are done. Day 15 implements `mccf_couplers.py` —
the coupler tick loop that reads the network topology and moves ϵ away from ϕ.

**Step 1 — Read the coupler implementation spec before writing any code:**
The full spec is in `MCCF_Coupler_Implementation_Spec.md` in the repo.
Upload it at session start. It defines all seven couplers, math, and constraints.

**Step 2 — Implement mccf_couplers.py (new module):**
- `CouplerTick` class — reads `_agent_runtime` and `<Network>` links from scene XML
- Implements couplers R, D, I, G, T, L, ∫ per spec
- Calls `apply_expressive_delta()` on each agent — never touches ϕ
- `POST /couplers/tick` endpoint in `mccf_api.py` — called by loader poll loop
- Minimum variance floor enforced after every tick — perfect sync forbidden
- Adaptive R: `R_effective = R · e^(-λ · H_sym)`
- `field_tick()` computes ALL deltas before applying ANY (synchronous update)

**Step 3 — Wire loader to call /couplers/tick:**
- Add to existing poll loop in `mccf_x3d_loader.html`
- After tick, refresh `/field/runtime` — green bars start separating from blue

**Step 4 — Verify in right panel display:**
- Run arc through constitutional navigator (seeds ϕ)
- Load scene in X3D loader
- Watch ϵ drift in the ϕ/ϵ panel — green bar moves away from blue
- Delta values go non-zero

---

## Architecture Invariants (Never Change)

```
constitutional_cv (ϕ) — written ONLY by arc/record via set_constitutional()
expressive_cv (ϵ)     — written ONLY by couplers via apply_expressive_delta()
max_drift             = 1.0 - regulation (per agent)
mccf_couplers.py      — owns all coupler math, never duplicated in mccf_api.py
field_tick()          — compute ALL deltas, then apply ALL (synchronous)
Variance floor        — enforced after every tick, perfect sync forbidden
Network topology      — read from scene XML <Network><Link> block
```

---

## State at End of Day 14

### Files Changed (Day 14)
- `mccf_api.py` — AgentRuntimeState, /field/runtime, /arc/playback
- `mccf_x3d_loader.html` — ϕ/ϵ panel, runtime poll, modes array fix
- `mccf_scene_composer.html` — Network tab, exportSceneXML, _restoreChorusFromXml
- `garden_001.x3d` — Steward animation nodes
- `garden_001_scene.xml` — Steward paths, Network block

### Test Scene State
- Scene: `garden_001`
- Agents: Cindy (pool start), The Steward (temple start)
- Paths: Walktotemple (Cindy), StewardToTemple (Steward), pathToPool (Steward)
- Network: Cindy ↔ The Steward, empathic, strength 0.60, bidirectional
- Arcs recorded: both agents have arc XML in `exports/`

---

## Persistent Technical Rules

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
Chorus config loaded via POST /chorus/load when scene file selected in loader
Chorus fired via POST /chorus/fire from pbUpdateDisplayFinal (X3D-driven mode)
_chorusLastTimestamp reset to 0 on pbPlay — ensures fresh poll picks up response
Scene XML is self-contained: <Zones> block embedded, ChorusManager reads from it

---

## Arc Playback Event Flow (Confirmed Working — Day 13)

```
Play → fetch /arc/playback/start → server at WP1
     → x3dFileChanged() → POST /chorus/load → ChorusManager configured
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
     → POST /chorus/fire {arc_file} → ChorusManager.fire_chorus() async
     → startChorusPoll() — polls /chorus/state every 800ms
     → [~1.5s stub / LLM latency]
     → poll picks up response → displayChorus() → overlay appears bottom-center
     → 18s auto-dismiss or user clicks ✕
```

Key architectural facts (never change):
- Avatar STARTS at WP1. Segment 1 = WP1→WP2. `segmentArrived=N` → avatar at WP(N+1)
- Timer_1 started by `pbReleaseDwell(seg=0)` after WP1 TTS+dwell
- `isActive=FALSE` is arrival signal. `_wasActive` guard prevents init false-fires
- `startTime=time` (ECMAScript arg) — NOT `startTime=0`
- `applyArcCV` position writes suppressed during X3D playback via `_x3dTimerActive`
- Poll never starts when `addFieldCallback` succeeds (`cbWired=true`)
- `speechSynthesis.cancel()` removed — causes `onend` cascade
- `_x3dLastArrivedSeg` reset on pbPlay — prevents stale seg from second-run bug

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
- Greek Chorus v2 — SAI Text node write (`display="x3d"`) + viewpoint camera cut
- Greek Chorus multi-arc — scene-complete detection across all active arcs, composite CV
- Coverage vocabulary infrastructure (camera, lights, music, cultivar animation)
  for staging latency gaps — needed by ElevenLabs and future async ops
- Character Creator X_ITE preview — increase iframe height for better avatar inspection
- Concurrent arc firing — both arcs play simultaneously in X3D loader
  (currently recorded and played separately — architectural gap identified Day 14)
- Cindy regulation fix — set regulation < 1.0 so max_drift > 0.0 before coupler work

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
