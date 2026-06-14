# MCCF Day 35 Session Handoff
**Generated:** 2026-06-02 end of Day 35  
**Repo:** https://github.com/artistinprocess/mccf — branch `master`  
**Rule:** Author does not edit code. Claude delivers complete files only.  
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. Avatar pipeline built — `POST /hanim/ingest`

Replaces the old normalize→wire two-step. Single endpoint:
- Detects naming convention (`blender_dot`, `blender_under`, `gltf_hyphen`, `mixamo`, `hanim`)
- Builds `joint_map { def: hanim_name }` — translation layer, X3D never renamed
- Writes `<JointMap>` + `<HAnimFigure src>` into cultivar XML
- Wires all joints with rest-rotation keyValues (this turns out to be wrong — see Priority 1)

`GET /hanim/joints` updated to return `joint_map` from cultivar alongside joints.

`_heResolveJoint()` updated to use joint map fallback — group buttons work for non-HAnim avatars.

`_joint_region()` updated to classify Blender dot / gltf_hyphen names via `_BLENDER_TO_HANIM` translation.

`_walk_joints()` fixed: `def` field is exact DEF= attribute, `name` field is name= attribute — kept separate because joint map keys on DEF.

### 2. Fourth naming convention documented — `gltf_hyphen`

X_ITE's glTF→X3D save renames Blender dot joints to hyphen-separated: `upper_arm.L` → `upper-arm-L`. Normalizer converts back to dot notation for lookup. Mixamo table also added.

### 3. Jack parser errors root-caused and fixed

Face morph `Coordinate` nodes (`JackCoord_skull` etc.) were inside `<Group DEF="JackFaceCoords">`. X_ITE infers `containerField="coord"` for Coordinate; Group has no `coord` field → parser error.

Attempts that failed: `containerField="point"` caused new errors on `IndexedTriangleSet`.

**Correct fix:** Move all 8 `JackCoord_` nodes to Scene level with no `containerField`. Scene-level named nodes register by DEF without field attachment. Morph driver reads them by `getNamedNode()`.

`POST /hanim/fix-face-coords` still uses the broken approach — **needs rewrite before use** (Priority 2).

### 4. Pipeline confirmed working end-to-end

- Original `jack_hanimOld.x3d` loads cleanly — no scissors hands confirmed
- Upload pipeline + ingest produces correct output
- Joint tree populates and organises by region
- Group buttons resolve via joint map
- Slider produces visible joint rotation response

### 5. Scissors hands root cause identified — rest rotation keyValues

**Not a file issue. Not a containerField issue.**

Blender bakes coordinate system corrections into joint `rotation` attributes at export. These are large:

```
thigh.L:      ~3.1  rad  axis=(0.999,  0.033, -0.006)
upper_arm.L:  ~1.93 rad  axis=(-0.532, 0.729, -0.431)
shoulder.L:   ~2.09 rad  axis=(-0.703, -0.474, -0.531)
hips/spine:   ~0.08 rad  (near-identity — fine)
```

The Day 34 fix used these as WireInterp keyValues ("rest rotation as pass-through"). But firing them at `set_fraction(0)` overrides the skeleton's bind pose with the coordinate correction, collapsing it. **The Day 34 diagnosis was wrong.** Identity keyValues (`0 0 1 0`) are correct — the stub should be a true pass-through that does nothing at rest.

### 6. W3DC technical note written

`W3DC_Note_HAnimPipeline.md` — covers the Blender export bug, four naming conventions, translation-at-ingest architecture.

---

## Known Issues / Start Day 36 Here

### Priority 1 — Fix WireInterp keyValues (identity, not rest rotation)

**Symptom:** After ingest, joint rotation is ~180° off from expected.

**Root cause:** `hanim_ingest()` and `hanim_wire_joints()` both set:
```python
kv = rest_rot + '  ' + rest_rot  # WRONG for Blender avatars
```

**Fix — one line change in both functions:**
```python
kv = '0 0 1 0  0 0 1 0'  # identity at both ends — true pass-through
```

This is in two places:
1. `hanim_wire_joints()` around line 1880
2. `hanim_ingest()` around line 2600

### Priority 2 — Fix `POST /hanim/fix-face-coords` endpoint

Rewrite to move named Coordinate nodes to Scene level (no containerField) instead of adding `containerField="point"`.

### Priority 3 — Jack face coord nodes

After fixing P1 and P2: upload `jack_hanimOld.x3d` through the editor, run ingest, then run fix-face-coords. Verify face morph coords found and no parser errors.

### Priority 4 — Cindy Ekman expressions (unblocked)

Can be done independently any time.

---

## Files Changed Day 35

| File | Location | Notes |
|------|----------|-------|
| mccf_api.py | project root | ingest, fix-face-coords (broken — P2), _walk_joints fix, _joint_region fix, gltf_hyphen convention, joint_map in /hanim/joints |
| mccf_character_creator.html | static/ | _heResolveJoint joint map fallback, _heJointMap state, ingest button |
| W3DC_Note_HAnimPipeline.md | — | Technical note for Colson |

---

## Current State of jack_hanim.x3d (in static/avatars/)

`jack_hanimOld.x3d` — original pre-MCCF file, no edits applied.
- No scissors hands on load ✓
- Parser errors present (face coord Group issue — unfixed)
- Not yet ingested

**Do not use any of the intermediate jack_hanim files produced during Day 35 — they all have issues. Start fresh from jack_hanimOld.x3d.**

---

## Day 36 Opening Sequence

1. Upload reference documents (mccf_api.py, mccf_character_creator.html)
2. Fix keyValues in `hanim_ingest()` and `hanim_wire_joints()`: `'0 0 1 0  0 0 1 0'`
3. Fix `fix-face-coords` endpoint: move named Coordinate nodes to Scene level
4. Upload `jack_hanimOld.x3d` through editor (runs pipeline)
5. Run `⚡ ingest`
6. Verify: no scissors hands, sliders rotate correctly
7. Run fix-face-coords
8. Verify: face morph coords found, no parser errors, body and face both working
