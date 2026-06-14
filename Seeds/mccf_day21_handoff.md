# MCCF Session Handoff — Day 21
*Generated end-of-session Day 20 — 2026-05-20*

---

## Project: The New York Rocket
**MCCF** — Multi-agent X3D real-time theater engine animating a novel-in-progress.

**Pipeline:** Novel → MCCF scene → animated theater → XML-to-prompt → video generation → ElevenLabs voices → film.

**Story:** Enheduana's daughter Enredhuanna founded Hypoborea, a secret society operating for 6,000 years. Principal agent Anna (the Librarian) delivers the opening monologue ending in *"They are our incense." / "Blessed be."* — at which point the Greek Chorus fires.

**Repo:** https://github.com/artistinprocess/mccf — branch **`master`** (not main)

**Author does not edit code. Claude delivers complete files only.**

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
_pbLastArcFiles          — matched from pb-file dropdown by prefix arc_{sessionId}_
Chorus fires at scene end (allDone=true) via pbUpdateDisplayFinal → /chorus/fire
  arc_file = chorusFiles[0], arc_files = chorusFiles (all arcs passed)
API var:                 var API = 'http://localhost:5000'  (in both HTML files)
Loader URL:              API + '/static/mccf_x3d_loader.html'
```

---

## Current Scene: garden_001

### Agents

| Agent | Status | waypointOrder | Waypoints | Segments | Notes |
|---|---|---|---|---|---|
| Cindy | Active, path recorded | 1 | 3 | 2 | Fires first |
| The Gardener | Active, path recorded | 2 | 2 | 1 | Fires after Cindy arrives WP1 |
| The Steward | Placed, no path | — | — | — | Stationary cultivar, does NOT block allDone |
| **Anna** | **NOT YET AUTHORED** | TBD | TBD | TBD | Opening monologue agent — **Day 21 priority** |

### Scene State
- Chorus: confirmed working end-of-scene. Fires after `allDone=true`. Ollama llama3.2, zone=Mountain, tone=reverent. Response ~26s (acceptable).
- Replay: working after Reset+Replay fix (Day 20).
- Flask server: `threaded=True` — no lockouts.

---

## Day 20 Bugs Fixed — All Confirmed

### Bug 1 — Zone command XML missing closing quote ✅
**File:** `mccf_scene_composer.html` → `exportZoneXML()`
**Fix:** `+'"/>\\n'` (was `+'/>\\n'` — missing `"` before `/>`)
**Also patched:** existing `garden_001_zones.xml` directly.

### Bug 2 — Kill_ script resets avatar to first waypoint instead of StartPosition ✅
**File:** `mccf_scene_composer.html` → `buildInterpNodes()` → Kill_ script generation
**Fix:** `var startPos = (placedAgents[path.agent] && placedAgents[path.agent].position) || wps[0].position || [0,0,0]`
Reads agent's placed StartPosition from global `placedAgents` object with fallback.

### Bug 3 — Flask single-threaded server lockout ✅
**File:** `mccf_api.py` line 2587
**Fix:** `app.run(debug=True, port=5000, threaded=True)`

### Bug 4 — /chorus/fire never reached server ✅
**File:** `mccf_x3d_loader.html` → `_pbLastArcFiles` population in `pbPlayAll`
**Root cause:** `start/all` sessions have no `.file` field → `_pbLastArcFiles = []` → `chorusFiles` empty → guard never passed.
**Fix:** Match session IDs to arc filenames in pb-file dropdown by prefix `arc_{sid}_`. Fallback: use all dropdown values if no match.

### Bug 5 — Reset calls single-arc playback instead of Play All ✅
**File:** `mccf_x3d_loader.html` → `pbReset()`
**Fix:** `pbReset()` now calls `pbPlayAll()` automatically after clearing JS state, both on server reset success and on timeout/failure. Button relabelled **"Reset + Replay"**.

### Feature — Open X3D Loader button in Scene Composer ✅
**File:** `mccf_scene_composer.html`
**Added:**
- `openLoader()` function: `window.open(API + '/static/mccf_x3d_loader.html', '_blank')`
- Persistent **purple** "Open X3D Loader" button in the Export panel (below Send to Launcher)
- Dynamic "Open X3D Loader" button appears in Record Scene Arc panel after arc save completes ("Launcher updated")

---

## Files Delivered Day 20

All four of these should be deployed before Day 21 testing:

| File | Destination | Changes |
|---|---|---|
| `mccf_scene_composer.html` | `static/` | Kill_ StartPosition fix + zone command quote fix + Open Loader button (two locations) |
| `mccf_x3d_loader.html` | `static/` | `_pbLastArcFiles` prefix fix + chorus/fire logging + Reset+Replay auto-pbPlayAll |
| `mccf_api.py` | repo root | `threaded=True` on line ~2587 |
| `garden_001_zones.xml` | `zones/` | OnExit broken quote fixed |

---

## Known Non-Issues — Do Not Fix

- `VP_Overview not found` on load — cosmetic, X_ITE
- `ambient/sync 500` — ModuleNotFoundError: No module named 'mccf_lighting'
- `lighting/scalars 404`
- AudioContext gesture warning from X_ITE
- MS audio 48khz reset

---

## Day 21 Priorities (in order)

### 1. Test Report
User will report on:
- Reset+Replay button — does it auto-fire pbPlayAll cleanly?
- Open Loader button — does it open in new tab from Composer?
- Chorus fire — still working after today's changes?

### 2. Author Anna's Path
Anna is the **principal agent** — the Librarian. She delivers the opening monologue.
- Place Anna on the map in Scene Composer
- Author her path with waypoints ending at the position from which she delivers *"Blessed be."*
- Record her arc
- Her `waypointOrder` needs to be determined relative to Cindy (1) and The Gardener (2) — likely order=1 as well if she fires simultaneously, or order=0 if she precedes everyone

**Anna's monologue endpoint:** the Chorus fires at *"Blessed be."* — this is the `allDone` trigger moment. Her final waypoint dwell should be long enough for the full monologue before `allDone` resolves.

**Story note:** Anna says *"They are our incense."* then *"Blessed be."* — the Chorus responds to this. The arc voice data for her waypoints should carry these lines.

### 3. Scene Rename (when ready)
`garden_001` → `hypoborea_001`
- Affects: `.x3d` filename, `_scene.xml`, `_zones.xml`, arc filenames, scene name field in Composer
- Do this after Anna is fully authored and tested — not before

### 4. Chorus Display Timing
Currently ~26s delay (Ollama llama3.2). Monitor as scene complexity grows. No action needed unless it starts blocking.

### 5. The Steward
Stationary cultivar. Path authoring deferred until scripted. Confirmed safe — does not affect `allDone` count.

---

## Playback Flow (current, after Day 20 fixes)

```
User clicks "Reset + Replay"
  → pbReset() called
  → pbStopPolling(), stopChorusPoll(), dismissChorus()
  → _pbResetViaKillScript() fires Kill_ nodes → avatars snap to StartPosition
  → All JS state cleared (_pbArcComplete, _pbLastArcFiles, etc.)
  → POST /arc/playback/reset (4s timeout)
  → pbPlayAll() fires automatically (both success and timeout paths)
    → POST /arc/playback/start/all
    → Sessions assigned, _pbLastArcFiles matched by prefix arc_{sessionId}_
    → X3D timers activated
    → WP1 dwell fires startFromLoader (SFTime)
    → isActive=FALSE arrivals trigger advanceSeg (SFInt32)
    → allDone=true → pbUpdateDisplayFinal → POST /chorus/fire
    → Chorus response renders (~26s)
```

---

## Workflow Notes

- **Author does not edit code.** Claude delivers complete replacement files.
- **Branch is master** — not main. All pushes go to master.
- **Static files** (`mccf_scene_composer.html`, `mccf_x3d_loader.html`) live in `static/`.
- **Python files** (`mccf_api.py`, `mccf_couplers.py`) live in repo root.
- The Scene Composer and X3D Loader communicate via the Flask API at `http://localhost:5000`.
- BroadcastChannel is used for real-time avatar position sync between Composer and Loader.

---

*End of Day 20 handoff. Paste this file at the start of the Day 21 conversation.*
