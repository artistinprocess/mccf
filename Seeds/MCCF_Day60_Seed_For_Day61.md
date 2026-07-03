# MCCF Day 60 Session Handoff → Day 61

## Status: Camera EventCues System — Static Computed Shots Working

**GitHub baseline:** Commit `c75c232` (master). All Days 57–60 files committed.
**Rule:** Author does not edit code. Claude delivers complete files only.
**Critical rule:** Always work from the file the author uploads. Never use a cached or previously generated version as a base. Confirm fixes by having the author upload the file back before proceeding.

---

## Reference Documents — Load These First

These must be uploaded and read at the start of any session touching camera, Events Editor, or X3D:

| Document | Location | Read when |
|---|---|---|
| `MCCF_Events_Editor_Architecture.md` | `docs/` | Any new event track, cue type, or vessel |
| `MCCF_Camera_System_Spec_v1.2.md` | `docs/` | Any camera cue, VP_Free, orientation math |
| `X3D_KNOWN_ISSUES.md` | `docs/` | Any X3D/X_ITE rendering or SAI issue |

**Do not write spatial math, SAI field writes, or camera routing code without reading the architecture doc and camera spec first.** Day 60 lost multiple test cycles to the X3D -Z convention and SAI output-field writes. Both are now documented.

---

## Files Changed Day 60

| File | Key Changes |
|---|---|
| `static/mccf_x3d_loader.html` | `_fireCameraEventCue` rewritten: clean baked/runtime split with `_STATIC_SHOTS`/`_MOVE_SHOTS` whitelists; `_lookAtOrientation` -Z convention fixed (was 180° reversed); `_executeStaticCameraShot` rewritten to use `CAM_Free_Transform` parent Transform + VP_Free bind; `_resolveSubjectPos` PATH 1 runtime `_agentCurrentStep` tracker; `_agentCurrentStep` write added to both `pbStepSession` and `pbStep`; `_agentCurrentStep` cleared on reset |
| `static/mccf_scene_composer.html` | `exportX3D()` now POSTs to `/scene/x3d/upload` (server) instead of browser download, with download fallback; VP_Free wrapped in `CAM_Free_Transform` in both `exportX3D()` and `buildX3DString()`; `viewpoint=` suppressed on `shot=` cues |
| `docs/MCCF_Camera_System_Spec_v1.2.md` | VP_Free/CAM_Free_Transform pattern documented; -Z orientation convention; SAI write rules |
| `docs/MCCF_Events_Editor_Architecture.md` | New document: baked vs runtime, vessel principle, SAI field table, coordinate system, new track checklist |

---

## Confirmed Working Day 60

- **Camera routing:** Clean four-path split — baked agent-attached / baked named VP / runtime static / runtime move (Phase 2 stub). Unknown shot types warn and skip — VP_Free never fires as fallback.
- **`_resolveSubjectPos` PATH 1:** `_agentCurrentStep` written at WP arrival in both `pbStepSession` and `pbStep`. Correct agent position used for camera framing.
- **`CAM_Free_Transform` pattern:** VP_Free wrapped in Transform. Loader writes `translation` and `rotation` to Transform (SAI-writable input fields), then binds VP_Free. Confirmed working in live playback.
- **`_lookAtOrientation`:** Fixed -Z convention. `yaw = atan2(-dx, -dz)`. Camera now faces subject correctly.
- **Static computed shots confirmed:** Medium shot at WP2 (Cindy), wide shot at WP3 (The Witness) both cut correctly.
- **Composer export path:** X3D now POSTs directly to `static/x3d/` on server. No more Windows Downloads confusion.
- **GitHub:** All Days 57–60 committed. `docs/` folder created with all specs. `requirements.txt` at root.

---

## Key Architecture Facts (carry forward)

### Baked vs Runtime cameras
- **Baked:** `agent_eye`/`agent_side` → bind `VP_{agent}_{Eye|Side}` inside agent Transform. Any `cue.viewpoint` set → bind named VP. Loader calls `_bindNamedViewpoint()` only.
- **Runtime:** static shot types → `_executeStaticCameraShot()` → writes to `CAM_Free_Transform`, binds VP_Free. Move shots (Phase 2) → same vessel, TimeSensor driven.
- VP_Free is never in the author's vocabulary. It never appears in cue data.

### CAM_Free_Transform / VP_Free vessel
```xml
<Transform DEF="CAM_Free_Transform" translation="0 0 0" rotation="0 1 0 0.0001">
  <Viewpoint DEF="VP_Free" description="Free Camera" position="0 0 0" orientation="0 1 0 0.0001" jump="true"/>
</Transform>
```
- Loader writes `CAM_Free_Transform.translation` and `CAM_Free_Transform.rotation`
- `Viewpoint.position` and `Viewpoint.orientation` are **output fields** — SAI writes ignored
- VP_Free must have non-zero authored orientation (`0 1 0 0.0001`) — zero angle = black viewport in X_ITE
- `set_bind` called on VP_Free after one `requestAnimationFrame`

### X3D coordinate system
- Right-handed: +X right, +Y up, **+Z toward viewer**, **-Z into scene**
- Cameras face **-Z** by default
- Look-at yaw: `atan2(-dx, -dz)` NOT `atan2(dx, dz)` — negation is required, not intuitive

### _resolveSubjectPos paths
- **PATH 1** (preferred): `_agentCurrentStep[safeName]` → `_agentWaypointCache[safeName][step]` — runtime arrived position
- **PATH 3** (fallback warning): pre-loaded cache, picks highest step — wrong during playback, fires only if PATH 1 missed
- **PATH 4**: `_cultivarStartPos` — before any arrival

### Scene XML / EventCues
- Camera cues: `shot=` present, no `viewpoint=` (Composer fix). Clean XML.
- Trigger candidates: `["Waypt2 arrive", "w2 arrive"]` — server ID + scene XML name

---

## Current Scene XML State (testssound_scene.xml as of end of Day 60)

```xml
<EventCues>
  <Cue track="camera" trackLabel="Camera" label="medium" t="0" dur="4"
       trigger="w2 arrive" shot="medium" subject="Cindy" transition="cut"
       distance="5" height="1.7" hAngle="0" vAngle="-8" delay="0" jump="true" blend="cut"/>
  <Cue track="camera" trackLabel="Camera" label="wide" t="4" dur="4"
       trigger="w3 arrive" shot="wide" subject="The Witness" transition="cut"
       distance="12" height="4.5" hAngle="28" vAngle="1" delay="1" jump="true" blend="cut"/>
</EventCues>
```

Both cues working. WP2 medium shot frames Cindy. WP3 wide shot frames The Witness + Cindy from hAngle=28°.
Note: WP2 hAngle=0 puts camera directly behind Cindy — consider adjusting to -20° or +20° for more interesting framing.

---

## Day 61 Tasks (in order)

### Task 1 — Housekeeping
- Update `MANIFEST.md` to reference `docs/` folder structure
- Update `docs/X3D_KNOWN_ISSUES.md` with -Z convention and SAI output-field write rules (VP_Free pattern)

### Task 2 — Named VP authoring UI in Events Editor
Currently there is no UI for the baked named VP path — an author cannot select `VP_Cindy_Side` from the Events Editor. The inspector has no "bind named VP" field. This is missing functionality, not broken code.
- Add a "named viewpoint" option to the camera inspector
- When selected: shows a dropdown or text field for VP name; writes `cue.viewpoint` and clears `cue.shot`
- The two paths (shot type = runtime, named VP = baked) must remain mutually exclusive in the UI

### Task 3 — Camera framing refinement
- Re-author WP2 medium cue with hAngle offset for better framing of Cindy
- Test agent_eye / agent_side shots now that routing is confirmed clean

### Task 4 — Phase 2 move shots (if ready)
- `_executeMoveShot(cue)` stub is in `_fireCameraEventCue` under `_MOVE_SHOTS`
- Implement orbit as first move shot: TimeSensor drives `CAM_Free_Transform` via PositionInterpolator/OrientationInterpolator
- Composer needs to emit `CAM_Timer`, `CAM_PosInterp`, `CAM_OrientInterp` vessel nodes

### Task 5 — Semantic/emotional animation track design
- Design the cue schema before writing any code
- Read `MCCF_Events_Editor_Architecture.md` Section 7 (Semantic track notes) first
- This is an all-runtime track — no baked nodes, all vessel-driven
- The checklist in Section 9 must be answered before any implementation

---

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| 1 | MANIFEST.md update | 🔴 Day 61 Task 1 |
| 2 | X3D_KNOWN_ISSUES.md update | 🔴 Day 61 Task 1 |
| 3 | Named VP authoring UI in Events Editor | 🔴 Day 61 Task 2 |
| 4 | Camera framing refinement / agent_eye test | 🔴 Day 61 Task 3 |
| 5 | Camera move shots — interpolated (Phase 2) | 🔲 Day 61 Task 4 |
| 6 | Semantic/emotional animation track | 🔲 Day 61 Task 5 |
| 7 | Replace dummy Stage map with real scene data | 🔲 Saturn II |
| 8 | X_ITE Playground / x3dom Editor buttons in Loader | 🔲 Day 61 or later |

---

## Documents Produced Day 60

| Document | Location | Status |
|---|---|---|
| `MCCF_Camera_System_Spec_v1.2.md` | `docs/` | Complete |
| `MCCF_Events_Editor_Architecture.md` | `docs/` | Complete |
| System Architecture Specification | — | 🔲 Planned |
| User Guide (with screenshots) | — | 🔲 Planned |

---

*Day 55: Loader EventCues pipeline wired.*
*Day 56: Export race fixed, WP name format confirmed, set_bind fix applied.*
*Day 57: Full EventCues pipeline confirmed. Trigger name mismatch fixed. Arc export mangling fixed. X_ITE pinned to 11.6.0. Camera fires. Jump parked.*
*Day 58: TELEPORT fix confirmed. Camera shot designer built in Events Editor. FOV cone on stage canvas. First camera cue firing confirmed. WP trigger candidate bug identified.*
*Day 59: BUG 1 fixed. Full camera schema serialized. VP_Free added to Composer export. Camera routing partially working.*
*Day 60: Camera routing rewritten (baked/runtime split). CAM_Free_Transform pattern confirmed. _lookAtOrientation -Z fix. Static computed shots verified in live playback. Composer exports to server. docs/ folder created. All committed.*
