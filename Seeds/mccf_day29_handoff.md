# MCCF Day 29 Session Handoff
**Generated:** 2026-05-28 end of Day 29
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Morning Philosophy — "AI as The Pool In The Garden"
Blog post reflection on AI as mirror: systems trained on human communication inherit the statistical structure of human social interaction. Tone is a control parameter on cognition-like behavior. "Aggression introduces turbulence into the channel." The pool reflects without grasping — Tae Sung Hae as koan.

---

### 2. cindy_v6_hanim.x3d — Face Transplant Complete
**File:** `static/avatars/cindy_v6_hanim.x3d` (1967 KB)

ManyClocks' 31-AU FACS face (Carlson/Jin/Cho/Chu/Lee/Jung) grafted onto Cindy's body.

**What was done across v1→v6:**
- Extracted `hanim0_skullbase` block (lines 94-1918) from ManyClocks.x3d
- Renamed `hanim0_` → `hanim_` throughout
- Renamed `hanim_sacrum` body segment → `hanim_skull`
- Scaled all geometry: Coordinate `point` data × 0.01 (cm → meters)
- Scaled HAnimDisplacer `displacements` × 0.01
- Baked world-space offset into Transform `translation` (skullbase at y=1.3127m):
  - `new_translation = original_mc_translation × 0.01 + (0, 1.3127, -0.0154)`
- **v3→v5 lesson:** X_ITE does NOT translate geometry via HAnimJoint.center — center is rotation pivot only. Visual position comes entirely from Transform.translation.
- **v3→v5 lesson:** X_ITE only fires HAnim deformation on the PRIMARY HAnimSegment child of a joint (spec: one joint, one segment). Multiple segments under one joint = only first gets joint transform.
- **v5 structure:** Each of the 49 face segments gets its own HAnimJoint wrapper. 48 new joints added to HAnimHumanoid.joints USE list.
- **v6 addition:** Extracted from ManyClocks lines 0–93 and 1924–3292:
  - 30 `ScalarInterpolator` nodes (`AnimationAdapter_JinXXX`, key="0 0.25 0.5 0.75 1", keyValue="0 0.5 1 0.5 0")
  - 30 `TimeSensor` nodes (JinBlink_Clock, JinJawDrop_Clock, etc., all `enabled="false"`)
  - 1290 ROUTEs: `AnimationAdapter_JinXXX.value_changed` → individual displacer `.weight` fields
  - 60 ROUTEs: `JinXXX_Clock.fraction_changed` → `AnimationAdapter_JinXXX.set_fraction`

**Current state of cindy_v6:**
- Face geometry: ✅ Correct position (head at right height)
- debugDisplacers: ✅ 30/30 AnimationAdapters found, 65 displacer nodes found
- SAI setDisplacerWeight: ✅ Targets AnimationAdapter ScalarInterpolator, sets `set_fraction = weight × 0.5`
- Displacer deformation: ❌ NOT FIRING — ROUTEs exist, nodes exist, timer enable does not animate

---

### 3. mccf_api.py — setDisplacerWeight Handler Updated
**File:** `mccf_api.py`

`setDisplacerWeight` SAI handler changed from per-mesh-prefix displacer loop to AnimationAdapter pattern:
```javascript
// NEW approach
var adapter = _scene.getNamedNode('AnimationAdapter_' + auName);
adapter.getField('set_fraction').setValue(new X3D.SFFloat(weight * 0.5));
// fallback: adapter['set_fraction'] = new X3D.SFFloat(weight * 0.5);
```

`debugDisplacers` updated to report AnimationAdapter count (30/30) in addition to individual displacer count (65).

---

## The Blocking Problem — Displacer Deformation Not Firing

### What we know:
- 30/30 AnimationAdapter ScalarInterpolator nodes: ✅ found in scene
- 65 displacer nodes: ✅ found in scene  
- 1290 ROUTE connections: ✅ in file
- TimeSensor enable via SAI: ❌ no visible animation
- SAI set_fraction on AnimationAdapter: ❌ no visible deformation
- Weight slider at 0.95: ❌ no visible jaw movement

### Root cause hypothesis (strongest):
X_ITE's HAnim displacer evaluation may be tied to `HAnimHumanoid.skinCoord` — the flat vertex buffer used in LOA-4 skinned figures. In Cindy's file, the whole body uses `skinCoord` for the skeleton mesh. The face segments use per-segment `coord` fields (ManyClocks' approach). These are two different HAnim rendering pathways in X_ITE. The per-segment displacer pathway may not be active when `skinCoord` is present.

**Supporting evidence:** ManyClocks worked in X_ITE with a flat `humanoid_root → skullbase` structure and NO skinCoord, NO body mesh — pure per-segment coords. Cindy has a full LOA-4 skinCoord body. The difference is the rendering architecture, not the ROUTE wiring.

### Paths forward (Priority 1):

**Option A — Two-Humanoid approach (most promising):**
Add ManyClocks as a SECOND standalone `HAnimHumanoid` in the Cindy scene file, positioned at head height using a `Transform`. The face humanoid gets its own minimal skeleton (humanoid_root → skullbase only, as in original ManyClocks), its own AnimationAdapters and ROUTEs. The body animation runs on Cindy's humanoid; face deformation runs on the ManyClocks humanoid. They share the same Transform to stay co-located.

**Option B — X_ITE issue tracker:**
File a minimal reproducible case: ManyClocks face segments + Cindy's body in one HAnimHumanoid → displacers don't fire. Ask Holger Seelig (X_ITE author) directly whether per-segment HAnimDisplacer is supported when skinCoord is also present.

**Option C — skinCoord bridge:**
Add the face mesh vertices to Cindy's existing skinCoord flat buffer, with HAnimJoint skin weights = 1.0 for the face joints. This is spec-compliant but requires remapping all ManyClocks vertex indices into Cindy's global coord array. Major data transformation.

---

## Bug Found Today — Behavior Buttons in Character Creator

**Symptom:** In the main Character Creator screen (not HAnim Editor), the Kick, Yaw, Pitch, Roll, Walk, Run, Jump behavior buttons do NOT fire. They work correctly in the HAnim Editor.

**Likely cause:** The behavior button click handlers in the main Character Creator are using a different SAI path or iframe reference than the HAnim Editor's `enableTimer` handler. The HAnim Editor overlay has direct access to the X_ITE iframe; the main screen's buttons may be targeting a stale reference or a different element ID.

**Files to check:** `static/mccf_character_creator.html` — look for the behavior button onClick handlers and compare the postMessage target with the HAnim Editor's button handlers.

---

## Current File State

| File | Status | Notes |
|------|--------|-------|
| `mccf_api.py` | ✅ Updated Day 29 | AnimationAdapter SAI handler, updated debugDisplacers |
| `static/avatars/cindy_v6_hanim.x3d` | ✅ Updated Day 29 | Full face transplant + AnimationAdapter infrastructure |
| `static/mccf_character_creator.html` | ✅ Unchanged from Day 28 | Behavior buttons broken in main screen |
| `mccf_cultivar_lambda.py` | ✅ Unchanged | Day 26 version |
| `mccf_x3d_loader.html` | ✅ Unchanged | Day 26 version |

---

## Start Day 30 Here

### Priority 1 — Fix displacer deformation (Option A recommended)
Build `cindy_v7_hanim.x3d`: Insert stripped ManyClocks HAnimHumanoid as second humanoid in scene, wrapped in `<Transform translation="0 1.3127 -0.0154">` to co-locate with Cindy's head. The face humanoid has its own `humanoid_root → skullbase` chain, its own AnimationAdapters and ROUTEs. No skinCoord conflict.

Steps:
1. Strip ManyClocks down to: Scene wrapper, TimeSensors, ScalarInterpolators, bare HAnimHumanoid (humanoid_root → skullbase → all 49 face segments), AnimationAdapter ROUTEs
2. Wrap in `<Transform translation="0 1.3127 -0.0154" scale="0.01 0.01 0.01">` (removing the per-segment scaling since the outer transform handles it — need to revert segment coord scaling)
3. Embed as second humanoid in Cindy's scene after her HAnimHumanoid
4. The SAI handler targets `AnimationAdapter_JinXXX` in whichever humanoid has them — node lookup by DEF still works across multiple humanoids in X_ITE

**NOTE:** If using outer Transform scale="0.01 0.01 0.01", the Coordinate point data and displacements should NOT be pre-scaled. Revert to raw ManyClocks values.

### Priority 2 — Fix behavior buttons in main Character Creator screen
Paste `mccf_character_creator.html` from local disk for diagnosis.

### Priority 3 — W3DC submission note
When face deformation works, compile the edit list for submission back to web3d.org. The note should cover:
- Scale normalization (cm → meters, 0.01 factor)
- HUD strip procedure
- Joint restructuring (one joint per segment requirement in X_ITE)
- AnimationAdapter ROUTE infrastructure requirement
- X_ITE SAI patterns that work (getField('set_fraction').setValue() vs direct property)
- Two-humanoid architecture if that's the solution

---

## Architecture Invariants (updated Day 29)

- `enabled=true/false` is the ONLY SAI mechanism for behavior timers in X_ITE
- `Timer_N.isActive=true` → Walk; `fraction_changed>=0.99` → Default
- ϕ written only by `arc/record`; ϵ written only by `apply_expressive_delta()`
- Trust modifies `strength_eff`, never agent state
- Salience stored in history, never applied to ϕ or ϵ directly
- `TimeSensor` DEF convention: `{ClipName}Timer`
- ROUTEs MUST be last in X3D scene file — enforced by `_write_clip_nodes()`
- All behavior Timers: `enabled="false"` in HAnim X3D file
- `var API = 'http://localhost:5000'` in all HTML files
- HAnim export writes both X3D and cultivar XML atomically via `.tmp` + `os.replace()`
- **X_ITE SAI type constructors** (`SFRotation`, `SFVec3f`, `SFFloat` etc.) live on the imported `X3D` **module**, not on browser or scene instance
- **X_ITE `getBrowser()`** must be called inside the canvas `load` event, not synchronously
- **HAnim USE nodes**: skip any `HAnimJoint` with a `USE` attribute when walking hierarchy tree — double-count trap
- **HAnimDisplacer SAI**: use `_scene.getNamedNode(DEF)` with full DEF string; tree walking on `_scene.rootNodes` does NOT work on SAI proxies
- **Python 3.14 f-strings**: `{{`/`}}` for JS braces, `\\n` for JS newlines in string literals
- **X_ITE HAnim geometry positioning**: `HAnimJoint.center` is rotation pivot ONLY — does NOT translate geometry. Visual position comes from `Transform.translation` inside HAnimSegment.
- **X_ITE HAnim deformation**: only fires on the PRIMARY (first) HAnimSegment child of a joint. Multiple segments under one joint = only first gets deformation.
- **ManyClocks AnimationAdapter pattern**: `ScalarInterpolator` key="0 0.25 0.5 0.75 1" keyValue="0 0.5 1 0.5 0". Set `set_fraction = weight × 0.5` to get static weight. ROUTEs fan `value_changed` → all mesh displacer `.weight` fields.
- **ManyClocks scale**: raw geometry in centimeters. Scale factor 0.01 to convert to Cindy's meters.
- **X_ITE displacer hypothesis**: per-segment HAnimDisplacer may not fire when HAnimHumanoid.skinCoord is present (LOA-4 body). Two-humanoid architecture may be required.

---

## Reference Documents (upload at session start if needed)

- `MCCF_HAnim_Editor_Spec.md` — full Phase 2/3 design
- `MCCF_HAnim_Behavior_Activation_Spec.md` — behavior system spec
- `MCCF_Relational_Dynamics_Extension_Spec.md` — Relational Dynamics spec
- `mccf_api.py` — current server (paste from local disk, not GitHub)
- `mccf_cultivar_lambda.py` — cultivar model
- `static/mccf_character_creator.html` — HAnim editor UI (paste from local disk)
- `static/avatars/cindy_v6_hanim.x3d` — current avatar with face transplant
- `static/avatars/ManyClocks.x3d` — Jin's original file with 31 FACS displacers
