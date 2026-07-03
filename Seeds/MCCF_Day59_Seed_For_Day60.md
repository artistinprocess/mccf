# MCCF Day 59 Session Handoff → Day 60

## Status: Camera EventCues System — Pipeline Working, Shot Routing Bug Remaining

**GitHub baseline:** Commit `0e3ae73` (Day 57). Days 58–59 files not yet committed.
**Rule:** Author does not edit code. Claude delivers complete files only.
**Critical rule:** Always work from the file the author uploads. Never use a cached or previously generated version as a base. Confirm fixes by having the author upload the file back before proceeding.

---

## Files Changed Day 59

| File | Key Changes |
|------|-------------|
| `static/mccf_x3d_loader.html` | BUG 1 fix; camera runtime execution; `_parseEventCues` full schema; `_pendingCueTimers` delay scheduling; duplicate log removed; `VP_Free` excluded from viewpoint toolbar; `_cultivarStartPos` cache; `X3D.SFRotation/SFVec3f` namespace fix; `rAF` deferral on `set_bind`; guard against VP_Free firing with no `shot=` |
| `static/mccf_scene_composer.html` | `VP_Free` node in both `exportX3D()` and `buildX3DString()`; full camera schema serialization in `_doExportSceneXML`; full camera schema read in XML restore; avatar URL backslash fix |
| `static/mccf_events_editor_prototype_2.html` | `applyShotPreset()` defaults `cue.subject` to `AGENTS[0]` if missing; `mccf_load_cues` handler defaults `subject` on camera cues restored from old XML |

---

## Confirmed Working Day 59

- **Task 1 — BUG 1 fixed:** `_resolveWpTriggerNames()` now returns only current WP candidates (`[serverWpId, _wpXmlNamesList[stepIndex]]`). Confirmed in console: `firing trigger candidates: ["Waypt2 arrive","w2 arrive"]` — exactly 2 entries, not all WPs.
- **Task 3:** Duplicate diagnostic log removed.
- **Task 4:** Delay scheduling confirmed working — `(delay 1s)` fires correctly after WP arrival; `_pendingCueTimers` cleared on Stop/Reset.
- **Composer cue serialization:** Full camera schema now written to `_scene.xml` — `shot`, `subject`, `transition`, `distance`, `height`, `hAngle`, `vAngle`, `delay` all confirmed in XML.
- **Subject defaulting:** `subject="Cindy"` now appears in both cues after Events Editor fix.
- **VP_Free:** Present in exported X3D. Excluded from Loader viewpoint toolbar (`_vpExclude`). `X3D.SFRotation/SFVec3f` namespace fixed. `set_bind` deferred to `requestAnimationFrame`.

---

## Remaining Bug — Day 60 PRIMARY TASK

### BUG: Camera routing ignores `viewpoint=` when `shot=` is also present

**Symptom:** Console shows:
```
[EventCues] firing: camera "medium" trigger: w2 arrive
[EventCues] camera: VP_Free static shot "medium" subj=Cindy pos=[24.80,1.70,30.60]
```
VP_Free fires even though the cue has `viewpoint="VP_Cindy_Side"` in the XML.

**Root cause:** In `_fireCameraEventCue()`, the routing logic is:
1. If `shot === 'agent_eye' || 'agent_side'` → bind named VP ✅
2. If `!shot && cue.viewpoint` → bind named VP (legacy) ✅
3. If `shot` present → `_executeStaticCameraShot()` ← **THIS IS WRONG**

When `shot="medium"` is present alongside `viewpoint="VP_Cindy_Side"`, the code reaches step 3 and fires VP_Free instead of respecting the authored `viewpoint`. The cue was authored with shot type "medium" but the Events Editor also wrote the legacy `viewpoint` field for backward compat. The Loader should prefer `viewpoint` when explicitly set.

**Fix required** in `_fireCameraEventCue()` in `mccf_x3d_loader.html`:

The routing should be:
1. `shot === 'agent_eye' || 'agent_side'` → bind `VP_{subject}_{Eye|Side}`
2. `cue.viewpoint` explicitly set (regardless of whether `shot` is also present) → bind named VP
3. `shot` present and no `viewpoint` → `_executeStaticCameraShot()`
4. Neither → skip with warning

OR: the Composer should stop writing the legacy `viewpoint=` attribute when a full `shot=` schema is present — so the Loader never sees both simultaneously.

**Recommended fix:** Option B — in `_doExportSceneXML` in the Composer, only write `viewpoint=` if the cue has no `shot=` attribute (i.e. it's a hand-authored legacy cue). When `shot=` is present the Loader computes the position dynamically and the `viewpoint` field is misleading noise.

**Second issue — subject position:**
`subj=Cindy pos=[24.80,1.70,30.60]` — the position `[24.80, 25.60]` is WP3's coordinates from `_waypointPosMap`, not Cindy's current position at WP2. `_resolveSubjectPos("Cindy")` is hitting `_waypointPosMap["Cindy"]` somehow, or the `_agentWaypointCache` has a stale/wrong entry. Need to trace how `_agentWaypointCache["Cindy"]` gets populated — it should be the most recent arrived WP, which at WP2 arrival should be WP2's coords `[18.90, 19.10]`, not WP3's.

Actually: `24.80` and `30.60` — `pos_x=24.80` is WP3's x. The z=30.60 doesn't match any WP. This looks like the `_cultivarStartPos` or `_waypointPosMap` lookup is returning wrong data. Needs console tracing in `_resolveSubjectPos`.

---

## Current Scene XML State (testssound_scene.xml as of end of Day 59)

Both cues correctly serialized:
```xml
<EventCues>
  <Cue track="camera" trackLabel="Camera" label="medium" t="0" dur="4"
       trigger="w2 arrive" shot="medium" subject="Cindy" transition="cut"
       distance="5" height="1.7" hAngle="0" vAngle="-8" delay="0"
       viewpoint="VP_Cindy_Side" jump="true" blend="cut"/>
  <Cue track="camera" trackLabel="Camera" label="wide" t="4" dur="4"
       trigger="w3 arrive" shot="wide" subject="Cindy" transition="cut"
       distance="12" height="4.5" hAngle="28" vAngle="1" delay="1"
       viewpoint="VP_The_Witness_Side" jump="true" blend="cut"/>
</EventCues>
```

Note: `wide` cue has `subject="Cindy"` but should be `subject="The Witness"` — the Events Editor defaulted to first agent. Author needs to re-select subject on the wide cue.

---

## Day 60 Tasks (in order)

### Task 1 — Fix camera routing: stop writing legacy `viewpoint=` when `shot=` is present
In `_doExportSceneXML` in `mccf_scene_composer.html`, change:
```javascript
if (cue.viewpoint)  x += ' viewpoint="'+xe(cue.viewpoint)+'"';
```
To only write `viewpoint=` when `cue.shot` is absent (legacy cues only).

### Task 2 — Fix `_resolveSubjectPos` logging and position accuracy
Add `console.log` at each resolution path in `_resolveSubjectPos` so we can trace which branch fires and what coordinates are returned. Then fix the wrong-position bug.

### Task 3 — Author correct subjects
After routing fix: re-author the `wide` cue with `subject="The Witness"` in Events Editor. Both cues should then resolve correct subject positions.

### Task 4 — Verify VP_Free static shot actually moves camera
Once routing is fixed and positions are correct, confirm the viewport cuts to the computed angle rather than VP_Free's default position.

### Task 5 — Commit Day 57–59 to GitHub
All confirmed-working files: `mccf_x3d_loader.html`, `mccf_scene_composer.html`, `mccf_events_editor_prototype_2.html`.

---

## Key Architecture Facts (carry forward)

- EventCues live in `scenes/<name>_scene.xml`, NOT in the X3D file
- Loader reads EventCues from `_scene.xml` via `/scene/load/scene/raw` at startup
- WP IDs from server: varies by arc age (`"Waypt2"`, `"WAYPT2"`, `"W2"`) — never rely on format
- Scene XML WP names: `name="w1"`, `name="w2"`, `name="w3"` — these are canonical
- `_wpXmlNamesList` in Loader: ordered array of scene XML WP names, built at scene load
- `stepno` from server is 1-based; `_wpXmlNamesList` is 0-based → index = stepno - 1
- Camera cue schema: `shot, subject, transition, flyDuration, distance, height, hAngle, vAngle, roll, delay, distanceEnd, hAngleEnd, vAngleEnd, heightEnd` — all per spec v1.0
- Agent-attached shots: `shot=agent_eye|agent_side` → bind named VP inside agent Transform
- Static computed shots: use VP_Free driven by SAI position/orientation write + set_bind (deferred via rAF)
- Move shots: VP_Free driven by TimeSensor interpolators (not yet implemented — Phase 2)
- NavigationInfo: `transitionType="TELEPORT"` in all exported scenes — confirmed working
- `VP_Free`: present in Composer export with `description="Free Camera"`. Excluded from Loader viewpoint toolbar via `_vpExclude`. NOT excluded from X_ITE's own viewpoint menu (that's X_ITE's business).
- X_ITE version: pinned to `@11.6.0`
- SAI field write pattern: always use `new X3D.SFVec3f(...)` and `new X3D.SFRotation(...)` with `X3D.` namespace prefix
- `_cultivarStartPos`: populated from `<EmotionalArc cultivar="X"><StartPosition x y z/>` in scene XML. Used as fallback in `_resolveSubjectPos` when agent cache is empty.
- `_agentWaypointCache`: `{safeName: {stepNo: {pos_x, pos_z}}}` — built from `pbUpdateDisplay` and `pbStepSession`. Should hold current WP position for active agents.
- postMessage bridge: Events Editor iframe ↔ Composer (same origin, no Loader)
- `mccf_playback.py` prefers `name` over `id` in arc XML for WP id resolution

---

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| 1 | Camera routing: stop writing legacy viewpoint= when shot= present | 🔴 Day 60 Task 1 |
| 2 | _resolveSubjectPos: trace and fix wrong position | 🔴 Day 60 Task 2 |
| 3 | Re-author wide cue with correct subject (The Witness) | 🔴 Day 60 Task 3 |
| 4 | Verify VP_Free static shot moves camera correctly | 🔲 Day 60 Task 4 |
| 5 | Camera move shots — interpolated (Phase 2) | 🔲 After Task 4 |
| 6 | Replace dummy Stage map with real scene data | 🔲 Saturn II |
| 7 | X_ITE Playground / x3dom Editor buttons in Loader | 🔲 Day 60 or later |
| 8 | Commit Day 57–59 to GitHub | 🔲 Day 60 Task 5 |
| — | X_ITE jump on set_bind | 🔲 Parked — resolved via TELEPORT workaround |

---

## Documents Produced Day 58–59

| Document | Status |
|---|---|
| `MCCF_Camera_System_Spec_v1.0.md` | Complete |
| System Architecture Specification | 🔲 Planned |
| User Guide (with screenshots) | 🔲 Planned — author gathers screenshots, Claude writes text/docx |

---

*Day 55: Loader EventCues pipeline wired.*
*Day 56: Export race fixed, WP name format confirmed, set_bind fix applied.*
*Day 57: Full EventCues pipeline confirmed. Trigger name mismatch fixed. Arc export mangling fixed. X_ITE pinned to 11.6.0. Camera fires. Jump parked.*
*Day 58: TELEPORT fix confirmed. Camera shot designer built in Events Editor. FOV cone on stage canvas. First camera cue firing confirmed. WP trigger candidate bug identified. Asset authoring two-tier architecture agreed with Don Brutzman input.*
*Day 59: BUG 1 fixed (WP trigger candidates). Full camera schema serialized in scene XML. VP_Free added to Composer export. Camera routing partially working — agent-attached and legacy viewpoint paths confirmed. Static computed path (VP_Free) fires but routes incorrectly when both shot= and viewpoint= present in cue. Subject position resolution needs tracing. Delay scheduling confirmed working.*
