# MCCF Day 31 Session Handoff
**Generated:** 2026-05-30 end of Day 31
**Repo:** https://github.com/artistinprocess/mccf — branch `master`
**Rule:** Author does not edit code. Claude delivers complete files only.
**Working files rule:** During a session, paste current files from local disk — do not pull from GitHub (always one session behind).

---

## What Was Accomplished Today

### 1. SAI coordinate write confirmed (carried over from Day 30 evening test)

Test harness confirmed: `node.point = new X3D.MFVec3f(...)` moves the rendered
mesh in X_ITE 10.5.2. This was the architectural prerequisite for everything
that followed.

### 2. DEF names added to Cindy's face Coordinate nodes

`cindy_hanim.x3d` now has named Coordinate nodes for all face segments:

  - CindyCoord_skull       (356 verts — drives most AUs)
  - CindyCoord_jaw         (27 verts — JawDrop, MouthStretch, ChinRaiser)
  - CindyCoord_l_eyebrow   (23 verts)
  - CindyCoord_r_eyebrow   (23 verts)
  - CindyCoord_l_eyelid    (28 verts)
  - CindyCoord_r_eyelid    (28 verts)
  - CindyCoord_l_eyeball   (31 verts)
  - CindyCoord_r_eyeball   (31 verts)

These DEF names survive normal load through the HAnim Editor (avatar/preview
route). They are stripped only if the file is re-uploaded through /avatar/upload.
If cindy_hanim.x3d is ever re-uploaded, the DEF names must be re-added.

### 3. SAI morph driver built into avatar/preview

`mccf_api.py` avatar/preview route now contains a full morph driver replacing
the defunct HAnimDisplacer/TimeSensor clock pathway.

**Architecture:**
- On scene load: reads all 8 face Coordinate nodes by DEF, caches rest pose
  as Float32Arrays
- Fetches cindy_expressions.xml from /static/avatars/ via DOMParser
- On setDisplacerWeight message: stores weight, calls _applyMorph()
- _applyMorph(): starts from rest pose copy, additively accumulates all active
  AU displacements * weights, writes result as new MFVec3f to each coord node

**Overlay:** fixed-position div in bottom-right corner of preview iframe shows:
- Coord cache status (DEF name: vertex count checkmark)
- Active AUs with bar graph and weight value
- Status line (morph driver ready / AU data loaded / coord nodes written)

Overlay font: 12px base, 260px wide. Readable without DevTools.

**postMessage interface is unchanged** — setDisplacerWeight, setJointRotation,
enableTimer, disableAllTimers all work as before. Drop-in replacement.

### 4. cindy_expressions.xml authored for all 30 AUs

Location: static/avatars/cindy_expressions.xml
Format: MCCFExpressions XML (per Day 30 spec — NOT JSON)

Structure:
  <MCCFExpressions version="1.0">
    <AU name="JinJawDrop">
      <Displacement coord="CindyCoord_jaw" coordIndex="..." vectors="..."/>
    </AU>
    ...
    <Expression name="content">
      <Weight au="JinLipCornerPuller" value="0.6"/>
    </Expression>
    ...
  </MCCFExpressions>

All 30 AUs have first-pass displacement data authored against Cindy's actual
vertex positions using bounding-box region selection. Displacements are
conservative first-pass estimates requiring interactive tuning.

Magnitudes scaled up on Day 31 pass 2 for: CheekPuffer (2.5x), LipCornerPuller
(2.0x), CheekRaiser (1.8x), LipCornerDepressor (1.8x), NoseWrinkler (2.0x),
LipsPart (2.0x), LipFunneler (2.0x), LipPuckerer (2.0x), MouthStretch (1.5x).

Expression blocks are NOT yet authored. The <Expression> section is empty.
That is Priority 1 for Day 32.

### 5. HAnim Editor face tab improvements

mccf_character_creator.html:
- Reset all button added to face tab (top right of Ekman presets section,
  red border). Zeros all AU sliders and sends weight=0 for every AU to the
  morph driver. Does not reset joint rotations.
- AU slider labels: 9px dim → 12px bold white
- AU value display: 9px → 11px bold
- Group headers (BROW, EYES & LIDS, etc.): 9px muted → 11px bold
- Slider thumb: 9px → 12px
- Slider track: 3px → 4px

### 6. W3DC technical note written

Plain text note explaining HAnimDisplacer findings, SAI morph driver
architecture, MCCFExpressions XML format, and migration path. Sent to W3DC.

---

## Confirmed Working (End of Day 31)

- All 8 face Coordinate nodes cache on scene load — all show checkmarks
- JawDrop slider moves jaw mesh visibly
- All 30 AU sliders produce mesh movement (magnitudes vary, need tuning)
- Overlay shows live AU weights with bar graphs
- Reset all button zeros sliders and returns mesh to rest pose
- Body animations (Walk/Pivot/Idle) unaffected — joint rotation pathway intact
- cindy_expressions.xml fetched and parsed via DOMParser on scene load
- Overlay status confirms "AU data loaded (30 AUs)"

---

## Start Day 32 Here

### Priority 1 — Author Expression blocks in cindy_expressions.xml

The <Expression> section is currently empty. Use the face tab sliders to dial
in each Ekman expression, then save it. The save button in the face tab
already writes to _heExpressions[]. What is NOT yet done is writing those
saved expressions back to cindy_expressions.xml.

Two sub-tasks:

  A) Wire heExport() to include expressions in the XML write. Currently
     hanim/export only writes skin, clips, and displacers. It needs to also
     write <Expression> blocks from _heExpressions[] to cindy_expressions.xml.

  B) Author the 7 base expressions interactively:
     neutral, content, happy, sad, angry, fearful, curious, surprised
     (Ekman presets are a starting point but need refinement on Cindy's mesh)

### Priority 2 — AU displacement tuning

First-pass magnitudes need interactive review. Likely candidates for adjustment:
  - Smile (LipCornerPuller) — may still be too subtle
  - CheekPuffer — direction may need adjustment (X vs Z)
  - Brow AUs — check that skull verts in brow region are correct
  - Eyelid AUs — confirm closure is complete at weight=1.0

Workflow: move slider, observe mesh, edit cindy_expressions.xml displacement
vectors directly. No code changes needed for tuning — XML only.

### Priority 3 — Wire expression lerp to phi/epsilon

Once expressions are authored:
  - phi/epsilon maps to expression name
  - Look up AU weight vector from cindy_expressions.xml
  - Lerp from current AU weights to target AU weights
  - Send updated weights via setDisplacerWeight messages

The ExpressionState element in the XML spec:
  <ExpressionState current="content" target="curious" lerp="0.3"/>

This needs a runtime handler in mccf_api.py that reads cultivar emotional
state and drives expression transitions.

### Priority 4 (cleanup) — Move cindy_expressions.xml to cultivars/

Currently served from static/avatars/ as a stopgap. Proper home is cultivars/
alongside cultivar_Cindy.xml, with a Flask route:
  GET /cultivar/<name>/expressions

The fetch URL in avatar/preview needs updating when this moves.

---

## Architecture Invariants (updated Day 31)

All Day 30 invariants hold, plus:

**SAI morph driver (new Day 31):**
- Face Coordinate nodes must have DEF names matching CindyCoord_* pattern
- Rest pose cached as Float32Array on scene load — never modified after cache
- AU blending is purely additive — no normalization, no clamping
- All 8 coord nodes written on every _applyMorph() call regardless of which
  AU changed — ensures coherent state
- MFVec3f rebuild on every write (not mutation) — required for X_ITE to
  detect the change

**cindy_expressions.xml:**
- XML only, not JSON — pipeline is XML throughout
- Lives in static/avatars/ for now (Day 32 cleanup: move to cultivars/)
- Fetched client-side by avatar/preview via DOMParser
- Two sections: <AU> geometry blocks and <Expression> weight vectors
- AU geometry authored once per mesh; Expression blocks authored interactively
- coordIndex and vectors attributes are compatible with HAnimDisplacer
  semantics — migration path is clear when X_ITE supports it

**HAnimDisplacer status:** unchanged from Day 30. Do not use.

---

## Files Changed Day 31

| File | Location | Notes |
|------|----------|-------|
| cindy_hanim.x3d | static/avatars/ | DEF names on 8 face Coordinate nodes |
| mccf_api.py | project root | SAI morph driver in avatar/preview |
| cindy_expressions.xml | static/avatars/ | All 30 AUs, no Expression blocks yet |
| mccf_character_creator.html | static/ | Reset button, larger AU slider fonts |

---

## Reference Documents (upload at session start)

- mccf_api.py — paste from local disk
- mccf_character_creator.html — paste from local disk
- cindy_hanim.x3d — paste from local disk
- cindy_expressions.xml — paste from local disk
- MCCF_HAnim_Editor_Spec.md
- MCCF_HAnim_Behavior_Activation_Spec.md
