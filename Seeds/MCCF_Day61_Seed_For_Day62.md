# MCCF Day 61 Session Handoff → Day 62

## Status: Named VP UI, Camera Preview, Avatar Persistence Fixed, Behavior Spec Extended

**GitHub baseline:** Commit `c75c232` (master) — Day 60 baseline. Day 61 files not yet committed.
**Rule:** Author does not edit code. Claude delivers complete files only.
**Critical rule:** Always work from the file the author uploads. Never use a cached or previously generated version as a base. Confirm fixes by having the author upload the file back before proceeding.

---

## Reference Documents — Load These First

| Document | Location | Read when |
|---|---|---|
| `MCCF_Events_Editor_Architecture.md` | `docs/` | Any new event track, cue type, or vessel |
| `MCCF_Camera_System_Spec_v1.2.md` | `docs/` | Any camera cue, VP_Free, orientation math |
| `MCCF_HAnim_Behavior_Activation_Spec.md` | `docs/` | Any behavior clip, field-driven animation, authored override |
| `X3D_KNOWN_ISSUES.md` | `docs/` | Any X3D/X_ITE rendering or SAI issue |

---

## Files Changed Day 61

| File | Key Changes |
|---|---|
| `static/mccf_events_editor_prototype_2.html` | Named VP UI (§Task 2); camera preview system (§Task 3 partial); `applyShotPreset` clears `cue.viewpoint` on runtime shots (Day 60 bug fix) |
| `static/mccf_scene_composer.html` | Avatar persistence fix: step 7 now unconditionally patches `hanim_src` from XML; cultivar load no longer clobbers XML `hanim_src` with empty string |
| `docs/MANIFEST.md` | Day 61 date; Seeds section clarified (local only, not pushed to GitHub); `MCCF_Scene_Animation_Spec.md` added to docs list |
| `docs/X3D_KNOWN_ISSUES.md` | Day 60 camera section added: D60-1 (Viewpoint output-only fields), D60-2 (zero-angle black viewport), D60-3 (-Z look-at convention) |
| `docs/MCCF_HAnim_Behavior_Activation_Spec.md` | v1.1.0: §6a Fallback Principle, §6b Authored Override (`_agentAuthoredClip`), §6c Persistence/Accrual notes; villain task added; implementation table updated to 11 tasks |

---

## Confirmed Working Day 61

- **Named VP UI:** Shot Type dropdown has new "Named Viewpoint" group with "Bind Named VP" option. Selecting it shows VP name text input, hides all framing sliders, writes `cue.viewpoint`, clears `cue.shot`. Mutually exclusive with runtime shot path. `applyShotPreset()` now clears `cue.viewpoint` when switching to any runtime shot (Day 60 bug root cause fixed).
- **Camera preview:** Selecting a camera cue in the Events Editor immediately binds VP_Free in the embedded X_ITE viewport using identical math to the Loader (`_prevComputeCamPos` + `_prevLookAtOrientation`). Fires on cue select, shot type change, and all framing slider drags. Status label shows `PREVIEW — <shot> / <subject>`. Imprecise until Composer sends real WP positions via `mccf_scene_data`; uses proportional fallback positions until then.
- **Avatar persistence:** `hanim_src` now survives scene reload in Scene Composer. Two-part fix: (a) step 7 always patches `hanim_src` from XML onto `placedAgents` regardless of whether server already populated them; (b) cultivar API load only overwrites `hanim_src` on `placedAgents` if the cultivar value is non-empty.
- **Chorus rendering:** Was intermittently not displaying — confirmed Firefox session issue, not a code bug. Chorus fires and displays correctly after browser restart.
- **Housekeeping docs:** MANIFEST.md and X3D_KNOWN_ISSUES.md updated and committed to `docs/`.

---

## Key Architecture Facts (carry forward)

### Named VP vs Runtime Shot — mutual exclusion
- `cue.viewpoint` set → baked named VP path → Loader calls `_bindNamedViewpoint()`
- `cue.shot` set → runtime path → Loader calls `_executeStaticCameraShot()` or `_executeMoveShot()`
- Both must never be set simultaneously. `applyShotPreset()` deletes `cue.viewpoint` on any runtime shot. Selecting "Bind Named VP" deletes `cue.shot` and all framing fields.
- VP_Free never appears in cue data. Never.

### Camera preview in Events Editor
- `_previewCameraShot()` in Events Editor drives `CAM_Free_Transform` + `VP_Free` in the Editor's own X_ITE instance (separate from Loader — no conflict).
- Math is identical to Loader: `_prevComputeCamPos` + `_prevLookAtOrientation` with -Z convention.
- Fires from: `selectCue()`, `applyShotPreset()`, `setCueProp()` on framing props, slider `oninput`.
- Skips silently if: viewport not loaded, cue is named VP, cue is agent-attached.
- Subject position uses `_prevResolveSubjectPos()` — proportional fallback until real WP data arrives from Composer.

### Avatar persistence fix
- Scene XML `hanim_src` is the authoritative source. Written by `saveHanimSrc()` and serialized by `_doExportSceneXML()`.
- Cultivar API `hanim_src` wins only if non-empty — empty string from server never clobbers XML value.
- Step 7 in scene load now uses if/else: builds full `placedAgents` entry if absent, patches `hanim_src`/`voice`/`position` if already present.

### Fallback Principle (behavior system)
- Field-driven clip selection is the default performer. Authored cues are the exception-handler.
- Parallel to dialog system: if no response is authored, LLM answers. If no clip is authored, field selects.
- `_agentAuthoredClip[safeName]` holds authored override with `expiresAt`. Checked first in `selectBehaviorClip()`. On expiry, field selection resumes automatically on next poll tick.

### Firefox / X_ITE performance
- Two X_ITE instances open simultaneously (Events Editor + Loader) causes GPU/memory pressure and sluggishness. Both maintain WebGL contexts and RAF loops in background tabs.
- Mitigation planned: lazy-load X_ITE in Events Editor (inject `<x3d-canvas>` only on explicit "Load Preview" click, destroy on tab switch). Character Creator has same issue.
- For now: restart Firefox if sluggishness appears. Do not keep both tabs active simultaneously during long sessions.

### Seeds — local only
- Session seed files live in `Seeds/` on local repo. Not pushed to GitHub.
- Seeds are session state. Stable architecture facts are promoted to `docs/` specs.
- `docs/` is the canonical reference. Seeds are the path that got there.

---

## Current Scene State (testssound_scene.xml as of end of Day 61)

```xml
<EventCues>
  <Cue track="camera" trackLabel="Camera" label="dutch Cindy" t="0" dur="4"
       trigger="w1 arrive" shot="dutch" subject="Cindy" transition="cut"
       distance="2.9" height="1.7" hAngle="0" vAngle="28" delay="0"/>
  <Cue track="camera" trackLabel="Camera" label="wide" t="4" dur="4"
       trigger="w2 arrive" shot="wide" subject="The Steward" transition="cut"
       distance="12" height="4.5" hAngle="28" vAngle="1" delay="1"/>
  <Cue track="camera" trackLabel="Camera" label="profile Cindy" t="8" dur="4"
       trigger="w3 arrive" shot="profile" subject="Cindy" transition="cut"
       distance="2.5" height="0.8" hAngle="-6" vAngle="24" delay="0"/>
</EventCues>
```

**Known authoring issues to fix in Day 62:**
- W2 wide cue: subject is "The Steward" — PATH 4 (stale start position) fires because The Steward is not the arc agent. Change subject to Cindy or The Witness.
- W1 dutch cue: `hAngle=0` puts camera directly behind Cindy. Adjust to ±20° with camera preview.
- W1 trigger: "w1 arrive" fires on first WP arrival which may be too late for an opening shot. Consider `scene start` trigger (deferred until animated camera work).
- W3 profile: vAngle=24 (looking up) at height=0.8 is an unusual framing — verify with preview.

---

## Day 62 Tasks (in order)

### Task 1 — Commit Day 61 files to GitHub
- `static/mccf_events_editor_prototype_2.html`
- `static/mccf_scene_composer.html`
- `docs/MANIFEST.md`
- `docs/X3D_KNOWN_ISSUES.md`
- `docs/MCCF_HAnim_Behavior_Activation_Spec.md`

### Task 2 — Camera framing refinement
Now that preview works, re-author all three cues:
- W2 wide: change subject to Cindy or The Witness (PATH 1 will fire correctly)
- W1 dutch: adjust hAngle to ±20° using preview
- Verify W3 profile framing
- Test `agent_eye` / `agent_side` shots — add a cue, verify Loader binds correct VP

### Task 3 — gLTF avatar test
- Load a gLTF file as an X3D Inline in a test scene
- Verify X_ITE converts it internally
- Check whether animation clips survive as SAI-addressable TimeSensor nodes
- If yes: `switchBehaviorTimer` can address them directly → unblocks HAnim Task 2

### Task 4 — HAnim Behavior Activation (implementation)
See `MCCF_HAnim_Behavior_Activation_Spec.md` §10 for full task list.
Start with Task 1 (`mccf_cultivar_lambda.py` — `<Behaviors>` parse/serialize).
Prerequisites: read spec §§4, 6a, 6b before writing any code.

### Task 5 — Phase 2 camera move shots
`_executeMoveShot(cue)` stub is in `_fireCameraEventCue` under `_MOVE_SHOTS`.
Implement orbit as first move shot: TimeSensor drives `CAM_Free_Transform` via
PositionInterpolator/OrientationInterpolator.
Composer needs to emit `CAM_Timer`, `CAM_PosInterp`, `CAM_OrientInterp` vessel nodes.

### Task 6 — Villain constitutional profiles (design session)
Design EBPS constitutional profiles for villain cultivars.
Source: literary mirrors of existing constitutionals (inverted regulation, same couplers).
See HAnim spec §10 Task 10 note. No code — design and cultivar XML authoring only.

### Task 7 — Chorus persistence / cross-scene accrual (design session)
Design `chorus_log` architecture and cross-scene context injection.
See HAnim spec §6c for framing. Requires: dialog persistence design first.

---

## Remaining Pre-Saturn II Tasks

| # | Item | Status |
|---|------|--------|
| 1 | MANIFEST.md update | ✅ Day 61 |
| 2 | X3D_KNOWN_ISSUES.md update | ✅ Day 61 |
| 3 | Named VP authoring UI in Events Editor | ✅ Day 61 |
| 4 | Camera preview in Events Editor viewport | ✅ Day 61 |
| 5 | Avatar persistence fix | ✅ Day 61 |
| 6 | Camera framing refinement / agent_eye test | 🔴 Day 62 Task 2 |
| 7 | Camera move shots — interpolated (Phase 2) | 🔴 Day 62 Task 5 |
| 8 | HAnim behavior activation (Tasks 1–9 in spec) | 🔴 Day 62 Task 4 |
| 9 | Villain constitutional profiles | 🔲 Day 62 Task 6 |
| 10 | Chorus persistence / cross-scene accrual | 🔲 Day 62 Task 7 |
| 11 | gLTF avatar test in X_ITE | 🔲 Day 62 Task 3 |
| 12 | Replace dummy Stage map with real scene data | 🔲 Saturn II |
| 13 | Scene-start trigger type | 🔲 Deferred (post animated camera) |
| 14 | Lazy-load X_ITE in Events Editor (performance) | 🔲 Deferred |
| 15 | X_ITE Playground / x3dom Editor buttons in Loader | 🔲 Deferred |

---

## Open Design Questions (carry forward)

- **Field-state triggers** (`field E>0.6` etc.) in Events Editor TRIGGERS list — stub entries only. Full implementation needs per-avatar, per-zone architecture. Deferred until semantic track design.
- **Scene-start trigger** — deferred until animated camera work is complete. Use X_ITE viewpoint menu for initial position in the interim.
- **Two X_ITE instances** — Events Editor + Loader open simultaneously causes Firefox memory pressure. Lazy-load fix deferred.
- **`_prevResolveSubjectPos` in Events Editor** — uses proportional fallback positions until Composer sends real WP x/z via `mccf_scene_data`. Preview accuracy improves automatically once that data is wired.
- **Chorus response** display intermittent — confirmed Firefox session issue. Restart browser if Chorus overlay doesn't appear.

---

## Documents Produced Day 61

| Document | Location | Status |
|---|---|---|
| `MCCF_HAnim_Behavior_Activation_Spec.md` | `docs/` | v1.1.0 — updated |
| `MANIFEST.md` | `docs/` | Updated Day 61 |
| `X3D_KNOWN_ISSUES.md` | `docs/` | Day 60 camera section added |
| System Architecture Specification | — | 🔲 Planned |
| User Guide (with screenshots) | — | 🔲 Planned |

---

*Day 55: Loader EventCues pipeline wired.*
*Day 56: Export race fixed, WP name format confirmed, set_bind fix applied.*
*Day 57: Full EventCues pipeline confirmed. Trigger name mismatch fixed. Arc export mangling fixed. X_ITE pinned to 11.6.0. Camera fires. Jump parked.*
*Day 58: TELEPORT fix confirmed. Camera shot designer built in Events Editor. FOV cone on stage canvas. First camera cue firing confirmed. WP trigger candidate bug identified.*
*Day 59: BUG 1 fixed. Full camera schema serialized. VP_Free added to Composer export. Camera routing partially working.*
*Day 60: Camera routing rewritten (baked/runtime split). CAM_Free_Transform pattern confirmed. _lookAtOrientation -Z fix. Static computed shots verified in live playback. Composer exports to server. docs/ folder created. All committed.*
*Day 61: Named VP UI. Camera preview (live slider feedback). Avatar persistence fixed (hanim_src round-trip). Behavior spec extended: Fallback Principle, authored override, persistence/accrual notes, villain task. Firefox X_ITE memory pressure noted.*
