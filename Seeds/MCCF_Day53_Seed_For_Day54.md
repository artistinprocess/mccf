# MCCF Day 54 Session Seed
## Handoff from Day 53 — Events Editor

**Rule:** Author does not edit code. Claude delivers complete files only.
**GitHub:** Commit `b3bb06c` on master — Day 53 complete.
**Current working build:** Saturn I (in progress). Saturn II = field-driven avatar animation milestone.

---

## What Was Accomplished Day 53

### Files committed to GitHub (b3bb06c)
| File | Change |
|------|--------|
| `static/avatars/cindy_hanim.x3d` | Stripped 339KB corrupt duplicate block; regenerated all 2352 ROUTEs (147 pairs × 8 clips) cleanly before </Scene> |
| `mccf_api.py` | `_write_clip_nodes` now emits `<EXPORT localDEF="X" AS="X"/>` for every TimeSensor written; preview page X_ITE version bumped 10.5.2 → 11.6.0 |
| `static/mccf_scene_composer.html` | `behavior_clips` now stored into `agents` and `placedAgents` at loadAll/loadAgents; `buildAvatarNode` IMPORT loop reads `a.behavior_clips` and merges custom timerDEFs with standard bases |
| `static/mccf_x3d_loader.html` | `pbActivateX3DTimers` builds `_timerBases` from `BEHAVIOR_TIMER_BASES.slice()` + `_agentBehaviorClips[sName].clips` timerDEFs before `getImportedNode` loop |

### Confirmed working
- Cindy loads, walks between waypoints, DefaultTimer idles at waypoints
- Console confirms: `_switchBehaviorTimer: Cindy → WalkTimer` and back to DefaultTimer on arrival
- Field state, zone audio, Chorus response all confirmed in screenshot

### Day 53 X3D corruption history (permanent record)
The original cindy_hanim.x3d had all behavior clip ROUTEs living inside a corrupt duplicate block appended at line 7225 by a previous `_write_clip_nodes` export. X_ITE was parsing them from there and animation worked. The strip operation removed the junk but also the ROUTEs. Fix: regenerated all ROUTEs from interpolator DEFs using pattern `<ClipName>_<joint>_RotationInterpolator` → `hanim_<joint>`. 2352 ROUTEs, 147 pairs per clip, 8 clips.

---

## Where We Are: Events Editor

### Session 1 — X_ITE feature assessment (this session)
Completed. See earlier in this conversation for the full node assessment table.

### Events Editor Prototype Built
File: `mccf_events_editor_prototype.html` (delivered, not yet in static/)

**Design confirmed from screenshot (Day 49 prototype reference):**
- **Left panel** — Stage top-down view (canvas) with agent dots, camera squares, light circles; Stage/Assets tabs; + Cam / + Light buttons
- **Center** — Horizontal timeline, track rows (Camera, Lights, Fog, Background, FX, Behavior), waypoint markers as purple vertical lines, cue blocks colored by track type, playhead, zoom
- **Right** — Inspector: cue label, trigger (on WP arrive / field threshold / manual), type-specific fields (viewpoint, light node/intensity, agent/clip, etc.), duration, Delete cue, Export cues

**Toolbar:** Play/pause, rewind, T display, Snap to WP, + Add cue, + Track, zoom ±

**Prototype data model:**
```js
_tracks = [{ type, label, cues: [{ label, t, dur, trigger, ...typeProps }] }]
WPS = [{ name, t }]  // from scene waypoints
```

**NOT YET DONE — prototype only, needs integration into Scene Composer:**

---

## Day 54 Primary Task: Integrate Events Editor into Scene Composer

### Step 1 — Verify prototype works
Author downloads and tests `mccf_events_editor_prototype.html`. If UX is confirmed:

### Step 2 — Add Events tab to Scene Composer
- Add `<button class="mtab" onclick="setMode('events')">Events</button>` to tab row (between Paths and Network)
- Add `<div id="mode-events" style="display:none">` panel
- Add `'events'` to the `ms` array in `setMode()`
- Add `if(m==='events') initEventsEditor();` to `setMode()`

### Step 3 — Replace hardcoded placeholder data with live scene data
In the prototype, AGENTS / WPS / VIEWS come from hardcoded arrays.
In the Composer, wire to:
- `AGENTS` → `Object.keys(placedAgents)`
- `WPS` → waypoint positions from `Object.values(waypoints)` ordered by path
- `VIEWS` → `Object.keys(placedAgents).flatMap(n => ['VP_'+safeId(n)+'_Eye','VP_'+safeId(n)+'_Side'])` + ['VP_Overview','VP_Origin']
- `CLIPS` → `BEHAVIOR_TIMER_BASES` merged with `a.behavior_clips` for each agent
- `LIGHTS_L` → hardcoded standard set (S0Light, KeyLight, FillLight, RimLight, AmbientLight)

### Step 4 — Wire into exportSceneXML
After `</Paths>` block, append:
```xml
<EventCues>
  <Cue track="camera" label="overview" t="0" dur="8" trigger="WP1 arrive" viewpoint="VP_Overview"/>
  ...
</EventCues>
```
The `_tracks` array serializes directly to this format.

### Step 5 — Load EventCues back from scene XML
In `loadSceneXML` (wherever it reads `<Paths>`), add reader for `<EventCues>/<Cue>` elements that populates `_tracks`.

---

## Architecture Decisions Already Made

**Timeline is waypoint-anchored, not clock-anchored.** Cues snap to waypoint arrival events. The `trigger` field on each cue is the primary timing anchor (`WP1 arrive`, `WP2 arrive`, `field E>0.6`, `manual`).

**Export format is XML in scene XML** (`<EventCues>` block), not a separate file. Same pattern as `<Zones>`, `<Paths>`, `<Waypoints>`.

**Loader reads EventCues at play time** (Session 5 work — not Day 54). Day 54 is authoring UI only.

**EXPORT convention confirmed:** Identity exports in X3D file (`localDEF="WalkTimer" AS="WalkTimer"`). Scene IMPORT adds agent suffix (`AS="WalkTimer_Cindy"`). No suffix in X3D file itself.

---

## Remaining Pre-Saturn II Tasks (from earlier assessment)

| # | Item | Status |
|---|------|--------|
| 1 | cindy_hanim.x3d corruption | ✅ Fixed |
| 2 | EXPORT generation in _write_clip_nodes | ✅ Done |
| 3 | Composer IMPORT cultivar-aware | ✅ Done |
| 4 | Loader custom clips in timer map | ✅ Done |
| 5 | Preview page X_ITE 11.6.0 | ✅ Done |
| 6 | Events Editor UI in Composer | 🔲 Day 54 |
| 7 | Six canonical expression slots in HAnim editor | 🔲 Deferred |
| 8 | Full-pose keyframe capture (all joints) | 🔲 Deferred |
| 9 | Loader reads EventCues and fires SAI | 🔲 Session 5 |
| 10 | Face pipeline via Blender MCP | 🔲 Post-Saturn II |

---

## Files to Have Available Day 54

- `mccf_scene_composer.html` — needs Events tab integrated
- `mccf_events_editor_prototype.html` — reference for integration
- `mccf_x3d_loader.html` — will need EventCue reader in Session 5

Upload all three at start of Day 54 session.

---

## Key Confirmed Facts (do not re-research)

- X_ITE SAI mechanism for timers: `enabled=true/false` — confirmed Day 25. startTime/stopTime do NOT work.
- Timer map uses `getImportedNode(base + '_' + agentSafeName)` — confirmed Day 24.
- EXPORT is identity (`AS="WalkTimer"`), IMPORT adds suffix (`AS="WalkTimer_Cindy"`).
- All behavior ROUTEs must be after last EXPORT in X3D, before `</Scene>`.
- `_write_clip_nodes` uses `ET.SubElement` with `_X3D_NS` namespace prefix.
- Cindy face: segment mode (no globalIndices), 8 coord regions, AU data in cindy_expressions.xml, AnimationAdapter not yet injected.
- Face pipeline deferred to Blender MCP conversion — not blocking Saturn II.

---

*Day 53: servers down most of day. Completed bug fixes, pushed to GitHub, built Events Editor prototype.*
*Day 54: integrate Events Editor into Scene Composer as live tab with scene data wired in.*
