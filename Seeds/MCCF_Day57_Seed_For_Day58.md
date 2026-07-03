# MCCF Day 57 Session Handoff → Day 58

## Status: Camera EventCues Pipeline — Working (jump pending X_ITE bug)

**GitHub baseline:** Commit `0e3ae73` (Day 57). All five files committed.
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## Files Changed Day 57

| File | Key Changes |
|------|-------------|
| `static/mccf_x3d_loader.html` | `_resolveWpTriggerNames` fires all XML WP names at every arrival, `_wpXmlNamesList` built from scene XML, `getField().setValue()` for jump, X_ITE pinned back to `@11.6.0` |
| `static/mccf_events_editor_prototype_2.html` | `exportCues` sends `mccf_save_cues` (no alert), `switchViewpoint` uses `set_bind`, `jump` checkbox in camera inspector, camera `addCue` defaults |
| `static/mccf_scene_composer.html` | `jump="true"` on all Viewpoint nodes in X3D export, iframe cache-bust `?v=58` |
| `mccf_api.py` | Arc export: waypoint name written as-is (no `.upper()` mangling) to arc XML `id` attribute |
| `mccf_playback.py` | `ArcWaypoint` prefers `name` attribute over `id` when reading arc XML (handles old mangled arcs) |

---

## Root Causes Found and Fixed Day 57

### 1. exportCues still showing alert() (FIXED)
Events Editor `exportCues()` was still calling `alert()` with XML preview.
Fixed to send `{ type: 'mccf_save_cues', tracks: _tracks }` postMessage to Composer parent.
Standalone fallback (when not in iframe) logs to console instead.

### 2. switchViewpoint using isBound (FIXED)
Events Editor `switchViewpoint()` was using `vpNode.isBound = true` (read-only).
Fixed to `vpNode.set_bind = true`.

### 3. WP trigger name mismatch — server vs scene XML (FIXED in Loader)
Server reports WP as `id:"Waypt2"` (or `"WAYPT2"`, `"W2"` depending on arc age).
Scene XML has `name="w2"`. Events Editor builds triggers from scene XML names → `"w2 arrive"`.
Fix: Loader builds `_wpXmlNamesList = ["w1","w2","w3"]` from scene XML at startup.
`_resolveWpTriggerNames()` returns server id PLUS all XML names.
`fireEventCuesForTrigger` fires for all candidates — only matching cues execute.
This is robust to any number of waypoints and any server naming scheme.

### 4. Arc export mangling waypoint names (FIXED in mccf_api.py)
`mccf_api.py` was calling `.replace(" ","_").upper()` on waypoint name before writing arc XML id.
`"w2"` → `"W2"`, older arcs had `"WAYPT2"`. Fixed to write name as-is.
`mccf_playback.py` now prefers `name` attribute over `id` for backwards compat with old arcs.

### 5. X_ITE version drift to 11.6.6 (FIXED)
Loader had drifted to `x_ite@11.6.6`. Pinned back to `@11.6.0` per Day 53 architecture decision.

### 6. Viewpoint jump attribute missing from X3D export (FIXED in Composer)
All `<Viewpoint>` nodes in Composer X3D export now have `jump="true"` explicitly.

---

## Confirmed Working Day 57

- EventCues export pipeline end-to-end: author → Export cues ↗ → scene XML saved → no alert
- WP arrival trigger matching: `"w2 arrive"` fires correctly regardless of server id format
- Camera viewpoint changes at WP arrival: `set_bind VP_Cindy_Side` executes
- X_ITE `@11.6.0` running (confirmed via X_ITE browser context menu)
- GitHub commit `0e3ae73` includes all five changed files

## NOT YET CONFIRMED / OPEN ISSUES

### X_ITE jump bug — PARKED pending Holger Selig
- Camera moves to correct viewpoint but transitions smoothly instead of cutting
- `jump="true"` is set in the X3D file on all Viewpoint nodes
- `vpNode.getField('jump').setValue(true)` called before `set_bind` — silently ignored
- X_ITE Viewpoint menu also ignores jump (confirms it's an X_ITE issue, not our code)
- X_ITE `11.6.0` confirmed running
- **File issue with Holger Selig:** `set_bind = true` via SAI ignores `jump` field on Viewpoint.
  Key details: X_ITE 11.6.0, `jump="true"` in X3D, SAI `set_bind`, camera moves but doesn't cut.
  Also: Viewpoint menu ignores jump too — may be intentional for re-bind vs initial bind.

---

## Day 58 Primary Tasks (in order)

### Task 1 — Remove diagnostic log duplicate
In `mccf_x3d_loader.html`, remove the duplicate log line:
```
console.log('[EventCues] WP arrival trigger (pbStep): "' + _wpArrId + ' arrive"', '— cues:', _eventCues.length);
```
This is at line ~2963 in the first WP arrival block. The primary log line above it is sufficient.

### Task 2 — Option B: WP-relative time offsets
Time-based EventCues that fire N seconds after a WP arrival, not just on arrival itself.
Architecture: cues with `trigger="w2 arrive"` and a `delay` field (seconds after arrival).
Loader implementation: on WP arrival, collect all matching cues, fire immediate ones now,
schedule delayed ones with `setTimeout(fn, delay * 1000)`.
Cancel pending timeouts on Stop/Reset.
Events Editor inspector: add `delay (s)` field for all cue types (default 0).
Scene XML serializer: write `delay` attribute on `<Cue>` elements.

### Task 3 — Replace dummy Stage map in Events Editor
The stage canvas currently draws hardcoded zones, agents, cameras, lights.
Replace with real scene data from `_buildSceneData()` — use `WPS`, `AGENTS`, waypoint positions.
Reference: `drawStage()` function in `mccf_events_editor_prototype_2.html`.

---

## Key Architecture Facts (carry forward)

- EventCues live in `scenes/<name>_scene.xml`, NOT in the X3D file
- Loader reads EventCues from `_scene.xml` via `/scene/load/scene/raw` at startup
- WP IDs from server: varies by arc age (`"Waypt2"`, `"WAYPT2"`, `"W2"`) — never rely on format
- Scene XML WP names: `name="w1"`, `name="w2"`, `name="w3"` — these are canonical
- `_wpXmlNamesList` in Loader: ordered array of scene XML WP names, built at scene load
- `set_bind = true` is the SAI write eventIn for Viewpoint (confirmed working)
- `jump` SAI write is broken in X_ITE — parked pending upstream fix
- `jump="true"` is explicit on all Viewpoint nodes in X3D export (correct for when fix lands)
- X_ITE version: pinned to `@11.6.0` — `@11.6.6` has TextComponent WASM OOM crash risk
- `gotoVP(id)` manual buttons use `vp.set_bind = true` — confirmed working reference
- postMessage bridge: Events Editor iframe ↔ Composer (same origin, no Loader)
- Loader is a separate top-level tab — does not receive postMessages from Composer
- Arc export: waypoint names written as-is (no mangling) since Day 57
- `mccf_playback.py` prefers `name` over `id` in arc XML for WP id resolution

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| — | Remove duplicate WP arrival diagnostic log | 🔲 Day 58 Task 1 |
| — | Option B: WP-relative time offsets | 🔲 Day 58 Task 2 |
| — | Replace dummy Stage map with real scene data | 🔲 Day 58 Task 3 |
| — | X_ITE jump on set_bind | 🔲 Parked — awaiting Holger Selig |
| — | Replace dummy Stage map with real scene data | 🔲 Saturn II |

---

*Day 55: Loader EventCues pipeline wired. Trigger-based execution architecture confirmed.*
*Day 56: Export race fixed, WP name format confirmed (WAYPT1/2/3), set_bind fix applied. Camera firing not yet confirmed due to browser caching issues blocking final test.*
*Day 57: Full EventCues pipeline confirmed working. Trigger name mismatch fixed (server vs scene XML). Arc export mangling fixed. X_ITE pinned to 11.6.0. Camera fires and moves to correct viewpoint. Jump behavior parked pending X_ITE upstream bug report to Holger Selig. All five files committed to GitHub at 0e3ae73.*
