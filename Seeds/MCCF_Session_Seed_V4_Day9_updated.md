# MCCF Session Seed — V4 "The New York Rocket" — Day 9
Repo: https://github.com/artistinprocess/mccf
Last commit: 990d75a — Day 8 working playback. Pushed to master.

---

## State at End of Day 8

### What Was Fixed Today

**MCCFMaster Script — COMPLETE**
- Added `startAgent` (inputOnly SFString) — starts Timer_N_1 via `Browser.currentTime` workaround
- Added `releaseDwellAgent` (inputOnly SFString, format "AgentSafeName:segNum") — starts Dwell_N
- Added `startNextTimer` (inputOnly SFString, format "AgentSafeName:segNum") — starts Timer_N+1 with try/catch for end-of-arc
- `Browser.currentTime` is undefined in X_ITE external SAI — confirmed. `time` argument to inputOnly functions is Unix epoch, not scene-relative. Fix: `startTime=0` works because X_ITE TimeSensors use Unix epoch internally — setting startTime=0 means "start now" when scene has been running for seconds.
- `_getSceneNow()` helper reads `Timer_N.time` for Dwell startTime — also returns epoch which is correct.

**Timer/Dwell Chaining — COMPLETE**
- Removed Dwell→Timer X3D ROUTE entirely — was routing `cycleTime` (duration) to `startTime` (absolute), wrong semantics
- Timer_1: `enabled=false`, started by MCCFMaster.startAgent
- Timer_2+: `enabled=false`, started by MCCFMaster.startNextTimer after JS setTimeout
- Dwell nodes: started by MCCFMaster.releaseDwellAgent after TTS completes
- JS `setTimeout(dwellInterval * 1000)` after pbReleaseDwell → checks for next timer → fires startNextTimer or does final pbStep

**WP1 Audio — COMPLETE**
- On `segmentArrived seg=1`: fetch `/arc/playback/state` (server already at WP1) instead of `pbStep()` (which would advance past WP1)
- Subsequent segments: `pbStep()` as before

**Final Waypoint Audio — COMPLETE**
- After last dwell, `startNextTimer` check finds no Timer_N+1 → falls through to `pbStep()` → fetches last waypoint → TTS fires
- Arc has N waypoints, N-1 segments. Last waypoint content was previously never reached.

**End-to-End Verified**
- 3-waypoint arc: WP1→WP2→WP3 all visited, all audio fired, dwell at each waypoint
- Tested with `arc_walktopool_2026-05-10T052132.xml`

---

## Architecture — Confirmed Working

```
Play → MCCFMaster.startAgent = 'Cindy'
     → Timer_Cindy_1.startTime=0; enabled=true
     → Avatar travels segment 1
     → Timer_1.cycleTime → ROUTE → Arrival_Cindy.arrived
     → Arrival_Cindy: segmentArrived=1 (outputOnly)
     → addFieldCallback fires → fetch /arc/playback/state → pbUpdateDisplay(WP1)
     → TTS fires WP1 lines → onComplete → pbReleaseDwell('Cindy')
     → MCCFMaster.releaseDwellAgent = 'Cindy:1'
     → Dwell_Cindy_1.startTime=Timer_Cindy_1.time; enabled=true
     → setTimeout(dwellInterval) → check Timer_Cindy_2 exists → MCCFMaster.startNextTimer='Cindy:1'
     → Timer_Cindy_2.startTime=0; enabled=true
     → Avatar travels segment 2
     → Arrival_Cindy: segmentArrived=2
     → pbStep() → server advances → pbUpdateDisplay(WP2)
     → TTS fires WP2 → pbReleaseDwell → Dwell_2 → setTimeout → no Timer_3 found
     → pbStep() → server advances → pbUpdateDisplay(WP3)
     → TTS fires WP3 → pbReleaseDwell → Dwell_3 → setTimeout → no Timer_4 → arc complete
```

**X3D Build Order (enforced, never change):**
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

**Timer node build (enforced):**
- All Timers: `enabled="false"` — MCCFMaster starts them all explicitly
- All Dwells: `enabled="false"` — MCCFMaster starts them all explicitly
- No Dwell→Timer ROUTEs — chaining is JS/MCCFMaster only

---

## Known Issues — Priority Order

1. **Voice assignments incorrect — Zira not firing, only default voice (MEDIUM)**
   - Root cause: `_buildSceneVoiceMap()` parses `<EmotionalArc cultivar="X" voice="Y">` from scene def XML
   - Scene def XML is fetched via `/scene/load/scene` on arc file select → parsed into `window._loadedSceneDefXml`
   - Verify: after arc select, check `window._pbSceneVoiceMap` in console — is it populated?
   - WP2 in test arc has speaker "The Advocate" — not a cultivar name, so no voice map entry. Expected to use rotation fallback.
   - Check: is `_pbVoices` populated? Is `_pbSceneVoiceMap` built? Is `_buildSceneVoiceMap` finding the `voice=` attribute?

2. **No linger at second-to-last waypoint (MEDIUM)**
   - When `startNextTimer` finds no next timer, it calls `pbStep()` immediately after `dwellInterval` setTimeout
   - But `pbStep()` fires TTS for the last WP immediately — avatar is still at second-to-last WP
   - Dwell at last WP: after last WP TTS completes, `pbReleaseDwell` is called but Dwell_N starts with no next timer — correct, arc ends
   - May need: do NOT call `pbStep()` after last dwell until TTS for current WP completes

3. **`static/x3d/` not in git — add `.gitkeep` (LOW)**
   ```bash
   mkdir -p static/x3d
   touch static/x3d/.gitkeep
   git add static/x3d/.gitkeep
   git commit -m "Add static/x3d/.gitkeep"
   git push origin master
   ```

4. **`/ambient/sync` 500 error on play (LOW)** — server endpoint error, separate issue

5. **Affective arc display in composer does nothing (LOW)** — artifact

6. **X3D export → server save (LOW)** — exportX3D downloads to browser; should POST to server

---

## Working File Manifest

| File | Location | Status |
|------|----------|--------|
| mccf_scene_composer.html | static/ | Day 8 — pushed |
| mccf_x3d_loader.html | static/ | Day 8 — pushed |
| mccf_api.py | repo root | Day 7/8 — pushed |
| mccf_playback.py | repo root | unchanged — pushed |
| mccf_constitutional.html | static/ | V2 — do not touch |

---

## Key Constraints — Never Change
- Avatar names late-bound: `safeId = name.replace(/[^A-Za-z0-9_]/g,'_')`
- SAI: `avatarNode.translation = new X3D.SFVec3f(x, y, z)`
- `/voice/speak` → SSE stream, not JSON
- Files: HTML → static/, Python → repo root
- Constitutional navigator (mccf_constitutional.html) is V2 — do not touch
- `applyArcCV` is confirmed working SAI path — BroadcastChannel mccf_arc
- TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo
- Edge has richer voice library than Firefox — use Edge for TTS testing
- sceneConfig default: width=40, depth=40 meters
- Arc XML root carries `scene="scene_name"` attribute
- ROUTEs MUST be last in X3D scene — enforced in buildX3DString and exportX3D
- GitHub: branch is `master` not `main`
- All Timers and Dwells: `enabled="false"` in X3D — MCCFMaster starts all explicitly
- No Dwell→Timer ROUTEs — JS/MCCFMaster owns all chaining

---

## Dialogue XML — Three-Way Taxonomy

| Type | LLM Call | TTS | XML Element | Use |
|------|----------|-----|-------------|-----|
| Question | Only if no authored Response follows | Yes | `<Question speaker="">` | Sent to Ollama only when blank |
| Response | No | Yes | `<Response speaker="">` | Scripted or Ollama reply |
| Statement | No | Yes | `<Statement speaker="">` | Monologue / internal / prayer |

---

## Operation Order for Testing
1. `ollama serve` + `py mccf_api.py`
2. Hard-reload composer (Ctrl+Shift+R)
3. Load existing scene from Export tab dropdown
4. Verify paths loaded: `Object.keys(paths).length` > 0 in console
5. Export Scene XML → Export X3D → Send to Launcher
6. Hard-reload loader (Ctrl+Shift+R)
7. Select new X3D, select arc, Voice ON, Play
8. Watch Firefox F12 console for full chain

---

## Deferred (Post Big Demo)
- Elevation grid Y coordinate support
- H-Anim figure integration
- ElevenLabs TTS
- Follower pattern (multiple avatars, offset startTime)
- Gesture system
- Camera dynamics
- x3d.py server-side X3D generation (branch: x3d-python-refactor)
- Cultivar Character Creator (full spec in Day 7 seed)
- Affective arc display in composer
- Waypoint path reorder UI (up/down arrows)
- X3D export → server save (exportX3D downloads to browser; should POST)

---

## Future Work — PFC Emulation (V4/V5, Post-Couplers)

**Reference:** https://aiartistinprocess.blogspot.com/2026/05/mccf-requirements-for-pfc-emulation.html

**Status:** Speculative design. Not a work item until couplers are implemented.

### Core Concept
The Prefrontal Cortex Module (PFCM) sits between the emotional field and the LLM generative layer as an **executive governor** — not a language generator. It produces constraints, priorities, weighting functions, and suppression signals. The LLM remains the expressive cortex. The PFC becomes the behavioral regulator.

### Key Architectural Insight
> "The PFC should NOT generate language. It should generate constraints, priorities, weighting functions, suppression signals, future evaluations."

This maps cleanly onto existing MCCF structure: LLM handles generation, field handles pressure, PFC handles arbitration between them.

### Eight Components (in recommended build order)

1. **Inhibition & Safety Layer** — Build first. Highest value, lowest complexity. Suppresses contradictory actions, scene-breaking behavior, lore violations, emotional discontinuities. Maps directly to existing EBPS channel weights. Produces the "character almost said it… but stopped" effect — dramatically more interesting than expression alone.

2. **Self-Model Consistency Manager** — Build second. Maintains evolving identity core (role, moral alignment, attachment style, core fear). Continuously checks: "Does this action still feel like ME?" Already implicit in cultivar design — formalizes it.

3. **Goal Arbitration Engine** — Build third. Dynamically weights competing drives (fear, loyalty, curiosity, duty, survival, ideology) given current context. Extends existing EBPS weighting. Produces believable hesitation and contradiction.

4. **Working Memory Buffer** — Build fourth. Active scene/context buffer: scene focus, active conflicts, emotional pressure, immediate goals, suppressed actions, attention weights. The "mental desktop" for the character.

5. **Social Prediction Layer** — Requires couplers. Maintains lightweight predictive models of other agents: trust, deception probability, attachment, dominance, emotional volatility, alliance structure. Enables manipulation, empathy, strategic deception, emotional realism.

6. **Executive Attention Router** — Builds on Social Prediction Layer. Chooses what matters now, what to ignore, what memory to recall, what emotional signal dominates. Without this, agents become diffuse and incoherent.

7. **Narrative Coherence Supervisor** — MCCF-specific. Monitors unresolved arcs, emotional pacing, symbolic motifs, tension curves, revelation timing. Can intentionally delay disclosure to maximize narrative tension. Dramatic executive control.

8. **Temporal Simulation Engine** — Build last. Most expensive, most speculative. Generates candidate actions, simulates futures to depth N, scores outcomes by emotional cost / narrative coherence / goal alignment / social risk / identity consistency. JEPA-adjacent: action-conditioned latent predictive modeling. **Risk:** at depth=3 with multiple candidates, requires many LLM calls per decision cycle — expensive for real-time dramatic systems. Requires dedicated design effort before committing.

### The Cognitive Energy Budget (Most Original Idea)
When PFC is overloaded, impulsivity rises, memory shortens, emotional leakage increases, planning depth decreases. Maps directly to field pressure in MCCF — stress as a function of EBPS channel pressure dynamically degrades planning depth. Deserves its own design document. This is what separates cognitive simulation from chatbot actor.

### Relationship to JEPA
MCCF with PFCM is closer to **Affective JEPA** than standard JEPA:
- JEPA asks: "What future state is likely?"
- MCCF PFC asks: "What future state is acceptable for THIS self, in THIS story, under THESE emotional pressures?"

Standard JEPA lacks value-weighted future selection. MCCF adds emotional manifolds, social modeling, autobiographical continuity, narrative intelligence, executive arbitration.

### Coupler Dependency
The full architecture requires couplers. The Social Prediction Layer and Temporal Simulation Engine have nothing to operate on without formal inter-agent relationships established by the coupler layer. Inhibition, Self-Model, and Goal Arbitration can be built as single-agent components before couplers. Full PFCM requires couplers first.

### Data Flow (Full System)
```
Scene Input
    ↓
Perceptual Parser
    ↓
Emotional State Update (existing MCCF field)
    ↓
PFC Executive Evaluation  ← new
    ↓
Candidate Action Generation
    ↓
Temporal Simulation  ← new
    ↓
Inhibition Filtering  ← new
    ↓
Dialogue / Action Output (existing LLM layer)
```

### Long-Term Horizon
At full implementation: hierarchical plans, autobiographical narrative identity, symbolic self-protection, moral drift, attachment adaptation, trauma persistence, ideology formation. At that point MCCF is no longer simulating dialogue — it is simulating executive cognition embedded in narrative time.
