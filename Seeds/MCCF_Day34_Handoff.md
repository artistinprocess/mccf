# MCCF Day 34 Session Handoff
**Generated:** 2026-06-02 end of Day 34
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Pose slider granularity fixed

Angle slider (`∠`) was `step=1` integer — too coarse for fine posing.

- Changed to `step=0.5` coarse / `step=0.1` fine
- **Fine mode toggle** button added to rotation panel button row
- Toggles via `hePoseToggleFine()` — changes step only, never touches min/max/value (range-swap approach was tried first and broke the slider by triggering browser clamping)
- All angle reads changed from `parseInt` to `parseFloat` throughout (hePoseRotChanged, hePoseMirror, hePoseAddKeyframe)
- Val display shows one decimal place (`42.5°`)

### 2. Group button slider reset fixed

Clicking a group button (L Arm, R Leg, etc.) did not reset sliders to zero when switching groups. Fixed: `_hePoseSetSliders([0,0,1,0])` now fires unconditionally at the top of `heRegionSelect` before joint resolution.

### 3. Jack loaded and tested — wire-joints infrastructure built

Jack (`jack_hanim.x3d`) has 175 HAnimJoint nodes, full skinCoordIndex/skinCoordWeight — completely rigged — but zero OrientationInterpolators, TimeSensors, or ROUTEs. Face morphs work (different path — Displacer nodes). Body pose did not work.

Built `POST /hanim/wire-joints`:
- Scans all HAnimJoint DEFs
- Generates stub TimeSensor + OrientationInterpolator + ROUTEs for each joint
- **keyValue = joint's actual rest rotation** (not identity — identity caused scissor hands by overriding Blender rest pose on scene load)
- Skips already-wired joints (safe to re-run)
- Atomic write with .bak
- `⚡ wire joints` button in editor statusbar — appears when avatar has no TimeSensors

### 4. SAI setJointRotation handler updated

Direct `node.rotation = SFRotation(...)` write doesn't update skin mesh in X_ITE HAnim — deformer only responds through the ROUTE chain. Updated preview page handler:
- Strategy 1: find `WireInterp_<jointDEF>`, set keyValue to target rotation at both keys, fire `set_fraction(0)` to flush ROUTE
- Strategy 2 fallback: direct rotation write for non-HAnim scenes

### 5. normalize-joints endpoint built (then scope-limited — see Known Issues)

Built `POST /hanim/normalize-joints` with full `_BLENDER_TO_HANIM` mapping table derived from ISO/IEC 19774 / X3D spec enumeration. Covers all Blender→HAnim 2.0 joint name mappings for spine, legs, arms, hands, fingers.

Also built:
- `⚙ normalize` button — always visible in editor statusbar
- Strip of stale WireTimer_*/WireInterp_* nodes on normalize (so re-wiring is clean)
- Wire button re-appears after normalize completes

**However:** normalize-joints is the wrong abstraction for already-rigged models. See Known Issues.

---

## Known Issues / Start Day 35 Here

### Priority 1 — Jack body pose still not working (restore from backup first)

Jack's X3D was modified by normalize-joints during Day 34 testing, producing scissor hands. The endpoint renamed joint DEFs but the skin weights were baked to Blender's bone orientations — renaming without retargeting breaks the skinning.

**Immediate action on Day 35 start:**
```bash
cp static/avatars/jack_hanim.x3d.bak static/avatars/jack_hanim.x3d
```
This restores Jack to his original Blender-exported state. Face morphs will work again.

### Priority 2 — Avatar pipeline (replaces normalize-joints approach)

**Core insight from Day 34:** The normalize-joints endpoint patches a file that's already wrong. Renaming Blender bone DEFs to HAnim 2.0 names without retargeting the rest pose orientations breaks skinning. The X3D geometry and skin weights were baked to Blender's coordinate conventions and cannot be fixed by text substitution.

**The correct architecture:**

`mccf_avatar_pipeline.py input.x3d AvatarName`

The pipeline script should:
1. Accept a Blender-exported X3D as input
2. Detect naming convention (Blender, Mixamo, BVH, etc.) by heuristic
3. **Write a joint name mapping into the cultivar metadata** — maps avatar's actual joint names to HAnim 2.0 equivalents
4. Wire joints (with rest rotations as keyValues — Day 34 fix)
5. The editor, group presets, SAI handler, and wire-joints all read the cultivar mapping at runtime

**The X3D is never renamed. The mapping is a translation layer in the cultivar, not surgery on the file.**

This is the open-source interoperability principle: standards compliance is a translation layer. The Blender→glTF→X3D pipeline discards HAnim naming. We absorb that at ingest, not at runtime.

### Priority 3 — Group presets don't work for Jack

Group buttons (L Leg, R Arm, etc.) use HAnim 2.0 names (`l_hip`, `l_shoulder`, etc.) in `_HE_GROUP_PRESETS`. Jack's joints are still Blender names (`thigh.L`, `shoulder.L`). After the pipeline is built and cultivar mapping exists, `_heResolveJoint()` should consult that mapping.

Current state: `_heResolveJoint()` is exact-match only (fuzzy alias table was removed in Day 34 as part of normalize approach). This is correct — the resolver should be exact-match against whatever names are in the loaded avatar, and the preset names should match via the cultivar map.

### Priority 4 — Author Ekman expression set for Cindy

`test_happy` is the only expression in `cindy_expressions.xml`. Need to author the full working set. This is unblocked and can be done independently of Jack work.

Workflow: open HAnim Editor → face tab → dial sliders → save → export tab → export. Verify each expression appears in dropdown on next editor open.

Expressions to author: `neutral`, `content`, `happy`, `sad`, `angry`, `fearful`, `curious`, `surprised`

### Priority 5 — Expression authoring for Jack (after pipeline)

After Cindy's set is confirmed and Jack's pipeline pass is done.

### Priority 6 — Wire expression lerp to phi/epsilon

Deferred. Once expressions are authored:
- phi/epsilon maps to expression name
- Look up AU weight vector from expressions XML
- Lerp from current AU weights to target
- Send via setDisplacerWeight messages

### Priority 7 — Static pose baking (rest pose export)

No way to save a static joint pose as avatar's default starting position. Export writes OrientationInterpolator keyframe data — playable animations, not rest pose. See Day 33 handoff for options A and B.

---

## Architecture Notes (updated Day 34)

### Why normalize-joints is wrong for rigged models

Blender exports joints with bone orientations baked into the rotation attributes and skin weights. HAnim 2.0 defines different canonical orientations for the same anatomical joints. You cannot fix this mismatch by renaming DEF attributes — the skin weights reference the original orientations implicitly. The correct fix is either:

- **At export time** in Blender: apply HAnim rest pose before export (requires Blender rigging expertise, hours of work per avatar)
- **At pipeline ingest time** in MCCF: record the name mapping in cultivar metadata and translate at runtime

The second approach is correct for an open-source system. We don't own Blender. We don't own glTF. We absorb whatever naming the exporter produced and translate it. Standards compliance is a translation layer, not a surgery.

### Wire-joints rest rotation keyValues (Day 34 fix)

Stub OrientationInterpolators must use the joint's actual `rotation` attribute as keyValue, not identity `0 0 1 0`. Identity overrides Blender rest pose on scene load, collapsing the skeleton. Rest rotation as keyValue makes the stub a pass-through — no visual change on load.

### SAI setJointRotation architecture

Two strategies in the preview page handler:
1. **WireInterp path** (wired avatars): set `WireInterp_<DEF>.keyValue` to target rotation at both keys, fire `set_fraction(0)` to flush ROUTE chain → skin deformer updates
2. **Direct path** (fallback): `node.rotation = SFRotation(...)` — works for non-skin-bound nodes

The ROUTE chain is required for skin deformation in X_ITE. Direct rotation writes on HAnimJoint do not trigger the deformer.

---

## Files Changed Day 34

| File | Location | Notes |
|------|----------|-------|
| mccf_api.py | project root | wire-joints (rest rot keyValues), normalize-joints, SAI handler fix |
| mccf_character_creator.html | static/ | Fine mode toggle, slider reset on group select, normalize/wire buttons |

---

## Reference Documents (upload at session start)

- mccf_api.py — paste from local disk
- mccf_character_creator.html — paste from local disk
- cindy_expressions.xml — paste from local disk (for expression authoring)
- MCCF_HAnim_Editor_Spec.md
- MCCF_HAnim_Behavior_Activation_Spec.md

---

## Day 35 Opening Sequence

1. `cp static/avatars/jack_hanim.x3d.bak static/avatars/jack_hanim.x3d` — restore Jack
2. Paste mccf_api.py and mccf_character_creator.html from local disk
3. Decide: pipeline first (unblocks Jack, group presets, expression lerp) or Cindy Ekman expressions first (unblocked now, delivers visible value)
