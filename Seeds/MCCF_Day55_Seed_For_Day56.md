# MCCF Day 55 Session Handoff → Day 56

## Status: Saturn I Pipeline Complete

**GitHub baseline:** Commit `b3bb06c` (Day 53). Days 54–55 changes not yet committed.
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## Files Changed Day 55 (not yet committed)

| File | Changes |
|------|---------|
| `static/mccf_x3d_loader.html` | EventCues pipeline: `_parseEventCues`, `fireEventCuesForTrigger`, `fireManualCues` (one-shot guard), 5 SAI handlers, WP arrival hooks in `pbStep`/`pbStepSession`, `_eventCues` reset in `x3dFileChanged`, camera retry loop |
| `static/mccf_events_editor_prototype_2.html` | Empty initial tracks, `_tracksAreStub=false`, `mccf_load_cues` merge into 6-track layout with auto-spread, `addCue` places after last cue, `×` clear-track button per row with truncating label CSS, Sound nodes muted in viewport |
| `static/mccf_scene_composer.html` | `_sendSceneDataToEventsEditor` guarded by `_sceneXmlLoaded`, scene data sent at end of `_restoreChorusFromXml`, `trackLabel` attr on XML export, named-track restore in `_restoreChorusFromXml`, `saveHanimSrc` auto-saves scene XML via `_requestCuesAndExport` |

---

## Confirmed Working (Day 55 end state)

- EventCues load from scene XML on Loader start
- `trigger="manual"` camera cue fires on scene load, retries up to 10× at 200ms if SAI not yet ready
- `trigger="w1 arrive"` etc. fire at WP arrivals via `pbStep`/`pbStepSession`
- Events Editor: 6 clean empty tracks on load, no stubs
- Events Editor: `+ Add cue` places cues rightward, no stacking
- Events Editor: `×` button clears a track (hover to reveal), label truncates for long names
- Events Editor: Sound nodes muted in X3D viewport
- Events Editor: `mccf_load_cues` merges into 6-track layout, auto-spreads any stacked cues from old XML
- Composer: scene data not sent to Events Editor until `_sceneXmlLoaded` — no spurious `garden_001` sends
- Composer: `saveHanimSrc` auto-saves XML immediately so avatar assignments persist
- Saturn I arc pipeline runs end-to-end: WP arrivals, zone audio, chorus, field ticks

---

## Key Architecture Decision (Day 55)

**EventCues are trigger-based, not time-based.** The timeline `t` value is authoring metadata for visual layout only — the Loader does not use it. Execution is driven entirely by `trigger`:

- `trigger="manual"` → fires on scene load
- `trigger="w1 arrive"` / `"w2 arrive"` / `"w3 arrive"` → fires at WP arrival
- `trigger="field E>0.6"` → stubbed, post Day 55

**Time-based firing** (music/dialogue sync) is deferred. The timeline will eventually have a clock that polls `_eventCues` against elapsed scene time. This requires a running timer in the Loader tied to scene start. **Design this before implementing** — the authoring model for mixing time-based and trigger-based cues needs a decision.

---

## Day 56 Primary Task: Timeline Clock Design + WP Trigger Polish

### Option A — Simple elapsed clock
- On Play, start `_sceneClockStart = Date.now()`
- Each second (or on `requestAnimationFrame`), check `_eventCues` for any cue whose `t <= elapsed` and `trigger="time"` (new trigger type) and hasn't fired yet
- Fire it, mark it fired
- Reset fired flags on Stop/Reset

### Option B — WP-relative time offsets
- `t` is offset in seconds from the WP arrival, not scene start
- `trigger="w1 arrive"` + `t=3` means "3 seconds after arriving at W1"
- Implemented as `setTimeout(fireCue, t * 1000)` inside `fireEventCuesForTrigger`

**Recommendation:** Option B first — it's simpler, works within the existing trigger architecture, and covers the music/dialogue sync case since dialogue is WP-locked. Option A (absolute timeline clock) is Saturn II+ work.

---

## Remaining Pre-Saturn II Tasks (updated)

| # | Item | Status |
|---|------|--------|
| 1 | cindy_hanim.x3d corruption | ✅ Fixed |
| 2 | EXPORT generation in _write_clip_nodes | ✅ Done |
| 3 | Composer IMPORT cultivar-aware | ✅ Done |
| 4 | Loader custom clips in timer map | ✅ Done |
| 5 | Preview page X_ITE 11.6.0 | ✅ Done |
| 6 | Events Editor UI in Composer | ✅ Done Day 54 |
| 7 | Six canonical expression slots in HAnim editor | 🔲 Deferred |
| 8 | Full-pose keyframe capture (all joints) | 🔲 Deferred |
| 9 | Loader reads EventCues and fires SAI | ✅ Done Day 55 |
| 10 | Face pipeline via Blender MCP | 🔲 Post-Saturn II |
| 11 | Field threshold triggers in EventCues | 🔲 Post Day 55 |
| — | Commit Day 54–55 changes to git | 🔲 Do at Day 56 start |
| — | Timeline clock design decision (Option A vs B) | 🔲 Day 56 |
| — | Rename `testssound` scene before Saturn II demo | 🔲 Low priority |

---

## Files to Upload Day 56

- `static/mccf_x3d_loader.html`
- `static/mccf_events_editor_prototype_2.html`
- `static/mccf_scene_composer.html`
- `scenes/testssound_scene.xml` — confirm EventCues round-trip is clean before starting

---

## Key Confirmed Facts (carry forward)

- X_ITE SAI timers: `enabled=true/false` only — `startTime`/`stopTime` do not work
- Viewpoint binding: `vpNode.isBound = true` — confirmed working, retry loop handles SAI timing
- `fireManualCues` one-shot guard: `window._manualCuesFiredFor` keyed to scene filename, cleared in `x3dFileChanged`
- `_parseSceneZoneData` called from `x3dFileChanged` (500ms delay) and optionally from `pbPlay` — both paths call `fireManualCues` but guard ensures only one fires per scene
- `canvas.browser.currentScene.getNamedNode()` may return null for 1–2 seconds after load event — always retry
- EventCues `trigger` strings are case-insensitive in `fireEventCuesForTrigger`
- WP name in trigger: `_stepWp.name || .id || .label` — whichever is populated by server arc step response
- `trackLabel` attribute now written to `<Cue>` elements in scene XML for named-track round-trip
- EXPORT is identity (`AS="WalkTimer"`), IMPORT adds suffix (`AS="WalkTimer_Cindy"`)
- `browser` object available in Loader as X_ITE SAI entry point via `canvas.browser`
- EventCues X3D file path: `static/x3d/<sceneName>.x3d`
- Scene XML path: `scenes/<sceneName>_scene.xml`
- postMessage bridge fully operational — no changes needed Day 56

---

*Day 54: Blender-style Events Editor layout, full postMessage bridge, live X3D viewport, EventCues round-trip confirmed.*
*Day 55: Loader EventCues pipeline wired end-to-end. Trigger-based execution confirmed working. Timeline authoring UI stable (empty tracks, rightward cue placement, clear-track button). Time-based firing deferred pending design decision.*
*Day 56: Design and implement WP-relative time offsets (Option B). Commit Days 54–55 to git. Assess Saturn II readiness.*
