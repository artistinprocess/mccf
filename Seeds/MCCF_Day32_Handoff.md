# MCCF Day 32 Session Handoff
**Generated:** 2026-05-31 end of Day 32
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. New avatar pipeline established — Blender → glTF → X3D → MCCF

The full pipeline from Blender export to live facial animation in MCCF is
now proven and working. The workflow:

  Blender → export glTF → convert in Sunrize → jack_hanim.x3d
  → mccf_avatar_pipeline scripts → jack_hanim.x3d (with face coord nodes)
  + jack_expressions.xml (with AU displacement data)
  → load in HAnim Editor → face sliders produce visible mesh deformation

This pipeline is repeatable for any rigged Blender avatar. The only
per-avatar human work is interactive AU displacement tuning. All
structural work is automated.

### 2. Jack avatar processed end-to-end

Input: final_low_poly_character__riggedX3D.x3d (from Blender via Sunrize)
- 1715 total skin verts, monolithic HAnim skin mesh
- Full skeleton including finger joints
- Two separate eyeball Shape nodes

Face region assignment (head skinCoordWeight > 0.5 filter):

| DEF Name              | Verts | Notes |
|-----------------------|-------|-------|
| JackCoord_skull       | 298   | Y≥5.47, head-owned |
| JackCoord_jaw         | 173   | Y<5.46, head-owned — lower face/lips/chin |
| JackCoord_l_eyebrow   |  45   | Y 5.62–5.82, Z>0.40 |
| JackCoord_r_eyebrow   |  44   | symmetric |
| JackCoord_l_eyelid    |  34   | Y 5.46–5.67, Z>0.55 |
| JackCoord_r_eyelid    |  34   | symmetric |
| JackCoord_r_eyeball   | 169   | local coords, Sphere_1 |
| JackCoord_l_eyeball   | 169   | local coords, Sphere-001_1 |

Key lesson: bounding-box region assignment must filter by head
skinCoordWeight > 0.5 first. Raw Y-position filtering includes
chest/shoulder/neck verts that HAnim skinning dominates, making
morphs imperceptible. The weight filter is mandatory for all
future avatars.

### 3. Global-index morph driver implemented and working

Jack uses a monolithic skin mesh (_3) unlike Cindy's separate face
segments. The morph driver was extended to support both modes:

SEGMENT mode (Cindy): writes directly to named face Coordinate nodes
  which are themselves rendered geometry.

GLOBAL mode (Jack): named Coordinate nodes (JackCoord_*) are metadata
  holders in the head HAnimSegment. Each carries a globalIndices
  attribute mapping local verts to global _3 indices. The morph driver
  accumulates all AU displacements and writes the full _3 array back.

Critical fix: the morph driver navigates to the skin coord node via
  HAnimHumanoid.skin[] field (the rendered Shape), NOT via
  getNamedNode('_3'). Writing to the DEF node does not trigger X_ITE
  re-render; writing to the node the IndexedTriangleSet references does.
  _skinCoordNode is resolved at scene load and cached.

### 4. AU name mapping resolved

The character creator face tab uses the Cindy/Jin naming convention
with -er/-or suffixes (JinLipCornerPuller, JinNoseWrinkler, JinDimpler).
Our first-pass expressions XML used simplified names. Full mapping
now locked in jack_expressions.xml — 29 AUs all confirmed firing.

Confirmed working from console/overlay testing:
  JinBlink, JinJawDrop, JinLipCornerPuller, JinLipCornerDepressor,
  JinLidDroop, JinLidTightener, JinSquint, JinBrowLower,
  JinInnerBrowRaise, JinOuterBrowRaise, JinNoseWrinkler,
  JinCheekRaiser, JinCheekPuffer, JinLipFunneler, JinLipPuckerer,
  JinLipStretcher, JinLipSuck, JinLipsPart, JinMouthStretch,
  JinLowerLipDepressor, JinDimpler, and others

### 5. mccf_api.py avatar/preview — avatar-agnostic morph driver

The preview route is now fully avatar-agnostic:
- Derives expressions filename from src URL (jack → jack_expressions.xml)
- Discovers face coord DEF names via *FaceCoords group pattern
- Auto-detects SEGMENT vs GLOBAL mode from globalIndices attributes
- Falls back to Cindy pattern if no FaceCoords group found
- Cindy unaffected — segment mode unchanged

### 6. Pipeline scripts (keep in tools/ or project root)

| Script | Purpose |
|--------|---------|
| analyze_head_verts.py | Spatial analysis of head joint verts |
| assign_face_regions.py | Region boundary tuning and validation |
| build_jack_x3d.py | Generates *_hanim.x3d with face coord nodes |
| build_jack_expressions.py | Generates *_expressions.xml stub |

These will be consolidated into mccf_avatar_pipeline.py (Day 33 task).

---

## Start Day 33 Here

### Priority 1 — Wire heExport() to write Expression blocks

POST /hanim/export currently writes skin, clips, and displacers.
It needs to also write <Expression> blocks from _heExpressions[]
to the avatar's expressions XML (cindy_expressions.xml or
jack_expressions.xml).

Sub-tasks:
  A) Update hanim/export route to include expression blocks in XML write
  B) Author 7 base Ekman expressions interactively for Cindy:
     neutral, content, happy, sad, angry, fearful, curious, surprised
     (use face tab sliders, save, export)
  C) Then do the same for Jack

### Priority 2 — Wire expression lerp to phi/epsilon

Once expressions are authored:
- phi/epsilon maps to expression name
- Look up AU weight vector from expressions XML
- Lerp from current AU weights to target AU weights
- Send updated weights via setDisplacerWeight messages

ExpressionState element:
  <ExpressionState current="content" target="curious" lerp="0.3"/>

Needs runtime handler in mccf_api.py reading cultivar emotional state
and driving expression transitions.

### Priority 3 — Consolidate pipeline into single CLI tool

  python3 mccf_avatar_pipeline.py input.x3d AvatarName

Outputs: avatarname_hanim.x3d + avatarname_expressions.xml
One command. Repeatable for any Blender avatar.

The key parameter to tune per-avatar: head skinCoordWeight threshold
(currently 0.5). Most avatars will use 0.5 but dense meshes may need
adjustment. Make this a CLI flag.

### Priority 4 — AU displacement tuning for Jack

First-pass magnitudes are working but need refinement:
- JawDrop: currently too aggressive at high weights
- LipCornerPuller (Smile): subtle, may need 2x magnitude
- Brows: check that falloff centers are correct for Jack's brow arch
- Eyelids: verify closure is complete at weight=1.0

Workflow: slider → observe → edit jack_expressions.xml vectors → reload.
No code changes needed.

### Priority 5 (later) — Skin mapping

Postponed. Separate creative pipeline:
  AI image generator → UV-mapped texture → atlas (256x256, face in
  upper-left quadrant) → applied via HAnim Editor skin tab.

Note for when this session arrives: Jack has vertex colors baked in
(<Color> node in IndexedTriangleSet). These may fight the texture.
May need to remove Color node or set colorPerVertex="false" in X_ITE.

### Priority 6 (later) — Move expressions XML to cultivars/

Currently served from static/avatars/ as stopgap.
Proper home: cultivars/ alongside cultivar_Cindy.xml
Flask route: GET /cultivar/<name>/expressions
Update fetch URL in avatar/preview when this moves.

---

## Architecture Invariants (updated Day 32)

All Day 31 invariants hold, plus:

**Global-index morph driver (Jack):**
- JackCoord_* nodes are metadata holders, NOT rendered geometry
- globalIndices attribute maps local vert index to global _3 index
- globalIndices='local' on eyeballs: write to that node directly
- _skinCoordNode resolved via HAnimHumanoid.skin[] at scene load
- Rest pose of _3 cached as Float32Array — never modified after cache
- Every _applyMorph() writes full _3 array (1715 verts)
- MFVec3f rebuild on every write — required for X_ITE to detect change

**Region assignment rule (all future avatars):**
- Filter head joint skinCoordIndex by skinCoordWeight > 0.5 FIRST
- Then apply spatial bounding-box rules within that filtered set
- Raw position filtering without weight filter will include
  chest/neck/shoulder bleed-through that HAnim skinning dominates

**AU naming convention (face tab standard):**
- Suffix: -er/-or (JinLipCornerPuller, JinNoseWrinkler, JinDimpler)
- Bilateral: no L/R suffix for face tab sliders (JinBrowLower not
  JinBrowLowererL/R) — the bilateral AU applies to both sides
- The expressions XML must use these exact names

**File naming convention:**
- avatarname_hanim.x3d → static/avatars/
- avatarname_expressions.xml → static/avatars/ (later: cultivars/)
- DEF pattern: [AvatarName]Coord_[region]
- FaceCoords group: [AvatarName]FaceCoords

---

## Files Changed Day 32

| File | Location | Notes |
|------|----------|-------|
| jack_hanim.x3d | static/avatars/ | Face coord nodes, globalIndices, eyeball DEFs |
| jack_expressions.xml | static/avatars/ | 29 AUs, correct face-tab names, first-pass displacements |
| mccf_api.py | project root | Avatar-agnostic morph driver, global/segment mode |

---

## Reference Documents (upload at session start)

- mccf_api.py — paste from local disk
- mccf_character_creator.html — paste from local disk
- jack_hanim.x3d — paste from local disk
- jack_expressions.xml — paste from local disk
- cindy_hanim.x3d — paste from local disk (for expression export work)
- cindy_expressions.xml — paste from local disk
- MCCF_HAnim_Editor_Spec.md
- MCCF_HAnim_Behavior_Activation_Spec.md
