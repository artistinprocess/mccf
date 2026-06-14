# MCCF Session Handoff — Day 23
*Generated end-of-session Day 22 — 2026-05-21*

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
```

---

## Current Scene: garden_001

### Agents

| Agent | Status | waypointOrder | Waypoints | Segments | Notes |
|---|---|---|---|---|---|
| Cindy | Active, path recorded | 1 | 3 | 2 | HANIM — cindy_hanim.x3d |
| The Gardener | Active, path recorded | 2 | 2 | 1 | Placeholder avatar |
| The Steward | Placed, no path | — | — | — | Stationary cultivar, does NOT block allDone |
| **Anna** | **NOT YET AUTHORED** | TBD | TBD | TBD | Principal agent — Day 23 priority |

### Scene State — confirmed working Day 22
- Full scene plays: Cindy (order 1) completes, The Gardener (order 2) fires, allDone triggers Chorus
- Chorus: **working** — transcript-direct to Ollama, overlay displays, auto-dismiss 18s
- Emotion display: working — ϕ/ϵ bars update per agent per waypoint
- Gardener avatar appears correctly on zone entry
- Reset+Replay: **working** — deadlock fixed in mccf_playback.py
- Edit Avatar in Scene Composer: dropdown populated from /avatar/list, pre-selects Character Creator value

---

## Day 22 Bugs Fixed — All Confirmed Working

### Bug 1 — Chorus "file not found" ✅
**Root cause:** Chorus was reading an arc export file to build the transcript. File lookup was unreliable (basename mismatch, dedup timing).
**Fix:** Eliminated file lookup entirely. Loader accumulates `_chorusTranscript` live during playback — every qaLine from every agent at every new step. At `allDone`, serializes to plain text and POSTs `{transcript, cv, scene_name}` directly to `/chorus/fire`. Server calls `fire_chorus_from_transcript()` — no file I/O.
**Files:** `mccf_x3d_loader.html`, `mccf_chorus.py`

### Bug 2 — Reset+Replay deadlock ✅
**Root cause:** `PlaybackManager.reset()` (and `stop()`, `step()`) acquired `self._lock` then called `self.state()` which tried to re-acquire the same non-reentrant `threading.Lock()` — deadlock on second run. Server restart required to clear.
**Fix:** Added `_state_unlocked()` helper — same logic as `state()` but assumes lock already held. `stop()`, `step()`, `reset()` call `_state_unlocked()` inside their lock blocks.
**File:** `mccf_playback.py`

### Bug 3 — SAI test moves Gardener to grid edge ✅
**Root cause:** Test wrote `SFVec3f(startX, 0, 0)` — Z collapsed to zero. Restore used live `startTrans` reference already mutated.
**Fix:** Capture X, Y, Z separately; restore with `new X3D.SFVec3f(startX, startY, startZ)`.
**File:** `mccf_x3d_loader.html`

### Bug 4 — Stale dwell timeouts causing post-reset server lock contention ✅
**Root cause:** `pbReleaseDwell` anonymous `setTimeout` callbacks survived reset, fired during `start/all`, posted `/arc/playback/step` while lock was held.
**Fix:** Generation guard on both `setTimeout` callbacks in `pbReleaseDwell`. `pbReset()` increments `_pbCbGeneration` immediately, invalidating all in-flight callbacks.
**File:** `mccf_x3d_loader.html`

### Bug 5 — Edit Avatar text input → dropdown ✅
**Fix:** `<select id="ad-hanim-select">` populated from `GET /avatar/list`. Pre-selects agent's current `hanim_src` from Character Creator. `loadAll()` chains `/cultivars/xml` on startup so `hanim_src` is always populated before placement.
**File:** `mccf_scene_composer.html`

---

## Known Non-Issues — Do Not Fix

- `VP_Overview not found` on load — cosmetic, X_ITE
- `ambient/sync 500` — ModuleNotFoundError: No module named 'mccf_lighting'
- `lighting/scalars 404`
- AudioContext gesture warning from X_ITE
- MS audio 48khz reset
- Jin.png local file path error — cosmetic, image asset not on server

---

## Day 23 Priorities (in order)

### 1. HAnim Emotional Mapping Design — BEFORE authoring Anna
New HAnim avatar files have been downloaded. Before authoring any new agent paths, the emotional-to-motion mapping must be designed. Authoring Anna first would record placeholder movement that would need to be redone.

**The design question:** how do the four MCCF channels drive HAnim joint behavior at runtime via SAI?

**Channel semantics to behavior:**
- **E** (emotion/arousal) → gesture expressiveness, facial animation amplitude
- **B** (behavioral activation) → movement energy, gait cycle selection, gesture frequency
- **P** (power/agency) → postural dominance, spine erect vs. collapsed, head orientation
- **S** (social orientation) → proxemic facing toward/away from other agents

**Approach options to decide between:**
- **Keyframed pose clips selected by channel thresholds** — more controllable for theater, author selects poses per emotional state band
- **Continuous procedural joint driving** — more responsive to live field, joints interpolate directly from CV values via SAI writes

**Current state:** hothouse polling already writes to `BodyMat_`, `GazeMat_`, `RingMat_` material nodes as a placeholder. HAnim replaces or augments this with actual joint motion.

**First step:** inspect the new avatar files — check joint hierarchy, LOA level, and what joints are exposed — before committing to a mapping design. LOA level constrains what's available.

### 2. Author Anna's Path (after HAnim mapping decided)
Anna is the **principal agent** — the Librarian. She delivers the opening monologue.
- Place Anna on the map in Scene Composer
- Author her path with waypoints ending at the position from which she delivers *"Blessed be."*
- `waypointOrder` TBD relative to Cindy (1) and The Gardener (2)
  — likely order=1 if she fires simultaneously with Cindy, or order=0 if she precedes everyone
- Her final waypoint dwell must be long enough for the full monologue before `allDone` resolves
- Arc voice data for her waypoints should carry *"They are our incense."* then *"Blessed be."*

### 3. Scene Rename (after Anna authored and tested)
`garden_001` → `hypoborea_001`
- Affects: `.x3d` filename, `_scene.xml`, `_zones.xml`, arc filenames, scene name field
- Do this after Anna is fully authored and tested — not before

### 3. The Steward
Stationary cultivar. Path authoring deferred until scripted.
Confirmed safe — does not affect `allDone` count.

---

## Playback Flow (current, confirmed working)

```
User clicks "Play All"
  → _pbPlayAllInFlight guard — blocks concurrent calls
  → pollingActive = false (pause polls during start/all)
  → POST /arc/playback/start/all
  → Sessions assigned, _pbCbGeneration++
  → X3D timers activated (Arrival_ callbacks wired)
  → Groups fired in waypointOrder sequence
  → Each group: pbUpdateDisplay → TTS → pbReleaseDwell → startFromLoader → Timer_1
  → isActive=FALSE arrivals → advanceSeg → next timer
  → allDone=true → pbUpdateDisplayFinal
    → _chorusTranscript serialized
    → POST /chorus/fire {transcript, cv, scene_name}
    → Ollama responds async (~26s)
    → startChorusPoll() picks up response
    → chorus-overlay displays, auto-dismiss 18s

User clicks "Reset + Replay"
  → pbReset() — _pbCbGeneration++ (invalidates stale dwell timeouts)
  → Kill_ nodes snap avatars to StartPosition
  → POST /arc/playback/reset (8s timeout)
  → pbPlayAll() fires on both success and timeout paths
  → _pbPlayAllInFlight guard prevents double-fire
```

---

## Workflow Notes

- **Author does not edit code.** Claude delivers complete replacement files.
- **Always ask before using GitHub.**
- **Branch is master** — not main. All pushes go to master.
- **Always deliver handoff as a downloadable .md file.**
- **Static files** (`mccf_scene_composer.html`, `mccf_x3d_loader.html`) live in `static/`.
- **Python files** (`mccf_api.py`, `mccf_couplers.py`, `mccf_cultivar_lambda.py`, `mccf_playback.py`, `mccf_chorus.py`) live in repo root.
- The Scene Composer and X3D Loader communicate via the Flask API at `http://localhost:5000`.
- BroadcastChannel is used for real-time avatar position sync between Composer and Loader.
- Avatars live in `static/avatars/`. Scene X3D files reference them as `../avatars/foo.x3d`.

---

## Future: MCCF as Programmed Instruction Platform

**Concept:** Adapt MCCF for interactive Skinnerian instruction with Anna as the teacher. Same engine, same agents, same emotional field — but user-driven rather than purely theatrical. Lesson stages map to zones; Anna delivers a lecture at each waypoint, poses a question, evaluates the user's response, and either advances or reworks based on the grade. The emotional field reflects her response to student performance.

**Why it matters:** Demonstrates MCCF's range beyond theater. An embodied animated teacher with emotional responsiveness, consistent rubric-based evaluation, and infinite patience for rework is a natural LLM application — and a compelling demo for adoption by others.

**What needs to be built (deferred):**
- User input field in the Loader (text or voice)
- `/lesson/evaluate` endpoint — `{question, answer, rubric}` → `{pass: bool, feedback: str}`
- Conditional advance in the playback sequencer — hold at waypoint until pass signal, not timer expiry
- Rework qaLines per waypoint — alternate dialogue for retry case

**Revisit** after the theater pipeline (Anna, scene rename, HAnim mapping) is stable.

---

*End of Day 22 handoff. Paste this file at the start of the Day 23 conversation.*
