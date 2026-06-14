# MCCF Session Seed — V4 "The New York Rocket" — Day 18
Repo: https://github.com/artistinprocess/mccf
Last commit: Day 17 — concurrent arc firing; Day 17b — TTS/step/zone queue fixes

---

## Workflow Rule — No Human-in-the-Loop Code Editing
Claude edits files directly and delivers them as outputs. No manual code editing.

---

## Day 17b — Completed (bug fixes)

**Fix A — Per-cultivar TTS state**
_pbLastSpoken, _pbLastStepKey, _pbSpeakToken changed from shared scalars to
per-cultivar dicts keyed by cultivar safe name. pbSpeakQALines takes third arg
cultivarKey; all call sites pass safeName.

**Fix B — Zone command serial queue**
_fireZoneCommand enqueues to _zoneCommandQueue; _drainZoneCommandQueue fires one
at a time. Prevents simultaneous Ollama calls timing out.

**Fix C — Per-session step-in-flight guard**
_pbStepInFlight changed from false to {} dict keyed by session_id.

**Fix D — pbReset / pbStop 415 fix**
Both fetches now send Content-Type: application/json and body '{}'.

### Test result after 17b
- Cindy moved. Steward did NOT move.
- Scene froze after reset; hard reload did not restart.
- Root cause unknown — server session stale (reset 415 was the bug) OR X3D nodes
  missing for The_Steward. The 415 fix may resolve it on clean restart.

---

## Day 18 — Start Here

### Step 1: Clean diagnostic test
1. Restart Flask server (py mccf_api.py) — clears all session state
2. Hard-reload loader in Edge (Ctrl+Shift+R)
3. Click Play All
4. Console must show ALL of:
   - pbUpdateDisplay: firing TTS for The_Steward
   - pbReleaseDwell: WP1 complete — waiting 2s then starting Timer_1 for The_Steward
   - MCCFMaster: started Timer_The_Steward_1
   - segmentArrived callback: Arrival_The_Steward seg=1

### Step 2: If MCCFMaster line missing
startAgent path broken for Steward. Re-export garden_001.x3d from Scene Composer.
Check that Timer_The_Steward_1 and Arrival_The_Steward exist in the X3D.

### Step 3: If all 4 lines present but Steward still not moving
Timer node exists but PositionInterpolator key/keyValue may be wrong.
Check scene composer waypoint positions for Steward's path.

---

## Priority Queue

1. Verify Steward moves (diagnostic above)
2. All-complete Chorus — wait for ALL sessions complete before firing
3. Relational Dynamics Extension Session 1 — Attentional Filter

---

## Files — Current State

| File | Version | Action |
|------|---------|--------|
| mccf_playback.py | Day 17 | Already deployed — leave |
| mccf_api.py | Day 17 | Already deployed — leave |
| mccf_x3d_loader.html | Day 17b | Deploy this to static/ |

---

## Architecture Invariants (Never Change)
constitutional_cv (phi) — written ONLY by arc/record
expressive_cv (eps)     — written ONLY by couplers
mccf_couplers.py        — owns all coupler math
field_tick()            — compute ALL deltas then apply ALL
observed_cv             — phi + eps clamped [0,1]

## Persistent Technical Rules
SAI: avatarNode.translation = new X3D.SFVec3f(x, y, z)
/voice/speak -> SSE stream not JSON
Files: HTML -> static/, Python -> repo root
ROUTEs MUST be last in X3D scene
GitHub branch is master not main
All Timers/Dwells: enabled="false" in X3D
isActive=FALSE is arrival signal NOT cycleTime
Timer_1 started by pbReleaseDwell(seg=0) via startAgent
Do NOT call speechSynthesis.cancel()
Poll IIFE only created when cbWired=false
Ollama called via urllib.request
pbReset and pbStop send Content-Type:application/json body:'{}' (415 fix)
_pbStepInFlight is dict {sessionId: bool}
_pbLastSpoken/_pbLastStepKey/_pbSpeakToken are dicts keyed by cultivar safe name
Zone commands serialised via _zoneCommandQueue
pbSpeakQALines(qaLines, onComplete, cultivarKey) — cultivarKey required
