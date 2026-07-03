# MCCF Day 56 Session Handoff → Day 57

## Status: Camera EventCues Pipeline — Nearly Working

**GitHub baseline:** Commit `b3bb06c` (Day 53). Days 54–56 changes not yet committed.
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## Files Changed Day 56 (deploy these to static/)

| File | Key Changes |
|------|-------------|
| `static/mccf_x3d_loader.html` | `set_bind` fix (was `isBound`), `jump` parse+write, WP arrival diagnostic log, `mccf_x3d_ready` handler |
| `static/mccf_events_editor_prototype_2.html` | `jump` field in camera inspector, `exportCues` sends `mccf_save_cues` with tracks, VIEWS array corrected, TRIGGERS array has `WAYPT1/2/3 arrive`, camera `addCue` defaults |
| `static/mccf_scene_composer.html` | `mccf_save_cues` handler → `_sendToLauncherWithTracks`, `jump` in XML serializer, iframe src has `?v=57` cache bust |

---

## Root Causes Found and Fixed Day 56

### 1. `isBound` vs `set_bind` (FIXED)
`_fireCameraEventCue` was using `vpNode.isBound = true` — a read-only status field.
The correct write eventIn is `vpNode.set_bind = true` (same as `gotoVP` manual buttons).

### 2. Export race condition (FIXED)
Old path: `exportCues` → `mccf_export_x3d` → Composer → `mccf_request_cues` → 500ms timeout → saves empty cues.
New path: `exportCues` → `mccf_save_cues` (tracks included) → Composer → `_sendToLauncherWithTracks` → saves correct cues immediately. No round-trip race.

### 3. WP name mismatch (FIXED in Events Editor TRIGGERS array)
Server returns `WAYPT1`, `WAYPT2`, `WAYPT3` — not `w1`, `w2`, `w3`.
Diagnostic log added to Loader confirms: `stepWp: {"id":"WAYPT2"}`.
TRIGGERS array now has `WAYPT1 arrive`, `WAYPT2 arrive`, `WAYPT3 arrive` at top.

### 4. Loader not re-parsing scene XML after export (PARTIALLY FIXED)
The Loader fetches `_scene.xml` once at startup. After Events Editor export,
the Loader needs a page reload (Ctrl+Shift+R with ?v=XX) to pick up new EventCues.
The `mccf_x3d_ready` postMessage handler was added to the Loader but only fires
for the Events Editor iframe — not the Loader's separate tab. Manual reload required.

### 5. Browser caching of Events Editor iframe (WORKAROUND)
Composer iframe src now has `?v=57` to force fresh fetch.
Firefox was aggressively caching the iframe despite "Disable Cache" in DevTools.
If this recurs in Day 57, increment to `?v=58` in the Composer iframe src.

---

## Confirmed Working Day 56

- EventCues save pipeline end-to-end: author → export → scene XML saved correctly
- WP arrival trigger format confirmed: `WAYPT1 arrive`, `WAYPT2 arrive`, `WAYPT3 arrive`
- `set_bind` is the correct SAI call (confirmed via `gotoVP` manual button path)
- `jump` attribute parsed, written to XML, and applied before `set_bind`
- Export button no longer shows `alert()` — sends tracks directly to Composer

## NOT YET CONFIRMED

- Camera actually changing in Loader at WP arrival (the final test)
- The trigger name mismatch was the last known blocker — fix is deployed but test interrupted

---

## Day 57 Primary Task: Confirm Camera Fires

### Step 1 — Deploy files
Copy all three files above to `static/`. Verify timestamps updated.

### Step 2 — Fresh Composer load
Open `http://localhost:5000/static/mccf_scene_composer.html` in a new tab
(or navigate to it with DevTools Network "Disable Cache" checked).
Confirm Events Editor iframe shows `WAYPT1 arrive` in trigger dropdown.

### Step 3 — Author one camera cue
- Track: Camera
- Trigger: `WAYPT2 arrive`
- Viewpoint: `VP_Cindy_Side`
- Jump: checked (true)
- Click "Export cues ↗"

### Step 4 — Confirm Composer console
```
[Composer] mccf_save_cues received — tracks: 6 cues: 1
[Composer] _sendToLauncherWithTracks: saving scene XML then uploading X3D
```

### Step 5 — Fresh Loader load
Navigate to `http://localhost:5000/static/mccf_x3d_loader.html?v=58`
Before hitting Play, confirm console shows:
```
[EventCues] loaded: 1  camera:WAYPT2 arrive
```

### Step 6 — Run arc
At WP2 arrival, expect:
```
[EventCues] WP arrival trigger: "WAYPT2 arrive" — cues loaded: 1
[EventCues] firing: camera "new cue" trigger: WAYPT2 arrive
[EventCues] camera: set_bind VP_Cindy_Side jump=true
```
And the viewport should cut to `VP_Cindy_Side`.

---

## Key Architecture Facts (carry forward)

- EventCues live in `scenes/<name>_scene.xml`, NOT in the X3D file
- Loader reads EventCues from `_scene.xml` via `/scene/load/scene/raw` at startup
- WP IDs from server: `WAYPT1`, `WAYPT2`, `WAYPT3` (confirmed from diagnostic log)
- `set_bind = true` is the SAI write eventIn for Viewpoint (not `isBound`)
- `jump` is an exposed field on Viewpoint: `true` = cut, `false` = fly-through
- X_ITE version: pin to `@11.6.0` — `@11.6.6` has TextComponent WASM OOM crash risk
- `gotoVP(id)` manual buttons use `vp.set_bind = true` — confirmed working reference
- postMessage bridge: Events Editor iframe ↔ Composer (same origin, no Loader)
- Loader is a separate top-level tab — does not receive postMessages from Composer

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| 1–9 | See Day 55 handoff | ✅ as before |
| — | Commit Days 54–56 to git | 🔲 Do at Day 57 start |
| — | Confirm camera set_bind fires at WP arrival | 🔲 Day 57 first task |
| — | Remove WP arrival diagnostic log after confirmed | 🔲 Day 57 cleanup |
| — | Option B: WP-relative time offsets for time-based cues | 🔲 Post camera confirm |
| — | Replace dummy Stage map with real scene data | 🔲 Saturn II |

---

*Day 55: Loader EventCues pipeline wired. Trigger-based execution architecture confirmed.*
*Day 56: Export race fixed, WP name format confirmed (WAYPT1/2/3), set_bind fix applied. Camera firing not yet confirmed due to browser caching issues blocking final test.*
*Day 57: Deploy files, confirm camera fires, then proceed to Option B time offsets.*
