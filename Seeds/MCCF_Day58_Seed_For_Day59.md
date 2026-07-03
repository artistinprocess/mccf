# MCCF Day 58 Session Handoff → Day 59

## Status: Camera EventCues System — Built, Tested, Partially Working

**GitHub baseline:** Commit `0e3ae73` (Day 57). Day 58 files not yet committed.
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## Files Changed Day 58

| File | Key Changes |
|------|-------------|
| `static/mccf_scene_composer.html` | `NavigationInfo` gets `transitionType='"TELEPORT"'` in both `exportX3D()` and `buildX3DString()`. `VP_Overview` angle changed from steep overhead to low three-quarter establishing shot (`height × 0.45`, `pullback × 1.1`, pitch `-0.38`). |
| `static/mccf_events_editor_prototype_2.html` | Full camera shot designer in inspector (shot type grouped dropdown, subject, transition cut/fly, framing sliders, delay). `applyShotPreset()` auto-fills from spec presets. `drawStage()` draws FOV cone for selected camera cue. `exportCues()` serializes all new camera fields. Font sizes increased throughout for readability. |

---

## Confirmed Working Day 58

- TELEPORT transition: camera cuts instantly to viewpoint — confirmed in Loader
- VP_Overview: low three-quarter establishing angle — confirmed visually
- Events Editor camera inspector: shot type dropdown, subject, framing sliders, delay all render and save correctly
- FOV cone on stage canvas: draws correctly, updates on cue select, blue=cut amber=fly
- `applyShotPreset()`: changing shot type auto-fills framing sliders from spec table
- Font sizes readable at normal viewing distance
- First camera cue (`orbit` → `w2 arrive`) fired correctly in Loader playback
- Full scene playback confirmed: TTS, zone audio, arc record, Chorus all working

---

## Bugs Found Day 58

### BUG 1 — WP trigger candidate list fires all WP names at every arrival (CRITICAL)
**Symptom:** Both camera cues fired at WP2 arrival. Console showed:
```
[EventCues] firing candidates: ["Waypt2 arrive","w1 arrive","w2 arrive","w3 arrive"]
[EventCues] firing: camera "orbit" trigger: w2 arrive     ← correct
[EventCues] firing: camera "wide"  trigger: w3 arrive     ← wrong, fired at WP2
```
**Root cause:** `_resolveWpTriggerNames()` in Loader returns ALL XML WP names as candidates at every arrival, not just the aliases for the current WP. The Day 57 fix was too broad.
**Fix required:** Candidate list should be: `[serverWpId, xmlNameForCurrentWp]` only — current WP aliases, not all waypoints.
**File:** `static/mccf_x3d_loader.html` — `_resolveWpTriggerNames()` and `fireEventCuesForTrigger()`.

---

## Day 59 Primary Tasks (in order)

### Task 1 — Fix WP trigger candidate list (BUG 1 above)
`_resolveWpTriggerNames(stepWp)` should return only:
- The server WP id (e.g. `"Waypt2"`)
- The canonical XML name for that WP position (e.g. `"w2"`) — looked up by position/index in `_wpXmlNamesList`

Not all XML names. The index mapping is: server waypoint step index (0-based) → `_wpXmlNamesList[index]`.

### Task 2 — Loader camera runtime resolution (Spec v1.0)
Implement the camera cue execution path in the Loader per the Camera System Specification.

**New node needed in Composer X3D export:**
```xml
<Viewpoint DEF="VP_Free" description="Free Camera"
  position="0 5 10" orientation="1 0 0 -0.4" jump="true"/>
```
Add to both `exportX3D()` and `buildX3DString()` in `mccf_scene_composer.html`.

**Loader changes — `_executeCameraEventCue(cue)` function:**

Step 1 — Identify shot category:
- `shot` in `{agent_eye, agent_side}` → agent-attached path: bind `VP_{subject}_{Eye|Side}`
- `shot` in `{dolly_in, dolly_out, pan, tilt, orbit, crane_up, track}` → move path (Phase 2)
- Otherwise → static computed path

Step 2 — Static computed path:
```javascript
function _computeCamPosition(subjectPos, distance, height, hAngleDeg) {
  var hRad = hAngleDeg * Math.PI / 180;
  return [
    subjectPos[0] + distance * Math.sin(hRad),
    subjectPos[1] + height,
    subjectPos[2] + distance * Math.cos(hRad)
  ];
}
function _lookAtOrientation(camPos, targetPos, vAngleDeg) {
  // Returns X3D axis-angle [ax, ay, az, angle]
  var dx = targetPos[0] - camPos[0];
  var dy = targetPos[1] - camPos[1] + Math.tan(vAngleDeg * Math.PI / 180) * 1;
  var dz = targetPos[2] - camPos[2];
  var len = Math.sqrt(dx*dx + dz*dz);
  var yaw   = Math.atan2(dx, dz);
  var pitch = -Math.atan2(dy, len);
  // Compose yaw then pitch as axis-angle for X3D
  // Simple approach: set position, derive orientation from look vector
}
```

Step 3 — Set VP_Free and bind:
```javascript
var vpFree = _scene.getNamedNode('VP_Free');
vpFree.getField('position').setValue(new SFVec3f(camPos[0], camPos[1], camPos[2]));
vpFree.getField('orientation').setValue(computedOrientation);
vpFree.set_bind = true;
```

Step 4 — Agent world positions:
The Loader already tracks agent positions via `_agentPositions[agentName] = [x, y, z]` updated each segment arrival. Use this as `subjectPos`.

**Move shots (Phase 2 — after static works):**
Use `PositionInterpolator` + `OrientationInterpolator` + `TimeSensor` driving VP_Free.
Start = current VP_Free position, End = computed from `distanceEnd/hAngleEnd/vAngleEnd`.
`TimeSensor.cycleInterval = cue.flyDuration`.
Cancel on Stop/Reset.

### Task 3 — Day 57 backlog: Remove duplicate diagnostic log
In `mccf_x3d_loader.html` ~line 2970, remove:
```javascript
console.log('[EventCues] WP arrival trigger (pbStep): "' + _wpArrId + ' arrive"', '— cues:', _eventCues.length);
```

### Task 4 — Day 57 backlog: WP-relative time offsets (Option B)
The `delay` field is now authored in Events Editor and serialized to scene XML.
Loader implementation: on WP arrival, collect matching cues, fire `delay=0` immediately,
schedule `delay>0` with `setTimeout(fn, cue.delay * 1000)`.
Cancel all pending timeouts on Stop/Reset via `_pendingCueTimers` array.

---

## Key Architecture Facts (carry forward)

- EventCues live in `scenes/<name>_scene.xml`, NOT in the X3D file
- Loader reads EventCues from `_scene.xml` via `/scene/load/scene/raw` at startup
- WP IDs from server: varies by arc age (`"Waypt2"`, `"WAYPT2"`, `"W2"`) — never rely on format
- Scene XML WP names: `name="w1"`, `name="w2"`, `name="w3"` — these are canonical
- `_wpXmlNamesList` in Loader: ordered array of scene XML WP names, built at scene load
- **BUG 1 above:** candidate list currently returns all WP names — fix is Day 59 Task 1
- Camera cue schema: `shot, subject, transition, flyDuration, distance, height, hAngle, vAngle, roll, delay, distanceEnd, hAngleEnd, vAngleEnd, heightEnd` — all per spec v1.0
- Agent-attached shots: `shot=agent_eye|agent_side` → bind named VP inside agent Transform
- Static computed shots: use VP_Free driven by SAI position/orientation write + set_bind
- Move shots: VP_Free driven by TimeSensor interpolators (not yet implemented)
- NavigationInfo: `transitionType="TELEPORT"` in all exported scenes — confirmed working
- `VP_Free` node: not yet in Composer export — needed for Day 59 Task 2
- X_ITE version: pinned to `@11.6.0`
- Arc export: waypoint names written as-is (no mangling) since Day 57
- `mccf_playback.py` prefers `name` over `id` in arc XML for WP id resolution
- postMessage bridge: Events Editor iframe ↔ Composer (same origin, no Loader)

---

## Asset Authoring Architecture (Don Brutzman input — Day 58)

Two-tier asset model agreed:

**Tier 1 — Scene direction** (MCCF tools):
Agents, waypoints, zones, cameras, lights, effects → authored in Composer/Events Editor,
runtime computed, stored in `_scene.xml` EventCues.

**Tier 2 — Geometry assets** (external X3D tools):
Terrain, props, set dressing, complex meshes → authored in X3D-Edit, Blender+X3D export,
or any DCC tool. Referenced by scene. Previewed via:
- X_ITE Playground: `https://create3000.github.io/x_ite/playground/?url=YOUR_X3D_URL`
- x3dom editor: `https://andreasplesch.github.io/Library/Viewer/index.html?url=YOUR_X3D_URL`

**Integration pattern (Don's approach):** URL query parameter — no tool modification needed.
Add `X_ITE Playground` and `X3DOM Editor` buttons to Loader toolbar that construct
`playgroundUrl = PLAYGROUND_BASE + '?url=' + encodeURIComponent(currentX3dUrl)` and open in new tab.
Works when scene is on a public server or via localtunnel/ngrok.

---

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| 1 | Fix WP trigger candidate list — fires all WPs at every arrival | 🔴 Day 59 Task 1 |
| 2 | Loader camera runtime resolution — static computed shots | 🔲 Day 59 Task 2 |
| 3 | Add VP_Free to Composer X3D export | 🔲 Day 59 Task 2 |
| 4 | Camera move shots — interpolated (Phase 2) | 🔲 After Task 2 |
| 5 | WP-relative time offsets (delay field) — Loader | 🔲 Day 59 Task 4 |
| 6 | Remove duplicate WP arrival diagnostic log | 🔲 Day 59 Task 3 |
| 7 | Replace dummy Stage map with real scene data | 🔲 Saturn II |
| 8 | X_ITE Playground / x3dom Editor buttons in Loader | 🔲 Day 59 or later |
| — | X_ITE jump on set_bind | 🔲 Parked — resolved via TELEPORT workaround |

---

## Documents Produced Day 58

| Document | Status |
|---|---|
| `MCCF_Camera_System_Spec_v1.0.md` | Complete — includes tutorial section |
| System Architecture Specification | 🔲 Planned — Day 59 or after |
| User Guide (with screenshots) | 🔲 Planned — author gathers screenshots, Claude writes text/docx |

---

*Day 55: Loader EventCues pipeline wired.*
*Day 56: Export race fixed, WP name format confirmed, set_bind fix applied.*
*Day 57: Full EventCues pipeline confirmed. Trigger name mismatch fixed. Arc export mangling fixed. X_ITE pinned to 11.6.0. Camera fires. Jump parked.*
*Day 58: TELEPORT fix confirmed. Camera shot designer built in Events Editor. FOV cone on stage canvas. First camera cue firing confirmed. WP trigger candidate bug identified. Asset authoring two-tier architecture agreed with Don Brutzman input.*
