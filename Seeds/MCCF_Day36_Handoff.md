# MCCF Day 36 Session Handoff
**Generated:** 2026-06-03 end of Day 36  
**Repo:** https://github.com/artistinprocess/mccf — branch `master`  
**Rule:** Author does not edit code. Claude delivers complete files only.  
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. P1 Fixed — WireInterp identity keyValues

`hanim_wire_joints()` (~line 1926) and `hanim_ingest()` (~line 2672) both previously used rest-rotation keyValues for the OrientationInterpolator stubs. This caused Blender avatars to snap to wrong poses on load because Blender bakes coordinate-system corrections into joint `rotation=` attributes at export.

**Fix:** Both functions now unconditionally use `'0 0 1 0  0 0 1 0'` — identity at both ends. True pass-through at rest. The old conditional `if len(parts) == 4` branch that used rest rotation is gone.

### 2. P2 Fixed — `POST /hanim/fix-face-coords` rewritten

Old approach injected `containerField="point"` via regex — this was wrong and caused new errors on `IndexedTriangleSet`.

**Fix:** Full rewrite using `ElementTree` structural moves. Builds a `parent_map` across the whole tree. For every `Coordinate` node with a `DEF` and no `containerField`, removes it from its current parent and appends it to `<Scene>` root. Scene-level named nodes register by DEF via `getNamedNode()` with no containerField attachment — exactly what the morph driver needs.

Response now includes `moved_defs` list showing which nodes were relocated.

### 3. Joint cache bug fixed — `mccf_character_creator.html`

`_hePoseJoints` was only cleared after ingest, not when switching avatars. So loading a second avatar in the same editor session reused the first avatar's joint list and never called `GET /hanim/joints` for the new file.

**Fix:** `_hePoseJoints = []` added in three places:
- `clearHAnim()` 
- `newCharacter()`
- Cultivar load (line ~2220) — when `_hanimPath` is set from `c.hanim_src`

### 4. SAI round-trip for joint rotation readback

**Root cause of slider overreaction:** Blender bakes non-identity rotations into joint `rotation=` attributes. The WireInterp has identity keyValues (correct). But when a joint is selected, sliders were initialised to identity `[0,0,1,0]` — not the joint's actual rendered state. Moving the slider from 0° fired identity which snapped joints away from their baked rest pose.

**Fix — `mccf_api.py` (preview page):** Added `getJointRotation` message handler. Reads the live `rotation` field from the named joint node via SAI and posts `{type: 'jointRotation', joint, rotation: [x,y,z,angle_rad]}` back to the parent window.

**Fix — `mccf_character_creator.html`:**
- `hePoseSelectJoint()` — if a keyframe exists for this joint at current timeline position, uses it immediately (scene already reflects it). If no keyframe, sets sliders to identity and fires `getJointRotation` to the iframe.
- New `window.addEventListener('message')` handler catches `jointRotation` response and calls `_hePoseSetSliders()` with the live scene value.

Tested against Cindy — confirmed working. Low-poly `gltf_hyphen` avatar is the next test (Day 37 Priority 1).

### 5. Avatar pipeline clarified and documented

**Correct pipeline for a new X_ITE glTF→X3D export:**
1. Export from X_ITE → save to hanim holding dir (archive copy)
2. Copy file to `static/avatars/` (or use Upload button in editor — does strip + FaceController injection too)
3. Open Character Creator → pick cultivar
4. Open HAnim Editor → load from HAnim dir (now finds file in `static/avatars/`)
5. Ingest button appears → press it → wires all joints with identity keyValues
6. Reset iframe → sliders work

**HAnim dir dropdown lists files already in `static/avatars/`** — it is not reading from the hanim holding directory. The similar naming is coincidental.

**Ingest saves:** writes back to the same filename in `static/avatars/` (atomic `os.replace`). No rename. Cultivar stores the filename in `hanim_src`.

---

## Known Issues / Start Day 37 Here

### Priority 1 — Test low-poly avatar sliders with SAI round-trip

The round-trip was confirmed working with Cindy (HAnim standard names). The low-poly uses `gltf_hyphen` naming (`shoulder-L`, `upper-arm-L`). Need to confirm:
- Slider opens at correct rest pose for `gltf_hyphen` joints
- Moving slider rotates the joint correctly
- Mirror and coupled joints work

### Priority 2 — Jack fix-face-coords

Upload `jack_hanim.x3d` through the editor, run ingest, then run `POST /hanim/fix-face-coords`. Verify:
- `moved_defs` in response lists the 8 `JackCoord_*` nodes
- No parser errors in X_ITE console
- Face morph sliders respond

### Priority 3 — Cindy Ekman expressions

Unblocked. Can be done independently.

### Priority 4 — Viewpoint mismatch between avatars

Jack loads with feet at world origin (center of view). Cindy loads with body centered. This is a `HAnimHumanoid` translation difference from the original exports — not a pipeline bug. Will matter when placing characters in a scene by cultivar position. Note for when scene composition work begins.

---

## Files Changed Day 36

| File | Notes |
|------|-------|
| `mccf_api.py` | P1: identity keyValues in `hanim_wire_joints()` and `hanim_ingest()`; P2: `fix-face-coords` rewrite; SAI: `getJointRotation` handler added to preview page |
| `mccf_character_creator.html` | Joint cache fix (`_hePoseJoints` cleared in 3 places); SAI round-trip (`hePoseSelectJoint` requests live rotation; `jointRotation` response listener) |

---

## Day 37 Opening Sequence

1. Upload current `mccf_api.py` and `mccf_character_creator.html`
2. Load low-poly avatar (`final_low_poly_character__rigged.x3d`) — already ingested in `static/avatars/`
3. Open HAnim Editor → Pose tab → select a joint → confirm slider opens at rest pose
4. Move slider → confirm figure moves correctly
5. If working: proceed to Jack face coords (Priority 2)
6. If broken: check console for `SAI write error` — likely `getNamedNode` failing on `gltf_hyphen` DEF name
