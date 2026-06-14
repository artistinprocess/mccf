# MCCF Day 28 Session Handoff
**Generated:** 2026-05-27 end of Day 28
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Body-Part Group Presets — Option 1 (complete)
**File:** `static/mccf_character_creator.html`

Region preset button row added above joint tree in Pose tab:
**spine / l arm / r arm / l leg / r leg / head / face / solo**

- Buttons highlight green when active; "coupled" badge appears in section label
- Each group drives a primary joint; coupled joints follow at scaled ratios
- Negative ratios handle antagonist pairs (knee bends opposite to hip)
- **head** and **face** buttons switch to the Face tab automatically
- Face tab shows group bar: "head/face group active · ← pose" back button
- `heRegionClear()` / solo button kills group mode and hides all badges

**Coupling table `_HE_GROUP_PRESETS`** — all tunable without code changes:
- spine: `vc7` primary → vc4 (0.7), vc2 (0.5), skullbase (0.3), vt12 (0.4), vt10 (0.3)
- left_arm: `l_shoulder` → l_elbow (0.6), l_wrist (0.3)
- right_arm: `r_shoulder` → r_elbow (0.6), r_wrist (0.3)
- left_leg: `l_hip` → l_knee (-0.5), l_ankle (0.25)
- right_leg: `r_hip` → r_knee (-0.5), r_ankle (0.25)
- head: `skullbase` → vc1 (0.5), vc2 (0.35), vc3 (0.2)
- face: `skullbase` → l/r eyeball (0.8), l/r eyelid (0.6), l/r eyebrow (0.4), temporomandibular (0.3)

**Bug fixed:** head/face presets originally used `skull` as primary — Cindy's skeleton
terminates at `skullbase` with no separate `skull` node. Fixed after joint inventory query.

**Confirmed working:** joint rotation SAI fires correctly for all body groups on Cindy.

---

### 2. Phase 3 Face Tab — AU Sliders (complete, pending displacer-equipped avatar)
**File:** `static/mccf_character_creator.html`

**AU table completed** — all 31 AUs from Jin/Colson's ManyClocks.x3d:
- Previously 23 AUs; added JinSquint, JinUpperLidRaiser, JinUpperLipRaiser, JinWink,
  JinMouthStretch, JinLipPuckerer, JinLipTightener, JinLipSuck (corrected from stub)

**Human-readable labels** — the HAnim spec was designed by medical professionals;
mortals now see "Smile", "Frown", "Blink", "Jaw drop" etc. with FACS code as tooltip.
FACS DEF name still in `data-au` attribute for SAI call.

**Grouped sections:** brow / eyes & lids / nose & cheeks / mouth & lips

**Ekman presets:** Neutral, Happy, Sad, Angry, Fearful, Disgusted, Surprised —
all fire `setDisplacerWeight` SAI messages on apply.

**`heAssignToClip()` now works** — records `auWeights` into keyframe at current `t`
on the active clip. Was stub "available in Phase 2" — Phase 2 is live, fixed.

**Export payload** — `displacers` array now populated from `_heAuWeights` (non-zero
weights only) on both export calls.

---

### 3. SAI `setDisplacerWeight` Handler — mccf_api.py
**File:** `mccf_api.py`

New message type added to `avatar/preview` SAI listener:

```javascript
{ type: 'setDisplacerWeight', au: 'JinBlink', weight: 0.75 }
```

Uses `_scene.getNamedNode(DEF)` with known mesh prefixes from Jin's file:
`Lower_teeth`, `Center_lower_vermillion_lip`, `Hair`, `__0`, `__2`, `__4`,
`Head`, `Face`, `Body`, `Skin`, `upper_teeth`, `tongue`

Uses `new X3D.SFFloat(weight)` — same SAI pattern as `SFRotation` for joints.

**`debugDisplacers` diagnostic message** added:
```javascript
document.getElementById('he-xite-frame')
  .contentWindow.postMessage({type:'debugDisplacers'}, '*')
```
Logs all resolvable displacer DEF names to the iframe console. Run this when
testing a new avatar to discover its actual prefix conventions.

**`_update_displacer_weights(scene_el, displacers)`** — Python helper added to
`/hanim/export` endpoint. Iterates all `HAnimDisplacer` elements, matches by AU
name suffix, writes `weight` attribute. Returns count updated.
Response now includes `displacers_updated` field.

---

### 4. Phase 3 Status — Blocked on Displacer-Equipped Avatar

**Root cause:** Cindy (`cindy_hanim.x3d`) and Jin (`jin_hanim.x3d`) are
skeleton-only HAnim figures with no `HAnimDisplacer` nodes.

**ManyClocks.x3d** (Colson's file) has 31 fully-baked FACS displacers but:
- Upload fails HTTP 400 — it's a full scene file, not a bare `HAnimHumanoid`
- John Carlson: "good luck putting that head on anything" — displacer `coordIndex`
  and `displacements` are baked to ManyClocks' specific mesh vertex layout;
  can't be transplanted without re-mapping every index

**Paths forward (pick one at session start):**
1. **Hand-edit ManyClocks** — strip to bare `HAnimHumanoid`, fix the 400, load
   in editor. Tedious but doable; author has done it before. X_ITE editor can
   validate X3D. Note: displacers stay valid as long as the mesh topology is
   preserved.
2. **X_ITE visual editor** — attach Jin's head (with displacers) to a body in
   the X_ITE editor UI. May be fastest path.
3. **Search W3DC examples** — check web3d.org HAnim examples archive for any
   other figures with displacer nodes. If none exist, we are at the bleeding
   edge of X3D HAnim authoring.
4. **Defer** — mark Phase 3 face tab as "pending displacer-equipped avatar",
   move to TouchSensor click-to-select (Option 2) or event sequencer.

**X_ITE does support displacers** — confirmed in spec. The gap is authoring,
not rendering.

---

### 5. Python 3.14 F-String Bugs — Running List (add to X3D_KNOWN_ISSUES or new PYTHON314_GOTCHAS.md)

All bugs occur inside Flask f-string HTML templates (`f"""..."""`):

| Bug | Symptom | Fix |
|-----|---------|-----|
| `{ }` in JS object literals | `TypeError: unsupported format string` at Flask render | Double to `{{ }}` |
| `\n` in JS string literals | `SyntaxError: Invalid or unexpected token` in browser | Use `\\n` |
| Regex `\(` `\.` in JS | Firefox strict mode `SyntaxError` | Use `[(]` `[.]` |
| `{{'key': 'val'}}` in f-string | Python interprets as set literal | Move dict outside f-string |

**Validator recommended:** render the f-string and pipe extracted JS through
Node.js `--check` before server start. Catches all of these in one pass.

---

## Start Day 29 Here

### Priority 1 — Resolve displacer-equipped avatar (see options above)

### Priority 2 — TouchSensor click-to-select on figure (Option 2)
Per Day 27 handoff design:
- Inject invisible zone geometry + `TouchSensor` nodes over body regions into
  live scene via SAI `createNode` at load time
- Click torso → selects spine group; click left arm → selects `l_shoulder`
- SAI `createNode` pattern confirmed available in X_ITE
- One session to implement properly

### Priority 3 — Event Sequencer (TBD design)
Per Day 28 discussion: camera sequencer + lighting sequencer + music sequencer
(mp3/wav/midi) — grouped into single tabbed event sequencer module.
Relates to jaminate dope sheet concept from John Carlson's W3DC response.
MCCF sequential nested groups (River of Life heritage) map naturally to this.

### Also queued
- **Villain model design** — divergence suppression coefficient, attractor depth
  as scene metric, coercion gradient, redemption arc
- **HAnim Phase 3** — fully ready, waiting on avatar with displacers
- **MCCF Challenge** — single-prompt X3D generation challenge to other AI labs
  (spec after reference implementation is airtight)

---

## Current File State

| File | Status | Notes |
|------|--------|-------|
| `mccf_api.py` | ✅ Updated Day 28 | setDisplacerWeight SAI, debugDisplacers, _update_displacer_weights, displacers_updated in export response |
| `static/mccf_character_creator.html` | ✅ Updated Day 28 | Group presets, face tab AU sliders complete, human-readable labels, heAssignToClip live |
| `mccf_cultivar_lambda.py` | ✅ Unchanged | Day 26 version |
| `mccf_x3d_loader.html` | ✅ Unchanged | Day 26 version |

---

## Architecture Invariants (updated Day 28)

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
- **X_ITE SAI type constructors** (`SFRotation`, `SFVec3f`, `SFFloat` etc.) live on
  the imported `X3D` **module**, not on browser or scene instance
- **X_ITE `getBrowser()`** must be called inside the canvas `load` event, not synchronously
- **HAnim USE nodes**: skip any `HAnimJoint` with a `USE` attribute when walking
  hierarchy tree — double-count trap
- **HAnimDisplacer SAI**: use `_scene.getNamedNode(DEF)` with full DEF string;
  tree walking on `_scene.rootNodes` does NOT work on SAI proxies
- **Python 3.14 f-strings**: `{{`/`}}` for JS braces, `\\n` for JS newlines in
  string literals — stricter than earlier Python versions

---

## Reference Documents (upload at session start if needed)

- `MCCF_HAnim_Editor_Spec.md` — full Phase 2/3 design
- `MCCF_HAnim_Behavior_Activation_Spec.md` — behavior system spec
- `MCCF_Relational_Dynamics_Extension_Spec.md` — Relational Dynamics spec
- `mccf_api.py` — current server (paste from local disk, not GitHub)
- `mccf_cultivar_lambda.py` — cultivar model
- `static/mccf_character_creator.html` — HAnim editor UI (paste from local disk)
- `static/avatars/ManyClocks.x3d` — Jin's file with 31 FACS displacers (if working on face)
