# MCCF Day 20 Session Handoff

## Project: The New York Rocket / MCCF
Multi-agent X3D real-time theater engine.
Repo: https://github.com/artistinprocess/mccf
Author does not edit code — Claude delivers complete files only.
Branch is `master` not `main`.

---

## The Story: The Garden of the Goddess

MCCF exists to animate a novel in progress (~200 pages).

**Pipeline:** Novel → MCCF scene → animated theater → XML-to-prompt → video generation → ElevenLabs voices + music → film.

**Premise:** Enheduana's daughter Enredhuanna founded a secret society when men's wars desecrated the temples. Temple servants of the old sex religions fled to a hidden island: **Hypoborea** (hypo — hidden beneath the north wind, not above it). Operating for 6,000 years as collectors of human art and courtesans who do good deeds and remove bad men.

**Anna (Enredhuanna):** Principal agent. Tall, brown-skinned Mesopotamian, flowing black hair, dark eyes that look old around the edges. Otherwise appears a young woman — vestal raised in a temple. Now goes by Anna, Librarian of the Garden. Has the scrolls of Hypatia. Was probably there when Alexandria burned.

Delivers the opening monologue to assembled ladies at the garden spring. The line that defines the organization: *"They are our incense."* Scene ends with *"Blessed be."* — Greek Chorus fires here.

**Hypoborea:** Hidden island. Garden spring where they bathe simply. Library of Inanna. Purification pool. Instruction spaces. Ancient stone, clear water, morning light. No ornament.

**The doctrine:** They cannot retire from the world of men. They must tame them. They preserve beauty because mortals need it and cannot protect it themselves. Civilizations are built on the ruins of the last ones. The organization endures through all of it. *"We rise on the smoke of their sweet impermanence."*

---

## Current Status — End of Day 19

### Working
- Scene Composer V4 — waypointOrder required, badge display, full export pipeline
- X3D Loader — group sequencer working, replay without server restart working
- Full run confirmed: Cindy (order=1) completes before The Gardener (order=2) fires
- TTS working — Microsoft Ava and David voices assigned per speaker
- Movement working — SAI confirmed, avatar translation working
- Coupler ticks firing — 7 ticks, PHASE TRANSITION at ts=4,5,6,7 mean_sim=0.9983–0.9997
- φ seeding working — arc/record called at each waypoint with correct E/B/P/S values
- Chorus fires correctly from pbUpdateDisplayFinal — Ollama not returning in poll window (next session)
- Reset button works — JS state clears, avatars return to start positions

### Current Workflow (until threaded=True added to server)
1. Restart Flask server
2. Open loader, select garden_001.x3d
3. Hit Play All — runs cleanly first time
4. Reset button works for JS/avatar state
5. For replay: restart server, reload scene, Play All again

### Next Session Priorities
1. **`threaded=True`** in `mccf.py` — one line, fixes all Flask single-thread contention, enables replay without restart
2. **Chorus debug** — `/chorus/state` returning empty; check if Ollama is responding to `/chorus/fire` and whether Mountain zone chorus config is wired correctly on server side
3. **Anna** — build her path, record her arc with opening monologue waypoints
4. **Scene rename** — garden_001 → hypoborea_001 or similar when ready

---

## Architecture Invariants (Permanent)

### waypointOrder (SFInt32, initializeOnly) — REQUIRED on every path
- Same number = simultaneous start
- Ascending number = sequential; next group waits for ALL `_pbArcComplete` in current group
- Missing or invalid = HARD STOP with named error. Scene will not run.
- Validator runs in `pbPlayAll` before any fetch: `_validateAndBuildOrderGroups()`
- `_pbWaitForGroup(group)` — 200ms poll on `_pbArcComplete` dict, 10-minute timeout
- Source of truth: `_scene.xml` `<Path waypointOrder="N">` — not X3D SAI
- X3D Arrival_ script also carries waypointOrder as initializeOnly field (documentation/redundancy)

### Flask Threading
Server runs single-threaded by default. Four pollers at 750ms keep request queue full.
`pbPlayAll` pauses polling before `start/all` and resumes after sessions confirmed.
**Permanent fix:** add `threaded=True` to `app.run()` in `mccf.py`.

### Constitutional Invariants
```
constitutional_cv (phi) — written ONLY by arc/record
expressive_cv (eps)     — written ONLY by couplers
mccf_couplers.py        — owns all coupler math
field_tick()            — compute ALL deltas then apply ALL
observed_cv             — phi + eps clamped [0,1]
```

### Persistent Technical Rules
```
SAI: avatarNode.translation = new X3D.SFVec3f(x, y, z)
/voice/speak -> SSE stream not JSON
Files: HTML -> static/, Python -> repo root
ROUTEs MUST be last in X3D scene
GitHub branch is master not main
All Timers/Dwells: enabled="false" in X3D
isActive=FALSE is arrival signal NOT cycleTime
startFromLoader (SFTime) fired by pbReleaseDwell after WP1 dwell
  value: performance.now()/1000 + 0.1
advanceSeg (SFInt32) fired by _pbAdvanceSeg after each dwell expires
Arrival scripts self-contained — no MCCFMaster for movement
_pbSpeechLock / _pbSpeechQueue — global speech serializer
_pbCultivarSessionMap — {safeName: session_id} set by pbPlayAll
_pbExpectedAgents — count for allDone detection
_pbLastArcFiles — for Chorus firing
pbReset and pbStop send Content-Type:application/json body:'{}'
_pbStepInFlight is dict {sessionId: bool}
_pbLastSpoken/_pbLastStepKey/_pbSpeakToken — dicts keyed by cultivar safe name
Zone commands serialised via _zoneCommandQueue
pbSpeakQALines(qaLines, onComplete, cultivarKey) — cultivarKey required
_pbArcComplete is dict {safeName: bool} — NOT a global bool
pollingActive paused during pbPlayAll start/all fetch — resumed after sessions confirmed
```

### Known Non-Issues (Do Not Fix)
- VP_Overview not found on load
- ambient/sync 500 Internal Server Error
- lighting/scalars 404 Not Found
- AudioContext gesture warning from X_ITE
- MS audio 48khz reset

---

## File State
- `mccf_scene_composer.html` — V4, syntax clean, waypointOrder complete
- `mccf_x3d_loader.html` — Day 19, group sequencer + polling pause complete
- Scene: `garden_001` — Cindy (2 waypoints, order=1), The Gardener (1 waypoint, order=2)
- Arc files: `arc_path_Cindy_2026-05-20T020337.xml`, `arc_path_Gardener_2026-05-20T020352.xml`

---

*The garden moves and speaks. Anna is next.*
