# MCCF Day 27 Session Handoff
**Generated:** 2026-05-26 end of Day 27
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.

---

## What Was Accomplished Today

### 1. HAnim Export Endpoints — implemented and confirmed working
**File:** `mccf_api.py`

Two new endpoints added:

**`POST /hanim/skin_upload`**
- Receives `{cultivar, data_url}` (base64 PNG or JPEG)
- Saves to `static/avatars/<cultivar_slug>_skin.png`
- Returns `{status, path}`
- Confirmed working: `{"status":"ok","path":"/static/avatars/test_skin.png"}`

**`POST /hanim/export`**
- Receives full editor payload: `{cultivar, hanim_src, skin_url, receptivity, expressions, clips, displacers}`
- Handles data URL skin inline (no separate skin_upload call needed)
- Updates `ImageTexture url` in HAnim X3D (prefers DEF containing `TextureAtlas`)
- Collects existing ROUTEs, strips from tree, re-appends last (ROUTE-last invariant enforced)
- Writes `TimeSensor` + `OrientationInterpolator` nodes for each clip (empty in Phase 1)
- Parses cultivar XML via `CultivarDefinition.from_xml()`, updates `hanim_src`, `receptivity`, `behavior_clips`, serialises via `.to_xml()`
- Atomic dual-write: `.tmp` files → `os.replace()` rename; `.bak` backup before any write
- Confirmed working: `{"status":"ok","clips_written":0,"routes_written":2352,"skin_updated":false}`

**Helper functions added** (all prefixed `_hanim_` / `_b64` / `_shutil_hanim` to avoid collisions):
`_hanim_base_dir`, `_avatar_dir`, `_cultivar_xml_path`, `_hanim_x3d_path`, `_hanim_backup`,
`_parse_x3d_file`, `_serialise_x3d`, `_update_image_texture_url`,
`_collect_routes`, `_remove_routes`, `_find_scene_el`, `_write_clip_nodes`

---

### 2. GET /hanim/joints — implemented and confirmed working
**File:** `mccf_api.py`

```
GET /hanim/joints?src=<hanim_src>
```

Returns flat depth-first array of joint descriptors:
```json
{
  "joints": [
    { "name": "humanoid_root", "def": "hanim_humanoid_root",
      "center": [0.0, 0.9149, 0.0], "parent": null, "region": "spine" },
    ...
  ],
  "count": 146,
  "src": "cindy_hanim.x3d"
}
```

**Key implementation notes:**
- Skips `USE` reference nodes (`<HAnimJoint USE="..."/>`) — these are the flat joint inventory on `HAnimHumanoid` and would double-count all 146 joints. Classic X3D trap.
- Handles both namespaced (`{https://www.web3d.org/...}HAnimJoint`) and non-namespaced elements
- Handles both direct nesting and `<skeleton>/<children>` container patterns (LOA 4)
- `_joint_region()` classifies joints using `_SPINE_JOINTS` set + `l_`/`r_` prefix + anatomical keyword matching to correctly distinguish arm from leg joints
- Confirmed: 146 joints, correct hierarchy, correct region assignment

**Bugs found and fixed during testing:**
1. Double-count (292 joints) — walker descended into both direct children AND container wrappers simultaneously. Fix: recurse unconditionally into all children; the non-joint wrapper branch handles containers transparently.
2. Still 292 — `USE` reference nodes being counted. Fix: `if el.get('USE'): return` at top of `_walk_joints`.

---

### 3. avatar/preview — path normalisation + SAI listener
**File:** `mccf_api.py`

**Path fix:** `avatar_preview()` now normalises `src` param to always resolve to `/static/avatars/`:
- `'cindy_hanim.x3d'` → `/static/avatars/cindy_hanim.x3d`
- `'avatars/cindy_hanim.x3d'` → `/static/avatars/cindy_hanim.x3d`
- `'/static/avatars/...'` → unchanged

**SAI postMessage listener** added to preview page using correct X_ITE v10 module pattern:

```javascript
import X3D from 'https://cdn.jsdelivr.net/npm/x_ite@10.5.2/dist/x_ite.min.mjs';
// getBrowser() called inside canvas 'load' event — not synchronously
_browser = X3D.getBrowser(canvas);
_scene   = _browser.currentScene;
// SFRotation lives on X3D module, NOT on browser instance
node.rotation = new X3D.SFRotation(r[0], r[1], r[2], r[3]);
```

**Critical X_ITE SAI invariant** (learned the hard way):
> SAI type constructors (`SFRotation`, `SFVec3f`, `SFColor`, `MFVec3f`, etc.) live on the **imported `X3D` module object**, not on the browser or scene instance. X_ITE is polymorphic (handles X3D, VRML, glTF) — the type system is on the module, not the runtime.

Confirmed working: `SAI ready — scene nodes: 13` in preview console.

**Message types handled:**
- `setJointRotation` — `{joint: DEF, rotation: [ax, ay, az, angle_rad]}`
- `enableTimer` — `{timerDEF: DEF}`
- `disableAllTimers` — stops known timer DEFs

---

### 4. HAnim Editor Phase 2 — Pose/Gesture tab live
**File:** `mccf_character_creator.html`

Replaced Phase 2 stub panel with fully working pose/gesture authoring UI.

**Joint hierarchy tree (left panel)**
- Loads from `GET /hanim/joints` on first tab switch via `hePoseInit()`
- Grouped into 5 collapsible regions: spine, left arm, right arm, left leg, right leg
- Filter input for quick joint search
- Event delegation on tree container (no inline onclick — avoids all quote-escaping issues)
- Selected joint highlighted green, touched joints shown with accent dot
- Tooltip shows DEF + center coordinates

**Rotation controls (right panel)**
- Four sliders: X axis, Y axis, Z axis (-1.0 to 1.0), Angle (-180° to +180°)
- Every slider change fires `hePoseSendSAI()` → `postMessage` to X_ITE iframe → **confirmed moving figure**
- Mirror button: negates Z axis for bilateral joints (`l_hip` ↔ `r_hip`)
- Reset: returns selected joint to identity `[0, 0, 1, 0]`
- Joint name display updates on selection

**Clip management**
- Default clip created on init
- Add/delete clips
- Name, cycle interval, priority, loop props
- Dropdown selector

**Keyframe timeline**
- Click to set `t` position (0.0–1.0)
- Keyframe markers rendered and draggable
- Add keyframe at current `t` — records current slider state for selected joint
- Delete keyframe (anchors at t=0 and t=1 protected)
- Preview button fires `enableTimer` SAI message

**Export integration**
- `heExport()` fully replaced — passes `_heClips` array to `/hanim/export`
- Phase 2 clips now flow through to X3D writer

**Bugs fixed during testing:**
1. `Uncaught SyntaxError: invalid escape sequence` — pre-existing `\(Natural\)` and `\.x3d$` in regex literals flagged by Firefox strict mode. Fixed: `[(]Natural[)]` and `[.]x3d$`.
2. Joint selection highlight not persisting — `hePoseSelectJoint` was calling `hePoseRenderTree` on every slider move. Fixed: decouple; only add `.touched` class directly on slider change.
3. Joint click not firing — inline `onclick="hePoseSelectJoint('...')"` quote escaping broken. Fixed: `data-jname` attribute + event delegation.
4. `TypeError: cannot use 'dict' as a set element` — `{{'Content-Type': 'text/html'}}` inside f-string returned as set literal in Python 3.14. Fixed: moved outside f-string.
5. `_browser.SFRotation is not a constructor` — SFRotation is on `X3D` module not browser. Fixed: `new X3D.SFRotation(...)`.

---

## Start Day 28 Here

### Interface design discussion — grabbers and body-part grouping

Joint-by-joint rotation is working but tedious for practical pose authoring. Day 28 priority is improving the authoring workflow. Two approaches to discuss and design:

**Option 1 — Body-part group presets (lower cost, immediate)**
- Region preset buttons above joint tree: spine, l-arm, r-arm, l-leg, r-leg, face
- Selecting a group selects the primary joint AND applies coupled slider behaviour
- e.g. "head nod" → drives `skullbase + vc7 + vc4` together with coupling ratios
- Pure JS in the editor — no X3D changes needed
- Covers 90% of pose authoring needs

**Option 2 — TouchSensor click-to-select on figure (moderate cost)**
- Inject invisible zone geometry + `TouchSensor` nodes over body regions into the live scene via SAI `createNode` at load time
- Click torso → selects spine group; click left arm → selects `l_shoulder`
- SAI `createNode` pattern confirmed available; requires generating overlay geometry
- One session to implement properly

**Option 3 — PlaneSensor drag handles (future spec)**
- Visible handle spheres at key joints (wrists, elbows, head, hips)
- `PlaneSensor` drag → approximate IK to distribute rotation across joint chain
- 2–3 sessions; candidate for WG submission / spec item

**Recommended Day 28 order:** Option 1 first (fast, immediately useful), then design Option 2.

### Also queued for Day 28+

- **Villain model design** — blog post "MCCF: Modeling Villains" reviewed Day 27. Key extensions identified:
  - Villain cultivar profile: divergence suppression coefficient
  - Attractor depth as scene metric (basin depth per agent in arc history)
  - Coercion gradient: villain links reduce `receptivity` in neighbouring agents
  - Redemption arc: high-salience perturbation exceeding suppression coefficient

- **HAnim Editor Phase 3** — displacer weight authoring (FACS AU → X3D HAnimDisplacer)

---

## Current File State

| File | Status | Notes |
|------|--------|-------|
| `mccf_api.py` | ✅ Deployed | +723 lines from Day 26: joints, export, skin_upload, SAI preview |
| `mccf_character_creator.html` | ✅ Deployed | Phase 2 pose tab live; SAI rotation confirmed working |
| `mccf_cultivar_lambda.py` | ✅ Unchanged | Day 26 version |
| `mccf_x3d_loader.html` | ✅ Unchanged | Day 26 version |

---

## Architecture Invariants (updated)

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
- **X_ITE SAI type constructors** (`SFRotation`, `SFVec3f`, etc.) live on the imported `X3D` **module**, not on browser or scene instance. Use `new X3D.SFRotation(x,y,z,a)`.
- **X_ITE `getBrowser()`** must be called inside the canvas `load` event, not synchronously
- **HAnim USE nodes**: `HAnimHumanoid.joints` field contains `USE` references to every joint — skip any `HAnimJoint` with a `USE` attribute when walking the hierarchy tree or you double-count

---

## Reference Documents (upload at session start if needed)

- `MCCF_HAnim_Editor_Spec.md` — full Phase 2/3 design
- `MCCF_HAnim_Behavior_Activation_Spec.md` — behavior system spec
- `MCCF_Relational_Dynamics_Extension_Spec.md` — Relational Dynamics spec
- `mccf_api.py` — current server
- `mccf_cultivar_lambda.py` — cultivar model
- `mccf_character_creator.html` — HAnim editor UI
