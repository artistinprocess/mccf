# MCCF Session Seed — V3 "The New York Rocket" — May 2026 (End of Day 4)

## State
All Day 3 fixes verified working or deployed.
Day 4 fixes: voice matching, scene load, color picker, waypoint edit, cylinder export.
Position/animation architecture undergoing redesign — see Known Issues.

## Repo
https://github.com/artistinprocess/mccf

---

## CRITICAL DEPLOY NOTE
All fixes exist only in local static/ and repo root — NOT pushed to GitHub yet.
At start of next session: confirm deployed files match session outputs before debugging.
Symptom of stale deploy: wrong voices, avatars at origin, boxes instead of cylinders.

---

## TTS Audio
Windows 11 system audio keeps resetting output device from 48kHz back to 44kHz.
Workaround: manually reset audio device to 48kHz before testing TTS.
Firefox exposes 5 voices: Microsoft David, Mark, Zira (all variants).
Edge has richer voice library — switch to Edge for production TTS testing.
Voice matching now uses base-name normalization:
  "Microsoft Zira - English (United States)" and "Microsoft Zira Desktop" → "microsoft zira"

---

## Completed This Session (Day 4)

### Voice Switching — VERIFIED WORKING
- Root cause: `_buildSceneVoiceMap` was parsing `_loadedSceneXml` (X3D file) which
  has no `<EmotionalArc>` elements. Voice map always built empty, fell to rotation.
- Fix: arc XML now carries `scene="garden_002"` attribute on root `<EmotionalArc>`.
  On arc select, loader fetches `/scene/load/scene` for that scene, reconstructs
  minimal `<EmotionalArc>` XML fragment from `placedAgents`, stores as `_loadedSceneDefXml`.
  `_buildSceneVoiceMap` and `resetToStartPosition` use `_loadedSceneDefXml` first.
- Voice base-name normalization added (4th matching pass).
- Files: `mccf_scene_composer.html`, `mccf_api.py`, `mccf_playback.py`, `mccf_x3d_loader.html`

### Scene Load — VERIFIED WORKING
- Load Scene UI moved from Export tab to Scene tab (correct location).
- Loading a scene populates Scene Name field from filename (strips `_scene.xml`).
- After load, switches to Waypoints tab automatically.
- Export tab is now export-only.
- Files: `mccf_scene_composer.html`

### Color Picker — VERIFIED WORKING
- `<input type="color">` added to agent detail panel (inline with agent name).
- Updates `agents`, `placedAgents`, `colorMap` immediately on change.
- Redraws canvas. Color carries through to X3D export via `hexToX3D`.
- Files: `mccf_scene_composer.html`

### Waypoint Edit Button — CODE COMPLETE, NEEDS VERIFICATION
- Edit button added to waypoint detail panel alongside Delete.
- Loads existing `qaLines`, name, label, zone, dwell into form.
- Sets `pendingPos` to existing position — no map click required to save.
- Confirm button relabels to "Save Changes", resets to "Place on Map" after save.
- Files: `mccf_scene_composer.html`

### Cylinder Zone Export — VERIFIED WORKING
- X3D export now uses `<Cylinder height="0.5" radius="r"/>` using declared zone radius.
- Billboard label raised to `r*0.5 + 1.2` to clear cylinder top at any radius.
- Canvas draw icon also updated.
- Files: `mccf_scene_composer.html`

### addColorStop Crash Fix — VERIFIED WORKING
- `drawZone` fallback color `'#888'` (3-digit, invalid for canvas gradient) → `'#888888'`.
- Files: `mccf_scene_composer.html`

### Zone Boxes in X3D — Still present in some scenes
- Zone markers in X3D still showing as boxes in some exported scenes.
- Root cause: old scene files exported before cylinder fix.
- Fix: re-export scene from composer to get cylinder geometry.

---

## Avatar Position Architecture — REDESIGN IN PROGRESS (HIGH PRIORITY)

### Current State
The X3D scene export already writes:
```xml
<PositionInterpolator DEF="Path_path_cindy" key="0.0 0.5 1.0" keyValue="x1 0 z1 x2 0 z2 x3 0 z3"/>
<TimeSensor DEF="Timer_path_cindy" cycleInterval="12.0" loop="false" enabled="false"/>
<ROUTE fromNode="Timer_path_cindy" fromField="fraction_changed" toNode="Path_path_cindy" toField="set_fraction"/>
<ROUTE fromNode="Path_path_cindy" fromField="value_changed" toNode="Avatar_Cindy" toField="translation"/>
```
`cycleInterval` is now sum of waypoint dwell times (fixed in Day 4).
`loop="false"` (fixed in Day 4).

### Problem
Single interpolator runs all waypoints as one continuous animation — never stops at
intermediate waypoints. Avatar reaches waypoint 2 and continues immediately to 3.
JS lerp was fighting the X3D ROUTE, causing position drift and waypoint skipping.

### Correct X3D Architecture (Next Session)
Per-segment interpolation: one `PositionInterpolator` + one `TimeSensor` per transition.
Chain via ROUTE: `Timer_seg1.cycleTime → Timer_seg2.startTime` (eventOut → eventIn).
Avatar stops at each waypoint for dwell time, then next timer fires.

Example for 3 waypoints (2 segments):
```xml
<!-- Segment 1: WP1 → WP2 -->
<PositionInterpolator DEF="Interp_Cindy_1" key="0 1" keyValue="x1 0 z1 x2 0 z2"/>
<TimeSensor DEF="Timer_Cindy_1" cycleInterval="4.0" loop="false" enabled="false"/>
<ROUTE fromNode="Timer_Cindy_1" fromField="fraction_changed" toNode="Interp_Cindy_1" toField="set_fraction"/>
<ROUTE fromNode="Interp_Cindy_1" fromField="value_changed" toNode="Avatar_Cindy" toField="translation"/>

<!-- Dwell at WP2 then start segment 2 — use Script or TimeSensor chain -->
<TimeSensor DEF="Dwell_Cindy_1" cycleInterval="2.0" loop="false" enabled="false"/>
<ROUTE fromNode="Timer_Cindy_1" fromField="cycleTime" toNode="Dwell_Cindy_1" toField="startTime"/>

<!-- Segment 2: WP2 → WP3 -->
<PositionInterpolator DEF="Interp_Cindy_2" key="0 1" keyValue="x2 0 z2 x3 0 z3"/>
<TimeSensor DEF="Timer_Cindy_2" cycleInterval="4.0" loop="false" enabled="false"/>
<ROUTE fromNode="Dwell_Cindy_1" fromField="cycleTime" toNode="Timer_Cindy_2" toField="startTime"/>
<ROUTE fromNode="Timer_Cindy_2" fromField="fraction_changed" toNode="Interp_Cindy_2" toField="set_fraction"/>
<ROUTE fromNode="Interp_Cindy_2" fromField="value_changed" toNode="Avatar_Cindy" toField="translation"/>
```

Loader activates by setting `Timer_Cindy_1.startTime = browser.currentTime` via SAI.
All subsequent timers fire automatically via ROUTEs. No polling for position.
TTS/dialogue polling continues independently — decoupled from position.

### Trigger Architecture (Single eventOut → Multiple Actions)
X3D ROUTE is n:m — one `cycleTime` eventOut can trigger:
- Next movement timer
- Dialogue/TTS event (via Script)
- Gesture interpolator
- Light change
- Sound trigger

This is the clean design for full scene choreography.

### Composer Export Changes Required
`buildInterp(path)` needs to generate per-segment nodes instead of single interpolator.
Each waypoint pair becomes one `Interp_`, one `Timer_`, one `Dwell_` node.
Dwell duration comes from `wp.dwell` on the destination waypoint.
Total nodes per N-waypoint path: (N-1) × 3 nodes + (N-1) × 4 ROUTEs.

---

## Known Issues — Priority Order

### 1. Avatar Position — Per-Segment X3D Architecture (HIGH — BLOCKS MULTI-WAYPOINT)
See Avatar Position Architecture section above.
Current single-interpolator approach visits all waypoints without stopping.
Next session: redesign `buildInterp` in composer, update loader SAI activation.

### 2. Waypoint Edit — Needs Verification (MEDIUM)
Edit button added but not fully tested against a loaded scene.
Verify: click placed waypoint → Edit button → form populates with existing Q/R/S lines
→ Save Changes → waypoint updates in place.

### 3. Voices Silent When X3D Timer Active (MEDIUM — Related to #1)
`pbActivateX3DTimers` marks all avatars as X3D-driven which causes `pbPushPosition`
to return early — this also short-circuits TTS trigger path.
Fix: decouple position skip from TTS. TTS should fire from `_pbLastStepKey` change
regardless of whether position is X3D-driven or JS-lerped.

### 4. Zone Markers Still Boxes in X3D (LOW — Re-export fixes it)
Old scene files show boxes. Re-export from composer to get cylinders.
Future: add zone label hide toggle (requested Day 4).

### 5. Viewpoints VP1-VP7 Not Found (LOW)
Loader buttons hardcoded VP1-VP7, composer uses VP_{zoneId}.
Fix: make viewpoint buttons dynamic from scene XML zone list.

---

## Architectural Direction — Next Phase

### X3D Native Animation (Agreed Day 4)
Stop reimplementing X3D features in JS. Use X3D as designed:
- Per-segment interpolators + timer chains for movement
- ROUTE eventOut for choreography triggers (lights, sound, gestures)
- MCCFMaster Script receives field state, drives gesture interpolators
- ProximitySensor zone detection already wired — extend to trigger field events

### Follower Pattern (Research Item)
Multiple avatars following same path at offset timing.
X3D: single `PositionInterpolator`, multiple ROUTEs to multiple `Transform` nodes,
offset `startTime` per avatar. Review X3D 4.0 follower components before implementing.

### Gesture System (Future — Post Big Demo)
`cvToGesture(cv)` mapping: field state E/B/P/S → HAnim interpolator DEF names.
Low B + Low E → slumped idle. High E → active gestures.
MCCFMaster Script already has arousal outputs per agent — extend to gesture selectors.
ExternProto for gesture library — X_ITE developer confirms working in current build.

### LLM as Agent (Future)
When agent has `actor="ollama"` (or other backend), `Question` waypoint sends text
to LLM, streams response, speaks via TTS, records CV back to field engine.
`Response` and `Statement` always scripted regardless of backend.
Prerequisite: step-fire-once reliability confirmed (Day 3 `_pbLastStepKey` fix).
Paste Q/A module files at start of that session.

### ElevenLabs TTS (Deferred — Big Demo)
Each Statement/Response = one EL streaming call.
Voice assignment: agent name → EL voice ID in scene XML `<Agent>` element.
voice_settings driven by E/B/P/S vectors per waypoint.

---

## Key Constraints — Never Change
- Avatar names late-bound: safeId = name.replace(/[^A-Za-z0-9_]/g,'_')
- SAI: avatarNode.translation = new X3D.SFVec3f(x, y, z)
- /voice/speak → SSE stream, not JSON
- Files: HTML → static/, Python → repo root
- Constitutional navigator (mccf_constitutional.html) is V2 — do not touch
- applyArcCV is confirmed working SAI path — BroadcastChannel mccf_arc
- TTS: Browser Web Speech API only. ElevenLabs deferred to Big Demo.
- Edge has richer voice library than Firefox — use Edge for TTS testing
- sceneConfig default: width=40, depth=40 meters
- Arc XML root carries `scene="scene_name"` attribute (added Day 4)

---

## Coordinate System — Confirmed
Composer canvas uses world meters = X3D scene units. SCALE/OX/OZ are display-only.
Arc XML pos_x/pos_z are world meters, directly used in X3D SAI translation.
Mismatch = stale scene file, not a transform bug.

---

## Dialogue XML — Three-Way Taxonomy
| Type      | LLM Call | TTS | XML Element              | Use                          |
|-----------|----------|-----|--------------------------|------------------------------|
| Question  | Yes*     | Yes | `<Question speaker="">`  | Directed — LLM responds      |
| Response  | No       | Yes | `<Response speaker="">`  | Scripted reply               |
| Statement | No       | Yes | `<Statement speaker="">` | Monologue / internal / prayer |

*LLM call not yet wired — currently speaks authored text only.
Multiple Q/R/S per waypoint supported. Speaker attribute required for voice assignment.

---

## Operation Order for Testing
1. `ollama serve` + `py mccf_api.py`
2. Hard-reload composer and loader after deploy (Ctrl+Shift+R)
3. Scene tab → Load existing scene OR set name + Apply Grid
4. Agents → Refresh → place agents with voice (use Edge for full voice list)
5. Waypoints → place with Q/R/S lines, speaker from dropdown
6. Paths → create path
7. Export → Send to Launcher
8. Open loader in separate tab, wait for scene load
9. Loader: select arc → voice checkbox ON → Play
10. Check console for `pbActivateX3DTimers: started Timer_*`

## Reference Scene
garden_002_scene.xml — 3 agents (Cindy/Steward/Witness), 3 waypoints, 80×80m
arc_path_cindy_2026-05-06T003643.xml — 3 waypoints, scene="garden_002" confirmed

## Working File Manifest
| File                        | Location   | Status                              |
|-----------------------------|------------|-------------------------------------|
| mccf_scene_composer.html    | static/    | Day 4 fixes deployed                |
| mccf_x3d_loader.html        | static/    | Day 4 fixes deployed                |
| mccf_api.py                 | repo root  | scene_name in arc export            |
| mccf_playback.py            | repo root  | scene_name in list_files            |
| mccf_constitutional.html    | static/    | V2 — do not touch                   |
| garden_002_scene.xml        | scenes/    | Reference: 3-agent 3-waypoint scene |
| arc_path_cindy_*.xml        | exports/   | Reference arc with scene attribute  |
