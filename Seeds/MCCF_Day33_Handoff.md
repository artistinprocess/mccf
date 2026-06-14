# MCCF Day 33 Session Handoff
**Generated:** 2026-06-01 end of Day 33
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Expression export wired — hanim/export now writes expressions XML

`POST /hanim/export` previously discarded the `expressions[]` payload.
Now fully wired:

- New helper `_expressions_xml_path(hanim_src)` derives expressions path
  from avatar filename: `jack_hanim.x3d` → `static/avatars/jack_expressions.xml`
- New helper `_write_expressions_xml(path, expressions)` upserts
  `<Expression>` blocks into MCCFExpressions XML. Full AU vector written
  (all AUs, zeroes included) — complete state preserved for downstream
  consumers and future lerp work. Atomic write via `.tmp` + `os.replace()`.
- Export upgraded from dual-write to **triple-write**: X3D + cultivar XML +
  expressions XML. All three backed up (.bak) before write. Expressions
  failure aborts before touching other files.
- Response now includes `expressions_path` and `expressions_written`.
- Tested with curl — `test_happy` block written correctly, all 29 AU Weight
  entries present, zeroes included, existing AU displacement data preserved.

### 2. HAnim Editor — preset buttons replaced with XML-driven dropdown

The hardcoded Ekman preset buttons (Happy, Sad, Angry etc.) were
avatar-specific (Jin geometry) and broke for any other avatar.
Replaced with:

- **Load expression dropdown** — populated from the avatar's own
  `*_expressions.xml` on editor open. If no file exists or no expressions
  are saved, dropdown shows "— no expressions saved —". Unambiguous.
- **Load button** — applies selected expression's full AU weight vector
  to sliders and sends each weight to the morph driver via SAI.
- Status line below dropdown shows active AUs at non-zero weights.
- After `heSaveExpression()`, dropdown refreshes immediately and selects
  the just-saved expression.
- `_heExpressions` reset to `[]` on every editor open — disk is source
  of truth, not accumulated memory state.
- Save toast clarified: "Expression saved: name — export to persist"
  so the save→export workflow is unambiguous.

### 3. HAnim Editor — playback clips from X3D TimeSensors

Pre-existing animation clips (Walk, Run, Jump, Kick, Pitch, Yaw, Roll)
were invisible in the editor. Fixed:

- `GET /hanim/joints` now also scans the X3D tree for TimeSensor nodes
  and returns `clips: [{name, timerDEF, cycleInterval, loop, enabled}]`
  alongside joints. No new route needed.
- New **Playback panel** in pose tab — populated from `data.clips` when
  joints load. One button per TimeSensor. Click to play (sends
  `enableTimer` SAI message), click again to stop. `■ stop all` button.
  Active clip highlighted green.
- `heVpPlay` (viewport play button) was reloading the iframe (useless).
  Now sends `enableTimer` for the currently selected authoring clip.
- Tested: Walk, Run, Jump, Kick, Pitch, Yaw, Roll all fire correctly.

### 4. HAnim Editor — skin URL corruption fixed

On editor open, `he-skin-url` input was being set to `_hanimPath`
(the X3D file path). This propagated as `_heSkinPending`, causing export
to send the X3D path as `skin_url`, which the server tried to load as
an image texture — producing `avatars/avatars/cindy_hanim.x3d` double-
prefix errors and clobbering the actual skin on every export.

Fixes:
- `openHAnimEditor`: skin URL input now set to `''` on open
- `heResetSkin`: clears to `''` not `_hanimPath`
- `heSkinUrlChanged`: guards against `.x3d` extension
- `heApplySkinUrl`: rejects `.x3d` files with clear error toast
- `heExport` (both instances): `skin_url: _heSkinPending || null`
  — server receives null when no skin is pending and leaves texture alone

### 5. HAnim Editor — head group rotation fixed

Clicking the "head" group button was switching to the face tab and
returning early — rotation sliders (which live in pose tab) were never
connected to skullbase. Head group now behaves like all other body
groups: stays on pose tab, selects skullbase as primary joint, coupled
neck vertebrae (vc1, vc2, vc3) follow at reduced ratios.
Only "face" group switches to the face tab.

### 6. HAnim Editor — pre-stored clips load from cultivar

`loadForm()` never loaded `behavior_clips` from the cultivar XML into
`_heClips`. The pose tab clip dropdown always started with only
"Default". Fixed — `loadForm` now maps `behavior_clips` into `_heClips`
objects so previously exported clips appear on editor open.

---

## Known Issues / Start Day 34 Here

### Priority 1 — Pose slider granularity

Rotation sliders are too coarse. Moving a slider a small amount sends
the joint from 90° to 0° — unusable for keyframe animation authoring.

Root cause: sliders are integer `-180` to `+180` degrees mapped directly
to `angleDeg`. A single pixel of movement = 1°+, which is too large for
fine posing.

Fix options (pick one or combine):
  A) Add a **fine mode toggle** — when active, sliders cover ±30° instead
     of ±180°, giving 6× more precision per pixel.
  B) Replace angle slider with a **numeric input + ± step buttons**
     (e.g. 0.5° per click).
  C) Add a **multiplier selector**: 1x / 0.5x / 0.1x applied to slider
     output before sending to SAI.

Recommendation: option A (fine mode toggle) — one button, no UI clutter,
preserves the slider feel.

### Priority 2 — Test expressions and clips on Jack

All Day 33 testing was on Cindy. Jack uses global-index morph mode
(monolithic skin mesh) vs Cindy's segment mode. Need to verify:
- Expression export and dropdown load work for Jack
- Morph driver fires correctly for Jack expressions
- Playback clips (if any) appear in Jack's playback panel
- AU displacement tuning still needed (JawDrop too aggressive,
  LipCornerPuller too subtle — see Day 32 handoff)

### Priority 3 — Static pose baking (rest pose export)

Currently there is no way to save a static joint pose as the avatar's
default starting position. Export writes OrientationInterpolator keyframe
data that only plays when a TimeSensor is enabled. The avatar always
loads in its original rest pose.

Two options:
  A) **Bake joint rotations into X3D** — write current slider values as
     `rotation` attribute defaults on HAnimJoint nodes in the X3D file.
     True rest pose change. Requires XML parse + joint attribute update.
  B) **Auto-play zero-duration pose clip** — export a looping 0s clip
     with the pose keyframe and enable its timer on scene load.

Option A is architecturally correct. Option B is a workaround but simpler.

### Priority 4 — Expression authoring: author Ekman set for Cindy

`test_happy` is the only expression in `cindy_expressions.xml`.
Need to author the full working set:
  neutral, content, happy, sad, angry, fearful, curious, surprised

Workflow: open HAnim Editor → face tab → dial sliders → save →
check status bar says "export to persist" → go to export tab → export.
Verify each expression appears in dropdown on next editor open.

### Priority 5 — Expression authoring: same for Jack

After Cindy's set is confirmed working, repeat for Jack.

### Priority 6 — Wire expression lerp to phi/epsilon (Day 33 original P2)

Deferred. Once expressions are authored:
- phi/epsilon maps to expression name
- Look up AU weight vector from expressions XML
- Lerp from current AU weights to target AU weights
- Send updated weights via setDisplacerWeight messages

ExpressionState element:
  `<ExpressionState current="content" target="curious" lerp="0.3"/>`

### Priority 7 — Consolidate avatar pipeline (Day 33 original P3)

`python3 mccf_avatar_pipeline.py input.x3d AvatarName`

Deferred from Day 33. One-command pipeline for any Blender avatar.

---

## Architecture Notes (updated Day 33)

### Expression save vs export — two-step workflow

**Save** (`heSaveExpression`): writes to `_heExpressions[]` in memory.
  Appears in dropdown immediately. Does NOT touch disk.

**Export** (`heExport`): sends `_heExpressions[]` to server via
  `POST /hanim/export`. Server writes to `*_expressions.xml`.
  Survives browser reload. Status bar says "export to persist" as reminder.

On editor open: `_heExpressions` reset to `[]`, then reloaded from
`*_expressions.xml`. Disk is always source of truth.

### Pose export — what it does and doesn't do

Export writes `OrientationInterpolator` + `TimeSensor` nodes into the
X3D file for each authored clip. These are **playable animations**, not
static poses. The avatar always loads in its original rest pose.
Static pose baking is not yet implemented (see Priority 3 above).

### Playback clips vs authoring clips

**Playback clips** (pose tab, top panel): read from X3D TimeSensor nodes
  via `/hanim/joints` response. These are pre-existing animations baked
  into the X3D file. Play/stop via SAI enableTimer. Read-only in editor.

**Authoring clips** (pose tab, clip dropdown): `_heClips[]` array.
  New keyframe sequences being authored. Exported as new
  OrientationInterpolator nodes. Editable in editor.

---

## Files Changed Day 33

| File | Location | Notes |
|------|----------|-------|
| mccf_api.py | project root | Expression XML write, hanim/joints clips, skin_url null fix |
| mccf_character_creator.html | static/ | Expression dropdown, playback panel, skin URL fix, head group fix, clip load fix |

---

## Reference Documents (upload at session start)

- mccf_api.py — paste from local disk
- mccf_character_creator.html — paste from local disk
- cindy_expressions.xml — paste from local disk
- jack_expressions.xml — paste from local disk
- cindy_hanim.x3d — paste from local disk (for pose baking work)
- jack_hanim.x3d — paste from local disk (for Jack testing)
- MCCF_HAnim_Editor_Spec.md
- MCCF_HAnim_Behavior_Activation_Spec.md
