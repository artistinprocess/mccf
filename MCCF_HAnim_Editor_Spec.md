# MCCF HAnim Editor Specification
**Version:** 1.0.0
**Date:** 2026-05-25
**Status:** Draft for Review — W3D Consortium H-Anim Working Group
**Authors:** Len Bullard, Claude Sonnet 4.6 (Tae)
**Repo:** https://github.com/artistinprocess/mccf — branch `master`

---

## 1. Overview

The MCCF HAnim Editor is a browser-based authoring tool integrated as a tab within the
MCCF Character Creator. It enables authors to create, preview, and export behavioral
animation clips for LOA 4 H-Anim figures without requiring 3D modeling expertise or
direct X3D file editing.

The editor operates on the Jin/Cindy figure family (LOA 4, UV-atlas-textured,
FACS-displacer-equipped) and exports outputs consumed directly by the MCCF playback
pipeline. It produces two artifacts simultaneously on every save:

- An updated HAnim X3D file (`static/avatars/<name>_hanim.x3d`) with `TimeSensor`,
  `OrientationInterpolator`, `HAnimDisplacer`, and `ROUTE` nodes for each authored clip
- An updated cultivar XML file (`cultivars/cultivar_<name>.xml`) with a `<Behaviors>`
  element and a `<Receptivity>` element reflecting the authored clip table

This dual-write contract is the architectural invariant that prevents the
behavioral-state / cultivar-XML desynchronization described in the MCCF Behavior
Activation Specification (v3.1.0, Section 8.4).

### 1.1 Design Principles

**Ease first.** Authors should be able to create a usable idle pose variation in under
five minutes without reading documentation. The interface surface visible at any moment
should be minimal.

**Fidelity through iteration.** The editor does not attempt to replace a professional
3D animation pipeline. It provides a sufficient tool for the MCCF behavioral vocabulary:
idle variations, directed gestures, locomotion cycles, and facial expressions. Realism
is a mesh and texture problem, not an editor problem.

**Live feedback always.** Every parameter change — joint rotation, displacer weight,
texture swap — is reflected in the embedded X_ITE viewport within one frame. There is
no "apply" step between authoring and preview.

**X_ITE SAI as the only write path.** All parameter writes to the live scene use the
X_ITE Scene Access Interface (`enabled = true/false`, direct property assignment on
named nodes). No intermediate serialization formats.

**Portable behaviors.** Animation clips are stored as joint-relative rotations, not
world-space transforms. A clip recorded on Cindy can be applied to any LOA 4 figure
with the same joint naming convention without modification.

---

## 2. Architecture

### 2.1 Integration Point

The HAnim Editor is Tab 3 of the Character Creator (`mccf_character_creator.html`),
activated when a cultivar with a valid `hanim_src` field is selected. The tab label
reads **HAnim Editor**.

The tab hosts:
- A full-height embedded X_ITE viewport (left 60% of panel)
- A three-section authoring panel (right 40%): Skin, Pose/Gesture, Face

### 2.2 Data Flow

```
Character Creator selects cultivar
        ↓
HAnim Editor loads:
  - cindy_hanim.x3d (or named hanim_src) via X_ITE Inline
  - cultivar_<name>.xml via GET /cultivars/<name>
  - existing <Behaviors> and <Receptivity> into editor state
        ↓
Author edits skin / poses / expressions
        ↓
Save (per-tab or unified)
        ↓
POST /hanim/export → writes updated X3D + cultivar XML atomically
```

### 2.3 Server Endpoints (new)

```
POST /hanim/export
  body: { cultivar, hanim_src, clips[], displacers[], skin_url, receptivity }
  writes: static/avatars/<hanim_src>, cultivars/cultivar_<cultivar>.xml
  returns: { status, hanim_path, cultivar_path, clips_written, displacers_written }

GET /hanim/joints?src=<hanim_src>
  returns: [ { name, def, center, parent } ]  — joint hierarchy for UI

GET /hanim/displacers?src=<hanim_src>
  returns: [ { def, name, weight, au_name, has_data } ]  — displacer inventory
```

### 2.4 State Model

The editor maintains an in-memory session state object:

```javascript
{
  cultivar:    "Cindy",
  hanim_src:   "cindy_hanim.x3d",
  skin_url:    "Jin.png",
  clips: [
    {
      name:          "Default",
      timerDEF:      "DefaultTimer",
      cycleInterval:  6.0,
      loop:           true,
      priority:       0,
      keyframes: [
        { t: 0.0,  joints: { "hanim_skullbase": [0,0,1,0], ... } },
        { t: 0.5,  joints: { ... } },
        { t: 1.0,  joints: { ... } }
      ],
      cv_conditions: { E_min: null, E_max: null, ... }
    }
  ],
  expressions: [
    {
      name:    "Neutral",
      au_weights: { "JinBlink": 0.0, "JinJawDrop": 0.0, ... }
    }
  ],
  receptivity: { E: 1.0, B: 1.0, P: 1.0, S: 1.0 },
  dirty: false
}
```

---

## 3. Tab 1 — Skin

### 3.1 Purpose

Replace the figure's texture atlas with an alternate image. The UV coordinate arrays
in the HAnim X3D file are not modified; only the `url` field on the single
`ImageTexture` node (`JinLOA4TextureAtlas` or equivalent DEF) is changed.

### 3.2 Current Atlas Layout

The Jin figure uses a single 256×256 RGBA atlas (`Jin.png`) with the following
approximate region assignments (UV space, origin bottom-left):

| Region (approx UV) | Content |
|--------------------|---------|
| (0.0–0.5, 0.5–1.0) | Face, neck, scalp |
| (0.5–1.0, 0.5–1.0) | Hair detail |
| (0.0–0.5, 0.25–0.5) | Torso front |
| (0.5–1.0, 0.25–0.5) | Torso back / clothing |
| (0.0–0.25, 0.0–0.25) | Hands / feet |
| (0.25–0.5, 0.0–0.25) | Accessories |
| (0.5–0.75, 0.0–0.25) | Leg detail |
| (0.75–1.0, 0.0–0.25) | Arm detail |

This layout is provided so AI image generation prompts can target specific atlas regions.
An author wishing to replace the face region should generate a 256×256 image with the
face rendered in the top-left quadrant matching the above mapping.

### 3.3 UI

- **Current skin** — thumbnail of active atlas, filename label
- **Drop zone** — drag-and-drop or file picker for replacement PNG/JPG
- **Atlas overlay toggle** — renders a semi-transparent UV grid over the viewport
  figure, colour-coded by body region, to aid replacement image authoring
- **Preview** — immediately applies replacement to live X_ITE viewport via SAI:
  `textureNode.url = [newUrl]`
- **Reset** — restores original atlas URL

### 3.4 AI Skin Generation Guidance (informational panel)

A collapsible panel displays guidance for generating compatible replacement skins:

> "Generate a 256×256 image. Place the face in the upper-left quadrant
> (approximately 0–128px × 128–256px from top). The UV layout is fixed; the image
> must match the atlas region assignments above. Anime-style flat shading works best
> with the current mesh density."

### 3.5 Export

Skin URL is included in the `/hanim/export` payload. The server copies the replacement
image to `static/avatars/` and updates the `url` field in the HAnim X3D file. The
original atlas is preserved as `<name>_atlas_backup.png`.

---

## 4. Tab 2 — Pose / Gesture (Body Animation)

### 4.1 Purpose

Author named animation clips by manipulating joint rotations on the live figure,
recording keyframes, and assembling them into named `TimeSensor`-driven behavior clips
compatible with the MCCF behavior activation system.

### 4.2 Joint Hierarchy Panel

A collapsible tree display of the LOA 4 joint hierarchy, matching the H-Anim 2.0
specification joint naming convention. Joints are grouped by body region:

- **Spine** — humanoid_root, sacroiliac, vl5, vl4, vl3, vl2, vl1, vt12 … vt1, vc7 … vc1, skullbase, skull
- **Left arm** — l_shoulder, l_elbow, l_radiocarpal, l_midcarpal_*, l_carpometacarpal_*
- **Right arm** — (mirror of left)
- **Left leg** — l_hip, l_knee, l_talocrural, l_talocalcaneonavicular, and foot joints
- **Right leg** — (mirror of left)

Clicking a joint in the tree:
1. Highlights the joint in the viewport (yellow sphere indicator)
2. Opens the joint rotation controls (see 4.3)
3. Records that joint as "touched" for the current keyframe

Cindy's figure has 146 `HAnimJoint` nodes (LOA 4 complete). The editor does not require
all joints to be explicitly keyed in every clip — unkeyed joints inherit the figure's
rest pose (`0 0 1 0` identity rotation in the current export).

### 4.3 Joint Rotation Controls

For the selected joint, the panel shows:

- **Rotation display** — current `SFRotation` value (axis-angle: x, y, z, angle in
  degrees)
- **Axis-angle sliders** — three sliders for x/y/z axis components (-1.0 to 1.0) and
  angle (-180° to +180°)
- **Anatomical presets** — where anatomically meaningful, preset buttons for common
  rotations: "flex", "extend", "abduct", "adduct" (calibrated per joint from the Jin
  figure's resting geometry)
- **Mirror** — copies rotation to the contralateral joint (e.g. l_hip → r_hip,
  negating the axis-Z component for bilateral symmetry)
- **Reset** — returns joint to rest pose

Each slider change writes directly to the joint node via SAI:
```javascript
jointNode.rotation = new X3D.SFRotation(ax, ay, az, angleRadians);
```

### 4.4 Keyframe Recording

A timeline bar at the bottom of the viewport shows the current clip's keyframes as
draggable markers on a 0.0–1.0 normalized time axis.

- **Add keyframe** — records the current pose of all touched joints at the current
  timeline position. Stores as `{ t, joints: { jointName: [ax,ay,az,angle] } }`.
- **Delete keyframe** — removes selected keyframe marker
- **Drag keyframe** — repositions in time, re-sorts the key array
- **Preview playback** — runs the `TimeSensor` live in X_ITE at authored
  `cycleInterval`. The `OrientationInterpolator` keyValues are synthesized from the
  recorded keyframes and written to the scene via SAI before playback starts.

### 4.5 Clip Management

Above the timeline, a clip list panel:

- **Clip name** — editable text field (becomes `TimeSensor DEF` suffix, e.g. "Walk" →
  `WalkTimer`)
- **Cycle interval** — seconds (float, 0.1–60.0)
- **Loop** — checkbox (maps to `TimeSensor.loop`)
- **Priority** — integer; higher priority clips take precedence in
  `selectBehaviorClip()` when multiple clips match the CV conditions
- **CV conditions** — four channel range pairs (E_min/E_max, B_min/B_max, P_min/P_max,
  S_min/S_max); empty = always eligible. These map directly to the `<Clip>` element
  in the `<Behaviors>` cultivar XML block.
- **New clip** — initializes a new clip with identity keyframes at t=0 and t=1
- **Duplicate clip** — copies current clip with suffix " (copy)"
- **Delete clip** — removes clip from session state (does not affect saved file until
  export)

### 4.6 Behavior Timer DEF Convention

Timer DEF names follow the convention established in the MCCF playback system:

```
{ClipName}Timer
```

Examples: `DefaultTimer`, `WalkTimer`, `RunTimer`, `JumpTimer`, `KickTimer`,
`PitchTimer`, `YawTimer`, `RollTimer`.

The editor enforces this convention: if the author names a clip "Sit", the DEF becomes
`SitTimer`. The loader's `_behaviorTimerMap` is built by scanning for nodes matching
this pattern at placement time.

### 4.7 Portable Behavior Clips

Clips are stored as joint-relative rotations using the H-Anim 2.0 standard joint names
(`hanim_l_hip`, `hanim_skullbase`, etc.). This makes clips figure-independent: a "nod"
clip authored on Cindy can be applied to any LOA 4 figure with the same joint naming
without modification.

On export, the editor serializes each clip as:

```xml
<TimeSensor DEF="WalkTimer" cycleInterval="2.5" loop="true" enabled="false"/>
<OrientationInterpolator DEF="Walk_hanim_l_hip_RotationInterpolator"
    key="0 0.25 0.5 0.75 1"
    keyValue="0 0 1 0, 1 0 0 0.3, 0 0 1 0, 1 0 0 -0.3, 0 0 1 0"/>
<!-- ... one OrientationInterpolator per keyed joint ... -->
<ROUTE fromNode="WalkTimer" fromField="fraction_changed"
       toNode="Walk_hanim_l_hip_RotationInterpolator" toField="set_fraction"/>
<ROUTE fromNode="Walk_hanim_l_hip_RotationInterpolator" fromField="value_changed"
       toNode="hanim_l_hip" toField="rotation"/>
```

ROUTEs are always written last in the X3D file (architecture invariant).

---

## 5. Tab 3 — Face (Displacer / Expression Authoring)

### 5.1 Purpose

Author named facial expressions by adjusting `HAnimDisplacer` weights on the live
figure. Expressions are named, saveable, and can be assigned as behavior-clip entry/exit
states or as dwell-time expressions in future waypoint authoring.

### 5.2 FACS Action Unit Inventory

The ManyClocks reference implementation provides the following Jin-specific FACS AU
displacers, confirmed working in X_ITE via `weight` field assignment (0.0–1.0):

| DEF Suffix | FACS Approximate | Description |
|------------|-----------------|-------------|
| JinBlink | AU46 | Wink / blink |
| JinBrowLowerer | AU4 | Brow lowerer |
| JinCheekPuffer | AU33 | Cheek puffer |
| JinCheekRaiser | AU6 | Cheek raiser |
| JinChinRaiser | AU17 | Chin raiser |
| JinDimpler | AU14 | Dimpler |
| JinEyesClosed | AU43/45 | Eye closure |
| JinInnerBrowRaiser | AU1 | Inner brow raiser |
| JinJawDrop | AU26/27 | Jaw drop |
| JinLidDroop | AU41 | Lid droop |
| JinLidTightener | AU7 | Lid tightener |
| JinLipCornerDepressor | AU15 | Lip corner depressor |
| JinLipCornerPuller | AU12 | Lip corner puller (smile) |
| JinLipFunneler | AU22 | Lip funneler |
| JinLipPressor | AU24 | Lip pressor |
| JinLipPuckerer | AU18 | Lip puckerer |
| JinLipsPart | AU25 | Lips part |
| JinLipStretcher | AU20 | Lip stretcher |
| JinLipSuck | AU28 | Lip suck |
| JinLipTightener | AU23 | Lip tightener |
| JinLowerLipDepressor | AU16 | Lower lip depressor |
| JinNasolabialDeepener | AU11 | Nasolabial deepener |
| JinNoseWrinkler | AU9 | Nose wrinkler |
| JinOuterBrowRaiser | AU2 | Outer brow raiser |
| JinSlit | AU44 | Eye slit |

The `coordIndex` and `displacements` arrays for each displacer are defined in the
source HAnim file. The editor does not modify these arrays; it only modifies the
`weight` field (0.0–1.0) via SAI.

### 5.3 Expression Authoring UI

**Face panel layout:**

- **Expression name** — text field at top of panel (e.g. "Curious", "Satisfied",
  "Wary"). Expressions are named independently of FACS AU nomenclature.
- **AU grid** — each FACS AU displayed as a labelled slider (0.0–1.0) with a small
  preview icon showing the isolated AU at weight=1.0.
  - Slider change writes immediately: `displacerNode.weight = value`
  - Multiple AUs can be active simultaneously; the mesh responds to the
    superposition of all active displacements.
- **Ekman presets** — one-click preset buttons for the six basic expressions
  (Neutral, Happy, Sad, Angry, Fearful, Disgusted, Surprised) with pre-calibrated
  AU weight combinations for the Jin figure:

  | Preset | Primary AUs (Jin weights) |
  |--------|--------------------------|
  | Neutral | all 0.0 |
  | Happy | JinLipCornerPuller 0.8, JinCheekRaiser 0.6, JinLidTightener 0.3 |
  | Sad | JinBrowLowerer 0.5, JinInnerBrowRaiser 0.6, JinLipCornerDepressor 0.7 |
  | Angry | JinBrowLowerer 0.9, JinLidTightener 0.6, JinNoseWrinkler 0.4 |
  | Fearful | JinInnerBrowRaiser 0.8, JinOuterBrowRaiser 0.5, JinEyesClosed 0.1, JinLipsPart 0.4 |
  | Disgusted | JinNoseWrinkler 0.7, JinLipCornerDepressor 0.5, JinCheekRaiser 0.3 |
  | Surprised | JinInnerBrowRaiser 0.9, JinOuterBrowRaiser 0.9, JinJawDrop 0.5, JinEyesClosed -0.1 |

- **Viseme palette** — a secondary tab within the face panel showing lip shape presets
  for common phoneme groups (A/Ah, E/Ih, O/Oh, U/Oo, M/B/P closed, F/V, Th, L/N/T/D).
  These are AU combinations rather than raw displacements, calibrated for the Jin
  lip geometry. Intended for use with TTS-driven lip sync authoring (future task).

- **Save expression** — adds current AU weight set to the expression library under the
  given name. Saved expressions appear in a dropdown for recall.

- **Assign to clip** — associates a saved expression with a body animation clip as
  the "entry expression" applied when the behavior timer activates. This association is
  stored in the clip record and serialized to the cultivar `<Behaviors>` element.

### 5.4 Displacer Activation Mechanism

In X_ITE, `HAnimDisplacer.weight` is a live `SFFloat` field that can be written via SAI
direct property assignment:

```javascript
var displacerNode = browser.currentScene.getNamedNode(displacerDEF);
displacerNode.weight = sliderValue;  // 0.0–1.0
```

This is confirmed working in the ManyClocks reference scene. The MCCF loader uses
the same pattern for behavior timer switching (`enabled = true/false`). The editor
uses the same pattern for expression preview.

**Note for WG review:** `HAnimDisplacer.weight` write via SAI has been confirmed
working in X_ITE (Holger Seelig, 2024). We are not aware of equivalent confirmation
for all X3D browser implementations. The export format stores displacer weights as
static `weight` attribute values for non-animated expressions, and as
`ScalarInterpolator` → ROUTE chains for animated expression transitions. Implementations
that do not support `weight` SAI writes will still receive correct static exports.

### 5.5 Animated Expression Transitions

For expressions that should transition over time (e.g. a slow smile building over 2
seconds), the author can add a `ScalarInterpolator` chain:

```xml
<ScalarInterpolator DEF="SmileInterp" key="0 0.5 1" keyValue="0.0 0.8 0.0"/>
<ROUTE fromNode="DefaultTimer" fromField="fraction_changed"
       toNode="SmileInterp" toField="set_fraction"/>
<ROUTE fromNode="SmileInterp" fromField="value_changed"
       toNode="<DisplacerDEF>" toField="weight"/>
```

The editor provides a "Animate expression" toggle per displacer that enables a
`key/keyValue` editor for the scalar interpolator, reusing the same `DefaultTimer`
or a named `ExpressionTimer`. This is an advanced feature; the simple case (static
expression at a given weight) requires no interpolator.

---

## 6. Export Format

### 6.1 HAnim X3D File Structure

The exported X3D file preserves the complete figure structure from the source file.
The editor appends/replaces only:

1. The `ImageTexture` `url` field (skin swap)
2. The `TimeSensor` block for each clip (one `<TimeSensor>` per clip)
3. The `OrientationInterpolator` block per clip per keyed joint
4. The `HAnimDisplacer` `weight` fields (static expression values; `coordIndex` and
   `displacements` are never modified)
5. `ScalarInterpolator` nodes for animated expressions
6. The `ROUTE` block (always last; regenerated completely on export)

The export preserves all existing ROUTEs from the source file and appends new clip
ROUTEs. Duplicate ROUTEs (same `fromNode/fromField/toNode/toField`) are deduplicated.

### 6.2 Cultivar XML Update

The export updates the cultivar XML with:

```xml
<Behaviors default="Default">
  <Clip name="Default" timerDEF="DefaultTimer" loop="true" priority="0"/>
  <Clip name="Walk"    timerDEF="WalkTimer"    loop="true" priority="1"/>
  <Clip name="Pitch"   timerDEF="PitchTimer"   loop="true" priority="1"
        E_min="0.6"/>
  <Clip name="Kick"    timerDEF="KickTimer"    loop="false" priority="2"
        E_min="0.8" B_max="0.3"/>
</Behaviors>

<Receptivity E="1.0" B="0.7" P="1.0" S="0.9"/>
```

The `<Receptivity>` values are authored in a separate mini-panel at the bottom of the
HAnim Editor tab (four sliders, one per channel, labelled with brief descriptions of
what each channel's receptivity controls in character terms).

### 6.3 Atomic Write

The server-side `/hanim/export` endpoint writes both files in a single handler. On
write failure of either file, neither file is updated. Both files are backed up before
write (`.bak` suffix, overwriting any previous backup).

---

## 7. Relationship to MCCF Playback System

### 7.1 Behavior Activation

The HAnim Editor produces clips consumed by `selectBehaviorClip()` and
`applyBehaviorClip()` in `mccf_x3d_loader.html` as specified in the MCCF HAnim
Behavior Activation Specification (v3.1.0). The editor is the authoring tool; the
loader is the runtime. No changes to the loader are required by this spec.

### 7.2 Loader Invariants Preserved

- All `TimeSensor` nodes exported with `enabled="false"` (loader activates via SAI)
- Timer DEF naming convention: `{ClipName}Timer`
- ROUTEs last in file
- `HAnimHumanoid` DEF: `hanim_{figureName}` (e.g. `hanim_JinLOA4`)
- `IMPORT AS` convention not affected (handled by loader at placement time)

### 7.3 New Loader Behavior (minor extension)

When `behavior_clips` includes an entry with a non-null `entry_expression` field
(expression name assigned in the editor), the loader calls `applyExpression()` at
behavior switch time in addition to `applyBehaviorClip()`. This function writes the
named expression's AU weights to the live displacer nodes via SAI. This is a one-function
addition to `mccf_x3d_loader.html`; the data contract is fully defined by the
export format above.

---

## 8. Implementation Plan

### Phase 1 — Skin Tab (1 session)
- File picker + drag-drop for texture atlas
- SAI texture swap on drop
- UV overlay rendering (SVG overlay on viewport)
- Export path for `url` update in X3D

### Phase 2 — Pose/Gesture Tab (3–4 sessions)
- Joint hierarchy panel (GET /hanim/joints)
- SAI joint rotation write (slider controls)
- Keyframe record / timeline bar
- Clip list management (name, interval, loop, priority, CV conditions)
- Live playback via TimeSensor enable/disable
- Export: OrientationInterpolator + ROUTE generation

### Phase 3 — Face Tab (2–3 sessions)
- Displacer inventory panel (GET /hanim/displacers)
- AU weight sliders with SAI write
- Ekman presets
- Expression save/recall
- Viseme palette (static presets only for Phase 3)
- Export: static weight values to X3D

### Phase 4 — Animated Expressions + Viseme (1–2 sessions)
- ScalarInterpolator chain authoring
- Animated expression export
- TTS-driven viseme sequencing (future; outside this spec)

### Phase 5 — Character Creator Integration (1 session)
- Wire as Tab 3 of `mccf_character_creator.html`
- Unified save button writes all three tabs in one `/hanim/export` call
- Cultivar selector propagates `hanim_src` to editor tab on selection

---

## 9. Notes for W3D Consortium H-Anim Working Group Review

The following items are raised for WG input before implementation begins:

**9.1 SAI weight write confirmation.** The MCCF implementation has confirmed
`HAnimDisplacer.weight` SAI write in X_ITE (2024–2026). We invite confirmation of
equivalent support in other X3D browser implementations (InstantReality, BS Contact,
X3DOM). Implementations that cannot support live `weight` writes remain correct for
static exports.

**9.2 LOA 4 joint coverage.** The Jin figure uses 146 joints (full LOA 4). The
editor's pose authoring UI is calibrated to this figure. We welcome WG guidance on
whether a reduced joint set (LOA 1 or LOA 2) would be more interoperable for clip
exchange between figures, while still supporting the MCCF behavioral vocabulary.

**9.3 Clip portability format.** We store clips as joint-relative rotations keyed
by H-Anim 2.0 standard joint names. We are not aware of an existing standard format
for portable HAnim behavioral clips. If the WG has a proposed or in-progress standard
for this, we prefer to align with it. Otherwise we propose the `<Behaviors>` element
structure in the MCCF cultivar XML (Section 6.2) as a candidate for standardization.

**9.4 FACS AU to displacer mapping.** The Jin displacer set uses FACS-inspired names
but is not a normative FACS implementation. The mapping table in Section 5.2 is
approximate. We welcome WG input on whether a normative HAnim FACS-to-displacer
binding table exists or is in development.

**9.5 UV atlas layout standardization.** The Jin figure uses a single 256×256 atlas.
The atlas layout (Section 3.2) is figure-specific and not standardized. For the
skin-swap workflow to be generically useful, a standard atlas layout for LOA 4 figures
would be valuable. We note this as a potential future standardization opportunity.

---

## 10. Architecture Invariants (complete list)

These invariants are preserved across all HAnim Editor operations and exports:

- `enabled="false"` on all `TimeSensor` nodes in exported X3D
- `{ClipName}Timer` DEF naming for all behavior timers
- ROUTEs always last in X3D file
- `coordIndex` and `displacements` on `HAnimDisplacer` nodes: never modified by editor
- `weight` on `HAnimDisplacer` nodes: modified only as SAI write (live preview) or
  static attribute value (export)
- `HAnimHumanoid` structure: never modified; editor appends only into `<X3D>` scope
  outside the `HAnimHumanoid` subtree (Timers, Interpolators, ROUTEs)
- Cultivar XML `<Behaviors>` and `<Receptivity>`: written atomically with HAnim X3D
- Clip rotations stored joint-relative (not world-space)
- `var API = 'http://localhost:5000'` — editor uses same API base as loader

---

*Specification developed in the context of the MCCF (Multi-Channel Coherence Field)
project. The MCCF project explores affective field dynamics in multi-agent X3D scenes.
HAnim Editor specification produced 2026-05-25.*
